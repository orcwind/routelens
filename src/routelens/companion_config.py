from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .paths import APP_ROOT, project_path

COMPANION_CONFIG_PATH = APP_ROOT / "config.json"

DEFAULT_CLIENT_PATHS = [
    APP_ROOT / "data" / "Client.txt",
    Path(r"C:\Program Files (x86)\Grinding Gear Games\Path of Exile 2\logs\Client.txt"),
    Path(r"C:\Program Files\Grinding Gear Games\Path of Exile 2\logs\Client.txt"),
    Path(os.path.expanduser(r"~\Documents\My Games\Path of Exile 2\logs\Client.txt")),
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\Path of Exile 2\logs\Client.txt"),
    Path(r"C:\Program Files\Steam\steamapps\common\Path of Exile 2\logs\Client.txt"),
    Path(r"C:\Program Files (x86)\Grinding Gear Games\Path of Exile\logs\Client.txt"),
    Path(os.path.expanduser(r"~\Documents\My Games\Path of Exile\logs\Client.txt")),
]

DEFAULT_LIVESPLIT_PATHS = [
    APP_ROOT / "livesplitEN" / "LiveSplit.exe",
    APP_ROOT / "LiveSplit" / "LiveSplit.exe",
    Path(os.path.expanduser(r"~\Desktop\LiveSplit\LiveSplit.exe")),
    Path(os.path.expanduser(r"~\Downloads\LiveSplit\LiveSplit.exe")),
]


@dataclass
class CompanionConfig:
    game: str
    game_display_name: str
    client_txt_path: str | None
    data_dir: str
    area_names_file: str
    auto_start_run: bool
    locale: str
    league: str
    town_area_keywords: list[str]
    poll_interval_seconds: float
    route_match_threshold: float
    livesplit_exe_path: str | None
    export_lss_path: str
    close_livesplit_on_quit: bool | None = None

    @property
    def resolved_livesplit_path(self) -> Path | None:
        if self.livesplit_exe_path:
            path = project_path(self.livesplit_exe_path)
            if path.is_file():
                return path.resolve()
        for candidate in DEFAULT_LIVESPLIT_PATHS:
            if candidate.is_file():
                return candidate.resolve()
        if self.livesplit_exe_path:
            path = project_path(self.livesplit_exe_path)
            if path.exists():
                return path.resolve()
        return None

    @property
    def resolved_export_lss_path(self) -> Path:
        return project_path(self.export_lss_path).resolve()

    @property
    def resolved_client_path(self) -> Path | None:
        if self.client_txt_path:
            path = project_path(self.client_txt_path)
            if path.is_file():
                return path.resolve()
        for candidate in DEFAULT_CLIENT_PATHS:
            if candidate.is_file():
                return candidate.resolve()
        if self.client_txt_path:
            path = project_path(self.client_txt_path)
            if path.exists():
                return path.resolve()
        return None

    @property
    def resolved_data_dir(self) -> Path:
        return project_path(self.data_dir)

    @property
    def resolved_area_names_path(self) -> Path:
        return project_path(self.area_names_file)


def discover_client_txt() -> Path | None:
    for candidate in DEFAULT_CLIENT_PATHS:
        if candidate.is_file():
            return candidate.resolve()
    return None


def discover_livesplit_exe() -> Path | None:
    for candidate in DEFAULT_LIVESPLIT_PATHS:
        if candidate.is_file():
            return candidate.resolve()
    return None


def is_setup_complete(config: CompanionConfig) -> bool:
    client = config.resolved_client_path
    exe = config.resolved_livesplit_path
    return client is not None and client.is_file() and exe is not None and exe.is_file()


def default_companion_section() -> dict:
    return {
        "game": "poe2",
        "game_display_name": "Path of Exile 2",
        "client_txt_path": None,
        "data_dir": "data/routelens",
        "area_names_file": "data/routelens/area_names.json",
        "auto_start_run": True,
        "locale": "zh_cn",
        "league": "",
        "town_area_keywords": ["Encampment", "Hideout", "Town"],
        "poll_interval_seconds": 0.2,
        "route_match_threshold": 0.95,
        "livesplit_exe_path": None,
        "export_lss_path": "data/routelens/route.lss",
        "close_livesplit_on_quit": None,
    }


def ensure_config_file(path: Path = COMPANION_CONFIG_PATH) -> None:
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"companion": default_companion_section()}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")


def load_companion_config(path: Path = COMPANION_CONFIG_PATH) -> CompanionConfig:
    ensure_config_file(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    companion = data.get("companion", {})
    defaults = default_companion_section()
    return CompanionConfig(
        game=companion.get("game") or defaults["game"],
        game_display_name=companion.get("game_display_name", defaults["game_display_name"]),
        client_txt_path=companion.get("client_txt_path"),
        data_dir=companion.get("data_dir", defaults["data_dir"]),
        area_names_file=companion.get("area_names_file", defaults["area_names_file"]),
        auto_start_run=bool(companion.get("auto_start_run", defaults["auto_start_run"])),
        locale=companion.get("locale", defaults["locale"]),
        league=companion.get("league", defaults["league"]),
        town_area_keywords=list(
            companion.get("town_area_keywords", defaults["town_area_keywords"])
        ),
        poll_interval_seconds=float(
            companion.get("poll_interval_seconds", defaults["poll_interval_seconds"])
        ),
        route_match_threshold=float(
            companion.get("route_match_threshold", defaults["route_match_threshold"])
        ),
        livesplit_exe_path=companion.get("livesplit_exe_path"),
        export_lss_path=companion.get("export_lss_path", defaults["export_lss_path"]),
        close_livesplit_on_quit=companion.get("close_livesplit_on_quit"),
    )


def _write_companion_field(key: str, value: str | None, path: Path = COMPANION_CONFIG_PATH) -> None:
    ensure_config_file(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    companion = data.setdefault("companion", default_companion_section())
    companion[key] = value
    path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")


def save_client_txt_path(client_path: str, path: Path = COMPANION_CONFIG_PATH) -> None:
    _write_companion_field("client_txt_path", client_path, path)


def save_game_display_name(name: str, path: Path = COMPANION_CONFIG_PATH) -> None:
    _write_companion_field("game_display_name", name, path)


def save_livesplit_exe_path(exe_path: str, path: Path = COMPANION_CONFIG_PATH) -> None:
    _write_companion_field("livesplit_exe_path", exe_path, path)


def save_setup_paths(
    client_path: str,
    livesplit_path: str,
    path: Path = COMPANION_CONFIG_PATH,
) -> None:
    ensure_config_file(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    companion = data.setdefault("companion", default_companion_section())
    companion["client_txt_path"] = client_path
    companion["livesplit_exe_path"] = livesplit_path
    path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")


def save_close_livesplit_on_quit(value: bool, path: Path = COMPANION_CONFIG_PATH) -> None:
    ensure_config_file(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    companion = data.setdefault("companion", default_companion_section())
    companion["close_livesplit_on_quit"] = value
    path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
