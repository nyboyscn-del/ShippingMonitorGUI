#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from safe_print import safe_print

"""Fix gui_main.py: remove unused methods, add _toggle_log_visibility."""

import re

filepath = r"D:\AI_Projects\shipping-monitor-gui-final\src\gui_main.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Remove _toggle_compact_mode method
pattern1 = r"    def _toggle_compact_mode\(self\) -> None:\n.*?        self\.add_log\(f.*?\)\n"
content = re.sub(pattern1, "", content, flags=re.DOTALL)

# 2. Remove _update_compact_mode_ui method
pattern2 = r"    def _update_compact_mode_ui\(self\) -> None:\n.*?self\.log_box\.setMaximumHeight\(16777215\)\n"
content = re.sub(pattern2, "", content, flags=re.DOTALL)

# 3. Remove _update_advanced_status_ui method
pattern3 = r"    def _update_advanced_status_ui\(self\) -> None:\n.*?            widget\.setVisible\(visible\)\n"
content = re.sub(pattern3, "", content, flags=re.DOTALL)

# 4. Remove _show_camera_settings method
pattern4 = r"    def _show_camera_settings\(self\) -> None:\n.*?        \)\n"
content = re.sub(pattern4, "", content, flags=re.DOTALL)

# 5. Remove _show_mp4_generator method
pattern5 = r"    def _show_mp4_generator\(self\) -> None:\n.*?        \)\n"
content = re.sub(pattern5, "", content, flags=re.DOTALL)

# 6. Add _toggle_log_visibility after _toggle_advanced_status
new_method = '''
    def _toggle_log_visibility(self) -> None:
        """Toggle log box visibility via View menu."""
        visible = not self.log_box.isVisible()
        self.log_box.setVisible(visible)
        self.log_toggle_action.setChecked(visible)
        self.add_log(f"日志区域已{'显示' if visible else '隐藏'}")
'''

# Insert after _toggle_advanced_status's add_log line
insert_after = '        self.add_log(f"高级状态已{\'显示\' if visible else \'隐藏\'}")'
content = content.replace(insert_after, insert_after + new_method)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

safe_print("Done! Methods updated.")
