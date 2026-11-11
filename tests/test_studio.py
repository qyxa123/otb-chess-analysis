"""Regressions for failed-process reporting and Studio correction flows."""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import chess.pgn

from dashboard.correction_utils import replace_move
from dashboard.utils import PROJECT_ROOT, analysis_command, load_board_sequences, stream_process
from dashboard_local.utils import parse_check_status, parse_tag_status


class StudioHelpersTests(unittest.TestCase):
    def test_failed_process_keeps_exit_status_and_stderr(self):
        stream = stream_process([sys.executable, "-c", "import sys; print('failure', file=sys.stderr); sys.exit(7)"])
        self.assertIsNone(stream.returncode)
        self.assertEqual(list(stream), ["failure"])
        self.assertEqual(stream.returncode, 7)

    def test_subprocess_uses_project_root_from_other_cwd(self):
        with tempfile.TemporaryDirectory() as temporary:
            stream = stream_process([sys.executable, "-c", "import os; print(os.getcwd())"])
            self.assertEqual(list(stream), [str(PROJECT_ROOT)])
            self.assertEqual(stream.returncode, 0)

    def test_status_ignores_pass_css_and_pass_rule_on_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "CHECK.html"
            report.write_text('<style>.status-pass {color:green}.status-fail {color:red}</style>'
                              '<div class="status-banner status-warning">Needs attention</div>')
            self.assertEqual(parse_check_status(report), "WARNING")
            report.write_text('<h1>Tag Mode Check: FAIL</h1><p>PASS rule: tags >= 28</p>')
            self.assertEqual(parse_tag_status(report), "FAIL")

    def test_single_board_grid_and_sequence_load_consistently(self):
        grid = [[0] * 8 for _ in range(8)]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "board_ids.json"
            for data in [grid, [grid], {"piece_ids": grid}, [{"piece_ids": grid}]]:
                path.write_text(json.dumps(data))
                self.assertEqual(load_board_sequences(path), [grid])
            path.write_text(json.dumps([[1, 2, 3]]))
            self.assertEqual(load_board_sequences(path), [])

    def test_cli_command_preserves_spaces_and_all_settings(self):
        command = analysis_command(Path("video with spaces.mp4"), Path("run with spaces"),
                                   use_piece_tags=True, fps=4, motion_threshold=0.012,
                                   enable_clahe=False, enable_threshold=False)
        self.assertIn("--use-piece-tags", command)
        self.assertEqual(command[command.index("--fps") + 1], "4")
        self.assertTrue(command[command.index("--input") + 1].endswith("video with spaces.mp4"))
        self.assertIn("--disable-clahe", command)
        self.assertIn("--disable-threshold-path", command)

    def test_correction_preserves_prefix_and_valid_suffix(self):
        corrected, discarded = replace_move("1. e4 e5 2. Nf3 Nc6 *", 2, "c5")
        game = chess.pgn.read_game(io.StringIO(corrected))
        self.assertFalse(game.errors)
        self.assertEqual([move.uci() for move in game.mainline_moves()],
                         ["e2e4", "c7c5", "g1f3", "b8c6"])
        self.assertEqual(discarded, 0)

    def test_correction_truncates_from_first_illegal_followup(self):
        corrected, discarded = replace_move("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *", 1, "d4")
        game = chess.pgn.read_game(io.StringIO(corrected))
        self.assertFalse(game.errors)
        self.assertEqual(len(list(game.mainline_moves())), 4)
        self.assertEqual(discarded, 2)


class StudioPagesTests(unittest.TestCase):
    def test_corrections_page_handles_single_frame_and_pgn(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "sample"
            run.mkdir()
            (run / "board_ids.json").write_text(json.dumps([[[0] * 8 for _ in range(8)]]))
            (run / "game.pgn").write_text("1. e4 e5 *")
            with patch("dashboard.utils.BASE_OUTDIR", Path(temporary)):
                app = AppTest.from_file(str(PROJECT_ROOT / "dashboard/pages/4_Corrections.py")).run(timeout=15)
                self.assertEqual(list(app.exception), [])
                self.assertEqual(len(app.number_input), 65)

    def test_home_uses_tag_mode_and_rejects_missing_upload(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as temporary:
            with patch("dashboard.utils.BASE_OUTDIR", Path(temporary)):
                app = AppTest.from_file(str(PROJECT_ROOT / "dashboard/pages/1_Home_New_Analysis.py")).run(timeout=15)
                self.assertEqual(list(app.exception), [])
                self.assertEqual(app.radio[0].value, "Tag mode")
                app.button[0].click().run()
                self.assertEqual(app.error[0].value, "Please upload a video first.")

    def test_review_understands_main_pipeline_schema_without_accuracy_claims(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "sample"
            run.mkdir()
            (run / "analysis.json").write_text(json.dumps({
                "moves": [{"move_number": 1, "eval_cp": 30, "analysis_source": "material"}],
                "keyMoves": [1], "metadata": {"analysis_source": "material", "warnings": ["Material only"], "partial": True}}))
            with patch("dashboard.utils.BASE_OUTDIR", Path(temporary)):
                app = AppTest.from_file(str(PROJECT_ROOT / "dashboard/pages/2_Review.py")).run(timeout=15)
                self.assertEqual(list(app.exception), [])
                self.assertEqual(app.metric[0].label, "Key moves")
                self.assertEqual(app.metric[0].value, "1")
                self.assertEqual(app.warning[0].value, "Material only")
                self.assertIn("uncertain", app.warning[1].value)
                self.assertTrue(any("Material evaluation" in item.value for item in app.markdown))


if __name__ == "__main__":
    unittest.main()
