# -*- coding: utf-8 -*-
"""Слайды первых 5 минут «Де-лидер 3» — Pillow, 1920x1080. Цифры — из банка visual_final (LIVE-таблица)."""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "first5", "slides"); os.makedirs(OUT, exist_ok=True)
W, H = 1920, 1080
BG, INK, MUT, ACC, LINE = (17, 18, 20), (240, 240, 240), (138, 143, 152), (200, 16, 46), (44, 46, 52)
C_STOCK, C_PBO, C_LOK, C_ANL = (154, 154, 154), (47, 128, 237), (200, 16, 46), (212, 175, 55)
F = r"C:\Windows\Fonts"
def font(size, bold=False, light=False):
    name = "segoeuib.ttf" if bold else ("segoeuil.ttf" if light else "segoeui.ttf")
    return ImageFont.truetype(os.path.join(F, name), size)

def canvas():
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 14, H], fill=ACC)                     # фирменная красная кромка слева
    d.text((W - 40, H - 46), "GOLDEN SAMPLE RESEARCH LAB", font=font(20, bold=True), fill=MUT, anchor="ra")
    return im, d

def text(d, xy, s, size, fill=INK, bold=False, anchor="la", light=False):
    d.text(xy, s, font=font(size, bold, light), fill=fill, anchor=anchor)

def save(im, name):
    p = os.path.join(OUT, name); im.save(p, quality=95); print("slide ->", p); return p

