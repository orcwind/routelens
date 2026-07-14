from __future__ import annotations

import re

from ..events import EventType
from .base import CLIENT_PREFIX, GameProfile
from .universal import UNIVERSAL_CHAPTERS, UNIVERSAL_SKIP, UNIVERSAL_PROFILE

from ..chapter_normalize import (
    POE2_ALL_CHAPTER_NAMES,
    POE2_CHAPTER_ORDER,
    POE2_IGNORED_CHAPTER_LABELS,
    normalize_poe2_chapter,
)

# PoE2 专用：从 Client.txt 解析区域与章节。
POE2_PROFILE = GameProfile(
    id="poe2",
    display_name="Path of Exile 2",
    skip_area_names=UNIVERSAL_SKIP,
    chapter_names=POE2_ALL_CHAPTER_NAMES,
    town_keywords=UNIVERSAL_PROFILE.town_keywords,
    livesplit_game_name="Path of Exile 2",
    area_names_file="data/routelens/area_names.json",
    export_lss_name="data/routelens/route.lss",
    extra_patterns=UNIVERSAL_PROFILE.extra_patterns,
)
