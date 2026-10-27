from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from .area_registry import AreaRegistry
from .act_map import (
    act_chapter_label,
    detect_act,
    is_campaign_over_area_id,
    is_poe1_campaign_area_id,
    is_poe2_campaign_area_id,
)
from .campaign_end import log_has_campaign_end, truncate_at_campaign_end
from .campaign_start import campaign_start_area_id
from .hideout_filter import is_hideout_area
from .log_analyzer import analyze_client_log
from .log_locale import detect_client_log_locale
from .route_library import merge_session_dicts
from . import test_log

from .campaign_end import log_has_campaign_end, truncate_at_campaign_end
from .models import ReferenceRoute, RouteNode

RECENT_ROUTE_LIMIT = 10
TAIL_READ_SIZES = (
    16 * 1024 * 1024,
    64 * 1024 * 1024,
    128 * 1024 * 1024,
)
TAIL_SESSION_SCAN_LIMIT = 200
MIN_COMPLETE_NODES = 35
# 过滤后不足这么多剧情节点 = 登录/回城残留，不算一条路线
MIN_ROUTE_SPLITS = 4
UNKNOWN_CHAPTER_LABELS = frozenset({"未知", "未知章节", ""})

EARLY_CHAPTERS = {"第一章", "第二章", "Act 1", "Act 2"}
MID_CHAPTERS_POE2 = {"第三章", "Act 3"}
LATE_CHAPTERS_POE1 = {"第五章", "第六章", "Act 5", "Act 6"}
LATE_CHAPTERS_POE2 = {"第四章", "第五章", "Act 4", "Act 5"}


def _load_area_chapter_map() -> dict[str, str]:
    """章节信息只认 Client.txt；不再使用外部 campaign_splits 表。"""
    return {}


def _expand_area_chapter_map(
    base: dict[str, str],
    area_registry: AreaRegistry | None,
) -> dict[str, str]:
    return dict(base) if base else {}


def _route_name(character: str, chapter_label: str, started_at: str | None = None) -> str:
    character = character.strip() or "未知角色"
    label = chapter_label.strip()
    if label and label not in UNKNOWN_CHAPTER_LABELS:
        base = f"{character} ({label})"
    else:
        base = character
    if started_at:
        try:
            moment = datetime.fromisoformat(started_at)
            base += f" · {moment.strftime('%m-%d %H:%M')}"
        except ValueError:
            pass
    return base


def _filtered_splits(session_dict: dict, game_id: str | None = None) -> list[dict]:
    splits = [
        split
        for split in session_dict.get("splits", [])
        if not is_hideout_area(str(split.get("area") or split.get("area_en") or ""))
    ]
    if game_id:
        splits = _drop_non_campaign_splits(splits, game_id)
        if not any(str(split.get("area_id") or "").strip() for split in splits):
            # 整段没有 area id（极旧日志 / 无 Generating 行）：无法判幕也无法
            # 找起点，只能退回旧行为 —— 按剧情结束后截断。
            return truncate_at_campaign_end(splits, game_id)
        # 一次开荒 = 从第一幕起点 → 剧情结束；中间反复回旧节点由去重处理。
        splits = _select_campaign_run(splits, game_id)
    return splits


def _split_campaign_runs(splits: list[dict], game_id: str) -> list[list[dict]]:
    """按「开荒起点」把节点切成若干次 run。

    一次开荒必然从第一幕固定起点开始（PoE1 = ``1_1_1`` / PoE2 = ``G1_1``），
    所以每一次出现起点 = 一次**新的开荒**。

    **找不到起点就返回空**（这条记录不能用）：
    Client.txt 会被轮转 / 清理，日志很可能只剩中途某一段。
    没有起点就无法确认「这是从那一次开荒的中途开始的」，
    按用户要求**放弃**，不伪造第一幕起点。

    第一个起点之前的节点属于「上一个角色 / 上一段」，直接丢弃。
    """
    start_id = campaign_start_area_id(game_id)
    if not start_id or not splits:
        return []
    runs: list[list[dict]] = []
    current: list[dict] = []
    for split in splits:
        if str(split.get("area_id") or "").strip() == start_id:
            if current:
                runs.append(current)
            current = [split]
        elif current:
            current.append(split)
    if current:
        runs.append(current)
    return runs


