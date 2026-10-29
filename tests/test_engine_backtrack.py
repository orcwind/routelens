"""回归测试：实时引擎（空白路线 / 自由记录）下的回退与来回跑去重。

对应用户诉求：
- 「我从 act3 回到了 act1」→ 回退到已去过的地点不该产生新节点
- 「同一幕我来回在两个地点来回」→ 重复地点不该产生新节点
- 重复进入 → **当作没有换节点**：时间也不并回原节点，算在当前节点上
  （用户 2026-10-29 定稿，与参考路线模式一致）
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.config import load_routelens_config  # noqa: E402
from routelens.engine import RunEngine  # noqa: E402
from routelens.models import ReferenceRoute  # noqa: E402


class FreeRouteDedupeTests(unittest.TestCase):
    """空白路线（无参考）下按实际进图记录，重复地点不产生新节点。"""

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

    def test_revisit_does_not_move_time_to_original_node(self) -> None:
        """重复进入已去过的地点：**时间不并回原节点**（用户 2026-10-29 定稿）。

        新建路线模式下重复进入 → 当作没有换节点：
        - 不新增节点
        - 时间也**不**并回原节点 → 回访的停留时间算在**当前节点**上
        """
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
        # 按名字定位索引，不依赖具体下标
        zone_a_index = next(i for i, n in enumerate(run.nodes) if n.name == "Zone A")
        zone_b_index = next(i for i, n in enumerate(run.nodes) if n.name == "Zone B")
        self.assertEqual(len(run.nodes), 2, "重复不该新增节点")
        zone_a = run.nodes[zone_a_index]
        # 重复进入不换节点 → 当前节点仍是 Zone B
        self.assertEqual(run.current_index, zone_b_index, "重复不该换节点")
        # Zone A 只保留第一次停留的 30s —— 回访的 30s 没有并回它
        self.assertLessEqual(zone_a.seconds or 0.0, 30.5)
        # 回访期间的时间归当前节点（Zone B）—— 它尚未离开，时间在累计段里
        self.assertGreater(engine.current_segment_seconds(), 0.0)

    def test_area_id_identity_distinguishes_same_name(self) -> None:
        """同名但 area_id 不同 = 不同区域实例，不能合并。

        注意：这里用**非试炼**区域。PoE1 迷宫房间（``*_Labyrinth_*``）属于试炼，
        按产品规则要折叠进「进门那一次」，见 ``test_trial_folding.py``。
        """
        engine = self._engine_with_blank_route()
        engine._inject_area_with_id("Aspirant's Trial", "1_6_boss_1")
        engine._inject_area_with_id("Mansion Halls", "1_6_EH_block_branch")
        engine._inject_area_with_id("Aspirant's Trial", "1_6_boss_2")

        run = engine.active_run
        assert run is not None
        self.assertEqual(len(run.nodes), 3)


class LiveTrialFoldingTests(unittest.TestCase):
    """实时引擎：一次试炼只记进门那一次（用户 2026-10-25 定）。"""

    def _engine_with_blank_route(self, game: str = "poe1") -> RunEngine:
        config = load_routelens_config()
        config.game = game
        engine = RunEngine(config)
        ref = ReferenceRoute(route_id="blank", name="空白路线", nodes=[])
        engine.new_run(ref)
        engine.start_or_split()
        return engine

    def test_poe1_labyrinth_rooms_merged_into_entry(self) -> None:
        engine = self._engine_with_blank_route("poe1")
        engine._inject_area_with_id("Aspirants' Plaza", "Labyrinth_Airlock")
        engine._inject_area_with_id("Estate Path", "1_Labyrinth_OH_straight")
        engine._inject_area_with_id("Aspirant's Trial", "1_Labyrinth_boss_1")
        engine._inject_area_with_id("Sepulchre Halls", "1_Labyrinth_C_branch_bottleneck_2")
        engine._inject_area_with_id("Aspirant's Trial", "1_Labyrinth_boss_2")
        engine._inject_area_with_id("The Sarn Encampment", "1_3_town")

        run = engine.active_run
        assert run is not None
        # 试炼房间不单独成节点
        names = [n.name for n in run.nodes]
        self.assertEqual(names, ["Aspirants' Plaza", "The Sarn Encampment"])
        self.assertTrue(run.nodes[0].is_trial_entry)

    def test_poe2_chaos_trial_airlock_and_body_are_one_node(self) -> None:
        engine = self._engine_with_blank_route("poe2")
        engine._inject_area_with_id("混沌神殿", "G3_10_Airlock")
        engine._inject_area_with_id("混沌試煉", "G3_10")
        engine._inject_area_with_id("混沌神殿", "G3_10_Airlock")
        engine._inject_area_with_id("混沌試煉", "G3_10")
        engine._inject_area_with_id("皆伐營地", "G1_town")

        run = engine.active_run
        assert run is not None
        names = [n.name for n in run.nodes]
        # 混沌神殿 ↔ 混沌試煉 来回 = 同一次试炼 → 1 个节点
        self.assertEqual(len(names), 2)
        self.assertEqual(names[0], "混沌試煉")
        self.assertTrue(run.nodes[0].is_trial_entry)

    def test_multiple_trials_each_recorded(self) -> None:
        engine = self._engine_with_blank_route("poe1")
        engine._inject_area_with_id("Aspirants' Plaza", "Labyrinth_Airlock")
        engine._inject_area_with_id("Estate Path", "1_Labyrinth_OH_straight")
        engine._inject_area_with_id("The Sarn Encampment", "1_3_town")
        engine._inject_area_with_id("Aspirants' Plaza", "Labyrinth_Airlock")
        engine._inject_area_with_id("Mansion Halls", "2_Labyrinth_EH_block_branch")
        engine._inject_area_with_id("The Sarn Encampment", "1_3_town")

        run = engine.active_run
        assert run is not None
        # 两次试炼 = 两个「Aspirants' Plaza」节点
        trial_nodes = [n for n in run.nodes if n.is_trial_entry]
        self.assertEqual(len(trial_nodes), 2)
        self.assertTrue(all(n.area_id == "Labyrinth_Airlock" for n in trial_nodes))


if __name__ == "__main__":
    unittest.main()
