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


class _IsolatedEngineCase(unittest.TestCase):
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
        self.engine = RunEngine(load_routelens_config())

    def _reference(self, names: list[str], seconds: float = 10.0) -> ReferenceRoute:
        return ReferenceRoute(
            route_id=f"ref-{'-'.join(names[:2]) or 'empty'}",
            name="ref",
            nodes=[RouteNode(name=name, seconds=seconds) for name in names],
        )


class ReferenceExhaustedTests(_IsolatedEngineCase):
    """参考路线跑完之后的行为（用户 2026-10-29 定稿规则）。

    规则：参考路线模式下**永远不自由记录** —— 节点集合恒等于参考路线。
    参考路线全部跑完后，玩家再进任何地方（回旧节点 / 藏身处 / 新地点），
    时间都记给**最后一个参考节点**，不新增节点。
    """

    def test_no_nodes_appended_after_reference_runs_out(self) -> None:
        self.engine.new_run(self._reference(["A", "B", "C"]))
        for area in ("A", "B", "C"):
            self.engine.simulate_area(area, write_client=False)

        assert self.engine.active_run is not None
        self.assertFalse(self.engine._can_free_record(), "参考模式不该自由记录")

        self.engine.simulate_area("D", write_client=False)
        self.engine.simulate_area("E", write_client=False)

        names = [node.name for node in self.engine.active_run.nodes]
        self.assertEqual(names, ["A", "B", "C"], "参考跑完后不该新增节点")
        # 最后一个参考节点继续计时
        self.assertEqual(self.engine.active_run.current_index, 2)

    def test_time_after_reference_ends_goes_to_last_reference_node(self) -> None:
        self.engine.new_run(self._reference(["A"]))
        for area in ("A", "B", "C"):
            self.engine.simulate_area(area, write_client=False)

        assert self.engine.active_run is not None
        nodes = self.engine.active_run.nodes
        self.assertEqual([n.name for n in nodes], ["A"])
        # 参考跑完后：B、C 的停留时间都归 A（最后一个参考节点）
        self.assertEqual(self.engine.active_run.current_index, 0)
        self.assertEqual(len(nodes), 1, "不该新增节点")
        # A 的用时在离开时才结算；这里直接验证「累计时间归 A」
        self.assertGreater(self.engine.current_segment_seconds(), 0.0)

    def test_delta_keeps_growing_after_reference_ends(self) -> None:
        """参考跑完后差值继续增长（后续时间算进最后一个参考节点）。

        旧行为是「冻结差值」——因为旧逻辑把后续时间算到参考路线之外的
        自由节点上，不参与参考对比。按新规则（后续时间归最后一个参考节点），
        差值 = 本次总时间 - 参考总时间，会如实反映「你比参考慢了多少」。
        """
        reference = self._reference(["A", "B"], seconds=100.0)
        self.engine.store.save_route(reference)
        self.engine.new_run(reference)
        self.engine.simulate_area("A", write_client=False)
        self.engine.simulate_area("B", write_client=False)
        self.engine.simulate_area("C", write_client=False)

        first = self.engine.comparison_delta_seconds()
        assert first is not None
        self.engine.simulate_area("D", write_client=False)
        second = self.engine.comparison_delta_seconds()
        assert second is not None
        self.assertGreater(second, first, "后续时间应计入差值")

    def test_mid_reference_unknown_area_is_still_ignored(self) -> None:
        self.engine.new_run(self._reference(["A", "B", "C"]))
        self.engine.simulate_area("A", write_client=False)
        # 参考还有未跑完节点：未知区域不能插进路线中间造成错位
        self.engine.simulate_area("X", write_client=False)

        assert self.engine.active_run is not None
        self.assertEqual([n.name for n in self.engine.active_run.nodes], ["A", "B", "C"])


