from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

POE2_MARKERS = re.compile(
    r"Path of Exile 2|PathOfExile2|Path of Exile 2/logs",
    re.IGNORECASE,
)
POE1_MARKERS = re.compile(
    r"Path of Exile/logs|流放之路|Path of Exile\\logs",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClientCandidate:
    path: Path
    platform_label: str
    game_id: str


CLIENT_HINTS_SHORT = "Client.txt 通常位置为：游戏目录\\logs\\Client.txt"
CLIENT_HINTS = CLIENT_HINTS_SHORT


def _exists(path: Path) -> Path | None:
    return path.resolve() if path.is_file() else None


def _guess_game_from_path(path: Path) -> str:
    text = str(path).lower()
    if "path of exile 2" in text or "pathofexile2" in text:
        return "poe2"
    if "流放之路" in text:
        return "poe1"
    if "path of exile" in text:
        return "poe1"
    return "poe2"


def detect_game_from_client(path: Path, *, sample_chars: int = 80_000) -> str:
    guess = _guess_game_from_path(path)
    try:
        sample = path.read_text(encoding="utf-8", errors="replace")[:sample_chars]
    except OSError:
        return guess

    if POE2_MARKERS.search(sample) or "第二章" in sample or "第三章" in sample:
        from companion.log_analyzer import discover_chapters_in_log

        if discover_chapters_in_log(path, "poe2"):
            return "poe2"

    if POE1_MARKERS.search(sample):
        return "poe1"

    if "You have entered" in sample and "Path of Exile 2" in sample:
        return "poe2"
    return guess


def iter_client_candidates() -> list[ClientCandidate]:
    home = Path.home()
    docs = home / "Documents" / "My Games"
    local = os.environ.get("LOCALAPPDATA", "")

    checks: list[tuple[str, list[Path]]] = [
        (
            "Path of Exile 2（官方）",
            [
                Path(r"C:\Program Files (x86)\Grinding Gear Games\Path of Exile 2\logs\Client.txt"),
                Path(r"C:\Program Files\Grinding Gear Games\Path of Exile 2\logs\Client.txt"),
                docs / "Path of Exile 2" / "logs" / "Client.txt",
            ],
        ),
        (
            "Path of Exile 2（Steam）",
            [
                Path(r"C:\Program Files (x86)\Steam\steamapps\common\Path of Exile 2\logs\Client.txt"),
                Path(r"C:\Program Files\Steam\steamapps\common\Path of Exile 2\logs\Client.txt"),
                Path(r"D:\Steam\steamapps\common\Path of Exile 2\logs\Client.txt"),
                Path(r"E:\Steam\steamapps\common\Path of Exile 2\logs\Client.txt"),
            ],
        ),
        (
            "Path of Exile 2（Epic）",
            [
                Path(r"C:\Program Files\Epic Games\PathOfExile2\logs\Client.txt"),
                Path(r"C:\Program Files\Epic Games\Path of Exile 2\logs\Client.txt"),
                Path(local) / "EpicGamesLauncher" / "Saved" / "Logs" / "Client.txt",
            ],
        ),
        (
            "Path of Exile 1（官方）",
            [
                Path(r"C:\Program Files (x86)\Grinding Gear Games\Path of Exile\logs\Client.txt"),
                Path(r"C:\Program Files\Grinding Gear Games\Path of Exile\logs\Client.txt"),
                docs / "Path of Exile" / "logs" / "Client.txt",
            ],
        ),
        (
            "Path of Exile 1（Steam）",
            [
                Path(r"C:\Program Files (x86)\Steam\steamapps\common\Path of Exile\logs\Client.txt"),
                Path(r"C:\Program Files\Steam\steamapps\common\Path of Exile\logs\Client.txt"),
            ],
        ),
        (
            "流放之路（腾讯）",
            [
                docs / "流放之路" / "logs" / "Client.txt",
                docs / "Path of Exile" / "logs" / "Client.txt",
            ],
        ),
    ]

    seen: set[Path] = set()
    found: list[ClientCandidate] = []
    for platform_label, paths in checks:
        for path in paths:
            resolved = _exists(path)
            if resolved is None or resolved in seen:
                continue
            seen.add(resolved)
            game_id = detect_game_from_client(resolved)
            found.append(ClientCandidate(path=resolved, platform_label=platform_label, game_id=game_id))
    return found


def discover_best_client() -> ClientCandidate | None:
    candidates = iter_client_candidates()
    return candidates[0] if candidates else None


def discover_client_for_game(game_id: str) -> ClientCandidate | None:
    """优先返回指定游戏（poe1/poe2）的 Client.txt。"""
    for candidate in iter_client_candidates():
        if candidate.game_id == game_id:
            return candidate
    # 路径猜测失败时，用目录名兜底
    for candidate in iter_client_candidates():
        guessed = _guess_game_from_path(candidate.path)
        if guessed == game_id:
            return candidate
    return None
