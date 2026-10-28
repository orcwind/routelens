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
    * ``P1_*`` … ``P3_*`` = **間歇（Interlude）**，Act 4 之后、終局之前的一段
    * ``G_Endgame_Town``  = 金字塔避难所 = **剧情结束（終局）**
    * ``Map*``            = **异界地图**
    * ``Expedition*``     = 精华地图（支线内容，不是剧情也不是终局）
    * ``Incursion*``      = 禁區（支线内容）

PoE2 **章节栏**（与游戏内一致，见 :func:`chapter_slots`）：

    第1章 第2章 第3章 第4章 間歇 終局

PoE2 **剧情区域判定**（导入开荒路线时用）：

    剧情 = area id 匹配 ``G<1..4>_*``（含 ``G<n>_town`` 城镇）
    + 間歇 ``P<1..3>_*``（PoE2 第 4 章之后、終局之前的一段）。
    以下**一律不是剧情**，不得进入开荒路线：

    * ``Map*``                       异界地图
    * ``Expedition*``                精华地图
    * ``Incursion*``                 禁區
    * ``Abyss*``                     深渊
    * ``Sanctum_*``                  试炼内部房间
    * ``Delirium*`` / ``Ritual*``    特殊地图
    * ``Hideout*``                   藏身处
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

# PoE2：**非剧情**前缀白名单（黑名单 = 明确不是剧情）。
# 实测自真实 Client.txt（2026-10）：异界地图 / 精华 / 禁區 / 深渊 /
# 试炼内部房间 / PoE1 移植区 / 藏身处，全部不是开荒剧情节点。
_POE2_NON_CAMPAIGN_PREFIXES = (
    "Map",  # 异界地图（含 MapUberBoss_* / MapUnique*）
    "Expedition",  # 精华地图
    "Incursion",  # 禁區
    "Abyss",  # 深渊
    "Sanctum_",  # 丝克玛试炼内部房间
    "Delirium",  #  delirium 地图
    "Ritual",  # 仪式地图
    "Hideout",  # 藏身处
    "ChayulaLeague",  # 剧情外赛季 boss 区域
    "BreachDomain_",  # 裂隙
)
# PoE1 移植区（P1_Town / P2_1 / P3_Town …）**不是**非剧情 ——
# PoE2 的「間歇（Interlude）」就是重走这些区域（实测 22 个，见 INTERLUDE 注释）。
_POE2_INTERLUDE_RE = re.compile(r"^P\d+(?:_|$)")

# PoE1：剧情区域必然是 ``<幕>_<序号>…``（1_1_2 / 2_10_9 / 1_2_14_2）。
_POE1_CAMPAIGN_AREA_RE = re.compile(r"^\d+_\d+")
# PoE1 升华试炼：进门 Labyrinth_Airlock（Aspirants' Plaza）+ 内部 <act>_Labyrinth_*
_POE1_TRIAL_AREA_RE = re.compile(r"^(?:\d+_)?Labyrinth_")

# PoE1：``2_11`` 起为剧情结束后的海岸
POE1_CAMPAIGN_END_ACT = 11


class ActInfo:
    """一次到访的归属：哪一幕 / 是否剧情已结束 / 是否支线。"""

    __slots__ = ("act", "area_id", "campaign_over", "is_side", "is_map", "is_interlude")

    def __init__(
        self,
        act: int | None,
        area_id: str = "",
        *,
        campaign_over: bool = False,
        is_side: bool = False,
        is_map: bool = False,
        is_interlude: bool = False,
    ) -> None:
        self.act = act
        self.area_id = area_id
        self.campaign_over = campaign_over
        self.is_side = is_side
        self.is_map = is_map
        self.is_interlude = is_interlude

    @property
    def label(self) -> str:
        if self.campaign_over:
            return "剧情结束"
        if self.is_interlude:
            return "間歇"
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
    # 間歇（Interlude）：Act 4 之后、終局之前的一段。
    # 实测 22 个区域，GGG 内部用 PoE1 移植前缀 P1_*/P2_*/P3_*：
    #   P1 = 火噬農地 → 狼之要塞 → 霍爾登宅第（庇護所）
    #   P2 = 卡里交匯道 → 奇瑪水源地（卡里市集）
    #   P3 = 灰燼森林 → 庫阿西克寶庫（林間空地）
    # 日志里这一段的章节行就是「幕間章」。
    if _POE2_INTERLUDE_RE.match(aid):
        return ActInfo(None, aid, is_interlude=True)
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


def is_poe1_campaign_area_id(area_id: str) -> bool:
    """PoE1 该 area id 是否属于**剧情**（含升华试炼入口 / 内部房间）。

    剧情区域命名固定为 ``<幕>_<序号>…``。其余命名区域都是非剧情：
    联盟城镇（``KalguuranSettlersLeague`` 君锋镇）、``Menagerie_Hub`` 兽栏、
    ``DeepwaterHub``、``MavenHub``、藏身处、``Delve_Main`` 等。
    """
    aid = (area_id or "").strip()
    if not aid:
        return False
    if _POE1_TRIAL_AREA_RE.match(aid):
        return True
    return bool(_POE1_CAMPAIGN_AREA_RE.match(aid))


