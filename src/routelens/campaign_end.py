"""开荒结束判定：进入终局城镇后截断，避免异界地图进入参考路线。"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path


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

_WAYSTONE_CSV = Path(__file__).resolve().parents[2] / "csv" / "poe2" / "poe2_waystone_maps.csv"


@lru_cache(maxsize=1)
def _poe2_waystone_area_names() -> frozenset[str]:
    if not _WAYSTONE_CSV.is_file():
        return frozenset()
    names: set[str] = set()
    try:
        with _WAYSTONE_CSV.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                for key in ("name_en", "name_cn", "name_tw"):
                    raw = str(row.get(key) or "").strip()
                    if raw:
                        names.add(_norm(raw))
    except OSError:
        return frozenset()
    # CSV 误含终局城镇，开荒截断时不当异界地图
    return frozenset(names) - POE2_CAMPAIGN_END


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


def is_poe2_waystone_map(area: str) -> bool:
    return _norm(area) in _poe2_waystone_area_names()


def truncate_at_campaign_end(splits: list[dict], game_id: str) -> list[dict]:
    """保留至第一个开荒终局城镇（含），之后全部丢弃。

    PoE2 额外：一旦出现异界地图名（Waystone 列表），立即停止且不纳入该地图。
    """
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
            # 终局城镇优先：纳入后截断（即使 CSV 误标为地图）
            if any(is_poe2_campaign_end(name) for name in names):
                result.append(split)
                break
            if any(is_poe2_waystone_map(name) for name in names):
                break
            result.append(split)
            continue

        result.append(split)

    return result
