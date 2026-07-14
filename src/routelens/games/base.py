from __future__ import annotations

from dataclasses import dataclass, field
import re

from ..events import EventType

LOG_TIMESTAMP = r"([0-9]{4}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})"
CLIENT_PREFIX = rf"{LOG_TIMESTAMP}.*\[INFO Client [0-9]+\]"


@dataclass(frozen=True)
class GameProfile:
    """游戏配置。默认 universal 适用于所有 GGG Client.txt 游戏，无需配置 game。"""

    id: str
    display_name: str
    log_open_marker: str = "***** LOG FILE OPENING *****"
    skip_area_names: frozenset[str] = frozenset()
    chapter_names: frozenset[str] = frozenset()
    town_keywords: tuple[str, ...] = ()
    livesplit_game_name: str = ""
    area_names_file: str = ""
    export_lss_name: str = ""
    extra_patterns: tuple[tuple[EventType, re.Pattern[str]], ...] = field(default_factory=tuple)

    def build_log_patterns(self) -> list[tuple[EventType, re.Pattern[str]]]:
        patterns = list(self.extra_patterns)
        patterns.extend(
            [
                (EventType.INSTANCE_CONNECT, re.compile(rf"{CLIENT_PREFIX} Connecting to instance server at (.+)\.")),
                (EventType.DISCONNECTED, re.compile(rf"{CLIENT_PREFIX} Disconnecting from instance server\.")),
            ]
        )
        return patterns
