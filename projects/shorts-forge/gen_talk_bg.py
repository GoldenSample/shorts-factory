# -*- coding: utf-8 -*-
"""Фоны под скринплей доклада — вторая волна генератива (команда «фоны круче»).

Сцены выведены из script-part1/2 (тексты в md, OCR снят Гором как лишний):
дом знания у курса, деревня с ратушей, шахта-разрез, библиотека со ступенями,
рынок-книга заявок, двое ворот в одну комнату (REST/MCP). Пять прежних сцен
остаются в reel_bg — эти шесть кладутся рядом, тем же конвейером отбора
(яркость в полосе игры, спокойный центр, vision-контроль).

Запуск: python gen_talk_bg.py   (ComfyUI должен быть жив; FLUX schnell fp8)
⚠ НЕ запускать параллельно с генерацией доклада: FLUX fp8 берёт ~17 ГБ VRAM.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_reel_bg as base

# Стиль тот же, что у первой волны — миры должны склеиваться в один.
STYLE = base.STYLE

SHOTS = {
    # часть 1: «дом знания» — курс как работающая площадка, не папка с текстами
    "06_study":   "Near-black scholar's room, lit only by one low candle flame on the desk "
                  "edge. The upper half of the frame is empty unlit black air with large "
                  "copy space. A plain writing desk and a tall shelf of unmarked spines "
                  "stand as dark silhouettes. The far wall dissolves into pure black. " + STYLE,
    # часть 2: деревня и ратуша — уровень ратуши = сколько у тебя агентов
    "07_village": "Near-black hilltop hamlet at deep night, lit only by two tiny warm "
                  "windows of a squat stone hall. The sky is empty dark air with large "
                  "copy space. A few low plain roofs cluster as dark silhouettes below "
                  "the hall. Everything else dissolves into pure black. " + STYLE,
    # подземье: разрез горизонтов, жилы — «лестница глубин»
    "08_mine":    "Near-black underground cavern seen in cross-section, lit only by faint "
                  "veins of pale ore glowing deep in the rock. The left third of the frame "
                  "is empty unlit black air. Rough plain rock ledges descend in steps into "
                  "darkness. No tools, nobody there. " + STYLE,
    # библиотека: знание по ступеням, купить нельзя
    "09_library": "Near-black vast archive hall, lit only by one narrow warm shaft of light "
                  "falling on a plain empty lectern. Tall dark shelves with bare unmarked "
                  "spines recede as silhouettes. The upper right of the frame is empty "
                  "unlit black air with large copy space. " + STYLE,
    # рынок: прилавок и весы — книга лимит-заявок, налог сгорает
    "10_market":  "Near-black covered market stall at night, lit only by a small hanging "
                  "oil lamp over plain wooden scales. The right half of the frame is empty "
                  "unlit black air with large copy space. Bare crates and a worn plain "
                  "counter stand as dark silhouettes. " + STYLE,
    # две двери в одну комнату: REST и MCP
    "11_twodoors": "Near-black stone wall with two identical plain archways side by side, "
                  "the same warm light glowing faintly from deep inside both passages. "
                  "The upper half of the frame is empty unlit black air with large copy "
                  "space. The wall face is bare and unmarked. " + STYLE,
}


def main() -> int:
    base.SHOTS.clear()
    base.SHOTS.update(SHOTS)
    return base.main()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
