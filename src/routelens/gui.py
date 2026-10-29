from __future__ import annotations

import re
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
import pystray

from . import test_log
from .companion_config import migrate_legacy_userdata
from .config import (
    load_check_updates,
    load_client_path_for_game,
    load_routelens_config,
    load_ui_lang,
    save_check_updates,
    save_routelens_setup,
    save_ui_lang,
)
from .engine import RunEngine
from .hotkey_win32 import (
    GlobalHotkeys,
    HOTKEY_TOGGLE_CLICK_THROUGH,
    MOD_NOREPEAT,
    MOD_SHIFT,
    VK_S,
)
from .paths import is_frozen
from .updater import (
    ReleaseInfo,
    fetch_latest_release,
    is_newer,
    open_releases_page,
    prepare_and_launch_update,
)
from .version import VERSION
from .models import ActiveRun, ReferenceRoute, RunResult, format_delta, format_duration
from .act_map import act_count, chapter_slots, infer_game_from_area_id
from .act_timing import build_act_timing, expected_act_labels
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
    FONT_FOOT,
    FONT_HINT,
    FONT_TIMER,
    FONT_TITLE,
    FONT_TITLEBAR,
    FONT_UI,
    FONT_UI_SM,
    GOLD_FG,
    GREEN_FG,
    MUTED_FG,
    PANEL_BG,
    RED_FG,
    SELECT_BG,
    SKIP_FG,
    SURFACE,
    TEXT_FG,
    WINDOW_EDGE,
    apply_theme,
)
from .single_instance import start_activation_watcher
from .split_panel import SplitPanel
from .tray_icon import apply_window_icon, load_tray_image, load_window_icon_image
from .ui_i18n import UI_LANG_EN, UI_LANG_ZH, t
from .version import APP_DISPLAY, APP_NAME, APP_VERSION_LINE, VERSION_LABEL

LIST_BG = SURFACE
NODES_PER_PAGE = 50
# 窗口拖动 / 数字热键绑定要跳过的控件：输入框、滚动条（拖动滚动条必须只滚列表，
# 不能同时把整个无边框窗口拖走）等自带鼠标/键盘语义的控件。
_INTERACTION_EXEMPT_CLASSES = {
    "Entry",
    "TEntry",
    "Text",
    "CTkEntry",
    "CTkTextbox",
    "Scrollbar",
    "TScrollbar",
    "CTkScrollbar",
}
# 空白路线：每个游戏各一颗按钮，游戏由用户点的那颗决定（不看设置里的当前游戏）
BLANK_ROUTE_ENTRIES: tuple[tuple[str, str], ...] = (
    ("poe1", "free_run_poe1"),
    ("poe2", "free_run_poe2"),
)


