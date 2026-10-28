from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from .log_analyzer import format_duration


def _slug(text: str, max_len: int = 20) -> str:
    value = re.sub(r'[<>:"/\\|?*]', "", text.strip())
    value = re.sub(r"\s+", " ", value)
    return (value[:max_len] if value else "未知")


def make_run_id(dt: datetime | None = None) -> str:
    moment = dt or datetime.now()
    return moment.strftime("%Y%m%d%H%M")


def make_folder_name(
    dt: datetime,
    character: str = "",
    league: str = "",
    chapters_filter: set[str] | None = None,
) -> str:
    time_part = dt.strftime("%Y-%m-%d %H-%M")
    parts = [time_part]
    if league:
        parts.append(_slug(league, 12))
    if character:
        parts.append(_slug(character, 16))
    if chapters_filter:
        if len(chapters_filter) == 1:
            parts.append(f"仅{next(iter(chapters_filter))}")
        else:
            parts.append("筛选章节")
    return " ".join(parts)


def _split_to_user_format(split: dict) -> dict:
    seconds = float(split.get("segment_seconds", 0))
    cumulative = split.get("cumulative_seconds")
    # 保留 Client.txt 里的原始区域名；不要用 display（会按配置语言改写成「清溪营」等错误简中）
    return {
        "area": split.get("area") or split.get("display") or split.get("area_en", ""),
        "area_en": split.get("area_en", ""),
        "elapsed": format_duration(seconds),
        "segment_seconds": seconds,
        "cumulative_seconds": cumulative,
        "arrived_at": split.get("arrived_at"),
        "area_id": split.get("area_id", "") or "",
        # 试炼进门节点：每次试炼都要记（area id 相同也不能去重）
        "is_trial_entry": bool(split.get("is_trial_entry")),
    }


def _split_area(split: dict) -> str:
    return split.get("area_en") or split.get("area") or ""


# 同名区域再次出现时，与上一次同名的距离小于该值 = 回城/折返噪声（丢弃）；
# 大于等于该值 = 真正的新一段进度（PoE1 的 Act 6–10 会复用 Act 1–5 区域名）。
REPEAT_NAME_MIN_GAP = 20


def _split_key(split: dict) -> str:
    """一次「到访」的身份。

    不能只用区域名：PoE1 的 Act 6–10 会重复使用 Act 1–5 的区域名
    （Lioneye's Watch / The Coast…），只用名字去重会把后半程整段删掉。
    有到达时间戳时用它做唯一身份（同一次到访才合并、重复导入仍幂等）。
    """
    arrived = str(split.get("arrived_at") or "").strip()
    area = _split_area(split)
    if arrived:
        return f"{area}@{arrived}"
    return area


def _chapter_label_from_list(chapters: list[str]) -> str:
    if not chapters:
        return ""
    if len(chapters) == 1:
        return chapters[0]
    return f"{chapters[0]} → {chapters[-1]}"


def _collect_chapters(*routes_or_sessions: dict) -> list[str]:
    from .chapter_normalize import sort_chapters

    chapters: list[str] = []
    for item in routes_or_sessions:
        for chapter in item.get("chapters") or []:
            if chapter not in chapters:
                chapters.append(chapter)
        label = item.get("chapter_label") or ""
        if "→" in label:
            for part in label.split("→"):
                name = part.strip()
                if name and name not in chapters:
                    chapters.append(name)
        elif label and label not in chapters:
            chapters.append(label)
    return sort_chapters(chapters)


