"""试炼（Trial / Ascension Trial）的结构定义与折叠规则。

**产品规则（用户 2026-10-25 定）**

一次试炼只记录**进门那一次**，试炼里面的房间不再单独记录。
但**多次试炼每次都要记录**（每次进门都是一个新节点）。

例：PoE1 一次升华试炼在日志里是 8 个连续节点
（Aspirants' Plaza → Estate Path → Aspirant's Trial → Sepulchre Halls → …），
只保留第一个「Aspirants' Plaza」，其余 7 个折叠进去（时间并入，不丢）。

**权威依据 = area id**（实测自真实 Client.txt，2026-10-25）

PoE1 —— 升华试炼（Labyrinth）：

    进门   ``Labyrinth_Airlock``        （Aspirants' Plaza）
    房间   ``<act>_Labyrinth_*``        （Estate Path / Aspirant's Trial / …）
            含 boss 房 ``*_Labyrinth_boss_*``

PoE2 —— 两个试炼：

    ==========  ====================  ==================  ==================
    试炼           进门 / hub            本体（显示名）        内部房间
    ==========  ====================  ==================  ==================
    絲克瑪試煉     ``G2_13``             ``G2_13``            ``Sanctum_*``
    混沌試煉       ``G3_10_Airlock``     ``G3_10``            ``G3_10_Airlock``
    ==========  ====================  ==================  ==================

    * 混沌試煉：玩家先到「混沌神殿」入口大厅（``G3_10_Airlock``），
      再进「混沌試煉」本体（``G3_10``），二者来回切换。

**不是试炼**（剧情区域，别误折叠）：

    * ``G4_4_3`` 「祖靈的試煉」= Act 4 剧情区域（Trial of the Ancestors），
      在 Kingsmarch 一带，与「悉妮蔻拉之眼」「亡者之殿」相邻。
      名字里带「試煉」但**不是**试炼内容，必须按普通剧情节点记录。

**显示名统一取「本体」id 在日志里的区域名**
（絲克瑪試煉 / 混沌試煉 / Aspirants' Plaza）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TrialSpec:
    """一个试炼的结构定义。"""

    trial_id: str
    # 进门 / hub：玩家实际踏入试炼区域的 id
    entry_ids: frozenset[str]
    # 内部房间 id 前缀
    room_prefixes: tuple[str, ...]
    # 本体 id —— 折叠后用它的区域名做显示名
    body_id: str


# ── PoE1：升华试炼 ─────────────────────────────────────────────
POE1_TRIAL = TrialSpec(
    trial_id="poe1_labyrinth",
    entry_ids=frozenset({"Labyrinth_Airlock"}),
    room_prefixes=(),
    body_id="Labyrinth_Airlock",
)
# 内部房间：1_Labyrinth_OH_straight / 2_Labyrinth_boss_1 / 3_Labyrinth_…
POE1_TRIAL_ROOM_RE = re.compile(r"^\d+_Labyrinth_")

# ── PoE2：两个试炼 ─────────────────────────────────────────────
POE2_TRIALS: tuple[TrialSpec, ...] = (
    TrialSpec(
        trial_id="G2_13",
        entry_ids=frozenset({"G2_13"}),
        room_prefixes=("Sanctum",),
        body_id="G2_13",
    ),
    TrialSpec(
        trial_id="G3_10",
        entry_ids=frozenset({"G3_10", "G3_10_Airlock"}),
        room_prefixes=("G3_10_Airlock",),
        body_id="G3_10",
    ),
)

ALL_TRIALS: tuple[TrialSpec, ...] = (POE1_TRIAL,) + POE2_TRIALS


@dataclass
class TrialInfo:
    """一次到访是否属于某个试炼，以及是试炼的哪一部分。"""

    __slots__ = ("trial_id", "is_entry", "is_room", "body_id")

    def __init__(
        self,
        trial_id: str = "",
        *,
        is_entry: bool = False,
        is_room: bool = False,
        body_id: str = "",
    ) -> None:
        self.trial_id = trial_id
        self.is_entry = is_entry
        self.is_room = is_room
        self.body_id = body_id

    @property
    def in_trial(self) -> bool:
        return bool(self.trial_id)

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        kind = "entry" if self.is_entry else ("room" if self.is_room else "-")
        return f"TrialInfo({self.trial_id!r}, {kind})"


NO_TRIAL = TrialInfo()

# 试炼本体的规范显示名（中文台服用；英文/简体走区域名本身）
TRIAL_DISPLAY_NAMES: dict[str, str] = {
    "poe1_labyrinth": "升华试炼",
    "G2_13": "絲克瑪試煉",
    "G3_10": "混沌試煉",
}

# trial_id → 本体 area id
_TRIAL_BODY_IDS: dict[str, str] = {
    spec.trial_id: spec.body_id for spec in ALL_TRIALS
}


def trial_body_id(trial_id: str) -> str:
    """试炼本体的 area id（例：G2_13）。"""
    return _TRIAL_BODY_IDS.get(trial_id, "")


def trial_body_ids() -> tuple[str, ...]:
    """所有试炼本体的 area id。"""
    return tuple(_TRIAL_BODY_IDS.values())


def trial_display_name(trial_id: str, fallback: str = "") -> str:
    """试炼的规范显示名（找不到就用区域名兜底）。"""
    return TRIAL_DISPLAY_NAMES.get(trial_id, fallback)


def trial_node_name(
    trial_id: str,
    entry_area_id: str,
    entry_area_name: str,
    body_name: str = "",
) -> str:
    """试炼节点的显示名（离线解析与实时引擎共用同一套规则）。

    规则：
    - 进门就是本体（PoE1 迷宫 / PoE2 絲克瑪）→ 用日志里的区域名
      （Aspirants' Plaza / 絲克瑪試煉），跟客户端语言一致
    - 进门是入口大厅（混沌神殿）→ 用**本体**的名字（混沌試煉），
      因为「进门」不是试炼本身
    - 本体名字未知时用规范名兜底
    """
    body_id = trial_body_id(trial_id)
    if entry_area_id == body_id:
        return entry_area_name or body_name or trial_display_name(trial_id)
    return body_name or trial_display_name(trial_id, entry_area_name)


def _match_poe1(aid: str) -> TrialInfo:
    spec = POE1_TRIAL
    if aid in spec.entry_ids:
        return TrialInfo(spec.trial_id, is_entry=True, body_id=spec.body_id)
    if POE1_TRIAL_ROOM_RE.match(aid):
        return TrialInfo(spec.trial_id, is_room=True, body_id=spec.body_id)
    return NO_TRIAL


def _match_poe2(aid: str) -> TrialInfo:
    for spec in POE2_TRIALS:
        if aid in spec.entry_ids:
            return TrialInfo(spec.trial_id, is_entry=True, body_id=spec.body_id)
        for prefix in spec.room_prefixes:
            if aid.startswith(prefix):
                return TrialInfo(spec.trial_id, is_room=True, body_id=spec.body_id)
    return NO_TRIAL


def detect_trial(area_id: str, game_id: str) -> TrialInfo:
    """按 area id 判定这个区域是不是试炼（进门 / 内部房间）。"""
    aid = (area_id or "").strip()
    if not aid:
        return NO_TRIAL
    game = str(game_id or "").strip().lower()
    if game == "poe1":
        return _match_poe1(aid)
    if game == "poe2":
        return _match_poe2(aid)
    return NO_TRIAL
