from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.game_detect import (  # noqa: E402
    POE1_AREA_SIGNATURES,
    POE2_AREA_SIGNATURES,
    detect_game_from_area_names,
    detect_game_from_log,
    resolve_import_game,
)
from routelens.store import RouteLensStore  # noqa: E402


class GameDetectTests(unittest.TestCase):
    def test_user_agent_poe1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Client.txt"
            path.write_text(
                "2026/09/18 13:12:39 ***** LOG FILE OPENING *****\n"
                "2026/09/18 13:12:39 17119609 3b79be17 [INFO Client 36876] "
                "[HTTP2] User agent: PoE release/tags/3.29.3b Windows x64\n",
                encoding="utf-8",
            )
            self.assertEqual(detect_game_from_log(path), "poe1")

    def test_user_agent_poe2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Client.txt"
            path.write_text(
                "[HTTP2] User agent: PathOfExile2 release/tags/0.3.0 Windows x64\n",
                encoding="utf-8",
            )
            self.assertEqual(detect_game_from_log(path), "poe2")

    def test_user_agent_poe2_production(self) -> None:
        # 实测 PoE2 写法："PoE poe2_production/tags/4.5.5 Windows x64"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Client.txt"
            path.write_text(
                "[INFO Client 1] [HTTP2] User agent: PoE poe2_production/tags/4.5.5 Windows x64\n",
                encoding="utf-8",
            )
            self.assertEqual(detect_game_from_log(path), "poe2")

    def test_user_agent_poe1_is_not_mistaken_for_poe2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Client.txt"
            path.write_text(
                "[HTTP2] User agent: PoE release/tags/3.25.0 Windows x64\n",
                encoding="utf-8",
            )
            self.assertEqual(detect_game_from_log(path), "poe1")

    def test_unknown_log_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Client.txt"
            path.write_text("nothing useful here\n", encoding="utf-8")
            self.assertIsNone(detect_game_from_log(path))

    def test_missing_file_returns_none(self) -> None:
        self.assertIsNone(detect_game_from_log(Path("no-such-file-xyz.txt")))

    def test_area_signatures_do_not_overlap(self) -> None:
        self.assertEqual(POE1_AREA_SIGNATURES & POE2_AREA_SIGNATURES, frozenset())

    def test_area_names_poe1(self) -> None:
        names = ["Lioneye's Watch", "The Coast", "The Mud Flats", "Highgate"]
        self.assertEqual(detect_game_from_area_names(names), "poe1")

    def test_area_names_poe2(self) -> None:
        names = ["The Riverbank", "Clearfell", "The Grelwood", "The Red Vale"]
        self.assertEqual(detect_game_from_area_names(names), "poe2")

    def test_area_names_need_enough_evidence(self) -> None:
        self.assertIsNone(detect_game_from_area_names(["Lioneye's Watch"]))
        self.assertIsNone(detect_game_from_area_names([]))

    def test_resolve_import_game_prefers_log_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Client.txt"
            path.write_text(
                "[HTTP2] User agent: PoE release/tags/3.29.3b Windows x64\n",
                encoding="utf-8",
            )
            # 用户在 PoE2 那一行选了 PoE1 的日志：以日志为准
            self.assertEqual(resolve_import_game(path, "poe2"), "poe1")

    def test_resolve_import_game_falls_back_to_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "Client.txt"
            path.write_text("no markers\n", encoding="utf-8")
            self.assertEqual(resolve_import_game(path, "POE2"), "poe2")
            self.assertIsNone(resolve_import_game(path, None))


class RouteGameRepairTests(unittest.TestCase):
    def _write_route(self, store: RouteLensStore, route_id: str, game_id: str, names: list[str]) -> Path:
        data = {
            "route_id": route_id,
            "name": f"route-{route_id}",
            "nodes": [{"name": name, "seconds": 10.0} for name in names],
            "created_at": "2026-10-20T10:00:00",
            "run_count": 0,
            "best_seconds": 40.0,
            "source": "client_txt",
            "character": "char",
            "game_id": game_id,
            "is_favorite": False,
        }
        path = store.routes_dir / f"{route_id}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def test_repair_mislabeled_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = RouteLensStore(Path(tmp))
            path = self._write_route(
                store, "r1", "poe2", ["Lioneye's Watch", "The Coast", "The Mud Flats"]
            )

            fixed = store.repair_client_route_games()

            self.assertEqual(len(fixed), 1)
            self.assertEqual(fixed[0][1:], ("poe2", "poe1"))
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["game_id"], "poe1")
            self.assertTrue((store.routes_dir / "_gamefix_backup" / path.name).is_file())

    def test_repair_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = RouteLensStore(Path(tmp))
            self._write_route(
                store, "r1", "poe2", ["Lioneye's Watch", "The Coast", "The Mud Flats"]
            )
            store.repair_client_route_games()
            self.assertEqual(store.repair_client_route_games(), [])

    def test_repair_leaves_correct_route_alone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = RouteLensStore(Path(tmp))
            path = self._write_route(
                store, "r1", "poe2", ["The Riverbank", "Clearfell", "The Grelwood"]
            )
            self.assertEqual(store.repair_client_route_games(), [])
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["game_id"], "poe2")

    def test_repair_skips_manual_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = RouteLensStore(Path(tmp))
            path = self._write_route(
                store, "r1", "poe2", ["Lioneye's Watch", "The Coast", "The Mud Flats"]
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            data["source"] = "manual"
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.assertEqual(store.repair_client_route_games(), [])


if __name__ == "__main__":
    unittest.main()
