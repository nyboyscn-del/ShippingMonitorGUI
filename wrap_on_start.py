import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from safe_print import safe_print

path = r'D:\AI_Projects\shipping-monitor-gui-final\src\gui_main.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find on_start_clicked function
in_func = False
func_start = -1
func_end = -1
for i, line in enumerate(lines):
    if line.strip() == 'def on_start_clicked(self) -> None:':
        in_func = True
        func_start = i
        continue
    if in_func and line.startswith('    def ') and i > func_start + 1:
        func_end = i
        break
    if in_func and line.startswith('class ') and i > func_start + 1:
        func_end = i
        break

if func_end == -1:
    func_end = len(lines)

safe_print(f'on_start_clicked: lines {func_start+1} to {func_end}')

# Check if already wrapped
func_lines = lines[func_start:func_end]
func_text = ''.join(func_lines)
if 'try:' in func_text and 'except Exception' in func_text:
    safe_print('Already wrapped, skipping')
else:
    # Wrap: add try after def line, indent body, add except at end
    # The function body starts at func_start+1
    # We need to:
    # 1. Keep the def line as is
    # 2. Insert '        try:\n' at func_start+1
    # 3. Indent all body lines (from func_start+2 to func_end-1) by 4 spaces
    # 4. Insert except block before the next def/class
    
    # Step 1: insert try:
    lines.insert(func_start + 1, '        try:\n')
    func_end += 1  # because we inserted a line
    
    # Step 2: indent body lines (now starting at func_start+2)
    for j in range(func_start + 2, func_end):
        if lines[j].strip() == '':
            continue  # skip empty lines
        if lines[j].startswith('        '):
            lines[j] = '    ' + lines[j]  # add 4 more spaces
        elif lines[j].startswith('    '):
            lines[j] = '        ' + lines[j].lstrip()
        else:
            lines[j] = '        ' + lines[j]
    
    # Step 3: insert except block before func_end
    except_block = [
        '        except Exception as e:\n',
        '            self.add_log(f"ERROR: on_start_clicked 异常: {e}")\n',
        '            import traceback\n',
        '            traceback.print_exc()\n',
    ]
    # Insert before the next def/class (at func_end)
    for k, eline in enumerate(except_block):
        lines.insert(func_end + k, eline)
    
    safe_print('Wrapped on_start_clicked with try/except')

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
safe_print('Done')
