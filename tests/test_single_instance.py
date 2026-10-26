"""单实例守卫测试：第二份进程不得抢 Shift+S，且必须能唤醒已有实例。"""

from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from routelens import single_instance  # noqa: E402


class SingleInstanceTest(unittest.TestCase):
    def test_second_acquire_is_rejected(self) -> None:
        self.assertTrue(single_instance.acquire_single_instance())
        # 同名互斥体已存在 → 第二个实例必须被拒绝（否则两进程抢 RegisterHotKey）
        self.assertFalse(single_instance.acquire_single_instance())

    def test_signal_wakes_running_instance(self) -> None:
        handle = single_instance.create_activation_event()
        self.assertTrue(handle)
        fired = threading.Event()
        single_instance.start_activation_watcher(handle, fired.set)
        self.assertTrue(single_instance.signal_existing_instance())
        self.assertTrue(fired.wait(timeout=3.0), "唤醒事件未触发回调")


if __name__ == "__main__":
    unittest.main()
