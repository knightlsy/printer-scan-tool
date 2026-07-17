# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\EDY\\AppData\\Roaming\\Tencent\\Marvis\\User\\oAN1i2ZyPCSytqedeXqn_UjQM-P4\\workspace\\conv_19e4f15ede6_0a66c9c3f1c0\\output\\打印机扫描工具.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
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
    name='打印机扫描工具',
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
