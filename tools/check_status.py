import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from safe_print import safe_print

with open('D:/AI_Projects/shipping-monitor-gui-final/src/gui_main.py', 'r', encoding='utf-8') as f:
    s = f.read()

# Check status panel layout
idx = s.find('core_rows = [')
if idx >= 0:
    snippet = s[idx:idx+800]
    lines = snippet.split('\n')[:25]
    for i, line in enumerate(lines):
        safe_print(f'  {i}: {repr(line)}')
