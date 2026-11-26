#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Обложка шортса 1080x1920 по спецификации JSON (скил shorts-cover). Стиль сайта и знака с 14.10.2026:
заголовки Tektur, текст Jost, фон чернила #070A12, голубой #58C4FF, ОДНО золотое слово или цифра #E2B256,
знак «Пластина» в подвале. Обобщение docs/scripts/5090-9070xt/cover.py.

На хабе (рендер; playwright живёт в PWPY):
    /opt/hermes/venv/bin/python3 cover.py spec.json [--out DIR] [--fonts DIR]
    -> DIR/cover.jpg (1080x1920, <= 2 МБ), DIR/preview.png (полка 190 px, светлая тема, прищур + обложка в половину),
       DIR/report.json;  DIR по умолчанию /opt/shorts/r5090/cover_skill/<name>/
Локально (только проверки до рендера; stdlib, браузер и шрифты не нужны):
    py -3.12 cover.py spec.json --check
Шрифты: Tektur.ttf и Jost.ttf (shortsmaker/vps/fonts, на хабе /opt/shorts/fonts). Порядок поиска: --fonts,
    $SHORTS_COVER_FONTS, /opt/shorts/fonts, папка fonts/ рядом с cover.py. Нет файлов — ошибка до рендера (код 1).

Раскладка (по умолчанию = обложка «5090 -> 9070 XT» 01.10, все зоны меняются полем box):
    голубая полоса 0-8 · верхняя подпись 44-214 · верхнее фото 215-905 · полоса середины 905-1155 (число 915-1140,
    подпись 1128-1174) · нижнее фото 1215-1700 · нижняя подпись 1700-1850 · подвал со знаком 1862-1906.
Ключи спецификации (пример — examples/5090-9070xt.json):
    name, title (заголовок ролика: виден под миниатюрой в превью), bg, grid; status — пометка для людей, скрипт не читает
    facts        {"script": [fact_gate.json проекта, final.json, ...: первый существующий], "derived": [{"value","expr"}],
                  "names": [..]}; поля source/link внутри сценария не читаются (там весь источник)
    top_label    {"text", "color", "max", "min", "box": [top, height]}
    top_photo    {"src", "origin", "crop": {"x","y","w","h"} или "x:y:w:h", "key_white": {"similarity","blend"} | false,
                  "fit": "contain"|"cover", "position": "50% 50%", "box": [x, y, w, h], "fade": [верх %, низ %]}
    middle       {"big", "color", "max", "min", "box", "caption", "caption_color", "caption_size", "caption_box",
                  "band": "#0D1422" | false, "band_box"}
    bottom_photo как top_photo;  bottom_label как top_label
    note         {"text", "color", "size", "box"} — сноска мелко; без box встаёт в подвал рядом со знаком
    brand        {"logo": "horizontal" | "symbol" | false, "box": [top, height], "bar": true | false} — знак «Пластина»
                  (контуры из work/logo-gspc/kit/svg, живым шрифтом не заменять) и голубая полоса сверху, как у og сайта
    Любой текст — строка или список кусков [["200", "#9FB0C3"], [" → ", "#9FB0C3"], ["600", "#E2B256"]]:
    «было → стало», золото только у одного куска (examples/lok-pbo.json).
Цвета по умолчанию (стиль-библия pc-store/nuxt.config.ts, work/logo-gspc/kit/GUIDE.md): подписи моделей белые #F7FAFC,
    число золотое #E2B256, подпись числа голубая #58C4FF, сноска #9FB0C3, полоса середины #0D1422. Цвета вендоров
    (зелёный NVIDIA, красный AMD, лайм) не вводим: сравнение держат слова и фото.
Внимание: кроп-строка здесь x:y:w:h, а не ffmpeg-порядок w:h:x:y из старого cover.py; надёжнее словарь.

Проверки до рендера (ошибка = стоп, код 2):
    цифры: каждое число на обложке есть в сценарии после фактчекера (fact_gate.json проекта; final.json — вход
           гейта, только запасной), процент — как процент;
           иначе только facts.derived (арифметика чисел сценария: expr считается и сверяется) или facts.names
           (число внутри названия: «Dota 2»); без сценария цифр на обложке нет;
    цены и советы про деньги: рубли, цена, скидка, наличные, выгода, подорожание, «копить/придержать» — стоп
           (no-prices, price-rise); давление и чужие площадки: «купи», «успей», «ниже рыночных», @, ссылки, Авито — стоп;
           «лучший» — предупреждение;
    фото: у каждого поле origin; путь не из генерации (gen/imagine/bank/broll) и не из чужих футажей (/ext/, game);
    знак Авито: кроп снимка витрины (<id>-N.jpg) не заходит в правый нижний угол (та же зона, что в find_photos.py).
Предупреждения до рендера (не стоп): больше 6 слов на обложке (модель = одно слово, сноска не в счёт); цвет вне
    стиль-библии; золото больше чем в одном месте; больше двух красок кроме белого и серого; подпись залезает в подвал.
После рендера (report.json и stdout):
    подписи в одну строку: кегль подбирается от max вниз по ширине зоны; ниже min — ошибка «сократить текст» (код 1);
    кегль на полке = кегль x 190/1080; главные надписи мельче 17 px на полке — предупреждение;
    предмет на фото: доля своей зоны (по альфа-рамке после выреза белого); меньше 70% по обеим осям — «фото мелкое»;
    шрифты: Tektur и Jost должны загрузиться (иначе ошибка, код 1);
    jpg <= 2 000 000 байт (YouTube и ВК; ВК берёт от 720x1280), качество снижается ступенями.
