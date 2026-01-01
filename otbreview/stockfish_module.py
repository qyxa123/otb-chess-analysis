import shutil
from typing import Dict, List, Optional

import chess
import chess.engine


class StockfishModule:
    def __init__(self, engine_path: Optional[str] = None, depth: int = 12):
        self.engine_path = engine_path or shutil.which("stockfish") or "stockfish"
        self.depth = depth

    def analyze(self, moves: List[Dict]) -> List[Dict]:
        board = chess.Board()
        annotated: List[Dict] = []
        try:
            with chess.engine.SimpleEngine.popen_uci(self.engine_path) as engine:
                for move_data in moves:
                    limit = chess.engine.Limit(depth=self.depth)
                    info_best = engine.analyse(board, limit, multipv=2)
                    best_score = info_best[0]["score"].pov(board.turn)
                    chosen_move = chess.Move.from_uci(move_data["uci"])
                    pv = [board.san(m) for m in info_best[0].get("pv", [])[:6]]
                    eval_cp = best_score.white().score(mate_score=100000)
                    board.push(chosen_move)
                    played_eval_info = engine.analyse(board, limit)
                    played_score = played_eval_info["score"].pov(board.turn)
                    played_cp = played_score.white().score(mate_score=100000)
                    delta = eval_cp - played_cp
                    classification = self._classify(delta)
                    annotated.append(
                        {
                            **move_data,
                            "evaluation_cp": played_cp,
                            "best_move_cp": eval_cp,
                            "delta_cp": delta,
                            "classification": classification,
                            "pv": pv,
                        }
                    )
        except FileNotFoundError:
            # Graceful fallback when engine is missing
            for move_data in moves:
                annotated.append(
                    {
                        **move_data,
                        "evaluation_cp": 0,
                        "best_move_cp": 0,
                        "delta_cp": 0,
                        "classification": "Engine missing",
                        "pv": [],
                    }
                )
        return annotated

    def _classify(self, delta: int) -> str:
        thresholds = [
            (20, "Best"),
            (60, "Excellent"),
            (120, "Good"),
            (200, "Inaccuracy"),
            (500, "Mistake"),
        ]
        for limit, label in thresholds:
            if abs(delta) <= limit:
                return label
        return "Blunder"
