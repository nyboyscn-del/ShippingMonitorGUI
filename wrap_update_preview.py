import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from safe_print import safe_print

path = r'D:\AI_Projects\shipping-monitor-gui-final\src\gui_main.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find update_preview_frame method
start_idx = None
for i, line in enumerate(lines):
    if '    def update_preview_frame(self) -> None:' in line:
        start_idx = i
        break

if start_idx is None:
    safe_print('ERROR: update_preview_frame not found')
    exit(1)

safe_print(f'Found update_preview_frame at line {start_idx+1}')

# Find end of method (next def or end of file)
end_idx = len(lines)
for i in range(start_idx + 1, len(lines)):
    if lines[i].startswith('    def ') and i > start_idx:
        end_idx = i
        break

safe_print(f'Method spans lines {start_idx+1} to {end_idx}')

# Extract method lines
method_lines = lines[start_idx:end_idx]

# Find first non-empty, non-comment line after def line (the body start)
body_start = None
for i in range(1, len(method_lines)):
    stripped = method_lines[i].strip()
    if stripped and not stripped.startswith('"""'):
        body_start = i
        break
    if stripped.startswith('"""'):
        # Skip docstring
        continue

if body_start is None:
    safe_print('ERROR: Could not find method body')
    exit(1)

safe_print(f'Body starts at relative line {body_start+1}')

# Check if already wrapped
if 'try:' in method_lines[body_start]:
    safe_print('Already wrapped with try/except, skipping')
else:
    # Insert try: before body
    method_lines.insert(body_start, '        try:\n')
    
    # Indent all body lines (from body_start+1 onwards, since we inserted try:)
    # The body now starts at body_start+1
    new_body_start = body_start + 1
    for i in range(new_body_start, len(method_lines)):
        if method_lines[i].strip():  # non-empty line
            method_lines[i] = '    ' + method_lines[i]
    
    # Add except block at end
    method_lines.append('\n')
    method_lines.append('        except Exception as e:\n')
    method_lines.append('            self.add_log(f"ERROR in update_preview_frame: {e}")\n')
    method_lines.append('            import traceback\n')
    method_lines.append('            traceback.print_exc()\n')
    
    # Replace in lines
    lines[start_idx:end_idx] = method_lines
    
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    safe_print('Successfully wrapped update_preview_frame with try/except')

# Verify
safe_print('\nVerification:')
for i in range(max(0, start_idx-2), min(len(lines), start_idx+10)):
    safe_print(f'{i+1}: {lines[i]}', end='')
