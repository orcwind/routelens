"""按幕（Act）聚合开荒计时。

节点的归属由 :mod:`routelens.act_map` 依据 area id 判定（唯一权威），
因此**不同玩家的节点顺序不同、支线不同都不影响分幕**。

聚合规则：

- 节点的 ``segment_seconds`` 是「在该区域停留的时长」（离开时才结算）。
- **同一幕的多次出现合并成一行**（如玩家重刷 Act 3 刷任务），
  幕用时 = 该幕所有节点的 segment 之和。
- 行序 = **幕号升序**（Act 1 … Act 10），剧情结束行在最后。
  跨多次登录合并的路线因此仍然呈现为「10 幕」的骨架。
- 累计时间 = 按幕序累加（Act 1 累计 = Act 1 用时；Act 2 累计 = Act 1 + Act 2）。
- 支线节点（迷宫 / 精华 / 禁區）不推进幕号，但**时间仍要计入**：
  归属到「当前所在幕」，避免漏计。
- 剧情结束节点单独成组（``is_endgame``），不计入任何幕。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .act_map import act_count, detect_act


@dataclass
class ActSplit:
    """一幕的计时汇总。"""

    act: int | None
    label: str
    segment_seconds: float = 0.0
    cumulative_seconds: float = 0.0
    node_count: int = 0
    first_area: str = ""
    last_area: str = ""
    is_endgame: bool = False

    def to_dict(self) -> dict:
        return {
            "act": self.act,
            "label": self.label,
            "segment_seconds": self.segment_seconds,
            "cumulative_seconds": self.cumulative_seconds,
            "node_count": self.node_count,
            "first_area": self.first_area,
            "last_area": self.last_area,
            "is_endgame": self.is_endgame,
        }


@dataclass
class ActTiming:
    """整条路线的分幕计时。"""

    game_id: str
    acts: list[ActSplit] = field(default_factory=list)
    total_seconds: float = 0.0
    node_count: int = 0
    current_act: int | None = None

    def to_dict(self) -> dict:
        return {
            "game_id": self.game_id,
            "acts": [act.to_dict() for act in self.acts],
            "total_seconds": self.total_seconds,
            "node_count": self.node_count,
            "current_act": self.current_act,
        }


def _split_area_id(split: dict) -> str:
    return str(split.get("area_id") or "").strip()


def _split_area(split: dict) -> str:
    return str(
        split.get("area")
        or split.get("area_en")
        or split.get("display")
        or ""
    )


def build_act_timing(splits: list[dict], game_id: str) -> ActTiming:
    """把节点列表聚合成幕计时。

    ``splits`` 需带 ``area_id``；缺失时该节点退化为「不归属任何幕」，
    但其时间仍会累计到总时间。
    """
    timing = ActTiming(game_id=game_id, node_count=len(splits))
    if not splits:
        return timing

    by_act: dict[int, ActSplit] = {}
    endgame: ActSplit | None = None
    current_act: int | None = None
    total = 0.0

    for split in splits:
        seconds = float(split.get("segment_seconds", 0) or 0)
        area_id = _split_area_id(split)
        area = _split_area(split)
        info = detect_act(area_id, game_id)

        if info.campaign_over:
            # 剧情结束：单独一组，不计入任何幕
            if endgame is None:
                endgame = ActSplit(
                    act=None,
                    label=info.label,
                    is_endgame=True,
                    first_area=area,
                )
            endgame.segment_seconds += seconds
            endgame.node_count += 1
            endgame.last_area = area
            total += seconds
            continue

        target_act = info.act
        if target_act is None:
            # 支线：归属到「当前所在幕」；还没有任何幕时归属 None（不显示）。
            target_act = current_act
        else:
            current_act = target_act

        if target_act is None:
            total += seconds
            continue

        act_split = by_act.get(target_act)
        if act_split is None:
            act_split = ActSplit(
                act=target_act,
                label=f"Act {target_act}",
                first_area=area,
            )
            by_act[target_act] = act_split
        act_split.segment_seconds += seconds
        act_split.node_count += 1
        act_split.last_area = area
        total += seconds

    # 幕序 = 幕号升序；剧情结束在最后
    for act_number in sorted(by_act):
        timing.acts.append(by_act[act_number])
    if endgame is not None:
        timing.acts.append(endgame)

    # 累计时间按幕序累加
    cumulative = 0.0
    for act_split in timing.acts:
        cumulative += act_split.segment_seconds
        act_split.cumulative_seconds = cumulative

    timing.total_seconds = total
    timing.current_act = current_act
    return timing


def expected_act_labels(game_id: str, locale: str = "zh_tw") -> list[str]:
    """该游戏的全部幕标签（用于 UI 显示「Act 1 … Act 10」骨架）。"""
    total = act_count(game_id)
    if locale == "en":
        return [f"Act {index}" for index in range(1, total + 1)]
    return [f"第 {index} 幕" for index in range(1, total + 1)]
