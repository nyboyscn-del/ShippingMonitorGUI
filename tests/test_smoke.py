"""Release smoke tests: module imports, headless GUI paths, path safety, licensing.

The whole suite is expected to finish well inside three minutes. GUI cases are
skipped when PyQt5 is unavailable so the core smoke checks still run on build
machines without a desktop stack.
"""

from __future__ import annotations

import base64
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

PYQT_AVAILABLE = importlib.util.find_spec("PyQt5") is not None
CRYPTOGRAPHY_AVAILABLE = importlib.util.find_spec("cryptography") is not None

CORE_MODULES = (
    "barcode_listener",
    "barcode_scanner",
    "camera_manager",
    "config_manager",
    "erp_manager",
    "excel_manager",
    "lan_query_server",
    "license_code_manager",
    "playback_manager",
    "query_manager",
    "recording_manager",
    "version",
)
GUI_MODULES = ("gui_main", "dialogs.camera_calibration_dialog")
SMOKE_FLAGS = (
    "--smoke-test",
    "--smoke-test-camera",
    "--smoke-test-record",
    "--smoke-test-autostop",
    "--smoke-test-disk",
    "--smoke-test-watchdog",
    "--smoke-test-duplicate-policy",
    "--smoke-test-query",
    "--smoke-test-frame-idle",
    "--smoke-test-scan",
)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class ModuleImportSmokeTests(unittest.TestCase):
    def test_core_modules_import(self):
        for name in CORE_MODULES:
            with self.subTest(module=name):
                try:
                    importlib.import_module(name)
                except ImportError as exc:
                    self.skipTest(f"optional runtime dependency missing for {name}: {exc}")

    @unittest.skipUnless(PYQT_AVAILABLE, "PyQt5 is required to import GUI modules.")
    def test_gui_modules_import(self):
        for name in GUI_MODULES:
            with self.subTest(module=name):
                importlib.import_module(name)

    def test_headless_smoke_entry_points_are_registered(self):
        source = (SRC_DIR / "gui_main.py").read_text(encoding="utf-8")
        for flag in SMOKE_FLAGS:
            with self.subTest(flag=flag):
                self.assertIn(flag, source)
        self.assertIn("_is_smoke_test_mode", source)