def click_through_hint_text(    *,
    click_through: bool,
    hotkey_registered: bool,
    translate,
) -> tuple[str, str]:
    """提示条上 Shift+S 那一段的文案与颜色（纯函数，便于单测）。"""
    if click_through:
        return f"⚡ {translate('hk_click_through')} · {translate('click_through_on')}", GOLD_FG
    if not hotkey_registered:
        # 全局热键被占用（1409）：如实提示，不要静默失效
        return f"Shift+S {translate('click_through_unavailable')}", MUTED_FG
    return f"Shift+S {translate('click_through_off')}", MUTED_FG


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
    def __init__(self, root: tk.Misc | None = None) -> None:
        apply_theme()
        migrate_legacy_userdata()
        self.config = load_routelens_config()
        test_log.init_log(self.config.resolved_data_dir)
        self.engine = RunEngine(self.config)
        self.engine.set_state_callback(self._on_run_state)

        # root 可注入：同一进程反复建/销 Tk 根会偶发毁掉共享的 Tcl 解释器
        # （tcl_findLibrary 报错）。测试里注入同一个根即可避开。
        self.root = root if root is not None else ctk.CTk()
        self.ui_lang = load_ui_lang()
        self.root.title(APP_VERSION_LINE)
        self.root.geometry("920x520")
        self.root.minsize(640, 420)
        self.root.configure(fg_color=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.container = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=0)
        self.container.pack(fill=tk.BOTH, expand=True)

        self._main_frame: ctk.CTkFrame | None = None
        self._run_frame: tk.Misc | None = None
        self._run_chrome: tk.Misc | None = None
        self._selected_route_id: str | None = None
        self._route_tree: ttk.Treeview | None = None
        self._route_vscroll: ttk.Scrollbar | None = None
        self._route_hscroll: ttk.Scrollbar | None = None
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
        self.total_delta_var = tk.StringVar(value="")
        self.current_var = tk.StringVar(value=self._t("press_0"))
        self.route_name_var = tk.StringVar(value="")

        self._split_panel: SplitPanel | None = None
        self._split_page = 0
        self._split_page_var = tk.StringVar(value="")
        # 分段视图：False = 节点视图（逐区域），True = 幕视图（逐幕汇总）
        self._act_view = False
        self._view_toggle_label: ctk.CTkLabel | None = None
        self._timer_label: ctk.CTkLabel | None = None
        self._total_delta_label: ctk.CTkLabel | None = None
        self._current_label: ctk.CTkLabel | None = None
        self._run_minimal = False
        # 普通 / 极简各自记住最后一次窗口几何（大小+位置），互不覆盖
        self._run_geometry_normal: str | None = None
        self._run_geometry_minimal: str | None = None
        self._run_titlebar: ctk.CTkFrame | None = None
        self._run_bar: ctk.CTkFrame | None = None
        self._run_foot: ctk.CTkFrame | None = None
        self._run_panel: ctk.CTkFrame | None = None
        self._run_nodes_host: ctk.CTkFrame | None = None
        self._run_list_body: ctk.CTkFrame | None = None
        self._run_vbar: ttk.Scrollbar | None = None
        self._click_through = False
        self._click_through_label: ctk.CTkLabel | None = None
        self._global_hotkeys: GlobalHotkeys | None = None
        self._hotkey_registered = False
        self._hotkey_retry_after = 0
        self._hotkey_retry_job: str | None = None
        self._run_minimal_rows = 1
        self._hotkey_hint_label: ctk.CTkFrame | ctk.CTkLabel | None = None
        self._hotkey_bar_items: list[tuple[ctk.CTkLabel, int]] = []
        self._hotkey_bar_height = 0
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
        self._window_icon_photos: list[object] = []
        self.root.bind("<Map>", self._on_root_map, add="+")

        self._bind_hotkeys()
        self._init_theme()
        self._apply_window_icon()
        self._tick_timer()

    def _t(self, key: str) -> str:
        return t(self.ui_lang, key)

    def _apply_window_icon(self, window: tk.Misc | None = None) -> None:
        """主窗与子窗统一 routelens.ico。"""
        target = window or self.root
        photo = apply_window_icon(target)
        if photo is not None:
            self._window_icon_photos.append(photo)

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
            "KP_0", "KP_2", "KP_3", "KP_5", "KP_8", "KP_9",
            "0", "2", "3", "5", "8", "9",
        ):
            self.root.bind_all(f"<KeyPress-{keysym}>", self._on_global_keypress, add="+")

    def _key_to_hotkey_digit(self, event: tk.Event) -> str | None:
        keysym = str(getattr(event, "keysym", "") or "")
        if keysym.startswith("KP_") and len(keysym) == 4 and keysym[3:].isdigit():
            return keysym[3:]
        if len(keysym) == 1 and keysym.isdigit():
            return keysym
        keycode = int(getattr(event, "keycode", 0) or 0)
        if keycode in _NUMPAD_KEYCODE_TO_DIGIT:
            return _NUMPAD_KEYCODE_TO_DIGIT[keycode]
        return None

    def _hotkey_actions(self) -> dict[str, object]:
        return {
            "0": self.engine.start_or_split,
            "2": self.engine.skip_split,
            "3": self.engine.pause_toggle,
            "4": self._toggle_act_view,
            "5": self._confirm_reset,
            "8": self.engine.undo_split,
            "9": self._toggle_run_minimal,
        }

    def _invoke_hotkey_digit(self, digit: str, *, source: str = "click") -> None:
        if self._run_frame is None:
            return
        action = self._hotkey_actions().get(digit)
        if action is None:
            return
        test_log.write(
            "USER",
            "热键",
            digit=digit,
            source=source,
            action=getattr(action, "__name__", str(action)),
        )
        action()

    def _build_clickable_hotkey_bar(self, foot: ctk.CTkFrame) -> None:
        """底栏快捷键做成可点击文字按钮（与小键盘同功能）。

        字号放大后整行可能放不下（窄窗 / 英文），这里按可用宽度自动折行。
        子控件一律用 place（Tk 不允许同一控件混用 pack/place）。

        容器用原生 tk.Frame：CTkFrame.configure() 会重设自己的 <Configure> 绑定，
        把这里的折行回调顶掉 → 窗口变窄后仍保持旧的一行坐标（Shift+S 被裁掉）。
        """
        bar = tk.Frame(foot, bg=BG, height=22, bd=0, highlightthickness=0)
        bar.pack(side=tk.TOP, fill=tk.X)
        bar.pack_propagate(False)
        self._hotkey_hint_label = bar
        self._hotkey_bar_items = []
        self._hotkey_bar_height = 0
        specs = (
            ("0", "hk_0"),
            ("2", "hk_2"),
            ("8", "hk_8"),
            ("3", "hk_3"),
            ("4", "hk_4"),
            ("5", "hk_5"),
            ("9", "hk_9"),
        )
        hover_fg = TEXT_FG
        normal_fg = MUTED_FG
        font = FONT_FOOT

        def hint_label(parent: tk.Misc, text: str, color: str, *, clickable: bool) -> tk.Label:
            """原生 tk.Label：CTkLabel.place 会按 DPI 缩放 x/y，与物理宽度比较必然错位。"""
            return tk.Label(
                parent,
                text=text,
                fg=color,
                bg=BG,
                font=font,
                bd=0,
                highlightthickness=0,
                padx=0,
                pady=0,
                cursor="hand2" if clickable else "",
            )

        for index, (digit, key) in enumerate(specs):
            if index:
                sep = hint_label(bar, "·", MUTED_FG, clickable=False)
                self._hotkey_bar_items.append((sep, 4))
            lbl = hint_label(bar, self._t(key), normal_fg, clickable=True)
            self._hotkey_bar_items.append((lbl, 0))

            def _enter(_e, widget=lbl) -> None:
                widget.configure(fg=hover_fg)

            def _leave(_e, widget=lbl) -> None:
                widget.configure(fg=normal_fg)

            lbl.bind("<Enter>", _enter)
            lbl.bind("<Leave>", _leave)
            lbl.bind("<Button-1>", lambda _e, d=digit: self._invoke_hotkey_digit(d))

        # Shift+S 鼠标穿透：显示快捷键，可点击切换（穿透时点不到，靠全局热键）
        sep = hint_label(bar, "·", MUTED_FG, clickable=False)
        self._hotkey_bar_items.append((sep, 4))
        ct_lbl = hint_label(bar, f"Shift+S {self._t('click_through_off')}", MUTED_FG, clickable=True)
        self._hotkey_bar_items.append((ct_lbl, 0))
        ct_lbl.bind("<Button-1>", lambda _e: self._toggle_click_through())
        self._click_through_label = ct_lbl
        bar.bind("<Configure>", self._on_hotkey_bar_resize)

    def _on_hotkey_bar_resize(self, event: tk.Event | None = None) -> None:
        bar = self._hotkey_hint_label
        if bar is None:
            return
        try:
            width = event.width if event is not None else bar.winfo_width()
        except (tk.TclError, AttributeError):
            return
        self._relayout_hotkey_bar(bar, width)

    def _schedule_hotkey_relayout(self) -> None:
        """窗口宽度变化后（或提示文案变化后）重排热键条，一次空闲内合并。"""
        if not hasattr(self, "_hotkey_relayout_pending"):
            self._hotkey_relayout_pending = False
        if self._hotkey_relayout_pending:
            return
        bar = self._hotkey_hint_label
        if bar is None:
            return
        self._hotkey_relayout_pending = True

        def _run() -> None:
            self._hotkey_relayout_pending = False
            current = self._hotkey_hint_label
            if current is None:
                return
            try:
                if not current.winfo_exists():
                    return
                width = min(current.winfo_width(), self.root.winfo_width())
            except tk.TclError:
                return
            self._relayout_hotkey_bar(current, width)

        try:
            self.root.after_idle(_run)
        except tk.TclError:
            self._hotkey_relayout_pending = False

    def _relayout_hotkey_bar(self, bar: tk.Misc, width: int) -> None:
        """把热键项按可用宽度流式折行（place 定位，不参与父容器尺寸推导）。

        可用宽度取 min(bar 宽度, 窗口宽度)：bar 的请求宽度可能被内容撑得比窗口还宽，
        只信 bar 自己会算出「放得下」，结果右端（Shift+S）被窗口裁掉。
        """
        items = self._hotkey_bar_items
        if not items or width <= 1:
            return
        try:
            bar.update_idletasks()
            root_width = self.root.winfo_width()
        except tk.TclError:
            return
        avail = max(1, min(width, root_width))
        x = 0
        y = 0
        line_h = 0
        placed: list[tuple[tk.Misc, int, int]] = []
        line_start = True
        for widget, gap in items:
            try:
                w = widget.winfo_reqwidth() + gap
                h = widget.winfo_reqheight()
            except tk.TclError:
                continue
            if x > 0 and x + w > avail:
                y += line_h
                x = 0
                line_h = 0
                line_start = True
            is_sep = str(widget.cget("text")) == "·"
            # 行首不摆分隔点（折行处会留下一个孤零零的「·」）
            if line_start and is_sep:
                continue
            placed.append((widget, x, y))
            line_start = False
            x += w
            line_h = max(line_h, h)

        # 行尾的分隔点也藏起来（下一个按钮已经折到下一行）
        hidden: set[tk.Misc] = set()
        for idx, (widget, _px, py) in enumerate(placed):
            if str(widget.cget("text")) != "·":
                continue
            if idx + 1 < len(placed) and placed[idx + 1][2] > py:
                hidden.add(widget)

        for widget, px, py in placed:
            try:
                if widget in hidden:
                    widget.place_forget()
                else:
                    widget.place(x=px, y=py)
            except tk.TclError:
                continue
        total_h = y + line_h
        if total_h == self._hotkey_bar_height:
            return
        self._hotkey_bar_height = total_h
        try:
            bar.configure(height=total_h)
        except tk.TclError:
            pass

    def _toggle_run_minimal(self) -> None:
        """9：极简 ↔ 正常。"""
        if self._run_frame is None:
            return
        if self._run_minimal:
            self._exit_run_minimal()
        else:
            self._enter_run_minimal()

    # ---- 鼠标穿透（Shift+S 切换；全局热键不依赖窗口焦点）----

    def _hwnd(self) -> int:
        try:
            return int(self.root.winfo_id())
        except (tk.TclError, ValueError):
            return 0

    @staticmethod
    def _get_window_long(hwnd: int) -> int:
        import ctypes

        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        if hasattr(ctypes, "windll") and hasattr(user32, "GetWindowLongPtrW"):
            return int(user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE))
        return int(ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE))

    @staticmethod
    def _set_window_long(hwnd: int, ex_style: int) -> None:
        import ctypes

        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        if hasattr(user32, "SetWindowLongPtrW"):
            user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex_style)
        else:
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)

    def _set_click_through(self, enabled: bool) -> bool:
        """Win32 WS_EX_TRANSPARENT|WS_EX_LAYERED 切换鼠标命中。

        关键：WS_EX_LAYERED 设置后必须调 SetLayeredWindowAttributes，
        否则 DWM 不再合成该窗口 → 画面冻结在最后一帧（计时/引擎照跑，显示暂停）。
        alpha=255 全不透明 = 画面正常刷新 + 点击穿透。
        """
        import ctypes

        if not hasattr(ctypes, "windll"):
            return False
        hwnd = self._hwnd()
        if not hwnd:
            return False
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        LWA_ALPHA = 0x00000002
        ex_style = self._get_window_long(hwnd)
        if enabled:
            ex_style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
        else:
            ex_style &= ~WS_EX_TRANSPARENT
            # layered 本身无害，但既然只为穿透而加，关掉更干净
            ex_style &= ~WS_EX_LAYERED
        self._set_window_long(hwnd, ex_style)
        if enabled:
            user32.SetLayeredWindowAttributes(hwnd, 0, 255, LWA_ALPHA)
        return True

    def _toggle_click_through(self) -> None:
        if self._run_frame is None:
            return
        # 热键未注册成功时禁止开启穿透：否则面板点不到、热键又没绑定，用户会被锁在外面
        if not self._click_through and not self._hotkey_registered:
            test_log.write("WARN", "拒绝开启穿透：Shift+S 热键未注册")
            return
        enabled = not self._click_through
        if not self._set_click_through(enabled):
            return
        self._click_through = enabled
        test_log.write("USER", "切换鼠标穿透", enabled=enabled)
        self._refresh_click_through_label()

    def _refresh_click_through_label(self) -> None:
        if self._split_panel is not None:
            self._split_panel.set_click_through_hint("", enabled=self._click_through)
        # 窗口边框金色 = 穿透中（任何模式下 1px 一眼可见，不占内容空间）
        chrome = self._run_chrome
        if chrome is not None:
            try:
                chrome.configure(bg=GOLD_FG if self._click_through else WINDOW_EDGE)
            except tk.TclError:
                pass
        label = self._click_through_label
        if label is None:
            return
        text, color = click_through_hint_text(
            click_through=self._click_through,
            hotkey_registered=self._hotkey_registered,
            translate=self._t,
        )
        try:
            label.configure(text=text, fg=color)
        except tk.TclError:
            pass
        # 文案长度变了（穿透开/关），折行可能变化
        self._schedule_hotkey_relayout()

    # ---- Shift+S 系统级全局热键 ----

    def _ensure_global_hotkeys(self) -> GlobalHotkeys | None:
        if self._global_hotkeys is not None:
            return self._global_hotkeys if self._global_hotkeys.available else None
        if not hasattr(self, "_hotkey_queue"):
            import queue

            self._hotkey_queue: "queue.Queue" = queue.Queue()

            # 主线程轮询泵：工作线程只入队，Tk 侧安全执行
            def _drain() -> None:
                import queue as _q

                q = self._hotkey_queue
                while True:
                    try:
                        cb = q.get_nowait()
                    except _q.Empty:
                        break
                    try:
                        cb()
                    except Exception:  # noqa: BLE001 - UI 回调异常不拖垮泵
                        pass
                self.root.after(50, _drain)

            self.root.after(50, _drain)
        hotkeys = GlobalHotkeys(schedule=self._hotkey_queue.put)
        if not hotkeys.available:
            return None
        self._global_hotkeys = hotkeys
        hotkeys.set_callback(
            HOTKEY_TOGGLE_CLICK_THROUGH, self._toggle_click_through
        )
        return hotkeys

    def _register_global_hotkeys(self) -> None:
        hotkeys = self._ensure_global_hotkeys()
        if hotkeys is None:
            return
        ok = hotkeys.register(
            HOTKEY_TOGGLE_CLICK_THROUGH,
            MOD_SHIFT | MOD_NOREPEAT,
            VK_S,
        )
        if ok:
            self._hotkey_retry_after = 0
            self._hotkey_registered = True
            self._refresh_click_through_label()
            return
        # 注册失败多为热键被其他程序临时占用（1409）：退避重试，不静默失效
        err = getattr(hotkeys, "last_error", 0)
        test_log.write("WARN", "全局热键注册失败，将重试", hotkey="Shift+S", win_error=err)
        self._hotkey_registered = False
        self._refresh_click_through_label()
        self._schedule_hotkey_retry()

    def _schedule_hotkey_retry(self) -> None:
        delay = self._hotkey_retry_after
        self._hotkey_retry_after = 1 if delay == 0 else min(60, delay * 2)
        if self._hotkey_retry_job is not None:
            try:
                self.root.after_cancel(self._hotkey_retry_job)
            except (tk.TclError, ValueError):
                pass
        self._hotkey_retry_job = self.root.after(
            self._hotkey_retry_after * 1000, self._retry_register_global_hotkeys
        )

    def _retry_register_global_hotkeys(self) -> None:
        self._hotkey_retry_job = None
        # 已离开 Run 界面则不再重试
        if self._run_frame is None:
            return
        hotkeys = self._global_hotkeys
        if hotkeys is None or not hotkeys.available:
            return
        ok = hotkeys.register(
            HOTKEY_TOGGLE_CLICK_THROUGH,
            MOD_SHIFT | MOD_NOREPEAT,
            VK_S,
        )
        if ok:
            self._hotkey_registered = True
            self._hotkey_retry_after = 0
            test_log.write("USER", "全局热键重试成功", hotkey="Shift+S")
            self._refresh_click_through_label()
            return
        self._schedule_hotkey_retry()

    def _unregister_global_hotkeys(self) -> None:
        if self._hotkey_retry_job is not None:
            try:
                self.root.after_cancel(self._hotkey_retry_job)
            except (tk.TclError, ValueError):
                pass
            self._hotkey_retry_job = None
        self._hotkey_registered = False
        self._hotkey_retry_after = 0
        hotkeys = self._global_hotkeys
        if hotkeys is None:
            return
        hotkeys.unregister(HOTKEY_TOGGLE_CLICK_THROUGH)

    def _on_global_keypress(self, event: tk.Event) -> str | None:
        if self._run_frame is None:
            return None
        widget = event.widget
        widget_class = str(widget.winfo_class())
        if widget_class in _INTERACTION_EXEMPT_CLASSES:
            return None
        digit = self._key_to_hotkey_digit(event)
        if digit is None:
            return None
        self._invoke_hotkey_digit(digit, source="key")
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
            if child_class in _INTERACTION_EXEMPT_CLASSES:
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
        if not self._restore_saved_run_or_main():
            return False
        # 主界面出来后再查更新，避免挡住首次设置
        self.root.after(1800, lambda: self._check_updates(manual=False))
        return True

    def _restore_saved_run_or_main(self) -> bool:
        """有未结束的 Run 时直接恢复上次状态，否则进主界面选路线。"""
        try:
            saved = self.engine.load_saved_run()
        except (OSError, ValueError):
            saved = None
        if saved is None:
            self._show_main()
            return True
        # 参考路线可能已被删除：仍恢复 Run（节点已在 Run 里快照），但不要崩溃
        try:
            self.engine.begin_continue_run(saved)
        except (FileNotFoundError, OSError):
            # Client.txt 暂不可用等：退回主界面，保证可用
            self._show_main()
            return True
        test_log.write("USER", "启动恢复 Run", route_id=saved.reference_route_id or "",
                       index=saved.current_index)
        try:
            self._show_run()
        except Exception:
            # 界面恢复失败则退回主界面，保证可用
            self._show_main()
        return True

    def _check_updates(self, *, manual: bool = False) -> None:
        if not manual and not load_check_updates():
            return

        def worker() -> None:
            try:
                latest = fetch_latest_release()
                if latest is None:
                    self.root.after(0, lambda: self._on_update_checked(None, "none", manual))
                elif is_newer(latest.version, VERSION):
                    self.root.after(0, lambda: self._on_update_checked(latest, None, manual))
                else:
                    self.root.after(0, lambda: self._on_update_checked(latest, "latest", manual))
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda: self._on_update_checked(None, exc, manual))

        threading.Thread(target=worker, daemon=True).start()

    def _on_update_checked(
        self,
        info: ReleaseInfo | None,
        status: object,
        manual: bool,
    ) -> None:
        if info is not None and status is None:
            body = self._t("update_body").format(current=VERSION, latest=info.version)
            if info.name and info.name not in {info.tag, info.version, f"v{info.version}"}:
                body = f"{info.name}\n\n{body}"
            if not messagebox.askyesno(self._t("update_title"), body, parent=self.root):
                return
            self._download_and_apply_update(info)
            return
        if not manual:
            return
        if status == "latest" and info is not None:
            messagebox.showinfo(
                self._t("check_updates_btn"),
                self._t("update_latest").format(version=info.version or VERSION),
                parent=self.root,
            )
            return
        messagebox.showinfo(
            self._t("check_updates_btn"),
            self._t("update_none"),
            parent=self.root,
        )

    def _download_and_apply_update(self, info: ReleaseInfo) -> None:
        if not is_frozen():
            open_releases_page()
            messagebox.showinfo(
                self._t("update_title"),
                self._t("update_dev_only"),
                parent=self.root,
            )
            return

        wait = ctk.CTkToplevel(self.root)
        self._apply_window_icon(wait)
        wait.title(self._t("update_title"))
        wait.configure(fg_color=BG)
        wait.transient(self.root)
        wait.geometry("360x120")
        wait.resizable(False, False)
        ctk.CTkLabel(
            wait,
            text=self._t("update_downloading"),
            text_color=TEXT_FG,
            font=FONT_UI,
            wraplength=320,
        ).pack(expand=True, padx=20, pady=20)
        wait.grab_set()

        def worker() -> None:
            try:
                prepare_and_launch_update(info)

                def finish() -> None:
                    try:
                        wait.destroy()
                    except tk.TclError:
                        pass
                    messagebox.showinfo(
                        self._t("update_title"),
                        self._t("update_ready"),
                        parent=self.root,
                    )
                    self._on_close()

                self.root.after(0, finish)
            except Exception as exc:  # noqa: BLE001

                def fail() -> None:
                    try:
                        wait.destroy()
                    except tk.TclError:
                        pass
                    messagebox.showerror(
                        self._t("update_fail"),
                        self._t("update_fail_detail").format(exc=exc),
                        parent=self.root,
                    )

                self.root.after(0, fail)

        threading.Thread(target=worker, daemon=True).start()

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
        unfinished = summary.get("unfinished_characters") or []
        if unfinished:
            message += self._t("import_msg_unfinished").format(
                names="、".join(unfinished[:8]) + ("…" if len(unfinished) > 8 else "")
            )
        detected = summary.get("detected_locale")
        if detected:
            message += self._t("import_msg_locale").format(locale=detected)
        game_id = str(summary.get("game_id") or "").strip().lower()
        if game_id in {"poe1", "poe2"}:
            game_label = self._t("game_poe2") if game_id == "poe2" else self._t("game_poe1")
            message += self._t("import_msg_game").format(game=game_label)
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
        self._route_tree = None
        self._route_vscroll = None
        self._route_hscroll = None
        self._run_titlebar = None
        self._run_title_sep = None
        self._run_bar = None
        self._run_foot = None
        self._run_panel = None
        self._run_nodes_host = None
        self._run_list_body = None
        self._run_vbar = None
        if self._run_frame is not None and not self._run_maximized:
            try:
                geo = self.root.geometry()
                if self._run_minimal:
                    self._run_geometry_minimal = geo
                else:
                    self._run_geometry_normal = geo
            except tk.TclError:
                pass
        self._run_minimal = False
        self._run_minimal_rows = 1
        self._timer_label = None
        self._total_delta_label = None
        self._current_label = None
        self._hotkey_hint_label = None
        self._hotkey_bar_items = []
        self._hotkey_bar_height = 0
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
        return self._parse_geometry_string(self.root.geometry())

    def _parse_geometry_string(self, geo: str) -> tuple[int, int, int, int]:
        import re

        match = re.match(r"(\d+)x(\d+)([+-]\d+)([+-]\d+)", str(geo or ""))
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
        if self._run_minimal:
            min_w = 280
            min_h = self._estimate_minimal_window_height(1)
        edge = self._resize_edge
        new_x, new_y, new_w, new_h = x, y, w, h

        # 极简竖直拉伸上限：略高于三行高度，松手再吸附
        if self._run_minimal and edge in {"n", "s", "ne", "nw", "se", "sw"}:
            max_h = self._estimate_minimal_window_height(3) + 40
        else:
            max_h = None

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

        if max_h is not None and new_h > max_h:
            if edge in {"n", "ne", "nw"}:
                new_y = y + (h - max_h)
            new_h = max_h

        self.root.geometry(f"{int(new_w)}x{int(new_h)}+{int(new_x)}+{int(new_y)}")
        if self._run_minimal and edge in {"n", "s", "ne", "nw", "se", "sw"}:
            self._update_minimal_rows_from_height(int(new_h))

    def _resize_end(self, _event: tk.Event | None = None) -> None:
        self._resize_edge = None
        self._resize_origin = None
        if self._run_minimal:
            self._snap_minimal_geometry()

    def _estimate_minimal_window_height(self, row_count: int) -> int:
        """极简窗口高度 = 内容 + 1px chrome。"""
        panel = self._split_panel
        if panel is None:
            return 56 if row_count < 2 else 96
        # 用 geometry 宽度，避免 winfo 在刚切模式时滞后导致估算失真
        w, _h, _x, _y = self._parse_run_geometry()
        width = max(200, w)
        content = panel.content_height_for_minimal(row_count, width)
        return max(48, content + 2)

    def _update_minimal_rows_from_height(self, height: int) -> None:
        if not self._run_minimal or self._split_panel is None:
            return
        single = self._estimate_minimal_window_height(1)
        triple = self._estimate_minimal_window_height(3)
        rows = 3 if height >= (single + triple) // 2 else 1
        if rows == self._run_minimal_rows:
            return
        self._run_minimal_rows = rows
        self._split_panel.set_minimal_rows(rows)
        self._ensure_minimal_content_width()

    def _snap_minimal_geometry(self, *, force_rows: int | None = None) -> None:
        """把极简窗口高度贴到 1 行或 3 行内容，去掉大块空白。

        force_rows: 进入极简时强制 1 行；用户拖拽松手时不传，按当前高度推断。
        """
        if not self._run_minimal or self._run_maximized:
            return
        w, h, x, y = self._parse_run_geometry()
        single = self._estimate_minimal_window_height(1)
        triple = self._estimate_minimal_window_height(3)
        if force_rows is not None:
            rows = 3 if force_rows >= 2 else 1
        else:
            # 绝不能因「残留的超高窗口」永久卡在巨大空白：超过三行阈值即强制回贴
            if h > triple + 48:
                rows = self._run_minimal_rows if self._run_minimal_rows in {1, 3} else 1
            else:
                rows = 3 if h >= (single + triple) // 2 else 1
        target = triple if rows == 3 else single
        self._run_minimal_rows = rows
        if self._split_panel is not None:
            self._split_panel.set_minimal_rows(rows)
        self.root.minsize(280, single)
        # 始终写高度，避免残留超高 geometry
        new_w = max(280, w)
        if new_w != w or abs(h - target) > 1:
            self.root.geometry(f"{new_w}x{target}+{x}+{y}")
            self.root.update_idletasks()
        self._ensure_minimal_content_width(clamp_height=target)
        self._run_geometry_minimal = self.root.geometry()

    def _ensure_minimal_content_width(self, *, clamp_height: int | None = None) -> None:
        """极简模式：节点名变化导致不够宽时自动扩宽；高度可夹到内容高度。"""
        if not self._run_minimal or self._run_maximized or self._split_panel is None:
            return
        try:
            screen_w = int(self.root.winfo_screenwidth())
        except tk.TclError:
            screen_w = 1920
        max_w = max(320, screen_w - 16)
        needed = self._split_panel.preferred_width_for_minimal(min_width=280, max_width=max_w)
        w, h, x, y = self._parse_run_geometry()
        target_h = clamp_height if clamp_height is not None else h
        if clamp_height is None:
            # 扩宽时若高度已离谱，一并压回当前行数对应高度
            single = self._estimate_minimal_window_height(1)
            triple = self._estimate_minimal_window_height(3)
            max_content = triple if self._run_minimal_rows >= 3 else single
            if h > max_content + 48:
                target_h = max_content
        if needed <= w and target_h == h:
            return
        new_w = max(w, needed)
        new_x = x
        if new_x + new_w > screen_w:
            new_x = max(0, screen_w - new_w)
        self.root.geometry(f"{new_w}x{int(target_h)}+{new_x}+{y}")
        self.root.update_idletasks()
        self._run_geometry_minimal = self.root.geometry()
        self._split_panel.redraw(preserve_scroll=True)

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
        # 与宿主同色，避免底角露出浅色块/白线
        try:
            grip_bg = str(outer.cget("bg"))
        except tk.TclError:
            grip_bg = WINDOW_EDGE
        for edge, cursor, place_kw in specs:
            grip = tk.Frame(outer, bg=grip_bg, cursor=cursor, borderwidth=0, highlightthickness=0)
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

    def attach_single_instance_activation(self, event_handle: int) -> None:
        """第二个实例启动 → 把它请求的「显示窗口」落到本实例（含托盘恢复）。

        工作线程只往队列里塞信号，Tk 相关操作全部在主线程泵里执行。
        """
        if not event_handle:
            return
        import queue

        signals: "queue.Queue[bool]" = queue.Queue()

        def _drain() -> None:
            try:
                signals.get_nowait()
            except queue.Empty:
                pass
            else:
                try:
                    self._restore_from_tray()
                except tk.TclError:
                    pass
            try:
                self.root.after(300, _drain)
            except tk.TclError:
                pass

        start_activation_watcher(event_handle, lambda: signals.put(True))
        self.root.after(300, _drain)

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
        # 滚动条自带拖拽语义，必须先于文本判断跳过，否则拖滚动条会拖整个窗口
        if str(widget.winfo_class()) in _INTERACTION_EXEMPT_CLASSES:
            return
        skip = {
            "极简",
            "Minimal",
            "─",
            "□",
            "×",
            "❐",
            "保存并关闭",
            "Save & Close",
            "存路线",
            "Save route",
            "返回",
            "返回路线选择",
            "Back",
            "Back to Routes",
            "撤销重置",
            "Undo Reset",
            "节点/幕",
            "Node/Act",
            "切到幕",
            "切到节点",
            "Act view",
            "Node view",
            "节点",
            "Node",
            "幕",
            "Act",
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
            if child_class in _INTERACTION_EXEMPT_CLASSES:
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
            panel.pack(side=tk.BOTTOM, fill=tk.X, padx=6, pady=(2, 4))
        if nodes is not None:
            nodes.pack(fill=tk.BOTH, expand=True, padx=6, pady=(4, 2))

    def _show_main(self) -> None:
        self.engine.stop_watching()
        self._set_click_through(False)
        self._click_through = False
        self._unregister_global_hotkeys()
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
        # 版本号常驻可见（选路线页标题栏），方便用户报 Bug 时直接报版本
        ctk.CTkLabel(
            brand,
            text=VERSION_LABEL,
            text_color=GOLD_FG,
            font=("Microsoft YaHei", 15, "bold"),
        ).pack(side=tk.LEFT, padx=(10, 0))
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
        # minwidth 不要过大，否则窄布局会强制出现横向滚动条
        self._route_tree.column("#0", stretch=True, minwidth=80, width=200)
        self._route_vscroll = ttk.Scrollbar(
            tree_host, orient=tk.VERTICAL, command=self._route_tree.yview, style="Route.Vertical.TScrollbar"
        )
        self._route_hscroll = ttk.Scrollbar(
            tree_host, orient=tk.HORIZONTAL, command=self._route_tree.xview, style="Route.Horizontal.TScrollbar"
        )
        self._route_tree.configure(
            yscrollcommand=lambda first, last: self._autohide_tree_scroll("y", first, last),
            xscrollcommand=lambda first, last: self._autohide_tree_scroll("x", first, last),
        )
        self._route_tree.grid(row=0, column=0, sticky="nsew")
        # 默认不放滚动条，内容超出时再 grid
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
        # 空白路线分两个游戏：走哪条由用户点的那颗按钮决定，不看设置里的当前游戏
        for game_id, key in BLANK_ROUTE_ENTRIES:
            self._btn(
                right,
                self._t(key),
                lambda g=game_id: self._on_free_run(g),
                variant="secondary",
                width=16,
            ).pack(anchor="w", fill=tk.X, pady=(6, 0))

        # 选路线页底部常驻版本号
        ctk.CTkLabel(
            right,
            text=APP_VERSION_LINE,
            text_color=MUTED_FG,
            font=FONT_FOOT,
            anchor="w",
        ).pack(anchor="w", pady=(16, 0))

        self._refresh_route_list()

    def _route_game_group(self, route: ReferenceRoute) -> str:
        # 只认路线自身的 game_id，不用当前设置游戏去归类，避免串组
        game_id = str(route.game_id or "").strip().lower()
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

    def _autohide_tree_scroll(self, axis: str, first: str, last: str) -> None:
        """内容未超出时隐藏路线列表滚动条。"""
        bar = self._route_vscroll if axis == "y" else self._route_hscroll
        if bar is None:
            return
        try:
            bar.set(first, last)
        except tk.TclError:
            return
        need = float(first) > 0.001 or float(last) < 0.999
        if need:
            if axis == "y":
                bar.grid(row=0, column=1, sticky="ns")
            else:
                bar.grid(row=1, column=0, sticky="ew")
        else:
            bar.grid_remove()

    def _on_route_tree_resize(self, event: tk.Event) -> None:
        if self._route_tree is None or event.widget is not self._route_tree:
            return
        # 列宽跟随可视区域，避免无谓的横向滚动条
        width = max(80, event.width - 4)
        self._route_tree.column("#0", width=width, minwidth=80)

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
        self.root.after_idle(self._sync_route_tree_scrollbars)

    def _sync_route_tree_scrollbars(self) -> None:
        if self._route_tree is None:
            return
        try:
            y0, y1 = self._route_tree.yview()
            x0, x1 = self._route_tree.xview()
        except tk.TclError:
            return
        self._autohide_tree_scroll("y", str(y0), str(y1))
        self._autohide_tree_scroll("x", str(x0), str(x1))

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
        self._apply_window_icon(dlg)
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
        # 按路线自己的游戏切过去：设置里默认 poe2，跑 PoE1 路线时
        # 不切会把 10 幕判成 4 幕、第一幕种子起点也种成 PoE2 的。
        route_game = str(getattr(route, "game_id", "") or "").strip().lower()
        if route_game in {"poe1", "poe2"} and not self._switch_run_game(route_game):
            return
        self.engine.begin_new_run(route)
        test_log.write("USER", "新 Run", route_id=route.route_id, route_name=route.name)
        self._show_run()

    def _on_free_run(self, game_id: str = "") -> None:
        """不选参考路线：节点名与时间全部按实际进图记录，用来生成新路线。

        两个入口各自钉死游戏（PoE1 / PoE2）：点哪颗就按哪个游戏查区、判幕，
        不依赖设置里的「当前游戏」，否则 PoE1 玩家点了 PoE2 空白路线就会整轮错判。
        """
        target = str(game_id or "").strip().lower()
        if target in {"poe1", "poe2"} and not self._switch_run_game(target):
            return
        self.engine.begin_new_run(None)
        test_log.write("USER", "自由路线 Run", game=target or self.config.game)
        self._show_run()

    def _switch_run_game(self, game_id: str) -> bool:
        """把「当前游戏」切到 game_id（含 Client.txt 路径）；缺 Client.txt 时明确拒绝。"""
        from pathlib import Path

        if str(self.config.game or "").strip().lower() == game_id:
            return True
        saved = load_client_path_for_game(game_id)
        path = Path(saved) if saved else None
        if path is None or not path.is_file():
            # 不拿「当前游戏的 Client.txt」凑：PoE2 的日志按 PoE1 判幕会整轮错。
            # 宁可让用户先去设置里选这条游戏的日志。
            messagebox.showinfo(
                self._t("need_client_for_game_title"),
                self._t("need_client_for_game").format(game=self._game_title(game_id)),
                parent=self.root,
            )
            return False
        save_routelens_setup(str(path), game_id)
        self.config = load_routelens_config()
        self.engine.config = self.config
        # 监听器绑的是「旧游戏的 Client.txt」：不先停掉，切游戏后会一直读错日志
        self.engine.stop_watching()
        self.engine.reload_game_profile()
        return True

    @staticmethod
    def _game_title(game_id: str) -> str:
        return "Path of Exile 2" if game_id == "poe2" else "Path of Exile"

    def _on_continue(self) -> None:
        route = self._route_by_id(self._selected_route_id)
        if route is None:
            return
        saved = self.engine.get_saved_run_for_route(route.route_id)
        if saved is None:
            messagebox.showinfo("提示", self._t("no_continue"), parent=self.root)
            return
        # 续跑同样按路线的游戏切过去；旧存档没有 run.game_id 时用路线自己的。
        resume_game = str(
            getattr(saved, "game_id", "") or getattr(route, "game_id", "") or ""
        ).strip().lower()
        if resume_game in {"poe1", "poe2"} and not self._switch_run_game(resume_game):
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
            self._timer_label.configure(font=("Consolas", max(14, int(24 * scale)), "bold"))
        if self._total_delta_label is not None:
            self._total_delta_label.configure(font=("Consolas", max(12, int(18 * scale)), "bold"))
        # 窗口变窄 → 热键条必须重排，否则 Shift+S 会被窗口右缘裁掉
        self._schedule_hotkey_relayout()
    def _show_run(self) -> None:
        self._clear_container()
        if self._run_geometry_normal:
            self.root.geometry(self._run_geometry_normal)
        else:
            self.root.geometry("360x480")
        self.root.minsize(260, 160)
        self.root.attributes("-topmost", True)
        self._set_run_borderless(True)
        self._run_minimal = False
        self._run_maximized = False
        self._run_geometry_before_max = None

        # 1px 外边框用原生 Frame，避免 CTk 画布抗锯齿在边缘打出浅色毛边
        chrome = tk.Frame(self.container, bg=WINDOW_EDGE, bd=0, highlightthickness=0)
        chrome.pack(fill=tk.BOTH, expand=True)
        self._run_chrome = chrome

        outer = tk.Frame(chrome, bg=BG, bd=0, highlightthickness=0)
        outer.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        outer.bind("<Configure>", self._on_run_resize)
        self._run_frame = outer
        self._current_label = None

        # 自定义顶栏：只放窗名与「极简」；其余动作统一收进底栏动作行，不再上下各一半
        titlebar = ctk.CTkFrame(outer, fg_color="#1a1a1a", corner_radius=0, height=26)
        titlebar.pack_propagate(False)
        self._run_titlebar = titlebar
        ctk.CTkLabel(
            titlebar,
            text=APP_DISPLAY,
            text_color=MUTED_FG,
            font=FONT_TITLEBAR,
        ).pack(side=tk.LEFT, padx=(8, 0))

        def title_btn(
            text: str, command, *, width: int = 36, side: str = tk.RIGHT
        ) -> ctk.CTkLabel:
            lbl = ctk.CTkLabel(
                titlebar,
                text=text,
                text_color=MUTED_FG,
                font=("Consolas", 14) if text in {"─", "□", "×", "❐"} else FONT_TITLEBAR,
                width=width,
                cursor="hand2",
            )
            lbl.pack(side=side, padx=1, pady=1)
            lbl.bind("<Button-1>", lambda _e, c=command: c())
            return lbl

        # 窗口控制固定在右上角（关窗 / 最小化只能靠它们，不挪到底栏）
        title_btn("×", self._on_close, width=28)
        self._run_max_btn = title_btn("□", self._run_toggle_maximize, width=28)
        title_btn("─", self._run_minimize, width=28)
        # 顶栏唯一的动作按钮：极简
        title_btn(self._t("minimal"), self._enter_run_minimal, width=48, side=tk.LEFT)

        # 顶栏底部分隔线
        self._run_title_sep = tk.Frame(outer, bg=BORDER, height=1, bd=0, highlightthickness=0)

        # 下方控制面板（固定在底，尽量矮）
        panel = ctk.CTkFrame(outer, fg_color=BG, corner_radius=0)
        self._run_panel = panel
        self._run_bar = None
        self._route_name_label = None

        foot = ctk.CTkFrame(panel, fg_color=BG, corner_radius=0)
        foot.pack(side=tk.BOTTOM, fill=tk.X, padx=2, pady=(0, 2))
        self._run_foot = foot

        # 底栏统一成两行：
        #   下行 = 动作行（左：返回 / 节点-幕；右：撤销重置 / 存路线 / 保存并关闭）
        #   上行 = 快捷键提示（可点击，按宽度自动折行）
        # 先 pack 下行（BOTTOM），再 pack 上行，避免动作按钮被提示条挤到窗口外。
        action_row = ctk.CTkFrame(foot, fg_color=BG, corner_radius=0)
        action_row.pack(side=tk.BOTTOM, fill=tk.X)
        self._run_action_row = action_row

        # 右侧主操作：从右往左依次 pack（保存并关闭最右）
        save_lbl = ctk.CTkLabel(
            action_row,
            text=self._t("save_close"),
            text_color=TEXT_FG,
            font=FONT_FOOT,
            cursor="hand2",
        )
        save_lbl.pack(side=tk.RIGHT, padx=(0, 2))
        save_lbl.bind("<Button-1>", lambda _e: self._save_and_close_run())
        self._save_route_label = ctk.CTkLabel(
            action_row,
            text=self._t("save_as_route"),
            text_color=GOLD_FG,
            font=FONT_FOOT,
            cursor="hand2",
        )
        self._save_route_label.pack(side=tk.RIGHT, padx=(0, 12))
        self._save_route_label.bind("<Button-1>", lambda _e: self._save_current_as_route())
        self._undo_reset_label = ctk.CTkLabel(
            action_row,
            text=self._t("undo_reset"),
            text_color=GOLD_FG,
            font=FONT_FOOT,
            cursor="hand2",
        )
        self._undo_reset_label.pack(side=tk.RIGHT, padx=(0, 12))
        self._undo_reset_label.bind("<Button-1>", lambda _e: self._undo_reset())
        self._update_undo_reset_button()

        # 左侧导航：返回 → 节点/幕（与右侧操作分组，不再散落在标题栏）
        back_lbl = ctk.CTkLabel(
            action_row,
            text=self._t("back_short"),
            text_color=MUTED_FG,
            font=FONT_FOOT,
            cursor="hand2",
        )
        back_lbl.pack(side=tk.LEFT, padx=(2, 14))
        back_lbl.bind("<Button-1>", lambda _e: self._leave_run())
        self._view_toggle_label = ctk.CTkLabel(
            action_row,
            text=self._t("view_toggle"),
            text_color=MUTED_FG,
            font=FONT_FOOT,
            cursor="hand2",
        )
        self._view_toggle_label.pack(side=tk.LEFT)
        self._view_toggle_label.bind("<Button-1>", lambda _e: self._toggle_act_view())
        self._update_view_toggle_label()

        self._build_clickable_hotkey_bar(foot)

        timer_row = ctk.CTkFrame(panel, fg_color=BG, corner_radius=0)
        timer_row.pack(side=tk.TOP, fill=tk.X, pady=(0, 0))
        self._timer_label = ctk.CTkLabel(
            timer_row,
            textvariable=self.elapsed_var,
            text_color=TEXT_FG,
            font=FONT_TIMER,
        )
        self._timer_label.pack(side=tk.LEFT, padx=(4, 8))
        self._total_delta_label = ctk.CTkLabel(
            timer_row,
            textvariable=self.total_delta_var,
            text_color=MUTED_FG,
            font=("Consolas", 18, "bold"),
        )
        self._total_delta_label.pack(side=tk.LEFT, padx=(0, 4))
        self._current_label = ctk.CTkLabel(
            timer_row,
            textvariable=self.current_var,
            text_color=GOLD_FG,
            font=FONT_UI,
            anchor="e",
            cursor="hand2",
        )
        self._current_label.pack(side=tk.RIGHT, padx=(4, 4))
        self._current_label.bind("<Button-1>", lambda _e: self._invoke_hotkey_digit("0"))

        # 上方节点容器：直角细边，避免圆角 CTk 边框发白/发灰
        nodes_host = ctk.CTkFrame(
            outer,
            fg_color=PANEL_BG,
            corner_radius=0,
            border_width=1,
            border_color=BORDER,
        )
        self._run_nodes_host = nodes_host
        list_body = ctk.CTkFrame(nodes_host, fg_color=PANEL_BG, corner_radius=0)
        list_body.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        self._run_list_body = list_body
        self._split_panel = SplitPanel(list_body)
        # 显式竖条，避免只能靠滚轮且滚到底误以为没有后续节点
        vbar = ttk.Scrollbar(list_body, orient=tk.VERTICAL, command=self._split_panel.yview)
        self._run_vbar = vbar
        self._split_panel.configure(yscrollcommand=vbar.set)
        self._split_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
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
            waiting=self._t("waiting_area"),
        )

        self._pack_run_normal_layout()
        self._bind_run_drag(outer)
        self._install_run_grips_if_needed()
        self._install_run_hotkeys(outer)
        self._split_page = 0
        self._refresh_run_view(self.engine.active_run)
        self._register_global_hotkeys()
        self.root.after_idle(self._focus_run_surface)

    def _enter_run_minimal(self) -> None:
        if self._run_minimal or self._split_panel is None:
            return
        if not self._run_maximized:
            self._run_geometry_normal = self.root.geometry()
        self._run_minimal = True
        self._run_minimal_rows = 1
        for widget in (self._run_titlebar, getattr(self, "_run_title_sep", None), self._run_panel):
            if widget is not None:
                widget.pack_forget()
        self._clear_run_resize_grips()
        # 极简藏滚动条、贴边
        if self._run_vbar is not None:
            self._run_vbar.pack_forget()
            self._split_panel.configure(yscrollcommand="")
        if self._run_list_body is not None:
            self._run_list_body.pack_configure(padx=0, pady=0)
        if self._run_nodes_host is not None:
            self._run_nodes_host.configure(border_width=0)
            self._run_nodes_host.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        self._split_panel.set_minimal(True)
        self._split_panel.set_minimal_rows(1)
        if not self._run_maximized:
            self.root.update_idletasks()
            single = self._estimate_minimal_window_height(1)
            self.root.minsize(280, single)
            # 只恢复极简的位置/宽度，高度一律按 1 行内容贴合（禁止带回超高空白窗）
            if self._run_geometry_minimal:
                mw, _mh, mx, my = self._parse_geometry_string(self._run_geometry_minimal)
                self.root.geometry(f"{max(280, mw)}x{single}+{mx}+{my}")
            else:
                self.root.geometry(f"360x{single}+80+80")
            self.root.update_idletasks()
        self._install_run_grips_if_needed()
        self._refresh_run_view(self.engine.active_run)
        self.root.after_idle(lambda: self._snap_minimal_geometry(force_rows=1))
        self.root.after_idle(self._focus_run_surface)

    def _exit_run_minimal(self) -> None:
        if not self._run_minimal or self._run_frame is None or self._split_panel is None:
            return
        if self._dragging:
            return
        if not self._run_maximized:
            self._run_geometry_minimal = self.root.geometry()
        self._run_minimal = False
        self._run_minimal_rows = 1
        self._split_panel.set_minimal(False)
        if self._run_nodes_host is not None:
            self._run_nodes_host.configure(border_width=1, border_color=BORDER)
            self._run_nodes_host.pack_forget()
        if self._run_list_body is not None:
            self._run_list_body.pack_configure(padx=1, pady=1)
        if self._run_vbar is not None:
            self._split_panel.configure(yscrollcommand=self._run_vbar.set)
            self._run_vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._pack_run_normal_layout()
        self._install_run_grips_if_needed()
        self.root.minsize(260, 160)
        if not self._run_maximized:
            if self._run_geometry_normal:
                self.root.geometry(self._run_geometry_normal)
            else:
                self.root.geometry("360x480")
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
        self._apply_window_icon(popup)
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

    def _save_current_as_route(self) -> None:
        """把本次实际跑出的节点与时间保存成一条新参考路线。"""
        if not self.engine.has_active_run:
            return
        self.engine._sync_elapsed()
        run = self.engine.active_run
        assert run is not None
        completed = [n for n in run.nodes if n.visited and n.name]
        if not completed:
            messagebox.showinfo("提示", "还没有跑出任何节点。", parent=self.root)
            return
        default_name = run.reference_route_name or datetime.now().strftime("%m-%d %H:%M")
        name = self._ask_route_name("保存为新路线", default_name)
        if not name:
            return
        route = self.engine.save_run_as_reference(name)
        test_log.write(
            "USER", "保存为新路线", name=name, route_id=route.route_id, nodes=len(route.nodes)
        )
        messagebox.showinfo(
            "已保存",
            f"已保存为新路线「{name}」（{len(route.nodes)} 节点）。",
            parent=self.root,
        )

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

        def _sync_scrollbars(_first: str = "0", _last: str = "1") -> None:
            # 用 bbox 与可视尺寸判断，避免未超出仍占滚动条
            bbox = canvas.bbox("all")
            if not bbox:
                vscroll.grid_remove()
                hscroll.grid_remove()
                return
            cw = max(1, canvas.winfo_width())
            ch = max(1, canvas.winfo_height())
            content_w = max(1, bbox[2] - bbox[0])
            content_h = max(1, bbox[3] - bbox[1])
            if content_h > ch + 1:
                vscroll.grid(row=0, column=1, sticky="ns")
            else:
                vscroll.grid_remove()
                canvas.yview_moveto(0)
            if content_w > cw + 1:
                hscroll.grid(row=1, column=0, sticky="ew")
            else:
                hscroll.grid_remove()
                canvas.xview_moveto(0)

        def _on_inner_configure(_event: object = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            _sync_scrollbars()

        def _on_canvas_configure(event: tk.Event) -> None:
            canvas.itemconfigure(window_id, width=event.width)
            _sync_scrollbars()

        def _yset(first: str, last: str) -> None:
            vscroll.set(first, last)
            _sync_scrollbars(first, last)

        def _xset(first: str, last: str) -> None:
            hscroll.set(first, last)
            _sync_scrollbars(first, last)

        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=_yset, xscrollcommand=_xset)

        canvas.grid(row=0, column=0, sticky="nsew")
        # 默认隐藏，超出时再显示

        def _on_mousewheel(event: tk.Event) -> None:
            # 仅当纵向可滚时响应
            first, last = canvas.yview()
            if float(first) <= 0.0 and float(last) >= 1.0:
                return
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
        self.root.title(APP_VERSION_LINE)
        # 主界面重建以刷新文案；Run 中则仅切语言，下次进入主界面生效
        if self._main_frame is not None:
            self._show_main()

    def _open_intro(self) -> None:
        dlg = ctk.CTkToplevel(self.root)
        self._apply_window_icon(dlg)
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
        self._apply_window_icon(win)
        win.title(f"{self._t('settings')} · {APP_DISPLAY} {VERSION_LABEL}")
        win.configure(fg_color=BG)
        win.transient(self.root)
        win.minsize(520, 360)
        win.geometry("580x400")

        shell = ctk.CTkFrame(win, fg_color=BG, corner_radius=0)
        shell.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        _canvas, frame = self._build_scrollable(shell)

        # 版本号：设置页顶部常驻显示
        version_block = ctk.CTkFrame(frame, fg_color=BG, corner_radius=0)
        version_block.pack(fill=tk.X, pady=(0, 16))
        ctk.CTkLabel(
            version_block,
            text=APP_DISPLAY,
            text_color=TEXT_FG,
            font=("Microsoft YaHei", 17, "bold"),
            anchor="w",
        ).pack(side=tk.LEFT)
        ctk.CTkLabel(
            version_block,
            text=VERSION_LABEL,
            text_color=GOLD_FG,
            font=("Microsoft YaHei", 15, "bold"),
            anchor="w",
        ).pack(side=tk.LEFT, padx=(10, 0))

        # 自动更新
        update_block = ctk.CTkFrame(frame, fg_color=BG, corner_radius=0)
        update_block.pack(fill=tk.X, pady=(0, 16))
        check_var = tk.BooleanVar(value=load_check_updates())

        def on_check_toggle() -> None:
            save_check_updates(bool(check_var.get()))

        ctk.CTkCheckBox(
            update_block,
            text=self._t("check_updates_toggle"),
            variable=check_var,
            command=on_check_toggle,
            font=FONT_UI_SM,
            text_color=TEXT_FG,
            fg_color=BTN_PRIMARY,
            hover_color=BTN_PRIMARY_HOVER,
        ).pack(anchor="w")
        self._btn(
            update_block,
            self._t("check_updates_btn"),
            lambda: self._check_updates(manual=True),
            variant="secondary",
        ).pack(anchor="w", pady=(8, 0))

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
            self._apply_window_icon(dlg)
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
            self._apply_window_icon(dlg)
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
        if self._global_hotkeys is not None:
            self._global_hotkeys.shutdown()
            self._global_hotkeys = None
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
            if self.engine.active_run and (
                self.engine.timer_running or self.engine.active_run.is_paused
            ):
                if tick % refresh_every == 0 or self._run_minimal:
                    self._refresh_run_view(self.engine.active_run)
                elif not self._run_minimal and tick % 2 == 0:
                    self._update_total_delta_display()
            elif self.engine.active_run and self._run_minimal:
                if tick % refresh_every == 0:
                    self._refresh_run_view(self.engine.active_run)
        self.root.after(50, self._tick_timer)

    def _refresh_run_view(self, run: ActiveRun | None) -> None:
        if run is None or self._split_panel is None:
            return

        name = run.reference_route_name or "自由路线"
        self.route_name_var.set(name)

        if self.engine.timer_running:
            self.current_var.set("")
        elif run.campaign_over:
            self.current_var.set(self._t("campaign_over"))
        else:
            self.current_var.set(self._t("press_0"))

        if self._act_view:
            rows, current_index = self._build_act_rows(run)
        else:
            rows, current_index = self._build_node_rows(run)

        # 全部节点进可滚动容器；极简模式只画表头+当前行（含总时间与累计差）
        total_text = self.elapsed_var.get()
        total_delta_text = self._update_total_delta_display()
        if self._run_minimal:
            self._split_panel.set_rows(
                rows,
                current_index,
                auto_scroll=False,
                total_text=total_text,
                total_delta_text=total_delta_text,
                redraw=False,
            )
            self._ensure_minimal_content_width()
            self._split_panel.redraw()
        else:
            self._split_panel.set_rows(
                rows,
                current_index,
                auto_scroll=False,
                total_text=total_text,
                total_delta_text=total_delta_text,
            )
        self._split_page_var.set("")

    def _build_node_rows(self, run: ActiveRun) -> tuple[list[dict], int]:
        """节点视图：逐区域一行。

        取数口径（RunNode 唯一不变量）：``seconds is not None`` ⇔ 本次到过。
        """
        rows: list[dict] = []
        for index, node in enumerate(run.nodes):
            ref_sec = self.engine.reference_seconds_at(index)
            ref_text = format_duration(ref_sec) if ref_sec is not None else ""

            if node.skipped:
                # 本次没去过这个区域（手动跳过 / 跳段没跑到）
                status = "skipped"
                time_text = "—"
                delta_text = ""
            elif node.visited:
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
        return rows, run.current_index

    def _resolve_run_game_id(self, run: ActiveRun) -> str:
        """幕视图用的游戏：先看运行记录，再用 area id 形态兜底。

        area id 是最硬的证据：``1_1_1`` = PoE1，``G1_1`` = PoE2。
        设置里的「当前游戏」不能作为判定依据 —— 默认是 poe2，
        跑 PoE1 路线会把 10 幕显示成 4 幕。
        """
        recorded = str(getattr(run, "game_id", "") or "").strip().lower()
        if recorded in ("poe1", "poe2"):
            return recorded
        for node in run.nodes:
            inferred = infer_game_from_area_id(getattr(node, "area_id", "") or "")
            if inferred:
                return inferred
        return str(self.engine.config.game or "").strip().lower()

    def _build_act_rows(self, run: ActiveRun) -> tuple[list[dict], int]:
        """幕视图：逐幕一行（幕内所有区域用时求和）。

        幕归属由 area id 判定（见 :mod:`routelens.act_map`），
        因此不同玩家的节点顺序 / 支线不同都不影响分幕。
        """
        game_id = self._resolve_run_game_id(run)

        # 参考路线的分幕用时（用于「参考」列）
        reference = self.engine.get_reference_route()
        ref_acts: dict[int, float] = {}
        ref_interlude = 0.0
        ref_endgame = 0.0
        if reference is not None:
            for act_split in build_act_timing(
                [
                    {
                        "area": node.name,
                        "area_id": node.area_id,
                        "segment_seconds": node.seconds or 0.0,
                    }
                    for node in reference.nodes
                ],
                game_id,
            ).acts:
                if act_split.act is not None:
                    ref_acts[act_split.act] = ref_acts.get(act_split.act, 0.0) + act_split.segment_seconds
                elif act_split.is_interlude:
                    ref_interlude += act_split.segment_seconds
                elif act_split.is_endgame:
                    ref_endgame += act_split.segment_seconds

        # 本次运行的节点（已完成的用已计时；当前的用实时段）
        #
        # 取数口径（RunNode 唯一不变量）：``seconds is not None`` ⇔ 本次到过。
        # 不再用「completed and not skipped」判断 —— 那个组合允许
        # 「有 87 秒用时 + skipped」这种自相矛盾状态，正是 2026-10-28
        # 那 28.3 分钟蒸发的根因。
        run_splits: list[dict] = []
        for index, node in enumerate(run.nodes):
            # 还没跑到的参考节点不能进幕计时：否则 Act 5..10 会显示 00:00
            # 并算作「已完成」，幕视图看起来像整条路线都跑完了。
            if not node.visited and index != run.current_index:
                continue
            seconds = node.seconds or 0.0
            if index == run.current_index and not node.visited:
                if self.engine.timer_running or run.is_paused:
                    seconds = self.engine.current_segment_seconds()
            run_splits.append(
                {
                    "area": node.name,
                    "area_id": node.area_id,
                    "segment_seconds": seconds,
                }
            )

        timing = build_act_timing(run_splits, game_id)
        # 章节骨架跟游戏内一致：
        #   PoE1 = 第1..10章
        #   PoE2 = 第1..4章 + 間歇 + 終局（缺間歇会把末段错算进第4章）
        slots = chapter_slots(game_id)
        if not slots:
            slots = [("act", str(n)) for n in range(1, act_count(game_id) + 1)]
        by_act = {a.act: a for a in timing.acts if a.act is not None}
        interlude_split = next((a for a in timing.acts if a.is_interlude), None)
        endgame_split = next((a for a in timing.acts if a.is_endgame), None)
        current_act = timing.current_act
        current_chapter = timing.current_chapter
        act_labels = expected_act_labels(game_id, "en" if self.ui_lang == "en" else "zh_tw")
        # 間歇 / 終局的标签取骨架最后两项（PoE2 才有間歇）
        interlude_label = (
            self._t("act_interlude")
            if any(kind == "interlude" for kind, _ in slots)
            else "间歇"
        )
        endgame_label = self._t("act_endgame")

        rows: list[dict] = []
        current_index = 0
        for slot_index, (kind, key) in enumerate(slots):
            if kind == "act":
                act_number = int(key)
                act_split = by_act.get(act_number)
                ref_sec = ref_acts.get(act_number)
                is_current = act_number == current_act and current_chapter == "act"
                label = (
                    act_labels[slot_index]
                    if slot_index < len(act_labels)
                    else f"Act {act_number}"
                )
            elif kind == "interlude":
                act_split = interlude_split
                ref_sec = ref_interlude if reference is not None else None
                is_current = current_chapter == "interlude"
                label = interlude_label
            else:  # endgame
                act_split = endgame_split
                ref_sec = ref_endgame if reference is not None else None
                is_current = current_chapter == "endgame"
                label = endgame_label

            if act_split is None:
                # 未到达的章节：占位但不计时
                rows.append(
                    {
                        "name": label,
                        "time": "",
                        "ref": format_duration(ref_sec) if ref_sec else "",
                        "delta": "",
                        "status": "current" if is_current else "pending",
                    }
                )
                if is_current:
                    current_index = len(rows) - 1
                continue

            rows.append(
                {
                    "name": label,
                    "time": format_duration(act_split.segment_seconds),
                    "ref": format_duration(ref_sec) if ref_sec else "",
                    "delta": format_delta(act_split.segment_seconds, ref_sec),
                    "status": "current" if is_current else "completed",
                }
            )
            if is_current:
                current_index = len(rows) - 1

        return rows, current_index

    def _toggle_act_view(self) -> None:
        """切换节点视图 / 幕视图。"""
        self._act_view = not self._act_view
        self._update_view_toggle_label()
        self._refresh_run_view(self.engine.active_run)

    def _update_view_toggle_label(self) -> None:
        if self._view_toggle_label is None:
            return
        text = self._t("view_switch_node") if self._act_view else self._t("view_switch_act")
        try:
            self._view_toggle_label.configure(text=text)
        except tk.TclError:  # pragma: no cover - 控件已销毁
            pass

    def _update_total_delta_display(self) -> str:
        """刷新普通模式计时器下的累计差；返回文案供极简模式同色显示。"""
        delta_sec = self.engine.comparison_delta_seconds()
        if delta_sec is None:
            text = ""
            color = MUTED_FG
        else:
            text = format_delta(delta_sec, 0.0)
            if abs(delta_sec) < 0.005:
                text = "+00:00"
                color = MUTED_FG
            elif delta_sec < 0:
                color = GREEN_FG
            else:
                color = RED_FG
        self.total_delta_var.set("" if self._run_minimal else text)
        if self._total_delta_label is not None and not self._run_minimal:
            self._total_delta_label.configure(text_color=color)
        return text
