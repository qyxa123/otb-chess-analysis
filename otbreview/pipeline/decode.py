#!/usr/bin/env python3
"""
合法性约束解码模块
功能：从观测到的棋盘状态推断走法（核心算法）
"""

import chess
import chess.engine
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import numpy as np


def decode_moves(
    board_states: List[Dict],
    initial_fen: Optional[str] = None,
    output_dir: Optional[str] = None
) -> Tuple[List[str], List[Dict]]:
    """
    从棋盘状态序列解码走法
    
    使用合法性约束：枚举所有合法走法，选择与观测最匹配的
    
    Args:
        board_states: 棋盘状态列表（来自pieces模块）
        initial_fen: 初始FEN（None表示标准初始局面）
        output_dir: 输出目录（保存差分热力图）
    
    Returns:
        (moves_san, confidence_list)
        moves_san: SAN格式走法列表
        confidence_list: 每步的置信度信息
    """
    if initial_fen is None:
        board = chess.Board()
    else:
        board = chess.Board(initial_fen)
    
    moves_san = []
    confidence_list = []
    
    if output_dir:
        output_path = Path(output_dir)
        diff_dir = output_path / "diff_heatmaps"
        diff_dir.mkdir(exist_ok=True)
    else:
        diff_dir = None
    
    prev_occupancy = _board_state_to_occupancy(board_states[0])
    
    for step_idx in range(1, len(board_states)):
        curr_occupancy = _board_state_to_occupancy(board_states[step_idx])
        
        # 找到最佳匹配的走法
        best_move, best_score, candidates = _find_best_move(
            board=board,
            prev_occupancy=prev_occupancy,
            curr_occupancy=curr_occupancy
        )
        
        if best_move is None:
            # 无法找到匹配的走法
            moves_san.append("??")
            confidence_list.append({
                'uncertain': True,
                'reason': 'no_matching_move',
                'candidates': []
            })
            continue
        
        # 执行走法
        board.push(best_move)
        san = board.san(best_move)
        moves_san.append(san)
        
        # 计算置信度
        uncertain = False
        if len(candidates) > 1:
            # 检查top2的差距
            if candidates[1]['score'] - best_score < 0.1:  # 差距很小
                uncertain = True
        
        confidence_list.append({
            'uncertain': uncertain,
            'score': float(best_score),
            'candidates': [
                {
                    'move': board.san(c['move']),
                    'score': float(c['score'])
                }
                for c in candidates[:3]  # top3候选
            ]
        })
        
        prev_occupancy = curr_occupancy
    
    return moves_san, confidence_list


def _board_state_to_occupancy(state: Dict) -> np.ndarray:
    """
    将board_state转换为8x8占用矩阵
    0=空, 1=白, 2=黑
    """
    return np.array(state['occupancy'], dtype=np.int32)


def _find_best_move(
    board: chess.Board,
    prev_occupancy: np.ndarray,
    curr_occupancy: np.ndarray
) -> Tuple[Optional[chess.Move], float, List[Dict]]:
    """
    找到与观测最匹配的合法走法
    
    Returns:
        (best_move, best_score, candidates_list)
    """
    legal_moves = list(board.legal_moves)
    
    if len(legal_moves) == 0:
        return None, float('inf'), []
    
    candidates = []
    
    for move in legal_moves:
        # 创建临时棋盘
        test_board = board.copy()
        test_board.push(move)
        
        # 计算预期占用状态
        expected_occupancy = _fen_to_occupancy(test_board.fen())
        
        # 计算与观测的距离
        score = _compute_occupancy_distance(expected_occupancy, curr_occupancy)
        
        candidates.append({
            'move': move,
            'score': score
        })
    
    # 按分数排序（越小越好）
    candidates.sort(key=lambda x: x['score'])
    
    best = candidates[0]
    return best['move'], best['score'], candidates


def _fen_to_occupancy(fen: str) -> np.ndarray:
    """
    将FEN转换为8x8占用矩阵
    """
    board = chess.Board(fen)
    occupancy = np.zeros((8, 8), dtype=np.int32)
    
    for square in chess.SQUARES:
        piece = board.piece_at(square)
        row = 7 - (square // 8)  # FEN是从上到下，numpy是从下到上
        col = square % 8
        
        if piece is None:
            occupancy[row, col] = 0
        elif piece.color == chess.WHITE:
            occupancy[row, col] = 1
        else:
            occupancy[row, col] = 2
    
    return occupancy


def _compute_occupancy_distance(occ1: np.ndarray, occ2: np.ndarray) -> float:
    """
    计算两个占用矩阵的距离
    """
    # 简单：不匹配的格子数
    diff = (occ1 != occ2).sum()
    
    # 可以加权：颜色错误比空/有错误更严重
    # 这里先用简单版本
    
    return float(diff)

