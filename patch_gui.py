import re

path = r'D:\AI_Projects\shipping-monitor-gui-final\src\gui_main.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Operation 1: setWindowTitle - main window
old1 = '        self.setWindowTitle(f"{__project_name__}")'
new1 = '        self.setWindowTitle(f"{__project_name__} v{__version__} (Build {__build__})")'
if old1 in content:
    content = content.replace(old1, new1, 1)
    print('Op1 setWindowTitle main: OK')
else:
    print('Op1 setWindowTitle main: pattern NOT found')

# Operation 2: insert_imports - check if already present at module level
import_line = 'from version import __project_name__, __version__, __build__, __copyright__'
if import_line in content:
    print('Op2 imports: already present at module level, skip')
else:
    print('Op2 imports: WARNING - import line not found at module level')

# Operation 3: show_about_dialog - already done, verify
if 'msg = f"""{__project_name__}\\n版本：{__version__}\\n构建：{__build__}\\n{__copyright__}"""' in content:
    print('Op3 show_about_dialog: already correct')
else:
    print('Op3 show_about_dialog: needs check')

# Operation 4: wrap on_start_clicked with try/except
# Find the function and check if already wrapped
pattern_start = r'    def on_start_clicked\(self\) -> None:\n        if self\.preview_timer'
if pattern_start in content and 'try:\n            if self.preview_timer' not in content:
    # Replace the function body with try wrapping
    old_func_start = '    def on_start_clicked(self) -> None:\n        if self.preview_timer.isActive()'
    new_func_start = '    def on_start_clicked(self) -> None:\n        try:\n            if self.preview_timer.isActive()'
    if old_func_start in content:
        content = content.replace(old_func_start, new_func_start, 1)
        # Now add except at the end of the function
        # Find the line with self.scan_input.setFocus() and add except after it
        old_end = '        self.scan_input.setFocus()'
        new_end = '            self.scan_input.setFocus()\n        except Exception as e:\n            self.add_log(f"ERROR: on_start_clicked 异常: {e}")\n            import traceback\n            traceback.print_exc()'
        # Only replace the last occurrence (in on_start_clicked)
        # Find the function boundaries
        idx = content.find('    def on_start_clicked(self) -> None:')
        next_def = content.find('\n    def ', idx + 1)
        if next_def == -1:
            next_def = len(content)
        func_body = content[idx:next_def]
        if old_end in func_body and 'except Exception' not in func_body:
            new_func_body = func_body.replace(old_end, new_end, 1)
            content = content[:idx] + new_func_body + content[next_def:]
            print('Op4 on_start_clicked: wrapped with try/except')
        else:
            print('Op4 on_start_clicked: already wrapped or pattern not found')
    else:
        print('Op4 on_start_clicked: function start pattern not found')
else:
    print('Op4 on_start_clicked: already wrapped or pattern mismatch')

# Operation 4b: wrap on_camera_calibration_clicked with try/except
idx2 = content.find('    def on_camera_calibration_clicked(self) -> None:')
if idx2 != -1:
    next_def2 = content.find('\n    def ', idx2 + 1)
    if next_def2 == -1:
        next_def2 = len(content)
    func_body2 = content[idx2:next_def2]
    if 'try:' not in func_body2:
        # Wrap first line after docstring
        old_calib = '        """打开摄像头矫正设置对话框（使用 dialogs.camera_calibration_dialog 模块）"""\n        if CameraCalibrationSettingsDialog is None:'
        new_calib = '        """打开摄像头矫正设置对话框（使用 dialogs.camera_calibration_dialog 模块）"""\n        try:\n            if CameraCalibrationSettingsDialog is None:'
        if old_calib in func_body2:
            new_func_body2 = func_body2.replace(old_calib, new_calib, 1)
            # Add except at end
            old_end2 = '        self.add_log("摄像头矫正设置已打开/保存")'
            new_end2 = '            self.add_log("摄像头矫正设置已打开/保存")\n        except Exception as e:\n            self.add_log(f"ERROR: on_camera_calibration_clicked 异常: {e}")\n            import traceback\n            traceback.print_exc()'
            new_func_body2 = new_func_body2.replace(old_end2, new_end2, 1)
            content = content[:idx2] + new_func_body2 + content[next_def2:]
            print('Op4b on_camera_calibration_clicked: wrapped with try/except')
        else:
            print('Op4b: docstring pattern not found')
    else:
        print('Op4b: already wrapped')
else:
    print('Op4b: function not found')

# Operation 5: ConfigDialog title
old5 = f'self.setWindowTitle(f"{{__project_name__}} - 配置编辑")'
new5 = f'self.setWindowTitle(f"{{__project_name__}} v{{__version__}} (Build {{__build__}}) - 配置编辑")'
# Actually need to find the exact string in the file
# Let me search for it
if 'self.setWindowTitle(f"{__project_name__} - 配置编辑")' in content:
    content = content.replace(
        'self.setWindowTitle(f"{__project_name__} - 配置编辑")',
        'self.setWindowTitle(f"{__project_name__} v{__version__} (Build {__build__}) - 配置编辑")',
        1
    )
    print('Op5 ConfigDialog title: OK')
else:
    print('Op5 ConfigDialog title: pattern not found')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('All operations done, file written.')
