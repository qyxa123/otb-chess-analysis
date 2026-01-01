#!/usr/bin/env python3
"""
稳定帧抽取模块
功能：从视频中抽取稳定局面帧（运动检测）
"""

import cv2
import numpy as np
from pathlib import Path
from typing import List
import csv


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


def extract_stable_frames_debug(
    video_path: str,
    output_dir: str,
    motion_csv_path: str,
    target_fps: float = 10.0,
    motion_threshold: float = 0.01,
    stable_duration: float = 0.7,
    min_interval: float = 0.8
) -> List[str]:
    """
    从视频中抽取稳定帧（Debug版本，带详细输出）
    
    - 降采样到target_fps（默认10fps）
    - 计算motion：absdiff(prev, curr)->gray->mean
    - 当motion连续低于阈值 >= stable_duration秒，取该段中间帧作为稳定帧
    - 去重：相邻稳定帧至少间隔min_interval秒
    - 输出motion.csv（time,motion,is_stable）
    
    Args:
        video_path: 输入视频路径
        output_dir: 稳定帧输出目录
        motion_csv_path: motion.csv输出路径
        target_fps: 目标FPS（降采样）
        motion_threshold: 运动阈值
        stable_duration: 稳定持续时间（秒）
        min_interval: 最小间隔（秒）
    
    Returns:
        稳定帧文件路径列表
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"无法打开视频: {video_path}")
    
    original_fps = cap.get(cv2.CAP_PROP_FPS)
    if original_fps <= 0:
        original_fps = 30.0  # 默认值
    
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / original_fps
    
    print(f"  视频信息: {total_frames}帧, {original_fps:.2f}fps, {duration:.1f}秒")
    
    # 计算跳帧步数（降采样到target_fps）
    skip_frames = max(1, int(original_fps / target_fps))
    print(f"  降采样: 每{skip_frames}帧取1帧 (目标{target_fps}fps)")
    
    stable_frame_count = int(target_fps * stable_duration)
    min_interval_frames = int(target_fps * min_interval)
    
    print(f"  稳定要求: 连续{stable_frame_count}帧运动<{motion_threshold}")
    print(f"  最小间隔: {min_interval_frames}帧 ({min_interval}秒)")
    
    stable_frames = []
    motion_data = []
    
    prev_frame = None
    stable_counter = 0
    stable_start_idx = None
    frame_idx = 0
    saved_count = 0
    last_saved_idx = -min_interval_frames  # 确保第一帧可以保存
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        
        # 降采样：只处理每skip_frames帧中的第一帧
        if frame_idx % skip_frames != 0:
            frame_idx += 1
            continue
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        time_sec = frame_idx / original_fps
        
        if prev_frame is not None:
            # 计算帧差
            diff = cv2.absdiff(gray, prev_frame)
            motion_energy = np.mean(diff) / 255.0  # 归一化到[0,1]
            
            is_stable = motion_energy < motion_threshold
            
            if is_stable:
                if stable_start_idx is None:
                    stable_start_idx = frame_idx
                stable_counter += 1
            else:
                stable_start_idx = None
                stable_counter = 0
            
            # 记录motion数据
            motion_data.append({
                'time': time_sec,
                'motion': motion_energy,
                'is_stable': is_stable
            })
            
            # 检查是否达到稳定要求
            if stable_counter >= stable_frame_count and stable_start_idx is not None:
                # 检查是否满足最小间隔
                if frame_idx - last_saved_idx >= min_interval_frames:
                    # 取该稳定段的中间帧
                    mid_idx = stable_start_idx + (stable_counter // 2) * skip_frames
                    
                    # 读取中间帧
                    cap.set(cv2.CAP_PROP_POS_FRAMES, mid_idx)
                    ret_mid, mid_frame = cap.read()
                    if ret_mid:
                        frame_filename = output_path / f"frame_{saved_count+1:04d}.png"
                        cv2.imwrite(str(frame_filename), mid_frame)
                        stable_frames.append(str(frame_filename))
                        saved_count += 1
                        last_saved_idx = frame_idx
                        
                        mid_time = mid_idx / original_fps
                        print(f"  ✅ 稳定帧 {saved_count}: 帧{mid_idx}, 时间{mid_time:.2f}s, motion={motion_energy:.4f}")
                    
                    # 重置
                    stable_start_idx = None
                    stable_counter = 0
        else:
            # 第一帧
            motion_data.append({
                'time': time_sec,
                'motion': 0.0,
                'is_stable': False
            })
        
        prev_frame = gray
        frame_idx += 1
    
    cap.release()
    
    # 保存motion.csv
    with open(motion_csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['time', 'motion', 'is_stable'])
        writer.writeheader()
        writer.writerows(motion_data)
    
    print(f"  📊 Motion数据已保存: {motion_csv_path} ({len(motion_data)} 条记录)")
    
    if len(stable_frames) == 0:
        print("  ⚠️  未检测到稳定帧，至少保存第一帧")
        cap = cv2.VideoCapture(video_path)
        ret, first_frame = cap.read()
        if ret:
            frame_filename = output_path / "frame_0000.png"
            cv2.imwrite(str(frame_filename), first_frame)
            stable_frames.append(str(frame_filename))
        cap.release()
    
    return stable_frames

