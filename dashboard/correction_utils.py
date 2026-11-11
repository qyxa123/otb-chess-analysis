"""Validated PGN corrections shared by the Studio and its regression tests."""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import List, Tuple

import chess
import chess.pgn


def replace_move(pgn_text: str, ply: int, replacement_san: str) -> Tuple[str, int]:
    """Replace a ply and retain the following moves until the first illegal one."""
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None or game.errors:
        raise ValueError("Could not parse the complete PGN.")
    moves = list(game.mainline_moves())
    if not 1 <= ply <= len(moves):
        raise ValueError("Move number is outside this game.")
    corrected = chess.pgn.Game()
    corrected.headers.update(game.headers)
    corrected.headers["Result"] = "*"
    board = game.board()
    node = corrected
    retained = 0
    for index, old_move in enumerate(moves, 1):
        move = board.parse_san(replacement_san) if index == ply else old_move
        if move not in board.legal_moves:
            break
        node = node.add_main_variation(move)
        board.push(move)
        retained += 1
    if board.is_game_over():
        corrected.headers["Result"] = board.result()
    return str(corrected), len(moves) - retained


def regenerate_review(run_dir: Path, pgn_text: str, confidence: List[dict] | None = None,
                      tag_board_path: Path | None = None) -> str | None:
    """Write mutually consistent PGN, move trace, analysis, and replay artifacts."""
    from otbreview.pipeline.analyze import analyze_game, find_stockfish
    from otbreview.pipeline.classify import classify_moves
    from otbreview.pipeline.keymoves import find_key_moves
    from otbreview.web.generate import generate_web_replay

    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None or game.errors:
        raise ValueError("Could not parse the complete PGN.")
    board = game.board()
    trace = []
    for move in game.mainline_moves():
        san = board.san(move)
        board.push(move)
        trace.append({"san": san, "uci": move.uci(), "fen": board.fen()})
    pgn_path = run_dir / "game.pgn"
    pgn_path.write_text(pgn_text, encoding="utf-8")
    (run_dir / "moves.json").write_text(json.dumps(trace, indent=2), encoding="utf-8")
    warning = None
    classified = []
    if find_stockfish():
        classified = classify_moves(analyze_game(str(pgn_path)))
    else:
        warning = "Stockfish is not installed. The replay is available without engine evaluations."
    payload = {"moves": classified, "keyMoves": find_key_moves(classified),
               "metadata": {"source": "corrections", "engine_warning": warning}}
    analysis_path = run_dir / "analysis.json"
    analysis_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    generate_web_replay(str(pgn_path), str(analysis_path), str(run_dir / "index.html"),
                        confidence=confidence,
                        tag_board_path=str(tag_board_path) if tag_board_path else None)
    return warning
