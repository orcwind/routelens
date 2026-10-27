"""PoE1 Client.txt 导入：章节（日志无章节行）+ 跨角色污染 + 非剧情区域。

真机证据（2026-10-26 E:\\POE\\logs\\Client.txt）：

* PoE1 日志**完全没有章节行**（``[SCENE] Set Source`` 只有区域名，
  没有任何「第一章」/「Act 1」），章节只能由 area id 推出。
* 一个 Client 进程里会**反复切换角色**：同一会话 09:02 是旧角色在 Act 3 城镇，
  13:21 才新建角色从 Twilight Strand 开始，17:02 又换成别的角色在 Act 9。
  日志里没有「换角色」事件（只有升级行带角色名），所以必须用「开荒起点 + 幕号
  单调性」把不属于这次开荒的节点剪掉。
* 联盟城镇 ``KalguuranSettlersLeague``（君锋镇）等命名区域不是剧情。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.act_map import act_chapter_label, is_poe1_campaign_area_id
from routelens.chapter_normalize import sort_chapters
from routelens.client_import import _filtered_splits, _infer_chapters_from_splits


def _split(area_id: str, area: str = "", seconds: float = 0.0) -> dict:
    return {"area_id": area_id, "area": area or area_id, "segment_seconds": seconds}


def _session(splits: list[dict]) -> dict:
    return {"splits": splits, "character": "t", "chapters": []}


class Poe1ChapterTest(unittest.TestCase):
    def test_area_id_gives_chapter_label(self) -> None:
        self.assertEqual(act_chapter_label("1_1_1", "poe1"), "第一章")
        self.assertEqual(act_chapter_label("1_7_2", "poe1"), "第七章")
        self.assertEqual(act_chapter_label("2_10_9", "poe1"), "第十章")
        self.assertEqual(act_chapter_label("2_6_1", "poe1"), "第六章")
        self.assertEqual(act_chapter_label("G3_5", "poe2"), "第三章")

    def test_non_campaign_has_no_chapter(self) -> None:
        for area_id in (
            "KalguuranSettlersLeague",
            "HideoutForest",
            "Delve_Main",
            "MapWorldsCitySquare",
            "2_11_endgame_town",
            "",
        ):
            self.assertEqual(act_chapter_label(area_id, "poe1"), "", area_id)

    def test_sort_chapters_by_act(self) -> None:
        # 读取顺序是「第四章 → 第一章 → 第二章」，显示必须按幕号
        self.assertEqual(
            sort_chapters(["第四章", "第一章", "第二章", "第三章"]),
            ["第一章", "第二章", "第三章", "第四章"],
        )
        self.assertEqual(
            sort_chapters(["第十章", "第九章", "第一章"]),
            ["第一章", "第九章", "第十章"],
        )
        self.assertEqual(
            sort_chapters(["Act 4", "Act 1"]), ["Act 1", "Act 4"]
        )

    def test_infer_chapters_from_area_ids(self) -> None:
        splits = [
            _split("1_1_1"),
            _split("1_1_town"),
            _split("2_10_9"),
        ]
        self.assertEqual(
            _infer_chapters_from_splits(splits, None, {}, "poe1"),
            ["第一章", "第十章"],
        )


class Poe1CampaignAreaTest(unittest.TestCase):
    def test_campaign_ids(self) -> None:
        for area_id in (
            "1_1_1",
            "1_1_2a",
            "1_2_14_2",
            "2_10_9",
            "2_8_7_1_",
            "Labyrinth_Airlock",
            "1_Labyrinth_OH_straight",
            "2_Labyrinth_boss_1",
        ):
            self.assertTrue(is_poe1_campaign_area_id(area_id), area_id)

    def test_non_campaign_ids(self) -> None:
        for area_id in (
            "KalguuranSettlersLeague",
            "Menagerie_Hub",
            "DeepwaterHub",
            "MavenHub",
            "Delve_Main",
            "MapWorldsCitySquare",
            "HideoutForest",
            "1_SideArea5_3_1",
        ):
            self.assertFalse(is_poe1_campaign_area_id(area_id), area_id)


class Poe1FilteredSplitsTest(unittest.TestCase):
    def test_trim_before_campaign_start(self) -> None:
        splits = [
            _split("1_3_town", "The Sarn Encampment"),
            _split("1_1_1", "The Twilight Strand"),
            _split("1_1_town", "Lioneye's Watch"),
        ]
        got = _filtered_splits(_session(splits), "poe1")
        self.assertEqual([s["area_id"] for s in got], ["1_1_1", "1_1_town"])

    def test_drop_non_campaign_area(self) -> None:
        splits = [
            _split("1_2_1", "The Southern Forest"),
            _split("KalguuranSettlersLeague", "Kingsmarch"),
            _split("1_2_town", "The Forest Encampment"),
        ]
        got = _filtered_splits(_session(splits), "poe1")
        self.assertEqual(
            [s["area_id"] for s in got], ["1_2_1", "1_2_town"]
        )

    def test_cut_impossible_forward_jump(self) -> None:
        # Act 1 跑到一半突然跳到 Act 3 城镇 = 换了角色
        splits = [
            _split("1_1_1"),
            _split("1_1_town"),
            _split("1_1_2"),
            _split("1_3_town"),
            _split("2_9_1"),
        ]
        got = _filtered_splits(_session(splits), "poe1")
        self.assertEqual(
            [s["area_id"] for s in got], ["1_1_1", "1_1_town", "1_1_2"]
        )

    def test_cut_impossible_backjump(self) -> None:
        # 已到 Act 9，下一步却是 Act 6 城镇（回退 3 幕）= 换了角色
        splits = [
            _split("2_9_1"),
            _split("2_6_town"),
            _split("1_2_town"),
        ]
        got = _filtered_splits(_session(splits), "poe1")
        self.assertEqual([s["area_id"] for s in got], ["2_9_1"])

    def test_allow_backtrack_one_act(self) -> None:
        # 回退 1 幕视为正常折返，不能剪
        splits = [
            _split("1_1_1"),
            _split("1_2_1"),
            _split("1_1_town"),
            _split("1_2_2"),
        ]
        got = _filtered_splits(_session(splits), "poe1")
        self.assertEqual(
            [s["area_id"] for s in got],
            ["1_1_1", "1_2_1", "1_1_town", "1_2_2"],
        )

    def test_second_run_in_same_client_keeps_longest(self) -> None:
        # 同一 Client 进程里先跑了 3 个节点的角色，再新建角色跑 6 个节点
        splits = [
            _split("1_1_1"),
            _split("1_1_town"),
            _split("1_1_2"),
            _split("1_1_1"),
            _split("1_1_town"),
            _split("1_1_2"),
            _split("1_1_3"),
            _split("1_1_4_1"),
            _split("1_1_2a"),
        ]
        got = _filtered_splits(_session(splits), "poe1")
        self.assertEqual(len(got), 6)
        self.assertEqual(got[0]["area_id"], "1_1_1")

    def test_drop_hideout(self) -> None:
        splits = [
            _split("1_1_1"),
            _split("HideoutForest", "Lush Hideout"),
            _split("1_1_town"),
        ]
        got = _filtered_splits(_session(splits), "poe1")
        self.assertEqual([s["area_id"] for s in got], ["1_1_1", "1_1_town"])


if __name__ == "__main__":
    unittest.main()
