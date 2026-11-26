# -*- coding: utf-8 -*-
"""Нормализатор текста под двойника голоса Гора: латиница и цифры -> как ГОР это произносит.

Один и тот же код готовит тексты обучения (voice_lexicon_retrain) и сценарии озвучки (gor_voice.py):
модель учится на той же записи, которую потом получает.

Правила чтения сняты с его роликов (GigaAM против whisper, voice_lexicon.py, 28.09.2026):
  видеокарты парами     5090 -> «пятьдесят девяносто», 1080 -> «десять восемьдесят» (записи 8/8);
  процессоры сотнями    9800X3D -> «девять восемьсот икс три дэ», 13900KS -> «тринадцать девятьсот ка эс»;
  сокеты                1700 -> «тысяча семьсот» (круглые целиком), 1851 -> «восемнадцать пятьдесят один»;
  чипсеты               B650E -> «бэ шестьсот пятьдесят е», Z790 -> «зет семьсот девяносто»;
  частоты               5.4 -> «пять и четыре»; вольтаж 1.30 -> «один точка три ноль»;
  диапазоны             12-15% -> «двенадцать пятнадцать процентов».
Словарь терминов: gor_lexicon.tsv. Латиница, которой нет ни в правилах, ни в словаре, транслитерируется
грубо и попадает в unknown(): такие слова надо вписать в словарь.

  python gor_normalize.py "текст"        показать нормализацию
  python gor_normalize.py --test         прогон контрольных фраз
"""
from __future__ import annotations

import re
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path

from num2words import num2words

HERE = Path(__file__).resolve().parent
LAT = re.compile(r"[A-Za-z]")
_unknown: list[str] = []


def card(n: int | str, case: str = "nominative", gender: str = "m") -> str:
    w = num2words(int(n), lang="ru", case=case, gender=gender)
    return re.sub(r"^одн(а|ой|у|ою) тысяч", "тысяч", w)   # в речи «тысяча семьсот», не «одна тысяча»


def ordw(n: int | str, case: str = "nominative", gender: str = "m", plural: bool = False) -> str:
    return num2words(int(n), lang="ru", to="ordinal", case=case, gender=gender, plural=plural)


@lru_cache(maxsize=1)
def lexicon() -> list[tuple[re.Pattern, str]]:
    items = []
    for line in (HERE / "gor_lexicon.tsv").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        term, spoken = line.split("\t")[:2]
        items.append((term, spoken))
    items.sort(key=lambda x: -len(x[0]))
    return [(re.compile(r"(?<![A-Za-zА-Яа-яЁё0-9])" + re.escape(t) + r"(?![A-Za-zА-Яа-яЁё0-9])", re.I), s)
            for t, s in items]


def lex_word(w: str) -> str:
    for rx, s in lexicon():
        if rx.fullmatch(w):
            return s
    return w


# ---------- модели железа ----------

def gpu_num(d: str) -> str:
    """5090 -> пятьдесят девяносто; 1660 -> шестнадцать шестьдесят."""
    a, b = int(d[:2]), int(d[2:])
    return card(a) + " " + (card(b) if b >= 10 else "ноль " + card(b))


def cpu_num(d: str) -> str:
    """9800 -> девять восемьсот; 13900 -> тринадцать девятьсот; 9950 -> девять девятьсот пятьдесят."""
    head, tail = (d[:-3], d[-3:])
    t = int(tail)
    return card(head) + " " + (card(t) if t else "тысяч")


def socket_num(d: str) -> str:
    return card(d) if d.endswith("00") else card(d[:2]) + " " + card(d[2:])


SUFFIX = {"x3d": "икс три дэ", "x": "икс", "k": "ка", "kf": "ка эф", "ks": "ка эс", "f": "эф", "g": "джи",
          "h": "аш", "hx": "аш икс", "t": "тэ", "ti": "ти ай", "super": "супер", "xt": "икс ти", "xtx": "икс ти икс",
          "d": "дэ", "e": "е", "i": "ай", "m": "эм", "a": "а"}
