"""Regression coverage for video sampling and stable-section extraction."""

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from otbreview.pipeline.extract import extract_stable_frames, extract_stable_frames_debug


class FakeCapture:
    def __init__(self, frames, fps):
        self.frames = frames
        self.fps = fps
        self.index = 0
        self.released = False

    def isOpened(self):
        return True

    def get(self, prop):
        if prop == cv2.CAP_PROP_FPS:
            return self.fps
        if prop == cv2.CAP_PROP_FRAME_COUNT:
            return len(self.frames)
        return self.index

    def read(self):
        if self.index == len(self.frames):
            return False, None
        frame = self.frames[self.index].copy()
        self.index += 1
        return True, frame

    def set(self, *args):
        raise AssertionError("Extraction must not seek the active capture")

    def release(self):
        self.released = True


def frames_with_motion(count, transition=None):
    frames = []
    for idx in range(count):
        image = np.full((16, 16, 3), 200 if transition is not None and idx >= transition else 0, dtype=np.uint8)
        # One pixel records the raw frame number without changing the motion class.
        image[0, 0] = idx
        frames.append(image)
    return frames


class StableFrameTests(unittest.TestCase):
    def run_extractor(self, frames, fps, debug=False, **kwargs):
        capture = FakeCapture(frames, fps)
        written = []
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "nested" / "motion.csv"
            with patch("otbreview.pipeline.extract.cv2.VideoCapture", return_value=capture) as factory, patch(
                "otbreview.pipeline.extract.cv2.imwrite",
                side_effect=lambda path, frame: written.append((path, frame.copy())) or True,
            ):
                if debug:
                    result = extract_stable_frames_debug("input.mp4", temp_dir, str(csv_path), **kwargs)
                else:
                    result = extract_stable_frames("input.mp4", temp_dir, **kwargs)
            self.assertEqual(factory.call_count, 1)
            self.assertEqual(capture.index, len(frames))
            self.assertTrue(capture.released)
            rows = []
            if csv_path.exists():
                with csv_path.open() as stream:
                    rows = list(csv.DictReader(stream))
        return result, written, rows

    def test_static_board_emitted_once_by_both_extractors(self):
        for debug in (False, True):
            with self.subTest(debug=debug):
                result, written, _ = self.run_extractor(frames_with_motion(90), 30, debug, stable_duration=0.5)
                self.assertEqual(len(result), 1)
                self.assertEqual(len(written), 1)

    def test_motion_rearms_capture_for_next_board(self):
        for debug in (False, True):
            with self.subTest(debug=debug):
                result, written, _ = self.run_extractor(
                    frames_with_motion(90, transition=45), 30, debug,
                    stable_duration=0.3,
                )
                self.assertEqual(len(result), 2)
                self.assertLess(int(written[0][1][0, 0, 0]), 45)
                self.assertGreaterEqual(int(written[1][1][0, 0, 0]), 45)

    def test_debug_reads_in_order_and_uses_actual_sample_timestamps(self):
        result, _, rows = self.run_extractor(
            frames_with_motion(30), 10, True, target_fps=3,
            stable_duration=0.7, min_interval=0,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual([round(float(row["time"]), 1) for row in rows], [round(i * 0.3, 1) for i in range(10)])

    def test_target_fps_above_video_rate_does_not_extend_stability_duration(self):
        result, written, _ = self.run_extractor(
            frames_with_motion(4), 5, True, target_fps=10,
            stable_duration=0.6,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(int(written[0][1][0, 0, 0]), 2)

    def test_min_interval_measured_between_saved_frame_timestamps(self):
        _, written, _ = self.run_extractor(
            frames_with_motion(30, transition=10), 10, True, target_fps=10,
            stable_duration=0.2, min_interval=1.5,
        )
        self.assertEqual(len(written), 2)
        first_idx, second_idx = [int(frame[0, 0, 0]) for _, frame in written]
        self.assertGreaterEqual((second_idx - first_idx) / 10, 1.5)

    def test_invalid_sampling_options_raise_clear_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for options in ({"target_fps": 0}, {"target_fps": float("nan")}, {"stable_duration": -1}, {"min_interval": -1}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    extract_stable_frames_debug("input.mp4", temp_dir, str(Path(temp_dir) / "motion.csv"), **options)


if __name__ == "__main__":
    unittest.main()
