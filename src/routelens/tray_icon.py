from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

from .paths import APP_ROOT, is_frozen, resource_path

ICON_PNG_NAME = "routelens-镂空.png"
ICON_ICO_NAME = "routelens.ico"


def _icon_dir() -> Path:
    local = Path(__file__).resolve().parent / "icon"
    if (local / ICON_ICO_NAME).is_file() or (local / ICON_PNG_NAME).is_file():
        return local
    return resource_path("routelens/icon")


def icon_png_path() -> Path:
    return _icon_dir() / ICON_PNG_NAME


def icon_ico_path() -> Path:
    return _icon_dir() / ICON_ICO_NAME


def _load_base_rgba() -> Image.Image | None:
    """优先 routelens.ico，缺省才回退 PNG。"""
    ico = icon_ico_path()
    if ico.is_file():
        try:
            img = Image.open(ico)
            best = img.convert("RGBA")
            max_area = best.size[0] * best.size[1]
            try:
                n = getattr(img, "n_frames", 1) or 1
                for i in range(n):
                    img.seek(i)
                    frame = img.convert("RGBA")
                    area = frame.size[0] * frame.size[1]
                    if area >= max_area:
                        max_area = area
                        best = frame
            except EOFError:
                pass
            return best
        except OSError:
            pass

    png = icon_png_path()
    if png.is_file():
        try:
            return Image.open(png).convert("RGBA")
        except OSError:
            return None
    return None


def _prepare_icon(size: int, *, margin_ratio: float = 0.02) -> Image.Image:
    """裁掉透明边后铺满目标尺寸。"""
    src = _load_base_rgba()
    if src is None:
        return Image.new("RGBA", (size, size), (32, 32, 32, 255))

    alpha = src.split()[-1]
    bbox = alpha.getbbox()
    if bbox is not None:
        src = src.crop(bbox)

    cw, ch = src.size
    side = max(cw, ch)
    margin = max(0, int(side * margin_ratio))
    canvas_side = side + margin * 2
    canvas = Image.new("RGBA", (canvas_side, canvas_side), (0, 0, 0, 0))
    canvas.paste(src, ((canvas_side - cw) // 2, (canvas_side - ch) // 2), src)
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def load_tray_image(size: int = 128) -> Image.Image:
    """托盘图标：来自 routelens.ico。"""
    return _prepare_icon(size, margin_ratio=0.02)


def load_window_icon_image(size: int = 64) -> Image.Image:
    """窗口 / 标题品牌图：来自 routelens.ico。"""
    return _prepare_icon(size, margin_ratio=0.04)


def ensure_window_ico() -> Path | None:
    """供 Windows iconbitmap / 任务栏的 .ico 路径（优先已有 routelens.ico）。"""
    ico = icon_ico_path()
    if ico.is_file():
        return ico.resolve()

    png = icon_png_path()
    if not png.is_file():
        return None
    target = APP_ROOT / ICON_ICO_NAME if is_frozen() else ico
    try:
        base = _prepare_icon(256, margin_ratio=0.02)
        target.parent.mkdir(parents=True, exist_ok=True)
        base.save(
            target,
            format="ICO",
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
        return target.resolve()
    except OSError:
        return None


def apply_window_icon(window) -> object | None:
    """给任意 Tk/CTk 窗口设置 routelens.ico；返回 PhotoImage 引用防 GC。"""
    import tkinter as tk

    ico = ensure_window_ico()
    if ico is not None:
        ico_str = str(ico)
        for call in (
            lambda: window.iconbitmap(default=ico_str),
            lambda: window.iconbitmap(ico_str),
            lambda: window.wm_iconbitmap(ico_str),
        ):
            try:
                call()
                break
            except tk.TclError:
                continue
    try:
        from PIL import ImageTk

        photo = ImageTk.PhotoImage(load_window_icon_image(64))
        window.iconphoto(True, photo)
        return photo
    except Exception:
        return None


def set_windows_app_id(app_id: str = "orcwind.RouteLens") -> None:
    """让任务栏挂到本进程 exe 图标，而不是 python.exe / 默认图标。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass
