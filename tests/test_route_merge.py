from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.campaign_end import truncate_at_campaign_end  # noqa: E402
from routelens.route_library import (  # noqa: E402
    REPEAT_NAME_MIN_GAP,
    _merge_splits,
    merge_session_dicts,
)


def _split(area: str, seconds: float, arrived: str) -> dict:
    return {
        "area": area,
        "area_en": area,
        "segment_seconds": seconds,
        "arrived_at": arrived,
    }


def _filler(count: int) -> list[dict]:
    return [
        _split(f"Filler {i}", 1, f"2026-10-24T11:{i:02d}:00")
        for i in range(count)
    ]


class Poe1RepeatedAreaTests(unittest.TestCase):
    def test_keeps_repeated_area_names_across_acts(self) -> None:
        # PoE1 的 Act 6 会重新进入 Act 1 的同名区域（距离远 = 真实新进度）
        session = [
            _split("Lioneye's Watch", 10, "2026-10-24T10:00:00"),
            _split("The Coast", 20, "2026-10-24T10:01:00"),
        ]
        session += _filler(REPEAT_NAME_MIN_GAP + 2)
        session += [
            _split("Lioneye's Watch", 30, "2026-10-24T12:00:00"),
            _split("The Coast", 40, "2026-10-24T12:01:00"),
        ]
        merged = _merge_splits([], session, keep_repeated_names=True)
        self.assertEqual(
            [item["area"] for item in merged[-2:]],
            ["Lioneye's Watch", "The Coast"],
        )
        self.assertEqual(len(merged), len(session))

    def test_drops_nearby_town_backtrack(self) -> None:
        # 回城 / 复活折返近距离同名区域 = 噪声
        session = [
            _split("Oriath Square", 10, "2026-10-24T10:00:00"),
            _split("The Templar Courts", 20, "2026-10-24T10:01:00"),
            _split("Oriath Square", 5, "2026-10-24T10:02:00"),
        ]
        merged = _merge_splits([], session, keep_repeated_names=True)
        self.assertEqual(
            [item["area"] for item in merged],
            ["Oriath Square", "The Templar Courts"],
        )

    def test_same_arrival_merged_twice_is_idempotent(self) -> None:
        session = _filler(30)
        once = _merge_splits([], session, keep_repeated_names=True)
        twice = _merge_splits(once, session, keep_repeated_names=True)
        self.assertEqual(len(once), len(twice))

    def test_merge_session_poe1_keeps_act6(self) -> None:
        first = {
            "character": "c",
            "started_at": "2026-10-24T10:00:00",
            "ended_at": "2026-10-24T11:00:00",
            "splits": [
                _split("Lioneye's Watch", 10, "2026-10-24T10:00:00"),
                _split("The Coast", 20, "2026-10-24T10:01:00"),
            ]
            + _filler(REPEAT_NAME_MIN_GAP + 2),
        }
        second = {
            "character": "c",
            "started_at": "2026-10-24T12:00:00",
            "ended_at": "2026-10-24T13:00:00",
            "splits": [
                _split("Lioneye's Watch", 30, "2026-10-24T12:00:00"),
                _split("The Mud Flats", 40, "2026-10-24T12:01:00"),
            ],
        }
        merged = merge_session_dicts([first, second], source="client_txt", game_id="poe1")
        self.assertEqual(
            [item["area"] for item in merged["splits"]][-2:],
            ["Lioneye's Watch", "The Mud Flats"],
        )


class Poe2RepeatedAreaTests(unittest.TestCase):
    def test_repeated_town_collapses(self) -> None:
        # PoE2 战役单轮，回城反复出现应只保留一次
        session = [
            _split("Clearfell Encampment", 10, "2026-10-24T10:00:00"),
            _split("The Grelwood", 20, "2026-10-24T10:01:00"),
            _split("Clearfell Encampment", 5, "2026-10-24T10:02:00"),
            _split("The Red Vale", 30, "2026-10-24T10:03:00"),
            _split("Clearfell Encampment", 5, "2026-10-24T10:04:00"),
        ]
        merged = _merge_splits([], session)
        self.assertEqual(
            [item["area"] for item in merged],
            ["Clearfell Encampment", "The Grelwood", "The Red Vale"],
        )

    def test_merge_session_poe2_dedupes_by_name(self) -> None:
        first = {
            "character": "c",
            "started_at": "2026-10-24T10:00:00",
            "splits": [_split("The Grelwood", 10, "2026-10-24T10:00:00")],
        }
        second = {
            "character": "c",
            "started_at": "2026-10-24T12:00:00",
            "splits": [_split("The Grelwood", 20, "2026-10-24T12:00:00")],
        }
        merged = merge_session_dicts([first, second], source="client_txt", game_id="poe2")
        self.assertEqual([item["area"] for item in merged["splits"]], ["The Grelwood"])


class KaruiShoresTruncateTests(unittest.TestCase):
    def test_act5_transition_is_not_campaign_end(self) -> None:
        splits = [
            {"area": "The Cathedral Rooftop"},
            {"area": "Karui Shores"},
            {"area": "Lioneye's Watch"},
            {"area": "The Coast"},
        ]
        truncated = truncate_at_campaign_end(splits, "poe1")
        self.assertEqual(
            [s["area"] for s in truncated],
            ["The Cathedral Rooftop", "Karui Shores", "Lioneye's Watch", "The Coast"],
        )

    def test_act10_end_still_truncates_after_final_boss(self) -> None:
        splits = [
            {"area": "The Feeding Trough"},
            {"area": "Karui Shores"},
            {"area": "Volcano"},
        ]
        truncated = truncate_at_campaign_end(splits, "poe1")
        self.assertEqual(
            [s["area"] for s in truncated],
            ["The Feeding Trough", "Karui Shores"],
        )


class Poe2CampaignEndTests(unittest.TestCase):
    def test_endgame_hub_is_not_reached_mid_campaign(self) -> None:
        # Act 3 途中反复回城（高地神塔營地）不应被当成终局枢纽截断
        splits = [
            {"area": "高地神塔營地"},
            {"area": "叢林遺跡"},
            {"area": "高地神塔營地"},
            {"area": "瑪特蘭水道"},
            {"area": "高地神塔庇護所"},
            {"area": "輿圖"},
        ]
        truncated = truncate_at_campaign_end(splits, "poe2")
        self.assertEqual(
            [s["area"] for s in truncated],
            ["高地神塔營地", "叢林遺跡", "高地神塔營地", "瑪特蘭水道", "高地神塔庇護所"],
        )


if __name__ == "__main__":
    unittest.main()
