from __future__ import annotations

from pathlib import Path

from .games.base import GameProfile


class AreaRegistry:
    """区域名一律以 Client.txt 原文为准，不做译名/别名映射。"""

    def __init__(self, path: Path | None, game: GameProfile, locale: str = "zh_cn") -> None:
        self.path = path
        self.game = game
        self.locale = locale
        self._entries: dict[str, dict] = {}
        self._alias_to_canonical: dict[str, str] = {}

    def set_locale(self, locale: str) -> None:
        self.locale = locale

    def canonical_name(self, area: str) -> str:
        return area

    def english_name(self, area: str) -> str:
        return area

    def display_name(self, area: str, locale: str | None = None) -> str:
        return area or ""

    def is_town(self, area: str) -> bool:
        if not area:
            return False
        lowered = area.lower()
        return any(keyword.lower() in lowered for keyword in self.game.town_keywords)

    def all_areas(self) -> dict[str, dict]:
        return {}
