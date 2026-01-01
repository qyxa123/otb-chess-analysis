#!/usr/bin/env python3
"""
棋子/占用识别模块
功能：识别每个格子的占用状态（empty/white/black）
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple


def detect_pieces(
    warped_board: np.ndarray,
    frame_idx: int,
    output_dir: str
) -> Dict[str, any]:
    """
    检测棋盘上的棋子
    
    Args:
        warped_board: 矫正后的棋盘图像
        frame_idx: 帧索引
        output_dir: 输出目录（保存每格切片）
    
    Returns:
        包含8x8格子状态的字典
        {
            'occupancy': [[0/1/2, ...], ...],  # 0=空, 1=白, 2=黑
            'confidence': [[float, ...], ...],  # 每格的置信度
            'cells': [[cell_image, ...], ...]   # 每格的图像（可选）
        }
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    h, w = warped_board.shape[:2]
    cell_h = h // 8
    cell_w = w // 8
    
    occupancy = []
    confidence = []
    cells = []
    
    for row in range(8):
        occ_row = []
        conf_row = []
        cell_row = []
        
        for col in range(8):
            # 提取格子区域（留边距避免边界干扰）
            margin = 2
            y1 = row * cell_h + margin
            y2 = (row + 1) * cell_h - margin
            x1 = col * cell_w + margin
            x2 = (col + 1) * cell_w - margin
            
            cell = warped_board[y1:y2, x1:x2]
            
            # 分析格子内容
            occ, conf = _classify_cell(cell)
            
            occ_row.append(occ)
            conf_row.append(conf)
            cell_row.append(cell)
            
            # 保存格子图像（用于调试）
            cell_filename = output_path / f"frame{frame_idx:04d}_r{row}_c{col}.jpg"
            cv2.imwrite(str(cell_filename), cell)
        
        occupancy.append(occ_row)
        confidence.append(conf_row)
        cells.append(cell_row)
    
    return {
        'occupancy': occupancy,
        'confidence': confidence,
        'cells': cells  # 可选，用于调试
    }


def _classify_cell(cell: np.ndarray) -> Tuple[int, float]:
    """
    分类单个格子：empty(0) / white(1) / black(2)
    
    Returns:
        (occupancy, confidence)
    """
    if cell.size == 0:
        return 0, 0.0
    
    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY) if len(cell.shape) == 3 else cell
    
    # 计算平均亮度
    mean_brightness = np.mean(gray)
    
    # 计算颜色方差（判断是否有内容）
    brightness_std = np.std(gray)
    
    # 简单阈值分类
    # TODO: 可以改进为更复杂的分类器
    
    if brightness_std < 10:  # 方差很小，可能是空格子或均匀背景
        # 进一步判断：如果亮度中等，可能是空格子
        if 80 < mean_brightness < 180:
            return 0, 0.7  # 空格子，中等置信度
        else:
            # 可能是纯色背景，需要更多信息
            return 0, 0.5
    
    # 有内容，根据亮度判断颜色
    if mean_brightness > 140:
        return 1, min(0.9, brightness_std / 50.0)  # 白色棋子
    elif mean_brightness < 100:
        return 2, min(0.9, brightness_std / 50.0)  # 黑色棋子
    else:
        # 中等亮度，可能是空格子或特殊棋子
        return 0, 0.6