def _order_splits_by_act(splits: list[dict], game_id: str) -> list[dict]:
    """把节点按章节归位；同一章内保持首次出现的先后顺序。

    多会话合并是「按时间顺序 append」的，退出游戏再上线那段会接在后面 ——
    于是出现结构性错位。真机证据（2026-10-27 用户日志 ``bafawefasdf``）：

        33 1_3_1       The City of Sarn      ← Act 3
        34 1_4_town    Highgate              ← Act 4 **插在 Act 3 中间**
        35 1_3_town    The Sarn Encampment   ← Act 3 还没跑完

    幕号是 area id 里写死的，不依赖玩家路线，所以按幕重排不会打乱真实顺序：
    已经有序的路线排序后完全不变（稳定排序）。

    **間歇（PoE2）** 同样要归位：它排在 Act 4 之后（内部槽位 = 5），
    组内按 ``P1 → P2 → P3``、每组内 ``Town → _1 → _2 …`` 排。
    真机证据（``azdasfasdfsa``）合并后 P3 跑到了 P1 前面。

    无幕号的节点（升华试炼 ``Labyrinth_Airlock``、支线）跟随它前一个节点的幕，
    保持相对位置，不会被甩到末尾。
    """
    if len(splits) < 2:
        return splits
    from .act_map import detect_act

    keyed: list[tuple[tuple[int, int, int], int, dict]] = []
    last_key = (0, 0, 0)
    for index, split in enumerate(splits):
        area_id = str(split.get("area_id") or "")
        info = detect_act(area_id, game_id)
        if info.act is not None:
            key = (info.act, 0, 0)
        elif info.campaign_over:
            # 終局 = 剧情终点，永远排最后
            key = (6, 0, 0)
        elif info.is_interlude:
            # P1_Town / P2_6 …：组号 + 组内序号（Town 视为组起点 0）
            parts = area_id.split("_")
            group = 0
            if len(parts) >= 1 and parts[0][1:].isdigit():
                group = int(parts[0][1:])
            seq = 0
            if len(parts) >= 2:
                head = parts[1]
                if head.isdigit():
                    seq = int(head) + 1  # Town(0) 排在 _1 之前
                elif head.lower() == "town":
                    seq = 0
            key = (5, group, seq)
        else:
            key = last_key
        last_key = key
        keyed.append((key, index, split))
    keyed.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in keyed]


def _merge_splits(
    existing: list[dict],
    new: list[dict],
    *,
    keep_repeated_names: bool = False,
) -> list[dict]:
    """合并节点。

    ``keep_repeated_names=False``（PoE2 / 通用）：按 **area id** 去重 ——
    area id 相同 = 同一个区域实例（回城 / 来回跑）→ 丢弃；
    **同名但 area id 不同 = 不同区域** → 保留。
    （实测 PoE2 Act 4：``G4_8a`` 与 ``G4_8b`` 都叫「阿拉塔斯」，
    ``G4_11_1a`` 与 ``G4_11_1b`` 都叫「尼加卡努」——按名字去重会吃掉后半程。
    area id 缺失时才退回「按名字去重」。）

    ``keep_repeated_names=True``（PoE1）：Act 6–10 会复用 Act 1–5 的区域名，
    必须保留**跨幕**再次出现的同名区域；同一幕内来回跑的同名要丢弃。

    判据 = area id（唯一标识一个区域实例）：
    同名但 area id 不同 → 不同区域（Act 5 的 The Ossuary vs Act 10 的）→ 保留；
    area id 相同 → 同一个区域又去了一次 → 丢弃。

    **试炼进门节点例外**：``is_trial_entry=True`` 的节点每次都要保留 ——
    多次试炼的进门 area id 完全相同（Labyrinth_Airlock），
    按 area id 去重会把第二次以后的试炼全删掉。
    """
    merged = [_split_to_user_format(item) if "elapsed" not in item else dict(item) for item in existing]
    seen = {_split_key(split) for split in merged if _split_key(split)}
    seen_areas = {_split_area(split) for split in merged if _split_area(split)}
    last_index_by_area: dict[str, int] = {}
    seen_area_ids: set[str] = set()
    for index, split in enumerate(merged):
        area = _split_area(split)
        if area:
            last_index_by_area[area] = index
        area_id = str(split.get("area_id") or "").strip()
        if area_id and not split.get("is_trial_entry"):
            seen_area_ids.add(area_id)
    for item in new:
        split = _split_to_user_format(item) if "elapsed" not in item else dict(item)
        is_trial = bool(split.get("is_trial_entry"))
        key = _split_key(split)
        if not key or key in seen:
            continue
        area = _split_area(split)
        area_id = str(split.get("area_id") or "").strip()
        if area and not is_trial:
            if keep_repeated_names:
                # area id 相同 = 同一个区域又去了一次（回城 / 来回跑）→ 丢弃
                if area_id and area_id in seen_area_ids:
                    continue
                # 同名但 area id 不同 = 不同区域（PoE1 Act 5 vs Act 10）→ 保留。
                # area id 缺失时才退回「距离窗口」启发式。
                if not area_id:
                    previous = last_index_by_area.get(area)
                    if previous is not None and len(merged) - 1 - previous < REPEAT_NAME_MIN_GAP:
                        continue
            elif area_id:
                # 有 area id = 以 area id 为唯一身份：
                # 同 id = 同一个区域又去了一次 → 丢弃；不同 id = 不同区域 → 保留。
                if area_id in seen_area_ids:
                    continue
            elif area in seen_areas:
                # 无 area id 时才退回「按名字去重」
                continue
        seen.add(key)
        merged.append(split)
        if area:
            seen_areas.add(area)
            last_index_by_area[area] = len(merged) - 1
        if area_id and not is_trial:
            seen_area_ids.add(area_id)
    return merged


