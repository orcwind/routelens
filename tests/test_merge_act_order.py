"""多会话合并：节点必须按幕归位，不能出现 Act4 夹在 Act3 中间。

事故（2026-10-27 用户真实路线库 ``bafawefasdf``）：

    33 1_3_1       The City of Sarn      ← Act 3
    34 1_4_town    Highgate              ← Act 4 **插在 Act 3 中间**
    35 1_3_town    The Sarn Encampment   ← Act 3 还没跑完

根因：多段会话按时间顺序 append，退出再上线那段接在末尾。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.act_map import detect_act
from routelens.route_library import merge_session_dicts


def _split(area_id: str, area: str) -> dict:
    return {"area_id": area_id, "area": area, "display": area, "segment_seconds": 60.0}


def _session(session_id: int, started: str, splits: list[dict]) -> dict:
    return {
        "session_id": session_id,
        "character": "tester",
        "started_at": started,
        "ended_at": started,
        "splits": splits,
        "chapters": [],
        "deaths": 0,
    }


class MergeActOrderTest(unittest.TestCase):
    def test_act4_town_not_inside_act3(self) -> None:
        # 会话 1：Act1 → Act4 城镇（Act3 没跑完）
        first = [
            _split("1_1_1", "The Twilight Strand"),
            _split("1_1_town", "Lioneye's Watch"),
            _split("1_3_1", "The City of Sarn"),
            _split("1_4_town", "Highgate"),
        ]
        # 会话 2：补 Act3 的剩余部分（时间上更晚）
        second = [
            _split("1_3_town", "The Sarn Encampment"),
            _split("1_3_2", "The Slums"),
            _split("1_3_3_1", "The Crematorium"),
        ]
        route = merge_session_dicts(
            [_session(1, "2026-10-22T13:03:00", first),
             _session(2, "2026-10-22T15:00:00", second)],
            source="client_txt",
            game_id="poe1",
        )
        ids = [s["area_id"] for s in route["splits"]]
        self.assertEqual(
            ids,
            ["1_1_1", "1_1_town", "1_3_1", "1_3_town", "1_3_2", "1_3_3_1", "1_4_town"],
        )
        # 幕号必须单调不减
        acts = [detect_act(i, "poe1").act for i in ids]
        self.assertEqual(acts, sorted(acts))

    def test_already_ordered_route_is_unchanged(self) -> None:
        first = [
            _split("1_1_1", "The Twilight Strand"),
            _split("1_1_town", "Lioneye's Watch"),
            _split("1_2_1", "The Southern Forest"),
            _split("1_2_town", "The Forest Encampment"),
        ]
        second = [_split("1_2_2", "The Old Fields")]
        route = merge_session_dicts(
            [_session(1, "2026-10-22T13:03:00", first),
             _session(2, "2026-10-22T14:00:00", second)],
            source="client_txt",
            game_id="poe1",
        )
        self.assertEqual(
            [s["area_id"] for s in route["splits"]],
            ["1_1_1", "1_1_town", "1_2_1", "1_2_town", "1_2_2"],
        )

    def test_single_session_not_reordered(self) -> None:
        """单会话是玩家真实顺序，绝不重排。"""
        session = _session(1, "2026-10-22T13:03:00", [
            _split("1_1_1", "The Twilight Strand"),
            _split("1_3_1", "The City of Sarn"),
            _split("1_1_2", "The Coast"),
        ])
        route = merge_session_dicts([session], source="client_txt", game_id="poe1")
        self.assertEqual(
            [s["area_id"] for s in route["splits"]],
            ["1_1_1", "1_3_1", "1_1_2"],
        )


if __name__ == "__main__":
    unittest.main()
