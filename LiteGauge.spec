# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += collect_submodules('app')


def find_path_dll(filename):
    """Return a DLL resolved from this build environment's PATH."""
    for directory in os.environ.get('PATH', '').split(os.pathsep):
        candidate = Path(directory) / filename
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError(f'Required runtime DLL not found on PATH: {filename}')


a = Analysis(
    ['start.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Keep ICU next to Qt6Core.  Putting it in the one-file extraction root makes
# the bootloader's root DLL search path win over Qt's own binary directory,
# which produces WinError 127 while importing PyQt6.QtCore.
qt_bin = r'PyQt6\Qt6\bin'
icu_names = {'icuuc.dll', 'icudt78.dll'}
a.binaries = [entry for entry in a.binaries if entry[0].lower() not in icu_names]
for icu_name in sorted(icu_names):
    a.binaries.append((f'{qt_bin}\\{icu_name}', find_path_dll(icu_name), 'BINARY'))

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='LiteGauge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icon.ico'],
)
