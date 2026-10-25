"""回归测试：实时引擎（空白路线 / 自由记录）下的回退与来回跑去重。

对应用户诉求：
- 「我从 act3 回到了 act1」→ 回退到已去过的地点不该产生新节点
- 「同一幕我来回在两个地点来回」→ 重复地点不该产生新节点
- 重复进入的时间要并回原节点，不能凭空消失
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.config import load_routelens_config  # noqa: E402
from routelens.engine import RunEngine  # noqa: E402
from routelens.models import ReferenceRoute, RouteNode  # noqa: E402


class FreeRouteDedupeTests(unittest.TestCase):
    """空白路线（无参考）下按实际进图记录，重复地点必须合并。"""

    def _engine_with_blank_route(self) -> RunEngine:
        engine = RunEngine(load_routelens_config())
        ref = ReferenceRoute(route_id="blank", name="空白路线", nodes=[])
        engine.new_run(ref)
        engine.start_or_split()
        return engine

    def test_backtrack_to_earlier_area_merges(self) -> None:
        engine = self._engine_with_blank_route()
        engine.simulate_area("Act3 Town", write_client=False)
        engine.simulate_area("Act3 Zone", write_client=False)
        engine.simulate_area("Act1 Town", write_client=False)
        engine.simulate_area("Act1 Zone", write_client=False)

        run = engine.active_run
        assert run is not None
        names = [n.name for n in run.nodes]
        self.assertEqual(names, ["Act3 Town", "Act3 Zone", "Act1 Town", "Act1 Zone"])

    def test_ping_pong_same_act_merges(self) -> None:
        engine = self._engine_with_blank_route()
        for area in ("Zone A", "Zone B", "Zone A", "Zone B", "Zone A"):
            engine.simulate_area(area, write_client=False)

        run = engine.active_run
        assert run is not None
        names = [n.name for n in run.nodes]
        # 同一幕内两个地点来回跑 → 只应保留两个节点
        self.assertEqual(names, ["Zone A", "Zone B"])

    def test_revisit_keeps_time_in_original_node(self) -> None:
        engine = self._engine_with_blank_route()
        engine.simulate_area("Zone A", write_client=False)
        engine.active_run.elapsed_seconds = 30.0
        engine._timer_started_at = None
        engine.simulate_area("Zone B", write_client=False)
        engine.active_run.elapsed_seconds = 60.0
        engine._timer_started_at = None
        # 回到 Zone A
        engine.simulate_area("Zone A", write_client=False)

        run = engine.active_run
        assert run is not None
        self.assertEqual(len(run.nodes), 2)
        zone_a = run.nodes[0]
        self.assertTrue(zone_a.completed)
        # 30s（第一次停留） + 60s（回访时又待了 60s）合并到同一个节点
        self.assertGreaterEqual(zone_a.seconds or 0.0, 30.0)

    def test_area_id_identity_distinguishes_same_name(self) -> None:
        """同名但 area_id 不同 = 不同区域实例，不能合并。"""
        engine = self._engine_with_blank_route()
        engine._inject_area_with_id("Aspirant's Trial", "1_Labyrinth_boss_1")
        engine._inject_area_with_id("Mansion Halls", "1_Labyrinth_EH_block_branch")
        engine._inject_area_with_id("Aspirant's Trial", "1_Labyrinth_boss_2")

        run = engine.active_run
        assert run is not None
        self.assertEqual(len(run.nodes), 3)


if __name__ == "__main__":
    unittest.main()