def _finalize_route_metrics(route: dict) -> dict:
    splits = route.get("splits", [])
    chapters = _collect_chapters(route)
    total_seconds = sum(float(item.get("segment_seconds", 0)) for item in splits)
    route["splits"] = splits
    route["node_count"] = len(splits)
    route["elapsed_seconds"] = total_seconds
    route["elapsed"] = format_duration(total_seconds)
    route["current_area"] = splits[-1]["area"] if splits else route.get("current_area", "")
    route["chapters"] = chapters
    route["chapter_label"] = _chapter_label_from_list(chapters) or route.get("chapter_label", "")
    route["updated_at"] = datetime.now().isoformat(timespec="seconds")
    return route


def merge_route_dicts(left: dict, right: dict) -> dict:
    if (left.get("started_at") or "") <= (right.get("started_at") or ""):
        base, extra = left, right
    else:
        base, extra = right, left

    merged = dict(base)
    merged["splits"] = _merge_splits(base.get("splits", []), extra.get("splits", []))
    merged["deaths"] = int(base.get("deaths", 0)) + int(extra.get("deaths", 0))
    merged["league"] = base.get("league") or extra.get("league") or ""
    merged["source"] = extra.get("source") or base.get("source", "")
    merged["finished"] = bool(base.get("finished")) and bool(extra.get("finished"))
    session_ids = list(base.get("session_ids") or [])
    if base.get("session_id") is not None:
        session_ids.append(int(base["session_id"]))
    for sid in extra.get("session_ids") or []:
        if sid not in session_ids:
            session_ids.append(sid)
    if extra.get("session_id") is not None and int(extra["session_id"]) not in session_ids:
        session_ids.append(int(extra["session_id"]))
    merged["session_ids"] = session_ids
    merged["last_played_at"] = max(
        filter(None, [base.get("last_played_at"), extra.get("last_played_at"), extra.get("ended_at"), extra.get("started_at")]),
        default=base.get("last_played_at"),
    )
    return _finalize_route_metrics(merged)


def merge_session_dicts(
    sessions: list[dict],
    *,
    source: str,
    chapters_filter: set[str] | None = None,
    game_id: str = "",
) -> dict:
    ordered = sorted(sessions, key=lambda item: item.get("started_at") or "")
    route = session_to_route(ordered[0], source=source, chapters_filter=chapters_filter)
    route["session_ids"] = []
    # PoE1 的 Act 6–10 复用 Act 1–5 区域名，必须保留远处同名节点；PoE2 继续按名去重
    keep_repeated = str(game_id or "").strip().lower() == "poe1"
    for session in ordered:
        splits = [_split_to_user_format(item) for item in session.get("splits", [])]
        route["splits"] = _merge_splits(
            route.get("splits", []), splits, keep_repeated_names=keep_repeated
        )
        route["deaths"] = int(route.get("deaths", 0)) + int(session.get("deaths", 0))
        session_id = session.get("session_id")
        if session_id is not None:
            route["session_ids"].append(int(session_id))
    route["last_played_at"] = ordered[-1].get("ended_at") or ordered[-1].get("started_at")
    route["chapters"] = _collect_chapters(*ordered)
    # 多段会话拼接后按幕归位：退出再上线那段会接在末尾，
    # 出现「Act 4 城镇夹在 Act 3 中间」这种结构性错位（见 _order_splits_by_act）。
    if len(ordered) > 1:
        route["splits"] = _order_splits_by_act(route.get("splits") or [], game_id)
    return _finalize_route_metrics(route)


