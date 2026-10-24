from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.config import load_routelens_config  # noqa: E402
from routelens.engine import MAX_FORWARD_MATCH, RunEngine  # noqa: E402
from routelens.models import ReferenceRoute, RouteNode  # noqa: E402


class ForwardMatchWindowTests(unittest.TestCase):
    def _engine(self) -> RunEngine:
        return RunEngine(load_routelens_config())

    def _route_with_duplicate_names(self) -> ReferenceRoute:
        # Act 1 前半 + 一段其它区域 + Act 6 重新进入同名区域
        names = ["Lioneye's Watch", "The Coast", "The Mud Flats"]
        names += [f"Filler {i}" for i in range(MAX_FORWARD_MATCH + 2)]
        names += ["Lioneye's Watch", "The Coast"]
        return ReferenceRoute(
            route_id="test-dup-acts",
            name="Act1+Act6",
            nodes=[RouteNode(name=name) for name in names],
        )

    def test_respawn_town_does_not_jump_to_later_act(self) -> None:
        engine = self._engine()
        route = self._route_with_duplicate_names()
        engine.new_run(route)
        engine.simulate_area("Lioneye's Watch", write_client=False)
        engine.simulate_area("The Coast", write_client=False)

        # Act 1 死亡后回到同名城镇：路线里有同名节点，不能跳到远处 Act 6 的那个
        engine.simulate_area("Lioneye's Watch", write_client=False)

        assert engine.active_run is not None
        self.assertEqual(engine.active_run.current_index, 1)
        self.assertFalse(
            any(node.skipped for node in engine.active_run.nodes),
            "不应把中间节点整段标成跳过",
        )

    def test_unique_name_still_allows_long_jump(self) -> None:
        engine = self._engine()
        names = ["The Coast"] + [f"Filler {i}" for i in range(MAX_FORWARD_MATCH + 5)]
        names.append("The Mud Flats")
        route = ReferenceRoute(
            route_id="test-unique",
            name="LongJump",
            nodes=[RouteNode(name=name) for name in names],
        )
        engine.new_run(route)
        engine.simulate_area("The Coast", write_client=False)
        engine.simulate_area("The Mud Flats", write_client=False)

        assert engine.active_run is not None
        self.assertEqual(engine.active_run.current_index, len(names) - 1)

    def test_nearby_duplicate_still_matches(self) -> None:
        engine = self._engine()
        route = self._route_with_duplicate_names()
        engine.new_run(route)
        engine.simulate_area("Lioneye's Watch", write_client=False)
        engine.simulate_area("The Coast", write_client=False)

        # 正常推进（相邻节点）不受窗口影响
        engine.simulate_area("The Mud Flats", write_client=False)
        assert engine.active_run is not None
        self.assertEqual(engine.active_run.current_index, 2)
        self.assertTrue(engine.active_run.nodes[1].completed)


if __name__ == "__main__":
    unittest.main()
