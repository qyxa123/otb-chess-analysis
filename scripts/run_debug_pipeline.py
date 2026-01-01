#!/usr/bin/env python3
"""
Debug Pipeline - 一键运行从视频到debug输出的流程
"""

import argparse
import sys
from pathlib import Path
import os

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from otbreview.pipeline.extract import extract_stable_frames_debug
from otbreview.pipeline.board_detect import detect_and_warp_board_debug


def find_video_file(search_dirs=None):
    """
    自动查找视频文件
    
    Args:
        search_dirs: 搜索目录列表，默认搜索根目录、data/、videos/、inbox/
    
    Returns:
        找到的视频文件路径（最近修改的），如果没找到返回None
    """
    if search_dirs is None:
        project_root = Path(__file__).parent.parent
        search_dirs = [
            project_root,
            project_root / "data",
            project_root / "videos",
            project_root / "inbox"
        ]
    
    video_extensions = ['.mp4', '.mov', '.MOV', '.MP4']
    video_files = []
    
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        
        for ext in video_extensions:
            video_files.extend(list(search_dir.glob(f"*{ext}")))
    
    if not video_files:
        return None
    
    # 按修改时间排序，返回最新的
    video_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return str(video_files[0])


def main():
    parser = argparse.ArgumentParser(
        description="Debug Pipeline - 从视频抽取稳定帧并做ArUco透视矫正"
    )
    parser.add_argument(
        '--input', '-i',
        type=str,
        default=None,
        help='输入视频文件路径（如果不指定，自动查找）'
    )
    parser.add_argument(
        '--outdir', '-o',
        type=str,
        required=True,
        help='输出目录'
    )
    parser.add_argument(
        '--use_markers',
        type=int,
        default=1,
        help='是否使用ArUco标记 (0=否, 1=是，默认1)'
    )
    
    args = parser.parse_args()
    
    # 确定输入视频
    if args.input:
        video_path = args.input
        if not Path(video_path).exists():
            print(f"错误: 视频文件不存在: {video_path}")
            sys.exit(1)
    else:
        print("自动查找视频文件...")
        video_path = find_video_file()
        if video_path is None:
            print("错误: 未找到视频文件（搜索: 根目录、data/、videos/、inbox/）")
            sys.exit(1)
    
    print(f"使用视频文件: {video_path}")
    
    # 创建输出目录
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    debug_dir = outdir / "debug"
    debug_dir.mkdir(exist_ok=True)
    
    use_markers = bool(args.use_markers)
    
    print("\n" + "="*60)
    print("步骤1: 抽取稳定帧")
    print("="*60)
    
    stable_frames = extract_stable_frames_debug(
        video_path=video_path,
        output_dir=str(debug_dir / "stable_frames"),
        motion_csv_path=str(debug_dir / "motion.csv")
    )
    
    print(f"\n抽取到 {len(stable_frames)} 个稳定帧")
    
    if len(stable_frames) == 0:
        print("错误: 未抽取到任何稳定帧")
        sys.exit(1)
    
    print("\n" + "="*60)
    print("步骤2: ArUco定位与透视矫正")
    print("="*60)
    
    if not use_markers:
        print("警告: --use_markers=0，但debug pipeline需要ArUco标记")
        print("建议使用 --use_markers 1")
    
    fail_frames = []
    warped_boards_dir = debug_dir / "warped_boards"
    warped_boards_dir.mkdir(exist_ok=True)
    
    for i, frame_path in enumerate(stable_frames):
        print(f"\n处理帧 {i+1}/{len(stable_frames)}: {Path(frame_path).name}")
        
        success, warped, preview_img, grid_img = detect_and_warp_board_debug(
            frame_path=frame_path,
            use_markers=use_markers,
            output_dir=str(warped_boards_dir),
            frame_idx=i
        )
        
        if not success:
            fail_frames.append(frame_path)
            print(f"  ❌ 失败: 未检测到4个ArUco标记")
        else:
            print(f"  ✅ 成功: 已保存矫正后的棋盘")
            
            # 保存第一帧的预览图和网格图
            if i == 0:
                if preview_img is not None:
                    preview_path = debug_dir / "aruco_preview.png"
                    import cv2
                    cv2.imwrite(str(preview_path), preview_img)
                    print(f"  📸 ArUco预览图已保存: {preview_path}")
                
                if grid_img is not None:
                    grid_path = debug_dir / "grid_overlay.png"
                    cv2.imwrite(str(grid_path), grid_img)
                    print(f"  📐 网格覆盖图已保存: {grid_path}")
    
    # 记录失败帧
    if fail_frames:
        fail_path = debug_dir / "fail_frames.txt"
        with open(fail_path, 'w', encoding='utf-8') as f:
            f.write("以下帧未能检测到4个ArUco标记:\n\n")
            for frame_path in fail_frames:
                f.write(f"{frame_path}\n")
        print(f"\n⚠️  失败帧记录: {fail_path} ({len(fail_frames)} 帧)")
    
    print("\n" + "="*60)
    print("✅ Debug Pipeline 完成!")
    print("="*60)
    print(f"\n输出目录: {outdir}")
    print(f"\n验收文件:")
    print(f"  - {debug_dir / 'stable_frames/'} (稳定帧)")
    print(f"  - {debug_dir / 'motion.csv'} (运动数据)")
    print(f"  - {debug_dir / 'aruco_preview.png'} (ArUco检测预览)")
    print(f"  - {debug_dir / 'grid_overlay.png'} (网格覆盖图，检查对齐)")
    print(f"  - {debug_dir / 'warped_boards/'} (矫正后的棋盘)")
    if fail_frames:
        print(f"  - {debug_dir / 'fail_frames.txt'} (失败帧列表)")


if __name__ == '__main__':
    main()

