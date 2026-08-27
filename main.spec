# -*- mode: python ; coding: utf-8 -*-

# SCAN.GATE 桌面版打包配置（PyInstaller onedir 模式）
# onedir：主程序 exe 与依赖 DLL 同目录，启动直接读本地文件，
# 配合 scangate/installer.py 首次运行自动安装到本机并建快捷方式。
# 注意：禁止改为 onefile —— 自解压 exe 会被 Windows Defender 拦截
# （Failed to load Python DLL），且 installer 依赖 onedir 目录结构。

a = Analysis(
    ['scangate\\main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 不 excludes fitz：PDF 预览/压缩需要惰性导入 PyMuPDF（见 services/preview.py、compress.py）
    excludes=[],
    noarchive=False,
    optimize=1,
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
    upx=True,
    upx_exclude=[],
    console=False,
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
    name='PrinterScanTool',
)