from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

from .companion_config import (
    COMPANION_CONFIG_PATH,
    CompanionConfig,
    default_companion_section,
    ensure_config_file,
    load_companion_config,
)

ROUTELENS_DATA_DIR = "data/routelens"


def load_routelens_config() -> CompanionConfig:
    config = load_companion_config()
    return replace(config, data_dir=ROUTELENS_DATA_DIR)


def is_routelens_setup_complete(config: CompanionConfig) -> bool:
    client = config.resolved_client_path
    return client is not None and client.is_file()


def save_routelens_setup(client_path: str, game_id: str) -> None:
    ensure_config_file(COMPANION_CONFIG_PATH)
    data = json.loads(COMPANION_CONFIG_PATH.read_text(encoding="utf-8"))
    companion = data.setdefault("companion", default_companion_section())
    companion["client_txt_path"] = client_path
    companion["game"] = game_id
    display = "Path of Exile 2" if game_id == "poe2" else "Path of Exile"
    companion["game_display_name"] = display
    by_game = companion.setdefault("client_txt_by_game", {})
    by_game[game_id] = client_path
    COMPANION_CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")


def clear_client_path_for_other_games(client_path: str, keep_game: str) -> None:
    """从其它游戏行移除同一 Client.txt 路径（选错游戏行导入后纠正显示）。"""
    keep = str(keep_game or "").strip().lower()
    if not keep:
        return
    target = os.path.normcase(os.path.abspath(client_path))
    ensure_config_file(COMPANION_CONFIG_PATH)
    data = json.loads(COMPANION_CONFIG_PATH.read_text(encoding="utf-8"))
    companion = data.get("companion") or {}
    by_game = companion.get("client_txt_by_game") or {}
    removed: list[str] = []
    for game_id, raw in list(by_game.items()):
        if str(game_id).strip().lower() == keep:
            continue
        if raw and os.path.normcase(os.path.abspath(str(raw))) == target:
            by_game.pop(game_id, None)
            removed.append(str(game_id))
    if not removed:
        return
    companion["client_txt_by_game"] = by_game
    data["companion"] = companion
    COMPANION_CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")


def load_client_path_for_game(game_id: str) -> Path | None:
    ensure_config_file(COMPANION_CONFIG_PATH)
    data = json.loads(COMPANION_CONFIG_PATH.read_text(encoding="utf-8"))
    companion = data.get("companion") or {}
    by_game = companion.get("client_txt_by_game") or {}
    raw = by_game.get(game_id) or ""
    if raw:
        path = Path(raw)
        if path.is_file():
            return path.resolve()
    # 兼容旧配置：当前游戏匹配时用主路径
    if companion.get("game") == game_id:
        main = companion.get("client_txt_path") or ""
        if main:
            path = Path(main)
            if path.is_file():
                return path.resolve()
    return None


def load_ui_lang() -> str:
    ensure_config_file(COMPANION_CONFIG_PATH)
    data = json.loads(COMPANION_CONFIG_PATH.read_text(encoding="utf-8"))
    companion = data.get("companion") or {}
    lang = str(companion.get("ui_lang") or "zh").lower()
    return "en" if lang.startswith("en") else "zh"


def save_ui_lang(lang: str) -> None:
    ensure_config_file(COMPANION_CONFIG_PATH)
    data = json.loads(COMPANION_CONFIG_PATH.read_text(encoding="utf-8"))
    companion = data.setdefault("companion", default_companion_section())
    companion["ui_lang"] = "en" if str(lang).lower().startswith("en") else "zh"
    COMPANION_CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")


def load_check_updates() -> bool:
    ensure_config_file(COMPANION_CONFIG_PATH)
    data = json.loads(COMPANION_CONFIG_PATH.read_text(encoding="utf-8"))
    companion = data.get("companion") or {}
    if "check_updates" not in companion:
        return True
    return bool(companion.get("check_updates"))


def save_check_updates(enabled: bool) -> None:
    ensure_config_file(COMPANION_CONFIG_PATH)
    data = json.loads(COMPANION_CONFIG_PATH.read_text(encoding="utf-8"))
    companion = data.setdefault("companion", default_companion_section())
    companion["check_updates"] = bool(enabled)
    COMPANION_CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
