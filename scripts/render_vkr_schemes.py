#!/usr/bin/env python3
"""Render Draw.io sources to readable PNGs sized for an A4 text column."""
import html
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DRAWIO = ROOT / "docs/vkr/manuscript/figures/drawio"
SCREENS = ROOT / "docs/vkr/manuscript/figures/screens"
OUT_W = 620

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/Library/Fonts/Times New Roman.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def load_font(size):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def unescape(value):
    text = html.unescape(value or "")
    text = text.replace("&#xa;", "\n").replace("<br>", "\n")
    return text


def parse_cells(path):
    tree = ET.parse(path)
    root = tree.getroot()
    cells = {}
    edges = []
    page_w, page_h = 800, 500
    model = root.find(".//mxGraphModel")
    if model is not None:
        page_w = int(float(model.get("pageWidth", page_w)))
        page_h = int(float(model.get("pageHeight", page_h)))
    for cell in root.iter("mxCell"):
        cid = cell.get("id")
        if cid in (None, "0", "1"):
            continue
        geom = cell.find("mxGeometry")
        value = unescape(cell.get("value"))
        style = cell.get("style") or ""
        if cell.get("vertex") == "1" and geom is not None and geom.get("x") is not None:
            cells[cid] = {
                "x": float(geom.get("x", 0)),
                "y": float(geom.get("y", 0)),
                "w": float(geom.get("width", 120)),
                "h": float(geom.get("height", 60)),
                "text": value,
                "dashed": "dashed=1" in style,
            }
        elif cell.get("edge") == "1":
            edges.append({
                "src": cell.get("source"),
                "dst": cell.get("target"),
                "text": value,
                "dashed": "dashed=1" in style,
            })
    return page_w, page_h, cells, edges


def box_anchor(box, toward):
    cx, cy = box["x"] + box["w"] / 2, box["y"] + box["h"] / 2
    tx, ty = toward
    dx, dy = tx - cx, ty - cy
    if abs(dx) < 1 and abs(dy) < 1:
        return cx, cy
    # Intersect ray with rectangle.
    hx, hy = box["w"] / 2, box["h"] / 2
    sx = abs(hx / dx) if dx else 1e9
    sy = abs(hy / dy) if dy else 1e9
    t = min(sx, sy)
    return cx + dx * t, cy + dy * t


def render(path, dest):
    page_w, page_h, cells, edges = parse_cells(path)
    scale = OUT_W / page_w
    img_h = max(80, int(page_h * scale) + 8)
    img = Image.new("RGB", (OUT_W, img_h), "white")
    draw = ImageDraw.Draw(img)
    font = load_font(15)
    small = load_font(13)

    def S(v):
        return v * scale

    for edge in edges:
        a = cells.get(edge["src"])
        b = cells.get(edge["dst"])
        if not a or not b:
            continue
        acx, acy = a["x"] + a["w"] / 2, a["y"] + a["h"] / 2
        bcx, bcy = b["x"] + b["w"] / 2, b["y"] + b["h"] / 2
        x1, y1 = box_anchor(a, (bcx, bcy))
        x2, y2 = box_anchor(b, (acx, acy))
        color = "black"
        if edge["dashed"]:
            # Manual dash.
            steps = 12
            for i in range(0, steps, 2):
                t0, t1 = i / steps, min(1, (i + 1) / steps)
                draw.line(
                    [(S(x1 + (x2 - x1) * t0), S(y1 + (y2 - y1) * t0)),
                     (S(x1 + (x2 - x1) * t1), S(y1 + (y2 - y1) * t1))],
                    fill=color, width=2,
                )
        else:
            draw.line([(S(x1), S(y1)), (S(x2), S(y2))], fill=color, width=2)
        # Arrow head.
        import math
        ang = math.atan2(y2 - y1, x2 - x1)
        ah = 10
        for da in (2.6, -2.6):
            draw.line(
                [(S(x2), S(y2)),
                 (S(x2) - ah * math.cos(ang + da * 0.35), S(y2) - ah * math.sin(ang + da * 0.35))],
                fill=color, width=2,
            )
        if edge["text"]:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            label = edge["text"]
            bbox = draw.textbbox((0, 0), label, font=small)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            lx, ly = S(mx) - tw / 2, S(my) - th - 4
            draw.rectangle([lx - 2, ly - 1, lx + tw + 2, ly + th + 2], fill="white")
            draw.text((lx, ly), label, fill="black", font=small)

    for box in cells.values():
        x0, y0 = S(box["x"]), S(box["y"])
        x1, y1 = S(box["x"] + box["w"]), S(box["y"] + box["h"])
        draw.rounded_rectangle([x0, y0, x1, y1], radius=6, outline="black", width=2, fill="white")
        max_w = max(20, (x1 - x0) - 12)
        lines = []
        for raw in box["text"].split("\n"):
            raw = raw.strip()
            if not raw:
                continue
            words = raw.split()
            cur = ""
            for word in words:
                trial = word if not cur else cur + " " + word
                bb = draw.textbbox((0, 0), trial, font=font)
                if bb[2] - bb[0] <= max_w:
                    cur = trial
                else:
                    if cur:
                        lines.append(cur)
                    cur = word
            if cur:
                lines.append(cur)
        heights = []
        for ln in lines:
            bb = draw.textbbox((0, 0), ln, font=font)
            heights.append(bb[3] - bb[1])
        total = sum(heights) + 3 * max(0, len(lines) - 1)
        y = y0 + max(4, (y1 - y0 - total) / 2)
        for ln, h in zip(lines, heights):
            bb = draw.textbbox((0, 0), ln, font=font)
            tw = bb[2] - bb[0]
            draw.text((x0 + (x1 - x0 - tw) / 2, y), ln, fill="black", font=font)
            y += h + 3

    img.save(dest, "PNG", optimize=True)
    print(dest.name, img.size)


