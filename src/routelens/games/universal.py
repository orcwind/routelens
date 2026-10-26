from __future__ import annotations

import re

from ..events import EventType
from .base import CLIENT_PREFIX, GameProfile

# 通用 Client.txt 规则：适用于 GGG 系游戏（PoE1 / PoE2 等），无需指定游戏 ID。
UNIVERSAL_CHAPTERS = frozenset(
    {
        "第一章",
        "第二章",
        "第三章",
        "第四章",
        "第五章",
        "第六章",
        "Act 1",
        "Act 2",
        "Act 3",
        "Act 4",
        "Act 5",
        "Act 6",
    }
)
UNIVERSAL_SKIP = frozenset({"(null)", "(unknown)", *UNIVERSAL_CHAPTERS})

# PoE1 剧情结束：打完 Act 10 奇塔弗后的永久削弱提示。
# 实测两种形态（真机 Client.txt）：
#   Act 5  第一次奇塔弗：Kitava's **cruel** affliction     → -30% 全抗（不是结束）
#   Act 10 第二次奇塔弗：Kitava's **merciless** affliction → -60% 全抗（剧情结束）
# 必须按 60% 区分，否则会在第 5 幕就误判剧情结束。
CAMPAIGN_END_PATTERN = re.compile(
    rf"{CLIENT_PREFIX} : .*(?:Kitava|奇塔弗|奇塔娃).*(?:-60%|60% )"
)

UNIVERSAL_PROFILE = GameProfile(
    id="auto",
    display_name="Auto",
    skip_area_names=UNIVERSAL_SKIP,
    chapter_names=UNIVERSAL_CHAPTERS,
    town_keywords=(
        "營地",
        "营地",
        "車隊",
        "车队",
        "庇護所",
        "庇护所",
        "郊區",
        "郊区",
        "Encampment",
        "Caravan",
        "Hideout",
        "Town",
        "Hub",
    ),
    livesplit_game_name="",
    area_names_file="",
    export_lss_name="data/routelens/route.lss",
    extra_patterns=(
        (EventType.CAMPAIGN_END, CAMPAIGN_END_PATTERN),
        (EventType.AREA_ENTERED, re.compile(rf"{CLIENT_PREFIX} : You have entered (.+)\.")),
        (EventType.AREA_ENTERED, re.compile(rf"{CLIENT_PREFIX} \[SCENE\] Set Source \[(.+?)\]")),
        (EventType.AREA_ENTERED, re.compile(rf"{CLIENT_PREFIX} \[LOADING SCREEN\] \((.+?)\)")),
        (EventType.CHARACTER_LEVEL, re.compile(rf"{CLIENT_PREFIX} : (.+?) \((.+?)\) is now level ([0-9]+)")),
        (EventType.CHARACTER_LEVEL, re.compile(rf"{CLIENT_PREFIX} : (.+?)[（(](.+?)[）)]目前等[級级]：?\s*([0-9]+)")),
        (EventType.DEATH, re.compile(rf"{CLIENT_PREFIX} : You have died ([0-9]+) times\.")),
        (EventType.DEATH, re.compile(rf"{CLIENT_PREFIX} : (.+?) has been slain\.")),
        (EventType.DEATH, re.compile(rf"{CLIENT_PREFIX} : (.+?) 被[殺杀][害死]了。")),
    ),
)
