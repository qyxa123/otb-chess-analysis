"""Exercise a real encoded video through detection, decoding and replay output.

These synthetic markers verify the software pipeline deterministically. They do
not measure recognition accuracy on recorded physical chess pieces or lighting.
"""

import csv
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import chess
import chess.pgn
import cv2
import numpy as np

from otbreview.pipeline.main import analyze_video


MOVES = ["e4", "e5", "Nf3", "Nc6", "Bb5", "a6", "Bxc6", "dxc6"]
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BOARD_OFFSET = 80
BOARD_SIZE = 800
FRAME_SIZE = BOARD_SIZE + BOARD_OFFSET * 2


def tagged_positions(moves=MOVES):
    """Keep physical tag identity across moves and captures."""
    config = json.loads((PROJECT_ROOT / "config" / "piece_id_map.json").read_text())
    positions = {chess.parse_square(info["square"]): int(tag) for tag, info in config.items()}
    board = chess.Board()

    def grid():
        result = [[0] * 8 for _ in range(8)]
        for square, tag in positions.items():
            result[7 - chess.square_rank(square)][chess.square_file(square)] = tag
        return result

    states = [grid()]
    for san in moves:
        move = board.parse_san(san)
        tag = positions.pop(move.from_square)
        positions[move.to_square] = tag
        board.push(move)
        states.append(grid())
    return states


def render_tagged_board(ids):
    """Render 4X4 corner IDs and 5X5 piece IDs in separate dictionaries."""
    image = np.full((FRAME_SIZE, FRAME_SIZE, 3), 255, dtype=np.uint8)
    for row in range(8):
        for col in range(8):
            y, x = BOARD_OFFSET + row * 100, BOARD_OFFSET + col * 100
            image[y:y + 100, x:x + 100] = 205 if (row + col) % 2 == 0 else 115
            tag = ids[row][col]
            if not tag:
                continue
            # Quiet zones keep the black marker border separate from dark cells.
            image[y + 20:y + 80, x + 20:x + 80] = 255
            dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100)
            marker = cv2.aruco.generateImageMarker(dictionary, tag, 42)
            image[y + 29:y + 71, x + 29:x + 71] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)

    corner_dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    for tag, (x, y) in enumerate(((80, 80), (880, 80), (880, 880), (80, 880))):
        image[y - 32:y + 32, x - 32:x + 32] = 255
        marker = cv2.aruco.generateImageMarker(corner_dictionary, tag, 48)
        image[y - 24:y + 24, x - 24:x + 24] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    return image


def write_tagged_video(destination, grids):
    """Use actual MJPG encoding and a short moving transition between boards."""
    writer = cv2.VideoWriter(
        str(destination), cv2.VideoWriter_fourcc(*"MJPG"), 10,
        (FRAME_SIZE, FRAME_SIZE),
    )
    if not writer.isOpened():
        raise RuntimeError("OpenCV MJPG video writer is unavailable")
    try:
        for idx, ids in enumerate(grids):
            if idx:
                writer.write(np.zeros((FRAME_SIZE, FRAME_SIZE, 3), dtype=np.uint8))
            frame = render_tagged_board(ids)
            # 1 second of stability also permits the debug extractor's 0.8s gap.
            for _ in range(10):
                writer.write(frame)
    finally:
        writer.release()


class VideoPipelineTests(unittest.TestCase):
    def test_tagged_video_produces_complete_capture_pgn_and_offline_replay(self):
        expected_grids = tagged_positions()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video_path = root / "tagged_game.avi"
            write_tagged_video(video_path, expected_grids)
            output = root / "run"
            # Exercise real analysis through its documented no-engine fallback.
            with patch("otbreview.pipeline.analyze.find_stockfish", return_value=None), redirect_stdout(io.StringIO()):
                analyze_video(
                    str(video_path), str(output), use_markers=True,
                    use_piece_tags=True, stable_duration=0.2, target_fps=10,
                    depth=1, pv_length=2,
                )
            with (output / "game.pgn").open(encoding="utf-8") as source:
                game = chess.pgn.read_game(source)
            self.assertIsNotNone(game)
            self.assertEqual(game.errors, [])
            board = game.board()
            observed_moves = []
            for move in game.mainline_moves():
                observed_moves.append(board.san(move))
                board.push(move)
            self.assertEqual(observed_moves, MOVES)
            self.assertEqual(json.loads((output / "board_ids.json").read_text()), expected_grids)
            with (output / "debug" / "tag_metrics.csv").open() as source:
                metrics = list(csv.DictReader(source))
            self.assertEqual(len(metrics), 9)
            self.assertTrue(all(int(row["corner_markers"]) == 4 for row in metrics))
            self.assertEqual(int(metrics[0]["tag_ids"]), 32)
            self.assertEqual(int(metrics[-1]["tag_ids"]), 30)
            analysis = json.loads((output / "analysis.json").read_text())
            self.assertEqual(len(analysis["moves"]), 9)
            self.assertEqual(analysis["metadata"]["analysis_source"], "material")
            self.assertFalse(analysis["metadata"]["partial"])
            self.assertEqual([item["san"] for item in json.loads((output / "moves.json").read_text())], MOVES)
            html = (output / "index.html").read_text(encoding="utf-8")
            replay_match = re.search(r'<script id="replay-data" type="application/json">(.*?)</script>', html, re.DOTALL)
            self.assertIsNotNone(replay_match)
            replay = json.loads(replay_match.group(1))
            self.assertEqual(len(replay["positions"]), 9)
            self.assertIn("<svg", replay["positions"][-1]["svg"])
            self.assertEqual(replay["positions"][-1]["fen"], board.fen())
            self.assertNotIn("__REPLAY_DATA__", html)
            self.assertIn("dxc6", html)


if __name__ == "__main__":
    unittest.main()