class LanPathSafetyTests(unittest.TestCase):
    def setUp(self):
        from lan_query_server import LanQueryServer
        from query_manager import QueryManager

        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "recordings"
        (self.root / "2026-05-18").mkdir(parents=True)
        (self.root / "2026-05-18" / "clip.mp4").write_bytes(b"mp4")
        self.server = LanQueryServer(
            "127.0.0.1",
            0,
            "test-token",
            QueryManager(Path(self.tmp.name) / "records.xlsx"),
            [self.root],
            PROJECT_ROOT / "web" / "lan_query",
        )
        self.index = self.server.allowed_roots.index(self.root.resolve())

    def tearDown(self):
        self.tmp.cleanup()

    def test_allowed_relative_path_resolves(self):
        target = self.server.resolve_public_path(f"{self.index}/2026-05-18/clip.mp4", "mp4")
        self.assertEqual(target, (self.root / "2026-05-18" / "clip.mp4").resolve())

    def test_url_encoded_allowed_path_resolves(self):
        target = self.server.resolve_public_path(f"{self.index}%2F2026-05-18%2Fclip.mp4", "mp4")
        self.assertEqual(target, (self.root / "2026-05-18" / "clip.mp4").resolve())

    def test_traversal_and_absolute_paths_are_rejected(self):
        rejected = (
            f"{self.index}/../escape.mp4",
            f"{self.index}/%2e%2e/escape.mp4",
            f"{self.index}/2026-05-18/../../escape.mp4",
            f"/{self.index}/2026-05-18/clip.mp4",
            f"{self.index}\\2026-05-18\\clip.mp4",
            f"{len(self.server.allowed_roots)}/2026-05-18/clip.mp4",
            "-1/2026-05-18/clip.mp4",
            "clip.mp4",
            "",
        )
        for value in rejected:
            with self.subTest(path=value):
                self.assertIsNone(self.server.resolve_public_path(value, "mp4"))

    def test_sensitive_parts_and_suffix_mismatch_are_rejected(self):
        rejected = (
            (f"{self.index}/config/clip.mp4", "mp4"),
            (f"{self.index}/src/clip.mp4", "mp4"),
            (f"{self.index}/2026-05-18/license.json", "json"),
            (f"{self.index}/2026-05-18/license_state_1.json", "json"),
            (f"{self.index}/2026-05-18/clip.avi", "mp4"),
            (f"{self.index}/2026-05-18/clip.pem", "pem"),
        )
        for value, file_type in rejected:
            with self.subTest(path=value, file_type=file_type):
                self.assertIsNone(self.server.resolve_public_path(value, file_type))

    def test_symlink_escape_is_rejected(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink is not supported on this platform.")
        outside = Path(self.tmp.name) / "outside.mp4"
        outside.write_bytes(b"outside")
        link = self.root / "2026-05-18" / "link.mp4"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        self.assertIsNone(self.server.resolve_public_path(f"{self.index}/2026-05-18/link.mp4", "mp4"))


class QueryWhitelistTests(unittest.TestCase):
    def setUp(self):
        from query_manager import QueryManager, safe_file_under_allowed_roots

        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "recordings"
        (self.root / "day").mkdir(parents=True)
        self.clip = self.root / "day" / "clip.mp4"
        self.clip.write_bytes(b"mp4")
        (self.root / "config").mkdir()
        (self.root / "config" / "clip.mp4").write_bytes(b"mp4")
        self.manager = QueryManager(Path(self.tmp.name) / "records.xlsx", allowed_roots=[self.root])
        self.safe_file_under_allowed_roots = staticmethod(safe_file_under_allowed_roots)

    def tearDown(self):
        self.tmp.cleanup()

    def test_allowed_absolute_and_relative_paths(self):
        self.assertEqual(self.safe_file_under_allowed_roots(self.clip, [self.root], {".mp4"}), self.clip.resolve())
        self.assertEqual(self.safe_file_under_allowed_roots("day/clip.mp4", [self.root], {".mp4"}), self.clip.resolve())

    def test_forbidden_and_invalid_paths(self):
        rejected = (
            (self.root / "day" / "clip.avi", {".mp4"}),
            ("day/clip.avi", {".mp4"}),
            ("../clip.mp4", {".mp4"}),
            (self.root / "config" / "clip.mp4", {".mp4"}),
            (self.root / "day" / "missing.mp4", {".mp4"}),
        )
        for value, extensions in rejected:
            with self.subTest(path=str(value)):
                self.assertIsNone(self.safe_file_under_allowed_roots(value, [self.root], extensions))

    def test_query_works_from_worker_threads(self):
        from excel_manager import ExcelManager

        excel = ExcelManager(Path(self.tmp.name) / "records.xlsx")
        excel.append_record("YT123456789", self.clip, "test")

        def worker(_: int) -> int:
            return len(self.manager.query("YT123456789", "", "", ""))

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(worker, range(8)))
        self.assertEqual(results, [1] * 8)


