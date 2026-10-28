"""回归：参考路线模式下回退到已去过的地点，不能判定成「路线分叉」。

真机事故（2026-10-28，PoE1 `gagffdgsfg (第一章 → 第十章)` 路线）：

    08:01:33 前进跳段 → The Submerged Passage (index 4)
    08:01:41 忽略进图（匹配点超出识别窗口）| area=The Coast matched_index=77
    08:01:41 参考路线分叉，转为实际记录 | {"areas":["The Coast","The Coast"]}

玩家只是从 The Submerged Passage 回到 The Coast（拿传送点 / 死亡回城），
而 Act 6 也有 The Coast（index 77），超出 15 节点窗口 → 找不到匹配
→ 被判成分叉 → 剩余 140 个参考节点全标 skipped
→ 节点视图只剩前 5 个节点有计时，幕视图也只到 Act 1。

两条独立缺陷：
1. 回退到**已跑过**的节点没有并回原节点（参考路线模式下回退识别被跳过）
2. 同一条进图日志重复出现被计成两个「未知区域」，立刻凑满分叉阈值
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import PropertyMock, patch

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.companion_config import CompanionConfig  # noqa: E402
from routelens.config import load_routelens_config  # noqa: E402
from routelens.engine import RunEngine  # noqa: E402
from routelens.models import ReferenceRoute, RouteNode  # noqa: E402


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch.object(
            CompanionConfig,
            "resolved_data_dir",
            new_callable=PropertyMock,
            return_value=Path(self._tmp.name),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        config = load_routelens_config()
        config.game = "poe1"
        self.engine = RunEngine(config)

    def _reference(self, nodes: list[tuple[str, str]]) -> ReferenceRoute:
        """nodes = [(区域名, area_id), ...]"""
        return ReferenceRoute(
            route_id="ref-act1",
            name="第一章 → 第十章",
            nodes=[
                RouteNode(name=name, seconds=10.0, area_id=area_id)
                for name, area_id in nodes
            ],
        )

    def _poe1_act1_route(self) -> ReferenceRoute:
        """Act 1 前段 + Act 6 同名区域（index 很远，超出识别窗口）。"""
        act1 = [
            ("The Twilight Strand", "1_1_1"),
            ("Lioneye's Watch", "1_1_town"),
            ("The Coast", "1_1_2"),
            ("The Mud Flats", "1_1_3"),
            ("The Submerged Passage", "1_1_4"),
            ("The Flooded Depths", "1_1_5"),
            ("The Ledge", "1_1_6"),
            ("The Climb", "1_1_7"),
        ]
        filler = [
            (f"Act5 Zone {i}", f"1_5_{i}") for i in range(1, 40)
        ]
        # Act 6 复用 Act 1 区域名（真实日志就是这样）
        act6 = [
            ("The Coast", "2_6_2"),
            ("The Mud Flats", "2_6_3"),
        ]
        return self._reference(act1 + filler + act6)


class BacktrackWithReferenceTests(_Case):
    def test_backtrack_to_visited_area_does_not_diverge(self) -> None:
        self.engine.new_run(self._poe1_act1_route())
        for name, area_id in [
            ("The Twilight Strand", "1_1_1"),
            ("Lioneye's Watch", "1_1_town"),
            ("The Coast", "1_1_2"),
            ("The Mud Flats", "1_1_3"),
            ("The Submerged Passage", "1_1_4"),
        ]:
            self.engine._inject_area_with_id(name, area_id)

        run = self.engine.active_run
        assert run is not None
        self.assertEqual(run.current_index, 4)

        # 回退到 The Coast（已去过）
        self.engine._inject_area_with_id("The Coast", "1_1_2")

        self.assertFalse(
            any(n.skipped for n in run.nodes),
            "回退不该把剩余参考节点全部标成跳过",
        )
        # 回退不把进度往回拨（回城期间时间仍算在当前节点）
        self.assertEqual(run.current_index, 4)

    def test_backtrack_then_continue_matches_reference(self) -> None:
        """回退后继续前进，仍然按参考路线推进（不会切到自由记录）。"""
        self.engine.new_run(self._poe1_act1_route())
        for name, area_id in [
            ("Lioneye's Watch", "1_1_town"),
            ("The Coast", "1_1_2"),
            ("The Mud Flats", "1_1_3"),
            ("The Submerged Passage", "1_1_4"),
        ]:
            self.engine._inject_area_with_id(name, area_id)
        self.engine._inject_area_with_id("The Coast", "1_1_2")

        run = self.engine.active_run
        assert run is not None
        added = len(run.nodes)

        # 继续前进：The Flooded Depths（index 5）
        self.engine._inject_area_with_id("The Flooded Depths", "1_1_5")
        self.assertEqual(len(run.nodes), added, "不能新增节点（参考路线还在用）")
        self.assertEqual(run.current_index, 5)
        # 到达的节点成为「当前节点」，正在计时
        self.assertFalse(run.nodes[5].completed)
        self.assertFalse(run.nodes[5].skipped)
        # 之前跑过的节点必须保留用时，不能被回退/跳段擦掉
        self.assertTrue(run.nodes[2].completed)
        self.assertFalse(run.nodes[2].skipped)

    def test_duplicate_enter_event_is_not_divergence_evidence(self) -> None:
        """同一条进图日志重复出现，不能立刻凑满分叉阈值。"""
        self.engine.new_run(self._poe1_act1_route())
        self.engine._inject_area_with_id("The Submerged Passage", "1_1_4")

        run = self.engine.active_run
        assert run is not None
        tail = len(run.nodes)

        # 未知区域 + 同一条日志重复一次（真机事故的形态）
        self.engine._inject_area_with_id("Some Unknown Zone", "1_1_9")
        self.engine._inject_area_with_id("Some Unknown Zone", "1_1_9")

        # 参考路线没有被作废：没有追加自由节点，剩余参考节点也没被标跳过
        self.assertEqual(len(run.nodes), tail, "不该追加自由节点")
        self.assertFalse(
            any(n.skipped for n in run.nodes[run.current_index + 1:]),
            "剩余参考节点不该被标成跳过",
        )

    def test_two_distinct_unknown_areas_still_diverge(self) -> None:
        """真正的路线分叉（两个不同的未知区域）仍然要能识别。"""
        self.engine.new_run(self._poe1_act1_route())
        self.engine._inject_area_with_id("The Submerged Passage", "1_1_4")
        tail = len(self.engine.active_run.nodes)
        self.engine._inject_area_with_id("Unknown One", "1_1_8")
        self.engine._inject_area_with_id("Unknown Two", "1_1_9")

        run = self.engine.active_run
        assert run is not None
        self.assertEqual(len(run.nodes), tail + 2, "应转为实际记录，追加两个节点")
        self.assertTrue(
            any(n.skipped for n in run.nodes),
            "剩余参考节点应被标成跳过",
        )

    def test_act6_same_name_is_not_treated_as_act1_backtrack(self) -> None:
        """Act 6 的 The Coast（area id 不同）不能被并回 Act 1 的同名节点。"""
        reference = self._reference(
            [
                ("The Coast", "1_1_2"),
                ("The Mud Flats", "1_1_3"),
                ("The Submerged Passage", "1_1_4"),
                ("The Ledge", "1_1_6"),
                ("The Climb", "1_1_7"),
                ("The Lower Prison", "1_1_8"),
                ("The Upper Prison", "1_1_9"),
                ("Prisoner's Gate", "1_1_10"),
                ("The Coast", "2_6_2"),
            ]
        )
        self.engine.new_run(reference)
        self.engine._inject_area_with_id("The Coast", "1_1_2")
        self.engine._inject_area_with_id("The Mud Flats", "1_1_3")
        self.engine._inject_area_with_id("The Submerged Passage", "1_1_4")

        run = self.engine.active_run
        assert run is not None
        # Act 6 的 The Coast：名字相同但 area id 不同 → 不是回退，按参考推进到 index 8
        self.engine._inject_area_with_id("The Coast", "2_6_2")
        self.assertEqual(run.current_index, 8)


if __name__ == "__main__":
    unittest.main()
