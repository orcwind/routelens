from __future__ import annotations

import unittest

from companion.chapter_normalize import normalize_poe2_chapter
from companion.log_locale import detect_client_log_locale


class LocaleSupportTests(unittest.TestCase):
    def test_normalize_chapter_multilingual(self) -> None:
        self.assertEqual(normalize_poe2_chapter("第一章"), "第一章")
        self.assertEqual(normalize_poe2_chapter("Act 3"), "第三章")
        self.assertEqual(normalize_poe2_chapter("act 4"), "第四章")
        self.assertEqual(normalize_poe2_chapter("Chapter 2"), "第二章")
        self.assertEqual(normalize_poe2_chapter("第5章"), "第五章")
        self.assertIsNone(normalize_poe2_chapter("Act 6"))
        self.assertIsNone(normalize_poe2_chapter("Lioneye's Watch"))

    def test_detect_english_log(self) -> None:
        from tempfile import TemporaryDirectory
        from pathlib import Path

        text = "\n".join(
            [
                "***** LOG FILE OPENING *****",
                "2026/01/01 12:00:00 1 [INFO Client 1] : You have entered Lioneye's Watch.",
                "2026/01/01 12:01:00 2 [INFO Client 1] : You have entered The Coast.",
            ]
            * 5
        )
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "Client.txt"
            path.write_text(text, encoding="utf-8")
            self.assertEqual(detect_client_log_locale(path), "en")

    def test_detect_traditional_chinese_log(self) -> None:
        from tempfile import TemporaryDirectory
        from pathlib import Path

        text = "\n".join(
            [
                "***** LOG FILE OPENING *****",
                "2026/01/01 12:00:00 1 [INFO Client 1] [SCENE] Set Source [第一章]",
                "2026/01/01 12:00:10 2 [INFO Client 1] [SCENE] Set Source [皆伐營地]",
                "2026/01/01 12:00:20 3 [INFO Client 1] [SCENE] Set Source [風沙沼澤]",
            ]
            * 5
        )
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "Client.txt"
            path.write_text(text, encoding="utf-8")
            self.assertEqual(detect_client_log_locale(path), "zh_tw")


if __name__ == "__main__":
    unittest.main()
