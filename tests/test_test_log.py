from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from companion import test_log


class TestLogTests(unittest.TestCase):
    def test_write_creates_log_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = test_log.init_log(Path(tmp))
            test_log.write("USER", "测试操作", area="皆伐", ok=True)
            content = log_path.read_text(encoding="utf-8")
            self.assertIn("[USER] 测试操作", content)
            self.assertIn("皆伐", content)
            self.assertIn("ok", content)


if __name__ == "__main__":
    unittest.main()
