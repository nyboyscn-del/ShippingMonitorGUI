import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from safe_print import safe_print

path = r'D:\AI_Projects\shipping-monitor-gui-final\src\gui_main.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find on_camera_calibration_clicked function
start = content.find('    def on_camera_calibration_clicked(self) -> None:')
if start == -1:
    safe_print('Function not found!')
    exit(1)

# Find end of function
next_def = content.find('\n    def ', start + 1)
if next_def == -1:
    next_def = len(content)

func = content[start:next_def]
safe_print('Current function:')
safe_print(func)
safe_print('---')

# The correct function with proper indentation:
new_func = '''    def on_camera_calibration_clicked(self) -> None:
        """打开摄像头矫正设置对话框（使用 dialogs.camera_calibration_dialog 模块）"""
        try:
            if CameraCalibrationSettingsDialog is None:
                QMessageBox.warning(self, "摄像头矫正", "摄像头矫正模块加载失败")
                return
            dialog = CameraCalibrationSettingsDialog(
                RUNTIME_CONFIG,
                EXAMPLE_CONFIG,
                self,
            )
            dialog.exec_()
            # 重新加载配置以使矫正参数生效
            self.config = get_config()
            if self.recorder is not None:
                self.recorder._config = self.config
            self.add_log("摄像头矫正设置已打开/保存")
        except Exception as e:
            self.add_log(f"ERROR: on_camera_calibration_clicked 异常: {e}")
            import traceback
            traceback.print_exc()
'''

# Replace
content = content[:start] + new_func + content[next_def:]

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
safe_print('Fixed on_camera_calibration_clicked indentation')
