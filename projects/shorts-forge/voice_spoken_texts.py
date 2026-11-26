# -*- coding: utf-8 -*-
"""Тексты обучения двойника в ПРОИЗНОСИМОЙ записи (под модель v3).

Модель v2 училась на тексте whisper («RTX 5090», «14-м») и сама угадывала, как это читается.
v3 учится на той же записи, которую потом даёт нормализатор gor_normalize.py, поэтому в
продакшне произношение терминов задаёт словарь, а не догадка модели.

Для каждой фразы с цифрами или латиницей:
  1) normalize(текст whisper) -> произносимый текст;
  2) выравнивание с транскриптом GigaAM того же куска (как Гор реально сказал): где у нормализатора
     числительное, а GigaAM слышит другую форму того же числа («пятьдесят» против «пятидесяти»),
     берётся форма GigaAM;
  3) если после этого текст расходится с GigaAM больше чем на 25 % CER, фраза в обучение не идёт
     (whisper ошибся или кусок невнятный).
Выход: dataset/train_spoken_raw.jsonl, dataset/test_spoken.jsonl, отчёт в консоль.
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gor_normalize import normalize
from voice_eval import cer_str

ROOT = HERE / "work_voice_gor"
DS = ROOT / "dataset"
HAS_LD = re.compile(r"[A-Za-z0-9]")
NUMW = re.compile(r"^(ноль|нол|одн|один|перв|два|две|двух|двум|втор|три|трех|трёх|трем|трём|трет|четыр|четвер|"
                  r"пят|шест|сем|восем|девят|десят|сорок|сто|ста|сот|двест|трист|тысяч|миллион|миллиард|полтор)")


def giga_map() -> dict[tuple[str, int], str]:
    out = {}
    for l in (ROOT / "lexicon" / "giga.jsonl").open(encoding="utf-8"):
        r = json.loads(l)
        out[(r["vid"], r["i"])] = r["giga"]
    return out


def fix_number_forms(norm: str, giga: str) -> str:
    """Числительные нормализатора -> формы, которые реально прозвучали (по GigaAM)."""
    toks = norm.split()
    keys = [re.sub(r"[^\wё-]", "", t.lower()) for t in toks]
    g = giga.split()
    sm = difflib.SequenceMatcher(a=keys, b=g, autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        span = toks[i1:i2]
        if (op == "replace" and span and all(NUMW.match(k) for k in keys[i1:i2] if k)
                and g[j1:j2] and all(NUMW.match(w) for w in g[j1:j2]) and abs((i2 - i1) - (j2 - j1)) <= 1):
            tail = re.sub(r"^[\wё-]+", "", span[-1])       # пунктуацию последнего слова сохраняем
            out.extend(g[j1:j2 - 1] + [g[j2 - 1] + tail])
        else:
            out.extend(span)
    return " ".join(out)


def convert(rows: list[dict], gm: dict) -> tuple[list[dict], dict]:
    stat = {"без цифр и латиницы": 0, "нормализовано": 0, "формы чисел по GigaAM": 0, "выкинуто": 0,
            "нет GigaAM": 0}
    out = []
    for r in rows:
        text = r["text"]
        if not HAS_LD.search(text):
            stat["без цифр и латиницы"] += 1
            out.append(r)
            continue
        stem = Path(r["audio"]).stem
        vid, i = stem.rsplit("_", 1)
        g = gm.get((vid, int(i)))
        norm = normalize(text)
        if not g:
            stat["нет GigaAM"] += 1
            out.append({**r, "text": norm})
            continue
        fixed = fix_number_forms(norm, g)
        if fixed != norm:
            stat["формы чисел по GigaAM"] += 1
        if cer_str(fixed, g) > 0.25:
            stat["выкинуто"] += 1
            continue
        stat["нормализовано"] += 1
        out.append({**r, "text": fixed, "text_whisper": text})
    return out, stat


def main() -> int:
    gm = giga_map()
    train = [json.loads(l) for l in (DS / "train_raw.jsonl").open(encoding="utf-8")]
    test = [json.loads(l) for l in (DS / "test.jsonl").open(encoding="utf-8")]
    tr, st = convert(train, gm)
    te, st2 = convert(test, gm)
    with (DS / "train_spoken_raw.jsonl").open("w", encoding="utf-8") as f:
        for r in tr:
            f.write(json.dumps({k: r[k] for k in ("audio", "text", "ref_audio", "language")}, ensure_ascii=False) + "\n")
    with (DS / "test_spoken.jsonl").open("w", encoding="utf-8") as f:
        for r in te:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("обучение:", st, "->", len(tr), "фраз")
    print("тест:    ", st2, "->", len(te), "фраз")
    shown = 0
    for r in tr:
        if "text_whisper" in r and shown < 8:
            print(f"  было:  {r['text_whisper']}\n  стало: {r['text']}")
            shown += 1
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
