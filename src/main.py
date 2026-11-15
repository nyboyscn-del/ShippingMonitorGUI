from __future__ import annotations

import logging
import os
import shutil
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

from barcode_listener import BarcodeListener, print_status_with_prompt
from camera_manager import CameraManager
from config_manager import PROJECT_ROOT, get_config, validate_license
from excel_manager import ExcelManager
from recording_manager import RecordingManager, should_auto_stop_recording


AUTO_STOP_MESSAGE = "Auto stop recording after idle timeout."


def setup_logging() -> None:
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "stage1_runtime.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def ensure_runtime_dirs(config) -> None:
    PROJECT_ROOT.joinpath("data").mkdir(parents=True, exist_ok=True)
    PROJECT_ROOT.joinpath("logs").mkdir(parents=True, exist_ok=True)
    config.excel_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        os.makedirs(config.storage_path, exist_ok=True)
        total, used, free = shutil.disk_usage(config.storage_path)
        free_gb = free / (1024 ** 3)
        logging.info("Storage path ready: %s, free space %.2f GB", config.storage_path, free_gb)
        if free_gb < config.min_free_disk_gb:
            warning = (
                f"Warning: storage path {config.storage_path} has only {free_gb:.2f} GB free. "
                f"Minimum configured free space is {config.min_free_disk_gb:.2f} GB."
            )
            print(warning)
            logging.warning(warning)
    except OSError as exc:
        logging.warning("Could not prepare or inspect storage path %s: %s", config.storage_path, exc)


def start_auto_stop_monitor(config, recorder: RecordingManager, camera: CameraManager):
    stop_event = threading.Event()
    state = {"last_scan_time": None}

    def mark_scan() -> None:
        state["last_scan_time"] = time.monotonic()

    def monitor() -> None:
        while not stop_event.is_set():
            if should_auto_stop_recording(
                state["last_scan_time"],
                time.monotonic(),
                config.auto_stop_enabled,
                config.auto_stop_timeout,
                recorder.is_recording(),
            ):
                print_status_with_prompt(AUTO_STOP_MESSAGE)
                logging.info(AUTO_STOP_MESSAGE)
                recorder.stop_recording()
                state["last_scan_time"] = None
                if not config.keep_camera_on_timeout:
                    camera.release_capture_only()
            stop_event.wait(1)

    thread = threading.Thread(target=monitor, name="stage1-auto-stop", daemon=True)
    thread.start()
    return mark_scan, stop_event, thread


def main() -> int:
    setup_logging()
    logging.info("Stage1 shipping monitor starting.")

    try:
        config = get_config()
    except Exception as exc:
        logging.exception("Could not load config.")
        print(f"Config load failed: {exc}")
        return 1

    ensure_runtime_dirs(config)

    license_ok, license_message = validate_license(config.license_path)
    if not license_ok:
        logging.error(license_message)
        print(f"License validation failed: {license_message}")
        print("Please place a valid license.json in the config directory and retry.")
        return 1
    logging.info(license_message)

    try:
        excel = ExcelManager(config.excel_path)
    except Exception as exc:
        logging.exception("Could not initialize Excel file.")
        print(f"Excel initialization failed: {exc}")
        return 1

    camera = CameraManager(config.camera_index, config.resolution_size, config.fps, config.storage_path)
    if not camera.open():
        print(f"Camera start failed: {camera.state.last_error}")
        return 1

    recorder = RecordingManager(
        camera,
        config.storage_path,
        config.fps,
        camera.resolution,
        min_free_disk_gb=config.min_free_disk_gb,
        watchdog_enabled=config.watchdog_enabled,
        watchdog_max_failures=config.watchdog_max_failures,
        watchdog_retry_count=config.watchdog_retry_count,
        watchdog_retry_interval=config.watchdog_retry_interval,
    )
    listener = BarcodeListener(disable_duplicate_scan=config.disable_duplicate_scan)
    mark_scan, auto_stop_event, auto_stop_thread = start_auto_stop_monitor(config, recorder, camera)

    def on_barcode(tracking_number: str, source: str) -> None:
        try:
            mark_scan()
            video_path = recorder.switch_segment(tracking_number)
            excel.append_record(tracking_number, video_path, source=source)
            print(f"Recorded: {tracking_number} -> {video_path}")
            logging.info("Processed tracking number: %s", tracking_number)
        except Exception as exc:
            logging.exception("Failed to process tracking number: %s", tracking_number)
            print(f"Failed to process tracking number {tracking_number}: {exc}")

    try:
        if config.enable_scanner:
            listener.listen_forever(on_barcode)
        else:
            print("Scanner listener is disabled in config.")
    except KeyboardInterrupt:
        print("\nExit requested. Closing recorder and camera safely...")
        logging.info("Interrupted by user.")
    finally:
        auto_stop_event.set()
        auto_stop_thread.join(timeout=2)
        recorder.stop_recording()
        camera.release()
        logging.info("Stage1 shipping monitor stopped.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
