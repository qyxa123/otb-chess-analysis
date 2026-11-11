"""Regression tests for legal decoding and the real OpenCV recognition paths."""
import tempfile
import unittest
from pathlib import Path

import chess
import cv2
import numpy as np

from otbreview.pipeline.board_detect import detect_and_warp_board
from otbreview.pipeline.decode import decode_moves_from_states, decode_moves_from_tags, _fen_to_occupancy
from otbreview.pipeline.pieces import detect_pieces_tags, detect_pieces_two_stage
from otbreview.pipeline.tag_decode import infer_moves_from_id_grids, load_piece_id_map


ROOT = Path(__file__).resolve().parents[1]


def id_states(moves, initial_fen=None):
    """Track physical IDs through moves, independently of the decoder."""
    board = chess.Board(initial_fen) if initial_fen else chess.Board()
    ids = {square: index + 1 for index, square in enumerate(sorted(board.piece_map()))}
    states = []

    def append_state():
        grid = np.zeros((8, 8), dtype=int)
        for square, pid in ids.items():
            grid[7 - chess.square_rank(square), chess.square_file(square)] = pid
        states.append({'piece_ids': grid.tolist()})

    append_state()
    for san in moves:
        move = board.parse_san(san)
        pid = ids.pop(move.from_square)
        if board.is_en_passant(move):
            ids.pop(move.to_square - 8 if board.turn else move.to_square + 8)
        if board.is_castling(move):
            rank = chess.square_rank(move.from_square)
            kingside = chess.square_file(move.to_square) > chess.square_file(move.from_square)
            rook_from = chess.square(7 if kingside else 0, rank)
            rook_to = chess.square(5 if kingside else 3, rank)
            ids[rook_to] = ids.pop(rook_from)
        ids[move.to_square] = pid
        board.push(move)
        append_state()
    return states


class DecodeTests(unittest.TestCase):
    def test_tag_sequence_with_capture_and_castling(self):
        moves = ['e4', 'e5', 'Nf3', 'Nc6', 'Bb5', 'a6', 'Bxc6', 'dxc6', 'O-O']
        decoded, confidence = decode_moves_from_tags(id_states(moves))
        self.assertEqual(decoded, moves)
        self.assertTrue(all(not c['uncertain'] for c in confidence))
        self.assertEqual(confidence[0]['candidates'][0]['move'], 'e4')

    def test_en_passant(self):
        moves = ['e4', 'a6', 'e5', 'd5', 'exd6']
        self.assertEqual(decode_moves_from_tags(id_states(moves))[0], moves)

    def test_promotion_type_requires_correction(self):
        fen = '7k/P7/8/8/8/8/8/7K w - - 0 1'
        for move in ['a8=Q+', 'a8=N']:
            decoded, confidence = decode_moves_from_tags(id_states([move], fen), fen)
            self.assertEqual(decoded, ['??'])
            self.assertTrue(confidence[0]['uncertain'])

    def test_unchanged_frames_do_not_invent_moves(self):
        states = id_states(['e4', 'e5'])
        repeated = [states[0], states[0], states[1], states[1], states[2]]
        self.assertEqual(decode_moves_from_tags(repeated)[0], ['e4', 'e5'])

    def test_missing_frame_stops_before_invented_continuation(self):
        states = id_states(['e4', 'e5'])
        empty = {'piece_ids': np.zeros((8, 8), dtype=int).tolist()}
        decoded, confidence = decode_moves_from_tags([states[0], states[1], empty, states[2]])
        self.assertEqual(decoded, ['e4', '??'])
        self.assertTrue(confidence[-1]['uncertain'])

    def test_skipped_opponent_move_is_uncertain(self):
        states = id_states(['e4', 'e5'])
        self.assertEqual(decode_moves_from_tags([states[0], states[2]])[0], ['??'])

    def test_occupancy_legal_san_and_duplicate_frames(self):
        board = chess.Board()
        states = [{'occupancy': _fen_to_occupancy(board.fen()).tolist()}]
        for san in ['e4', 'd5', 'exd5']:
            board.push_san(san)
            states.append({'occupancy': _fen_to_occupancy(board.fen()).tolist()})
        states.insert(1, states[0])
        self.assertEqual(decode_moves_from_states(states)[0], ['e4', 'd5', 'exd5'])

    def test_configured_id_decoder_handles_capture_and_castling(self):
        piece_map = load_piece_id_map(ROOT / 'config/piece_id_map.json')
        # IDs are arbitrary physical identities; their locations identify pieces.
        moves = ['e4', 'e5', 'Nf3', 'Nc6', 'Bb5', 'a6', 'Bxc6', 'dxc6', 'O-O']
        grids = [{'board_ids': s['piece_ids']} for s in id_states(moves)]
        self.assertEqual(infer_moves_from_id_grids(grids, piece_map)[0], moves)

    def test_empty_inputs(self):
        self.assertEqual(decode_moves_from_tags([]), ([], []))
        self.assertEqual(decode_moves_from_states([]), ([], []))