"""
import argparse
import glob
import html
import json
import os
import re
import struct
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

W, H = 1080, 1920
SHELF = 190
MAX_BYTES = 2_000_000
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIRS = ["/opt/shorts/fonts", os.path.join(HERE, "fonts")]
FONT_FILES = ("Tektur.ttf", "Jost.ttf")
SHELF_MIN = 17          # px кегля на полке для главных надписей
FILL_MIN = 0.70         # доля зоны, которую должен занимать предмет хотя бы по одной оси
WORDS_MAX = 6           # слов на обложке (модель = одно слово, сноска не в счёт): больше — предупреждение
SQUINT_SIGMA = 3        # тест прищура: плитка 190 px с размытием gblur

# Стиль-библия (pc-store/nuxt.config.ts, work/logo-gspc/kit/GUIDE.md). Новые цвета не вводить.
INK, SURFACE, PAPER, MUTED = "#070A12", "#0D1422", "#F7FAFC", "#9FB0C3"
AZURE, GOLD, DIM = "#58C4FF", "#E2B256", "#2A3A52"
PALETTE = {INK, SURFACE, PAPER, MUTED, AZURE, GOLD, DIM}
NEUTRAL = {INK, SURFACE, PAPER, MUTED, DIM}

DEFAULTS = {
    "bg": INK,
    "top_label": {"box": [44, 170], "max": 190, "min": 90, "color": PAPER},
    "top_photo": {"box": [90, 215, 900, 690], "fit": "contain"},
    "middle": {"box": [915, 225], "max": 250, "min": 90, "color": GOLD, "caption_box": [1128, 46], "caption_size": 44,
               "caption_color": AZURE, "band": SURFACE, "band_box": [905, 250]},
    "bottom_photo": {"box": [0, 1215, 1080, 485], "fit": "cover"},
    "bottom_label": {"box": [1700, 150], "max": 165, "min": 90, "color": PAPER},
    "note": {"size": 28, "color": MUTED},
    "brand": {"logo": "horizontal", "box": [1862, 44], "bar": True},
}
PHOTO_DENY = ("/ext/", "/gen/", "imagine", "bank", "broll", "game_", "/footage", "/env_")
MONEY = re.compile(r"₽|€|\bруб|\bтыс\.?\s*₽|\bцен[аеуыо]|\bдешев|\bдорож|подорож|скидк|налич|выгод|\bдолл|"
                   r"\bкопи(ть|те)|придерж|пока не (подорож|вырос)|\$\s*\d|\d\s*\$", re.I)
PUSH = re.compile(r"\bкупи|\bуспе(й|йте|ть)\b|ниже рыночн|@|https?://|\bt\.me\b|\bwww\.|\bavito|\bавито", re.I)
BEST = re.compile(r"\bлучш", re.I)
# --out на хабе: только своя рабочая папка, прод-папки /opt/shorts не трогаем
OUT_OK = re.compile(r"^(/tmp/[^/].*|/opt/shorts/[^/]+/cover_skill(/.*)?)$")
NUM = re.compile(r"\d+(?:[.,]\d+)?")
STORE_PHOTO = re.compile(r"(^|/)\d{9,11}-\d+\.(jpe?g|png|webp)$", re.I)
LOCAL_BUILDS = os.path.join(os.environ.get("GSPC_ROOT", r"C:/Users/Administrator/Documents/git"),
                            "pc-store", "public", "builds")
# название модели или технологии читается одним словом: «RX 9070 XT», «DLSS 5», «Ryzen 7 9850X3D»
PRODUCT = re.compile(r"\b(?:RTX|GTX|RX|Arc|DLSS|FSR|XeSS|Ryzen\s?\d|Core\s?Ultra\s?\d|Core\s?i\d)\s?[A-Z]?\d{1,4}"
                     r"[A-Z0-9]*(?:\s?(?:Ti|Super|XTX|XT|GRE))?\b|\b\d{4}X3D\d?\b", re.I)

# Знак «Пластина», контуры: копии work/logo-gspc/kit/svg (gspc-horizontal-on-dark.svg, gspc-symbol-on-dark.svg,
# 14.10.2026). Не красить, не растягивать, без теней; сменился знак в ките — перекопировать сюда и в publish_pack.py.
LOGO_H = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1726 256"><title>Golden Sample PCs</title><path fill="#58C4FF" d="M242.64 86.27A122 122 0 1 1 169.73 13.36L163.57 30.27A104 104 0 1 0 225.73 92.43ZM67 64H97A3 3 0 0 1 100 67V97A3 3 0 0 1 97 100H67A3 3 0 0 1 64 97V67A3 3 0 0 1 67 64ZM113 64H143A3 3 0 0 1 146 67V97A3 3 0 0 1 143 100H113A3 3 0 0 1 110 97V67A3 3 0 0 1 113 64ZM67 110H97A3 3 0 0 1 100 113V143A3 3 0 0 1 97 146H67A3 3 0 0 1 64 143V113A3 3 0 0 1 67 110ZM113 110H143A3 3 0 0 1 146 113V143A3 3 0 0 1 143 146H113A3 3 0 0 1 110 143V113A3 3 0 0 1 113 110ZM159 110H189A3 3 0 0 1 192 113V143A3 3 0 0 1 189 146H159A3 3 0 0 1 156 143V113A3 3 0 0 1 159 110ZM67 156H97A3 3 0 0 1 100 159V189A3 3 0 0 1 97 192H67A3 3 0 0 1 64 189V159A3 3 0 0 1 67 156ZM113 156H143A3 3 0 0 1 146 159V189A3 3 0 0 1 143 192H113A3 3 0 0 1 110 189V159A3 3 0 0 1 113 156ZM159 156H189A3 3 0 0 1 192 159V189A3 3 0 0 1 189 192H159A3 3 0 0 1 156 189V159A3 3 0 0 1 159 156Z"/><path fill="#E2B256" d="M187 36H217A3 3 0 0 1 220 39V69A3 3 0 0 1 217 72H187A3 3 0 0 1 184 69V39A3 3 0 0 1 187 36Z"/><path fill="#F7FAFC" d="M350.04 174.20L333.94 158.10L333.94 97.90L350.04 81.80L401.52 81.80L401.52 101.07L356.12 101.07L356.12 154.93L387.53 154.93L387.53 135.92L368.26 135.92L368.26 118.36L407.07 118.36L407.07 174.20L350.04 174.20ZM440.33 174.20L424.23 158.10L424.23 97.90L440.33 81.80L486.00 81.80L502.11 97.90L502.11 158.10L486.00 174.20L440.33 174.20ZM479.14 101.07L447.20 101.07L447.20 154.93L479.14 154.93L479.14 101.07ZM586.19 174.20L519.66 174.20L519.66 81.80L541.84 81.80L541.84 155.72L566.66 155.72L566.66 137.24L586.19 137.24L586.19 174.20ZM623.55 101.07L623.55 154.93L650.74 154.93L650.74 101.07L623.55 101.07ZM656.81 174.20L601.37 174.20L601.37 81.80L656.81 81.80L672.92 97.90L672.92 158.10L656.81 174.20ZM756.74 174.20L690.47 174.20L690.47 81.80L755.42 81.80L755.42 100.28L712.65 100.28L712.65 118.23L748.82 118.23L748.82 135.92L712.65 135.92L712.65 155.72L756.74 155.72L756.74 174.20ZM792.90 174.20L772.31 174.20L772.31 81.80L793.30 81.80L828.81 140.54L828.81 81.80L849.40 81.80L849.40 174.20L828.41 174.20L792.90 115.46L792.90 174.20ZM963.84 174.20L907.88 174.20L907.88 154.93L956.98 154.93L956.98 137.64L906.56 133.28L906.56 97.11L921.87 81.80L977.84 81.80L977.84 101.07L928.73 101.07L928.73 117.04L979.16 121.40L979.16 158.89L963.84 174.20ZM1015.32 174.20L991.83 174.20L1012.16 81.80L1055.19 81.80L1075.52 174.20L1052.02 174.20L1048.19 154.40L1019.15 154.40L1015.32 174.20ZM1029.58 99.36L1021.92 138.43L1045.42 138.43L1037.76 99.36L1029.58 99.36ZM1110.36 174.20L1088.58 174.20L1088.58 81.80L1115.25 81.80L1133.73 121.14L1152.21 81.80L1178.87 81.80L1178.87 174.20L1157.09 174.20L1157.09 110.05L1138.48 148.33L1128.98 148.33L1110.36 110.05L1110.36 174.20ZM1219 99.49L1219 136.71L1247.25 136.71L1247.25 99.49L1219 99.49ZM1253.32 81.80L1269.42 97.90L1269.42 138.30L1253.32 154.40L1219 154.40L1219 174.20L1196.82 174.20L1196.82 81.80L1253.32 81.80ZM1351.26 174.20L1284.74 174.20L1284.74 81.80L1306.91 81.80L1306.91 155.72L1331.73 155.72L1331.73 137.24L1351.26 137.24L1351.26 174.20ZM1432.71 174.20L1366.44 174.20L1366.44 81.80L1431.39 81.80L1431.39 100.28L1388.62 100.28L1388.62 118.23L1424.79 118.23L1424.79 135.92L1388.62 135.92L1388.62 155.72L1432.71 155.72L1432.71 174.20Z"/><path fill="#58C4FF" d="M1498.71 92.36L1498.71 143.84L1543.59 143.84L1543.59 92.36L1498.71 92.36ZM1544.91 81.80L1555.47 92.36L1555.47 143.84L1544.91 154.40L1498.71 154.40L1498.71 174.20L1486.83 174.20L1486.83 81.80L1544.91 81.80ZM1581.87 174.20L1571.31 163.64L1571.31 92.36L1581.87 81.80L1630.71 81.80L1630.71 92.62L1583.19 92.62L1583.19 163.38L1632.03 163.38L1632.03 174.20L1581.87 174.20ZM1699.08 174.20L1645.89 174.20L1645.89 163.64L1698.69 163.64L1698.69 141.86L1645.89 141.86L1645.89 112.16L1657.77 100.28L1710.57 100.28L1710.57 110.84L1657.77 110.84L1657.77 131.30L1710.57 131.30L1710.57 162.72L1699.08 174.20Z"/></svg>'
LOGO_S = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><title>Golden Sample PCs</title><path fill="#58C4FF" d="M242.64 86.27A122 122 0 1 1 169.73 13.36L163.57 30.27A104 104 0 1 0 225.73 92.43ZM67 64H97A3 3 0 0 1 100 67V97A3 3 0 0 1 97 100H67A3 3 0 0 1 64 97V67A3 3 0 0 1 67 64ZM113 64H143A3 3 0 0 1 146 67V97A3 3 0 0 1 143 100H113A3 3 0 0 1 110 97V67A3 3 0 0 1 113 64ZM67 110H97A3 3 0 0 1 100 113V143A3 3 0 0 1 97 146H67A3 3 0 0 1 64 143V113A3 3 0 0 1 67 110ZM113 110H143A3 3 0 0 1 146 113V143A3 3 0 0 1 143 146H113A3 3 0 0 1 110 143V113A3 3 0 0 1 113 110ZM159 110H189A3 3 0 0 1 192 113V143A3 3 0 0 1 189 146H159A3 3 0 0 1 156 143V113A3 3 0 0 1 159 110ZM67 156H97A3 3 0 0 1 100 159V189A3 3 0 0 1 97 192H67A3 3 0 0 1 64 189V159A3 3 0 0 1 67 156ZM113 156H143A3 3 0 0 1 146 159V189A3 3 0 0 1 143 192H113A3 3 0 0 1 110 189V159A3 3 0 0 1 113 156ZM159 156H189A3 3 0 0 1 192 159V189A3 3 0 0 1 189 192H159A3 3 0 0 1 156 189V159A3 3 0 0 1 159 156Z"/><path fill="#E2B256" d="M187 36H217A3 3 0 0 1 220 39V69A3 3 0 0 1 217 72H187A3 3 0 0 1 184 69V39A3 3 0 0 1 187 36Z"/></svg>'
LOGO_RATIO = {"horizontal": 1726 / 256, "symbol": 1.0}


# ---------------------------------------------------------------- общие мелочи

def furl(p):
    """file://-адрес: на хабе путь /opt/... -> file:///opt/..., на Windows C:\\... -> file:///C:/... (локальная проба)."""
    p = p.replace("\\", "/")
    return "file://" + (p if p.startswith("/") else "/" + p)


