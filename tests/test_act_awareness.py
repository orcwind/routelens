"""幕（Act）感知：分幕判定 / 剧情结束 / 异界地图排除 / 分幕计时。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.act_map import (
    POE1_ACT_COUNT,
    POE2_ACT_COUNT,
    act_count,
    detect_act,
    is_campaign_over_area_id,
    is_endgame_map_area_id,
)
from routelens.act_timing import build_act_timing
from routelens.campaign_end import truncate_at_campaign_end


class ActDetectionTests(unittest.TestCase):
    def test_poe1_act_from_area_id(self) -> None:
        # PoE1 area id = X_Y，第二位是幕号
        self.assertEqual(detect_act("1_1_2", "poe1").act, 1)
        self.assertEqual(detect_act("1_5_6", "poe1").act, 5)
        self.assertEqual(detect_act("2_6_1", "poe1").act, 6)
        self.assertEqual(detect_act("2_10_6", "poe1").act, 10)
        self.assertEqual(detect_act("1_2_town", "poe1").act, 2)
        self.assertEqual(detect_act("2_9_town", "poe1").act, 9)

    def test_poe1_act5_and_act10_share_area_names(self) -> None:
        """Act 5 与 Act 10 区域名相同，只能靠 area id 区分。"""
        # The Ossuary / The Cathedral Rooftop 在 Act 5 与 Act 10 都出现
        self.assertEqual(detect_act("1_5_9", "poe1").act, 5)
        self.assertEqual(detect_act("2_10_9", "poe1").act, 10)
        self.assertEqual(detect_act("1_5_8", "poe1").act, 5)
        self.assertEqual(detect_act("2_10_8", "poe1").act, 10)

    def test_poe1_campaign_end(self) -> None:
        """``2_11`` = 奇塔弗之后的卡鲁海滩 = 剧情结束。"""
        self.assertTrue(is_campaign_over_area_id("2_11_endgame_town", "poe1"))
        self.assertTrue(is_campaign_over_area_id("2_11", "poe1"))
        self.assertFalse(is_campaign_over_area_id("2_10_6", "poe1"))
        self.assertFalse(is_campaign_over_area_id("2_11_endgame_town", "poe2"))

    def test_poe1_endgame_map(self) -> None:
        self.assertTrue(is_endgame_map_area_id("MapWorldsChateau", "poe1"))
        self.assertTrue(is_endgame_map_area_id("MapWorldsEstuary", "poe1"))
        self.assertFalse(is_endgame_map_area_id("2_10_6", "poe1"))

    def test_poe1_side_content(self) -> None:
        """迷宫 / 支线不是剧情推进，也不该当成终局。"""
        for area_id in ("1_Labyrinth_boss_1", "1_SideArea5_3_1", "1_SideArea3_12"):
            info = detect_act(area_id, "poe1")
            self.assertIsNone(info.act)
            self.assertTrue(info.is_side)
            self.assertFalse(info.campaign_over)
            self.assertFalse(info.is_map)

    def test_poe2_act_from_area_id(self) -> None:
        self.assertEqual(detect_act("G1_4", "poe2").act, 1)
        self.assertEqual(detect_act("G2_10_1", "poe2").act, 2)
        self.assertEqual(detect_act("G3_town", "poe2").act, 3)
        self.assertEqual(detect_act("G4_1", "poe2").act, 4)

    def test_poe2_campaign_end(self) -> None:
        self.assertTrue(is_campaign_over_area_id("G_Endgame_Town", "poe2"))
        self.assertFalse(is_campaign_over_area_id("G4_1", "poe2"))

    def test_poe2_endgame_map_and_side(self) -> None:
        for area_id in ("MapBloomingField", "MapStronghold", "MapMire"):
            info = detect_act(area_id, "poe2")
            self.assertTrue(info.is_map)
            self.assertFalse(info.campaign_over)
        for area_id in ("ExpeditionLogBook_Peninsula", "IncursionTemple"):
            info = detect_act(area_id, "poe2")
            self.assertTrue(info.is_side)
            self.assertFalse(info.is_map)
            self.assertFalse(info.campaign_over)

    def test_act_count(self) -> None:
        self.assertEqual(act_count("poe1"), POE1_ACT_COUNT)
        self.assertEqual(act_count("poe2"), POE2_ACT_COUNT)
        self.assertEqual(POE1_ACT_COUNT, 10)
        self.assertEqual(POE2_ACT_COUNT, 4)


class TruncateTests(unittest.TestCase):
    def test_poe1_truncate_at_campaign_end(self) -> None:
        splits = [
            {"area": "The Feeding Trough", "area_id": "2_10_6", "segment_seconds": 10},
            {"area": "Karui Shores", "area_id": "2_11_endgame_town", "segment_seconds": 5},
            {"area": "Chateau", "area_id": "MapWorldsChateau", "segment_seconds": 20},
            {"area": "Estuary", "area_id": "MapWorldsEstuary", "segment_seconds": 30},
        ]
        result = truncate_at_campaign_end(splits, "poe1")
        self.assertEqual([s["area"] for s in result], ["The Feeding Trough", "Karui Shores"])

    def test_poe1_endgame_map_dropped_even_before_end(self) -> None:
        """异界地图即使出现在剧情中段也要丢弃。"""
        splits = [
            {"area": "The Coast", "area_id": "1_1_2", "segment_seconds": 10},
            {"area": "Chateau", "area_id": "MapWorldsChateau", "segment_seconds": 20},
            {"area": "The Mud Flats", "area_id": "1_1_3", "segment_seconds": 10},
        ]
        result = truncate_at_campaign_end(splits, "poe1")
        self.assertEqual([s["area"] for s in result], ["The Coast", "The Mud Flats"])

    def test_poe1_act6_karui_shores_not_campaign_end(self) -> None:
        """Act 5→6 过渡的 Karui Shores 不是终点（area id = 2_6_*）。"""
        splits = [
            {"area": "The Sceptre of God", "area_id": "1_3_9", "segment_seconds": 10},
            {"area": "Karui Shores", "area_id": "2_6_town", "segment_seconds": 5},
            {"area": "The Coast", "area_id": "2_6_2", "segment_seconds": 10},
        ]
        result = truncate_at_campaign_end(splits, "poe1")
        self.assertEqual(len(result), 3)

    def test_poe2_truncate_at_endgame_town(self) -> None:
        splits = [
            {"area": "Kingsmarch", "area_id": "G4_town", "segment_seconds": 10},
            {"area": "Ziggurat Refuge", "area_id": "G_Endgame_Town", "segment_seconds": 5},
            {"area": "Stronghold", "area_id": "MapStronghold", "segment_seconds": 30},
        ]
        result = truncate_at_campaign_end(splits, "poe2")
        self.assertEqual([s["area"] for s in result], ["Kingsmarch", "Ziggurat Refuge"])


class ActTimingTests(unittest.TestCase):
    def test_poe1_act_timing_sums_nodes(self) -> None:
        splits = [
            {"area": "The Coast", "area_id": "1_1_2", "segment_seconds": 30},
            {"area": "The Mud Flats", "area_id": "1_1_3", "segment_seconds": 40},
            {"area": "The Ancient Pyramid", "area_id": "1_2_8", "segment_seconds": 50},
            {"area": "The Feeding Trough", "area_id": "2_10_6", "segment_seconds": 60},
            {"area": "Karui Shores", "area_id": "2_11_endgame_town", "segment_seconds": 10},
        ]
        timing = build_act_timing(splits, "poe1")
        acts = {a.act: a for a in timing.acts if a.act is not None}
        self.assertEqual(acts[1].segment_seconds, 70)
        self.assertEqual(acts[2].segment_seconds, 50)
        self.assertEqual(acts[10].segment_seconds, 60)
        self.assertEqual(acts[1].node_count, 2)
        self.assertEqual(acts[1].cumulative_seconds, 70)
        self.assertEqual(acts[2].cumulative_seconds, 120)
        # 剧情结束单独成组
        endgame = [a for a in timing.acts if a.is_endgame]
        self.assertEqual(len(endgame), 1)
        self.assertEqual(endgame[0].segment_seconds, 10)

    def test_same_act_revisited_merges_into_one_row(self) -> None:
        """玩家重刷早期幕（刷任务）→ 同一幕合并成一行，不重复出现。"""
        splits = [
            {"area": "The Coast", "area_id": "1_1_2", "segment_seconds": 30},
            {"area": "The Ancient Pyramid", "area_id": "1_2_8", "segment_seconds": 50},
            {"area": "The Coast", "area_id": "1_1_2", "segment_seconds": 20},
            {"area": "The Feeding Trough", "area_id": "2_10_6", "segment_seconds": 60},
        ]
        timing = build_act_timing(splits, "poe1")
        acts = [a.act for a in timing.acts]
        self.assertEqual(acts, [1, 2, 10])  # 幕号升序，无重复
        act1 = timing.acts[0]
        self.assertEqual(act1.segment_seconds, 50)  # 30 + 20
        self.assertEqual(act1.node_count, 2)

    def test_acts_sorted_by_number(self) -> None:
        """行序 = 幕号升序（跨多次登录合并后仍是 Act 1…N 的骨架）。"""
        splits = [
            {"area": "A", "area_id": "2_10_1", "segment_seconds": 10},
            {"area": "B", "area_id": "1_1_1", "segment_seconds": 20},
            {"area": "C", "area_id": "1_5_1", "segment_seconds": 30},
        ]
        timing = build_act_timing(splits, "poe1")
        self.assertEqual([a.act for a in timing.acts], [1, 5, 10])
        # 累计按幕序累加
        self.assertEqual(timing.acts[0].cumulative_seconds, 20)
        self.assertEqual(timing.acts[1].cumulative_seconds, 50)
        self.assertEqual(timing.acts[2].cumulative_seconds, 60)

    def test_side_node_time_counted_into_current_act(self) -> None:
        """支线不推进幕号，但时间必须计入当前幕（不能漏计）。"""
        splits = [
            {"area": "The Coast", "area_id": "1_1_2", "segment_seconds": 30},
            {"area": "Sepulchre Halls", "area_id": "1_Labyrinth_C_straight", "segment_seconds": 20},
            {"area": "The Mud Flats", "area_id": "1_1_3", "segment_seconds": 40},
        ]
        timing = build_act_timing(splits, "poe1")
        act1 = [a for a in timing.acts if a.act == 1][0]
        self.assertEqual(act1.segment_seconds, 90)
        self.assertEqual(act1.node_count, 3)

    def test_different_node_order_same_act_result(self) -> None:
        """用户节点顺序不同 / 有支线，分幕结果必须一致。"""
        route_a = [
            {"area": "A", "area_id": "1_1_2", "segment_seconds": 10},
            {"area": "B", "area_id": "1_1_3", "segment_seconds": 10},
        ]
        route_b = [
            {"area": "A", "area_id": "1_1_2", "segment_seconds": 5},
            {"area": "Side", "area_id": "1_Labyrinth_boss_1", "segment_seconds": 5},
            {"area": "B", "area_id": "1_1_3", "segment_seconds": 10},
        ]
        timing_a = build_act_timing(route_a, "poe1")
        timing_b = build_act_timing(route_b, "poe1")
        acts_a = [a.act for a in timing_a.acts]
        acts_b = [a.act for a in timing_b.acts]
        self.assertEqual(acts_a, acts_b)
        self.assertEqual(timing_a.acts[0].segment_seconds, timing_b.acts[0].segment_seconds)

    def test_act5_and_act10_distinguished(self) -> None:
        """同名区域在 Act 5 / Act 10 必须分成不同的幕。"""
        splits = [
            {"area": "The Ossuary", "area_id": "1_5_9", "segment_seconds": 10},
            {"area": "The Ossuary", "area_id": "2_10_9", "segment_seconds": 20},
        ]
        timing = build_act_timing(splits, "poe1")
        acts = [a.act for a in timing.acts]
        self.assertEqual(acts, [5, 10])
    def test_total_matches_node_sum(self) -> None:
        splits = [
            {"area": "A", "area_id": "G1_1", "segment_seconds": 10},
            {"area": "B", "area_id": "G2_1", "segment_seconds": 20},
            {"area": "C", "area_id": "G4_1", "segment_seconds": 30},
        ]
        timing = build_act_timing(splits, "poe2")
        self.assertEqual(timing.total_seconds, 60)
        self.assertEqual(len(timing.acts), 3)


if __name__ == "__main__":
    unittest.main()
