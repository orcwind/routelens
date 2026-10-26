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
    def test_appends_nodes_after_reference_runs_out(self) -> None:
        self.engine.new_run(self._reference(["A", "B", "C"]))
        for area in ("A", "B", "C"):
            self.engine.simulate_area(area, write_client=False)

        assert self.engine.active_run is not None
        self.assertTrue(self.engine._can_free_record())

        self.engine.simulate_area("D", write_client=False)
        self.engine.simulate_area("E", write_client=False)

        names = [node.name for node in self.engine.active_run.nodes]
        self.assertEqual(names, ["A", "B", "C", "D", "E"])
        # 最后一个节点是「当前正在计时」的节点
        self.assertEqual(self.engine.active_run.current_index, 4)
        self.assertFalse(self.engine.active_run.nodes[4].completed)
        self.assertTrue(self.engine.active_run.nodes[3].completed)
        self.assertIsNotNone(self.engine.active_run.nodes[3].seconds)

    def test_free_nodes_get_their_own_seconds(self) -> None:
        self.engine.new_run(self._reference(["A"]))
        for area in ("A", "B", "C"):
            self.engine.simulate_area(area, write_client=False)

        assert self.engine.active_run is not None
        nodes = self.engine.active_run.nodes
        self.assertEqual([n.name for n in nodes], ["A", "B", "C"])
        self.assertTrue(nodes[0].completed)
        self.assertTrue(nodes[1].completed)
        self.assertIsNotNone(nodes[1].seconds)

    def test_recent_repeat_is_not_appended(self) -> None:
        self.engine.new_run(self._reference(["A"]))
        for area in ("A", "B", "C"):
            self.engine.simulate_area(area, write_client=False)
        # 回城 / 折返：刚跑过的区域不应变成新节点
        self.engine.simulate_area("C", write_client=False)
        self.engine.simulate_area("B", write_client=False)

        assert self.engine.active_run is not None
        self.assertEqual([n.name for n in self.engine.active_run.nodes], ["A", "B", "C"])

    def test_total_delta_freezes_after_reference_ends(self) -> None:
        reference = self._reference(["A", "B"], seconds=100.0)
        self.engine.store.save_route(reference)
        self.engine.new_run(reference)
        self.engine.simulate_area("A", write_client=False)
        self.engine.simulate_area("B", write_client=False)
        self.engine.simulate_area("C", write_client=False)

        frozen = self.engine.comparison_delta_seconds()
        assert frozen is not None
        self.engine.simulate_area("D", write_client=False)
        self.assertEqual(self.engine.comparison_delta_seconds(), frozen)

    def test_mid_reference_unknown_area_is_still_ignored(self) -> None:
        self.engine.new_run(self._reference(["A", "B", "C"]))
        self.engine.simulate_area("A", write_client=False)
        # 参考还有未跑完节点：未知区域不能插进路线中间造成错位
        self.engine.simulate_area("X", write_client=False)

        assert self.engine.active_run is not None
        self.assertEqual([n.name for n in self.engine.active_run.nodes], ["A", "B", "C"])


class DivergenceTests(_IsolatedEngineCase):
    def test_divergence_after_two_unknown_areas(self) -> None:
        self.engine.new_run(self._reference(["A", "B", "C", "D", "E"]))
        self.engine.simulate_area("A", write_client=False)
        self.engine.simulate_area("B", write_client=False)

        # 走的不是参考那条路（跨幕 / 实际路线不同）：连续两个区域都不在参考里
        self.engine.simulate_area("X1", write_client=False)
        self.engine.simulate_area("X2", write_client=False)

        assert self.engine.active_run is not None
        names = [n.name for n in self.engine.active_run.nodes]
        self.assertEqual(names, ["A", "B", "C", "D", "E", "X1", "X2"])
        self.assertTrue(self.engine.active_run.nodes[2].skipped)
        self.assertTrue(self.engine.active_run.nodes[4].skipped)
        self.assertTrue(self.engine.active_run.nodes[5].completed)
        self.assertFalse(self.engine.active_run.nodes[6].completed)

    def test_single_unknown_area_then_back_is_not_divergence(self) -> None:
        self.engine.new_run(self._reference(["A", "B", "C", "D"]))
        self.engine.simulate_area("A", write_client=False)
        self.engine.simulate_area("B", write_client=False)

        # 回城后回到参考路径：不应当成路线分叉
        self.engine.simulate_area("Unknown Town", write_client=False)
        self.engine.simulate_area("C", write_client=False)

        assert self.engine.active_run is not None
        self.assertEqual(
            [n.name for n in self.engine.active_run.nodes], ["A", "B", "C", "D"]
        )
        self.assertFalse(any(n.skipped for n in self.engine.active_run.nodes))

    def test_recent_repeat_does_not_accumulate_divergence(self) -> None:
        self.engine.new_run(self._reference(["A", "B", "C", "D"]))
        self.engine.simulate_area("A", write_client=False)
        self.engine.simulate_area("B", write_client=False)

        # 反复回城到刚跑过的区域：不应触发分叉
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
