"""Generate the app icon, splash and background pattern with Pillow (dev-only script).

    python scripts/make_assets.py

Writes into src/assets/:
  icon.png            1024x1024, opaque (web, Windows, Linux, iOS)
  icon_macos.png      1024x1024, rounded macOS tile on a transparent canvas
  icon_android.png    1024x1024, transparent foreground inside the adaptive-icon safe zone
                      (flet uses it as `adaptive_icon_foreground`; background colour comes
                      from [tool.flet.android].adaptive_icon_background in pyproject.toml)
  splash.png          1024x1024, transparent logo for the Android / iOS / web splash
  bg_pattern.png      1600x1000, faint football-pitch lines for the app background
Artwork: a football with a rising green chart arrow — readable down to 16 px.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "assets"

SS = 4  # supersampling factor
SIZE = 1024
NAVY = (10, 26, 51)
TEAL = (11, 42, 58)
PITCH = (12, 74, 52)
ACCENT = (34, 197, 94)
INK = (15, 23, 42)
WHITE = (248, 250, 252)


def _gradient(size: int, top_left: tuple, bottom_right: tuple, middle: tuple) -> Image.Image:
    """Diagonal three-stop gradient."""
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            if t < 0.5:
                a, b, k = top_left, middle, t / 0.5
            else:
                a, b, k = middle, bottom_right, (t - 0.5) / 0.5
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * k) for i in range(3))
    return img


def _pentagon(cx: float, cy: float, r: float, rotation: float) -> list[tuple[float, float]]:
    return [
        (
            cx + r * math.cos(rotation + i * 2 * math.pi / 5),
            cy + r * math.sin(rotation + i * 2 * math.pi / 5),
        )
        for i in range(5)
    ]


def _ball(size: int, cx: float, cy: float, radius: float) -> Image.Image:
    """RGBA football: white disc, central pentagon, seams and clipped outer pentagons."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=WHITE + (255,))
    patches = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pdraw = ImageDraw.Draw(patches)
    up = -math.pi / 2
    inner = _pentagon(cx, cy, radius * 0.3, up)
    pdraw.polygon(inner, fill=INK + (255,))
    seam = max(2, round(radius * 0.05))
    for i, (vx, vy) in enumerate(inner):
        angle = up + i * 2 * math.pi / 5
        ox, oy = cx + radius * 0.97 * math.cos(angle), cy + radius * 0.97 * math.sin(angle)
        outer = _pentagon(ox, oy, radius * 0.25, angle + math.pi)
        pdraw.polygon(outer, fill=INK + (255,))
        near = min(outer, key=lambda p: (p[0] - vx) ** 2 + (p[1] - vy) ** 2)
        pdraw.line([(vx, vy), near], fill=INK + (255,), width=seam)
        # seams between neighbouring outer pentagons
        nxt = up + (i + 0.5) * 2 * math.pi / 5
        mx, my = cx + radius * 0.62 * math.cos(nxt), cy + radius * 0.62 * math.sin(nxt)
        pdraw.line(
            [(mx, my), (cx + radius * math.cos(nxt), cy + radius * math.sin(nxt))],
            fill=INK + (255,),
            width=seam,
        )
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=255)
    patches.putalpha(ImageChops.multiply(patches.getchannel("A"), mask))
    layer.alpha_composite(patches)
    ring = max(3, round(radius * 0.06))
    draw = ImageDraw.Draw(layer)
    draw.ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius), outline=INK + (255,), width=ring
    )
    return layer


