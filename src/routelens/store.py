from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from .models import ActiveRun, ReferenceRoute, RouteNode, RunNode, RunResult
from .game_detect import detect_game_from_area_names


class RouteLensStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.routes_dir = data_dir / "routes"
        self.results_dir = data_dir / "results"
        self.active_run_path = data_dir / "active_run.json"
        self.active_run_backup_path = data_dir / "active_run_before_reset.json"
        self.routes_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def list_routes(self) -> list[ReferenceRoute]:
        routes: list[ReferenceRoute] = []
        for path in sorted(self.routes_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                routes.append(ReferenceRoute.from_dict(data))
            except (json.JSONDecodeError, OSError):
                continue
        routes.sort(key=lambda item: item.name.lower())
        client_routes = [route for route in routes if route.source == "client_txt"]
        other_routes = [route for route in routes if route.source != "client_txt"]
        client_routes.sort(key=lambda item: item.created_at or "", reverse=True)
        client_routes.sort(key=lambda item: 0 if item.is_favorite else 1)
        other_routes.sort(key=lambda item: (0 if item.is_favorite else 1, item.name.lower()))
        return client_routes + other_routes

    def delete_routes(self, route_ids: list[str]) -> None:
        for route_id in route_ids:
            path = self.routes_dir / f"{route_id}.json"
            if path.is_file():
                path.unlink()

    def rename_route(self, route_id: str, name: str) -> None:
        route = self.get_route(route_id)
        if route is None:
            return
        route.name = name.strip()
        self.save_route(route)

    def set_favorite(self, route_id: str, favorite: bool) -> None:
        route = self.get_route(route_id)
        if route is None:
            return
        route.is_favorite = favorite
        self.save_route(route)

    def get_route(self, route_id: str) -> ReferenceRoute | None:
        path = self.routes_dir / f"{route_id}.json"
        if not path.is_file():
            return None
        try:
            return ReferenceRoute.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            return None

    def save_route(self, route: ReferenceRoute) -> None:
        path = self.routes_dir / f"{route.route_id}.json"
        path.write_text(json.dumps(route.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def create_route_from_run(self, name: str, nodes: list[RunNode]) -> ReferenceRoute:
        now = datetime.now().isoformat(timespec="seconds")
        route = ReferenceRoute(
            route_id=str(uuid.uuid4()),
            name=name,
            nodes=[
                RouteNode(name=node.name, seconds=node.seconds, area_id=node.area_id)
                for node in nodes
                if node.completed and node.name
            ],
            created_at=now,
            run_count=0,
            best_seconds=None,
            source="manual",
        )
        self.save_route(route)
        return route

    def replace_client_routes(self, routes: list[ReferenceRoute], *, game_id: str | None = None) -> int:
        """仅替换指定游戏的 Client.txt 导入路线；另一游戏与手动路线一律保留。"""
        target_game = str(game_id or "").strip().lower() or None
        for path in list(self.routes_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if data.get("source") != "client_txt":
                continue
            existing_game = str(data.get("game_id") or "").strip().lower()
            # 必须带 game_id 才替换；未知归属的旧路线不删，避免误清另一游戏
            if target_game is None:
                continue
            if existing_game != target_game:
                continue
            path.unlink(missing_ok=True)
        for route in routes:
            if target_game and not str(route.game_id or "").strip():
                route.game_id = target_game
            self.save_route(route)
        return len(routes)

    def repair_client_route_games(self) -> list[tuple[str, str, str]]:
        """按节点区域名修正历史误标的游戏归属（幂等）。

        v0.1.1 曾把导入目标游戏强制套到所有路线，PoE1 日志从 PoE2 入口
        导入后会被整批标成 poe2。这里按区域名重判，证据不足不动。
        返回 [(路线名, 原归属, 新归属)]。
        """
        fixed: list[tuple[str, str, str]] = []
        backup_dir = self.routes_dir / "_gamefix_backup"
        for path in sorted(self.routes_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if data.get("source") != "client_txt":
                continue
            current = str(data.get("game_id") or "").strip().lower()
            if current not in {"poe1", "poe2"}:
                continue
            names = [
                str(node.get("name") or "")
                for node in (data.get("nodes") or [])
                if isinstance(node, dict)
            ]
            guess = detect_game_from_area_names(names)
            if guess is None or guess == current:
                continue
            try:
                backup_dir.mkdir(parents=True, exist_ok=True)
                (backup_dir / path.name).write_text(
                    path.read_text(encoding="utf-8"), encoding="utf-8"
                )
            except OSError:
                continue
            data["game_id"] = guess
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            fixed.append((str(data.get("name") or path.stem), current, guess))
        return fixed

    def upsert_client_routes(self, routes: list[ReferenceRoute]) -> int:
        existing = {route.route_id: route for route in self.list_routes()}
        by_character = {
            route.character: route
            for route in existing.values()
            if route.source == "client_txt" and route.character
        }

        count = 0
        for route in routes:
            match = by_character.get(route.character)
            if match:
                route.route_id = match.route_id
                route.run_count = match.run_count
                if match.best_seconds is not None:
                    if route.best_seconds is None or match.best_seconds < route.best_seconds:
                        route.best_seconds = match.best_seconds
            self.save_route(route)
            count += 1
        return count

    def update_route_stats(self, route_id: str, total_seconds: float) -> None:
        route = self.get_route(route_id)
        if route is None:
            return
        route.run_count += 1
        if route.best_seconds is None or total_seconds < route.best_seconds:
            route.best_seconds = total_seconds
        self.save_route(route)

    def load_active_run(self) -> ActiveRun | None:
        if not self.active_run_path.is_file():
            return None
        try:
            data = json.loads(self.active_run_path.read_text(encoding="utf-8"))
            run = ActiveRun.from_dict(data)
        except json.JSONDecodeError:
            return None
        if not run.is_active:
            return None
        return run

    def save_active_run(self, run: ActiveRun) -> None:
        self.active_run_path.write_text(
            json.dumps(run.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def clear_active_run(self) -> None:
        if self.active_run_path.is_file():
            self.active_run_path.unlink()

    def save_reset_backup(self, run: ActiveRun) -> None:
        """重置前备份，供误触后恢复。"""
        self.active_run_backup_path.write_text(
            json.dumps(run.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_reset_backup(self) -> ActiveRun | None:
        if not self.active_run_backup_path.is_file():
            return None
        try:
            data = json.loads(self.active_run_backup_path.read_text(encoding="utf-8"))
            return ActiveRun.from_dict(data)
        except (json.JSONDecodeError, TypeError, KeyError, ValueError):
            return None

    def clear_reset_backup(self) -> None:
        if self.active_run_backup_path.is_file():
            self.active_run_backup_path.unlink()

    def has_reset_backup(self) -> bool:
        return self.active_run_backup_path.is_file()

    def save_result(self, result: RunResult) -> None:
        folder_key = result.route_id or "free_run"
        folder = self.results_dir / folder_key
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{result.run_id}.json"
        path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def list_results(self, route_id: str | None = None) -> list[RunResult]:
        results: list[RunResult] = []
        if route_id:
            folders = [self.results_dir / route_id]
        else:
            folders = [path for path in self.results_dir.iterdir() if path.is_dir()]

        for folder in folders:
            if not folder.is_dir():
                continue
            for path in folder.glob("*.json"):
                try:
                    results.append(RunResult.from_dict(json.loads(path.read_text(encoding="utf-8"))))
                except (json.JSONDecodeError, OSError):
                    continue
        results.sort(key=lambda item: item.finished_at, reverse=True)
        return results