CHIP_LETTER = {"a": "а", "b": "бэ", "h": "аш", "x": "икс", "z": "зет", "q": "кью", "w": "дабл ю"}

UNITS = {  # (один, два-четыре и дробь, пять+)
    "ггц": ("гигагерц", "гигагерца", "гигагерц"), "мгц": ("мегагерц", "мегагерца", "мегагерц"),
    "гц": ("герц", "герца", "герц"), "вт": ("ватт", "ватта", "ватт"), "квт": ("киловатт", "киловатта", "киловатт"),
    "мв": ("милливольт", "милливольта", "милливольт"), "в": ("вольт", "вольта", "вольт"),
    "гб": ("гигабайт", "гигабайта", "гигабайт"), "тб": ("терабайт", "терабайта", "терабайт"),
    "мб": ("мегабайт", "мегабайта", "мегабайт"), "нм": ("нанометр", "нанометра", "нанометров"),
    "мм": ("миллиметр", "миллиметра", "миллиметров"), "мс": ("миллисекунда", "миллисекунды", "миллисекунд"),
    "нс": ("наносекунда", "наносекунды", "наносекунд"), "°c": ("градус", "градуса", "градусов"),
    "°": ("градус", "градуса", "градусов"), "%": ("процент", "процента", "процентов"),
    "мб/с": ("мегабайт в секунду", "мегабайта в секунду", "мегабайт в секунду"),
    "гб/с": ("гигабайт в секунду", "гигабайта в секунду", "гигабайт в секунду"),
    "гбит/с": ("гигабит в секунду", "гигабита в секунду", "гигабит в секунду"),
    "руб": ("рубль", "рубля", "рублей"), "₽": ("рубль", "рубля", "рублей"), "$": ("доллар", "доллара", "долларов"),
}
UNIT_RX = r"(МБ/с|ГБ/с|Гбит/с|ГГц|МГц|Гц|кВт|Вт|мВ|В|ГБ|ТБ|МБ|нм|мм|мс|нс|°C|°С|°|%|руб\.?|₽)(?![А-Яа-яA-Za-z])"


def plural(n: int, forms: tuple[str, str, str]) -> str:
    n = abs(n) % 100
    if 11 <= n <= 19:
        return forms[2]
    n %= 10
    return forms[0] if n == 1 else forms[1] if 2 <= n <= 4 else forms[2]


def unit_forms(u: str) -> tuple[str, str, str]:
    u = u.lower().rstrip(".").replace("°с", "°c")
    return UNITS[u]


def decimal_words(a: str, b: str) -> str:
    if len(b) == 1:
        return f"{card(a)} и {card(b)}"
    return f"{card(a)} точка " + " ".join(card(ch) for ch in b)


