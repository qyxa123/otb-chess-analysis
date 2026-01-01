#!/usr/bin/env python3
"""
第一帧调试脚本：详细输出piece vs empty和light vs dark的中间结果
"""

import argparse
import sys
from pathlib import Path
import cv2
import numpy as np
import json

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from otbreview.pipeline.pieces import detect_pieces_two_stage


def main():
    parser = argparse.ArgumentParser(
        description="调试第一帧识别：输出详细的中间结果"
    )
    parser.add_argument(
        '--outdir',
        type=str,
        required=True,
        help='输出目录（包含debug/warped_boards/warp_0001.png）'
    )
    parser.add_argument(
        '--patch_ratio',
        type=float,
        default=0.40,
        help='格子中心patch比例（默认0.40，即40%×40%）'
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
    
    # 查找第一帧
    first_frame = warped_dir / "warp_0001.png"
    if not first_frame.exists():
        first_frame = warped_dir / "frame_0001_warped.jpg"
    
    if not first_frame.exists():
        print(f"错误: 未找到第一帧: {warped_dir}")
        sys.exit(1)
    
    print(f"读取第一帧: {first_frame}")
    warped = cv2.imread(str(first_frame))
    if warped is None:
        print(f"错误: 无法读取图像: {first_frame}")
        sys.exit(1)
    
    # 创建输出目录
    debug_check_dir = outdir / "debug_check"
    debug_check_dir.mkdir(exist_ok=True)
    cells_dir = debug_check_dir / "cells_8x8"
    cells_dir.mkdir(exist_ok=True)
    
    print(f"\n=== 两阶段识别调试 ===")
    
    # 运行两阶段识别
    result = detect_pieces_two_stage(
        warped_board=warped,
        frame_idx=0,
        output_dir=str(debug_check_dir),
        patch_ratio=args.patch_ratio,
        debug=True
    )
    
    if result is None:
        print("错误: 识别失败")
        sys.exit(1)
    
    print(f"\n✅ 调试输出已保存到: {debug_check_dir}")
    print(f"\n验收标准：")
    print(f"  1. piece_mask.png - 只有前两排+后两排为piece（白色）")
    print(f"  2. occupancy_map.png - 上两排几乎全D，下两排几乎全L，中间几乎全E")
    print(f"  3. metrics.json - 查看T1, T2, Tld等阈值")


if __name__ == '__main__':
    main()

