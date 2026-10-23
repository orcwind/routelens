"""开荒结束判定：进入终局城镇后截断。"""

from __future__ import annotations


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


def is_poe1_campaign_end(area: str) -> bool:
    return _norm(area) in POE1_CAMPAIGN_END


def is_poe2_campaign_end(area: str) -> bool:
    return _norm(area) in POE2_CAMPAIGN_END


def log_has_campaign_end(splits: list[dict], game_id: str) -> bool:
    """日志窗口里是否出现过开荒终点锚点。

    没出现 = 该角色在日志窗口内未通关（旧账号/中途弃坑），
    导入时应拒绝并提醒换已通关账号的日志。
    """
    game = str(game_id or "").strip().lower()
    is_end = is_poe1_campaign_end if game == "poe1" else is_poe2_campaign_end
    return any(is_end(name) for split in splits for name in _split_area_names(split))


def truncate_at_campaign_end(splits: list[dict], game_id: str) -> list[dict]:
    """保留至第一个开荒终局城镇（含），之后全部丢弃。"""
    if not splits:
        return []

    game = str(game_id or "").strip().lower()
    seen_final_boss = False
    result: list[dict] = []

    for split in splits:
        names = _split_area_names(split)
        if game == "poe1":
            if any(_norm(name) in POE1_FINAL_BOSS_AREA for name in names):
                seen_final_boss = True
            result.append(split)
            if any(is_poe1_campaign_end(name) for name in names):
                break
            if seen_final_boss and any(
                _norm(name) in POE1_LEGACY_TOWN_AFTER_BOSS for name in names
            ):
                break
            continue

        if game == "poe2":
            result.append(split)
            if any(is_poe2_campaign_end(name) for name in names):
                break
            continue

        result.append(split)

    return result
