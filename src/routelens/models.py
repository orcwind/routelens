from __future__ import annotations

from dataclasses import dataclass, field


def format_duration(seconds: float) -> str:
    total = int(max(0, seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_delta(actual: float, reference: float | None) -> str:
    if reference is None:
        return ""
    diff = actual - reference
    sign = "+" if diff >= 0 else "-"
    return f"{sign}{format_duration(abs(diff))}"


@dataclass
class RouteNode:
    name: str
    seconds: float | None = None
    area_id: str = ""
    # 试炼进门节点：每次试炼都要记（area id 相同也不能去重）
    is_trial_entry: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "seconds": self.seconds,
            "area_id": self.area_id,
            "is_trial_entry": self.is_trial_entry,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RouteNode:
        raw = data.get("seconds")
        return cls(
            name=str(data.get("name", "")),
            seconds=float(raw) if raw is not None else None,
            area_id=str(data.get("area_id", "") or ""),
            is_trial_entry=bool(data.get("is_trial_entry", False)),
        )


@dataclass
class ReferenceRoute:
    route_id: str
    name: str
    nodes: list[RouteNode] = field(default_factory=list)
    created_at: str = ""
    run_count: int = 0
    best_seconds: float | None = None
    source: str = ""  # client_txt | manual
    character: str = ""
    game_id: str = ""  # poe1 | poe2
    is_favorite: bool = False

    def to_dict(self) -> dict:
        return {
            "route_id": self.route_id,
            "name": self.name,
            "nodes": [node.to_dict() for node in self.nodes],
            "created_at": self.created_at,
            "run_count": self.run_count,
            "best_seconds": self.best_seconds,
            "source": self.source,
            "character": self.character,
            "game_id": self.game_id,
            "is_favorite": self.is_favorite,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ReferenceRoute:
        return cls(
            route_id=str(data.get("route_id", "")),
            name=str(data.get("name", "")),
            nodes=[RouteNode.from_dict(item) for item in data.get("nodes", [])],
            created_at=str(data.get("created_at", "")),
            run_count=int(data.get("run_count", 0)),
            best_seconds=(
                float(data["best_seconds"]) if data.get("best_seconds") is not None else None
            ),
            source=str(data.get("source", "")),
            character=str(data.get("character", "")),
            game_id=str(data.get("game_id", "")),
            is_favorite=bool(data.get("is_favorite", False)),
        )


@dataclass
class RunNode:
    """本次运行里的一个区域节点。

    **不变量（唯一事实源）**：

    ==========================  =========================================
    ``seconds is not None``     本次运行在这个区域**待过**，时间在这里
    ``skipped is True``         本次运行**没去过**这个区域
    ==========================  =========================================

    两者**互斥**：不允许出现「有 87 秒用时 + skipped」这种自相矛盾的状态。

    真机事故 2026-10-28：跳段把玩家真跑过的 24 个节点标成 ``skipped=True``
    却保留了 ``seconds`` → 统计时按 ``skipped`` 排除 → 28.3 分钟凭空消失
    （总时间 1:06:37，幕行只显示 38 分钟）。

    写入侧必须用 :meth:`mark_visited` / :meth:`mark_skipped`，
    不要直接给 ``seconds`` / ``skipped`` 赋值。
    """

    name: str
    seconds: float | None = None
    completed: bool = False
    skipped: bool = False
    area_id: str = ""
    # 试炼进门节点：每次试炼都要记（area id 相同也不能去重）
    is_trial_entry: bool = False

    @property
    def visited(self) -> bool:
        """本次运行是否真的在这个区域待过（时间存在即为待过）。"""
        return self.seconds is not None

    def mark_visited(self, seconds: float) -> None:
        """记为「本次到过，用时 seconds 秒」。"""
        self.seconds = max(0.0, float(seconds))
        self.completed = True
        self.skipped = False

    def mark_skipped(self) -> None:
        """记为「本次没去过」（跳过 / 未到达）。不得带用时。"""
        self.completed = True
        self.skipped = True
        self.seconds = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "seconds": self.seconds,
            "completed": self.completed,
            "skipped": self.skipped,
            "area_id": self.area_id,
            "is_trial_entry": self.is_trial_entry,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RunNode":
        raw = data.get("seconds")
        seconds = float(raw) if raw is not None else None
        skipped = bool(data.get("skipped", False))
        # 迁移：违反不变量（**有实际用时**却标成跳过）的老存档 → 按「待过」处理。
        # 真机事故 2026-10-28 的 24 个节点就是这种状态（28.3 分钟蒸发）。
        # 判据用 ``> 0``：0 秒没有实际意义，历史数据里通常是「跳过」的占位。
        if skipped and seconds is not None and seconds > 0:
            skipped = False
        return cls(
            name=str(data.get("name", "")),
            seconds=seconds,
            completed=bool(data.get("completed", False)) or seconds is not None,
            skipped=skipped,
            area_id=str(data.get("area_id", "") or ""),
            is_trial_entry=bool(data.get("is_trial_entry", False)),
        )


@dataclass
class ActiveRun:
    run_id: str
    reference_route_id: str | None
    reference_route_name: str
    nodes: list[RunNode] = field(default_factory=list)
    current_index: int = 0
    current_area: str = ""
    elapsed_seconds: float = 0.0
    started_at: str = ""
    is_active: bool = True
    is_paused: bool = False
    # 剧情已结束（PoE1 Act 10 奇塔弗）：出现后计时自动暂停
    campaign_over: bool = False
    # 本次运行所属游戏（poe1 / poe2）。
    # 必须跟随「所选路线 / 新建时点的那颗按钮」，不能用全局 config.game 兜底：
    # 设置里默认 poe2，跑 PoE1 路线时会把 10 幕判成 4 幕、种子起点也种错。
    game_id: str = ""
    # **参考路线模式**（用户 2026-10-29 定稿规则）：
    #   True  → 节点集合恒等于参考路线；不在「当前节点之后」的参考节点出现时，
    #            时间记给当前节点，不新增节点、不存在「路线分叉」。
    #   False → 新建路线模式：进哪记什么（但重复/藏身处仍按规则处理）。
    #
    # 判据是「**本次运行有没有参考节点**」，不是「有没有 reference_route_id」：
    # 空白路线也会带一个 route_id（用来标记来源），但它没有参考节点。
    is_reference_mode: bool = False

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "reference_route_id": self.reference_route_id,
            "reference_route_name": self.reference_route_name,
            "nodes": [node.to_dict() for node in self.nodes],
            "current_index": self.current_index,
            "current_area": self.current_area,
            "elapsed_seconds": self.elapsed_seconds,
            "started_at": self.started_at,
            "is_active": self.is_active,
            "is_paused": self.is_paused,
            "campaign_over": self.campaign_over,
            "game_id": self.game_id,
            "is_reference_mode": self.is_reference_mode,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ActiveRun:
        nodes = [RunNode.from_dict(item) for item in data.get("nodes", [])]
        raw_mode = data.get("is_reference_mode")
        if raw_mode is None:
            # 老存档没有这个字段 → 按「有没有参考节点」推断
            # （空白路线有 route_id 但只有 1 个种子节点 → 不是参考模式）
            raw_mode = bool(data.get("reference_route_id")) and len(nodes) > 1
        elif not raw_mode and data.get("reference_route_id") and len(nodes) > 1:
            # 自愈：字段说「新建路线模式」，但存档里明明有多个参考节点。
            # 真机事故 2026-10-29 14:16：reset_run() 漏传 is_reference_mode
            # → 存档被写成 False，节点却还是 145 个参考节点
            # → 每次进图都被判成「重复进入已去过的地点」→ 永不换节点。
            # 字段与事实矛盾时**以事实为准**：多节点 + 有 route_id = 参考路线模式。
            raw_mode = True
        return cls(
            run_id=str(data.get("run_id", "")),
            reference_route_id=data.get("reference_route_id"),
            reference_route_name=str(data.get("reference_route_name", "")),
            nodes=nodes,
            current_index=int(data.get("current_index", 0)),
            current_area=str(data.get("current_area", "")),
            elapsed_seconds=float(data.get("elapsed_seconds", 0.0)),
            started_at=str(data.get("started_at", "")),
            is_active=bool(data.get("is_active", True)),
            is_paused=bool(data.get("is_paused", False)),
            campaign_over=bool(data.get("campaign_over", False)),
            game_id=str(data.get("game_id", "") or ""),
            is_reference_mode=bool(raw_mode),
        )

    @property
    def next_node_name(self) -> str:
        if self.current_index < len(self.nodes):
            return self.nodes[self.current_index].name
        return ""


@dataclass
class RunResult:
    run_id: str
    route_id: str | None
    route_name: str
    total_seconds: float
    finished_at: str
    nodes: list[RunNode] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "route_id": self.route_id,
            "route_name": self.route_name,
            "total_seconds": self.total_seconds,
            "finished_at": self.finished_at,
            "nodes": [node.to_dict() for node in self.nodes],
        }

    @classmethod
    def from_dict(cls, data: dict) -> RunResult:
        return cls(
            run_id=str(data.get("run_id", "")),
            route_id=data.get("route_id"),
            route_name=str(data.get("route_name", "")),
            total_seconds=float(data.get("total_seconds", 0.0)),
            finished_at=str(data.get("finished_at", "")),
            nodes=[RunNode.from_dict(item) for item in data.get("nodes", [])],
        )
