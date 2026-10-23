from __future__ import annotations

import os
import sys
from pathlib import Path


def _detect_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    # src/routelens/paths.py → 仓库根目录
    return Path(__file__).resolve().parents[2]


APP_ROOT = _detect_app_root()
PROJECT_ROOT = APP_ROOT


def _detect_user_data_root() -> Path:
    """用户数据根目录：%APPDATA%\\RouteLens（换目录 / 更新不丢）。

    开发模式（源码运行）沿用仓库内路径，保持开发者本机数据与打包版一致。
    """
    if not getattr(sys, "frozen", False):
        return APP_ROOT
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return base / "RouteLens"


USER_DATA_ROOT = _detect_user_data_root()


def project_path(path: str | Path) -> Path:
    """相对仓库根 / exe 目录的路径（程序侧资源）。"""
    value = Path(path)
    if value.is_absolute():
        return value
    return APP_ROOT / value


def user_data_path(path: str | Path) -> Path:
    """相对用户数据根的路径（config / 路线 / 进度等用户记录）。"""
    value = Path(path)
    if value.is_absolute():
        return value
    return USER_DATA_ROOT / value


def resource_path(path: str | Path) -> Path:
    """打包进安装包的只读资源（datas）。"""
    rel = Path(path)
    if rel.is_absolute():
        return rel
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidate = Path(meipass) / rel
            if candidate.exists():
                return candidate
        next_to_exe = APP_ROOT / rel
        if next_to_exe.exists():
            return next_to_exe
        under_internal = APP_ROOT / "_internal" / rel
        if under_internal.exists():
            return under_internal
        return next_to_exe
    return APP_ROOT / rel


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))
