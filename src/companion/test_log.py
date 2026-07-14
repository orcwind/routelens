from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path

_lock = threading.Lock()
_log_path: Path | None = None


def init_log(data_dir: Path) -> Path:
    global _log_path
    _log_path = data_dir / "assist.log"
    _log_path.parent.mkdir(parents=True, exist_ok=True)
    write("SESSION", "助手启动", log_file=str(_log_path))
    return _log_path


def get_log_path() -> Path | None:
    return _log_path


def write(category: str, message: str, **fields) -> None:
    if _log_path is None:
        return
    line = _format_line(category, message, fields)
    with _lock:
        with _log_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")


def _format_line(category: str, message: str, fields: dict) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    if fields:
        detail = json.dumps(fields, ensure_ascii=False, separators=(",", ":"))
        return f"[{timestamp}] [{category}] {message} | {detail}"
    return f"[{timestamp}] [{category}] {message}"