def hardware(t: str) -> str:
    # видеокарты: RTX 5090 Ti, RX 9070 XT, GTX 1080
    def _gpu(m):
        s = lex_word(m.group(1)) + " " + gpu_num(m.group(2))
        if m.group(3):
            s += " " + SUFFIX[m.group(3).lower()]
        if m.group(4):
            s += " " + SUFFIX[m.group(4).lower()]
        return s
    t = re.sub(r"\b(RTX|GTX|RX)\s?(\d{4})(D)?(?:\s?(Ti|Super|XTX|XT))?\b", _gpu, t, flags=re.I)
    # процессоры: Core i7-14700K, i9 14900KS, Ryzen 7 9800X3D, 7700X, 13900KS
    t = re.sub(r"\bi([3579])(?=[\s-]|\b)", lambda m: "ай " + ordw(m.group(1)), t)
    t = re.sub(r"(ай [а-я]+)[\s-](\d{4,5})([A-Za-z0-9]*)",
               lambda m: m.group(1) + " " + cpu_num(m.group(2)) + (" " + SUFFIX.get(m.group(3).lower(), m.group(3))
                                                                   if m.group(3) else ""), t)
    t = re.sub(r"\b(Ryzen|Райзен)\s([3579])\s(\d{4})(X3D|X|G)?\b",
               lambda m: f"{m.group(1)} {card(m.group(2))} {cpu_num(m.group(3))}" +
                         (" " + SUFFIX[m.group(4).lower()] if m.group(4) else ""), t, flags=re.I)
    t = re.sub(r"\b(\d{4,5})(X3D|KF|KS|K|X|F)\b",
               lambda m: cpu_num(m.group(1)) + " " + SUFFIX[m.group(2).lower()], t, flags=re.I)
    t = re.sub(r"\b(Core Ultra)\s(?:([3579])\s)?(\d{3})(KF|K|HX|H|F)?\b",
               lambda m: "кор ультра " + (card(m.group(2)) + " " if m.group(2) else "") + card(m.group(3)) +
                         (" " + SUFFIX[m.group(4).lower()] if m.group(4) else ""), t, flags=re.I)
    # сокеты и чипсеты
    t = re.sub(r"\bLGA?\s?(\d{4})\b", lambda m: "лга " + socket_num(m.group(1)), t, flags=re.I)
    t = re.sub(r"\b([ABHXZQW])(\d{3})([EIM]?)\b",
               lambda m: CHIP_LETTER[m.group(1).lower()] + " " + card(m.group(2)) +
                         (" " + SUFFIX[m.group(3).lower()] if m.group(3) else ""), t)
    # шины, память, разрешения
    t = re.sub(r"\bPCIe\s?(\d)(?:\.0)?\b", lambda m: "пи си ай е " + card(m.group(1)), t, flags=re.I)
    t = re.sub(r"\bGen\s?(\d)\b", lambda m: "ген " + card(m.group(1)), t, flags=re.I)
    t = re.sub(r"\bDDR(\d)[\s-](\d{4,5})\b", lambda m: f"дэ дэ эр {card(m.group(1))} {card(m.group(2))}", t, flags=re.I)
    t = re.sub(r"\bCL\s?(\d{2})\b", lambda m: "си эль " + card(m.group(1)), t, flags=re.I)
    t = re.sub(r"\b(\d)\s?[KК](?![A-Za-zА-Яа-я])", lambda m: card(m.group(1)) + " ка", t)
    t = re.sub(r"\b[xх](\d)\b", lambda m: "икс " + card(m.group(1)), t, flags=re.I)
    # голые номера видеокарт: 4090, 5070 (кроме годов 20xx/19xx)
    t = re.sub(r"(?<![\d.,])\b(10|16|30|40|50|60)([5-9]0)\b(?![.,]\d)", lambda m: gpu_num(m.group(0)), t)
    return t


# ---------- числа ----------

ORD_SUFFIX = {  # окончание после дефиса -> (падеж, род, множ)
    "й": ("nominative", "m", False), "ый": ("nominative", "m", False), "ий": ("nominative", "m", False),
    "ой": ("nominative", "m", False), "го": ("genitive", "m", False), "му": ("dative", "m", False),
    "м": ("instrumental", "m", False), "я": ("nominative", "f", False), "ю": ("accusative", "f", False),
    "е": ("nominative", "n", False), "х": ("genitive", "m", True), "ми": ("instrumental", "m", True),
}
PREP_LOC = {"в", "во", "на", "о", "об", "при"}


