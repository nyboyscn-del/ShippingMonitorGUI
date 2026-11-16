from __future__ import annotations

import os
import importlib.util
import hashlib
import json
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import platform

if platform.system() == "Windows":
    import winsound
else:
    winsound = None

from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QDate, QRect, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QImage, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QAction,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QAbstractItemView,
    QHeaderView,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QColorDialog,
)

from camera_manager import (
    CameraManager,
    cv2,
    probe_available_cameras,
    validate_camera_candidate,
)
from config_manager import (
    EXAMPLE_CONFIG,
    RUNTIME_CONFIG,
    ensure_lan_query_token,
    get_config,
    resolve_storage_path,
    runtime_root,
)

try:
    from dialogs.camera_calibration_dialog import CameraCalibrationDialog as CameraCalibrationSettingsDialog
except Exception:  # noqa: BLE001
    CameraCalibrationSettingsDialog = None
from excel_manager import ExcelManager
from erp_manager import ERPManager
from playback_manager import PlaybackManager
from query_manager import (
    QueryManager,
    get_invalid_tracking_reason,
    is_valid_tracking_number,
    normalize_tracking_number,
)
from lan_query_server import LanQueryServer, mask_token
from recording_manager import (
    LOW_DISK_BLOCKED_MESSAGE,
    RecordingManager,
    cleanup_old_recordings,
    convert_avi_to_mp4,
    find_ffmpeg_executable,
    has_min_free_disk_space,
)
from barcode_scanner import BarcodeScanner
from license_code_manager import (
    activate_with_code,
    extract_authorization_code,
    format_machine_code,
    get_license_status,
    get_machine_code,
    is_recording_allowed,
)
from version import __project_name__, __version__, __build__, __copyright__, release_channel


DEFAULT_RECORDINGS_DIR = resolve_storage_path("recordings")
PREVIEW_INTERVAL_MS = 33
RESOLUTION_OPTIONS = ["3840x2160", "2560x1440", "1920x1080", "1600x900", "1280x720"]
WATERMARK_POSITIONS = [
    ("\u5de6\u4e0a", "top_left"),
    ("\u53f3\u4e0a", "top_right"),
    ("\u5de6\u4e0b", "bottom_left"),
    ("\u53f3\u4e0b", "bottom_right"),
]
SHARED_STORAGE_ALLOWED_EXTENSIONS = {".avi", ".mp4", ".jpg"}
CAMERA_QUALITY_PROBE_VERSION = 2
SHARED_STORAGE_FORBIDDEN_PARTS = {
    "backup",
    "config",
    "dist",
    "license_keys",
    "release",
    "src",
    "tools",
}
SUPPORT_WECHAT = "izch-claw"
SUPPORT_EMAIL = "izchclaw@qq.com"
SUPPORT_LICENSE_HINT = (
    "请复制本机机器码发送给供应商获取授权码。\n"
    f"售后微信：{SUPPORT_WECHAT}\n"
    f"售后邮箱：{SUPPORT_EMAIL}"
)


def test_shared_storage_writable(path_text: str) -> tuple[bool, str]:
    value = str(path_text or "").strip()
    if not value:
        return False, "\u5171\u4eab\u5b58\u50a8\u8def\u5f84\u4e3a\u7a7a"
    path = Path(value)
    if ".." in path.parts:
        return False, "\u5171\u4eab\u5b58\u50a8\u8def\u5f84\u4e0d\u80fd\u5305\u542b .."
    if not path.is_dir():
        return False, "\u5171\u4eab\u5b58\u50a8\u8def\u5f84\u4e0d\u5b58\u5728\u6216\u4e0d\u53ef\u8bbf\u95ee"

    test_file = path / f".shipping_monitor_write_test_{os.getpid()}_{time.time_ns()}.tmp"
    try:
        test_file.write_text("write-test", encoding="utf-8")
        test_file.unlink()
        return True, "\u5171\u4eab\u5b58\u50a8\u8def\u5f84\u53ef\u5199"
    except OSError as exc:
        try:
            test_file.unlink(missing_ok=True)
        except OSError:
            pass
        return False, f"\u5171\u4eab\u5b58\u50a8\u8def\u5f84\u4e0d\u53ef\u5199\uff1a{exc}"


TEXT = {
    "title": f"\u53d1\u8d27\u76d1\u63a7\u7cfb\u7edf - {release_channel}",
    "preview_placeholder": "\u6444\u50cf\u5934\u9884\u89c8\u533a\uff0c\u70b9\u51fb\u5f00\u59cb\u540e\u663e\u793a\u753b\u9762\u3002",
    "log_placeholder": "\u663e\u793a\u6700\u8fd1\u4e8b\u4ef6",
    "status_panel": "\u72b6\u6001\u9762\u677f",
    "scan_panel": "扫码输入（一定先切换到英文状态）",
    "actions": "\u64cd\u4f5c",
    "recent_tracking_panel": "\u6700\u8fd1\u5355\u53f7",
    "current_tracking": "\u5f53\u524d\u5355\u53f7\uff1a",
    "recording_status": "\u5f55\u50cf\u72b6\u6001\uff1a",
    "excel_status": "Excel \u72b6\u6001\uff1a",
    "disk_status": "\u78c1\u76d8\u7a7a\u95f4\uff1a",
    "camera_status": "\u6444\u50cf\u5934\u72b6\u6001\uff1a",
    "license_status": "\u6388\u6743\u72b6\u6001\uff1a",
    "storage_path": "\u5b58\u50a8\u8def\u5f84\uff1a",
    "auto_stop_status": "\u81ea\u52a8\u505c\u6b62\uff1a",
    "idle_countdown": "\u7a7a\u95f2\u5012\u8ba1\u65f6\uff1a",
    "watchdog_status": "Watchdog\uff1a",
    "frame_failures": "\u8fde\u7eed\u8bfb\u5e27\u5931\u8d25\uff1a",
    "min_disk": "\u78c1\u76d8\u6700\u4f4e\u8981\u6c42\uff1a",
    "duplicate_policy_status": "\u91cd\u590d\u7b56\u7565\uff1a",
    "configured_resolution_fps": "\u914d\u7f6e\u5206\u8fa8\u7387 / FPS\uff1a",
    "actual_resolution": "\u5b9e\u9645\u5206\u8fa8\u7387\uff1a",
    "actual_fps": "\u5b9e\u9645 FPS\uff1a",
    "actual_resolution_fps": "\u5b9e\u9645\u5206\u8fa8\u7387 / FPS\uff1a",
    "frame_motion_status": "\u753b\u9762\u72b6\u6001\uff1a",
    "lens_correction": "Lens Correction\uff1a",
    "not_scanned": "\u672a\u626b\u63cf",
    "not_started": "\u672a\u542f\u52a8",
    "not_written": "\u672a\u5199\u5165",
    "not_checked": "\u672a\u68c0\u6d4b",
    "not_verified": "\u672a\u6821\u9a8c",
    "not_loaded": "\u672a\u8bfb\u53d6",
    "previewing": "\u9884\u89c8\u4e2d",
    "start_failed": "\u542f\u52a8\u5931\u8d25",
    "stopped": "\u5df2\u505c\u6b62",
    "not_recording": "\u672a\u5f55\u50cf",
    "license_ok": "\u5df2\u901a\u8fc7\u57fa\u7840\u6821\u9a8c",
    "license_failed": "\u5931\u8d25",
    "disk_low": "\u78c1\u76d8\u7a7a\u95f4\u4e0d\u8db3",
    "disk_failed": "\u68c0\u6d4b\u5931\u8d25",
    "config_failed": "\u914d\u7f6e\u8bfb\u53d6\u5931\u8d25",
    "input_placeholder": "\u8bf7\u626b\u63cf\u6216\u8f93\u5165\u7269\u6d41\u5355\u53f7\u540e\u56de\u8f66",
    "start": "\u5f00\u59cb",
    "stop_preview": "\u505c\u6b62\u9884\u89c8",
    "open_config": "\u6253\u5f00\u914d\u7f6e",
    "open_query": "\u67e5\u8be2\u8bb0\u5f55",
    "open_recordings": "\u6253\u5f00\u5f55\u50cf\u76ee\u5f55",
    "exit": "\u9000\u51fa",
    "config_title": "\u914d\u7f6e",
    "config_later": "\u914d\u7f6e\u529f\u80fd\u5c06\u5728\u540e\u7eed\u7248\u672c\u63a5\u5165",
    "license_fail_title": "\u6388\u6743\u6821\u9a8c\u5931\u8d25",
    "recordings_missing_title": "\u5f55\u50cf\u76ee\u5f55\u4e0d\u5b58\u5728",
    "camera_fail_title": "\u6444\u50cf\u5934\u542f\u52a8\u5931\u8d25",
    "accepted_not_recording": "\u5df2\u63a5\u6536\uff0c\u672a\u5f55\u50cf",
    "recording": "\u5f55\u50cf\u4e2d",
    "excel_ok": "\u5199\u5165\u6210\u529f",
    "excel_failed": "\u5199\u5165\u5931\u8d25",
    "recorded_excel_ok": "\u5df2\u5f55\u50cf\uff0c\u5df2\u5199\u5165Excel",
    "recording_failed": "\u5f55\u50cf\u5931\u8d25",
    "start_first": "\u8bf7\u5148\u70b9\u51fb\u5f00\u59cb",
    "disk_blocked": "\u78c1\u76d8\u7a7a\u95f4\u4e0d\u8db3",
    "enabled": "\u542f\u7528",
    "disabled": "\u5173\u95ed",
    "waiting_scan": "\u5f85\u626b\u7801",
    "auto_stopped": "\u5df2\u81ea\u52a8\u505c\u6b62",
    "camera_released": "\u6444\u50cf\u5934\u5df2\u91ca\u653e",
    "watchdog_reconnected": "watchdog \u91cd\u8fde\u6210\u529f",
    "watchdog_failed": "watchdog \u91cd\u8fde\u5931\u8d25\uff0c\u8bf7\u68c0\u67e5\u6444\u50cf\u5934",
    "disk_stopped": "\u78c1\u76d8\u4e0d\u8db3\uff0c\u5f55\u50cf\u5df2\u505c\u6b62",
    "disk_not_recorded": "\u78c1\u76d8\u4e0d\u8db3\uff0c\u672a\u5f55\u50cf",
    "config_saved": "\u914d\u7f6e\u4fdd\u5b58\u6210\u529f",
    "config_save_failed": "\u914d\u7f6e\u4fdd\u5b58\u5931\u8d25",
    "config_saved_hint": "\u914d\u7f6e\u5df2\u4fdd\u5b58\uff0c\u90e8\u5206\u529f\u80fd\u53ef\u80fd\u9700\u8981\u91cd\u65b0\u542f\u52a8\u9884\u89c8\u540e\u751f\u6548",
    "duplicate_blocked_completed": "\u91cd\u590d\u5df2\u62e6\u622a",
    "duplicate_blocked_window": "\u65f6\u95f4\u7a97\u53e3\u91cd\u590d\u5df2\u62e6\u622a",
    "recording_failed_retry": "\u5f55\u50cf\u5931\u8d25\uff0c\u53ef\u91cd\u8bd5",
    "excel_failed_retry": "Excel\u5931\u8d25\uff0c\u53ef\u91cd\u8bd5",
    "disk_retry": "\u78c1\u76d8\u4e0d\u8db3\uff0c\u672a\u5f55\u50cf\uff0c\u53ef\u91cd\u8bd5",
    "camera_retry": "\u6444\u50cf\u5934\u5f02\u5e38\uff0c\u53ef\u91cd\u8bd5",
    "on": "On",
    "off": "Off",
    "query_title": "\u5f55\u50cf\u67e5\u8be2",
    "query_button": "\u67e5\u8be2",
    "query_placeholder": "\u8f93\u5165\u5355\u53f7\uff0c\u7559\u7a7a\u67e5\u5168\u90e8",
    "open_or_create_mp4": "\u6253\u5f00/\u751f\u6210 MP4",
    "open_avi": "\u6253\u5f00 AVI",
    "export_csv": "\u5bfc\u51fa CSV",
    "export_excel": "\u5bfc\u51fa Excel",
    "all_sources": "\u5168\u90e8\u6765\u6e90",
    "total_records": "\u603b\u8bb0\u5f55\u6570\uff1a",
    "filtered_records": "\u7b5b\u9009\u6570\u91cf\uff1a",
    "recent_video": "\u6700\u8fd1\u5f55\u50cf\uff1a",
    "actual_paths": "AVI/MP4 \u8def\u5f84\uff1a",
    "recorded_status": "\u5f55\u50cf\u5b8c\u6210",
    "missing_status": "\u672a\u5b8c\u6210",
    "choose_color": "\u9009\u62e9\u989c\u8272",
    "motion_active": "\u6709\u53d8\u5316",
    "motion_static": "\u9759\u6b62",
}


DUPLICATE_POLICY_OPTIONS = [
    ("\u5141\u8bb8\u91cd\u590d\u626b\u7801", "allow"),
    ("\u5df2\u6210\u529f\u5f55\u50cf\u7684\u5355\u53f7\u4e0d\u91cd\u590d\u5904\u7406\uff08\u63a8\u8350\uff09", "block_completed_only"),
    ("\u6307\u5b9a\u65f6\u95f4\u5185\u4e0d\u91cd\u590d\u5904\u7406", "block_within_seconds"),
]
VALID_DUPLICATE_POLICIES = {value for _label, value in DUPLICATE_POLICY_OPTIONS}
DuplicatePolicy = str


def duplicate_policy_to_legacy_disable(policy: DuplicatePolicy) -> bool:
    return policy in {"block_completed_only", "block_within_seconds"}


def duplicate_policy_display(policy: DuplicatePolicy, block_seconds: int | float = 30) -> str:
    if policy == "allow":
        return "\u5141\u8bb8\u91cd\u590d\u626b\u7801"
    if policy == "block_completed_only":
        return "\u5df2\u6210\u529f\u5355\u53f7\u4e0d\u91cd\u590d"
    if policy == "block_within_seconds":
        return f"{int(block_seconds)} \u79d2\u5185\u4e0d\u91cd\u590d"
    return "\u672a\u77e5\u7b56\u7565"


def disk_usage_target(path: str | Path) -> Path:
    target = Path(path)
    if target.exists():
        return target
    for parent in target.parents:
        if parent.exists():
            return parent
    return Path.cwd()


def get_free_disk_gb(path: str | Path) -> float:
    usage = shutil.disk_usage(disk_usage_target(path))
    return usage.free / (1024 ** 3)


class ConfigDialog(QDialog):
    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.setWindowTitle(f"{__project_name__} v{__version__} (Build {__build__}) - 配置编辑")
        self.resize(620, 560)
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        camera_form = QFormLayout()

        self.camera_index = QSpinBox()
        self.camera_index.setRange(0, 10)
        camera_form.addRow("\u6444\u50cf\u5934\u7d22\u5f15", self.camera_index)

        self.resolution = QComboBox()
        for resolution in RESOLUTION_OPTIONS:
            self.resolution.addItem(resolution, resolution)
        camera_form.addRow("\u5206\u8fa8\u7387", self.resolution)

        self.fps = QSpinBox()
        self.fps.setRange(10, 30)
        self.fps.setSuffix(" FPS")
        camera_form.addRow("FPS", self.fps)

        self.resolution_policy = QComboBox()
        self.resolution_policy.addItem("配置分辨率优先", "config_first")
        self.resolution_policy.addItem("自动推荐", "auto_best")
        self.resolution_policy.addItem("流畅优先", "smooth_first")
        camera_form.addRow("分辨率策略", self.resolution_policy)

        self.recording_writer_codec = QComboBox()
        self.recording_writer_codec.addItem("MJPG（兼容/高质量）", "MJPG")
        self.recording_writer_codec.addItem("XVID（节省空间）", "XVID")
        camera_form.addRow("录像编码", self.recording_writer_codec)

        self.enable_lens_correction = QCheckBox("Enable Lens Correction")
        camera_form.addRow("Lens Correction", self.enable_lens_correction)
        scroll_layout.addWidget(self._form_group("\u6444\u50cf\u5934\u8bbe\u7f6e", camera_form))

        recording_form = QFormLayout()
        self.auto_stop_enabled = QCheckBox("\u542f\u7528\u7a7a\u95f2\u81ea\u52a8\u505c\u6b62")
        recording_form.addRow("\u81ea\u52a8\u505c\u6b62", self.auto_stop_enabled)
        storage_layout = QHBoxLayout()
        self.storage_path = QLineEdit()
        browse_button = QPushButton("\u9009\u62e9\u76ee\u5f55")
        browse_button.clicked.connect(self.choose_storage_path)
        storage_layout.addWidget(self.storage_path, stretch=1)
        storage_layout.addWidget(browse_button)
        recording_form.addRow("\u5b58\u50a8\u76ee\u5f55", storage_layout)

        self.auto_stop_timeout = QSpinBox()
        self.auto_stop_timeout.setRange(5, 86400)
        self.auto_stop_timeout.setSuffix(" \u79d2")
        recording_form.addRow("\u7a7a\u95f2\u8d85\u65f6\uff08\u79d2\uff09", self.auto_stop_timeout)

        self.keep_camera_on_timeout = QCheckBox("\u81ea\u52a8\u505c\u6b62\u540e\u4fdd\u6301\u9884\u89c8")
        recording_form.addRow("\u8d85\u65f6\u540e\u6444\u50cf\u5934", self.keep_camera_on_timeout)

        self.min_free_disk_gb = QSpinBox()
        self.min_free_disk_gb.setRange(1, 1000)
        self.min_free_disk_gb.setSuffix(" GB")
        recording_form.addRow("\u6700\u4f4e\u78c1\u76d8\u7a7a\u95f4\uff08GB\uff09", self.min_free_disk_gb)
        scroll_layout.addWidget(self._form_group("\u5f55\u50cf\u8bbe\u7f6e", recording_form))

        duplicate_form = QFormLayout()
        self.duplicate_policy = QComboBox()
        for label, value in DUPLICATE_POLICY_OPTIONS:
            self.duplicate_policy.addItem(label, value)
        self.duplicate_policy.currentIndexChanged.connect(self.update_duplicate_seconds_enabled)
        duplicate_form.addRow("\u91cd\u590d\u5355\u53f7\u5904\u7406\u7b56\u7565", self.duplicate_policy)

        self.duplicate_block_seconds = QSpinBox()
        self.duplicate_block_seconds.setRange(1, 3600)
        self.duplicate_block_seconds.setSuffix(" \u79d2")
        duplicate_form.addRow("\u91cd\u590d\u62e6\u622a\u65f6\u95f4\uff08\u79d2\uff09", self.duplicate_block_seconds)
        scroll_layout.addWidget(self._form_group("\u91cd\u590d\u5355\u53f7\u7b56\u7565", duplicate_form))

        watermark_form = QFormLayout()
        self.watermark_position = QComboBox()
        for label, value in WATERMARK_POSITIONS:
            self.watermark_position.addItem(label, value)
        watermark_form.addRow("\u6c34\u5370\u4f4d\u7f6e", self.watermark_position)

        self.watermark_font_scale = QDoubleSpinBox()
        self.watermark_font_scale.setRange(0.4, 3.0)
        self.watermark_font_scale.setSingleStep(0.1)
        self.watermark_font_scale.setDecimals(1)
        watermark_form.addRow("\u6c34\u5370\u5b57\u53f7", self.watermark_font_scale)

        color_layout = QHBoxLayout()
        self.watermark_color = QLineEdit()
        color_button = QPushButton(TEXT["choose_color"])
        color_button.clicked.connect(self.choose_watermark_color)
        color_layout.addWidget(self.watermark_color, stretch=1)
        color_layout.addWidget(color_button)
        watermark_form.addRow("\u6c34\u5370\u989c\u8272", color_layout)

        self.watermark_opacity = QSpinBox()
        self.watermark_opacity.setRange(10, 100)
        self.watermark_opacity.setSuffix(" %")
        watermark_form.addRow("\u6c34\u5370\u900f\u660e\u5ea6", self.watermark_opacity)
        scroll_layout.addWidget(self._form_group("\u6c34\u5370\u8bbe\u7f6e", watermark_form))

        query_form = QFormLayout()
        self.mp4_output_folder = QLineEdit()
        query_form.addRow("MP4 \u8f93\u51fa\u6587\u4ef6\u5939", self.mp4_output_folder)
        self.generate_mp4_on_query = QCheckBox("\u67e5\u8be2\u65f6\u5141\u8bb8\u751f\u6210 MP4")
        query_form.addRow("MP4", self.generate_mp4_on_query)
        self.query_default_source = QComboBox()
        self.query_default_source.addItem(TEXT["all_sources"], "")
        self.query_default_source.addItem("GUI", "GUI")
        self.query_default_source.addItem("\u626b\u7801", "\u626b\u7801")
        self.query_default_source.addItem("\u624b\u5de5", "\u624b\u5de5")
        query_form.addRow("\u9ed8\u8ba4\u6765\u6e90", self.query_default_source)
        self.query_default_start_date = QLineEdit()
        self.query_default_end_date = QLineEdit()
        query_form.addRow("\u9ed8\u8ba4\u5f00\u59cb\u65e5\u671f", self.query_default_start_date)
        query_form.addRow("\u9ed8\u8ba4\u7ed3\u675f\u65e5\u671f", self.query_default_end_date)
        scroll_layout.addWidget(self._form_group("\u67e5\u8be2 / MP4 \u8bbe\u7f6e", query_form))

        frame_idle_form = QFormLayout()
        self.frame_idle_detection_enabled = QCheckBox("\u542f\u7528\u753b\u9762\u9759\u6b62\u68c0\u6d4b")
        frame_idle_form.addRow("\u9759\u6b62\u68c0\u6d4b", self.frame_idle_detection_enabled)
        self.frame_idle_timeout = QSpinBox()
        self.frame_idle_timeout.setRange(1, 3600)
        self.frame_idle_timeout.setSuffix(" \u79d2")
        frame_idle_form.addRow("\u9759\u6b62\u8d85\u65f6", self.frame_idle_timeout)
        self.frame_motion_threshold = QDoubleSpinBox()
        self.frame_motion_threshold.setRange(0.1, 255.0)
        self.frame_motion_threshold.setDecimals(1)
        self.frame_motion_threshold.setSingleStep(0.5)
        frame_idle_form.addRow("\u53d8\u5316\u9608\u503c", self.frame_motion_threshold)
        scroll_layout.addWidget(self._form_group("\u753b\u9762\u9759\u6b62\u68c0\u6d4b", frame_idle_form))

        voice_form = QFormLayout()
        self.voice_enabled = QCheckBox("\u542f\u7528\u58f0\u97f3\u64ad\u62a5")
        voice_form.addRow("\u603b\u5f00\u5173", self.voice_enabled)
        self.voice_on_scan_success = QCheckBox("\u5355\u53f7\u8bc6\u522b\u6210\u529f")
        voice_form.addRow("\u626b\u7801\u6210\u529f", self.voice_on_scan_success)
        self.voice_on_record_start = QCheckBox("\u5f00\u59cb\u5f55\u50cf")
        voice_form.addRow("\u5f55\u50cf\u5f00\u59cb", self.voice_on_record_start)
        self.voice_on_record_stop = QCheckBox("\u5f55\u50cf\u5b8c\u6210")
        voice_form.addRow("\u5f55\u50cf\u505c\u6b62", self.voice_on_record_stop)
        self.voice_on_invalid_tracking = QCheckBox("\u5355\u53f7\u65e0\u6548")
        voice_form.addRow("\u65e0\u6548\u5355\u53f7", self.voice_on_invalid_tracking)
        self.voice_on_auth_problem = QCheckBox("\u8bf7\u6fc0\u6d3b\u6388\u6743")
        voice_form.addRow("\u6388\u6743\u95ee\u9898", self.voice_on_auth_problem)
        scroll_layout.addWidget(self._form_group("\u58f0\u97f3\u64ad\u62a5", voice_form))

        shared_form = QFormLayout()
        self.shared_storage_enabled = QCheckBox("\u542f\u7528\u5c40\u57df\u7f51\u5171\u4eab\u5b58\u50a8")
        shared_form.addRow("\u603b\u5f00\u5173", self.shared_storage_enabled)
        shared_path_layout = QHBoxLayout()
        self.shared_storage_path = QLineEdit()
        self.shared_storage_path.setPlaceholderText("\\\\NAS\\share \u6216 Z:\\ShippingEvidence")
        shared_browse_button = QPushButton("\u9009\u62e9\u76ee\u5f55")
        shared_browse_button.clicked.connect(self.choose_shared_storage_path)
        shared_test_button = QPushButton("\u6d4b\u8bd5\u8def\u5f84")
        shared_test_button.clicked.connect(self.test_shared_storage_path)
        shared_path_layout.addWidget(self.shared_storage_path, stretch=1)
        shared_path_layout.addWidget(shared_browse_button)
        shared_path_layout.addWidget(shared_test_button)
        shared_form.addRow("\u5171\u4eab\u5b58\u50a8\u8def\u5f84", shared_path_layout)
        self.shared_storage_test_status = QLabel("\u672a\u6d4b\u8bd5")
        shared_form.addRow("\u8def\u5f84\u72b6\u6001", self.shared_storage_test_status)
        self.shared_storage_copy_after_recording = QCheckBox("\u5f55\u50cf\u7ed3\u675f\u540e\u540e\u53f0\u590d\u5236")
        shared_form.addRow("\u81ea\u52a8\u590d\u5236", self.shared_storage_copy_after_recording)
        self.shared_storage_copy_avi = QCheckBox("\u590d\u5236 AVI")
        shared_form.addRow("AVI", self.shared_storage_copy_avi)
        self.shared_storage_copy_mp4 = QCheckBox("\u590d\u5236\u5df2\u5b58\u5728\u7684 MP4")
        shared_form.addRow("MP4", self.shared_storage_copy_mp4)
        self.shared_storage_copy_label_image = QCheckBox("\u590d\u5236\u9762\u5355\u622a\u56fe")
        shared_form.addRow("\u9762\u5355\u622a\u56fe", self.shared_storage_copy_label_image)
        self.shared_storage_fallback_local = QCheckBox("\u590d\u5236\u5931\u8d25\u65f6\u4fdd\u7559\u672c\u5730\u6587\u4ef6")
        self.shared_storage_fallback_local.setEnabled(False)
        self.shared_storage_fallback_local.setToolTip("\u672c\u5730\u539f\u6587\u4ef6\u59cb\u7ec8\u4fdd\u7559")
        shared_form.addRow("\u672c\u5730\u4fdd\u7559", self.shared_storage_fallback_local)
        scroll_layout.addWidget(self._form_group("\u5c40\u57df\u7f51\u5171\u4eab\u5b58\u50a8", shared_form))

        scroll_layout.addStretch(1)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("\u4fdd\u5b58\u914d\u7f6e")
        buttons.button(QDialogButtonBox.Cancel).setText("\u53d6\u6d88")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setWindowTitle(f"{__project_name__} v{__version__} (Build {__build__})")

    def _form_group(self, title: str, form: QFormLayout) -> QGroupBox:
        group = QGroupBox(title)
        group.setLayout(form)
        return group

    def _load_values(self) -> None:
        self.camera_index.setValue(int(self.config.camera_index))
        resolution_index = self.resolution.findData(str(self.config.resolution))
        self.resolution.setCurrentIndex(resolution_index if resolution_index >= 0 else 1)
        self.fps.setValue(int(self.config.fps))
        policy_index = self.resolution_policy.findData(
            str(getattr(self.config, "resolution_policy", "config_first"))
        )
        self.resolution_policy.setCurrentIndex(policy_index if policy_index >= 0 else 0)
        codec_index = self.recording_writer_codec.findData(
            str(getattr(self.config, "recording_writer_codec", "MJPG")).upper()
        )
        self.recording_writer_codec.setCurrentIndex(codec_index if codec_index >= 0 else 0)
        self.enable_lens_correction.setChecked(bool(getattr(self.config, "enable_lens_correction", False)))
        self.storage_path.setText(str(self.config.storage_path))
        self.auto_stop_enabled.setChecked(bool(getattr(self.config, "auto_stop_enabled", True)))
        self.auto_stop_timeout.setValue(int(self.config.auto_stop_timeout))
        self.keep_camera_on_timeout.setChecked(bool(getattr(self.config, "keep_camera_on_timeout", True)))
        self.min_free_disk_gb.setValue(int(float(self.config.min_free_disk_gb)))
        policy = getattr(self.config, "duplicate_policy", "block_completed_only")
        index = self.duplicate_policy.findData(policy)
        self.duplicate_policy.setCurrentIndex(index if index >= 0 else 1)
        self.duplicate_block_seconds.setValue(int(getattr(self.config, "duplicate_block_seconds", 30)))
        watermark_index = self.watermark_position.findData(getattr(self.config, "watermark_position", "top_left"))
        self.watermark_position.setCurrentIndex(watermark_index if watermark_index >= 0 else 0)
        self.watermark_font_scale.setValue(float(getattr(self.config, "watermark_font_scale", 0.9)))
        self.watermark_color.setText(str(getattr(self.config, "watermark_color", "#00FF00")))
        self.watermark_opacity.setValue(int(float(getattr(self.config, "watermark_opacity", 0.75)) * 100))
        self.mp4_output_folder.setText(str(getattr(self.config, "mp4_output_folder", "MP4")))
        self.generate_mp4_on_query.setChecked(bool(getattr(self.config, "generate_mp4_on_query", False)))
        source_index = self.query_default_source.findData(getattr(self.config, "query_default_source", ""))
        self.query_default_source.setCurrentIndex(source_index if source_index >= 0 else 0)
        self.query_default_start_date.setText(str(getattr(self.config, "query_default_start_date", "")))
        self.query_default_end_date.setText(str(getattr(self.config, "query_default_end_date", "")))
        self.frame_idle_detection_enabled.setChecked(bool(getattr(self.config, "frame_idle_detection_enabled", True)))
        self.frame_idle_timeout.setValue(int(getattr(self.config, "frame_idle_timeout", 30)))
        self.frame_motion_threshold.setValue(float(getattr(self.config, "frame_motion_threshold", 3.0)))
        self.voice_enabled.setChecked(bool(getattr(self.config, "voice_enabled", False)))
        self.voice_on_scan_success.setChecked(bool(getattr(self.config, "voice_on_scan_success", True)))
        self.voice_on_record_start.setChecked(bool(getattr(self.config, "voice_on_record_start", True)))
        self.voice_on_record_stop.setChecked(bool(getattr(self.config, "voice_on_record_stop", True)))
        self.voice_on_invalid_tracking.setChecked(bool(getattr(self.config, "voice_on_invalid_tracking", True)))
        self.voice_on_auth_problem.setChecked(bool(getattr(self.config, "voice_on_auth_problem", True)))
        self.shared_storage_enabled.setChecked(bool(getattr(self.config, "shared_storage_enabled", False)))
        self.shared_storage_path.setText(str(getattr(self.config, "shared_storage_path", "")))
        self.shared_storage_copy_after_recording.setChecked(
            bool(getattr(self.config, "shared_storage_copy_after_recording", True))
        )
        self.shared_storage_copy_avi.setChecked(bool(getattr(self.config, "shared_storage_copy_avi", True)))
        self.shared_storage_copy_mp4.setChecked(bool(getattr(self.config, "shared_storage_copy_mp4", True)))
        self.shared_storage_copy_label_image.setChecked(
            bool(getattr(self.config, "shared_storage_copy_label_image", True))
        )
        self.shared_storage_fallback_local.setChecked(True)
        self.update_duplicate_seconds_enabled()

    def choose_storage_path(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "\u9009\u62e9\u5b58\u50a8\u76ee\u5f55", self.storage_path.text())
        if selected:
            self.storage_path.setText(selected)

    def choose_shared_storage_path(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "\u9009\u62e9\u5171\u4eab\u5b58\u50a8\u76ee\u5f55",
            self.shared_storage_path.text().strip(),
        )
        if selected:
            self.shared_storage_path.setText(selected)

    def test_shared_storage_path(self) -> None:
        path_text = self.shared_storage_path.text().strip()
        ok, message = test_shared_storage_writable(path_text)
        self.shared_storage_test_status.setText(message)
        if ok:
            QMessageBox.information(self, "\u5171\u4eab\u5b58\u50a8", message)
        else:
            QMessageBox.warning(self, "\u5171\u4eab\u5b58\u50a8", message)

    def choose_watermark_color(self) -> None:
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self.watermark_color.setText(color.name().upper())

    def update_duplicate_seconds_enabled(self) -> None:
        self.duplicate_block_seconds.setEnabled(self.duplicate_policy.currentData() == "block_within_seconds")

    def values(self) -> dict:
        return {
            "camera_index": int(self.camera_index.value()),
            "resolution": self.resolution.currentData(),
            "fps": int(self.fps.value()),
            "resolution_policy": self.resolution_policy.currentData(),
            "recording_writer_codec": self.recording_writer_codec.currentData(),
            "enable_lens_correction": bool(self.enable_lens_correction.isChecked()),
            "storage_path": self.storage_path.text().strip(),
            "auto_stop_enabled": bool(self.auto_stop_enabled.isChecked()),
            "auto_stop_timeout": int(self.auto_stop_timeout.value()),
            "keep_camera_on_timeout": bool(self.keep_camera_on_timeout.isChecked()),
            "min_free_disk_gb": int(self.min_free_disk_gb.value()),
            "duplicate_policy": self.duplicate_policy.currentData(),
            "duplicate_block_seconds": int(self.duplicate_block_seconds.value()),
            "disable_duplicate_scan": duplicate_policy_to_legacy_disable(self.duplicate_policy.currentData()),
            "watermark_position": self.watermark_position.currentData(),
            "watermark_font_scale": float(self.watermark_font_scale.value()),
            "watermark_color": self.watermark_color.text().strip(),
            "watermark_opacity": float(self.watermark_opacity.value()) / 100,
            "mp4_output_folder": self.mp4_output_folder.text().strip() or "MP4",
            "generate_mp4_on_query": bool(self.generate_mp4_on_query.isChecked()),
            "query_default_source": self.query_default_source.currentData(),
            "query_default_start_date": self.query_default_start_date.text().strip(),
            "query_default_end_date": self.query_default_end_date.text().strip(),
            "frame_idle_detection_enabled": bool(self.frame_idle_detection_enabled.isChecked()),
            "frame_idle_timeout": int(self.frame_idle_timeout.value()),
            "frame_motion_threshold": float(self.frame_motion_threshold.value()),
            "voice_enabled": bool(self.voice_enabled.isChecked()),
            "voice_on_scan_success": bool(self.voice_on_scan_success.isChecked()),
            "voice_on_record_start": bool(self.voice_on_record_start.isChecked()),
            "voice_on_record_stop": bool(self.voice_on_record_stop.isChecked()),
            "voice_on_invalid_tracking": bool(self.voice_on_invalid_tracking.isChecked()),
            "voice_on_auth_problem": bool(self.voice_on_auth_problem.isChecked()),
            "shared_storage_enabled": bool(self.shared_storage_enabled.isChecked()),
            "shared_storage_path": self.shared_storage_path.text().strip(),
            "shared_storage_copy_after_recording": bool(
                self.shared_storage_copy_after_recording.isChecked()
            ),
            "shared_storage_copy_avi": bool(self.shared_storage_copy_avi.isChecked()),
            "shared_storage_copy_mp4": bool(self.shared_storage_copy_mp4.isChecked()),
            "shared_storage_copy_label_image": bool(
                self.shared_storage_copy_label_image.isChecked()
            ),
            "shared_storage_fallback_local": True,
        }


