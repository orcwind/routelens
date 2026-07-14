from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from companion.log_analyzer import analyze_client_log, discover_chapters_in_log, format_duration
from companion.livesplit_export import export_lss, update_livesplit_settings


class LogAnalyzerIntegrationTests(unittest.TestCase):
    def test_discover_chapters(self) -> None:
        client_path = Path(__file__).resolve().parents[1] / "data" / "Client.txt"
        if not client_path.exists():
            self.skipTest("sample Client.txt not available")
        chapters = discover_chapters_in_log(client_path)
        self.assertIn("第二章", chapters)
        self.assertIn("第三章", chapters)

    def test_analyze_single_chapter(self) -> None:
        client_path = Path(__file__).resolve().parents[1] / "data" / "Client.txt"
        if not client_path.exists():
            self.skipTest("sample Client.txt not available")

        all_sessions = analyze_client_log(client_path, game_id="poe2", chapters_filter=None)
        act2_sessions = analyze_client_log(
            client_path,
            game_id="poe2",
            chapters_filter={"第二章"},
            min_nodes=1,
        )
        self.assertGreaterEqual(len(all_sessions), 1)
        self.assertGreaterEqual(len(act2_sessions), 1)
        act2_nodes = act2_sessions[0].build_splits(chapters_filter={"第二章"})
        full_nodes = all_sessions[0].build_splits()
        self.assertLessEqual(len(act2_nodes), len(full_nodes))
        self.assertGreater(len(act2_nodes), 0)

    def test_analyze_sample_client_log(self) -> None:
        client_path = Path(__file__).resolve().parents[1] / "data" / "Client.txt"
        if not client_path.exists():
            self.skipTest("sample Client.txt not available")

        sessions = analyze_client_log(client_path, game_id="poe2")
        self.assertGreaterEqual(len(sessions), 1)
        first = sessions[0].to_dict()
        self.assertIn("splits", first)
        self.assertGreater(first["node_count"], 0)
        self.assertTrue(format_duration(first["total_seconds"]))


class LiveSplitExportTests(unittest.TestCase):
    def test_export_lss(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "test.lss"
            export_lss(
                path,
                [
                    {"area_en": "Clearfell", "display": "皆伐", "segment_seconds": 95.5},
                    {"area_en": "The Red Vale", "display": "赤谷", "segment_seconds": 120.0},
                ],
            )
            content = path.read_text(encoding="utf-8")
            self.assertIn("Clearfell", content)

    def test_export_lss_chinese(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "test.lss"
            export_lss(
                path,
                [{"area_en": "Clearfell", "display": "皆伐", "segment_seconds": 10.0}],
                use_chinese_names=True,
            )
            content = path.read_text(encoding="utf-8")
            self.assertIn("皆伐", content)

    def test_update_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Path(temp_dir) / "settings.cfg"
            shutil.copy(
                Path(__file__).resolve().parents[1] / "livesplitEN" / "settings.cfg",
                settings,
            )
            lss = Path(temp_dir) / "poe2_route.lss"
            lss.write_text("test", encoding="utf-8")
            update_livesplit_settings(settings, lss)
            content = settings.read_text(encoding="utf-8")
            self.assertIn(str(lss.resolve()), content)
            self.assertIn("Path of Exile 2", content)


if __name__ == "__main__":
    unittest.main()
