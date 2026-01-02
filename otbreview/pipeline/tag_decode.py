"""基于棋子标签的走法推断模块"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import chess
import json


class PieceIdMapError(Exception):
    """配置文件错误"""


def load_piece_id_map(map_path: Path) -> Dict[int, Dict[str, str]]:
    """读取并校验piece_id_map.json"""
    data = json.loads(map_path.read_text(encoding="utf-8"))
    parsed: Dict[int, Dict[str, str]] = {}
    for key, value in data.items():
        pid = int(key)
        if "symbol" not in value or "square" not in value:
            raise PieceIdMapError(f"缺少symbol/square: {key}")
        parsed[pid] = {
            "symbol": value["symbol"],
            "square": value["square"],
            "name": value.get("name", str(pid)),
        }
    return parsed


def _init_board_from_map(piece_map: Dict[int, Dict[str, str]]) -> Tuple[chess.Board, Dict[int, chess.Piece], Dict[int, int]]:
    board = chess.Board.empty()
    id_to_piece: Dict[int, chess.Piece] = {}
    id_to_square: Dict[int, int] = {}

    for pid, info in piece_map.items():
        piece = chess.Piece.from_symbol(info["symbol"])
        square = chess.parse_square(info["square"])
        board.set_piece_at(square, piece)
        id_to_piece[pid] = piece
        id_to_square[pid] = square

    board.turn = chess.WHITE
    return board, id_to_piece, id_to_square


def _grid_to_positions(board_ids: List[List[int]]) -> Dict[int, int]:
    positions: Dict[int, int] = {}
    for row in range(8):
        for col in range(8):
            pid = board_ids[row][col]
            if pid <= 0:
                continue
            square = chess.square(col, 7 - row)
            positions[pid] = square
    return positions


def _match_legal_move(board: chess.Board, from_sq: int, to_sq: int, promotion: Optional[int]) -> Optional[chess.Move]:
    for move in board.legal_moves:
        if move.from_square == from_sq and move.to_square == to_sq:
            if promotion is None or move.promotion == promotion:
                return move
    return None


def _detect_castling(moved_ids: List[int], prev_positions: Dict[int, int], curr_positions: Dict[int, int], id_to_piece: Dict[int, chess.Piece]) -> Optional[chess.Move]:
    if len(moved_ids) != 2:
        return None

    king_id = None
    rook_id = None
    for pid in moved_ids:
        piece = id_to_piece.get(pid)
        if piece is None:
            continue
        if piece.piece_type == chess.KING:
            king_id = pid
        elif piece.piece_type == chess.ROOK:
            rook_id = pid

    if king_id is None or rook_id is None:
        return None

    king_from = prev_positions.get(king_id)
    king_to = curr_positions.get(king_id)
    rook_from = prev_positions.get(rook_id)
    rook_to = curr_positions.get(rook_id)

    if None in [king_from, king_to, rook_from, rook_to]:
        return None

    if king_from == chess.E1 and king_to == chess.G1 and rook_from == chess.H1 and rook_to == chess.F1:
        return chess.Move.from_uci("e1g1")
    if king_from == chess.E1 and king_to == chess.C1 and rook_from == chess.A1 and rook_to == chess.D1:
        return chess.Move.from_uci("e1c1")
    if king_from == chess.E8 and king_to == chess.G8 and rook_from == chess.H8 and rook_to == chess.F8:
        return chess.Move.from_uci("e8g8")
    if king_from == chess.E8 and king_to == chess.C8 and rook_from == chess.A8 and rook_to == chess.D8:
        return chess.Move.from_uci("e8c8")

    return None


def infer_moves_from_id_grids(
    board_grids: List[Dict],
    piece_map: Dict[int, Dict[str, str]],
    output_dir: Optional[Path] = None,
) -> Tuple[List[str], List[Dict]]:
    """根据相邻棋子ID矩阵推断走法"""
    if not board_grids:
        return [], []

    board, id_to_piece, id_to_square = _init_board_from_map(piece_map)
    prev_positions = _grid_to_positions(board_grids[0]["board_ids"])
    id_to_square.update(prev_positions)

    moves_san: List[str] = []
    move_debug: List[Dict] = []
    uncertain: List[Dict] = []

    for idx in range(1, len(board_grids)):
        curr_positions = _grid_to_positions(board_grids[idx]["board_ids"])
        moved_ids = [pid for pid in set(prev_positions.keys()) | set(curr_positions.keys()) if prev_positions.get(pid) != curr_positions.get(pid)]

        record: Dict = {
            "step": idx,
            "moved_ids": moved_ids,
            "from_to": {},
            "uncertain": False,
        }

        chosen_move: Optional[chess.Move] = None

        castle = _detect_castling(moved_ids, prev_positions, curr_positions, id_to_piece)
        if castle and castle in board.legal_moves:
            chosen_move = castle

        if chosen_move is None and len(moved_ids) == 1:
            pid = moved_ids[0]
            from_sq = prev_positions.get(pid)
            to_sq = curr_positions.get(pid)
            piece = id_to_piece.get(pid)
            record["from_to"] = {"id": pid, "from": from_sq, "to": to_sq}

            if from_sq is not None and to_sq is not None and piece is not None:
                promotion = None
                rank = chess.square_rank(to_sq)
                if piece.piece_type == chess.PAWN and rank in (0, 7):
                    promotion = chess.QUEEN
                move = chess.Move(from_sq, to_sq, promotion=promotion)
                if move in board.legal_moves:
                    chosen_move = move
                else:
                    chosen_move = _match_legal_move(board, from_sq, to_sq, promotion)

        if chosen_move is None:
            record["uncertain"] = True
            record["reason"] = "无法唯一确定走法"
            moves_san.append("??")
            uncertain.append(record)
            prev_positions = curr_positions
            continue

        san = board.san(chosen_move)
        board.push(chosen_move)
        moves_san.append(san)
        prev_positions = curr_positions
        record["san"] = san
        move_debug.append(record)

    if output_dir and uncertain:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "uncertain_moves.json").write_text(
            json.dumps(uncertain, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return moves_san, move_debug
