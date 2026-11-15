from __future__ import annotations

import json
import logging
import os
import secrets
import shutil
import sys
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
EXAMPLE_CONFIG = CONFIG_DIR / "config.example.json"
RUNTIME_CONFIG = CONFIG_DIR / "config.json"
DEFAULT_STORAGE_PATH = "recordings"


@dataclass(frozen=True)
class AppConfig:
    camera_index: int
    resolution: str
    fps: int
    storage_path: str
    segment_duration: int
    segment_on_barcode: bool
    auto_stop_enabled: bool
    auto_stop_timeout: int
    keep_camera_on_timeout: bool
    retention_days: int
    enable_scanner: bool
    disable_duplicate_scan: bool
    duplicate_policy: str
    duplicate_block_seconds: int
    beep_enabled: bool
    excel_file: str
    license_file: str
    min_free_disk_gb: float
    watchdog_enabled: bool
    watchdog_max_failures: int
    watchdog_retry_count: int
    watchdog_retry_interval: float
    camera_backend: str = "DirectShow"
    camera_fourcc_preference: str = "MJPG"
    resolution_policy: str = "config_first"
    recording_writer_codec: str = "MJPG"
    enable_lens_correction: bool = False
    mp4_output_folder: str = "MP4"
    query_default_source: str = ""
    query_default_start_date: str = ""
    query_default_end_date: str = ""
    watermark_position: str = "top_left"
    watermark_font_scale: float = 0.9
    watermark_color: str = "#00FF00"
    watermark_opacity: float = 0.75
    generate_mp4_on_query: bool = False
    frame_idle_detection_enabled: bool = True
    frame_idle_timeout: int = 5
    frame_motion_threshold: float = 3.0
    camera_calibration_enabled: bool = True
    camera_calibration_brightness: int = 0
    camera_calibration_contrast: int = 0
    camera_calibration_roi_enabled: bool = False
    camera_calibration_roi_x: int = 0
    camera_calibration_roi_y: int = 0
    camera_calibration_roi_w: int = 0
    camera_calibration_roi_h: int = 0
    camera_focus_enabled: bool = False
    camera_focus_value: int = 0
    camera_autofocus_enabled: bool = True
    barcode_scan_enabled: bool = False
    enable_camera_barcode_scanner: bool = False
    barcode_roi_guide_enabled: bool = True
    barcode_roi_use_guide_area: bool = True
    barcode_label_width_mm: int = 76
    barcode_label_height_mm: int = 130
    barcode_roi_scale: float = 1.25
    barcode_roi_center_x_ratio: float = 0.50
    barcode_roi_center_y_ratio: float = 0.50
    barcode_roi_color: str = "#FF0000"
    barcode_roi_thickness: int = 2
    barcode_roi_dash_length: int = 16
    barcode_roi_gap_length: int = 10
    barcode_scan_interval_ms: int = 300
    barcode_scan_debounce_seconds: int = 5
    watermark_enabled: bool = True
    watermark_text: str = ""
    auto_trial_enabled: bool = True
    auto_trial_days: int = 30
    lan_query_enabled: bool = False
    lan_query_host: str = "0.0.0.0"
    lan_query_port: int = 18080
    lan_query_token: str = ""
    lan_query_readonly: bool = True
    voice_enabled: bool = False
    voice_on_scan_success: bool = True
    voice_on_record_start: bool = True
    voice_on_record_stop: bool = True
    voice_on_invalid_tracking: bool = True
    voice_on_auth_problem: bool = True
    shared_storage_enabled: bool = False
    shared_storage_path: str = ""
    shared_storage_copy_after_recording: bool = True
    shared_storage_copy_avi: bool = True
    shared_storage_copy_mp4: bool = True
    shared_storage_copy_label_image: bool = True
    shared_storage_fallback_local: bool = True

    @property
    def resolution_size(self) -> tuple[int, int]:
        width, height = self.resolution.lower().split("x", 1)
        return int(width), int(height)

    @property
    def excel_path(self) -> Path:
        return resolve_project_path(self.excel_file)

    @property
    def license_path(self) -> Path:
        return resolve_project_path(self.license_file)


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT


