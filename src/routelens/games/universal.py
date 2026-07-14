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
    area_names_file="data/routelens/area_names.json",
    export_lss_name="data/routelens/route.lss",
    extra_patterns=(
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