def numbers(t: str) -> str:
    t = re.sub(r"(\d)[   ](\d{3})\b", r"\1\2", t)           # 21 500 -> 21500
    # диапазоны 12-15, 3-4
    t = re.sub(r"\b(\d+)\s?[-–]\s?(\d+)\b", lambda m: f"{m.group(1)} {m.group(2)}", t)

    # порядковые с окончанием: 14-м, 13-го, 50-х
    def _ord(m):
        n, suf = m.group(1), m.group(2).lower()
        if suf not in ORD_SUFFIX:
            return m.group(0)
        case, g, pl = ORD_SUFFIX[suf]
        prev = t[max(0, m.start() - 4):m.start()].strip().split()
        if suf == "м" and prev and prev[-1].lower() in PREP_LOC:
            case = "prepositional"
        return ordw(n, case=case, gender=g, plural=pl)
    t = re.sub(r"\b(\d+)-(й|ый|ий|ой|го|му|м|я|ю|е|х|ми)\b", _ord, t)

    # составные прилагательные: 12-ядерный, 300-ваттной, 5-вольтовый
    def _comp(m):
        n = int(m.group(1))
        head = "одно" if n == 1 else card(n, case="genitive")
        return head.replace(" ", "") + m.group(2)
    t = re.sub(r"\b(\d+)-([а-яё]{3,})", _comp, t)

    # дроби с единицами и без
    def _dec_unit(m):
        return decimal_words(m.group(1), m.group(2)) + " " + unit_forms(m.group(3))[1]
    t = re.sub(r"\b(\d+)[.,](\d+)\s?" + UNIT_RX, _dec_unit, t)
    t = re.sub(r"\b(\d+)[.,](\d+)\b", lambda m: decimal_words(m.group(1), m.group(2)), t)

    # целые с единицами
    def _int_unit(m):
        n = int(m.group(1))
        return card(n) + " " + plural(n, unit_forms(m.group(2)))
    t = re.sub(r"\b(\d+)\s?" + UNIT_RX, _int_unit, t)
    t = re.sub(r"\$\s?(\d+)", lambda m: card(m.group(1)) + " " + plural(int(m.group(1)), UNITS["$"]), t)
    # оставшиеся целые
    t = re.sub(r"\d+", lambda m: card(m.group(0)), t)
    return t


# ---------- латиница вне словаря ----------

TRANSLIT = [("sh", "ш"), ("ch", "ч"), ("th", "т"), ("ph", "ф"), ("oo", "у"), ("ee", "и"), ("ck", "к"),
            ("qu", "кв"), ("a", "а"), ("b", "б"), ("c", "к"), ("d", "д"), ("e", "е"), ("f", "ф"), ("g", "г"),
            ("h", "х"), ("i", "и"), ("j", "дж"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"),
            ("p", "п"), ("q", "к"), ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"), ("v", "в"), ("w", "в"),
            ("x", "кс"), ("y", "й"), ("z", "з")]


def translit(w: str) -> str:
    s = w.lower()
    for a, b in TRANSLIT:
        s = s.replace(a, b)
    return s


def latin(t: str) -> str:
    for rx, s in lexicon():
        t = rx.sub(s, t)

    def _left(m):
        _unknown.append(m.group(0))
        return translit(m.group(0))
    return re.sub(r"[A-Za-z][A-Za-z.\-']*", _left, t)


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFC", text)
    t = t.replace("—", ",").replace("–", "-").replace("«", "").replace("»", "").replace("…", "...")
    t = hardware(t)
    for rx, s in lexicon():
        t = rx.sub(s, t)
    t = numbers(t)
    t = latin(t)
    t = re.sub(r"\s+,", ",", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def unknown() -> list[str]:
    return sorted(set(_unknown))


TESTS = [
    "RTX 5090 против RTX 4090: прирост 30% в 4K при 575 Вт.",
    "Ryzen 7 9800X3D на плате ASUS ROG Strix B650E, память DDR5 6000 CL30, EXPO включён.",
    "Intel Core i9-14900KS держит 6.2 ГГц на всех ядрах при 1.30 В, VCCSA не выше 1.30.",
    "Сокет LGA 1700 и новый LGA 1851 под Core Ultra 285K, чипсет Z890.",
    "Samsung 9100 Pro 4 ТБ: 14800 МБ/с на чтение, PCIe 5.0, цена $619.",
    "С 14-м поколением Intel у 12-ядерный процессор греется до 95°C, диапазон 12-15%.",
    "RX 9070 XT быстрее RTX 5070 Ti, а DLSS 4 и FSR 4 дают плюс 50 fps.",
]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        for s in TESTS:
            print(s, "\n  ->", normalize(s), "\n")
        print("вне словаря:", unknown())
    else:
        print(normalize(" ".join(sys.argv[1:])))
        if unknown():
            print("вне словаря:", unknown())