@unittest.skipUnless(CRYPTOGRAPHY_AVAILABLE, "cryptography is required for signature checks.")
class LicenseSignatureTests(unittest.TestCase):
    def test_malformed_authorization_code_is_rejected(self):
        from license_code_manager import verify_authorization_code

        for code in ("", "not-a-code", "SMG1.bad", "SMG1...", "SMG1.!!.??"):
            with self.subTest(code=code):
                result = verify_authorization_code(code)
                self.assertFalse(result.ok)
                self.assertEqual(result.status, "invalid_format")

    def test_tampered_signature_is_rejected(self):
        from license_code_manager import verify_authorization_code

        payload = {
            "license_version": 1,
            "product": "ShippingMonitorGUI",
            "machine_code": "a" * 64,
            "customer": "smoke-test",
            "edition": "permanent",
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": None,
            "features": {"recording": True, "query": True, "export": True, "camera_barcode": False},
        }
        payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        signature = b"not-a-valid-rsa-signature" * 4
        code = f"SMG1.{_b64url(payload_bytes)}.{_b64url(signature)}"
        result = verify_authorization_code(code, current_machine_code="a" * 64)
        self.assertFalse(result.ok)
        self.assertEqual(result.status, "invalid_signature")

    def test_formal_license_rollback_is_detected(self):
        from license_code_manager import get_formal_license_status

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "license_state.json"
            future = datetime.now(timezone.utc) + timedelta(days=3)
            state_path.write_text(
                json.dumps(
                    {
                        "signature_payload": "payload",
                        "signature": "signature",
                        "last_seen_time": future.isoformat(),
                    }
                ),
                encoding="utf-8",
            )
            status = get_formal_license_status(state_path, now=datetime.now(timezone.utc))
            self.assertFalse(status.ok)
            self.assertEqual(status.status, "time_error")

    def test_trial_rollback_is_detected(self):
        from license_code_manager import TrialManager

        with tempfile.TemporaryDirectory() as tmp:
            manager = TrialManager(
                primary_path=Path(tmp) / "trial_state.json",
                backup_path=Path(tmp) / "trial_state.backup.json",
                machine_code="a" * 64,
                trial_days=30,
            )
            started_at = datetime.now(timezone.utc)
            started = manager.start_trial(now=started_at)
            self.assertEqual(started.status, "trial_valid")
            rolled_back = manager.get_status(now=started_at - timedelta(days=3))
            self.assertFalse(rolled_back.ok)
            self.assertEqual(rolled_back.status, "trial_time_error")


class RetentionCleanupTests(unittest.TestCase):
    def test_only_expired_video_files_are_deleted(self):
        from recording_manager import cleanup_old_recordings

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "recordings"
            day = root / "2020-01-01"
            day.mkdir(parents=True)
            old_video = day / "old.avi"
            old_video.write_bytes(b"old")
            old_note = root / "keep.txt"
            old_note.write_text("keep", encoding="utf-8")
            fresh_video = root / "fresh.mp4"
            fresh_video.write_bytes(b"fresh")

            old_time = (datetime.now() - timedelta(days=40)).timestamp()
            for path in (old_video, old_note):
                os.utime(path, (old_time, old_time))

            result = cleanup_old_recordings(root, 30)

            self.assertEqual(result["deleted_files"], 1)
            self.assertEqual(result["failed"], 0)
            self.assertFalse(old_video.exists())
            self.assertTrue(fresh_video.exists())
            self.assertTrue(old_note.exists())


@unittest.skipUnless(PYQT_AVAILABLE, "PyQt5 is required for GUI smoke tests.")
class GuiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        for name in ("src", "web", "templates"):
            shutil.copytree(PROJECT_ROOT / name, cls.root / name)
        (cls.root / "config").mkdir()
        shutil.copy2(PROJECT_ROOT / "config" / "config.example.json", cls.root / "config" / "config.example.json")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_smoke(self, flag: str) -> str:
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["PYTHONPATH"] = str(self.root / "src")
        completed = subprocess.run(
            [sys.executable, str(self.root / "src" / "gui_main.py"), flag],
            cwd=self.root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=90,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)
        return completed.stdout

    def test_headless_startup_and_shutdown(self):
        self.run_smoke("--smoke-test")

    def test_headless_watchdog_logic(self):
        output = self.run_smoke("--smoke-test-watchdog")
        self.assertIn("smoke_watchdog_should_trigger", output)

    def test_headless_duplicate_policy_logic(self):
        output = self.run_smoke("--smoke-test-duplicate-policy")
        self.assertIn("smoke_duplicate_policy", output)


if __name__ == "__main__":
    unittest.main()