def _cut_impossible_forward_jump(splits: list[dict], game_id: str) -> list[dict]:
    """在「前进超过 1 幕」处截断 —— 那是换了角色，不属于这次开荒。

    幕号只能**逐幕前进**：Act 1 的角色物理上不可能直接出现在 Act 9 区域。
    日志窗口里出现 Act 1 → Act 9，说明同一 Client 进程里换了别的角色
    （实测 2026-10-26 PoE1：09:02 旧角色 Act 3 → 13:21 新建角色 Act 1 →
    17:02 又换了 Act 9 的角色，日志里没有任何换角色事件）。

    **回退不截断**：角色可以用传送点回旧幕做支线 / 买装备，这是正常开荒行为，
    重复的旧节点由去重逻辑处理（按 area id，同一地点只保留首次出现）。
    """
    if not splits:
        return splits
    max_act = 0
    allowed: list[dict] = []
    for split in splits:
        act = detect_act(str(split.get("area_id") or ""), game_id).act
        if act is not None:
            if max_act and act > max_act + 1:
                break
            max_act = max(max_act, act)
        allowed.append(split)
    return allowed


def _campaign_run_score(run: list[dict], game_id: str) -> tuple:
    """挑哪一段开荒：**完整通关优先**，其次节点多。

    用户要求的是「从第一幕开始一直跑到剧情结束」的完整记录；
    同一次会话里若出现多次开荒（反复新建角色），取通关的那一段。
    """
    return (log_has_campaign_end(run, game_id), len(run))


def _select_campaign_run(splits: list[dict], game_id: str) -> list[dict]:
    """从一次会话里选出**属于开荒的那一段节点**。

    ``splits`` 此时已去掉藏身处 / 非剧情区。
    处理顺序：按起点切 run → 每段剪掉「换角色」的前进跳跃 → 剪到剧情结束 →
    取最完整的一段。

    **没有起点不等于放弃**：同一次开荒的后续会话（退出游戏后再上线）
    本来就不会再出现第一幕起点，必须保留并在**角色级合并**时接上。
    「整条记录是否从第一幕开始」由 :func:`has_campaign_start` 在合并后判定。
    """
    game = str(game_id or "").strip().lower()
    runs = _split_campaign_runs(splits, game)
    if not runs:
        runs = [list(splits)]
    best: list[dict] = []
    best_score: tuple = ()
    for run in runs:
        cut = _cut_impossible_forward_jump(run, game)
        cut = truncate_at_campaign_end(cut, game)
        score = _campaign_run_score(cut, game)
        if not best or score > best_score:
            best, best_score = cut, score
    return best


def has_campaign_start(splits: list[dict], game_id: str) -> bool:
    """这条记录是否包含**第一幕起点**（PoE1 ``1_1_1`` / PoE2 ``G1_1``）。

    开荒必然从第一幕起点开始。日志被轮转 / 只剩中后段时找不到起点，
    这种记录无法确认是不是一次完整开荒 → 按用户要求放弃。
    """
    start_id = campaign_start_area_id(game_id)
    if not start_id:
        return True
    return any(
        str(split.get("area_id") or "").strip() == start_id for split in splits
    )


