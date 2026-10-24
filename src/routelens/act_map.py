"""幕（Act）判定：从 Client.txt 的 area id 推出当前所在幕。

权威依据（实测自真实 Client.txt，2026-10）：

PoE1 —— area id 形如 ``X_Y``（``1_1`` … ``2_11``）：
    * 第二段数字 = 幕号（1..10）
    * ``1_1`` … ``1_5``  = Act 1 … Act 5
    * ``2_6`` … ``2_10`` = Act 6 … Act 10
    * ``2_11``           = 奇塔弗之后的卡鲁海滩 = **剧情结束**
    * ``1_Labyrinth_*``  = 迷宫事件（支线）
    * ``1_SideArea*``    = 支线
    * ``MapWorlds*``     = **异界地图**（Chateau / Estuary / Forbidden Woods）

    注意：PoE1 的 Act 5 与 Act 10 区域名几乎完全相同
    （The Quarry / The Refinery / The Belly of the Beast / The Cathedral Rooftop …），
    **只能靠 area id 判幕**，不能靠区域名。

PoE2 —— area id 形如 ``G<act>_<sub>``：
    * ``G1_*`` … ``G4_*`` = Act 1 … Act 4
    * ``G_Endgame_Town``  = 金字塔避难所 = **剧情结束**
    * ``Map*``            = **异界地图**
    * ``Expedition*``     = 精华地图（支线内容，不是剧情也不是终局）
    * ``Incursion*``      = 禁區（支线内容）
    * ``P<n>_*``          = PoE1 移植区域（不属于 PoE2 剧情）
"""

from __future__ import annotations

import re

# ── 剧情幕数量 ────────────────────────────────────────────────
POE1_ACT_COUNT = 10
POE2_ACT_COUNT = 4

# ── area id 正则 ──────────────────────────────────────────────
# PoE1: 1_5_6 / 1_5_8 / 1_5_town / 1_5_11_2
_POE1_ACT_ID_RE = re.compile(r"^(\d+)_(\d+)(?:_|$)")
# PoE2: G2_10_1 / G2_town / G3
_POE2_ACT_ID_RE = re.compile(r"^G(\d+)(?:_|$)")

# PoE1：异界地图
_POE1_MAP_PREFIXES = ("MapWorlds",)
# PoE2：异界地图 / 精华 / 禁區
_POE2_MAP_PREFIXES = ("Map",)
_POE2_SIDE_PREFIXES = ("Expedition", "Incursion")

# PoE1：``2_11`` 起为剧情结束后的海岸
POE1_CAMPAIGN_END_ACT = 11


class ActInfo:
    """一次到访的归属：哪一幕 / 是否剧情已结束 / 是否支线。"""

    __slots__ = ("act", "area_id", "campaign_over", "is_side", "is_map")

    def __init__(
        self,
        act: int | None,
        area_id: str = "",
        *,
        campaign_over: bool = False,
        is_side: bool = False,
        is_map: bool = False,
    ) -> None:
        self.act = act
        self.area_id = area_id
        self.campaign_over = campaign_over
        self.is_side = is_side
        self.is_map = is_map

    @property
    def label(self) -> str:
        if self.campaign_over:
            return "剧情结束"
        if self.act is not None:
            return f"Act {self.act}"
        if self.is_map:
            return "异界"
        if self.is_side:
            return "支线"
        return "—"

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"ActInfo({self.label}, id={self.area_id!r})"


def _poe1_info(area_id: str) -> ActInfo:
    aid = (area_id or "").strip()
    if not aid:
        return ActInfo(None, aid)
    if aid.startswith(_POE1_MAP_PREFIXES):
        return ActInfo(None, aid, is_map=True)
    match = _POE1_ACT_ID_RE.match(aid)
    if not match:
        # 迷宫事件 / 支线：归属当前幕，但不算剧情推进
        return ActInfo(None, aid, is_side=True)
    act = int(match.group(2))
    if act >= POE1_CAMPAIGN_END_ACT:
        # 奇塔弗之后 = 剧情结束
        return ActInfo(None, aid, campaign_over=True)
    if not 1 <= act <= POE1_ACT_COUNT:
        return ActInfo(None, aid, is_side=True)
    return ActInfo(act, aid)


def _poe2_info(area_id: str) -> ActInfo:
    aid = (area_id or "").strip()
    if not aid:
        return ActInfo(None, aid)
    if aid.startswith(_POE2_MAP_PREFIXES):
        return ActInfo(None, aid, is_map=True)
    if aid.startswith(_POE2_SIDE_PREFIXES):
        return ActInfo(None, aid, is_side=True)
    if aid == "G_Endgame_Town":
        return ActInfo(None, aid, campaign_over=True)
    match = _POE2_ACT_ID_RE.match(aid)
    if not match:
        return ActInfo(None, aid, is_side=True)
    act = int(match.group(1))
    if not 1 <= act <= POE2_ACT_COUNT:
        return ActInfo(None, aid, is_side=True)
    return ActInfo(act, aid)


def detect_act(area_id: str, game_id: str) -> ActInfo:
    """按 area id 与游戏判定幕归属。"""
    game = str(game_id or "").strip().lower()
    if game == "poe1":
        return _poe1_info(area_id)
    if game == "poe2":
        return _poe2_info(area_id)
    return ActInfo(None, area_id)


def act_count(game_id: str) -> int:
    game = str(game_id or "").strip().lower()
    if game == "poe1":
        return POE1_ACT_COUNT
    if game == "poe2":
        return POE2_ACT_COUNT
    return 0


def is_campaign_over_area_id(area_id: str, game_id: str) -> bool:
    """该 area id 是否代表剧情已经结束（奇塔弗之后 / 金字塔避难所）。"""
    return detect_act(area_id, game_id).campaign_over


def is_endgame_map_area_id(area_id: str, game_id: str) -> bool:
    """该 area id 是否是异界地图（剧情之后的地图，不应导入开荒路线）。"""
    return detect_act(area_id, game_id).is_map
