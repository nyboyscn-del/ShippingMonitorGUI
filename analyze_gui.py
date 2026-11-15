#!/usr/bin/env python3
"""
Fix gui_main.py structure:
1. Find all methods that belong to the main window class
2. Create class ShippingMonitorWindow(QMainWindow) and put them inside
3. Leave ConfigDialog as a separate class
4. Fix main() to instantiate ShippingMonitorWindow()
"""

import re

filepath = r"D:\AI_Projects\shipping-monitor-gui-final\src\gui_main.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# The methods that belong to the main window class are currently
# inside ConfigDialog (wrong!). We need to:
# 1. Extract them from ConfigDialog
# 2. Create a new class ShippingMonitorWindow(QMainWindow)
# 3. Put them in the correct class

# Actually, the file structure is:
# - Module-level functions (duplicate_policy_to_legacy_disable, etc.)
# - class ConfigDialog(QDialog):  <-- contains _build_ui, etc. (WRONG!)
# - class FakeRecorder:
# - def main():

# The correct structure should be:
# - Module-level functions
# - class ShippingMonitorWindow(QMainWindow):
# - class ConfigDialog(QDialog):
# - class FakeRecorder:
# - def main():

# Let me find where ConfigDialog's __init__ ends and where the misplaced methods start.
# Actually, let me find the _build_ui that's inside ConfigDialog.

# Strategy: 
# 1. Find "class ConfigDialog(QDialog):"
# 2. Find the end of ConfigDialog (next "class " or "def " at module level)
# 3. Extract the methods that belong to the main window
# 4. Create the ShippingMonitorWindow class

# This is complex. Let me try a different approach:
# Reconstruct the file from scratch based on what we know.

# Actually, let me just find and fix the issue.
# The problem is: _build_ui() etc. are inside ConfigDialog.
# I need to:
# 1. Remove these methods from ConfigDialog
# 2. Create a new class ShippingMonitorWindow(QMainWindow) before ConfigDialog
# 3. Put the methods in ShippingMonitorWindow

# Let me find the line numbers.
# "class ConfigDialog(QDialog):" is at line 210
# The _build_ui() inside ConfigDialog is at line 219 (based on earlier search)
# Actually, earlier I searched for "def _build_ui" and found it at line 219.
# But that was BEFORE I removed duplicates. Now _build_ui is at line 219 (after fixes).

# Let me search for "class ConfigDialog" and "def _build_ui" again
config_dialog_match = re.search(r"class ConfigDialog\(QDialog\):", content)
print(f"ConfigDialog starts at position: {config_dialog_match.start()}")

# Find the _build_ui inside ConfigDialog
# Actually, let me use a simpler approach.
# I'll manually construct the correct file.

# Let me split the file into parts:
# Part 1: Imports and module-level functions (lines 1-209)
# Part 2: ConfigDialog class (incorrectly contains main window methods)
# Part 3: FakeRecorder class
# Part 4: main() function

# I need to:
# 1. Extract the main window methods from Part 2
# 2. Create Part 1.5: class ShippingMonitorWindow(QMainWindow)
# 3. Put the extracted methods in Part 1.5

# This is getting complex. Let me try a different approach:
# Delete ConfigDialog and reconstruct it without the misplaced methods.

# Actually, I think the simplest fix is:
# 1. Find where ConfigDialog's __init__ ends and _build_ui starts
# 2. Move everything from _build_ui to the end of ConfigDialog into a new class

# Let me just read the file and understand its structure manually.

print("This script needs manual review. Let me output the file structure.")
# Print lines around ConfigDialog
lines = content.split('\n')
for i, line in enumerate(lines):
    if i < 5:
        print(f"{i+1}: {line}")
    elif "class ConfigDialog" in line or "def _build_ui" in line or "class FakeRecorder" in line or "def main" in line:
        print(f"{i+1}: {line}")
    elif i > 210 and i < 240:
        print(f"{i+1}: {line}")
