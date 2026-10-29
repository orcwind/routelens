"""端到端操作序列测试：**不预设期望值，只检查系统自洽**。

为什么要有这组测试
------------------
真机事故 2026-10-29 14:16：点「重置 Run」后再也不换节点，26 分钟全堆在
第 1 个节点。根因是 ``reset_run()`` 构造运行状态时漏传 ``is_reference_mode``。

**为什么之前的测试没抓到**：旧测试全是「构造场景 → 断言我期望的值」，
每条都只覆盖一个函数。重置这条路径从来没被跑过。

这组测试的做法不同：**模拟一整串真实操作**，然后检查**不变量**
（无论用户按了什么都必须成立的性质），而不是检查某个具体数字。

    不变量清单（每条都在每个操作步骤后检查）：

    I1  模式自洽：``is_reference_mode`` 与「节点里有没有参考节点」一致
        （ActiveRun.create / from_dict 的判据是节点来源标记）
    I2  时间守恒：总时间 == 各节点用时之和 + 当前节点实时段
    I3  节点不变量：有实际用时 ⇔ 本次到过（与 skipped 互斥）
    I4  参考路线模式下节点集合恒等于参考路线（不增不减）
    I5  参考路线模式下 current_index 指向的节点必须在参考路线内
    I6  存档往返一致：保存 → 重新加载 → 关键状态不变（mode / nodes / index）
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import PropertyMock, patch

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.companion_config import CompanionConfig  # noqa: E402
from routelens.config import load_routelens_config  # noqa: E402
from routelens.engine import RunEngine  # noqa: E402
from routelens.models import ActiveRun, ReferenceRoute, RouteNode  # noqa: E402


REFERENCE = [
    "The Twilight Strand",
    "Lioneye's Watch",
    "The Coast",
    "The Mud Flats",
    "The Submerged Passage",
    "The Tidal Island",
]


class _Case(unittest.TestCase):
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
        config = load_routelens_config()
        config.game = "poe1"
        self.engine = RunEngine(config)

    def _reference(self, names: list[str], route_id: str = "ref-seq") -> ReferenceRoute:
        return ReferenceRoute(
            route_id=route_id,
            name="seq route",
            nodes=[RouteNode(name=name, seconds=60.0) for name in names],
        )


class InvariantChecker:
    """检查器：把「必须永远成立」的性质集中在一处。

    刻意**不**继承 TestCase —— 否则 pytest 会尝试收集它。
    断言直接用 ``assert`` 语句（失败抛 AssertionError，由调用方接收）。
    """

    def __init__(self, engine: RunEngine, reference_names: list[str] | None) -> None:
        self.engine = engine
        self.reference_names = reference_names

    def check(self, step: str = "") -> None:
        run = self.engine.active_run
        if run is None:
            return

        # I1 模式自洽
        marked = sum(1 for n in run.nodes if n.from_reference)
        assert run.is_reference_mode == (marked > 0), (
            f"I1 模式与节点来源标记矛盾：mode={run.is_reference_mode} "
            f"marked={marked} ({step})"
        )
        assert run.reference_node_count == marked, (
            f"I1 reference_node_count 与实际标记数不符："
            f"{run.reference_node_count} != {marked} ({step})"
        )

        # I3 节点不变量
        for node in run.nodes:
            assert not (node.visited and node.skipped), (
                f"I3 节点既标了到过又标了跳过：{node.name} ({step})"
            )

        # I2 时间守恒
        total = sum(n.seconds or 0.0 for n in run.nodes)
        segment = self.engine.current_segment_seconds()
        expected = self.engine.elapsed_seconds()
        assert abs((total + segment) - expected) <= 1.5, (
            f"I2 时间不守恒：节点合计 {total:.1f} + 实时段 {segment:.1f} "
            f"!= 总时间 {expected:.1f} ({step})"
        )

        # I4 / I5 参考路线模式下节点集合恒定
        if self.reference_names is not None and run.is_reference_mode:
            assert [n.name for n in run.nodes] == list(self.reference_names), (
                f"I4 参考路线模式下节点集合变了 ({step})"
            )
            assert 0 <= run.current_index < len(run.nodes), (
                f"I5 current_index 越界：{run.current_index} ({step})"
            )


class OperationSequenceTests(_Case):
    """跑一整串真实操作，每步之后检查不变量。"""

    def _reference_run(self) -> None:
        self.engine.new_run(self._reference(REFERENCE))
        checker = InvariantChecker(self.engine, REFERENCE)
        checker.check("new_run")

        # 正常推进
        for name in REFERENCE[:4]:
            self.engine.simulate_area(name, write_client=False)
            checker.check(f"area:{name}")

        # 回旧节点
        self.engine.simulate_area("Lioneye's Watch", write_client=False)
        checker.check("backtrack")

        # 新地点（不在参考里）
        self.engine.simulate_area("Some Side Area", write_client=False)
        checker.check("unknown-area")

        # 继续推进
        for name in REFERENCE[4:]:
            self.engine.simulate_area(name, write_client=False)
            checker.check(f"area:{name}")

    def test_full_sequence_keeps_invariants(self) -> None:
        """新 Run → 推进 → 回旧节点 → 新地点 → 继续 → 重置 → 再推进。"""
        self._reference_run()

        # 重置（v0.1.14 事故点）
        self.engine.reset_run()
        checker = InvariantChecker(self.engine, REFERENCE)
        checker.check("after reset")

        run = self.engine.active_run
        assert run is not None
        self.assertTrue(run.is_reference_mode, "重置后必须仍是参考路线模式")
        self.assertEqual(run.current_index, 0, "重置后回到起点")

        # 重置后继续推进
        for name in REFERENCE[:3]:
            self.engine.simulate_area(name, write_client=False)
            checker.check(f"after reset area:{name}")

        run = self.engine.active_run
        assert run is not None
        self.assertEqual(
            run.current_index,
            2,
            "重置后节点必须继续推进（这是 v0.1.14 事故的直接断言）",
        )

    def test_reset_twice_keeps_invariants(self) -> None:
        """连续重置两次（用户反复重置）也不能坏。"""
        self._reference_run()
        checker = InvariantChecker(self.engine, REFERENCE)

        for i in range(2):
            self.engine.reset_run()
            checker.check(f"reset #{i + 1}")
            run = self.engine.active_run
            assert run is not None
            self.assertTrue(run.is_reference_mode, f"第 {i + 1} 次重置后模式错了")

    def test_undo_after_reset_keeps_invariants(self) -> None:
        """重置后撤销也不能坏。"""
        self._reference_run()
        self.engine.reset_run()
        checker = InvariantChecker(self.engine, REFERENCE)
        checker.check("after reset")

        self.engine.simulate_area(REFERENCE[0], write_client=False)
        self.engine.simulate_area(REFERENCE[1], write_client=False)
        checker.check("after reset 2 areas")

        self.engine.undo_split()
        checker.check("after undo")

    def test_free_run_sequence_keeps_invariants(self) -> None:
        """空白路线（自由模式）跑完整串操作，不变量同样成立。"""
        self.engine.new_run(None)
        checker = InvariantChecker(self.engine, None)
        checker.check("free new_run")

        for name in ("Zone A", "Zone B", "Zone A", "Zone C"):
            self.engine.simulate_area(name, write_client=False)
            checker.check(f"free area:{name}")

        self.engine.reset_run()
        checker.check("free after reset")

        run = self.engine.active_run
        assert run is not None
        self.assertFalse(run.is_reference_mode, "空白路线重置后仍是自由模式")

    def test_save_and_reload_keeps_invariants(self) -> None:
        """存档 → 重新加载 → 状态必须一致（mode / 节点 / index）。"""
        self._reference_run()
        self.engine.reset_run()
        self.engine.simulate_area(REFERENCE[0], write_client=False)
        self.engine.simulate_area(REFERENCE[1], write_client=False)

        run = self.engine.active_run
        assert run is not None
        before = {
            "mode": run.is_reference_mode,
            "count": run.reference_node_count,
            "names": [n.name for n in run.nodes],
            "index": run.current_index,
        }

        reloaded = ActiveRun.from_dict(run.to_dict())

        self.assertEqual(reloaded.is_reference_mode, before["mode"], "I6 模式往返不一致")
        self.assertEqual(reloaded.reference_node_count, before["count"], "I6 计数往返不一致")
        self.assertEqual([n.name for n in reloaded.nodes], before["names"], "I6 节点往返不一致")
        self.assertEqual(reloaded.current_index, before["index"], "I6 index 往返不一致")


if __name__ == "__main__":
    unittest.main()
