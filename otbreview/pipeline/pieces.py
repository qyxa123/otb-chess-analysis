#!/usr/bin/env python3
"""
棋子/占用识别模块
功能：识别每个格子的占用状态（empty/light/dark）
两阶段识别：Phase A (piece vs empty) + Phase B (light vs dark)
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import json

from .tag_detector import detect_piece_tags


def detect_pieces_tags(
    warped_board: np.ndarray,
    frame_idx: int,
    output_dir: str,
    tag_family: str = 'apriltag36h11',
    min_area_ratio: float = 0.0005,
    enable_clahe: bool = True,
    enable_threshold: bool = True,
) -> Dict[str, any]:
    """
    使用 ArUco/AprilTag 检测棋子 ID
    
    Args:
        warped_board: 800x800 矫正后的棋盘图
        frame_idx: 帧索引
        output_dir: 输出目录
        tag_family: 标签系列 (apriltag36h11, aruco4x4, etc)
        
    Returns:
        board_state: {
            'piece_ids': [[id, ...], ...],  # 8x8 matrix of detected IDs (0 if none)
            'piece_centers': [[(x,y), ...], ...], # Centers for debug
            'tag_detections': list of raw detection dicts
        }
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    result = detect_piece_tags(
        warped_board=warped_board,
        frame_idx=frame_idx,
        output_dir=output_path,
        min_area_ratio=min_area_ratio,
        enable_clahe=enable_clahe,
        enable_threshold=enable_threshold,
    )

    piece_centers_map = [[None for _ in range(8)] for _ in range(8)]
    for det in result.detections:
        piece_centers_map[det.row][det.col] = (det.center[0], det.center[1])

    # 如果是第一帧，输出额外的验证图
    if frame_idx == 0:
        _save_first_frame_views(
            warped_board=warped_board,
            board_ids=result.board_ids,
            output_path=output_path,
            detections=result.detections,
            overlay_path=result.overlay_path,
        )

    return {
        'piece_ids': result.board_ids,
        'piece_centers': piece_centers_map,
        'tag_detections': [det.__dict__ for det in result.detections],
        'tag_warnings': result.warnings,
        'tag_conflicts': result.conflict_log,
    }


