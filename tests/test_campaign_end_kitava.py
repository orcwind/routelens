"""PoE1 剧情结束：奇塔弗 -60% 永久削弱 → 暂停计时。

真机 Client.txt 实测两种形态，必须精确区分：
- Act 5  第一次奇塔弗：Kitava's **cruel** affliction     → -30% 全抗（不是结束）
- Act 10 第二次奇塔弗：Kitava's **merciless** affliction → -60% 全抗（剧情结束）
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import PropertyMock, patch

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.companion_config import CompanionConfig  # noqa: E402
from routelens.config import load_routelens_config  # noqa: E402
from routelens.engine import RunEngine  # noqa: E402
from routelens.events import EventType, GameEvent  # noqa: E402
from routelens.games.registry import get_game  # noqa: E402
from routelens.log_parser import parse_line  # noqa: E402
from routelens.models import ActiveRun  # noqa: E402

ACT5_LINE = (
    "2026/10/14 14:45:19 22762750 cffb065b [INFO Client 2184] : You have been "
    "permanently weakened by Kitava's cruel affliction. You now have -30% to all Resistances."
)
ACT10_LINE = (
    "2026/10/15 22:36:19 47477703 cffb065b [INFO Client 48040] : You have been "
    "permanently weakened by Kitava's merciless affliction. You now have a total of "
    "-60% to all Resistances."
)
ACT10_LINE_TW = (
    "2026/10/15 22:36:19 47477703 cffb065b [INFO Client 48040] : "
    "你已被奇塔弗的無情折磨永久削弱。你現在有總計 -60% 的全抗性。"
)


class CampaignEndParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.game = get_game("poe1")

    def test_act10_merciless_is_campaign_end(self) -> None:
        event = parse_line(ACT10_LINE, self.game)
        assert event is not None
        self.assertEqual(event.type, EventType.CAMPAIGN_END)
        self.assertIsInstance(event.timestamp, datetime)

    def test_act5_cruel_is_not_campaign_end(self) -> None:
        """Act 5 的 -30% 不能被当成剧情结束，否则第 5 幕就停表。"""
        self.assertIsNone(parse_line(ACT5_LINE, self.game))

    def test_traditional_chinese_act10_is_campaign_end(self) -> None:
        event = parse_line(ACT10_LINE_TW, self.game)
        assert event is not None
        self.assertEqual(event.type, EventType.CAMPAIGN_END)


class CampaignEndEngineTests(unittest.TestCase):
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

    def _campaign_end_event(self) -> GameEvent:
        return GameEvent(
            type=EventType.CAMPAIGN_END,
            timestamp=datetime.now(),
            raw_line=ACT10_LINE,
        )

    def test_act10_pauses_timer_and_marks_over(self) -> None:
        run = self.engine.new_run(None)
        self.engine.start_or_split()  # 开始计时
        self.assertTrue(self.engine.timer_running)

        self.engine.event_bus.publish(self._campaign_end_event())

        assert self.engine.active_run is not None
        self.assertTrue(self.engine.active_run.campaign_over)
        self.assertTrue(self.engine.active_run.is_paused)
        self.assertFalse(self.engine.timer_running)

    def test_areas_after_campaign_end_are_not_recorded(self) -> None:
        """剧情结束后进终局城镇 / 地图，不污染开荒路线。"""
        self.engine.new_run(None)
        self.engine.start_or_split()
        self.engine._inject_area_with_id("The Feeding Trough", "2_10_11")
        before = len(self.engine.active_run.nodes)

        self.engine.event_bus.publish(self._campaign_end_event())

        self.engine._inject_area_with_id("Karui Shores", "2_11_endgame_town")
        self.engine._inject_area_with_id("Forbidden Woods", "MapWorldsForbiddenWoods")

        assert self.engine.active_run is not None
        self.assertEqual(len(self.engine.active_run.nodes), before)
        self.assertNotIn(
            "Karui Shores", [n.name for n in self.engine.active_run.nodes]
        )

    def test_pause_happens_once(self) -> None:
        self.engine.new_run(None)
        self.engine.start_or_split()
        self.engine.event_bus.publish(self._campaign_end_event())
        elapsed_first = self.engine.active_run.elapsed_seconds
        self.engine.event_bus.publish(self._campaign_end_event())
        assert self.engine.active_run is not None
        self.assertEqual(self.engine.active_run.elapsed_seconds, elapsed_first)

    def test_new_run_clears_campaign_over(self) -> None:
        self.engine.new_run(None)
        self.engine.event_bus.publish(self._campaign_end_event())
        run = self.engine.new_run(None)
        self.assertFalse(run.campaign_over)
        self.assertFalse(run.is_paused)

    def test_campaign_over_persists_round_trip(self) -> None:
        run = ActiveRun(
            run_id="x",
            reference_route_id=None,
            reference_route_name="",
            campaign_over=True,
        )
        restored = ActiveRun.from_dict(run.to_dict())
        self.assertTrue(restored.campaign_over)


if __name__ == "__main__":
    unittest.main()
