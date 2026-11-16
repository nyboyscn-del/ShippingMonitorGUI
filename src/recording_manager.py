from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from camera_manager import CameraManager, cv2


LOW_DISK_BLOCKED_MESSAGE = "Disk free space too low, recording blocked."
LOW_DISK_STOPPED_MESSAGE = "Disk free space too low, recording stopped."
WATCHDOG_RECONNECTED_MESSAGE = "Camera watchdog reconnected."
WATCHDOG_FAILED_MESSAGE = "Camera watchdog failed, please check camera."
WATCHDOG_RECORDING_STOPPED_MESSAGE = "Camera watchdog failed; recording stopped."
RETENTION_VIDEO_SUFFIXES = {".avi", ".mp4"}
RETENTION_SKIP_DIRS = {"backup", "config", "dist", "logs", "reports", "src", "__pycache__"}
_FFMPEG_STATUS_LOGGED: set[str] = set()
WRITER_FPS_HEADROOM = 0.95
WRITE_FRAME_MAX_RETRIES = 3
WRITE_FRAME_RETRY_INTERVAL_SECONDS = 0.05


def sanitize_tracking_number(tracking_number: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", tracking_number.strip())
    return cleaned or "UNKNOWN"


def build_video_path(storage_path: str | Path, tracking_number: str, now: datetime | None = None) -> Path:
    timestamp = now or datetime.now()
    safe_number = sanitize_tracking_number(tracking_number)
    session_dir = Path(storage_path) / timestamp.strftime("%Y%m%d") / timestamp.strftime("%H%M%S")
    filename = f"{timestamp.strftime('%Y%m%d_%H%M%S')}_{safe_number}.avi"
    return session_dir / filename


def build_mp4_path(avi_path: str | Path, tracking_number: str, mp4_folder_name: str = "MP4") -> Path:
    avi = Path(avi_path)
    return avi.with_suffix(".mp4")


def _emit_mp4_log(message: str, logger=None, level: int = logging.INFO) -> None:
    logging.log(level, message)
    if logger is not None:
        try:
            logger(message)
        except Exception:  # noqa: BLE001
            logging.exception("MP4 logger failed.")


def _emit_ffmpeg_status_once(key: str, message: str, logger=None) -> None:
    if key in _FFMPEG_STATUS_LOGGED:
        return
    _FFMPEG_STATUS_LOGGED.add(key)
    _emit_mp4_log(message, logger)


def _runtime_search_roots() -> list[Path]:
    roots: list[Path] = []
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
    else:
        roots.append(Path(__file__).resolve().parents[1])

    bundle_root = getattr(sys, "_MEIPASS", "")
    if bundle_root:
        roots.append(Path(bundle_root).resolve())

    project_root = Path(__file__).resolve().parents[1]
    if project_root not in roots:
        roots.append(project_root)
    return roots


def find_ffmpeg_executable(logger=None) -> Path | None:
    candidates: list[Path] = []
    for root in _runtime_search_roots():
        candidates.extend(
            [
                root / "tools" / "ffmpeg" / "ffmpeg.exe",
                root / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe",
            ]
        )

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if candidate.exists():
            _emit_ffmpeg_status_once(f"found:{resolved}", f"FFmpeg found: {resolved}", logger)
            return resolved

    path_ffmpeg = shutil.which("ffmpeg")
    if path_ffmpeg:
        resolved = Path(path_ffmpeg).resolve()
        _emit_ffmpeg_status_once(f"found:{resolved}", f"FFmpeg found: {resolved}", logger)
        return resolved

    _emit_ffmpeg_status_once("missing", "FFmpeg not found, fallback to OpenCV mp4v", logger)
    return None


def convert_avi_to_mp4_ffmpeg(
    input_avi: str | Path,
    output_mp4: str | Path,
    ffmpeg_path: str | Path | None = None,
    logger=None,
) -> bool:
    source = Path(input_avi)
    target = Path(output_mp4)
    executable = Path(ffmpeg_path) if ffmpeg_path else find_ffmpeg_executable(logger)
    if executable is None:
        return False
    if not source.exists():
        _emit_mp4_log(f"FFmpeg MP4 failed, fallback to OpenCV: AVI file not found: {source}", logger, logging.WARNING)
        return False

    target.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target.with_name(f"{target.stem}.ffmpeg_tmp{target.suffix}")
    if temp_target.exists():
        temp_target.unlink()
    command = [
        str(executable),
        "-y",
        "-i",
        str(source),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-movflags",
        "+faststart",
        str(temp_target),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=600,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or f"exit code {result.returncode}").strip().splitlines()
            reason = detail[-1] if detail else f"exit code {result.returncode}"
            raise RuntimeError(reason)
        if not temp_target.exists() or temp_target.stat().st_size <= 0:
            raise RuntimeError("output file is missing or empty")
        temp_target.replace(target)
        _emit_mp4_log(f"FFmpeg MP4 created: {target}", logger)
        return True
    except Exception as exc:  # noqa: BLE001
        _emit_mp4_log(f"FFmpeg MP4 failed, fallback to OpenCV: {exc}", logger, logging.WARNING)
        return False
    finally:
        if temp_target.exists():
            try:
                temp_target.unlink()
            except OSError:
                pass


def convert_avi_to_mp4_opencv(input_avi: str | Path, output_mp4: str | Path, logger=None) -> Path:
    if cv2 is None:
        raise RuntimeError("opencv-python is not installed.")

    source = Path(input_avi)
    target = Path(output_mp4)
    if not source.exists():
        raise FileNotFoundError(f"AVI file not found: {source}")

    target.parent.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open AVI file: {source}")

    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS)) or 15.0
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if width <= 0 or height <= 0:
            ok, frame = capture.read()
            if not ok or frame is None:
                raise RuntimeError(f"Could not read AVI file: {source}")
            height, width = frame.shape[:2]
            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)

        writer = cv2.VideoWriter(
            str(target),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height),
        )
        if not writer.isOpened():
            raise RuntimeError(f"Could not create MP4 file: {target}")
        try:
            while True:
                ok, frame = capture.read()
                if not ok or frame is None:
                    break
                writer.write(frame)
        finally:
            writer.release()
    finally:
        capture.release()

    if not target.exists() or target.stat().st_size <= 0:
        raise RuntimeError(f"MP4 conversion failed: {target}")
    _emit_mp4_log(f"OpenCV mp4v MP4 created: {target}", logger)
    return target