def shrink_screens():
    for name in ("leagues.png", "fixtures.png", "forecast.png"):
        src = SCREENS / name
        if not src.exists():
            continue
        im = Image.open(src).convert("RGB")
        h = round(im.height * OUT_W / im.width)
        im = im.resize((OUT_W, h), Image.Resampling.LANCZOS)
        im.save(src, "PNG", optimize=True)
        print("screen", name, im.size)


def canvas(w, h):
    img = Image.new("RGB", (w, h), "white")
    return img, ImageDraw.Draw(img), load_font(16), load_font(14)


def draw_box(draw, font, x, y, w, h, text):
    draw.rounded_rectangle([x, y, x + w, y + h], radius=8, outline="black", width=2, fill="white")
    lines = []
    max_w = w - 16
    for raw in text.split("\n"):
        words = raw.split()
        cur = ""
        for word in words:
            trial = word if not cur else f"{cur} {word}"
            bb = draw.textbbox((0, 0), trial, font=font)
            if bb[2] - bb[0] <= max_w:
                cur = trial
            else:
                if cur:
                    lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
    heights = [draw.textbbox((0, 0), ln, font=font)[3] for ln in lines]
    total = sum(heights) + 3 * (len(lines) - 1)
    ty = y + max(6, (h - total) / 2)
    for ln, lh in zip(lines, heights):
        tw = draw.textbbox((0, 0), ln, font=font)[2]
        draw.text((x + (w - tw) / 2, ty), ln, fill="black", font=font)
        ty += lh + 3


def harrow(draw, font, x1, x2, y, label, above=True):
    draw.line([(x1, y), (x2, y)], fill="black", width=2)
    draw.polygon([(x2, y), (x2 - 10, y - 5), (x2 - 10, y + 5)], fill="black")
    if label:
        bb = draw.textbbox((0, 0), label, font=font)
        tw, th = bb[2], bb[3]
        lx = (x1 + x2) / 2 - tw / 2
        ly = y - th - 6 if above else y + 6
        draw.rectangle([lx - 2, ly - 1, lx + tw + 2, ly + th + 1], fill="white")
        draw.text((lx, ly), label, fill="black", font=font)


def varrow(draw, font, x, y1, y2, label):
    draw.line([(x, y1), (x, y2)], fill="black", width=2)
    draw.polygon([(x, y2), (x - 5, y2 - 10), (x + 5, y2 - 10)], fill="black")
    if label:
        draw.text((x + 8, (y1 + y2) / 2 - 8), label, fill="black", font=font)


