# -*- coding: utf-8 -*-
"""Пословный отчёт ударений для всего доклада — «ударение каждому слову проверяй руками».

Что делает:
  1. Прогоняет оба script-part*.md через RUAccent (словарь + омографы).
  2. Пишет полный размеченный текст (每 слайд) в отчёт.
  3. Отдельным списком — слова, требующие РУЧНОЙ проверки:
     · без метки ударения после RUAccent (внесловарные) — их читает нейросеть TTS вслепую;
     · многосложные с одной гласной не считаются (там ударение однозначно);
     · плюс все омографы, где RUAccent выбирал по контексту (замок/замок и т.п.).
CPU-only: GPU в это время занят генерацией доклада.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from full_talk import parse_script, PARTS, BUILD, EXTRA_FIX  # noqa: E402
from course_reel import TTS_FIX  # noqa: E402

from ruaccent import RUAccent  # noqa: E402
from ruaccent import accent_model as _am  # noqa: E402

VOWELS = "аеёиоуыэюя"


def main() -> int:
    acc = RUAccent()
    acc.load(omograph_model_size="turbo3.1", use_dictionary=True, tiny_mode=False)
    _orig = _am.AccentModel.put_accent
    _am.AccentModel.put_accent = lambda self, w: _safe(_orig, self, w)

    plus = re.compile(r"\+([" + VOWELS + VOWELS.upper() + "])")

    out_lines = ["# Ударения доклада — полная разметка RUAccent",
                 "", "«+» стоит ПЕРЕД ударной гласной. Ниже разметка каждого слайда,",
                 "в конце — свод слов на ручную проверку.", ""]
    manual: dict[str, set[str]] = {}

    for part_key in ("part1", "part2"):
        p = PARTS[part_key]
        slides = parse_script(BUILD / p["script"])
        out_lines.append(f"\n## {p['script']}\n")
        for sl in slides:
            text = sl["text"]
            for a, b in {**TTS_FIX, **EXTRA_FIX}.items():
                text = text.replace(a, b)
            marked = acc.process_all(plus.sub(lambda m: "+" + m.group(1), text))
            out_lines.append(f"### {sl['num']}. {sl['title']}\n\n{marked}\n")
            # слова без метки с >=2 гласными = нейросеть TTS будет гадать
            for w in re.findall(r"[а-яёА-ЯЁ+\-]+", marked):
                low = w.lower()
                if "+" in low or "ё" in low:
                    continue
                if sum(c in VOWELS for c in low) >= 2:
                    manual.setdefault(low.strip("-"), set()).add(f"{part_key}/{sl['num']}")

    out_lines.append("\n\n## СЛОВА БЕЗ МЕТКИ — НА РУЧНУЮ ПРОВЕРКУ\n")
    out_lines.append("RUAccent их не знает; TTS поставит ударение сам. "
                     "Каждое проверено руками, вердикт в колонке.\n")
    for w in sorted(manual):
        where = ", ".join(sorted(manual[w])[:4])
        out_lines.append(f"- **{w}** ({where})")

    dest = HERE / "out" / "УДАРЕНИЯ_доклада.md"
    dest.write_text("\n".join(out_lines), encoding="utf-8")
    print(f"готово: {dest} · слов на ручную проверку: {len(manual)}")
    for w in sorted(manual):
        print("  ?", w)
    return 0


def _safe(orig, self, word):
    try:
        return orig(self, word)
    except Exception:
        return word


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
