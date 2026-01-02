"""标签棋子识别模块

在透视矫正后的棋盘上（默认800x800）检测1-32号棋子标签，并输出8x8的piece_id矩阵。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


@dataclass
class TagDetection:
    marker_id: int
    row: int
    col: int
    center: List[float]
    area: float
    corners: List[List[float]]
    score: float
    decode_margin: float
    border_penalty: float


@dataclass
class TagDetectResult:
    board_ids: List[List[int]]
    detections: List[TagDetection]
    overlay_path: Optional[Path]
    warnings: List[str]
    conflict_log: List[Dict[str, float]]


def detect_piece_tags(
    warped_board: np.ndarray,
    frame_idx: int,
    output_dir: Path,
    allowed_ids: Optional[List[int]] = None,
    min_area_ratio: float = 0.0005,
    tag_size_mm: float = 3.0,
    expected_square_mm: float = 50.0,
    denoise: bool = True,
) -> TagDetectResult:
    """检测矫正棋盘上的棋子标签，并输出8x8矩阵。

    兼顾两条路径：增强+去噪 和 自适应阈值，按有效检测数量择优。
    冲突处理规则：
    - 同一格子保留得分最高的标签
    - 同一个ID仅保留得分最高的所在格
    """

    try:
        from cv2 import aruco
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "OpenCV缺少aruco模块，请安装opencv-contrib-python"
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)

    if allowed_ids is None:
        allowed_ids = list(range(1, 33))

    warnings: List[str] = []

    size = warped_board.shape[0]
    cell = size / 8.0
    min_area = size * size * min_area_ratio

    gray = cv2.cvtColor(warped_board, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    equalized = cv2.equalizeHist(gray)
    processed_base = cv2.fastNlMeansDenoising(enhanced, None, 7, 7, 21) if denoise else enhanced

    # 强反光检测：高亮区域占比过大时，额外尝试阈值化路径
    highlight_ratio = float((gray > 235).mean())
    adaptive = cv2.adaptiveThreshold(
        processed_base,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        15,
        2,
    )
    otsu_val, otsu = cv2.threshold(equalized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if highlight_ratio > 0.25:
        warnings.append(f"High glare ratio {highlight_ratio:.2f}, trying threshold path")

    processed_candidates: List[Tuple[str, np.ndarray, float]] = [
        ("enhanced", processed_base, 1.0),
        ("upsampled", cv2.resize(processed_base, None, fx=1.4, fy=1.4, interpolation=cv2.INTER_CUBIC), 1.4),
        ("upsampled2", cv2.resize(processed_base, None, fx=1.8, fy=1.8, interpolation=cv2.INTER_CUBIC), 1.8),
        ("threshold", adaptive, 1.0),
        ("otsu", otsu, 1.0),
    ]

    aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_5X5_100)
    params = aruco.DetectorParameters()
    params.minMarkerPerimeterRate = 0.014
    params.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX
    params.cornerRefinementWinSize = 4
    detector = aruco.ArucoDetector(aruco_dict, params)

    best_key = None
    best_detections: List[TagDetection] = []
    debug_candidates: Dict[str, List[TagDetection]] = {}

    for name, processed, scale in processed_candidates:
        dets = _detect_on_candidate(
            detector=detector,
            processed=processed,
            scale=scale,
            allowed_ids=allowed_ids,
            min_area=min_area,
            cell=cell,
            size=size,
        )
        debug_candidates[name] = dets

        unique_ids = len({d.marker_id for d in dets})
        total_score = sum(d.score for d in dets)
        best_unique = len({d.marker_id for d in best_detections})
        best_score = sum(d.score for d in best_detections)
        if (
            unique_ids > best_unique
            or (unique_ids == best_unique and len(dets) > len(best_detections))
            or (unique_ids == best_unique and len(dets) == len(best_detections) and total_score > best_score)
            or (not best_detections and dets)
        ):
            best_detections = dets
            best_key = name

    if best_key == "threshold":
        warnings.append("阈值化路径自动启用，可能存在反光")
    if highlight_ratio > 0.02:
        warnings.append("检测到高光区域，建议调整光源和俯拍角度")

    expected_tag_px = cell * (tag_size_mm / max(expected_square_mm, 1e-3))
    if expected_tag_px < 6:
        warnings.append(
            f"标签在画面中过小(估计 {expected_tag_px:.1f}px)，建议靠近拍摄或提高分辨率"
        )

    conflict_log: List[Dict[str, float]] = []

    # Step1: 同一格子仅保留得分最高
    best_by_cell: Dict[Tuple[int, int], TagDetection] = {}
    for det in best_detections:
        key = (det.row, det.col)
        prev = best_by_cell.get(key)
        if prev is None or det.score > prev.score:
            if prev is not None:
                conflict_log.append(
                    {
                        "reason": "cell",
                        "cell": key,
                        "kept_id": prev.marker_id,
                        "discarded_id": det.marker_id,
                        "kept_score": prev.score,
                        "discarded_score": det.score,
                    }
                )
            best_by_cell[key] = det
        else:
            conflict_log.append(
                {
                    "reason": "cell",
                    "cell": key,
                    "kept_id": prev.marker_id,
                    "discarded_id": det.marker_id,
                    "kept_score": prev.score,
                    "discarded_score": det.score,
                }
            )

    # Step2: 同一个ID仅保留最佳格子
    best_by_id: Dict[int, TagDetection] = {}
    for det in best_by_cell.values():
        prev = best_by_id.get(det.marker_id)
        if prev is None or det.score > prev.score:
            if prev is not None:
                conflict_log.append(
                    {
                        "reason": "id",
                        "marker_id": det.marker_id,
                        "kept_cell": (prev.row, prev.col),
                        "discarded_cell": (det.row, det.col),
                        "kept_score": prev.score,
                        "discarded_score": det.score,
                    }
                )
            best_by_id[det.marker_id] = det
        else:
            conflict_log.append(
                {
                    "reason": "id",
                    "marker_id": det.marker_id,
                    "kept_cell": (prev.row, prev.col),
                    "discarded_cell": (det.row, det.col),
                    "kept_score": prev.score,
                    "discarded_score": det.score,
                }
            )

    board_ids = [[0 for _ in range(8)] for _ in range(8)]
    final_dets = list(best_by_id.values())
    for det in final_dets:
        board_ids[det.row][det.col] = det.marker_id

    overlay_path = output_dir / f"overlay_{frame_idx + 1:04d}.png"
    overlay = _draw_overlay(warped_board, final_dets, cell)
    cv2.imwrite(str(overlay_path), overlay)

    _save_visual_pack(
        overlay=overlay,
        board_ids=board_ids,
        detections=final_dets,
        frame_idx=frame_idx,
        debug_root=output_dir.parent,
    )

    avg_side = _average_side_length(final_dets)
    expected_px = (tag_size_mm / expected_square_mm) * cell if expected_square_mm else 0
    if avg_side and avg_side < max(8, expected_px * 0.8):
        warnings.append(
            f"标签在画面中边长仅 {avg_side:.1f}px，期望至少 {expected_px:.1f}px，可能过小导致误检"
        )

    return TagDetectResult(
        board_ids=board_ids,
        detections=final_dets,
        overlay_path=overlay_path,
        warnings=warnings,
        conflict_log=conflict_log,
    )


def _detect_on_candidate(
    detector,
    processed: np.ndarray,
    scale: float,
    allowed_ids: List[int],
    min_area: float,
    cell: float,
    size: int,
) -> List[TagDetection]:
    corners_list, ids, _ = detector.detectMarkers(processed)
    detections: List[TagDetection] = []
    if ids is None:
        return detections

    for marker_corners, marker_id in zip(corners_list, ids.flatten()):
        marker_id = int(marker_id)
        if marker_id not in allowed_ids:
            continue

        corners_scaled = marker_corners[0].astype(np.float32) / scale
        area = float(cv2.contourArea(corners_scaled))
        if area < min_area:
            continue

        center = corners_scaled.mean(axis=0)
        col = int(np.clip(center[0] // cell, 0, 7))
        row = int(np.clip(center[1] // cell, 0, 7))

        border_penalty = _calc_border_penalty(corners_scaled, size)
        decode_margin = _calc_decode_margin(corners_scaled)
        score = area * (1 - border_penalty) * decode_margin

        detections.append(
            TagDetection(
                marker_id=marker_id,
                row=row,
                col=col,
                center=[float(center[0]), float(center[1])],
                area=area,
                corners=corners_scaled.tolist(),
                score=score,
                decode_margin=decode_margin,
                border_penalty=border_penalty,
            )
        )

    return detections


def _draw_overlay(image: np.ndarray, detections: List[TagDetection], cell_size: float) -> np.ndarray:
    overlay = image.copy()
    try:
        from cv2 import aruco
    except ImportError:  # pragma: no cover
        return overlay

    if detections:
        corners = [np.array(det.corners, dtype=np.float32) for det in detections]
        ids = np.array([det.marker_id for det in detections], dtype=np.int32).reshape(-1, 1)
        aruco.drawDetectedMarkers(overlay, corners, ids)

    # 画网格
    size = overlay.shape[0]
    for i in range(9):
        pos = int(i * cell_size)
        cv2.line(overlay, (pos, 0), (pos, size), (0, 255, 0), 1)
        cv2.line(overlay, (0, pos), (size, pos), (0, 255, 0), 1)

    for det in detections:
        center = (int(det.center[0]), int(det.center[1]))
        cv2.circle(overlay, center, 6, (255, 0, 0), -1)
        label = f"ID {det.marker_id} ({det.score:.1f})"
        cv2.putText(
            overlay,
            label,
            (center[0] - 20, center[1] - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 255),
            2,
        )

    return overlay


def _save_visual_pack(
    overlay: np.ndarray,
    board_ids: List[List[int]],
    detections: List[TagDetection],
    frame_idx: int,
    debug_root: Path,
) -> None:
    """输出易验证的可视化包。"""

    debug_root.mkdir(parents=True, exist_ok=True)
    tag_overlay_path = debug_root / f"tag_overlay_{frame_idx + 1:04d}.png"
    cv2.imwrite(str(tag_overlay_path), overlay)

    zoom = cv2.resize(overlay, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    cv2.imwrite(str(debug_root / f"tag_overlay_zoom_{frame_idx + 1:04d}.png"), zoom)

    grid_img = _draw_grid_table(board_ids)
    cv2.imwrite(str(debug_root / f"tag_grid_{frame_idx + 1:04d}.png"), grid_img)

    missing = [pid for pid in range(1, 33) if pid not in np.array(board_ids).flatten()]
    missing_txt = debug_root / f"tag_missing_ids_{frame_idx + 1:04d}.txt"
    missing_txt.write_text("\n".join(map(str, missing)) if missing else "None", encoding="utf-8")

    missing_img = np.full((180, 360, 3), 30, dtype=np.uint8)
    cv2.putText(missing_img, "Missing IDs:", (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    cv2.putText(
        missing_img,
        ", ".join(map(str, missing)) if missing else "None",
        (20, 120),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (255, 200, 200),
        2,
    )
    cv2.imwrite(str(debug_root / f"tag_missing_ids_{frame_idx + 1:04d}.png"), missing_img)

    # 为首帧保留老名字兼容旧报告
    if frame_idx == 0:
        cv2.imwrite(str(debug_root / "tag_overlay.png"), overlay)
        cv2.imwrite(str(debug_root / "tag_overlay_zoom.png"), zoom)
        cv2.imwrite(str(debug_root / "tag_grid.png"), grid_img)
        cv2.imwrite(str(debug_root / "tag_missing_ids.png"), missing_img)
        (debug_root / "tag_missing_ids.txt").write_text(missing_txt.read_text(encoding="utf-8"), encoding="utf-8")


def _draw_grid_table(board_ids: List[List[int]]) -> np.ndarray:
    cell_px = 80
    img = np.full((cell_px * 8, cell_px * 8, 3), 30, dtype=np.uint8)
    for r in range(8):
        for c in range(8):
            top_left = (c * cell_px, r * cell_px)
            bottom_right = ((c + 1) * cell_px, (r + 1) * cell_px)
            color = (70, 70, 70) if (r + c) % 2 == 0 else (50, 50, 50)
            cv2.rectangle(img, top_left, bottom_right, color, -1)
            cv2.rectangle(img, top_left, bottom_right, (120, 180, 255), 1)
            pid = board_ids[r][c]
            if pid:
                cv2.putText(
                    img,
                    str(pid),
                    (top_left[0] + 10, top_left[1] + cell_px // 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (255, 255, 255),
                    2,
                )
    return img


def _calc_border_penalty(corners: np.ndarray, size: int) -> float:
    min_border = float(
        min(
            np.min(corners[:, 0]),
            size - np.max(corners[:, 0]),
            np.min(corners[:, 1]),
            size - np.max(corners[:, 1]),
        )
    )
    safe_margin = max(size / 100.0, 1.0)
    if min_border >= safe_margin:
        return 0.0
    return float(max(0.0, 1.0 - min_border / safe_margin))


def _calc_decode_margin(corners: np.ndarray) -> float:
    side_lengths = [
        np.linalg.norm(corners[i] - corners[(i + 1) % 4]) for i in range(4)
    ]
    max_len = max(side_lengths) if side_lengths else 1.0
    min_len = min(side_lengths) if side_lengths else 1.0
    squareness = min_len / (max_len + 1e-6)
    return float(max(0.1, min(1.0, squareness)))


def _average_side_length(detections: List[TagDetection]) -> float:
    if not detections:
        return 0.0
    perimeters = []
    for det in detections:
        corners = np.array(det.corners, dtype=np.float32)
        lengths = [np.linalg.norm(corners[i] - corners[(i + 1) % 4]) for i in range(4)]
        perimeters.append(sum(lengths))
    if not perimeters:
        return 0.0
    return float(np.mean(perimeters) / 4.0)
