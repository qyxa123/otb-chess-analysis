import os
from typing import Dict

import cv2
import numpy as np

from .utils import ensure_dir


class PieceDetector:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir

    def detect(self, warped_board: np.ndarray) -> Dict[str, str]:
        cell_size = warped_board.shape[0] // 8
        occupancy: Dict[str, str] = {}
        board_gray = cv2.cvtColor(warped_board, cv2.COLOR_BGR2GRAY)
        _, global_thresh = cv2.threshold(board_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        background_mean = np.mean(board_gray)
        letters = "abcdefgh"
        for r in range(8):
            for c in range(8):
                crop = warped_board[r * cell_size : (r + 1) * cell_size, c * cell_size : (c + 1) * cell_size]
                gray = board_gray[r * cell_size : (r + 1) * cell_size, c * cell_size : (c + 1) * cell_size]
                mask = cv2.threshold(gray, global_thresh, 255, cv2.THRESH_BINARY_INV)[1]
                fg_ratio = float(np.sum(mask > 0)) / mask.size
                square = f"{letters[c]}{8 - r}"
                if fg_ratio < 0.12:
                    occupancy[square] = "empty"
                    continue
                mean_intensity = float(np.mean(gray[mask > 0])) if np.sum(mask > 0) > 0 else float(np.mean(gray))
                color = "white" if mean_intensity > background_mean else "black"
                occupancy[square] = color
        return occupancy

    def save_cell_debug(self, warped_board: np.ndarray) -> None:
        debug_cells_dir = ensure_dir(os.path.join(self.output_dir, "debug", "cells"))
        cell_size = warped_board.shape[0] // 8
        for r in range(8):
            for c in range(8):
                cell_img = warped_board[r * cell_size : (r + 1) * cell_size, c * cell_size : (c + 1) * cell_size]
                cv2.imwrite(os.path.join(debug_cells_dir, f"occ_{r}_{c}.png"), cell_img)
