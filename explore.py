"""Opening/database exploration helpers."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
import io

import chess
import chess.pgn

DATA_DIR = Path(__file__).parent / "dashboard" / "sample_data"


@dataclass
class OpeningLine:
    eco: str
    name: str
    moves: str
    white_win_rate: float
    black_win_rate: float
    draw_rate: float
    plans: List[str]
    notable_games: List[Dict[str, str]]


class OpeningDatabase:
    """Tiny opening reference used by the dashboard."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or DATA_DIR / "openings.json"
        self._lines = [OpeningLine(**entry) for entry in json.loads(self.path.read_text())]

    def match(self, moves: List[str]) -> List[OpeningLine]:
        prefix = " ".join(moves)
        return [line for line in self._lines if line.moves.startswith(prefix)]

    def recommendations(self, moves: List[str]) -> Dict[str, object]:
        matches = self.match(moves)
        if not matches:
            return {"openings": [], "message": "暂无匹配的开局，尝试探索新的着法"}
        return {
            "openings": [line.__dict__ for line in matches],
            "message": "根据你的走法，推荐相关开局与对局。",
        }


def extract_opening_from_pgn(pgn_text: str) -> Dict[str, object]:
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        return {"openings": [], "message": "未找到有效PGN"}
    board = game.board()
    san_moves = []
    for move in game.mainline_moves():
        san_moves.append(board.san(move))
        board.push(move)
        if len(san_moves) >= 10:  # limit early phase
            break

    db = OpeningDatabase()
    return db.recommendations(san_moves)


__all__ = ["OpeningDatabase", "extract_opening_from_pgn", "OpeningLine"]