def _drop_non_campaign_splits(splits: list[dict], game_id: str) -> list[dict]:
    """丢弃非剧情节点（PoE2 的异界地图 / 精华 / 禁區 / PoE1 移植区 …）。

    * **PoE2**：``G<1..4>_*`` 之外的 area id 一律不是剧情。
    * **PoE1**：剧情区域必然是 ``<幕>_<序号>…`` 形式（``1_1_2`` / ``2_10_9``）；
      其余命名区域是**联盟城镇 / 藏身处 / 兽栏 / 矿井**等非剧情区
      （实测 2026-10 真机日志里有 ``KalguuranSettlersLeague`` 君锋镇、
      ``Menagerie_Hub``、``DeepwaterHub``、``MavenHub`` …）。
      升华试炼 ``Labyrinth_Airlock`` / ``<act>_Labyrinth_*`` 例外保留 ——
      试炼只记进门那一次（折叠由 trial.py 负责）。
      异界地图 ``MapWorlds*`` 交给 :func:`truncate_at_campaign_end`。
    """
    game = str(game_id or "").strip().lower()
    if game not in {"poe1", "poe2"}:
        return splits
    kept: list[dict] = []
    for split in splits:
        area_id = str(split.get("area_id") or "").strip()
        if not area_id:
            # 没有 area id = 无从判定，保留（宁可多留也不误删剧情）
            kept.append(split)
            continue
        if game == "poe2":
            if is_poe2_campaign_area_id(area_id) or is_campaign_over_area_id(
                area_id, "poe2"
            ):
                kept.append(split)
            continue
        if is_poe1_campaign_area_id(area_id) or is_campaign_over_area_id(
            area_id, "poe1"
        ):
            kept.append(split)
    return kept


def _raw_splits(session_dict: dict) -> list[dict]:
    """未过滤/未截断的原始 splits，供锚点存在性检查。"""
    return list(session_dict.get("splits") or [])


def _sanitize_chapters(chapters: list[str] | None) -> list[str]:
    from .chapter_normalize import sort_chapters

    ordered: list[str] = []
    for chapter in chapters or []:
        name = str(chapter or "").strip()
        if not name or name in UNKNOWN_CHAPTER_LABELS:
            continue
        if name not in ordered:
            ordered.append(name)
    return sort_chapters(ordered)


def _chapter_label_from_list(chapters: list[str]) -> str:
    if not chapters:
        return ""
    if len(chapters) == 1:
        return chapters[0]
    return f"{chapters[0]} → {chapters[-1]}"


def _infer_chapters_from_splits(
    splits: list[dict],
    area_registry: AreaRegistry | None,
    area_chapter_map: dict[str, str],
    game_id: str = "",
) -> list[str]:
    """由节点推出章节。

    **area id 是唯一权威**（PoE1 的 Client.txt 完全没有章节行，
    只能靠 ``X_Y`` 的第二位数字判幕；PoE2 靠 ``G<act>_*``）。
    区域名映射表仅作最后兜底。
    """
    from .chapter_normalize import sort_chapters

    chapters: list[str] = []
    for split in splits:
        area_id = str(split.get("area_id") or "").strip()
        chapter = act_chapter_label(area_id, game_id) if area_id else ""
        if not chapter:
            candidates = [
                str(split.get("area_en") or ""),
                str(split.get("area") or ""),
            ]
            if area_registry is not None:
                for name in list(candidates):
                    if name:
                        candidates.append(area_registry.canonical_name(name))
                        candidates.append(area_registry.english_name(name))
                        candidates.append(area_registry.display_name(name))
            for name in candidates:
                if not name:
                    continue
                chapter = area_chapter_map.get(name, "")
                if chapter:
                    break
        if chapter and chapter not in chapters:
            chapters.append(chapter)
    return sort_chapters(chapters)


def _area_lookup_keys(split: dict, area_registry: AreaRegistry | None) -> set[str]:
    keys: set[str] = set()
    for field in ("area", "area_en"):
        raw = str(split.get(field) or "").strip()
        if not raw:
            continue
        keys.add(raw)
        if area_registry is not None:
            keys.add(area_registry.canonical_name(raw))
            keys.add(area_registry.english_name(raw))
            keys.add(area_registry.display_name(raw))
    return {key for key in keys if key}


def infer_route_game_id(
    session_dict: dict,
    *,
    poe2_area_keys: set[str],
    area_registry: AreaRegistry | None,
    default_game_id: str,
) -> str:
    """根据区域名判断路线属于 PoE1 还是 PoE2（混合 Client.txt 按路线拆分）。

    无 PoE2 区域查找表时不可靠，一律沿用本次导入目标游戏，避免把 PoE2 误标成 PoE1。
    """
    default = str(default_game_id or "").strip().lower() or "poe2"
    if not poe2_area_keys:
        return default
    poe2_hits = 0
    poe1_hits = 0
    for split in _filtered_splits(session_dict):
        keys = _area_lookup_keys(split, area_registry)
        if not keys:
            continue
        if keys & poe2_area_keys:
            poe2_hits += 1
        else:
            poe1_hits += 1
    if poe2_hits > 0 and poe2_hits >= poe1_hits:
        return "poe2"
    if poe1_hits > 0:
        return "poe1"
    return default


