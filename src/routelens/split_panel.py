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
        self._minimal_rows = 1  # 极简：1=仅当前；3=前一个+当前+后一个
        self._total_text = ""
        self._total_delta_text = ""
        self._headers = {
            "node": "节点",
            "time": "用时",
            "ref": "参考",
            "delta": "差值",
            "total": "总时间",
        }
        self._menu_exit_minimal = "退出极简模式"
        self._menu_close = "关闭"
        self._waiting_text = "等待进图"
        self._ct_on = False
        self._ct_header_text = "⚡ Shift+S 恢复点击"
        self._on_exit_minimal: Callable[[], None] | None = None
        self._on_close_app: Callable[[], None] | None = None
        self.bind("<Configure>", self._on_configure)
        self.bind("<MouseWheel>", self._on_mousewheel)
        self.bind("<Enter>", self._bind_wheel)
        self.bind("<Leave>", self._unbind_wheel)
        self.bind("<Double-Button-1>", self._on_double_click)
        self.bind("<Button-3>", self._on_right_click)

    def _bind_wheel(self, _event: object = None) -> None:
        self.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_wheel(self, _event: object = None) -> None:
        self.unbind_all("<MouseWheel>")

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
        waiting: str | None = None,
    ) -> None:
        """表头与右键菜单文案（节点名等内容仍由外部数据决定，不翻译）。"""
        if headers:
            self._headers.update(headers)
        if exit_minimal is not None:
            self._menu_exit_minimal = exit_minimal
        if close_app is not None:
            self._menu_close = close_app
        if waiting is not None:
            self._waiting_text = waiting
        self._redraw(preserve_scroll=True)

    def set_click_through_hint(self, text: str, *, enabled: bool) -> None:
        """穿透状态：开启时表头节点位显示恢复提示（不占额外高度）。"""
        if self._ct_on == enabled:
            return
        self._ct_on = enabled
        self._redraw(preserve_scroll=True)

    @property
    def minimal(self) -> bool:
        return self._minimal

    def set_minimal(self, enabled: bool) -> None:
        if self._minimal == enabled:
            return
        self._minimal = enabled
        if enabled:
            self._minimal_rows = 1
        self._redraw()

    def set_minimal_rows(self, count: int) -> None:
        """极简上下文行数：1 或 3。"""
        rows = 3 if count >= 2 else 1
        if self._minimal_rows == rows:
            return
        self._minimal_rows = rows
        if self._minimal:
            self._redraw(preserve_scroll=True)

    def content_height_for_minimal(self, row_count: int, width: int | None = None) -> int:
        """估算极简模式内容高度（表头 + 行），供窗口贴边/吸附。"""
        w = max(1, width or self.winfo_width() or self.BASE_WIDTH)
        self._update_scale(w)
        header_h = self._header_height()
        n = 3 if row_count >= 2 else 1
        # 当前行 bump 略高
        body = 0
        if n == 1:
            body = self._row_height + 4
        else:
            body = (self._row_height) + (self._row_height + 4) + self._row_height
        return header_h + body + 4

    def set_rows(
        self,
        rows: list[dict],
        current_index: int,
        *,
        auto_scroll: bool = False,
        total_text: str = "",
        total_delta_text: str = "",
        redraw: bool = True,
    ) -> None:
        self._rows = rows
        self._current_index = current_index
        self._auto_scroll = auto_scroll
        self._total_text = total_text
        self._total_delta_text = total_delta_text
        if redraw:
            self._redraw()

    def redraw(self, *, preserve_scroll: bool = False) -> None:
        self._redraw(preserve_scroll=preserve_scroll)

    def _waiting_row(self) -> dict:
        """极简模式的占位行（还没有任何节点时）。

        名字列提示「等待进图」，数值列留空；总时间仍会画在这一行上，
        保证计时器永远可见。
        """
        return {
            "name": self._waiting_text,
            "time": "",
            "ref": "",
            "delta": "",
            "status": "current",
        }

    def _visible_minimal_indices(self) -> tuple[list[int], int]:
        """极简可见行索引与当前行索引。"""
        ci = self._current_index
        if not self._rows:
            return [], -1
        if ci < 0 or ci >= len(self._rows):
            for i, row in enumerate(self._rows):
                if row.get("status") == "current":
                    ci = i
                    break
            else:
                ci = len(self._rows) - 1
        indices: list[int] = []
        if ci >= 0:
            if self._minimal_rows >= 3 and ci > 0:
                indices.append(ci - 1)
            indices.append(ci)
            if self._minimal_rows >= 3 and ci + 1 < len(self._rows):
                indices.append(ci + 1)
        return indices, ci

    def preferred_width_for_minimal(
        self,
        *,
        min_width: int = 280,
        max_width: int = 1920,
    ) -> int:
        """计算极简模式下完整显示可见节点名所需宽度（随字号迭代）。"""
        if not self._minimal:
            return min_width
        width = max(min_width, int(self.winfo_width() or self.BASE_WIDTH))
        ceiling = max(min_width, max_width)
        for _ in range(16):
            self._update_scale(width)
            needed = self._minimal_content_min_width()
            needed = max(min_width, min(ceiling, needed))
            if needed <= width + 1:
                return needed
            width = needed
        return width

    def _minimal_content_min_width(self) -> int:
        pad = 6
        gap = max(6, int(8 * self._scale))
        bump = 2
        indices, ci = self._visible_minimal_indices()
        visible = [self._rows[i] for i in indices if 0 <= i < len(self._rows)]
        if not visible:
            # 无节点时画占位行（「等待进图」），宽度也要算进去
            visible = [self._waiting_row()]

        max_name = self._text_width(self._headers.get("node", "节点"), self._header_font())
        for row in visible:
            name = str(row.get("name", ""))
            font = self._name_font(bump=bump)
            max_name = max(max_name, self._text_width(name, font))

        times = [str(r.get("time", "")) for r in visible]
        refs = [str(r.get("ref", "")) for r in visible]
        deltas = [str(r.get("delta", "")) for r in visible]
        if self._total_delta_text:
            deltas.append(self._total_delta_text)
        time_w = self._max_cell_width("time", times, bump=bump)
        ref_w = self._max_cell_width("ref", refs, bump=bump)
        delta_w = self._max_cell_width("delta", deltas, bump=bump)
        totals = [self._total_text] if self._total_text else []
        total_w = self._max_cell_width("total", totals, bump=bump)
        delta_total_w = 0
        if self._total_delta_text:
            delta_total_w = self._text_width(self._total_delta_text, self._font(11, bump=bump)) + gap

        # pad + 完整节点名 + 各数值列（含累计差与总时间）
        return (
            pad
            + max_name
            + 8
            + gap
            + time_w
            + gap
            + ref_w
            + gap
            + delta_w
            + gap
            + delta_total_w
            + total_w
            + pad
        )

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
        """按窗口宽度缩放。

        极简模式：只按宽度比例缩放，不够宽由外层自动扩窗，禁止缩小字号挤节点名。
        普通模式：必要时微缩字号，避免数值列被裁切。
        """
        scale = max(0.55, min(1.35, width / self.BASE_WIDTH))
        if self._minimal:
            self._scale = scale
            self._row_height = max(14, int(20 * scale))
            return
        # 预留当前行 bump=2 的最宽数值，找不到合适字号则继续缩小
        for _ in range(12):
            self._scale = scale
            self._row_height = max(16, int(24 * scale))
            name_w, _time_r, _ref_r, _delta_r, _total_r = self._column_layout(width)
            if name_w >= 36 or scale <= 0.55:
                break
            scale = max(0.55, scale * 0.92)

    def _font(self, base: int, *, bold: bool = False, bump: int = 0) -> tuple[str, int, str]:
        # 极简模式保持小字号（产品目标：极简越小越好）；普通模式放大并设下限
        floor = 7 if self._minimal else 10
        size = max(floor, int(base * self._scale) + bump)
        style = "bold" if bold else "normal"
        return ("Consolas", size, style)

    def _name_font(self, *, bump: int = 0) -> tuple[str, int, str]:
        if self._minimal:
            return ("Microsoft YaHei", max(7, int(11 * self._scale) + bump), "normal")
        size = max(11, int(12 * self._scale) + bump)
        return ("Microsoft YaHei", size, "normal")

    def _header_font(self) -> tuple[str, int, str]:
        if self._minimal:
            return ("Microsoft YaHei", max(7, int(11 * self._scale)), "normal")
        size = max(11, int(12 * self._scale))
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
        font = self._font(11, bump=bump)
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
            delta_total_w = 0
            if self._total_delta_text:
                delta_total_w = self._text_width(self._total_delta_text, self._font(11, bump=bump)) + gap
            total_r = right
            delta_r = total_r - total_w - delta_total_w - gap
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
        cell_font = self._font(11, bump=bump)
        raw_name = str(row.get("name", ""))
        # 极简模式禁止省略号截断；由窗口自动扩宽保证完整显示
        if self._minimal:
            name = raw_name
        else:
            name = self._truncate(raw_name, name_w - 4, font=name_font)
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
            total_font = cell_font
            if self._total_delta_text:
                delta = self._total_delta_text
                d_color = GREEN if delta.startswith("-") else RED if delta.startswith("+") else WHITE
                total_w = tkfont.Font(font=total_font).measure(self._total_text)
                gap = max(6, int(8 * self._scale))
                self.create_text(
                    total_r - total_w - gap,
                    y,
                    anchor="ne",
                    text=delta,
                    fill=d_color,
                    font=total_font,
                    tags=("body",),
                )
            self.create_text(
                total_r,
                y,
                anchor="ne",
                text=self._total_text,
                fill=WHITE,
                font=total_font,
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
        # 穿透开启：表头节点位显示金色恢复提示（零高度占用）
        node_header = self._headers.get("node", "节点")
        node_color: str = HEADER_FG
        if self._ct_on:
            node_header = self._ct_header_text
            node_color = GOLD
        self.create_text(
            8,
            y0 + pad,
            anchor="nw",
            text=node_header,
            fill=node_color,
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
            indices, ci = self._visible_minimal_indices()
            if not indices:
                # 一个节点都没有时也要画一行占位：否则总时间画在「当前行」上，
                # 没有当前行 = 计时器完全不显示（用户实测：新建路线后极简看不到计时）。
                indices = [-1]
                ci = -1
            for idx in indices:
                row = self._rows[idx] if idx >= 0 else self._waiting_row()
                is_current = idx == ci
                y += self._draw_row(
                    y=y,
                    width=width,
                    name_w=name_w,
                    time_r=time_r,
                    ref_r=ref_r,
                    delta_r=delta_r,
                    total_r=total_r,
                    row=row,
                    bump=2 if is_current else 0,
                    show_total=is_current,
                )
            # 极简：scrollregion 贴内容，不撑满黑底空洞
            total_h = max(y + 2, header_h + self._row_height)
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
