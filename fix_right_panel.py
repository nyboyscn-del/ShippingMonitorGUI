#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from safe_print import safe_print

"""Fix right-side panel layout in gui_main.py: no scroll, compact, fixed visible."""

import re

filepath = r"D:\AI_Projects\shipping-monitor-gui-final\src\gui_main.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# ─── 1. Replace _build_ui() inside ShippingMonitorWindow ───

old_build_ui = '''    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)

        self.preview_area = QLabel(TEXT["preview_placeholder"])
        self.preview_area.setAlignment(Qt.AlignCenter)
        self.preview_area.setMinimumSize(760, 430)
        self.preview_area.setFrameShape(QFrame.StyledPanel)
        self.preview_area.setStyleSheet(
            "QLabel { background: #111827; color: #e5e7eb; font-size: 22px; border-radius: 6px; }"
        )
        content_layout.addWidget(self.preview_area, stretch=3)

        side_widget = QWidget()
        side_panel = QVBoxLayout(side_widget)
        side_panel.setSpacing(10)
        side_panel.addWidget(self._create_status_panel())
        side_panel.addWidget(self._create_input_panel())
        side_panel.addWidget(self._create_recent_tracking_panel())
        side_panel.addWidget(self._create_button_panel())
        side_panel.addStretch(1)

        self.side_scroll_area = QScrollArea()
        self.side_scroll_area.setWidgetResizable(True)
        self.side_scroll_area.setFrameShape(QFrame.NoFrame)
        self.side_scroll_area.setMinimumWidth(320)
        self.side_scroll_area.setMaximumWidth(340)
        self.side_scroll_area.setWidget(side_widget)
        content_layout.addWidget(self.side_scroll_area, stretch=1)

        root_layout.addLayout(content_layout, stretch=4)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(180)
        self.log_box.setPlaceholderText(TEXT["log_placeholder"])
        root_layout.addWidget(self.log_box, stretch=1)
        self._apply_responsive_fonts()'''

new_build_ui = '''    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)

        self.preview_area = QLabel(TEXT["preview_placeholder"])
        self.preview_area.setAlignment(Qt.AlignCenter)
        self.preview_area.setMinimumSize(760, 430)
        self.preview_area.setFrameShape(QFrame.StyledPanel)
        self.preview_area.setStyleSheet(
            "QLabel { background: #111827; color: #e5e7eb; font-size: 22px; border-radius: 6px; }"
        )
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
        self._apply_responsive_fonts()'''

content = content.replace(old_build_ui, new_build_ui)
assert old_build_ui not in content, "ERROR: old _build_ui still present after replacement"

# ─── 2. Replace _create_status_panel ───

old_status_panel = '''    def _create_status_panel(self) -> QGroupBox:
        group = QGroupBox(TEXT["status_panel"])
        layout = QGridLayout(group)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(10)

        self.current_tracking = QLabel(TEXT["not_scanned"])
        self.recording_status = QLabel(TEXT["not_started"])
        self.excel_status = QLabel(TEXT["not_written"])
        self.disk_status = QLabel(TEXT["not_checked"])
        self.camera_status = QLabel(TEXT["not_started"])
        self.license_status = QLabel(TEXT["not_verified"])
        self.storage_path_status = QLabel(TEXT["not_loaded"])
        self.auto_stop_status = QLabel(TEXT["not_loaded"])
        self.idle_countdown_status = QLabel("--")
        self.watchdog_status = QLabel(TEXT["not_loaded"])
        self.frame_failures_status = QLabel("0/0")
        self.min_disk_status = QLabel("--")
        self.duplicate_policy_status = QLabel(TEXT["not_loaded"])
        self.selected_resolution_status = QLabel(TEXT["not_loaded"])
        self.actual_resolution_status = QLabel("--")
        self.actual_fps_status = QLabel("--")
        self.frame_motion_status = QLabel("--")
        self.lens_correction_status = QLabel(TEXT["off"])

        rows = [
            (TEXT["current_tracking"], self.current_tracking),
            (TEXT["recording_status"], self.recording_status),
            (TEXT["camera_status"], self.camera_status),
            (TEXT["excel_status"], self.excel_status),
            (TEXT["disk_status"], self.disk_status),
            (TEXT["actual_resolution_fps"], self.actual_resolution_status),
            (TEXT["storage_path"], self.storage_path_status),
            (TEXT["idle_countdown"], self.idle_countdown_status),
            (TEXT["frame_motion_status"], self.frame_motion_status),
        ]

        for row, (label_text, value_widget) in enumerate(rows):
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
            value_widget.setWordWrap(True)
            layout.addWidget(label, row, 0)
            layout.addWidget(value_widget, row, 1)

        return group'''

