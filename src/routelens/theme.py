"""RouteLens 深色主题与 CustomTkinter 全局配置。"""

from __future__ import annotations

import customtkinter as ctk

BG = "#121212"
PANEL_BG = "#1a1a1a"
SURFACE = "#2d2d2d"
BORDER = "#2e2e2e"
WINDOW_EDGE = "#1c1c1c"
BTN_ACTIVE = "#3a3a3a"
BTN_PRIMARY = "#007acc"
BTN_PRIMARY_HOVER = "#1a8cd8"
BTN_PRIMARY_DISABLED = "#264f78"
TEXT_FG = "#e0e0e0"
MUTED_FG = "#a0a0a0"
GOLD_FG = "#f0c040"
GREEN_FG = "#7fd47f"
RED_FG = "#ff6b6b"
SKIP_FG = "#666666"
SELECT_BG = "#264f78"
CORNER_RADIUS = 8
BTN_HEIGHT = 40

# 使用元组字体，避免在创建 CTk 根窗口前实例化 CTkFont
FONT_UI = ("Microsoft YaHei", 13)
FONT_UI_SM = ("Microsoft YaHei", 12)
FONT_TITLE = ("Microsoft YaHei", 22, "bold")
FONT_HEADING = ("Microsoft YaHei", 17, "bold")
FONT_TIMER = ("Consolas", 30, "bold")
FONT_SPLIT = ("Consolas", 13)
FONT_HINT = ("Microsoft YaHei", 12)


def apply_theme() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
