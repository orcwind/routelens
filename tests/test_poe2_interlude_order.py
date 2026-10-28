"""間歇（PoE2 Interlude）在路线里必须归位。

真机证据（2026-10-27 用户日志 ``azdasfasdfsa``）：多会话合并后間歇段顺序是

    P3_Town P3_1 … P3_4 P1_Town P1_1 … P2_7      ← P3 跑到了 P1 前面

``_order_splits_by_act`` 现在把間歇按 P1 → P2 → P3、组内 Town → _1 → _2 … 排。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.route_library import _order_splits_by_act

INTERLUDE_ORDER = [
    "P1_Town", "P1_1", "P1_2", "P1_3", "P1_4", "P1_5", "P1_6",
    "P2_Town", "P2_1", "P2_2", "P2_3", "P2_5", "P2_6", "P2_7",
    "P3_Town", "P3_1", "P3_2", "P3_3", "P3_4", "P3_5", "P3_6", "P3_7",
]


def _split(area_id: str) -> dict:
    return {"area": area_id, "area_id": area_id}


class InterludeOrderTest(unittest.TestCase):
    def test_scrambled_interlude_is_reordered(self) -> None:
        scrambled = [
            _split("P3_Town"), _split("P3_1"), _split("P3_4"),
            _split("P1_Town"), _split("P1_1"), _split("P1_6"),
            _split("P2_Town"), _split("P2_7"),
        ]
        ordered = [s["area_id"] for s in _order_splits_by_act(scrambled, "poe2")]
        self.assertEqual(
            ordered,
            ["P1_Town", "P1_1", "P1_6", "P2_Town", "P2_7", "P3_Town", "P3_1", "P3_4"],
        )

    def test_full_interlude_passes_through_sorted(self) -> None:
        splits = [_split(a) for a in INTERLUDE_ORDER]
        ordered = [s["area_id"] for s in _order_splits_by_act(splits, "poe2")]
        self.assertEqual(ordered, INTERLUDE_ORDER)

    def test_interlude_sits_after_act4_before_endgame(self) -> None:
        splits = [
            _split("P1_Town"), _split("P1_1"),
            _split("G4_town"), _split("G4_15"),
            _split("G_Endgame_Town"),
            _split("G1_1"),
        ]
        ordered = [s["area_id"] for s in _order_splits_by_act(splits, "poe2")]
        # Act 1 → Act 4 → 間歇 → 終局（endgame 无幕号，跟随前一个节点）
        self.assertEqual(
            ordered,
            ["G1_1", "G4_town", "G4_15", "P1_Town", "P1_1", "G_Endgame_Town"],
        )

    def test_poe1_order_unaffected(self) -> None:
        """PoE1 的 P 前缀没有間歇含义，不能被当成間歇打乱。"""
        splits = [_split("1_1_1"), _split("1_2_1"), _split("1_10_1")]
        ordered = [s["area_id"] for s in _order_splits_by_act(splits, "poe1")]
        self.assertEqual(ordered, ["1_1_1", "1_2_1", "1_10_1"])


if __name__ == "__main__":
    unittest.main()