class RecognitionTests(unittest.TestCase):
    def test_missing_image_returns_consistent_tuple(self):
        self.assertEqual(detect_and_warp_board('/does/not/exist.png'), (None, None, 0))

    def test_blank_image_does_not_become_a_board(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'blank.png')
            cv2.imwrite(path, np.full((800, 800, 3), 255, dtype=np.uint8))
            self.assertEqual(detect_and_warp_board(path, use_markers=True), (None, None, 0))
            self.assertEqual(detect_and_warp_board(path, use_markers=False), (None, None, 0))

    def test_marker_mode_does_not_fall_back_to_unrelated_rectangle(self):
        frame = np.full((800, 800, 3), 255, dtype=np.uint8)
        cv2.rectangle(frame, (100, 100), (700, 700), (0, 0, 0), 10)
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'rectangle.png')
            cv2.imwrite(path, frame)
            self.assertEqual(detect_and_warp_board(path, use_markers=True), (None, None, 0))

    def test_two_stage_recognition_uses_input_image(self):
        board = np.zeros((800, 800, 3), dtype=np.uint8)
        for row in range(8):
            for col in range(8):
                color = 150 if (row + col) % 2 == 0 else 90
                board[row * 100:(row + 1) * 100, col * 100:(col + 1) * 100] = color
                if row in (0, 1, 6, 7):
                    value = 20 if row < 2 else 230
                    cv2.circle(board, (col * 100 + 50, row * 100 + 50), 30, (value,) * 3, -1)
        with tempfile.TemporaryDirectory() as directory:
            state = detect_pieces_two_stage(board, 0, directory, debug=True)
            self.assertEqual(state['occupancy'][0], [2] * 8)
            self.assertEqual(state['occupancy'][3], [0] * 8)
            self.assertEqual(state['occupancy'][7], [1] * 8)

    def test_small_tags_are_not_rejected_by_default_area(self):
        board = np.full((800, 800, 3), 255, dtype=np.uint8)
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100)
        marker = cv2.aruco.generateImageMarker(dictionary, 5, 14)
        board[443:457, 443:457] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
        with tempfile.TemporaryDirectory() as directory:
            state = detect_pieces_tags(board, 0, directory)
            self.assertEqual(state['piece_ids'][4][4], 5)

    def test_explicit_apriltag_family_is_honored(self):
        board = np.full((800, 800, 3), 255, dtype=np.uint8)
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
        marker = cv2.aruco.generateImageMarker(dictionary, 9, 40)
        board[430:470, 430:470] = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
        with tempfile.TemporaryDirectory() as directory:
            state = detect_pieces_tags(board, 0, directory, tag_family='apriltag36h11')
            self.assertEqual(state['piece_ids'][4][4], 9)


if __name__ == '__main__':
    unittest.main()
