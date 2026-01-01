#!/usr/bin/env python3
"""
Stockfish分析模块
功能：使用本地Stockfish引擎分析PGN
"""

import chess
import chess.engine
import chess.pgn
import shutil
from pathlib import Path
from typing import List, Dict, Optional


def find_stockfish() -> Optional[str]:
    """
    查找Stockfish可执行文件路径
    """
    # 尝试常见路径
    candidates = [
        "stockfish",  # 在PATH中
        "/usr/local/bin/stockfish",  # macOS brew
        "/opt/homebrew/bin/stockfish",  # macOS Apple Silicon brew
        "./stockfish",  # 当前目录
    ]
    
    for path in candidates:
        if shutil.which(path):
            return path
    
    return None


def analyze_game(
    pgn_path: str,
    depth: int = 14,
    pv_length: int = 6
) -> List[Dict]:
    """
    分析PGN文件，生成每步的评估和PV
    
    Args:
        pgn_path: PGN文件路径
        depth: 分析深度
        pv_length: 主变PV长度
    
    Returns:
        分析结果列表，每项包含：
        {
            'move_number': int,
            'move_san': str,
            'fen': str,
            'eval_cp': float,  # centipawns
            'eval_mate': Optional[int],  # mate步数，None表示非mate
            'pv': List[str],  # 主变走法列表
            'depth': int
        }
    """
    stockfish_path = find_stockfish()
    if stockfish_path is None:
        raise RuntimeError(
            "找不到Stockfish。请安装: brew install stockfish\n"
            "或确保stockfish在PATH中"
        )
    
    with open(pgn_path, 'r', encoding='utf-8') as f:
        game = chess.pgn.read_game(f)
    
    if game is None:
        raise ValueError("无法解析PGN文件")
    
    board = game.board()
    analysis_results = []
    move_number = 0
    
    with chess.engine.SimpleEngine.popen_uci(stockfish_path) as engine:
        # 分析初始局面
        initial_info = engine.analyse(board, chess.engine.Limit(depth=depth))
        initial_eval = _extract_eval(initial_info['score'], board.turn)
        initial_pv = _extract_pv(initial_info.get('pv', []), board, pv_length)
        
        analysis_results.append({
            'move_number': 0,
            'move_san': '初始局面',
            'fen': board.fen(),
            'eval_cp': initial_eval['cp'],
            'eval_mate': initial_eval['mate'],
            'pv': initial_pv,
            'depth': initial_info.get('depth', depth)
        })
        
        # 遍历每一步
        for move in game.mainline_moves():
            move_number += 1
            
            # 分析走棋前的局面（评估玩家走这步后的局面）
            board.push(move)
            
            info = engine.analyse(board, chess.engine.Limit(depth=depth))
            eval_data = _extract_eval(info['score'], board.turn)
            pv = _extract_pv(info.get('pv', []), board, pv_length)
            
            analysis_results.append({
                'move_number': move_number,
                'move_san': board.san(move),
                'fen': board.fen(),
                'eval_cp': eval_data['cp'],
                'eval_mate': eval_data['mate'],
                'pv': pv,
                'depth': info.get('depth', depth)
            })
    
    return analysis_results


def _extract_eval(score, turn: bool) -> Dict:
    """
    提取评估值
    
    Returns:
        {'cp': float, 'mate': Optional[int]}
    """
    if score.is_mate():
        mate_score = score.mate()
        if mate_score is not None:
            # 转换为从当前走棋方视角的mate
            if turn == chess.WHITE:
                return {'cp': None, 'mate': mate_score}
            else:
                return {'cp': None, 'mate': -mate_score}
    
    cp = score.score()
    if cp is None:
        return {'cp': 0.0, 'mate': None}
    
    # 转换为从白方视角的centipawns
    if turn == chess.BLACK:
        cp = -cp
    
    return {'cp': cp / 100.0, 'mate': None}


def _extract_pv(pv_moves: List, board: chess.Board, max_length: int) -> List[str]:
    """
    提取主变走法（SAN格式）
    """
    pv_san = []
    test_board = board.copy()
    
    for move in pv_moves[:max_length]:
        try:
            san = test_board.san(move)
            pv_san.append(san)
            test_board.push(move)
        except (ValueError, AssertionError):
            break
    
    return pv_san

