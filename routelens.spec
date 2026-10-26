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
    # 发布包只装运行期真正用到的：GUI(tkinter/customtkinter) + 托盘(pystray/Pillow)。
    # numpy / yaml / psutil / charset_normalizer 等是开发环境顺带被扫进来的，体积最大头。
    excludes=[
        "numpy",
        "scipy",
        "pandas",
        "matplotlib",
        "yaml",
        "psutil",
        "charset_normalizer",
        "pyreadline3",
        "IPython",
        "pytest",
        "setuptools",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Tcl/Tk 的 tzdata（约 600 个时区文件）只有 clock 命令按时区名解析时才用；
# 轨镜只用 datetime/时间戳，不解析时区名 → 直接剔除，显著减少文件数。
def _keep_data(entry) -> bool:
    dest = str(entry[1]).replace("\\", "/")
    if "/tzdata/" in dest or dest.endswith("/tzdata"):
        return False
    if dest.endswith("/demos") or "/demos/" in dest:
        return False
    return True


a.datas = [d for d in a.datas if _keep_data(d)]

# Pillow 自带的 AVIF / WebP 解码器（_avif 单个就 7.5MB）轨镜用不到（只读 PNG/ICO）。
_DROP_BINARY_MARKS = ("_avif", "_webp")
a.binaries = [
    b for b in a.binaries if not any(mark in str(b[0]) for mark in _DROP_BINARY_MARKS)
]

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
