#!/usr/bin/env python3
"""
走法分类模块
功能：对每步走法进行分类（Best/Good/Inaccuracy/Mistake/Blunder/Book/Miss）
"""

import chess
import chess.pgn
from typing import List, Dict


# 分类阈值（centipawn loss）
THRESHOLDS = {
    'best': 0,      # 0 cp loss
    'good': 50,     # < 50 cp loss
    'inaccuracy': 100,  # 50-100 cp loss
    'mistake': 200,     # 100-200 cp loss
    'blunder': float('inf')  # > 200 cp loss
}


def classify_moves(analysis: List[Dict]) -> List[Dict]:
    """
    对每步走法进行分类
    
    Args:
        analysis: 来自analyze模块的分析结果
    
    Returns:
        增强的分析结果，每项添加：
        - 'classification': str (best/good/inaccuracy/mistake/blunder/book/miss)
        - 'cp_loss': float (相对于最佳走法的损失)
        - 'is_book': bool
    """
    if len(analysis) < 2:
        return analysis
    
    classified = []
    
    for i in range(len(analysis)):
        move_data = analysis[i].copy()
        
        if i == 0:
            # 初始局面
            move_data['classification'] = 'initial'
            move_data['cp_loss'] = 0.0
            move_data['is_book'] = False
            classified.append(move_data)
            continue
        
        # 计算cp loss
        prev_eval = analysis[i-1]['eval_cp']
        curr_eval = move_data['eval_cp']
        
        # 考虑走棋方
        if i % 2 == 1:  # 白方走棋
            cp_loss = prev_eval - curr_eval  # 白方希望eval增加
        else:  # 黑方走棋
            cp_loss = curr_eval - prev_eval  # 黑方希望eval减少
        
        move_data['cp_loss'] = cp_loss
        
        # 检查是否是开局库走法
        is_book = _is_book_move(move_data.get('fen', ''), move_data.get('move_san', ''))
        move_data['is_book'] = is_book
        
        # 分类
        if is_book:
            classification = 'book'
        elif cp_loss <= THRESHOLDS['best']:
            classification = 'best'
        elif cp_loss <= THRESHOLDS['good']:
            classification = 'good'
        elif cp_loss <= THRESHOLDS['inaccuracy']:
            classification = 'inaccuracy'
        elif cp_loss <= THRESHOLDS['mistake']:
            classification = 'mistake'
        else:
            classification = 'blunder'
        
        move_data['classification'] = classification
        
        # 检查是否错过明显机会（Miss）
        # 如果存在明显更好的走法（eval swing > 200），但玩家没走
        if i > 0:
            # 这里简化处理，实际应该分析最佳走法
            # TODO: 改进为实际分析最佳走法
            pass
        
        classified.append(move_data)
    
    return classified


def _is_book_move(fen: str, move_san: str) -> bool:
    """
    检查是否是开局库走法
    
    TODO: 实现真正的开局库检查
    可以使用python-chess的ECO数据库或外部开局库
    """
    # 简化实现：前10步都认为是开局
    # 实际应该使用开局库
    return False  # 暂时返回False

