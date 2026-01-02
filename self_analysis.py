"""Engine-lite self analysis utilities.

This module offers lightweight analysis with :mod:`python-chess` to produce
evaluation bars, candidate lines, and feedback JSON for the dashboard.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
import io

import chess
import chess.pgn


PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 300,
    chess.BISHOP: 320,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}


@dataclass
class CandidateLine:
    san: str
    eval_after: float
    continuation: str


@dataclass
class MoveAnalysis:
    ply: int
    move_san: str
    eval_before: float
    eval_after: float
    best_san: Optional[str]
    best_diff: float
    candidate_lines: List[CandidateLine]
    suggestion_arrow: Optional[Dict[str, str]]
    feedback: str

    def as_json(self) -> Dict[str, object]:
        data = asdict(self)
        data["candidate_lines"] = [asdict(c) for c in self.candidate_lines]
        return data


def material_eval(board: chess.Board) -> float:
    """Simple material-only evaluation in centipawns (positive for White)."""
    score = 0
    for piece_type, value in PIECE_VALUES.items():
        score += len(board.pieces(piece_type, chess.WHITE)) * value
        score -= len(board.pieces(piece_type, chess.BLACK)) * value
    return float(score)


def candidate_variations(board: chess.Board, limit: int = 3) -> List[CandidateLine]:
    """Generate lightweight candidate moves ranked by resulting material."""
    scored_moves = []
    for move in list(board.legal_moves)[:10]:  # sample subset for speed
        san = board.san(move)
        board.push(move)
        eval_after = material_eval(board)
        continuation = " ".join(board.san(m) for m in list(board.legal_moves)[:3])
        scored_moves.append((eval_after if board.turn else -eval_after, san, continuation, move))
        board.pop()

    scored_moves.sort(key=lambda t: t[0], reverse=True)
    best = []
    for _, san, continuation, move in scored_moves[:limit]:
        board.push(move)
        best.append(
            CandidateLine(
                san=san,
                eval_after=material_eval(board),
                continuation=continuation,
            )
        )
        board.pop()
    return best


def analyze_pgn(pgn_text: str) -> List[Dict[str, object]]:
    """Analyze a PGN string and return JSON-ready move analysis list."""
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("Invalid PGN provided")

    board = game.board()
    analyses: List[Dict[str, object]] = []

    for idx, move in enumerate(game.mainline_moves()):
        eval_before = material_eval(board)
        candidate_lines = candidate_variations(board)
        best_line = candidate_lines[0] if candidate_lines else None

        move_san = board.san(move)
        board.push(move)
        eval_after = material_eval(board)
        best_san = best_line.san if best_line else None
        best_diff = (best_line.eval_after - eval_after) if best_line else 0.0

        feedback = _feedback_text(eval_before, eval_after, move_san)
        suggestion_arrow = _arrow_for_move(move)

        analysis = MoveAnalysis(
            ply=idx + 1,
            move_san=move_san,
            eval_before=eval_before,
            eval_after=eval_after,
            best_san=best_san,
            best_diff=best_diff,
            candidate_lines=candidate_lines,
            suggestion_arrow=suggestion_arrow,
            feedback=feedback,
        )
        analyses.append(analysis.as_json())

    return analyses


def _feedback_text(eval_before: float, eval_after: float, san: str) -> str:
    swing = eval_after - eval_before
    if swing > 40:
        return f"{san} 强化了先手，优势扩大。"
    if swing > 0:
        return f"{san} 保持了压力，局面稳健。"
    if swing > -40:
        return f"{san} 略有不精，但仍可防守。"
    return f"{san} 让局面迅速恶化，注意战术漏洞。"


def _arrow_for_move(move: chess.Move) -> Dict[str, str]:
    return {
        "from": chess.square_name(move.from_square),
        "to": chess.square_name(move.to_square),
    }


def analyze_pgn_file(path: str) -> List[Dict[str, object]]:
    with open(path, "r", encoding="utf-8") as fh:
        return analyze_pgn(fh.read())


__all__ = [
    "analyze_pgn",
    "analyze_pgn_file",
    "MoveAnalysis",
    "CandidateLine",
]
