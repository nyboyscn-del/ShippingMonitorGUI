from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from safe_print import safe_print

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover - depends on local runtime
    cv2 = None


@dataclass
class CameraState:
    opened: bool = False
    last_error: str = ""


class CameraManager:
    def __init__(
        self,
        camera_index: int = 0,
        resolution: tuple[int, int] = (2560, 1440),
        fps: int = 15,
        storage_path: str | Path = "C:/fhjk260227",
        enable_lens_correction: bool = False,
        camera_focus_enabled: bool = False,
        camera_focus_value: int = 0,
        camera_autofocus_enabled: bool = True,
        settings_source: str = "user config",
        preferred_backend: str = "DirectShow",
        fourcc_preference: str = "MJPG",
        log_callback=None,
    ):
        self.camera_index = camera_index
        self.resolution = resolution
        self.requested_resolution = resolution
        self.fps = fps
        self.storage_path = Path(storage_path)
        self.enable_lens_correction = enable_lens_correction
        self.camera_focus_enabled = camera_focus_enabled
        self.camera_focus_value = camera_focus_value
        self.camera_autofocus_enabled = camera_autofocus_enabled
        self.settings_source = settings_source
        self.preferred_backend = str(preferred_backend or "DirectShow")
        self.fourcc_preference = str(fourcc_preference or "MJPG").upper()
        self._log_callback = log_callback
        self.capture = None
        self.state = CameraState()
        self._recorder: Any = None
        self.actual_resolution: tuple[int, int] | None = None
        self.actual_fps: float | None = None
        self.measured_capture_fps: float | None = None
        self.actual_fourcc: str = ""
        self.backend_name: str = ""
        self._frame_condition = threading.Condition()
        self._latest_frame = None
        self._latest_frame_monotonic: float | None = None
        self._frame_sequence = 0
        self._lens_map_size: tuple[int, int] | None = None
        self._lens_map_x = None
        self._lens_map_y = None
        self._capture_stop_event = threading.Event()
        self._capture_thread: threading.Thread | None = None

    def open(self) -> bool:
        if cv2 is None:
            self.state = CameraState(False, "opencv-python is not installed.")
            logging.error(self.state.last_error)
            return False

        if self.capture is not None and self.capture.isOpened():
            self.state = CameraState(True, "")
            return True

        for backend_name, backend in self._capture_backends():
            for width, height in self._resolution_candidates():
                for requested_fps in self._fps_candidates():
                    for fourcc_name in self._fourcc_candidates():
                        if self._try_open_profile(
                            backend_name,
                            backend,
                            width,
                            height,
                            requested_fps,
                            fourcc_name,
                        ):
                            return True

        self.state = CameraState(False, self._camera_failure_message())
        safe_print(self.state.last_error)
        logging.error(self.state.last_error)
        return False

    def _try_open_profile(
        self,
        backend_name: str,
        backend: int | None,
        width: int,
        height: int,
        requested_fps: float,
        fourcc_name: str,
    ) -> bool:
        self._emit_log(
            "camera_open_attempt: "
            f"index={self.camera_index} backend={backend_name} fourcc={fourcc_name}"
        )
        capture = self._create_capture(backend)
        try:
            if fourcc_name != "DEFAULT":
                capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc_name))
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            capture.set(cv2.CAP_PROP_FPS, requested_fps)

            if not capture.isOpened():
                logging.warning(
                    "Camera open failed: index=%s backend=%s requested=%sx%s/%.2f",
                    self.camera_index,
                    backend_name,
                    width,
                    height,
                    requested_fps,
                )
                self._emit_log(
                    "camera_open_failed: "
                    f"index={self.camera_index} backend={backend_name} reason=not_opened"
                )
                return False

            ret, frame = self._read_test_frame(capture)
            if not ret or frame is None:
                logging.warning(
                    "Camera opened but could not read frame: index=%s backend=%s requested=%sx%s/%.2f",
                    self.camera_index,
                    backend_name,
                    width,
                    height,
                    requested_fps,
                )
                self._emit_log(
                    "camera_open_failed: "
                    f"index={self.camera_index} backend={backend_name} reason=no_valid_frame"
                )
                return False

            frame_height, frame_width = frame.shape[:2]
            actual_width = int(frame_width or capture.get(cv2.CAP_PROP_FRAME_WIDTH) or width)
            actual_height = int(frame_height or capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or height)
            reported_fps = float(capture.get(cv2.CAP_PROP_FPS)) or float(requested_fps)
            actual_fourcc = self._decode_fourcc(capture.get(cv2.CAP_PROP_FOURCC))
            acceptable_fourccs = {
                "MJPG": {"MJPG"},
                "YUY2": {"YUY2", "YUYV", "YUNV"},
                "DEFAULT": {actual_fourcc.upper()},
            }.get(fourcc_name, {fourcc_name})
            if actual_fourcc.upper() not in acceptable_fourccs:
                logging.warning(
                    "CAMERA_FOURCC_NOT_APPLIED: backend=%s requested_fourcc=%s actual_fourcc=%s "
                    "requested=%sx%s/%.2f",
                    backend_name,
                    fourcc_name,
                    actual_fourcc,
                    width,
                    height,
                    requested_fps,
                )
                if backend_name != "DEFAULT":
                    return False
            measured_fps, measured_frame = self._measure_capture_fps(capture, duration_seconds=2.0)
            if measured_frame is not None:
                frame = measured_frame
            if measured_fps < 0.5:
                logging.warning(
                    "Camera profile produced no usable frame rate: backend=%s requested=%sx%s/%.2f",
                    backend_name,
                    width,
                    height,
                    requested_fps,
                )
                return False

            self.capture = capture
            self.resolution = (actual_width, actual_height)
            self.actual_resolution = self.resolution
            self.actual_fps = reported_fps
            self.measured_capture_fps = measured_fps
            self.actual_fourcc = actual_fourcc
            self.backend_name = backend_name
            self.state = CameraState(True, "")
            self._set_latest_frame(frame)
            self._emit_log(
                "camera_selected: "
                f"index={self.camera_index} backend={backend_name} "
                f"fourcc={actual_fourcc} actual={actual_width}x{actual_height}/{measured_fps:.2f}"
            )

            try:
                if self.camera_autofocus_enabled:
                    capture.set(cv2.CAP_PROP_AUTOFOCUS, 1)
                elif self.camera_focus_enabled:
                    capture.set(cv2.CAP_PROP_AUTOFOCUS, 0)
                    capture.set(cv2.CAP_PROP_FOCUS, self.camera_focus_value)
                    logging.info("Manual focus set: value=%s", self.camera_focus_value)
            except Exception as focus_err:
                logging.debug("Focus setting not supported: %s", focus_err)

            autofocus_readback = capture.get(cv2.CAP_PROP_AUTOFOCUS)
            focus_readback = capture.get(cv2.CAP_PROP_FOCUS)
            brightness_readback = capture.get(cv2.CAP_PROP_BRIGHTNESS)
            contrast_readback = capture.get(cv2.CAP_PROP_CONTRAST)
            exposure_readback = capture.get(cv2.CAP_PROP_EXPOSURE)
            focus_mode = "autofocus" if self.camera_autofocus_enabled else (
                "manual" if self.camera_focus_enabled else "camera_default"
            )
            message = (
                f"Camera started: index={self.camera_index}, camera_backend={backend_name}, "
                f"requested_fourcc={fourcc_name}, camera_input_fourcc={actual_fourcc}, "
                f"requested={width}x{height}/{requested_fps:.2f}, "
                f"reported={actual_width}x{actual_height}/{reported_fps:.2f}, "
                f"measured_capture_fps={measured_fps:.2f}, "
                f"focus_mode={focus_mode}, autofocus_readback={autofocus_readback:.2f}, "
                f"manual_focus_value={self.camera_focus_value if self.camera_focus_enabled else 'unused'}, "
                f"focus_readback={focus_readback:.2f}, brightness_readback={brightness_readback:.2f}, "
                f"contrast_readback={contrast_readback:.2f}, exposure_readback={exposure_readback:.2f}, "
                f"settings_source={self.settings_source}, "
                f"lens_correction={'on' if self.enable_lens_correction else 'off'}"
            )
            safe_print(message)
            logging.info(message)
            if measured_fps < 10:
                logging.warning(
                    "WARNING: measured camera fps too low, check USB port/driver/backend/format. "
                    "camera_backend=%s camera_input_fourcc=%s measured_capture_fps=%.2f",
                    backend_name,
                    actual_fourcc,
                    measured_fps,
                )
            self._start_capture_thread()
            return True
        except Exception:
            logging.exception(
                "Camera profile failed: backend=%s requested=%sx%s/%.2f",
                backend_name,
                width,
                height,
                requested_fps,
            )
            return False
        finally:
            if self.capture is not capture:
                try:
                    capture.release()
                except Exception:
                    logging.exception("Camera capture release failed after profile attempt.")

    def read_frame(self):
        with self._frame_condition:
            frame = self._latest_frame
        return frame is not None, frame.copy() if frame is not None else None

    def wait_for_new_frame(self, last_sequence: int, timeout: float = 1.0):
        with self._frame_condition:
            self._frame_condition.wait_for(
                lambda: self._frame_sequence > last_sequence or self._capture_stop_event.is_set(),
                timeout=max(0.01, float(timeout)),
            )
            if self._frame_sequence <= last_sequence or self._latest_frame is None:
                return False, None, last_sequence, None
            frame = self._latest_frame
            sequence = self._frame_sequence
            captured_at = self._latest_frame_monotonic
        # Published arrays are replaced, never edited by the producer. Keep the
        # reference alive while copying outside the lock so capture can continue.
        return True, frame.copy(), sequence, captured_at

    def is_opened(self) -> bool:
        return bool(self.capture is not None and self.capture.isOpened())

    def release(self) -> None:
        self.stop_recording()
        self.release_capture_only()

    def release_capture_only(self) -> None:
        self._capture_stop_event.set()
        with self._frame_condition:
            self._frame_condition.notify_all()
        if (
            self._capture_thread is not None
            and self._capture_thread.is_alive()
            and threading.current_thread() is not self._capture_thread
        ):
            try:
                self._capture_thread.join(timeout=3)
            except Exception:
                logging.exception("Camera capture thread join failed.")
        self._capture_thread = None
        if self.capture is not None:
            try:
                self.capture.release()
            except Exception:
                logging.exception("Camera release failed.")
            finally:
                self.capture = None
        with self._frame_condition:
            self._latest_frame = None
            self._latest_frame_monotonic = None
        self._lens_map_size = None
        self._lens_map_x = None
        self._lens_map_y = None
        self.state = CameraState(False, "")
        logging.info("Camera released.")

    def start_recording(self, tracking_number: str) -> Path:
        return self._get_recorder().start_recording(tracking_number)

    def switch_segment(self, tracking_number: str) -> Path:
        return self._get_recorder().switch_segment(tracking_number)

    def stop_recording(self) -> None:
        if self._recorder is not None:
            self._recorder.stop_recording()

    def get_recording_status(self) -> dict[str, str | bool | None]:
        if self._recorder is None:
            return {"recording": False, "tracking_number": None, "video_path": None}
        return self._recorder.get_status()

    def _get_recorder(self):
        if self._recorder is None:
            from recording_manager import RecordingManager

            self._recorder = RecordingManager(self, self.storage_path, self.fps, self.resolution)
        return self._recorder

    def _create_capture(self, backend: int | None):
        if backend is None:
            return cv2.VideoCapture(self.camera_index)
        return cv2.VideoCapture(self.camera_index, backend)

    def _capture_backends(self) -> list[tuple[str, int | None]]:
        backends = [
            ("DirectShow", cv2.CAP_DSHOW),
            ("MSMF", cv2.CAP_MSMF),
            ("DEFAULT", None),
        ]
        preferred = self.preferred_backend.upper()
        return sorted(backends, key=lambda item: 0 if item[0].upper() == preferred else 1)

    def _fourcc_candidates(self) -> list[str]:
        candidates = [self.fourcc_preference, "MJPG", "YUY2", "DEFAULT"]
        return list(
            dict.fromkeys(
                candidate
                for candidate in candidates
                if len(candidate) == 4 or candidate == "DEFAULT"
            )
        )

    def _resolution_candidates(self) -> list[tuple[int, int]]:
        return [self.requested_resolution]

    def _fps_candidates(self) -> list[float]:
        requested = float(max(self.fps, 1))
        candidates = [requested]
        if requested > 15:
            candidates.append(15.0)
        return candidates

    def _read_test_frame(self, capture) -> tuple[bool, Any]:
        last_ret = False
        last_frame = None
        saw_black_frame = False
        for _ in range(5):
            last_ret, last_frame = capture.read()
            if last_ret and last_frame is not None:
                if self._is_valid_frame(last_frame):
                    return True, last_frame
                saw_black_frame = True
            time.sleep(0.15)
        if saw_black_frame:
            self._emit_log(
                f"camera_open_failed: index={self.camera_index} reason=opened but black frame"
            )
            return False, None
        return last_ret, last_frame

    @staticmethod
    def _is_valid_frame(frame) -> bool:
        if frame is None or not hasattr(frame, "shape") or len(frame.shape) < 2:
            return False
        height, width = frame.shape[:2]
        if width < 160 or height < 120:
            return False
        sample = frame[:: max(1, height // 120), :: max(1, width // 160)]
        return bool(float(np.mean(sample)) > 2.0 or float(np.std(sample)) > 1.0)

    def _emit_log(self, message: str) -> None:
        logging.info(message)
        if self._log_callback is None:
            return
        try:
            self._log_callback(message)
        except Exception:
            logging.debug("Camera log callback failed.", exc_info=True)

    def _measure_capture_fps(self, capture, duration_seconds: float) -> tuple[float, Any]:
        start = time.monotonic()
        deadline = start + max(0.5, float(duration_seconds))
        frame_count = 0
        last_frame = None
        while time.monotonic() < deadline:
            ok, frame = capture.read()
            if ok and frame is not None:
                if self.enable_lens_correction:
                    self._apply_lens_correction(frame)
                frame_count += 1
                last_frame = frame
        elapsed = max(0.001, time.monotonic() - start)
        return frame_count / elapsed, last_frame

    def _set_latest_frame(self, frame) -> None:
        if frame is None:
            return
        if self.enable_lens_correction:
            frame = self._apply_lens_correction(frame)
        with self._frame_condition:
            # Published frames must remain unchanged; readers own their copies.
            self._latest_frame = frame
            self._latest_frame_monotonic = time.monotonic()
            self._frame_sequence += 1
            self._frame_condition.notify_all()

    def _start_capture_thread(self) -> None:
        self._capture_stop_event.clear()
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            name="camera-capture",
            daemon=True,
        )
        self._capture_thread.start()

    def _capture_loop(self) -> None:
        while not self._capture_stop_event.is_set():
            capture = self.capture
            if capture is None or not capture.isOpened():
                break
            try:
                ok, frame = capture.read()
            except Exception:
                logging.exception("Camera frame capture failed.")
                time.sleep(0.05)
                continue
            if ok and frame is not None:
                self._set_latest_frame(frame)
            else:
                time.sleep(0.02)

    def _camera_failure_message(self) -> str:
        return (
            f"Could not open camera index {self.camera_index}.\n"
            "The camera may be busy.\n"
            "Please close the original shipping monitor, WeChat, browser, OBS, or other camera apps.\n"
            "If it still fails, change camera_index in config.json."
        )

    def _decode_fourcc(self, value: float) -> str:
        code = int(value)
        if code <= 0:
            return "UNKNOWN"
        decoded = "".join(chr((code >> 8 * index) & 0xFF) for index in range(4)).strip()
        if len(decoded) != 4 or any(ord(char) < 32 or ord(char) > 126 for char in decoded):
            return "UNKNOWN"
        return decoded

    def _apply_lens_correction(self, frame):
        height, width = frame.shape[:2]
        size = (width, height)
        if self._lens_map_size != size:
            camera_matrix = np.array(
                [
                    [width, 0, width / 2],
                    [0, width, height / 2],
                    [0, 0, 1],
                ],
                dtype=np.float32,
            )
            distortion = np.array([-0.08, 0.02, 0.0, 0.0, 0.0], dtype=np.float32)
            new_matrix, _roi = cv2.getOptimalNewCameraMatrix(
                camera_matrix, distortion, size, 1
            )
            self._lens_map_x, self._lens_map_y = cv2.initUndistortRectifyMap(
                camera_matrix, distortion, None, new_matrix, size, cv2.CV_32FC1
            )
            self._lens_map_size = size
        return cv2.remap(frame, self._lens_map_x, self._lens_map_y, cv2.INTER_LINEAR)


def probe_available_cameras(
    preferred_index: int = 0,
    preferred_backend: str = "DirectShow",
    width: int = 1920,
    height: int = 1080,
    fps: float = 16.0,
    resolution_policy: str = "config_first",
    writer_codec: str = "MJPG",
    max_index: int = 9,
    timeout_seconds: float = 25.0,
    log_callback=None,
) -> dict[str, object] | None:
    if cv2 is None:
        return None

    def emit(message: str) -> None:
        logging.info(message)
        if log_callback is not None:
            try:
                log_callback(message)
            except Exception:
                logging.debug("Camera probe log callback failed.", exc_info=True)

    backend_values = {
        "DirectShow": cv2.CAP_DSHOW,
        "MSMF": cv2.CAP_MSMF,
        "DEFAULT": None,
    }
    backend_names = ["DirectShow", "MSMF", "DEFAULT"]
    preferred_name = next(
        (name for name in backend_names if name.upper() == str(preferred_backend).upper()),
        "DirectShow",
    )
    backend_names.remove(preferred_name)
    backend_names.insert(0, preferred_name)
    indices = [int(preferred_index)] + [
        index for index in range(0, int(max_index) + 1) if index != int(preferred_index)
    ]
    deadline = time.monotonic() + max(1.0, float(timeout_seconds))
    decoder = CameraManager.__new__(CameraManager)
    candidates: list[dict[str, object]] = []
    configured_statuses: list[str] = []
    policy = str(resolution_policy or "config_first").lower()
    if policy not in {"config_first", "auto_best", "smooth_first"}:
        policy = "config_first"
    emit(f"recording_resolution_policy={policy}")
    emit(f"configured_resolution={int(width)}x{int(height)}")
    emit(f"configured_fps={float(fps):.0f}")
    emit(f"writer_codec_requested={str(writer_codec or 'MJPG').upper()}")
    emit(
        "camera_probe_scope="
        + ("configured_resolution_first" if policy == "config_first" else policy)
    )

    def score_candidate(
        actual_width: int,
        actual_height: int,
        actual_fourcc: str,
        measured_fps: float,
        stable: bool,
    ) -> int:
        score = 200
        if actual_fourcc == "MJPG":
            score += 80
        elif actual_fourcc in {"YUY2", "YUYV", "YUNV"}:
            score -= 30
        score += int(round(measured_fps * 10))
        pixels = actual_width * actual_height
        if pixels >= 1920 * 1080:
            score += 60
        elif pixels >= 1600 * 900:
            score += 40
        elif pixels >= 1280 * 720:
            score += 30
        if stable:
            score += 20
        if measured_fps < 8:
            score -= 100
        if measured_fps < 5:
            score -= 200
        return score

    def evaluate(
        index: int,
        backend_name: str,
        fourcc_name: str,
        requested_width: int,
        requested_height: int,
        requested_fps: float,
    ) -> str:
        if time.monotonic() >= deadline:
            return "timeout"
        backend = backend_values[backend_name]
        capture = cv2.VideoCapture(index) if backend is None else cv2.VideoCapture(index, backend)
        opened = False
        black_frame = False
        try:
            if fourcc_name != "DEFAULT":
                capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc_name))
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, requested_width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, requested_height)
            capture.set(cv2.CAP_PROP_FPS, requested_fps)
            opened = bool(capture.isOpened())
            if not opened:
                emit(
                    "camera_candidate: "
                    f"index={index} backend={backend_name} "
                    f"requested={requested_width}x{requested_height}/{requested_fps:.0f} "
                    f"fourcc={fourcc_name} opened=False black_frame=False score=-999"
                )
                return "unavailable"

            valid_frame = None
            saw_frame = False
            for _ in range(5):
                ok, frame = capture.read()
                if ok and frame is not None:
                    saw_frame = True
                    if CameraManager._is_valid_frame(frame):
                        valid_frame = frame
                        break
                time.sleep(0.05)
            if valid_frame is None:
                black_frame = saw_frame
                emit(
                    "camera_candidate: "
                    f"index={index} backend={backend_name} "
                    f"requested={requested_width}x{requested_height}/{requested_fps:.0f} "
                    f"fourcc={fourcc_name} opened=True black_frame={black_frame} score=-999"
                )
                return "black_frame" if black_frame else "unavailable"

            actual_height, actual_width = valid_frame.shape[:2]
            reported_fps = float(capture.get(cv2.CAP_PROP_FPS)) or requested_fps
            actual_fourcc = decoder._decode_fourcc(capture.get(cv2.CAP_PROP_FOURCC))
            measure_started = time.monotonic()
            measure_deadline = min(deadline, measure_started + 0.65)
            frame_count = 0
            while time.monotonic() < measure_deadline:
                ok, measured_frame = capture.read()
                if ok and measured_frame is not None and CameraManager._is_valid_frame(measured_frame):
                    frame_count += 1
            elapsed = max(0.001, time.monotonic() - measure_started)
            measured_fps = frame_count / elapsed
            expected_frames = min(reported_fps, requested_fps) * elapsed
            stable = frame_count >= max(3, int(expected_frames * 0.5))
            score = score_candidate(
                actual_width,
                actual_height,
                actual_fourcc,
                measured_fps,
                stable,
            )
            candidate = {
                "camera_index": index,
                "camera_backend": backend_name,
                "camera_fourcc_preference": fourcc_name,
                "requested_width": requested_width,
                "requested_height": requested_height,
                "requested_fps": requested_fps,
                "actual_width": actual_width,
                "actual_height": actual_height,
                "actual_fps": reported_fps,
                "measured_capture_fps": measured_fps,
                "actual_fourcc": actual_fourcc,
                "stable": stable,
                "score": score,
            }
            candidates.append(candidate)
            emit(
                "camera_candidate: "
                f"index={index} backend={backend_name} "
                f"requested={requested_width}x{requested_height}/{requested_fps:.0f} "
                f"fourcc={fourcc_name} opened=True black_frame=False "
                f"actual={actual_width}x{actual_height}/{reported_fps:.2f} "
                f"measured_capture_fps={measured_fps:.2f} stable={stable} score={score}"
            )
            return "valid"
        except Exception as exc:
            emit(
                "camera_candidate: "
                f"index={index} backend={backend_name} "
                f"requested={requested_width}x{requested_height}/{requested_fps:.0f} "
                f"fourcc={fourcc_name} opened={opened} black_frame={black_frame} "
                f"error={type(exc).__name__} score=-999"
            )
            return "unavailable"
        finally:
            try:
                capture.release()
            except Exception:
                pass

    fps_candidates = list(dict.fromkeys((float(fps), 15.0, 10.0)))
    fourcc_candidates = ["MJPG", "YUY2", "DEFAULT"]
    resolution_candidates = [
        (3840, 2160),
        (2560, 1440),
        (1920, 1080),
        (1600, 900),
        (1280, 720),
    ]

    def scan_resolution(
        requested_width: int,
        requested_height: int,
        configured: bool,
        stop_on_usable: bool = True,
        stop_at: float | None = None,
    ) -> None:
        for index in indices:
            for backend_name in backend_names:
                for fourcc_name in fourcc_candidates:
                    for requested_fps in fps_candidates:
                        status = evaluate(
                            index,
                            backend_name,
                            fourcc_name,
                            requested_width,
                            requested_height,
                            requested_fps,
                        )
                        if configured:
                            configured_statuses.append(status)
                        if (
                            stop_on_usable
                            and status == "valid"
                            and candidates
                            and int(candidates[-1]["actual_width"]) == requested_width
                            and int(candidates[-1]["actual_height"]) == requested_height
                            and float(candidates[-1]["measured_capture_fps"]) >= 8.0
                        ):
                            return
                        if time.monotonic() >= deadline:
                            return
                        if stop_at is not None and time.monotonic() >= stop_at:
                            return

    if policy == "config_first":
        configured_deadline = min(
            deadline,
            time.monotonic() + min(12.0, max(2.0, float(timeout_seconds) * 0.55)),
        )
        scan_resolution(
            int(width),
            int(height),
            configured=True,
            stop_at=configured_deadline,
        )
        configured_candidates = [
            item
            for item in candidates
            if int(item["actual_width"]) == int(width)
            and int(item["actual_height"]) == int(height)
        ]
        usable_configured = [
            item
            for item in configured_candidates
            if float(item["measured_capture_fps"]) >= 8.0
        ]
        if usable_configured:
            pool = usable_configured
            fallback_reason = ""
            source = "configured_resolution"
        else:
            if configured_candidates:
                fallback_reason = "configured_resolution_low_fps"
                emit("low_fps_warning=TRUE")
                emit(
                    "camera_quality_warning: configured resolution measured_capture_fps "
                    "below 8fps; trying lower resolution"
                )
            elif "black_frame" in configured_statuses:
                fallback_reason = "configured_resolution_black_frame"
            else:
                fallback_reason = "configured_resolution_unavailable"
            emit(f"fallback_reason={fallback_reason}")
            configured_pixels = int(width) * int(height)
            for fallback_width, fallback_height in resolution_candidates:
                if (
                    fallback_width * fallback_height >= configured_pixels
                    or (fallback_width, fallback_height) == (int(width), int(height))
                ):
                    continue
                scan_resolution(fallback_width, fallback_height, configured=False)
                usable_fallback = [
                    item
                    for item in candidates
                    if (
                        int(item["actual_width"]),
                        int(item["actual_height"]),
                    )
                    == (fallback_width, fallback_height)
                    and float(item["measured_capture_fps"]) >= 8.0
                ]
                if usable_fallback:
                    break
            fallback_pool = [
                item
                for item in candidates
                if (
                    int(item["actual_width"]),
                    int(item["actual_height"]),
                )
                != (int(width), int(height))
                and float(item["measured_capture_fps"]) >= 8.0
            ]
            pool = fallback_pool or configured_candidates or candidates
            source = (
                "fallback"
                if fallback_pool
                else "configured_resolution_low_fps_used"
                if configured_candidates
                else "fallback"
            )
    else:
        for candidate_width, candidate_height in resolution_candidates:
            scan_resolution(candidate_width, candidate_height, configured=False)
            if time.monotonic() >= deadline:
                break
        pool = candidates
        fallback_reason = ""
        source = policy

    if not candidates:
        emit(
            "camera_probe_all_failed"
            + (": reason=timeout" if time.monotonic() >= deadline else "")
        )
        return None

    best = max(pool, key=lambda item: (int(item["score"]), float(item["measured_capture_fps"])))
    selected = dict(best)
    selected["source"] = source
    selected["fallback_reason"] = fallback_reason
    selected["resolution_policy"] = policy
    selected["writer_codec"] = str(writer_codec or "MJPG").upper()
    selected["mode"] = (
        "QUALITY_1080P"
        if int(best["actual_width"]) >= 1920 and float(best["measured_capture_fps"]) >= 10
        else "STABLE_720P"
        if int(best["actual_width"]) <= 1280 and float(best["measured_capture_fps"]) >= 8
        else "LOW_FPS_WARNING"
        if float(best["measured_capture_fps"]) < 8
        else "AUTO_RECOMMENDED"
    )
    emit(
        "camera_best_selected: "
        f"index={best['camera_index']} backend={best['camera_backend']} "
        f"fourcc={best['actual_fourcc']} "
        f"resolution={best['actual_width']}x{best['actual_height']} "
        f"fps={best['requested_fps']:.0f} "
        f"measured_capture_fps={best['measured_capture_fps']:.2f} "
        f"score={best['score']} source={source} "
        f"fallback_reason={fallback_reason or 'none'} mode={selected['mode']}"
    )
    if float(best["measured_capture_fps"]) < 8:
        emit("camera_quality_warning: measured_capture_fps below 8fps")
    return selected


