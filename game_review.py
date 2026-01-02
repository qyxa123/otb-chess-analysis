"""Teaching-focused game review utilities.

This module converts raw engine/self analysis data into human-readable labels
and coach-style explanations similar to Chess.com "Game Review". It does not
require an external engine; it consumes structured evaluations such as those
produced by :mod:`self_analysis`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import io

import chess
import chess.pgn


LABEL_ORDER = [
    "Brilliant",
    "Great",
    "Best",
    "Good",
    "Mistake",
    "Blunder",
    "Miss",
]


@dataclass
class CoachBubble:
    """Lightweight container for coach feedback."""

    headline: str
    detail: str
    suggestions: List[str] = field(default_factory=list)


@dataclass
class MoveReview:
    """Classification and explanation for a single move."""

    ply: int
    san: str
    label: str
    eval_before: float
    eval_after: float
    perspective_change: float
    best_san: Optional[str]
    coach: CoachBubble


@dataclass
class GameReview:
    """Full review payload for one PGN."""

    headers: Dict[str, str]
    reviews: List[MoveReview]
    annotated_pgn: str


class GameReviewFormatter:
    """Format evaluation data into coach-friendly text."""

    @staticmethod
    def label_move(perspective_change: float, best_delta: Optional[float] = None) -> str:
        """Assign a descriptive label based on evaluation swings.

        Args:
            perspective_change: Evaluation change from the mover's perspective.
            best_delta: Difference between played move and the best move. Optional.
        """

        if perspective_change >= 50:
            return "Brilliant"
        if perspective_change >= 20:
            return "Great"
        if perspective_change >= -10:
            return "Best" if best_delta is None or best_delta < 5 else "Good"
        if perspective_change >= -50:
            return "Good" if perspective_change > -25 else "Mistake"
        if perspective_change >= -120:
            return "Blunder"
        return "Miss"

    @staticmethod
    def coach_text(label: str, san: str, best_san: Optional[str], swing: float) -> CoachBubble:
        intro = {
            "Brilliant": "闪电般的灵感！",
            "Great": "出色的想法",
            "Best": "稳健的最佳着法",
            "Good": "扎实的着法",
            "Mistake": "这里有改进空间",
            "Blunder": "严重失误",
            "Miss": "漏掉了关键战术",
        }.get(label, "走子解析")

        detail_parts = [f"你选择了 {san}。"]
        if swing > 0:
            detail_parts.append("这个选择提升了局面优势。")
        elif swing > -15:
            detail_parts.append("局面几乎没有变化，仍然可接受。")
        else:
            detail_parts.append("评估下降，留意对手的反击。")

        if best_san and best_san != san:
            detail_parts.append(f"引擎更喜欢 {best_san}，因为它能保持更高的稳定性。")

        suggestions = []
        if label in {"Mistake", "Blunder", "Miss"}:
            suggestions.append("关注对手的威胁与未防守的弱点。")
            suggestions.append("尝试计算一到两步后的战术变化。")
        elif label in {"Brilliant", "Great"}:
            suggestions.append("继续保持这种前瞻性的战术视角。")
        else:
            suggestions.append("保持中心控制并优化子力协调。")

        return CoachBubble(headline=intro, detail=" ".join(detail_parts), suggestions=suggestions)

    def build_review(self, pgn_text: str, analysis: List[Dict[str, object]]) -> GameReview:
        """Combine PGN and analysis results into a :class:`GameReview`."""
        pgn_game = chess.pgn.read_game(io.StringIO(pgn_text))
        if pgn_game is None:
            raise ValueError("Invalid PGN provided")

        reviews: List[MoveReview] = []
        board = pgn_game.board()
        annotated_game = chess.pgn.Game.from_board(board)
        annotated_game.headers.update(pgn_game.headers)

        for idx, move in enumerate(pgn_game.mainline_moves()):
            analysis_entry = analysis[idx]
            eval_before = float(analysis_entry.get("eval_before", 0.0))
            eval_after = float(analysis_entry.get("eval_after", 0.0))
            best_san = analysis_entry.get("best_san")

            mover_is_white = board.turn
            swing_raw = eval_after - eval_before
            perspective_change = swing_raw if mover_is_white else -swing_raw

            label = self.label_move(perspective_change, analysis_entry.get("best_diff"))
            san = board.san(move)
            coach = self.coach_text(label, san, best_san, perspective_change)

            reviews.append(
                MoveReview(
                    ply=idx + 1,
                    san=san,
                    label=label,
                    eval_before=eval_before,
                    eval_after=eval_after,
                    perspective_change=perspective_change,
                    best_san=best_san,
                    coach=coach,
                )
            )

            board.push(move)

            # Annotate PGN with comments for readability
            comment_parts = [f"{label}: Δ{perspective_change:.1f}cp"]
            if best_san:
                comment_parts.append(f"推荐 {best_san}")
            comment_parts.append(coach.headline)
            pgn_node = annotated_game.add_variation(move)
            pgn_node.comment = " | ".join(comment_parts)

        annotated_io = chess.pgn.StringIO()
        exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=True)
        annotated_game.accept(exporter)
        annotated_pgn = str(exporter)

        return GameReview(headers=dict(pgn_game.headers), reviews=reviews, annotated_pgn=annotated_pgn)


__all__ = [
    "CoachBubble",
    "GameReview",
    "GameReviewFormatter",
    "MoveReview",
]
