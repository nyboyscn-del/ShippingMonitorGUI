#!/usr/bin/env python3
"""Keep only the LAST _build_ui() in gui_main.py, remove all earlier duplicates."""

import re

filepath = r"D:\AI_Projects\shipping-monitor-gui-final\src\gui_main.py"

with open(filepath, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find all line indices where "    def _build_ui(self)" occurs
indices = [i for i, line in enumerate(lines) if line.rstrip() == "    def _build_ui(self) -> None:"]

print(f"Found {len(indices)} occurrences at lines: {[i+1 for i in indices]}")

if len(indices) <= 1:
    print("No duplicates found, exiting.")
    exit(0)

# Keep only the LAST occurrence
# Strategy: rebuild file content:
# 1. Everything before the first occurrence
# 2. Everything from the last occurrence onwards
# But we need to SKIP the middle occurrences.

# Actually, simpler: find the last occurrence, then remove any previous 
# "_build_ui" method blocks.

# Let's use a different strategy:
# 1. Find the start of the LAST _build_ui (indices[-1])
# 2. Extract everything from that point to the end of file (or next method)
# 3. Reconstruct file: everything before indices[0] + extracted last _build_ui

last_start = indices[-1]

# Find where the last _build_ui ends (next method at same indent level, or EOF)
last_build_ui_lines = []
in_method = False
for i in range(last_start, len(lines)):
    line = lines[i]
    if i == last_start:
        in_method = True
    elif in_method and line.startswith("    def ") and not line.startswith("        "):
        # Next method at same indent level - stop
        break
    last_build_ui_lines.append(line)

print(f"Last _build_ui: lines {last_start+1} to {last_start+len(last_build_ui_lines)}")

# Now reconstruct the file:
# Everything before the FIRST _build_ui + the last _build_ui + everything after the last _build_ui
first_start = indices[0]
# Lines before first _build_ui
new_lines = lines[:first_start]
# Add the last _build_ui
new_lines.extend(last_build_ui_lines)
# Add everything after the last _build_ui (but skip the last _build_ui itself)
# Actually, we already have the last _build_ui. Now add everything AFTER it.
# The "last_build_ui_lines" includes from "    def _build_ui" to the line before next method.
# We need to add everything from the end of last _build_ui to EOF.

# Find where last_build_ui_lines ends in the original file
last_end = last_start + len(last_build_ui_lines)
new_lines.extend(lines[last_end:])

with open(filepath, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print(f"Done! Removed {len(indices)-1} duplicate(s).")
print(f"New file: {len(new_lines)} lines (was {len(lines)} lines)")