def validate_camera_candidate(
    camera_index: int,
    backend_name: str,
    fourcc_name: str,
    width: int,
    height: int,
    fps: float,
    timeout_seconds: float = 2.0,
) -> dict[str, object]:
    if cv2 is None:
        return {"valid": False, "reason": "opencv_unavailable"}

    backend = {
        "DIRECTSHOW": cv2.CAP_DSHOW,
        "MSMF": cv2.CAP_MSMF,
        "DEFAULT": None,
    }.get(str(backend_name).upper())
    if str(backend_name).upper() not in {"DIRECTSHOW", "MSMF", "DEFAULT"}:
        return {"valid": False, "reason": "unknown_backend"}

    capture = (
        cv2.VideoCapture(int(camera_index))
        if backend is None
        else cv2.VideoCapture(int(camera_index), backend)
    )
    deadline = time.monotonic() + max(0.8, float(timeout_seconds))
    try:
        if str(fourcc_name).upper() != "DEFAULT":
            capture.set(
                cv2.CAP_PROP_FOURCC,
                cv2.VideoWriter_fourcc(*str(fourcc_name).upper()),
            )
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, int(width))
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))
        capture.set(cv2.CAP_PROP_FPS, float(fps))
        if not capture.isOpened():
            return {"valid": False, "reason": "not_opened"}

        valid_frame = None
        saw_frame = False
        for _ in range(5):
            ok, frame = capture.read()
            if ok and frame is not None:
                saw_frame = True
                if CameraManager._is_valid_frame(frame):
                    valid_frame = frame
                    break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        if valid_frame is None:
            return {
                "valid": False,
                "reason": "black_frame" if saw_frame else "no_readable_frame",
            }

        actual_height, actual_width = valid_frame.shape[:2]
        reported_fps = float(capture.get(cv2.CAP_PROP_FPS)) or float(fps)
        measure_started = time.monotonic()
        frame_count = 0
        while time.monotonic() < deadline:
            ok, frame = capture.read()
            if ok and frame is not None and CameraManager._is_valid_frame(frame):
                frame_count += 1
        elapsed = max(0.001, time.monotonic() - measure_started)
        measured_fps = frame_count / elapsed
        decoder = CameraManager.__new__(CameraManager)
        actual_fourcc = decoder._decode_fourcc(capture.get(cv2.CAP_PROP_FOURCC))
        return {
            "valid": True,
            "reason": "ok",
            "actual_width": actual_width,
            "actual_height": actual_height,
            "actual_fps": reported_fps,
            "measured_capture_fps": measured_fps,
            "actual_fourcc": actual_fourcc,
        }
    except Exception as exc:
        return {"valid": False, "reason": type(exc).__name__}
    finally:
        try:
            capture.release()
        except Exception:
            pass
