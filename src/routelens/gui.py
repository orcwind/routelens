from __future__ import annotations

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
import pystray

from . import test_log
from .config import (
    load_client_path_for_game,
    load_routelens_config,
    load_ui_lang,
    save_routelens_setup,
    save_ui_lang,
)
from .engine import RunEngine
from .models import ActiveRun, ReferenceRoute, RunResult, format_delta, format_duration
from .setup import ensure_setup
from .simulator import SimulatorPanel
from .theme import (
    BG,
    BORDER,
    BTN_ACTIVE,
    BTN_HEIGHT,
    BTN_PRIMARY,
    BTN_PRIMARY_DISABLED,
    BTN_PRIMARY_HOVER,
    CORNER_RADIUS,
    FONT_HEADING,
    FONT_HINT,
    FONT_TIMER,
    FONT_TITLE,
    FONT_UI,
    FONT_UI_SM,
    GOLD_FG,
    GREEN_FG,
    MUTED_FG,
    PANEL_BG,
    SELECT_BG,
    SKIP_FG,
    SURFACE,
    TEXT_FG,
    WINDOW_EDGE,
    apply_theme,
)
from .split_panel import SplitPanel
from .tray_icon import ensure_window_ico, load_tray_image, load_window_icon_image
from .ui_i18n import UI_LANG_EN, UI_LANG_ZH, t
from .version import APP_DISPLAY, APP_NAME

LIST_BG = SURFACE
NODES_PER_PAGE = 50
GAME_GROUP_LABELS = {
    "poe1": "Path of Exile",
    "poe2": "Path of Exile 2",
    "other": "其他",
}

# Windows 小键盘虚拟键码（VK_NUMPAD0 = 0x60 = 96）
_NUMPAD_KEYCODE_TO_DIGIT: dict[int, str] = {
    96: "0",
    97: "1",
    98: "2",
    99: "3",
    100: "4",
    101: "5",
    102: "6",
    103: "7",
    104: "8",
    105: "9",
}


