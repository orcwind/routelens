from __future__ import annotations

from .base import GameProfile
from .poe2 import POE2_PROFILE
from .universal import UNIVERSAL_PROFILE

# 默认走通用 Profile；可选插件仅用于追加区域名等增强数据，不是使用前提。
_PLUGINS: dict[str, GameProfile] = {
    POE2_PROFILE.id: POE2_PROFILE,
}

DEFAULT_GAME_ID = UNIVERSAL_PROFILE.id


def get_game(game_id: str | None = None) -> GameProfile:
    if not game_id or game_id.lower() in {"auto", "default", "universal", ""}:
        return UNIVERSAL_PROFILE
    plugin = _PLUGINS.get(game_id.lower())
    if plugin is not None:
        return plugin
    return UNIVERSAL_PROFILE


def list_games() -> list[GameProfile]:
    return [UNIVERSAL_PROFILE, *_PLUGINS.values()]