def find_fonts(explicit=None):
    dirs = [d for d in (explicit, os.environ.get("SHORTS_COVER_FONTS")) if d] + FONT_DIRS
    for d in dirs:
        if all(os.path.exists(os.path.join(d, f)) for f in FONT_FILES):
            return d, dirs
    return None, dirs


def avito_zone(w, h):
    """Левый верхний угол зоны знака Авито (правый нижний угол снимка витрины). Та же формула в find_photos.py."""
    return w - max(round(0.14 * w), 140), h - max(round(0.08 * h), 70)


def exif_orientation(data):
    i = data.find(b"Exif\x00\x00")
    if i < 0:
        return 1
    t = data[i + 6:]
    try:
        end = "<" if t[:2] == b"II" else ">"
        off = struct.unpack(end + "I", t[4:8])[0]
        n = struct.unpack(end + "H", t[off:off + 2])[0]
        for k in range(n):
            e = off + 2 + 12 * k
            if struct.unpack(end + "H", t[e:e + 2])[0] == 0x0112:
                return struct.unpack(end + "H", t[e + 8:e + 10])[0]
    except Exception:
        pass
    return 1


def dims(path):
    """(ширина, высота) с поворотом EXIF — так кадр видят ffmpeg и браузер. stdlib, JPEG и PNG."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        m = data[i + 1]
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        ln = struct.unpack(">H", data[i + 2:i + 4])[0]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            if exif_orientation(data[:i]) in (5, 6, 7, 8):
                w, h = h, w
            return w, h
        i += 2 + ln
    return None


def merged(spec, key):
    d = dict(DEFAULTS.get(key, {}))
    v = spec.get(key)
    if isinstance(v, dict):
        d.update(v)
    elif v is False:
        d["off"] = True
    return d


def parse_crop(c):
    if not c:
        return None
    if isinstance(c, dict):
        return int(c["x"]), int(c["y"]), int(c["w"]), int(c["h"])
    x, y, w, h = [int(v) for v in str(c).split(":")]
    return x, y, w, h


def resolve(base, p):
    return p if os.path.isabs(p) or p.startswith("/") else os.path.normpath(os.path.join(base, p))


def segments(t, color):
    """Текст — строка или список кусков [текст, цвет] / {"text","color"}: «200 → 600», золото у одного куска."""
    if isinstance(t, list):
        out = []
        for s in t:
            if isinstance(s, dict):
                out.append((str(s.get("text", "")), s.get("color") or color))
            else:
                out.append((str(s[0]), s[1] if len(s) > 1 and s[1] else color))
        return out
    return [(str(t), color)]


def plain(t):
    return "".join(s for s, _ in segments(t, None))


TEXT_FIELDS = (("top_label", "text", "color"), ("middle", "big", "color"), ("middle", "caption", "caption_color"),
               ("bottom_label", "text", "color"), ("note", "text", "color"))


def texts_of(spec):
    out = []
    for key, field, _ in TEXT_FIELDS:
        t = (spec.get(key) or {}).get(field)
        if t:
            out.append(("%s.%s" % (key, field), plain(t)))
    return out


def words(t):
    """Слова для лимита обложки: модель или технология («RX 9070 XT», «DLSS 5») — одно слово; знаки (→ + ·) не слова."""
    return [w for w in re.split(r"\s+", PRODUCT.sub("M", t.replace("\u00a0", " "))) if re.search(r"\w", w)]


SKIP_KEYS = ("source", "source_text", "link", "url")   # fact_gate.json несёт весь источник: его числа не в счёт


def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            if k not in SKIP_KEYS:
                yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)


def norm(n):
    n = n.replace(",", ".")
    return n.rstrip("0").rstrip(".") if "." in n else n


# ---------------------------------------------------------------- проверки до рендера

def check_facts(spec, base, errors, notes):
    facts = spec.get("facts") or {}
    cover_nums = [(where, m) for where, t in texts_of(spec) for m in NUM.finditer(t)]
    names = " | ".join(facts.get("names") or [])
    script_path = None
    for cand in ([facts["script"]] if isinstance(facts.get("script"), str) else facts.get("script") or []):
        p = resolve(base, cand)
        if os.path.exists(p):
            script_path = p
            break
    if not cover_nums:
        notes.append("цифры: на обложке чисел нет")
        return
    if not script_path:
        errors.append("цифры: на обложке есть числа, а сценария (facts.script) не нашёл — цифры только из сценария "
                      "после фактчекера (fact_gate.json проекта)")
        return
    with open(script_path, encoding="utf-8") as f:
        script = "\n".join(strings(json.load(f)))
    have = {}
    for m in NUM.finditer(script):
        tail = script[m.end():m.end() + 12].lstrip()
        have.setdefault(norm(m.group()), set()).add("%" if tail.startswith("%") or tail.lower().startswith("процент")
                                                    else "")
    derived = {norm(str(d["value"])): d for d in facts.get("derived") or []}
    notes.append("цифры: сценарий %s%s" % (script_path, "" if os.path.basename(script_path) == "fact_gate.json"
                 else " (не fact_gate.json: годится, если гейт реплики с цифрами не правил)"))
    for where, m in cover_nums:
        t = dict(texts_of(spec))[where]
        n = norm(m.group())
        is_pct = t[m.end():].lstrip().startswith("%")
        if n in have and (not is_pct or "%" in have[n]):
            notes.append("цифры: %s%s (%s) есть в сценарии" % (m.group(), "%" if is_pct else "", where))
            continue
        if n in derived:
            expr = str(derived[n].get("expr", ""))
            if not re.fullmatch(r"[0-9.\s()+\-*/]+", expr):
                errors.append("цифры: derived %s — expr только из чисел и + - * / ( )" % n)
                continue
            bad = [x for x in NUM.findall(expr) if norm(x) not in have]
            val = eval(expr, {"__builtins__": {}}, {})  # noqa: S307 — только цифры и знаки, проверено выше
            if bad:
                errors.append("цифры: %s выведено из %s, а их нет в сценарии" % (n, ", ".join(bad)))
            elif abs(round(val) - float(n)) > 0.5 and abs(val - float(n)) > 0.05:
                errors.append("цифры: %s = %s даёт %.2f, не %s" % (n, expr, val, n))
            else:
                notes.append("цифры: %s = %s = %.1f (арифметика чисел сценария)" % (m.group(), expr, val))
            continue
        if names and re.search(r"(?<![0-9])" + re.escape(m.group()) + r"(?![0-9])", names):
            notes.append("цифры: %s — часть названия из facts.names (%s)" % (m.group(), names))
            continue
        errors.append("цифры: %s%s (%s) нет в сценарии %s" % (m.group(), "%" if is_pct else "", where,
                                                               os.path.basename(script_path)))


def check_money(spec, errors, notes):
    for where, t in texts_of(spec) + [("title", spec.get("title") or "")]:
        if t and MONEY.search(t):
            errors.append("деньги: «%s» (%s) — на обложке ни цен, ни скидок, ни советов про покупку" % (t, where))
        if t and PUSH.search(t):
            errors.append("давление/площадки: «%s» (%s) — без «купи/успей», ссылок, @ и названий площадок" % (t, where))
        elif t and BEST.search(t):
            notes.append("ПРЕДУПРЕЖДЕНИЕ %s: «%s» — превосходная степень; годится, только если это замер из сценария"
                         % (where, t))


def check_photo(key, ph, base, errors, notes, local):
    src = ph.get("src")
    if not src:
        return None
    src = resolve(base, src)
    if not ph.get("origin"):
        errors.append("%s: нет поля origin (откуда снимок: pc-store <id> или фото клиента)" % key)
    low = src.replace("\\", "/").lower()
    bad = [d for d in PHOTO_DENY if d in low]
    if bad:
        errors.append("%s: %s — путь похож на генерацию или чужой ролик (%s); на обложку только настоящие фото"
                      % (key, src, ", ".join(bad)))
    path = src
    if local and not os.path.exists(path):
        alt = os.path.join(LOCAL_BUILDS, os.path.basename(src))
        path = alt if os.path.exists(alt) else None
    wh = dims(path) if path and os.path.exists(path) else None
    crop = parse_crop(ph.get("crop"))
    if not wh:
        (notes if local else errors).append("%s: не прочитал размеры %s%s" % (
            key, src, " — кроп и знак Авито проверит запуск на хабе" if local else ""))
        return None
    x, y, w, h = crop or (0, 0, wh[0], wh[1])
    if x < 0 or y < 0 or x + w > wh[0] or y + h > wh[1]:
        errors.append("%s: кроп x=%d y=%d w=%d h=%d выходит за снимок %dx%d (порядок x:y:w:h, не ffmpeg w:h:x:y)"
                      % (key, x, y, w, h, wh[0], wh[1]))
    if STORE_PHOTO.search(low):
        zx, zy = avito_zone(*wh)
        if x + w > zx and y + h > zy:
            errors.append("%s: кроп заходит в угол знака Авито (x>=%d и y>=%d на снимке %dx%d) — срезать, не замазывать"
                          % (key, zx, zy, wh[0], wh[1]))
        else:
            notes.append("%s: знак Авито вне кропа (зона x>=%d, y>=%d)" % (key, zx, zy))
    return wh


def check_style(spec, notes):
    """Стиль сайта: не больше 6 слов, две краски (голубой + одно золото), цвета только из стиль-библии, подвал свободен."""
    counted = [(where, t) for where, t in texts_of(spec) if where != "note.text"]
    n = sum(len(words(t)) for _, t in counted)
    detail = ", ".join("%s %d" % (where.split(".")[0] if where != "middle.caption" else "подпись", len(words(t)))
                       for where, t in counted)
    if n > WORDS_MAX:
        notes.append("ПРЕДУПРЕЖДЕНИЕ слова: на обложке %d слов (%s) — больше %d в плитке не читается; модель = одно "
                     "слово, сноска не в счёт" % (n, detail, WORDS_MAX))
    else:
        notes.append("слова: %d из %d (%s)" % (n, WORDS_MAX, detail))
    used = []                               # (где, цвет) у текстов, с цветами по умолчанию
    for key, field, ckey in TEXT_FIELDS:
        part = spec.get(key) or {}
        if not part.get(field):
            continue
        default = merged(spec, key).get(ckey)
        for s, c in segments(part[field], part.get(ckey) or default):
            if s.strip():
                used.append(("%s.%s «%s»" % (key, field, s.strip()), (c or "").upper()))
    md = merged(spec, "middle")
    other = []                              # фон проверяется отдельной строкой ниже
    if md.get("band") and not md.get("off"):
        other.append(("middle.band", str(md["band"]).upper()))
    for where, c in used + other:
        if c and c not in PALETTE:
            notes.append("ПРЕДУПРЕЖДЕНИЕ цвет: %s (%s) — вне стиль-библии; чернила %s, белый %s, серый %s, голубой %s, "
                         "золото %s (одно), полоса %s" % (c, where, INK, PAPER, MUTED, AZURE, GOLD, SURFACE))
    if str(spec.get("bg") or INK).upper() != INK:
        notes.append("ПРЕДУПРЕЖДЕНИЕ фон %s — фон обложки чернила %s" % (spec.get("bg"), INK))
    gold = [where for where, c in used if c == GOLD]
    if len(gold) > 1:
        notes.append("ПРЕДУПРЕЖДЕНИЕ золото: %d места (%s) — золото одно: цифра или слово-вердикт" % (
            len(gold), "; ".join(gold)))
    elif not gold:
        notes.append("золото: нет — акцент обложки (цифра или слово-вердикт) обычно золотом %s" % GOLD)
    accents = sorted({c for _, c in used if c not in NEUTRAL})
    if len(accents) > 2:
        notes.append("ПРЕДУПРЕЖДЕНИЕ краски: %s — больше двух красок кроме белого и серого (голубой + золото)"
                     % ", ".join(accents))
    br = merged(spec, "brand")
    if br.get("off") or not br.get("logo"):
        notes.append("знак: выключен (brand: false) — по стилю сайта знак «Пластина» стоит в подвале")
        return
    top = br["box"][0]
    for key in ("top_label", "middle", "bottom_label"):
        d = merged(spec, key)
        if (spec.get(key) or {}).get("text" if key != "middle" else "big") and d["box"][0] + d["box"][1] > top:
            notes.append("ПРЕДУПРЕЖДЕНИЕ %s: зона %d-%d залезает в подвал со знаком (%d+) — поднять box"
                         % (key, d["box"][0], d["box"][0] + d["box"][1], top))


def precheck(spec, base, local):
    errors, notes = [], []
    check_facts(spec, base, errors, notes)
    check_money(spec, errors, notes)
    for key in ("top_photo", "bottom_photo"):
        if spec.get(key):
            check_photo(key, spec[key], base, errors, notes, local)
    for where, t in texts_of(spec):
        if where != "middle.caption" and where != "note.text" and len(words(t)) > 3:
            notes.append("ПРЕДУПРЕЖДЕНИЕ %s: «%s» — больше трёх слов, на полке не прочтётся" % (where, t))
    check_style(spec, notes)
    return errors, notes


# ---------------------------------------------------------------- рендер на хабе

def sh(*cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("ffmpeg: %s\n%s" % (" ".join(cmd), r.stderr[-800:]))
    return r


def prep_photo(key, ph, base, out):
    """Кроп и вырез белого фона ffmpeg'ом -> png; рамка предмета по альфе (или весь кадр)."""
    src = resolve(base, ph["src"])
    crop = parse_crop(ph.get("crop"))
    vf = []
    if crop:
        x, y, w, h = crop
        vf.append("crop=%d:%d:%d:%d" % (w, h, x, y))
    vf.append("scale='min(2000,iw)':-2")
    kw = ph.get("key_white")
    if kw:
        kw = kw if isinstance(kw, dict) else {}
        vf.append("format=rgba,colorkey=0xFFFFFF:%s:%s" % (kw.get("similarity", 0.10), kw.get("blend", 0.08)))
    dst = os.path.join(out, "p_%s.png" % key)
    sh("ffmpeg", "-nostdin", "-y", "-v", "error", "-i", src, "-vf", ",".join(vf), dst)
    w, h = dims(dst)
    bbox = (0, 0, w, h)
    if kw:
        r = subprocess.run(["ffmpeg", "-nostdin", "-v", "info", "-i", dst, "-vf", "alphaextract,bbox=min_val=24",
                            "-f", "null", "-"], capture_output=True, text=True)
        m = re.findall(r"x1:(\d+) x2:(\d+) y1:(\d+) y2:(\d+) w:(\d+) h:(\d+)", r.stderr)
        if m:
            x1, x2, y1, y2, bw, bh = [int(v) for v in m[-1]]
            bbox = (x1, y1, bw, bh)
    return dst, (w, h), bbox


