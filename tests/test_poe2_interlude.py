"""PoE2 章节结构：第1..4章 + 間歇 + 終局（不是只有 4 幕）。

真机证据（2026-10-27，``Path of Exile 2/logs/Client.txt``）：

* 章节行 ``幕間章`` 出现 **307 次**（是真正的章节，不是 UI 过场）
* 間歇区域共 **22 个**，area id 用 PoE1 移植前缀：
    P1 火噬農地 → 霍爾登宅第（庇護所）
    P2 卡里交匯道 → 奇瑪水源地（卡里市集）
    P3 灰燼森林 → 庫阿西克寶庫（林間空地）
* 游戏内章节切换栏：第1章 第2章 第3章 第4章 間歇 終局

旧实现把 ``P\\d+_`` 当「PoE1 移植区、非剧情」整段丢弃 → 間歇从路线里消失，
末段用时被错算进第 4 章。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.act_map import (
    chapter_slots,
    detect_act,
    is_poe2_campaign_area_id,
)
from routelens.act_timing import build_act_timing, expected_act_labels

INTERLUDE_IDS = [
    "P1_Town", "P1_1", "P1_2", "P1_3", "P1_4", "P1_5", "P1_6",
    "P2_Town", "P2_1", "P2_2", "P2_3", "P2_5", "P2_6", "P2_7",
    "P3_Town", "P3_1", "P3_2", "P3_3", "P3_4", "P3_5", "P3_6", "P3_7",
]


class InterludeDetectTest(unittest.TestCase):
    def test_all_22_interlude_areas_detected(self) -> None:
        for area_id in INTERLUDE_IDS:
            info = detect_act(area_id, "poe2")
            self.assertTrue(info.is_interlude, area_id)
            self.assertIsNone(info.act, area_id)
            self.assertFalse(info.campaign_over, area_id)
            self.assertEqual(info.label, "間歇", area_id)

    def test_interlude_is_campaign(self) -> None:
        """間歇属于剧情，导入时不能被丢掉。"""
        for area_id in INTERLUDE_IDS:
            self.assertTrue(is_poe2_campaign_area_id(area_id), area_id)

    def test_non_campaign_still_excluded(self) -> None:
        for area_id in ("MapAlpineRidge", "ExpeditionHub", "IncursionHub",
                        "Abyss_Hub", "Sanctum_1", "HideoutFelled"):
            self.assertFalse(is_poe2_campaign_area_id(area_id), area_id)

    def test_p1_in_poe1_is_just_side(self) -> None:
        """P 前缀只在 PoE2 有間歇含义，PoE1 不受影响。"""
        self.assertFalse(detect_act("P1_Town", "poe1").is_interlude)


class ChapterSlotsTest(unittest.TestCase):
    def test_poe2_slots_match_game_ui(self) -> None:
        self.assertEqual(
            chapter_slots("poe2"),
            [("act", "1"), ("act", "2"), ("act", "3"), ("act", "4"),
             ("interlude", ""), ("endgame", "")],
        )

    def test_poe1_slots_are_ten_acts(self) -> None:
        slots = chapter_slots("poe1")
        self.assertEqual(len(slots), 11)  # 10 幕 + 剧情结束
        self.assertTrue(all(kind == "act" for kind, _ in slots[:10]))
        self.assertEqual(slots[-1][0], "endgame")

    def test_labels_include_interlude_and_endgame(self) -> None:
        labels = expected_act_labels("poe2", "zh_tw")
        self.assertEqual(labels[-2:], ["間歇", "终局"])
        self.assertEqual(len(labels), 6)

    def test_poe1_labels_unchanged(self) -> None:
        labels = expected_act_labels("poe1", "zh_tw")
        self.assertEqual(len(labels), 11)
        self.assertEqual(labels[0], "第 1 幕")
        self.assertEqual(labels[-1], "终局")


class InterludeTimingTest(unittest.TestCase):
    def _splits(self) -> list[dict]:
        return [
            {"area": "河岸", "area_id": "G1_1", "segment_seconds": 100.0},
            {"area": "皆伐營地", "area_id": "G1_town", "segment_seconds": 50.0},
            {"area": "奧格姆宅第", "area_id": "G4_15", "segment_seconds": 200.0},
            {"area": "火噬農地", "area_id": "P1_1", "segment_seconds": 300.0},
            {"area": "奇瑪", "area_id": "P2_6", "segment_seconds": 400.0},
            {"area": "庫阿西克寶庫", "area_id": "P3_7", "segment_seconds": 500.0},
            {"area": "金字塔避難所", "area_id": "G_Endgame_Town", "segment_seconds": 60.0},
        ]

    def test_interlude_row_between_act4_and_endgame(self) -> None:
        timing = build_act_timing(self._splits(), "poe2")
        order = [(a.act, a.is_interlude, a.is_endgame) for a in timing.acts]
        self.assertEqual(
            order,
            [(1, False, False), (4, False, False), (None, True, False),
             (None, False, True)],
        )

    def test_interlude_seconds_not_counted_into_act4(self) -> None:
        timing = build_act_timing(self._splits(), "poe2")
        act4 = next(a for a in timing.acts if a.act == 4)
        inter = next(a for a in timing.acts if a.is_interlude)
        self.assertEqual(act4.segment_seconds, 200.0)
        self.assertEqual(inter.segment_seconds, 1200.0)
        self.assertEqual(inter.node_count, 3)
        self.assertEqual(timing.total_seconds, 1610.0)

    def test_poe1_has_no_interlude_row(self) -> None:
        splits = [
            {"area": "A", "area_id": "1_1_1", "segment_seconds": 10.0},
            {"area": "B", "area_id": "1_2_1", "segment_seconds": 20.0},
        ]
        timing = build_act_timing(splits, "poe1")
        self.assertFalse(any(a.is_interlude for a in timing.acts))

    def test_current_chapter_marks_interlude(self) -> None:
        """走到間歇时 current_chapter = interlude（幕视图靠它高亮那一行）。"""
        splits = [
            {"area": "河岸", "area_id": "G1_1", "segment_seconds": 10.0},
            {"area": "奧格姆宅第", "area_id": "G4_15", "segment_seconds": 20.0},
            {"area": "火噬農地", "area_id": "P1_1", "segment_seconds": 30.0},
        ]
        timing = build_act_timing(splits, "poe2")
        self.assertEqual(timing.current_chapter, "interlude")

    def test_current_chapter_marks_act_and_endgame(self) -> None:
        act_splits = [{"area": "河岸", "area_id": "G1_1", "segment_seconds": 10.0}]
        self.assertEqual(build_act_timing(act_splits, "poe2").current_chapter, "act")

        end_splits = [
            {"area": "河岸", "area_id": "G1_1", "segment_seconds": 10.0},
            {"area": "金字塔避難所", "area_id": "G_Endgame_Town", "segment_seconds": 5.0},
        ]
        self.assertEqual(build_act_timing(end_splits, "poe2").current_chapter, "endgame")


if __name__ == "__main__":
    unittest.main()
