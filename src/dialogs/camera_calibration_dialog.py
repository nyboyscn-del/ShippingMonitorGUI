"""
摄像头矫正配置对话框。
独立文件，不修改 gui_main.py / config_manager.py / 录像逻辑。
"""

import json
import os
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


# 默认配置值
DEFAULTS = {
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

# 配置字段列表
FIELDS = list(DEFAULTS.keys())

# 配置 / 示例配置文件的相对路径（相对于项目根目录）
CONFIG_REL_PATH = "config/config.json"
EXAMPLE_REL_PATH = "config/config.example.json"


def _find_project_root(start: str | os.PathLike | None = None) -> Path:
    """从当前文件向上查找项目根目录（包含 config/ 目录）。"""
    if start is None:
        start = Path(__file__).resolve()
    p = Path(start).parent if not Path(start).is_dir() else Path(start)
    for parent in [p] + list(p.parents):
        if (parent / "config").is_dir():
            return parent
    # 降级：使用 cwd
    cwd = Path.cwd()
    if (cwd / "config").is_dir():
        return cwd
    return cwd


class CameraCalibrationDialog(QDialog):
    """摄像头矫正设置弹窗 - 基础参数配置"""

    def __init__(
        self,
        config_path,  # str（文件路径）或 dict（RUNTIME_CONFIG）
        example_config_path=None,  # str 或 dict 或 None
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("摄像头矫正")
        self.resize(520, 420)

        # 解析 config_path
        if isinstance(config_path, dict):
            self._config_dict = config_path
            self._config_file_path = _find_project_root() / CONFIG_REL_PATH
        elif isinstance(config_path, (str, os.PathLike)):
            self._config_file_path = Path(config_path).resolve()
            self._config_dict = self._load_json(self._config_file_path, DEFAULTS)
        else:
            self._config_dict = dict(DEFAULTS)
            self._config_file_path = _find_project_root() / CONFIG_REL_PATH

        # 解析 example_config_path
        self._example_dict = None
        self._example_file_path = None
        if isinstance(example_config_path, dict):
            self._example_dict = example_config_path
        elif isinstance(example_config_path, (str, os.PathLike)):
            self._example_file_path = Path(example_config_path).resolve()
            self._example_dict = self._load_json(self._example_file_path, {})
        else:
            # 尝试自动发现
            auto = _find_project_root() / EXAMPLE_REL_PATH
            if auto.exists():
                self._example_file_path = auto
                self._example_dict = self._load_json(auto, {})

        # 确保 config_dict 包含所有字段
        for k, v in DEFAULTS.items():
            self._config_dict.setdefault(k, v)

        self._widgets: dict[str, QWidget] = {}
        self._build_ui()

    # ------------------------------------------------------------------ #
    #  UI 构建
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # ---- 分组一：基础开关 ----
        gb_basic = QGroupBox("基础开关")
        form_basic = QFormLayout(gb_basic)
        cb_enabled = QCheckBox("启用摄像头矫正")
        cb_enabled.setChecked(self._config_dict.get(
            "camera_calibration_enabled", True))
        form_basic.addRow(cb_enabled)
        self._widgets["camera_calibration_enabled"] = cb_enabled
        root.addWidget(gb_basic)

        # ---- 分组二：画面增强 ----
        gb_enhance = QGroupBox("画面增强")
        form_enhance = QFormLayout(gb_enhance)

        sb_brightness = QSpinBox()
        sb_brightness.setRange(-100, 100)
        sb_brightness.setValue(self._config_dict.get(
            "camera_calibration_brightness", 0))
        form_enhance.addRow("亮度", sb_brightness)
        self._widgets["camera_calibration_brightness"] = sb_brightness

        sb_contrast = QSpinBox()
        sb_contrast.setRange(-100, 100)
        sb_contrast.setValue(self._config_dict.get(
            "camera_calibration_contrast", 0))
        form_enhance.addRow("对比度", sb_contrast)
        self._widgets["camera_calibration_contrast"] = sb_contrast

        root.addWidget(gb_enhance)

        # ---- 分组三：ROI 裁切 ----
        gb_roi = QGroupBox("ROI 裁切")
        form_roi = QFormLayout(gb_roi)

        cb_roi = QCheckBox("启用 ROI 裁切")
        cb_roi.setChecked(self._config_dict.get(
            "camera_calibration_roi_enabled", False))
        form_roi.addRow(cb_roi)
        self._widgets["camera_calibration_roi_enabled"] = cb_roi

        for label, key in [
            ("X", "camera_calibration_roi_x"),
            ("Y", "camera_calibration_roi_y"),
            ("宽度 W", "camera_calibration_roi_w"),
            ("高度 H", "camera_calibration_roi_h"),
        ]:
            sb = QSpinBox()
            sb.setRange(0, 10000)
            sb.setValue(self._config_dict.get(key, 0))
            form_roi.addRow(label, sb)
            self._widgets[key] = sb

        root.addWidget(gb_roi)

        # ---- 分组四：对焦设置 ----
        gb_focus = QGroupBox("\u5bf9\u7126\u8bbe\u7f6e")
        form_focus = QFormLayout(gb_focus)

        cb_autofocus = QCheckBox("\u542f\u7528\u81ea\u52a8\u5bf9\u7126")
        cb_autofocus.setChecked(self._config_dict.get(
            "camera_autofocus_enabled", True))
        cb_autofocus.toggled.connect(self._on_autofocus_toggled)
        form_focus.addRow(cb_autofocus)
        self._widgets["camera_autofocus_enabled"] = cb_autofocus

        cb_manual_focus = QCheckBox("\u542f\u7528\u624b\u52a8\u5bf9\u7126")
        cb_manual_focus.setChecked(self._config_dict.get(
            "camera_focus_enabled", False)
            and not self._config_dict.get("camera_autofocus_enabled", True))
        cb_manual_focus.toggled.connect(self._on_manual_focus_toggled)
        form_focus.addRow(cb_manual_focus)
        self._widgets["camera_focus_enabled"] = cb_manual_focus

        sb_focus_value = QSpinBox()
        sb_focus_value.setRange(0, 255)
        sb_focus_value.setValue(self._config_dict.get(
            "camera_focus_value", 0))
        form_focus.addRow("\u624b\u52a8\u5bf9\u7126\u503c", sb_focus_value)
        self._widgets["camera_focus_value"] = sb_focus_value
        self._update_focus_controls()

        root.addWidget(gb_focus)

        # ---- 分组五：说明文字 ----
        info = QLabel(
            "\u8bf4\u660e\uff1a\n"
            "1. \u4eae\u5ea6\uff1a\u6570\u503c\u8d8a\u5927\u753b\u9762\u8d8a\u4eae\uff0c\u9002\u5408\u73af\u5883\u504f\u6697\u65f6\u4f7f\u7528\u3002\n"
            "2. \u5bf9\u6bd4\u5ea6\uff1a\u6570\u503c\u8d8a\u5927\u9ed1\u767d\u53cd\u5dee\u8d8a\u660e\u663e\uff0c\u9002\u5408\u9762\u5355\u6587\u5b57\u4e0d\u6e05\u6670\u65f6\u4f7f\u7528\u3002\n"
            "3. ROI \u88c1\u5207\uff1a\u53ea\u4fdd\u7559\u6307\u5b9a\u533a\u57df\u753b\u9762\uff0cX/Y \u662f\u5de6\u4e0a\u89d2\u4f4d\u7f6e\uff0cW/H \u662f\u88c1\u5207\u5bbd\u9ad8\u3002\n"
            "4. ROI \u7684 W/H \u4e3a 0 \u65f6\u4e0d\u4f1a\u88c1\u5207\u3002\n"
            "5. \u53c2\u6570\u4fdd\u5b58\u540e\uff0c\u4f1a\u5e94\u7528\u5230\u5b9e\u65f6\u9884\u89c8\u548c\u65b0\u5f55\u5236\u7684\u89c6\u9891\u3002\n"
            "6. \u5bf9\u7126\uff1a\u90e8\u5206\u6444\u50cf\u5934\u652f\u6301\u81ea\u52a8\u5bf9\u7126\u6216\u624b\u52a8\u5bf9\u7126\uff1b\u5982\u679c\u6444\u50cf\u5934\u4e0d\u652f\u6301\uff0c\u4fdd\u5b58\u53c2\u6570\u4e0d\u4f1a\u62a5\u9519\uff0c\u4f46\u5b9e\u9645\u753b\u9762\u53ef\u80fd\u4e0d\u53d8\u5316\u3002"
        )
        info.setWordWrap(True)
        root.addWidget(info)

        root.addStretch(1)

        # ---- 底部按钮 ----
        btns = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        reset_button = btns.addButton(
            "\u6062\u590d\u9ed8\u8ba4\u6444\u50cf\u5934\u8bbe\u7f6e",
            QDialogButtonBox.ResetRole,
        )
        reset_button.clicked.connect(self._reset_defaults)
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    # ------------------------------------------------------------------ #
    #  保存
    # ------------------------------------------------------------------ #

    def _on_save(self) -> None:
        try:
            # 1. 从 UI 读取值
            values: dict = {}
            for key in FIELDS:
                w = self._widgets[key]
                if isinstance(w, QCheckBox):
                    values[key] = w.isChecked()
                elif isinstance(w, QSpinBox):
                    values[key] = w.value()
                else:
                    values[key] = DEFAULTS[key]
            if values["camera_autofocus_enabled"]:
                values["camera_focus_enabled"] = False
            elif values["camera_focus_enabled"]:
                values["camera_autofocus_enabled"] = False
            values["camera_calibration_brightness"] = max(
                -50, min(50, int(values["camera_calibration_brightness"]))
            )
            values["camera_calibration_contrast"] = max(
                -50, min(50, int(values["camera_calibration_contrast"]))
            )

            # 2. 更新内存中的 config dict
            self._config_dict.update(values)

            # 3. 写回 config.json
            self._save_json(self._config_file_path, self._config_dict)

            QMessageBox.information(
                self, "摄像头矫正", "摄像头矫正参数已保存")
            self.accept()

        except Exception as exc:
            QMessageBox.warning(
                self, "保存失败", f"保存摄像头矫正参数失败：\n{exc}")

    # ------------------------------------------------------------------ #
    #  工具方法
    # ------------------------------------------------------------------ #

    def _on_autofocus_toggled(self, checked: bool) -> None:
        if checked:
            manual = self._widgets.get("camera_focus_enabled")
            if isinstance(manual, QCheckBox):
                manual.blockSignals(True)
                manual.setChecked(False)
                manual.blockSignals(False)
        self._update_focus_controls()

    def _on_manual_focus_toggled(self, checked: bool) -> None:
        if checked:
            autofocus = self._widgets.get("camera_autofocus_enabled")
            if isinstance(autofocus, QCheckBox):
                autofocus.blockSignals(True)
                autofocus.setChecked(False)
                autofocus.blockSignals(False)
        self._update_focus_controls()

    def _update_focus_controls(self) -> None:
        autofocus = self._widgets.get("camera_autofocus_enabled")
        manual = self._widgets.get("camera_focus_enabled")
        focus_value = self._widgets.get("camera_focus_value")
        auto_enabled = isinstance(autofocus, QCheckBox) and autofocus.isChecked()
        manual_enabled = isinstance(manual, QCheckBox) and manual.isChecked()
        if isinstance(manual, QCheckBox):
            manual.setEnabled(not auto_enabled)
        if isinstance(focus_value, QSpinBox):
            focus_value.setEnabled(manual_enabled and not auto_enabled)

    def _reset_defaults(self) -> None:
        for key, value in DEFAULTS.items():
            widget = self._widgets[key]
            if isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))
        self._update_focus_controls()

    @staticmethod
    def _load_json(path: Path, defaults: dict) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except FileNotFoundError:
            return dict(defaults)
        except Exception:
            return dict(defaults)

    @staticmethod
    def _save_json(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
