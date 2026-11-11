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
    # Board.empty() has no castling rights. The configured initial arrangement
    # must retain the rights of unmoved home kings and rooks.
    board.castling_rights = chess.BB_CORNERS
    board.castling_rights = board.clean_castling_rights()
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
    """Decode configured piece IDs using the same legal matcher as video mode.

    Captures change two IDs and castling changes four squares. Matching the
    complete legal move avoids treating these normal moves as detection errors.
    """
    from .decode import decode_moves_from_tags

    if not board_grids:
        return [], []
    board, _, _ = _init_board_from_map(piece_map)
    states = [{"piece_ids": frame["board_ids"]} for frame in board_grids]
    moves, confidence = decode_moves_from_tags(
        states, initial_fen=board.fen(),
        output_dir=str(output_dir) if output_dir else None,
    )
    debug = []
    for move, item in zip(moves, confidence):
        record = dict(item, step=item.get("frame"))
        if move != "??":
            record["san"] = move
        debug.append(record)
    uncertain = [item for item in debug if item["uncertain"]]
    if output_dir and uncertain:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "uncertain_moves.json").write_text(
            json.dumps(uncertain, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    return moves, debug
