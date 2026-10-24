from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.campaign_end import truncate_at_campaign_end  # noqa: E402
from routelens.route_library import _merge_splits, merge_session_dicts  # noqa: E402


def _split(area: str, seconds: float, arrived: str) -> dict:
    return {
        "area": area,
        "area_en": area,
        "segment_seconds": seconds,
        "arrived_at": arrived,
    }


class MergeSplitsTests(unittest.TestCase):
    def test_keeps_repeated_area_names_across_acts(self) -> None:
        # PoE1 的 Act 6 会重新进入 Act 1 的同名区域，不能按区域名去重
        session = [
            _split("Lioneye's Watch", 10, "2026-10-24T10:00:00"),
            _split("The Coast", 20, "2026-10-24T10:01:00"),
            _split("The Cathedral Rooftop", 30, "2026-10-24T12:00:00"),
            _split("Lioneye's Watch", 40, "2026-10-24T12:05:00"),
            _split("The Coast", 50, "2026-10-24T12:06:00"),
        ]
        merged = _merge_splits([], session)
        self.assertEqual(
            [item["area"] for item in merged],
            [
                "Lioneye's Watch",
                "The Coast",
                "The Cathedral Rooftop",
                "Lioneye's Watch",
                "The Coast",
            ],
        )

    def test_drops_adjacent_duplicate_area(self) -> None:
        session = [
            _split("Oriath Square", 10, "2026-10-24T10:00:00"),
            _split("Oriath Square", 5, "2026-10-24T10:00:30"),
            _split("The Templar Courts", 20, "2026-10-24T10:02:00"),
        ]
        merged = _merge_splits([], session)
        self.assertEqual(
            [item["area"] for item in merged],
            ["Oriath Square", "The Templar Courts"],
        )

    def test_same_arrival_merged_twice_is_idempotent(self) -> None:
        session = [
            _split("The Coast", 10, "2026-10-24T10:00:00"),
            _split("The Coast", 20, "2026-10-24T10:05:00"),
        ]
        once = _merge_splits([], session)
        twice = _merge_splits(once, session)
        self.assertEqual(len(once), len(twice))
        self.assertEqual([i["area"] for i in twice], ["The Coast"])

    def test_merge_session_does_not_lose_second_half(self) -> None:
        first = {
            "character": "c",
            "started_at": "2026-10-24T10:00:00",
            "ended_at": "2026-10-24T11:00:00",
            "splits": [
                _split("Lioneye's Watch", 10, "2026-10-24T10:00:00"),
                _split("The Coast", 20, "2026-10-24T10:01:00"),
            ],
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
        merged = merge_session_dicts([first, second], source="client_txt")
        self.assertEqual(
            [item["area"] for item in merged["splits"]],
            ["Lioneye's Watch", "The Coast", "Lioneye's Watch", "The Mud Flats"],
        )


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


if __name__ == "__main__":
    unittest.main()
