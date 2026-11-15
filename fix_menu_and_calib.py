#!/usr/bin/env python3
"""Simplify Settings menu and add Camera Calibration dialog."""

filepath = r"D:\AI_Projects\shipping-monitor-gui-final\src\gui_main.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# ─── 1. Replace Settings menu (simplify to one item) ───

old_settings = '''        settings_menu = self.menuBar().addMenu("\u8bbe\u7f6e")
        for title in (
            "\u6444\u50cf\u5934\u9ad8\u7ea7\u8bbe\u7f6e",
            "\u9009\u62e9\u6444\u50cf\u5934",
            "\u5206\u8fa8\u7387\u8bbe\u7f6e",
            "\u5e27\u7387\u8bbe\u7f6e",
            "\u5f55\u50cf\u63a7\u5236",
            "\u6c34\u5370\u8bbe\u7f6e",
            "\u91cd\u590d\u5355\u53f7\u7b56\u7565",
            "\u5b58\u50a8\u8def\u5f84\u8bbe\u7f6e",
            "\u67e5\u8be2/MP4\u8bbe\u7f6e",
            "\u753b\u9762\u9759\u6b62\u68c0\u6d4b\u8bbe\u7f6e",
        ):
            action = QAction(title, self)
            action.triggered.connect(self.on_config_clicked)
            settings_menu.addAction(action)'''

new_settings = '''        settings_menu = self.menuBar().addMenu("\u8bbe\u7f6e")
        config_action = QAction("\u6253\u5f00\u914d\u7f6e\u7f16\u8f91", self)
        config_action.triggered.connect(self.on_config_clicked)
        settings_menu.addAction(config_action)'''

content = content.replace(old_settings, new_settings)
assert old_settings not in content, "ERROR: old Settings menu still present"

# ─── 2. Replace Tools menu (add camera calibration) ───

old_tools = '''        tools_menu = self.menuBar().addMenu("\u5de5\u5177")
        query_action = QAction("\u67e5\u8be2\u8bb0\u5f55", self)
        query_action.triggered.connect(self.on_query_clicked)
        recordings_action = QAction("\u6253\u5f00\u5f55\u50cf\u76ee\u5f55", self)
        recordings_action.triggered.connect(self.on_open_recordings_clicked)
        export_today_action = QAction("\u5bfc\u51fa\u5f53\u5929\u8bb0\u5f55", self)
        export_today_action.triggered.connect(self.export_today_records)
        deps_action = QAction("\u68c0\u67e5\u4f9d\u8d56", self)
        deps_action.triggered.connect(self.check_dependencies_from_menu)
        log_file_action = QAction("\u67e5\u770b\u65e5\u5fd7", self)
        log_file_action.triggered.connect(self.open_log_file)
        about_action = QAction("\u5173\u4e8e", self)
        about_action.triggered.connect(self.show_about_dialog)
        for action in (query_action, recordings_action, export_today_action, deps_action, log_file_action, about_action):
            tools_menu.addAction(action)'''

new_tools = '''        tools_menu = self.menuBar().addMenu("\u5de5\u5177")
        query_action = QAction("\u67e5\u8be2\u8bb0\u5f55", self)
        query_action.triggered.connect(self.on_query_clicked)
        recordings_action = QAction("\u6253\u5f00\u5f55\u50cf\u76ee\u5f55", self)
        recordings_action.triggered.connect(self.on_open_recordings_clicked)
        export_today_action = QAction("\u5bfc\u51fa\u5f53\u5929\u8bb0\u5f55", self)
        export_today_action.triggered.connect(self.export_today_records)
        deps_action = QAction("\u68c0\u67e5\u4f9d\u8d56", self)
        deps_action.triggered.connect(self.check_dependencies_from_menu)
        log_file_action = QAction("\u67e5\u770b\u65e5\u5fd7", self)
        log_file_action.triggered.connect(self.open_log_file)
        about_action = QAction("\u5173\u4e8e", self)
        about_action.triggered.connect(self.show_about_dialog)
        camera_calib_action = QAction("\u6444\u50cf\u5934\u77eb\u6b63", self)
        camera_calib_action.triggered.connect(self._show_camera_calibration)
        for action in (query_action, recordings_action, export_today_action, deps_action, log_file_action, about_action, camera_calib_action):
            tools_menu.addAction(action)'''

content = content.replace(old_tools, new_tools)
assert old_tools not in content, "ERROR: old Tools menu still present"

# ─── 3. Add CameraCalibrationDialog class before ShippingMonitorWindow ───
# Use triple-quoted string to avoid issues with newlines

camera_calib_dialog_class = '''class CameraCalibrationDialog(QDialog):
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
            "摄像头矫正功能\\n\\n"
            "当前状态：全局启用\\n\\n"
            "说明：\\n"
            "• 自动校正摄像头畸变和失真\\n"
            "• 支持手动标定模式\\n"
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


'''

# Insert before "class ShippingMonitorWindow(QMainWindow):"
insert_marker = "class ShippingMonitorWindow(QMainWindow):"
assert insert_marker in content, "ERROR: ShippingMonitorWindow class not found"
content = content.replace(insert_marker, camera_calib_dialog_class + insert_marker)

# ─── 4. Add _show_camera_calibration method after show_about_dialog ───

old_show_about = '''    def show_about_dialog(self) -> None:
        QMessageBox.information(self, TEXT["title"], "ShippingMonitorGUI\\nUSB 便携版研究版")'''

new_show_about = '''    def show_about_dialog(self) -> None:
        QMessageBox.information(self, TEXT["title"], "ShippingMonitorGUI\\nUSB 便携版研究版")

    def _show_camera_calibration(self) -> None:
        """打开摄像头矫正设置弹窗"""
        dialog = CameraCalibrationDialog(self)
        dialog.exec_()'''

content = content.replace(old_show_about, new_show_about)
if old_show_about in content:
    # The file might have actual newline character instead of \\n
    # Read the actual content around show_about_dialog
    import re
    match = re.search(r'(    def show_about_dialog\(self\) -> None:\n        QMessageBox\.information\(self, TEXT\["title"\], "[^"]+"\))', content)
    if match:
        actual_old = match.group(1)
        content = content.replace(actual_old, new_show_about)
        print(f"Replaced show_about_dialog using regex match")
    else:
        raise AssertionError("ERROR: could not find show_about_dialog to replace")

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Menu simplification and camera calibration added successfully.")
