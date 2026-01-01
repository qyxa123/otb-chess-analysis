import os
from typing import List, Optional, Tuple

import cv2
import numpy as np

from .utils import ensure_dir


class BoardLocator:
    def __init__(self, output_dir: str, target_size: int = 800):
        self.output_dir = output_dir
        self.target_size = target_size
        self._has_aruco = hasattr(cv2, "aruco")
        if self._has_aruco:
            self._aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
            self._aruco_params = cv2.aruco.DetectorParameters_create()

    def locate(self, frame_path: str) -> Tuple[np.ndarray, np.ndarray]:
        frame = cv2.imread(frame_path)
        if frame is None:
            raise FileNotFoundError(frame_path)
        corners = self._detect_aruco(frame)
        if corners is None:
            corners = self._detect_contours(frame)
        if corners is None:
            raise RuntimeError("Unable to detect board corners in frame")
        warp, H = self._warp(frame, corners)
        self._save_debug(frame, warp, corners)
        return warp, H

    def warp_with_h(self, frame_path: str, H: np.ndarray) -> np.ndarray:
        frame = cv2.imread(frame_path)
        if frame is None:
            raise FileNotFoundError(frame_path)
        warp = cv2.warpPerspective(frame, H, (self.target_size, self.target_size))
        return warp

    def _detect_aruco(self, frame: np.ndarray) -> Optional[np.ndarray]:
        if not self._has_aruco:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = cv2.aruco.detectMarkers(gray, self._aruco_dict, parameters=self._aruco_params)
        if ids is None or len(ids) < 4:
            return None
        # sort markers by id so 0: top-left,1:top-right,2:bottom-right,3:bottom-left recommended
        id_to_corner = {int(i[0]): c[0] for i, c in zip(ids, corners)}
        needed = [0, 1, 2, 3]
        if not all(i in id_to_corner for i in needed):
            return None
        ordered = np.array([id_to_corner[i][0] for i in needed], dtype=np.float32)
        return ordered

    def _detect_contours(self, frame: np.ndarray) -> Optional[np.ndarray]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        for cnt in contours:
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            if len(approx) == 4:
                return approx[:, 0, :].astype(np.float32)
        return None

    def _warp(self, frame: np.ndarray, corners: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        dest = np.array(
            [[0, 0], [self.target_size - 1, 0], [self.target_size - 1, self.target_size - 1], [0, self.target_size - 1]],
            dtype=np.float32,
        )
        H, _ = cv2.findHomography(corners, dest)
        warped = cv2.warpPerspective(frame, H, (self.target_size, self.target_size))
        return warped, H

    def _save_debug(self, frame: np.ndarray, warp: np.ndarray, corners: np.ndarray) -> None:
        debug_dir = ensure_dir(os.path.join(self.output_dir, "debug"))
        overlay = frame.copy()
        for i in range(4):
            pt1 = tuple(corners[i].astype(int))
            pt2 = tuple(corners[(i + 1) % 4].astype(int))
            cv2.line(overlay, pt1, pt2, (0, 255, 0), 3)
        cv2.imwrite(os.path.join(debug_dir, "board_detection_overlay.png"), overlay)
        cv2.imwrite(os.path.join(debug_dir, "warped_board.png"), warp)
        self._save_grid_overlay(warp)

    def _save_grid_overlay(self, warp: np.ndarray) -> None:
        grid = warp.copy()
        cell = self.target_size // 8
        for i in range(1, 8):
            cv2.line(grid, (0, i * cell), (self.target_size, i * cell), (0, 0, 255), 1)
            cv2.line(grid, (i * cell, 0), (i * cell, self.target_size), (0, 0, 255), 1)
        debug_cells_dir = ensure_dir(os.path.join(self.output_dir, "debug", "cells"))
        cv2.imwrite(os.path.join(self.output_dir, "debug", "grid_overlay.png"), grid)
        cell_size = warp.shape[0] // 8
        for r in range(8):
            for c in range(8):
                cell_img = warp[r * cell_size : (r + 1) * cell_size, c * cell_size : (c + 1) * cell_size]
                cv2.imwrite(os.path.join(debug_cells_dir, f"{r}_{c}.png"), cell_img)
