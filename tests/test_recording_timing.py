"""Regression checks for frame placement and calibrated recording dimensions."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from camera_manager import CameraManager
from recording_manager import RecordingManager


class MemoryWriter:
    def __init__(self):
        self.frames = []

    def write(self, frame):
        self.frames.append(frame)


class RecordingRegressionTests(unittest.TestCase):
    def recorder(self, config=None):
        recorder = RecordingManager(SimpleNamespace(), Path(__file__).parent, 4, (16, 12), config=config)
        recorder.writer = MemoryWriter()
        return recorder

    def test_gap_preserves_new_frame_presentation_time(self):
        recorder = self.recorder()
        recorder._write_timed_frame("first", 100.0)
        recorder._write_timed_frame("next", 100.75)
        self.assertEqual(recorder.writer.frames, ["first", "first", "first", "next"])
        self.assertEqual(recorder.duplicated_frame_count, 2)

    def test_regular_cadence_does_not_duplicate(self):
        recorder = self.recorder()
        for index in range(8):
            recorder._write_timed_frame(index, 100.0 + index / 4)
        self.assertEqual(recorder.writer.frames, list(range(8)))
        self.assertEqual(recorder.duplicated_frame_count, 0)

    def test_frame_in_same_output_slot_is_dropped(self):
        recorder = self.recorder()
        recorder._write_timed_frame("first", 100.0)
        recorder._write_timed_frame("early", 100.125)
        recorder._write_timed_frame("next", 100.25)
        self.assertEqual(recorder.writer.frames, ["first", "next"])

    def test_unused_frames_skip_watermark_processing(self):
        recorder = self.recorder()
        frames = iter([(100.0, 1), (100.125, 2), (100.25, 3)])

        def receive(*args, **kwargs):
            timestamp, sequence = next(frames)
            if sequence == 3:
                recorder._stop_event.set()
            return True, np.zeros((12, 16, 3), dtype=np.uint8), sequence, timestamp

        recorder.camera.wait_for_new_frame = receive
        with patch("recording_manager.has_min_free_disk_space", return_value=True), \
                patch.object(recorder, "apply_watermark", side_effect=lambda frame, _: frame) as watermark:
            recorder._record_loop()
        self.assertEqual(watermark.call_count, 2)
        self.assertEqual(len(recorder.writer.frames), 2)
        self.assertEqual(recorder.timeline_dropped_frame_count, 1)

    def test_crop_keeps_writer_dimensions_and_selected_content(self):
        config = SimpleNamespace(camera_calibration_enabled=True,
            camera_calibration_roi_enabled=True, camera_calibration_roi_x=4,
            camera_calibration_roi_y=3, camera_calibration_roi_w=4,
            camera_calibration_roi_h=4)
        recorder = self.recorder(config)
        frame = np.zeros((12, 16, 3), dtype=np.uint8)
        frame[3:7, 4:8] = 123
        result = recorder._apply_camera_calibration(frame)
        self.assertEqual(result.shape, (12, 16, 3))
        self.assertTrue(np.all(result == 123))
        config.camera_calibration_roi_x = -1
        self.assertIs(recorder._apply_camera_calibration(frame), frame)

    def test_consumers_cannot_mutate_published_camera_frame(self):
        camera = CameraManager(enable_lens_correction=False)
        camera._set_latest_frame(np.zeros((12, 16, 3), dtype=np.uint8))
        _, preview = camera.read_frame()
        preview[:] = 255
        ok, recorded, sequence, timestamp = camera.wait_for_new_frame(0)
        self.assertTrue(ok)
        self.assertTrue(np.all(recorded == 0))
        self.assertEqual(sequence, 1)
        self.assertIsNotNone(timestamp)


if __name__ == "__main__":
    unittest.main()
