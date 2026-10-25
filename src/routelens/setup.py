from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

from .client_discovery import ClientCandidate, detect_game_from_client
from .config import (
    is_routelens_setup_complete,
    load_routelens_config,
    save_routelens_setup,
    save_ui_lang,
)
from .theme import (
    BG,
    BTN_HEIGHT,
    BTN_PRIMARY,
    BTN_PRIMARY_HOVER,
    CORNER_RADIUS,
    FONT_UI,
    FONT_UI_SM,
    GREEN_FG,
    MUTED_FG,
    SURFACE,
    TEXT_FG,
)
from .tray_icon import apply_window_icon
from .ui_i18n import UI_LANG_EN, UI_LANG_ZH, t
from .version import APP_DISPLAY, APP_VERSION_LINE

if TYPE_CHECKING:
    from .gui import RouteLensApp


class SetupWizard:
    """首次启动：引导选择 Client.txt；页内可切换中 / 英界面。"""

    def __init__(self, app: RouteLensApp) -> None:
        self.app = app
        self._result = False
        self._candidate: ClientCandidate | None = None
        self._icon_photo = None
        self._step = "pick"

        self.win = ctk.CTkToplevel(app.root)
        self.win.geometry("520x360")
        self.win.resizable(False, False)
        self.win.transient(app.root)
        self.win.grab_set()
        self.win.configure(fg_color=BG)
        self.win.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._icon_photo = apply_window_icon(self.win)
        self.win.after(50, lambda: apply_window_icon(self.win))

        self.container = ctk.CTkFrame(self.win, fg_color=BG, corner_radius=0)
        self.container.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)
        self._refresh()

    def _t(self, key: str) -> str:
        return t(self.app.ui_lang, key)

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

    def _button(
        self,
        text: str,
        command,
        *,
        primary: bool = False,
        parent: tk.Misc | None = None,
    ) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent if parent is not None else self.container,
            text=text,
            command=command,
            height=BTN_HEIGHT,
            corner_radius=CORNER_RADIUS,
            font=FONT_UI,
            fg_color=BTN_PRIMARY if primary else SURFACE,
            hover_color=BTN_PRIMARY_HOVER if primary else "#3a3a3a",
            text_color="#ffffff" if primary else TEXT_FG,
        )

    def _toggle_ui_lang(self) -> None:
        self.app.ui_lang = UI_LANG_EN if self.app.ui_lang == UI_LANG_ZH else UI_LANG_ZH
        save_ui_lang(self.app.ui_lang)
        self._refresh()

    def _pack_lang_row(self) -> None:
        """顶部中英切换：英文用户打开此页就能立刻看懂。"""
        row = ctk.CTkFrame(self.container, fg_color=BG, corner_radius=0)
        row.pack(fill=tk.X, pady=(0, 12))
        ctk.CTkLabel(
            row,
            text="语言 / Language",
            text_color=MUTED_FG,
            font=FONT_UI_SM,
        ).pack(side=tk.LEFT)
        # 按钮文案：当前为中文时显示 EN；当前为英文时显示 中文
        self._button(self._t("lang_btn"), self._toggle_ui_lang, parent=row).pack(side=tk.RIGHT)

    def _refresh(self) -> None:
        self.win.title(f"{APP_VERSION_LINE} - {self._t('setup_title')}")
        if self._step == "found" and self._candidate is not None:
            self._show_found(self._candidate)
        else:
            self._show_pick()

    def _show_pick(self) -> None:
        self._step = "pick"
        self._clear()
        self._pack_lang_row()
        self._label(self._t("setup_welcome").format(app=APP_DISPLAY), size=18).pack(
            anchor="w", pady=(0, 12)
        )
        self._label(self._t("setup_hint"), color=MUTED_FG).pack(anchor="w", pady=(0, 16))
        self._button(self._t("setup_browse"), self._browse, primary=True).pack(anchor="w")

    def _show_found(self, candidate: ClientCandidate) -> None:
        self._step = "found"
        self._candidate = candidate
        self._clear()
        self._pack_lang_row()
        self._label(self._t("setup_found_title"), size=18).pack(anchor="w", pady=(0, 12))
        game_name = "Path of Exile 2" if candidate.game_id == "poe2" else "Path of Exile"
        self._label(f"✓ {game_name}", size=15, color=GREEN_FG).pack(anchor="w", pady=2)
        platform = candidate.platform_label
        if platform in {"手动选择", "Manual select"}:
            platform = self._t("setup_manual")
        self._label(platform, color=MUTED_FG).pack(anchor="w", pady=(0, 4))
        self._label(str(candidate.path), color="#aaaaaa").pack(anchor="w", pady=(0, 20))

        row = ctk.CTkFrame(self.container, fg_color=BG, corner_radius=0)
        row.pack(fill=tk.X, pady=(12, 0))
        self._button(
            self._t("setup_use"),
            lambda: self._accept(candidate),
            primary=True,
            parent=row,
        ).pack(side=tk.RIGHT)
        self._button(self._t("setup_reselect"), self._browse, parent=row).pack(
            side=tk.RIGHT, padx=(0, 8)
        )

    def _browse(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.win,
            title=self._t("setup_pick_title"),
            filetypes=[("Client log", "Client.txt"), ("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not selected:
            return
        path = Path(selected)
        if not path.is_file():
            messagebox.showerror(
                self._t("setup_bad_path"),
                self._t("setup_bad_path_detail").format(path=path),
                parent=self.win,
            )
            return
        game_id = detect_game_from_client(path)
        candidate = ClientCandidate(
            path=path.resolve(),
            platform_label=self._t("setup_manual"),
            game_id=game_id,
        )
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
        if messagebox.askyesno(
            self._t("setup_exit_title"),
            self._t("setup_exit_confirm"),
            parent=self.win,
        ):
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
