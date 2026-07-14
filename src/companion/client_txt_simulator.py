from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path

from . import test_log

BACKUP_SUFFIX = ".poe2assist.bak"

# 第一章陵墓区常见乱序：先配偶墓室再政务官陵墓
TOMB_BRANCH_OUT_OF_ORDER = ["配偶的墓室", "政務官陵墓", "獵場"]


def backup_path(client_path: Path) -> Path:
    return client_path.with_name(client_path.name + BACKUP_SUFFIX)


def has_backup(client_path: Path) -> bool:
    return backup_path(client_path).is_file()


def backup_client_txt(client_path: Path) -> Path:
    target = backup_path(client_path)
    if not target.exists():
        shutil.copy2(client_path, target)
        test_log.write("CLIENT", "已备份 Client.txt", client=str(client_path), backup=str(target))
    return target


def restore_client_txt(client_path: Path) -> bool:
    source = backup_path(client_path)
    if not source.is_file():
        test_log.write("CLIENT", "恢复失败：无备份", client=str(client_path))
        return False
    shutil.copy2(source, client_path)
    source.unlink()
    test_log.write("CLIENT", "已恢复 Client.txt", client=str(client_path))
    return True


def format_scene_line(area: str, moment: datetime | None = None) -> str:
    now = moment or datetime.now()
    timestamp = now.strftime("%Y/%m/%d %H:%M:%S")
    tick = int(now.timestamp() * 1000) % 100_000_000
    return f"{timestamp} {tick} 7fbd1225 [INFO Client 99999] [SCENE] Set Source [{area}]\n"


def append_scene_change(client_path: Path, area: str, moment: datetime | None = None) -> None:
    if not client_path.is_file():
        raise FileNotFoundError(f"找不到 Client.txt：{client_path}")
    backup_client_txt(client_path)
    line = format_scene_line(area, moment)
    with client_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
    test_log.write(
        "CLIENT",
        "追加 SCENE 行",
        client=str(client_path),
        area=area,
        line=line.strip(),
    )


def append_scene_sequence(
    client_path: Path,
    areas: list[str],
    *,
    step_seconds: float = 1.0,
    start_at: datetime | None = None,
) -> None:
    moment = start_at or datetime.now()
    for index, area in enumerate(areas):
        append_scene_change(client_path, area, moment + timedelta(seconds=index * step_seconds))