def resolve_storage_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (runtime_root() / path).resolve()


def is_legacy_default_storage_path(value: Any) -> bool:
    normalized = str(value or "").strip().replace("\\", "/").rstrip("/").lower()
    return normalized == "c:/fhjk260227"


def ensure_config(config_path: Path = RUNTIME_CONFIG, example_path: Path = EXAMPLE_CONFIG) -> Path:
    if not example_path.exists():
        raise FileNotFoundError(f"Missing example config: {example_path}")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        shutil.copy2(example_path, config_path)
        logging.info("Created runtime config from example: %s", config_path)
        return config_path

    added = merge_missing_config_fields(config_path, example_path)
    if added:
        logging.info("Added missing config fields to %s: %s", config_path, ", ".join(added))
    return config_path


def merge_missing_config_fields(config_path: Path, example_path: Path = EXAMPLE_CONFIG) -> list[str]:
    with example_path.open("r", encoding="utf-8") as handle:
        defaults: dict[str, Any] = json.load(handle)
    with config_path.open("r", encoding="utf-8") as handle:
        current: dict[str, Any] = json.load(handle)

    added: list[str] = []
    if "duplicate_policy" not in current:
        if current.get("disable_duplicate_scan") is True:
            current["duplicate_policy"] = "block_within_seconds"
        elif current.get("disable_duplicate_scan") is False:
            current["duplicate_policy"] = "allow"
        else:
            current["duplicate_policy"] = defaults.get("duplicate_policy", "block_completed_only")
        added.append("duplicate_policy")

    for key, value in defaults.items():
        if key not in current:
            current[key] = value
            added.append(key)

    if is_legacy_default_storage_path(current.get("storage_path")):
        current["storage_path"] = DEFAULT_STORAGE_PATH
        added.append("storage_path_migrated")

    if added:
        with config_path.open("w", encoding="utf-8") as handle:
            json.dump(current, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    return added


def get_config(config_path: Path = RUNTIME_CONFIG, example_path: Path = EXAMPLE_CONFIG) -> AppConfig:
    config_path = ensure_config(config_path, example_path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = json.load(handle)
    raw.setdefault("storage_path", DEFAULT_STORAGE_PATH)
    raw.setdefault("enable_lens_correction", False)
    raw.setdefault("camera_backend", "DirectShow")
    raw.setdefault("camera_fourcc_preference", "MJPG")
    raw.setdefault("resolution_policy", "config_first")
    raw.setdefault("recording_writer_codec", "MJPG")
    if str(raw["resolution_policy"]).lower() not in {
        "config_first",
        "auto_best",
        "smooth_first",
    }:
        raw["resolution_policy"] = "config_first"
    else:
        raw["resolution_policy"] = str(raw["resolution_policy"]).lower()
    if str(raw["recording_writer_codec"]).upper() not in {"MJPG", "XVID"}:
        raw["recording_writer_codec"] = "MJPG"
    else:
        raw["recording_writer_codec"] = str(raw["recording_writer_codec"]).upper()
    raw.setdefault("mp4_output_folder", "MP4")
    raw.setdefault("query_default_source", "")
    raw.setdefault("query_default_start_date", "")
    raw.setdefault("query_default_end_date", "")
    raw.setdefault("watermark_position", "top_left")
    raw.setdefault("watermark_font_scale", 0.9)
    raw.setdefault("watermark_color", "#00FF00")
    raw.setdefault("watermark_opacity", 0.75)
    raw.setdefault("generate_mp4_on_query", False)
    raw.setdefault("frame_idle_detection_enabled", True)
    raw.setdefault("frame_idle_timeout", 5)
    raw.setdefault("frame_motion_threshold", 3.0)
    raw.setdefault("camera_calibration_enabled", True)
    raw.setdefault("camera_calibration_brightness", 0)
    raw.setdefault("camera_calibration_contrast", 0)
    raw.setdefault("camera_calibration_roi_enabled", False)
    raw.setdefault("camera_calibration_roi_x", 0)
    raw.setdefault("camera_calibration_roi_y", 0)
    raw.setdefault("camera_calibration_roi_w", 0)
    raw.setdefault("camera_calibration_roi_h", 0)
    raw.setdefault("camera_focus_enabled", False)
    raw.setdefault("camera_focus_value", 0)
    raw.setdefault("camera_autofocus_enabled", True)
    if bool(raw["camera_autofocus_enabled"]):
        raw["camera_focus_enabled"] = False
    raw["camera_focus_value"] = max(0, min(255, int(raw["camera_focus_value"])))
    raw["camera_calibration_brightness"] = max(
        -50, min(50, int(raw["camera_calibration_brightness"]))
    )
    raw["camera_calibration_contrast"] = max(
        -50, min(50, int(raw["camera_calibration_contrast"]))
    )
    raw.setdefault("barcode_scan_enabled", False)
    raw.setdefault("watermark_enabled", True)
    raw.setdefault("watermark_text", "")
    raw.setdefault("auto_trial_enabled", True)
    raw.setdefault("auto_trial_days", 30)
    raw.setdefault("lan_query_enabled", False)
    raw.setdefault("lan_query_host", "0.0.0.0")
    raw.setdefault("lan_query_port", 18080)
    raw.setdefault("lan_query_token", "")
    raw.setdefault("lan_query_readonly", True)
    raw.setdefault("voice_enabled", False)
    raw.setdefault("voice_on_scan_success", True)
    raw.setdefault("voice_on_record_start", True)
    raw.setdefault("voice_on_record_stop", True)
    raw.setdefault("voice_on_invalid_tracking", True)
    raw.setdefault("voice_on_auth_problem", True)
    raw.setdefault("shared_storage_enabled", False)
    raw.setdefault("shared_storage_path", "")
    raw.setdefault("shared_storage_copy_after_recording", True)
    raw.setdefault("shared_storage_copy_avi", True)
    raw.setdefault("shared_storage_copy_mp4", True)
    raw.setdefault("shared_storage_copy_label_image", True)
    raw.setdefault("shared_storage_fallback_local", True)
    # Barcode ROI guide settings
    raw.setdefault("enable_camera_barcode_scanner", False)
    raw.setdefault("barcode_roi_guide_enabled", True)
    raw.setdefault("barcode_roi_use_guide_area", True)
    raw.setdefault("barcode_label_width_mm", 76)
    raw.setdefault("barcode_label_height_mm", 130)
    raw.setdefault("barcode_roi_scale", 1.25)
    raw.setdefault("barcode_roi_center_x_ratio", 0.50)
    raw.setdefault("barcode_roi_center_y_ratio", 0.50)
    raw.setdefault("barcode_roi_color", "#FF0000")
    raw.setdefault("barcode_roi_thickness", 2)
    raw.setdefault("barcode_roi_dash_length", 16)
    raw.setdefault("barcode_roi_gap_length", 10)
    raw.setdefault("barcode_scan_interval_ms", 300)
    raw.setdefault("barcode_scan_debounce_seconds", 5)
    valid_keys = {f.name for f in fields(AppConfig)}
    filtered = {k: v for k, v in raw.items() if k in valid_keys}
    return AppConfig(**filtered)


def ensure_lan_query_token(config_path: Path = RUNTIME_CONFIG) -> str:
    ensure_config(config_path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = json.load(handle)
    token = str(raw.get("lan_query_token", "")).strip()
    if token:
        return token

    token = secrets.token_urlsafe(24)
    raw["lan_query_token"] = token
    temporary = config_path.with_name(f"{config_path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(raw, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, config_path)
    return token


def validate_license(license_path: Path) -> tuple[bool, str]:
    if not license_path.exists():
        return False, f"License file not found: {license_path}"

    try:
        with license_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        return False, f"License file is not valid JSON: {exc}"
    except OSError as exc:
        return False, f"Could not read license file: {exc}"

    required = ("machine_code", "license_key", "activation_date")
    missing = [field for field in required if not str(data.get(field, "")).strip()]
    if missing:
        return False, "License file is missing required fields: " + ", ".join(missing)

    return True, "License file passed basic local validation."
