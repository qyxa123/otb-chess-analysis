"""标签棋子识别模块

在透视矫正后的棋盘上（默认800x800）检测1-32号棋子标签，并输出8x8的piece_id矩阵。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

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


@dataclass
class TagDetectResult:
    board_ids: List[List[int]]
    detections: List[TagDetection]
    overlay_path: Optional[Path]


def detect_piece_tags(
    warped_board: np.ndarray,
    frame_idx: int,
    output_dir: Path,
    allowed_ids: Optional[List[int]] = None,
    min_area_ratio: float = 0.0005,
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
    aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    detector = aruco.ArucoDetector(aruco_dict, aruco.DetectorParameters())

    corners_list, ids, _ = detector.detectMarkers(gray)

    detections: List[TagDetection] = []
    if ids is not None:
        for marker_corners, marker_id in zip(corners_list, ids.flatten()):
            marker_id = int(marker_id)
            if marker_id not in allowed_ids:
                continue

            corners = marker_corners[0].astype(np.float32)
            area = float(cv2.contourArea(corners))
            if area < min_area:
                continue

            center = corners.mean(axis=0)
            col = int(np.clip(center[0] // cell, 0, 7))
            row = int(np.clip(center[1] // cell, 0, 7))

            detections.append(
                TagDetection(
                    marker_id=marker_id,
                    row=row,
                    col=col,
                    center=[float(center[0]), float(center[1])],
                    area=area,
                    corners=corners.tolist(),
                )
            )

    # 先对相同ID保留面积最大的检测
    best_by_id: Dict[int, TagDetection] = {}
    for det in detections:
        prev = best_by_id.get(det.marker_id)
        if prev is None or det.area > prev.area:
            best_by_id[det.marker_id] = det

    # 再对同一格子保留面积最大的检测
    best_by_cell: Dict[tuple, TagDetection] = {}
    for det in best_by_id.values():
        key = (det.row, det.col)
        prev = best_by_cell.get(key)
        if prev is None or det.area > prev.area:
            best_by_cell[key] = det

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
        label = f"ID {det.marker_id} -> r{det.row}c{det.col}"
        cv2.putText(
            overlay,
            label,
            (center[0] - 20, center[1] - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 255),
            2,
        )

    return overlay
