from __future__ import annotations

import uuid
from datetime import datetime
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
from .area_registry import known_area_name
from .campaign_start import (
    campaign_start_area_id,
    campaign_start_name,
    resolve_area_name_from_log,
)
from .client_import import import_routes_from_client
from .config import clear_client_path_for_other_games
from .game_detect import detect_game_from_log, resolve_import_game
from .models import ActiveRun, ReferenceRoute, RunNode, RunResult
from .route_library import REPEAT_NAME_MIN_GAP
from .store import RouteLensStore
from .trial import detect_trial, trial_body_id, trial_node_name

StateCallback = Callable[[ActiveRun | None], None]

# 向前匹配窗口：超过这个距离的同名区域不认（PoE1 各 Act 有同名区域，防止误跳整幕）
# 名字在整个路线里唯一时不受此限制；窗口外只认 area id 精确匹配。
MAX_FORWARD_MATCH = 15


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
        # 当前进行中的试炼（trial_id, 进门节点的 index）；离开试炼区域后清空
        self._active_trial: tuple[str, int] | None = None
        # 刚进入试炼、节点尚未建好时的标记（建好后补 index）
        self._pending_trial_entry: str | None = None
        # 预置的第一幕起点是否已被玩家真正进入过（未被认领的预置节点不记时间）
        self._seed_claimed = False
        self.event_bus.subscribe(EventType.AREA_ENTERED, self._on_area_entered)
        self.event_bus.subscribe(EventType.CAMPAIGN_END, self._on_campaign_end)

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
        has_reference_nodes = False
        if reference:
            nodes = [
                RunNode(name=node.name, completed=False, area_id=node.area_id)
                for node in filter_hideout_nodes(reference.nodes)
            ]
            has_reference_nodes = bool(nodes)
        # 本次运行的游戏归属：路线自带的优先，其次才用设置里的当前游戏。
        # 设置默认 poe2；跑 PoE1 路线时若按设置判，10 幕会被判成 4 幕。
        run_game = str(
            (getattr(reference, "game_id", "") if reference else "") or self.config.game or ""
        ).strip().lower()
        if not reference:
            # 自由路线（空白路线）：开荒必然从第一幕开始，第一幕起点是**固定**的。
            # 预置 node 0，玩家一进图就能对上；否则首个区域永远缺失。
            # 注意：预置的种子节点**不算**参考节点 → 仍是新建路线模式。
            nodes = self._seed_campaign_start_nodes(run_game)
        run = ActiveRun(
            run_id=str(uuid.uuid4()),
            reference_route_id=reference.route_id if reference else None,
            reference_route_name=reference.name if reference else "",
            nodes=nodes,
            started_at=now,
            game_id=run_game,
            # 参考路线模式 = **本次运行有参考节点**。
            # 空白路线也带 route_id（标记来源），但它没有参考节点 → 新建路线模式。
            is_reference_mode=has_reference_nodes,
        )
        self.active_run = run
        self._timer_started_at = None
        self._last_area = ""
        self._seed_claimed = False
        self._persist()
        self._emit_state()
        return run

    def _seed_campaign_start_nodes(self, game_id: str = "") -> list[RunNode]:
        """新建（自由）路线：预置第一幕固定起点为 node 0。

        开荒必然从第一幕开始，所以起点 area id 是常量（见 campaign_start.py）。
        预置后：
        - 玩家还没进图就有 node 0（极简模式能立刻显示计时）
        - 玩家进第一幕起点时按 area id 匹配到 node 0，不会多出一行
        """
        area_id = campaign_start_area_id(game_id or self._run_game_id())
        if not area_id:
            return []
        # 区域名随客户端语言变化：日志原文优先，取不到才用内置译名
        name = (
            known_area_name(area_id)
            or resolve_area_name_from_log(self.client_path, area_id)
            or campaign_start_name(area_id, self.config.locale)
        )
        return [RunNode(name=name, completed=False, area_id=area_id)]

    def resume_run(self, run: ActiveRun) -> ActiveRun:
        self.active_run = run
        self._timer_started_at = datetime.now() if not run.is_paused else None
        self._last_area = run.current_area
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
        self._persist()
        self._emit_state()
        return run

    def load_saved_run(self) -> ActiveRun | None:
        run = self.store.load_active_run()
        if run is not None:
            self._repair_skipped_with_time(run)
        return run

    @staticmethod
    def _repair_skipped_with_time(run: ActiveRun) -> None:
        """修复违反不变量的历史数据：``skipped`` 却带真实用时的节点。

        真机事故 2026-10-28：跳段把玩家**真跑过**的 24 个节点标成 skipped，
        但保留了它们的 seconds。统计时 skipped 节点被排除 → 28.3 分钟凭空消失
        （总时间 1:06:37，幕行只显示 38 分钟）。

        判据（``RunNode`` 的唯一不变量）：``seconds is not None`` ⇔ 本次到过。
        所以「有时间却标成跳过」= 事实被写坏了 → 按「到过」恢复。

        ``RunNode.from_dict`` 也会做同样的迁移（存档读取时）；
        这里是幂等自愈，覆盖其它入口构造的 run。
        """
        changed = 0
        for node in run.nodes:
            if node.skipped and node.seconds is not None and node.seconds > 0:
                node.skipped = False
                node.completed = True
                changed += 1
        if changed:
            test_log.write(
                "MIGRATE",
                "修复被误标跳过的节点",
                count=changed,
            )

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
        """把一次运行的结果存成新路线。

        只收**本次真正到过**的节点（``seconds is not None``）。
        跳过的 / 没跑到的参考节点不进新路线 —— 否则新路线会带上一堆
        「玩家从没去过、用时 0」的节点。
        """
        nodes = [
            RunNode(
                name=node.name,
                seconds=node.seconds,
                completed=True,
                area_id=node.area_id,
            )
            for node in result.nodes
            if node.seconds is not None and node.name
        ]
        return self.store.create_route_from_run(name, nodes)

    def reload_game_profile(self) -> None:
        self.game = get_game(self.config.game)
        self.area_registry = AreaRegistry(
            self.config.resolved_area_names_path,
            self.game,
            self.config.locale,
        )

    def _run_game_id(self) -> str:
        """本次运行的游戏：运行状态里记的优先，其次设置里的当前游戏。

        运行状态里的 game_id 由 `new_run` 按所选路线写入；旧存档没有该字段时
        退回 config.game（与历史行为一致）。
        """
        if self.active_run is not None:
            recorded = str(self.active_run.game_id or "").strip().lower()
            if recorded in ("poe1", "poe2"):
                return recorded
        return str(self.config.game or "").strip().lower()

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
        else:
            # 自由路线重置：同样回到第一幕固定起点
            nodes = self._seed_campaign_start_nodes()
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
        self._seed_claimed = False
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
        node.mark_skipped()
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

    def _inject_area_with_id(self, area: str, area_id: str) -> None:
        """模拟进图并带 area id（幕归属权威来源，同名不同实例要能区分）。"""
        event = GameEvent(
            type=EventType.AREA_ENTERED,
            timestamp=datetime.now(),
            area=area,
            area_id=area_id,
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
                if node.visited
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
        """本次运行**真正到过**的节点（用于「存为路线」）。

        按 RunNode 不变量判定：``seconds is not None`` ⇔ 本次到过。
        没用过的节点（跳过的 / 没跑到的）不进新路线 —— 否则路线里会带上一堆
        「玩家从没去过、用时 0」的节点。
        """
        if not self.active_run:
            return []
        return [node for node in self.active_run.nodes if node.visited and node.name]

    def _on_area_entered(self, event: GameEvent) -> None:
        if not self.has_active_run:
            return
        assert self.active_run is not None
        if self.active_run.campaign_over:
            # 剧情已结束：之后的区域（终局城镇 / 地图 / 藏身处）都不进开荒路线，
            # 否则保存成路线时会带进一堆终局节点。
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
            # 进图没被记录 → 试炼进门标记作废（否则会挂到后面的节点上）
            self._pending_trial_entry = None
            return
        # 试炼进门节点已建好 → 记住它，后续试炼房间都并进来
        self._resolve_pending_trial_entry()
        self._last_area = area
        self._sync_current_area_display()
        self._persist()
        self._emit_state()

    def _on_campaign_end(self, event: GameEvent) -> None:
        """剧情结束（PoE1 Act 10 奇塔弗 -60% 永久削弱）：暂停计时。

        出现这条系统提示时玩家刚打完剧情最终 Boss，开荒已经结束；
        继续计时只会把终局内容（地图 / 藏身处）算进开荒时间。
        """
        if not self.has_active_run:
            return
        assert self.active_run is not None
        if self.active_run.campaign_over:
            return

        # 先在当前时刻收尾：把已经跑完的段算进去，再冻结总时间
        self._sync_elapsed()
        if not self.active_run.is_paused:
            self.active_run.is_paused = True
        self._timer_started_at = None
        self.active_run.campaign_over = True
        test_log.write(
            "RUN",
            "剧情结束，暂停计时",
            raw_line=event.raw_line[:160],
            elapsed=round(self.active_run.elapsed_seconds, 2),
        )
        self._persist()
        self._emit_state()

    def _sync_current_area_display(self) -> None:
        assert self.active_run is not None
        if self.active_run.current_index < len(self.active_run.nodes):
            self.active_run.current_area = self.active_run.nodes[self.active_run.current_index].name
        else:
            self.active_run.current_area = ""

    def _segment_seconds(self, _timestamp: datetime) -> float:
        """当前节点已累计的停留时长（总时间 - 已计入节点的用时之和）。

        求和口径用 ``visited``（``seconds is not None``）——
        这是「时间确实存在于某个节点」的唯一判据。
        """
        assert self.active_run is not None
        completed_sum = sum(
            node.seconds or 0.0 for node in self.active_run.nodes if node.visited
        )
        return max(0.0, self.elapsed_seconds() - completed_sum)

    def _correct_seeded_node_name(self, area: str, area_id: str) -> None:
        """预置的第一幕起点节点：按日志原文校正显示名。

        预置时只能拿到回退译名（客户端语言未知），玩家真正进图后日志里
        才有原文，用原文覆盖，保证界面显示与游戏一致。
        """
        if not self.active_run or not area_id:
            return
        seed_id = campaign_start_area_id(self._run_game_id())
        for node in self.active_run.nodes:
            if node.area_id == area_id and node.area_id == seed_id:
                # 玩家真正进了第一幕起点 → 预置节点已被认领
                self._seed_claimed = True
                if node.name != area:
                    node.name = area
                return
            if node.area_id == area_id and node.name != area:
                node.name = area
                return

    def _record_node(
        self,
        area: str,
        segment_seconds: float,
        timestamp: datetime | None = None,
        area_id: str = "",
    ) -> bool:
        assert self.active_run is not None
        display = self.display_name(area) or area
        has_reference = self.active_run.is_reference_mode
        # 预置的第一幕起点：名字可能是回退译名，玩家真进图后按日志原文校正
        self._correct_seeded_node_name(area, area_id)

        # 试炼折叠：一次试炼只记进门那一次，试炼里的房间不单独记录。
        # 玩家在试炼内来回（混沌神殿 ↔ 混沌試煉）也算同一次试炼。
        trial_info = detect_trial(area_id, self._run_game_id())
        if self._merge_into_active_trial(area, display, area_id, segment_seconds):
            return True

        # 回到已经去过的地点（从 Act 3 回 Act 1、同幕内来回跑）：
        # **当作没有换节点** —— 不新增节点，**时间也不并回原节点**，
        # 这段时间算在**当前节点**上（与参考路线模式完全一致）。
        #
        # 用户 2026-10-29 定稿：
        #   新建路线模式「是什么节点就记录什么」，但重复不新增节点，
        #   时间也不并回重复节点，而是当作没有换节点。
        #
        # 试炼进门例外：多次试炼的进门 area id 相同，每次都要记。
        if trial_info.in_trial:
            pass
        elif not has_reference:
            revisited = self._find_revisited_node(area, area_id)
            if revisited is not None and revisited != self.active_run.current_index:
                # 重复进入已去过的地点 → 不换节点，时间留在当前节点
                test_log.write(
                    "RUN",
                    "重复进入已去过的地点（不换节点）",
                    area=area,
                    display=display,
                    revisited_index=revisited,
                    current_index=self.active_run.current_index,
                )
                return True

        if self.active_run.nodes:
            match_index = self._find_forward_match(area, area_id)
            if match_index is None:
                # **参考路线模式的核心规则**（用户 2026-10-29 定稿）：
                #
                #   参考路线 A B C D E，实际 A C B D E。
                #   玩家在 C 时，只在「C 之后」（即 D、E）里找下一个参考节点。
                #   找不到 → 这段时间**记给当前节点 C**，角色**不换节点**。
                #
                #   下面这些全都归 C：
                #     - 回到 C 之前的节点（B / A）—— 它们在「C 之后」这个范围里没有记录
                #     - 藏身处
                #     - 参考路线里根本没有的新地点
                #     - 参考路线已经全部跑完（当前节点 = 最后一个参考节点）
                #
                #   参考路线模式下**不新增任何节点、不作废任何参考节点、
                #   不存在「路线分叉」这回事** —— 节点集合恒等于参考路线。
                #
                # 历史包袱（本次已删除的旧逻辑）：
                #   真机事故 2026-10-28：旧逻辑攒 2 次「未知区域」就判定路线分叉
                #   → 剩余 140 个参考节点全被标 skipped → 28.3 分钟用时蒸发。
                if has_reference and not trial_info.in_trial:
                    # 时间继续算在当前节点上：不换节点、不新增、不改任何标记。
                    test_log.write(
                        "RUN",
                        "时间归当前节点（非后续参考节点）",
                        area=area,
                        display=display,
                        current_index=self.active_run.current_index,
                        timing=self.next_expected_area(),
                    )
                    return True
                # 新建路线模式：进哪记哪（无参考节点可匹配时新增节点）。
                # 先给当前节点收尾 —— 它的时间到此为止。
                self._close_current_node(segment_seconds)
                return self._append_free_node(area, display, area_id)

            if match_index == self.active_run.current_index:
                # 匹配到**当前节点自己** = 玩家进的就是当前正在计时的区域
                # （典型：第一次进图时当前节点是预置的第一幕起点）。
                #
                # **不要在这里结算时间**：当前节点的时间是「累积」的，
                # 离开它时才由 ``_close_current_node`` / 跳段分支结算。
                # 提前 mark_visited 会把这段停留重复计两次。
                test_log.write(
                    "RUN",
                    "认领当前节点",
                    area=area,
                    display=display,
                    index=match_index,
                )
                return True

            if match_index > self.active_run.current_index:
                closed_index = self.active_run.current_index
                active = self.active_run.nodes[closed_index]
                if not active.completed:
                    active.mark_visited(segment_seconds)
                for index in range(closed_index + 1, match_index):
                    skip_node = self.active_run.nodes[index]
                    if skip_node.visited:
                        # 已经有过真实用时 = 玩家确实在这个区域待过。
                        # 绝不能标成 skipped：skipped 的节点在统计时被排除，
                        # 那段时间会凭空消失（真机事故 2026-10-28：
                        # 24 个真跑过的节点被标 skipped → 28.3 分钟用时蒸发）。
                        continue
                    skip_node.mark_skipped()
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

    def _can_free_record(self) -> bool:
        """是否可以按实际进图自由记录（新增节点）。

        **仅新建路线模式**（无参考路线）成立。

        参考路线模式下**永远不自由记录**：节点集合恒等于参考路线，
        不在「当前节点之后」的参考节点出现时，时间记给当前节点
        （用户 2026-10-29 定稿规则）。
        """
        if not self.active_run:
            return False
        if self.active_run.is_reference_mode:
            return False
        return True

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
        if self._is_unvisited_seed(node):
            # 预置的第一幕起点玩家根本没进过（新建路线时人已经在别的幕）：
            # 标记跳过，不能记一段假时间。
            node.mark_skipped()
            return
        node.mark_visited(segment_seconds)

    def _is_unvisited_seed(self, node: RunNode) -> bool:
        """该节点是否是「预置但玩家从未真正进过」的第一幕起点。

        判定：预置起点 area id 与节点一致，且节点还没有任何时间记录。
        玩家一旦进过该区域，``_correct_seeded_node_name`` 会把名字改成日志原文，
        这里用「名字仍是预置译名/空」来判断是否被认领过。
        """
        if not self.active_run:
            return False
        seed_id = campaign_start_area_id(self._run_game_id())
        if not seed_id or node.area_id != seed_id:
            return False
        if self._seed_claimed:
            return False
        # 玩家已进过该区域（名字被改成日志原文 / 节点已有时间）
        return node.seconds is None and not node.completed

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

    def _find_revisited_node(self, area: str, area_id: str) -> int | None:
        """找「已经去过的同一地点」节点（玩家又回到了这个区域）。

        身份优先用 area id（唯一标识一个区域实例）：
        - 有 area id 时，只匹配 area id 相同的节点。
          否则 PoE1 迷宫里三个同名 boss 实例
          （1_Labyrinth_boss_1 / boss_2 / boss_2_end）会被错误合并成一个。
        - 只有节点本身没有 area id 时，才退回按区域名匹配
          （回城 / 无 id 的自由记录场景）。

        只在**已跑过**的节点里找：玩家从 Act 3 回到 Act 1、或同一幕内来回跑，
        都不该再产生新节点。

        调用方的处理（用户 2026-10-29 定稿）：识别到重复后**当作没有换节点** ——
        不新增节点，时间也不并回原节点，这段时间算在当前节点上。
        """
        if not self.active_run:
            return None
        if area_id:
            for index, node in enumerate(self.active_run.nodes):
                if node.area_id == area_id:
                    return index
            # 节点没有 area id（旧数据 / 手工建路线）→ 退回按名匹配
            for index, node in enumerate(self.active_run.nodes):
                if not node.area_id and self._areas_match(area, node.name):
                    return index
            return None
        for index, node in enumerate(self.active_run.nodes):
            if self._areas_match(area, node.name):
                return index
        return None

    def _merge_into_active_trial(
        self,
        area: str,
        display: str,
        area_id: str,
        segment_seconds: float,
    ) -> bool:
        """试炼折叠（实时）：试炼里的房间不单独记录，时间并入「进门那一次」。

        规则（用户 2026-10-25 定）：
        - 一次试炼只记录进门那一次，房间不单独记录
        - 多次试炼每次都记录（每次进门都是一个新节点）

        「一次试炼」的边界 = 从进入试炼区域开始，到玩家**离开**试炼区域为止。
        这期间再遇到任何试炼区域都属于同一次试炼（混沌神殿 ↔ 混沌試煉 来回也算）。

        返回 True 表示已折叠处理（调用方不要再建节点）。
        """
        assert self.active_run is not None
        info = detect_trial(area_id, self._run_game_id())
        if not info.in_trial:
            # 离开试炼区域 → 下次再进来是另一次试炼
            self._active_trial = None
            self._pending_trial_entry = None
            return False

        if self._active_trial is not None:
            trial_id, entry_index = self._active_trial
            if trial_id == info.trial_id and 0 <= entry_index < len(self.active_run.nodes):
                entry = self.active_run.nodes[entry_index]
                entry.seconds = (entry.seconds or 0.0) + segment_seconds
                # 试炼内继续以进门节点为当前节点
                self.active_run.current_index = entry_index
                # 本体区域第一次出现时，纠正显示名
                # （进门是入口大厅 / 前厅时，名字要在见到本体后才准）
                if area_id == trial_body_id(trial_id) and display:
                    entry.name = display
                test_log.write(
                    "RUN",
                    "试炼内区域，并入进门节点",
                    index=entry_index,
                    name=entry.name,
                    area=area,
                    seconds=round(segment_seconds, 2),
                )
                return True

        # 试炼的第一次进入 = 进门 → 交给调用方建节点，
        # 建好后由 _resolve_pending_trial_entry 补上 index
        self._pending_trial_entry = info.trial_id
        self._active_trial = None
        return False

    def _resolve_pending_trial_entry(self) -> None:
        """进门节点建好后，记下它在哪（后续试炼房间都并进来）。"""
        if not self._pending_trial_entry or not self.active_run:
            return
        trial_id = self._pending_trial_entry
        self._pending_trial_entry = None
        index = self.active_run.current_index
        if not 0 <= index < len(self.active_run.nodes):
            return
        node = self.active_run.nodes[index]
        node.is_trial_entry = True
        # 显示名统一规则（与离线解析一致，见 trial_node_name）
        body_name = known_area_name(trial_body_id(trial_id))
        canonical = trial_node_name(
            trial_id, node.area_id, node.name, body_name
        )
        if canonical:
            node.name = canonical
        self._active_trial = (trial_id, index)

    def _is_recent_repeat(self, area: str, area_id: str = "") -> bool:
        """该区域是否刚跑过（回城 / 死亡折返 / 反复进出），避免污染自由节点。

        有 area id 时按 id 判定：PoE1 迷宫里三个同名 boss 实例
        （boss_1 / boss_2 / boss_2_end）不是同一个区域，不能互相屏蔽。
        """
        if not self.active_run:
            return False
        recent = self.active_run.nodes[-REPEAT_NAME_MIN_GAP:]
        if area_id:
            return any(node.area_id == area_id for node in recent)
        return any(self._areas_match(area, node.name) for node in recent)

    def _manual_split(self) -> None:
        assert self.active_run is not None
        self._sync_elapsed()
        segment_seconds = self._segment_seconds(datetime.now())
        if self.active_run.current_index < len(self.active_run.nodes):
            node = self.active_run.nodes[self.active_run.current_index]
            if not node.completed:
                node.mark_visited(segment_seconds)
                self.active_run.current_index = self._next_uncompleted_index(self.active_run.current_index + 1)
                self._persist()
                self._emit_state()

    @staticmethod
    def _area_id_compatible(node: RunNode, area_id: str) -> bool:
        """area id 兼容性：节点没记录 id 时不阻止匹配（老数据 / 手工路线）。

        两边都有 id 时必须一致 —— 同名不同实例（PoE1 迷宫三个 boss）不能混为一谈。
        """
        if not area_id or not node.area_id:
            return True
        return node.area_id == area_id

    def _node_matches(self, node: RunNode, area: str, area_id: str) -> bool:
        """节点是否就是这次进图的区域。

        area id 相同 = 直接命中（权威身份）。
        否则按区域名匹配；预置的第一幕起点可能只有回退译名，
        靠 area id 才能对上。
        """
        if area_id and node.area_id and node.area_id == area_id:
            return True
        if not self._areas_match(area, node.name):
            return False
        return self._area_id_compatible(node, area_id)

    def _find_forward_match(self, area: str, area_id: str = "") -> int | None:
        """找「下一个」参考节点。

        **匹配范围 = ``[current_index .. 末尾]``**（含当前节点本身）。

        用户 2026-10-29 定稿的规则：

            参考路线 A B C D E，实际 A C B D E。
            玩家在 C 时，只在「C 之后」（D、E）里找下一个参考节点。
            B 在「C 之后」这个范围里没有记录 → 玩家回 B 时这段时间**记给 C**。

        为什么**含**当前节点：
            第一次进图时当前节点就是「正在计时的那个」（可能是预置的第一幕起点），
            玩家进的就是它 —— 必须能匹配上，否则会凭空新增一个重复节点。

        为什么**不含**当前节点之前的：
            回到 C 之前的节点（A、B）不在搜索范围内 → 落入「记给当前节点」分支。
            这正是用户要的规则：回旧节点不换节点、时间归当前节点。

        **两阶段匹配**（解决同名节点歧义 + 保留远距离精确匹配）：

        1. **窗口内按名匹配**：``[current_index, current_index + MAX_FORWARD_MATCH)``
           范围内第一个名字 / area id 匹配的节点。
           窗口存在的理由：PoE1 的 Act 6–10 复用 Act 1–5 的区域名，
           玩家回 Act 1 城镇时不能跳到远处 Act 6 的同名节点。

        2. **窗口外只接受 area id 精确匹配**：area id 是区域的唯一身份，
           ``1_2_15`` = The Fellshrine Ruins，不可能指别的区域。
           真机事故 2026-10-28：参考路线把 Act 3 的 The Fellshrine Ruins 插在
           Act 2 节点中间（index 37），玩家实打实跑到它时因超出 15 窗口被拒
           → 累积 2 次「未知区域」→ 判定路线分叉 → 剩余 100 个节点全废。
           现在这种情况由 area id 精确命中兜住，不会误判分叉。

        已 visited（本次已跑过）与 skipped（跳段判定没去过）的节点都不再匹配。
        """
        assert self.active_run is not None
        nodes = self.active_run.nodes
        start = max(0, self.active_run.current_index)
        # 名字在整个路线里唯一 → 没有同名歧义 → 全程可跳（远距离跳段）。
        # 名字出现多次（PoE1 的 Act 6–10 复用 Act 1–5 区域名）→ 限定窗口。
        occurrences = sum(1 for node in nodes if self._areas_match(area, node.name))
        if occurrences <= 1:
            limit = len(nodes)
        else:
            limit = min(len(nodes), start + MAX_FORWARD_MATCH)

        def _matchable(node: RunNode) -> bool:
            if node.visited:
                # 已经记过用时 = 本次已经跑过这个节点，不再重复匹配
                return False
            if node.skipped:
                # 跳段时被判定「本次没去过」的参考节点，不再作为匹配目标。
                # 否则玩家走回它时会被当成「下一个参考节点」，
                # 违反「只看当前节点之后」的规则（参考路线 A B C D E，
                # 玩家实际 A C B D E：跳到 C 时 B 被标 skipped，
                # 之后玩家进 B 应当归 C，而不是跳回 B）。
                return False
            return True

        # 阶段 1：窗口内匹配（按名 / area id 都行）
        for index in range(start, limit):
            node = nodes[index]
            if not _matchable(node):
                continue
            if self._node_matches(node, area, area_id):
                return index

        # 阶段 2：窗口外只认 area id 精确匹配（唯一身份，不受窗口限制）
        if area_id:
            for index in range(limit, len(nodes)):
                node = nodes[index]
                if not _matchable(node):
                    continue
                if node.area_id and node.area_id == area_id:
                    return index
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
