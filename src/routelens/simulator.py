from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING

import customtkinter as ctk

from companion.client_txt_simulator import TOMB_BRANCH_OUT_OF_ORDER
from companion import test_log

from .area_filter import filter_hideout_nodes
from .theme import BG, BORDER, CORNER_RADIUS, FONT_UI_SM, SURFACE, TEXT_FG

if TYPE_CHECKING:
    from .engine import RunEngine
    from .gui import RouteLensApp

LIST_BG = "#1a1a1a"
FONT = ("Consolas", 12)


class SimulatorPanel(ctk.CTkFrame):
    """往 Client.txt 写入进图行，供测试 autosplit。"""

    def __init__(self, parent: tk.Misc, app: RouteLensApp) -> None:
        super().__init__(parent, fg_color=BG, corner_radius=0)
        self.app = app
        self._build_ui()

    @property
    def engine(self) -> RunEngine:
        return self.app.engine

    def _build_ui(self) -> None:
        header = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        header.pack(fill=tk.X, pady=(0, 8))
        ctk.CTkLabel(
            header,
            text="点区域右侧「进图」写入 Client.txt",
            text_color=TEXT_FG,
            font=FONT_UI_SM,
        ).pack(side=tk.LEFT)
        ctk.CTkButton(
            header,
            text="陵墓乱序",
            command=self._simulate_tomb_branch,
            height=32,
            corner_radius=CORNER_RADIUS,
            fg_color=SURFACE,
            hover_color="#3a3a3a",
            font=FONT_UI_SM,
        ).pack(side=tk.RIGHT)

        container = ctk.CTkFrame(
            self, fg_color=LIST_BG, corner_radius=CORNER_RADIUS, border_width=1, border_color=BORDER
        )
        container.pack(fill=tk.BOTH, expand=True)

        self._canvas = tk.Canvas(container, bg=LIST_BG, highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4), pady=4)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)

        self._list_inner = tk.Frame(self._canvas, bg=LIST_BG)
        self._canvas_window = self._canvas.create_window((0, 0), window=self._list_inner, anchor="nw")
        self._list_inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<Enter>", self._bind_mousewheel)
        self._canvas.bind("<Leave>", self._unbind_mousewheel)

    def _bind_mousewheel(self, _event: object = None) -> None:
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event: object = None) -> None:
        self._canvas.unbind_all("<MouseWheel>")

    def _on_inner_configure(self, _event: object = None) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self._canvas.itemconfigure(self._canvas_window, width=event.width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        self._canvas.yview_scroll(int(-event.delta / 120), "units")

    def refresh(self) -> None:
        """仅打开窗口时加载一次，不自动改滚动位置。"""
        for child in self._list_inner.winfo_children():
            child.destroy()

        names: list[str] = []
        run = self.engine.active_run
        if run and run.nodes:
            names = [node.name for node in filter_hideout_nodes(run.nodes)]
        else:
            routes = self.engine.store.list_routes()
            if routes:
                names = [node.name for node in filter_hideout_nodes(routes[0].nodes)]

        for name in names:
            row = tk.Frame(self._list_inner, bg=LIST_BG)
            row.pack(fill=tk.X, pady=2)

            tk.Label(
                row,
                text=name,
                bg=LIST_BG,
                fg=TEXT_FG,
                font=("Consolas", 11),
                anchor="w",
            ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 8))

            ctk.CTkButton(
                row,
                text="进图",
                font=FONT,
                height=28,
                width=56,
                corner_radius=6,
                fg_color=SURFACE,
                hover_color="#3a3a3a",
                command=lambda area=name: self._simulate(area),
            ).pack(side=tk.RIGHT, padx=(0, 6))

    def _simulate(self, area: str) -> None:
        try:
            self.engine.simulate_area(area, write_client=True)
        except (FileNotFoundError, OSError) as exc:
            messagebox.showerror("模拟失败", str(exc), parent=self.app.root)
            test_log.write("SIM", "模拟失败", area=area, error=str(exc))

    def _simulate_tomb_branch(self) -> None:
        client_path = self.engine.client_path
        if client_path is None or not client_path.is_file():
            messagebox.showerror("模拟失败", "未找到 Client.txt", parent=self.app.root)
            return
        try:
            from companion.client_txt_simulator import append_scene_sequence

            test_log.write("SIM", "陵墓乱序分支", areas=list(TOMB_BRANCH_OUT_OF_ORDER))
            append_scene_sequence(client_path, list(TOMB_BRANCH_OUT_OF_ORDER), step_seconds=0.8)
            for area in TOMB_BRANCH_OUT_OF_ORDER:
                self.engine._last_area = ""
                self.engine._inject_area(area)
            if self.engine.log_watcher:
                self.engine.log_watcher.seek_to_end()
        except OSError as exc:
            messagebox.showerror("模拟失败", str(exc), parent=self.app.root)
            test_log.write("SIM", "陵墓乱序失败", error=str(exc))
