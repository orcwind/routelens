"""回归测试：试炼折叠（一次试炼只记进门那一次）。

对应用户诉求（2026-10-25）：
- 「poe1 的升华试炼，每一次试炼只记录进门那一次，里面的房间不再记录」
- 「不过多次试炼每次都记录」
- 「poe2 有两个试炼，混沌试炼和丝科玛试炼，每次试炼只做 1 个记录」

权威依据 = area id（实测自真实 Client.txt）：
- PoE1 进门 = ``Labyrinth_Airlock``，房间 = ``<act>_Labyrinth_*``
- PoE2 絲克瑪 = ``G2_13`` + ``Sanctum_*``
- PoE2 混沌 = ``G3_10_Airlock``（入口大厅）↔ ``G3_10``（本体）

**不是试炼**（用户 2026-10-25 澄清）：
- ``G4_4_3``「祖靈的試煉」= Act 4 剧情区域（Trial of the Ancestors），
  名字带「試煉」但不是试炼 → 必须按普通剧情节点记录。
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.log_analyzer import AreaVisit, LogRunSession  # noqa: E402
from routelens.trial import detect_trial  # noqa: E402


def _session_timed(game: str, rows: list[tuple[str, str, int]]) -> LogRunSession:
    """rows = [(area_id, area_name, 该段停留秒数)]，按给定秒数铺时间戳。

    第 N 段的停留 = rows[N][2]（该区停留到下次进入的间隔）。
    最后一段没有后继 → 停留为 0。
    """
    base = datetime(2026, 10, 25, 10, 0, 0)
    visits: list[AreaVisit] = []
    ts = base
    for index, (area_id, area, seconds) in enumerate(rows):
        visits.append(AreaVisit(area=area, timestamp=ts, chapter="", area_id=area_id))
        if index + 1 < len(rows):
            ts += timedelta(seconds=seconds)
    session = LogRunSession(session_id=1, character="tester", game_id=game)
    session.visits = visits
    return session


class TrialDetectionTests(unittest.TestCase):
    """area id → 试炼归属判定。"""

    def test_poe1_labyrinth(self) -> None:
        entry = detect_trial("Labyrinth_Airlock", "poe1")
        self.assertTrue(entry.in_trial)
        self.assertTrue(entry.is_entry)

        for room in (
            "1_Labyrinth_OH_straight",
            "1_Labyrinth_boss_1",
            "2_Labyrinth_boss_2_end",
            "3_Labyrinth_EH_branch_bottleneck_2",
        ):
            info = detect_trial(room, "poe1")
            self.assertTrue(info.in_trial, room)
            self.assertTrue(info.is_room, room)
            self.assertEqual(info.trial_id, "poe1_labyrinth")

    def test_poe1_normal_area_not_trial(self) -> None:
        for area_id in ("1_3_town", "2_6_7_1", "MapWorldsCells"):
            self.assertFalse(detect_trial(area_id, "poe1").in_trial, area_id)

    def test_poe2_two_trials(self) -> None:
        cases = {
            "G2_13": "G2_13",
            "Sanctum_1_Foyer_1": "G2_13",
            "G3_10": "G3_10",
            "G3_10_Airlock": "G3_10",
        }
        for area_id, trial_id in cases.items():
            info = detect_trial(area_id, "poe2")
            self.assertTrue(info.in_trial, area_id)
            self.assertEqual(info.trial_id, trial_id, area_id)

    def test_poe2_normal_area_not_trial(self) -> None:
        for area_id in ("G1_town", "G2_13_x", "MapNecropolis", "G4_7"):
            self.assertFalse(detect_trial(area_id, "poe2").in_trial, area_id)

    def test_ancestral_trial_is_story_area_not_trial(self) -> None:
        """「祖靈的試煉」= Act 4 剧情区域（Trial of the Ancestors），**不是**试炼。

        名字里带「試煉」很容易误判成试炼，必须按普通剧情节点记录。
        """
        for area_id in ("G4_4_3", "G4_4_1", "G4_4_2"):
            self.assertFalse(detect_trial(area_id, "poe2").in_trial, area_id)


class PoE1LabyrinthFoldTests(unittest.TestCase):
    """PoE1 升华试炼：一次试炼 = 1 个节点。"""

    def test_single_trial_folds_rooms_into_entry(self) -> None:
        # 实测真实形态（2026-10-14 21:45:43 的一次试炼）
        session = _session_timed(
            "poe1",
            [
                ("1_3_town", "The Sarn Encampment", 120),
                ("Labyrinth_Airlock", "Aspirants' Plaza", 9),
                ("1_Labyrinth_OH_straight", "Estate Path", 22),
                ("1_Labyrinth_boss_1", "Aspirant's Trial", 40),
                ("1_Labyrinth_C_branch_bottleneck_2", "Sepulchre Halls", 33),
                ("1_Labyrinth_boss_2", "Aspirant's Trial", 37),
                ("1_Labyrinth_EH_block_branch", "Mansion Halls", 46),
                ("1_Labyrinth_OH_quad_#", "Estate Crossing", 2839),
                ("1_Labyrinth_boss_2_end", "Aspirant's Trial", 70),
                ("1_3_town", "The Sarn Encampment", 137),
            ],
        )
        nodes = session.build_splits()

        # 试炼房间不应单独成节点
        names = [n.area for n in nodes]
        self.assertNotIn("Estate Path", names)
        self.assertNotIn("Sepulchre Halls", names)
        self.assertNotIn("Mansion Halls", names)
        self.assertNotIn("Estate Crossing", names)
        # 进门那一次保留
        self.assertIn("Aspirants' Plaza", names)
        trial_nodes = [n for n in nodes if n.is_trial_entry]
        self.assertEqual(len(trial_nodes), 1)
        # 房间时间并入进门节点（时间不丢）
        self.assertEqual(
            trial_nodes[0].segment_seconds,
            9 + 22 + 40 + 33 + 37 + 46 + 2839 + 70,
        )

    def test_multiple_trials_each_recorded(self) -> None:
        # 实测真实形态（2026-10-16 的两次试炼，中间离开迷宫）
        session = _session_timed(
            "poe1",
            [
                ("Labyrinth_Airlock", "Aspirants' Plaza", 9),
                ("2_Labyrinth_OH_branch", "Estate Walkways", 32),
                ("2_Labyrinth_boss_2", "Aspirant's Trial", 44),
                ("2_Labyrinth_OH_branch_bottleneck_1", "Estate Walkways", 54),
                ("2_Labyrinth_RT_branch_bottleneck_1", "Basilica Halls", 38),
                ("2_Labyrinth_boss_2_end", "Aspirant's Trial", 71),
                ("2_11_endgame_town", "Karui Shores", 168),
                ("MapWorldsCells", "Cells", 153),
                ("Labyrinth_Airlock", "Aspirants' Plaza", 9),
                ("3_Labyrinth_OH_straight", "Estate Path", 112),
                ("3_Labyrinth_boss_2", "Aspirant's Trial", 44),
                ("3_Labyrinth_EH_straight_bottleneck", "Mansion Passage", 38),
                ("3_Labyrinth_RT_straight", "Basilica Passage", 56),
                ("3_Labyrinth_boss_2_end_#", "Aspirant's Trial", 42),
            ],
        )
        nodes = session.build_splits()
        trial_nodes = [n for n in nodes if n.is_trial_entry]

        # 两次试炼 = 两个节点（area id 相同也要都保留）
        self.assertEqual(len(trial_nodes), 2)
        self.assertEqual([n.area_id for n in trial_nodes], ["Labyrinth_Airlock"] * 2)
        self.assertEqual(trial_nodes[0].segment_seconds, 9 + 32 + 44 + 54 + 38 + 71)
        # 最后一段没有后继 → 停留 0（与真实解析一致）
        self.assertEqual(trial_nodes[1].segment_seconds, 9 + 112 + 44 + 38 + 56)

    def test_total_time_preserved(self) -> None:
        session = _session_timed(
            "poe1",
            [
                ("Labyrinth_Airlock", "Aspirants' Plaza", 10),
                ("1_Labyrinth_boss_1", "Aspirant's Trial", 20),
                ("1_3_town", "The Sarn Encampment", 30),
            ],
        )
        nodes = session.build_splits()
        # 折叠不改变总时长（最后一个节点无后继 → 停留 0）
        self.assertAlmostEqual(sum(n.segment_seconds for n in nodes), 10 + 20, places=3)


class PoE2TrialFoldTests(unittest.TestCase):
    """PoE2 三个试炼：一次试炼 = 1 个节点。"""

    def test_sekhema_trial_folds_sanctum_rooms(self) -> None:
        # 实测真实形态（2026-09-25 23:01:28 的一次絲克瑪試煉）
        session = _session_timed(
            "poe2",
            [
                ("HideoutFelled", "藏身處：殞落", 41),
                ("G2_13", "絲克瑪試煉", 34),
                ("Sanctum_1_Foyer_1", "絲克瑪試煉", 303),
                ("Sanctum_2_Foyer_3", "絲克瑪試煉", 307),
                ("Sanctum_3_Foyer_3", "絲克瑪試煉", 417),
                ("Sanctum_4_Foyer_3", "絲克瑪試煉", 433),
                ("G2_13", "絲克瑪試煉", 148),
                ("HideoutFelled", "藏身處：殞落", 24),
            ],
        )
        nodes = session.build_splits()
        trial_nodes = [n for n in nodes if n.is_trial_entry]
        self.assertEqual(len(trial_nodes), 1)
        self.assertEqual(trial_nodes[0].area, "絲克瑪試煉")
        self.assertEqual(trial_nodes[0].segment_seconds, 34 + 303 + 307 + 417 + 433 + 148)

    def test_chaos_trial_airlock_and_body_are_one_run(self) -> None:
        # 实测真实形态（2026-09-06 00:09:29）：混沌神殿 ↔ 混沌試煉 来回
        session = _session_timed(
            "poe2",
            [
                ("HideoutFelled", "藏身處：殞落", 50),
                ("G3_10_Airlock", "混沌神殿", 13),
                ("G3_10", "混沌試煉", 360),
                ("G3_10_Airlock", "混沌神殿", 28),
                ("G3_10", "混沌試煉", 341),
                ("G3_10_Airlock", "混沌神殿", 8),
                ("HideoutLimestone", "藏身處：石灰岩", 8),
                ("G3_10_Airlock", "混沌神殿", 18),
                ("G3_10", "混沌試煉", 219),
                ("HideoutFelled", "藏身處：殞落", 9),
            ],
        )
        nodes = session.build_splits()
        trial_nodes = [n for n in nodes if n.is_trial_entry]
        # 进出藏身处会打断试炼 → 2 次试炼
        self.assertEqual(len(trial_nodes), 2)
        # 显示名统一取本体（混沌試煉）
        self.assertEqual([n.area for n in trial_nodes], ["混沌試煉", "混沌試煉"])
        self.assertEqual(trial_nodes[0].segment_seconds, 13 + 360 + 28 + 341 + 8)
        self.assertEqual(trial_nodes[1].segment_seconds, 18 + 219)

    def test_ancestral_trial_stays_normal_story_nodes(self) -> None:
        """「祖靈的試煉」是 Act 4 剧情区域 → 必须按普通剧情节点逐个记录。"""
        # 实测真实形态（2026-07-06 20:37~20:58）：悉妮蔻拉之眼 → 亡者之殿 → 祖靈的試煉
        session = _session_timed(
            "poe2",
            [
                ("G4_4_1", "悉妮蔻拉之眼", 100),
                ("G4_4_2", "亡者之殿", 200),
                ("G4_4_3", "祖靈的試煉", 300),
                ("G4_4_1", "悉妮蔻拉之眼", 64),
                ("G4_town", "金司馬區", 40),
            ],
        )
        nodes = session.build_splits()
        # 没有试炼节点
        self.assertEqual([n for n in nodes if n.is_trial_entry], [])
        # 剧情区域逐个保留（原始区域名，不被改写）
        names = [n.area for n in nodes]
        self.assertIn("悉妮蔻拉之眼", names)
        self.assertIn("亡者之殿", names)
        self.assertIn("祖靈的試煉", names)


if __name__ == "__main__":
    unittest.main()

