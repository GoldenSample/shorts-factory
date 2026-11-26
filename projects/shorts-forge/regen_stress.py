# -*- coding: utf-8 -*-
"""Точечная перегенерация слайдов доклада под новые ударения.

Первый прогон генерации шёл до расширения словаря STRESS_FIX — слова оттуда
модель читала вслепую. Здесь: найти слайды, в чьём тексте встречаются эти
слова, удалить их wav/mp4 из кэша и напечатать, что перегенерять. Сама
перегенерация — обычный запуск full_talk.py: он дособерёт только удалённое.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from full_talk import parse_script, PARTS, BUILD, STRESS_FIX  # noqa: E402

def main() -> int:
    total = 0
    for key in ("part1", "part2"):
        p = PARTS[key]
        work = HERE / f"work_talk_{p['slides']}"
        for sl in parse_script(BUILD / p["script"]):
            low = sl["text"].lower()
            hits = sorted({k for k in STRESS_FIX if k in low})
            if not hits:
                continue
            wav = work / f"s{sl['num']:02d}.wav"
            vid = work / f"v{sl['num']:02d}.mp4"
            existed = wav.exists()
            wav.unlink(missing_ok=True)
            vid.unlink(missing_ok=True)
            total += existed
            print(f"  {key} слайд {sl['num']:2} ({'сброшен' if existed else 'ещё не был'}): "
                  + ", ".join(hits[:6]))
    print(f"\nсброшено {total} слайдов — теперь снова запустить full_talk.py "
          f"part2 и part1, дособерутся только они")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
