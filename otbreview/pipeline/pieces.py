#!/usr/bin/env python3
"""
棋子/占用识别模块
功能：识别每个格子的占用状态（empty/light/dark）
支持自动校准和KMeans聚类
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from sklearn.cluster import KMeans
import json


def detect_pieces_auto_calibrate(
    warped_board: np.ndarray,
    frame_idx: int,
    output_dir: str,
    calibration_data: Optional[Dict] = None
) -> Tuple[Dict[str, any], Optional[Dict]]:
    """
    检测棋盘上的棋子（自动校准版本）
    
    Args:
        warped_board: 矫正后的棋盘图像（800x800）
        frame_idx: 帧索引（0表示第一帧，用于校准）
        output_dir: 输出目录
        calibration_data: 校准数据（None表示需要校准）
    
    Returns:
        (board_state, new_calibration_data)
        board_state: {
            'occupancy': [[0/1/2, ...], ...],  # 0=empty, 1=light, 2=dark
            'confidence': [[float, ...], ...],
            'labels': [['empty'/'light'/'dark', ...], ...]
        }
        new_calibration_data: 如果frame_idx==0，返回校准数据
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    h, w = warped_board.shape[:2]
    cell_h = h // 8
    cell_w = w // 8
    
    # 提取所有格子的特征
    cell_features = []
    cell_positions = []
    
    for row in range(8):
        for col in range(8):
            # 提取格子中心区域（40% × 40%，即中心30%~70%）
            margin_h = int(cell_h * 0.3)  # 上下各留30%
            margin_w = int(cell_w * 0.3)  # 左右各留30%
            y1 = row * cell_h + margin_h
            y2 = (row + 1) * cell_h - margin_h
            x1 = col * cell_w + margin_w
            x2 = (col + 1) * cell_w - margin_w
            
            cell = warped_board[y1:y2, x1:x2]
            
            if cell.size == 0:
                continue
            
            # 提取特征（Lab颜色空间，只取mean(L), mean(a), mean(b)）
            lab = cv2.cvtColor(cell, cv2.COLOR_BGR2LAB)
            feature = lab.mean(axis=(0, 1))  # L, a, b 均值（3维）
            
            cell_features.append(feature)
            cell_positions.append((row, col))
    
    cell_features = np.array(cell_features)
    
    # 第一帧：校准
    if frame_idx == 0 or calibration_data is None:
        calibration_data = _calibrate_from_first_frame(
            warped_board, cell_features, cell_positions, output_path
        )
    
    # 使用校准数据分类
    occupancy, confidence, labels = _classify_cells(
        cell_features, cell_positions, calibration_data
    )
    
    # 保存第一帧的格子切片（用于debug）
    if frame_idx == 0:
        cells_dir = output_path / "cells"
        cells_dir.mkdir(exist_ok=True)
        for (row, col), label in zip(cell_positions, labels):
            margin = int(cell_h * 0.4)
            y1 = row * cell_h + margin
            y2 = (row + 1) * cell_h - margin
            x1 = col * cell_w + margin
            x2 = (col + 1) * cell_w - margin
            cell = warped_board[y1:y2, x1:x2]
            cell_filename = cells_dir / f"r{row}_c{col}.png"
            cv2.imwrite(str(cell_filename), cell)
    
    # 构建8x8矩阵
    occupancy_map = np.zeros((8, 8), dtype=np.int32)
    confidence_map = np.zeros((8, 8), dtype=np.float32)
    labels_map = [['empty'] * 8 for _ in range(8)]
    
    for (row, col), occ, conf, label in zip(cell_positions, occupancy, confidence, labels):
        occupancy_map[row, col] = occ
        confidence_map[row, col] = conf
        labels_map[row][col] = label
    
    board_state = {
        'occupancy': occupancy_map.tolist(),
        'confidence': confidence_map.tolist(),
        'labels': labels_map
    }
    
    return board_state, calibration_data