def convert_avi_to_mp4(input_avi: str | Path, output_mp4: str | Path, logger=None) -> Path:
    target = Path(output_mp4)
    ffmpeg_path = find_ffmpeg_executable(logger)
    if ffmpeg_path is not None and convert_avi_to_mp4_ffmpeg(input_avi, target, ffmpeg_path, logger):
        return target
    return convert_avi_to_mp4_opencv(input_avi, target, logger)


def get_free_disk_gb(path: str | Path) -> float:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    free_bytes = shutil.disk_usage(target).free
    return free_bytes / (1024 ** 3)


def has_min_free_disk_space(path: str | Path, min_free_disk_gb: float) -> bool:
    return get_free_disk_gb(path) >= float(min_free_disk_gb)


def should_auto_stop_recording(
    last_scan_time: float | None,
    now: float,
    enabled: bool,
    timeout_seconds: int | float,
    is_recording: bool,
) -> bool:
    if not enabled or not is_recording or last_scan_time is None:
        return False
    return now - last_scan_time >= float(timeout_seconds)


def cleanup_old_recordings(storage_path: str | Path, retention_days: int, logger=None) -> dict[str, int]:
    result = {"deleted_files": 0, "deleted_dirs": 0, "skipped": 0, "failed": 0}
    root = Path(storage_path)

    def emit(message: str, level: int = logging.INFO) -> None:
        logging.log(level, message)
        if logger is not None:
            try:
                logger(message)
            except Exception:  # noqa: BLE001
                logging.exception("Retention logger failed.")

    try:
        days = int(retention_days)
    except (TypeError, ValueError):
        days = 0

    emit(f"retention cleanup start: path={root}, days={days}")
    if days <= 0:
        emit("retention cleanup skipped: retention_days must be greater than 0")
        return result

    try:
        root.mkdir(parents=True, exist_ok=True)
        resolved_root = root.resolve()
    except OSError as exc:
        result["failed"] += 1
        emit(f"retention cleanup skipped: could not prepare storage path: {exc}", logging.WARNING)
        return result

    drive_root = Path(resolved_root.anchor) if resolved_root.anchor else None
    if drive_root is not None and resolved_root == drive_root:
        emit("retention cleanup skipped: storage path is a drive root", logging.WARNING)
        return result
    if any((resolved_root / name).exists() for name in ("src", "config", "backup", "dist")):
        emit("retention cleanup skipped: storage path looks like a project root", logging.WARNING)
        return result

    cutoff = time.time() - days * 24 * 60 * 60
    cleanup_dirs: list[Path] = []
    for current_dir, dirnames, filenames in os.walk(resolved_root, topdown=True, followlinks=False):
        current_path = Path(current_dir)
        kept_dirnames: list[str] = []
        for dirname in dirnames:
            child_dir = current_path / dirname
            if dirname.lower() in RETENTION_SKIP_DIRS or child_dir.is_symlink():
                result["skipped"] += 1
                continue
            kept_dirnames.append(dirname)
            cleanup_dirs.append(child_dir)
        dirnames[:] = kept_dirnames

        for filename in filenames:
            file_path = current_path / filename
            if file_path.suffix.lower() not in RETENTION_VIDEO_SUFFIXES or file_path.is_symlink():
                result["skipped"] += 1
                continue
            try:
                if file_path.stat().st_mtime >= cutoff:
                    result["skipped"] += 1
                    continue
                file_path.unlink()
                result["deleted_files"] += 1
            except OSError as exc:
                result["failed"] += 1
                emit(f"retention cleanup file delete failed: {file_path}: {exc}", logging.WARNING)

    for directory in sorted(cleanup_dirs, key=lambda item: len(item.parts), reverse=True):
        try:
            if directory.exists() and not any(directory.iterdir()):
                directory.rmdir()
                result["deleted_dirs"] += 1
        except OSError as exc:
            result["failed"] += 1
            emit(f"retention cleanup directory delete failed: {directory}: {exc}", logging.WARNING)

    emit(
        "retention cleanup done: "
        f"deleted_files={result['deleted_files']}, "
        f"deleted_dirs={result['deleted_dirs']}, "
        f"skipped={result['skipped']}, "
        f"failed={result['failed']}"
    )
    return result


