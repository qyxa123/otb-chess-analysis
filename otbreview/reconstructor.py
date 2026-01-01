from typing import Dict, List, Tuple

import chess

from .utils import MoveCandidate


class MoveReconstructor:
    def __init__(self, ambiguity_limit: int = 3):
        self.ambiguity_limit = ambiguity_limit

    def reconstruct(self, occupancies: List[Dict[str, str]]) -> Tuple[chess.Board, List[Dict]]:
        board = chess.Board()
        moves_data: List[Dict] = []
        for idx in range(1, len(occupancies)):
            prev = occupancies[idx - 1]
            curr = occupancies[idx]
            best_moves = self._select_moves(board, curr)
            chosen = best_moves[0][0] if best_moves else None
            confidence = best_moves[0][1] if best_moves else 0.0
            candidates = [MoveCandidate(board.san(m), score, "occupancy diff").to_dict() for m, score in best_moves]
            if chosen is None:
                break
            san = board.san(chosen)
            board.push(chosen)
            moves_data.append(
                {
                    "index": idx,
                    "san": san,
                    "uci": chosen.uci(),
                    "fen": board.fen(),
                    "confidence": confidence,
                    "candidates": candidates,
                    "observed": curr,
                }
            )
        return board, moves_data

    def _select_moves(self, board: chess.Board, observation: Dict[str, str]) -> List[Tuple[chess.Move, float]]:
        scored: List[Tuple[chess.Move, float]] = []
        for move in board.legal_moves:
            temp = board.copy()
            temp.push(move)
            cost = self._compare(temp, observation)
            score = max(0.0, 1.0 - cost / 32.0)
            scored.append((move, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[: self.ambiguity_limit]

    def _compare(self, board: chess.Board, observation: Dict[str, str]) -> int:
        cost = 0
        for square in chess.SQUARES:
            square_name = chess.square_name(square)
            obs_state = observation.get(square_name, "empty")
            piece = board.piece_at(square)
            if obs_state == "empty" and piece is None:
                continue
            if obs_state == "empty" and piece is not None:
                cost += 1
                continue
            if obs_state != "empty" and piece is None:
                cost += 1
                continue
            if obs_state == "white" and piece.color != chess.WHITE:
                cost += 1
            if obs_state == "black" and piece.color != chess.BLACK:
                cost += 1
        return cost
