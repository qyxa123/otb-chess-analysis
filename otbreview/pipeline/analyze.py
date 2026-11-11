"""Evaluate every PGN position with Stockfish, or explicitly marked material scores."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional

import chess
import chess.engine
import chess.pgn

from self_analysis import material_eval, parse_pgn_text

MATE_SCORE = 100000


def find_stockfish() -> Optional[str]:
    """Find an executable in the configured path or common installation locations."""
    candidates = [
        os.environ.get("STOCKFISH_PATH", ""),
        "stockfish",
        "/usr/games/stockfish",
        "/usr/local/bin/stockfish",
        "/opt/homebrew/bin/stockfish",
        str(Path(__file__).resolve().parents[2] / "stockfish"),
    ]
    for candidate in candidates:
        if candidate:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
    return None


def analyze_game(
    pgn_path: str,
    depth: int = 14,
    pv_length: int = 6,
    allow_fallback: bool = True,
) -> List[Dict]:
    """Return the initial position and each played move's resulting position.

    ``eval_cp`` always uses centipawns from White's perspective. Mate scores
    retain ``eval_mate`` and use a finite signed score for downstream arithmetic.
    Without Stockfish the results explicitly identify material-only evaluation;
    these scores are not tactical analysis.
    """
    if depth < 1 or pv_length < 0:
        raise ValueError("分析深度必须大于0，PV长度不能为负数")
    with open(pgn_path, encoding="utf-8") as handle:
        game = parse_pgn_text(handle.read())

    stockfish_path = find_stockfish()
    if stockfish_path is None:
        if not allow_fallback:
            raise RuntimeError("找不到Stockfish。请安装Stockfish或设置 STOCKFISH_PATH。")
        print("警告: 未找到Stockfish，仅生成基础子力评估；不包含战术分析。")
        return _analyze_positions(game, None, depth, pv_length)
    with chess.engine.SimpleEngine.popen_uci(stockfish_path) as engine:
        return _analyze_positions(game, engine, depth, pv_length)


def _position_info(board, engine, depth, pv_length):
    if engine is None:
        mate = 0 if board.is_checkmate() else None
        cp = material_eval(board)
        if mate is not None:
            cp = -MATE_SCORE if board.turn == chess.WHITE else MATE_SCORE
        elif board.is_game_over():
            cp = 0.0
        return {"cp": cp, "mate": mate}, [], 0
    info = engine.analyse(board, chess.engine.Limit(depth=depth))
    return (
        _extract_eval(info["score"], board.turn),
        _extract_pv(info.get("pv", []), board, pv_length),
        info.get("depth", depth),
    )


def _analyze_positions(game, engine, depth, pv_length):
    board = game.board()
    source = "stockfish" if engine is not None else "material"
    evaluation, pv, reached_depth = _position_info(board, engine, depth, pv_length)
    results = [{
        "move_number": 0,
        "move_san": "初始局面",
        "fen": board.fen(),
        "eval_cp": evaluation["cp"],
        "eval_mate": evaluation["mate"],
        "pv": pv,
        "depth": reached_depth,
        "analysis_source": source,
    }]
    if engine is None:
        results[0]["warning"] = "未找到Stockfish，仅显示基础子力评估；不提供战术分析、走法评级或准确率。"
    for ply, move in enumerate(game.mainline_moves(), start=1):
        # SAN and the mover belong to the position *before* push().
        san = board.san(move)
        mover_is_white = board.turn == chess.WHITE
        best_san = pv[0] if pv else None
        board.push(move)
        evaluation, pv, reached_depth = _position_info(board, engine, depth, pv_length)
        results.append({
            "move_number": ply,
            "move_san": san,
            "fen": board.fen(),
            "eval_cp": evaluation["cp"],
            "eval_mate": evaluation["mate"],
            "pv": pv,
            "depth": reached_depth,
            "analysis_source": source,
            "mover_is_white": mover_is_white,
            "best_san": best_san,
        })
    return results


def _extract_eval(score, turn: bool = chess.WHITE) -> Dict:
    """Normalize a python-chess PovScore (or side-relative Score) to White."""
    white_score = score.white() if isinstance(score, chess.engine.PovScore) else (
        score if turn == chess.WHITE else -score
    )
    return {
        "cp": float(white_score.score(mate_score=MATE_SCORE)),
        "mate": white_score.mate() if white_score.is_mate() else None,
    }


def _extract_pv(pv_moves: List, board: chess.Board, max_length: int) -> List[str]:
    """Convert a legal principal variation to SAN without mutating the board."""
    result = []
    position = board.copy()
    for move in pv_moves[:max_length]:
        if move not in position.legal_moves:
            break
        result.append(position.san(move))
        position.push(move)
    return result