class RecordingManager:
    def __init__(
        self,
        camera: CameraManager,
        storage_path: str | Path,
        fps: int,
        resolution: tuple[int, int],
        min_free_disk_gb: float = 5,
        watchdog_enabled: bool = True,
        watchdog_max_failures: int = 30,
        watchdog_retry_count: int = 3,
        watchdog_retry_interval: float = 2,
        watermark_position: str = "top_left",
        watermark_font_scale: float = 0.9,
        watermark_color: str = "#00FF00",
        watermark_opacity: float = 0.75,
        config=None,
        log_callback=None,
    ):
        self.camera = camera
        self.storage_path = Path(storage_path)
        self.fps = fps
        self.resolution = resolution
        self.min_free_disk_gb = float(min_free_disk_gb)
        self.watchdog_enabled = watchdog_enabled
        self.watchdog_max_failures = watchdog_max_failures
        self.watchdog_retry_count = watchdog_retry_count
        self.watchdog_retry_interval = watchdog_retry_interval
        self.watermark_position = watermark_position
        self.watermark_font_scale = float(watermark_font_scale)
        self.watermark_color = watermark_color
        self.watermark_opacity = max(0.0, min(1.0, float(watermark_opacity)))
        self.writer = None
        self.current_video_path: Path | None = None
        self.current_tracking_number: str | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._config = config
        self._log_callback = log_callback
        self._lock = threading.Lock()
        self.recording_start_monotonic: float | None = None
        self.writer_fps = float(max(self.fps, 1))
        self.written_frame_count = 0
        self.duplicated_frame_count = 0
        self.timeline_dropped_frame_count = 0
        self.received_new_frame_count = 0
        self.skipped_capture_frame_count = 0
        self.last_written_frame = None
        self.last_write_monotonic: float | None = None
        self.processing_seconds = 0.0
        self.processed_frame_count = 0
        self.writer_seconds = 0.0
        self.max_capture_age_seconds = 0.0
        self.max_writer_seconds = 0.0
        requested_codec = str(
            getattr(config, "recording_writer_codec", "MJPG")
        ).upper()
        self.writer_codec_requested = requested_codec if requested_codec in {"MJPG", "XVID"} else "MJPG"
        self.writer_codec_actual = "MJPG"

    def start_recording(self, tracking_number: str) -> Path:
        with self._lock:
            self._stop_recording_locked()

            if not has_min_free_disk_space(self.storage_path, self.min_free_disk_gb):
                print(LOW_DISK_BLOCKED_MESSAGE)
                logging.error(LOW_DISK_BLOCKED_MESSAGE)
                raise RuntimeError(LOW_DISK_BLOCKED_MESSAGE)

            if cv2 is None:
                raise RuntimeError("opencv-python is not installed.")
            if not self.camera.is_opened() and not self.camera.open():
                raise RuntimeError(self.camera.state.last_error or "Camera is not available.")

            self.resolution = self.camera.resolution
            measured_fps = float(getattr(self.camera, "measured_capture_fps", 0.0) or 0.0)
            requested_fps = float(max(self.fps, 1))
            self.writer_fps = (
                max(1.0, min(requested_fps, measured_fps * WRITER_FPS_HEADROOM))
                if measured_fps >= 0.5
                else requested_fps
            )
            self._emit_recording_log(
                "before_recording_dir_create: "
                f"tracking_number={tracking_number}, requested_resolution_fps="
                f"{self.resolution[0]}x{self.resolution[1]}/{requested_fps:.2f}"
            )
            video_path = build_video_path(self.storage_path, tracking_number)
            video_path.parent.mkdir(parents=True, exist_ok=True)
            self._emit_recording_log(f"after_recording_dir_create: path={video_path.parent}")

            resolution_policy = str(
                getattr(self._config, "resolution_policy", "config_first")
            )
            configured_resolution = str(
                getattr(self._config, "resolution", f"{self.resolution[0]}x{self.resolution[1]}")
            )
            configured_fps = float(getattr(self._config, "fps", requested_fps))
            self._emit_recording_log(f"recording_resolution_policy={resolution_policy}")
            self._emit_recording_log(f"configured_resolution={configured_resolution}")
            self._emit_recording_log(f"configured_fps={configured_fps:.0f}")
            self._emit_recording_log(
                f"writer_codec_requested={self.writer_codec_requested}"
            )
            self._emit_recording_log(
                "before_writer_open: "
                f"path={video_path}, writer_fps={self.writer_fps:.2f}, "
                f"writer_codec_requested={self.writer_codec_requested}"
            )
            writer = self._open_video_writer(video_path)
            self._emit_recording_log(
                "after_writer_open: "
                f"path={video_path}, writer_fps={self.writer_fps:.2f}, "
                f"writer_codec_actual={self.writer_codec_actual}, "
                "writer_open_success=TRUE, "
                f"writer_fps_source={'measured_capture_fps_x_0.95' if measured_fps >= 0.5 else 'requested_fps_fallback'}"
            )

            self._reset_recording_timing(reset_writer_fps=False)
            self.writer = writer
            self.current_video_path = video_path
            self.current_tracking_number = tracking_number
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._record_loop, name="stage1-recording", daemon=True)
            self._thread.start()
            self._emit_recording_log(
                "Recording started: "
                f"writer_fps={self.writer_fps:.2f}, "
                f"resolution={self.resolution}, "
                f"measured_capture_fps={measured_fps:.2f}, "
                f"camera_backend={getattr(self.camera, 'backend_name', 'UNKNOWN')}, "
                f"camera_input_fourcc={getattr(self.camera, 'actual_fourcc', 'UNKNOWN')}, "
                f"writer_codec={self.writer_codec_actual}, "
                f"requested_resolution_fps={configured_resolution}/{configured_fps:.2f}, "
                f"actual_resolution_fps={self.resolution[0]}x{self.resolution[1]}/"
                f"{float(getattr(self.camera, 'actual_fps', 0.0) or 0.0):.2f}, "
                f"path={video_path}"
            )
            return video_path

    def _open_video_writer(self, video_path: Path):
        codecs = [self.writer_codec_requested]
        if self.writer_codec_requested == "XVID":
            codecs.append("MJPG")
        for codec in codecs:
            writer = cv2.VideoWriter(
                str(video_path),
                cv2.VideoWriter_fourcc(*codec),
                self.writer_fps,
                self.resolution,
            )
            if writer.isOpened():
                self.writer_codec_actual = codec
                self._emit_recording_log(f"writer_codec_actual={codec}")
                if codec != self.writer_codec_requested:
                    self._emit_recording_log(
                        "writer_fallback_reason=xvid_writer_open_failed",
                        warning=True,
                    )
                return writer
            try:
                writer.release()
            except Exception:
                pass
        raise RuntimeError(
            f"Could not open video writer: {video_path}; "
            f"requested_codec={self.writer_codec_requested}"
        )

    def switch_segment(self, tracking_number: str) -> Path:
        logging.info("Switching recording segment: %s", tracking_number)
        return self.start_recording(tracking_number)

    def stop_recording(self) -> None:
        self._emit_recording_log("stop_recording begin")
        try:
            with self._lock:
                self._stop_recording_locked()
        except Exception as exc:  # noqa: BLE001
            self._emit_recording_log(f"Recording finalize failed: {exc}", warning=True)
        finally:
            self._emit_recording_log("stop_recording end")

    def _stop_recording_locked(self) -> None:
        self._stop_event.set()
        if (
            self._thread is not None
            and self._thread.is_alive()
            and threading.current_thread() is not self._thread
        ):
            try:
                self._thread.join(timeout=3)
                if self._thread.is_alive():
                    self._emit_recording_log(
                        "Recording thread join timed out; continuing guarded shutdown.",
                        warning=True,
                    )
            except Exception as exc:  # noqa: BLE001
                self._emit_recording_log(f"Recording thread join failed: {exc}", warning=True)
        self._thread = None
        self._release_writer()

    def _release_writer(self) -> None:
        writer = self.writer
        if writer is None:
            return
        try:
            self._finalize_recording_timing()
        except Exception as exc:  # noqa: BLE001
            self._emit_recording_log(f"Recording finalize failed: {exc}", warning=True)
        try:
            writer.release()
            logging.info("Recording stopped: %s", self.current_video_path)
        except Exception as exc:  # noqa: BLE001
            self._emit_recording_log(f"VideoWriter release failed: {exc}", warning=True)
        finally:
            self.writer = None

    def _emit_recording_log(self, message: str, warning: bool = False) -> None:
        if warning:
            logging.warning(message)
        else:
            logging.info(message)
        if self._log_callback is None:
            return
        try:
            self._log_callback(message)
        except Exception:  # noqa: BLE001
            return

    def _reset_recording_timing(self, reset_writer_fps: bool = True) -> None:
        self.recording_start_monotonic = None
        if reset_writer_fps:
            self.writer_fps = float(max(self.fps, 1))
        self.written_frame_count = 0
        self.duplicated_frame_count = 0
        self.timeline_dropped_frame_count = 0
        self.received_new_frame_count = 0
        self.skipped_capture_frame_count = 0
        self.last_written_frame = None
        self.last_write_monotonic = None
        self.processing_seconds = 0.0
        self.processed_frame_count = 0
        self.writer_seconds = 0.0
        self.max_capture_age_seconds = 0.0
        self.max_writer_seconds = 0.0

    def _write_timed_frame(self, frame, captured_at: float | None = None) -> None:
        if self.writer is None:
            return

        now = captured_at if captured_at is not None else time.monotonic()
        if self.recording_start_monotonic is None:
            self.recording_start_monotonic = now
            self.writer.write(frame)
            self.written_frame_count += 1
            self.last_written_frame = frame
            self.last_write_monotonic = now
            return

        elapsed = max(0.0, now - self.recording_start_monotonic)
        expected_count = int(elapsed * self.writer_fps)
        if expected_count < self.written_frame_count:
            self.timeline_dropped_frame_count += 1
            return
        need = expected_count - self.written_frame_count

        if need > 0 and self.last_written_frame is not None:
            max_duplicate_per_call = int(self.writer_fps * 2)
            duplicate_count = min(need, max_duplicate_per_call)
            if duplicate_count < need:
                logging.warning(
                    "frame duplication capped: need=%s, capped=%s",
                    need,
                    duplicate_count,
                )
            self._duplicate_last_frame(duplicate_count)

        if self.writer is not None:
            self.writer.write(frame)
            self.written_frame_count += 1
            self.last_written_frame = frame
            self.last_write_monotonic = now

    def _duplicate_last_frame(self, duplicate_count: int) -> None:
        if self.writer is None or self.last_written_frame is None or duplicate_count <= 0:
            return
        for _ in range(duplicate_count):
            self.writer.write(self.last_written_frame)
            self.written_frame_count += 1
            self.duplicated_frame_count += 1

    def _finalize_recording_timing(self) -> None:
        if self.recording_start_monotonic is None:
            estimated_play_duration = self.written_frame_count / self.writer_fps if self.writer_fps > 0 else 0.0
            self._emit_recording_log(
                "Recording finalized: "
                "wall_duration=0.00s, "
                f"writer_fps={self.writer_fps:.2f}, "
                f"written_frames={self.written_frame_count}, "
                f"duplicated_frames={self.duplicated_frame_count}, "
                "real_frames=0, "
                f"received_new_frames={self.received_new_frame_count}, "
                f"timeline_dropped_frames={self.timeline_dropped_frame_count}, "
                f"skipped_capture_frames={self.skipped_capture_frame_count}, "
                "duplicate_ratio=0.00%, "
                f"estimated_play_duration={estimated_play_duration:.2f}s, "
                f"measured_capture_fps={float(getattr(self.camera, 'measured_capture_fps', 0.0) or 0.0):.2f}, "
                f"camera_backend={getattr(self.camera, 'backend_name', 'UNKNOWN')}, "
                f"camera_input_fourcc={getattr(self.camera, 'actual_fourcc', 'UNKNOWN')}, "
                f"writer_codec={self.writer_codec_actual}, "
                "note=no_frames_written"
            )
            return

        final_elapsed = max(0.0, time.monotonic() - self.recording_start_monotonic)
        expected_final_count = int(final_elapsed * self.writer_fps)
        if self.last_written_frame is not None and self.written_frame_count < expected_final_count:
            missing_frames = expected_final_count - self.written_frame_count
            max_finalize_duplicates = max(1, int(self.writer_fps * 2))
            duplicate_count = min(missing_frames, max_finalize_duplicates)
            if duplicate_count < missing_frames:
                self._emit_recording_log(
                    "Final frame duplication capped to protect shutdown: "
                    f"missing={missing_frames}, capped={duplicate_count}",
                    warning=True,
                )
            self._duplicate_last_frame(duplicate_count)

        estimated_play_duration = self.written_frame_count / self.writer_fps if self.writer_fps > 0 else 0.0
        real_frames = max(0, self.written_frame_count - self.duplicated_frame_count)
        duplicate_ratio = (
            self.duplicated_frame_count / self.written_frame_count
            if self.written_frame_count > 0
            else 0.0
        )
        log_message = (
            "Recording finalized: "
            f"wall_duration={final_elapsed:.2f}s, "
            f"writer_fps={self.writer_fps:.2f}, "
            f"written_frames={self.written_frame_count}, "
            f"duplicated_frames={self.duplicated_frame_count}, "
            f"real_frames={real_frames}, "
            f"received_new_frames={self.received_new_frame_count}, "
            f"timeline_dropped_frames={self.timeline_dropped_frame_count}, "
            f"skipped_capture_frames={self.skipped_capture_frame_count}, "
            f"real_processing_fps={self.received_new_frame_count / max(final_elapsed, 0.001):.2f}, "
            f"processed_frames={self.processed_frame_count}, "
            f"avg_processing_ms={1000 * self.processing_seconds / max(self.processed_frame_count, 1):.1f}, "
            f"avg_writer_ms={1000 * self.writer_seconds / max(self.processed_frame_count, 1):.1f}, "
            f"max_writer_ms={1000 * self.max_writer_seconds:.1f}, "
            f"max_capture_age_ms={1000 * self.max_capture_age_seconds:.1f}, "
            f"duplicate_ratio={duplicate_ratio:.2%}, "
            f"estimated_play_duration={estimated_play_duration:.2f}s, "
            f"measured_capture_fps={float(getattr(self.camera, 'measured_capture_fps', 0.0) or 0.0):.2f}, "
            f"camera_backend={getattr(self.camera, 'backend_name', 'UNKNOWN')}, "
            f"camera_input_fourcc={getattr(self.camera, 'actual_fourcc', 'UNKNOWN')}, "
            f"writer_codec={self.writer_codec_actual}, "
            f"requested_resolution_fps={getattr(self.camera, 'requested_resolution', self.resolution)}"
            f"/{float(self.fps):.2f}, "
            f"actual_resolution_fps={getattr(self.camera, 'actual_resolution', self.resolution)}"
            f"/{float(getattr(self.camera, 'actual_fps', 0.0) or 0.0):.2f}"
        )
        self._emit_recording_log(log_message)
        if duplicate_ratio > 0.5:
            self._emit_recording_log(
                "WARNING: duplicate frame ratio high; recording may appear choppy.",
                warning=True,
            )
        if abs(estimated_play_duration - final_elapsed) > 1.0:
            self._emit_recording_log(
                "Recording duration mismatch: "
                f"wall_duration={final_elapsed:.2f}s, "
                f"estimated_play_duration={estimated_play_duration:.2f}s",
                warning=True,
            )

    def _record_loop(self) -> None:
        failure_count = 0
        last_disk_check = 0.0
        last_sequence: int | None = None

        try:
            while not self._stop_event.is_set():
                now = time.monotonic()
                if now - last_disk_check >= 1:
                    last_disk_check = now
                    if not has_min_free_disk_space(self.storage_path, self.min_free_disk_gb):
                        print(LOW_DISK_STOPPED_MESSAGE)
                        logging.error(LOW_DISK_STOPPED_MESSAGE)
                        self._stop_event.set()
                        break

                wait_sequence = last_sequence if last_sequence is not None else 0
                ok, frame, sequence, captured_at = self.camera.wait_for_new_frame(
                    wait_sequence, timeout=1.0
                )
                if ok and frame is not None and self.writer is not None:
                    processing_started = time.monotonic()
                    if captured_at is not None:
                        self.max_capture_age_seconds = max(
                            self.max_capture_age_seconds, processing_started - captured_at
                        )
                    if last_sequence is not None:
                        self.skipped_capture_frame_count += max(0, sequence - last_sequence - 1)
                    last_sequence = sequence
                    self.received_new_frame_count += 1
                    failure_count = 0
                    # Skip frames outside the output cadence before applying image
                    # processing. The writer checks again for direct callers.
                    if (
                        captured_at is not None
                        and self.recording_start_monotonic is not None
                        and int(max(0.0, captured_at - self.recording_start_monotonic) * self.writer_fps)
                        < self.written_frame_count
                    ):
                        self.timeline_dropped_frame_count += 1
                        continue
                    self.processed_frame_count += 1
                    frame = self._apply_camera_calibration(frame)
                    frame = self.apply_watermark(frame, self.current_tracking_number or "")
                    writer_started = time.monotonic()
                    self.processing_seconds += writer_started - processing_started
                    write_error: Exception | None = None
                    for attempt in range(1, WRITE_FRAME_MAX_RETRIES + 1):
                        try:
                            self._write_timed_frame(frame, captured_at)
                            write_error = None
                            break
                        except Exception as exc:  # noqa: BLE001
                            write_error = exc
                            self._emit_recording_log(
                                "Frame write failed "
                                f"(attempt {attempt}/{WRITE_FRAME_MAX_RETRIES}): {exc}",
                                warning=True,
                            )
                            if attempt < WRITE_FRAME_MAX_RETRIES:
                                time.sleep(WRITE_FRAME_RETRY_INTERVAL_SECONDS)
                    writer_elapsed = time.monotonic() - writer_started
                    self.writer_seconds += writer_elapsed
                    self.max_writer_seconds = max(self.max_writer_seconds, writer_elapsed)
                    if write_error is not None:
                        self._emit_recording_log(
                            "Frame write retries exhausted; ending recording segment.",
                            warning=True,
                        )
                        self._stop_event.set()
                        break
                    continue

                failure_count += 1
                logging.warning("Camera frame read failed, consecutive_failures=%s", failure_count)
                if self.watchdog_enabled and failure_count > self.watchdog_max_failures:
                    self._handle_watchdog_failure()
                    failure_count = 0
                time.sleep(0.1)
        except Exception as exc:  # noqa: BLE001
            self._emit_recording_log(
                f"Recording loop aborted by unexpected error: {exc}",
                warning=True,
            )
        finally:
            self._release_writer()

    def _handle_watchdog_failure(self) -> None:
        self._release_writer()
        self.camera.release_capture_only()

        for attempt in range(1, self.watchdog_retry_count + 1):
            logging.warning("Camera watchdog reconnect attempt %s/%s", attempt, self.watchdog_retry_count)
            time.sleep(self.watchdog_retry_interval)
            if self.camera.open():
                self._emit_recording_log(WATCHDOG_RECONNECTED_MESSAGE)
                if not self._resume_recording_after_reconnect():
                    self._emit_recording_log(WATCHDOG_RECORDING_STOPPED_MESSAGE, warning=True)
                    self._stop_event.set()
                return

        self._emit_recording_log(WATCHDOG_FAILED_MESSAGE, warning=True)
        self._emit_recording_log(WATCHDOG_RECORDING_STOPPED_MESSAGE, warning=True)
        self._stop_event.set()

    def _resume_recording_after_reconnect(self) -> bool:
        tracking_number = self.current_tracking_number
        if not tracking_number:
            return False
        resume_path = build_video_path(self.storage_path, tracking_number)
        camera_resolution = getattr(self.camera, "resolution", None)
        if isinstance(camera_resolution, (tuple, list)) and len(camera_resolution) == 2:
            self.resolution = (int(camera_resolution[0]), int(camera_resolution[1]))
        try:
            resume_path.parent.mkdir(parents=True, exist_ok=True)
            if resume_path.exists() or resume_path == self.current_video_path:
                base = resume_path.with_name(f"{resume_path.stem}_resume")
                candidate = base.with_suffix(resume_path.suffix)
                index = 1
                while (candidate.exists() or candidate == self.current_video_path) and index <= 99:
                    candidate = base.with_name(f"{base.name}_{index}").with_suffix(resume_path.suffix)
                    index += 1
                resume_path = candidate
            writer = self._open_video_writer(resume_path)
        except Exception as exc:  # noqa: BLE001
            self._emit_recording_log(
                f"Recording resume after camera watchdog reconnect failed: {exc}",
                warning=True,
            )
            return False
        self._reset_recording_timing(reset_writer_fps=False)
        self.writer = writer
        self.current_video_path = resume_path
        self._emit_recording_log(
            "Recording resumed after camera watchdog reconnect: "
            f"path={resume_path}, writer_fps={self.writer_fps:.2f}, "
            f"writer_codec={self.writer_codec_actual}"
        )
        return True

    def is_recording(self) -> bool:
        return self.writer is not None and self._thread is not None and self._thread.is_alive()

    def get_status(self) -> dict[str, str | bool | None]:
        return {
            "recording": self.is_recording(),
            "tracking_number": self.current_tracking_number,
            "video_path": str(self.current_video_path) if self.current_video_path else None,
        }

    def _apply_camera_calibration(self, frame):
        """对帧应用摄像头矫正（亮度/对比度/ROI裁切）"""
        if self._config is None or cv2 is None:
            return frame
        if not getattr(self._config, "camera_calibration_enabled", False):
            return frame
        alpha = 1.0 + getattr(self._config, "camera_calibration_contrast", 0) / 100.0
        beta = float(getattr(self._config, "camera_calibration_brightness", 0))
        if alpha != 1.0 or beta != 0.0:
            frame = cv2.convertScaleAbs(frame, alpha=alpha, beta=beta)
        if getattr(self._config, "camera_calibration_roi_enabled", False):
            roi_x = int(getattr(self._config, "camera_calibration_roi_x", 0))
            roi_y = int(getattr(self._config, "camera_calibration_roi_y", 0))
            roi_w = int(getattr(self._config, "camera_calibration_roi_w", 0))
            roi_h = int(getattr(self._config, "camera_calibration_roi_h", 0))
            h, w = frame.shape[:2]
            if (roi_x >= 0 and roi_y >= 0 and roi_w > 0 and roi_h > 0
                    and roi_x + roi_w <= w and roi_y + roi_h <= h):
                frame = frame[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]
                # VideoWriter requires the dimensions chosen when it was opened.
                frame = cv2.resize(frame, self.resolution, interpolation=cv2.INTER_LINEAR)
        return frame

    def apply_watermark(self, frame, tracking_number: str):
        if cv2 is None:
            return frame

        now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [tracking_number or "UNKNOWN", now_text]
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = max(0.3, float(self.watermark_font_scale))
        thickness = max(1, int(round(font_scale * 2)))
        outline_thickness = thickness + 2
        line_gap = max(8, int(12 * font_scale))
        margin = max(16, int(24 * font_scale))
        color = self._parse_watermark_color(self.watermark_color)

        sizes = [cv2.getTextSize(line, font, font_scale, thickness)[0] for line in lines]
        block_width = max(width for width, _height in sizes)
        block_height = sum(height for _width, height in sizes) + line_gap * (len(lines) - 1)
        x, y = self._watermark_origin(frame.shape[1], frame.shape[0], block_width, block_height, margin)

        # Blend only the text area instead of copying and blending the full video frame.
        padding = outline_thickness + 2
        x0 = max(0, x - padding)
        y0 = max(0, y - padding)
        x1 = min(frame.shape[1], x + block_width + padding)
        y1 = min(frame.shape[0], y + block_height + padding)
        target = frame[y0:y1, x0:x1]
        overlay = target.copy()

        current_y = y
        for index, line in enumerate(lines):
            text_width, text_height = sizes[index]
            baseline_y = current_y + text_height
            cv2.putText(
                overlay,
                line,
                (x - x0, baseline_y - y0),
                font,
                font_scale,
                (0, 0, 0),
                outline_thickness,
                cv2.LINE_AA,
            )
            cv2.putText(
                overlay,
                line,
                (x - x0, baseline_y - y0),
                font,
                font_scale,
                color,
                thickness,
                cv2.LINE_AA,
            )
            current_y += text_height + line_gap

        cv2.addWeighted(
            overlay,
            self.watermark_opacity,
            target,
            1 - self.watermark_opacity,
            0,
            dst=target,
        )
        return frame

    def _watermark_origin(
        self,
        frame_width: int,
        frame_height: int,
        block_width: int,
        block_height: int,
        margin: int,
    ) -> tuple[int, int]:
        position = self.watermark_position
        if position == "top_right":
            return max(margin, frame_width - block_width - margin), margin
        if position == "bottom_left":
            return margin, max(margin, frame_height - block_height - margin)
        if position == "bottom_right":
            return (
                max(margin, frame_width - block_width - margin),
                max(margin, frame_height - block_height - margin),
            )
        return margin, margin

    def _parse_watermark_color(self, value: str) -> tuple[int, int, int]:
        text = (value or "").strip()
        if text.startswith("#") and len(text) == 7:
            try:
                red = int(text[1:3], 16)
                green = int(text[3:5], 16)
                blue = int(text[5:7], 16)
                return blue, green, red
            except ValueError:
                pass
        return 0, 255, 0
