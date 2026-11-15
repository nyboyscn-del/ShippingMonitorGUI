from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from camera_manager import cv2
from camera_manager import CameraManager
from config_manager import get_config, validate_license
from excel_manager import ExcelManager
from playback_manager import PlaybackManager
from query_manager import QueryManager
from recording_manager import (
    RecordingManager,
    build_mp4_path,
    build_video_path,
    get_free_disk_gb,
    has_min_free_disk_space,
    should_auto_stop_recording,
)


def sample_config() -> dict:
    return {
        "camera_index": 0,
        "resolution": "2560x1440",
        "fps": 15,
        "storage_path": "C:/fhjk260227",
        "segment_duration": 600,
        "segment_on_barcode": True,
        "auto_stop_enabled": True,
        "auto_stop_timeout": 180,
        "keep_camera_on_timeout": True,
        "retention_days": 365,
        "enable_scanner": True,
        "disable_duplicate_scan": False,
        "duplicate_policy": "block_completed_only",
        "duplicate_block_seconds": 30,
        "beep_enabled": True,
        "excel_file": "data/scan_records.xlsx",
        "license_file": "config/license.json",
        "mp4_output_folder": "MP4",
        "query_default_source": "",
        "query_default_start_date": "",
        "query_default_end_date": "",
        "watermark_position": "top_left",
        "watermark_font_scale": 0.9,
        "watermark_color": "#00FF00",
        "watermark_opacity": 0.75,
        "generate_mp4_on_query": False,
        "min_free_disk_gb": 5,
        "watchdog_enabled": True,
        "watchdog_max_failures": 30,
        "watchdog_retry_count": 3,
        "watchdog_retry_interval": 2,
    }


