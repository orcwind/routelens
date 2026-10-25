from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


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
    name: str
    seconds: float | None = None
    completed: bool = False
    skipped: bool = False
    area_id: str = ""
    # 试炼进门节点：每次试炼都要记（area id 相同也不能去重）
    is_trial_entry: bool = False

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
    def from_dict(cls, data: dict) -> RunNode:
        raw = data.get("seconds")
        return cls(
            name=str(data.get("name", "")),
            seconds=float(raw) if raw is not None else None,
            completed=bool(data.get("completed", False)),
            skipped=bool(data.get("skipped", False)),
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
        }

    @classmethod
    def from_dict(cls, data: dict) -> ActiveRun:
        return cls(
            run_id=str(data.get("run_id", "")),
            reference_route_id=data.get("reference_route_id"),
            reference_route_name=str(data.get("reference_route_name", "")),
            nodes=[RunNode.from_dict(item) for item in data.get("nodes", [])],
            current_index=int(data.get("current_index", 0)),
            current_area=str(data.get("current_area", "")),
            elapsed_seconds=float(data.get("elapsed_seconds", 0.0)),
            started_at=str(data.get("started_at", "")),
            is_active=bool(data.get("is_active", True)),
            is_paused=bool(data.get("is_paused", False)),
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
