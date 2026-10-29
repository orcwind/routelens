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
    # **本节点来自参考路线**（不是自由记录出来的）。
    #
    # 这是「参考路线模式 vs 新建路线模式」的**唯一权威信号**。
    # 为什么不能靠别的：
    #   - 「有没有 reference_route_id」→ 空白路线在 UI 里也是一条 route，有 id
    #   - 「节点总数 > 1」→ 空白路线跑到第 2 个区域就 > 1 了（进哪记哪）
    #   - 「节点有没有 seconds」→ 参考路线里还没跑到/被跳过的节点也没有
    #
    # 参考路线带进来的节点 → True；空白路线的种子起点、自由记录的新节点 → False。
    from_reference: bool = False

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
            "from_reference": self.from_reference,
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
            # 老存档没有这个字段 → 按「有参考路线 + 多节点」推断（见 ActiveRun.from_dict）
            from_reference=bool(data.get("from_reference", False)),
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
    # 权威来源 = ``reference_node_count``（本次运行带进来的**参考**节点数）。
    # 不用「节点总数」也不用「有没有 route_id」判断：
    #   - 空白路线在 UI 里**也是**一条 route（有 route_id），跑起来还会不断
    #     新增节点 → 这两个信号都会误判。
    #   - 只有「这批节点里有多少个是参考来的」才是权威事实。
    #
    # 兼容说明：本字段仍会序列化（老存档靠它自愈），但**写入侧一律走
    # :meth:`create` 工厂，不要直接给 ActiveRun(...) 传参。
    is_reference_mode: bool = False
    # 本次运行带进来的**参考**节点数（空白路线 = 0）。
    # 存档里存这个值，是为了让加载时能自愈 is_reference_mode 被写坏的情况。
    reference_node_count: int = 0

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
            "reference_node_count": self.reference_node_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ActiveRun:
        nodes = [RunNode.from_dict(item) for item in data.get("nodes", [])]
        raw_mode = data.get("is_reference_mode")
        raw_count = data.get("reference_node_count")
        if raw_count is None:
            # 老存档没有这个字段 → 从节点的 from_reference 标记数推断
            reference_count = sum(1 for n in nodes if n.from_reference)
            if reference_count == 0:
                # 更老的存档连 from_reference 都没有 → 退回「有 route_id + 多节点」
                # （空白路线在 UI 里也是 route，这条推断对空白路线可能偏保守，
                #   但空白路线本来就不该有 route_id，除非用户选了自建空白路线 —— 那时
                #   它有参考节点，判成参考模式是对的）
                reference_count = (
                    len(nodes) if (data.get("reference_route_id") and len(nodes) > 1) else 0
                )
            # 补齐节点标记：老存档的节点没有 from_reference → 按推断出的
            # 参考节点数补上前 N 个，保证「标记数 == reference_node_count」
            # （否则 I1 不变量会失败：计数说有 145 个参考节点，标记却是 0）
            if reference_count > 0:
                for node in nodes[:reference_count]:
                    node.from_reference = True
        else:
            reference_count = int(raw_count or 0)
            # 存档里的节点缺 from_reference 标记（老存档）→ 补上
            if reference_count > 0:
                marked = sum(1 for n in nodes if n.from_reference)
                if marked == 0:
                    for node in nodes[:reference_count]:
                        node.from_reference = True
        if raw_mode is None:
            raw_mode = reference_count > 0
        elif not raw_mode and reference_count > 0:
            # 自愈：字段说「新建路线模式」，但存档里明明有参考节点。
            # 真机事故 2026-10-29 14:16：reset_run() 漏传 is_reference_mode
            # → 存档被写成 False，节点却还是 145 个参考节点
            # → 每次进图都被判成「重复进入已去过的地点」→ 永不换节点。
            # 字段与事实矛盾时**以事实为准**。
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
            reference_node_count=reference_count,
        )

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        nodes: list[RunNode],
        reference_route_id: str | None = None,
        reference_route_name: str = "",
        started_at: str = "",
        game_id: str = "",
        is_paused: bool = False,
        is_active: bool = True,
    ) -> ActiveRun:
        """**唯一**的运行状态构造入口。

        为什么必须收口：
            真机事故 2026-10-29 14:16 —— ``reset_run()`` 直接调 ``ActiveRun(...)``
            时漏传 ``is_reference_mode`` / ``game_id``，还丢了每个节点的 ``area_id``，
            导致重置后再也不换节点。同一份「构造运行状态」的知识散在两处，
            改一处忘另一处 = 上线一个静默致命 bug。

        规则（**看节点自己的来源标记**，不看 route_id、不看节点总数）：

            节点里存在 ``from_reference=True`` → 参考路线模式
            全部是自由记录/种子起点 → 新建路线模式（空白路线）

        为什么不能用别的信号：
            - 「有没有 reference_route_id」→ 空白路线在 UI 里**也是**一条 route
              （有 id），实测 ``new_run(None)`` 只是碰巧传 None；用户自建的空白
              路线被选中时走的是「有 reference」的分支 → 有 id。
            - 「节点总数 > 1」→ 空白路线跑到第 2 个区域就 > 1 了（进哪记哪）。
            - 「节点有没有 seconds」→ 参考路线里还没跑到/被跳过的节点也没有。

        唯一权威信号 = 「这批节点里有多少个是参考路线带进来的」。

        所有「新建运行 / 重置运行」都必须走这里，不要直接 ``ActiveRun(...)``。
        """
        reference_count = sum(1 for node in nodes if node.from_reference)
        return cls(
            run_id=run_id,
            reference_route_id=reference_route_id,
            reference_route_name=reference_route_name,
            nodes=nodes,
            started_at=started_at,
            is_paused=is_paused,
            is_active=is_active,
            game_id=game_id,
            # 参考路线模式 = **本次运行带进来的参考节点数 > 0**。
            is_reference_mode=reference_count > 0,
            reference_node_count=reference_count,
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
