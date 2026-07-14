from __future__ import annotations

from pathlib import Path

from PIL import Image

ICON_DIR = Path(__file__).resolve().parent / "icon"
ICON_PNG = ICON_DIR / "routelens-镂空.png"


def icon_png_path() -> Path:
    return ICON_PNG


def _prepare_icon(size: int, *, margin_ratio: float = 0.02) -> Image.Image:
    """裁掉透明边后尽量铺满目标尺寸，避免托盘里看起来只有中间一小点。"""
    if not ICON_PNG.is_file():
        return Image.new("RGBA", (size, size), (32, 32, 32, 255))

    src = Image.open(ICON_PNG).convert("RGBA")
    alpha = src.split()[-1]
    bbox = alpha.getbbox()
    if bbox is not None:
        src = src.crop(bbox)

    # 放到正方形画布，只留一点点边距让主体更大
    cw, ch = src.size
    side = max(cw, ch)
    margin = max(1, int(side * margin_ratio))
    canvas_side = side + margin * 2
    canvas = Image.new("RGBA", (canvas_side, canvas_side), (0, 0, 0, 0))
    canvas.paste(src, ((canvas_side - cw) // 2, (canvas_side - ch) // 2), src)
    return canvas.resize((size, size), Image.Resampling.LANCZOS)


def load_tray_image(size: int = 128) -> Image.Image:
    """托盘图标：默认 128，HiDPI 下比 64 更清晰也更大。"""
    return _prepare_icon(size, margin_ratio=0.02)


def load_window_icon_image(size: int = 64) -> Image.Image:
    return _prepare_icon(size, margin_ratio=0.04)


def ensure_window_ico() -> Path | None:
    """生成多尺寸 .ico，供 Windows 标题栏使用。"""
    if not ICON_PNG.is_file():
        return None
    ico_path = ICON_DIR / "routelens.ico"
    try:
        if ico_path.is_file() and ico_path.stat().st_mtime >= ICON_PNG.stat().st_mtime:
            return ico_path
        base = _prepare_icon(256, margin_ratio=0.02)
        base.save(
            ico_path,
            format="ICO",
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
        return ico_path
    except OSError:
        return None