class DivergenceTests(_IsolatedEngineCase):
    """参考路线模式**不存在「路线分叉」**（用户 2026-10-29 定稿）。

    规则：只在「当前节点之后」找下一个参考节点；找不到 → 时间记给当前节点。
    节点集合恒等于参考路线：不新增、不作废。

    旧行为（已删除）：攒 2 个未知区域 → 判定分叉 → 追加自由节点 +
    剩余参考节点全标 skipped。正是 2026-10-28 那 28.3 分钟蒸发的根因。
    """

    def test_unknown_areas_do_not_diverge(self) -> None:
        self.engine.new_run(self._reference(["A", "B", "C", "D", "E"]))
        self.engine.simulate_area("A", write_client=False)
        self.engine.simulate_area("B", write_client=False)

        # 走的不是参考那条路：连续两个区域都不在参考里
        self.engine.simulate_area("X1", write_client=False)
        self.engine.simulate_area("X2", write_client=False)

        assert self.engine.active_run is not None
        names = [n.name for n in self.engine.active_run.nodes]
        self.assertEqual(names, ["A", "B", "C", "D", "E"], "不该新增节点")
        self.assertFalse(any(n.skipped for n in self.engine.active_run.nodes))
        self.assertEqual(self.engine.active_run.current_index, 1, "不该换节点")

    def test_single_unknown_area_then_back_is_not_divergence(self) -> None:
        self.engine.new_run(self._reference(["A", "B", "C", "D"]))
        self.engine.simulate_area("A", write_client=False)
        self.engine.simulate_area("B", write_client=False)

        # 回城后回到参考路径
        self.engine.simulate_area("Unknown Town", write_client=False)
        self.engine.simulate_area("C", write_client=False)

        assert self.engine.active_run is not None
        self.assertEqual(
            [n.name for n in self.engine.active_run.nodes], ["A", "B", "C", "D"]
        )
        self.assertFalse(any(n.skipped for n in self.engine.active_run.nodes))
        # 回到参考路径后正常推进到 C
        self.assertEqual(self.engine.active_run.current_index, 2)

    def test_recent_repeat_does_not_accumulate_divergence(self) -> None:
        self.engine.new_run(self._reference(["A", "B", "C", "D"]))
        self.engine.simulate_area("A", write_client=False)
        self.engine.simulate_area("B", write_client=False)

        # 反复回城到刚跑过的区域
        for _ in range(3):
            self.engine.simulate_area("B", write_client=False)
            self.engine.simulate_area("A", write_client=False)

        assert self.engine.active_run is not None
        self.assertFalse(any(n.skipped for n in self.engine.active_run.nodes))
        self.assertEqual(
            [n.name for n in self.engine.active_run.nodes], ["A", "B", "C", "D"]
        )


class BlankRouteTests(_IsolatedEngineCase):
    def test_blank_reference_records_every_area(self) -> None:
        self.engine.new_run(self._reference([]))
        for area in ("Lioneye's Watch", "The Coast", "The Mud Flats"):
            self.engine.simulate_area(area, write_client=False)

        assert self.engine.active_run is not None
        self.assertEqual(
            [n.name for n in self.engine.active_run.nodes],
            ["Lioneye's Watch", "The Coast", "The Mud Flats"],
        )

    def test_no_reference_run_records_every_area(self) -> None:
        self.engine.new_run(None)
        for area in ("A", "B"):
            self.engine.simulate_area(area, write_client=False)

        assert self.engine.active_run is not None
        # 自由路线预置第一幕固定起点（PoE1 = 1_1_1 The Twilight Strand）
        self.assertEqual(
            [n.name for n in self.engine.active_run.nodes],
            ["The Twilight Strand", "A", "B"],
        )
        self.assertIsNone(self.engine.comparison_delta_seconds())

    def test_hideout_is_never_recorded(self) -> None:
        self.engine.new_run(None)
        self.engine.simulate_area("A", write_client=False)
        self.engine.simulate_area("Lush Hideout", write_client=False)
        self.engine.simulate_area("B", write_client=False)

        assert self.engine.active_run is not None
        self.assertEqual(
            [n.name for n in self.engine.active_run.nodes],
            ["The Twilight Strand", "A", "B"],
        )


if __name__ == "__main__":
    unittest.main()
