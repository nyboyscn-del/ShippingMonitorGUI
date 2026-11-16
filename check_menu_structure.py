import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from safe_print import safe_print

"""
Part 5.2: 自动检查 gui_main.py 菜单结构
"""
import re
import sys

FILE = r"D:\AI_Projects\shipping-monitor-gui-final\src\gui_main.py"

with open(FILE, "r", encoding="utf-8") as f:
    content = f.read()

errors = []

# 1. 设置菜单应包含：打开配置编辑、摄像头矫正
if '"打开配置编辑"' not in content:
    errors.append("FAIL: 设置菜单缺少 '打开配置编辑'")
else:
    safe_print("OK: 设置菜单包含 '打开配置编辑'")

if '"摄像头矫正"' not in content:
    errors.append("FAIL: 设置菜单缺少 '摄像头矫正'")
else:
    safe_print("OK: 设置菜单包含 '摄像头矫正'")

# 2. 工具菜单应包含 6 项（不含摄像头矫正）
tool_items = ["查询记录", "打开录像目录", "导出当天记录", "检查依赖", "查看日志", "关于"]
for item in tool_items:
    if item in content:
        safe_print(f"OK: 工具菜单包含 '{item}'")
    else:
        errors.append(f"FAIL: 工具菜单缺少 '{item}'")

# 3. 工具菜单不应包含 摄像头矫正（在 tools_menu 的 for-action 循环中）
# 查找 _create_menu_bar 方法中 tools_menu 的 action 列表
pattern = r"for action in \((.*?)\):"
match = re.search(pattern, content, re.DOTALL)
if match:
    action_block = match.group(1)
    if "摄像头矫正" in action_block:
        errors.append("FAIL: 工具菜单的 action 列表包含 '摄像头矫正'")
    else:
        safe_print("OK: 工具菜单的 action 列表不包含 '摄像头矫正'")
else:
    safe_print("WARN: 未找到 tools_menu 的 action 列表（可能用了实例变量）")

# 4. 摄像头矫正绑定检查
if "self.camera_calibration_action.triggered.connect(self.on_camera_calibration_clicked)" in content:
    safe_print("OK: camera_calibration_action 绑定到 on_camera_calibration_clicked")
elif "camera_calibration_action" in content and "on_camera_calibration_clicked" in content:
    safe_print("WARN: camera_calibration_action 和 on_camera_calibration_clicked 均存在，但未找到直接绑定")
else:
    errors.append("FAIL: 未找到 camera_calibration_action 绑定")

# 5. on_camera_calibration_clicked 使用 CameraCalibrationSettingsDialog
if "def on_camera_calibration_clicked" in content:
    safe_print("OK: 存在 on_camera_calibration_clicked 方法")
    # 提取该方法内容
    m2 = re.search(r"def on_camera_calibration_clicked\(self.*?\) -> None:(.*?)(?=\n    def |\nclass )", content, re.DOTALL)
    if m2:
        method_body = m2.group(1)
        if "CameraCalibrationSettingsDialog" in method_body:
            safe_print("OK: on_camera_calibration_clicked 使用 CameraCalibrationSettingsDialog")
        else:
            errors.append("FAIL: on_camera_calibration_clicked 未使用 CameraCalibrationSettingsDialog")
        if "RUNTIME_CONFIG" in method_body and "EXAMPLE_CONFIG" in method_body:
            safe_print("OK: on_camera_calibration_clicked 使用 RUNTIME_CONFIG 和 EXAMPLE_CONFIG")
        else:
            errors.append("FAIL: on_camera_calibration_clicked 未使用 RUNTIME_CONFIG/EXAMPLE_CONFIG")
else:
    errors.append("FAIL: 未找到 on_camera_calibration_clicked 方法")

# 6. import 检查
if "from dialogs.camera_calibration_dialog import CameraCalibrationDialog as CameraCalibrationSettingsDialog" in content:
    safe_print("OK: import CameraCalibrationSettingsDialog 成功")
else:
    errors.append("FAIL: 未找到 CameraCalibrationSettingsDialog 的 import")

# 7. 旧绑定检查（菜单不应绑定 _show_camera_calibration）
if "self.camera_calib_action.triggered.connect(self._show_camera_calibration)" in content:
    errors.append("FAIL: 仍存在旧绑定 self.camera_calib_action -> _show_camera_calibration")
else:
    safe_print("OK: 无旧绑定 self.camera_calib_action -> _show_camera_calibration")

safe_print("\n===== 检查结果 =====")
if errors:
    safe_print(f"发现 {len(errors)} 个错误：")
    for e in errors:
        safe_print(f"  {e}")
    sys.exit(1)
else:
    safe_print("全部检查通过 ✅")
    sys.exit(0)
