"""离开世界（回登录 / 换账号）的用时边界。

真机证据（2026-10-27 14:28:41 → 14:32:55，E:\\POE\\logs\\Client.txt）：

    14:28:41  GEN 1_1_1  → A 进游戏
    14:28:48  (null)+(unknown)  → A 退出（回选角）
    14:29:56  重新登录
    14:29:57  GEN 1_1_1  → B 进游戏（**另一个账号**）
    14:30:02  (null)+(unknown)  → B 退出
    14:31:36  GEN 1_1_1  → A 再进游戏
    14:32:41  : nasdfsdfasdfsa (Duelist) is now level 2
    14:32:50  进入 1_1_town

Client.txt **没有登录时的角色名**（名字只出现在升级 / 死亡行），
所以无法把三次登录按角色切开；但可以保证「离开世界的空档」
不被算进任何一个区域的用时，且重新登录后的同名区域重新计时。
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))

from routelens.log_analyzer import analyze_client_log

OPEN = "2026/10/27 14:28:00 12345 ***** LOG FILE OPENING *****"

LINES = [
    # ── 第 1 次登录（A）：进 Twilight Strand 5 秒后退出 ──
    "2026/10/27 14:28:41 26040000 [SCENE] Set Source [(null)]",
    '2026/10/27 14:28:41 26040001 Generating level 1 area "1_1_1" with seed 3837974753',
    "2026/10/27 14:28:41 26040002 [SCENE] Set Source [(null)]",
    "2026/10/27 14:28:41 26040003 Got Instance Details from login server",
    "2026/10/27 14:28:41 26040004 Client-Safe Instance ID = 3550399669",
    "2026/10/27 14:28:42 26040005 [SCENE] Set Source [(null)]",
    "2026/10/27 14:28:42 26040006 [SCENE] Set Source [The Twilight Strand]",
    "2026/10/27 14:28:43 26040007 : You have entered The Twilight Strand.",
    "2026/10/27 14:28:48 26041000 [SCENE] Set Source [(null)]",
    "2026/10/27 14:28:48 26041001 [SCENE] Set Source [(unknown)]",
    "2026/10/27 14:28:48 26041002 [SCENE] Set Source [(null)]",
    # ── 第 2 次登录（B，另一账号）：同一区 5 秒 ──
    "2026/10/27 14:29:56 26060000 [SCENE] Set Source [(null)]",
    "2026/10/27 14:29:56 26060001 Async connecting to sng.login.pathofexile.com:20481",
    "2026/10/27 14:29:56 26060002 [SCENE] Set Source [(null)]",
    '2026/10/27 14:29:57 26060003 Generating level 1 area "1_1_1" with seed 3540577185',
    "2026/10/27 14:29:57 26060004 Got Instance Details from login server",
    "2026/10/27 14:29:57 26060005 Client-Safe Instance ID = 3748023060",
    "2026/10/27 14:29:57 26060006 [SCENE] Set Source [(null)]",
    "2026/10/27 14:29:57 26060007 [SCENE] Set Source [The Twilight Strand]",
    "2026/10/27 14:30:01 26060008 : You have entered The Twilight Strand.",
    "2026/10/27 14:30:02 26061000 [SCENE] Set Source [(null)]",
    "2026/10/27 14:30:02 26061001 [SCENE] Set Source [(unknown)]",
    "2026/10/27 14:30:02 26061002 [SCENE] Set Source [(null)]",
    # ── 第 3 次登录（A 回来，把 1_1_1 打完 → 1_1_town）──
    '2026/10/27 14:31:36 26090000 Generating level 1 area "1_1_1" with seed 1234567890',
    "2026/10/27 14:31:36 26090001 Got Instance Details from login server",
    "2026/10/27 14:31:36 26090002 Client-Safe Instance ID = 2196069812",
    "2026/10/27 14:31:36 26090003 [SCENE] Set Source [(null)]",
    "2026/10/27 14:31:36 26090004 [SCENE] Set Source [The Twilight Strand]",
    "2026/10/27 14:31:37 26090005 : You have entered The Twilight Strand.",
    "2026/10/27 14:32:41 26092000 : nasdfsdfasdfsa (Duelist) is now level 2",
    '2026/10/27 14:32:49 26093000 Generating level 2 area "1_1_town" with seed 777',
    "2026/10/27 14:32:49 26093001 [SCENE] Set Source [Lioneye's Watch]",
    "2026/10/27 14:32:50 26093002 : You have entered Lioneye's Watch.",
    "2026/10/27 14:32:53 26094000 [SCENE] Set Source [(null)]",
    "2026/10/27 14:32:53 26094001 [SCENE] Set Source [(unknown)]",
]


class LogoutBoundaryTest(unittest.TestCase):
    def _analyze(self, lines: list[str]):
        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        )
        tmp.write(OPEN + "\n")
        tmp.write("\n".join(lines) + "\n")
        tmp.close()
        try:
            return analyze_client_log(Path(tmp.name), game_id="poe1", min_nodes=2)
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    def test_logout_gap_not_charged_to_area(self) -> None:
        sessions = self._analyze(LINES)
        self.assertEqual(len(sessions), 1)
        session = sessions[0]
        splits = session.build_splits()
        self.assertEqual([s.area_id for s in splits], ["1_1_1", "1_1_town"])

        strand = splits[0]
        # 三段实际停留：5s + 5s + 73s = 83s。
        # 修复前是「首次进入 → 进入城镇」的整段 247s（含退出与换账号的空档）。
        self.assertGreaterEqual(strand.segment_seconds, 80)
        self.assertLessEqual(strand.segment_seconds, 86)
        self.assertLess(strand.segment_seconds, 200)

    def test_logout_detected(self) -> None:
        session = self._analyze(LINES)[0]
        # 三次退出：14:28:48（A）、14:30:02（B）、14:32:53（A 打完城镇后退出）
        self.assertEqual(len(session.world_left_at), 3)


if __name__ == "__main__":
    unittest.main()