def act_count(game_id: str) -> int:
    game = str(game_id or "").strip().lower()
    if game == "poe1":
        return POE1_ACT_COUNT
    if game == "poe2":
        return POE2_ACT_COUNT
    return 0


def chapter_slots(game_id: str) -> list[tuple[str, str]]:
    """章节切换栏的完整条目（与游戏内一致）。

    PoE2 不只有 4 幕 —— 实测游戏内章节栏为：

        第1章 第2章 第3章 第4章 間歇 終局

    返回 ``[(kind, key), ...]``，kind ∈ {"act", "interlude", "endgame"}；
    act 的 key 是幕号字符串（"1".."10"），interlude / endgame 的 key 为 ""。
    """
    game = str(game_id or "").strip().lower()
    if game == "poe2":
        slots: list[tuple[str, str]] = [
            ("act", str(n)) for n in range(1, POE2_ACT_COUNT + 1)
        ]
        slots.append(("interlude", ""))
        slots.append(("endgame", ""))
        return slots
    if game == "poe1":
        slots = [("act", str(n)) for n in range(1, POE1_ACT_COUNT + 1)]
        # PoE1 也有剧情结束点（2_11_endgame_town 卡鲁海滩），单独一行
        slots.append(("endgame", ""))
        return slots
    return []


def infer_game_from_area_id(area_id: str) -> str:
    """由 area id 形态反推游戏（``1_1_1`` → poe1，``G1_1`` → poe2）。

    这是**最硬的身份证据**：设置里的「当前游戏」是全局默认值，
    用户同时有 PoE1 / PoE2 路线时，按设置判会把 PoE1 的 10 幕显示成 4 幕。
    """
    aid = (area_id or "").strip()
    if not aid:
        return ""
    if aid.startswith(_POE1_MAP_PREFIXES):
        return "poe1"
    if _POE1_ACT_ID_RE.match(aid):
        return "poe1"
    if aid == "G_Endgame_Town" or _POE2_ACT_ID_RE.match(aid):
        return "poe2"
    return ""


_CHINESE_NUMERALS = ("零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十")


def _chinese_numeral(value: int) -> str:
    """1..20 → 中文数字（1 → 一，10 → 十，12 → 十二）。"""
    if value < 0:
        return str(value)
    if value <= 10:
        return _CHINESE_NUMERALS[value]
    if value < 20:
        return "十" + _CHINESE_NUMERALS[value - 10]
    return str(value)


def act_chapter_label(area_id: str, game_id: str) -> str:
    """该 area id 所属的章节标签；非剧情返回空串。

    PoE1 的 Client.txt **没有章节行**（``[SCENE] Set Source`` 只有区域名，
    实测 2026-10 真机日志无「第一章」/「Act 1」），因此章节只能由 area id 推出。
    PoE2 有 ``[SCENE]`` 章节行，但仍可作交叉校验。

    标签格式与界面既有章节名一致（中文数字）：``第一章`` / ``第十章``。
    PoE2 的間歇（Act 4 之后）返回 ``間歇``。
    """
    info = detect_act(area_id, game_id)
    if info.is_interlude:
        return "間歇"
    if info.act is None:
        return ""
    return f"第{_chinese_numeral(info.act)}章"


def is_campaign_over_area_id(area_id: str, game_id: str) -> bool:
    """该 area id 是否代表剧情已经结束（奇塔弗之后 / 金字塔避难所）。"""
    return detect_act(area_id, game_id).campaign_over


def is_endgame_map_area_id(area_id: str, game_id: str) -> bool:
    """该 area id 是否是异界地图（剧情之后的地图，不应导入开荒路线）。"""
    return detect_act(area_id, game_id).is_map


def is_poe2_campaign_area_id(area_id: str) -> bool:
    """该 area id 是否属于 **PoE2 剧情**（开荒路线只应包含这些）。

    PoE2 剧情 = 主四幕 + 間歇 + 終局，对照游戏内章节切换栏：

        第1章 第2章 第3章 第4章 間歇 終局

    * ``G<1..4>_*``   主四幕（含 ``G<n>_town`` 城镇）
    * ``P<1..3>_*``   **間歇（Interlude）** —— 实测 22 个区域：
      P1 火噬農地 → 霍爾登宅第、P2 卡里交匯道 → 奇瑪水源地、
      P3 灰燼森林 → 庫阿西克寶庫。这一段日志里的章节行是「幕間章」。
    * ``G_Endgame_Town`` 終局（剧情结束点，单独判定）

    明确**不是**剧情的（实测自真实 Client.txt，2026-10）：

    * ``Map*``               异界地图
    * ``Expedition*``        精华地图
    * ``Incursion*``         禁區
    * ``Abyss*``             深渊
    * ``Sanctum_*``          试炼内部房间
    * ``Delirium*`` / ``Ritual*``
    * ``Hideout*``           藏身处
    """
    aid = (area_id or "").strip()
    if not aid:
        return False
    if aid == "G_Endgame_Town":
        return False
    if aid.startswith(_POE2_NON_CAMPAIGN_PREFIXES):
        return False
    if _POE2_INTERLUDE_RE.match(aid):
        return True
    match = _POE2_ACT_ID_RE.match(aid)
    if not match:
        return False
    return 1 <= int(match.group(1)) <= POE2_ACT_COUNT
