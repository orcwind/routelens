"""回归：参考路线模式的「只看本节点之后」规则（用户 2026-10-29 定稿）。

规则原文：

    1 先讨论最多的情况，也就是读取路线（非从0路线），情况A：
       只看本节点之后的路线，不看之前的。举例读取路线是 A B C D E，
       而实际游戏是 ACBDE，则在C之后，是不看AB的，只看下一个D以及后续的。
       这时不管是回到了A，还是去了新地点B，或藏身处，
       只要不在C之后的读取路线的节点，都将这些时间记为C的时间。

    2 如果是新建路线，也就是从0开始，那么是什么节点就记录什么。
       但是依然遵循重复/藏身处规则。

核心不变量：

    参考路线模式下**节点集合恒等于参考路线**
    —— 不新增节点、不作废参考节点、不存在「路线分叉」。
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

    def _reference(self, names: list[str]) -> ReferenceRoute:
        return ReferenceRoute(
            route_id="ref-abcde",
            name="A-E",
            nodes=[RouteNode(name=name, seconds=10.0) for name in names],
        )


class ReferenceForwardRuleTests(_Case):
    """规则 1：参考路线模式。"""

    def test_node_set_always_equals_reference(self) -> None:
        """参考路线 A B C D E，玩家乱跑 → 节点数恒等于 5。"""
        self.engine.new_run(self._reference(["A", "B", "C", "D", "E"]))
        for area in ("A", "C", "B", "D", "E", "X", "A", "Y"):
            self.engine.simulate_area(area, write_client=False)

        run = self.engine.active_run
        assert run is not None
        self.assertEqual(
            [n.name for n in run.nodes],
            ["A", "B", "C", "D", "E"],
            "参考路线模式下节点集合恒等于参考路线",
        )

    def test_backtrack_to_earlier_node_keeps_current(self) -> None:
        """回到当前节点之前的参考节点 → 不换节点，时间归当前节点。"""
        self.engine.new_run(self._reference(["A", "B", "C", "D", "E"]))
        self.engine.simulate_area("A", write_client=False)
        self.engine.simulate_area("B", write_client=False)
        self.engine.simulate_area("C", write_client=False)

        run = self.engine.active_run
        assert run is not None
        self.assertEqual(run.current_index, 2, "当前节点是 C")

        # 回到 B（在 C 之前）→ 不换节点
        self.engine.simulate_area("B", write_client=False)
        self.assertEqual(run.current_index, 2, "回到旧节点不该换节点")

    def test_unknown_area_keeps_current(self) -> None:
        """参考路线外的新地点 → 不换节点、不新增节点。"""
        self.engine.new_run(self._reference(["A", "B", "C"]))
        self.engine.simulate_area("A", write_client=False)
        self.engine.simulate_area("B", write_client=False)

        run = self.engine.active_run
        assert run is not None
        self.engine.simulate_area("Some Side Area", write_client=False)

        self.assertEqual(run.current_index, 1, "不该换节点")
        self.assertEqual(len(run.nodes), 3, "不该新增节点")

    def test_time_lands_on_current_node(self) -> None:
        """在旧节点停留的时间，最终算到当前节点头上。"""
        self.engine.new_run(self._reference(["A", "B", "C", "D"]))
        self.engine.simulate_area("A", write_client=False)
        self.engine.simulate_area("B", write_client=False)
        self.engine.simulate_area("C", write_client=False)

        run = self.engine.active_run
        assert run is not None
        self.assertEqual(run.current_index, 2, "当前节点是 C")

        # 回旧节点 B 停留 —— 时间继续算在 C 上（不换节点）
        self.engine.active_run.elapsed_seconds = 100.0
        self.engine._timer_started_at = None
        self.engine.simulate_area("B", write_client=False)
        self.assertEqual(run.current_index, 2, "回到旧节点不该换节点")

        # 推进到 D 时，C 收尾 —— C 的用时应包含在 B 停留的那段时间
        self.engine.active_run.elapsed_seconds = 160.0
        self.engine._timer_started_at = None
        self.engine.simulate_area("D", write_client=False)

        self.assertEqual(run.current_index, 3, "应推进到 D")
        self.assertTrue(run.nodes[2].visited, "C 应有真实用时")
        self.assertIsNotNone(run.nodes[2].seconds)

    def test_no_divergence_concept(self) -> None:
        """连续多个参考外区域也不判定分叉（分叉概念已删除）。"""
        self.engine.new_run(self._reference(["A", "B", "C", "D", "E"]))
        self.engine.simulate_area("A", write_client=False)
        self.engine.simulate_area("B", write_client=False)

        run = self.engine.active_run
        assert run is not None
        for area in ("X1", "X2", "X3"):
            self.engine.simulate_area(area, write_client=False)

        self.assertEqual(len(run.nodes), 5, "不该新增节点")
        self.assertFalse(
            any(n.skipped for n in run.nodes[run.current_index + 1:]),
            "剩余参考节点不该被标成跳过",
        )

    def test_reference_exhausted_keeps_last_node(self) -> None:
        """参考路线跑完后，继续游玩 → 时间归最后一个参考节点，不新增节点。"""
        self.engine.new_run(self._reference(["A", "B"]))
        self.engine.simulate_area("A", write_client=False)
        self.engine.simulate_area("B", write_client=False)

        run = self.engine.active_run
        assert run is not None
        self.assertEqual(run.current_index, 1)

        self.engine.simulate_area("Anything", write_client=False)
        self.engine.simulate_area("Elsewhere", write_client=False)

        self.assertEqual(len(run.nodes), 2, "不该新增节点")
        self.assertEqual(run.current_index, 1, "不该换节点")


class BlankRouteRuleTests(_Case):
    """规则 2：新建路线模式 —— 什么节点记录什么，但遵循重复 / 藏身处规则。"""

    def test_records_every_new_area(self) -> None:
        self.engine.new_run(None)
        for area in ("A", "B", "C"):
            self.engine.simulate_area(area, write_client=False)

        run = self.engine.active_run
        assert run is not None
        names = [n.name for n in run.nodes]
        self.assertIn("A", names)
        self.assertIn("B", names)
        self.assertIn("C", names)

    def test_repeat_does_not_add_node(self) -> None:
        """重复进入已去过的地点 → 不新增节点。"""
        self.engine.new_run(None)
        self.engine.simulate_area("Zone A", write_client=False)
        self.engine.simulate_area("Zone B", write_client=False)
        self.engine.simulate_area("Zone A", write_client=False)

        run = self.engine.active_run
        assert run is not None
        names = [n.name for n in run.nodes]
        self.assertEqual(names.count("Zone A"), 1, "重复地点不该新增节点")

    def test_repeat_keeps_current_node_and_time(self) -> None:
        """重复进入已去过的地点 → **当作没有换节点**。

        用户 2026-10-29 定稿：
        重复不新增节点，**时间也不并回重复节点**，而是当作没有换节点
        —— 这段时间算在**当前节点**上（与参考路线模式完全一致）。
        """
        self.engine.new_run(None)
        self.engine.simulate_area("Zone A", write_client=False)
        self.engine.simulate_area("Zone B", write_client=False)

        run = self.engine.active_run
        assert run is not None
        # 注意：新建路线会预置第一幕固定起点（index 0），所以 Zone B 不是 index 1
        zone_b_index = next(i for i, n in enumerate(run.nodes) if n.name == "Zone B")
        zone_a_index = next(i for i, n in enumerate(run.nodes) if n.name == "Zone A")
        self.assertEqual(run.current_index, zone_b_index, "当前节点是 Zone B")

        self.engine.active_run.elapsed_seconds = 60.0
        self.engine._timer_started_at = None
        # 回到 Zone A
        self.engine.simulate_area("Zone A", write_client=False)

        self.assertEqual(run.current_index, zone_b_index, "重复不该换节点")
        self.assertEqual(len(run.nodes), 3, "重复不该新增节点")
        # Zone A 只保留第一次停留的 30s —— 回访的 30s 没有并回它
        self.assertLessEqual(run.nodes[zone_a_index].seconds or 0.0, 30.0)
        # 回访期间的时间归当前节点（Zone B）—— 它尚未离开，所以时间在累计段里
        self.assertGreater(self.engine.current_segment_seconds(), 0.0)

    def test_hideout_is_never_a_node(self) -> None:
        """藏身处不产生节点（时间留在当前节点）。"""
        self.engine.new_run(None)
        self.engine.simulate_area("A", write_client=False)
        self.engine.simulate_area("Lush Hideout", write_client=False)
        self.engine.simulate_area("B", write_client=False)

        run = self.engine.active_run
        assert run is not None
        self.assertNotIn("Lush Hideout", [n.name for n in run.nodes])


class ResetRunKeepsReferenceModeTests(_Case):
    """真机事故 2026-10-29 14:16：重置 Run 后必须仍是**参考路线模式**。

    事故现象：点「重置 Run」后再也不换节点 —— 26 分钟全堆在 node 0。

    根因：``reset_run()`` 构造 ``ActiveRun`` 时漏传 ``is_reference_mode``
    → 落回 ``False``，但 ``nodes`` 仍是 145 个参考节点
    → 走新建路线分支 → 每个区域都被 ``_find_revisited_node``
    判成「重复进入已去过的地点」→ 永不换节点。
    """

    def test_reset_keeps_reference_mode(self) -> None:
        self.engine.new_run(self._reference(["A", "B", "C", "D", "E"]))
        self.engine.simulate_area("A", write_client=False)
        self.engine.simulate_area("B", write_client=False)

        self.engine.reset_run()

        run = self.engine.active_run
        assert run is not None
        self.assertTrue(
            run.is_reference_mode,
            "重置后仍是参考路线模式（有参考节点就不该退回新建路线模式）",
        )
        self.assertEqual(len(run.nodes), 5, "重置后节点集合仍等于参考路线")
        self.assertEqual(run.current_index, 0, "重置后回到起点")

    def test_reset_then_areas_advance_nodes(self) -> None:
        """重置后再进图 → 节点必须继续推进（事故的直接复现路径）。"""
        self.engine.new_run(self._reference(["A", "B", "C", "D", "E"]))
        self.engine.simulate_area("A", write_client=False)
        self.engine.reset_run()

        self.engine.simulate_area("A", write_client=False)
        self.engine.simulate_area("B", write_client=False)
        self.engine.simulate_area("C", write_client=False)

        run = self.engine.active_run
        assert run is not None
        self.assertEqual(run.current_index, 2, "重置后节点必须继续推进（C）")
        self.assertEqual(len(run.nodes), 5, "不该新增节点")

    def test_reset_preserves_area_id(self) -> None:
        """重置后参考节点要保住 area_id（精确匹配靠它）。"""
        from routelens.models import ReferenceRoute, RouteNode

        route = ReferenceRoute(
            route_id="ref-area",
            name="area",
            nodes=[
                RouteNode(name="A", seconds=10.0, area_id="1_1_1"),
                RouteNode(name="B", seconds=10.0, area_id="1_1_2"),
            ],
        )
        self.engine.new_run(route)
        self.engine.reset_run()

        run = self.engine.active_run
        assert run is not None
        self.assertEqual(run.nodes[0].area_id, "1_1_1")
        self.assertEqual(run.nodes[1].area_id, "1_1_2")

    def test_reset_preserves_game_id(self) -> None:
        """重置后要保住 game_id（否则幕归属判错）。"""
        self.engine.new_run(self._reference(["A", "B"]))
        self.engine.reset_run()

        run = self.engine.active_run
        assert run is not None
        self.assertEqual(run.game_id, "poe1", "重置后 game_id 不能丢")


class CorruptedModeHealsOnLoadTests(unittest.TestCase):
    """存档自愈：``is_reference_mode`` 与事实矛盾时以事实为准。

    真机事故 2026-10-29 14:16：``reset_run()`` 漏传 ``is_reference_mode``
    → 存档写成 ``False``，节点却还是 145 个参考节点
    → 每次进图都被判成「重复进入已去过的地点」→ 永不换节点。
    """

    def test_false_mode_with_many_nodes_heals_to_true(self) -> None:
        from routelens.models import ActiveRun

        run = ActiveRun.from_dict(
            {
                "reference_route_id": "ref-1",
                "reference_route_name": "long route",
                "is_reference_mode": False,
                "nodes": [
                    {"name": "A", "seconds": None, "completed": False},
                    {"name": "B", "seconds": None, "completed": False},
                    {"name": "C", "seconds": None, "completed": False},
                ],
            }
        )
        self.assertTrue(run.is_reference_mode, "多节点 + 有 route_id → 应自愈为参考模式")

    def test_free_run_with_many_nodes_stays_false(self) -> None:
        """空白路线跑出多节点后**不能**被误判成参考模式。"""
        from routelens.models import ActiveRun

        run = ActiveRun.from_dict(
            {
                "reference_route_id": None,
                "reference_route_name": "",
                "is_reference_mode": False,
                "nodes": [
                    {"name": "Zone A", "seconds": 30.0, "completed": True},
                    {"name": "Zone B", "seconds": 20.0, "completed": True},
                ],
            }
        )
        self.assertFalse(run.is_reference_mode, "空白路线（无 route_id）不能被自愈成参考模式")

    def test_seed_only_run_stays_false(self) -> None:
        """只有 1 个种子节点的 run → 仍是新建路线模式。"""
        from routelens.models import ActiveRun

        run = ActiveRun.from_dict(
            {
                "reference_route_id": None,
                "is_reference_mode": False,
                "nodes": [{"name": "河岸", "seconds": None, "completed": False}],
            }
        )
        self.assertFalse(run.is_reference_mode)


class RunNodeInvariantTests(unittest.TestCase):
    """``RunNode`` 唯一不变量：seconds 有值 ⇔ 本次到过；两者互斥。"""

    def test_mark_visited_and_mark_skipped_are_exclusive(self) -> None:
        from routelens.models import RunNode

        node = RunNode(name="A")
        self.assertFalse(node.visited)
        node.mark_visited(12.5)
        self.assertTrue(node.visited)
        self.assertFalse(node.skipped)

        other = RunNode(name="B")
        other.mark_skipped()
        self.assertFalse(other.visited)
        self.assertTrue(other.skipped)
        self.assertIsNone(other.seconds)

    def test_from_dict_repairs_broken_state(self) -> None:
        """老存档里「有时间 + skipped」的自相矛盾状态要被修好。"""
        from routelens.models import RunNode

        node = RunNode.from_dict(
            {"name": "B", "seconds": 87.0, "completed": True, "skipped": True}
        )
        self.assertFalse(node.skipped)
        self.assertTrue(node.visited)
        self.assertEqual(node.seconds, 87.0)


if __name__ == "__main__":
    unittest.main()
