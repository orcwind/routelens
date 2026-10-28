"""回归：幕行用时之和必须等于总时间（用时不能凭空消失）。

真机事故 2026-10-28（PoE1，参考路线 ``10-26 16:02``，145 节点）：

    总时间 1:06:37（3997.8s）
    幕行合计 2296.8s（Act1 1466.8 + Act2 830.0）
    差额 1697.9s = 28.3 分钟，挂在 24 个 ``skipped`` 节点上

三个独立缺陷：

1. **跳段把真跑过的节点标成 skipped**：玩家实打实跑过的 Act 2 后半 / Act 3 /
   Act 4 节点（The Wetlands / The City of Sarn / The Aqueduct …）有真实 seconds，
   却被 ``前进跳段`` 标成 ``skipped=True`` → 统计时排除 → 时间蒸发。
2. **area id 精确匹配被窗口限制**：参考路线把 Act 3 的 The Fellshrine Ruins
   (1_2_15) 插在 Act 2 节点中间（index 37），玩家跑到它时因超出 15 窗口被拒
   → 累积 2 次「未知区域」→ 判定路线分叉 → 剩余 100 个节点全废。
3. **分叉后追加的自由节点不带 area_id** → 判不出幕 → 那段时间不进任何幕行。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import PropertyMock, patch

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.act_map import detect_act  # noqa: E402
from routelens.act_timing import build_act_timing  # noqa: E402
from routelens.companion_config import CompanionConfig  # noqa: E402
from routelens.config import load_routelens_config  # noqa: E402
from routelens.engine import RunEngine  # noqa: E402
from routelens.models import ActiveRun, ReferenceRoute, RouteNode  # noqa: E402


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
        return ReferenceRoute(
            route_id="ref",
            name="ref",
            nodes=[
                RouteNode(name=name, seconds=10.0, area_id=area_id)
                for name, area_id in nodes
            ],
        )

    def _act_sum(self, run: ActiveRun) -> float:
        """幕行用时之和（复刻 gui._build_act_rows 的取数口径）。"""
        splits = []
        for index, node in enumerate(run.nodes):
            if node.completed and node.skipped:
                continue
            if not node.completed and index != run.current_index:
                continue
            splits.append(
                {
                    "area": node.name,
                    "area_id": node.area_id,
                    "segment_seconds": node.seconds or 0.0,
                }
            )
        return build_act_timing(splits, "poe1").total_seconds

    def _node_sum(self, run: ActiveRun) -> float:
        return sum(node.seconds or 0.0 for node in run.nodes)


class SkippedWithTimeTests(_Case):
    """缺陷 1：跳段不能把已有真实用时的节点标成 skipped。"""

    def test_forward_skip_keeps_already_timed_nodes(self) -> None:
        """玩家真跑过的节点（已有 seconds）不能被跳段标成 skipped。"""
        reference = self._reference(
            [
                ("A", "1_1_1"),
                ("B", "1_1_2"),
                ("C", "1_1_3"),
                ("D", "1_1_4"),
            ]
        )
        self.engine.new_run(reference)
        # 玩家依次跑过 A、B、C（各自留下真实用时）
        self.engine._inject_area_with_id("A", "1_1_1")
        self.engine._inject_area_with_id("B", "1_1_2")
        run = self.engine.active_run
        assert run is not None
        # C 已被玩家跑过并记录了用时（completed=True, skipped=False）
        run.nodes[2].seconds = 55.0
        run.nodes[2].completed = True
        run.nodes[2].skipped = False

        # 玩家跳到 D
        self.engine._inject_area_with_id("D", "1_1_4")

        self.assertFalse(run.nodes[2].skipped, "有真实用时的节点不能标 skipped")
        self.assertEqual(run.nodes[2].seconds, 55.0)

    def test_forward_skip_marks_untouched_nodes_as_skipped(self) -> None:
        """对照组：玩家没跑过的节点仍应被标 skipped（seconds=None）。"""
        reference = self._reference(
            [("A", "1_1_1"), ("B", "1_1_2"), ("C", "1_1_3"), ("D", "1_1_4")]
        )
        self.engine.new_run(reference)
        self.engine._inject_area_with_id("A", "1_1_1")
        self.engine._inject_area_with_id("D", "1_1_4")

        run = self.engine.active_run
        assert run is not None
        self.assertTrue(run.nodes[1].skipped)
        self.assertIsNone(run.nodes[1].seconds)
        self.assertTrue(run.nodes[2].skipped)

    def test_repair_skipped_with_time_on_load(self) -> None:
        """缺陷 1 的存量数据修复：历史 run 里的 skipped+有时间的节点要恢复。"""
        run = ActiveRun(
            run_id="r",
            reference_route_id="ref",
            reference_route_name="ref",
            nodes=[
                _node("A", "1_1_1", 10.0, completed=True),
                _node("B", "1_1_2", 20.0, completed=True, skipped=True),
                _node("C", "1_1_3", 0.0, completed=True, skipped=True),
            ],
        )
        self.engine._repair_skipped_with_time(run)
        self.assertFalse(run.nodes[1].skipped)
        self.assertEqual(run.nodes[1].seconds, 20.0)
        # 真正跳过（无时间）的保持跳过
        self.assertTrue(run.nodes[2].skipped)


class ExactAreaIdMatchTests(_Case):
    """缺陷 2：area id 精确匹配不受「向前识别窗口」限制。"""

    def test_area_id_match_beyond_window_is_accepted(self) -> None:
        """The Fellshrine Ruins (1_2_15) 在 index 39，超窗口 15。"""
        nodes = [("Act1 Zone", f"1_1_{i}") for i in range(1, 40)]
        nodes.append(("The Fellshrine Ruins", "1_2_15"))
        nodes.append(("The Crypt Level 1", "1_2_5_1"))
        self.engine.new_run(self._reference(nodes))

        self.engine._inject_area_with_id("Act1 Zone", "1_1_1")
        run = self.engine.active_run
        assert run is not None
        self.assertEqual(run.current_index, 0)

        # 直接跳到 index 39 的 The Fellshrine Ruins（远超窗口）
        self.engine._inject_area_with_id("The Fellshrine Ruins", "1_2_15")
        self.assertEqual(run.current_index, 39, "area id 精确匹配应被接受")
        # 关键：不能因为「超出窗口」而把它当成未知区域 → 后续触发分叉
        self.assertFalse(
            any(n.skipped for n in run.nodes[40:]),
            "分叉后剩余参考节点不该被标跳过",
        )
        self.assertEqual(len(run.nodes), 41, "不该追加自由节点（参考路线仍然有效）")


class FreeNodeAreaIdTests(_Case):
    """缺陷 3：分叉后追加的自由节点必须带 area id（否则判不出幕）。"""

    def test_diverged_free_nodes_carry_area_id(self) -> None:
        self.engine.new_run(self._reference([("A", "1_1_1"), ("B", "1_1_2"), ("C", "1_1_3")]))
        self.engine._inject_area_with_id("A", "1_1_1")
        self.engine._inject_area_with_id("B", "1_1_2")

        # 两个未知区域 → 分叉
        self.engine._inject_area_with_id("Unknown One", "1_2_9")
        self.engine._inject_area_with_id("Unknown Two", "1_2_10")

        run = self.engine.active_run
        assert run is not None
        free = [n for n in run.nodes if n.area_id in {"1_2_9", "1_2_10"}]
        self.assertEqual(len(free), 2, "自由节点应带 area id")
        for node in free:
            info = detect_act(node.area_id, "poe1")
            self.assertEqual(info.act, 2, "自由节点应能判出幕")


class ActSumMatchesTotalTests(_Case):
    """端到端：跑完一段路线后，幕行用时之和 == 节点用时总和。"""

    def test_act_sum_equals_node_sum(self) -> None:
        reference = self._reference(
            [
                ("The Twilight Strand", "1_1_1"),
                ("Lioneye's Watch", "1_1_town"),
                ("The Coast", "1_1_2"),
                ("The Mud Flats", "1_1_3"),
                ("The Submerged Passage", "1_1_4"),
                ("The Broken Bridge", "1_2_4"),
                ("The Riverways", "1_2_7"),
                ("The Wetlands", "1_2_12"),
                ("The City of Sarn", "1_3_1"),
                ("The Sarn Encampment", "1_3_town"),
                ("The Aqueduct", "1_4_1"),
            ]
        )
        self.engine.new_run(reference)
        for name, area_id in [
            ("The Twilight Strand", "1_1_1"),
            ("Lioneye's Watch", "1_1_town"),
            ("The Coast", "1_1_2"),
            ("The Mud Flats", "1_1_3"),
            ("The Submerged Passage", "1_1_4"),
            ("The Broken Bridge", "1_2_4"),
            ("The Riverways", "1_2_7"),
            ("The Wetlands", "1_2_12"),
            ("The City of Sarn", "1_3_1"),
            ("The Sarn Encampment", "1_3_town"),
            ("The Aqueduct", "1_4_1"),
        ]:
            self.engine._inject_area_with_id(name, area_id)

        run = self.engine.active_run
        assert run is not None
        node_sum = self._node_sum(run)
        act_sum = self._act_sum(run)
        self.assertGreater(node_sum, 0.0)
        self.assertAlmostEqual(
            act_sum,
            node_sum,
            delta=1.0,
            msg=f"幕行合计 {act_sum} 应等于节点总和 {node_sum}",
        )


def _node(name, area_id, seconds, completed=True, skipped=False):
    from routelens.models import RunNode

    return RunNode(
        name=name,
        seconds=seconds,
        completed=completed,
        skipped=skipped,
        area_id=area_id,
    )


if __name__ == "__main__":
    unittest.main()