def license_status_display(status) -> str:
    status_name = getattr(status, "status", "")
    if status_name == "trial_available":
        return "\u53ef\u514d\u8d39\u8bd5\u7528 30 \u5929"
    if status_name == "trial_valid":
        return f"\u8bd5\u7528\u5269\u4f59 {getattr(status, 'trial_days_remaining', 0) or 0} \u5929"
    if status_name == "trial_expired":
        return "\u8bd5\u7528\u5df2\u5230\u671f\uff0c\u8bf7\u8054\u7cfb\u4f9b\u5e94\u5546\u6fc0\u6d3b"
    if status_name == "trial_time_error":
        return "\u7cfb\u7edf\u65f6\u95f4\u5f02\u5e38"
    if status_name in {"trial_corrupted", "trial_machine_mismatch", "trial_write_error"}:
        return "\u8bd5\u7528\u72b6\u6001\u5f02\u5e38"
    if getattr(status, "ok", False) and getattr(status, "status", "") == "valid":
        return "试用版" if getattr(status, "edition", "") == "trial" else "正式版"
    return {
        "state_missing": "未授权",
        "expired": "已过期",
        "machine_mismatch": "机器码不匹配",
        "time_error": "系统时间异常",
        "state_corrupted": "授权状态损坏",
        "invalid_signature": "授权状态损坏",
        "invalid_format": "授权状态损坏",
        "public_key_error": "授权状态损坏",
        "product_mismatch": "授权状态损坏",
    }.get(getattr(status, "status", ""), "读取失败")


def license_expiry_display(status) -> str:
    if getattr(status, "edition", "") == "permanent":
        return "永久"
    return str(getattr(status, "expires_at", "") or "—")


def configured_license_status(config=None):
    return get_license_status(
        trial_enabled=bool(getattr(config, "auto_trial_enabled", True)),
        trial_days=int(getattr(config, "auto_trial_days", 30)),
    )


def license_features_display(features: dict | None) -> str:
    if not features:
        return "—"
    labels = {
        "recording": "录像",
        "query": "查询",
        "export": "导出",
        "camera_barcode": "摄像头条码",
    }
    return "，".join(
        f"{labels.get(name, name)}：{'开' if enabled else '关'}"
        for name, enabled in features.items()
    )


def license_activation_error_display(status: str, fallback: str) -> str:
    return {
        "invalid_format": "未检测到有效授权码，请复制以 SMG1. 开头的授权码，或直接粘贴完整授权工具输出。",
        "invalid_signature": "授权签名无效，请联系供应商重新获取授权码。",
        "machine_mismatch": "授权码与本机机器码不匹配。",
        "expired": "授权已过期，请联系供应商获取新授权码。",
        "time_error": "系统时间异常，请检查电脑时间后重试。",
        "public_key_error": "授权公钥校验失败，请联系供应商。",
        "product_mismatch": "授权码不属于当前软件。",
    }.get(status, fallback or "授权激活失败。")


class LicenseActivationDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.main_window = parent
        self.machine_code = get_machine_code()
        self.setWindowTitle("软件授权 / 激活")
        self.resize(700, 560)
        self._build_ui()
        self.refresh_license_status()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        hint = QLabel(SUPPORT_LICENSE_HINT)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        self.status_value = QLabel("读取中")
        self.customer_value = QLabel("—")
        self.edition_value = QLabel("—")
        self.expiry_value = QLabel("—")
        self.features_value = QLabel("—")
        self.features_value.setWordWrap(True)
        self.machine_code_value = QLabel(format_machine_code(self.machine_code))
        self.machine_code_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.machine_code_value.setWordWrap(True)
        form.addRow("授权状态", self.status_value)
        form.addRow("客户名称", self.customer_value)
        form.addRow("授权类型", self.edition_value)
        form.addRow("到期时间", self.expiry_value)
        form.addRow("授权功能", self.features_value)
        form.addRow("本机机器码", self.machine_code_value)
        layout.addLayout(form)

        machine_buttons = QHBoxLayout()
        copy_machine_button = QPushButton("复制机器码")
        copy_machine_button.clicked.connect(self.copy_machine_code)
        machine_buttons.addWidget(copy_machine_button)
        machine_buttons.addStretch(1)
        layout.addLayout(machine_buttons)

        self.authorization_code_input = QTextEdit()
        self.authorization_code_input.setPlaceholderText("请粘贴供应商提供的授权码")
        self.authorization_code_input.setMinimumHeight(130)
        layout.addWidget(self.authorization_code_input)

        action_buttons = QHBoxLayout()
        paste_code_button = QPushButton("粘贴授权码")
        paste_code_button.clicked.connect(self.paste_authorization_code)
        activate_button = QPushButton("激活")
        activate_button.clicked.connect(self.activate_code)
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.reject)
        action_buttons.addWidget(paste_code_button)
        action_buttons.addStretch(1)
        action_buttons.addWidget(activate_button)
        action_buttons.addWidget(close_button)
        layout.addLayout(action_buttons)

    def refresh_license_status(self) -> None:
        try:
            status = configured_license_status(getattr(self.main_window, "config", None))
        except Exception:  # noqa: BLE001
            self.status_value.setText("读取失败")
            self.customer_value.setText("—")
            self.edition_value.setText("—")
            self.expiry_value.setText("—")
            self.features_value.setText("—")
            return

        self.status_value.setText(license_status_display(status))
        self.customer_value.setText(status.customer or "—")
        self.edition_value.setText(status.edition or "—")
        self.expiry_value.setText(license_expiry_display(status))
        self.features_value.setText(license_features_display(status.features) if status.ok else "—")

    def copy_machine_code(self) -> None:
        QApplication.clipboard().setText(self.machine_code_value.text())
        QMessageBox.information(self, "软件授权", "机器码已复制。")

    def paste_authorization_code(self) -> None:
        clipboard_text = QApplication.clipboard().text()
        extracted_code = extract_authorization_code(clipboard_text)
        if extracted_code:
            self.authorization_code_input.setPlainText(extracted_code)
            return
        self.authorization_code_input.setPlainText(clipboard_text)
        QMessageBox.warning(self, "软件授权", "未检测到 SMG1 授权码。")

    def activate_code(self) -> None:
        pasted_text = self.authorization_code_input.toPlainText().strip()
        if not pasted_text:
            QMessageBox.warning(self, "软件授权", "请先粘贴授权码。")
            return
        code = extract_authorization_code(pasted_text) or pasted_text

        result = activate_with_code(code)
        if not result.ok:
            QMessageBox.warning(
                self,
                "软件授权",
                license_activation_error_display(result.status, result.message),
            )
            self.refresh_license_status()
            return

        QMessageBox.information(self, "软件授权", "激活成功")
        self.refresh_license_status()
        if self.main_window is not None and hasattr(self.main_window, "add_log"):
            self.main_window.add_log(f"授权激活成功：{result.customer or '—'} / {result.edition or '—'}")