def fill_of(ph, img_wh, bbox):
    bx, by, bw, bh = ph["box"]
    iw, ih = img_wh
    s = (max if ph.get("fit") == "cover" else min)(bw / iw, bh / ih)
    fw = min(bbox[2] * s, bw) / bw
    fh = min(bbox[3] * s, bh) / bh
    return round(fw, 3), round(fh, 3)


def fit_div(id_, text, top, height, color, mx, mn, cls="lbl", side=36):
    inner = "".join('<i style="font-style:normal;color:%s">%s</i>' % (c, html.escape(s))
                    for s, c in segments(text, color))
    return ('<div id="%s" class="fit %s" data-max="%d" data-min="%d" style="top:%dpx;height:%dpx;left:%dpx;'
            'right:%dpx;color:%s;font-size:%dpx"><span>%s</span></div>'
            % (id_, cls, mx, mn, top, height, side, side, color, mx, inner))


def font_css(fonts):
    """Tektur (вес 400-900) и Jost (100-900, size-adjust 108.7% как на сайте: у Jost низкие строчные). В Jost нет «→» —
    стрелка берётся из Tektur через запасной шрифт в font-family."""
    return ("@font-face{font-family:'Tektur';src:url('%(t)s');font-weight:400 900;}"
            "@font-face{font-family:'Jost';src:url('%(j)s');font-weight:100 900;size-adjust:108.7%%;}"
            % {"t": furl(os.path.join(fonts, "Tektur.ttf")), "j": furl(os.path.join(fonts, "Jost.ttf"))})


