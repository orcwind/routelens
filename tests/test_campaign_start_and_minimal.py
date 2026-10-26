"""新建路线的第一幕起点 + 极简模式计时可见性。

用户实测问题（2026-10-25）：
1. 「新建路线，没有读出第一个地图的名称」—— 玩家在第一幕起点时点新建，
   首个区域永远缺失。
2. 「极简模式计时就看不到」—— 没有任何节点时极简模式一行都不画，
   总时间画在「当前行」上 → 计时器完全不显示。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import PropertyMock, patch

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.campaign_start import (  # noqa: E402
    campaign_start_area_id,
    campaign_start_name,
)
from routelens.companion_config import CompanionConfig  # noqa: E402
from routelens.config import load_routelens_config  # noqa: E402
from routelens.engine import RunEngine  # noqa: E402
from routelens.models import ReferenceRoute, RouteNode  # noqa: E402


class CampaignStartTests(unittest.TestCase):
    def test_first_act_start_is_fixed_per_game(self) -> None:
        self.assertEqual(campaign_start_area_id("poe1"), "1_1_1")
        self.assertEqual(campaign_start_area_id("poe2"), "G1_1")
        self.assertEqual(campaign_start_area_id("auto"), "")

    def test_fallback_name_is_never_empty(self) -> None:
        self.assertTrue(campaign_start_name("1_1_1", "en"))
        self.assertTrue(campaign_start_name("G1_1", "zh_tw"))
        self.assertEqual(campaign_start_name("nope", "en"), "")


class SeededNodeTests(unittest.TestCase):
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

    def test_free_run_seeds_first_act_start(self) -> None:
        run = self.engine.new_run(None)
        self.assertEqual(len(run.nodes), 1)
        self.assertEqual(run.nodes[0].area_id, "1_1_1")
        self.assertTrue(run.nodes[0].name)
        self.assertFalse(run.nodes[0].completed)
        self.assertEqual(run.current_index, 0)

    def test_entering_first_area_reuses_seeded_node(self) -> None:
        """玩家进第一幕起点：认领预置节点，不多出一行。"""
        self.engine.new_run(None)
        self.engine._inject_area_with_id("The Twilight Strand", "1_1_1")

        run = self.engine.active_run
        assert run is not None
        self.assertEqual(len(run.nodes), 1)
        self.assertEqual(run.nodes[0].name, "The Twilight Strand")
        self.assertEqual(run.nodes[0].area_id, "1_1_1")
        self.assertEqual(run.current_index, 0)

    def test_seeded_name_corrected_by_log_original(self) -> None:
        """预置名是回退译名时，玩家进图后按日志原文校正。"""
        self.engine.new_run(None)
        run = self.engine.active_run
        assert run is not None
        run.nodes[0].name = "暮光之岸"
        self.engine._inject_area_with_id("The Twilight Strand", "1_1_1")
        self.assertEqual(self.engine.active_run.nodes[0].name, "The Twilight Strand")

    def test_other_area_becomes_second_node(self) -> None:
        self.engine.new_run(None)
        self.engine._inject_area_with_id("The Coast", "1_1_2")

        run = self.engine.active_run
        assert run is not None
        self.assertEqual([n.name for n in run.nodes], ["The Twilight Strand", "The Coast"])
        self.assertEqual(run.current_index, 1)

    def test_reference_run_is_not_seeded(self) -> None:
        """有参考路线时不预置（参考路线自带节点列表）。"""
        ref = ReferenceRoute(
            route_id="r1",
            name="ref",
            nodes=[RouteNode(name="The Coast", seconds=10.0)],
        )
        run = self.engine.new_run(ref)
        self.assertEqual([n.name for n in run.nodes], ["The Coast"])

    def test_reset_free_run_seeds_again(self) -> None:
        self.engine.new_run(None)
        self.engine._inject_area_with_id("The Coast", "1_1_2")
        self.engine.reset_run()
        run = self.engine.active_run
        assert run is not None
        self.assertEqual(len(run.nodes), 1)
        self.assertEqual(run.nodes[0].area_id, "1_1_1")

    def test_unvisited_seed_is_skipped_not_faked(self) -> None:
        """玩家新建路线时人已在别的幕：预置起点不能记一段假时间。"""
        self.engine.new_run(None)
        self.engine._inject_area_with_id("The Cathedral Rooftop", "1_5_8")

        run = self.engine.active_run
        assert run is not None
        seed = run.nodes[0]
        self.assertEqual(seed.area_id, "1_1_1")
        self.assertTrue(seed.skipped)
        self.assertIsNone(seed.seconds)
        # 实际进的区域成为当前节点
        self.assertEqual(run.nodes[-1].name, "The Cathedral Rooftop")
        self.assertEqual(run.current_index, len(run.nodes) - 1)


if __name__ == "__main__":
    unittest.main()
