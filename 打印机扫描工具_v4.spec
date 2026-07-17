# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('scangate/web/static', 'scangate/web/static'), ('scangate/web/default_config.json', 'scangate/web/default_config.json'), ('scangate/updater/update_source.json', 'scangate/updater')]
binaries = []
hiddenimports = ['webview', 'fitz', 'pythonnet', 'clr_loader', 'scangate.updater', 'scangate.updater.updater', 'scangate.updater.manifest', 'scangate.updater.download', 'scangate.updater.install', 'scangate.updater.rollback', 'scangate.updater.settings']
tmp_ret = collect_all('pymupdf')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pythonnet')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main_web.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='打印机扫描工具_v4',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['scan_gate_icon.ico'],
)
