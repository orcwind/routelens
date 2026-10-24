"""开荒（剧情）结束判定。

判定依据优先级：

1. **area id**（权威）：``Generating level N area "X_Y"``。
   PoE1 = ``X_Y``（第二位数字 = 幕号，``2_11`` 起 = 剧情结束）；
   PoE2 = ``G<act>_*``（``G_Endgame_Town`` = 剧情结束）。
   见 :mod:`routelens.act_map`。

2. **区域名**（兜底，仅当日志没有 area id 时）：
   PoE1 = 卡鲁海滩 / Karui Shores（奇塔弗之后那一次）；
   PoE2 = 高地神塔庇護所 / The Ziggurat Refuge。

名称兜底不可靠的原因：PoE1 的 Karui Shores 在 Act 5→6 与 Act 7→8 过渡时都会出现，
Act 5 与 Act 10 的区域名几乎完全相同。只有 area id 能无歧义判定。
"""

from __future__ import annotations

from .act_map import (
    POE1_CAMPAIGN_END_ACT,
    detect_act,
    is_campaign_over_area_id,
    is_endgame_map_area_id,
)


# ── 区域名兜底集合 ────────────────────────────────────────────
def _norm(name: str) -> str:
    text = str(name or "").strip().casefold()
    if text.startswith("the "):
        text = text[4:].strip()
    return text


def _name_set(*names: str) -> frozenset[str]:
    return frozenset(_norm(name) for name in names if name)


# PoE1：击败奇塔弗后进入卡鲁沿岸/海滩 = 开荒结束（保留该城镇节点）
POE1_CAMPAIGN_END = _name_set(
    "Karui Shores",
    "卡鲁海滩",
    "卡鲁海岸",
    "卡魯沿岸",
    "卡魯海岸",
)

# 末班剧情区（饲槽），用于兼容旧版「破沿血道 → 奧瑞亞」流程
POE1_FINAL_BOSS_AREA = _name_set(
    "The Feeding Trough",
    "Feeding Trough",
    "饲槽",
    "飼養槽",
    "饲养槽",
    "破沿血道",
)

# 仅在已进入饲槽之后，才把「奥瑞亚」城镇视为旧版终局（避开 Act5/10 途中的奥瑞亚）
POE1_LEGACY_TOWN_AFTER_BOSS = _name_set(
    "Oriath",
    "奥瑞亚",
    "奧瑞亞",
)

# PoE2：进入终局枢纽「金字塔避难所 / 高地神塔庇護所」= 开荒结束（保留该节点）
POE2_CAMPAIGN_END = _name_set(
    "The Ziggurat Refuge",
    "Ziggurat Refuge",
    "金字塔避难所",
    "金字塔避難所",
    "高地神塔庇护所",
    "高地神塔庇護所",
)


def _split_area_names(split: dict) -> list[str]:
    names: list[str] = []
    for field in ("area", "area_en", "name"):
        raw = str(split.get(field) or "").strip()
        if raw:
            names.append(raw)
    return names


def _split_area_id(split: dict) -> str:
    return str(split.get("area_id") or "").strip()


def is_poe1_campaign_end(area: str) -> bool:
    return _norm(area) in POE1_CAMPAIGN_END


def is_poe2_campaign_end(area: str) -> bool:
    return _norm(area) in POE2_CAMPAIGN_END


def log_has_campaign_end(splits: list[dict], game_id: str) -> bool:
    """日志窗口里是否出现过开荒终点。

    没出现 = 该角色在日志窗口内未通关（旧账号/中途弃坑），
    导入时应拒绝并提醒换已通关账号的日志。
    """
    game = str(game_id or "").strip().lower()
    is_end = is_poe1_campaign_end if game == "poe1" else is_poe2_campaign_end
    for split in splits:
        area_id = _split_area_id(split)
        if area_id and is_campaign_over_area_id(area_id, game):
            return True
        if any(is_end(name) for name in _split_area_names(split)):
            return True
    return False


def split_is_endgame_map(split: dict, game_id: str) -> bool:
    """该节点是否是异界地图（剧情之后的地图，不应导入开荒路线）。"""
    area_id = _split_area_id(split)
    if not area_id:
        return False
    return is_endgame_map_area_id(area_id, game_id)


def truncate_at_campaign_end(splits: list[dict], game_id: str) -> list[dict]:
    """保留至剧情结束点（含），之后全部丢弃。

    - 异界地图节点（``MapWorlds*`` / ``Map*``）一律丢弃，不进开荒路线。
    - 剧情结束点（PoE1 ``2_11`` 卡鲁海滩 / PoE2 ``G_Endgame_Town``）保留该节点。
    - 没有 area id 时退回区域名判定（保留旧行为）。
    """
    if not splits:
        return []

    game = str(game_id or "").strip().lower()
    seen_final_boss = False
    result: list[dict] = []

    for split in splits:
        area_id = _split_area_id(split)
        names = _split_area_names(split)

        # 异界地图：直接丢弃（不是剧情，也不该出现在开荒路线里）
        if area_id and is_endgame_map_area_id(area_id, game):
            continue

        if game == "poe1":
            if any(_norm(name) in POE1_FINAL_BOSS_AREA for name in names):
                seen_final_boss = True
            result.append(split)
            if area_id:
                # area id 权威：``2_11`` = 奇塔弗之后的卡鲁海滩 = 剧情结束
                if detect_act(area_id, game).campaign_over:
                    break
                continue
            # 名称兜底：Karui Shores 在 Act 5→6 过渡时也会出现（之后是 Act 6
            # Lioneye's Watch），只有「打完 Act 10 奇塔弗（饲槽）之后」的那次才是终点。
            if seen_final_boss and any(is_poe1_campaign_end(name) for name in names):
                break
            if seen_final_boss and any(
                _norm(name) in POE1_LEGACY_TOWN_AFTER_BOSS for name in names
            ):
                break
            continue

        if game == "poe2":
            result.append(split)
            if area_id:
                if detect_act(area_id, game).campaign_over:
                    break
                continue
            if any(is_poe2_campaign_end(name) for name in names):
                break
            continue

        result.append(split)

    return result


def campaign_end_act(game_id: str) -> int:
    """剧情结束的幕号（PoE1 = 11 表示 ``2_11``；PoE2 = 0 表示无幕号概念）。"""
    if str(game_id or "").strip().lower() == "poe1":
        return POE1_CAMPAIGN_END_ACT
    return 0