class Stage1Tests(unittest.TestCase):
    def test_config_can_be_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            example = tmp_path / "config.example.json"
            runtime = tmp_path / "config.json"
            example.write_text(json.dumps(sample_config()), encoding="utf-8")

            config = get_config(runtime, example)
            self.assertEqual(config.resolution_size, (2560, 1440))
            self.assertTrue(runtime.exists())

    def test_existing_config_gets_missing_p1_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            example = tmp_path / "config.example.json"
            runtime = tmp_path / "config.json"
            full_config = sample_config()
            old_config = dict(full_config)
            old_config.pop("min_free_disk_gb")
            old_config.pop("watchdog_enabled")
            old_config["auto_stop_timeout"] = 99

            example.write_text(json.dumps(full_config), encoding="utf-8")
            runtime.write_text(json.dumps(old_config), encoding="utf-8")

            config = get_config(runtime, example)
            self.assertEqual(config.auto_stop_timeout, 99)
            self.assertEqual(config.min_free_disk_gb, 5)
            self.assertTrue(config.watchdog_enabled)

    def test_legacy_duplicate_scan_field_maps_to_new_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            example = tmp_path / "config.example.json"
            runtime = tmp_path / "config.json"
            full_config = sample_config()
            old_config = dict(full_config)
            old_config.pop("duplicate_policy")
            old_config.pop("duplicate_block_seconds")
            old_config["disable_duplicate_scan"] = True

            example.write_text(json.dumps(full_config), encoding="utf-8")
            runtime.write_text(json.dumps(old_config), encoding="utf-8")

            config = get_config(runtime, example)
            self.assertEqual(config.duplicate_policy, "block_within_seconds")
            self.assertEqual(config.duplicate_block_seconds, 30)

    def test_missing_license_has_friendly_error(self):
        ok, message = validate_license(Path(tempfile.gettempdir()) / "missing_stage1_license.json")
        self.assertFalse(ok)
        self.assertIn("License file not found", message)

    def test_excel_can_create_and_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            excel_path = Path(tmp) / "scan_records.xlsx"
            manager = ExcelManager(excel_path)
            manager.append_record("YT8869602188120", "C:/fhjk260227/20260518/test.avi", "test")
            self.assertTrue(excel_path.exists())

    def test_simulated_tracking_number_can_generate_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            excel_path = Path(tmp) / "scan_records.xlsx"
            video_path = Path(tmp) / "20260518_153347_YT8869602188120.avi"
            manager = ExcelManager(excel_path)
            manager.append_record("YT8869602188120", video_path, "test", "simulated")
            self.assertTrue(excel_path.exists())

    def test_video_path_naming_rule(self):
        now = datetime(2026, 5, 18, 15, 33, 47)
        path = build_video_path("C:/fhjk260227", "YT8869602188120", now)
        self.assertEqual(path.name, "20260518_153347_YT8869602188120.avi")
        self.assertIn("20260518", str(path))
        self.assertIn("153347", str(path))

    def test_mp4_path_naming_rule(self):
        avi = Path("D:/records/20260518/153347/20260518_153347_YT8869602188120.avi")
        path = build_mp4_path(avi, "YT8869602188120")
        self.assertEqual(path.name, "20260518_153347_YT8869602188120.mp4")
        self.assertEqual(path.parent, avi.parent)

    def test_watermark_changes_frame_pixels(self):
        class DummyCamera:
            resolution = (640, 480)

            def is_opened(self):
                return True

            def open(self):
                return True

        manager = RecordingManager(
            DummyCamera(),
            tempfile.gettempdir(),
            15,
            (640, 480),
            watermark_position="top_left",
            watermark_font_scale=0.9,
            watermark_color="#00FF00",
            watermark_opacity=0.75,
        )
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        watermarked = manager.apply_watermark(frame.copy(), "TEST123")
        self.assertTrue(np.any(watermarked != frame))

    def test_watermark_leaves_pixels_outside_text_region_unchanged(self):
        class DummyCamera:
            resolution = (640, 480)

        manager = RecordingManager(
            DummyCamera(),
            tempfile.gettempdir(),
            15,
            (640, 480),
            watermark_position="top_left",
        )
        frame = np.full((480, 640, 3), 37, dtype=np.uint8)
        watermarked = manager.apply_watermark(frame.copy(), "TEST123")
        self.assertTrue(np.any(watermarked[:160] != frame[:160]))
        self.assertTrue(np.array_equal(watermarked[240:], frame[240:]))

    def test_timed_writer_drops_only_frames_ahead_of_output_timeline(self):
        class DummyCamera:
            resolution = (320, 240)

        class DummyWriter:
            def __init__(self):
                self.frames = []

            def write(self, frame):
                self.frames.append(frame.copy())

        manager = RecordingManager(DummyCamera(), tempfile.gettempdir(), 10, (320, 240))
        manager.writer = DummyWriter()
        manager.writer_fps = 10.0
        frames = [np.full((240, 320, 3), value, dtype=np.uint8) for value in (10, 20, 30)]

        with patch("recording_manager.time.monotonic", side_effect=(100.0, 100.02, 100.11)):
            for frame in frames:
                manager._write_timed_frame(frame)

        self.assertEqual(manager.written_frame_count, 2)
        self.assertEqual(manager.timeline_dropped_frame_count, 1)
        self.assertEqual([int(frame[0, 0, 0]) for frame in manager.writer.frames], [10, 30])

    def test_query_mp4_export_and_playback_readability(self):
        if cv2 is None:
            self.skipTest("opencv-python is required for MP4 conversion test.")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            avi_path = tmp_path / "20260518_153347_YT8869602188120.avi"
            writer = cv2.VideoWriter(str(avi_path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (320, 240))
            for index in range(8):
                frame = np.full((240, 320, 3), (20 + index, 80, 160), dtype=np.uint8)
                writer.write(frame)
            writer.release()

            excel_path = tmp_path / "scan_records.xlsx"
            excel = ExcelManager(excel_path)
            excel.append_record(
                "YT8869602188120",
                avi_path,
                "gui",
                "unit test",
                datetime(2026, 5, 18, 15, 33, 47),
            )

            query = QueryManager(excel_path)
            results = query.query("YT8869602188120", "2026-05-18", "2026-05-18", "GUI")
            self.assertEqual(len(results), 1)
            mp4_path = query.ensure_mp4(avi_path, "YT8869602188120")
            self.assertTrue(mp4_path.exists())
            self.assertTrue(PlaybackManager().can_read_first_frame(mp4_path))

            csv_path = query.export_csv(results, tmp_path / "query.csv")
            xlsx_path = query.export_excel(results, tmp_path / "query.xlsx")
            self.assertTrue(csv_path.exists())
            self.assertTrue(xlsx_path.exists())

    def test_disk_space_check_functions(self):
        with tempfile.TemporaryDirectory() as tmp:
            free_gb = get_free_disk_gb(tmp)
            self.assertGreaterEqual(free_gb, 0)
            self.assertTrue(has_min_free_disk_space(tmp, 0))

    def test_auto_stop_logic(self):
        self.assertTrue(should_auto_stop_recording(100.0, 281.0, True, 180, True))
        self.assertFalse(should_auto_stop_recording(100.0, 200.0, True, 180, True))
        self.assertFalse(should_auto_stop_recording(100.0, 281.0, False, 180, True))
        self.assertFalse(should_auto_stop_recording(None, 281.0, True, 180, True))
        self.assertFalse(should_auto_stop_recording(100.0, 281.0, True, 180, False))

    def test_camera_can_be_skipped(self):
        if os.environ.get("RUN_CAMERA_TEST") != "1":
            self.skipTest("Set RUN_CAMERA_TEST=1 to open a real camera.")
        camera = CameraManager()
        self.assertTrue(camera.open())
        camera.release()


if __name__ == "__main__":
    unittest.main()
