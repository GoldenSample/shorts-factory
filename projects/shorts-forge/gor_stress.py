# -*- coding: utf-8 -*-
"""Ударения для двойника голоса Гора: знак U+0301 после ударной гласной.

Зачем (слово Гора 03.10: «он похож спору нет но ударения это салам пополам», «гигагерцА на всех ярАх»):
Qwen3-TTS сам ставит ударения и ошибается примерно в каждом седьмом слове, а знаки ударения без обучения
игнорирует. Двойник v4 обучен на текстах, где ударная гласная помечена (70 % многосложных слов), поэтому
пометкам подчиняется: ударение задаёт акцентуатор и словарь, а не догадка модели.

Акцентуатор: silero-stress 1.5 (MIT, отдельная модель омографов). Его «+» перед гласной переводится в
U+0301 после гласной; односложные слова и слова с «ё» не помечаются. Ручные исправления:
STRESS_FIX ниже и столбец ударений в будущем (слово -> слово со знаком).
Работает только в окружении с torch и silero-stress (venv qwen-tts).
"""
from __future__ import annotations

import random
import re
from functools import lru_cache

ACUTE = "́"
VOW = "аеёиоуыэюяАЕЁИОУЫЭЮЯ"
WORD = re.compile(r"[А-Яа-яЁё+́]+")

# ручные ударения поверх акцентуатора: ключ без знаков, значение с «+» перед ударной гласной
STRESS_FIX = {
    "гигагерц": "гигаг+ерц", "гигагерца": "гигаг+ерца", "гигагерцах": "гигаг+ерцах",
    "мегагерц": "мегаг+ерц", "мегагерца": "мегаг+ерца", "ядрах": "+ядрах", "ядра": "+ядра",
    "равно": "равн+о", "драйверы": "др+айверы", "драйверов": "др+айверов", "кабели": "к+абели", "кабелей": "к+абелей",
}


@lru_cache(maxsize=1)
def _acc():
    from silero_stress import load_accentor
    return load_accentor()


def _vowels(w: str) -> int:
    return sum(ch in VOW for ch in w)


def plus_to_acute(w: str) -> str:
    """з+амок -> за́мок (знак после гласной)."""
    return re.sub(r"\+([" + VOW + "])", lambda m: m.group(1) + ACUTE, w)


def accent(text: str, share: float = 1.0, seed: int | None = None) -> str:
    """Поставить ударения: share = доля многосложных слов со знаком (обучение 0.7, инференс 1.0)."""
    if not text.strip():
        return text
    rnd = random.Random(seed)
    marked = _acc()(text)                       # «Д+ержит ш+есть»: та же строка с плюсами
    out, pos = [], 0
    for m in WORD.finditer(marked):
        out.append(marked[pos:m.start()])
        w = m.group(0)
        bare = w.replace("+", "")
        key = bare.lower()
        if key in STRESS_FIX:
            fix = STRESS_FIX[key]
            w = (fix[0].upper() + fix[1:]) if bare[:1].isupper() and not fix.startswith("+") else fix
            if bare[:1].isupper() and fix.startswith("+"):
                w = "+" + fix[1].upper() + fix[2:]
        if _vowels(bare) < 2 or "ё" in key or rnd.random() > share:
            out.append(bare)
        else:
            out.append(plus_to_acute(w) if "+" in w else bare)
        pos = m.end()
    out.append(marked[pos:])
    return "".join(out)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    for s in sys.argv[1:] or ["Держит шесть и два гигагерца на всех ядрах при один точка три ноль вольта.",
                               "Драйверы и кабели меняем, замок на двери старый."]:
        print(accent(s))
