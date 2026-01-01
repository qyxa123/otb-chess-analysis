#!/usr/bin/env python3
"""
关键走法识别模块
功能：识别对局中的关键走法（用于Next按钮跳转）
"""

from typing import List, Dict


def find_key_moves(analysis: List[Dict]) -> List[int]:
    """
    找到关键走法索引
    
    关键走法包括：
    - 最后一步开局库走法
    - 最大eval swing
    - blunder/mistake
    - miss（错过明显机会）
    
    Args:
        analysis: 分类后的分析结果
    
    Returns:
        关键走法的move_number列表
    """
    key_moves = []
    
    if len(analysis) < 2:
        return key_moves
    
    # 1. 最后一步开局库走法
    last_book = None
    for i, move_data in enumerate(analysis):
        if move_data.get('is_book', False):
            last_book = move_data.get('move_number', i)
    if last_book is not None:
        key_moves.append(last_book)
    
    # 2. 最大eval swing
    max_swing = 0
    max_swing_move = None
    for i in range(1, len(analysis)):
        prev_eval = analysis[i-1].get('eval_cp', 0)
        curr_eval = analysis[i].get('eval_cp', 0)
        swing = abs(curr_eval - prev_eval)
        if swing > max_swing:
            max_swing = swing
            max_swing_move = analysis[i].get('move_number', i)
    if max_swing_move is not None and max_swing > 100:
        key_moves.append(max_swing_move)
    
    # 3. Blunder和Mistake
    for move_data in analysis:
        classification = move_data.get('classification', '')
        move_num = move_data.get('move_number', 0)
        if classification in ['blunder', 'mistake'] and move_num > 0:
            key_moves.append(move_num)
    
    # 去重并排序
    key_moves = sorted(list(set(key_moves)))
    
    return key_moves