def _enrich_session_dict(
    session_dict: dict,
    *,
    area_registry: AreaRegistry | None,
    area_chapter_map: dict[str, str],
    poe2_area_keys: set[str],
    default_game_id: str,
) -> dict:
    session = dict(session_dict)
    game = infer_route_game_id(
        session,
        poe2_area_keys=poe2_area_keys,
        area_registry=area_registry,
        default_game_id=default_game_id,
    )
    # 章节以**裁剪后的节点**为准（area id 权威）：日志里的章节行可能包含
    # 已被裁掉的尾巴（例：PoE2 角色先在 Act 4 城镇上线，章节读到「第四章」）。
    chapters = _infer_chapters_from_splits(
        _filtered_splits(session, game), area_registry, area_chapter_map, game
    )
    if not chapters:
        chapters = _sanitize_chapters(session.get("chapters"))
    session["chapters"] = chapters
    label = str(session.get("chapter_label") or "").strip()
    if chapters:
        session["chapter_label"] = _chapter_label_from_list(chapters)
    elif label in UNKNOWN_CHAPTER_LABELS:
        session["chapter_label"] = ""
    session["game_id"] = game
    return session


def _session_reject_reason(session_dict: dict, game_id: str) -> str | None:
    """返回未通过完整开荒筛选的原因；通过则返回 None。"""
    splits = _filtered_splits(session_dict, game_id)
    node_count = len(splits)
    chapters = _sanitize_chapters(session_dict.get("chapters"))
    chapter_label = session_dict.get("chapter_label") or ""

    if node_count < MIN_COMPLETE_NODES:
        return f"节点不足({node_count}<{MIN_COMPLETE_NODES})"

    if not chapters:
        fallback_min = 55 if game_id == "poe1" else 50
        if node_count >= fallback_min:
            return None
        return f"日志无章节行且节点不足({node_count}<{fallback_min})"

    has_early = bool(set(chapters) & EARLY_CHAPTERS) or len(chapters) >= 2
    if not has_early:
        return f"章节跨度不足(chapters={chapters or chapter_label or '无'})"

    if game_id == "poe1":
        if set(chapters) & LATE_CHAPTERS_POE1:
            return None
        if node_count >= 55:
            return None
        return f"未达后期章节且节点不足({node_count}<55)"

    chapter_set = set(chapters)
    if chapter_set & LATE_CHAPTERS_POE2:
        return None
    if chapter_set & MID_CHAPTERS_POE2 and node_count >= 38:
        return None
    if node_count >= 45:
        return None
    return f"未达后期章节且节点不足({node_count}<45)"


def _session_is_complete_campaign(session_dict: dict, game_id: str) -> bool:
    return _session_reject_reason(session_dict, game_id) is None


def _merged_route_to_session_dict(route: dict, *, raw_session_count: int) -> dict:
    return {
        "session_id": (route.get("session_ids") or [0])[0],
        "character": route.get("character") or "未知角色",
        "chapters": _sanitize_chapters(route.get("chapters")),
        "chapter_label": route.get("chapter_label") or "",
        "started_at": route.get("started_at"),
        "ended_at": route.get("last_played_at") or route.get("started_at"),
        "total_seconds": float(route.get("elapsed_seconds", 0) or 0),
        "node_count": int(route.get("node_count", 0) or 0),
        "deaths": int(route.get("deaths", 0) or 0),
        "splits": list(route.get("splits") or []),
        "merged_session_count": raw_session_count,
    }


