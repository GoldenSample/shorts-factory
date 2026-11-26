# -*- coding: utf-8 -*-
"""Слайды второй половины «Де-лидер 3» (кадры 9–41 визуального скринплея). Цифры — LIVE-таблица."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from slides import (canvas, text, save, plate, ladder, font, INK, MUT, ACC, LINE,
                    C_STOCK, C_PBO, C_LOK, C_ANL, STEPS_E)
from PIL import ImageDraw

GREEN = (46, 160, 87)
YELL = (212, 175, 55)
STEPS_B = [("СТОК + EXPO", "41 234", C_STOCK, 41234), ("ПБО", "46 642", C_PBO, 46642), ("ЛОК", "46 117", C_LOK, 46117), ("АНЛИМ", "47 439", C_ANL, 47439)]

def rows_slide(name, title, sub, rows, footer=None, title_col=INK):
    im, d = canvas()
    text(d, (120, 100), title, 56, title_col, bold=True)
    if sub: text(d, (120, 180), sub, 32, MUT)
    for k, (a, b) in enumerate(rows):
        y = 280 + k * 108
        d.rounded_rectangle([120, y, 1800, y + 86], radius=12, fill=(24, 25, 29), outline=LINE, width=2)
        text(d, (160, y + 22), a, 36, MUT); text(d, (1760, y + 22), b, 40, INK, bold=True, anchor="ra")
    if footer: text(d, (120, 300 + len(rows) * 108 + 20), footer, 32, ACC, bold=True)
    return save(im, name)

def split_slide(name, title, verdict, vcol, left, right, items, note=None):
    """очная ставка: два бара R23 + строки сравнения. items: [(label, lval, rval, hi)] hi: -1 лево, 1 право, 0 никто"""
    im, d = canvas()
    text(d, (120, 90), title, 56, INK, bold=True)
    plate(d, (120, 190), verdict, 40, bg=vcol)
    lv, rv = left[1], right[1]
    base, top = 40000, 49500
    x0, y0, h, bw = 150, 380, 420, 300
    d.line([x0 - 10, y0 + h, x0 + 2 * bw + 130, y0 + h], fill=LINE, width=3)
    for i, (nm, sc, col) in enumerate([left, right]):
        x = x0 + i * (bw + 120)
        bh = int((sc - base) / (top - base) * h)
        d.rounded_rectangle([x, y0 + h - bh, x + bw, y0 + h], radius=8, fill=col)
        text(d, (x + bw // 2, y0 + h - bh - 18), "{:,}".format(sc).replace(",", " "), 46, INK, bold=True, anchor="ms")
        text(d, (x + bw // 2, y0 + h + 20), nm, 32, MUT, bold=True, anchor="ma")
    ax = 1080
    for k, (lab, lval, rval, hi) in enumerate(items):
        y = 340 + k * 118
        d.rounded_rectangle([ax, y, 1820, y + 100], radius=10, fill=(24, 25, 29), outline=LINE, width=2)
        text(d, (ax + 24, y + 8), lab, 24, MUT)
        if lval: text(d, (ax + 24, y + 44), lval, 32, INK if hi != -1 else GREEN, bold=(hi == -1))
        if rval: text(d, (1796, y + 44), rval, 32, INK if hi != 1 else GREEN, bold=(hi == 1), anchor="ra")
    if note: text(d, (120, 900), note, 30, MUT)
    return save(im, name)

# ---- 9-11: ЛОК ----
def s11():
    return rows_slide("s11_lok_cfg.png", "ЛОК — ДУМАЕМ ЗА ПЛАТУ САМИ", "думать плате запрещено",
        [("Множители Per-CCX", "54,75–54,85 / 56,35–56,45"), ("LLC", "6"), ("Vcore в биосе", "1,33"),
         ("Vcore под нагрузкой", "1,21"), ("Лимиты", "как у лока")], None, C_LOK)

def s12():
    im, d = canvas()
    text(d, (120, 100), "ЛОК", 56, C_LOK, bold=True)
    text(d, (120, 180), "третья ступень", 32, MUT)
    ladder(d, 120, 300, 1200, 560, STEPS_E, 3, anchor=[("CS2 avg / low", "980 / 247", "ниже, чем на ПБО"), ("КП сред / мин", "235 / 201", "лучший в серии")])
    plate(d, (1400, 300), "5557 МГц · 325 Вт · 83,6°", 34, bg=(34, 35, 40))
    return save(im, "s12_lok.png")

def s13():
    im, d = canvas()
    text(d, (120, 110), "ПРОГОН ПОВТОРИЛИ", 64, INK, bold=True)
    for i, (v, lab) in enumerate([("48 579", "первый прогон"), ("48 189", "повтор")]):
        x = 260 + i * 760
        d.rounded_rectangle([x, 330, x + 640, 690], radius=20, fill=(24, 25, 29), outline=C_LOK, width=5)
        text(d, (x + 320, 400), v, 110, INK, bold=True, anchor="ma")
        text(d, (x + 320, 580), lab, 34, MUT, anchor="ma")
    plate(d, (740, 780), "разброс 0,8%", 40, bg=(34, 35, 40))
    text(d, (120, 930), "обе цифры остаются на экране: главный вывод ролика не должен выглядеть точнее, чем он есть", 30, MUT)
    return save(im, "s13_lok_repeat.png")

def s14():
    im, d = canvas()
    text(d, (120, 110), "ИГРЫ НА ЛОКЕ", 64, C_LOK, bold=True)
    rows = [("Киберпанк сред / мин", "235 / 201", "лучший в серии", GREEN), ("CS2 avg / low", "980 / 247", "ниже, чем на ПБО", ACC)]
    for k, (a, b, m, c) in enumerate(rows):
        y = 300 + k * 200
        d.rounded_rectangle([120, y, 1800, y + 160], radius=14, fill=(24, 25, 29), outline=LINE, width=2)
        text(d, (160, y + 30), a, 40, MUT); text(d, (1200, y + 20), b, 72, INK, bold=True)
        text(d, (160, y + 96), m, 30, c, bold=True)
    text(d, (120, 780), "Один профиль всё не берёт.", 48, INK, bold=True)
    return save(im, "s14_lok_games.png")

# ---- 12-16: АНЛИМ ----
def s15():
    return rows_slide("s15_anl_cfg.png", "АНЛИМ — ЛОК БЕЗ ОГРАНИЧИТЕЛЕЙ", "методика рекордная",
        [("База", "тот же лок"), ("Current Limiter", "off"), ("Термальный порог", "200"),
         ("Методика", "single-pass в BenchMate"), ("Результат", "лучший из нескольких попыток")],
        "поэтому это потолок, а не ещё одна ступень", C_ANL)

def s16():
    im, d = canvas()
    text(d, (120, 100), "АНЛИМ — ПОТОЛОК", 56, C_ANL, bold=True)
    ladder(d, 120, 300, 1200, 560, STEPS_E, 4, anchor=None)
    plate(d, (1400, 300), "+301 к локу", 40, bg=C_ANL, fg=(20, 20, 20))
    text(d, (1400, 400), "5671 МГц против 5557", 30, INK, bold=True)
    text(d, (1400, 460), "79° против 83,6° — но single-pass короче,", 24, MUT)
    text(d, (1400, 492), "температуру в заслугу профилю не пишем", 24, MUT)
    return save(im, "s16_anl.png")

def s17():
    im, d = canvas()
    text(d, (120, 100), "ЛИЧНЫЙ ПОТОЛОК ЭТОГО ЭКЗЕМПЛЯРА", 56, INK, bold=True)
    text(d, (120, 180), "наша вода · эта сессия · не мировой рекорд", 32, MUT)
    # схема поля HWBot: точки, наша обведена, выше есть другие
    d.rounded_rectangle([120, 280, 1800, 820], radius=16, fill=(24, 25, 29), outline=LINE, width=3)
    text(d, (160, 310), "HWBot · Cinebench R23 · вода · дата в кадре", 28, MUT, bold=True)
    import random
    random.seed(7)
    for i in range(28):
        x = 260 + random.randint(0, 1400); y = 420 + random.randint(0, 320)
        d.ellipse([x, y, x + 14, y + 14], fill=(90, 92, 98))
    for x, y in ((520, 400), (760, 380), (1120, 415)):
        d.ellipse([x, y, x + 14, y + 14], fill=(150, 152, 160))
    ox, oy = 900, 470
    d.ellipse([ox, oy, ox + 18, oy + 18], fill=C_ANL)
    d.ellipse([ox - 14, oy - 14, ox + 32, oy + 32], outline=C_ANL, width=4)
    text(d, (ox + 44, oy - 8), "мы — 48 880", 32, INK, bold=True)
    text(d, (160, 770), "выше есть другие — проверяется за минуту. Кремниевая лотерея: ваш чип другой, пишите свои цифры в комменты", 26, MUT)
    return save(im, "s17_hwbot.png")

def s18():
    im, d = canvas()
    text(d, (960, 380), "АНЛИМ — СЕССИЯ, НЕ ДЕЙЛИ", 84, ACC, bold=True, anchor="ma")
    text(d, (960, 540), "24/7 на этом — прямой путь к деградации", 44, INK, anchor="ma")
    text(d, (960, 660), "[монтаж: мем «проц в микроволновке» из второй серии]", 28, MUT, anchor="ma")
    return save(im, "s18_session.png")

def s19():
    im, d = canvas()
    text(d, (120, 100), "ЛЕСТНИЦА НА ФЛАГМАНЕ ЦЕЛИКОМ", 56, INK, bold=True)
    ladder(d, 120, 300, 1200, 560, STEPS_E, 4, anchor=None)
    plate(d, (1400, 340), "+15,9%", 72, bg=ACC)
    text(d, (1400, 500), "от стока до потолка", 32, MUT)
    text(d, (1400, 560), "из одного куска кремния", 32, MUT)
    return save(im, "s19_ladder_full.png")

# ---- 17: переезд ----
def s20():
    im, d = canvas()
    text(d, (120, 150), "ТА ЖЕ ЛЕСТНИЦА", 92, INK, bold=True)
    text(d, (120, 270), "B650-A GAMING WIFI · ×4 ДЕШЕВЛЕ", 92, ACC, bold=True)
    text(d, (120, 430), "тот же кристалл · тот же контур · та же память", 40, MUT)
    ladder(d, 120, 560, 900, 380, STEPS_B, 0, anchor=None)
    text(d, (1200, 700), "по логике страха сейчас", 36, MUT)
    text(d, (1200, 750), "всё должно посыпаться", 36, MUT)
    return save(im, "s20_b650_intro.png")

# ---- 18-22: очная ставка ----
def s21():
    return split_slide("s21_b650_stock.png", "СТОК: −2,2%", "РАВНЫ · ПИТАНИЕ НЕ ЛИМИТЕР", GREEN,
        ("Extreme", 42181, C_STOCK), ("B650", 41234, (100, 100, 104)),
        [("Пакет", "200 Вт", "200 Вт", 0), ("Температура", "61°", "60°", 0),
         ("CS2 avg / low", "971 / 248", "949 / 242", -1), ("КП сред / мин", "225 / 189", "226 / 193", 0)],
        "в контре на стоке впереди как раз дорогая — чтобы вы нас потом не поймали в комментах")

def s22():
    return split_slide("s22_b650_pbo.png", "ПБО: +0,3% У ДЕШЁВОЙ", "НИЧЬЯ · В КОНТРЕ ДЕШЁВАЯ ВПЕРЕДИ", GREEN,
        ("Extreme", 46500, C_PBO), ("B650", 46642, (36, 98, 181)),
        [("CS2 avg / low", "1023 / 266", "1116 / 322", 1), ("КП сред / мин", "228 / 196", "226 / 196", 0)],
        "1116 — лучший средний fps всего ролика: плата за четверть цены, автопрофиль, полный набор ядер")

def s23():
    return split_slide("s23_b650_lok.png", "ЛОК: −5,1%", "СТРАХ НАСТОЯЩИЙ · САМЫЙ БОЛЬШОЙ РАЗРЫВ", ACC,
        ("Extreme", 48579, C_LOK), ("B650", 46117, (120, 30, 40)),
        [("R23", "48 579 / 48 189", "46 117", -1), ("от повтора", "", "−4,3%", 0),
         ("КП сред / мин", "235 / 201", "224 / 193", -1), ("CS2 avg / low", "980 / 247", "1006 / 258", 1)],
        "во что упёрлась — вскроем через минуту. Даже здесь в контре впереди дешёвая")

def s24():
    return split_slide("s24_b650_anl.png", "АНЛИМ: −2,9%", "РАЗРЫВ СЖАЛСЯ ПОЧТИ ВДВОЕ (был −5,1%)", YELL,
        ("Extreme", 48880, C_ANL), ("B650", 47439, (150, 125, 40)),
        [("конфиг B650", "", "5450 all-core", 0), ("Пакет / T°", "—", "308 Вт / 85°", 0),
         ("к своему локу", "+301", "+1322", 1), ("игры Extreme", "не мерено", "", 0)],
        "Extreme · Анлим · полный чип · игры — не мерено (плашка, не бар)")

def s25():
    im, d = canvas()
    text(d, (120, 110), "ИГРЫ НА АНЛИМЕ · B650", 64, C_ANL, bold=True)
    rows = [("CS2 avg / low", "1088 / 314", "ниже своего ПБО", ACC), ("Киберпанк сред / мин", "233 / 200", "выше своего лока", GREEN)]
    for k, (a, b, m, c) in enumerate(rows):
        y = 300 + k * 200
        d.rounded_rectangle([120, y, 1800, y + 160], radius=14, fill=(24, 25, 29), outline=LINE, width=2)
        text(d, (160, y + 30), a, 40, MUT); text(d, (1200, y + 20), b, 72, INK, bold=True)
        text(d, (160, y + 96), m, 30, c, bold=True)
    text(d, (120, 780), "Снова разные профили везут разное.", 48, INK, bold=True)
    return save(im, "s25_b650_anl_games.png")

# ---- 23-24: две лестницы, payoff ----
def s26():
    im, d = canvas()
    text(d, (120, 90), "ДВЕ ЛЕСТНИЦЫ", 56, INK, bold=True)
    ladder(d, 120, 280, 780, 520, STEPS_E, 4, anchor=None)
    ladder(d, 1010, 280, 780, 520, STEPS_B, 4, anchor=None)
    plate(d, (330, 190), "Extreme · +15,9%", 34, bg=(34, 35, 40))
    plate(d, (1220, 190), "B650 · +15,0%", 34, bg=(34, 35, 40))
    text(d, (960, 960), "разница в пределах процента: настройка даёт дешёвой практически столько же", 32, MUT, anchor="ma")
    return save(im, "s26_two_ladders.png")

def s27():
    im, d = canvas()
    text(d, (480, 300), "47 439", 150, INK, bold=True, anchor="ma")
    text(d, (480, 500), "B650 · анлим · ручной профиль", 34, MUT, anchor="ma")
    text(d, (480, 560), "плата за четверть цены", 34, MUT, anchor="ma")
    text(d, (960, 380), ">", 110, ACC, bold=True, anchor="ma")
    text(d, (1440, 300), "46 500", 150, MUT, bold=True, anchor="ma")
    text(d, (1440, 500), "Extreme · ПБО · автопрофиль", 34, MUT, anchor="ma")
    text(d, (1440, 560), "флагман, которому развязали руки", 34, MUT, anchor="ma")
    text(d, (960, 800), "на пару процентов, но обгоняет · в дейли-профилях равны: 46 642 против 46 500", 32, INK, anchor="ma")
    return save(im, "s27_payoff.png")

# ---- 25-28: вскрытие ----
def hw_rows(d, rows, y0):
    for k, (a, b, c) in enumerate(rows):
        y = y0 + k * 96
        d.rounded_rectangle([120, y, 1800, y + 76], radius=10, fill=(24, 25, 29), outline=LINE, width=2)
        text(d, (160, y + 18), a, 32, MUT); text(d, (1760, y + 14), b, 38, c, bold=True, anchor="ra")

def s28():
    im, d = canvas()
    text(d, (120, 100), "ВСКРЫТИЕ: HWiNFO С ТОГО САМОГО ПРОГОНА", 52, INK, bold=True)
    text(d, (120, 175), "инфографика по показаниям · B650 · лок", 28, MUT)
    hw_rows(d, [("HTC / PROCHOT (троттлинг)", "нет", GREEN), ("Thermal limit", "83% — до порога далеко", GREEN),
                ("Кристалл", "79°", GREEN), ("Vcore max", "1,290 — в норме", GREEN),
                ("FCLK", "2167 против 2133 у Extreme — память ни при чём", GREEN),
                ("Датчик VRM", "не писали — про нагрев платы не говорим", MUT)], 260)
    return save(im, "s28_hwinfo.png")

def s29():
    im, d = canvas()
    text(d, (120, 100), "А ВОТ ЭТО — ДА", 52, ACC, bold=True)
    hw_rows(d, [("EDC", "95,4% — под самый лимит", ACC), ("Пакет", "281 Вт (пик 290) против 325 у Extreme", ACC)], 260)
    text(d, (120, 560), "Плата не упирается в температуру.", 48, INK, bold=True)
    text(d, (120, 640), "Судя по этому скрину — ей не хватает тока.", 48, ACC, bold=True)
    return save(im, "s29_edc.png")

def s30():
    im, d = canvas()
    text(d, (120, 100), "С ВЫВОДОМ ОСТОРОЖНО: ГДЕ МЕРИЛИ", 52, INK, bold=True)
    cols = ["ЛОК", "АНЛИМ"]; rows = ["B650", "Extreme"]
    x0, y0, cw, ch = 420, 280, 460, 220
    for j, c in enumerate(cols): text(d, (x0 + cw * j + cw // 2, y0 - 60), c, 36, MUT, bold=True, anchor="ma")
    for i, r in enumerate(rows): text(d, (x0 - 40, y0 + ch * i + ch // 2 - 20), r, 36, MUT, bold=True, anchor="ra")
    for i in range(2):
        for j in range(2):
            filled = (i == 0 and j == 0)
            d.rounded_rectangle([x0 + cw * j + 10, y0 + ch * i + 10, x0 + cw * (j + 1) - 10, y0 + ch * (i + 1) - 10],
                                radius=14, fill=(24, 60, 36) if filled else (24, 25, 29), outline=GREEN if filled else LINE, width=4 if filled else 2)
            text(d, (x0 + cw * j + cw // 2, y0 + ch * i + ch // 2 - 24), "есть скрин" if filled else "не мерили", 34, GREEN if filled else LINE, bold=True, anchor="ma")
    text(d, (120, 800), "гипотеза с одним скрином, не теорема · стенд описан полностью — повторяйте", 32, MUT)
    return save(im, "s30_matrix.png")

def s31():
    im, d = canvas()
    text(d, (120, 100), "ЛОК → АНЛИМ: КТО СКОЛЬКО ОТЫГРАЛ", 52, INK, bold=True)
    for k, (lab, val, wpx, col) in enumerate([("B650", "+1322", 1300, YELL), ("Extreme", "+301", 300, C_ANL)]):
        y = 320 + k * 200
        text(d, (160, y - 50), lab, 36, MUT, bold=True)
        d.rounded_rectangle([160, y, 160 + wpx, y + 90], radius=12, fill=col)
        text(d, (180 + wpx, y + 18), val, 52, INK, bold=True)
    text(d, (120, 800), "похоже, флагману тока хватало и на локе, а дешёвой нет — потому разрыв и сжался", 34, INK, bold=True)
    return save(im, "s31_deltas.png")

# ---- 29-33: контра ----
def s32():
    im, d = canvas()
    text(d, (120, 130), "ТОТ ЖЕ КРИСТАЛЛ ТЕПЕРЬ ИГРАЕТ", 64, INK, bold=True)
    cx, cy = 960, 560
    for i, (lab, on) in enumerate([("CCD0 · кэш", True), ("CCD1 · частота", False)]):
        x = cx - 380 + i * 400
        col = GREEN if on else (60, 62, 68)
        d.rounded_rectangle([x, cy - 140, x + 360, cy + 140], radius=18, fill=(24, 40, 30) if on else (22, 23, 26), outline=col, width=5)
        text(d, (x + 180, cy - 30), lab, 36, col, bold=True, anchor="ma")
        text(d, (x + 180, cy + 40), "живой" if on else "выключен в биосе", 28, col, anchor="ma")
    text(d, (120, 880), "и играет он лучше всего, когда мы выключаем ему половину ядер", 36, MUT)
    return save(im, "s32_cs2_intro.png")

def s33():
    im, d = canvas()
    text(d, (120, 90), "РЕКОРД против ДЕЙЛИ", 56, INK, bold=True)
    cards = [("РЕКОРД", "1093 / 327", ["CCD1 off · SMT off", "Reflex off · кап снят", "пакет 138 Вт"], C_ANL),
             ("ДЕЙЛИ", "955 / 257", ["оба чиплета · SMT on", "Process Lasso → кэш-CCD", "как играем каждый день"], C_PBO)]
    for i, (t_, v, ls, c) in enumerate(cards):
        x = 140 + i * 880
        d.rounded_rectangle([x, 240, x + 800, 800], radius=18, fill=(24, 25, 29), outline=c, width=5)
        text(d, (x + 400, 290), t_, 44, c, bold=True, anchor="ma")
        text(d, (x + 400, 380), v, 96, INK, bold=True, anchor="ma")
        for k, l in enumerate(ls):
            text(d, (x + 400, 560 + k * 60), l, 30, MUT, anchor="ma")
    text(d, (960, 880), "CS2 avg / 0,1% low", 28, MUT, anchor="ma")
    return save(im, "s33_rec_daily.png")

def s34():
    im, d = canvas()
    text(d, (120, 100), "МЕНЬШЕ ЯДЕР — БЫСТРЕЕ", 56, INK, bold=True)
    hw_rows(d, [("Рекорд против дейли", "+14% avg · +27% low", GREEN),
                ("Рекорд против ПБО той же платы", "+7% avg", INK),
                ("Магии нет", "контре не нужен ток — нужен кэш и чтобы не дёргали", MUT)], 280)
    return save(im, "s34_cs2_deltas.png")

def s35():
    im, d = canvas()
    text(d, (120, 100), "ЦЕНА РЕКОРД-РЕЖИМА", 56, INK, bold=True)
    for i, (lab, v, sub, c) in enumerate([("Cinebench в рекорд-режиме", "16 277", "рендер падает втрое", ACC),
                                          ("Cinebench в дейли", "48 500", "полный чип на месте", GREEN)]):
        y = 280 + i * 240
        d.rounded_rectangle([120, y, 1800, y + 190], radius=14, fill=(24, 25, 29), outline=LINE, width=2)
        text(d, (160, y + 40), lab, 36, MUT); text(d, (1200, y + 20), v, 84, INK, bold=True)
        text(d, (160, y + 120), sub, 30, c, bold=True)
    text(d, (120, 800), "Две цифры рядом — выбирайте сами. По низам рекорд выше: 327 против 322 у ПБО B650.", 32, INK)
    return save(im, "s35_fork.png")

def s36():
    im, d = canvas()
    text(d, (960, 340), "ГИПОТЕЗА ЛЁХИ", 84, INK, bold=True, anchor="ma")
    text(d, (960, 480), "игру — на частотный чиплет, фон — на кэшевый. Вопреки всем гайдам", 36, MUT, anchor="ma")
    plate(d, (700, 620), "в отдельном ролике по контре", 40, bg=ACC)
    return save(im, "s36_lyoha.png")

# ---- 34-35: мы проверили и себя ----
def s37():
    im, d = canvas()
    text(d, (120, 100), "МЫ ПРОВЕРИЛИ И СЕБЯ · ПАМЯТЬ", 52, INK, bold=True)
    hw_rows(d, [("8000 CL40 (2:1)", "983 / 243 — и нестабильна", ACC),
                ("6000 CL28 (рабочий сет)", "980 / 247", GREEN),
                ("Разница", "плюс три кадра по среднему, минус четыре по низам", MUT)], 280)
    text(d, (120, 660), "Рабочий сет остаётся.", 48, INK, bold=True)
    return save(im, "s37_mem.png")

def s38():
    im, d = canvas()
    text(d, (120, 100), "КАП ПО FPS · НА ТОЙ ЖЕ 8000", 52, INK, bold=True)
    for k, (lab, val, wpx, col) in enumerate([("низы БЕЗ капа", "243", 1200, GREEN), ("низы С капом fps_max 500", "188", 930, ACC)]):
        y = 300 + k * 200
        text(d, (160, y - 50), lab, 34, MUT, bold=True)
        d.rounded_rectangle([160, y, 160 + wpx, y + 90], radius=12, fill=col)
        text(d, (180 + wpx, y + 18), val, 52, INK, bold=True)
    text(d, (120, 760), "минус двадцать три процента. Сам по себе кап фреймтайм не лечит — проверяйте на своём сете.", 34, INK, bold=True)
    text(d, (120, 830), "на рабочей 6000 кап не гоняли — вывод скромный", 28, MUT)
    return save(im, "s38_cap.png")

# ---- 36-41: итог ----
def s39():
    im, d = canvas()
    plate(d, (350, 90), "ПЛАТА — ДО 5%. БИОС — 15%. НА ОБЕИХ ПЛАТАХ", 44, bg=ACC)
    ladder(d, 120, 300, 760, 480, STEPS_E, 4, anchor=None)
    ladder(d, 1030, 300, 760, 480, STEPS_B, 4, anchor=None)
    verds = [("СТОК", "РАВНЫ", GREEN), ("ПБО", "РАВНЫ", GREEN), ("ЛОК", "−5,1%", ACC), ("АНЛИМ", "−2,9%", YELL)]
    for k, (a, b, c) in enumerate(verds):
        x = 200 + k * 400
        d.rounded_rectangle([x, 920, x + 340, 1000], radius=12, fill=c)
        text(d, (x + 170, 936), "%s · %s" % (a, b), 32, INK if c != YELL else (20, 20, 20), bold=True, anchor="ma")
    return save(im, "s39_final.png")

def s40():
    im, d = canvas()
    text(d, (120, 140), "КОМУ НУЖНА ДОРОГАЯ ПЛАТА", 64, INK, bold=True)
    text(d, (120, 300), "тому, кто вручную выгрызает последние проценты на локе — и знает, зачем", 40, INK)
    text(d, (120, 420), "всем остальным хватит получаса в биосе", 40, ACC, bold=True)
    plate(d, (120, 600), "47 439 у дешёвой с руками  >  46 500 у флагмана на автомате", 40, bg=(34, 35, 40))
    return save(im, "s40_who.png")

def s41():
    im, d = canvas()
    text(d, (120, 100), "ОДНОГО ЛУЧШЕГО ПРОФИЛЯ НЕТ", 56, INK, bold=True)
    rows = [("ПБО", "киберспорт — 1116 в контре; на обеих платах в контре ПБО впереди лока", C_PBO),
            ("ЛОК", "Киберпанк и рендер на флагмане — 235 · 48 579 / 48 189", C_LOK),
            ("АНЛИМ", "счёт Cinebench — 48 880 и 47 439 · сессия · игры на полном чипе не мерены", C_ANL)]
    for k, (a, b, c) in enumerate(rows):
        y = 280 + k * 180
        d.rounded_rectangle([120, y, 1800, y + 140], radius=14, fill=(24, 25, 29), outline=c, width=4)
        text(d, (160, y + 20), a, 48, c, bold=True)
        text(d, (400, y + 44), b, 32, INK)
    return save(im, "s41_table.png")

def s42():
    im, d = canvas()
    text(d, (120, 110), "КОМУ ЧТО", 64, INK, bold=True)
    cards = [("КАЗУАЛУ", "ПБО", "под воздух и AIO и рассчитан — в этой серии их не гоняли", C_PBO),
             ("ЭНТУЗИАСТУ", "ЛОК", "думать за плату самому", C_LOK),
             ("ЛОВЦУ ЦИФРЫ", "АНЛИМ", "на одну сессию, и не дольше", C_ANL)]
    for i, (who, prof, sub, c) in enumerate(cards):
        x = 130 + i * 570
        d.rounded_rectangle([x, 280, x + 530, 800], radius=18, fill=(24, 25, 29), outline=c, width=5)
        text(d, (x + 265, 340), who, 40, MUT, bold=True, anchor="ma")
        text(d, (x + 265, 440), prof, 84, c, bold=True, anchor="ma")
        words, line, yy = sub.split(), "", 620
        dd = ImageDraw.Draw(im)
        for wd in words:
            if dd.textlength(line + " " + wd, font=font(28)) > 470:
                text(d, (x + 265, yy), line, 28, INK, anchor="ma"); yy += 40; line = wd
            else:
                line = (line + " " + wd).strip()
        text(d, (x + 265, yy), line, 28, INK, anchor="ma")
    return save(im, "s42_persona.png")

def s43():
    im, d = canvas()
    text(d, (960, 300), "ГУСЬ ПРОВЕРИЛ — ОЧЕРЕДЬ ВАША", 72, INK, bold=True, anchor="ma")
    text(d, (960, 460), "[монтаж: гусь живьём в кадре, реакция на итоговую таблицу — НЕ рендер]", 30, MUT, anchor="ma")
    plate(d, (560, 600), "полная таблица прогонов и профили BIOS — в Telegram", 40, bg=ACC)
    text(d, (960, 760), "ссылка в описании", 32, MUT, anchor="ma")
    return save(im, "s43_goose.png")

def s44():
    im, d = canvas()
    text(d, (960, 380), "В СЛЕДУЮЩЕЙ СЕРИИ", 52, MUT, bold=True, anchor="ma")
    text(d, (960, 480), "9950X3D В КОНТРЕ ПОД МИКРОСКОПОМ", 72, INK, bold=True, anchor="ma")
    return save(im, "s44_next.png")

if __name__ == "__main__":
    for fn in (s11, s12, s13, s14, s15, s16, s17, s18, s19, s20, s21, s22, s23, s24, s25,
               s26, s27, s28, s29, s30, s31, s32, s33, s34, s35, s36, s37, s38, s39, s40, s41, s42, s43, s44):
        fn()
    print("слайды второй половины готовы")
