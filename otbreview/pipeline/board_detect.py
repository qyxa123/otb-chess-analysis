#!/usr/bin/env python3
"""
棋盘定位与透视矫正模块
功能：检测棋盘边界，进行透视变换
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple


def detect_and_warp_board(
    frame_path: str,
    use_markers: bool = False,
    output_dir: Optional[str] = None
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """
    检测棋盘并执行透视矫正
    
    Args:
        frame_path: 输入帧路径
        use_markers: 是否使用ArUco/AprilTag标记
        output_dir: 输出目录（保存矫正后的棋盘）
    
    Returns:
        (warped_board, grid_overlay_image) 或 (None, None) 如果失败
    """
    frame = cv2.imread(frame_path)
    if frame is None:
        return None, None
    
    if use_markers:
        warped, grid_img = _detect_with_markers(frame)
    else:
        warped, grid_img = _detect_without_markers(frame)
    
    if warped is not None and output_dir is not None:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        frame_name = Path(frame_path).stem
        output_file = output_path / f"{frame_name}_warped.jpg"
        cv2.imwrite(str(output_file), warped)
    
    return warped, grid_img


def _detect_with_markers(frame: np.ndarray) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """
    使用ArUco标记检测棋盘四角
    """
    # TODO: 实现ArUco检测
    # 使用 cv2.aruco.detectMarkers
    # 找到4个标记，提取角点，计算透视变换矩阵
    
    # 临时fallback到无标记方法
    return _detect_without_markers(frame)


def _detect_without_markers(frame: np.ndarray) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
    """
    不使用标记，通过棋盘边界检测
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # 边缘检测
    edges = cv2.Canny(gray, 50, 150)
    
    # 查找轮廓
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # 找到最大的矩形轮廓（假设是棋盘）
    board_contour = None
    max_area = 0
    
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < max_area:
            continue
        
        # 近似为多边形
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
        
        # 如果是四边形
        if len(approx) == 4:
            board_contour = approx
            max_area = area
    
    if board_contour is None:
        # 如果找不到四边形，使用整个图像
        h, w = frame.shape[:2]
        board_contour = np.array([
            [0, 0],
            [w, 0],
            [w, h],
            [0, h]
        ], dtype=np.float32)
    else:
        board_contour = board_contour.reshape(4, 2).astype(np.float32)
    
    # 确定四个角点的顺序（左上、右上、右下、左下）
    board_contour = _order_points(board_contour)
    
    # 计算目标尺寸（假设棋盘是正方形，使用最大边长）
    (tl, tr, br, bl) = board_contour
    width_a = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
    width_b = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
    height_a = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
    height_b = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
    
    max_width = max(int(width_a), int(width_b))
    max_height = max(int(height_a), int(height_b))
    
    # 使用较大的尺寸作为正方形边长
    size = max(max_width, max_height)
    
    # 目标点（正方形）
    dst = np.array([
        [0, 0],
        [size, 0],
        [size, size],
        [0, size]
    ], dtype=np.float32)
    
    # 计算透视变换矩阵
    M = cv2.getPerspectiveTransform(board_contour, dst)
    
    # 执行透视变换
    warped = cv2.warpPerspective(frame, M, (size, size))
    
    # 生成网格覆盖图（用于调试）
    grid_img = frame.copy()
    cv2.drawContours(grid_img, [board_contour.astype(np.int32)], -1, (0, 255, 0), 3)
    for pt in board_contour:
        cv2.circle(grid_img, tuple(pt.astype(int)), 10, (255, 0, 0), -1)
    
    return warped, grid_img


def _order_points(pts: np.ndarray) -> np.ndarray:
    """
    将四个点按顺序排列：左上、右上、右下、左下
    """
    # 初始化结果数组
    rect = np.zeros((4, 2), dtype=np.float32)
    
    # 左上角点：x+y最小
    # 右下角点：x+y最大
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # 左上
    rect[2] = pts[np.argmax(s)]  # 右下
    
    # 右上角点：x-y最小
    # 左下角点：x-y最大
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # 右上
    rect[3] = pts[np.argmax(diff)]  # 左下
    
    return rect

