path = r'D:\AI_Projects\shipping-monitor-gui-final\src\gui_main.py'
with open(path, 'rb') as f:
    data = f.read()

# Find the line with 'ERROR: on_start_clicked'
idx = data.find(b'ERROR: on_start_clicked')
if idx != -1:
    # Find start of line
    line_start = data.rfind(b'\n', 0, idx) + 1
    # Find end of line
    line_end = data.find(b'\n', idx)
    if line_end == -1:
        line_end = len(data)
    old_line = data[line_start:line_end]
    print('Old line bytes:', old_line)
    print('Old line repr:', repr(old_line))
    
    # New line with correct UTF-8
    new_line = '            self.add_log(f"ERROR: on_start_clicked 异常: {e}")\n'.encode('utf-8')
    print('New line bytes:', new_line)
    
    # Replace
    data = data[:line_start] + new_line + data[line_end:]
    
    with open(path, 'wb') as f:
        f.write(data)
    print('Fixed!')
else:
    print('Pattern not found')
