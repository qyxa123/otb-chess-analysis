"""Teaching-focused game review utilities.

This module converts raw engine/self analysis data into human-readable labels
and coach-style explanations similar to Chess.com "Game Review". It does not
require an external engine; it consumes structured evaluations such as those
produced by :mod:`self_analysis`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import chess
import chess.pgn
from self_analysis import parse_pgn_text


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

        # A material gain alone cannot establish a brilliant move. Compare
        # against the available best move, using a swing only as a fallback.
        loss = max(0.0, float(best_delta)) if best_delta is not None else max(0.0, -perspective_change)
        if loss <= 10:
            return "Best"
        if loss <= 50:
            return "Good"
        if loss <= 100:
            return "Mistake"
        return "Blunder"

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
            detail_parts.append(f"可比较推荐着法 {best_san}，再结合完整变化判断。")

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
        pgn_game = parse_pgn_text(pgn_text)
        moves = list(pgn_game.mainline_moves())
        if len(analysis) != len(moves):
            raise ValueError("Analysis length does not match the PGN move count")

        reviews: List[MoveReview] = []
        board = pgn_game.board()
        annotated_game = chess.pgn.Game.from_board(board)
        annotated_game.headers.update(pgn_game.headers)
        annotated_node = annotated_game

        for idx, move in enumerate(moves):
            analysis_entry = analysis[idx]
            eval_before = float(analysis_entry.get("eval_before", 0.0))
            eval_after = float(analysis_entry.get("eval_after", 0.0))
            best_san = analysis_entry.get("best_san")

            mover_is_white = board.turn
            swing_raw = eval_after - eval_before
            perspective_change = swing_raw if mover_is_white else -swing_raw

            material_only = analysis_entry.get("analysis_source") == "material"
            label = "Material" if material_only else self.label_move(perspective_change, analysis_entry.get("best_diff"))
            san = board.san(move)
            coach = self.coach_text(label, san, best_san, perspective_change)
            if material_only:
                coach = CoachBubble(
                    headline="基础子力变化",
                    detail=str(analysis_entry.get("feedback", "仅比较子力数量，未进行引擎战术分析。")),
                    suggestions=["安装Stockfish后再判断最佳着法和失误。"],
                )

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
            annotated_node = annotated_node.add_variation(move)
            annotated_node.comment = " | ".join(comment_parts)

        exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=True)
        annotated_pgn = annotated_game.accept(exporter)

        return GameReview(headers=dict(pgn_game.headers), reviews=reviews, annotated_pgn=annotated_pgn)


__all__ = [
    "CoachBubble",
    "GameReview",
    "GameReviewFormatter",
    "MoveReview",
]
