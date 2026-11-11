"""Offline replay should contain exactly the PGN's legal positions."""
import io
import json
from pathlib import Path
import re
import tempfile
import unittest

import chess
import chess.pgn

from otbreview.web.generate import _generate_html, generate_web_replay


def payload(html):
    return json.loads(re.search(r'<script id="replay-data" type="application/json">(.*?)</script>', html, re.S).group(1))


class WebReplayTests(unittest.TestCase):
    def test_every_move_has_correct_board_and_analysis(self):
        game = chess.pgn.read_game(io.StringIO('1. e4 e5 2. Nf3 Nc6 *'))
        analysis = [{"move_number": i, "eval_cp": i * 100, "analysis_source": "stockfish"} for i in range(5)]
        html = _generate_html(game, analysis, [2, 4], [], None)
        data = payload(html)
        self.assertEqual(len(data['positions']), 5)
        board = game.board()
        self.assertEqual(data['positions'][0]['fen'], board.fen())
        for ply, move in enumerate(game.mainline_moves(), 1):
            board.push(move)
            self.assertEqual(data['positions'][ply]['fen'], board.fen())
            self.assertEqual(data['positions'][ply]['eval_cp'], ply * 100)
            self.assertIn('<svg', data['positions'][ply]['svg'])
        self.assertNotIn('src="http', html)
        self.assertEqual(data['key_moves'], [2, 4])

    def test_custom_black_to_move_and_script_safe_pgn(self):
        game = chess.pgn.read_game(io.StringIO('[White "</script><script>alert(1)</script>"]\n[SetUp "1"]\n[FEN "8/8/8/8/8/4k3/8/K7 b - - 0 12"]\n\n12... Kd3 *'))
        html = _generate_html(game, [], [], [], None)
        self.assertEqual(payload(html)['positions'][1]['label'], '12... Kd3')
        self.assertNotIn('</script><script>alert', html)
        self.assertEqual(payload(html)['positions'][0]['fen'], game.board().fen())

    def test_raw_tag_grids_are_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'game.pgn').write_text('1. e4 *', encoding='utf-8')
            (root / 'analysis.json').write_text('{"moves": []}', encoding='utf-8')
            grid = [[0] * 8 for _ in range(8)]
            grid[6][4] = 5
            (root / 'board_ids.json').write_text(json.dumps([grid]), encoding='utf-8')
            result = generate_web_replay(str(root / 'game.pgn'), str(root / 'analysis.json'), str(root / 'index.html'), tag_board_path=str(root / 'board_ids.json'))
            self.assertEqual(payload(Path(result).read_text())['tags']['frames'][0]['board_ids'][6][4], 5)

    def test_truncated_recognition_is_marked_in_offline_replay(self):
        game = chess.pgn.read_game(io.StringIO('1. e4 *'))
        html = _generate_html(game, [], [], [{"uncertain": False}, {"uncertain": True}], None)
        self.assertTrue(payload(html)['partial'])
        self.assertEqual(len(payload(html)['positions']), 2)


if __name__ == '__main__':
    unittest.main()
