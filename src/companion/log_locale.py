"""从 Client.txt 内容推断日志语言（en / zh_cn / zh_tw）。"""

from __future__ import annotations

import re
from pathlib import Path

# 繁体常见用字（区域/章节标签里出现）
_TRAD_MARKERS = frozenset("營車隊縣區縮獵擊劇藥劇臺廳廳獵獸臟臺")
# 简体常见用字
_SIMP_MARKERS = frozenset("营车队县区缩猎击剧药厅脏台兽")

_ENTERED_EN_RE = re.compile(r": You have entered .+\.")
_ENTERED_CN_RE = re.compile(r"[:：].*(?:進入|进入).+")


def _read_tail_text(path: Path, tail_bytes: int = 4 * 1024 * 1024) -> str:
    size = path.stat().st_size
    read_size = min(size, tail_bytes)
    with path.open("rb") as handle:
        handle.seek(max(0, size - read_size))
        data = handle.read(read_size)
    text = data.decode("utf-8", errors="replace")
    if size > read_size:
        lines = text.splitlines()
        if lines:
            return "\n".join(lines[1:])
    return text


def detect_client_log_locale(path: Path, *, tail_bytes: int = 4 * 1024 * 1024) -> str:
    """
    根据 Client.txt 末尾内容判断语言。
    返回 en | zh_cn | zh_tw
    """
    if not path.is_file():
        return "zh_tw"

    text = _read_tail_text(path, tail_bytes=tail_bytes)
    en_entered = len(_ENTERED_EN_RE.findall(text))
    cn_entered = len(_ENTERED_CN_RE.findall(text))

    if en_entered >= 5 and en_entered >= cn_entered * 2:
        return "en"

    trad_score = sum(text.count(ch) for ch in _TRAD_MARKERS)
    simp_score = sum(text.count(ch) for ch in _SIMP_MARKERS)

    if simp_score > trad_score + 3:
        return "zh_cn"
    if trad_score > 0 or cn_entered > 0:
        return "zh_tw"
    if en_entered > 0:
        return "en"
    return "zh_tw"
