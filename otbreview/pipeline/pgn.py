#!/usr/bin/env python3
"""
PGN生成模块
"""

import chess
import chess.pgn
from datetime import datetime
from typing import List, Dict, Any


def generate_pgn(moves: List[str]) -> str:
    """
    从走法列表生成PGN
    
    Args:
        moves: SAN格式走法列表
    
    Returns:
        PGN字符串
    """
    game = chess.pgn.Game()
    game.headers["Event"] = "OTB Review"
    game.headers["Site"] = "?"
    game.headers["Date"] = datetime.now().strftime("%Y.%m.%d")
    game.headers["Round"] = "?"
    game.headers["White"] = "Player 1"
    game.headers["Black"] = "Player 2"
    game.headers["Result"] = "*"
    
    node = game
    board = game.board()
    
    for move_san in moves:
        if move_san == "??":
            # 无法解析的走法，跳过
            continue
        
        try:
            move = board.parse_san(move_san)
            node = node.add_variation(move)
            board.push(move)
        except ValueError:
            # 无效走法，跳过
            continue
    
    # 确定结果
    if board.is_checkmate():
        if board.turn == chess.WHITE:
            game.headers["Result"] = "0-1"
        else:
            game.headers["Result"] = "1-0"
    elif board.is_stalemate() or board.is_insufficient_material() or board.is_seventy_five_moves():
        game.headers["Result"] = "1/2-1/2"
    
    return str(game)


def generate_moves_json(moves: List[str]) -> List[Dict[str, Any]]:
    """Return a detailed move trace with SAN/UCI/FEN for each ply."""

    board = chess.Board()
    trace: List[Dict[str, Any]] = []
    for move_san in moves:
        if move_san == "??":
            continue
        parsed_move = None
        try:
            parsed_move = board.parse_san(move_san)
        except ValueError:
            try:
                parsed_move = chess.Move.from_uci(move_san)
                if parsed_move not in board.legal_moves:
                    parsed_move = None
            except ValueError:
                parsed_move = None

        if parsed_move is None:
            continue

        san = board.san(parsed_move)
        uci = parsed_move.uci()
        board.push(parsed_move)
        trace.append({"san": san, "uci": uci, "fen": board.fen()})

    return trace