class RouteLensApp:
    def __init__(self) -> None:
        apply_theme()
        self.config = load_routelens_config()
        test_log.init_log(self.config.resolved_data_dir)
        self.engine = RunEngine(self.config)
        self.engine.set_state_callback(self._on_run_state)

        self.root = ctk.CTk()
        self.ui_lang = load_ui_lang()
        self.root.title(APP_DISPLAY)
        self.root.geometry("920x520")
        self.root.minsize(640, 420)
        self.root.configure(fg_color=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.container = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0)
        self.container.pack(fill=tk.BOTH, expand=True)

        self._main_frame: ctk.CTkFrame | None = None
        self._run_frame: ctk.CTkFrame | None = None
        self._run_chrome: ctk.CTkFrame | None = None
        self._selected_route_id: str | None = None
        self._route_tree: ttk.Treeview | None = None
        self._route_tree_items: dict[str, str] = {}
        self._route_tree_groups: dict[str, str] = {}
        self._detail_title: tk.StringVar | None = None
        self._detail_meta: tk.StringVar | None = None
        self._detail_continue: tk.StringVar | None = None
        self._detail_hint: tk.StringVar | None = None
        self._continue_btn: ctk.CTkButton | None = None
        self._sim_panel: SimulatorPanel | None = None
        self._sim_popup: tk.Toplevel | None = None

        self.elapsed_var = tk.StringVar(value="00:00.00")
        self.current_var = tk.StringVar(value=self._t("press_0"))
        self.route_name_var = tk.StringVar(value="")

        self._split_panel: SplitPanel | None = None
        self._split_page = 0
        self._split_page_var = tk.StringVar(value="")
        self._timer_label: ctk.CTkLabel | None = None
        self._current_label: ctk.CTkLabel | None = None
        self._run_minimal = False
        self._run_geometry_before_minimal: str | None = None
        self._run_titlebar: ctk.CTkFrame | None = None
        self._run_bar: ctk.CTkFrame | None = None
        self._run_foot: ctk.CTkFrame | None = None
        self._run_panel: ctk.CTkFrame | None = None
        self._run_nodes_host: ctk.CTkFrame | None = None
        self._hotkey_hint_label: ctk.CTkLabel | None = None
        self._undo_reset_label: ctk.CTkLabel | None = None
        self._route_name_label: ctk.CTkLabel | None = None
        self._run_maximized = False
        self._run_geometry_before_max: str | None = None
        self._drag_ox = 0
        self._drag_oy = 0
        self._dragging = False
        self._run_borderless = False
        self._pending_reborder = False
        self._resize_edge: str | None = None
        self._resize_origin: tuple[int, int, int, int, int, int] | None = None
        self._run_resize_grips: list[tk.Misc] = []
        self._tray_icon: pystray.Icon | None = None
        self._tray_thread: threading.Thread | None = None
        self.root.bind("<Map>", self._on_root_map, add="+")

        self._bind_hotkeys()
        self._init_theme()
        self._apply_window_icon()
        self._tick_timer()

    def _t(self, key: str) -> str:
        return t(self.ui_lang, key)

    def _apply_window_icon(self) -> None:
        """窗口/任务栏图标：优先 .ico，其次 PNG。"""
        ico = ensure_window_ico()
        if ico is not None:
            try:
                self.root.iconbitmap(default=str(ico))
            except tk.TclError:
                pass
        try:
            from PIL import ImageTk

            img = load_window_icon_image(64)
            photo = ImageTk.PhotoImage(img)
            self.root.iconphoto(True, photo)
            self._window_icon_photo = photo
        except Exception:
            self._window_icon_photo = None

    def _init_theme(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Route.Treeview",
            background=SURFACE,
            foreground=TEXT_FG,
            fieldbackground=SURFACE,
            bordercolor=BORDER,
            lightcolor=SURFACE,
            darkcolor=SURFACE,
            rowheight=38,
            font=("Microsoft YaHei", 12),
            relief="flat",
        )
        style.map(
            "Route.Treeview",
            background=[("selected", SELECT_BG)],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "Route.Vertical.TScrollbar",
            background=BORDER,
            troughcolor=BG,
            borderwidth=0,
            arrowcolor=MUTED_FG,
        )
        style.configure(
            "Route.Horizontal.TScrollbar",
            background=BORDER,
            troughcolor=BG,
            borderwidth=0,
            arrowcolor=MUTED_FG,
        )

    def _bind_hotkeys(self) -> None:
        self.root.bind_all("<KeyPress>", self._on_global_keypress, add="+")
        for keysym in (
            "KP_0", "KP_2", "KP_3", "KP_5", "KP_8",
            "0", "2", "3", "5", "8",
        ):
            self.root.bind_all(f"<KeyPress-{keysym}>", self._on_global_keypress, add="+")

    def _key_to_hotkey_digit(self, event: tk.Event) -> str | None:
        keysym = str(getattr(event, "keysym", "") or "")
        if keysym.startswith("KP_") and len(keysym) == 4:
            return keysym[3:]
        keycode = int(getattr(event, "keycode", 0) or 0)
        if keycode in _NUMPAD_KEYCODE_TO_DIGIT:
            return _NUMPAD_KEYCODE_TO_DIGIT[keycode]
        return None

    def _hotkey_actions(self) -> dict[str, object]:
        return {
            "0": self.engine.start_or_split,
            "2": self.engine.skip_split,
            "3": self.engine.pause_toggle,
            "5": self._confirm_reset,
            "8": self.engine.undo_split,
        }

    def _on_global_keypress(self, event: tk.Event) -> str | None:
        if self._run_frame is None:
            return None
        widget = event.widget
        widget_class = str(widget.winfo_class())
        if widget_class in {"Entry", "TEntry", "Text", "CTkEntry", "CTkTextbox"}:
            return None
        digit = self._key_to_hotkey_digit(event)
        if digit is None:
            return None
        action = self._hotkey_actions().get(digit)
        if action is None:
            return None
        test_log.write("USER", "小键盘", digit=digit, action=getattr(action, "__name__", str(action)))
        action()
        return "break"

    def _install_run_hotkeys(self, widget: tk.Misc) -> None:
        widget.bind("<KeyPress>", self._on_global_keypress, add="+")
        widget_class = str(widget.winfo_class())
        if not widget_class.startswith("CTk"):
            try:
                widget.configure(takefocus=1)
            except (tk.TclError, ValueError):
                pass
        for child in widget.winfo_children():
            child_class = child.winfo_class()
            if child_class in {"Entry", "TEntry", "Text", "CTkEntry", "CTkTextbox"}:
                continue
            self._install_run_hotkeys(child)

    def _focus_run_surface(self) -> None:
        if self._run_frame is None:
            return
        try:
            self._run_frame.focus_set()
        except tk.TclError:
            pass

    def _btn(
        self,
        parent: tk.Misc,
        text: str,
        command,
        *,
        variant: str = "ghost",
        width: int | None = None,
    ) -> ctk.CTkButton:
        if variant == "primary":
            fg, hover, text_color = BTN_PRIMARY, BTN_PRIMARY_HOVER, "#ffffff"
            font = ("Microsoft YaHei", 13, "bold")
            border_width = 0
        elif variant == "secondary":
            fg, hover, text_color = SURFACE, BTN_ACTIVE, TEXT_FG
            font = FONT_UI
            border_width = 1
        else:
            fg, hover, text_color = PANEL_BG, SURFACE, MUTED_FG
            font = FONT_UI_SM
            border_width = 1

        kwargs: dict = {
            "master": parent,
            "text": text,
            "command": command,
            "font": font,
            "fg_color": fg,
            "hover_color": hover,
            "text_color": text_color,
            "corner_radius": CORNER_RADIUS,
            "height": BTN_HEIGHT,
            "border_width": border_width,
            "border_color": BORDER,
        }
        if width is not None:
            kwargs["width"] = max(120, width * 10)
        return ctk.CTkButton(**kwargs)

    def run_startup(self) -> bool:
        if not ensure_setup(self, on_analyzed=self._on_first_analyze):
            return False
        self._show_main()
        return True

    def _format_import_message(self, summary: dict) -> str:
        sessions = summary.get("session_count", 0)
        merged = summary.get("merged_candidates", 0)
        routes = summary.get("route_count", 0)
        log_path = test_log.get_log_path()
        if summary.get("recent_only"):
            message = self._t("import_msg_recent").format(
                sessions=sessions, merged=merged, routes=routes
            )
        else:
            message = self._t("import_msg_full").format(
                sessions=sessions, merged=merged, routes=routes
            )
        if routes == 0:
            message += self._t("import_msg_zero")
        detected = summary.get("detected_locale")
        if detected:
            message += self._t("import_msg_locale").format(locale=detected)
        if log_path:
            message += self._t("import_msg_log").format(path=log_path)
        return message

    def _on_first_analyze(self, summary: dict) -> None:
        sessions = summary.get("session_count", 0)
        routes = summary.get("route_count", 0)
        if sessions or routes:
            messagebox.showinfo(
                self._t("analyze_done"),
                self._format_import_message(summary),
                parent=self.root,
            )

    def run(self) -> None:
        self.root.mainloop()

    def _clear_container(self) -> None:
        for child in self.container.winfo_children():
            child.destroy()
        self._main_frame = None
        self._run_frame = None
        self._run_chrome = None
        self._split_panel = None
        self._run_titlebar = None
        self._run_title_sep = None
        self._run_bar = None
        self._run_foot = None
        self._run_panel = None
        self._run_nodes_host = None
        self._run_minimal = False
        self._run_geometry_before_minimal = None
        self._timer_label = None
        self._current_label = None
        self._hotkey_hint_label = None
        self._undo_reset_label = None
        self._route_name_label = None
        self._clear_run_resize_grips()
        self._resize_end()

    def _run_grip_host(self) -> tk.Misc | None:
        return self._run_chrome or self._run_frame

    def _install_run_grips_if_needed(self) -> None:
        host = self._run_grip_host()
        if host is not None and not self._run_maximized:
            self._install_run_resize_grips(host)

    def _set_run_borderless(self, enabled: bool) -> None:
        if self._run_borderless == enabled:
            return
        self._run_borderless = enabled
        try:
            self.root.overrideredirect(enabled)
        except tk.TclError:
            pass

    def _drag_start(self, event: tk.Event) -> None:
        if self._run_frame is None or self._resize_edge:
            return
        self._drag_ox = event.x_root - self.root.winfo_x()
        self._drag_oy = event.y_root - self.root.winfo_y()
        self._dragging = False

    def _drag_motion(self, event: tk.Event) -> None:
        if self._run_frame is None or self._run_maximized or self._resize_edge:
            return
        dx = abs(event.x_root - self.root.winfo_x() - self._drag_ox)
        dy = abs(event.y_root - self.root.winfo_y() - self._drag_oy)
        if dx > 3 or dy > 3:
            self._dragging = True
        if self._dragging:
            self.root.geometry(f"+{event.x_root - self._drag_ox}+{event.y_root - self._drag_oy}")

    def _parse_run_geometry(self) -> tuple[int, int, int, int]:
        """从 geometry 字符串解析 WxH+X+Y，避免 winfo 在无边框窗口下读偏导致越拉越宽。"""
        import re

        geo = self.root.geometry()
        match = re.match(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)", geo)
        if match:
            return (
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
                int(match.group(4)),
            )
        return (
            max(260, self.root.winfo_width()),
            max(160, self.root.winfo_height()),
            self.root.winfo_x(),
            self.root.winfo_y(),
        )

    def _resize_start(self, edge: str, event: tk.Event) -> None:
        if self._run_maximized or not self._run_borderless:
            return
        w, h, x, y = self._parse_run_geometry()
        self._resize_edge = edge
        self._resize_origin = (x, y, w, h, event.x_root, event.y_root)

    def _resize_motion(self, event: tk.Event) -> None:
        if not self._resize_edge or self._resize_origin is None:
            return
        x, y, w, h, ox, oy = self._resize_origin
        dx = event.x_root - ox
        dy = event.y_root - oy
        min_w, min_h = 260, 160
        edge = self._resize_edge
        new_x, new_y, new_w, new_h = x, y, w, h

        # 用精确边集合，禁止 "e" in "se" 这类误伤；上下拖绝不改宽度
        if edge == "e":
            new_w = max(min_w, w + dx)
        elif edge == "w":
            new_w = max(min_w, w - dx)
            new_x = x + (w - new_w)
        elif edge == "s":
            new_h = max(min_h, h + dy)
        elif edge == "n":
            new_h = max(min_h, h - dy)
            new_y = y + (h - new_h)
        elif edge == "se":
            new_w = max(min_w, w + dx)
            new_h = max(min_h, h + dy)
        elif edge == "sw":
            new_w = max(min_w, w - dx)
            new_x = x + (w - new_w)
            new_h = max(min_h, h + dy)
        elif edge == "ne":
            new_w = max(min_w, w + dx)
            new_h = max(min_h, h - dy)
            new_y = y + (h - new_h)
        elif edge == "nw":
            new_w = max(min_w, w - dx)
            new_x = x + (w - new_w)
            new_h = max(min_h, h - dy)
            new_y = y + (h - new_h)

        self.root.geometry(f"{int(new_w)}x{int(new_h)}+{int(new_x)}+{int(new_y)}")

    def _resize_end(self, _event: tk.Event | None = None) -> None:
        self._resize_edge = None
        self._resize_origin = None

    def _clear_run_resize_grips(self) -> None:
        for grip in self._run_resize_grips:
            try:
                grip.destroy()
            except tk.TclError:
                pass
        self._run_resize_grips = []

    def _install_run_resize_grips(self, outer: tk.Misc) -> None:
        """无边框窗口边缘拉伸；上下边条避开左右角，避免误触斜角把宽度拉开。"""
        self._clear_run_resize_grips()
        size = 6
        corner = size + 6
        inset = corner / max(1, outer.winfo_width()) if outer.winfo_width() > 1 else 0.05
        inset = min(0.08, max(0.03, inset))
        specs: list[tuple[str, str, dict]] = [
            (
                "n",
                "size_ns",
                {"relx": inset, "rely": 0, "relwidth": max(0.2, 1 - 2 * inset), "height": size},
            ),
            (
                "s",
                "size_ns",
                {
                    "relx": inset,
                    "rely": 1,
                    "relwidth": max(0.2, 1 - 2 * inset),
                    "height": size,
                    "anchor": "sw",
                },
            ),
            ("w", "size_we", {"relx": 0, "rely": inset, "relheight": max(0.2, 1 - 2 * inset), "width": size}),
            (
                "e",
                "size_we",
                {
                    "relx": 1,
                    "rely": inset,
                    "relheight": max(0.2, 1 - 2 * inset),
                    "width": size,
                    "anchor": "ne",
                },
            ),
            ("nw", "size_nw_se", {"relx": 0, "rely": 0, "width": corner, "height": corner}),
            ("ne", "size_ne_sw", {"relx": 1, "rely": 0, "width": corner, "height": corner, "anchor": "ne"}),
            ("sw", "size_ne_sw", {"relx": 0, "rely": 1, "width": corner, "height": corner, "anchor": "sw"}),
            ("se", "size_nw_se", {"relx": 1, "rely": 1, "width": corner, "height": corner, "anchor": "se"}),
        ]
        for edge, cursor, place_kw in specs:
            grip = tk.Frame(outer, bg=BG, cursor=cursor, borderwidth=0, highlightthickness=0)
            grip.place(**place_kw)
            grip.bind("<ButtonPress-1>", lambda e, ed=edge: self._resize_start(ed, e))
            grip.bind("<B1-Motion>", self._resize_motion)
            grip.bind("<ButtonRelease-1>", self._resize_end)
            self._run_resize_grips.append(grip)
        for grip in self._run_resize_grips[-4:]:
            grip.lift()

    def _on_root_map(self, event: tk.Event) -> None:
        if event.widget is not self.root:
            return
        if self._pending_reborder and self._run_frame is not None:
            self._pending_reborder = False
            self.root.after(80, lambda: self._set_run_borderless(True))

    def _run_minimize(self) -> None:
        """最小化：隐藏窗口，进入托盘（任务栏隐藏图标区）。"""
        self._ensure_tray()
        # 无边框窗用 withdraw，比 iconify 更干净
        self.root.withdraw()

    def _ensure_tray(self) -> None:
        if self._tray_icon is not None:
            return

        def show_window(icon: object | None = None, item: object | None = None) -> None:
            self.root.after(0, self._restore_from_tray)

        def quit_app(icon: object | None = None, item: object | None = None) -> None:
            self.root.after(0, self._on_close)

        menu = pystray.Menu(
            pystray.MenuItem(self._t("tray_show"), show_window, default=True),
            pystray.MenuItem(self._t("tray_close"), quit_app),
        )
        self._tray_icon = pystray.Icon(
            APP_DISPLAY,
            load_tray_image(128),
            APP_DISPLAY,
            menu,
        )
        self._tray_thread = threading.Thread(target=self._tray_icon.run, daemon=True)
        self._tray_thread.start()

    def _stop_tray(self) -> None:
        icon = self._tray_icon
        self._tray_icon = None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass

    def _restore_from_tray(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        # Run 无边框状态在 withdraw 后可能丢，补回
        if self._run_frame is not None and self._run_borderless:
            try:
                self.root.overrideredirect(True)
            except tk.TclError:
                pass
        self._stop_tray()
        self.root.after_idle(self._focus_run_surface)

    def _run_toggle_maximize(self) -> None:
        btn = getattr(self, "_run_max_btn", None)
        if self._run_maximized:
            self._run_maximized = False
            geo = self._run_geometry_before_max or "360x480+100+100"
            self.root.geometry(geo)
            self._run_geometry_before_max = None
            if btn is not None:
                btn.configure(text="□")
            self._install_run_grips_if_needed()
            return
        self._run_geometry_before_max = self.root.geometry()
        self._run_maximized = True
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{sw}x{sh}+0+0")
        if btn is not None:
            btn.configure(text="❐")
        self._clear_run_resize_grips()

    def _bind_run_drag(self, widget: tk.Misc) -> None:
        skip = {
            "极简",
            "Minimal",
            "─",
            "□",
            "×",
            "❐",
            "保存并关闭",
            "Save & Close",
            "返回路线选择",
            "Back to Routes",
            "撤销重置",
            "Undo Reset",
        }
        try:
            text = str(widget.cget("text"))
        except (tk.TclError, AttributeError, ValueError):
            text = ""
        if text in skip:
            return
        widget.bind("<ButtonPress-1>", self._drag_start, add="+")
        widget.bind("<B1-Motion>", self._drag_motion, add="+")
        for child in widget.winfo_children():
            child_class = str(child.winfo_class())
            if child_class in {"Entry", "TEntry", "Text", "CTkEntry", "CTkTextbox"}:
                continue
            self._bind_run_drag(child)

    def _pack_run_normal_layout(self) -> None:
        """常规布局：顶栏 → 分隔线 → 节点区(上) → 下方控制面板。"""
        title = self._run_titlebar
        sep = getattr(self, "_run_title_sep", None)
        panel = self._run_panel
        nodes = self._run_nodes_host
        if title is not None:
            title.pack(side=tk.TOP, fill=tk.X)
        if sep is not None:
            sep.pack(side=tk.TOP, fill=tk.X)
        if panel is not None:
            panel.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=(4, 4))
        if nodes is not None:
            nodes.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 2))

    def _show_main(self) -> None:
        self.engine.stop_watching()
        self._set_run_borderless(False)
        self._run_maximized = False
        self._run_geometry_before_max = None
        self.root.attributes("-topmost", False)
        self.root.geometry("960x560")
        self.root.minsize(720, 480)
        self._clear_container()
        frame = ctk.CTkFrame(self.container, fg_color=BG, corner_radius=0)
        frame.pack(fill=tk.BOTH, expand=True, padx=24, pady=24)
        self._main_frame = frame

        header = ctk.CTkFrame(frame, fg_color=BG, corner_radius=0)
        header.pack(fill=tk.X, pady=(0, 20))
        brand = ctk.CTkFrame(header, fg_color=BG, corner_radius=0)
        brand.pack(side=tk.LEFT)
        try:
            from PIL import ImageTk

            mark = ImageTk.PhotoImage(load_window_icon_image(36))
            self._header_icon_photo = mark
            icon_lbl = tk.Label(brand, image=mark, bg=BG, borderwidth=0)
            icon_lbl.pack(side=tk.LEFT, padx=(0, 10))
        except Exception:
            self._header_icon_photo = None
        ctk.CTkLabel(brand, text=self._t("app_name"), text_color=TEXT_FG, font=FONT_TITLE).pack(
            side=tk.LEFT
        )
        self._btn(header, self._t("settings"), self._open_settings, variant="ghost").pack(
            side=tk.RIGHT
        )
        self._btn(header, self._t("lang_btn"), self._toggle_ui_lang, variant="ghost").pack(
            side=tk.RIGHT, padx=(0, 8)
        )
        self._btn(header, self._t("intro"), self._open_intro, variant="ghost").pack(
            side=tk.RIGHT, padx=(0, 8)
        )

        body = ctk.CTkFrame(frame, fg_color=BG, corner_radius=0)
        body.pack(fill=tk.BOTH, expand=True)
        body.grid_columnconfigure(0, weight=3, minsize=420)
        body.grid_columnconfigure(1, weight=1, minsize=220)
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(body, fg_color=BG, corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        ctk.CTkLabel(left, text=self._t("ref_routes"), text_color=MUTED_FG, font=FONT_UI_SM).pack(
            anchor="w", pady=(0, 8)
        )

        list_card = ctk.CTkFrame(left, fg_color=BORDER, corner_radius=CORNER_RADIUS)
        list_card.pack(fill=tk.BOTH, expand=True)
        list_inner = ctk.CTkFrame(list_card, fg_color=SURFACE, corner_radius=CORNER_RADIUS - 1)
        list_inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        tree_host = tk.Frame(list_inner, bg=SURFACE)
        tree_host.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        tree_host.grid_rowconfigure(0, weight=1)
        tree_host.grid_columnconfigure(0, weight=1)

        self._route_tree = ttk.Treeview(
            tree_host,
            style="Route.Treeview",
            show="tree",
            selectmode="extended",
        )
        self._route_tree.column("#0", stretch=True, minwidth=360, width=560)
        route_vscroll = ttk.Scrollbar(
            tree_host, orient=tk.VERTICAL, command=self._route_tree.yview, style="Route.Vertical.TScrollbar"
        )
        route_hscroll = ttk.Scrollbar(
            tree_host, orient=tk.HORIZONTAL, command=self._route_tree.xview, style="Route.Horizontal.TScrollbar"
        )
        self._route_tree.configure(yscrollcommand=route_vscroll.set, xscrollcommand=route_hscroll.set)
        self._route_tree.grid(row=0, column=0, sticky="nsew")
        route_vscroll.grid(row=0, column=1, sticky="ns")
        route_hscroll.grid(row=1, column=0, sticky="ew")
        self._route_tree.bind("<<TreeviewSelect>>", self._on_route_select)
        self._route_tree.bind("<Button-1>", self._on_route_tree_click)
        self._route_tree.bind("<Double-1>", self._on_route_tree_double_click)
        self._route_tree.bind("<Button-3>", self._on_route_tree_context)
        self._route_tree.bind("<Configure>", self._on_route_tree_resize)
        self._route_tree.tag_configure(
            "favorite",
            foreground=GOLD_FG,
            font=("Microsoft YaHei", 14, "bold"),
        )
        self._route_tree.tag_configure("route", foreground=TEXT_FG)
        self._route_tree.tag_configure("group", foreground=MUTED_FG)

        right = ctk.CTkFrame(body, fg_color=BG, corner_radius=0)
        right.grid(row=0, column=1, sticky="nsew")

        self._detail_title = tk.StringVar(value=self._t("select_route"))
        self._detail_meta = tk.StringVar(value="")
        self._detail_continue = tk.StringVar(value="")
        self._detail_hint = tk.StringVar(value=self._t("no_routes_hint"))

        ctk.CTkLabel(
            right,
            textvariable=self._detail_title,
            text_color=TEXT_FG,
            font=FONT_HEADING,
            anchor="w",
            justify="left",
            wraplength=240,
        ).pack(anchor="w", pady=(8, 6), fill=tk.X)
        ctk.CTkLabel(
            right,
            textvariable=self._detail_meta,
            text_color=MUTED_FG,
            font=FONT_UI,
            anchor="w",
            justify="left",
            wraplength=240,
        ).pack(anchor="w", fill=tk.X)
        ctk.CTkLabel(
            right,
            textvariable=self._detail_hint,
            text_color="#707070",
            font=FONT_HINT,
            anchor="w",
            justify="left",
            wraplength=240,
        ).pack(anchor="w", pady=(12, 0), fill=tk.X)

        ctk.CTkFrame(right, fg_color=BORDER, height=1, corner_radius=0).pack(fill=tk.X, pady=24)

        self._continue_btn = self._btn(right, self._t("continue"), self._on_continue, variant="primary", width=16)
        self._continue_btn.pack(anchor="w", fill=tk.X, pady=(0, 6))
        ctk.CTkLabel(
            right,
            textvariable=self._detail_continue,
            text_color=GOLD_FG,
            font=FONT_UI_SM,
            anchor="w",
            wraplength=240,
        ).pack(anchor="w", pady=(0, 20), fill=tk.X)

        self._btn(right, self._t("new_run"), self._on_new_run, variant="secondary", width=16).pack(
            anchor="w", fill=tk.X
        )

        self._refresh_route_list()

    def _route_game_group(self, route: ReferenceRoute) -> str:
        game_id = (route.game_id or self.config.game or "other").lower()
        if game_id in {"poe1", "poe2"}:
            return game_id
        return "other"

    def _route_tree_label(self, route: ReferenceRoute) -> str:
        best = format_duration(route.best_seconds) if route.best_seconds else "—"
        prefix = "★ " if route.is_favorite else ""
        return f"{prefix}{route.name} · {route.run_count}次 · {best} · {len(route.nodes)}节点"

    def _sort_routes_for_group(self, routes: list[ReferenceRoute]) -> list[ReferenceRoute]:
        # 收藏置顶，同优先级按名称
        return sorted(
            routes,
            key=lambda r: (0 if r.is_favorite else 1, (r.name or "").lower()),
        )

    def _on_route_tree_resize(self, event: tk.Event) -> None:
        if self._route_tree is None or event.widget is not self._route_tree:
            return
        # 给 #0 列吃满可见宽度，长路线名尽量直接显示，少用横向滚动
        width = max(360, event.width - 24)
        self._route_tree.column("#0", width=width, minwidth=360)

    def _refresh_route_list(self) -> None:
        if self._route_tree is None:
            return
        for item in self._route_tree.get_children():
            self._route_tree.delete(item)
        self._route_tree_items.clear()
        self._route_tree_groups.clear()

        routes = self.engine.store.list_routes()
        grouped: dict[str, list[ReferenceRoute]] = {
            "poe1": [],
            "poe2": [],
            "other": [],
        }
        for route in routes:
            grouped[self._route_game_group(route)].append(route)

        for group_key in ("poe1", "poe2", "other"):
            items = self._sort_routes_for_group(grouped[group_key])
            if not items:
                continue
            group_id = self._route_tree.insert(
                "",
                tk.END,
                text=f"{GAME_GROUP_LABELS[group_key]} ({len(items)})",
                open=True,
                tags=("group",),
            )
            self._route_tree_groups[group_id] = group_key
            for route in items:
                tags = ("favorite",) if route.is_favorite else ("route",)
                item_id = self._route_tree.insert(
                    group_id,
                    tk.END,
                    text=self._route_tree_label(route),
                    tags=tags,
                )
                self._route_tree_items[item_id] = route.route_id

        selected_route: ReferenceRoute | None = None
        if self._selected_route_id:
            selected_route = self._route_by_id(self._selected_route_id)
        if selected_route is None and routes:
            selected_route = routes[0]
            self._selected_route_id = routes[0].route_id

        if selected_route:
            for item_id, route_id in self._route_tree_items.items():
                if route_id == selected_route.route_id:
                    self._route_tree.selection_set(item_id)
                    self._route_tree.see(item_id)
                    break
            self._update_route_detail(selected_route)
        else:
            self._selected_route_id = None
            if self._detail_title:
                self._detail_title.set(self._t("no_routes"))
            if self._detail_meta:
                self._detail_meta.set("")
            if self._detail_hint:
                self._detail_hint.set(self._t("no_routes_hint"))
            if self._continue_btn:
                self._continue_btn.configure(
                    state="disabled",
                    fg_color=BTN_PRIMARY_DISABLED,
                    text_color="#8a9bb0",
                )

    def _selected_route_ids(self) -> list[str]:
        if self._route_tree is None:
            return []
        route_ids: list[str] = []
        for item in self._route_tree.selection():
            route_id = self._route_tree_items.get(item)
            if route_id:
                route_ids.append(route_id)
        return route_ids

    def _on_route_select(self, _event: object = None) -> None:
        route_ids = self._selected_route_ids()
        if not route_ids:
            return
        self._selected_route_id = route_ids[-1]
        route = self._route_by_id(self._selected_route_id)
        if route:
            self._update_route_detail(route)

    def _on_route_tree_click(self, event: tk.Event) -> str | None:
        if self._route_tree is None:
            return None
        item = self._route_tree.identify_row(event.y)
        if not item:
            return None
        # 整行点击分组头即可展开/折叠，不必点小三角
        if item in self._route_tree_groups:
            opened = bool(self._route_tree.item(item, "open"))
            self._route_tree.item(item, open=not opened)
            return "break"
        return None

    def _on_route_tree_double_click(self, event: tk.Event) -> None:
        if self._route_tree is None:
            return
        item = self._route_tree.identify_row(event.y)
        if not item:
            return
        if item in self._route_tree_groups:
            return
        route_id = self._route_tree_items.get(item)
        if route_id:
            self._selected_route_id = route_id
            route = self._route_by_id(route_id)
            if route:
                self._update_route_detail(route)

    def _on_route_tree_context(self, event: tk.Event) -> None:
        if self._route_tree is None:
            return
        item = self._route_tree.identify_row(event.y)
        if item and item in self._route_tree_items:
            if item not in self._route_tree.selection():
                self._route_tree.selection_set(item)
        route_ids = self._selected_route_ids()
        if not route_ids:
            return

        menu = tk.Menu(self.root, tearoff=0)
        if len(route_ids) == 1:
            route = self._route_by_id(route_ids[0])
            fav_text = self._t("unfavorite") if route and route.is_favorite else self._t("favorite")
            menu.add_command(label=fav_text, command=lambda: self._toggle_favorite_routes(route_ids))
            menu.add_command(label=self._t("rename"), command=lambda: self._rename_route(route_ids[0]))
            menu.add_separator()
        menu.add_command(
            label=self._t("delete") if len(route_ids) == 1 else f"{self._t('delete')} ({len(route_ids)})",
            command=lambda: self._delete_routes(route_ids),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _toggle_favorite_routes(self, route_ids: list[str]) -> None:
        for route_id in route_ids:
            route = self._route_by_id(route_id)
            if route is None:
                continue
            self.engine.store.set_favorite(route_id, not route.is_favorite)
        self._refresh_route_list()

    def _rename_route(self, route_id: str) -> None:
        route = self._route_by_id(route_id)
        if route is None:
            return
        name = self._ask_route_name("重命名", route.name)
        if name and name.strip():
            self.engine.store.rename_route(route_id, name.strip())
            self._refresh_route_list()

    def _ask_route_name(self, title: str, initial: str) -> str | None:
        """重命名对话框：宽度按完整名称测算，再加一点余量。"""
        import tkinter.font as tkfont

        dlg = ctk.CTkToplevel(self.root)
        dlg.title(title)
        dlg.configure(fg_color=BG)
        dlg.transient(self.root)
        dlg.grab_set()

        measure = tkfont.Font(family="Microsoft YaHei", size=13)
        text_w = measure.measure(initial or "路线名称")
        win_w = max(420, min(900, text_w + 160))
        dlg.geometry(f"{win_w}x140")
        dlg.minsize(win_w, 140)

        ctk.CTkLabel(
            dlg,
            text="路线名称：",
            text_color=MUTED_FG,
            font=("Microsoft YaHei", 12),
            anchor="w",
        ).pack(anchor="w", padx=16, pady=(16, 6))

        entry = ctk.CTkEntry(dlg, font=("Microsoft YaHei", 13), height=32)
        entry.pack(fill=tk.X, padx=16, pady=(0, 12))
        entry.insert(0, initial)
        entry.focus_set()
        entry.select_range(0, tk.END)

        result: dict[str, str | None] = {"value": None}

        def accept() -> None:
            result["value"] = entry.get()
            dlg.destroy()

        def cancel() -> None:
            result["value"] = None
            dlg.destroy()

        btns = ctk.CTkFrame(dlg, fg_color=BG, corner_radius=0)
        btns.pack(fill=tk.X, padx=16, pady=(0, 12))
        self._btn(btns, "取消", cancel, variant="ghost").pack(side=tk.RIGHT, padx=(8, 0))
        self._btn(btns, "确定", accept, variant="primary").pack(side=tk.RIGHT)
        entry.bind("<Return>", lambda _e: accept())
        dlg.protocol("WM_DELETE_WINDOW", cancel)
        dlg.wait_window()
        return result["value"]

    def _delete_routes(self, route_ids: list[str]) -> None:
        if not route_ids:
            return
        if not messagebox.askyesno("删除路线", f"确定删除 {len(route_ids)} 条路线？", parent=self.root):
            return
        self.engine.store.delete_routes(route_ids)
        if self._selected_route_id in route_ids:
            self._selected_route_id = None
        self._refresh_route_list()

    def _update_route_detail(self, route: ReferenceRoute) -> None:
        if self._detail_title is None:
            return
        self._detail_title.set(route.name)
        best = format_duration(route.best_seconds) if route.best_seconds else "—"
        nodes = len(route.nodes)
        self._detail_meta.set(f"{route.run_count} 次练习 · 最佳 {best} · {nodes} 个节点")
        if self._detail_hint:
            self._detail_hint.set("")

        saved = self.engine.get_saved_run_for_route(route.route_id)
        if self._continue_btn and self._detail_continue:
            if saved:
                area = saved.current_area or "进行中"
                elapsed = format_duration(saved.elapsed_seconds)
                self._detail_continue.set(f"{area}  ·  {elapsed}")
                self._continue_btn.configure(
                    state="normal",
                    fg_color=BTN_PRIMARY,
                    text_color="#ffffff",
                )
            else:
                self._detail_continue.set("")
                self._continue_btn.configure(
                    state="disabled",
                    fg_color=BTN_PRIMARY_DISABLED,
                    text_color="#8a9bb0",
                )

    def _route_by_id(self, route_id: str | None) -> ReferenceRoute | None:
        if not route_id:
            return None
        return self.engine.store.get_route(route_id)

    def _on_new_run(self) -> None:
        route = self._route_by_id(self._selected_route_id)
        if route is None:
            messagebox.showinfo("提示", self._t("pick_route_first"), parent=self.root)
            return
        self.engine.begin_new_run(route)
        test_log.write("USER", "新 Run", route_id=route.route_id, route_name=route.name)
        self._show_run()

    def _on_continue(self) -> None:
        route = self._route_by_id(self._selected_route_id)
        if route is None:
            return
        saved = self.engine.get_saved_run_for_route(route.route_id)
        if saved is None:
            messagebox.showinfo("提示", self._t("no_continue"), parent=self.root)
            return
        self.engine.begin_continue_run(saved)
        test_log.write("USER", "继续 Run", route_id=route.route_id, index=saved.current_index)
        self._show_run()

    def _on_run_resize(self, event: tk.Event) -> None:
        if self._run_frame is None or event.widget is not self._run_frame:
            return
        width = max(200, event.width)
        scale = max(0.55, min(1.35, width / 280))
        if self._timer_label is not None:
            self._timer_label.configure(font=("Consolas", max(14, int(26 * scale)), "bold"))
        # 快捷键提示随窗口变窄换行，避免撑破窗口宽度
        if self._hotkey_hint_label is not None:
            self._hotkey_hint_label.configure(wraplength=max(60, width - 100))
        if self._route_name_label is not None:
            self._route_name_label.configure(wraplength=max(80, width - 16))

    def _show_run(self) -> None:
        self._clear_container()
        self.root.geometry("360x480")
        self.root.minsize(260, 160)
        self.root.attributes("-topmost", True)
        self._set_run_borderless(True)
        self._run_minimal = False
        self._run_maximized = False
        self._run_geometry_before_minimal = None
        self._run_geometry_before_max = None

        # 1px 外边框：无系统标题栏时仍能看清窗口边界
        chrome = ctk.CTkFrame(self.container, fg_color=WINDOW_EDGE, corner_radius=0)
        chrome.pack(fill=tk.BOTH, expand=True)
        self._run_chrome = chrome

        outer = ctk.CTkFrame(chrome, fg_color=BG, corner_radius=0)
        outer.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        outer.bind("<Configure>", self._on_run_resize)
        self._run_frame = outer
        self._current_label = None

        # 自定义顶栏：极简 / 隐藏 / 最大化 / 关闭
        titlebar = ctk.CTkFrame(outer, fg_color="#1f1f1f", corner_radius=0, height=28)
        titlebar.pack_propagate(False)
        self._run_titlebar = titlebar
        ctk.CTkLabel(
            titlebar,
            text=APP_DISPLAY,
            text_color=MUTED_FG,
            font=("Microsoft YaHei", 11),
        ).pack(side=tk.LEFT, padx=(8, 0))

        def title_btn(text: str, command, *, width: int = 36) -> ctk.CTkLabel:
            lbl = ctk.CTkLabel(
                titlebar,
                text=text,
                text_color=MUTED_FG,
                font=("Consolas", 12) if text in {"─", "□", "×", "❐"} else ("Microsoft YaHei", 11),
                width=width,
                cursor="hand2",
            )
            lbl.pack(side=tk.RIGHT, padx=1, pady=2)
            lbl.bind("<Button-1>", lambda _e, c=command: c())
            return lbl

        title_btn("×", self._on_close, width=32)
        self._run_max_btn = title_btn("□", self._run_toggle_maximize, width=32)
        title_btn("─", self._run_minimize, width=32)
        title_btn(self._t("minimal"), self._enter_run_minimal, width=56)

        # 顶栏底部分隔线
        self._run_title_sep = ctk.CTkFrame(outer, fg_color=BORDER, height=1, corner_radius=0)

        # 下方控制面板（固定在底）
        panel = ctk.CTkFrame(outer, fg_color=BG, corner_radius=0)
        self._run_panel = panel

        foot = ctk.CTkFrame(panel, fg_color=BG, corner_radius=0)
        foot.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 0))
        self._run_foot = foot
        self._hotkey_hint_label = ctk.CTkLabel(
            foot,
            text=self._t("hotkeys"),
            text_color=MUTED_FG,
            font=("Microsoft YaHei", 10),
            justify="left",
            anchor="w",
            wraplength=240,
        )
        self._hotkey_hint_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        save_lbl = ctk.CTkLabel(
            foot,
            text=self._t("save_close"),
            text_color=MUTED_FG,
            font=("Microsoft YaHei", 10),
            cursor="hand2",
        )
        save_lbl.pack(side=tk.RIGHT, padx=2)
        save_lbl.bind("<Button-1>", lambda _e: self._save_and_close_run())
        self._undo_reset_label = ctk.CTkLabel(
            foot,
            text=self._t("undo_reset"),
            text_color=GOLD_FG,
            font=("Microsoft YaHei", 10),
            cursor="hand2",
        )
        self._undo_reset_label.pack(side=tk.RIGHT, padx=(0, 8))
        self._undo_reset_label.bind("<Button-1>", lambda _e: self._undo_reset())
        self._update_undo_reset_button()

        bar = ctk.CTkFrame(panel, fg_color=BG, corner_radius=0)
        bar.pack(side=tk.TOP, fill=tk.X)
        self._run_bar = bar
        back = ctk.CTkLabel(
            bar,
            text=self._t("back_routes"),
            text_color=MUTED_FG,
            font=("Microsoft YaHei", 11),
            cursor="hand2",
            anchor="w",
        )
        back.pack(side=tk.TOP, anchor="w", pady=(0, 2))
        back.bind("<Button-1>", lambda _e: self._leave_run())
        self._route_name_label = ctk.CTkLabel(
            bar,
            textvariable=self.route_name_var,
            text_color="#888888",
            font=("Microsoft YaHei", 10),
            anchor="w",
            justify="left",
            wraplength=320,
        )
        self._route_name_label.pack(side=tk.TOP, fill=tk.X, anchor="w")

        self._timer_label = ctk.CTkLabel(
            panel,
            textvariable=self.elapsed_var,
            text_color=TEXT_FG,
            font=FONT_TIMER,
        )
        self._timer_label.pack(side=tk.TOP, pady=(0, 0))

        self._current_label = ctk.CTkLabel(
            panel,
            textvariable=self.current_var,
            text_color=MUTED_FG,
            font=("Microsoft YaHei", 11),
        )
        self._current_label.pack(side=tk.TOP, pady=(0, 2))

        # 上方节点容器（占满剩余）
        nodes_host = ctk.CTkFrame(
            outer,
            fg_color=PANEL_BG,
            corner_radius=CORNER_RADIUS,
            border_width=2,
            border_color=BORDER,
        )
        self._run_nodes_host = nodes_host
        self._split_panel = SplitPanel(nodes_host)
        self._split_panel.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self._split_panel.set_exit_minimal_callback(self._exit_run_minimal)
        self._split_panel.set_close_app_callback(self._on_close)
        self._split_panel.set_ui_texts(
            headers={
                "node": self._t("col_node"),
                "time": self._t("col_time"),
                "ref": self._t("col_ref"),
                "delta": self._t("col_delta"),
                "total": self._t("col_total"),
            },
            exit_minimal=self._t("exit_minimal"),
            close_app=self._t("close"),
        )

        self._pack_run_normal_layout()
        self._bind_run_drag(outer)
        self._install_run_grips_if_needed()
        self._install_run_hotkeys(outer)
        self._split_page = 0
        self._refresh_run_view(self.engine.active_run)
        self.root.after_idle(self._focus_run_surface)

    def _enter_run_minimal(self) -> None:
        if self._run_minimal or self._split_panel is None:
            return
        self._run_minimal = True
        if not self._run_maximized:
            self._run_geometry_before_minimal = self.root.geometry()
        for widget in (self._run_titlebar, getattr(self, "_run_title_sep", None), self._run_panel):
            if widget is not None:
                widget.pack_forget()
        self._clear_run_resize_grips()
        if self._run_nodes_host is not None:
            self._run_nodes_host.pack(fill=tk.BOTH, expand=True, padx=3, pady=3)
        self._split_panel.set_minimal(True)
        self.root.minsize(280, 72)
        if not self._run_maximized:
            self.root.geometry("360x78")
        # 极简仍可边缘拉宽，保证总时间列能露出来
        self._install_run_grips_if_needed()
        self._refresh_run_view(self.engine.active_run)
        self.root.after_idle(self._focus_run_surface)

    def _exit_run_minimal(self) -> None:
        if not self._run_minimal or self._run_frame is None or self._split_panel is None:
            return
        if self._dragging:
            return
        self._run_minimal = False
        self._split_panel.set_minimal(False)
        if self._run_nodes_host is not None:
            self._run_nodes_host.pack_forget()
        self._pack_run_normal_layout()
        self._install_run_grips_if_needed()
        self.root.minsize(260, 160)
        if not self._run_maximized:
            if self._run_geometry_before_minimal:
                self.root.geometry(self._run_geometry_before_minimal)
            else:
                self.root.geometry("360x480")
        self._run_geometry_before_minimal = None
        self._refresh_run_view(self.engine.active_run)
        self.root.after_idle(self._focus_run_surface)

    def _split_page_prev(self) -> None:
        if self._split_page > 0:
            self._split_page -= 1
            self._refresh_run_view(self.engine.active_run)

    def _split_page_next(self) -> None:
        run = self.engine.active_run
        if run is None:
            return
        total_pages = max(1, (len(run.nodes) + NODES_PER_PAGE - 1) // NODES_PER_PAGE)
        if self._split_page + 1 < total_pages:
            self._split_page += 1
            self._refresh_run_view(run)

    def _open_simulator(self) -> None:
        if self._sim_popup is not None and self._sim_popup.winfo_exists():
            self._sim_popup.lift()
            return
        popup = ctk.CTkToplevel(self.root)
        popup.title("模拟进图")
        popup.geometry("400x360")
        popup.configure(fg_color=BG)
        popup.transient(self.root)
        self._sim_popup = popup
        panel = SimulatorPanel(popup, self)
        panel.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        panel.refresh()
        popup.protocol("WM_DELETE_WINDOW", lambda: popup.destroy())

    def _leave_run(self) -> None:
        if self.engine.has_active_run:
            self.engine.save_now()
        self._show_main()

    def _save_and_close_run(self) -> None:
        test_log.write("USER", "保存并关闭 Run")
        self._on_close()

    def _confirm_reset(self) -> None:
        if not self.engine.has_active_run:
            return
        if messagebox.askyesno(
            self._t("reset_title"),
            self._t("reset_confirm"),
            parent=self.root,
        ):
            self.engine.reset_run()
            test_log.write("USER", "重置 Run（已备份）")
            self._update_undo_reset_button()
            self._refresh_run_view(self.engine.active_run)

    def _undo_reset(self) -> None:
        if not self.engine.has_reset_backup():
            messagebox.showinfo(self._t("undo_reset"), self._t("undo_reset_none"), parent=self.root)
            return
        if not messagebox.askyesno(
            self._t("undo_reset"),
            self._t("undo_reset_confirm"),
            parent=self.root,
        ):
            return
        restored = self.engine.restore_reset_backup()
        if restored is None:
            messagebox.showerror("撤销失败", "备份损坏或无法读取。", parent=self.root)
            return
        test_log.write("USER", "撤销重置", index=restored.current_index)
        self._update_undo_reset_button()
        self._refresh_run_view(restored)
        messagebox.showinfo(self._t("undo_reset"), self._t("undo_reset_ok"), parent=self.root)

    def _update_undo_reset_button(self) -> None:
        lbl = self._undo_reset_label
        if lbl is None:
            return
        if self.engine.has_reset_backup():
            lbl.configure(text_color=GOLD_FG)
            lbl.pack(side=tk.RIGHT, padx=(0, 8))
        else:
            lbl.pack_forget()

    def _build_scrollable(self, parent: tk.Misc) -> tuple[tk.Canvas, ctk.CTkFrame]:
        host = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        host.pack(fill=tk.BOTH, expand=True)
        host.grid_rowconfigure(0, weight=1)
        host.grid_columnconfigure(0, weight=1)

        canvas = tk.Canvas(host, bg=BG, highlightthickness=0)
        vscroll = ttk.Scrollbar(host, orient=tk.VERTICAL, command=canvas.yview)
        hscroll = ttk.Scrollbar(host, orient=tk.HORIZONTAL, command=canvas.xview)
        inner = ctk.CTkFrame(canvas, fg_color=BG, corner_radius=0)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_event: object = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event: tk.Event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)

        canvas.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")
        hscroll.grid(row=1, column=0, sticky="ew")

        def _on_mousewheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-event.delta / 120), "units")

        def _bind_wheel(_event: object = None) -> None:
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_wheel(_event: object = None) -> None:
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)
        return canvas, inner

    def _toggle_ui_lang(self) -> None:
        self.ui_lang = UI_LANG_EN if self.ui_lang == UI_LANG_ZH else UI_LANG_ZH
        save_ui_lang(self.ui_lang)
        self.root.title(APP_DISPLAY)
        # 主界面重建以刷新文案；Run 中则仅切语言，下次进入主界面生效
        if self._main_frame is not None:
            self._show_main()

    def _open_intro(self) -> None:
        dlg = ctk.CTkToplevel(self.root)
        dlg.title(self._t("intro_title"))
        dlg.configure(fg_color=BG)
        dlg.transient(self.root)
        dlg.geometry("560x520")
        dlg.minsize(480, 400)
        box = ctk.CTkTextbox(dlg, font=FONT_UI, wrap="word", fg_color=SURFACE, text_color=TEXT_FG)
        box.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)
        box.insert("1.0", self._t("intro_body"))
        box.configure(state="disabled")

    def _open_settings(self) -> None:
        win = ctk.CTkToplevel(self.root)
        win.title(self._t("settings"))
        win.configure(fg_color=BG)
        win.transient(self.root)
        win.minsize(520, 280)
        win.geometry("580x320")

        shell = ctk.CTkFrame(win, fg_color=BG, corner_radius=0)
        shell.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        _canvas, frame = self._build_scrollable(shell)

        def build_game_row(game_id: str, title: str) -> None:
            block = ctk.CTkFrame(frame, fg_color=BG, corner_radius=0)
            block.pack(fill=tk.X, pady=(0, 18))

            row = ctk.CTkFrame(block, fg_color=BG, corner_radius=0)
            row.pack(fill=tk.X)

            ctk.CTkLabel(
                row,
                text=title,
                text_color=TEXT_FG,
                font=("Microsoft YaHei", 14, "bold"),
                width=100,
                anchor="w",
            ).pack(side=tk.LEFT, padx=(0, 8))

            saved = load_client_path_for_game(game_id)
            path_var = tk.StringVar(value=str(saved) if saved else "")

            def browse_game() -> None:
                selected = filedialog.askopenfilename(
                    parent=win,
                    title=self._t("pick_client_title").format(game=title),
                    filetypes=[("Client log", "Client.txt"), ("Text files", "*.txt"), ("All files", "*.*")],
                )
                if not selected:
                    return
                from pathlib import Path

                path = Path(selected).resolve()
                save_routelens_setup(str(path), game_id)
                self.config = load_routelens_config()
                self.engine.config = self.config
                self.engine.reload_game_profile()
                path_var.set(str(path))

            def import_game() -> None:
                from pathlib import Path

                raw = path_var.get().strip()
                path = Path(raw) if raw else None
                if path is None or not path.is_file():
                    messagebox.showerror(
                        self._t("import_fail_title"),
                        self._t("import_need_client"),
                        parent=win,
                    )
                    return
                try:
                    summary = self.engine.import_from_client_txt(client_path=path, game_id=game_id)
                except FileNotFoundError:
                    messagebox.showerror(
                        self._t("import_fail"),
                        self._t("client_not_found"),
                        parent=win,
                    )
                    return
                except OSError as exc:
                    messagebox.showerror(self._t("import_fail"), str(exc), parent=win)
                    return
                self.config = load_routelens_config()
                messagebox.showinfo(
                    self._t("analyze_done"),
                    self._format_import_message(summary),
                    parent=win,
                )
                if self._main_frame is not None:
                    self._refresh_route_list()

            self._btn(row, self._t("browse_client"), browse_game, variant="secondary").pack(
                side=tk.LEFT, padx=(0, 8)
            )
            self._btn(row, self._t("import_routes"), import_game, variant="primary").pack(
                side=tk.LEFT
            )

            ctk.CTkLabel(
                block,
                textvariable=path_var,
                text_color=MUTED_FG,
                font=FONT_UI_SM,
                anchor="w",
                justify="left",
                wraplength=520,
            ).pack(anchor="w", fill=tk.X, pady=(8, 0))

        build_game_row("poe1", self._t("game_poe1"))
        build_game_row("poe2", self._t("game_poe2"))

        ctk.CTkLabel(
            frame,
            text=self._t("client_hint"),
            text_color=TEXT_FG,
            font=("Microsoft YaHei", 13),
            anchor="w",
            justify="left",
        ).pack(anchor="w", fill=tk.X, pady=(12, 0))

        ctk.CTkFrame(frame, fg_color=BORDER, height=1, corner_radius=0).pack(fill=tk.X, pady=16)

        actions = ctk.CTkFrame(frame, fg_color=BG, corner_radius=0)
        actions.pack(fill=tk.X)

        def open_log() -> None:
            import os
            from pathlib import Path

            log_path = test_log.get_log_path()
            if log_path is None or not Path(log_path).is_file():
                messagebox.showinfo(
                    self._t("open_log"),
                    self._t("open_log_empty"),
                    parent=win,
                )
                return
            try:
                os.startfile(str(log_path))  # type: ignore[attr-defined]
            except OSError as exc:
                messagebox.showerror(
                    self._t("open_fail"),
                    self._t("open_fail_detail").format(exc=exc, path=log_path),
                    parent=win,
                )

        def open_log_folder() -> None:
            import os
            import subprocess
            from pathlib import Path

            log_path = test_log.get_log_path()
            if log_path is None:
                messagebox.showinfo(
                    self._t("open_log_folder"),
                    self._t("open_log_folder_empty"),
                    parent=win,
                )
                return
            folder = Path(log_path).parent
            try:
                folder.mkdir(parents=True, exist_ok=True)
                if Path(log_path).is_file():
                    # 打开目录并选中 assist.log，便于定位
                    subprocess.run(
                        ["explorer", f"/select,{Path(log_path).resolve()}"],
                        check=False,
                    )
                else:
                    os.startfile(str(folder))  # type: ignore[attr-defined]
            except OSError as exc:
                messagebox.showerror(
                    self._t("open_fail"),
                    self._t("open_fail_detail").format(exc=exc, path=folder),
                    parent=win,
                )

        def show_bug_feedback() -> None:
            from .version import BUG_FEEDBACK_TEXT, BUG_FEEDBACK_TEXT_EN

            dlg = ctk.CTkToplevel(win)
            dlg.title(self._t("bug"))
            dlg.configure(fg_color=BG)
            dlg.transient(win)
            dlg.geometry("480x400")
            box = ctk.CTkTextbox(dlg, font=FONT_UI, wrap="word", fg_color=SURFACE, text_color=TEXT_FG)
            box.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
            bug_text = BUG_FEEDBACK_TEXT_EN if self.ui_lang == UI_LANG_EN else BUG_FEEDBACK_TEXT
            box.insert("1.0", bug_text)
            box.configure(state="disabled")

            def copy_all() -> None:
                self.root.clipboard_clear()
                self.root.clipboard_append(bug_text)
                messagebox.showinfo(self._t("copied"), self._t("copied_bug"), parent=dlg)

            btn_row = ctk.CTkFrame(dlg, fg_color=BG, corner_radius=0)
            btn_row.pack(fill=tk.X, padx=12, pady=(0, 12))
            self._btn(btn_row, self._t("copy_all"), copy_all, variant="primary").pack(
                side=tk.LEFT, padx=(0, 8)
            )
            self._btn(
                btn_row, self._t("open_log_folder"), open_log_folder, variant="secondary"
            ).pack(side=tk.LEFT)

        def show_about() -> None:
            from .version import ABOUT_TEXT, ABOUT_TEXT_EN, APP_DISPLAY, VERSION

            dlg = ctk.CTkToplevel(win)
            dlg.title(f"{self._t('about')} {APP_DISPLAY}")
            dlg.configure(fg_color=BG)
            dlg.transient(win)
            dlg.geometry("480x420")
            ctk.CTkLabel(
                dlg,
                text=f"{APP_DISPLAY}  v{VERSION}",
                text_color=TEXT_FG,
                font=("Microsoft YaHei", 18, "bold"),
            ).pack(anchor="w", padx=16, pady=(16, 8))
            box = ctk.CTkTextbox(dlg, font=FONT_UI, wrap="word", fg_color=SURFACE, text_color=TEXT_FG)
            box.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
            about = ABOUT_TEXT_EN if self.ui_lang == UI_LANG_EN else ABOUT_TEXT
            box.insert("1.0", about)
            box.configure(state="disabled")

        self._btn(actions, self._t("open_log"), open_log, variant="secondary").pack(
            side=tk.LEFT, padx=(0, 8)
        )
        self._btn(actions, self._t("open_log_folder"), open_log_folder, variant="secondary").pack(
            side=tk.LEFT, padx=(0, 8)
        )
        self._btn(actions, self._t("bug"), show_bug_feedback, variant="secondary").pack(
            side=tk.LEFT, padx=(0, 8)
        )
        self._btn(actions, self._t("about"), show_about, variant="ghost").pack(side=tk.LEFT)

        win.update_idletasks()
        req_w = max(640, frame.winfo_reqwidth() + 56)
        req_h = max(360, frame.winfo_reqheight() + 64)
        win.geometry(f"{req_w}x{req_h}")

    def _analyze_client(self, *, quiet: bool) -> None:
        try:
            summary = self.engine.import_from_client_txt()
        except FileNotFoundError:
            if not quiet:
                messagebox.showerror(
                    self._t("analyze_fail"),
                    self._t("client_not_found"),
                    parent=self.root,
                )
            return
        except OSError as exc:
            if not quiet:
                messagebox.showerror(self._t("read_fail"), str(exc), parent=self.root)
            return
        if quiet:
            return
        messagebox.showinfo(
            self._t("analyze_done"),
            self._format_import_message(summary),
            parent=self.root,
        )
        if self._main_frame is not None:
            self._refresh_route_list()

    def _on_close(self) -> None:
        if self.engine.has_active_run:
            self.engine.save_now()
        self.engine.stop_watching()
        self._stop_tray()
        self.root.destroy()

    def _on_run_state(self, run: ActiveRun | None) -> None:
        self.root.after(0, lambda: self._refresh_run_view(run))

    def _tick_timer(self) -> None:
        if self.engine.has_active_run and self._run_frame is not None:
            seconds = self.engine.elapsed_seconds()
            total_cs = int(seconds * 100)
            hours, rem = divmod(total_cs, 360000)
            minutes, rem = divmod(rem, 6000)
            secs, cs = divmod(rem, 100)
            if hours:
                text = f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"
            else:
                text = f"{minutes:02d}:{secs:02d}.{cs:02d}"
            self.elapsed_var.set(text)
            tick = getattr(self, "_tick_count", 0) + 1
            self._tick_count = tick
            refresh_every = 2 if self._run_minimal else 8
            if tick % refresh_every == 0 and self.engine.active_run and (
                self.engine.timer_running or self.engine.active_run.is_paused or self._run_minimal
            ):
                self._refresh_run_view(self.engine.active_run)
        self.root.after(50, self._tick_timer)

    def _refresh_run_view(self, run: ActiveRun | None) -> None:
        if run is None or self._split_panel is None:
            return

        name = run.reference_route_name or "自由路线"
        self.route_name_var.set(name)

        if self.engine.timer_running:
            self.current_var.set("")
        else:
            self.current_var.set(self._t("press_0"))

        rows: list[dict] = []
        for index, node in enumerate(run.nodes):
            ref_sec = self.engine.reference_seconds_at(index)
            ref_text = format_duration(ref_sec) if ref_sec is not None else ""

            if node.completed and node.skipped:
                status = "skipped"
                time_text = "—"
                delta_text = ""
            elif node.completed:
                status = "completed"
                time_text = format_duration(node.seconds or 0.0)
                delta_text = format_delta(node.seconds or 0.0, ref_sec)
            elif index == run.current_index:
                status = "current"
                if self.engine.timer_running or run.is_paused:
                    seg = self.engine.current_segment_seconds()
                    time_text = format_duration(seg)
                    delta_text = format_delta(seg, ref_sec)
                else:
                    time_text = ""
                    delta_text = ""
            else:
                status = "pending"
                time_text = ""
                delta_text = ""

            rows.append(
                {
                    "name": node.name,
                    "time": time_text,
                    "ref": ref_text,
                    "delta": delta_text,
                    "status": status,
                }
            )

        # 全部节点进可滚动容器；极简模式只画表头+当前行（含总时间）
        total_text = self.elapsed_var.get()
        self._split_panel.set_rows(
            rows,
            run.current_index,
            auto_scroll=False,
            total_text=total_text,
        )
        self._split_page_var.set("")
