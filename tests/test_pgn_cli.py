import io
import subprocess
import sys
import unittest
from pathlib import Path

import chess
import chess.pgn

from otbreview.pipeline.pgn import generate_moves_json, generate_pgn


class PgnExportTests(unittest.TestCase):
    def test_unknown_observation_stops_legal_prefix(self):
        moves = ["e4", "??", "e5", "Nf3"]
        game = chess.pgn.read_game(io.StringIO(generate_pgn(moves)))
        self.assertFalse(game.errors)
        self.assertEqual([move.uci() for move in game.mainline_moves()], ["e2e4"])
        self.assertIn("不确定", game.end().comment)
        self.assertEqual(len(generate_moves_json(moves)), 1)

    def test_illegal_move_is_not_silently_dropped(self):
        for exporter in (generate_pgn, generate_moves_json):
            with self.subTest(exporter=exporter.__name__), self.assertRaises(ValueError):
                exporter(["e4", "Nf3", "e5"])

    def test_null_moves_are_rejected(self):
        for exporter in (generate_pgn, generate_moves_json):
            with self.subTest(exporter=exporter.__name__), self.assertRaises(ValueError):
                exporter(["--"])

    def test_custom_start_position_is_preserved(self):
        board = chess.Board()
        board.push_san("e4")
        pgn = generate_pgn(["e5", "Nf3"], initial_fen=board.fen())
        game = chess.pgn.read_game(io.StringIO(pgn))
        self.assertEqual(game.board().fen(), board.fen())
        self.assertEqual(len(list(game.mainline_moves())), 2)


class CliTests(unittest.TestCase):
    def test_documented_module_entry_point(self):
        result = subprocess.run(
            [sys.executable, "-m", "otbreview", "analyze", "--help"],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--use-piece-tags", result.stdout)
        self.assertIn("--stable-duration", result.stdout)


if __name__ == "__main__":
    unittest.main()