def _arrow(size: int, points: list[tuple[float, float]], width: float) -> Image.Image:
    """Rising chart line with an arrow head; dark outline keeps it readable on the ball."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    (x1, y1), (x2, y2) = points[-2], points[-1]
    angle = math.atan2(y2 - y1, x2 - x1)
    head = width * 2.3
    tip = (x2 + head * 0.55 * math.cos(angle), y2 + head * 0.55 * math.sin(angle))
    left = (x2 + head * math.cos(angle + 2.4), y2 + head * math.sin(angle + 2.4))
    right = (x2 + head * math.cos(angle - 2.4), y2 + head * math.sin(angle - 2.4))
    for color, grow in ((INK + (255,), width * 0.45), (ACCENT + (255,), 0.0)):
        w = round(width + grow)
        draw.line(points, fill=color, width=w, joint="curve")
        for x, y in points[:-1]:
            draw.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=color)
        if grow:
            k = grow / 2
            draw.polygon(
                [
                    (tip[0] + k * math.cos(angle), tip[1] + k * math.sin(angle)),
                    (left[0] + k * math.cos(angle + 2.4), left[1] + k * math.sin(angle + 2.4)),
                    (right[0] + k * math.cos(angle - 2.4), right[1] + k * math.sin(angle - 2.4)),
                ],
                fill=color,
            )
        else:
            draw.polygon([tip, left, right], fill=color)
    return layer


def artwork(size: int, *, scale: float = 1.0) -> Image.Image:
    """Transparent logo (ball + rising chart) fitted in `scale` of the canvas."""
    s = size * SS
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    def p(x: float, y: float) -> tuple[float, float]:
        # design grid 0..1 mapped to the central `scale` area
        off = (1 - scale) / 2
        return ((off + x * scale) * s, (off + y * scale) * s)

    # the chart rises from behind the ball: arrow first, ball on top
    chart = [p(0.30, 0.70), p(0.58, 0.44), p(0.71, 0.57), p(0.89, 0.21)]
    layer.alpha_composite(_arrow(s, chart, 0.085 * scale * s))
    bx, by = p(0.31, 0.69)
    layer.alpha_composite(_ball(s, bx, by, 0.27 * scale * s))
    return layer.resize((size, size), Image.LANCZOS)


def _shadow(img: Image.Image, blur: int, opacity: float) -> Image.Image:
    alpha = img.getchannel("A").filter(ImageFilter.GaussianBlur(blur))
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow.putalpha(alpha.point(lambda a: int(a * opacity)))
    return shadow


def background_tile(size: int) -> Image.Image:
    base = _gradient(size, NAVY, PITCH, TEAL).convert("RGBA")
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse(
        (size * 0.05, -size * 0.25, size * 0.95, size * 0.55), fill=(34, 197, 94, 60)
    )
    base.alpha_composite(glow.filter(ImageFilter.GaussianBlur(size // 8)))
    return base


def make_icon() -> Image.Image:
    img = background_tile(SIZE)
    art = artwork(SIZE, scale=0.84)
    img.alpha_composite(_shadow(art, 18, 0.45), (0, 10))
    img.alpha_composite(art)
    return img.convert("RGB")


def make_macos_icon() -> Image.Image:
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    tile_size = 824
    tile = make_icon().resize((tile_size, tile_size), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (tile_size * SS, tile_size * SS), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, tile_size * SS - 1, tile_size * SS - 1), radius=185 * SS, fill=255
    )
    tile.putalpha(mask.resize((tile_size, tile_size), Image.LANCZOS))
    off = (SIZE - tile_size) // 2
    placed = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    placed.alpha_composite(tile, (off, off))
    canvas.alpha_composite(_shadow(placed, 14, 0.5), (0, 8))
    canvas.alpha_composite(placed)
    return canvas


def make_pattern(width: int = 1600, height: int = 1000) -> Image.Image:
    """Faint pitch markings (white lines on transparent), drawn once, stretched to cover."""
    img = Image.new("RGBA", (width * 2, height * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w, h = width * 2, height * 2
    c = (255, 255, 255, 255)
    lw = 6
    m = 80
    d.rectangle((m, m, w - m, h - m), outline=c, width=lw)
    d.line((w / 2, m, w / 2, h - m), fill=c, width=lw)
    r = h * 0.16
    d.ellipse((w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r), outline=c, width=lw)
    d.ellipse((w / 2 - 10, h / 2 - 10, w / 2 + 10, h / 2 + 10), fill=c)
    for side in (0, 1):
        x0 = m if side == 0 else w - m
        sign = 1 if side == 0 else -1
        box_w, box_h = w * 0.13, h * 0.5
        six_w, six_h = w * 0.05, h * 0.22
        d.rectangle(
            sorted_box(x0, h / 2 - box_h / 2, x0 + sign * box_w, h / 2 + box_h / 2),
            outline=c,
            width=lw,
        )
        d.rectangle(
            sorted_box(x0, h / 2 - six_h / 2, x0 + sign * six_w, h / 2 + six_h / 2),
            outline=c,
            width=lw,
        )
        spot = x0 + sign * w * 0.09
        d.ellipse((spot - 8, h / 2 - 8, spot + 8, h / 2 + 8), fill=c)
        arc_box = (spot - r, h / 2 - r, spot + r, h / 2 + r)
        d.arc(
            arc_box, start=-53 if side == 0 else 127, end=53 if side == 0 else 233, fill=c, width=lw
        )
    return img.resize((width, height), Image.LANCZOS)


def sorted_box(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    make_icon().save(ASSETS / "icon.png", optimize=True)
    make_macos_icon().save(ASSETS / "icon_macos.png", optimize=True)
    artwork(SIZE, scale=0.56).save(ASSETS / "icon_android.png", optimize=True)
    artwork(SIZE, scale=0.5).save(ASSETS / "splash.png", optimize=True)
    make_pattern().save(ASSETS / "bg_pattern.png", optimize=True)
    for name in ("icon.png", "icon_macos.png", "icon_android.png", "splash.png", "bg_pattern.png"):
        path = ASSETS / name
        print(
            f"{path.relative_to(ROOT)}  {Image.open(path).size}  {path.stat().st_size // 1024} KB"
        )


if __name__ == "__main__":
    main()