def _calibrate_from_first_frame(
    warped_board: np.ndarray,
    cell_features: np.ndarray,
    cell_positions: List[Tuple[int, int]],
    output_path: Path
) -> Dict:
    """
    从第一帧校准：识别empty/light/dark三类
    
    策略：
    - rows 0,1,6,7 作为"piece samples"（有棋子）
    - rows 2~5 作为"empty samples"（空格子）
    """
    # 分离piece samples和empty samples
    piece_samples = []
    empty_samples = []
    
    for i, (row, col) in enumerate(cell_positions):
        if row in [0, 1, 6, 7]:
            piece_samples.append(cell_features[i])
        elif row in [2, 3, 4, 5]:
            empty_samples.append(cell_features[i])
    
    piece_samples = np.array(piece_samples)
    empty_samples = np.array(empty_samples)
    
    # 对所有格子做KMeans聚类（K=3）
    kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
    kmeans.fit(cell_features)
    
    cluster_centers = kmeans.cluster_centers_
    cluster_labels = kmeans.labels_
    
    # 改进的自动判定方法：
    # 1. empty类：在rows 2~5中占比最高的cluster
    empty_row_indices = [i for i, (row, _) in enumerate(cell_positions) if row in [2, 3, 4, 5]]
    empty_cluster_counts = [0, 0, 0]
    for idx in empty_row_indices:
        cluster_id = cluster_labels[idx]
        empty_cluster_counts[cluster_id] += 1
    empty_cluster_idx = np.argmax(empty_cluster_counts)
    
    # 2. light/dark：根据在rows 0,1和rows 6,7中的分布
    # rows 0,1应该是light（白方），rows 6,7应该是dark（黑方）
    light_row_indices = [i for i, (row, _) in enumerate(cell_positions) if row in [0, 1]]
    dark_row_indices = [i for i, (row, _) in enumerate(cell_positions) if row in [6, 7]]
    
    remaining_indices = [i for i in range(3) if i != empty_cluster_idx]
    
    # 计算每个remaining cluster在light rows和dark rows中的占比
    light_scores = []
    dark_scores = []
    for cluster_id in remaining_indices:
        light_count = sum(1 for idx in light_row_indices if cluster_labels[idx] == cluster_id)
        dark_count = sum(1 for idx in dark_row_indices if cluster_labels[idx] == cluster_id)
        light_scores.append(light_count)
        dark_scores.append(dark_count)
    
    # 在light rows中占比高的=light，在dark rows中占比高的=dark
    if light_scores[0] > light_scores[1]:
        light_cluster_idx = remaining_indices[0]
        dark_cluster_idx = remaining_indices[1]
    else:
        light_cluster_idx = remaining_indices[1]
        dark_cluster_idx = remaining_indices[0]
    
    # 如果还是不确定，用L通道亮度作为fallback
    if light_scores[0] == light_scores[1]:
        l_values = [cluster_centers[i][0] for i in remaining_indices]
        if l_values[0] > l_values[1]:
            light_cluster_idx = remaining_indices[0]
            dark_cluster_idx = remaining_indices[1]
        else:
            light_cluster_idx = remaining_indices[1]
            dark_cluster_idx = remaining_indices[0]
    
    calibration_data = {
        'cluster_centers': cluster_centers.tolist(),
        'empty_cluster': int(empty_cluster_idx),
        'light_cluster': int(light_cluster_idx),
        'dark_cluster': int(dark_cluster_idx),
        'empty_samples_mean': empty_samples.mean(axis=0).tolist(),
        'empty_samples_std': empty_samples.std(axis=0).tolist()
    }
    
    # 保存校准数据
    calib_path = output_path / "calibration.json"
    with open(calib_path, 'w', encoding='utf-8') as f:
        json.dump(calibration_data, f, indent=2, ensure_ascii=False)
    
    print(f"  校准完成: empty={empty_cluster_idx}, light={light_cluster_idx}, dark={dark_cluster_idx}")
    
    return calibration_data


def _classify_cells(
    cell_features: np.ndarray,
    cell_positions: List[Tuple[int, int]],
    calibration_data: Dict
) -> Tuple[List[int], List[float], List[str]]:
    """
    使用校准数据分类每个格子
    
    Returns:
        (occupancy_list, confidence_list, labels_list)
    """
    cluster_centers = np.array(calibration_data['cluster_centers'])
    empty_cluster = calibration_data['empty_cluster']
    light_cluster = calibration_data['light_cluster']
    dark_cluster = calibration_data['dark_cluster']
    
    occupancy = []
    confidence = []
    labels = []
    
    for feature in cell_features:
        # 计算到每个聚类中心的距离
        dists = np.linalg.norm(cluster_centers - feature, axis=1)
        closest_idx = np.argmin(dists)
        min_dist = dists[closest_idx]
        
        # 映射到类别
        if closest_idx == empty_cluster:
            label = 'empty'
            occ = 0
        elif closest_idx == light_cluster:
            label = 'light'
            occ = 1
        else:  # dark_cluster
            label = 'dark'
            occ = 2
        
        # 计算置信度（距离越小，置信度越高）
        # 使用到所属聚类中心的距离，映射到0~1
        # 假设最大合理距离为100（Lab空间，L范围0-100）
        max_reasonable_dist = 100.0
        conf = max(0.0, min(1.0, 1.0 - (min_dist / max_reasonable_dist)))
        
        occupancy.append(occ)
        confidence.append(conf)
        labels.append(label)
    
    return occupancy, confidence, labels


def detect_pieces(
    warped_board: np.ndarray,
    frame_idx: int,
    output_dir: str
) -> Dict[str, any]:
    """
    检测棋盘上的棋子（兼容旧接口）
    """
    board_state, _ = detect_pieces_auto_calibrate(
        warped_board=warped_board,
        frame_idx=frame_idx,
        output_dir=output_dir,
        calibration_data=None
    )
    return board_state
