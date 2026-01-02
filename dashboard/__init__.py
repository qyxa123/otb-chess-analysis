"""Lightweight Flask dashboard for game review and exploration."""
from __future__ import annotations

from pathlib import Path
from typing import Dict

from flask import Flask, jsonify, render_template

from game_review import GameReviewFormatter
from self_analysis import analyze_pgn_file
from explore import extract_opening_from_pgn

BASE_DIR = Path(__file__).parent
SAMPLE_PGN = BASE_DIR / "sample_data" / "sample_game.pgn"


def build_payload() -> Dict[str, object]:
    pgn_text = SAMPLE_PGN.read_text(encoding="utf-8")
    analysis = analyze_pgn_file(str(SAMPLE_PGN))
    review = GameReviewFormatter().build_review(pgn_text, analysis)
    openings = extract_opening_from_pgn(pgn_text)
    return {
        "pgn": pgn_text,
        "analysis": analysis,
        "review": review,
        "openings": openings,
    }


def create_app() -> Flask:
    app = Flask(__name__)
    payload = build_payload()

    @app.route("/")
    def index():
        return render_template("index.html", data=payload)

    @app.route("/api/data")
    def api_data():
        serialized_review = {
            "headers": payload["review"].headers,
            "moves": [
                {
                    "ply": r.ply,
                    "san": r.san,
                    "label": r.label,
                    "eval_before": r.eval_before,
                    "eval_after": r.eval_after,
                    "swing": r.perspective_change,
                    "best_san": r.best_san,
                    "coach": {
                        "headline": r.coach.headline,
                        "detail": r.coach.detail,
                        "suggestions": r.coach.suggestions,
                    },
                }
                for r in payload["review"].reviews
            ],
            "annotated_pgn": payload["review"].annotated_pgn,
        }
        return jsonify(
            {
                "pgn": payload["pgn"],
                "analysis": payload["analysis"],
                "review": serialized_review,
                "openings": payload["openings"],
            }
        )

    return app


__all__ = ["create_app"]