new_status_panel = '''    def _create_status_panel(self) -> QGroupBox:
        group = QGroupBox(TEXT["status_panel"])
        layout = QGridLayout(group)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(3)

        # Initialize ALL status labels (needed by business logic elsewhere)
        self.current_tracking = QLabel(TEXT["not_scanned"])
        self.recording_status = QLabel(TEXT["not_started"])
        self.excel_status = QLabel(TEXT["not_written"])
        self.disk_status = QLabel(TEXT["not_checked"])
        self.camera_status = QLabel(TEXT["not_started"])
        self.license_status = QLabel(TEXT["not_verified"])
        self.storage_path_status = QLabel(TEXT["not_loaded"])
        self.auto_stop_status = QLabel(TEXT["not_loaded"])
        self.idle_countdown_status = QLabel("--")
        self.watchdog_status = QLabel(TEXT["not_loaded"])
        self.frame_failures_status = QLabel("0/0")
        self.min_disk_status = QLabel("--")
        self.duplicate_policy_status = QLabel(TEXT["not_loaded"])
        self.selected_resolution_status = QLabel(TEXT["not_loaded"])
        self.actual_resolution_status = QLabel("--")
        self.actual_fps_status = QLabel("--")
        self.frame_motion_status = QLabel("--")
        self.lens_correction_status = QLabel(TEXT["off"])

        # Only show core fields in the panel
        core_rows = [
            (TEXT["current_tracking"], self.current_tracking),
            (TEXT["recording_status"], self.recording_status),
            (TEXT["camera_status"], self.camera_status),
            (TEXT["excel_status"], self.excel_status),
            (TEXT["disk_status"], self.disk_status),
            (TEXT["actual_resolution_fps"], self.actual_resolution_status),
            (TEXT["storage_path"], self.storage_path_status),
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

        return group'''

content = content.replace(old_status_panel, new_status_panel)
assert old_status_panel not in content, "ERROR: old _create_status_panel still present"

# ─── 3. Replace _create_recent_tracking_panel ───

old_recent = '''    def _create_recent_tracking_panel(self) -> QGroupBox:
        group = QGroupBox(TEXT["recent_tracking_panel"])
        layout = QVBoxLayout(group)

        self.recent_tracking_box = QTextEdit()
        self.recent_tracking_box.setReadOnly(True)
        self.recent_tracking_box.setMinimumHeight(130)
        layout.addWidget(self.recent_tracking_box)

        return group'''

new_recent = '''    def _create_recent_tracking_panel(self) -> QGroupBox:
        group = QGroupBox(TEXT["recent_tracking_panel"])
        layout = QVBoxLayout(group)

        self.recent_tracking_box = QTextEdit()
        self.recent_tracking_box.setReadOnly(True)
        self.recent_tracking_box.setMinimumHeight(90)
        self.recent_tracking_box.setMaximumHeight(120)
        layout.addWidget(self.recent_tracking_box)

        return group'''

content = content.replace(old_recent, new_recent)
assert old_recent not in content, "ERROR: old _create_recent_tracking_panel still present"

# ─── 4. Replace _create_button_panel ───

old_buttons = '''    def _create_button_panel(self) -> QGroupBox:
        group = QGroupBox(TEXT["actions"])
        layout = QVBoxLayout(group)

        start_button = QPushButton(TEXT["start"])
        stop_button = QPushButton(TEXT["stop_preview"])
        config_button = QPushButton(TEXT["open_config"])
        query_button = QPushButton(TEXT["open_query"])
        recordings_button = QPushButton(TEXT["open_recordings"])
        exit_button = QPushButton(TEXT["exit"])

        start_button.clicked.connect(self.on_start_clicked)
        stop_button.clicked.connect(self.on_stop_clicked)
        config_button.clicked.connect(self.on_config_clicked)
        query_button.clicked.connect(self.on_query_clicked)
        recordings_button.clicked.connect(self.on_open_recordings_clicked)
        exit_button.clicked.connect(self.close)

        for button in (start_button, stop_button, query_button, recordings_button, config_button, exit_button):
            button.setMinimumHeight(34)
            layout.addWidget(button)

        return group'''

new_buttons = '''    def _create_button_panel(self) -> QGroupBox:
        group = QGroupBox(TEXT["actions"])
        layout = QGridLayout(group)
        layout.setHorizontalSpacing(6)
        layout.setVerticalSpacing(4)

        start_button = QPushButton(TEXT["start"])
        stop_button = QPushButton(TEXT["stop_preview"])
        query_button = QPushButton(TEXT["open_query"])
        recordings_button = QPushButton(TEXT["open_recordings"])
        config_button = QPushButton(TEXT["open_config"])
        exit_button = QPushButton(TEXT["exit"])

        start_button.clicked.connect(self.on_start_clicked)
        stop_button.clicked.connect(self.on_stop_clicked)
        config_button.clicked.connect(self.on_config_clicked)
        query_button.clicked.connect(self.on_query_clicked)
        recordings_button.clicked.connect(self.on_open_recordings_clicked)
        exit_button.clicked.connect(self.close)

        for btn in (start_button, stop_button, query_button, recordings_button, config_button, exit_button):
            btn.setMinimumHeight(30)

        layout.addWidget(start_button, 0, 0)
        layout.addWidget(stop_button, 0, 1)
        layout.addWidget(query_button, 1, 0)
        layout.addWidget(recordings_button, 1, 1)
        layout.addWidget(config_button, 2, 0)
        layout.addWidget(exit_button, 2, 1)

        return group'''

content = content.replace(old_buttons, new_buttons)
assert old_buttons not in content, "ERROR: old _create_button_panel still present"

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

safe_print("All 4 methods replaced successfully.")
