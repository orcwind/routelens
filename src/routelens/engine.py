from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from .area_registry import AreaRegistry
from .companion_config import CompanionConfig
from .events import EventBus, EventType, GameEvent
from .games.registry import get_game
from .log_watcher import LogWatcher
from . import test_log
from .hideout_filter import is_hideout_area

from .area_filter import filter_hideout_nodes
from .client_import import import_routes_from_client
from .config import clear_client_path_for_other_games
from .game_detect import detect_game_from_log, resolve_import_game
from .models import ActiveRun, ReferenceRoute, RunNode, RunResult
from .route_library import REPEAT_NAME_MIN_GAP
from .store import RouteLensStore

StateCallback = Callable[[ActiveRun | None], None]

# 向前匹配窗口：超过这个距离的同名区域不认（PoE1 各 Act 有同名区域，防止误跳整幕）
MAX_FORWARD_MATCH = 15

# 连续 N 个「不在参考路线里」的区域 → 判定参考路线与实际路径已分叉
# （跨幕 / 玩家走的不是同一条路），之后按实际进图记录
FREE_RECORD_CONFIRM = 2


class RunEngine:
    """监听 Client.txt，管理一次 Run 的计时与节点记录。"""

    def __init__(self, config: CompanionConfig) -> None:
        self.config = config
        self.game = get_game(config.game)
        self.store = RouteLensStore(config.resolved_data_dir)
        for name, before, after in self.store.repair_client_route_games():
            test_log.write(
                "MIGRATE",
                "修正路线游戏归属",
                route=name,
                before=before,
                after=after,
            )
        self.area_registry = AreaRegistry(
            config.resolved_area_names_path,
            self.game,
            config.locale,
        )
        self.event_bus = EventBus()
        self.log_watcher: LogWatcher | None = None
        self.active_run: ActiveRun | None = None
        self._timer_started_at: datetime | None = None
        self._last_area = ""
        self._state_callback: StateCallback | None = None
        # 参考路线里匹配不上、等待确认是否分叉的区域（(显示名, 进入时刻)）
        self._pending_areas: list[tuple[str, datetime]] = []
        self.event_bus.subscribe(EventType.AREA_ENTERED, self._on_area_entered)

    def set_state_callback(self, callback: StateCallback | None) -> None:
        self._state_callback = callback

    @property
    def has_active_run(self) -> bool:
        return self.active_run is not None and self.active_run.is_active

    @property
    def client_path(self) -> Path | None:
        return self.config.resolved_client_path

    @property
    def timer_running(self) -> bool:
        return self._timer_started_at is not None and not (
            self.active_run and self.active_run.is_paused
        )

    def elapsed_seconds(self) -> float:
        if self.active_run is None:
            return 0.0
        if self.active_run.is_paused:
            return self.active_run.elapsed_seconds
        if self._timer_started_at is None:
            return self.active_run.elapsed_seconds
        delta = (datetime.now() - self._timer_started_at).total_seconds()
        return self.active_run.elapsed_seconds + max(0.0, delta)

    def start_watching(self) -> None:
        client_path = self.client_path
        if client_path is None or not client_path.is_file():
            raise FileNotFoundError("未找到 Client.txt，请在设置中选择路径。")
        if self.log_watcher and self.log_watcher.running:
            return
        self.log_watcher = LogWatcher(
            log_path=client_path,
            event_bus=self.event_bus,
            poll_interval=self.config.poll_interval_seconds,
            game=self.game,
        )
        self.log_watcher.start()

    def stop_watching(self) -> None:
        if self.log_watcher:
            self.log_watcher.stop()
            self.log_watcher = None

    def new_run(self, reference: ReferenceRoute | None) -> ActiveRun:
        self._sync_elapsed()
        now = datetime.now().isoformat(timespec="seconds")
        nodes: list[RunNode] = []
        if reference:
            nodes = [
                RunNode(name=node.name, completed=False, area_id=node.area_id)
                for node in filter_hideout_nodes(reference.nodes)
            ]
        run = ActiveRun(
            run_id=str(uuid.uuid4()),
            reference_route_id=reference.route_id if reference else None,
            reference_route_name=reference.name if reference else "",
            nodes=nodes,
            started_at=now,
        )
        self.active_run = run
        self._timer_started_at = None
        self._last_area = ""
        self._pending_areas = []
        self._persist()
        self._emit_state()
        return run

    def resume_run(self, run: ActiveRun) -> ActiveRun:
        self.active_run = run
        self._timer_started_at = datetime.now() if not run.is_paused else None
        self._last_area = run.current_area
        self._pending_areas = []
        self._persist()
        self._emit_state()
        return run

    def _enter_waiting_to_start(self, run: ActiveRun) -> ActiveRun:
        """进入 Run 时一律暂停，需按 0 才开始计时。"""
        # 若内存里仍是同一次 Run，先把已走的表时间落盘，再进入等待
        if self.active_run is not None and self.active_run.run_id == run.run_id:
            self._sync_elapsed()
            run = self.active_run
        run.is_paused = True
        self.active_run = run
        self._timer_started_at = None
        self._last_area = run.current_area
        self._pending_areas = []
        self._persist()
        self._emit_state()
        return run

    def load_saved_run(self) -> ActiveRun | None:
        return self.store.load_active_run()

    def finish_run(self) -> RunResult | None:
        if not self.has_active_run:
            return None
        self._sync_elapsed()
        assert self.active_run is not None
        # 收尾最后一个节点（参考最后一个 / 自由记录最后一个），否则它永远没有时间
        self._close_current_node(self.current_segment_seconds())
        run = self.active_run
        run.is_active = False
        result = RunResult(
            run_id=run.run_id,
            route_id=run.reference_route_id,
            route_name=run.reference_route_name or "自由路线",
            total_seconds=self.elapsed_seconds(),
            finished_at=datetime.now().isoformat(timespec="seconds"),
            nodes=[
                RunNode(
                    name=node.name,
                    seconds=node.seconds,
                    completed=node.completed,
                    area_id=node.area_id,
                )
                for node in run.nodes
            ],
        )
        self.store.save_result(result)
        if run.reference_route_id:
            self.store.update_route_stats(run.reference_route_id, result.total_seconds)
        self.store.clear_active_run()
        self.active_run = None
        self._timer_started_at = None
        self._last_area = ""
        self._emit_state()
        return result

    def abandon_run(self) -> None:
        self._sync_elapsed()
        if self.active_run:
            self.store.clear_active_run()
        self.active_run = None
        self._timer_started_at = None
        self._last_area = ""
        self._emit_state()

    def save_now(self) -> None:
        self._sync_elapsed()
        if self.active_run is not None:
            self.active_run.is_paused = True
        self._timer_started_at = None
        self._persist()

    def save_run_as_reference(self, name: str) -> ReferenceRoute:
        nodes = self._completed_nodes()
        return self.store.create_route_from_run(name, nodes)

    def save_result_as_reference(self, result: RunResult, name: str) -> ReferenceRoute:
        nodes = [
            RunNode(
                name=node.name,
                seconds=node.seconds,
                completed=True,
                area_id=node.area_id,
            )
            for node in result.nodes
            if node.completed and node.name
        ]
        return self.store.create_route_from_run(name, nodes)

    def reload_game_profile(self) -> None:
        self.game = get_game(self.config.game)
        self.area_registry = AreaRegistry(
            self.config.resolved_area_names_path,
            self.game,
            self.config.locale,
        )

    def import_from_client_txt(
        self,
        *,
        min_nodes: int = 5,
        client_path: Path | None = None,
        game_id: str | None = None,
    ) -> dict:
        from .config import load_routelens_config, save_routelens_setup

        target_path = client_path or self.client_path
        target_game = game_id or self.config.game
        if target_path is None or not Path(target_path).is_file():
            raise FileNotFoundError("未找到 Client.txt，请在设置中选择路径。")
        target_path = Path(target_path)

        # 以日志内容为准：选错游戏行 / 设置里游戏不对时，不能把整批路线标错。
        detected_game = detect_game_from_log(target_path)
        resolved_game = resolve_import_game(target_path, target_game)
        if resolved_game:
            configured = str(target_game or "").strip().lower()
            if detected_game and detected_game != configured:
                test_log.write(
                    "IMPORT",
                    "日志内容与设置游戏不一致，按日志归类",
                    setting=configured or "unknown",
                    detected=detected_game,
                    path=str(target_path),
                )
            target_game = resolved_game
            clear_client_path_for_other_games(str(target_path.resolve()), resolved_game)

        save_routelens_setup(str(target_path.resolve()), target_game)
        self.config = load_routelens_config()
        self.reload_game_profile()

        routes, session_count, merged_count, unfinished = import_routes_from_client(
            target_path,
            area_registry=self.area_registry,
            locale=self.config.locale,
            game_id=target_game,
            min_nodes=min_nodes,
        )
        route_count = self.store.replace_client_routes(routes, game_id=target_game)
        from .log_locale import detect_client_log_locale

        return {
            "session_count": session_count,
            "merged_candidates": merged_count,
            "route_count": route_count,
            "unfinished_characters": unfinished,
            "recent_only": True,
            "detected_locale": detect_client_log_locale(target_path),
            "game_id": target_game,
        }

    def get_saved_run_for_route(self, route_id: str) -> ActiveRun | None:
        saved = self.store.load_active_run()
        if saved is None or saved.reference_route_id != route_id:
            return None
        return saved

    def begin_new_run(self, reference: ReferenceRoute | None) -> ActiveRun:
        self.store.clear_active_run()
        run = self.new_run(reference)
        self._enter_waiting_to_start(run)
        self.start_watching()
        return run

    def begin_continue_run(self, run: ActiveRun) -> ActiveRun:
        # 不论上次是跑还是停，续跑一律暂停，等按 0 再计时
        self._enter_waiting_to_start(run)
        self.start_watching()
        return run

    def start_or_split(self) -> None:
        """小键盘 0：开始计时 / 切区。"""
        if not self.has_active_run:
            return
        assert self.active_run is not None
        if self.active_run.is_paused:
            self.resume_timer()
            return
        if self._timer_started_at is None:
            self._timer_started_at = datetime.now()
            self._persist()
            self._emit_state()
            return
        self._manual_split()

    def reset_run(self) -> None:
        """小键盘 5：重置计时与进度（先备份，可用 restore_reset_backup 找回）。"""
        if not self.active_run:
            return
        self._sync_elapsed()
        assert self.active_run is not None
        self.store.save_reset_backup(self.active_run)

        reference = None
        if self.active_run.reference_route_id:
            reference = self.store.get_route(self.active_run.reference_route_id)
        route_id = self.active_run.reference_route_id
        route_name = self.active_run.reference_route_name
        now = datetime.now().isoformat(timespec="seconds")
        nodes: list[RunNode] = []
        if reference:
            nodes = [
                RunNode(name=node.name, completed=False)
                for node in filter_hideout_nodes(reference.nodes)
            ]
        self.active_run = ActiveRun(
            run_id=str(uuid.uuid4()),
            reference_route_id=route_id,
            reference_route_name=route_name,
            nodes=nodes,
            started_at=now,
            is_paused=True,
        )
        self._timer_started_at = None
        self._last_area = ""
        self._pending_areas = []
        self._persist()
        self._emit_state()

    def has_reset_backup(self) -> bool:
        return self.store.has_reset_backup()

    def restore_reset_backup(self) -> ActiveRun | None:
        """恢复最近一次重置前的进度。"""
        backup = self.store.load_reset_backup()
        if backup is None:
            return None
        self._enter_waiting_to_start(backup)
        return backup

    def undo_split(self) -> None:
        """小键盘 8：撤销上一段。"""
        if not self.has_active_run:
            return
        assert self.active_run is not None
        self._sync_elapsed()
        run = self.active_run
        if not run.nodes:
            return

        target = run.current_index - 1
        while target >= 0 and not run.nodes[target].completed:
            target -= 1
        if target < 0:
            return

        node = run.nodes[target]
        node.completed = False
        node.skipped = False
        node.seconds = None
        run.current_index = target
        run.current_area = ""
        self._last_area = ""
        self._persist()
        self._emit_state()

    def skip_split(self) -> None:
        """小键盘 2：跳过当前节点。"""
        if not self.has_active_run:
            return
        assert self.active_run is not None
        if self._timer_started_at is None:
            self._timer_started_at = datetime.now()
        self._sync_elapsed()
        run = self.active_run
        if run.current_index >= len(run.nodes):
            return
        node = run.nodes[run.current_index]
        node.completed = True
        node.skipped = True
        node.seconds = None
        run.current_index = self._next_uncompleted_index(run.current_index + 1)
        self._persist()
        self._emit_state()

    def pause_toggle(self) -> None:
        """小键盘 3：暂停 / 继续。"""
        if not self.has_active_run:
            return
        assert self.active_run is not None
        if self.active_run.is_paused:
            self.resume_timer()
        else:
            self.pause_timer()

    def pause_timer(self) -> None:
        if not self.has_active_run or self.active_run.is_paused:
            return
        self._sync_elapsed()
        assert self.active_run is not None
        self.active_run.is_paused = True
        self._timer_started_at = None
        self._persist()
        self._emit_state()

    def resume_timer(self) -> None:
        if not self.has_active_run or not self.active_run.is_paused:
            return
        assert self.active_run is not None
        self.active_run.is_paused = False
        self._timer_started_at = datetime.now()
        self._persist()
        self._emit_state()

    def simulate_area(self, area: str, *, write_client: bool = True) -> None:
        """模拟进图：写入 Client.txt 并立即同步处理。"""
        test_log.write(
            "SIM",
            "模拟进图",
            area=area,
            write_client=write_client,
            current_index=self.active_run.current_index if self.active_run else None,
            expected_next=self.next_expected_area(),
        )
        if write_client:
            client_path = self.client_path
            if client_path is None or not client_path.is_file():
                raise FileNotFoundError("未找到 Client.txt")
            from .client_txt_simulator import append_scene_change

            append_scene_change(client_path, area)
        self._last_area = ""
        self._inject_area(area)
        if write_client and self.log_watcher:
            self.log_watcher.seek_to_end()

    def _inject_area(self, area: str) -> None:
        event = GameEvent(
            type=EventType.AREA_ENTERED,
            timestamp=datetime.now(),
            area=area,
            raw_line=f"[SIMULATE] {area}",
        )
        self._on_area_entered(event)

    def next_expected_area(self) -> str:
        if not self.active_run:
            return ""
        if self.active_run.current_index < len(self.active_run.nodes):
            return self.active_run.nodes[self.active_run.current_index].name
        return ""

    def get_reference_route(self) -> ReferenceRoute | None:
        if not self.active_run or not self.active_run.reference_route_id:
            return None
        return self.store.get_route(self.active_run.reference_route_id)

    def reference_seconds_at(self, index: int) -> float | None:
        route = self.get_reference_route()
        if route is None or index < 0:
            return None
        # 索引必须与 active_run.nodes 对齐：建 Run 时参考节点已过滤掉藏身处
        ref_nodes = filter_hideout_nodes(route.nodes)
        if index >= len(ref_nodes):
            # 超出参考范围的节点是实际跑出来的自由节点，没有参考时间
            return None
        return ref_nodes[index].seconds

    def comparison_delta_seconds(self) -> float | None:
        """相对参考的累计超前/落后（LiveSplit Ahead/Behind）。

        当前总用时 − 参考路线前缀累计（含当前节点参考段）。
        负值=领先，正值=落后。无参考或尚未开始计时时返回 None。
        """
        if not self.active_run or not self.active_run.reference_route_id:
            return None
        if self._timer_started_at is None and self.active_run.elapsed_seconds <= 0:
            return None
        route = self.get_reference_route()
        if route is None or not route.nodes:
            return None
        ref_nodes = filter_hideout_nodes(route.nodes)
        if not ref_nodes:
            return None
        index = max(0, min(self.active_run.current_index, len(ref_nodes) - 1))
        ref_sum = 0.0
        found = False
        for node in ref_nodes[: index + 1]:
            if node.seconds is None:
                continue
            ref_sum += float(node.seconds)
            found = True
        if not found:
            return None
        # 参考节点已跑完：之后的节点属于实际自由记录，没有参考可比，差值必须冻结在
        # 「跑完参考那一刻」，否则总差值会随着继续游玩一路涨。
        if self.active_run.current_index >= len(ref_nodes):
            actual = sum(
                float(node.seconds or 0.0)
                for node in self.active_run.nodes[: len(ref_nodes)]
                if node.completed and not node.skipped
            )
            return actual - ref_sum
        return self.elapsed_seconds() - ref_sum

    def current_segment_seconds(self) -> float:
        return self._segment_seconds(datetime.now())

    def display_name(self, area: str) -> str:
        """节点名即 Client.txt 原文，不做词典翻译。"""
        return area or ""

    def areas_match(self, area: str, expected: str) -> bool:
        return self._areas_match(area, expected)

    def _completed_nodes(self) -> list[RunNode]:
        if not self.active_run:
            return []
        return [node for node in self.active_run.nodes if node.completed and node.name]

    def _on_area_entered(self, event: GameEvent) -> None:
        if not self.has_active_run:
            return
        area = event.area
        if not area or area == self._last_area:
            return
        if is_hideout_area(area):
            test_log.write("RUN", "忽略藏身处", area=area)
            return
        if self._timer_started_at is None and not self.active_run.is_paused:
            self._timer_started_at = datetime.now()
        self._sync_elapsed()
        assert self.active_run is not None
        segment_seconds = self._segment_seconds(event.timestamp)
        if not self._record_node(area, segment_seconds, event.timestamp, event.area_id):
            return
        self._last_area = area
        self._sync_current_area_display()
        self._persist()
        self._emit_state()

    def _sync_current_area_display(self) -> None:
        assert self.active_run is not None
        if self.active_run.current_index < len(self.active_run.nodes):
            self.active_run.current_area = self.active_run.nodes[self.active_run.current_index].name
        else:
            self.active_run.current_area = ""

    def _segment_seconds(self, _timestamp: datetime) -> float:
        assert self.active_run is not None
        completed_sum = sum(
            node.seconds or 0.0 for node in self.active_run.nodes if node.completed
        )
        return max(0.0, self.elapsed_seconds() - completed_sum)

    def _record_node(
        self,
        area: str,
        segment_seconds: float,
        timestamp: datetime | None = None,
        area_id: str = "",
    ) -> bool:
        assert self.active_run is not None
        display = self.display_name(area) or area
        has_reference = bool(self.active_run.reference_route_id)

        if self.active_run.nodes:
            match_index = self._find_forward_match(area)
            if match_index is None:
                # 参考路线已跑完：关闭最后一个参考节点，之后按实际进图自由记录。
                # （参考只提供已跑节点的时间基准，节点名由实际进图生成）
                if self._can_free_record() and not self._is_recent_repeat(area):
                    self._close_current_node(segment_seconds)
                    return self._append_free_node(area, display, area_id)
                if self._track_divergence(area, display, segment_seconds, timestamp):
                    return True
                if has_reference:
                    test_log.write(
                        "RUN",
                        "忽略进图（回退或未知道路）",
                        area=area,
                        display=display,
                        current_index=self.active_run.current_index,
                        timing=self.next_expected_area(),
                    )
                return False

            if match_index == self.active_run.current_index:
                self._pending_areas = []
                test_log.write(
                    "RUN",
                    "忽略进图（重复当前区）",
                    area=area,
                    display=display,
                    index=match_index,
                )
                return False

            if match_index > self.active_run.current_index:
                self._pending_areas = []
                closed_index = self.active_run.current_index
                active = self.active_run.nodes[closed_index]
                if not active.completed:
                    active.seconds = segment_seconds
                    active.completed = True
                    active.skipped = False
                for index in range(closed_index + 1, match_index):
                    skip_node = self.active_run.nodes[index]
                    if not skip_node.completed:
                        skip_node.completed = True
                        skip_node.skipped = True
                        skip_node.seconds = None
                self.active_run.current_index = match_index
                # 记录实际到达区域的 area id（幕归属权威来源）
                if area_id:
                    self.active_run.nodes[match_index].area_id = area_id
                test_log.write(
                    "RUN",
                    "前进跳段",
                    area=area,
                    display=display,
                    closed_index=closed_index,
                    arrived_index=match_index,
                    seconds=round(segment_seconds, 2),
                    next_index=self.active_run.current_index,
                )
                return True

            return False

        return self._append_free_node(area, display, area_id)

    def _track_divergence(
        self,
        area: str,
        display: str,
        segment_seconds: float,
        timestamp: datetime | None,
    ) -> bool:
        """参考路线与实际路径分叉时，按实际进图继续记录。

        单次「进图不在参考里」可能只是回城 / 折返（随后会回到参考路径），所以先挂起；
        连续 FREE_RECORD_CONFIRM 个都不在参考里 = 参考已断（跨幕 / 走了别的路），
        此时作废剩余参考节点，把实际经过的区域补成新节点继续计时。
        """
        assert self.active_run is not None
        now = timestamp or datetime.now()
        if self._is_recent_repeat(area):
            # 回城 / 死亡折返：不记录，也不累积「分叉」证据
            self._pending_areas = []
            return False
        self._pending_areas.append((display, now))
        if len(self._pending_areas) < FREE_RECORD_CONFIRM:
            return False

        pending = self._pending_areas
        self._pending_areas = []
        # 当前参考节点收尾时间 = 进入第一个挂起区域之前
        base = now - timedelta(seconds=max(0.0, segment_seconds))
        self._close_current_node(max(0.0, (pending[0][1] - base).total_seconds()))
        # 剩余参考节点已经不可能再跑：标记跳过，避免继续阻塞记录
        for node in self.active_run.nodes[self.active_run.current_index + 1 :]:
            if not node.completed:
                node.completed = True
                node.skipped = True
                node.seconds = None
        for index in range(len(pending) - 1):
            name, arrived = pending[index]
            following = pending[index + 1][1]
            self.active_run.nodes.append(
                RunNode(
                    name=name,
                    seconds=max(0.0, (following - arrived).total_seconds()),
                    completed=True,
                )
            )
        last_name, _last_arrived = pending[-1]
        self.active_run.nodes.append(RunNode(name=last_name, completed=False))
        self.active_run.current_index = len(self.active_run.nodes) - 1
        test_log.write(
            "RUN",
            "参考路线分叉，转为实际记录",
            areas=[name for name, _ in pending],
            index=self.active_run.current_index,
        )
        return True

    def _can_free_record(self) -> bool:
        """当前节点是否已是参考路线的最后一个节点（之后按实际进图自由记录）。"""
        if not self.active_run:
            return False
        nodes = self.active_run.nodes
        if not nodes:
            return True
        return self._next_uncompleted_index(self.active_run.current_index + 1) >= len(nodes)

    def _close_current_node(self, segment_seconds: float) -> None:
        """把当前节点收尾（节点时间 = 该区域停留时长）。"""
        if not self.active_run:
            return
        index = self.active_run.current_index
        if not 0 <= index < len(self.active_run.nodes):
            return
        node = self.active_run.nodes[index]
        if node.completed:
            return
        node.seconds = segment_seconds
        node.completed = True
        node.skipped = False

    def _append_free_node(self, area: str, display: str, area_id: str = "") -> bool:
        """把实际进入的区域追加为当前节点，并开始为它计时。"""
        assert self.active_run is not None
        self.active_run.nodes.append(
            RunNode(name=display, completed=False, area_id=area_id)
        )
        self.active_run.current_index = len(self.active_run.nodes) - 1
        test_log.write(
            "RUN",
            "参考已跑完，记录新节点",
            area=area,
            display=display,
            index=self.active_run.current_index,
        )
        return True

    def _is_recent_repeat(self, area: str) -> bool:
        """该区域是否刚跑过（回城 / 死亡折返 / 反复进出），避免污染自由节点。"""
        if not self.active_run:
            return False
        recent = self.active_run.nodes[-REPEAT_NAME_MIN_GAP:]
        return any(self._areas_match(area, node.name) for node in recent)

    def _manual_split(self) -> None:
        assert self.active_run is not None
        self._sync_elapsed()
        segment_seconds = self._segment_seconds(datetime.now())
        if self.active_run.current_index < len(self.active_run.nodes):
            node = self.active_run.nodes[self.active_run.current_index]
            if not node.completed:
                node.seconds = segment_seconds
                node.completed = True
                node.skipped = False
                self.active_run.current_index = self._next_uncompleted_index(self.active_run.current_index + 1)
                self._persist()
                self._emit_state()

    def _find_forward_match(self, area: str) -> int | None:
        """仅在当前节点之后查找匹配（只认向前推进）。

        路线里同名区域出现多次时（PoE1 的 Act 6–10 复用 Act 1–5 区域名），
        只在一定窗口内匹配：否则 Act 1 死亡回城会命中 Act 6 的同名节点，
        把中间几十个节点全部标成「跳过」。
        名字唯一的区域保持原有行为（允许远距离跳段）。
        """
        assert self.active_run is not None
        nodes = self.active_run.nodes
        start = max(0, self.active_run.current_index)
        occurrences = sum(1 for node in nodes if self._areas_match(area, node.name))
        limit = len(nodes) if occurrences <= 1 else min(len(nodes), start + MAX_FORWARD_MATCH)
        for index in range(start, limit):
            node = nodes[index]
            if node.completed and not node.skipped:
                continue
            if self._areas_match(area, node.name):
                return index
        for index in range(limit, len(nodes)):
            node = nodes[index]
            if node.completed and not node.skipped:
                continue
            if self._areas_match(area, node.name):
                test_log.write(
                    "RUN",
                    "忽略进图（匹配点超出识别窗口）",
                    area=area,
                    current_index=start,
                    matched_index=index,
                    window=MAX_FORWARD_MATCH,
                )
                break
        return None

    def _next_uncompleted_index(self, start: int = 0) -> int:
        assert self.active_run is not None
        for index in range(start, len(self.active_run.nodes)):
            if not self.active_run.nodes[index].completed:
                return index
        return len(self.active_run.nodes)

    def _areas_match(self, area: str, expected: str) -> bool:
        if not area or not expected:
            return False
        if area == expected:
            return True
        return self._canonical(area) == self._canonical(expected)

    def _canonical(self, area: str) -> str:
        return self.area_registry.canonical_name(area)

    def _sync_elapsed(self) -> None:
        if self.active_run is None or self._timer_started_at is None or self.active_run.is_paused:
            return
        delta = (datetime.now() - self._timer_started_at).total_seconds()
        self.active_run.elapsed_seconds += max(0.0, delta)
        self._timer_started_at = datetime.now()

    def _persist(self) -> None:
        if self.active_run and self.active_run.is_active:
            self.store.save_active_run(self.active_run)

    def _emit_state(self) -> None:
        if self._state_callback:
            self._state_callback(self.active_run)
