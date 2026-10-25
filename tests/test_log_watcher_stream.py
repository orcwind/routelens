"""回归测试：实时日志监听（LogWatcher）的解析规则。

与离线分析（log_analyzer）保持一致：
- 非游戏主进程（Client 99999）写入的场景名要忽略
- 一批 Generating 只对应一个真实区域（第一个非 null 的 Set Source）
- area id 消费式配对（生成即消费）
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.events import EventBus, EventType  # noqa: E402
from routelens.games.registry import get_game  # noqa: E402
from routelens.log_watcher import LogWatcher  # noqa: E402

BASE = datetime(2026, 10, 25, 12, 0, 0)


def _line(offset: int, text: str, client: int = 1000) -> str:
    t = (BASE + timedelta(seconds=offset)).strftime("%Y/%m/%d %H:%M:%S")
    return f"{t} 12345678 abcdef01 [INFO Client {client}] {text}\n"


class LogWatcherStreamTests(unittest.TestCase):
    def _watch(self, body: str, game: str = "poe1") -> list:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "Client.txt"
            path.write_text(body, encoding="utf-8")
            bus = EventBus()
            watcher = LogWatcher(path, bus, game=get_game(game))
            events: list = []
            bus.subscribe(EventType.AREA_ENTERED, events.append)
            watcher._read_new_lines()
            return events

    def test_area_entered_carries_area_id(self) -> None:
        events = self._watch(
            _line(0, 'Generating level 33 area "1_1_2" with seed 1')
            + _line(1, ": You have entered The Coast.")
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].area, "The Coast")
        self.assertEqual(events[0].area_id, "1_1_2")

    def test_foreign_client_is_ignored(self) -> None:
        events = self._watch(
            _line(0, 'Generating level 33 area "1_1_2" with seed 1')
            + _line(1, ": You have entered The Coast.")
            + _line(2, "[SCENE] Set Source [幕間章]", client=99999)
        )
        self.assertEqual([e.area for e in events], ["The Coast"])

    def test_poe2_batch_yields_single_area(self) -> None:
        events = self._watch(
            _line(0, 'Generating level 33 area "P2_1" with seed 1')
            + _line(1, "[SCENE] Set Source [(null)]")
            + _line(2, "[SCENE] Set Source [卡里交匯道]")
            + _line(3, "[SCENE] Set Source [幕間章]")
            + _line(4, "[SCENE] Set Source [(null)]"),
            game="poe2",
        )
        self.assertEqual([e.area for e in events], ["卡里交匯道"])
        self.assertEqual(events[0].area_id, "P2_1")

    def test_area_id_is_consumed_not_reused(self) -> None:
        """第二个区域没有新的 Generating → 不应复用上一个 id。"""
        events = self._watch(
            _line(0, 'Generating level 33 area "1_1_2" with seed 1')
            + _line(1, ": You have entered The Coast.")
            + _line(2, ": You have entered The Mud Flats.")
        )
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].area_id, "1_1_2")
        self.assertEqual(events[1].area_id, "")

    def test_scene_without_generating_is_ignored(self) -> None:
        events = self._watch(
            _line(0, "[SCENE] Set Source [幕間章]")
            + _line(1, "[SCENE] Set Source [The Twilight Strand]")
        )
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
