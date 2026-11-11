import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import chess
import chess.engine
import chess.pgn

from game_review import GameReviewFormatter
from self_analysis import analyze_pgn, candidate_variations
from stockfish_analyzer import StockfishAnalyzer
from otbreview.pipeline.analyze import _extract_eval, analyze_game
from otbreview.pipeline.classify import classify_moves
from otbreview.pipeline.keymoves import find_key_moves


class FakeEngine:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def analyse(self, board, limit):
        return {
            'score': chess.engine.PovScore(chess.engine.Cp(125 if board.turn else -125), board.turn),
            'pv': list(board.legal_moves)[:1],
            'depth': 4,
        }


class AnalysisTests(unittest.TestCase):
    def pgn_file(self, text):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'game.pgn'
        path.write_text(text, encoding='utf-8')
        return str(path)

    def test_engine_analysis_keeps_san_and_white_centipawn_perspective(self):
        path = self.pgn_file('1. e4 e5 2. Nf3 Nc6 *')
        with patch('otbreview.pipeline.analyze.find_stockfish', return_value='fake-stockfish'), patch(
            'chess.engine.SimpleEngine.popen_uci', return_value=FakeEngine()
        ):
            result = analyze_game(path)
        self.assertEqual([r['move_san'] for r in result], ['初始局面', 'e4', 'e5', 'Nf3', 'Nc6'])
        self.assertEqual([r['eval_cp'] for r in result], [125] * 5)
        self.assertEqual([r['mover_is_white'] for r in result[1:]], [True, False, True, False])
        board = chess.Board()
        for row, move in zip(result[1:], ['e4', 'e5', 'Nf3', 'Nc6']):
            board.push_san(move)
            self.assertEqual(row['fen'], board.fen())

    def test_missing_engine_is_marked_and_not_rated(self):
        path = self.pgn_file('1. e4 d5 2. exd5 *')
        with patch('otbreview.pipeline.analyze.find_stockfish', return_value=None):
            result = analyze_game(path)
            with self.assertRaisesRegex(RuntimeError, 'Stockfish'):
                analyze_game(path, allow_fallback=False)
        self.assertTrue(result[0]['warning'])
        self.assertTrue(all(r['analysis_source'] == 'material' for r in result))
        classified = classify_moves(result)
        self.assertEqual(classified[-1]['eval_cp'], 100)
        self.assertEqual(classified[-1]['classification'], 'material')
        self.assertIsNone(classified[-1]['cp_loss'])

    def test_mate_scores_and_older_none_evaluations_do_not_crash(self):
        score = _extract_eval(chess.engine.PovScore(chess.engine.Mate(2), chess.BLACK))
        self.assertLess(score['cp'], 0)
        self.assertEqual(score['mate'], -2)
        analysis = [
            {'move_number': 0, 'eval_cp': 0, 'eval_mate': None},
            {'move_number': 1, 'eval_cp': None, 'eval_mate': -1},
        ]
        classified = classify_moves(analysis)
        self.assertEqual(classified[1]['classification'], 'blunder')
        self.assertEqual(find_key_moves(classified), [1])

    def test_custom_fen_black_move_uses_mover_perspective(self):
        fen = chess.STARTING_FEN.replace(' w ', ' b ')
        result = classify_moves([
            {'move_number': 0, 'eval_cp': 100, 'fen': fen},
            {'move_number': 1, 'eval_cp': 300},
        ])
        self.assertEqual(result[1]['cp_loss'], 200)
        self.assertEqual(result[1]['classification'], 'mistake')

    def test_illegal_pgn_is_rejected_instead_of_analyzing_truncated_game(self):
        path = self.pgn_file('1. e4 e5 2. e5 *')
        with self.assertRaises(ValueError):
            analyze_game(path)
        with self.assertRaises(ValueError):
            analyze_pgn('1. e4 e5 2. e5 *')
        with self.assertRaises(ValueError):
            analyze_game(self.pgn_file('this is not a PGN'))

    def test_candidates_consider_all_legal_moves_and_both_colors(self):
        board = chess.Board()
        for san in ['e4', 'd5']:
            board.push_san(san)
        before = board.fen()
        white = candidate_variations(board)[0]
        self.assertEqual(white.san, 'exd5')  # beyond the original first 10 moves
        self.assertEqual(board.fen(), before)
        preview = board.copy()
        preview.push_san(white.san)
        for san in white.continuation.split():
            preview.push_san(san)  # a continuation must be sequential legal SAN
        board.push_san('Nc3')
        black = candidate_variations(board)[0]
        self.assertEqual(black.san, 'dxe4')

    def test_annotated_pgn_keeps_the_entire_mainline(self):
        text = '1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *'
        analysis = analyze_pgn(text)
        review = GameReviewFormatter().build_review(text, analysis)
        original = chess.pgn.read_game(io.StringIO(text))
        annotated = chess.pgn.read_game(io.StringIO(review.annotated_pgn))
        self.assertEqual(annotated.errors, [])
        self.assertEqual(list(original.mainline_moves()), list(annotated.mainline_moves()))
        self.assertEqual({r.label for r in review.reviews}, {'Material'})
        self.assertTrue(all(node.comment for node in annotated.mainline()))
        with self.assertRaisesRegex(ValueError, 'length'):
            GameReviewFormatter().build_review(text, [])

    def test_legacy_stockfish_analyzer_reads_text_and_formats_scores(self):
        with patch('chess.engine.SimpleEngine.popen_uci', return_value=FakeEngine()):
            result = StockfishAnalyzer('fake-stockfish').analyze_pgn('1. e4 e5 *')
        self.assertEqual([r['move'] for r in result], ['e4', 'e5', '终局'])
        self.assertTrue(all(r['evaluation'] == '1.25' for r in result))


if __name__ == '__main__':
    unittest.main()
