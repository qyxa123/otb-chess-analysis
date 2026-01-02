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
    """
    检测矫正棋盘上的棋子标签，并输出8x8矩阵。

    Args:
        warped_board: 透视矫正后的棋盘（正方形）
        frame_idx: 帧索引用于命名
        output_dir: 输出overlay目录
        allowed_ids: 允许的标签ID列表（默认1-32）
        min_area_ratio: 过滤面积占比阈值
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

    size = warped_board.shape[0]
    cell = size / 8.0
    min_area = size * size * min_area_ratio

    gray = cv2.cvtColor(warped_board, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    noise_reduced = cv2.fastNlMeansDenoising(enhanced, None, 7, 7, 21) if denoise else enhanced

    # 强反光检测：高亮区域占比过大时，额外尝试阈值化路径
    highlight_ratio = float((gray > 235).mean())
    reflection_path = None
    if highlight_ratio > 0.02:
        adaptive = cv2.adaptiveThreshold(
            noise_reduced,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            15,
            2,
        )
        reflection_path = adaptive

    processed_candidates: List[Tuple[str, np.ndarray, float]] = [
        ("enhanced", noise_reduced, 1.0),
        ("upsampled", cv2.resize(noise_reduced, None, fx=1.4, fy=1.4, interpolation=cv2.INTER_CUBIC), 1.4),
    ]
    if reflection_path is not None:
        processed_candidates.append(("reflection", reflection_path, 1.0))

    aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    params = aruco.DetectorParameters()
    params.minMarkerPerimeterRate = 0.015
    params.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX
    params.cornerRefinementWinSize = 3
    detector = aruco.ArucoDetector(aruco_dict, params)

    detections: List[TagDetection] = []
    conflict_log: List[Dict[str, float]] = []

    for name, processed, scale in processed_candidates:
        corners_list, ids, _ = detector.detectMarkers(processed)
        if ids is None:
            continue
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

    expected_tag_px = cell * (tag_size_mm / max(expected_square_mm, 1e-3))
    warnings: List[str] = []
    if expected_tag_px < 6:
        warnings.append(
            f"标签在画面中过小(估计 {expected_tag_px:.1f}px)，建议靠近拍摄或提高分辨率"
        )
    if reflection_path is not None:
        warnings.append("检测到高光反射，已启用自适应阈值路径")

    # 先对相同ID保留得分最高的检测
    best_by_id: Dict[int, TagDetection] = {}
    for det in detections:
        prev = best_by_id.get(det.marker_id)
        if prev is None or det.score > prev.score:
            best_by_id[det.marker_id] = det
        elif prev is not None:
            conflict_log.append({
                "marker_id": det.marker_id,
                "kept_score": prev.score,
                "discarded_score": det.score,
            })

    # 再对同一格子保留面积最大的检测
    best_by_cell: Dict[tuple, TagDetection] = {}
    for det in best_by_id.values():
        key = (det.row, det.col)
        prev = best_by_cell.get(key)
        if prev is None or det.score > prev.score:
            best_by_cell[key] = det
        elif prev is not None:
            conflict_log.append({
                "cell": key,
                "kept_id": prev.marker_id,
                "discarded_id": det.marker_id,
                "kept_score": prev.score,
                "discarded_score": det.score,
            })

    board_ids = [[0 for _ in range(8)] for _ in range(8)]
    final_dets = list(best_by_cell.values())
    for det in final_dets:
        board_ids[det.row][det.col] = det.marker_id

    overlay_path = output_dir / f"overlay_{frame_idx:04d}.png"
    overlay = _draw_overlay(warped_board, final_dets, cell)
    cv2.imwrite(str(overlay_path), overlay)

    return TagDetectResult(
        board_ids=board_ids,
        detections=final_dets,
        overlay_path=overlay_path,
        warnings=warnings,
        conflict_log=conflict_log,
    )


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