def brand_html(spec):
    br = merged(spec, "brand")
    parts = []
    if br.get("off"):
        return parts, None
    if br.get("bar", True):
        parts.append('<div style="position:absolute;left:0;right:0;top:0;height:8px;background:%s"></div>' % AZURE)
    logo = br.get("logo")
    if not logo:
        return parts, None
    top, h = br["box"]
    svg = LOGO_S if logo == "symbol" else LOGO_H
    w = round(h * LOGO_RATIO.get(logo, LOGO_RATIO["horizontal"]))
    svg = svg.replace("<svg ", '<svg width="%d" height="%d" style="display:block;flex:none" ' % (w, h), 1)
    return parts, (top, h, svg)


def build_html(spec, photos, fonts):
    bg = spec.get("bg", DEFAULTS["bg"])
    parts = []
    if spec.get("grid"):
        parts.append('<div class="grid"></div>')
    for key in ("top_photo", "bottom_photo"):
        if key not in photos:
            continue
        ph, path = photos[key]["spec"], photos[key]["png"]
        x, y, w, h = ph["box"]
        parts.append('<img src="%s" style="position:absolute;left:%dpx;top:%dpx;width:%dpx;height:%dpx;'
                     'object-fit:%s;object-position:%s">' % (furl(path), x, y, w, h, ph.get("fit", "contain"),
                                                            ph.get("position", "50% 50%")))
        fade = ph.get("fade", [16, 14] if ph.get("fit") == "cover" else None)
        if fade:
            parts.append('<div style="position:absolute;left:%dpx;top:%dpx;width:%dpx;height:%dpx;background:'
                         'linear-gradient(180deg,%s 0%%,transparent %d%%,transparent %d%%,%s 100%%)"></div>'
                         % (x, y, w, h, bg, fade[0], 100 - fade[1], bg))
    bar, logo = brand_html(spec)
    parts += bar
    tl = merged(spec, "top_label")
    if tl.get("text"):
        parts.append(fit_div("top_label", tl["text"], tl["box"][0], tl["box"][1], tl["color"], tl["max"], tl["min"]))
    md = merged(spec, "middle")
    if md.get("band"):
        bt, bh = md["band_box"]
        parts.append('<div style="position:absolute;left:0;right:0;top:%dpx;height:%dpx;background:linear-gradient('
                     '90deg,%s,%s 22%%,%s 78%%,%s)"></div>' % (bt, bh, bg, md["band"], md["band"], bg))
        parts.append('<div style="position:absolute;left:0;right:0;top:%dpx;height:2px;background:linear-gradient('
                     '90deg,transparent,%s55 22%%,%s55 78%%,transparent)"></div>' % (bt, AZURE, AZURE))
        parts.append('<div style="position:absolute;left:0;right:0;top:%dpx;height:2px;background:linear-gradient('
                     '90deg,transparent,%s55 22%%,%s55 78%%,transparent)"></div>' % (bt + bh - 2, AZURE, AZURE))
    if md.get("big"):
        parts.append(fit_div("middle_big", md["big"], md["box"][0], md["box"][1], md["color"], md["max"], md["min"]))
    if md.get("caption"):
        parts.append(fit_div("middle_caption", md["caption"], md["caption_box"][0], md["caption_box"][1],
                             md.get("caption_color"), md["caption_size"], 22, cls="sub", side=48))
    bl = merged(spec, "bottom_label")
    if bl.get("text"):
        parts.append(fit_div("bottom_label", bl["text"], bl["box"][0], bl["box"][1], bl["color"], bl["max"], bl["min"]))
    nt = merged(spec, "note")
    foot_note = ""
    if nt.get("text"):
        if nt.get("box"):
            parts.append(fit_div("note", nt["text"], nt["box"][0], nt["box"][1], nt["color"], nt["size"], 18,
                                 cls="sub", side=48))
        else:
            foot_note = ('<span id="note" style="color:%s;font-size:%dpx;white-space:nowrap">%s</span>'
                         % (nt["color"], nt["size"], html.escape(plain(nt["text"]))))
    if logo or foot_note:
        top, h, svg = logo or (DEFAULTS["brand"]["box"][0], DEFAULTS["brand"]["box"][1], "")
        parts.append('<div id="foot" class="sub" style="position:absolute;left:48px;right:48px;top:%dpx;height:%dpx;'
                     'display:flex;align-items:center;justify-content:center;gap:28px">%s%s</div>'
                     % (top, h, foot_note, svg))
    return """<html><head><meta charset="utf-8"><style>
%(fontcss)s
html,body{margin:0;width:%(w)dpx;height:%(h)dpx;overflow:hidden;background:%(bg)s;color:%(paper)s;font-family:'Jost','Tektur',sans-serif;}
.grid{position:absolute;inset:0;background-image:linear-gradient(#58C4FF0D 1px,transparent 1px),linear-gradient(90deg,#58C4FF0D 1px,transparent 1px);background-size:60px 60px;}
.fit{position:absolute;display:flex;align-items:center;justify-content:center;white-space:nowrap;}
.fit>span{flex:none;display:block;}
.lbl{font-family:'Tektur',sans-serif;font-weight:700;letter-spacing:-.01em;line-height:.9;}
.sub{font-family:'Jost','Tektur',sans-serif;font-weight:600;letter-spacing:.06em;line-height:1;}
</style></head><body>%(body)s</body></html>""" % {"fontcss": font_css(fonts), "w": W, "h": H, "bg": bg,
                                                  "paper": PAPER, "body": "".join(parts)}


