"""开荒起点：每个游戏第一幕的**固定**起始区域。

新建路线（自由路线 / 空白路线）必然从第一幕开始，所以第一幕起点是**常量**，
不需要从日志反推「玩家当前在哪」：

- PoE1：``1_1_1`` = The Twilight Strand
- PoE2：``G1_1``  = 河岸 / The Riverbank

实测依据（真机 Client.txt）：
- PoE1 每个新角色的**首个** Generating 都是 ``area "1_1_1"``
- PoE2 每个新角色的**首个** Generating 都是 ``area "G1_1"``

区域名随客户端语言变化，因此显示名优先取**日志原文**
（``resolve_area_name_from_log``），取不到才回退到内置译名。
"""

from __future__ import annotations

import re
from pathlib import Path

# area id → 各语言显示名（仅作缺省回退，日志原文优先）
CAMPAIGN_START_AREAS: dict[str, dict[str, str]] = {
    "1_1_1": {
        "en": "The Twilight Strand",
        "zh_tw": "暮光之岸",
        "zh_cn": "暮光之岸",
    },
    "G1_1": {
        "en": "The Riverbank",
        "zh_tw": "河岸",
        "zh_cn": "河岸",
    },
}

# 每个游戏的第一幕固定起点 area id
GAME_CAMPAIGN_START: dict[str, str] = {
    "poe1": "1_1_1",
    "poe2": "G1_1",
}

# 日志解析用的正则（与 log_parser 一致）
_GEN_RE = re.compile(r'Generating level \d+ area "([^"]+)"')
_SCENE_RE = re.compile(r"\[SCENE\] Set Source \[(.+?)\]")
_ENTER_RE = re.compile(r": You have entered (.+)\.")


def campaign_start_area_id(game_id: str) -> str:
    """该游戏第一幕的固定起点 area id（未知游戏返回空串）。"""
    game = str(game_id or "").strip().lower()
    return GAME_CAMPAIGN_START.get(game, "")


def campaign_start_name(area_id: str, locale: str = "zh_tw") -> str:
    """第一幕起点的缺省显示名。"""
    entry = CAMPAIGN_START_AREAS.get(area_id)
    if not entry:
        return ""
    lang = str(locale or "").strip().lower()
    if lang in ("zh", "zh_cn", "zh_tw", "zh_hk", "zh_hant", "tw", "hant"):
        return entry.get("zh_tw") or entry.get("en") or ""
    return entry.get("en") or entry.get("zh_tw") or ""


def resolve_area_name_from_log(
    log_path: Path | None,
    area_id: str,
    *,
    max_bytes: int = 4 * 1024 * 1024,
) -> str:
    """从 Client.txt 尾部找该 area id 最近一次的**日志原文**区域名。

    区域名随客户端语言变化（The Twilight Strand / 暮光之岸 / …），
    只有日志原文才是玩家真正看到的名字。取不到返回空串。
    """
    if not log_path or not area_id:
        return ""
    path = Path(log_path)
    try:
        if not path.is_file():
            return ""
        size = path.stat().st_size
        start = max(0, size - max_bytes)
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(start)
            if start > 0:
                handle.readline()
            lines = handle.readlines()
    except OSError:
        return ""

    pending = ""
    found = ""
    for line in lines:
        gen = _GEN_RE.search(line)
        if gen:
            pending = gen.group(1).strip()
            continue
        scene = _SCENE_RE.search(line)
        if scene:
            name = scene.group(1).strip()
            if pending == area_id and name not in ("(null)", "(unknown)"):
                found = name
                pending = ""
            continue
        entered = _ENTER_RE.search(line)
        if entered:
            name = entered.group(1).strip()
            if pending == area_id:
                found = name
                pending = ""
    return found
