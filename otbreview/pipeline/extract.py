#!/usr/bin/env python3
"""Extract one representative frame from each stable section of a video."""

import csv
import math
from collections import deque
from pathlib import Path
from typing import List

import cv2
import numpy as np


def _validate_options(motion_threshold: float, stable_duration: float) -> None:
    if not math.isfinite(motion_threshold) or not 0 < motion_threshold <= 1:
        raise ValueError("motion_threshold必须大于0且不超过1")
    if not math.isfinite(stable_duration) or stable_duration < 0:
        raise ValueError("stable_duration必须为非负数")


def _video_fps(cap) -> float:
    fps = cap.get(cv2.CAP_PROP_FPS)
    return fps if math.isfinite(fps) and fps > 0 else 30.0


def _save_frame(path: Path, frame: np.ndarray) -> str:
    if not cv2.imwrite(str(path), frame):
        raise OSError(f"无法保存稳定帧: {path}")
    return str(path)


def extract_stable_frames(
    video_path: str,
    output_dir: str,
    motion_threshold: float = 0.01,
    stable_duration: float = 0.5,
) -> List[str]:
    """Save one frame after each motion-free interval of stable_duration seconds.

    A static board is emitted only once, until motion starts another interval.
    For a clip shorter than the interval, retain the first frame as a fallback.
    """
    _validate_options(motion_threshold, stable_duration)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        cap.release()
        raise ValueError(f"无法打开视频: {video_path}")

    fps = _video_fps(cap)
    required_intervals = max(1, math.ceil(fps * stable_duration))
    print(f"视频FPS: {fps:.2f}, 稳定帧数要求: {required_intervals}")
    stable_frames = []
    first_frame = None
    previous_gray = None
    stable_counter = 0
    plateau_saved = False
    frame_idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if first_frame is None:
                first_frame = frame.copy()
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if previous_gray is not None:
                motion = float(np.mean(cv2.absdiff(gray, previous_gray))) / 255.0
                if motion < motion_threshold:
                    stable_counter += 1
                    if stable_counter >= required_intervals and not plateau_saved:
                        path = output_path / f"stable_{len(stable_frames):04d}.jpg"
                        stable_frames.append(_save_frame(path, frame))
                        plateau_saved = True
                        print(f"  保存稳定帧 {len(stable_frames)}: 帧{frame_idx}, 运动能量={motion:.4f}")
                else:
                    stable_counter = 0
                    plateau_saved = False
            previous_gray = gray
            frame_idx += 1
    finally:
        cap.release()

    if not stable_frames and first_frame is not None:
        stable_frames.append(_save_frame(output_path / "stable_0000.jpg", first_frame))
    return stable_frames


def extract_stable_frames_debug(
    video_path: str,
    output_dir: str,
    motion_csv_path: str,
    target_fps: float = 10.0,
    motion_threshold: float = 0.01,
    stable_duration: float = 0.7,
    min_interval: float = 0.8,
) -> List[str]:
    """Sample motion and save the middle of each stable section once.

    Durations use the actual sampling rate, capped at the video's frame rate.
    Midpoint images are buffered without seeking the active video capture, so
    subsequent frames and CSV timestamps always remain in chronological order.
    """
    _validate_options(motion_threshold, stable_duration)
    if not math.isfinite(target_fps) or target_fps <= 0:
        raise ValueError("target_fps必须大于0")
    if not math.isfinite(min_interval) or min_interval < 0:
        raise ValueError("min_interval必须为非负数")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    csv_path = Path(motion_csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        cap.release()
        raise ValueError(f"无法打开视频: {video_path}")

    fps = _video_fps(cap)
    skip_frames = max(1, round(fps / target_fps))
    sampled_fps = fps / skip_frames
    required_intervals = max(1, math.ceil(sampled_fps * stable_duration))
    # Only retain one stability window, even when min_interval delays a save.
    stable_window = deque(maxlen=required_intervals + 1)
    print(f"  视频FPS: {fps:.2f}; 每{skip_frames}帧取1帧 (实际{sampled_fps:.2f}fps)")
    print(f"  稳定要求: 连续{required_intervals}次运动<{motion_threshold}")

    stable_frames = []
    first_frame = None
    previous_gray = None
    previous_sample = None
    frame_idx = 0
    stable_counter = 0
    plateau_saved = False
    last_saved_time = -float("inf")
    try:
        with csv_path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["time", "motion", "is_stable"])
            writer.writeheader()
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                current_idx = frame_idx
                frame_idx += 1
                if current_idx % skip_frames:
                    continue
                if first_frame is None:
                    first_frame = frame.copy()
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                time_sec = current_idx / fps
                motion = 0.0
                is_stable = False
                if previous_gray is not None:
                    motion = float(np.mean(cv2.absdiff(gray, previous_gray))) / 255.0
                    is_stable = motion < motion_threshold
                    if is_stable:
                        if stable_counter == 0:
                            stable_window.append(previous_sample)
                        stable_counter += 1
                        if not plateau_saved:
                            stable_window.append((time_sec, frame.copy()))
                            if stable_counter >= required_intervals:
                                mid_time, mid_frame = stable_window[len(stable_window) // 2]
                                if mid_time - last_saved_time >= min_interval:
                                    path = output_path / f"frame_{len(stable_frames) + 1:04d}.png"
                                    stable_frames.append(_save_frame(path, mid_frame))
                                    last_saved_time = mid_time
                                    plateau_saved = True
                                    stable_window.clear()
                                    print(f"  稳定帧 {len(stable_frames)}: 时间{mid_time:.2f}s, motion={motion:.4f}")
                    else:
                        stable_counter = 0
                        plateau_saved = False
                        stable_window.clear()
                writer.writerow({"time": time_sec, "motion": motion, "is_stable": is_stable})
                previous_gray = gray
                previous_sample = (time_sec, frame.copy())
    finally:
        cap.release()

    print(f"  Motion数据已保存: {csv_path}")
    if not stable_frames and first_frame is not None:
        stable_frames.append(_save_frame(output_path / "frame_0000.png", first_frame))
    return stable_frames