class QueryDialog(QDialog):
    COLUMNS = [
        "\u5355\u53f7",
        "\u72b6\u6001",
        "\u6765\u6e90",
        "AVI \u8def\u5f84",
        "MP4 \u8def\u5f84",
        "\u9762\u5355\u622a\u56fe",
    ]
    AVI_COLUMN = 3
    MP4_COLUMN = 4
    LABEL_IMAGE_COLUMN = 5
    export_log = pyqtSignal(str)
    export_mp4_done = pyqtSignal(int, int)

    def __init__(
        self,
        query_manager: QueryManager,
        defaults: dict[str, str] | None = None,
        generate_mp4_on_query: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.query_manager = query_manager
        self.playback_manager = PlaybackManager()
        self.results: list[dict[str, str]] = []
        self.defaults = defaults or {}
        self.generate_mp4_on_query = generate_mp4_on_query
        self.last_evidence_package_path: Path | None = None
        self.erp_manager = ERPManager(runtime_root() / "data" / "erp_orders.xlsx")
        self.setWindowTitle(TEXT["query_title"])
        self.resize(1120, 640)
        self._build_ui()
        self.export_log.connect(self.add_log)
        self.export_mp4_done.connect(self._on_export_mp4_done)
        self._load_defaults()
        # Do NOT auto-query on open; user must click query or press Enter

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        search_layout = QGridLayout()
        search_layout.setHorizontalSpacing(8)
        search_layout.setVerticalSpacing(8)
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText(TEXT["query_placeholder"])
        self.query_input.returnPressed.connect(self.search_records)
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        self.source_filter = QComboBox()
        self.source_filter.addItem(TEXT["all_sources"], "")
        self.source_filter.addItem("GUI", "GUI")
        self.source_filter.addItem("\u626b\u7801", "\u626b\u7801")
        self.source_filter.addItem("\u624b\u5de5", "\u624b\u5de5")
        query_button = QPushButton(TEXT["query_button"])
        query_button.clicked.connect(self.search_records)
        open_avi_button = QPushButton(TEXT["open_avi"])
        open_avi_button.clicked.connect(self.open_selected_avi)
        mp4_button = QPushButton(TEXT["open_or_create_mp4"])
        mp4_button.clicked.connect(self.open_or_create_selected_mp4)
        export_csv_button = QPushButton(TEXT["export_csv"])
        export_csv_button.clicked.connect(self.export_csv)
        export_excel_button = QPushButton(TEXT["export_excel"])
        export_excel_button.clicked.connect(self.export_excel)

        # Row 0: query input + date filters + source
        # 使用独立容器精确控制日期筛选区间距
        date_filter_widget = QWidget()
        date_filter_layout = QHBoxLayout(date_filter_widget)
        date_filter_layout.setContentsMargins(0, 0, 0, 0)
        date_filter_layout.setSpacing(4)

        start_label = QLabel("\u5f00\u59cb")
        start_label.setFixedWidth(32)
        start_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        end_label = QLabel("\u7ed3\u675f")
        end_label.setFixedWidth(32)
        end_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        date_filter_layout.addWidget(start_label)
        date_filter_layout.addWidget(self.start_date)
        date_filter_layout.addSpacing(10)
        date_filter_layout.addWidget(end_label)
        date_filter_layout.addWidget(self.end_date)
        date_filter_layout.addSpacing(8)
        date_filter_layout.addWidget(self.source_filter)
        date_filter_layout.addStretch()

        search_layout.addWidget(self.query_input, 0, 0, 1, 4)
        search_layout.addItem(QSpacerItem(35, 0, QSizePolicy.Fixed, QSizePolicy.Minimum), 0, 4)
        search_layout.addWidget(date_filter_widget, 0, 5, 1, 6)
        # Row 1: buttons
        export_avi_button = QPushButton("\u5bfc\u51fa AVI")
        export_avi_button.clicked.connect(self.export_selected_avi)
        export_mp4_button = QPushButton("\u5bfc\u51fa MP4")
        export_mp4_button.clicked.connect(self.export_selected_mp4)
        evidence_button = QPushButton("导出证据包")
        evidence_button.clicked.connect(self.export_evidence_package)
        open_evidence_button = QPushButton("打开证据包目录")
        open_evidence_button.clicked.connect(self.open_evidence_package_directory)
        search_layout.addWidget(query_button, 1, 0)
        search_layout.addWidget(open_avi_button, 1, 1)
        search_layout.addWidget(mp4_button, 1, 2)
        search_layout.addWidget(export_avi_button, 1, 3)
        search_layout.addWidget(export_mp4_button, 1, 4)
        search_layout.addWidget(export_csv_button, 1, 5)
        search_layout.addWidget(export_excel_button, 1, 6)
        search_layout.addWidget(evidence_button, 1, 7)
        search_layout.addWidget(open_evidence_button, 1, 8)
        delete_button = QPushButton("\u5220\u9664\u9009\u4e2d\u5f55\u50cf")
        delete_button.clicked.connect(self.delete_selected_records)
        search_layout.addWidget(delete_button, 1, 9)
        import_erp_button = QPushButton("导入 ERP 订单")
        import_erp_button.clicked.connect(self.import_erp_orders)
        export_erp_button = QPushButton("导出 ERP 留证结果")
        export_erp_button.clicked.connect(self.export_erp_evidence_results)
        template_erp_button = QPushButton("生成 ERP 导入模板")
        template_erp_button.clicked.connect(self.generate_erp_import_template)
        search_layout.addWidget(import_erp_button, 2, 0, 1, 2)
        search_layout.addWidget(export_erp_button, 2, 2, 1, 2)
        search_layout.addWidget(template_erp_button, 2, 4, 1, 2)
        search_layout.setColumnStretch(0, 2)
        layout.addLayout(search_layout)

        status_layout = QGridLayout()
        self.total_records_status = QLabel("0")
        self.filtered_records_status = QLabel("0")
        self.recent_video_status = QLabel("--")
        self.actual_paths_status = QLabel("--")
        self.actual_paths_status.setWordWrap(True)
        status_rows = [
            (TEXT["total_records"], self.total_records_status),
            (TEXT["filtered_records"], self.filtered_records_status),
            (TEXT["recent_video"], self.recent_video_status),
            (TEXT["actual_paths"], self.actual_paths_status),
        ]
        for row, (label_text, widget) in enumerate(status_rows):
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            status_layout.addWidget(label, row, 0)
            status_layout.addWidget(widget, row, 1)
        layout.addLayout(status_layout)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, stretch=1)

    # Enable Ctrl+C copy for table
    def keyPressEvent(self, event) -> None:
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_C:
            self.copy_selection()
        else:
            super().keyPressEvent(event)

    def copy_selection(self) -> None:
        selection = self.table.selectionModel().selectedIndexes()
        if not selection:
            return
        rows = sorted(set(s.row() for s in selection))
        cols = sorted(set(s.column() for s in selection))
        text_lines = []
        for r in rows:
            row_text = []
            for c in cols:
                item = self.table.item(r, c)
                row_text.append(item.text() if item else "")
            text_lines.append("\t".join(row_text))
        clipboard_text = "\n".join(text_lines)
        QApplication.clipboard().setText(clipboard_text)
        self.add_log(f"Copied {len(rows)} row(s) to clipboard")

    def add_log(self, message: str) -> None:
        if hasattr(self, 'log_box'):
            self.log_box.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")


    def _load_defaults(self) -> None:
        current = QDate.currentDate()
        start_text = self.defaults.get("query_default_start_date", "")
        end_text = self.defaults.get("query_default_end_date", "")
        start = QDate.fromString(start_text, "yyyy-MM-dd") if start_text else current.addMonths(-1)
        end = QDate.fromString(end_text, "yyyy-MM-dd") if end_text else current
        self.start_date.setDate(start if start.isValid() else current.addMonths(-1))
        self.end_date.setDate(end if end.isValid() else current)
        source_index = self.source_filter.findData(self.defaults.get("query_default_source", ""))
        self.source_filter.setCurrentIndex(source_index if source_index >= 0 else 0)

    def search_records(self) -> None:
        try:
            start = self.start_date.date().toString("yyyy-MM-dd")
            end = self.end_date.date().toString("yyyy-MM-dd")
            source = self.source_filter.currentData()
            self.results = self.query_manager.query(self.query_input.text(), start, end, source)
            self.save_query_preferences(start, end, source)
            self._fill_results_table()
            self.refresh_status_panel()
            self.add_log(f"查询完成: {len(self.results)} 条记录")
        except Exception as e:
            self.add_log(f"查询失败: {e}")

    def _fill_results_table(self) -> None:
        self.table.setRowCount(len(self.results))
        for row_index, result in enumerate(self.results):
            label_image_path = str(result.get("label_image_path", "") or "").strip()
            label_image_exists = bool(label_image_path) and Path(label_image_path).is_file()
            values = [
                result.get("tracking_number", ""),
                self.display_status(result.get("status", "")),
                result.get("source", ""),
                result.get("avi_path", ""),
                result.get("mp4_path", ""),
                "\u67e5\u770b" if label_image_exists else "\u65e0",
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column_index == self.LABEL_IMAGE_COLUMN and label_image_path:
                    item.setToolTip(label_image_path)
                else:
                    item.setToolTip(value)
                self.table.setItem(row_index, column_index, item)


    def run_query(self) -> None:
        self.search_records()

    def selected_result(self) -> dict[str, str] | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.results):
            return None
        return self.results[row]

    def on_cell_double_clicked(self, row: int, column: int) -> None:
        self.table.selectRow(row)
        if column == self.AVI_COLUMN:
            self.open_selected_avi()
        elif column == self.MP4_COLUMN:
            self.open_or_create_selected_mp4()
        elif column == self.LABEL_IMAGE_COLUMN:
            self.open_selected_label_image()

    def open_selected_avi(self) -> None:
        result = self.selected_result()
        if not result:
            return
        avi_path = Path(result.get("avi_path", ""))
        if not avi_path.exists():
            QMessageBox.warning(self, TEXT["query_title"], f"AVI \u6587\u4ef6\u4e0d\u5b58\u5728\uff1a{avi_path}")
            return
        self.playback_manager.open_video(avi_path)

    def open_or_create_selected_mp4(self) -> None:
        result = self.selected_result()
        if not result:
            return
        try:
            mp4_path_text = result.get("mp4_path", "").strip()
            mp4_path = Path(mp4_path_text) if mp4_path_text else None
            if mp4_path is None or not mp4_path.exists():
                if not self.generate_mp4_on_query:
                    answer = QMessageBox.question(
                        self,
                        TEXT["query_title"],
                        "MP4 \u4e0d\u5b58\u5728\uff0c\u662f\u5426\u7acb\u5373\u751f\u6210\uff1f",
                    )
                    if answer != QMessageBox.Yes:
                        return
                mp4_path = self.query_manager.ensure_mp4(
                    result.get("avi_path", ""),
                    result.get("tracking_number", ""),
                )
                result["mp4_path"] = str(mp4_path)
                item = QTableWidgetItem(str(mp4_path))
                item.setToolTip(str(mp4_path))
                self.table.setItem(self.table.currentRow(), self.MP4_COLUMN, item)
                self.refresh_status_panel()
            self.playback_manager.open_video(mp4_path)
        except Exception as exc:
            QMessageBox.warning(self, TEXT["query_title"], f"MP4 \u5904\u7406\u5931\u8d25\uff1a{exc}")

    def open_selected_label_image(self) -> None:
        result = self.selected_result()
        if not result:
            return
        label_image_text = str(result.get("label_image_path", "") or "").strip()
        if not label_image_text:
            QMessageBox.information(self, TEXT["query_title"], "\u8be5\u8bb0\u5f55\u65e0\u9762\u5355\u622a\u56fe")
            return
        label_image = Path(label_image_text)
        if not label_image.is_file():
            QMessageBox.warning(
                self,
                TEXT["query_title"],
                f"\u9762\u5355\u622a\u56fe\u6587\u4ef6\u4e0d\u5b58\u5728\uff1a{label_image}",
            )
            return
        try:
            if os.name == "nt":
                os.startfile(str(label_image))
            else:
                subprocess.Popen(["xdg-open", str(label_image)])
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                TEXT["query_title"],
                f"\u65e0\u6cd5\u6253\u5f00\u9762\u5355\u622a\u56fe\uff1a{exc}",
            )

    def export_csv(self) -> None:
        target, _filter = QFileDialog.getSaveFileName(self, TEXT["export_csv"], "query_results.csv", "CSV (*.csv)")
        if not target:
            return
        self.query_manager.export_csv(self.results, target)

    def export_excel(self) -> None:
        target, _filter = QFileDialog.getSaveFileName(self, TEXT["export_excel"], "query_results.xlsx", "Excel (*.xlsx)")
        if not target:
            return
        self.query_manager.export_excel(self.results, target)

    def import_erp_orders(self) -> None:
        source, _filter = QFileDialog.getOpenFileName(
            self,
            "导入 ERP 订单",
            "",
            "ERP 订单文件 (*.xlsx *.csv)",
        )
        if not source:
            return
        try:
            result = self.erp_manager.import_orders(source)
            message = (
                f"ERP 订单导入完成：{result['imported']} 条，"
                f"跳过 {result['skipped']} 条，当前共 {result['total']} 条。"
            )
            missing_fields = result.get("missing_fields", [])
            if missing_fields:
                message += f"\n未提供的非关键字段已留空：{', '.join(missing_fields)}"
            self.add_log(message)
            QMessageBox.information(self, "导入 ERP 订单", message)
        except Exception as exc:  # noqa: BLE001
            self.add_log(f"ERP 订单导入失败：{exc}")
            QMessageBox.warning(self, "导入 ERP 订单", f"导入失败：{exc}")

    def export_erp_evidence_results(self) -> None:
        if not self.results:
            QMessageBox.information(self, "导出 ERP 留证结果", "请先查询需要导出的留证记录")
            return
        target, selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出 ERP 留证结果",
            "erp_evidence_results.xlsx",
            "Excel (*.xlsx);;CSV (*.csv)",
        )
        if not target:
            return
        output = Path(target)
        if not output.suffix:
            output = output.with_suffix(".csv" if "CSV" in selected_filter else ".xlsx")
        try:
            exported = self.erp_manager.export_evidence_results(self.results, output)
            self.add_log(f"ERP 留证结果已导出：{exported}")
            QMessageBox.information(self, "导出 ERP 留证结果", f"已导出：{exported}")
        except Exception as exc:  # noqa: BLE001
            self.add_log(f"ERP 留证结果导出失败：{exc}")
            QMessageBox.warning(self, "导出 ERP 留证结果", f"导出失败：{exc}")

    def generate_erp_import_template(self) -> None:
        target, selected_filter = QFileDialog.getSaveFileName(
            self,
            "生成 ERP 导入模板",
            "erp_import_template.xlsx",
            "Excel (*.xlsx);;CSV (*.csv)",
        )
        if not target:
            return
        output = Path(target)
        if not output.suffix:
            output = output.with_suffix(".csv" if "CSV" in selected_filter else ".xlsx")
        try:
            generated = self.erp_manager.generate_template(output)
            self.add_log(f"ERP 导入模板已生成：{generated}")
            QMessageBox.information(self, "生成 ERP 导入模板", f"已生成：{generated}")
        except Exception as exc:  # noqa: BLE001
            self.add_log(f"ERP 导入模板生成失败：{exc}")
            QMessageBox.warning(self, "生成 ERP 导入模板", f"生成失败：{exc}")

    def export_evidence_package(self) -> None:
        result = self.selected_result()
        if not result:
            QMessageBox.information(self, TEXT["query_title"], "请先选择一条查询记录")
            return
        try:
            package_path, export_result = self.query_manager.create_evidence_package(result)
            self.last_evidence_package_path = package_path
            missing_count = len(export_result.get("notes", []))
            message = f"证据包已导出：\n{package_path}"
            if missing_count:
                message += f"\n\n有 {missing_count} 项文件缺失或未复制，详情见 summary.txt。"
            self.add_log(f"证据包已导出：{package_path}")
            QMessageBox.information(self, "导出证据包", message)
        except Exception as exc:  # noqa: BLE001
            self.add_log(f"证据包导出失败：{exc}")
            QMessageBox.warning(self, "导出证据包", f"导出失败：{exc}")

    def open_evidence_package_directory(self) -> None:
        target = self.last_evidence_package_path
        if target is None or not target.is_dir():
            QMessageBox.information(self, "打开证据包目录", "暂无已导出的证据包")
            return
        try:
            if os.name == "nt":
                os.startfile(str(target))
            else:
                subprocess.Popen(["xdg-open", str(target)])
            self.add_log(f"已打开证据包目录：{target}")
        except Exception as exc:  # noqa: BLE001
            self.add_log(f"打开证据包目录失败：{exc}")
            QMessageBox.warning(self, "打开证据包目录", f"无法打开目录：{exc}")

    def _get_selected_results(self) -> list[dict[str, str]]:
        rows = sorted(set(idx.row() for idx in self.table.selectionModel().selectedIndexes()))
        if not rows:
            QMessageBox.information(self, TEXT["query_title"], "\u8bf7\u5148\u9009\u62e9\u8981\u5bfc\u51fa\u7684\u5f55\u50cf\u8bb0\u5f55")
            return []
        return [self.results[r] for r in rows if r < len(self.results)]

    def export_selected_avi(self) -> None:
        selected = self._get_selected_results()
        if not selected:
            return
        target_dir = QFileDialog.getExistingDirectory(self, "\u9009\u62e9\u5bfc\u51fa\u76ee\u5f55")
        if not target_dir:
            return
        import shutil
        success, fail = 0, 0
        for rec in selected:
            avi = rec.get("avi_path", "").strip()
            if not avi or not Path(avi).exists():
                fail += 1
                self.add_log(f"AVI \u4e0d\u5b58\u5728: {avi}")
                continue
            dest = Path(target_dir) / Path(avi).name
            if dest.exists():
                stem, suffix = dest.stem, dest.suffix
                n = 1
                while dest.exists():
                    dest = Path(target_dir) / f"{stem}_{n}{suffix}"
                    n += 1
            try:
                shutil.copy2(avi, dest)
                success += 1
            except Exception as e:
                fail += 1
                self.add_log(f"AVI \u5bfc\u51fa\u5931\u8d25: {e}")
        QMessageBox.information(self, TEXT["query_title"], f"\u5bfc\u51fa AVI \u5b8c\u6210\uff1a\u6210\u529f {success}\uff0c\u5931\u8d25 {fail}")

    def export_selected_mp4(self) -> None:
        selected = self._get_selected_results()
        if not selected:
            return
        target_dir = QFileDialog.getExistingDirectory(self, "\u9009\u62e9\u5bfc\u51fa\u76ee\u5f55")
        if not target_dir:
            return
        import shutil
        from threading import Thread
        target_path = Path(target_dir)

        def _do_export():
            success, fail = 0, 0
            for idx, rec in enumerate(selected):
                avi_text = rec.get("avi_path", "").strip()
                mp4_text = rec.get("mp4_path", "").strip()
                tracking = rec.get("tracking_number", "").strip()
                
                # Determine destination filename
                if avi_text:
                    base_name = Path(avi_text).stem + ".mp4"
                elif tracking:
                    base_name = f"{tracking}.mp4"
                else:
                    fail += 1
                    self.export_log.emit(f"MP4 \u5bfc\u51fa\u5931\u8d25: \u65e0\u6cd5\u786e\u5b9a\u6587\u4ef6\u540d")
                    continue
                
                dest = target_path / base_name
                if dest.exists():
                    stem, suffix = Path(base_name).stem, ".mp4"
                    n = 1
                    while dest.exists():
                        dest = target_path / f"{stem}_{n}{suffix}"
                        n += 1
                
                # If MP4 already exists at source, copy it
                mp4_src = Path(mp4_text) if mp4_text else None
                if mp4_src and mp4_src.exists():
                    try:
                        shutil.copy2(mp4_src, dest)
                        success += 1
                        self.export_log.emit(f"MP4 \u5df2\u590d\u5236: {dest}")
                    except Exception as e:
                        fail += 1
                        self.export_log.emit(f"MP4 \u590d\u5236\u5931\u8d25: {e}")
                    continue
                
                # MP4 doesn't exist - generate from AVI directly to target folder
                if not avi_text or not Path(avi_text).exists():
                    fail += 1
                    self.export_log.emit(f"AVI \u4e0d\u5b58\u5728: {avi_text}")
                    continue
                
                try:
                    # Generate MP4 directly to target folder
                    generated = self._generate_mp4_to_target(avi_text, str(dest))
                    if generated:
                        success += 1
                        self.export_log.emit(f"MP4 \u5df2\u751f\u6210: {dest}")
                    else:
                        fail += 1
                except Exception as e:
                    fail += 1
                    self.export_log.emit(f"MP4 \u751f\u6210\u5931\u8d25: {e}")
            
            # Update UI from main thread
            self.export_mp4_done.emit(success, fail)

        class ExportThread(Thread):
            def __init__(self_inner):
                super().__init__(daemon=True)
            def run(self_inner):
                _do_export()

        self._export_thread = ExportThread()
        self._export_thread.start()
        self.add_log("MP4 \u5bfc\u51fa\u5f00\u59cb\u2026\u2026")

    def _generate_mp4_to_target(self, avi_path: str, target_mp4_path: str) -> bool:
        """Generate MP4 from AVI directly to target path."""
        try:
            convert_avi_to_mp4(avi_path, target_mp4_path, logger=self.export_log.emit)
            return Path(target_mp4_path).exists()
        except Exception as e:
            self.export_log.emit(f"_generate_mp4_to_target error: {e}")
            return False

    def _on_export_mp4_done(self, success: int, fail: int) -> None:
        QMessageBox.information(self, TEXT["query_title"], f"\u5bfc\u51fa MP4 \u5b8c\u6210\uff1a\u6210\u529f {success}\uff0c\u5931\u8d25 {fail}")
        self.add_log(f"MP4 \u5bfc\u51fa\u5b8c\u6210: \u6210\u529f {success}, \u5931\u8d25 {fail}")

    def delete_selected_records(self) -> None:
        """Delete selected records and their video files."""
        rows = sorted(set(idx.row() for idx in self.table.selectionModel().selectedIndexes()))
        if not rows:
            QMessageBox.information(self, TEXT["query_title"], "\u8bf7\u5148\u9009\u62e9\u8981\u5220\u9664\u7684\u5f55\u50cf\u8bb0\u5f55")
            return
        
        # Confirm with user
        reply = QMessageBox.question(
            self, 
            TEXT["query_title"],
            f"\u786e\u5b9a\u8981\u5220\u9664\u9009\u4e2d\u7684 {len(rows)} \u6761\u8bb0\u5f55\u53ca\u5176\u89c6\u9891\u6587\u4ef6\u5417\uff1f\u6b64\u64cd\u4f5c\u4e0d\u53ef\u64a4\u9500\u3002",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        success, fail = 0, 0
        failed_tracking_numbers: list[str] = []
        try:
            # Delete from end to avoid index shifting
            for row in reversed(rows):
                if row >= len(self.results):
                    continue
                rec = self.results[row]
                tracking = rec.get('tracking_number', '')

                # Delete AVI file
                avi_path = rec.get('avi_path', '').strip()
                if avi_path and Path(avi_path).exists():
                    try:
                        Path(avi_path).unlink()
                        self.add_log(f"\u5df2\u5220\u9664 AVI: {avi_path}")
                    except Exception as e:
                        fail += 1
                        failed_tracking_numbers.append(tracking)
                        self.add_log(f"\u5355\u53f7 {tracking} \u5220\u9664 AVI \u5931\u8d25: {e}")
                        continue

                # Delete MP4 file if exists
                mp4_path = rec.get('mp4_path', '').strip()
                if mp4_path and Path(mp4_path).exists():
                    try:
                        Path(mp4_path).unlink()
                        self.add_log(f"\u5df2\u5220\u9664 MP4: {mp4_path}")
                    except Exception as e:
                        fail += 1
                        failed_tracking_numbers.append(tracking)
                        self.add_log(f"\u5355\u53f7 {tracking} \u5220\u9664 MP4 \u5931\u8d25: {e}")
                        continue

                # Remove from results list
                self.results.pop(row)
                success += 1
        finally:
            try:
                # Refresh table
                self._fill_results_table()
                # Update status panel
                self.refresh_status_panel()
            except Exception as exc:
                self.add_log(f"\u5220\u9664\u540e\u5237\u65b0\u5217\u8868\u5931\u8d25\uff1a{exc}")

            summary = f"\u5220\u9664\u5b8c\u6210\uff1a\u6210\u529f {success} \u6761\uff0c\u5931\u8d25 {fail} \u6761"
            if failed_tracking_numbers:
                summary += "\n\u5931\u8d25\u5355\u53f7\uff1a" + "\u3001".join(failed_tracking_numbers)
            QMessageBox.information(self, TEXT["query_title"], summary)
            self.add_log(f"\u5220\u9664\u8bb0\u5f55\u5b8c\u6210: \u6210\u529f {success}, \u5931\u8d25 {fail}")

    def refresh_status_panel(self) -> None:
        try:
            total = len(self.query_manager.query())
        except Exception:
            total = 0
        self.total_records_status.setText(str(total))
        self.filtered_records_status.setText(str(len(self.results)))
        if not self.results:
            self.recent_video_status.setText("--")
            self.actual_paths_status.setText("--")
            return
        latest = self.results[-1]
        self.recent_video_status.setText(
            f"{latest.get('tracking_number', '')} / {self.display_status(latest.get('status', ''))}"
        )
        self.actual_paths_status.setText(
            f"AVI: {latest.get('avi_path', '')}\nMP4: {latest.get('mp4_path', '') or '--'}"
        )

    def display_status(self, status: str) -> str:
        if status == "recorded":
            return TEXT["recorded_status"]
        if status == "missing_avi":
            return TEXT["missing_status"]
        return status

    def save_query_preferences(self, start: str, end: str, source: str) -> None:
        try:
            with RUNTIME_CONFIG.open("r", encoding="utf-8") as handle:
                raw_config = json.load(handle)
            raw_config["query_default_start_date"] = start
            raw_config["query_default_end_date"] = end
            raw_config["query_default_source"] = source
            with RUNTIME_CONFIG.open("w", encoding="utf-8") as handle:
                json.dump(raw_config, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
        except Exception:
            return


class CameraCalibrationDialog(QDialog):
    """摄像头矫正设置弹窗 - 默认全局启用"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("摄像头矫正")
        self.resize(400, 280)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # 信息显示
        info_text = (
            "摄像头矫正功能\n\n"
            "当前状态:全局启用\n\n"
            "说明:\n"
            "• 自动校正摄像头畸变和失真\n"
            "• 支持手动标定模式\n"
            "• 用于提升画面质量"
        )
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        layout.addStretch(1)

        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)


class PreviewLabel(QLabel):
    double_clicked = pyqtSignal()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class FullscreenPreviewWindow(QDialog):
    closed = pyqtSignal()

    def __init__(self, owner) -> None:
        super().__init__(owner)
        self.owner = owner
        self._pixmap: QPixmap | None = None
        self.setWindowTitle("全屏预览")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setStyleSheet("background: #000000;")
        self.setFocusPolicy(Qt.StrongFocus)

        self.video_label = QLabel("暂无摄像头预览画面", self)
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("color: #d1d5db; background: #000000; font-size: 24px;")

        self.status_overlay = QLabel(self)
        self.status_overlay.setStyleSheet(
            "color: white; background: rgba(0, 0, 0, 150); "
            "padding: 12px 16px; font-size: 20px; font-weight: 600;"
        )
        self.status_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.exit_hint = QLabel("按 Esc 退出全屏", self)
        self.exit_hint.setAlignment(Qt.AlignCenter)
        self.exit_hint.setStyleSheet(
            "color: white; background: rgba(0, 0, 0, 130); "
            "padding: 8px 14px; font-size: 16px;"
        )
        self.exit_hint.setAttribute(Qt.WA_TransparentForMouseEvents)

    def set_preview_pixmap(self, pixmap: QPixmap | None) -> None:
        self._pixmap = QPixmap(pixmap) if pixmap is not None and not pixmap.isNull() else None
        self._refresh_pixmap()

    def set_status_text(self, text: str) -> None:
        self.status_overlay.setText(text)
        self.status_overlay.adjustSize()
        self._position_overlays()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.video_label.setGeometry(self.rect())
        self._refresh_pixmap()
        self._position_overlays()

    def mouseDoubleClickEvent(self, event) -> None:
        self.close()
        event.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Escape, Qt.Key_F11):
            self.close()
            event.accept()
            return

        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.owner.on_tracking_entered()
            event.accept()
            return

        if event.key() == Qt.Key_Backspace:
            self.owner.scan_input.backspace()
            event.accept()
            return

        text = event.text()
        if text and text.isprintable() and not (event.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
            self.owner.scan_input.insert(text)
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self.closed.emit()
        super().closeEvent(event)

    def _refresh_pixmap(self) -> None:
        if self._pixmap is None:
            self.video_label.clear()
            self.video_label.setText("暂无摄像头预览画面")
            return
        self.video_label.setPixmap(
            self._pixmap.scaled(self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def _position_overlays(self) -> None:
        margin = 24
        self.status_overlay.move(margin, margin)
        self.exit_hint.adjustSize()
        self.exit_hint.move(
            max(margin, (self.width() - self.exit_hint.width()) // 2),
            max(margin, self.height() - self.exit_hint.height() - margin),
        )


class ShippingMonitorWindow(QMainWindow):
    shared_storage_update = pyqtSignal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.config = None
        self.recordings_dir = DEFAULT_RECORDINGS_DIR
        self.license_error: str | None = None
        self.camera: CameraManager | None = None
        self.recorder: RecordingManager | None = None
        self.excel_manager: ExcelManager | None = None
        self.last_video_path: Path | None = None
        self.current_label_image_path: Path | None = None
        self.last_scan_monotonic: float | None = None
        self.frame_failure_count = 0
        self.watchdog_retry_attempt = 0
        self.watchdog_reconnecting = False
        self.previous_motion_gray = None
        self.frame_idle_started_at: float | None = None
        self.frame_idle_seconds = 0
        self.frame_motion_diff = 0.0
        self.frame_is_static = False
        self.retention_cleanup_ran = False
        self._license_warning_shown = False
        self._recording_auth_warning_shown = False
        self._recording_auth_session_cache = None
        self.runtime_log_path = self._initialize_runtime_log_file()
        self.recent_tracking_records: list[tuple[str, str, str]] = []
        self.last_tracking_number: str | None = None
        self.completed_tracking_numbers: set[str] = set()
        self.tracking_last_seen: dict[str, float] = {}
        self.latest_preview_pixmap: QPixmap | None = None
        self.latest_label_source_frame = None
        self.fullscreen_preview_window: FullscreenPreviewWindow | None = None
        self.lan_query_server: LanQueryServer | None = None
        self.lan_query_access_url = ""
        self._shared_copy_scheduled: set[str] = set()
        self._shared_copy_lock = threading.Lock()
        self.last_known_good_camera_config: dict[str, object] | None = None
        self._camera_settings_source = "user config"
        self._selected_camera_profile: dict[str, object] | None = None
        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(PREVIEW_INTERVAL_MS)
        self.preview_timer.timeout.connect(self.update_preview_frame)
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(1000)
        self.status_timer.timeout.connect(self.update_runtime_status)

        self.setWindowTitle(f"{__project_name__} v{__version__} (Build {__build__})")
        self.resize(1200, 760)
        self._build_ui()
        self.shared_storage_update.connect(self._on_shared_storage_update)
        self._create_menu_bar()
        self.add_log(f"GUI\u5df2\u542f\u52a8\uff0c\u5f53\u524d\u4e3a{release_channel}")
        self.load_config_and_license()
        self.update_recording_experience_status()
        self.status_timer.start()
        QTimer.singleShot(0, self.show_license_startup_notice)

        # 条码扫描器（摄像头条码识别）
        self.barcode_scanner = BarcodeScanner()

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)

        self.preview_area = PreviewLabel(TEXT["preview_placeholder"])
        self.preview_area.setAlignment(Qt.AlignCenter)
        self.preview_area.setMinimumSize(760, 430)
        self.preview_area.setFrameShape(QFrame.StyledPanel)
        self.preview_area.setStyleSheet(
            "QLabel { background: #111827; color: #e5e7eb; font-size: 22px; border-radius: 6px; }"
        )
        self.preview_area.double_clicked.connect(self.toggle_fullscreen_preview)
        content_layout.addWidget(self.preview_area, stretch=3)

        # Right side: fixed width, no scroll area
        side_widget = QWidget()
        side_panel = QVBoxLayout(side_widget)
        side_panel.setContentsMargins(0, 0, 0, 0)
        side_panel.setSpacing(6)
        side_panel.addWidget(self._create_status_panel())
        side_panel.addWidget(self._create_input_panel())
        side_panel.addWidget(self._create_recent_tracking_panel())
        side_panel.addWidget(self._create_button_panel())
        side_panel.addStretch(1)

        side_widget.setMinimumWidth(300)
        side_widget.setMaximumWidth(340)
        content_layout.addWidget(side_widget, stretch=1)

        root_layout.addLayout(content_layout, stretch=4)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(120)
        self.log_box.setMaximumHeight(160)
        self.log_box.setPlaceholderText(TEXT["log_placeholder"])
        root_layout.addWidget(self.log_box, stretch=0)
        self._apply_responsive_fonts()

    def _create_menu_bar(self) -> None:
        # 防止 Windows 原生菜单栏接管导致点击无响应
        self.menuBar().setNativeMenuBar(False)
        # --- 视图菜单 ---
        view_menu = self.menuBar().addMenu("\u89c6\u56fe")
        compact_action = QAction("\u7b80\u6d01\u6a21\u5f0f", self)
        compact_action.triggered.connect(lambda: self.set_compact_mode(True))
        log_action = QAction("\u663e\u793a/\u9690\u85cf\u65e5\u5fd7\u9762\u677f", self)
        log_action.triggered.connect(self.toggle_log_panel)
        advanced_action = QAction("\u9ad8\u7ea7\u72b6\u6001\u8be6\u60c5", self)
        advanced_action.triggered.connect(self.show_advanced_status_dialog)
        fullscreen_action = QAction("\u5168\u5c4f\u9884\u89c8", self)
        fullscreen_action.setShortcut("F11")
        fullscreen_action.triggered.connect(self.toggle_fullscreen_preview)
        for action in (compact_action, log_action, advanced_action, fullscreen_action):
            view_menu.addAction(action)

        # --- 设置菜单：打开配置编辑 + 摄像头矫正 ---
        self.settings_menu = self.menuBar().addMenu("\u8bbe\u7f6e")
        self.config_edit_action = QAction("\u6253\u5f00\u914d\u7f6e\u7f16\u8f91", self)
        self.config_edit_action.triggered.connect(self.on_config_clicked)
        self.settings_menu.addAction(self.config_edit_action)
        self.camera_calibration_action = QAction("\u6444\u50cf\u5934\u77eb\u6b63", self)
        self.camera_calibration_action.triggered.connect(self.on_camera_calibration_clicked)
        self.settings_menu.addAction(self.camera_calibration_action)
        # 摄像头条码识别开关（待升级，强制禁用）
        self.barcode_scan_action = QAction('摄像头条码识别（待升级）', self)
        self.barcode_scan_action.setEnabled(False)
        self.barcode_scan_action.setToolTip(
            "该功能待升级，当前建议使用扫码枪或手动输入物流单号。")
        self.settings_menu.addAction(self.barcode_scan_action)

        # --- 工具菜单 ---
        self.erp_menu = self.menuBar().addMenu("数据 / ERP")
        self.open_erp_template_action = QAction("打开 ERP 导入模板", self)
        self.open_erp_template_action.triggered.connect(self.open_erp_import_template)
        self.import_erp_action = QAction("导入 ERP 订单", self)
        self.import_erp_action.triggered.connect(self.import_erp_orders_from_main)
        self.export_erp_action = QAction("导出 ERP 留证结果", self)
        self.export_erp_action.triggered.connect(self.export_erp_results_from_main)
        self.erp_menu.addAction(self.open_erp_template_action)
        self.erp_menu.addAction(self.import_erp_action)
        self.erp_menu.addAction(self.export_erp_action)

        self.tools_menu = self.menuBar().addMenu("\u5de5\u5177")
        self.query_action = QAction("\u67e5\u8be2\u8bb0\u5f55", self)
        self.query_action.triggered.connect(self.on_query_clicked)
        self.recordings_action = QAction("\u6253\u5f00\u5f55\u50cf\u76ee\u5f55", self)
        self.recordings_action.triggered.connect(self.on_open_recordings_clicked)
        self.export_today_action = QAction("\u5bfc\u51fa\u5f53\u5929\u8bb0\u5f55", self)
        self.export_today_action.triggered.connect(self.export_today_records)
        self.deps_action = QAction("\u68c0\u67e5\u4f9d\u8d56", self)
        self.deps_action.triggered.connect(self.check_dependencies_from_menu)
        self.log_file_action = QAction("\u67e5\u770b\u65e5\u5fd7", self)
        self.log_file_action.triggered.connect(self.open_log_file)
        self.start_lan_query_action = QAction("启动局域网查询", self)
        self.start_lan_query_action.triggered.connect(self.start_lan_query_server)
        self.stop_lan_query_action = QAction("停止局域网查询", self)
        self.stop_lan_query_action.triggered.connect(self.stop_lan_query_server)
        self.copy_lan_query_url_action = QAction("复制局域网访问地址", self)
        self.copy_lan_query_url_action.triggered.connect(self.copy_lan_query_access_url)
        self.stop_lan_query_action.setEnabled(False)
        self.copy_lan_query_url_action.setEnabled(False)
        self.license_action = QAction("授权 / 激活", self)
        self.license_action.triggered.connect(self.on_license_activation_clicked)
        self.about_action = QAction("\u5173\u4e8e", self)
        self.about_action.triggered.connect(self.show_about_dialog)
        for action in (
            self.query_action,
            self.recordings_action,
            self.export_today_action,
            self.deps_action,
            self.log_file_action,
            self.license_action,
            self.about_action,
        ):
            self.tools_menu.addAction(action)
        self.tools_menu.addSeparator()
        self.tools_menu.addAction(self.start_lan_query_action)
        self.tools_menu.addAction(self.stop_lan_query_action)
        self.tools_menu.addAction(self.copy_lan_query_url_action)
        print("DEBUG: _create_menu_bar completed - tools_menu has", self.tools_menu.actions().__len__(), "actions")

    def set_compact_mode(self, compact: bool = True) -> None:
        self.add_log("\u5df2\u5207\u6362\u5230\u7b80\u6d01\u6a21\u5f0f" if compact else "\u5df2\u5207\u6362\u5230\u8be6\u7ec6\u6a21\u5f0f")

    def toggle_log_panel(self) -> None:
        self.log_box.setVisible(not self.log_box.isVisible())

    def toggle_fullscreen_preview(self) -> None:
        if self.fullscreen_preview_window is not None:
            self.fullscreen_preview_window.close()
            return

        window = FullscreenPreviewWindow(self)
        window.closed.connect(self._on_fullscreen_preview_closed)
        window.set_preview_pixmap(self.latest_preview_pixmap)
        window.set_status_text(self._fullscreen_status_text())
        self.fullscreen_preview_window = window
        window.showFullScreen()
        window.activateWindow()
        window.setFocus()

    def _on_fullscreen_preview_closed(self) -> None:
        window = self.fullscreen_preview_window
        self.fullscreen_preview_window = None
        if window is not None:
            window.deleteLater()
        if hasattr(self, "scan_input"):
            self.scan_input.setFocus()

    def show_about_dialog(self) -> None:
        try:
            try:
                status = configured_license_status(getattr(self, "config", None))
                license_lines = [
                    f"授权状态：{license_status_display(status)}",
                    f"客户名称：{status.customer or '—'}",
                    f"授权类型：{status.edition or '—'}",
                    f"到期时间：{license_expiry_display(status)}",
                ]
            except Exception:  # noqa: BLE001
                license_lines = [
                    "授权状态：读取失败",
                    "客户名称：—",
                    "授权类型：—",
                    "到期时间：—",
                ]
            msg = (
                f"{__project_name__}\n"
                f"版本：{__version__}\n"
                f"构建：{__build__}\n"
                f"{__copyright__}\n\n"
                + "\n".join(license_lines)
                + f"\n\n售后微信：{SUPPORT_WECHAT}\n售后邮箱：{SUPPORT_EMAIL}"
            )
            QMessageBox.about(self, f"关于 {__project_name__}", msg)
            self.add_log("DEBUG: About dialog opened")
            return
            msg = f"""{__project_name__}\n版本：{__version__}\n构建：{__build__}\n{__copyright__}"""
            QMessageBox.about(self, f"关于 {__project_name__}", msg)
            self.add_log("DEBUG: About dialog opened")
        except Exception as e:
            self.add_log(f"ERROR: Failed to open About dialog: {e}")

    def on_license_activation_clicked(self) -> None:
        LicenseActivationDialog(self).exec_()

    def _is_smoke_test_mode(self) -> bool:
        return any(arg.startswith("--smoke-test") for arg in sys.argv)

    def _get_cached_recording_authorization(self):
        cache = self._recording_auth_session_cache
        if not cache or not cache.get("allowed"):
            return None
        checked_at = cache.get("checked_at")
        if checked_at is None or datetime.now().astimezone() < checked_at:
            self._recording_auth_session_cache = None
            return None
        status = cache.get("status")
        expires_at = getattr(status, "expires_at", None)
        if expires_at:
            try:
                expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
                now = datetime.now(expiry.tzinfo) if expiry.tzinfo is not None else datetime.now()
                if now >= expiry:
                    self._recording_auth_session_cache = None
                    return None
            except (TypeError, ValueError):
                self._recording_auth_session_cache = None
                return None
        return status

    def ensure_recording_authorized(
        self,
        prompt_for_activation: bool,
        popup_once: bool = False,
        use_session_cache: bool = False,
    ) -> bool:
        if use_session_cache:
            cached_status = self._get_cached_recording_authorization()
            if cached_status is not None:
                self.add_log("trial_check_source=session_cache")
                self.license_status.setText(license_status_display(cached_status))
                return True
        self.add_log("trial_check_source=fresh_check")
        try:
            start_trial = bool(prompt_for_activation and not self._is_smoke_test_mode())
            allowed, reason, status = is_recording_allowed(
                start_trial=start_trial,
                trial_enabled=bool(getattr(self.config, "auto_trial_enabled", True)),
                trial_days=int(getattr(self.config, "auto_trial_days", 30)),
            )
        except Exception as exc:  # noqa: BLE001
            allowed = False
            reason = "授权状态读取失败，请重新激活或联系供应商。"
            self.add_log(f"授权状态读取失败：{exc}")
            status = None
        if allowed:
            self._recording_auth_session_cache = {
                "allowed": True,
                "status": status,
                "checked_at": datetime.now().astimezone(),
            }
            self.license_status.setText(license_status_display(status))
            if getattr(status, "status", "") == "trial_valid":
                days_left = getattr(status, "trial_days_remaining", 0) or 0
                if bool(getattr(status, "payload", {}) and status.payload.get("_just_started")):
                    message = f"\u5df2\u81ea\u52a8\u5f00\u542f {getattr(self.config, 'auto_trial_days', 30)} \u5929\u514d\u8d39\u8bd5\u7528\u3002"
                    self.add_log(message)
                    if not self._is_smoke_test_mode():
                        QMessageBox.information(self, "\u8f6f\u4ef6\u8bd5\u7528", message)
                else:
                    self.add_log(f"\u8bd5\u7528\u5269\u4f59 {days_left} \u5929\u3002")
            return True

        self._recording_auth_session_cache = None
        self.play_sound_hint("auth_problem")
        self.add_log(f"授权无效，已阻止录像：{reason}")
        if self._is_smoke_test_mode():
            status_text = getattr(status, "status", "read_failed")
            print(f"smoke_recording_authorization_blocked => {status_text}: {reason}")
            return False

        if prompt_for_activation:
            reply = QMessageBox.question(
                self,
                "软件授权",
                (
                    f"当前授权无法开始录像。\n{reason}\n"
                    "请复制机器码发送给供应商获取授权码。\n"
                    f"售后微信：{SUPPORT_WECHAT}\n\n是否打开授权窗口？"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self.on_license_activation_clicked()
            return False

        if popup_once and self._recording_auth_warning_shown:
            return False
        self._recording_auth_warning_shown = True
        QMessageBox.warning(self, "软件授权", f"授权无效，已阻止录像。\n{reason}")
        return False

    def show_license_startup_notice(self) -> None:
        if self._license_warning_shown or self._is_smoke_test_mode():
            return
        try:
            status = configured_license_status(getattr(self, "config", None))
        except Exception as exc:  # noqa: BLE001
            self.add_log(f"授权状态读取失败：{exc}")
            return

        if status.status == "trial_available":
            self.add_log("\u5f53\u524d\u672a\u6fc0\u6d3b\uff0c\u53ef\u514d\u8d39\u8bd5\u7528 30 \u5929\uff1b\u9996\u6b21\u70b9\u51fb\u201c\u5f00\u59cb\u201d\u65f6\u624d\u5f00\u59cb\u8ba1\u65f6\u3002")
            return
        if status.status == "trial_valid":
            self.add_log(f"\u8bd5\u7528\u5269\u4f59 {status.trial_days_remaining or 0} \u5929\u3002")
            return
        if status.status == "trial_expired":
            self._license_warning_shown = True
            QMessageBox.warning(
                self,
                "\u8f6f\u4ef6\u8bd5\u7528",
                "\u8bd5\u7528\u5df2\u5230\u671f\uff0c\u8bf7\u8054\u7cfb\u4f9b\u5e94\u5546\u6fc0\u6d3b\u3002\u67e5\u8be2\u3001\u5bfc\u51fa\u548c\u6388\u6743\u6fc0\u6d3b\u4ecd\u53ef\u4f7f\u7528\u3002",
            )
            return
        if status.status == "trial_time_error":
            self._license_warning_shown = True
            QMessageBox.warning(
                self,
                "\u8f6f\u4ef6\u8bd5\u7528",
                "\u68c0\u6d4b\u5230\u7cfb\u7edf\u65f6\u95f4\u5f02\u5e38\uff0c\u8bf7\u6821\u51c6\u7535\u8111\u65f6\u95f4\u540e\u91cd\u8bd5\u3002",
            )
            return
        if status.status == "state_missing":
            self.add_log("当前软件未激活，开始录像前将要求授权。")
            return
        if status.status == "time_error":
            self._license_warning_shown = True
            QMessageBox.warning(self, "软件授权", "检测到系统时间异常，请校准电脑时间。当前将限制开始录像。")
            return
        if status.status == "expired":
            self._license_warning_shown = True
            QMessageBox.warning(
                self,
                "软件授权",
                "授权已过期，软件进入受限模式。可以查询和导出历史记录，但不能开始新录像。",
            )
            return
        if not status.ok or status.edition == "permanent" or not status.expires_at:
            return

        try:
            expiry = datetime.fromisoformat(str(status.expires_at).replace("Z", "+00:00"))
            current = datetime.now(expiry.tzinfo) if expiry.tzinfo is not None else datetime.now()
            seconds_left = (expiry - current).total_seconds()
        except Exception as exc:  # noqa: BLE001
            self.add_log(f"授权到期时间读取失败：{exc}")
            return
        if seconds_left < 0:
            return

        days_left = int(seconds_left // (24 * 60 * 60))
        if 3 < days_left <= 7:
            self._license_warning_shown = True
            QMessageBox.information(
                self,
                "软件授权",
                f"试用授权将在 {days_left} 天后到期，请及时联系供应商续期。",
            )
        elif 0 <= days_left <= 3:
            self._license_warning_shown = True
            QMessageBox.warning(
                self,
                "软件授权",
                f"试用授权将在 {days_left} 天后到期，到期后将无法开始新录像。",
            )

    def _show_camera_calibration(self) -> None:
        """打开摄像头矫正设置弹窗"""
        print("DEBUG: _show_camera_calibration triggered")
        self.add_log("DEBUG: 摄像头矫正菜单点击")
        dialog = CameraCalibrationDialog(self)
        dialog.exec_()

    def on_camera_calibration_clicked(self) -> None:
        """打开摄像头矫正设置对话框（使用 dialogs.camera_calibration_dialog 模块）"""
        try:
            if CameraCalibrationSettingsDialog is None:
                QMessageBox.warning(self, "摄像头矫正", "摄像头矫正模块加载失败")
                return
            previous_settings = self._camera_settings_snapshot(self.config)
            was_previewing = bool(
                self.camera is not None
                and self.camera.is_opened()
                and self.preview_timer.isActive()
            )
            dialog = CameraCalibrationSettingsDialog(
                RUNTIME_CONFIG,
                EXAMPLE_CONFIG,
                self,
            )
            if dialog.exec_() != QDialog.Accepted:
                return
            self.config = get_config()
            normalized = self._normalized_camera_settings(self._camera_settings_snapshot(self.config))
            self._write_camera_settings(normalized)
            self.config = get_config()
            changed_fields = sorted(
                key for key, value in normalized.items()
                if previous_settings.get(key) != value
            )
            self.add_log(
                "camera settings saved: "
                f"changed_fields={','.join(changed_fields) if changed_fields else 'none'}, "
                f"focus_mode={'autofocus' if self.config.camera_autofocus_enabled else 'manual'}"
            )

            if was_previewing:
                self.stop_preview()
                QApplication.processEvents()
                time.sleep(0.5)
                self._camera_settings_source = "user config"
                self.on_start_clicked()
                applied = self.camera is not None and self.camera.is_opened()
            else:
                applied = self._probe_camera_settings(self.config, "user config")

            if applied:
                self.last_known_good_camera_config = self._camera_settings_snapshot(self.config)
                self._persist_last_known_good_camera_config(self.last_known_good_camera_config)
                self.add_log("camera settings apply success")
                if not was_previewing:
                    self.add_log("camera settings validated; preview remains stopped")
                return

            self.add_log("camera settings apply failed")
            rollback = self.last_known_good_camera_config or previous_settings
            self.add_log("rollback to last known good")
            self._write_camera_settings(rollback)
            self.config = get_config()
            if was_previewing:
                QApplication.processEvents()
                time.sleep(0.5)
                self._camera_settings_source = "rollback"
                self.on_start_clicked()
                rollback_ok = self.camera is not None and self.camera.is_opened()
            else:
                rollback_ok = self._probe_camera_settings(self.config, "rollback")
            self.add_log(f"rollback open {'success' if rollback_ok else 'failed'}")
            if not rollback_ok:
                QMessageBox.warning(
                    self,
                    "摄像头设置",
                    "新设置应用失败，回滚后摄像头仍无法打开。请使用“恢复默认摄像头设置”后重试。",
                )
        except Exception as e:
            self.add_log(f"ERROR: on_camera_calibration_clicked 异常: {e}")
            import traceback
            traceback.print_exc()
            self.add_log("on_start_clicked end")

    @staticmethod
    def _camera_settings_snapshot(config) -> dict[str, object]:
        keys = (
            "camera_index",
            "camera_backend",
            "camera_fourcc_preference",
            "resolution",
            "fps",
            "resolution_policy",
            "recording_writer_codec",
            "enable_lens_correction",
            "camera_calibration_enabled",
            "camera_calibration_brightness",
            "camera_calibration_contrast",
            "camera_calibration_roi_enabled",
            "camera_calibration_roi_x",
            "camera_calibration_roi_y",
            "camera_calibration_roi_w",
            "camera_calibration_roi_h",
            "camera_focus_enabled",
            "camera_focus_value",
            "camera_autofocus_enabled",
        )
        return {key: getattr(config, key) for key in keys}

    @staticmethod
    def _normalized_camera_settings(settings: dict[str, object]) -> dict[str, object]:
        normalized = dict(settings)
        autofocus = bool(normalized.get("camera_autofocus_enabled", True))
        manual = bool(normalized.get("camera_focus_enabled", False))
        if autofocus:
            manual = False
        normalized["camera_autofocus_enabled"] = autofocus
        normalized["camera_focus_enabled"] = manual
        normalized["camera_focus_value"] = max(
            0, min(255, int(normalized.get("camera_focus_value", 0)))
        )
        normalized["camera_calibration_brightness"] = max(
            -50, min(50, int(normalized.get("camera_calibration_brightness", 0)))
        )
        normalized["camera_calibration_contrast"] = max(
            -50, min(50, int(normalized.get("camera_calibration_contrast", 0)))
        )
        return normalized

    @staticmethod
    def _write_camera_settings(settings: dict[str, object]) -> None:
        with RUNTIME_CONFIG.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        raw.update(settings)
        temporary = RUNTIME_CONFIG.with_name(f"{RUNTIME_CONFIG.name}.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(raw, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(RUNTIME_CONFIG)

    @staticmethod
    def _load_last_known_good_camera_config() -> dict[str, object] | None:
        try:
            with RUNTIME_CONFIG.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
            value = raw.get("last_known_good_camera_config")
            return dict(value) if isinstance(value, dict) else None
        except (OSError, ValueError, TypeError):
            return None

    @staticmethod
    def _persist_last_known_good_camera_config(settings: dict[str, object]) -> None:
        with RUNTIME_CONFIG.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        raw["last_known_good_camera_config"] = dict(settings)
        temporary = RUNTIME_CONFIG.with_name(f"{RUNTIME_CONFIG.name}.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(raw, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(RUNTIME_CONFIG)

    def _probe_camera_settings(self, config, settings_source: str) -> bool:
        camera = CameraManager(
            config.camera_index,
            config.resolution_size,
            config.fps,
            self.recordings_dir,
            enable_lens_correction=config.enable_lens_correction,
            camera_focus_enabled=config.camera_focus_enabled,
            camera_focus_value=config.camera_focus_value,
            camera_autofocus_enabled=config.camera_autofocus_enabled,
            settings_source=settings_source,
            preferred_backend=getattr(config, "camera_backend", "DirectShow"),
            fourcc_preference=getattr(config, "camera_fourcc_preference", "MJPG"),
            log_callback=self.add_log,
        )
        try:
            return camera.open()
        finally:
            camera.release()

    def reset_camera_settings_to_defaults(self) -> None:
        if self.config is None:
            return
        previous_settings = self._camera_settings_snapshot(self.config)
        defaults = dict(previous_settings)
        defaults.update(
            {
                "camera_index": 0,
                "camera_backend": "DirectShow",
                "camera_fourcc_preference": "MJPG",
                "resolution": "1920x1080",
                "fps": 16,
                "resolution_policy": "config_first",
                "recording_writer_codec": "MJPG",
                "enable_lens_correction": True,
                "camera_calibration_enabled": True,
                "camera_calibration_brightness": 0,
                "camera_calibration_contrast": 0,
                "camera_calibration_roi_enabled": False,
                "camera_calibration_roi_x": 0,
                "camera_calibration_roi_y": 0,
                "camera_calibration_roi_w": 0,
                "camera_calibration_roi_h": 0,
                "camera_focus_enabled": False,
                "camera_focus_value": 0,
                "camera_autofocus_enabled": True,
            }
        )
        was_previewing = bool(
            self.camera is not None
            and self.camera.is_opened()
            and self.preview_timer.isActive()
        )
        self._write_camera_quality_cache(None)
        self._selected_camera_profile = None
        self.add_log("camera_quality_cache_cleared: reason=reset_defaults")
        self._write_camera_settings(defaults)
        self.config = get_config()
        self.add_log("camera settings reset to defaults")
        if was_previewing:
            self.stop_preview()
            QApplication.processEvents()
            time.sleep(0.5)
            self._camera_settings_source = "reset defaults"
            self.on_start_clicked()
            opened = self.camera is not None and self.camera.is_opened()
        else:
            opened = self._probe_camera_settings(self.config, "reset defaults")
        if opened:
            self.last_known_good_camera_config = self._camera_settings_snapshot(self.config)
            self._persist_last_known_good_camera_config(self.last_known_good_camera_config)
            self.add_log("camera settings reset open success")
            QMessageBox.information(self, "摄像头设置", "默认摄像头设置已恢复并验证成功。")
            return
        self.add_log("camera settings reset open failed")
        self._write_camera_settings(previous_settings)
        self.config = get_config()
        QMessageBox.warning(
            self,
            "摄像头设置",
            "默认设置仍无法打开摄像头，已恢复修改前配置。请检查 USB 端口、驱动或摄像头占用。",
        )

    def on_barcode_scan_toggled(self, checked: bool) -> None:
        """设置菜单：启用/禁用摄像头条码识别"""
        if self.config is None:
            return
        self.config = replace(self.config, barcode_scan_enabled=checked)
        # 保存到配置文件
        try:
            import json, dataclasses
            with open(RUNTIME_CONFIG, 'w', encoding='utf-8') as f:
                json.dump(dataclasses.asdict(self.config), f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.add_log(f"保存配置失败: {e}")
        status = "启用（待升级）" if checked else "禁用"
        self.add_log(f"摄像头条码识别已{status}")
        # 同步到 recorder
        if self.recorder is not None:
            self.recorder._config = self.config

    def show_advanced_status_dialog(self) -> None:
        if self.config is None:
            QMessageBox.information(self, TEXT["status_panel"], TEXT["config_failed"])
            return
        lines = [
            f"{TEXT['auto_stop_status']} {self.auto_stop_status.text()}",
            f"{TEXT['watchdog_status']} {self.watchdog_status.text()}",
            f"{TEXT['frame_failures']} {self.frame_failures_status.text()}",
            f"{TEXT['min_disk']} {self.min_disk_status.text()}",
            f"{TEXT['duplicate_policy_status']} {self.duplicate_policy_status.text()}",
            f"{TEXT['configured_resolution_fps']} {self.configured_resolution_status.text()}",
            f"{TEXT['actual_fps']} {self.actual_fps_status.text()}",
            f"{TEXT['lens_correction']} {self.lens_correction_status.text()}",
            f"\u753b\u9762\u53d8\u5316\u5dee\u503c\uff1a{self.frame_motion_diff:.2f}",
            f"\u753b\u9762\u9759\u6b62\u68c0\u6d4b\uff1a"
            f"{TEXT['enabled'] if self.config.frame_idle_detection_enabled else TEXT['disabled']}",
            f"\u9759\u6b62\u8d85\u65f6\uff1a{self.config.frame_idle_timeout} \u79d2",
            f"\u53d8\u5316\u9608\u503c\uff1a{self.config.frame_motion_threshold}",
            f"MP4 folder: {self.config.mp4_output_folder}",
            f"MP4 on query: {self.config.generate_mp4_on_query}",
        ]
        QMessageBox.information(self, "\u9ad8\u7ea7\u72b6\u6001\u8be6\u60c5", "\n".join(lines))

    def export_today_records(self) -> None:
        if self.config is None:
            QMessageBox.warning(self, TEXT["query_title"], TEXT["config_failed"])
            return
        today = datetime.now().strftime("%Y-%m-%d")
        query = QueryManager(self.config.excel_path, self.config.mp4_output_folder)
        results = query.search_by_date_range(today, today)
        target = Path("reports") / f"query_results_{today}.xlsx"
        query.export_excel(results, target)
        self.add_log(f"\u5df2\u5bfc\u51fa\u5f53\u5929\u8bb0\u5f55\uff1a{target}")
        QMessageBox.information(self, TEXT["export_excel"], f"\u5df2\u5bfc\u51fa\uff1a{target}")

    def check_dependencies_from_menu(self) -> None:
        lines = ["依赖检查结果：", f"[OK] 运行模式：{'frozen EXE' if getattr(sys, 'frozen', False) else 'source'}"]
        for label, module_name in (
            ("PyQt5", "PyQt5"),
            ("OpenCV", "cv2"),
            ("openpyxl", "openpyxl"),
            ("numpy", "numpy"),
            ("cryptography", "cryptography"),
        ):
            lines.append(f"[OK] {label}" if self._module_available(module_name) else f"[FAIL] {label} 不可用")

        if self._module_available("pyzbar"):
            lines.append("[OK] pyzbar")
        else:
            lines.append("[WARN] pyzbar 不可用，摄像头条码识别待升级，不影响扫码枪/手动输入")

        ffmpeg_path = find_ffmpeg_executable(logger=self.add_log)
        if ffmpeg_path is None:
            lines.append("[WARN] FFmpeg 未找到，MP4 将使用 OpenCV mp4v 回退")
        else:
            lines.append(f"[OK] FFmpeg：{ffmpeg_path}")

        lines.append(self._recordings_dependency_line())
        lines.append(f"[OK] config.json：{RUNTIME_CONFIG}" if RUNTIME_CONFIG.exists() else f"[FAIL] config.json 不存在：{RUNTIME_CONFIG}")

        license_state = RUNTIME_CONFIG.parent / "license_state.json"
        if license_state.exists():
            lines.append(f"[OK] 授权状态文件：{license_state}")
        else:
            lines.append("[INFO] 授权状态文件不存在：当前未授权或尚未激活")

        if platform.system() == "Windows" and winsound is not None:
            lines.append("[OK] 声音播报：Windows 系统提示音")
        else:
            lines.append("[INFO] 声音播报：当前平台不支持 winsound")

        lines.extend(self._release_sensitive_dependency_lines())
        self.add_log("工具菜单已显示依赖检查结果")
        QMessageBox.information(self, "检查依赖", "\n".join(lines))

    def open_log_file(self) -> None:
        log_path = self._initialize_runtime_log_file()
        self.runtime_log_path = log_path
        self.add_log(f"工具菜单打开运行日志：{log_path}")
        try:
            os.startfile(str(log_path.resolve()))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "查看日志", f"无法打开日志文件：\n{log_path}\n\n{exc}")

    @staticmethod
    def _module_available(module_name: str) -> bool:
        try:
            return importlib.util.find_spec(module_name) is not None
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _runtime_log_path() -> Path:
        return runtime_root() / "logs" / "ShippingMonitorGUI.log"

    def _initialize_runtime_log_file(self) -> Path:
        log_path = self._runtime_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if not log_path.exists() or log_path.stat().st_size == 0:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write("Log file initialized.\n")
        return log_path

    def _append_runtime_log(self, line: str) -> None:
        try:
            log_path = getattr(self, "runtime_log_path", None) or self._initialize_runtime_log_file()
            with Path(log_path).open("a", encoding="utf-8") as handle:
                handle.write(f"{line}\n")
        except Exception:  # noqa: BLE001
            return

    def _recordings_dependency_line(self) -> str:
        target = Path(getattr(self, "recordings_dir", DEFAULT_RECORDINGS_DIR))
        try:
            target.mkdir(parents=True, exist_ok=True)
            writable = os.access(target, os.W_OK)
        except Exception as exc:  # noqa: BLE001
            return f"[FAIL] 录像目录不可用：{target} ({exc})"
        return f"[OK] 录像目录可写：{target}" if writable else f"[FAIL] 录像目录不可写：{target}"

    @staticmethod
    def _release_sensitive_dependency_lines() -> list[str]:
        root = runtime_root()
        found = [
            path
            for path in (
                root / "private_key_prod.pem",
                root / "private_key_dev.pem",
                root / "license_code_generator.py",
                root / "issued_licenses.csv",
                root / "tools" / "license_keys" / "private_key_prod.pem",
                root / "tools" / "license_keys" / "private_key_dev.pem",
                root / "tools" / "license_code_generator.py",
                root / "tools" / "issued_licenses.csv",
                root / "_internal" / "private_key_prod.pem",
                root / "_internal" / "private_key_dev.pem",
                root / "_internal" / "license_code_generator.py",
                root / "_internal" / "issued_licenses.csv",
                root / "_internal" / "tools" / "license_keys" / "private_key_prod.pem",
                root / "_internal" / "tools" / "license_keys" / "private_key_dev.pem",
                root / "_internal" / "tools" / "license_code_generator.py",
                root / "_internal" / "tools" / "issued_licenses.csv",
            )
            if path.exists()
        ]
        if not found:
            return ["[OK] 未发现私钥或授权生成工具"]
        prefix = "[FAIL]" if getattr(sys, "frozen", False) else "[WARN]"
        return [f"{prefix} 运行目录发现发布敏感文件：{path}" for path in found]

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_fonts()

    def _apply_responsive_fonts(self) -> None:
        width = max(900, self.width())
        point_size = max(10, min(14, width // 130))
        for widget in self.findChildren(QWidget):
            font = widget.font()
            if font.pointSize() != point_size:
                font.setPointSize(point_size)
                widget.setFont(font)
        preview_font_px = max(18, min(28, width // 58))
        self.preview_area.setStyleSheet(
            "QLabel { background: #111827; color: #e5e7eb; "
            f"font-size: {preview_font_px}px; border-radius: 6px; }}"
        )

    def _create_status_panel(self) -> QGroupBox:
        group = QGroupBox(TEXT["status_panel"])
        layout = QGridLayout(group)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(3)

        # Initialize ALL status labels (needed by business logic elsewhere)
        self.current_tracking = QLabel(TEXT["not_scanned"])
        self.recording_status = QLabel(TEXT["not_started"])
        self.recording_duration_status = QLabel("00:00")
        self.recording_file_status = QLabel("暂无录像文件")
        self.excel_status = QLabel(TEXT["not_written"])
        self.disk_status = QLabel(TEXT["not_checked"])
        self.camera_status = QLabel(TEXT["not_started"])
        self.license_status = QLabel(TEXT["not_verified"])
        self.storage_path_status = QLabel(TEXT["not_loaded"])
        self.shared_storage_status = QLabel("\u5171\u4eab\u5b58\u50a8\u672a\u542f\u7528")
        self.auto_stop_status = QLabel(TEXT["not_loaded"])
        self.idle_countdown_status = QLabel("--")
        self.watchdog_status = QLabel(TEXT["not_loaded"])
        self.frame_failures_status = QLabel("0/0")
        self.min_disk_status = QLabel("--")
        self.duplicate_policy_status = QLabel(TEXT["not_loaded"])
        self.configured_resolution_status = QLabel(TEXT["not_loaded"])
        self.actual_resolution_status = QLabel("-- / --")
        self.actual_fps_status = QLabel("--")
        self.frame_motion_status = QLabel("--")
        self.lens_correction_status = QLabel(TEXT["off"])

        # Only show core fields in the panel
        core_rows = [
            (TEXT["current_tracking"], self.current_tracking),
            (TEXT["recording_status"], self.recording_status),
            ("已录制时长：", self.recording_duration_status),
            ("录像文件：", self.recording_file_status),
            (TEXT["camera_status"], self.camera_status),
            (TEXT["excel_status"], self.excel_status),
            (TEXT["disk_status"], self.disk_status),
            (TEXT["configured_resolution_fps"], self.configured_resolution_status),
            (TEXT["actual_resolution_fps"], self.actual_resolution_status),
            (TEXT["storage_path"], self.storage_path_status),
            ("\u5171\u4eab\u5b58\u50a8\uff1a", self.shared_storage_status),
            (TEXT["idle_countdown"], self.idle_countdown_status),
            (TEXT["frame_motion_status"], self.frame_motion_status),
        ]

        for row, (label_text, value_widget) in enumerate(core_rows):
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value_widget.setWordWrap(True)
            layout.addWidget(label, row, 0)
            layout.addWidget(value_widget, row, 1)

        return group

    def _create_input_panel(self) -> QGroupBox:
        group = QGroupBox(TEXT["scan_panel"])
        layout = QVBoxLayout(group)

        self.scan_input = QLineEdit()
        self.scan_input.setPlaceholderText(TEXT["input_placeholder"])
        self.scan_input.returnPressed.connect(self.on_tracking_entered)
        layout.addWidget(self.scan_input)

        return group

    def _create_recent_tracking_panel(self) -> QGroupBox:
        group = QGroupBox(TEXT["recent_tracking_panel"])
        layout = QVBoxLayout(group)

        self.recent_tracking_box = QTextEdit()
        self.recent_tracking_box.setReadOnly(True)
        self.recent_tracking_box.setMinimumHeight(90)
        self.recent_tracking_box.setMaximumHeight(120)
        layout.addWidget(self.recent_tracking_box)

        return group

    def _create_button_panel(self) -> QGroupBox:
        group = QGroupBox(TEXT["actions"])
        layout = QGridLayout(group)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(4)

        start_button = QPushButton(TEXT["start"])
        stop_button = QPushButton(TEXT["stop_preview"])
        query_button = QPushButton(TEXT["open_query"])
        recordings_button = QPushButton(TEXT["open_recordings"])
        current_video_button = QPushButton("打开当前录像")
        current_video_folder_button = QPushButton("打开当前录像文件夹")
        fullscreen_button = QPushButton("全屏预览")
        config_button = QPushButton(TEXT["open_config"])
        exit_button = QPushButton(TEXT["exit"])

        start_button.clicked.connect(self.on_start_clicked)
        stop_button.clicked.connect(self.on_stop_clicked)
        config_button.clicked.connect(self.on_config_clicked)
        query_button.clicked.connect(self.on_query_clicked)
        recordings_button.clicked.connect(self.on_open_recordings_clicked)
        current_video_button.clicked.connect(self.on_open_current_video_clicked)
        current_video_folder_button.clicked.connect(self.on_open_current_video_folder_clicked)
        fullscreen_button.clicked.connect(self.toggle_fullscreen_preview)
        exit_button.clicked.connect(self.close)

        for btn in (
            start_button,
            stop_button,
            query_button,
            recordings_button,
            current_video_button,
            current_video_folder_button,
            fullscreen_button,
            config_button,
            exit_button,
        ):
            btn.setMinimumHeight(30)

        layout.addWidget(start_button, 0, 0)
        layout.addWidget(stop_button, 0, 1)
        layout.addWidget(query_button, 1, 0)
        layout.addWidget(recordings_button, 1, 1)
        layout.addWidget(current_video_button, 2, 0)
        layout.addWidget(current_video_folder_button, 2, 1)
        layout.addWidget(fullscreen_button, 3, 0)
        layout.addWidget(config_button, 3, 1)
        layout.addWidget(exit_button, 4, 0, 1, 2)

        return group

    def load_config_and_license(self) -> None:
        try:
            self.config = get_config()
            self.last_known_good_camera_config = (
                self._load_last_known_good_camera_config()
                or self._camera_settings_snapshot(self.config)
            )
            self.recordings_dir = resolve_storage_path(self.config.storage_path)
            self.recordings_dir.mkdir(parents=True, exist_ok=True)
            self.storage_path_status.setText(str(self.recordings_dir))
            self.apply_config_status()
            self.add_log("\u914d\u7f6e\u8bfb\u53d6\u6210\u529f")
            self.add_log(f"storage_path resolved: {self.config.storage_path} -> {self.recordings_dir}")
            self.run_retention_cleanup_once()
            self.update_disk_status(log_event=True)
            self.init_excel_manager()
        except Exception as exc:
            self.config = None
            self.add_log(f"\u914d\u7f6e\u8bfb\u53d6\u5931\u8d25\uff1a{exc}")
            self.storage_path_status.setText(TEXT["config_failed"])
            self.disk_status.setText(TEXT["not_checked"])
            return

        try:
            self.license_status.setText(license_status_display(configured_license_status(self.config)))
        except Exception as exc:
            self.license_status.setText(TEXT["not_verified"])
            self.add_log(f"authorization status unavailable: {exc}")

    def apply_config_status(self) -> None:
        if self.config is None:
            return
        self.auto_stop_status.setText(TEXT["enabled"] if self.config.auto_stop_enabled else TEXT["disabled"])
        self.watchdog_status.setText(TEXT["enabled"] if self.config.watchdog_enabled else TEXT["disabled"])
        self.frame_failures_status.setText(f"0/{self.config.watchdog_max_failures}")
        self.min_disk_status.setText(f"{float(self.config.min_free_disk_gb):.2f} GB")
        self.duplicate_policy_status.setText(
            duplicate_policy_display(self.config.duplicate_policy, self.config.duplicate_block_seconds)
        )
        self.configured_resolution_status.setText(self._configured_resolution_fps_text())
        self.actual_resolution_status.setText("-- / --")
        self.actual_fps_status.setText("--")
        self.lens_correction_status.setText(
            TEXT["on"] if self.config.enable_lens_correction else TEXT["off"]
        )
        if bool(getattr(self.config, "shared_storage_enabled", False)):
            shared_path = str(getattr(self.config, "shared_storage_path", "") or "").strip()
            self.shared_storage_status.setText(shared_path or "\u5171\u4eab\u5b58\u50a8\u8def\u5f84\u672a\u914d\u7f6e")
            self.shared_storage_status.setToolTip(shared_path)
        else:
            self.shared_storage_status.setText("\u5171\u4eab\u5b58\u50a8\u672a\u542f\u7528")
            self.shared_storage_status.setToolTip("")
        self.idle_countdown_status.setText("--")

    def init_excel_manager(self) -> None:
        if self.config is None:
            return
        try:
            self.excel_manager = ExcelManager(self.config.excel_path)
            self.excel_status.setText(TEXT["not_written"])
            self.add_log(f"Excel \u521d\u59cb\u5316\u6210\u529f\uff1a{self.config.excel_path}")
        except Exception as exc:
            self.excel_manager = None
            self.excel_status.setText(TEXT["excel_failed"])
            self.add_log(f"Excel \u521d\u59cb\u5316\u5931\u8d25\uff1a{exc}")

    def run_retention_cleanup_once(self) -> None:
        if self.config is None or self.retention_cleanup_ran:
            return
        self.retention_cleanup_ran = True
        cleanup_old_recordings(self.recordings_dir, self.config.retention_days, logger=self.add_log)

    def update_disk_status(self, log_event: bool = False) -> bool:
        if self.config is None:
            return True

        try:
            free_gb = get_free_disk_gb(self.recordings_dir)
            if log_event:
                self.add_log(f"free disk GB: {free_gb:.2f}")
            if free_gb < float(self.config.min_free_disk_gb):
                self.disk_status.setText(TEXT["disk_low"])
                if log_event:
                    self.add_log(
                        f"\u78c1\u76d8\u7a7a\u95f4\u8b66\u544a\uff1a"
                        f"\u5269\u4f59 {free_gb:.2f} GB\uff0c"
                        f"\u4f4e\u4e8e {self.config.min_free_disk_gb} GB"
                    )
                return False
            else:
                self.disk_status.setText(f"{free_gb:.2f} GB / min {float(self.config.min_free_disk_gb):.2f} GB")
                return True
        except OSError as exc:
            self.disk_status.setText(TEXT["disk_failed"])
            self.add_log(f"\u78c1\u76d8\u7a7a\u95f4\u68c0\u6d4b\u5931\u8d25\uff1a{exc}")
            return True

    def update_runtime_status(self) -> None:
        if self.config is None:
            return
        disk_ok = self.update_disk_status(log_event=False)
        if not disk_ok and self.recorder is not None and self.recorder.is_recording():
            shared_context = self._capture_shared_recording_context()
            self.recorder.stop_recording()
            self.schedule_shared_storage_copy(shared_context)
            self.play_sound_hint("record_stop")
            self.recording_status.setText(TEXT["disk_stopped"])
            self.update_recent_tracking_status(TEXT["disk_stopped"])
            self.add_log("Disk free space too low, recording stopped.")

        self.update_idle_countdown()
        self.update_recording_experience_status()

    def update_recording_experience_status(self) -> None:
        is_recording = self.recorder is not None and self.recorder.is_recording()
        current_path = self._current_video_path()

        if is_recording:
            self.recording_status.setText("● 正在录像")
            self.recording_status.setStyleSheet("color: #dc2626; font-weight: 700;")
            started_at = getattr(self.recorder, "recording_start_monotonic", None)
            elapsed = max(0.0, time.monotonic() - started_at) if started_at is not None else 0.0
            self.recording_duration_status.setText(self._format_duration(elapsed))
        else:
            self.recording_status.setText("● 未录像")
            self.recording_status.setStyleSheet("color: #4b5563; font-weight: 600;")
            self.recording_duration_status.setText("00:00")

        if current_path is None:
            self.recording_file_status.setText("暂无录像文件")
        elif current_path.exists():
            self.recording_file_status.setText(f"已创建：{current_path.name}")
            self.recording_file_status.setToolTip(str(current_path))
        else:
            self.recording_file_status.setText(f"尚未创建：{current_path.name}")
            self.recording_file_status.setToolTip(str(current_path))

        if self.fullscreen_preview_window is not None:
            self.fullscreen_preview_window.set_status_text(self._fullscreen_status_text())

    @staticmethod
    def _format_duration(elapsed_seconds: float) -> str:
        total_seconds = max(0, int(elapsed_seconds))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _fullscreen_status_text(self) -> str:
        is_recording = self.recorder is not None and self.recorder.is_recording()
        status = "● 正在录像" if is_recording else "● 未录像"
        tracking_number = self.last_tracking_number or "暂无"
        duration = self.recording_duration_status.text() if hasattr(self, "recording_duration_status") else "00:00"
        return f"{status}\n当前单号：{tracking_number}\n已录制时长：{duration}"

    def _current_video_path(self) -> Path | None:
        if self.recorder is not None:
            recorder_path = getattr(self.recorder, "current_video_path", None)
            if recorder_path:
                return Path(recorder_path)
        return self.last_video_path

    def update_idle_countdown(self) -> None:
        if self.config is None or not self.config.auto_stop_enabled:
            self.idle_countdown_status.setText("--")
            return
        if self.recorder is None or not self.recorder.is_recording() or self.last_scan_monotonic is None:
            self.idle_countdown_status.setText("--")
            return

        elapsed = time.monotonic() - self.last_scan_monotonic
        remaining = max(0, int(float(self.config.auto_stop_timeout) - elapsed))
        self.idle_countdown_status.setText(f"{remaining} \u79d2")
        if self.should_auto_stop_now():
            self.auto_stop_recording()

    def auto_stop_conditions_met(self) -> bool:
        if self.config is None or not self.config.auto_stop_enabled or self.last_scan_monotonic is None:
            return False
        elapsed = time.monotonic() - self.last_scan_monotonic
        if elapsed < float(self.config.auto_stop_timeout):
            return False
        if not getattr(self.config, "frame_idle_detection_enabled", True):
            return True
        return self.frame_idle_seconds >= int(getattr(self.config, "frame_idle_timeout", 30))

    def should_auto_stop_now(self) -> bool:
        if self.recorder is None or not self.recorder.is_recording():
            return False
        return self.auto_stop_conditions_met()

    def auto_stop_recording(self) -> None:
        if self.recorder is None or not self.recorder.is_recording():
            return
        shared_context = self._capture_shared_recording_context()
        self.recorder.stop_recording()
        self.schedule_shared_storage_copy(shared_context)
        self.play_sound_hint("record_stop")
        self.last_scan_monotonic = None
        self.recording_status.setText(TEXT["auto_stopped"])
        self.update_recording_experience_status()
        self.update_recent_tracking_status(TEXT["auto_stopped"])
        self.add_log("Auto stop recording after idle timeout.")

        if self.config is not None and self.config.keep_camera_on_timeout:
            self.camera_status.setText(TEXT["waiting_scan"])
        else:
            self.stop_preview()
            self.camera_status.setText(TEXT["camera_released"])
        self.scan_input.setFocus()

    def show_license_failure(self) -> None:
        if not self.license_error:
            return
        if "--smoke-test" in sys.argv or "--smoke-test-camera" in sys.argv:
            return
        QMessageBox.warning(self, TEXT["license_fail_title"], self.license_error)

    def add_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}"
        self.log_box.append(line)
        self._append_runtime_log(line)

    def add_recording_diagnostic_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._append_runtime_log(f"[{timestamp}] {message}")

    def _create_camera_from_config(self, settings_source: str) -> CameraManager:
        profile = self._selected_camera_profile or {}
        resolution = (
            int(profile.get("width", self.config.resolution_size[0])),
            int(profile.get("height", self.config.resolution_size[1])),
        )
        return CameraManager(
            int(profile.get("camera_index", self.config.camera_index)),
            resolution,
            int(profile.get("fps", self.config.fps)),
            self.recordings_dir,
            enable_lens_correction=self.config.enable_lens_correction,
            camera_focus_enabled=self.config.camera_focus_enabled,
            camera_focus_value=self.config.camera_focus_value,
            camera_autofocus_enabled=self.config.camera_autofocus_enabled,
            settings_source=settings_source,
            preferred_backend=str(
                profile.get(
                    "backend",
                    getattr(self.config, "camera_backend", "DirectShow"),
                )
            ),
            fourcc_preference=str(
                profile.get(
                    "fourcc",
                    getattr(self.config, "camera_fourcc_preference", "MJPG"),
                )
            ),
            log_callback=self.add_log,
        )

    @staticmethod
    def _camera_quality_machine_key() -> str:
        seed = f"{platform.node()}|{RUNTIME_CONFIG.resolve().parent}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _load_camera_quality_cache() -> dict[str, object] | None:
        try:
            with RUNTIME_CONFIG.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
            cache = raw.get("camera_quality_cache")
            return dict(cache) if isinstance(cache, dict) else None
        except (OSError, ValueError, TypeError):
            return None

    @staticmethod
    def _write_camera_quality_cache(cache: dict[str, object] | None) -> None:
        with RUNTIME_CONFIG.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if cache is None:
            raw.pop("camera_quality_cache", None)
        else:
            raw["camera_quality_cache"] = cache
        temporary = RUNTIME_CONFIG.with_name(f"{RUNTIME_CONFIG.name}.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(raw, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(RUNTIME_CONFIG)

    def _camera_quality_cache_matches_config(self, cache: dict[str, object]) -> bool:
        expected = {
            "configured_camera_index": int(self.config.camera_index),
            "configured_backend": str(getattr(self.config, "camera_backend", "DirectShow")),
            "configured_fourcc": str(getattr(self.config, "camera_fourcc_preference", "MJPG")),
            "configured_resolution": str(self.config.resolution),
            "configured_fps": int(self.config.fps),
            "resolution_policy": str(
                getattr(self.config, "resolution_policy", "config_first")
            ),
            "writer_codec": str(
                getattr(self.config, "recording_writer_codec", "MJPG")
            ).upper(),
        }
        return all(cache.get(key) == value for key, value in expected.items())

    def _save_camera_quality_cache(self, result: dict[str, object]) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        measured_fps = float(result["measured_capture_fps"])
        cache = {
            "enabled": True,
            "machine_key": self._camera_quality_machine_key(),
            "configured_camera_index": int(self.config.camera_index),
            "configured_backend": str(getattr(self.config, "camera_backend", "DirectShow")),
            "configured_fourcc": str(
                getattr(self.config, "camera_fourcc_preference", "MJPG")
            ),
            "configured_resolution": str(self.config.resolution),
            "configured_fps": int(self.config.fps),
            "camera_index": int(result["camera_index"]),
            "backend": str(result["camera_backend"]),
            "input_fourcc": str(result["camera_fourcc_preference"]),
            "selected_resolution": (
                f"{int(result['actual_width'])}x{int(result['actual_height'])}"
            ),
            "selected_fps": int(round(float(result["requested_fps"]))),
            "measured_capture_fps": measured_fps,
            "resolution_policy": str(
                getattr(self.config, "resolution_policy", "config_first")
            ),
            "writer_codec": str(
                getattr(self.config, "recording_writer_codec", "MJPG")
            ).upper(),
            "score": int(result["score"]),
            "low_fps_warning": measured_fps < 8,
            "created_at": now,
            "validated_at": now,
            "app_camera_probe_version": CAMERA_QUALITY_PROBE_VERSION,
        }
        self._write_camera_quality_cache(cache)
        self.add_log("camera_quality_cache_saved")

    def _validate_camera_quality_cache(self, cache: dict[str, object]) -> bool:
        self.add_log("camera_quality_cache_validate_start")
        result = validate_camera_candidate(
            int(cache["camera_index"]),
            str(cache["backend"]),
            str(cache["input_fourcc"]),
            int(str(cache["selected_resolution"]).split("x", 1)[0]),
            int(str(cache["selected_resolution"]).split("x", 1)[1]),
            float(cache["selected_fps"]),
            timeout_seconds=2.0,
        )
        measured_fps = float(result.get("measured_capture_fps", 0.0) or 0.0)
        cached_fps = float(cache.get("measured_capture_fps", 0.0) or 0.0)
        if (
            not bool(result.get("valid"))
            or measured_fps < 8.0
            or (cached_fps > 0 and measured_fps < cached_fps * 0.6)
        ):
            reason = str(result.get("reason", "fps_below_threshold"))
            if bool(result.get("valid")):
                reason = "fps_below_threshold"
            self.add_log(
                "camera_quality_cache_validate_failed: "
                f"reason={reason} measured_capture_fps={measured_fps:.2f}"
            )
            return False
        cache["validated_at"] = datetime.now().isoformat(timespec="seconds")
        cache["last_measured_capture_fps"] = measured_fps
        self._write_camera_quality_cache(cache)
        self.add_log(
            "camera_quality_cache_validate_success: "
            f"measured_capture_fps={measured_fps:.2f}"
        )
        self.add_log("camera_selected_from_cache")
        selected_width, selected_height = (
            int(part) for part in str(cache["selected_resolution"]).split("x", 1)
        )
        self._selected_camera_profile = {
            "camera_index": int(cache["camera_index"]),
            "backend": str(cache["backend"]),
            "fourcc": str(cache["input_fourcc"]),
            "width": selected_width,
            "height": selected_height,
            "fps": int(cache["selected_fps"]),
        }
        self._camera_settings_source = "quality cache"
        return True

    def _prepare_camera_quality_selection(self) -> bool:
        cache = self._load_camera_quality_cache()
        if cache is not None:
            self.add_log("camera_quality_cache_found")
            cache_valid = (
                bool(cache.get("enabled", True))
                and cache.get("machine_key") == self._camera_quality_machine_key()
                and int(cache.get("app_camera_probe_version", 0))
                == CAMERA_QUALITY_PROBE_VERSION
                and self._camera_quality_cache_matches_config(cache)
            )
            if cache_valid:
                if self._validate_camera_quality_cache(cache):
                    return True
                self.add_log("camera_quality_cache_invalidated")
                self.add_log(
                    "camera_quality_cache_invalid_reason=quick_validation_failed"
                )
            else:
                self.add_log("camera_quality_cache_invalidated")
                self.add_log(
                    "camera_quality_cache_invalid_reason=cache_metadata_mismatch"
                )
            self._write_camera_quality_cache(None)
            self._selected_camera_profile = None
        return self._auto_select_available_camera()

    def _auto_select_available_camera(self) -> bool:
        self.add_log("camera_quality_probe_start")
        result = probe_available_cameras(
            preferred_index=self.config.camera_index,
            preferred_backend=getattr(self.config, "camera_backend", "DirectShow"),
            width=self.config.resolution_size[0],
            height=self.config.resolution_size[1],
            fps=self.config.fps,
            resolution_policy=getattr(self.config, "resolution_policy", "config_first"),
            writer_codec=getattr(self.config, "recording_writer_codec", "MJPG"),
            max_index=9,
            timeout_seconds=25.0,
            log_callback=self.add_log,
        )
        if result is None:
            return False
        self._selected_camera_profile = {
            "camera_index": int(result["camera_index"]),
            "backend": str(result["camera_backend"]),
            "fourcc": str(result["camera_fourcc_preference"]),
            "width": int(result["actual_width"]),
            "height": int(result["actual_height"]),
            "fps": int(round(float(result["requested_fps"]))),
        }
        self._save_camera_quality_cache(result)
        self._camera_settings_source = "automatic probe"
        self.add_log(
            "camera_selected: "
            f"index={result['camera_index']} backend={result['camera_backend']} "
            f"fourcc={result['camera_fourcc_preference']} "
            f"resolution={result['actual_width']}x{result['actual_height']} "
            f"fps={result['requested_fps']} "
            f"measured_capture_fps={float(result['measured_capture_fps']):.2f} "
            f"score={int(result['score'])} mode={result['mode']}"
        )
        if float(result["measured_capture_fps"]) < 8:
            warning = (
                "\u5f53\u524d\u6444\u50cf\u5934/\u7535\u8111\u7ec4\u5408\u5e27\u7387\u8f83\u4f4e\uff0c"
                "\u5f55\u50cf\u53ef\u80fd\u4e0d\u6d41\u7545\u3002\u5efa\u8bae\u66f4\u6362\u6444\u50cf\u5934\u3001"
                "USB \u63a5\u53e3\u6216\u964d\u4f4e\u5206\u8fa8\u7387\u3002"
            )
            self.add_log(warning)
            if not self._is_smoke_test_mode():
                QMessageBox.warning(self, "\u6444\u50cf\u5934\u5e27\u7387\u8f83\u4f4e", warning)
        return True

    def on_start_clicked(self) -> None:
        self.add_log("start_button_clicked")
        self.add_log("on_start_clicked begin")
        try:
            if self.preview_timer.isActive() and self.camera is not None and self.camera.is_opened():
                self.add_log("\u6444\u50cf\u5934\u5df2\u5728\u9884\u89c8\u4e2d")
                return

            if not self.ensure_recording_authorized(prompt_for_activation=True):
                return

            if self.config is None:
                QMessageBox.warning(self, TEXT["camera_fail_title"], "\u914d\u7f6e\u672a\u6210\u529f\u8bfb\u53d6")
                self.add_log("\u6444\u50cf\u5934\u542f\u52a8\u5931\u8d25\uff1a\u914d\u7f6e\u672a\u6210\u529f\u8bfb\u53d6")
                return

            if not self._prepare_camera_quality_selection():
                self.camera_status.setText(TEXT["start_failed"])
                self.add_log("camera_probe_all_failed")
                if not self._is_smoke_test_mode():
                    QMessageBox.warning(
                        self,
                        TEXT["camera_fail_title"],
                        "\u672a\u627e\u5230\u53ef\u7528\u7684\u6444\u50cf\u5934\u8d28\u91cf\u6a21\u5f0f\u3002"
                        "\u8bf7\u5173\u95ed Windows \u76f8\u673a App \u540e\u91cd\u8bd5\uff0c"
                        "\u6216\u91cd\u65b0\u63d2\u62d4\u6444\u50cf\u5934\u3002",
                    )
                self.add_log("on_start_clicked end")
                return

            self.camera = self._create_camera_from_config(self._camera_settings_source)
            if not self.camera.open():
                self.camera_status.setText(TEXT["start_failed"])
                reason = self.camera.state.last_error or "\u672a\u77e5\u9519\u8bef"
                self.add_log(f"\u6444\u50cf\u5934\u542f\u52a8\u5931\u8d25\uff1a{reason}")
                try:
                    self.camera.release()
                except Exception:  # noqa: BLE001
                    pass
                self.camera = None
                self._write_camera_quality_cache(None)
                self._selected_camera_profile = None
                if (
                    self._camera_settings_source != "automatic probe"
                    and self._auto_select_available_camera()
                ):
                    QTimer.singleShot(100, self.on_start_clicked)
                    return
                current_settings = self._camera_settings_snapshot(self.config)
                rollback_settings = self.last_known_good_camera_config
                if (
                    rollback_settings
                    and current_settings != rollback_settings
                    and self._camera_settings_source != "rollback"
                ):
                    self.add_log("camera settings apply failed")
                    self.add_log("rollback to last known good")
                    self._write_camera_settings(rollback_settings)
                    self.config = get_config()
                    self._camera_settings_source = "rollback"
                    QTimer.singleShot(500, self.on_start_clicked)
                    return
                if not self._is_smoke_test_mode():
                    QMessageBox.warning(
                        self,
                        TEXT["camera_fail_title"],
                        "\u672a\u627e\u5230\u53ef\u7528\u6444\u50cf\u5934\u3002Windows \u76f8\u673a\u53ef\u7528\u65f6\uff0c"
                        "\u8bf7\u5c1d\u8bd5\u5173\u95ed\u76f8\u673a App \u540e\u91cd\u8bd5\uff0c"
                        "\u6216\u91cd\u65b0\u63d2\u62d4\u6444\u50cf\u5934\u3002",
                    )
                self.add_log("camera_probe_all_failed")
                self.add_log("on_start_clicked end")
                return

            self.recorder = RecordingManager(
                self.camera,
                self.recordings_dir,
                self.config.fps,
                self.camera.resolution,
                min_free_disk_gb=self.config.min_free_disk_gb,
                watchdog_enabled=self.config.watchdog_enabled,
                watchdog_max_failures=self.config.watchdog_max_failures,
                watchdog_retry_count=self.config.watchdog_retry_count,
                watchdog_retry_interval=self.config.watchdog_retry_interval,
                watermark_position=self.config.watermark_position,
                watermark_font_scale=self.config.watermark_font_scale,
                watermark_color=self.config.watermark_color,
                watermark_opacity=self.config.watermark_opacity,
                config=self.config,
                log_callback=self.add_recording_diagnostic_log,
            )
            self.frame_failure_count = 0
            self.frame_failures_status.setText(f"0/{self.config.watchdog_max_failures}")
            self.reset_frame_idle_state()
            self.update_runtime_status()
            self.camera_status.setText(TEXT["previewing"])
            self.recording_status.setText(TEXT["not_recording"])
            self.add_log("\u6444\u50cf\u5934\u542f\u52a8\u6210\u529f\uff0c\u5f00\u59cb\u9884\u89c8")
            self.add_log("preview_started")
            self.update_watchdog_status()  # Refresh actual resolution/FPS after camera negotiation.
            self.log_camera_output_status()
            self.last_known_good_camera_config = self._camera_settings_snapshot(self.config)
            self._persist_last_known_good_camera_config(self.last_known_good_camera_config)
            self.add_log(
                f"camera settings applied successfully; settings_source={self._camera_settings_source}"
            )
            self._camera_settings_source = "user config"
            self._start_preview_timer()
            self.scan_input.setFocus()
            self.add_log("on_start_clicked end")

        except Exception as e:
            self.add_log(f"ERROR: on_start_clicked 异常: {e}")

            import traceback
            traceback.print_exc()
    def on_stop_clicked(self) -> None:
        if not self.preview_timer.isActive() and (self.camera is None or not self.camera.is_opened()):
            self.add_log("\u5f53\u524d\u672a\u542f\u52a8\u9884\u89c8")
            return
        self.stop_preview()

    def stop_preview(self) -> None:
        was_recording = self.recorder is not None and self.recorder.is_recording()
        shared_context = self._capture_shared_recording_context()
        self._recording_auth_session_cache = None
        try:
            if self.recorder is not None:
                try:
                    self.recorder.stop_recording()
                except Exception as exc:  # noqa: BLE001
                    self.add_log(f"Recording finalize failed: {exc}")
                finally:
                    self.recorder = None
            self.schedule_shared_storage_copy(shared_context)
            if was_recording:
                self.play_sound_hint("record_stop")
            if self.preview_timer.isActive():
                self.preview_timer.stop()
            if self.camera is not None:
                try:
                    self.camera.release()
                except Exception as exc:  # noqa: BLE001
                    self.add_log(f"Camera release failed: {exc}")
                finally:
                    self.camera = None
        finally:
            self.update_watchdog_status()
            self.preview_area.clear()
            self.preview_area.setText(TEXT["preview_placeholder"])
            self.latest_preview_pixmap = None
            self.latest_label_source_frame = None
            if self.fullscreen_preview_window is not None:
                self.fullscreen_preview_window.set_preview_pixmap(None)
            self.camera_status.setText(TEXT["stopped"])
            self.recording_status.setText(TEXT["not_recording"])
            self.last_scan_monotonic = None
            self.reset_frame_idle_state()
            self.update_recording_experience_status()
            self.add_log("\u6444\u50cf\u5934\u5df2\u91ca\u653e")
            self.scan_input.setFocus()

    def update_preview_frame(self) -> None:
        try:
            if self.camera is None or not self.camera.is_opened():
                self.stop_preview()
                return

            ok, frame = self.camera.read_frame()
            if not ok or frame is None:
                self.frame_failure_count += 1
                self.update_watchdog_status()
                self.add_log("\u6444\u50cf\u5934\u9884\u89c8\u8bfb\u5e27\u5931\u8d25")
                if self.should_trigger_watchdog():
                    self.trigger_watchdog()
                return

            if self.frame_failure_count:
                self.frame_failure_count = 0
                self.update_watchdog_status()

            if cv2 is None:
                self.add_log("OpenCV \u672a\u5b89\u88c5\uff0c\u65e0\u6cd5\u663e\u793a\u9884\u89c8")
                return

            frame = self._apply_camera_calibration(frame)
            self.update_frame_motion_state(frame)
            self.latest_label_source_frame = frame.copy()

            # Apply watermark first
            display_frame = self._apply_watermark(frame.copy())
            label_roi = None

            # Draw the fixed label close-up guide on the preview only.
            barcode_enabled = bool(
                getattr(self.config, "barcode_scan_enabled", False)
                or getattr(self.config, "enable_camera_barcode_scanner", False)
            )

            if self._label_setting("label_closeup_enabled", True):
                h, w = display_frame.shape[:2]
                roi = self.calculate_barcode_roi(w, h)
                label_roi = self.expand_roi_with_padding(roi, w, h, 0.25)
                color_val = getattr(self.config, "barcode_roi_color", "#FF0000") or "#FF0000"
                r = int(color_val[1:3], 16)
                g = int(color_val[3:5], 16)
                b = int(color_val[5:7], 16)
                color = (b, g, r)  # BGR
                thickness = int(getattr(self.config, "barcode_roi_thickness", 2))
                dash_length = int(getattr(self.config, "barcode_roi_dash_length", 16))
                gap_length = int(getattr(self.config, "barcode_roi_gap_length", 10))
                self.draw_dashed_rectangle(display_frame, roi, color, thickness, dash_length, gap_length)

            # Camera barcode recognition (use ROI area if enabled)
            # Compatible with both old and new config keys
            barcode_enabled = bool(
                getattr(self.config, "barcode_scan_enabled", False)
                or getattr(self.config, "enable_camera_barcode_scanner", False)
            )
            
            if barcode_enabled:
                scan_frame = frame
                if getattr(self.config, "barcode_roi_use_guide_area", True):
                    h, w = frame.shape[:2]
                    roi = self.calculate_barcode_roi(w, h)
                    x1, y1, x2, y2 = roi
                    scan_frame = frame[y1:y2, x1:x2]
                code = self.barcode_scanner.detect(scan_frame)
                if code:
                    self.add_log(f"摄像头识别到单号：{code}")
                    self.scan_input.setText(code)
                    self.on_tracking_entered()

            rgb_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
            height, width, channel_count = rgb_frame.shape
            bytes_per_line = channel_count * width
            image = QImage(rgb_frame.data, width, height, bytes_per_line, QImage.Format_RGB888).copy()
            if label_roi is not None:
                self.draw_label_roi_hint(image, label_roi)
            pixmap = QPixmap.fromImage(image)
            self.latest_preview_pixmap = pixmap
            scaled = pixmap.scaled(
                self.preview_area.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.preview_area.setPixmap(scaled)
            if self.fullscreen_preview_window is not None:
                self.fullscreen_preview_window.set_preview_pixmap(pixmap)


        except Exception as e:
            self.add_log(f"ERROR in update_preview_frame: {e}")
            import traceback
            traceback.print_exc()

    def _start_preview_timer(self) -> None:
        # Rendering more often than the configured camera rate repeats frames and
        # spends GUI time scaling full-resolution images while recording runs.
        preview_fps = max(1, min(int(self.config.fps), 20))
        self.preview_timer.setInterval(max(PREVIEW_INTERVAL_MS, round(1000 / preview_fps)))
        self.preview_timer.start()

    def reset_frame_idle_state(self) -> None:
        self.previous_motion_gray = None
        self.frame_idle_started_at = None
        self.frame_idle_seconds = 0
        self.frame_motion_diff = 0.0
        self.frame_is_static = False
        if hasattr(self, "frame_motion_status"):
            self.frame_motion_status.setText("--")

    def update_frame_motion_state(self, frame) -> None:
        if self.config is None or cv2 is None:
            return
        if not getattr(self.config, "frame_idle_detection_enabled", True):
            self.frame_motion_status.setText(TEXT["disabled"])
            return

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (160, 90))
        now = time.monotonic()

        if self.previous_motion_gray is None:
            self.previous_motion_gray = gray
            self.frame_idle_started_at = None
            self.frame_idle_seconds = 0
            self.frame_is_static = False
            self.frame_motion_status.setText(TEXT["motion_active"])
            return

        self.frame_motion_diff = float(cv2.absdiff(self.previous_motion_gray, gray).mean())
        self.previous_motion_gray = gray
        threshold = float(getattr(self.config, "frame_motion_threshold", 3.0))
        if self.frame_motion_diff < threshold:
            if self.frame_idle_started_at is None:
                self.frame_idle_started_at = now
            self.frame_idle_seconds = int(now - self.frame_idle_started_at)
            self.frame_is_static = True
            self.frame_motion_status.setText(f"{TEXT['motion_static']} {self.frame_idle_seconds} \u79d2")
        else:
            self.frame_idle_started_at = None
            self.frame_idle_seconds = 0
            self.frame_is_static = False
            self.frame_motion_status.setText(TEXT["motion_active"])

    def _apply_camera_calibration(self, frame):
        """对帧应用摄像头矫正（亮度/对比度/ROI裁切）"""
        if self.config is None or cv2 is None:
            return frame
        if not getattr(self.config, "camera_calibration_enabled", False):
            return frame
        alpha = 1.0 + getattr(self.config, "camera_calibration_contrast", 0) / 100.0
        beta = float(getattr(self.config, "camera_calibration_brightness", 0))
        if alpha != 1.0 or beta != 0.0:
            frame = cv2.convertScaleAbs(frame, alpha=alpha, beta=beta)
        if getattr(self.config, "camera_calibration_roi_enabled", False):
            roi_x = int(getattr(self.config, "camera_calibration_roi_x", 0))
            roi_y = int(getattr(self.config, "camera_calibration_roi_y", 0))
            roi_w = int(getattr(self.config, "camera_calibration_roi_w", 0))
            roi_h = int(getattr(self.config, "camera_calibration_roi_h", 0))
            h, w = frame.shape[:2]
            if roi_w > 0 and roi_h > 0 and roi_x + roi_w <= w and roi_y + roi_h <= h:
                frame = frame[roi_y:roi_y + roi_h, roi_x:roi_x + roi_w]
        return frame

    def _apply_watermark(self, frame):
        """Apply watermark to frame for preview display."""
        if self.config is None or cv2 is None:
            return frame
        if not getattr(self.config, "watermark_enabled", True):
            return frame
        # Always show watermark: tracking number (or -- if none) + current time
        tracking = getattr(self, "current_tracking_number", None) or ""
        if not tracking and self.recorder is not None:
            tracking = self.recorder.current_tracking_number or ""
        text = getattr(self.config, "watermark_text", "") or tracking
        # Always show watermark - use "--" as placeholder if no tracking number
        display_text = text if text else "--"
        
        frame_out = frame.copy()
        overlay = frame_out.copy()
        now_text = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [display_text, now_text]
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = max(0.3, float(getattr(self.config, "watermark_font_scale", 0.9)))
        thickness = max(1, int(round(font_scale * 2)))
        outline_thickness = thickness + 2
        line_gap = max(8, int(12 * font_scale))
        margin = max(16, int(24 * font_scale))
        color_val = getattr(self.config, "watermark_color", "#00FF00") or "#00FF00"
        r = int(color_val[1:3], 16)
        g = int(color_val[3:5], 16)
        b = int(color_val[5:7], 16)
        color = (b, g, r)  # BGR
        alpha = max(0.0, min(1.0, float(getattr(self.config, "watermark_opacity", 0.75))))
        sizes = [cv2.getTextSize(line, font, font_scale, thickness)[0] for line in lines]
        block_width = max(w for w, _h in sizes)
        block_height = sum(h for _w, h in sizes) + line_gap * (len(lines) - 1)
        position = getattr(self.config, "watermark_position", "top_left")
        x, y = margin, margin
        if position == "top_right":
            x = max(margin, frame_out.shape[1] - block_width - margin)
        elif position == "bottom_left":
            y = max(margin, frame_out.shape[0] - block_height - margin)
        elif position == "bottom_right":
            x = max(margin, frame_out.shape[1] - block_width - margin)
            y = max(margin, frame_out.shape[0] - block_height - margin)
        cur_y = y
        for idx, line in enumerate(lines):
            tw, th = sizes[idx]
            by = cur_y + th
            cv2.putText(overlay, line, (x, by), font, font_scale, (0, 0, 0), outline_thickness, cv2.LINE_AA)
            cv2.putText(overlay, line, (x, by), font, font_scale, color, thickness, cv2.LINE_AA)
            cur_y += th + line_gap
        return cv2.addWeighted(overlay, alpha, frame_out, 1 - alpha, 0)

    def calculate_barcode_roi(self, frame_width: int, frame_height: int) -> tuple:
        """按面单比例 76:130 计算条码识别 ROI 区域。"""
        if self.config is None:
            return (0, 0, frame_width, frame_height)
        
        # 面单比例：76mm x 130mm（竖向）
        label_w = float(getattr(self.config, "barcode_label_width_mm", 76))
        label_h = float(getattr(self.config, "barcode_label_height_mm", 130))
        scale = float(getattr(self.config, "barcode_roi_scale", 1.25))
        
        # ROI 宽高（像素）
        roi_h = int(frame_height * 0.55 * scale)
        roi_w = int(roi_h * (label_w / label_h))
        
        # 中心点位置（可配置）
        cx_ratio = max(0.1, min(0.9, float(getattr(self.config, "barcode_roi_center_x_ratio", 0.50))))
        cy_ratio = max(0.1, min(0.9, float(getattr(self.config, "barcode_roi_center_y_ratio", 0.50))))
        
        cx = int(frame_width * cx_ratio)
        cy = int(frame_height * cy_ratio)
        
        # 计算左上角坐标
        x1 = max(0, cx - roi_w // 2)
        y1 = max(0, cy - roi_h // 2)
        x2 = min(frame_width, x1 + roi_w)
        y2 = min(frame_height, y1 + roi_h)
        
        # 调整确保不超出边界
        if x2 - x1 < roi_w:
            x1 = max(0, x2 - roi_w)
        if y2 - y1 < roi_h:
            y1 = max(0, y2 - roi_h)
        
        return (x1, y1, x2, y2)

    @staticmethod
    def expand_roi_with_padding(
        roi: tuple[int, int, int, int],
        frame_width: int,
        frame_height: int,
        padding_ratio: float = 0.25,
    ) -> tuple[int, int, int, int]:
        x1, y1, x2, y2 = roi
        padding = max(0.0, float(padding_ratio))
        pad_x = int(round(max(0, x2 - x1) * padding))
        pad_y = int(round(max(0, y2 - y1) * padding))
        return (
            max(0, x1 - pad_x),
            max(0, y1 - pad_y),
            min(frame_width, x2 + pad_x),
            min(frame_height, y2 + pad_y),
        )

    def draw_dashed_rectangle(self, frame, roi: tuple, color: tuple, thickness: int = 2, dash_length: int = 16, gap_length: int = 10) -> None:
        """在帧上绘制红色虚线矩形。"""
        x1, y1, x2, y2 = roi
        
        # 绘制四条虚线
        for start, end, horizontal in [
            ((x1, y1), (x2, y1), True),   # 上边
            ((x1, y2), (x2, y2), True),   # 下边
            ((x1, y1), (x1, y2), False),  # 左边
            ((x2, y1), (x2, y2), False),  # 右边
        ]:
            if horizontal:
                x = start[0]
                while x < end[0]:
                    x_next = min(x + dash_length, end[0])
                    cv2.line(frame, (x, start[1]), (x_next, start[1]), color, thickness)
                    x = x_next + gap_length
            else:
                y = start[1]
                while y < end[1]:
                    y_next = min(y + dash_length, end[1])
                    cv2.line(frame, (start[0], y), (start[0], y_next), color, thickness)
                    y = y_next + gap_length

    def draw_label_roi_hint(self, image: QImage, roi: tuple) -> None:
        x1, y1, _x2, y2 = roi
        painter = QPainter(image)
        try:
            font = QFont("Microsoft YaHei")
            font.setPixelSize(max(18, min(30, image.width() // 52)))
            font.setBold(True)
            painter.setFont(font)
            text = "请将快递面单放入此区域"
            metrics = painter.fontMetrics()
            padding = 7
            text_width = metrics.horizontalAdvance(text)
            text_x = max(8, min(x1, image.width() - text_width - padding * 2 - 8))
            text_y = y1 - 12 if y1 - metrics.height() - 12 >= 0 else min(
                image.height() - 8,
                y2 + metrics.height() + 12,
            )
            background = QRect(
                text_x - padding,
                text_y - metrics.ascent() - padding,
                text_width + padding * 2,
                metrics.height() + padding * 2,
            )
            painter.fillRect(background, QColor(0, 0, 0, 150))
            painter.setPen(QPen(QColor(0, 0, 0), 5))
            painter.drawText(text_x, text_y, text)
            painter.setPen(QPen(QColor(255, 72, 72), 2))
            painter.drawText(text_x, text_y, text)
        finally:
            painter.end()

    def _label_setting(self, key: str, default: bool) -> bool:
        value = getattr(self.config, key, None) if self.config is not None else None
        if value is not None:
            return bool(value)
        try:
            with RUNTIME_CONFIG.open("r", encoding="utf-8") as handle:
                return bool(json.load(handle).get(key, default))
        except (OSError, ValueError, TypeError):
            return default

    def save_label_snapshot(self, tracking_number: str, video_path: str | Path) -> Path | None:
        if not self._label_setting("label_closeup_enabled", True) or not self._label_setting(
            "label_snapshot_enabled", True
        ):
            self.add_log("面单特写未启用，跳过截图")
            return None
        if cv2 is None:
            self.add_log("面单截图保存失败：OpenCV 不可用")
            return None
        frame = self.latest_label_source_frame
        if frame is None:
            self.add_log("面单截图保存失败：暂无当前预览帧")
            return None

        try:
            source = frame.copy()
            height, width = source.shape[:2]
            if self._label_setting("label_roi_use_barcode_roi", True):
                x1, y1, x2, y2 = self.calculate_barcode_roi(width, height)
                x1, y1, x2, y2 = self.expand_roi_with_padding(
                    (x1, y1, x2, y2),
                    width,
                    height,
                    0.25,
                )
            else:
                x1, y1, x2, y2 = (0, 0, width, height)
            x1 = max(0, min(width, int(x1)))
            y1 = max(0, min(height, int(y1)))
            x2 = max(x1, min(width, int(x2)))
            y2 = max(y1, min(height, int(y2)))
            crop = source[y1:y2, x1:x2]
            if crop.size == 0:
                raise ValueError("ROI 区域为空")

            crop_height, crop_width = crop.shape[:2]
            target_width = 1200
            if crop_width < target_width:
                scale = target_width / float(crop_width)
                target_height = max(1, int(round(crop_height * scale)))
                crop = cv2.resize(crop, (target_width, target_height), interpolation=cv2.INTER_CUBIC)

            video = Path(video_path)
            safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", video.stem).strip("_") or tracking_number
            output = video.with_name(f"{safe_stem}_label.jpg")
            output.parent.mkdir(parents=True, exist_ok=True)
            if not cv2.imwrite(str(output), crop, [int(cv2.IMWRITE_JPEG_QUALITY), 92]):
                raise OSError("JPEG 写入失败")
            self.add_log(f"面单截图已保存：{output.name}")
            return output
        except Exception as exc:  # noqa: BLE001
            self.add_log(f"面单截图保存失败：{exc}")
            return None

    def save_delayed_label_snapshot(self, tracking_number: str, video_path: str | Path) -> None:
        bound_video_path = Path(video_path)
        current_video_path = getattr(self.recorder, "current_video_path", None) if self.recorder else None
        if current_video_path is None or Path(current_video_path) != bound_video_path:
            self.add_log(f"面单截图已跳过：录像已切换，避免串单（{tracking_number}）")
            return
        label_image_path = self.save_label_snapshot(tracking_number, bound_video_path)
        if label_image_path is None:
            return
        self.current_label_image_path = Path(label_image_path)
        if self.excel_manager is None:
            self.add_log("面单截图路径回写失败：Excel 未初始化")
            return
        try:
            if not self.excel_manager.update_label_image_path(
                tracking_number,
                bound_video_path,
                label_image_path,
            ):
                self.add_log(f"面单截图路径回写失败：未找到对应记录（{tracking_number}）")
        except Exception as exc:  # noqa: BLE001
            self.add_log(f"面单截图路径回写失败：{exc}")

    def play_sound_hint(self, event_name: str) -> None:
        if self.config is None or not bool(getattr(self.config, "voice_enabled", False)):
            return
        events = {
            "scan_success": ("voice_on_scan_success", "单号已识别", "SystemAsterisk"),
            "record_start": ("voice_on_record_start", "开始录像", "SystemQuestion"),
            "record_stop": ("voice_on_record_stop", "录像完成", "SystemAsterisk"),
            "invalid_tracking": ("voice_on_invalid_tracking", "单号无效", "SystemExclamation"),
            "auth_problem": ("voice_on_auth_problem", "请激活授权", "SystemHand"),
        }
        event = events.get(event_name)
        if event is None:
            return
        setting_name, display_text, sound_alias = event
        if not bool(getattr(self.config, setting_name, True)):
            return
        self.add_log(f"声音提示：{display_text}")
        if platform.system() != "Windows":
            return
        try:
            winsound.PlaySound(
                sound_alias,
                winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
        except Exception as exc:  # noqa: BLE001
            self.add_log(f"声音提示播放失败：{exc}")

    def _play_success_beep(self) -> None:
        self.play_sound_hint("scan_success")

    def update_watchdog_status(self) -> None:
        if self.camera is None:
            self.actual_resolution_status.setText("-- / --")
            self.actual_fps_status.setText("--")
            return

        actual_resolution_text, actual_fps_text = self._camera_output_status_text()
        self.actual_resolution_status.setText(f"{actual_resolution_text} / {actual_fps_text}")
        self.actual_fps_status.setText(actual_fps_text)
        self.lens_correction_status.setText(TEXT["on"] if self.camera.enable_lens_correction else TEXT["off"])

    def _configured_resolution_fps_text(self) -> str:
        if self.config is None:
            return TEXT["not_loaded"]
        return f"{self.config.resolution} / {int(self.config.fps)} FPS"

    def _camera_output_status_text(self) -> tuple[str, str]:
        if self.camera is None:
            return "--", "--"

        actual_resolution = self.camera.actual_resolution or self.camera.resolution
        actual_resolution_text = "--"
        if actual_resolution:
            actual_resolution_text = f"{actual_resolution[0]}x{actual_resolution[1]}"

        actual_fps = getattr(self.camera, "actual_fps", None)
        if actual_fps is not None and float(actual_fps) > 0:
            actual_fps_text = f"{float(actual_fps):.2f} FPS"
        elif self.config is not None:
            actual_fps_text = f"{int(self.config.fps)} FPS"
        else:
            actual_fps_text = "--"
        return actual_resolution_text, actual_fps_text

    def log_camera_output_status(self) -> None:
        if self.config is None or self.camera is None:
            return

        actual_resolution_text, actual_fps_text = self._camera_output_status_text()
        requested_resolution = self.config.resolution
        requested_fps_text = f"{int(self.config.fps)} FPS"
        self.add_log(
            "Camera diagnostics: "
            f"camera_backend={getattr(self.camera, 'backend_name', 'UNKNOWN')}, "
            f"camera_input_fourcc={getattr(self.camera, 'actual_fourcc', 'UNKNOWN')}, "
            f"requested={requested_resolution}/{int(self.config.fps)}, "
            f"reported={actual_resolution_text}/{actual_fps_text}, "
            f"measured_capture_fps={float(getattr(self.camera, 'measured_capture_fps', 0.0) or 0.0):.2f}"
        )
        self.add_log(f"请求摄像头参数：{requested_resolution} / {requested_fps_text}")
        self.add_log(f"摄像头实际输出：{actual_resolution_text} / {actual_fps_text}")

        actual_resolution = self.camera.actual_resolution or self.camera.resolution
        resolution_differs = actual_resolution != self.config.resolution_size
        actual_fps = getattr(self.camera, "actual_fps", None)
        fps_differs = (
            actual_fps is not None
            and float(actual_fps) > 0
            and abs(float(actual_fps) - float(self.config.fps)) >= 0.01
        )
        if resolution_differs or fps_differs:
            self.add_log(
                "摄像头实际输出与配置不同："
                f"请求 {requested_resolution} / {requested_fps_text}，"
                f"实际 {actual_resolution_text} / {actual_fps_text}，"
                "可能是摄像头或驱动不支持该模式。"
            )

    def should_trigger_watchdog(self) -> bool:
        if self.config is None or not self.config.watchdog_enabled or self.watchdog_reconnecting:
            return False
        return self.frame_failure_count > int(self.config.watchdog_max_failures)

    def trigger_watchdog(self) -> None:
        if self.config is None:
            return
        self.watchdog_reconnecting = True
        self.watchdog_retry_attempt = 0
        self.watchdog_status.setText("triggered")
        self.add_log("Camera watchdog triggered.")
        if self.recorder is not None:
            was_recording = self.recorder.is_recording()
            shared_context = self._capture_shared_recording_context()
            self.recorder.stop_recording()
            self.schedule_shared_storage_copy(shared_context)
            if was_recording:
                self.play_sound_hint("record_stop")
            self.recording_status.setText(TEXT["not_recording"])
        if self.preview_timer.isActive():
            self.preview_timer.stop()
        if self.camera is not None:
            self.camera.release_capture_only()
        self.schedule_watchdog_retry()

    def schedule_watchdog_retry(self) -> None:
        if self.config is None:
            return
        if self.watchdog_retry_attempt >= int(self.config.watchdog_retry_count):
            self.watchdog_reconnecting = False
            self.watchdog_status.setText(TEXT["watchdog_failed"])
            self.camera_status.setText(TEXT["watchdog_failed"])
            self.add_log("Camera watchdog failed, please check camera.")
            return

        self.watchdog_retry_attempt += 1
        interval_ms = int(float(self.config.watchdog_retry_interval) * 1000)
        QTimer.singleShot(interval_ms, self.try_watchdog_reconnect)

    def try_watchdog_reconnect(self) -> None:
        if self.config is None:
            return
        self.add_log(
            f"Camera watchdog reconnect attempt {self.watchdog_retry_attempt}/{self.config.watchdog_retry_count}"
        )
        self.camera = self._create_camera_from_config("watchdog reconnect")
        if self.camera.open():
            self.recorder = RecordingManager(
                self.camera,
                self.recordings_dir,
                self.config.fps,
                self.camera.resolution,
                min_free_disk_gb=self.config.min_free_disk_gb,
                watchdog_enabled=self.config.watchdog_enabled,
                watchdog_max_failures=self.config.watchdog_max_failures,
                watchdog_retry_count=self.config.watchdog_retry_count,
                watchdog_retry_interval=self.config.watchdog_retry_interval,
                watermark_position=self.config.watermark_position,
                watermark_font_scale=self.config.watermark_font_scale,
                watermark_color=self.config.watermark_color,
                watermark_opacity=self.config.watermark_opacity,
                config=self.config,
                log_callback=self.add_recording_diagnostic_log,
            )
            self.frame_failure_count = 0
            self.update_watchdog_status()
            self.update_runtime_status()
            self.watchdog_reconnecting = False
            self.watchdog_status.setText(TEXT["watchdog_reconnected"])
            self.camera_status.setText(TEXT["previewing"])
            self.add_log("Camera watchdog reconnected.")
            self._start_preview_timer()
            self.scan_input.setFocus()
            return

        self.schedule_watchdog_retry()

    def on_config_clicked(self) -> None:
        if self.config is None:
            QMessageBox.warning(self, TEXT["config_title"], "\u914d\u7f6e\u672a\u6210\u529f\u8bfb\u53d6")
            return
        dialog = ConfigDialog(self.config, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        self.save_config_from_dialog(dialog.values())

    def on_query_clicked(self) -> None:
        if self.config is None:
            QMessageBox.warning(self, TEXT["query_title"], "\u914d\u7f6e\u672a\u6210\u529f\u8bfb\u53d6")
            return
        defaults = {
            "query_default_source": self.config.query_default_source,
            "query_default_start_date": self.config.query_default_start_date,
            "query_default_end_date": self.config.query_default_end_date,
        }
        dialog = QueryDialog(
            QueryManager(
                self.config.excel_path,
                self.config.mp4_output_folder,
                allowed_roots=[self.recordings_dir],
                evidence_output_dir=runtime_root() / "evidence_packages",
            ),
            defaults,
            self.config.generate_mp4_on_query,
            self,
        )
        dialog.exec_()

    def _erp_manager(self) -> ERPManager:
        return ERPManager(runtime_root() / "data" / "erp_orders.xlsx")

    def _runtime_query_manager(self) -> QueryManager:
        return QueryManager(
            self.config.excel_path,
            self.config.mp4_output_folder,
            allowed_roots=[self.recordings_dir],
            evidence_output_dir=runtime_root() / "evidence_packages",
        )

    def open_erp_import_template(self) -> None:
        bundle_root = Path(getattr(sys, "_MEIPASS", runtime_root()))
        candidates = [
            runtime_root() / "templates" / "erp_import_template.xlsx",
            bundle_root / "templates" / "erp_import_template.xlsx",
        ]
        template = next((path for path in candidates if path.is_file()), None)
        if template is None:
            template = runtime_root() / "templates" / "erp_import_template.xlsx"
            try:
                self._erp_manager().generate_template(template)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, "ERP 导入模板", f"模板生成失败：{exc}")
                return
        try:
            os.startfile(str(template))
            self.add_log(f"已打开 ERP 导入模板：{template}")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "ERP 导入模板", f"无法打开模板：{exc}")

    def import_erp_orders_from_main(self) -> None:
        source, _filter = QFileDialog.getOpenFileName(
            self,
            "导入 ERP 订单",
            "",
            "ERP 订单文件 (*.xlsx *.csv)",
        )
        if not source:
            return
        try:
            result = self._erp_manager().import_orders(source)
            message = (
                f"ERP 订单导入完成：{result['imported']} 条，"
                f"跳过 {result['skipped']} 条，当前共 {result['total']} 条。"
            )
            missing_fields = result.get("missing_fields", [])
            if missing_fields:
                message += f"\n未提供的非关键字段已留空：{', '.join(missing_fields)}"
            self.add_log(message)
            QMessageBox.information(self, "导入 ERP 订单", message)
        except Exception as exc:  # noqa: BLE001
            self.add_log(f"ERP 订单导入失败：{exc}")
            QMessageBox.warning(self, "导入 ERP 订单", f"导入失败：{exc}")

    def export_erp_results_from_main(self) -> None:
        if self.config is None:
            QMessageBox.warning(self, "导出 ERP 留证结果", "配置尚未成功读取")
            return
        try:
            results = self._runtime_query_manager().query()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "导出 ERP 留证结果", f"读取留证记录失败：{exc}")
            return
        if not results:
            QMessageBox.information(self, "导出 ERP 留证结果", "暂无可导出的留证记录")
            return
        target, selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出 ERP 留证结果",
            "erp_evidence_results.xlsx",
            "Excel (*.xlsx);;CSV (*.csv)",
        )
        if not target:
            return
        output = Path(target)
        if not output.suffix:
            output = output.with_suffix(".csv" if "CSV" in selected_filter else ".xlsx")
        try:
            exported = self._erp_manager().export_evidence_results(results, output)
            self.add_log(f"ERP 留证结果已导出：{exported}")
            QMessageBox.information(self, "导出 ERP 留证结果", f"已导出：{exported}")
        except Exception as exc:  # noqa: BLE001
            self.add_log(f"ERP 留证结果导出失败：{exc}")
            QMessageBox.warning(self, "导出 ERP 留证结果", f"导出失败：{exc}")

    def start_lan_query_server(self) -> None:
        if self.lan_query_server is not None and self.lan_query_server.is_running():
            QMessageBox.information(self, "局域网查询", f"服务已在运行：\n{self.lan_query_access_url}")
            return
        if self.config is None:
            QMessageBox.warning(self, "局域网查询", "配置尚未成功读取。")
            return
        if not bool(getattr(self.config, "lan_query_readonly", True)):
            QMessageBox.warning(self, "局域网查询", "局域网查询必须以只读模式运行。")
            return

        try:
            token = ensure_lan_query_token()
            self.config = get_config()
            host = str(getattr(self.config, "lan_query_host", "0.0.0.0") or "0.0.0.0")
            port = int(getattr(self.config, "lan_query_port", 18080))
            web_root = runtime_root() / "web" / "lan_query"
            server = LanQueryServer(
                host=host,
                port=port,
                token=token,
                query_manager=QueryManager(self.config.excel_path, self.config.mp4_output_folder),
                allowed_roots=[self.recordings_dir],
                web_root=web_root,
            )
            status = server.start()
            display_host = self._lan_display_host(host)
            self.lan_query_server = server
            self.lan_query_access_url = f"http://{display_host}:{status.port}/?token={token}"
            self.start_lan_query_action.setEnabled(False)
            self.stop_lan_query_action.setEnabled(True)
            self.copy_lan_query_url_action.setEnabled(True)
            self.add_log(
                f"局域网查询已启动：http://{display_host}:{status.port}/ "
                f"token={mask_token(token)}"
            )
            QMessageBox.information(
                self,
                "局域网查询已启动",
                f"访问地址：\n{self.lan_query_access_url}\n\n"
                "仅限局域网使用，请勿暴露公网。\n"
                "Windows 防火墙可能需要允许访问。",
            )
        except OSError as exc:
            self.lan_query_server = None
            self.add_log(f"局域网查询启动失败：{exc}")
            QMessageBox.warning(self, "局域网查询启动失败", f"端口可能被占用或不可用：\n{exc}")
        except Exception as exc:  # noqa: BLE001
            self.lan_query_server = None
            self.add_log(f"局域网查询启动失败：{exc}")
            QMessageBox.warning(self, "局域网查询启动失败", str(exc))

    def stop_lan_query_server(self, show_message: bool = True) -> None:
        server = self.lan_query_server
        self.lan_query_server = None
        self.lan_query_access_url = ""
        if server is not None:
            try:
                server.stop()
            except Exception as exc:  # noqa: BLE001
                self.add_log(f"局域网查询停止异常：{exc}")
        if hasattr(self, "start_lan_query_action"):
            self.start_lan_query_action.setEnabled(True)
            self.stop_lan_query_action.setEnabled(False)
            self.copy_lan_query_url_action.setEnabled(False)
        if show_message:
            self.add_log("局域网查询已停止")
            QMessageBox.information(self, "局域网查询", "局域网查询已停止。")

    def copy_lan_query_access_url(self) -> None:
        if not self.lan_query_access_url:
            QMessageBox.information(self, "局域网查询", "局域网查询服务尚未启动。")
            return
        QApplication.clipboard().setText(self.lan_query_access_url)
        self.add_log("局域网查询访问地址已复制")

    @staticmethod
    def _lan_display_host(configured_host: str) -> str:
        if configured_host not in ("0.0.0.0", "::", ""):
            return configured_host
        try:
            addresses = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
            for item in addresses:
                address = item[4][0]
                if address and not address.startswith("127."):
                    return address
        except OSError:
            pass
        return "127.0.0.1"

    def save_config_from_dialog(self, values: dict) -> bool:
        try:
            self.validate_config_values(values)
            storage_path = resolve_storage_path(values["storage_path"])
            if not storage_path.exists():
                answer = QMessageBox.question(
                    self,
                    TEXT["config_title"],
                    f"\u5b58\u50a8\u76ee\u5f55\u4e0d\u5b58\u5728\uff1a{storage_path}\n\u662f\u5426\u521b\u5efa\uff1f",
                )
                if answer != QMessageBox.Yes:
                    return False
                storage_path.mkdir(parents=True, exist_ok=True)

            with RUNTIME_CONFIG.open("r", encoding="utf-8") as handle:
                raw_config = json.load(handle)
            raw_config.update(values)
            raw_config["disable_duplicate_scan"] = duplicate_policy_to_legacy_disable(values["duplicate_policy"])
            with RUNTIME_CONFIG.open("w", encoding="utf-8") as handle:
                json.dump(raw_config, handle, ensure_ascii=False, indent=2)
                handle.write("\n")

            self.config = get_config()
            self.recordings_dir = resolve_storage_path(self.config.storage_path)
            self.storage_path_status.setText(str(self.recordings_dir))
            self.apply_config_status()
            self.update_disk_status(log_event=True)
            self.add_log(TEXT["config_saved"])
            QMessageBox.information(self, TEXT["config_title"], TEXT["config_saved_hint"])
            return True
        except Exception as exc:
            self.add_log(f"{TEXT['config_save_failed']}\uff1a{exc}")
            QMessageBox.warning(self, TEXT["config_title"], f"{TEXT['config_save_failed']}\uff1a{exc}")
            return False

    def validate_config_values(self, values: dict) -> None:
        if not values["storage_path"]:
            raise ValueError("storage_path is empty")
        if int(values["auto_stop_timeout"]) < 5:
            raise ValueError("auto_stop_timeout must be >= 5")
        if int(values["min_free_disk_gb"]) < 1:
            raise ValueError("min_free_disk_gb must be >= 1")
        if values["resolution"] not in RESOLUTION_OPTIONS:
            raise ValueError("resolution is invalid")
        if not 10 <= int(values["fps"]) <= 30:
            raise ValueError("fps must be between 10 and 30")
        if values["resolution_policy"] not in {
            "config_first",
            "auto_best",
            "smooth_first",
        }:
            raise ValueError("resolution_policy is invalid")
        if values["recording_writer_codec"] not in {"MJPG", "XVID"}:
            raise ValueError("recording_writer_codec is invalid")
        if values["duplicate_policy"] not in VALID_DUPLICATE_POLICIES:
            raise ValueError("duplicate_policy is invalid")
        if int(values["duplicate_block_seconds"]) < 1:
            raise ValueError("duplicate_block_seconds must be >= 1")
        if values["watermark_position"] not in {value for _label, value in WATERMARK_POSITIONS}:
            raise ValueError("watermark_position is invalid")
        if not 0.4 <= float(values["watermark_font_scale"]) <= 3.0:
            raise ValueError("watermark_font_scale must be between 0.4 and 3.0")
        if not str(values["watermark_color"]).startswith("#") or len(str(values["watermark_color"])) != 7:
            raise ValueError("watermark_color must be a hex color like #00FF00")
        if not 0.1 <= float(values["watermark_opacity"]) <= 1.0:
            raise ValueError("watermark_opacity must be between 0.1 and 1.0")
        if not values["mp4_output_folder"]:
            raise ValueError("mp4_output_folder is empty")
        if int(values["frame_idle_timeout"]) < 1:
            raise ValueError("frame_idle_timeout must be >= 1")
        if float(values["frame_motion_threshold"]) <= 0:
            raise ValueError("frame_motion_threshold must be > 0")
        shared_path = str(values.get("shared_storage_path", "") or "").strip()
        if ".." in Path(shared_path).parts:
            raise ValueError("shared_storage_path cannot contain ..")
        if bool(values.get("shared_storage_enabled")) and not shared_path:
            raise ValueError("shared_storage_path is required when shared storage is enabled")

    def _on_shared_storage_update(self, status_text: str, log_text: str) -> None:
        self.shared_storage_status.setText(status_text)
        if log_text:
            self.add_log(log_text)

    def _capture_shared_recording_context(self) -> dict[str, object] | None:
        if self.recorder is None or not self.recorder.is_recording():
            return None
        video_path = self._current_video_path()
        if video_path is None:
            return None
        tracking_number = (
            str(getattr(self.recorder, "current_tracking_number", "") or "").strip()
            or str(self.last_tracking_number or "").strip()
        )
        return {
            "avi_path": Path(video_path),
            "tracking_number": tracking_number,
            "label_image_path": self.current_label_image_path,
        }

    def schedule_shared_storage_copy(self, context: dict[str, object] | None) -> threading.Thread | None:
        if not context or self.config is None:
            return None
        if not bool(getattr(self.config, "shared_storage_enabled", False)):
            self.shared_storage_status.setText("\u5171\u4eab\u5b58\u50a8\u672a\u542f\u7528")
            return None
        if not bool(getattr(self.config, "shared_storage_copy_after_recording", True)):
            return None

        shared_path_text = str(getattr(self.config, "shared_storage_path", "") or "").strip()
        if not shared_path_text:
            self.shared_storage_update.emit(
                "\u5171\u4eab\u5b58\u50a8\u8def\u5f84\u672a\u914d\u7f6e",
                "\u5171\u4eab\u5b58\u50a8\u8def\u5f84\u4e3a\u7a7a\uff0c\u5df2\u8df3\u8fc7\u590d\u5236",
            )
            return None
        if ".." in Path(shared_path_text).parts:
            self.shared_storage_update.emit(
                "\u5171\u4eab\u5b58\u50a8\u8def\u5f84\u4e0d\u5b89\u5168",
                "\u5171\u4eab\u5b58\u50a8\u8def\u5f84\u5305\u542b ..\uff0c\u5df2\u8df3\u8fc7\u590d\u5236",
            )
            return None

        avi_path = Path(context.get("avi_path") or "")
        copy_key = str(avi_path.resolve())
        with self._shared_copy_lock:
            if copy_key in self._shared_copy_scheduled:
                return None
            self._shared_copy_scheduled.add(copy_key)

        thread = threading.Thread(
            target=self._copy_recording_to_shared_storage,
            args=(context, shared_path_text, copy_key),
            name="shared-storage-copy",
            daemon=True,
        )
        thread.start()
        return thread

    def _copy_recording_to_shared_storage(
        self,
        context: dict[str, object],
        shared_path_text: str,
        copy_key: str,
    ) -> None:
        self.shared_storage_update.emit(
            "\u6b63\u5728\u590d\u5236\u5230\u5171\u4eab\u5b58\u50a8",
            "\u5f00\u59cb\u540e\u53f0\u590d\u5236\u5f55\u50cf\u8bc1\u636e\u5230\u5171\u4eab\u5b58\u50a8",
        )
        try:
            writable, message = test_shared_storage_writable(shared_path_text)
            if not writable:
                raise OSError(message)

            avi_path = Path(context.get("avi_path") or "")
            tracking_number = normalize_tracking_number(str(context.get("tracking_number") or ""))
            safe_tracking = re.sub(r"[^A-Z0-9_-]+", "_", tracking_number).strip("_") or "UNKNOWN"
            timestamp = self._shared_recording_timestamp(avi_path)
            target_root = Path(shared_path_text)
            target_dir = target_root / timestamp[:8] / f"{safe_tracking}_{timestamp}"
            target_dir.mkdir(parents=True, exist_ok=True)

            sources: list[Path] = []
            if bool(getattr(self.config, "shared_storage_copy_avi", True)):
                sources.append(avi_path)
            if bool(getattr(self.config, "shared_storage_copy_mp4", True)):
                mp4_path = QueryManager(
                    self.config.excel_path,
                    self.config.mp4_output_folder,
                ).existing_mp4_path(avi_path, tracking_number)
                if mp4_path is not None:
                    sources.append(mp4_path)
            if bool(getattr(self.config, "shared_storage_copy_label_image", True)):
                label_path = context.get("label_image_path")
                if label_path:
                    sources.append(Path(label_path))

            copied: list[str] = []
            for source in sources:
                safe_source = self._validated_shared_storage_source(source)
                if safe_source is None or not safe_source.is_file():
                    continue
                shutil.copy2(safe_source, target_dir / safe_source.name)
                copied.append(safe_source.name)

            if not copied:
                raise FileNotFoundError("\u6ca1\u6709\u53ef\u590d\u5236\u7684\u5f55\u50cf\u6216\u9762\u5355\u6587\u4ef6")
            self.shared_storage_update.emit(
                "\u5df2\u590d\u5236\u5230\u5171\u4eab\u5b58\u50a8",
                f"\u5df2\u590d\u5236\u5230\u5171\u4eab\u5b58\u50a8\uff1a{target_dir}",
            )
        except Exception as exc:  # noqa: BLE001
            self.shared_storage_update.emit(
                "\u5171\u4eab\u5b58\u50a8\u590d\u5236\u5931\u8d25\uff0c\u5df2\u4fdd\u7559\u672c\u5730\u6587\u4ef6",
                f"\u5171\u4eab\u5b58\u50a8\u590d\u5236\u5931\u8d25\uff0c\u5df2\u4fdd\u7559\u672c\u5730\u6587\u4ef6\uff1a{exc}",
            )
        finally:
            with self._shared_copy_lock:
                self._shared_copy_scheduled.discard(copy_key)

    def _validated_shared_storage_source(self, source: Path) -> Path | None:
        try:
            resolved = source.resolve()
            relative = resolved.relative_to(self.recordings_dir.resolve())
        except (OSError, ValueError):
            return None
        if ".." in relative.parts:
            return None
        if {part.lower() for part in relative.parts} & SHARED_STORAGE_FORBIDDEN_PARTS:
            return None
        if resolved.suffix.lower() not in SHARED_STORAGE_ALLOWED_EXTENSIONS:
            return None
        lowered_name = resolved.name.lower()
        if lowered_name.startswith(("license_state", "trial_state")) or resolved.suffix.lower() == ".pem":
            return None
        return resolved

    @staticmethod
    def _shared_recording_timestamp(avi_path: Path) -> str:
        match = re.search(r"(\d{8})[_-]?(\d{6})", avi_path.stem)
        if match:
            return f"{match.group(1)}_{match.group(2)}"
        try:
            return datetime.fromtimestamp(avi_path.stat().st_mtime).strftime("%Y%m%d_%H%M%S")
        except OSError:
            return datetime.now().strftime("%Y%m%d_%H%M%S")

    def on_open_recordings_clicked(self) -> None:
        target = self.recordings_dir
        if target.exists():
            os.startfile(str(target))
            self.add_log(f"\u5df2\u6253\u5f00\u5f55\u50cf\u76ee\u5f55\uff1a{target}")
            return

        QMessageBox.warning(self, TEXT["recordings_missing_title"], f"\u5f55\u50cf\u76ee\u5f55\u4e0d\u5b58\u5728\uff1a{target}")
        self.add_log(f"\u5f55\u50cf\u76ee\u5f55\u4e0d\u5b58\u5728\uff1a{target}")

    def on_open_current_video_clicked(self) -> None:
        target = self._current_video_path()
        if target is None:
            QMessageBox.information(self, "打开当前录像", "暂无当前录像")
            self.add_log("打开当前录像：暂无当前录像")
            return
        if not target.exists():
            QMessageBox.warning(self, "打开当前录像", f"录像文件不存在：{target}")
            self.add_log(f"打开当前录像失败，文件不存在：{target}")
            return
        try:
            os.startfile(str(target.resolve()))
            self.add_log(f"已打开当前录像：{target}")
        except OSError as exc:
            QMessageBox.warning(self, "打开当前录像", f"无法打开录像文件：{exc}")
            self.add_log(f"打开当前录像失败：{exc}")

    def on_open_current_video_folder_clicked(self) -> None:
        target = self._current_video_path()
        if target is None:
            QMessageBox.information(self, "打开当前录像文件夹", "暂无当前录像")
            self.add_log("打开当前录像文件夹：暂无当前录像")
            return
        folder = target.parent
        if not folder.exists():
            QMessageBox.warning(self, "打开当前录像文件夹", f"录像文件夹不存在：{folder}")
            self.add_log(f"打开当前录像文件夹失败，目录不存在：{folder}")
            return
        try:
            os.startfile(str(folder.resolve()))
            self.add_log(f"已打开当前录像文件夹：{folder}")
        except OSError as exc:
            QMessageBox.warning(self, "打开当前录像文件夹", f"无法打开录像文件夹：{exc}")
            self.add_log(f"打开当前录像文件夹失败：{exc}")

    def on_tracking_entered(self) -> None:
        barcode_received_monotonic = time.monotonic()
        self.add_log(
            "barcode_received: "
            f"timestamp={datetime.now().isoformat(timespec='milliseconds')}"
        )
        raw_value = self.scan_input.text()
        tracking_number = normalize_tracking_number(raw_value)
        if not tracking_number:
            self.add_log("\u626b\u7801\u8f93\u5165\u4e3a\u7a7a\uff0c\u5df2\u5ffd\u7565")
            self.scan_input.clear()
            self.scan_input.setFocus()
            return

        if not is_valid_tracking_number(tracking_number):
            reason = get_invalid_tracking_reason(tracking_number)
            self.current_tracking.setText("\u5355\u53f7\u683c\u5f0f\u5f02\u5e38\uff0c\u5df2\u5ffd\u7565")
            self.add_log(f"\u5df2\u5ffd\u7565\u65e0\u6548\u5355\u53f7\uff1a{tracking_number}\uff0c\u539f\u56e0\uff1a{reason}")
            self.play_sound_hint("invalid_tracking")
            self.add_recent_tracking(tracking_number or "\u7a7a", "\u5355\u53f7\u683c\u5f0f\u5f02\u5e38\uff0c\u5df2\u5ffd\u7565")
            self.scan_input.clear()
            self.scan_input.setFocus()
            return

        should_block, block_status = self.should_block_duplicate(tracking_number)
        if should_block:
            self.current_tracking.setText(f"{tracking_number} ({block_status})")
            self.add_recent_tracking(tracking_number, block_status)
            self.scan_input.clear()
            self.scan_input.setFocus()
            return

        self.last_tracking_number = tracking_number
        self.tracking_last_seen[tracking_number] = time.monotonic()
        self.current_tracking.setText(tracking_number)
        self.add_log(f"\u6536\u5230\u5355\u53f7\uff1a{tracking_number}")
        self._play_success_beep()
        self.process_tracking_number(tracking_number, barcode_received_monotonic)
        self.scan_input.clear()
        self.scan_input.setFocus()

    def should_block_duplicate(self, tracking_number: str) -> tuple[bool, str]:
        if self.config is None:
            return False, ""
        policy = getattr(self.config, "duplicate_policy", "block_completed_only")

        if policy == "allow":
            if tracking_number in self.tracking_last_seen:
                self.add_log(f"\u91cd\u590d\u5355\u53f7\uff0c\u7b56\u7565\u5141\u8bb8\u7ee7\u7eed\u5904\u7406\uff1a{tracking_number}")
            return False, ""

        if policy == "block_completed_only":
            if tracking_number in self.completed_tracking_numbers:
                self.add_log(f"\u5355\u53f7\u5df2\u6210\u529f\u5904\u7406\uff0c\u91cd\u590d\u5df2\u62e6\u622a\uff1a{tracking_number}")
                return True, TEXT["duplicate_blocked_completed"]
            return False, ""

        if policy == "block_within_seconds":
            last_seen = self.tracking_last_seen.get(tracking_number)
            if last_seen is not None and time.monotonic() - last_seen < float(self.config.duplicate_block_seconds):
                self.add_log(f"\u65f6\u95f4\u7a97\u53e3\u5185\u91cd\u590d\u5355\u53f7\u5df2\u62e6\u622a\uff1a{tracking_number}")
                return True, TEXT["duplicate_blocked_window"]
            return False, ""

        return False, ""

    def process_tracking_number(
        self,
        tracking_number: str,
        barcode_received_monotonic: float | None = None,
    ) -> None:
        scan_started = barcode_received_monotonic or time.monotonic()
        tracking_number = normalize_tracking_number(tracking_number)
        if not is_valid_tracking_number(tracking_number):
            reason = get_invalid_tracking_reason(tracking_number)
            self.add_log(f"\u5df2\u5ffd\u7565\u65e0\u6548\u5355\u53f7\uff1a{tracking_number}\uff0c\u539f\u56e0\uff1a{reason}")
            self.play_sound_hint("invalid_tracking")
            return
        if self.config is None:
            self.add_log("\u914d\u7f6e\u672a\u8bfb\u53d6\uff0c\u65e0\u6cd5\u5f55\u50cf")
            self.add_recent_tracking(tracking_number, TEXT["recording_failed"])
            return

        if self.camera is None or not self.camera.is_opened() or self.recorder is None:
            self.add_log(TEXT["start_first"])
            self.add_recent_tracking(tracking_number, TEXT["camera_retry"])
            return

        self.add_log("before_trial_check")
        if not self.ensure_recording_authorized(
            prompt_for_activation=False,
            popup_once=True,
            use_session_cache=True,
        ):
            self.add_log("after_trial_check: allowed=FALSE")
            self.add_recent_tracking(tracking_number, TEXT["recording_failed"])
            return
        self.add_log("after_trial_check: allowed=TRUE")

        if not self.update_disk_status(log_event=False) or not has_min_free_disk_space(
            self.recordings_dir,
            self.config.min_free_disk_gb,
        ):
            self.disk_status.setText(TEXT["disk_low"])
            self.add_log(LOW_DISK_BLOCKED_MESSAGE)
            self.add_recent_tracking(tracking_number, TEXT["disk_retry"])
            return

        try:
            previous_shared_context = self._capture_shared_recording_context()
            self.add_log("before_recording_start")
            video_path = self.recorder.switch_segment(tracking_number)
            elapsed_ms = (time.monotonic() - scan_started) * 1000.0
            self.add_log(
                "recording_started: "
                f"timestamp={datetime.now().isoformat(timespec='milliseconds')}, "
                f"scan_to_recording_start_elapsed_ms={elapsed_ms:.1f}"
            )
            self.schedule_shared_storage_copy(previous_shared_context)
            self.last_video_path = Path(video_path)
            self.last_scan_monotonic = time.monotonic()
            self.recording_status.setText(TEXT["recording"])
            self.update_recording_experience_status()
            self.add_log(f"\u5df2\u5f00\u59cb\u5f55\u50cf\uff1a{video_path}")
            self.play_sound_hint("record_start")
            label_image_path = None
            self.current_label_image_path = None
            QTimer.singleShot(
                1000,
                lambda number=tracking_number, path=Path(video_path): self.save_delayed_label_snapshot(
                    number,
                    path,
                ),
            )
        except Exception as exc:
            self.recording_status.setText(TEXT["recording_failed"])
            self.add_log(f"\u5f55\u50cf\u542f\u52a8\u5931\u8d25\uff1a{exc}")
            self.add_recent_tracking(tracking_number, TEXT["recording_failed_retry"])
            return

        if self.excel_manager is None:
            self.excel_status.setText(TEXT["excel_failed"])
            self.add_log("Excel \u672a\u521d\u59cb\u5316\uff0c\u672a\u5199\u5165\u8bb0\u5f55")
            self.add_recent_tracking(tracking_number, TEXT["excel_failed_retry"])
            return

        try:
            self.add_log("before_excel_write")
            write_target = self.excel_manager.append_record(
                tracking_number,
                video_path,
                source="gui",
                remark="GUI\u626b\u7801\u5f55\u5236",
                label_image_path=label_image_path,
            )
            if write_target == "backup_csv":
                self.excel_status.setText("\u5df2\u5199\u5165\u5907\u4efdCSV")
                QMessageBox.warning(
                    self,
                    TEXT["query_title"],
                    f"\u53f0\u8d26 Excel \u6587\u4ef6\u88ab\u5360\u7528\uff0c\u5355\u53f7 {tracking_number} \u7684\u8bb0\u5f55\u5df2\u5199\u5165\u5907\u4efd CSV\uff0c\u8bf7\u5173\u95ed Excel \u540e\u5904\u7406\u8be5\u5907\u4efd\u8bb0\u5f55\u3002",
                )
                self.add_log(f"Excel \u88ab\u5360\u7528\uff0c\u5df2\u5199\u5165\u5907\u4efd CSV\uff1a{tracking_number}")
                self.add_log("after_excel_write: success=TRUE target=backup_csv")
                self.completed_tracking_numbers.add(tracking_number)
                self.add_recent_tracking(tracking_number, "Excel\u88ab\u5360\u7528\uff0c\u5df2\u5199\u5165\u5907\u4efdCSV")
            else:
                self.excel_status.setText(TEXT["excel_ok"])
                self.add_log(f"Excel\u5199\u5165\u6210\u529f\uff1a{tracking_number}")
                self.add_log("after_excel_write: success=TRUE")
                self.completed_tracking_numbers.add(tracking_number)
                self.add_recent_tracking(tracking_number, TEXT["recorded_excel_ok"])
        except Exception as exc:
            self.excel_status.setText(TEXT["excel_failed"])
            self.add_log(f"Excel \u5199\u5165\u5931\u8d25\uff1a{exc}")
            self.add_log("after_excel_write: success=FALSE")
            self.add_recent_tracking(tracking_number, TEXT["excel_failed_retry"])

    def add_recent_tracking(self, tracking_number: str, status: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.recent_tracking_records.insert(0, (timestamp, tracking_number, status))
        self.recent_tracking_records = self.recent_tracking_records[:10]
        self.refresh_recent_tracking_box()

    def refresh_recent_tracking_box(self) -> None:
        lines = [
            f"{timestamp}  {tracking_number}  {status}"
            for timestamp, tracking_number, status in self.recent_tracking_records
        ]
        self.recent_tracking_box.setPlainText("\n".join(lines))

    def update_recent_tracking_status(self, status: str) -> None:
        if not self.recent_tracking_records:
            return
        timestamp, tracking_number, _old_status = self.recent_tracking_records[0]
        self.recent_tracking_records[0] = (timestamp, tracking_number, status)
        self.refresh_recent_tracking_box()

    def run_smoke_recording_scan(self, attempt: int = 0) -> None:
        if self.camera is not None and self.camera.is_opened() and self.recorder is not None:
            self.scan_input.setText("GUISTUDY0001")
            self.on_tracking_entered()
            print(f"smoke_last_video_path => {self.last_video_path}")
            QTimer.singleShot(2500, self.close)
            return

        if attempt >= 12:
            print("smoke_recording_scan => camera_not_ready")
            QTimer.singleShot(200, self.close)
            return

        QTimer.singleShot(500, lambda: self.run_smoke_recording_scan(attempt + 1))

    def run_smoke_autostop_scan(self, attempt: int = 0) -> None:
        if self.camera is not None and self.camera.is_opened() and self.recorder is not None:
            self.scan_input.setText("GUIAUTOSTOP0001")
            self.on_tracking_entered()
            QTimer.singleShot(4200, self.print_smoke_autostop_status)
            QTimer.singleShot(4600, self.close)
            return

        if attempt >= 12:
            print("smoke_autostop => camera_not_ready")
            QTimer.singleShot(200, self.close)
            return

        QTimer.singleShot(500, lambda: self.run_smoke_autostop_scan(attempt + 1))

    def print_smoke_autostop_status(self) -> None:
        is_recording = self.recorder.is_recording() if self.recorder is not None else False
        print(f"smoke_autostop_recording => {is_recording}")
        print(f"smoke_autostop_status => {self.recording_status.text()}")

    def run_smoke_disk_scan(self, attempt: int = 0) -> None:
        if self.camera is not None and self.camera.is_opened() and self.recorder is not None:
            self.scan_input.setText("GUIDISKLOW0001")
            self.on_tracking_entered()
            print(f"smoke_disk_status => {self.disk_status.text()}")
            print(f"smoke_disk_last_video_path => {self.last_video_path}")
            QTimer.singleShot(500, self.close)
            return

        if attempt >= 12:
            print("smoke_disk => camera_not_ready")
            QTimer.singleShot(200, self.close)
            return

        QTimer.singleShot(500, lambda: self.run_smoke_disk_scan(attempt + 1))

    def run_smoke_watchdog_logic(self) -> None:
        if self.config is not None:
            self.frame_failure_count = int(self.config.watchdog_max_failures) + 1
            self.update_watchdog_status()
            print(f"smoke_watchdog_should_trigger => {self.should_trigger_watchdog()}")
        QTimer.singleShot(400, self.close)

    def run_smoke_duplicate_policy_logic(self) -> None:
        if self.config is None:
            print("smoke_duplicate_policy => config_not_loaded")
            QTimer.singleShot(200, self.close)
            return

        self.config = replace(self.config, duplicate_policy="block_completed_only", duplicate_block_seconds=30)
        self.apply_config_status()
        self.completed_tracking_numbers.add("DUPLICATE_COMPLETED")
        print(f"smoke_duplicate_policy_status => {self.duplicate_policy_status.text()}")
        print(f"smoke_duplicate_completed => {self.should_block_duplicate('DUPLICATE_COMPLETED')}")

        self.config = replace(self.config, duplicate_policy="block_within_seconds", duplicate_block_seconds=30)
        self.apply_config_status()
        self.tracking_last_seen["DUPLICATE_WINDOW"] = time.monotonic()
        print(f"smoke_duplicate_window_status => {self.duplicate_policy_status.text()}")
        print(f"smoke_duplicate_window => {self.should_block_duplicate('DUPLICATE_WINDOW')}")

        self.config = replace(self.config, duplicate_policy="allow", duplicate_block_seconds=30)
        self.apply_config_status()
        self.tracking_last_seen["DUPLICATE_ALLOWED"] = time.monotonic()
        print(f"smoke_duplicate_allow_status => {self.duplicate_policy_status.text()}")
        print(f"smoke_duplicate_allow => {self.should_block_duplicate('DUPLICATE_ALLOWED')}")
        QTimer.singleShot(400, self.close)

    def run_smoke_query_logic(self) -> None:
        if cv2 is None:
            print("smoke_query => opencv_missing")
            QTimer.singleShot(200, self.close)
            return

        try:
            import numpy as np

            base = Path("D:/AI_Projects/99_Temp/shipping-monitor-query-core-test")
            base.mkdir(parents=True, exist_ok=True)
            avi_path = base / "20260518_235900_YT123456789.avi"
            writer = cv2.VideoWriter(str(avi_path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (320, 240))
            for index in range(10):
                frame = np.full((240, 320, 3), (20 + index * 8, 90, 160), dtype=np.uint8)
                writer.write(frame)
            writer.release()

            excel_path = base / "scan_records.xlsx"
            excel = ExcelManager(excel_path)
            excel.append_record(
                "YT123456789",
                avi_path,
                source="gui",
                remark="smoke query",
                timestamp=datetime(2026, 5, 18, 23, 59, 0),
            )
            query = QueryManager(excel_path)
            results = query.query("YT123456789", "2026-05-18", "2026-05-18", "GUI")
            mp4_path = query.ensure_mp4(avi_path, "YT123456789")
            mp4_capture = cv2.VideoCapture(str(mp4_path))
            mp4_readable, _frame = mp4_capture.read()
            mp4_capture.release()
            refreshed = query.query("YT123456789", "2026-05-18", "2026-05-18", "GUI")
            csv_path = query.export_csv(refreshed, base / "query_results.csv")
            xlsx_path = query.export_excel(refreshed, base / "query_results.xlsx")
            print(f"smoke_query_count => {len(results)}")
            print(f"smoke_query_mp4 => {mp4_path}")
            print(f"smoke_query_mp4_exists => {mp4_path.exists()}")
            print(f"smoke_query_mp4_readable => {mp4_readable}")
            print(f"smoke_query_csv => {csv_path.exists()}")
            print(f"smoke_query_excel => {xlsx_path.exists()}")
            print(f"smoke_query_json => {query.query_json('YT123456789', '2026-05-18', '2026-05-18', 'GUI')}")
        except Exception as exc:
            print(f"smoke_query_failed => {exc}")
        QTimer.singleShot(300, self.close)

    def run_smoke_frame_idle_logic(self) -> None:
        if cv2 is None:
            print("smoke_frame_idle => opencv_missing")
            QTimer.singleShot(200, self.close)
            return

        try:
            import numpy as np

            if self.config is not None:
                self.config = replace(
                    self.config,
                    auto_stop_enabled=True,
                    auto_stop_timeout=1,
                    frame_idle_detection_enabled=True,
                    frame_idle_timeout=2,
                    frame_motion_threshold=3.0,
                )
                self.apply_config_status()

            class FakeRecorder:
                def is_recording(self) -> bool:
                    return True

            static_frame = np.zeros((240, 320, 3), dtype=np.uint8)
            changed_frame = np.full((240, 320, 3), 80, dtype=np.uint8)

            self.reset_frame_idle_state()
            self.update_frame_motion_state(static_frame)
            self.update_frame_motion_state(static_frame)
            self.frame_idle_started_at = time.monotonic() - 3
            self.update_frame_motion_state(static_frame)
            static_increased = self.frame_idle_seconds >= 2
            print(f"smoke_frame_idle_static_increased => {static_increased}")

            self.update_frame_motion_state(changed_frame)
            reset_after_motion = self.frame_idle_seconds == 0 and not self.frame_is_static
            print(f"smoke_frame_idle_reset_on_motion => {reset_after_motion}")

            self.recorder = FakeRecorder()  # type: ignore[assignment]
            self.last_scan_monotonic = time.monotonic() - 2
            self.frame_idle_seconds = 0
            print(f"smoke_frame_idle_no_stop_when_motion => {not self.should_auto_stop_now()}")

            self.frame_idle_seconds = 3
            print(f"smoke_frame_idle_stop_when_static => {self.should_auto_stop_now()}")
            self.recorder = None
        except Exception as exc:
            print(f"smoke_frame_idle_failed => {exc}")
        QTimer.singleShot(300, self.close)

    def closeEvent(self, event) -> None:
        self.stop_lan_query_server(show_message=False)
        if self.fullscreen_preview_window is not None:
            self.fullscreen_preview_window.close()
        self.stop_preview()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    window = ShippingMonitorWindow()
    window.show()

    if "--smoke-test-camera" in sys.argv:
        QTimer.singleShot(200, window.on_start_clicked)
        QTimer.singleShot(2200, window.close)
    elif "--smoke-test-record" in sys.argv:
        QTimer.singleShot(200, window.on_start_clicked)
        QTimer.singleShot(1000, window.run_smoke_recording_scan)
    elif "--smoke-test-autostop" in sys.argv:
        if window.config is not None:
            window.config = replace(window.config, auto_stop_timeout=2, keep_camera_on_timeout=True)
            window.apply_config_status()
        QTimer.singleShot(200, window.on_start_clicked)
        QTimer.singleShot(1000, window.run_smoke_autostop_scan)
    elif "--smoke-test-disk" in sys.argv:
        if window.config is not None:
            window.config = replace(window.config, min_free_disk_gb=999999)
            window.apply_config_status()
        QTimer.singleShot(200, window.on_start_clicked)
        QTimer.singleShot(1000, window.run_smoke_disk_scan)
    elif "--smoke-test-watchdog" in sys.argv:
        QTimer.singleShot(200, window.run_smoke_watchdog_logic)
    elif "--smoke-test-duplicate-policy" in sys.argv:
        QTimer.singleShot(200, window.run_smoke_duplicate_policy_logic)
    elif "--smoke-test-query" in sys.argv:
        QTimer.singleShot(200, window.run_smoke_query_logic)
    elif "--smoke-test-frame-idle" in sys.argv:
        QTimer.singleShot(200, window.run_smoke_frame_idle_logic)
    elif "--smoke-test-scan" in sys.argv:
        QTimer.singleShot(200, lambda: window.scan_input.setText("  YT8869602188120\t"))
        QTimer.singleShot(260, window.on_tracking_entered)
        QTimer.singleShot(360, lambda: window.scan_input.setText("YT8869602188121"))
        QTimer.singleShot(420, window.on_tracking_entered)
        QTimer.singleShot(900, window.close)
    elif "--smoke-test" in sys.argv:
        QTimer.singleShot(800, window.close)

    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
