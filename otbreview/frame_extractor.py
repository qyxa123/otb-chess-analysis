import os
from typing import List, Tuple

import cv2
import numpy as np

from .utils import ensure_dir


class FrameExtractor:
    """Extracts stable frames from a video using motion energy heuristics."""

    def __init__(self, motion_threshold: float = 3.5, stable_seconds: float = 0.7, sample_rate: int = 1):
        self.motion_threshold = motion_threshold
        self.stable_seconds = stable_seconds
        self.sample_rate = sample_rate

    def extract(self, video_path: str, outdir: str) -> List[str]:
        stable_dir = ensure_dir(os.path.join(outdir, "debug", "stable_frames"))
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise FileNotFoundError(f"Cannot open video: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        required_stable = int(self.stable_seconds * fps)
        prev_gray = None
        stable_counter = 0
        frame_idx = 0
        saved_frames: List[str] = []

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_idx += 1
            if frame_idx % self.sample_rate != 0:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if prev_gray is None:
                prev_gray = gray
                continue
            diff = cv2.absdiff(gray, prev_gray)
            motion_energy = float(np.mean(diff))
            if motion_energy < self.motion_threshold:
                stable_counter += 1
            else:
                stable_counter = 0
            prev_gray = gray
            if stable_counter >= required_stable:
                stable_counter = 0
                save_path = os.path.join(stable_dir, f"stable_{frame_idx:05d}.png")
                cv2.imwrite(save_path, frame)
                saved_frames.append(save_path)
        cap.release()
        return saved_frames


class MockFrameGenerator:
    """Create synthetic top-down board frames for demo usage."""

    def __init__(self, size: int = 800):
        self.size = size

    def _draw_board(self, board_state: np.ndarray) -> np.ndarray:
        img = np.zeros((self.size, self.size, 3), dtype=np.uint8)
        light = (240, 217, 181)
        dark = (181, 136, 99)
        cell = self.size // 8
        for r in range(8):
            for c in range(8):
                color = light if (r + c) % 2 == 0 else dark
                cv2.rectangle(img, (c * cell, r * cell), ((c + 1) * cell, (r + 1) * cell), color, -1)
                if board_state[r, c] != 0:
                    piece_color = (255, 255, 255) if board_state[r, c] == 1 else (20, 20, 20)
                    cv2.circle(img, (c * cell + cell // 2, r * cell + cell // 2), cell // 3, piece_color, -1)
        return img

    def generate_sequence(self, states: List[np.ndarray], outdir: str) -> List[str]:
        stable_dir = ensure_dir(os.path.join(outdir, "debug", "stable_frames"))
        paths: List[str] = []
        for idx, state in enumerate(states):
            frame = self._draw_board(state)
            path = os.path.join(stable_dir, f"mock_{idx:02d}.png")
            cv2.imwrite(path, frame)
            paths.append(path)
        return paths