FIT_JS = """async () => {
  await document.fonts.ready;
  const out = [];
  for (const box of document.querySelectorAll('.fit')) {
    const span = box.firstElementChild, mx = +box.dataset.max, mn = +box.dataset.min;
    let s = mx;
    const over = () => { const r = span.getBoundingClientRect();
      return r.width > box.clientWidth || r.height > box.clientHeight + 2; };
    box.style.fontSize = s + 'px';
    while (s > 8 && over()) { s -= 2; box.style.fontSize = s + 'px'; }
    const r = span.getBoundingClientRect();
    out.push({id: box.id, text: span.textContent, max: mx, min: mn, size: s, width: Math.round(r.width),
              box_w: box.clientWidth, height: Math.round(r.height), box_h: box.clientHeight,
              lines: new Set([...span.querySelectorAll('i')].flatMap(
                e => [...e.getClientRects()].map(r => Math.round(r.top)))).size});
  }
  return {items: out, fonts: {tektur: document.fonts.check('700 100px "Tektur"'),
                              jost: document.fonts.check('600 40px "Jost"')}};
}"""


PREVIEW = """<html><head><meta charset="utf-8"><style>
%(fontcss)s
html,body{margin:0;background:#1B1C1F;color:#C9CCD1;font-family:'Jost',sans-serif;}
.wrap{display:flex;gap:24px;padding:24px;align-items:flex-start;}
.col{display:flex;flex-direction:column;gap:24px;width:250px;}
.tile{padding:18px 30px 20px;border-radius:10px;}
.tile img{display:block;width:190px;height:%(th)dpx;border-radius:8px;}
.t{font-family:Arial,sans-serif;font-size:13px;line-height:1.3;margin-top:8px;font-weight:500;max-width:190px;}
.cap{font-size:14px;letter-spacing:.02em;margin-bottom:10px;color:#8A8F98;white-space:nowrap;}
</style></head><body><div class="wrap">
<div class="col">
 <div class="tile" style="background:#0F0F0F"><div class="cap">YouTube · полка 190 px</div>
  <img src="%(thumb)s"><div class="t" style="color:#F1F1F1">%(title)s</div></div>
 <div class="tile" style="background:#FFFFFF"><div class="cap" style="color:#6D7178">ВК · светлая тема</div>
  <img src="%(thumb)s"><div class="t" style="color:#000">%(title)s</div></div>
 <div class="tile" style="background:#0F0F0F"><div class="cap">прищур · 190 px, размытие</div>
  <img src="%(squint)s"><div class="t" style="color:#8A8F98">тезис и цифра угадываются силуэтом?</div></div>
</div>
<div><div class="cap">обложка x0.5 (540x960)</div><img src="%(half)s" style="display:block;width:540px;height:960px"></div>
</div></body></html>"""


