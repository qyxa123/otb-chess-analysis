#!/usr/bin/env python3
"""
稳定帧抽取模块
功能：从视频中抽取稳定局面帧（运动检测）
"""

import cv2
import numpy as np
from pathlib import Path
from typing import List


def extract_stable_frames(
    video_path: str,
    output_dir: str,
    motion_threshold: float = 0.01,
    stable_duration: float = 0.5
) -> List[str]:
    """
    从视频中抽取稳定帧
    
    当运动能量低于阈值持续N帧（对应stable_duration秒），记录一帧作为"稳定局面"
    
    Args:
        video_path: 输入视频路径
        output_dir: 稳定帧输出目录
        motion_threshold: 运动阈值（归一化的运动能量）
        stable_duration: 稳定持续时间（秒）
    
    Returns:
        稳定帧文件路径列表
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"无法打开视频: {video_path}")
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 30.0  # 默认值
    
    stable_frame_count = int(fps * stable_duration)
    
    stable_frames = []
    prev_frame = None
    stable_counter = 0
    frame_idx = 0
    saved_count = 0
    
    print(f"视频FPS: {fps:.2f}, 稳定帧数要求: {stable_frame_count}")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        if prev_frame is not None:
            # 计算帧差
            diff = cv2.absdiff(gray, prev_frame)
            motion_energy = np.mean(diff) / 255.0  # 归一化到[0,1]
            
            if motion_energy < motion_threshold:
                stable_counter += 1
                if stable_counter >= stable_frame_count:
                    # 保存稳定帧
                    frame_filename = output_path / f"stable_{saved_count:04d}.jpg"
                    cv2.imwrite(str(frame_filename), frame)
                    stable_frames.append(str(frame_filename))
                    saved_count += 1
                    print(f"  保存稳定帧 {saved_count}: 帧{frame_idx}, 运动能量={motion_energy:.4f}")
                    stable_counter = 0  # 重置计数器，避免连续保存
            else:
                stable_counter = 0  # 运动检测到，重置计数器
        
        prev_frame = gray
        frame_idx += 1
    
    cap.release()
    
    if len(stable_frames) == 0:
        # 如果没有检测到稳定帧，至少保存第一帧和最后一帧
        cap = cv2.VideoCapture(video_path)
        ret, first_frame = cap.read()
        if ret:
            frame_filename = output_path / "stable_0000.jpg"
            cv2.imwrite(str(frame_filename), first_frame)
            stable_frames.append(str(frame_filename))
        cap.release()
    
    return stable_frames

