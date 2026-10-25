"""回归测试：回退/来回跑去重 + 「幕間章」脏节点过滤 + area_id 消费式配对。

对应真机发现（2026-10-25）：
- 日志里存在非游戏主进程（Client 99999），只写 [SCENE] Set Source，
  写出「幕間章」这类与玩家无关的场景名 → 污染出「幕間章」节点。
- 一次 Generating 只对应**一个**真实区域 = 该批第一个非 null 的 Set Source。
- 玩家从 Act 3 回到 Act 1、或同一幕内两个地点来回跑 → 重复地点应合并，
  且停留时间不能丢。
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.log_analyzer import LogRunSession, analyze_client_log  # noqa: E402
from routelens.log_parser import parse_line  # noqa: E402

TS = "2026/10/25 12:00:00"


def _line(offset: int, text: str, client: int = 1000) -> str:
    t = (datetime(2026, 10, 25, 12, 0, 0) + timedelta(seconds=offset)).strftime(
        "%Y/%m/%d %H:%M:%S"
    )
    return f"{t} 12345678 abcdef01 [INFO Client {client}] {text}"


class ForeignClientTests(unittest.TestCase):
    """非游戏主进程（99999）写入的场景名必须被忽略。"""

    def _log(self, tmp: Path, body: str) -> Path:
        path = tmp / "Client.txt"
        path.write_text(
            "2026/10/25 12:00:00 1 a [INFO Client 1000] ***** LOG FILE OPENING *****\n"
            + body,
            encoding="utf-8",
        )
        return path

    def test_foreign_client_scene_is_ignored(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            path = self._log(
                tmp,
                _line(0, 'Generating level 33 area "1_1_1" with seed 1') + "\n"
                + _line(1, "[SCENE] Set Source [The Twilight Strand]") + "\n"
                + _line(2, ": You have entered The Twilight Strand.") + "\n"
                + _line(3, "[SCENE] Set Source [幕間章]", client=99999) + "\n",
            )
            sessions = analyze_client_log(path, min_nodes=1, game_id="poe1")
            areas = [v.area for s in sessions for v in s.visits]
            self.assertNotIn("幕間章", areas)
            self.assertIn("The Twilight Strand", areas)

    def test_foreign_client_only_log_produces_no_nodes(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            path = self._log(
                tmp,
                _line(0, "[SCENE] Set Source [幕間章]", client=99999) + "\n"
                + _line(1, "[SCENE] Set Source [The Twilight Strand]", client=99999) + "\n",
            )
            sessions = analyze_client_log(path, min_nodes=1, game_id="poe1")
            self.assertEqual([v.area for s in sessions for v in s.visits], [])


class SceneBatchTests(unittest.TestCase):
    """一批 Generating 只对应一个真实区域（第一个非 null 的 Set Source）。"""

    def test_interlude_scene_in_batch_is_ignored(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            path = tmp / "Client.txt"
            path.write_text(
                "2026/10/25 12:00:00 1 a [INFO Client 1000] ***** LOG FILE OPENING *****\n"
                + _line(0, 'Generating level 33 area "P2_1" with seed 1') + "\n"
                + _line(1, "[SCENE] Set Source [(null)]") + "\n"
                + _line(2, "[SCENE] Set Source [卡里交匯道]") + "\n"
                + _line(3, "[SCENE] Set Source [幕間章]") + "\n"
                + _line(4, "[SCENE] Set Source [(null)]") + "\n"
                + _line(5, "[SCENE] Set Source [卡里交匯道]") + "\n",
                encoding="utf-8",
            )
            sessions = analyze_client_log(path, min_nodes=1, game_id="poe2")
            areas = [v.area for s in sessions for v in s.visits]
            self.assertEqual(areas, ["卡里交匯道"])
            self.assertEqual(sessions[0].visits[0].area_id, "P2_1")

    def test_scene_without_generating_is_ignored(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            path = tmp / "Client.txt"
            path.write_text(
                "2026/10/25 12:00:00 1 a [INFO Client 1000] ***** LOG FILE OPENING *****\n"
                + _line(0, "[SCENE] Set Source [幕間章]") + "\n",
                encoding="utf-8",
            )
            sessions = analyze_client_log(path, min_nodes=1, game_id="poe1")
            self.assertEqual([v.area for s in sessions for v in s.visits], [])


class AreaIdPairingTests(unittest.TestCase):
    """area id 必须消费式配对（生成即消费），不能被后续 Generating 覆盖。"""

    def test_area_id_not_stale_after_consumption(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            path = tmp / "Client.txt"
            path.write_text(
                "2026/10/25 12:00:00 1 a [INFO Client 1000] ***** LOG FILE OPENING *****\n"
                + _line(0, 'Generating level 33 area "1_1_1" with seed 1') + "\n"
                + _line(1, ": You have entered The Twilight Strand.") + "\n"
                + _line(2, ": You have entered Lioneye's Watch.") + "\n",
                encoding="utf-8",
            )
            sessions = analyze_client_log(path, min_nodes=1, game_id="poe1")
            visits = sessions[0].visits
            self.assertEqual(visits[0].area_id, "1_1_1")
            # 第二次进入没有新的 Generating → 不应复用上一个 id
            self.assertEqual(visits[1].area_id, "")

    def test_parse_line_area_id_kwarg(self) -> None:
        event = parse_line(
            _line(0, ": You have entered The Coast."), area_id="1_1_2"
        )
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event.area, "The Coast")
        self.assertEqual(event.area_id, "1_1_2")


class DedupeTests(unittest.TestCase):
    """回退 / 来回跑去重，且停留时间必须守恒。"""

    def _session(self, visits: list[tuple[str, str, int]]) -> LogRunSession:
        from routelens.log_analyzer import AreaVisit

        session = LogRunSession(session_id=1, character="test")
        base = datetime(2026, 10, 25, 12, 0, 0)
        for name, area_id, offset in visits:
            session.visits.append(
                AreaVisit(
                    area=name,
                    timestamp=base + timedelta(seconds=offset),
                    chapter="",
                    area_id=area_id,
                )
            )
        return session

    def test_same_area_visited_twice_is_merged(self) -> None:
        session = self._session(
            [
                ("The Coast", "1_1_2", 0),
                ("The Mud Flats", "1_1_3", 60),
                ("The Coast", "1_1_2", 120),
                ("The Climb", "1_1_6", 180),
            ]
        )
        splits = session.build_splits()
        names = [s.area for s in splits]
        self.assertEqual(names, ["The Coast", "The Mud Flats", "The Climb"])
        # The Coast 的两段时间（0-60 与 120-180）要合并回去
        coast = splits[0]
        self.assertAlmostEqual(coast.segment_seconds, 120.0, places=1)

    def test_backtrack_to_earlier_act_is_removed(self) -> None:
        session = self._session(
            [
                ("Act3 Town", "1_3_town", 0),
                ("Act3 Zone", "1_3_2", 60),
                ("Act1 Town", "1_1_town", 120),
                ("Act1 Zone", "1_1_2", 180),
            ]
        )
        splits = session.build_splits()
        ids = [s.area_id for s in splits]
        self.assertEqual(ids, ["1_3_town", "1_3_2", "1_1_town", "1_1_2"])

    def test_total_time_is_conserved(self) -> None:
        session = self._session(
            [
                ("A", "1_1_1", 0),
                ("B", "1_1_2", 30),
                ("A", "1_1_1", 90),
                ("C", "1_1_3", 150),
            ]
        )
        splits = session.build_splits()
        raw_total = 150.0  # 最后一段没闭合，按相邻差算
        self.assertAlmostEqual(sum(s.segment_seconds for s in splits), raw_total, places=1)

    def test_different_acts_same_name_are_kept(self) -> None:
        """PoE1 Act 3 / Act 8 区域名相同，必须保留两个节点。"""
        session = self._session(
            [
                ("The Sarn Encampment", "1_3_town", 0),
                ("Something", "1_3_2", 60),
                ("The Sarn Encampment", "2_8_town", 120),
            ]
        )
        splits = session.build_splits()
        self.assertEqual(len(splits), 3)
        self.assertEqual(splits[0].area_id, "1_3_town")
        self.assertEqual(splits[2].area_id, "2_8_town")

    def test_labyrinth_instances_are_kept(self) -> None:
        """迷宫同名不同实例（boss_1 / boss_2 / boss_2_end）必须保留。"""
        session = self._session(
            [
                ("Aspirant's Trial", "1_Labyrinth_boss_1", 0),
                ("Mansion Halls", "1_Labyrinth_EH_block_branch", 30),
                ("Aspirant's Trial", "1_Labyrinth_boss_2", 60),
            ]
        )
        splits = session.build_splits()
        self.assertEqual(len(splits), 3)


class MergeSplitsTests(unittest.TestCase):
    """路线合并层（route_library._merge_splits）的去重判据。"""

    @staticmethod
    def _split(name: str, area_id: str, arrived: str) -> dict:
        return {
            "area": name,
            "area_en": name,
            "elapsed": "00:30",
            "segment_seconds": 30.0,
            "cumulative_seconds": 30.0,
            "arrived_at": arrived,
            "area_id": area_id,
        }

    def test_same_area_id_is_dropped(self) -> None:
        from routelens.route_library import _merge_splits

        existing = [self._split("Lioneye's Watch", "1_1_town", "2026-10-25T12:00:00")]
        new = [self._split("Lioneye's Watch", "1_1_town", "2026-10-25T13:00:00")]
        merged = _merge_splits(existing, new, keep_repeated_names=True)
        self.assertEqual(len(merged), 1)

    def test_cross_act_same_name_is_kept(self) -> None:
        from routelens.route_library import _merge_splits

        existing = [self._split("The Sarn Encampment", "1_3_town", "2026-10-25T12:00:00")]
        new = [self._split("The Sarn Encampment", "2_8_town", "2026-10-25T13:00:00")]
        merged = _merge_splits(existing, new, keep_repeated_names=True)
        self.assertEqual(len(merged), 2)

    def test_poe2_default_drops_same_name(self) -> None:
        from routelens.route_library import _merge_splits

        existing = [self._split("The Coast", "G1_2", "2026-10-25T12:00:00")]
        new = [self._split("The Coast", "G1_2", "2026-10-25T13:00:00")]
        merged = _merge_splits(existing, new)
        self.assertEqual(len(merged), 1)


if __name__ == "__main__":
    unittest.main()
