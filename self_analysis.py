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
    analysis_source: str = "material"

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
    mover = board.turn
    scored_moves = []
    for move in list(board.legal_moves):
        san = board.san(move)
        board.push(move)
        eval_after = material_eval(board)
        board.pop()
        scored_moves.append((eval_after if mover == chess.WHITE else -eval_after, san, move, eval_after))

    scored_moves.sort(key=lambda t: t[0], reverse=True)
    best = []
    for _, san, move, eval_after in scored_moves[:max(0, limit)]:
        # The earlier implementation joined three alternative replies as though
        # they were a single variation. Build a legal, sequential line instead.
        preview = board.copy()
        preview.push(move)
        continuation = []
        for _ in range(3):
            replies = list(preview.legal_moves)
            if not replies:
                break
            def reply_score(reply):
                preview.push(reply)
                score = material_eval(preview)
                preview.pop()
                return score
            reply = max(replies, key=reply_score) if preview.turn == chess.WHITE else min(replies, key=reply_score)
            continuation.append(preview.san(reply))
            preview.push(reply)
        best.append(
            CandidateLine(
                san=san,
                eval_after=eval_after,
                continuation=" ".join(continuation),
            )
        )
    return best


def analyze_pgn(pgn_text: str) -> List[Dict[str, object]]:
    """Analyze a PGN string and return JSON-ready move analysis list."""
    game = parse_pgn_text(pgn_text)

    board = game.board()
    analyses: List[Dict[str, object]] = []

    for idx, move in enumerate(game.mainline_moves()):
        mover = board.turn
        eval_before = material_eval(board)
        candidate_lines = candidate_variations(board)
        best_line = candidate_lines[0] if candidate_lines else None
        suggestion_arrow = _arrow_for_move(board.parse_san(best_line.san)) if best_line else None

        move_san = board.san(move)
        board.push(move)
        eval_after = material_eval(board)
        best_san = best_line.san if best_line else None
        best_diff = ((best_line.eval_after - eval_after) * (1 if mover else -1)) if best_line else 0.0
        best_diff = max(0.0, best_diff)

        feedback = _feedback_text(eval_before, eval_after, move_san, mover)

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


def parse_pgn_text(pgn_text: str) -> chess.pgn.Game:
    """Reject illegal or unrecognized input instead of accepting a partial game."""
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None or game.errors:
        raise ValueError("Invalid PGN provided: missing game or illegal move")
    if not game.board().is_valid():
        raise ValueError("Invalid PGN starting position")
    if not game.variations and not pgn_text.lstrip().startswith('[') and pgn_text.strip() not in {
        '*', '1-0', '0-1', '1/2-1/2',
    }:
        raise ValueError("Invalid PGN provided: no moves or PGN headers")
    return game


def _feedback_text(eval_before: float, eval_after: float, san: str, mover: bool = chess.WHITE) -> str:
    swing = (eval_after - eval_before) * (1 if mover else -1)
    if swing > 40:
        return f"{san} 增加了己方子力优势（仅基础子力评估）。"
    if swing > 0:
        return f"{san} 略微增加了己方子力（仅基础子力评估）。"
    if swing > -40:
        return f"{san} 的子力差基本不变；战术优劣需要引擎判断。"
    return f"{san} 减少了己方子力；请用引擎确认是否为合理弃子。"


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
