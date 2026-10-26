from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

import tkinter as tk

from routelens.client_discovery import detect_game_from_client, iter_client_candidates
from routelens.config import load_routelens_config
from routelens.engine import RunEngine
from routelens.models import ReferenceRoute, RouteNode, format_delta, format_duration
from routelens.split_panel import SplitPanel

# 同一进程反复建/销 Tk 根会偶发毁掉共享的 Tcl 解释器（tcl_findLibrary 报错）。
# 全部 GUI 用例共用一个根，测试结束时统一销毁。
_SHARED_TK_ROOT: tk.Misc | None = None


def shared_tk_root() -> tk.Misc:
    """共享的 GUI 根（CustomTkinter，因为 RouteLensApp 会 configure(fg_color=...)）。"""
    global _SHARED_TK_ROOT
    if _SHARED_TK_ROOT is None:
        import customtkinter as ctk

        _SHARED_TK_ROOT = ctk.CTk()
        _SHARED_TK_ROOT.withdraw()
    return _SHARED_TK_ROOT


def tearDownModule() -> None:
    global _SHARED_TK_ROOT
    if _SHARED_TK_ROOT is not None:
        try:
            _SHARED_TK_ROOT.destroy()
        except tk.TclError:  # pragma: no cover - 解释器已被拆
            pass
        _SHARED_TK_ROOT = None


