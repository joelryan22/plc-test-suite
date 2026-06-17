# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_data_files

# jedi ships typeshed stubs + parso ships a grammar file that PyInstaller's
# static analysis misses; collect them explicitly so hover help works frozen.
jedi_datas, jedi_binaries, jedi_hiddenimports = collect_all('jedi')
parso_datas = collect_data_files('parso')

a = Analysis(
    ['plc_test_suite\\main.py'],
    pathex=[],
    binaries=[*jedi_binaries],
    datas=[*jedi_datas, *parso_datas],
    hiddenimports=['PyQt6.Qsci', 'parso', *jedi_hiddenimports],
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
    a.binaries,
    a.datas,
    [],
    name='PLC-Test-Suite',
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
)