def save_diagram(name, img):
    if img.width != 620:
        h = round(img.height * 620 / img.width)
        img = img.resize((620, h), Image.Resampling.LANCZOS)
    dest = DRAWIO / name
    img.save(dest, "PNG", optimize=True)
    print(name, img.size)


def draw_context():
    img, draw, font, small = canvas(640, 520)
    draw_box(draw, font, 16, 24, 170, 72, "Пользователь")
    draw_box(draw, font, 250, 16, 240, 88, "Настольное\nприложение")
    harrow(draw, small, 186, 250, 60, "запрос")
    draw_box(draw, font, 250, 160, 240, 90, "Текстовое пояснение\nне выбирает исход")
    varrow(draw, small, 470, 104, 160, "факты")
    draw_box(draw, font, 250, 300, 240, 80, "Локальный кэш SQLite\nTTL 6 ч и 24 ч")
    varrow(draw, small, 300, 250, 300, "кэш")
    draw_box(draw, font, 250, 420, 240, 80, "football-data.org\nREST API v4")
    varrow(draw, small, 300, 380, 420, "промах TTL")
    save_diagram("context.png", img)


def draw_layers():
    img, draw, font, small = canvas(640, 420)
    draw_box(draw, font, 220, 16, 200, 70, "ui\nэкраны")
    draw_box(draw, font, 20, 16, 160, 70, "domain\nтипы данных")
    harrow(draw, small, 180, 220, 50, "типы")
    draw_box(draw, font, 220, 140, 200, 70, "services\nсценарий прогноза")
    varrow(draw, small, 320, 86, 140, "")
    draw_box(draw, font, 16, 280, 190, 90, "data\nHTTP, CSV, SQLite")
    draw_box(draw, font, 226, 280, 190, 90, "models\nЭло и Пуассон")
    draw_box(draw, font, 436, 280, 188, 90, "ai\nтекстовое пояснение")
    varrow(draw, small, 110, 210, 280, "")
    varrow(draw, small, 320, 210, 280, "")
    varrow(draw, small, 530, 210, 280, "")
    save_diagram("layers.png", img)


def draw_sequence():
    img, draw, font, small = canvas(640, 560)
    steps = [
        (24, "1. Данные\nкэш SQLite, при промахе TTL запрос к API"),
        (128, "2. Признаки\nформа, очные встречи, Эло, голы за 5 матчей, таблица"),
        (232, "3. Расчёт\nменьше четырёх матчей: только Эло; иначе Пуассон 65 % и Эло 35 %"),
        (336, "4. Пояснение\nна вход идут факты и вероятности; текст не выбирает исход"),
        (440, "5. Экран\nчисла показываются всегда; текст добавляется, если он есть"),
    ]
    for y, text in steps:
        draw_box(draw, font, 40, y, 560, 84, text)
    for y in (108, 212, 316, 420):
        varrow(draw, small, 320, y, y + 20, "")
    save_diagram("forecast-sequence.png", img)


def draw_sqlite():
    img, draw, font, small = canvas(640, 460)
    items = [
        (20, 20, "meta\nключ кэша, время, etag"),
        (330, 20, "competitions\nкод, название, герб"),
        (20, 150, "matches\nдата, статус, команды, голы"),
        (330, 150, "standings\nместо, игры, очки, мячи"),
        (20, 280, "team_rosters\nкоманда, заявка, тренер"),
        (330, 280, "match_lineups\nстарт и запас матча"),
    ]
    for x, y, text in items:
        draw_box(draw, font, x, y, 290, 110, text)
    draw.text((20, 410), "Файл кэша. SCHEDULED: 6 ч. FINISHED и таблицы: 24 ч.", fill="black", font=small)
    save_diagram("sqlite-cache.png", img)


def draw_screens():
    img, draw, font, small = canvas(640, 180)
    draw_box(draw, font, 16, 78, 150, 70, "Лиги")
    draw_box(draw, font, 245, 78, 150, 70, "Календарь")
    draw_box(draw, font, 474, 78, 150, 70, "Прогноз")
    harrow(draw, small, 166, 245, 48, "выбор лиги")
    harrow(draw, small, 395, 474, 48, "выбор матча")
    save_diagram("screens-nav.png", img)


def main():
    draw_context()
    draw_layers()
    draw_sequence()
    draw_sqlite()
    draw_screens()
    shrink_screens()


if __name__ == "__main__":
    main()
