"""从 Client.txt 内容判断所属游戏（PoE1 / PoE2）。

用途：导入路线 / 首次设置时不要「以设置里的游戏为准」，否则把 PoE1 的
Client.txt 选到 PoE2 那一行，整批路线会被标成 PoE2。

判据（按可靠性排序）：
1. 客户端启动时写入的 ``[HTTP2] User agent:``（语言无关，最可靠）
2. 区域名特征（无 UA 行的旧日志兜底；只用于高置信度判断）
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

_UA_LINE_RE = re.compile(r"User agent:\s*([^\r\n]*)", re.IGNORECASE)
# PoE1 实测："PoE release/tags/3.29.3b Windows x64"
_POE1_UA_RE = re.compile(r"^\s*PoE\s+(?:release|poe1_production)\b", re.IGNORECASE)
# PoE2 实测："PoE poe2_production/tags/4.5.5 Windows x64"
# 兼容其它写法："PoE2 ..." / "PathOfExile2 ..." / "Path of Exile 2 ..."
# 注意：不能把 PoE1 的 "PoE release/" 当成 PoE2。
_POE2_UA_RE = re.compile(
    r"^\s*PoE\s+poe2_production\b"
    r"|^\s*(?:PoE2|PathOfExile2|Path\s+of\s+Exile\s+2)\b",
    re.IGNORECASE,
)

HEAD_BYTES = 64 * 1024
TAIL_BYTES = 2 * 1024 * 1024


def _norm_area(name: str) -> str:
    text = str(name or "").strip().casefold()
    if text.startswith("the "):
        text = text[4:].strip()
    return text.rstrip(" .。")


def _name_set(*names: str) -> frozenset[str]:
    return frozenset(_norm_area(name) for name in names if name)


# 只收录「PoE2 不存在」的 PoE1 专属区域，避免误判。
POE1_AREA_SIGNATURES = _name_set(
    "Lioneye's Watch",
    "The Twilight Strand",
    "The Coast",
    "The Mud Flats",
    "The Ledge",
    "The Climb",
    "The Prisoner's Gate",
    "The Ship Graveyard",
    "The Ship Graveyard Cave",
    "The Cavern of Wrath",
    "The Cavern of Anger",
    "The Southern Forest",
    "The Forest Encampment",
    "The Old Fields",
    "The Crossroads",
    "The Chamber of Sins",
    "The Broken Bridge",
    "The Fellshrine Ruins",
    "The Crypt",
    "The Vaal Ruins",
    "The Northern Forest",
    "The Ancient Pyramid",
    "The City of Sarn",
    "Sarn Encampment",
    "The Slums",
    "The Crematorium",
    "The Sewers",
    "The Marketplace",
    "The Battlefront",
    "The Docks",
    "The Solaris Temple",
    "The Ebony Barracks",
    "The Lunaris Temple",
    "The Sceptre of God",
    "The Upper Sceptre of God",
    "The Aqueduct",
    "Highgate",
    "The Dried Lake",
    "The Crystal Veins",
    "Daresso's Dream",
    "Kaom's Dream",
    "The Belly of the Beast",
    "The Harvest",
    "The Ascent",
    "The Slave Pens",
    "The Control Blocks",
    "Oriath Square",
    "The Templar Courts",
    "The Chamber of Innocence",
    "The Torched Courts",
    "The Ruined Square",
    "The Reliquary",
    "The Ossuary",
    "The Cathedral Rooftop",
    "The Cathedral Apex",
    "The Karui Fortress",
    "The Ridge",
    "The Lower Prison",
    "Shavronne's Tower",
    "The Western Forest",
    "The Wetlands",
    "The Riverways",
    "The Beacon",
    "The Brine King's Reef",
    "The Bridge Encampment",
    "The Ashen Fields",
    "The Causeway",
    "The Vaal City",
    "The Temple of Decay",
    "The Sarn Ramparts",
    "The Toxic Conduits",
    "The Grand Promenade",
    "The Quay",
    "The Bath House",
    "The High Gardens",
    "The Lunaris Concourse",
    "The Harbour Bridge",
    "The Solaris Concourse",
    "The Blood Aqueduct",
    "The Canals",
    "The Feeding Trough",
    "The Rotting Core",
    "The Karui Shores",
    "Oriath",
    "The Descent",
)

# 只收录「PoE1 不存在」的 PoE2 专属区域。
POE2_AREA_SIGNATURES = _name_set(
    "The Riverbank",
    "Clearfell",
    "Clearfell Encampment",
    "The Mud Burrow",
    "The Grelwood",
    "The Red Vale",
    "The Grim Tangle",
    "Cemetery of the Eternals",
    "Tomb of the Consort",
    "Mausoleum of the Praetor",
    "Ogham Farmlands",
    "Ogham Village",
    "The Manor Ramparts",
    "Ogham Manor",
    "The Halani Gates",
    "Traitor's Passage",
    "The Mast",
    "The Sinking City",
    "The Vastiri Outskirts",
    "The Ardura Caravan",
    "The Ziggurat Encampment",
    "The Ziggurat Refuge",
)


def _read_sample(path: Path, *, head_bytes: int, tail_bytes: int) -> str:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            chunks: list[bytes] = []
            handle.seek(0)
            chunks.append(handle.read(head_bytes))
            if size > head_bytes:
                handle.seek(max(0, size - tail_bytes))
                chunks.append(handle.read(tail_bytes))
    except OSError:
        return ""
    return b"\n".join(chunks).decode("utf-8", errors="replace")


def detect_game_from_log(
    path: Path | str,
    *,
    head_bytes: int = HEAD_BYTES,
    tail_bytes: int = TAIL_BYTES,
) -> str | None:
    """按 Client.txt 内容判断游戏；判不出来返回 None（调用方自行回退）。"""
    text = _read_sample(Path(path), head_bytes=head_bytes, tail_bytes=tail_bytes)
    if not text:
        return None
    found: str | None = None
    for match in _UA_LINE_RE.finditer(text):
        agent = match.group(1)
        if _POE2_UA_RE.match(agent):
            found = "poe2"
        elif _POE1_UA_RE.match(agent):
            found = "poe1"
    return found


def detect_game_from_area_names(names: Iterable[str], *, min_hits: int = 2) -> str | None:
    """按区域名判断游戏；证据不足返回 None，绝不猜。"""
    poe1_hits = 0
    poe2_hits = 0
    for raw in names:
        key = _norm_area(raw)
        if not key:
            continue
        if key in POE1_AREA_SIGNATURES:
            poe1_hits += 1
        elif key in POE2_AREA_SIGNATURES:
            poe2_hits += 1
    if poe1_hits >= min_hits and poe1_hits > poe2_hits:
        return "poe1"
    if poe2_hits >= min_hits and poe2_hits > poe1_hits:
        return "poe2"
    return None


def resolve_import_game(path: Path | str, requested: str | None) -> str | None:
    """导入时的最终归属：日志内容优先，判不出来才用调用方的游戏。"""
    return detect_game_from_log(path) or (str(requested or "").strip().lower() or None)
