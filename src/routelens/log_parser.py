from __future__ import annotations

import re
from datetime import datetime

from .events import EventType, GameEvent
from .games.base import GameProfile
from .games.registry import get_game

# area id = 幕归属的唯一权威来源（PoE1: 1_5_6 / PoE2: G2_10_1）
GENERATING_AREA_RE = re.compile(r"Generating level \d+ area \"([^\"]+)\"")


def parse_timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y/%m/%d %H:%M:%S")


def parse_line(
    line: str,
    game: GameProfile | None = None,
    *,
    last_area_id: str = "",
) -> GameEvent | None:
    profile = game or get_game(None)
    stripped = line.strip()
    if not stripped:
        return None

    if profile.log_open_marker in stripped:
        return GameEvent(
            type=EventType.LOG_OPENED,
            timestamp=datetime.now(),
            raw_line=stripped,
        )

    for event_type, pattern in profile.build_log_patterns():
        match = pattern.search(stripped)
        if not match:
            continue

        groups = match.groups()
        timestamp = parse_timestamp(groups[0])
        payload = groups[1:]

        if event_type == EventType.AREA_ENTERED:
            area = payload[0].strip().rstrip(".")
            if area in profile.skip_area_names or area in profile.chapter_names:
                return None
            return GameEvent(
                type=event_type,
                timestamp=timestamp,
                raw_line=stripped,
                area=area,
                area_id=last_area_id,
            )

        if event_type == EventType.CHARACTER_LEVEL:
            return GameEvent(
                type=event_type,
                timestamp=timestamp,
                raw_line=stripped,
                character=payload[0].strip(),
                character_class=payload[1].strip(),
                level=int(payload[2]),
            )

        if event_type == EventType.DEATH and len(payload) == 1:
            if payload[0].isdigit():
                return GameEvent(
                    type=event_type,
                    timestamp=timestamp,
                    raw_line=stripped,
                    death_count=int(payload[0]),
                )
            return GameEvent(
                type=event_type,
                timestamp=timestamp,
                raw_line=stripped,
                character=payload[0].strip(),
            )

        if event_type == EventType.INSTANCE_CONNECT:
            return GameEvent(
                type=event_type,
                timestamp=timestamp,
                raw_line=stripped,
                server=payload[0].strip(),
            )

        if event_type == EventType.DISCONNECTED:
            return GameEvent(
                type=event_type,
                timestamp=timestamp,
                raw_line=stripped,
            )

    return None
