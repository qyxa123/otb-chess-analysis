import os
from typing import Dict, List

import chess
import chess.pgn
import cv2
import numpy as np

from .board_locator import BoardLocator
from .frame_extractor import FrameExtractor, MockFrameGenerator
from .piece_detector import PieceDetector
from .reconstructor import MoveReconstructor
from .stockfish_module import StockfishModule
from .utils import ensure_dir, save_json


class Pipeline:
    def __init__(self, outdir: str, engine_path: str = None, depth: int = 12):
        self.outdir = outdir
        ensure_dir(outdir)
        self.board_locator = BoardLocator(outdir)
        self.piece_detector = PieceDetector(outdir)
        self.reconstructor = MoveReconstructor()
        self.stockfish = StockfishModule(engine_path, depth)

    def run_demo(self) -> Dict:
        initial = self._initial_board_state()
        state1 = initial.copy()
        state2 = self._apply_demo_move(state1, "e2", "e4")
        state3 = self._apply_demo_move(state2, "c7", "c5")
        state4 = self._apply_demo_move(state3, "g1", "f3")
        state5 = self._apply_demo_move(state4, "d7", "d6")
        states = [state1, state2, state3, state4, state5]
        generator = MockFrameGenerator()
        frame_paths = generator.generate_sequence(states, self.outdir)
        return self._process_frames(frame_paths)

    def run(self, video_path: str) -> Dict:
        extractor = FrameExtractor()
        stable_frames = extractor.extract(video_path, self.outdir)
        if not stable_frames:
            raise RuntimeError("No stable frames detected")
        return self._process_frames(stable_frames)

    def _process_frames(self, frame_paths: List[str]) -> Dict:
        first_warp, H = self.board_locator.locate(frame_paths[0])
        self.piece_detector.save_cell_debug(first_warp)
        occupancies: List[Dict[str, str]] = []
        warped_paths: List[str] = []
        for path in frame_paths:
            warped = self.board_locator.warp_with_h(path, H)
            occ = self.piece_detector.detect(warped)
            occupancies.append(occ)
            warped_path = os.path.join(self.outdir, "debug", os.path.basename(path).replace(".png", "_warped.png"))
            ensure_dir(os.path.dirname(warped_path))
            cv2.imwrite(warped_path, warped)
            warped_paths.append(warped_path)
        board, moves = self.reconstructor.reconstruct(occupancies)
        pgn_path = os.path.join(self.outdir, "game.pgn")
        self._save_pgn(moves, pgn_path)
        analysis = self.stockfish.analyze(moves)
        analysis_json_path = os.path.join(self.outdir, "analysis.json")
        save_json({"moves": analysis, "stable_frames": frame_paths}, analysis_json_path)
        return {
            "pgn_path": pgn_path,
            "analysis_json": analysis_json_path,
            "moves": analysis,
            "stable_frames": frame_paths,
        }

    def _initial_board_state(self) -> np.ndarray:
        state = np.zeros((8, 8), dtype=np.int32)
        state[1, :] = 1
        state[6, :] = -1
        state[0, :] = 1
        state[7, :] = -1
        return state

    def _apply_demo_move(self, state: np.ndarray, from_sq: str, to_sq: str) -> np.ndarray:
        letters = "abcdefgh"
        r_from = 8 - int(from_sq[1])
        c_from = letters.index(from_sq[0])
        r_to = 8 - int(to_sq[1])
        c_to = letters.index(to_sq[0])
        new_state = state.copy()
        new_state[r_to, c_to] = new_state[r_from, c_from]
        new_state[r_from, c_from] = 0
        return new_state

    def _save_pgn(self, moves: List[Dict], path: str) -> None:
        board = chess.Board()
        with open(path, "w", encoding="utf-8") as f:
            for move in moves:
                board.push_uci(move["uci"])
            game = chess.pgn.Game.from_board(board)
            f.write(str(game))