def to_jpg(png, jpg):
    for q in (3, 4, 5, 6, 8, 10, 12):
        sh("ffmpeg", "-nostdin", "-y", "-v", "error", "-i", png, "-q:v", str(q), jpg)
        if os.path.getsize(jpg) <= MAX_BYTES:
            return q
    raise SystemExit("cover.jpg больше 2 МБ даже на q=12")


def render(spec, base, out, fonts):
    from playwright.sync_api import sync_playwright
    photos, report = {}, {"photos": {}, "texts": [], "warnings": [], "errors": [], "fonts": fonts}
    for key in ("top_photo", "bottom_photo"):
        ph = merged(spec, key)
        if not ph.get("src"):
            continue
        png, wh, bbox = prep_photo(key, ph, base, out)
        fw, fh = fill_of(ph, wh, bbox)
        photos[key] = {"spec": ph, "png": png}
        report["photos"][key] = {"src": resolve(base, ph["src"]), "origin": ph.get("origin"), "crop": ph.get("crop"),
                                 "key_white": bool(ph.get("key_white")), "prepared": list(wh),
                                 "subject_bbox": list(bbox), "fill_w": fw, "fill_h": fh}
        if max(fw, fh) < FILL_MIN:
            report["warnings"].append("%s: предмет занимает %.0f%% x %.0f%% своей зоны — фото мелкое, кроп туже"
                                      % (key, fw * 100, fh * 100))
    page_html = os.path.join(out, "cover.html")
    with open(page_html, "w", encoding="utf-8") as f:
        f.write(build_html(spec, photos, fonts))
    exe = (glob.glob("/root/.cache/ms-playwright/chromium-*/chrome-linux*/chrome") + [None])[0]
    png, jpg = os.path.join(out, "cover.png"), os.path.join(out, "cover.jpg")
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox", "--allow-file-access-from-files"], executable_path=exe)
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
        pg.goto(furl(page_html), wait_until="load", timeout=30000)
        fit = pg.evaluate(FIT_JS)
        pg.wait_for_timeout(300)
        pg.screenshot(path=png)
        q = to_jpg(png, jpg)
        thumb, half = os.path.join(out, "thumb190.png"), os.path.join(out, "half.png")
        squint = os.path.join(out, "squint190.png")
        th = round(H * SHELF / W)
        sh("ffmpeg", "-nostdin", "-y", "-v", "error", "-i", jpg, "-vf", "scale=%d:%d:flags=lanczos" % (SHELF, th), thumb)
        sh("ffmpeg", "-nostdin", "-y", "-v", "error", "-i", jpg, "-vf",
           "scale=%d:%d:flags=lanczos,gblur=sigma=%s" % (SHELF, th, SQUINT_SIGMA), squint)
        sh("ffmpeg", "-nostdin", "-y", "-v", "error", "-i", jpg, "-vf", "scale=540:960:flags=lanczos", half)
        prev_html = os.path.join(out, "preview.html")
        with open(prev_html, "w", encoding="utf-8") as f:
            f.write(PREVIEW % {"fontcss": font_css(fonts), "th": th, "thumb": furl(thumb), "half": furl(half),
                               "squint": furl(squint),
                               "title": html.escape(spec.get("title") or spec.get("name", ""))})
        pp = b.new_page(viewport={"width": 862, "height": 1050}, device_scale_factor=1)
        pp.goto(furl(prev_html), wait_until="load", timeout=30000)
        pp.evaluate("async () => { await document.fonts.ready; }")
        pp.wait_for_timeout(200)
        pp.screenshot(path=os.path.join(out, "preview.png"), full_page=True)
        b.close()
    if not (fit["fonts"]["tektur"] and fit["fonts"]["jost"]):
        report["errors"].append("шрифты не загрузились из %s: %s" % (fonts, fit["fonts"]))
    for it in fit["items"]:
        it["shelf_px"] = round(it["size"] * SHELF / W, 1)
        it["shrunk"] = it["size"] < it["max"]
        report["texts"].append(it)
        main = it["id"] in ("top_label", "middle_big", "bottom_label")
        if it["size"] < it["min"] or it["width"] > it["box_w"]:
            report["errors"].append("%s: «%s» не влезает в строку даже кеглем %d — сократить текст"
                                    % (it["id"], it["text"], it["size"]))
        if it["lines"] > 1:
            report["errors"].append("%s: «%s» перенеслась на %d строки" % (it["id"], it["text"], it["lines"]))
        if main and it["shelf_px"] < SHELF_MIN:
            report["warnings"].append("%s: на полке %.1f px — мелко (нужно >= %d)" % (it["id"], it["shelf_px"],
                                                                                    SHELF_MIN))
    wh = dims(jpg)
    size = os.path.getsize(jpg)
    report["cover"] = {"jpg": jpg, "size": size, "wh": list(wh), "q": q, "preview": os.path.join(out, "preview.png"),
                       "squint": squint}
    if tuple(wh) != (W, H) or size > MAX_BYTES:
        report["errors"].append("cover.jpg %sx%s, %d байт — нужно 1080x1920 и <= 2 МБ" % (wh[0], wh[1], size))
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--out", help="папка вывода (по умолчанию /opt/shorts/r5090/cover_skill/<name>/)")
    ap.add_argument("--fonts", help="папка с Tektur.ttf и Jost.ttf (по умолчанию /opt/shorts/fonts или fonts/ рядом)")
    ap.add_argument("--check", action="store_true", help="только проверки до рендера, без браузера (локально)")
    a = ap.parse_args()
    spec_path = os.path.abspath(a.spec)
    base = os.path.dirname(spec_path)
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    errors, notes = precheck(spec, base, local=a.check)
    for n in notes:
        print("  " + n)
    for e in errors:
        print("ОШИБКА " + e)
    if errors:
        sys.exit(2)
    if a.check:
        print("проверки до рендера пройдены: %s" % spec.get("name", spec_path))
        return
    out = os.path.abspath(a.out or "/opt/shorts/r5090/cover_skill/%s" % spec.get("name", "cover"))
    if not OUT_OK.match(out.replace("\\", "/")):
        sys.exit("--out %s: только /tmp/<имя> или /opt/shorts/<проект>/cover_skill/<имя> (прод-папки не трогаем)" % out)
    fonts, tried = find_fonts(a.fonts)
    if not fonts:
        print("ОШИБКА шрифты стиля сайта: нет %s ни в одной папке (%s). На хаб их кладёт выкат shortsmaker/vps/fonts/ "
              "в /opt/shorts/fonts; до выката — scp vps/fonts/*.ttf в папку fonts/ рядом с cover.py или --fonts DIR"
              % (" и ".join(FONT_FILES), ", ".join(tried)))
        sys.exit(1)
    os.makedirs(out, exist_ok=True)
    report = render(spec, base, out, fonts)
    report["prechecks"] = notes
    with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    for it in report["texts"]:
        print("  %-15s %-28s кегль %3d из %3d, ширина %4d/%4d, на полке %.1f px"
              % (it["id"], "«%s»" % it["text"], it["size"], it["max"], it["width"], it["box_w"], it["shelf_px"]))
    for k, v in report["photos"].items():
        print("  %-15s предмет %.0f%% x %.0f%% зоны, %s" % (k, v["fill_w"] * 100, v["fill_h"] * 100, v["origin"]))
    c = report["cover"]
    print("  cover.jpg %dx%d, %d байт (q=%d), шрифты %s" % (c["wh"][0], c["wh"][1], c["size"], c["q"], fonts))
    for w_ in report["warnings"]:
        print("ПРЕДУПРЕЖДЕНИЕ " + w_)
    for e in report["errors"]:
        print("ОШИБКА " + e)
    print(c["jpg"])
    print(c["preview"])
    sys.exit(1 if report["errors"] else 0)


if __name__ == "__main__":
    main()
