# -*- mode: python ; coding: utf-8 -*-
"""Portable directory build.

The one-file bootloader changes the DLL search order before PyQt6 starts.
Keeping Qt's native libraries as ordinary files makes their load location
explicit and avoids that collision.
"""

from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ["start.py"],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=collect_submodules("app"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Do not bundle the unrelated ICU 78 DLL discovered on this machine's PATH.
# Qt6Core imports the unversioned Windows ICU API (ucnv_open), provided by
# Windows 10's System32\icuuc.dll and its system dependency icu.dll.
icu_names = {"icuuc.dll", "icudt78.dll"}
a.binaries = [
    entry
    for entry in a.binaries
    if entry[0].replace("\\", "/").rsplit("/", 1)[-1].lower() not in icu_names
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LiteGauge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=["icon.ico"],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="LiteGauge",
)
