"""运行游戏归属：路线是 PoE1 时，幕数必须是 10，不能跟设置里的当前游戏。

事故（2026-10-27，用户真机截图）：

* 设置 ``config.json`` 的 ``game`` 是 ``null`` → 加载时回落默认 ``poe2``
* 导入的 PoE1 路线 ``gagffdgsfg (第一章 → 第十章)``（144 节点，game_id=poe1）
* 新建 Run 后切「幕」视图 → **只有 4 幕**（按 poe2 判）
* 空白的 PoE1 路线种子起点按 poe2 种成 ``G1_1``，与真实 ``1_1_1`` 对不上
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.act_map import act_count
from routelens.companion_config import CompanionConfig
from routelens.engine import RunEngine
from routelens.models import ActiveRun, ReferenceRoute, RouteNode


def _config(game: str = "poe2") -> CompanionConfig:
    """用真实加载器拿一份配置（字段多），只覆盖 game。"""
    from dataclasses import replace

    from routelens.config import load_routelens_config

    return replace(load_routelens_config(), game=game)


def _poe1_route() -> ReferenceRoute:
    return ReferenceRoute(
        route_id="r-poe1",
        name="gagffdgsfg (第一章 → 第十章)",
        nodes=[
            RouteNode(name="The Twilight Strand", seconds=10.0, area_id="1_1_1"),
            RouteNode(name="Lioneye's Watch", seconds=20.0, area_id="1_1_town"),
            RouteNode(name="The Sarn Encampment", seconds=30.0, area_id="1_3_town"),
            RouteNode(name="Highgate", seconds=40.0, area_id="2_8_town"),
        ],
        game_id="poe1",
    )


class RunGameOwnershipTest(unittest.TestCase):
    def test_active_run_records_game_id(self) -> None:
        run = ActiveRun(
            run_id="x",
            reference_route_id=None,
            reference_route_name="",
            game_id="poe1",
        )
        self.assertEqual(ActiveRun.from_dict(run.to_dict()).game_id, "poe1")

    def test_route_game_wins_over_config_game(self) -> None:
        """设置写 poe2、路线是 poe1 → 本次运行必须判成 poe1（10 幕）。"""
        engine = RunEngine(_config("poe2"))
        run = engine.new_run(_poe1_route())
        self.assertEqual(run.game_id, "poe1")
        self.assertEqual(engine._run_game_id(), "poe1")
        self.assertEqual(act_count(engine._run_game_id()), 10)

    def test_blank_run_seeds_poe1_start(self) -> None:
        """空白路线的种子起点必须是本游戏的第一幕（PoE1 = 1_1_1）。"""
        engine = RunEngine(_config("poe1"))
        run = engine.new_run(None)
        self.assertTrue(run.nodes)
        self.assertEqual(run.nodes[0].area_id, "1_1_1")

    def test_blank_run_in_poe2_seeds_g1_1(self) -> None:
        engine = RunEngine(_config("poe2"))
        run = engine.new_run(None)
        self.assertTrue(run.nodes)
        self.assertEqual(run.nodes[0].area_id, "G1_1")

    def test_area_id_infers_game(self) -> None:
        """旧存档没有 run.game_id 时，靠 area id 兜底判游戏。"""
        from routelens.act_map import infer_game_from_area_id

        self.assertEqual(infer_game_from_area_id("1_1_1"), "poe1")
        self.assertEqual(infer_game_from_area_id("2_10_9"), "poe1")
        self.assertEqual(infer_game_from_area_id("MapWorldsEstuary"), "poe1")
        self.assertEqual(infer_game_from_area_id("G1_1"), "poe2")
        self.assertEqual(infer_game_from_area_id("G_Endgame_Town"), "poe2")
        self.assertEqual(infer_game_from_area_id("P1_Town"), "")
        self.assertEqual(infer_game_from_area_id(""), "")

    def test_poe1_route_has_ten_acts(self) -> None:
        """回归：截图事故 —— PoE1 路线切幕视图必须是 10 幕。"""
        engine = RunEngine(_config("poe2"))
        run = engine.new_run(_poe1_route())
        self.assertEqual(act_count(engine._run_game_id()), 10)
        self.assertEqual(len(run.nodes), 4)
        # 第 3 个节点是 Act 3 城镇，必须落在 Act 3 而不是「未知」
        from routelens.act_map import detect_act

        self.assertEqual(detect_act(run.nodes[2].area_id, engine._run_game_id()).act, 3)


if __name__ == "__main__":
    unittest.main()
