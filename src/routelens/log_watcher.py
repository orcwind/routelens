from __future__ import annotations

import threading
import time
from pathlib import Path

from .events import EventBus
from .games.base import GameProfile
from .games.registry import get_game
from .log_parser import GENERATING_AREA_RE, parse_line


class LogWatcher:
    def __init__(
        self,
        log_path: Path,
        event_bus: EventBus,
        poll_interval: float = 0.2,
        game: GameProfile | None = None,
    ) -> None:
        self.log_path = log_path
        self.event_bus = event_bus
        self.poll_interval = poll_interval
        self.game = game or get_game("poe2")
        self._running = False
        self._thread: threading.Thread | None = None
        self._offset = 0
        self._paused = False
        # 最近的 area id（幕归属权威来源）
        self._last_area_id = ""

    @property
    def paused(self) -> bool:
        return self._paused

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        if not self.log_path.exists():
            raise FileNotFoundError(f"找不到 Client.txt：{self.log_path}")

        self._offset = self.log_path.stat().st_size
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def seek_to_end(self) -> None:
        if self.log_path.exists():
            self._offset = self.log_path.stat().st_size

    def flush(self) -> None:
        if self._running:
            self._read_new_lines()

    def read_tail(self, max_bytes: int = 1024 * 1024) -> list[str]:
        if not self.log_path.exists():
            return []

        size = self.log_path.stat().st_size
        start = max(0, size - max_bytes)
        with self.log_path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(start)
            if start > 0:
                handle.readline()
            return handle.readlines()

    def _loop(self) -> None:
        while self._running:
            try:
                self._read_new_lines()
            except OSError:
                time.sleep(1.0)
            time.sleep(self.poll_interval)

    def _read_new_lines(self) -> None:
        if self._paused or not self.log_path.exists():
            return

        size = self.log_path.stat().st_size
        if size < self._offset:
            self._offset = 0

        if size == self._offset:
            return

        with self.log_path.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(self._offset)
            for line in handle:
                generating = GENERATING_AREA_RE.search(line)
                if generating:
                    self._last_area_id = generating.group(1).strip()
                event = parse_line(line, self.game, last_area_id=self._last_area_id)
                if event is not None:
                    self.event_bus.publish(event)
            self._offset = handle.tell()
