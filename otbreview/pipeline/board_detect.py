#!/usr/bin/env python3
"""
棋盘定位与透视矫正模块
功能：检测棋盘边界，进行透视变换
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, Dict


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
    
    需要4个ArUco标记（ID: 0, 1, 2, 3）分别位于棋盘四角
    """
    id_to_corner = detect_aruco_corners(frame)
    
    if id_to_corner is None:
        print("  警告: 未检测到足够的ArUco标记，fallback到纯视觉检测")
        return _detect_without_markers(frame)
    
    # 使用ArUco标记进行透视变换
    warped = warp_board(frame, id_to_corner)
    
    # 生成网格覆盖图（用于调试）
    grid_img = frame.copy()
    for marker_id, corners in id_to_corner.items():
        # 绘制标记边界
        corners_int = corners.astype(np.int32)
        cv2.polylines(grid_img, [corners_int], True, (0, 255, 0), 3)
        # 绘制标记中心
        center = corners.mean(axis=0).astype(int)
        cv2.circle(grid_img, tuple(center), 10, (255, 0, 0), -1)
        # 标记ID
        cv2.putText(grid_img, str(marker_id), tuple(center), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    return warped, grid_img


def detect_aruco_corners(image: np.ndarray) -> Optional[Dict[int, np.ndarray]]:
    """
    检测ArUco标记并返回ID到角点的映射
    
    Args:
        image: 输入图像
    
    Returns:
        如果检测到4个标记（ID: 0,1,2,3），返回 {id: corners} 字典
        否则返回None
    """
    try:
        from cv2 import aruco
    except ImportError:
        print("  错误: OpenCV未安装aruco模块，请升级opencv-contrib-python")
        return None
    
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    params = aruco.DetectorParameters()
    detector = aruco.ArucoDetector(aruco_dict, params)
    
    corners, ids, _ = detector.detectMarkers(gray)
    
    if ids is None or len(ids) < 4:
        return None
    
    id_to_corner = {}
    for i, marker_id in enumerate(ids.flatten()):
        id_to_corner[int(marker_id)] = corners[i][0]
    
    # 只关心 0, 1, 2, 3
    if not all(k in id_to_corner for k in [0, 1, 2, 3]):
        return None
    
    return id_to_corner


def warp_board(image: np.ndarray, id_to_corner: Dict[int, np.ndarray], size: int = 800) -> np.ndarray:
    """
    使用ArUco标记进行透视变换
    
    Args:
        image: 输入图像
        id_to_corner: ArUco标记ID到角点的映射
        size: 输出棋盘尺寸（正方形）
    
    Returns:
        透视矫正后的棋盘图像
    """
    def center(corners: np.ndarray) -> np.ndarray:
        """计算标记中心点"""
        return corners.mean(axis=0)
    
    # 源点：4个标记的中心点
    # 顺序：左上(0), 右上(1), 右下(2), 左下(3)
    src = np.array([
        center(id_to_corner[0]),  # top-left
        center(id_to_corner[1]),  # top-right
        center(id_to_corner[2]),  # bottom-right
        center(id_to_corner[3]),  # bottom-left
    ], dtype=np.float32)
    
    # 目标点：正方形四个角
    dst = np.array([
        [0, 0],
        [size, 0],
        [size, size],
        [0, size],
    ], dtype=np.float32)
    
    # 计算透视变换矩阵
    M = cv2.getPerspectiveTransform(src, dst)
    
    # 执行透视变换
    warped = cv2.warpPerspective(image, M, (size, size))
    
    return warped


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


def detect_and_warp_board_debug(
    frame_path: str,
    use_markers: bool = True,
    output_dir: Optional[str] = None,
    frame_idx: int = 0
) -> Tuple[bool, Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray]]:
    """
    检测棋盘并执行透视矫正（Debug版本）
    
    Args:
        frame_path: 输入帧路径
        use_markers: 是否使用ArUco标记
        output_dir: 输出目录
        frame_idx: 帧索引（用于命名）
    
    Returns:
        (success, warped_board, preview_image, grid_overlay_image)
        success: 是否成功检测到4个标记
        warped: 矫正后的棋盘（800x800）
        preview: ArUco检测预览图（原图+标记框）
        grid: 网格覆盖图（warped+8x8网格）
    """
    frame = cv2.imread(frame_path)
    if frame is None:
        return False, None, None, None
    
    if not use_markers:
        return False, None, None, None
    
    # 检测ArUco标记
    id_to_corner = detect_aruco_corners(frame)
    
    if id_to_corner is None:
        return False, None, None, None
    
    # 使用ArUco标记进行透视变换
    warped = warp_board(frame, id_to_corner, size=800)
    
    # 生成ArUco预览图（原图+标记框）
    preview_img = frame.copy()
    for marker_id, corners in id_to_corner.items():
        # 绘制标记边界（绿色）
        corners_int = corners.astype(np.int32)
        cv2.polylines(preview_img, [corners_int], True, (0, 255, 0), 3)
        # 绘制标记中心（红色圆点）
        center = corners.mean(axis=0).astype(int)
        cv2.circle(preview_img, tuple(center), 15, (0, 0, 255), -1)
        # 标记ID（白色文字）
        cv2.putText(preview_img, f"ID:{marker_id}", 
                   (center[0] - 20, center[1] - 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)
    
    # 生成网格覆盖图（在warped上画8x8网格）
    grid_img = warped.copy()
    cell_size = 800 // 8  # 100像素每格
    
    # 画垂直线
    for i in range(9):
        x = i * cell_size
        cv2.line(grid_img, (x, 0), (x, 800), (0, 255, 0), 2)
    
    # 画水平线
    for i in range(9):
        y = i * cell_size
        cv2.line(grid_img, (0, y), (800, y), (0, 255, 0), 2)
    
    # 保存矫正后的棋盘
    if output_dir is not None:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        output_file = output_path / f"warp_{frame_idx+1:04d}.png"
        cv2.imwrite(str(output_file), warped)
    
    return True, warped, preview_img, grid_img

