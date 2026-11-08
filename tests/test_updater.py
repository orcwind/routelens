"""自动更新脚本内容回归（不出现 ping 黑窗）。"""

from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from routelens.updater import _write_apply_script  # noqa: E402


def test_apply_update_bat_no_ping_uses_timeout(tmp_path: Path) -> None:
    payload = tmp_path / "payload"
    payload.mkdir()
    bat = _write_apply_script(
        install_dir=tmp_path,
        payload_dir=payload,
        exe_name="RouteLens.exe",
    )
    text = bat.read_text(encoding="ascii").lower()
    assert "ping -n" not in text
    assert "127.0.0.1" not in text
    assert "timeout /t 3 /nobreak" in text
    assert "timeout /t 2 /nobreak" in text