def _save_first_frame_views(
    warped_board: np.ndarray,
    board_ids: List[List[int]],
    output_path: Path,
    detections,
    overlay_path: Optional[Path] = None,
) -> None:
    """为首帧输出额外的视觉包，便于快速人工校验。"""

    overlay_candidate = overlay_path if overlay_path and overlay_path.exists() else None
    if overlay_candidate is None:
        fallback = sorted(output_path.glob("overlay_*.png"))
        overlay_candidate = fallback[0] if fallback else None

    if overlay_candidate and overlay_candidate.exists():
        overlay = cv2.imread(str(overlay_candidate))
    else:
        overlay = warped_board

    debug_root = output_path.parent
    debug_root.mkdir(parents=True, exist_ok=True)

    cv2.imwrite(str(debug_root / "tag_overlay.png"), overlay)

    zoom = cv2.resize(overlay, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    cv2.imwrite(str(debug_root / "tag_overlay_zoom.png"), zoom)

    grid_img = np.zeros_like(warped_board)
    cell = warped_board.shape[0] // 8
    for r in range(8):
        for c in range(8):
            top_left = (c * cell, r * cell)
            bottom_right = ((c + 1) * cell, (r + 1) * cell)
            cv2.rectangle(grid_img, top_left, bottom_right, (50, 180, 255), 2)
            pid = board_ids[r][c]
            if pid:
                cv2.putText(
                    grid_img,
                    str(pid),
                    (top_left[0] + 10, top_left[1] + cell // 2),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (255, 255, 255),
                    2,
                )
    cv2.imwrite(str(debug_root / "tag_grid.png"), grid_img)

    missing = [pid for pid in range(1, 33) if pid not in np.array(board_ids).flatten()]
    missing_img = np.full((300, 600, 3), 255, dtype=np.uint8)
    cv2.putText(
        missing_img,
        "Missing IDs:",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 0, 0),
        2,
    )
    cv2.putText(
        missing_img,
        ", ".join(map(str, missing)) if missing else "None",
        (20, 90),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (0, 0, 0),
        2,
    )
    cv2.imwrite(str(debug_root / "tag_missing_ids.png"), missing_img)


def detect_pieces_two_stage(
    warped_board: np.ndarray,
    frame_idx: int,
    output_dir: str,
    patch_ratio: float = 0.40,
    debug: bool = False
) -> Optional[Dict[str, any]]:
    """
    两阶段识别：Phase A (piece vs empty) + Phase B (light vs dark)
    
    Args:
        warped_board: 矫正后的棋盘图像（800x800）
        frame_idx: 帧索引（0表示第一帧，用于校准）
        output_dir: 输出目录
        patch_ratio: 格子中心patch比例（默认0.40，即40%×40%）
        debug: 是否输出详细debug信息
    
    Returns:
        board_state: {
            'occupancy': [[0/1/2, ...], ...],  # 0=empty, 1=light, 2=dark
            'confidence': [[float, ...], ...],
            'labels': [['empty'/'light'/'dark', ...], ...]
        }
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    h, w = warped_board.shape[:2]
    cell_h = h // 8
    cell_w = w // 8
    
    # 保存第一帧warped图
    if frame_idx == 0 and debug:
        cv2.imwrite(str(output_path / "board_first_warp.png"), warped)
    
    # Phase A: piece vs empty
    piece_mask, diff_heatmap, edge_heatmap, metrics = _phase_a_piece_empty(
        warped_board=warped,
        frame_idx=frame_idx,
        output_path=output_path,
        patch_ratio=patch_ratio,
        debug=debug
    )
    
    if piece_mask is None:
        return None
    
    # Phase B: light vs dark（只在piece格）
    occupancy, labels, confidence = _phase_b_light_dark(
        warped_board=warped,
        piece_mask=piece_mask,
        frame_idx=frame_idx,
        output_path=output_path,
        patch_ratio=patch_ratio,
        metrics=metrics,
        debug=debug
    )
    
    # 保存可视化
    if debug:
        _save_piece_mask(piece_mask, output_path / "piece_mask.png")
        _save_occupancy_map(occupancy, output_path / "occupancy_map.png", labels)
        if diff_heatmap is not None:
            _save_heatmap(diff_heatmap, output_path / "diff_heatmap.png", "Color Diff")
        if edge_heatmap is not None:
            _save_heatmap(edge_heatmap, output_path / "edge_heatmap.png", "Edge Score")
    
    # 保存metrics
    if debug and metrics:
        metrics_path = output_path / "metrics.json"
        with open(metrics_path, 'w', encoding='utf-8') as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)
    
    board_state = {
        'occupancy': occupancy.tolist() if isinstance(occupancy, np.ndarray) else occupancy,
        'confidence': confidence.tolist() if isinstance(confidence, np.ndarray) else confidence,
        'labels': labels
    }
    
    return board_state


def _phase_a_piece_empty(
    warped_board: np.ndarray,
    frame_idx: int,
    output_path: Path,
    patch_ratio: float,
    debug: bool
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[np.ndarray], Optional[Dict]]:
    """
    Phase A: piece vs empty识别
    
    Returns:
        (piece_mask, diff_heatmap, edge_heatmap, metrics)
    """
    h, w = warped_board.shape[:2]
    cell_h = h // 8
    cell_w = w // 8
    
    # 提取所有格子的中心patch
    patches = []
    patch_positions = []
    
    margin_h = int(cell_h * (1 - patch_ratio) / 2)
    margin_w = int(cell_w * (1 - patch_ratio) / 2)
    
    for row in range(8):
        for col in range(8):
            y1 = row * cell_h + margin_h
            y2 = (row + 1) * cell_h - margin_h
            x1 = col * cell_w + margin_w
            x2 = (col + 1) * cell_w - margin_w
            
            patch = warped_board[y1:y2, x1:x2]
            if patch.size == 0:
                continue
            
            patches.append((row, col, patch))
            patch_positions.append((row, col))
            
            # 保存第一帧的patch（debug）
            if frame_idx == 0 and debug:
                cells_dir = output_path / "cells_8x8"
                cells_dir.mkdir(exist_ok=True)
                cv2.imwrite(str(cells_dir / f"r{row}_c{col}.png"), patch)
    
    # 第一帧：校准（采样空格模板）
    if frame_idx == 0:
        # 从中间四排(rows 2-5)采样空格
        empty_patches_white = []  # 白格空格
        empty_patches_black = []  # 黑格空格
        
        for row, col, patch in patches:
            if row in [2, 3, 4, 5]:
                # 判断是白格还是黑格（棋盘格颜色）
                is_white_square = (row + col) % 2 == 0
                lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB)
                lab_mean = lab.mean(axis=(0, 1))
                
                if is_white_square:
                    empty_patches_white.append(lab_mean)
                else:
                    empty_patches_black.append(lab_mean)
        
        if len(empty_patches_white) == 0 or len(empty_patches_black) == 0:
            print("  警告: 空格样本不足，无法校准")
            return None, None, None, None
        
        # 计算两种底色模板
        template_white = np.mean(empty_patches_white, axis=0)
        template_black = np.mean(empty_patches_black, axis=0)
        
        # 计算空格样本的color_diff和edge_score分布
        color_diffs_empty = []
        edge_scores_empty = []
        
        for row, col, patch in patches:
            if row in [2, 3, 4, 5]:
                lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB)
                is_white_square = (row + col) % 2 == 0
                template = template_white if is_white_square else template_black
                
                # color_diff
                lab_mean = lab.mean(axis=(0, 1))
                color_diff = np.mean(np.abs(lab_mean - template))
                color_diffs_empty.append(color_diff)
                
                # edge_score
                gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
                edges = cv2.Canny(gray, 50, 150)
                edge_score = np.sum(edges > 0) / edges.size
                edge_scores_empty.append(edge_score)
        
        # 阈值自动估计
        T1 = np.mean(color_diffs_empty) + 4 * np.std(color_diffs_empty)
        T2 = np.mean(edge_scores_empty) + 4 * np.std(edge_scores_empty)
        
        # 保存校准数据
        calibration = {
            'template_white': template_white.tolist(),
            'template_black': template_black.tolist(),
            'T1': float(T1),
            'T2': float(T2),
            'empty_samples_count': len(color_diffs_empty),
            'color_diff_empty_mean': float(np.mean(color_diffs_empty)),
            'color_diff_empty_std': float(np.std(color_diffs_empty)),
            'edge_score_empty_mean': float(np.mean(edge_scores_empty)),
            'edge_score_empty_std': float(np.std(edge_scores_empty))
        }
        
        calib_path = output_path / "calibration_phase_a.json"
        with open(calib_path, 'w', encoding='utf-8') as f:
            json.dump(calibration, f, indent=2, ensure_ascii=False)
        
        print(f"  Phase A校准: T1={T1:.2f}, T2={T2:.4f}")
    else:
        # 加载校准数据
        calib_path = output_path / "calibration_phase_a.json"
        if not calib_path.exists():
            print("  错误: 未找到校准数据，请先处理第一帧")
            return None, None, None, None
        
        with open(calib_path, 'r', encoding='utf-8') as f:
            calibration = json.load(f)
        
        template_white = np.array(calibration['template_white'])
        template_black = np.array(calibration['template_black'])
        T1 = calibration['T1']
        T2 = calibration['T2']
    
    # 对所有格子进行piece判定
    piece_mask = np.zeros((8, 8), dtype=np.uint8)
    diff_heatmap = np.zeros((8, 8), dtype=np.float32)
    edge_heatmap = np.zeros((8, 8), dtype=np.float32)
    
    for row, col, patch in patches:
        lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB)
        is_white_square = (row + col) % 2 == 0
        template = template_white if is_white_square else template_black
        
        # color_diff
        lab_mean = lab.mean(axis=(0, 1))
        color_diff = np.mean(np.abs(lab_mean - template))
        diff_heatmap[row, col] = color_diff
        
        # edge_score
        gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        edge_score = np.sum(edges > 0) / edges.size
        edge_heatmap[row, col] = edge_score
        
        # piece判定
        is_piece = (color_diff > T1) or (edge_score > T2)
        piece_mask[row, col] = 1 if is_piece else 0
    
    metrics = {
        'patch_ratio': patch_ratio,
        'T1': float(T1),
        'T2': float(T2),
        'piece_count': int(np.sum(piece_mask)),
        'empty_count': int(64 - np.sum(piece_mask))
    }
    
    return piece_mask, diff_heatmap, edge_heatmap, metrics


def _phase_b_light_dark(
    warped_board: np.ndarray,
    piece_mask: np.ndarray,
    frame_idx: int,
    output_path: Path,
    patch_ratio: float,
    metrics: Dict,
    debug: bool
) -> Tuple[np.ndarray, List[List[str]], np.ndarray]:
    """
    Phase B: light vs dark识别（只在piece格）
    
    Returns:
        (occupancy, labels, confidence)
    """
    h, w = warped_board.shape[:2]
    cell_h = h // 8
    cell_w = w // 8
    
    margin_h = int(cell_h * (1 - patch_ratio) / 2)
    margin_w = int(cell_w * (1 - patch_ratio) / 2)
    
    occupancy = np.zeros((8, 8), dtype=np.int32)
    labels = [['empty'] * 8 for _ in range(8)]
    confidence = np.ones((8, 8), dtype=np.float32) * 0.5  # 默认中等置信度
    
    # 第一帧：校准（确定light/dark阈值）
    if frame_idx == 0:
        # rows 0-1的piece样本为dark，rows 6-7的piece样本为light
        dark_samples = []
        light_samples = []
        
        for row in range(8):
            for col in range(8):
                if piece_mask[row, col] == 0:  # empty格跳过
                    continue
                
                y1 = row * cell_h + margin_h
                y2 = (row + 1) * cell_h - margin_h
                x1 = col * cell_w + margin_w
                x2 = (col + 1) * cell_w - margin_w
                
                patch = warped_board[y1:y2, x1:x2]
                if patch.size == 0:
                    continue
                
                lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB)
                L_value = lab.mean(axis=(0, 1))[0]  # L通道均值
                
                if row in [0, 1]:
                    dark_samples.append(L_value)
                elif row in [6, 7]:
                    light_samples.append(L_value)
        
        if len(dark_samples) == 0 or len(light_samples) == 0:
            print("  警告: light/dark样本不足，使用默认阈值")
            Tld = 100.0  # 默认阈值
        else:
            dark_mean = np.mean(dark_samples)
            light_mean = np.mean(light_samples)
            Tld = (dark_mean + light_mean) / 2.0
        
        # 保存校准数据
        calibration_b = {
            'Tld': float(Tld),
            'dark_mean': float(np.mean(dark_samples)) if dark_samples else None,
            'light_mean': float(np.mean(light_samples)) if light_samples else None,
            'dark_samples_count': len(dark_samples),
            'light_samples_count': len(light_samples)
        }
        
        calib_path = output_path / "calibration_phase_b.json"
        with open(calib_path, 'w', encoding='utf-8') as f:
            json.dump(calibration_b, f, indent=2, ensure_ascii=False)
        
        metrics['Tld'] = float(Tld)
        dark_mean_val = np.mean(dark_samples) if dark_samples else 0
        light_mean_val = np.mean(light_samples) if light_samples else 0
        print(f"  Phase B校准: Tld={Tld:.2f} (dark_mean={dark_mean_val:.2f}, light_mean={light_mean_val:.2f})")
    else:
        # 加载校准数据
        calib_path = output_path / "calibration_phase_b.json"
        if not calib_path.exists():
            print("  错误: 未找到Phase B校准数据")
            Tld = 100.0
        else:
            with open(calib_path, 'r', encoding='utf-8') as f:
                calibration_b = json.load(f)
            Tld = calibration_b['Tld']
    
    # 对所有格子分类
    for row in range(8):
        for col in range(8):
            if piece_mask[row, col] == 0:
                # empty
                occupancy[row, col] = 0
                labels[row][col] = 'empty'
                confidence[row, col] = 0.8  # empty置信度较高
            else:
                # piece格：判断light/dark
                y1 = row * cell_h + margin_h
                y2 = (row + 1) * cell_h - margin_h
                x1 = col * cell_w + margin_w
                x2 = (col + 1) * cell_w - margin_w
                
                patch = warped_board[y1:y2, x1:x2]
                if patch.size == 0:
                    continue
                
                lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB)
                L_value = lab.mean(axis=(0, 1))[0]
                
                if L_value >= Tld:
                    occupancy[row, col] = 1  # light
                    labels[row][col] = 'light'
                else:
                    occupancy[row, col] = 2  # dark
                    labels[row][col] = 'dark'
                
                # 置信度：距离阈值越远，置信度越高
                dist_to_threshold = abs(L_value - Tld)
                max_dist = 50.0  # L范围0-100，最大距离50
                confidence[row, col] = min(1.0, 0.5 + (dist_to_threshold / max_dist) * 0.5)
    
    return occupancy, labels, confidence


def _save_piece_mask(piece_mask: np.ndarray, output_path: Path):
    """保存piece_mask可视化（piece=白色，empty=黑色）"""
    img = np.zeros((800, 800, 3), dtype=np.uint8)
    cell_size = 100
    
    for row in range(8):
        for col in range(8):
            y1 = row * cell_size
            y2 = (row + 1) * cell_size
            x1 = col * cell_size
            x2 = (col + 1) * cell_size
            
            if piece_mask[row, col] == 1:
                color = (255, 255, 255)  # 白色（piece）
            else:
                color = (0, 0, 0)  # 黑色（empty）
            
            img[y1:y2, x1:x2] = color
    
    cv2.imwrite(str(output_path), img)


def _save_occupancy_map(occupancy: np.ndarray, output_path: Path, labels: List[List[str]]):
    """保存occupancy map可视化"""
    img = np.zeros((800, 800, 3), dtype=np.uint8)
    cell_size = 100
    
    for row in range(8):
        for col in range(8):
            y1 = row * cell_size
            y2 = (row + 1) * cell_size
            x1 = col * cell_size
            x2 = (col + 1) * cell_size
            
            occ = occupancy[row, col]
            if occ == 0:
                color = (128, 128, 128)  # 灰色（empty）
            elif occ == 1:
                color = (255, 255, 255)  # 白色（light）
            else:
                color = (0, 0, 0)  # 黑色（dark）
            
            img[y1:y2, x1:x2] = color
            
            # 标注label文字
            label = labels[row][col][0].upper()  # E/L/D
            text_color = (255, 0, 0) if occ == 0 else (0, 0, 255)
            cv2.putText(img, label, (x1 + 10, y1 + 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, text_color, 2)
    
    cv2.imwrite(str(output_path), img)


def _save_heatmap(heatmap: np.ndarray, output_path: Path, title: str):
    """保存热力图可视化"""
    # 归一化到0-255
    if heatmap.max() > 0:
        normalized = (heatmap / heatmap.max() * 255).astype(np.uint8)
    else:
        normalized = heatmap.astype(np.uint8)
    
    # 应用colormap
    colored = cv2.applyColorMap(normalized, cv2.COLORMAP_JET)
    
    # 放大到800x800
    img = cv2.resize(colored, (800, 800), interpolation=cv2.INTER_NEAREST)
    
    # 添加标题
    cv2.putText(img, title, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    
    cv2.imwrite(str(output_path), img)


# 保持向后兼容
def detect_pieces_auto_calibrate(
    warped_board: np.ndarray,
    frame_idx: int,
    output_dir: str,
    calibration_data: Optional[Dict] = None
) -> Tuple[Dict[str, any], Optional[Dict]]:
    """
    自动校准版本（兼容旧接口，内部调用两阶段识别）
    """
    result = detect_pieces_two_stage(
        warped_board=warped_board,
        frame_idx=frame_idx,
        output_dir=output_dir,
        patch_ratio=0.40,
        debug=False
    )
    
    if result is None:
        return {}, None
    
    return result, None


def detect_pieces(
    warped_board: np.ndarray,
    frame_idx: int,
    output_dir: str
) -> Dict[str, any]:
    """
    检测棋盘上的棋子（兼容旧接口）
    """
    result = detect_pieces_two_stage(
        warped_board=warped_board,
        frame_idx=frame_idx,
        output_dir=output_dir,
        patch_ratio=0.40,
        debug=False
    )
    
    if result is None:
        return {'occupancy': [[0]*8]*8, 'confidence': [[0.0]*8]*8, 'labels': [['empty']*8]*8}
    
    return result