def plate(d, xy, s, size=40, fg=INK, bg=ACC, pad=22, bold=True):
    f = font(size, bold); x, y = xy
    l, t, r, b = d.textbbox((x, y), s, font=f)
    d.rounded_rectangle([l - pad, t - pad // 2, r + pad, b + pad // 2], radius=10, fill=bg)
    d.text((x, y), s, font=f, fill=fg)

def ladder(d, x0, y0, w, h, steps, filled, anchor=None, title=None):
    """steps: list of (label, value_str, color, score or None). filled: сколько ступеней залито."""
    n = len(steps); gap = 36; bw = (w - gap * (n - 1)) // n
    base, top = 40000, 49500
    d.line([x0, y0 + h, x0 + w, y0 + h], fill=LINE, width=3)
    for i, (lab, val, col, score) in enumerate(steps):
        x = x0 + i * (bw + gap)
        if i < filled and score:
            bh = int((score - base) / (top - base) * h)
            d.rounded_rectangle([x, y0 + h - bh, x + bw, y0 + h], radius=8, fill=col)
            vsize = 44 if bw >= 240 else 28
            text(d, (x + bw // 2, y0 + h - bh - 14), val, vsize, INK, bold=True, anchor="ms")
        else:
            d.rounded_rectangle([x, y0 + 20, x + bw, y0 + h], radius=8, outline=LINE, width=3)
            text(d, (x + bw // 2, y0 + h // 2), "—", 44, LINE, bold=True, anchor="mm")
        lsize = 34 if bw >= 240 else 22
        text(d, (x + bw // 2, y0 + h + 22), lab, lsize, col if i < filled else MUT, bold=True, anchor="ma")
    if title: text(d, (x0, y0 - 70), title, 36, MUT, bold=True)
    if anchor is not None:
        ax, ay, aw, ah = W - 560, H - 360, 480, 260
        d.rounded_rectangle([ax, ay, ax + aw, ay + ah], radius=14, fill=(26, 27, 31), outline=LINE, width=2)
        text(d, (ax + 24, ay + 18), "ЯКОРЬ · игры этой ступени", 22, MUT, bold=True)
        if anchor:
            for k, (lab, val, mark) in enumerate(anchor):
                yy = ay + 66 + k * 92
                text(d, (ax + 24, yy + 10), lab, 24, MUT)
                text(d, (ax + aw - 24, yy), val, 40, INK, bold=True, anchor="ra")
                if mark: text(d, (ax + 24, yy + 52), mark, 20, ACC, bold=True)
        else:
            text(d, (ax + 24, ay + 100), "пока пусто", 28, LINE)

# ---------------- слайды ----------------
def s00_intro():
    im, d = canvas()
    text(d, (120, 380), "ВСТУПЛЕНИЕ", 96, INK, bold=True)
    text(d, (120, 500), "уже записано · 0:00–0:50 · сварка, руки, стенд, страх", 40, MUT)
    text(d, (120, 620), "таймкод для тех, кто сразу к графикам → 3:40", 32, ACC, bold=True)
    return save(im, "s00_intro.png")

def s01_rules():
    im, d = canvas()
    text(d, (120, 150), "ОДИН КАМЕНЬ. ОДИН КОНТУР.", 92, INK, bold=True)
    text(d, (120, 270), "ДВЕ ПЛАТЫ — ×4 В ЦЕНЕ", 92, ACC, bold=True)
    text(d, (120, 420), "Переменная одна. Плата.", 48, MUT)
    # две платы схемой + ценники
    d.rounded_rectangle([140, 560, 900, 900], radius=16, outline=(90, 92, 98), width=4)
    text(d, (520, 600), "ROG Crosshair X870E Extreme", 40, INK, bold=True, anchor="ma")
    d.rounded_rectangle([1020, 560, 1780, 900], radius=16, outline=(90, 92, 98), width=4)
    text(d, (1400, 600), "B650-A GAMING WIFI", 40, INK, bold=True, anchor="ma")
    # ценники: один большой против четырёх маленьких
    d.rounded_rectangle([400, 700, 640, 840], radius=10, fill=ACC); text(d, (520, 770), "×4", 64, INK, bold=True, anchor="mm")
    for k in range(4):
        x = 1170 + k * 120
        d.rounded_rectangle([x, 740, x + 100, 820], radius=8, fill=(90, 92, 98)); text(d, (x + 50, 780), "×1", 30, INK, bold=True, anchor="mm")
    text(d, (120, 960), "Охлад — третий страх из вступления — закрыт во второй серии. Сегодня контур один и он не казуальный.", 28, MUT)
    return save(im, "s01_rules.png")

def s02_judge():
    im, d = canvas()
    d.rounded_rectangle([420, 140, 1500, 640], radius=20, fill=(26, 27, 31), outline=ACC, width=6)
    text(d, (960, 200), "СУДЬЯ", 40, ACC, bold=True, anchor="ma")
    text(d, (960, 300), "Cinebench R23", 110, INK, bold=True, anchor="ma")
    text(d, (960, 470), "все проценты «плата против платы» — только по нему", 34, MUT, anchor="ma")
    for x, name in ((330, "CS2"), (1190, "Киберпанк 2077")):
        d.rounded_rectangle([x, 720, x + 400, 940], radius=16, fill=(22, 23, 26), outline=LINE, width=3)
        text(d, (x + 200, 750), "СВИДЕТЕЛЬ", 26, MUT, bold=True, anchor="ma")
        text(d, (x + 200, 810), name, 48, INK, bold=True, anchor="ma")
        text(d, (x + 200, 880), "показывает, где настройка ведёт себя иначе", 22, MUT, anchor="ma")
    return save(im, "s02_judge.png")

def s03_profiles():
    im, d = canvas()
    text(d, (120, 110), "ЧЕТЫРЕ ПРОФИЛЯ", 64, INK, bold=True)
    cards = [("СТОК", "из коробки + EXPO", C_STOCK), ("ПБО", "плата крутит кривую сама, ты развязываешь руки", C_PBO),
             ("ЛОК", "множители и напряжение — руками, думать плате запрещено", C_LOK), ("АНЛИМ", "лок без ограничителей по току и температуре", C_ANL)]
    cw, gap, x0, y0 = 390, 36, 120, 260
    for i, (t_, s_, c) in enumerate(cards):
        x = x0 + i * (cw + gap)
        d.rounded_rectangle([x, y0, x + cw, y0 + 520], radius=18, fill=(24, 25, 29), outline=c, width=5)
        d.rectangle([x, y0, x + cw, y0 + 16], fill=c)
        text(d, (x + 30, y0 + 60), t_, 64, c, bold=True)
        # перенос описания
        words, line, yy = s_.split(), "", y0 + 180
        for wd in words:
            if d.textlength(line + " " + wd, font=font(32)) > cw - 60:
                text(d, (x + 30, yy), line, 32, INK); yy += 44; line = wd
            else:
                line = (line + " " + wd).strip()
        text(d, (x + 30, yy), line, 32, INK)
    return save(im, "s03_profiles.png")

def s04_physics():
    im, d = canvas()
    text(d, (120, 100), "У RYZEN НЕТ ОДНОЙ РУЧКИ «ЧАСТОТА»", 60, INK, bold=True)
    cx, cy = 960, 560
    d.rounded_rectangle([cx - 160, cy - 160, cx + 160, cy + 160], radius=24, fill=(30, 31, 36), outline=(120, 122, 130), width=4)
    for k in range(5):
        d.line([cx - 110 + k * 55, cy - 110, cx - 110 + k * 55, cy + 110], fill=(50, 52, 58), width=2)
        d.line([cx - 110, cy - 110 + k * 55, cx + 110, cy - 110 + k * 55], fill=(50, 52, 58), width=2)
    text(d, (cx, cy), "9950X3D", 40, INK, bold=True, anchor="mm")
    sats = [("ЧАСТОТА", (cx, cy - 330), MUT), ("ВОЛЬТАЖ", (cx + 520, cy), MUT), ("ТЕМПЕРАТУРА", (cx, cy + 330), MUT), ("ТОК", (cx - 520, cy), ACC)]
    for lab, (sx, sy), col in sats:
        d.line([cx, cy, sx, sy], fill=LINE, width=3)
        d.ellipse([sx - 70, sy - 40, sx + 70, sy + 40], fill=(24, 25, 29), outline=col, width=5)
        text(d, (sx, sy), lab, 26, col, bold=True, anchor="mm")
    text(d, (cx - 520, cy + 70), "упёрлись первым —", 24, ACC, anchor="ma")
    text(d, (cx - 520, cy + 100), "остальные три уже не важны", 24, ACC, anchor="ma")
    text(d, (120, 960), "Холоднее кристалл → меньше тока на ту же частоту. На этой фразе держится вся серия про скальп и воду.", 30, INK)
    return save(im, "s04_physics.png")

def s05_bios_count():
    im, d = canvas()
    text(d, (120, 120), "576 НАСТРОЕК", 120, INK, bold=True)
    x0, y0, w, h = 120, 420, 1680, 120
    a = int(w * 25 / 576); b = int(w * 15 / 576)
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=12, fill=(34, 35, 40))
    d.rectangle([x0, y0, x0 + a, y0 + h], fill=ACC)
    d.rectangle([x0 + a, y0, x0 + a + b, y0 + h], fill=(120, 122, 130))
    for k, (col, lab) in enumerate([(ACC, "влияют — 25"), ((120, 122, 130), "подчищают хвосты — ещё ~15"), ((34, 35, 40), "балласт, музей и ловушки — всё остальное")]):
        y = y0 + h + 60 + k * 80
        d.rounded_rectangle([x0, y, x0 + 48, y + 48], radius=8, fill=col, outline=LINE, width=2)
        text(d, (x0 + 76, y), lab, 40, INK if k < 2 else MUT, bold=True)
    text(d, (120, 930), "по нашему счёту", 30, MUT)
    return save(im, "s05_bios_count.png")

def s06_bios_traps():
    im, d = canvas()
    text(d, (120, 110), "ДВЕ ЛОВУШКИ ПО НАЗВАНИЮ", 64, INK, bold=True)
    for i, (t1, t2, t3) in enumerate([("Gaming Adaptive CCD Parker", "звучит как «сделать хорошо для игр»", "на нашей прошивке — неиграбельная система"),
                                       ("Performance Bias", "среди пресетов буквально стоит «CB R23»", "ASUS зашила имя бенчмарка в прошивку")]):
        x = 120 + i * 860
        d.rounded_rectangle([x, 260, x + 820, 760], radius=18, fill=(24, 25, 29), outline=LINE, width=3)
        d.rectangle([x, 260, x + 820, 276], fill=ACC)
        text(d, (x + 40, 320), t1, 44, INK, bold=True)
        text(d, (x + 40, 420), t2, 32, MUT)
        text(d, (x + 40, 560), t3, 34, ACC, bold=True)
    text(d, (120, 860), "Рынок рекордов немного договорной.", 40, INK, bold=True)
    return save(im, "s06_bios_traps.png")

STEPS_E = [("СТОК + EXPO", "42 181", C_STOCK, 42181), ("ПБО", "46 500", C_PBO, 46500), ("ЛОК", "48 579 / 48 189", C_LOK, 48579), ("АНЛИМ", "48 880", C_ANL, 48880)]

def s07_ladder_empty():
    im, d = canvas()
    text(d, (120, 100), "ЛЕСТНИЦА · ROG Crosshair X870E Extreme", 56, INK, bold=True)
    text(d, (120, 180), "снизу вверх, каждый шаг отдельно", 32, MUT)
    ladder(d, 120, 300, 1200, 560, STEPS_E, 0, anchor=[])
    return save(im, "s07_ladder_empty.png")

def s08_stock():
    im, d = canvas()
    text(d, (120, 100), "СТОК + EXPO", 56, C_STOCK, bold=True)
    text(d, (120, 180), "так живёт большинство · нулевая отметка", 32, MUT)
    ladder(d, 120, 300, 1200, 560, STEPS_E, 1, anchor=[("CS2 avg / low", "971 / 248", ""), ("КП сред / мин", "225 / 189", "")])
    plate(d, (1400, 300), "200 Вт · 61°", 40, bg=(34, 35, 40))
    text(d, (1400, 400), "пакет заводской,", 28, MUT); text(d, (1400, 436), "температура на прямом контакте", 28, MUT)
    return save(im, "s08_stock.png")

def s09_pbo_cfg():
    im, d = canvas()
    text(d, (120, 100), "ПБО — ПЛАТА КРУТИТ САМА", 56, C_PBO, bold=True)
    text(d, (120, 180), "мы только сняли поводок", 32, MUT)
    rows = [("Curve Optimizer", "−25 / −20 по чиплетам"), ("Curve Shaper", "−30 / −30 / −25 / −10"), ("Boost Override", "+200"), ("Scalar", "10X"), ("Лимиты", "Motherboard")]
    for k, (a, b) in enumerate(rows):
        y = 300 + k * 110
        d.rounded_rectangle([120, y, 1800, y + 86], radius=12, fill=(24, 25, 29), outline=LINE, width=2)
        text(d, (160, y + 22), a, 36, MUT); text(d, (1760, y + 22), b, 40, INK, bold=True, anchor="ra")
    text(d, (120, 900), "десять минут в биосе · это ещё не разгон", 32, C_PBO, bold=True)
    return save(im, "s09_pbo_cfg.png")

def s10_pbo():
    im, d = canvas()
    text(d, (120, 100), "ПБО", 56, C_PBO, bold=True)
    text(d, (120, 180), "плата просто перестала бояться", 32, MUT)
    ladder(d, 120, 300, 1200, 560, STEPS_E, 2, anchor=[("CS2 avg / low", "1023 / 266", "держите в голове до части про контру"), ("КП сред / мин", "228 / 196", "")])
    plate(d, (1400, 300), "+10,2% к стоку", 40, bg=C_PBO)
    text(d, (1400, 400), "частоту и ватты этой ступени", 24, MUT); text(d, (1400, 432), "в кадр не выносим", 24, MUT)
    return save(im, "s10_pbo.png")

if __name__ == "__main__":
    for fn in (s00_intro, s01_rules, s02_judge, s03_profiles, s04_physics, s05_bios_count, s06_bios_traps, s07_ladder_empty, s08_stock, s09_pbo_cfg, s10_pbo):
        fn()
