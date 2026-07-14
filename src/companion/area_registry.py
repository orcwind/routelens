from __future__ import annotations

import json
from pathlib import Path

from .games.base import GameProfile


class AreaRegistry:
    def __init__(self, path: Path, game: GameProfile, locale: str = "zh_cn") -> None:
        self.path = path
        self.game = game
        self.locale = locale
        self._entries, self._alias_to_canonical = self._load()

    def canonical_name(self, area: str) -> str:
        return self._alias_to_canonical.get(area, area)

    def english_name(self, area: str) -> str:
        canonical = self.canonical_name(area)
        entry = self._entries.get(canonical, {})
        return entry.get("en", canonical)

    def display_name(self, area: str) -> str:
        canonical = self.canonical_name(area)
        entry = self._entries.get(canonical, {})
        if self.locale == "zh_tw":
            return entry.get("zh_tw") or entry.get("zh_cn") or area
        if self.locale == "zh_cn":
            return entry.get("zh_cn") or entry.get("zh_tw") or area
        return entry.get("en") or entry.get("zh_cn") or area

    def is_town(self, area: str) -> bool:
        canonical = self.canonical_name(area)
        lowered = canonical.lower()
        if any(keyword.lower() in lowered for keyword in self.game.town_keywords):
            return True
        entry = self._entries.get(canonical, {})
        if entry.get("is_town"):
            return True
        raw_entry = self._entries.get(area, {})
        return bool(raw_entry.get("is_town", False))

    def all_areas(self) -> dict[str, dict]:
        return dict(self._entries)

    def _load(self) -> tuple[dict[str, dict], dict[str, str]]:
        if not self.path.exists():
            return {}, {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}, {}

        entries: dict[str, dict] = {}
        alias_map: dict[str, str] = {}

        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            canonical = value.get("en") or key
            entry = dict(value)
            entry.setdefault("en", canonical)
            entries[canonical] = entry
            for alias in self._aliases_for_entry(canonical, entry, key):
                alias_map[alias] = canonical

        return entries, alias_map

    @staticmethod
    def _aliases_for_entry(canonical: str, entry: dict, key: str) -> set[str]:
        names = {canonical, key, entry.get("en", ""), entry.get("zh_tw", ""), entry.get("zh_cn", "")}
        extra = entry.get("aliases", [])
        if isinstance(extra, list):
            names.update(extra)
        return {name for name in names if name}
