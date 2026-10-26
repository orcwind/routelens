from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable


class EventType(str, Enum):
    AREA_ENTERED = "area_entered"
    CHARACTER_LEVEL = "character_level"
    DEATH = "death"
    DISCONNECTED = "disconnected"
    LOG_OPENED = "log_opened"
    INSTANCE_CONNECT = "instance_connect"
    # 剧情结束：PoE1 打完 Act 10 奇塔弗（-60% 全抗永久削弱）
    CAMPAIGN_END = "campaign_end"


@dataclass(frozen=True)
class GameEvent:
    type: EventType
    timestamp: datetime
    raw_line: str = ""
    area: str = ""
    area_id: str = ""
    character: str = ""
    character_class: str = ""
    level: int = 0
    death_count: int = 0
    server: str = ""


EventHandler = Callable[[GameEvent], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = {}
        self._global_handlers: list[EventHandler] = []

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        self._global_handlers.append(handler)

    def publish(self, event: GameEvent) -> None:
        for handler in self._global_handlers:
            handler(event)
        for handler in self._handlers.get(event.type, []):
            handler(event)
