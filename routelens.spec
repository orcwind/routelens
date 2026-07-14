# -*- mode: python ; coding: utf-8 -*-
# 打包：powershell -File build_routelens.ps1
# 或：pyinstaller --noconfirm routelens.spec
# 输出：dist/RouteLens/

from pathlib import Path

block_cipher = None
root = Path(SPECPATH)
src = root / "src"
icon_ico = src / "routelens" / "icon" / "routelens.ico"
icon_dir = src / "routelens" / "icon"

datas = [
    (str(icon_dir), "routelens/icon"),
]

a = Analysis(
    [str(src / "routelens_app.py")],
    pathex=[str(src)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "customtkinter",
        "pystray",
        "PIL",
        "PIL.Image",
        "PIL.ImageTk",
        "routelens",
        "routelens.gui",
        "routelens.games.poe2",
        "routelens.games.universal",
        "routelens.games.registry",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RouteLens",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_ico) if icon_ico.is_file() else None,
    contents_directory="_internal",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="RouteLens",
)
