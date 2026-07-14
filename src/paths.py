from __future__ import annotations

import sys
from pathlib import Path


def _detect_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_ROOT = _detect_app_root()
PROJECT_ROOT = APP_ROOT


def project_path(path: str | Path) -> Path:
    value = Path(path)
    if value.is_absolute():
        return value
    return APP_ROOT / value


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))
