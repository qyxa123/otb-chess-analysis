#!/usr/bin/env python3
"""
从warped棋盘识别8x8 empty/light/dark
"""

import argparse
import sys
from pathlib import Path
import cv2
import json

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from otbreview.pipeline.pieces import detect_pieces_two_stage
import numpy as np


def save_occupancy_map(occupancy: list, output_path: Path, labels: list = None):
    """
    保存occupancy map可视化
    empty=灰色, light=白色, dark=黑色
    """
    img = np.zeros((800, 800, 3), dtype=np.uint8)
    cell_size = 100
    
    for row in range(8):
        for col in range(8):
            y1 = row * cell_size
            y2 = (row + 1) * cell_size
            x1 = col * cell_size
            x2 = (col + 1) * cell_size
            
            occ = occupancy[row][col]
            if occ == 0:
                color = (128, 128, 128)  # 灰色（empty）
            elif occ == 1:
                color = (255, 255, 255)  # 白色（light）
            else:
                color = (0, 0, 0)  # 黑色（dark）
            
            img[y1:y2, x1:x2] = color
            
            # 可选：在格子上标注label文字
            if labels:
                label = labels[row][col]
                cv2.putText(img, label[0].upper(), 
                           (x1 + 10, y1 + 30),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
    
    cv2.imwrite(str(output_path), img)


def save_confidence_map(confidence: list, output_path: Path):
    """
    保存confidence map可视化（热力图）
    """
    import numpy as np
    
    conf_array = np.array(confidence, dtype=np.float32)
    # 归一化到0-255
    conf_normalized = (conf_array * 255).astype(np.uint8)
    
    # 应用colormap（绿色=高置信度，红色=低置信度）
    img = cv2.applyColorMap(conf_normalized, cv2.COLORMAP_JET)
    
    # 放大到800x800
    img = cv2.resize(img, (800, 800), interpolation=cv2.INTER_NEAREST)
    
    cv2.imwrite(str(output_path), img)


def main():
    parser = argparse.ArgumentParser(
        description="从warped棋盘识别8x8 empty/light/dark"
    )
    parser.add_argument(
        '--outdir',
        type=str,
        required=True,
        help='输出目录（包含debug/warped_boards/）'
    )
    
    args = parser.parse_args()
    
    outdir = Path(args.outdir)
    if not outdir.exists():
        print(f"错误: 输出目录不存在: {outdir}")
        sys.exit(1)
    
    warped_dir = outdir / "debug" / "warped_boards"
    if not warped_dir.exists():
        print(f"错误: warped目录不存在: {warped_dir}")
        sys.exit(1)
    
    # 查找所有warped图像
    warped_files = sorted(warped_dir.glob("warp_*.png"))
    if not warped_files:
        warped_files = sorted(warped_dir.glob("*_warped.jpg"))
    
    if len(warped_files) == 0:
        print(f"错误: 未找到warped图像: {warped_dir}")
        sys.exit(1)
    
    print(f"找到 {len(warped_files)} 张warped图像")
    
    debug_dir = outdir / "debug"
    debug_dir.mkdir(exist_ok=True)
    cells_sample_dir = debug_dir / "cells_sample"
    cells_sample_dir.mkdir(exist_ok=True)
    
    # 处理所有帧
    board_states = []
    calibration_data = None
    
    for i, warped_file in enumerate(warped_files):
        print(f"\n处理帧 {i+1}/{len(warped_files)}: {warped_file.name}")
        
        warped = cv2.imread(str(warped_file))
        if warped is None:
            print(f"  警告: 无法读取 {warped_file}")
            continue
        
        # 使用两阶段识别
        board_state = detect_pieces_two_stage(
            warped_board=warped,
            frame_idx=i,
            output_dir=str(debug_dir),
            patch_ratio=0.40,
            debug=(i == 0)  # 只对第一帧输出debug
        )
        
        if board_state is None:
            print(f"  警告: 识别失败 {warped_file}")
            continue
        
        # 保存第一帧的64个格子切片
        if i == 0:
            h, w = warped.shape[:2]
            cell_h = h // 8
            cell_w = w // 8
            
            for row in range(8):
                for col in range(8):
                    # 中心40% × 40%区域（即中心30%~70%）
                    margin_h = int(cell_h * 0.3)  # 上下各留30%
                    margin_w = int(cell_w * 0.3)  # 左右各留30%
                    y1 = row * cell_h + margin_h
                    y2 = (row + 1) * cell_h - margin_h
                    x1 = col * cell_w + margin_w
                    x2 = (col + 1) * cell_w - margin_w
                    
                    cell = warped[y1:y2, x1:x2]
                    cell_filename = cells_sample_dir / f"r{row}_c{col}.png"
                    cv2.imwrite(str(cell_filename), cell)
        
        # 构建输出格式
        state_data = {
            'frame_idx': i,
            'filename': warped_file.name,
            'labels': board_state['labels'],
            'confidence': board_state['confidence']
        }
        board_states.append(state_data)
        
        # 保存前5帧的occupancy map
        if i < 5:
            occupancy_path = debug_dir / f"occupancy_map_{i+1:04d}.png"
            save_occupancy_map(
                board_state['occupancy'],
                occupancy_path,
                labels=board_state['labels']
            )
            print(f"  ✅ 已保存: {occupancy_path}")
            
            # 保存confidence map
            confidence_path = debug_dir / f"confidence_map_{i+1:04d}.png"
            save_confidence_map(board_state['confidence'], confidence_path)
            print(f"  ✅ 已保存: {confidence_path}")
    
    # 保存board_states.json
    board_states_path = outdir / "board_states.json"
    with open(board_states_path, 'w', encoding='utf-8') as f:
        json.dump(board_states, f, indent=2, ensure_ascii=False)
    print(f"\n✅ board_states.json已保存: {board_states_path}")
    
    print("\n=== 完成 ===")
    print(f"\n验收标准：")
    print(f"  1. 查看 {debug_dir / 'occupancy_map_0001.png'}")
    print(f"     - 第8/7行（索引7/6）应该几乎全dark（黑色）")
    print(f"     - 第2/1行（索引1/0）应该几乎全light（白色）")
    print(f"     - 中间四行（索引2-5）应该几乎全empty（灰色）")
    print(f"  2. 查看 {cells_sample_dir} - 第一帧的64个格子切片")
    print(f"  3. 查看 {board_states_path} - 完整的识别结果")


if __name__ == '__main__':
    import numpy as np
    main()

