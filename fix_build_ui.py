#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from safe_print import safe_print

"""Replace _build_ui() in gui_main.py with corrected layout."""

import re

filepath = r"D:\AI_Projects\shipping-monitor-gui-final\src\gui_main.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# Read the new _build_ui method from a separate file
# We'll construct it as a string here
new_build_ui = '''    def _build_ui(self) -> None:
        self._create_menu_bar()
        central = QWidget(self)
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)

        # === Left: preview area ===
        self.preview_area = QLabel(TEXT["preview_placeholder"])
        self.preview_area.setAlignment(Qt.AlignCenter)
        self.preview_area.setMinimumSize(760, 430)
        self.preview_area.setFrameShape(QFrame.StyledPanel)
        self.preview_area.setStyleSheet(
            "QLabel { background: #111827; color: #e5e7eb; font-size: 22px; border-radius: 6px; }"
        )
        content_layout.addWidget(self.preview_area, stretch=3)

        # === Right: fixed operation bar ===
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        # 1. Core status (fixed top, compressed)
        self._core_status_widget = self._create_core_status_panel()
        right_layout.addWidget(self._core_status_widget)

        # 2. Advanced status (hidden by default, collapsible)
        self._advanced_status_container = self._create_advanced_status_panel()
        self._advanced_status_container.setVisible(False)
        self.show_advanced_status = False
        right_layout.addWidget(self._advanced_status_container)

        # 3. Scan input (always visible)
        right_layout.addWidget(self._create_input_panel())

        # 4. Recent tracking (always visible, fixed small height)
        recent = self._create_recent_tracking_panel()
        recent.setMaximumHeight(110)
        right_layout.addWidget(recent)

        # 5. Action buttons (always visible)
        right_layout.addWidget(self._create_button_panel())

        right_layout.addStretch(1)

        # Fix right panel width
        right_container.setMinimumWidth(300)
        right_container.setMaximumWidth(340)
        content_layout.addWidget(right_container, stretch=1)

        root_layout.addLayout(content_layout, stretch=4)

        # === Bottom: log area (fixed height) ===
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(120)
        self.log_box.setMaximumHeight(160)
        self.log_box.setPlaceholderText(TEXT["log_placeholder"])
        root_layout.addWidget(self.log_box, stretch=0)

        self._apply_responsive_fonts()
'''

# Find the old _build_ui method and replace it
# Match from "    def _build_ui" to the next "    def " at indent level 4
pattern = r"    def _build_ui\(self\) -> None:\n.*?(?=\n    def [a-zA-Z])"
replacement = new_build_ui.rstrip()
content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

safe_print("Done! _build_ui() replaced.")