class RouteLensSmokeTests(unittest.TestCase):
    def test_format_helpers(self) -> None:
        self.assertEqual(format_duration(125), "02:05")
        self.assertEqual(format_delta(100, 90), "+00:10")
        self.assertEqual(format_delta(80, 90), "-00:10")

    def test_client_discovery(self) -> None:
        candidates = iter_client_candidates()
        self.assertIsInstance(candidates, list)
        config = load_routelens_config()
        client = config.resolved_client_path
        if client and client.is_file():
            game = detect_game_from_client(client)
            self.assertIn(game, {"poe1", "poe2"})

    def test_hideout_filter(self) -> None:
        from routelens.hideout_filter import is_hideout_area

        self.assertTrue(is_hideout_area("Overgrown Hideout"))
        self.assertTrue(is_hideout_area("藏身处"))
        self.assertTrue(is_hideout_area("藏身處"))
        self.assertFalse(is_hideout_area("The Coast"))

    def test_import_limits_recent_routes(self) -> None:
        from tempfile import TemporaryDirectory

        from routelens.client_import import RECENT_ROUTE_LIMIT, import_routes_from_client

        marker = "***** LOG FILE OPENING *****"
        scene = "2026/01/01 12:00:00 12345 [INFO Client 1] [SCENE] Set Source [河岸]\n"
        area_line = (
            "2026/01/01 12:00:10 12346 [INFO Client 1] "
            ": You have entered 皆伐.\n"
        )
        blocks = []
        for index in range(15):
            hour = index % 24
            blocks.append(f"{marker}\n")
            blocks.append(scene.replace("12:00:00", f"{hour:02d}:00:00"))
            for step in range(6):
                blocks.append(
                    area_line.replace("12:00:10", f"{hour:02d}:00:{10 + step:02d}").replace(
                        "皆伐", f"区域{step}"
                    )
                )
        client_text = "".join(blocks)

        with TemporaryDirectory() as tmp:
            client_path = Path(tmp) / "Client.txt"
            client_path.write_text(client_text, encoding="utf-8")
            engine = RunEngine(load_routelens_config())
            routes, session_count, _merged, _unqualified = import_routes_from_client(
                client_path,
                area_registry=engine.area_registry,
                locale=engine.config.locale,
                game_id=engine.config.game,
                min_nodes=5,
                max_routes=RECENT_ROUTE_LIMIT,
            )
            self.assertLessEqual(len(routes), RECENT_ROUTE_LIMIT)
            self.assertGreater(session_count, 0)
            # 短测试日志通常不构成「完整开荒」，允许 routes 为 0

    def test_merged_sessions_can_qualify_as_complete(self) -> None:
        from routelens.client_import import _group_and_merge_sessions, _session_is_complete_campaign

        def _make_splits(start: int, count: int) -> list[dict]:
            return [
                {
                    "area": f"区域{index}",
                    "area_en": f"Zone{index}",
                    "segment_seconds": 10.0,
                    "arrived_at": f"2026-01-01T12:{index % 60:02d}:00",
                }
                for index in range(start, start + count)
            ]

        sessions = [
            {
                "session_id": 1,
                "character": "Tester",
                "chapters": ["第一章", "第二章"],
                "chapter_label": "第一章 → 第二章",
                "started_at": "2026-01-01T10:00:00",
                "ended_at": "2026-01-01T11:00:00",
                "splits": _make_splits(0, 20),
                "deaths": 0,
            },
            {
                "session_id": 2,
                "character": "Tester",
                "chapters": ["第三章", "第四章"],
                "chapter_label": "第三章 → 第四章",
                "started_at": "2026-01-02T10:00:00",
                "ended_at": "2026-01-02T12:00:00",
                "splits": _make_splits(20, 20)
                + [{"area": "高地神塔庇護所", "area_en": "The Ziggurat Refuge", "segment_seconds": 10.0}],
                "deaths": 1,
            },
        ]
        merged = _group_and_merge_sessions(sessions)
        self.assertEqual(len(merged), 1)
        self.assertGreaterEqual(len(merged[0].get("splits", [])), 35)
        self.assertTrue(_session_is_complete_campaign(merged[0], "poe2"))

    def test_no_chapter_lines_fallback_by_node_count(self) -> None:
        from routelens.client_import import _enrich_session_dict, _session_is_complete_campaign

        session = {
            "character": "Tester",
            "chapters": ["未知"],
            "chapter_label": "未知",
            "splits": [
                {
                    "area": f"区域{index}",
                    "area_en": f"Zone{index}",
                    "segment_seconds": 10.0,
                }
                for index in range(52)
            ]
            + [{"area": "高地神塔庇護所", "area_en": "The Ziggurat Refuge", "segment_seconds": 10.0}],
        }
        enriched = _enrich_session_dict(
            session,
            area_registry=None,
            area_chapter_map={},
            poe2_area_keys=set(),
            default_game_id="poe2",
        )
        self.assertEqual(enriched.get("chapters"), [])
        self.assertTrue(_session_is_complete_campaign(enriched, "poe2"))

    def test_unfinished_character_imported_and_reported(self) -> None:
        """日志窗口无开荒终点锚点 = 未通关 → 照常导入现有节点，但进提醒名单。"""
        from routelens.client_import import sessions_to_reference_routes

        def _splits(count: int, with_end: bool) -> list[dict]:
            result = [
                {
                    "area": f"区域{index}",
                    "area_en": f"Zone{index}",
                    "segment_seconds": 10.0,
                }
                for index in range(count)
            ]
            if with_end:
                result.append({"area": "高地神塔庇護所", "area_en": "The Ziggurat Refuge", "segment_seconds": 10.0})
            return result

        finished = {
            "character": "Finished",
            "chapters": ["第一章", "第五章"],
            "splits": _splits(40, with_end=True),
        }
        unfinished = {
            "character": "OldChar",
            "chapters": [],
            "splits": _splits(60, with_end=False),
        }

        routes, unfinished_names = sessions_to_reference_routes(
            [finished, unfinished], game_id="poe2", max_routes=10
        )
        # 未通关也导入；名单仅提醒
        self.assertEqual(
            sorted(r.character for r in routes), ["Finished", "OldChar"]
        )
        self.assertEqual(unfinished_names, ["OldChar"])

    def test_infer_route_game_id_poe1(self) -> None:
        from routelens.client_import import infer_route_game_id

        session = {
            "splits": [
                {"area": "Lioneye's Watch", "area_en": "Lioneye's Watch", "segment_seconds": 10.0},
                {"area": "The Coast", "area_en": "The Coast", "segment_seconds": 20.0},
            ]
        }
        self.assertEqual(
            infer_route_game_id(
                session,
                poe2_area_keys={"河岸", "Clearfell", "The Riverbank"},
                area_registry=None,
                default_game_id="poe2",
            ),
            "poe1",
        )

    def test_import_and_routes(self) -> None:
        engine = RunEngine(load_routelens_config())
        summary = engine.import_from_client_txt()
        self.assertIn("session_count", summary)
        self.assertIn("route_count", summary)
        self.assertIn("merged_candidates", summary)
        self.assertLessEqual(summary["route_count"], 10)

    def test_engine_run_flow(self) -> None:
        engine = RunEngine(load_routelens_config())
        routes = engine.store.list_routes()
        if not routes:
            self.skipTest("无参考路线")
        route = routes[0]
        engine.begin_new_run(route)
        self.assertTrue(engine.has_active_run)

        engine.start_or_split()
        self.assertTrue(engine.timer_running)

        area = route.nodes[0].name if route.nodes else "河岸"
        engine.simulate_area(area)
        run = engine.active_run
        assert run is not None
        self.assertEqual(run.current_index, 0)
        if len(route.nodes) > 1:
            from routelens.hideout_filter import is_hideout_area

            second_area = next(
                (node.name for node in route.nodes[1:] if not is_hideout_area(node.name)),
                None,
            )
            if second_area:
                engine.simulate_area(second_area, write_client=False)
                self.assertGreater(run.current_index, 0)

        ref = engine.reference_seconds_at(0)
        self.assertIsNotNone(ref)

        engine.skip_split()
        engine.undo_split()
        engine.pause_toggle()
        engine.pause_toggle()
        engine.reset_run()
        assert engine.active_run is not None
        self.assertEqual(engine.active_run.current_index, 0)

        engine.save_now()
        saved = engine.load_saved_run()
        self.assertIsNotNone(saved)

    def test_split_panel_redraw(self) -> None:
        root = shared_tk_root()
        try:
            panel = SplitPanel(root, width=280, height=200)
            panel.pack()
            root.update_idletasks()
            rows = [
                {"name": "河岸", "time": "01:00", "ref": "01:15", "delta": "-00:15", "status": "completed"},
                {"name": "皆伐營地", "time": "", "ref": "00:34", "delta": "", "status": "current"},
                {"name": "皆伐", "time": "", "ref": "01:20", "delta": "", "status": "pending"},
            ]
            panel.set_rows(rows, 1)
            root.update_idletasks()
            self.assertGreater(panel.winfo_width(), 0)
            panel.destroy()
        finally:
            root.update_idletasks()

    def test_minimal_mode_always_shows_total_timer(self) -> None:
        """极简模式没有任何节点时也必须画出总时间（用户实测看不到计时）。"""
        root = shared_tk_root()
        try:
            panel = SplitPanel(root, width=280, height=120)
            panel.pack()
            root.update_idletasks()
            panel.set_minimal(True)
            panel.set_rows([], 0, total_text="01:23.45")
            root.update_idletasks()

            rendered = {
                str(panel.itemcget(item, "text"))
                for item in panel.find_all()
                if panel.type(item) == "text"
            }
            self.assertIn("01:23.45", rendered)
            panel.destroy()
        finally:
            root.update_idletasks()

    def test_minimal_mode_with_rows_shows_total_timer(self) -> None:
        root = shared_tk_root()
        try:
            panel = SplitPanel(root, width=280, height=120)
            panel.pack()
            root.update_idletasks()
            panel.set_minimal(True)
            rows = [
                {"name": "河岸", "time": "01:00", "ref": "", "delta": "", "status": "completed"},
                {"name": "皆伐營地", "time": "00:12", "ref": "", "delta": "", "status": "current"},
            ]
            panel.set_rows(rows, 1, total_text="02:03.45")
            root.update_idletasks()

            rendered = {
                str(panel.itemcget(item, "text"))
                for item in panel.find_all()
                if panel.type(item) == "text"
            }
            self.assertIn("02:03.45", rendered)
            panel.destroy()
        finally:
            root.update_idletasks()

    def test_reference_route_no_append(self) -> None:
        engine = RunEngine(load_routelens_config())
        routes = engine.store.list_routes()
        if not routes:
            self.skipTest("无参考路线")
        route = routes[0]
        if len(route.nodes) < 2:
            self.skipTest("路线节点不足")
        engine.begin_new_run(route)
        engine.start_or_split()
        initial_len = len(engine.active_run.nodes)  # type: ignore[union-attr]

        wrong_area = "___not_a_real_area___"
        engine.simulate_area(wrong_area, write_client=False)
        self.assertEqual(len(engine.active_run.nodes), initial_len)  # type: ignore[union-attr]

        next_area = engine.next_expected_area()
        self.assertTrue(next_area)
        engine.simulate_area(next_area, write_client=False)
        self.assertEqual(engine.active_run.current_index, 0)  # type: ignore[union-attr]
        self.assertEqual(len(engine.active_run.nodes), initial_len)  # type: ignore[union-attr]

    def test_jump_from_a_to_c_keeps_c_running(self) -> None:
        engine = RunEngine(load_routelens_config())
        ref = ReferenceRoute(
            route_id="test-abcde",
            name="A-B-C-D-E",
            nodes=[RouteNode(name=name) for name in ("A", "B", "C", "D", "E")],
        )
        engine.new_run(ref)
        engine.start_or_split()
        assert engine.active_run is not None
        engine.active_run.elapsed_seconds = 30.0
        engine._timer_started_at = None

        engine.simulate_area("C", write_client=False)
        run = engine.active_run
        self.assertTrue(run.nodes[0].completed)
        self.assertAlmostEqual(run.nodes[0].seconds or 0.0, 30.0, places=1)
        self.assertTrue(run.nodes[1].skipped)
        self.assertFalse(run.nodes[2].completed)
        self.assertEqual(run.current_index, 2)

    def test_out_of_order_ignores_backtrack(self) -> None:
        engine = RunEngine(load_routelens_config())
        ref = ReferenceRoute(
            route_id="test-acbd",
            name="A-C-B-D",
            nodes=[RouteNode(name=name) for name in ("A", "B", "C", "D")],
        )
        engine.new_run(ref)
        engine.start_or_split()

        engine.simulate_area("A", write_client=False)
        engine.simulate_area("C", write_client=False)
        run = engine.active_run
        assert run is not None
        self.assertTrue(run.nodes[0].completed)
        self.assertTrue(run.nodes[1].skipped)
        self.assertFalse(run.nodes[2].completed)
        self.assertEqual(run.current_index, 2)

        engine._last_area = ""
        engine.simulate_area("B", write_client=False)
        self.assertTrue(run.nodes[1].skipped)
        self.assertIsNone(run.nodes[1].seconds)
        self.assertEqual(run.current_index, 2)

        engine._last_area = ""
        engine.simulate_area("D", write_client=False)
        self.assertTrue(run.nodes[2].completed)
        self.assertFalse(run.nodes[3].completed)
        self.assertEqual(run.current_index, 3)

    def test_forward_only_sequence_abcdef(self) -> None:
        engine = RunEngine(load_routelens_config())
        ref = ReferenceRoute(
            route_id="test-abcdef",
            name="A-F",
            nodes=[RouteNode(name=name) for name in ("A", "B", "C", "D", "E", "F")],
        )
        engine.new_run(ref)
        engine.start_or_split()

        sequence = ["A", "C", "B", "C", "E", "C", "D", "E", "A", "D", "E"]
        for area in sequence:
            engine._last_area = ""
            engine._inject_area(area)

        run = engine.active_run
        assert run is not None
        self.assertTrue(run.nodes[0].completed)
        self.assertTrue(run.nodes[1].skipped)
        self.assertTrue(run.nodes[2].completed)
        self.assertTrue(run.nodes[3].skipped)
        self.assertFalse(run.nodes[4].completed)
        self.assertEqual(run.current_index, 4)

    def test_forward_jump_skip_middle(self) -> None:
        engine = RunEngine(load_routelens_config())
        ref = ReferenceRoute(
            route_id="test-abd",
            name="A-B-C-D",
            nodes=[RouteNode(name=name) for name in ("A", "B", "C", "D")],
        )
        engine.new_run(ref)
        engine.start_or_split()

        engine.simulate_area("A", write_client=False)
        engine.simulate_area("B", write_client=False)
        engine.simulate_area("D", write_client=False)
        run = engine.active_run
        assert run is not None
        self.assertTrue(run.nodes[0].completed)
        self.assertTrue(run.nodes[1].completed)
        self.assertTrue(run.nodes[2].skipped)
        self.assertFalse(run.nodes[3].completed)
        self.assertEqual(run.current_index, 3)

    def test_hotkey_digit_mapping(self) -> None:
        from routelens.gui import RouteLensApp, _NUMPAD_KEYCODE_TO_DIGIT

        app = RouteLensApp(root=shared_tk_root())
        app.root.withdraw()
        try:
            event = tk.Event()
            event.keysym = "KP_0"
            event.keycode = 96
            self.assertEqual(app._key_to_hotkey_digit(event), "0")
            self.assertEqual(_NUMPAD_KEYCODE_TO_DIGIT.get(98), "2")
        finally:
            app._stop_tray()
            if app._global_hotkeys is not None:
                app._global_hotkeys.shutdown()
                app._global_hotkeys = None
            app.root.update_idletasks()

    def test_truncate_poe1_at_karui_shores(self) -> None:
        from routelens.campaign_end import truncate_at_campaign_end

        splits = [
            {"area": "The Canals", "segment_seconds": 10},
            {"area": "The Feeding Trough", "segment_seconds": 20},
            {"area": "Karui Shores", "segment_seconds": 30},
            {"area": "Volcano", "segment_seconds": 40},
            {"area": "Promenade", "segment_seconds": 50},
        ]
        truncated = truncate_at_campaign_end(splits, "poe1")
        self.assertEqual(
            [s["area"] for s in truncated],
            ["The Canals", "The Feeding Trough", "Karui Shores"],
        )

    def test_truncate_poe1_zh_locales(self) -> None:
        from routelens.campaign_end import truncate_at_campaign_end

        cn = truncate_at_campaign_end(
            [
                {"area": "饲槽"},
                {"area": "卡鲁海滩"},
                {"area": "火山"},
            ],
            "poe1",
        )
        self.assertEqual([s["area"] for s in cn], ["饲槽", "卡鲁海滩"])

        tw = truncate_at_campaign_end(
            [
                {"area": "破沿血道"},
                {"area": "卡魯沿岸"},
                {"area": "Volcano"},
            ],
            "poe1",
        )
        self.assertEqual([s["area"] for s in tw], ["破沿血道", "卡魯沿岸"])

    def test_truncate_poe2_at_refuge(self) -> None:
        from routelens.campaign_end import truncate_at_campaign_end

        truncated = truncate_at_campaign_end(
            [
                {"area": "Kingsmarch"},
                {"area": "The Ziggurat Refuge"},
                {"area": "Digsite"},
            ],
            "poe2",
        )
        self.assertEqual(
            [s["area"] for s in truncated],
            ["Kingsmarch", "The Ziggurat Refuge"],
        )

        # 异界地图（area id = Map*）必须被排除，不进开荒路线。
        # 实测：挖掘地 = MapExcavation
        truncated_map = truncate_at_campaign_end(
            [
                {"area": "Kingsmarch", "area_id": "G4_town"},
                {"area": "挖掘地", "area_id": "MapExcavation"},
                {"area": "Creek", "area_id": "MapCreek"},
            ],
            "poe2",
        )
        self.assertEqual([s["area"] for s in truncated_map], ["Kingsmarch"])

    def test_area_id_dedup_keeps_act5_and_act10_same_name(self) -> None:
        """Act 5 / Act 10 同名区域必须保留两段（只按区域名去重会吃掉后半程）。

        实测真机日志：The Ossuary -> 1_5_6 (Act 5) 与 2_10_9 (Act 10)；
        The Cathedral Rooftop -> 1_5_8 (Act 5) 与 2_10_1 (Act 10)。
        """
        from routelens.log_analyzer import AreaVisit, LogRunSession

        session = LogRunSession(session_id=1, character="Tester")
        from datetime import datetime

        base = datetime(2026, 10, 15, 22, 0, 0)
        session.visits = [
            AreaVisit(area="The Ossuary", timestamp=base, area_id="1_5_6"),
            AreaVisit(area="The Ossuary", timestamp=base.replace(hour=23), area_id="2_10_9"),
        ]
        splits = session.build_splits()
        self.assertEqual(len(splits), 2)
        self.assertEqual([s.area_id for s in splits], ["1_5_6", "2_10_9"])

    def test_act_view_labels_and_endgame_row(self) -> None:
        """幕视图：中文标签 + 终局行（PoE1 = 2_11 / PoE2 = G_Endgame_Town）。"""
        from routelens.gui import RouteLensApp
        from routelens.models import ActiveRun, RunNode

        app = RouteLensApp(root=shared_tk_root())
        app.root.withdraw()
        try:
            app.ui_lang = "zh"
            run = ActiveRun(
                run_id="r1",
                reference_route_id="ref1",
                reference_route_name="测试",
                nodes=[
                    RunNode(name="The Coast", seconds=30.0, completed=True, area_id="1_1_2"),
                    RunNode(name="The Ossuary", seconds=60.0, completed=True, area_id="1_5_6"),
                    RunNode(name="Karui Shores", seconds=10.0, completed=True, area_id="2_11_endgame_town"),
                ],
            )
            app._act_view = True
            rows, current_index = app._build_act_rows(run)
            names = [r["name"] for r in rows]
            # PoE1 骨架 = 10 幕 + 终局行
            self.assertEqual(len(rows), 11)
            self.assertEqual(names[0], "第 1 幕")
            self.assertEqual(names[4], "第 5 幕")
            self.assertEqual(names[-1], "终局")
            # 第 1 幕 = 30s（只有 1_1_2），第 5 幕 = 60s
            self.assertEqual(rows[0]["time"], "00:30")
            self.assertEqual(rows[4]["time"], "01:00")
            self.assertEqual(rows[-1]["time"], "00:10")
        finally:
            app._stop_tray()
            if app._global_hotkeys is not None:
                app._global_hotkeys.shutdown()
                app._global_hotkeys = None
            app.root.update_idletasks()

    def test_expected_act_labels(self) -> None:
        from routelens.act_timing import expected_act_labels

        self.assertEqual(len(expected_act_labels("poe1", "en")), 10)
        self.assertEqual(len(expected_act_labels("poe2", "en")), 4)
        self.assertEqual(expected_act_labels("poe1", "en")[0], "Act 1")
        self.assertEqual(expected_act_labels("poe1", "zh_tw")[0], "第 1 幕")
        self.assertEqual(expected_act_labels("poe2", "zh_tw")[3], "第 4 幕")

    def test_version_visible_in_route_picker_and_settings(self) -> None:
        """版本号必须在「选路线」页与「设置」页都可见（用户报 Bug 时要能直接报版本）。"""
        from routelens.gui import RouteLensApp
        from routelens.version import APP_DISPLAY, VERSION, VERSION_LABEL

        app = RouteLensApp(root=shared_tk_root())
        app.root.withdraw()
        try:
            # 窗口标题带版本
            self.assertIn(VERSION, app.root.title())
            self.assertIn(VERSION_LABEL, app.root.title())

            # 选路线页
            app._show_main()
            app.root.update_idletasks()
            self.assertIsNotNone(app._main_frame)
            main_text = _collect_widget_text(app._main_frame)
            self.assertIn(VERSION_LABEL, main_text)
            self.assertIn(APP_DISPLAY, main_text)

            # 设置页（独立 toplevel，单独校验，避免被主界面的版本号"顶过"）
            before = set(app.root.winfo_children())
            app._open_settings()
            app.root.update_idletasks()
            new_windows = [w for w in app.root.winfo_children() if w not in before]
            self.assertTrue(new_windows, "设置窗口应作为新 toplevel 打开")
            settings_win = new_windows[0]
            self.assertIn(VERSION, settings_win.title())
            settings_text = _collect_widget_text(settings_win)
            self.assertIn(VERSION_LABEL, settings_text)
            self.assertIn(APP_DISPLAY, settings_text)
            settings_win.destroy()
        finally:
            app._stop_tray()
            if app._global_hotkeys is not None:
                app._global_hotkeys.shutdown()
                app._global_hotkeys = None
            app.root.update_idletasks()


def _collect_widget_text(widget: tk.Misc) -> str:
    """收集一棵 Tk 控件树里所有可见文本（用于断言界面显示了版本号）。"""
    chunks: list[str] = []
    stack: list[tk.Misc] = [widget]
    while stack:
        node = stack.pop()
        try:
            text = node.cget("text")
        except (tk.TclError, ValueError):
            text = ""
        if text:
            chunks.append(str(text))
        try:
            children = node.winfo_children()
        except tk.TclError:
            children = ()
        stack.extend(children)
    return "\n".join(chunks)


if __name__ == "__main__":
    unittest.main()