def _group_and_merge_sessions(session_dicts: list[dict], *, game_id: str = "") -> list[dict]:
    """同一角色的多次 Client 启动片段合并为一条候选路线。"""
    grouped: dict[str, list[dict]] = {}
    for session in session_dicts:
        character = (session.get("character") or "未知角色").strip() or "未知角色"
        grouped.setdefault(character, []).append(session)

    merged: list[dict] = []
    for character, items in grouped.items():
        ordered = sorted(items, key=lambda item: item.get("started_at") or "")
        if len(ordered) == 1:
            single = dict(ordered[0])
            single["merged_session_count"] = 1
            merged.append(single)
            continue
        route = merge_session_dicts(ordered, source="client_txt", game_id=game_id)
        merged.append(_merged_route_to_session_dict(route, raw_session_count=len(ordered)))
    if game_id:
        # 合并后仍然找不到第一幕起点 = 日志已轮转 / 只剩中后段，
        # 无法确认是一次完整开荒 → 放弃（不伪造第一幕起点）。
        merged = [
            item
            for item in merged
            if has_campaign_start(_filtered_splits(item, game_id), game_id)
        ]
    merged.sort(key=lambda item: item.get("ended_at") or item.get("started_at") or "", reverse=True)
    return merged


def sessions_to_reference_routes(
    session_dicts: list[dict],
    *,
    game_id: str,
    max_routes: int = RECENT_ROUTE_LIMIT,
) -> list[ReferenceRoute]:
    # 未通关角色名单（日志窗口无开荒终点锚点）：照常导入现有节点，
    # 名单仅供 UI 提醒「未通关，路线可能不完整」。
    import_game = str(game_id or "").strip().lower() or "poe2"
    unfinished_characters = sorted(
        {
            (session.get("character") or "未知角色").strip() or "未知角色"
            for session in session_dicts
            if str(session.get("game_id") or game_id) == import_game
            and not log_has_campaign_end(_raw_splits(session), import_game)
        },
        key=str.casefold,
    )
    qualified = [
        session
        for session in session_dicts
        # 过滤后只剩「登录 → 城镇 → 终局城镇」这种 1~3 个节点残留，
        # 不成路线（例：金司馬區 → 高地神塔庇護所），不要塞进路线列表。
        if len(_filtered_splits(session, import_game)) >= MIN_ROUTE_SPLITS
    ]
    qualified.sort(key=lambda item: item.get("ended_at") or item.get("started_at") or "", reverse=True)
    if max_routes > 0:
        qualified = qualified[:max_routes]

    # 设置页按游戏导入时传入的 game_id 为准，保证 PoE1/PoE2 路线互不覆盖
    import_game = str(game_id or "").strip().lower() or "poe2"

    routes: list[ReferenceRoute] = []
    for session in qualified:
        character = session.get("character") or "未知角色"
        route_game = import_game
        # Client.txt 原文优先，不用经过 locale 改写的 display
        nodes = [
            RouteNode(
                name=str(
                    split.get("area")
                    or split.get("display")
                    or split.get("area_en")
                    or ""
                ),
                seconds=float(split.get("segment_seconds", 0)),
                area_id=str(split.get("area_id") or ""),
                is_trial_entry=bool(split.get("is_trial_entry")),
            )
            for split in _filtered_splits(session, route_game)
            if split.get("area") or split.get("display") or split.get("area_en")
        ]
        if len(nodes) < 2:
            continue

        truncated_seconds = sum(node.seconds for node in nodes)
        routes.append(
            ReferenceRoute(
                route_id=str(uuid.uuid4()),
                name=_route_name(
                    character,
                    str(session.get("chapter_label") or ""),
                    session.get("started_at"),
                ),
                nodes=nodes,
                created_at=str(session.get("started_at") or ""),
                run_count=0,
                best_seconds=truncated_seconds or None,
                source="client_txt",
                character=character,
                game_id=route_game,
            )
        )
    return routes, unfinished_characters


