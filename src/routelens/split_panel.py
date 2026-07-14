from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable
from typing import Literal

RowStatus = Literal["completed", "current", "pending", "skipped"]

BG = "#121212"
LIST_BG = "#1a1a1a"
GOLD = "#f0c040"
GREEN = "#7fd47f"
RED = "#ff6b6b"
GRAY = "#666666"
HEADER_FG = "#d0d0d0"
WHITE = "#f0f0f0"
CURRENT_BG = "#1a1408"
HEADER_LINE = "#2a2a2a"


class SplitPanel(tk.Canvas):
    """LiveSplit 风格分段列表：表头冻结；列右对齐 + 字号随宽度自适应，避免裁切。"""

    BASE_WIDTH = 320

    def __init__(self, parent: tk.Misc, **kwargs) -> None:
        super().__init__(parent, bg=LIST_BG, highlightthickness=0, bd=0, **kwargs)
        self._rows: list[dict] = []
        self._current_index = 0
        self._scale = 1.0
        self._row_height = 20
        self._auto_scroll = False
        self._minimal = False
        self._total_text = ""
        self._headers = {
            "node": "节点",
            "time": "用时",
            "ref": "参考",
            "delta": "差值",
            "total": "总时间",
        }
        self._menu_exit_minimal = "退出极简模式"
        self._menu_close = "关闭"
        self._on_exit_minimal: Callable[[], None] | None = None
        self._on_close_app: Callable[[], None] | None = None
        self.bind("<Configure>", self._on_configure)
        self.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Double-Button-1>", self._on_double_click)
        self.bind("<Button-3>", self._on_right_click)

    def set_exit_minimal_callback(self, callback: Callable[[], None] | None) -> None:
        self._on_exit_minimal = callback

    def set_close_app_callback(self, callback: Callable[[], None] | None) -> None:
        self._on_close_app = callback

    def set_ui_texts(
        self,
        *,
        headers: dict[str, str] | None = None,
        exit_minimal: str | None = None,
        close_app: str | None = None,
    ) -> None:
        """表头与右键菜单文案（节点名等内容仍由外部数据决定，不翻译）。"""
        if headers:
            self._headers.update(headers)
        if exit_minimal is not None:
            self._menu_exit_minimal = exit_minimal
        if close_app is not None:
            self._menu_close = close_app
        self._redraw(preserve_scroll=True)

    @property
    def minimal(self) -> bool:
        return self._minimal

    def set_minimal(self, enabled: bool) -> None:
        if self._minimal == enabled:
            return
        self._minimal = enabled
        self._redraw()

    def set_rows(
        self,
        rows: list[dict],
        current_index: int,
        *,
        auto_scroll: bool = False,
        total_text: str = "",
    ) -> None:
        self._rows = rows
        self._current_index = current_index
        self._auto_scroll = auto_scroll
        self._total_text = total_text
        self._redraw()

    def _on_double_click(self, _event: tk.Event) -> None:
        if self._minimal and self._on_exit_minimal is not None:
            self._on_exit_minimal()

    def _on_right_click(self, event: tk.Event) -> None:
        if not self._minimal:
            return
        menu = tk.Menu(self, tearoff=0, bg=LIST_BG, fg=WHITE, activebackground="#2a2a2a", activeforeground=WHITE)
        if self._on_exit_minimal is not None:
            menu.add_command(label=self._menu_exit_minimal, command=self._on_exit_minimal)
        if self._on_close_app is not None:
            menu.add_command(label=self._menu_close, command=self._on_close_app)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _on_configure(self, _event: object = None) -> None:
        self._update_scale(max(1, self.winfo_width()))
        self._redraw(preserve_scroll=True)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if self._minimal:
            return
        self.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self._draw_frozen_header()

    def _update_scale(self, width: int) -> None:
        """按窗口宽度缩放，并进一步缩小直到数值列不被裁切。"""
        scale = max(0.55, min(1.35, width / self.BASE_WIDTH))
        # 预留当前行 bump=2 的最宽数值，找不到合适字号则继续缩小
        for _ in range(12):
            self._scale = scale
            self._row_height = max(14, int(20 * scale))
            name_w, _time_r, _ref_r, _delta_r, _total_r = self._column_layout(width)
            if name_w >= 36 or scale <= 0.55:
                break
            scale = max(0.55, scale * 0.92)

    def _font(self, base: int, *, bold: bool = False, bump: int = 0) -> tuple[str, int, str]:
        size = max(7, int(base * self._scale) + bump)
        style = "bold" if bold else "normal"
        return ("Consolas", size, style)

    def _name_font(self, *, bump: int = 0) -> tuple[str, int, str]:
        size = max(7, int(11 * self._scale) + bump)
        return ("Microsoft YaHei", size, "normal")

    def _header_font(self) -> tuple[str, int, str]:
        size = max(7, int(11 * self._scale))
        return ("Microsoft YaHei", size, "normal")

    def _header_height(self) -> int:
        return int(6 * self._scale) + self._row_height

    def _truncate(self, text: str, max_px: int, *, font: tuple[str, int, str] | None = None) -> str:
        if not text:
            return ""
        font = font or self._name_font()
        if max_px <= 8:
            return "…"
        if self._text_width(text, font) <= max_px:
            return text
        trimmed = text
        while len(trimmed) > 1 and self._text_width(trimmed + "…", font) > max_px:
            trimmed = trimmed[:-1]
        return trimmed + "…"

    def _text_width(self, text: str, font: tuple[str, int, str]) -> int:
        weight = "bold" if len(font) > 2 and font[2] == "bold" else "normal"
        measure_font = tkfont.Font(family=font[0], size=font[1], weight=weight)
        return measure_font.measure(text)

    def _max_cell_width(self, key: str, samples: list[str], *, bump: int) -> int:
        font = self._font(10, bump=bump)
        header_font = self._header_font()
        widths = [self._text_width(s, font) for s in samples if s]
        # 表头本身
        header_map = {
            "time": self._headers.get("time", "用时"),
            "ref": self._headers.get("ref", "参考"),
            "delta": self._headers.get("delta", "差值"),
            "total": self._headers.get("total", "总时间"),
        }
        widths.append(self._text_width(header_map.get(key, ""), header_font))
        # 兜底样例，避免空表时列宽为 0
        fallback = {"time": "00:00", "ref": "00:00", "delta": "+00:00", "total": "00:00.00"}
        widths.append(self._text_width(fallback.get(key, "00:00"), font))
        return max(widths) if widths else 40

    def _column_layout(self, width: int) -> tuple[int, int, int, int, int | None]:
        """返回 name_w 与 time/ref/delta(/total) 的右边界（右对齐绘制）。"""
        pad = 6
        gap = max(6, int(8 * self._scale))
        bump = 2  # 按当前行最大字号预留

        times = [str(r.get("time", "")) for r in self._rows]
        refs = [str(r.get("ref", "")) for r in self._rows]
        deltas = [str(r.get("delta", "")) for r in self._rows]
        time_w = self._max_cell_width("time", times, bump=bump)
        ref_w = self._max_cell_width("ref", refs, bump=bump)
        delta_w = self._max_cell_width("delta", deltas, bump=bump)

        right = width - pad
        if self._minimal:
            totals = [self._total_text] if self._total_text else []
            total_w = self._max_cell_width("total", totals, bump=bump)
            total_r = right
            delta_r = total_r - total_w - gap
            ref_r = delta_r - delta_w - gap
            time_r = ref_r - ref_w - gap
            name_w = max(24, time_r - time_w - gap - pad)
            return name_w, time_r, ref_r, delta_r, total_r

        delta_r = right
        ref_r = delta_r - delta_w - gap
        time_r = ref_r - ref_w - gap
        name_w = max(24, time_r - time_w - gap - pad)
        return name_w, time_r, ref_r, delta_r, None

    def _draw_row(
        self,
        *,
        y: int,
        width: int,
        name_w: int,
        time_r: int,
        ref_r: int,
        delta_r: int,
        total_r: int | None,
        row: dict,
        bump: int = 0,
        show_total: bool = False,
    ) -> int:
        status: RowStatus = row.get("status", "pending")
        time_text = str(row.get("time", ""))
        ref_text = str(row.get("ref", ""))
        delta_text = str(row.get("delta", ""))
        name_font = self._name_font(bump=bump)
        cell_font = self._font(10, bump=bump)
        name = self._truncate(str(row.get("name", "")), name_w - 4, font=name_font)
        row_h = self._row_height + (4 if bump else 0)

        if status == "current":
            self.create_rectangle(0, y - 2, width, y + row_h - 2, fill=CURRENT_BG, outline="", tags=("body",))
            name_color = GOLD
        elif status == "skipped":
            name_color = GRAY
        elif status == "completed":
            if delta_text.startswith("-"):
                name_color = GREEN
            elif delta_text.startswith("+"):
                name_color = RED
            else:
                name_color = WHITE
        else:
            name_color = GRAY

        self.create_text(8, y, anchor="nw", text=name, fill=name_color, font=name_font, tags=("body",))
        if time_text:
            self.create_text(
                time_r, y, anchor="ne", text=time_text, fill=name_color, font=cell_font, tags=("body",)
            )
        self.create_text(
            ref_r,
            y,
            anchor="ne",
            text=ref_text,
            fill=GRAY if status == "pending" else name_color,
            font=cell_font,
            tags=("body",),
        )
        if delta_text:
            d_color = GREEN if delta_text.startswith("-") else RED if delta_text.startswith("+") else WHITE
            self.create_text(
                delta_r, y, anchor="ne", text=delta_text, fill=d_color, font=cell_font, tags=("body",)
            )
        if show_total and total_r is not None and self._total_text:
            self.create_text(
                total_r,
                y,
                anchor="ne",
                text=self._total_text,
                fill=WHITE,
                font=cell_font,
                tags=("body",),
            )
        return row_h

    def _draw_frozen_header(self) -> None:
        self.delete("header")
        width = max(1, self.winfo_width())
        name_w, time_r, ref_r, delta_r, total_r = self._column_layout(width)
        y0 = self.canvasy(0)
        header_h = self._header_height()
        pad = int(6 * self._scale)
        header_font = self._header_font()

        self.create_rectangle(
            0, y0, width, y0 + header_h, fill=LIST_BG, outline="", tags=("header",)
        )
        self.create_line(
            0, y0 + header_h - 1, width, y0 + header_h - 1, fill=HEADER_LINE, tags=("header",)
        )
        self.create_text(
            8,
            y0 + pad,
            anchor="nw",
            text=self._headers.get("node", "节点"),
            fill=HEADER_FG,
            font=header_font,
            tags=("header",),
        )
        self.create_text(
            time_r,
            y0 + pad,
            anchor="ne",
            text=self._headers.get("time", "用时"),
            fill=HEADER_FG,
            font=header_font,
            tags=("header",),
        )
        self.create_text(
            ref_r,
            y0 + pad,
            anchor="ne",
            text=self._headers.get("ref", "参考"),
            fill=HEADER_FG,
            font=header_font,
            tags=("header",),
        )
        self.create_text(
            delta_r,
            y0 + pad,
            anchor="ne",
            text=self._headers.get("delta", "差值"),
            fill=HEADER_FG,
            font=header_font,
            tags=("header",),
        )
        if self._minimal and total_r is not None:
            self.create_text(
                total_r,
                y0 + pad,
                anchor="ne",
                text=self._headers.get("total", "总时间"),
                fill=HEADER_FG,
                font=header_font,
                tags=("header",),
            )
        self.tag_raise("header")
        _ = name_w

    def _redraw(self, *, preserve_scroll: bool = False) -> None:
        scroll_top = self.yview()[0] if preserve_scroll or not getattr(self, "_auto_scroll", False) else None
        self.delete("all")
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        self._update_scale(width)
        name_w, time_r, ref_r, delta_r, total_r = self._column_layout(width)
        header_h = self._header_height()

        y = header_h
        if self._minimal:
            current = None
            if 0 <= self._current_index < len(self._rows):
                current = self._rows[self._current_index]
            elif self._rows:
                current = next(
                    (r for r in self._rows if r.get("status") == "current"), self._rows[-1]
                )
            if current is not None:
                y += self._draw_row(
                    y=y,
                    width=width,
                    name_w=name_w,
                    time_r=time_r,
                    ref_r=ref_r,
                    delta_r=delta_r,
                    total_r=total_r,
                    row=current,
                    bump=2,
                    show_total=True,
                )
            total_h = max(height, y + 8)
            self.configure(scrollregion=(0, 0, width, total_h))
            self.yview_moveto(0)
            self._draw_frozen_header()
            self._auto_scroll = False
            return

        for row in self._rows:
            status: RowStatus = row.get("status", "pending")
            bump = 2 if status == "current" else 0
            y += self._draw_row(
                y=y,
                width=width,
                name_w=name_w,
                time_r=time_r,
                ref_r=ref_r,
                delta_r=delta_r,
                total_r=None,
                row=row,
                bump=bump,
                show_total=False,
            )

        total_h = max(height, y + 8)
        self.configure(scrollregion=(0, 0, width, total_h))
        if scroll_top is not None:
            self.yview_moveto(scroll_top)
        self._draw_frozen_header()
        self._auto_scroll = False
