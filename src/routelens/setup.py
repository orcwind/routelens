from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

from .client_discovery import CLIENT_HINTS, ClientCandidate, detect_game_from_client, discover_best_client
from .config import is_routelens_setup_complete, load_routelens_config, save_routelens_setup
from .theme import (
    BG,
    BTN_HEIGHT,
    BTN_PRIMARY,
    BTN_PRIMARY_HOVER,
    CORNER_RADIUS,
    FONT_UI,
    GREEN_FG,
    MUTED_FG,
    SURFACE,
    TEXT_FG,
)
from .version import APP_DISPLAY

if TYPE_CHECKING:
    from .gui import RouteLensApp


class SetupWizard:
    """首次启动：自动搜索 Client.txt，识别游戏。"""

    def __init__(self, app: RouteLensApp) -> None:
        self.app = app
        self._result = False
        self._candidate: ClientCandidate | None = None

        self.win = ctk.CTkToplevel(app.root)
        self.win.title(f"{APP_DISPLAY} - 首次设置")
        self.win.geometry("520x360")
        self.win.resizable(False, False)
        self.win.transient(app.root)
        self.win.grab_set()
        self.win.configure(fg_color=BG)
        self.win.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.container = ctk.CTkFrame(self.win, fg_color=BG, corner_radius=0)
        self.container.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)
        self._show_searching()
        self.win.after(200, self._run_search)

    def _clear(self) -> None:
        for child in self.container.winfo_children():
            child.destroy()

    def _label(self, text: str, *, size: int = 13, color: str = TEXT_FG) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            self.container,
            text=text,
            text_color=color,
            font=("Microsoft YaHei", size),
            justify="left",
            anchor="w",
            wraplength=460,
        )

    def _button(self, text: str, command, *, primary: bool = False) -> ctk.CTkButton:
        return ctk.CTkButton(
            self.container,
            text=text,
            command=command,
            height=BTN_HEIGHT,
            corner_radius=CORNER_RADIUS,
            font=FONT_UI,
            fg_color=BTN_PRIMARY if primary else SURFACE,
            hover_color=BTN_PRIMARY_HOVER if primary else "#3a3a3a",
            text_color="#ffffff" if primary else TEXT_FG,
        )

    def _show_searching(self) -> None:
        self._clear()
        self._label(f"欢迎使用 {APP_DISPLAY}", size=18).pack(anchor="w", pady=(0, 12))
        self._label("正在搜索游戏日志 Client.txt …", color=MUTED_FG).pack(anchor="w")

    def _run_search(self) -> None:
        self._candidate = discover_best_client()
        if self._candidate:
            self._show_found(self._candidate)
        else:
            self._show_not_found()

    def _show_found(self, candidate: ClientCandidate) -> None:
        self._clear()
        self._label("发现游戏日志", size=18).pack(anchor="w", pady=(0, 12))
        game_name = "Path of Exile 2" if candidate.game_id == "poe2" else "Path of Exile"
        self._label(f"✓ {game_name}", size=15, color=GREEN_FG).pack(anchor="w", pady=2)
        self._label(candidate.platform_label, color=MUTED_FG).pack(anchor="w", pady=(0, 4))
        self._label(str(candidate.path), color="#aaaaaa").pack(anchor="w", pady=(0, 20))

        row = ctk.CTkFrame(self.container, fg_color=BG, corner_radius=0)
        row.pack(fill=tk.X)
        self._button("使用这个", lambda: self._accept(candidate), primary=True).pack(side=tk.RIGHT)
        self._button("重新选择", self._browse).pack(side=tk.RIGHT, padx=(0, 8))

    def _show_not_found(self) -> None:
        self._clear()
        self._label("没有找到 Client.txt", size=18).pack(anchor="w", pady=(0, 12))
        self._label(CLIENT_HINTS, color=MUTED_FG).pack(anchor="w", pady=(0, 16))
        self._button("浏览选择 Client.txt", self._browse, primary=True).pack(anchor="w")

    def _browse(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.win,
            title="选择 Client.txt",
            filetypes=[("Client log", "Client.txt"), ("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not selected:
            return
        path = Path(selected)
        if not path.is_file():
            messagebox.showerror("路径无效", f"找不到文件：\n{path}", parent=self.win)
            return
        game_id = detect_game_from_client(path)
        candidate = ClientCandidate(path=path.resolve(), platform_label="手动选择", game_id=game_id)
        self._candidate = candidate
        self._show_found(candidate)

    def _accept(self, candidate: ClientCandidate) -> None:
        save_routelens_setup(str(candidate.path), candidate.game_id)
        self.app.config = load_routelens_config()
        self.app.engine.config = self.app.config
        self.app.engine.reload_game_profile()
        self._result = True
        self.win.destroy()

    def _on_cancel(self) -> None:
        if messagebox.askyesno("退出", "未完成设置将无法使用。\n确定退出？", parent=self.win):
            self._result = False
            self.win.destroy()

    def run(self) -> bool:
        self.win.wait_window()
        return self._result


def ensure_setup(app: RouteLensApp, on_analyzed: Callable[[dict], None] | None = None) -> bool:
    if is_routelens_setup_complete(app.config):
        return True
    if not SetupWizard(app).run():
        return False
    try:
        summary = app.engine.import_from_client_txt()
        if on_analyzed:
            on_analyzed(summary)
    except (FileNotFoundError, OSError):
        pass
    return True