def _log_session_summary(label: str, session_dict: dict, default_game_id: str) -> None:
    route_game = str(session_dict.get("game_id") or default_game_id)
    splits = _filtered_splits(session_dict, route_game)
    reason = _session_reject_reason(session_dict, route_game)
    test_log.write(
        "IMPORT",
        label,
        character=session_dict.get("character") or "?",
        game_id=route_game,
        nodes=len(splits),
        chapters=session_dict.get("chapters") or [],
        chapter_label=session_dict.get("chapter_label") or "",
        merged_sessions=session_dict.get("merged_session_count", 1),
        started_at=session_dict.get("started_at"),
        ended_at=session_dict.get("ended_at"),
        qualified=reason is None,
        reject_reason=reason or "",
    )


def _log_import_pass(
    *,
    client_path: Path,
    game_id: str,
    tail_bytes: int,
    raw_sessions: int,
    merged_sessions: list[dict],
    complete_count: int,
    max_routes: int,
) -> None:
    test_log.write(
        "IMPORT",
        "扫描 Client.txt 片段",
        path=str(client_path),
        game_id=game_id,
        tail_mb=round(tail_bytes / (1024 * 1024), 1),
        raw_sessions=raw_sessions,
        merged_candidates=len(merged_sessions),
        complete_routes=complete_count,
        target_routes=max_routes,
    )
    for index, session in enumerate(merged_sessions[:12]):
        _log_session_summary(f"候选#{index + 1}", session, game_id)


def import_routes_from_client(
    client_path: Path,
    *,
    area_registry: AreaRegistry,
    locale: str = "zh_tw",
    game_id: str = "poe2",
    min_nodes: int = 5,
    max_routes: int = RECENT_ROUTE_LIMIT,
) -> tuple[list[ReferenceRoute], int, int]:
    test_log.write(
        "IMPORT",
        "开始导入 Client.txt",
        path=str(client_path),
        game_id=game_id,
        locale=locale,
        min_nodes=min_nodes,
        max_routes=max_routes,
    )

    detected_locale = detect_client_log_locale(client_path)
    effective_locale = detected_locale
    test_log.write(
        "IMPORT",
        "日志语言",
        configured=locale,
        detected=detected_locale,
        effective=effective_locale,
    )

    area_chapter_map = _expand_area_chapter_map(_load_area_chapter_map(), area_registry)
    poe2_area_keys = set(area_chapter_map.keys())
    sessions: list = []
    merged_session_dicts: list[dict] = []
    session_count = 0

    for tail_bytes in TAIL_READ_SIZES:
        sessions = analyze_client_log(
            client_path,
            min_nodes=min_nodes,
            locale=effective_locale,
            game_id=game_id,
            area_registry=area_registry,
            max_sessions=TAIL_SESSION_SCAN_LIMIT,
            tail_bytes=tail_bytes,
        )
        session_count = len(sessions)
        session_dicts = [session.to_dict(effective_locale, area_registry) for session in sessions]
        merged_session_dicts = [
            _enrich_session_dict(
                item,
                area_registry=area_registry,
                area_chapter_map=area_chapter_map,
                poe2_area_keys=poe2_area_keys,
                default_game_id=game_id,
            )
            for item in _group_and_merge_sessions(session_dicts, game_id=game_id)
        ]
        complete_count = sum(
            1
            for item in merged_session_dicts
            if _session_is_complete_campaign(item, str(item.get("game_id") or game_id))
        )
        _log_import_pass(
            client_path=client_path,
            game_id=game_id,
            tail_bytes=tail_bytes,
            raw_sessions=session_count,
            merged_sessions=merged_session_dicts,
            complete_count=complete_count,
            max_routes=max_routes,
        )
        if complete_count >= max_routes:
            break

    if not sessions:
        test_log.write("IMPORT", "未找到有效日志片段", path=str(client_path))
        return [], session_count, 0, []

    routes, unfinished = sessions_to_reference_routes(
        merged_session_dicts, game_id=game_id, max_routes=max_routes
    )
    test_log.write(
        "IMPORT",
        "导入完成",
        raw_sessions=session_count,
        merged_candidates=len(merged_session_dicts),
        imported_routes=len(routes),
        route_names=[route.name for route in routes],
        unfinished_characters=unfinished,
    )
    return routes, session_count, len(merged_session_dicts), unfinished
