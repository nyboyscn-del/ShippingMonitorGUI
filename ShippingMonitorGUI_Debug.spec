# -*- mode: python ; coding: utf-8 -*-

import PyQt5.sip


a = Analysis(
    ['src\\gui_main.py'],
    pathex=['src'],
    binaries=[(PyQt5.sip.__file__, 'PyQt5')],
    datas=[('config', 'config'), ('src\\assets', 'assets')],
    hiddenimports=['query_manager', 'playback_manager'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ShippingMonitorGUI_Debug',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ShippingMonitorGUI_Debug',
)