def session_to_route(
    session_dict: dict,
    *,
    source: str,
    chapters_filter: set[str] | None = None,
) -> dict:
    started_raw = session_dict.get("started_at") or ""
    started_dt = datetime.fromisoformat(started_raw) if started_raw else datetime.now()
    splits = [_split_to_user_format(item) for item in session_dict.get("splits", [])]
    total_seconds = float(session_dict.get("total_seconds", 0))
    current_area = splits[-1]["area"] if splits else session_dict.get("chapter_label", "")
    run_id = make_run_id(started_dt)
    return {
        "run_id": run_id,
        "character": session_dict.get("character") or "未知角色",
        "league": session_dict.get("league") or "",
        "started": started_dt.strftime("%Y-%m-%d %H:%M"),
        "started_at": started_dt.isoformat(timespec="seconds"),
        "finished": True,
        "elapsed": format_duration(total_seconds),
        "elapsed_seconds": total_seconds,
        "current_area": current_area,
        "chapter_label": session_dict.get("chapter_label", ""),
        "chapters": list(session_dict.get("chapters") or []),
        "chapters_filter": sorted(chapters_filter) if chapters_filter else None,
        "deaths": session_dict.get("deaths", 0),
        "node_count": len(splits),
        "splits": splits,
        "source": source,
        "session_id": session_dict.get("session_id"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


class RouteStore:
    """路线 = 一个角色的一次开荒。每个角色一个文件夹，多次登录自动合并。"""

    ROUTE_FILE = "route.json"
    CHECKPOINT_FILE = "checkpoint.json"
    PROGRESS_SAVES_DIR = "progress_saves"
    ACTIVE_PROGRESS_FILE = "active_progress.json"
    LSS_FILE = "livesplit.lss"

    def __init__(self, data_dir: Path) -> None:
        self.routes_root = data_dir / "Routes"
        self.routes_root.mkdir(parents=True, exist_ok=True)
        self.current_path = data_dir / "current_route.json"
        self.compare_path = data_dir / "compare_route.json"

    def import_session(
        self,
        session_dict: dict,
        source: str,
        chapters_filter: set[str] | None = None,
    ) -> Path:
        folders = self.import_sessions([session_dict], source, chapters_filter)
        return folders[0]

    def import_sessions(
        self,
        sessions: list[dict],
        source: str,
        chapters_filter: set[str] | None = None,
    ) -> list[Path]:
        grouped: dict[tuple[str, str], list[dict]] = {}
        for session in sessions:
            character = session.get("character") or "未知角色"
            league = session.get("league") or ""
            grouped.setdefault((character, league), []).append(session)

        folders: list[Path] = []
        for (character, league), character_sessions in grouped.items():
            folders.append(
                self._import_character_sessions(character, league, character_sessions, source, chapters_filter)
            )
        return folders

    def _import_character_sessions(
        self,
        character: str,
        league: str,
        sessions: list[dict],
        source: str,
        chapters_filter: set[str] | None = None,
    ) -> Path:
        imported = merge_session_dicts(sessions, source=source, chapters_filter=chapters_filter)
        existing_folders = self.folders_for_character(character)
        if existing_folders:
            keeper = self._pick_canonical_folder(existing_folders)
            merged = imported
            for folder_name in existing_folders:
                route = self.load(folder_name)
                if route:
                    merged = merge_route_dicts(route, merged)
            folder = self.folder_for(keeper)
            for folder_name in existing_folders:
                if folder_name != keeper:
                    self.delete(folder_name)
            self._write_route(folder, merged)
            return folder

        started_dt = datetime.fromisoformat(imported["started_at"])
        folder_name = make_folder_name(started_dt, character, league, chapters_filter)
        folder = self._unique_folder(folder_name, imported["run_id"])
        self._write_route(folder, imported)
        return folder

    def create_route(
        self,
        *,
        character: str = "",
        league: str = "",
        template: dict | None = None,
        mark_in_progress: bool = True,
    ) -> Path:
        now = datetime.now()
        route = session_to_route(
            {
                "character": character or (template or {}).get("character", ""),
                "league": league or (template or {}).get("league", ""),
                "started_at": now.isoformat(timespec="seconds"),
                "chapter_label": (template or {}).get("chapter_label", ""),
                "total_seconds": 0.0,
                "deaths": 0,
                "splits": (template or {}).get("splits", []),
                "session_id": 0,
            },
            source="new_route",
        )
        if template:
            route["splits"] = [_split_to_user_format(item) for item in template.get("splits", [])]
            route["node_count"] = len(route["splits"])
        route["finished"] = not mark_in_progress
        route["elapsed"] = "00:00"
        route["elapsed_seconds"] = 0.0
        route["current_area"] = route["splits"][0]["area"] if route["splits"] else ""
        route["source"] = "template" if template else "blank"

        existing = self.folders_for_character(route["character"])
        if route["character"] and existing:
            folder = self.folder_for(self._pick_canonical_folder(existing))
            if template:
                merged = merge_route_dicts(self.load(folder.name) or route, route)
                self._write_route(folder, merged)
            else:
                self._write_route(folder, route)
            self.set_current(folder.name)
            return folder

        folder_name = make_folder_name(now, route["character"], route["league"])
        folder = self._unique_folder(folder_name, route["run_id"])
        self._write_route(folder, route)
        self.set_current(folder.name)
        return folder

    def list_routes(self) -> list[dict]:
        items: list[dict] = []
        for folder in self.routes_root.iterdir():
            if not folder.is_dir():
                continue
            route = self.load(folder.name)
            if route:
                route["folder_name"] = folder.name
                items.append(route)
        items.sort(key=lambda item: item.get("started_at") or "", reverse=True)
        return items

    def load(self, folder_name: str) -> dict | None:
        path = self.routes_root / folder_name / self.ROUTE_FILE
        return self._read_json(path)

    def folder_for(self, folder_name: str) -> Path:
        return self.routes_root / folder_name

    def lss_path(self, folder_name: str) -> Path:
        return self.folder_for(folder_name) / self.LSS_FILE

    def checkpoint_path(self, folder_name: str) -> Path:
        return self.folder_for(folder_name) / self.CHECKPOINT_FILE

    def save_route(self, folder_name: str, route: dict) -> None:
        route["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._write_route(self.folder_for(folder_name), route)

    def save_checkpoint(self, folder_name: str, payload: dict) -> None:
        folder = self.folder_for(folder_name)
        folder.mkdir(parents=True, exist_ok=True)
        data = {"saved_at": datetime.now().isoformat(timespec="seconds"), **payload}
        (folder / self.CHECKPOINT_FILE).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        route = self.load(folder_name)
        if route:
            route["finished"] = False
            route["elapsed"] = payload.get("elapsed", route.get("elapsed", "00:00"))
            route["current_area"] = payload.get("current_area") or payload.get("current_split_name") or route.get("current_area", "")
            self.save_route(folder_name, route)

    def load_checkpoint(self, folder_name: str) -> dict | None:
        active = self.get_active_progress(folder_name)
        if active:
            return active
        return self._read_json(self.checkpoint_path(folder_name))

    def progress_saves_dir(self, folder_name: str) -> Path:
        path = self.folder_for(folder_name) / self.PROGRESS_SAVES_DIR
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _progress_save_path(self, folder_name: str, save_id: str) -> Path:
        safe = re.sub(r'[<>:"/\\|?*]', "_", save_id.strip())
        return self.progress_saves_dir(folder_name) / f"{safe}.json"

    def progress_lss_path(self, folder_name: str, save_id: str) -> Path:
        safe = re.sub(r'[<>:"/\\|?*]', "_", save_id.strip())
        return self.progress_saves_dir(folder_name) / f"{safe}.lss"

    def make_progress_save_id(self, name: str) -> str:
        moment = datetime.now()
        return f"{moment.strftime('%Y%m%d_%H%M%S')}_{_slug(name, 24)}"

    def _migrate_legacy_checkpoint(self, folder_name: str) -> None:
        legacy = self._read_json(self.checkpoint_path(folder_name))
        if not legacy:
            return
        saves = self._list_progress_save_files(folder_name)
        if saves:
            return
        name = legacy.get("name") or "上次进度"
        self.save_progress_named(folder_name, name, legacy)

    def _list_progress_save_files(self, folder_name: str) -> list[Path]:
        folder = self.progress_saves_dir(folder_name)
        return sorted(folder.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)

    def list_progress_saves(self, folder_name: str) -> list[dict]:
        self._migrate_legacy_checkpoint(folder_name)
        items: list[dict] = []
        active_id = self.get_active_progress_id(folder_name)
        for path in self._list_progress_save_files(folder_name):
            data = self._read_json(path)
            if not data:
                continue
            save_id = data.get("save_id") or path.stem
            items.append(
                {
                    "save_id": save_id,
                    "name": data.get("name") or save_id,
                    "saved_at": data.get("saved_at", ""),
                    "current_area": data.get("current_area", ""),
                    "elapsed": data.get("elapsed", ""),
                    "split_index": data.get("split_index", 0),
                    "is_active": save_id == active_id,
                }
            )
        return items

    def save_progress_named(
        self,
        folder_name: str,
        name: str,
        payload: dict,
        *,
        save_id: str | None = None,
    ) -> dict:
        folder = self.folder_for(folder_name)
        folder.mkdir(parents=True, exist_ok=True)
        moment = datetime.now()
        resolved_id = save_id or f"{moment.strftime('%Y%m%d_%H%M%S')}_{_slug(name, 24)}"
        data = {
            "save_id": resolved_id,
            "name": name.strip() or resolved_id,
            "saved_at": moment.isoformat(timespec="seconds"),
            **payload,
        }
        self._progress_save_path(folder_name, resolved_id).write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.set_active_progress_id(folder_name, resolved_id)
        route = self.load(folder_name)
        if route:
            route["finished"] = False
            route["elapsed"] = payload.get("elapsed", route.get("elapsed", "00:00"))
            route["current_area"] = payload.get("current_area") or route.get("current_area", "")
            self.save_route(folder_name, route)
        return data

    def load_progress_by_id(self, folder_name: str, save_id: str) -> dict | None:
        return self._read_json(self._progress_save_path(folder_name, save_id))

    def get_active_progress_id(self, folder_name: str) -> str | None:
        data = self._read_json(self.folder_for(folder_name) / self.ACTIVE_PROGRESS_FILE)
        if not data:
            return None
        save_id = data.get("save_id")
        return str(save_id) if save_id else None

    def set_active_progress_id(self, folder_name: str, save_id: str) -> None:
        folder = self.folder_for(folder_name)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / self.ACTIVE_PROGRESS_FILE).write_text(
            json.dumps({"save_id": save_id}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_active_progress(self, folder_name: str) -> dict | None:
        save_id = self.get_active_progress_id(folder_name)
        if not save_id:
            return None
        return self.load_progress_by_id(folder_name, save_id)

    def clear_active_progress(self, folder_name: str) -> None:
        path = self.folder_for(folder_name) / self.ACTIVE_PROGRESS_FILE
        path.unlink(missing_ok=True)

    def delete_progress_save(self, folder_name: str, save_id: str) -> bool:
        path = self._progress_save_path(folder_name, save_id)
        if not path.exists():
            return False
        path.unlink()
        if self.get_active_progress_id(folder_name) == save_id:
            (self.folder_for(folder_name) / self.ACTIVE_PROGRESS_FILE).unlink(missing_ok=True)
        return True

    def delete(self, folder_name: str) -> bool:
        folder = self.folder_for(folder_name)
        if not folder.exists():
            return False
        shutil.rmtree(folder)
        if self.get_current_folder() == folder_name and self.current_path.exists():
            self.current_path.unlink()
        return True

    def delete_many(self, folder_names: list[str]) -> int:
        unique = list(dict.fromkeys(folder_names))
        return sum(1 for name in unique if self.delete(name))

    def folders_for_character(self, character: str) -> list[str]:
        return [
            route["folder_name"]
            for route in self.list_routes()
            if route.get("character") == character and route.get("folder_name")
        ]

    def delete_by_character(self, character: str) -> list[str]:
        deleted: list[str] = []
        for folder_name in self.folders_for_character(character):
            if self.delete(folder_name):
                deleted.append(folder_name)
        return deleted

    def set_current(self, folder_name: str) -> dict | None:
        route = self.load(folder_name)
        if route is None:
            return None
        self.current_path.write_text(
            json.dumps({"folder_name": folder_name, "run_id": route.get("run_id", "")}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return route

    def get_current_folder(self) -> str | None:
        if not self.current_path.exists():
            return None
        try:
            data = json.loads(self.current_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return data.get("folder_name")

    def get_current_route(self) -> dict | None:
        folder = self.get_current_folder()
        if not folder:
            return None
        route = self.load(folder)
        if route:
            route["folder_name"] = folder
        return route

    def save_compare_route(self, route: dict) -> None:
        self.compare_path.write_text(json.dumps(route, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_compare_route(self) -> dict | None:
        return self._read_json(self.compare_path)

    def consolidate_all_characters(self) -> int:
        grouped: dict[str, list[str]] = {}
        for route in self.list_routes():
            character = route.get("character") or ""
            folder_name = route.get("folder_name")
            if character and folder_name:
                grouped.setdefault(character, []).append(folder_name)

        merged = 0
        for character, folders in grouped.items():
            if len(folders) > 1 and self._consolidate_character_folders(character, folders):
                merged += 1
        return merged

    def _consolidate_character_folders(
        self,
        character: str,
        folders: list[str] | None = None,
    ) -> Path | None:
        folders = folders or self.folders_for_character(character)
        if len(folders) <= 1:
            return self.folder_for(folders[0]) if folders else None

        keeper = self._pick_canonical_folder(folders)
        merged = self.load(keeper)
        if merged is None:
            return None

        for folder_name in folders:
            if folder_name == keeper:
                continue
            route = self.load(folder_name)
            if route:
                merged = merge_route_dicts(merged, route)
            self.delete(folder_name)

        self._write_route(self.folder_for(keeper), merged)
        return self.folder_for(keeper)

    def _pick_canonical_folder(self, folder_names: list[str]) -> str:
        def started_key(name: str) -> str:
            route = self.load(name)
            return route.get("started_at") if route else ""

        return min(folder_names, key=started_key)

    def route_summary_line(self, route: dict) -> str:
        status = "已完成" if route.get("finished") else "进行中"
        return (
            f"{route.get('started', '?')} | {route.get('character', '?')} | "
            f"{status} | {route.get('chapter_label') or route.get('current_area') or '-'} | "
            f"{route.get('elapsed', '00:00')} | {route.get('node_count', 0)} 个区域"
        )

    def _unique_folder(self, folder_name: str, run_id: str) -> Path:
        candidate = self.routes_root / folder_name
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        alt = self.routes_root / f"{folder_name} ({run_id})"
        alt.mkdir(parents=True, exist_ok=True)
        return alt

    def _write_route(self, folder: Path, route: dict) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / self.ROUTE_FILE).write_text(json.dumps(route, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
