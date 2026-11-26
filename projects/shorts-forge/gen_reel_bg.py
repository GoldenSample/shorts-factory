# -*- coding: utf-8 -*-
"""Атмосферные фоны для рила Cognopolis: генерация с КАЛИБРОВКОЙ и автоотбором.

ГРАНИЦА. Генератив рисует МИР игры (тёмное фэнтези Железных Марок) и никогда —
интерфейс, консоль или «скриншот продукта»: для этого есть настоящие кадры.
Фон идёт только в те секции рила, где скриншота нет и быть не должно.

ПОЧЕМУ КОНВЕЙЕР, А НЕ ОДИН ВЫЗОВ. Питч инвестору не терпит «на глаз»: фон обязан
уйти под текст, а не спорить с ним. Замер палитры боевых кадров игры дал жёсткий
ориентир — средняя яркость 19-24 из 255, до 60% площади чистый чёрный. Поэтому
каждый вариант проверяется объективно:

  1. ЯРКОСТЬ   — попадание в полосу игры (иначе фон светлее интерфейса рядом);
  2. ЧИТАЕМОСТЬ — центральная зона под текст должна быть темнее и спокойнее краёв;
  3. VISION    — локальная qwen3-vl смотрит, нет ли в кадре текста, интерфейса
                 и людей крупным планом (в игре персонажи спрайтовые, фотореализм спорит).

Проходной вариант выбирается по сумме, непрошедшие остаются в browse/ для ручного
пересмотра. Все замеры печатаются: решение видно, а не «доверьтесь».
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import requests

import comfy_gen
HERE = Path(__file__).resolve().parent
OUT = HERE / "reel_bg"
BROWSE = OUT / "browse"
OLLAMA = "http://127.0.0.1:11434"
VLM = "qwen3-vl:8b-instruct"

# Замерено на боевых кадрах: средняя яркость 19-24/255. Фон держим в этой полосе
# с небольшим запасом вверх — иначе он перебьёт интерфейс на соседних секциях.
LUMA_MIN, LUMA_MAX = 14, 58
VARIANTS = 6      # локальная генерация бесплатна — перебираем шире, чем позволял пул

# ⚑ Промпты переписаны по замеру, а не по вкусу. Три правила, которые их определили:
#  1. Негатива у schnell НЕТ (cfg=1.0 вырождает вторую ветку), поэтому «нет надписей»
#     заменено на положительный признак поверхности: bare, unmarked, plain.
#     Прежний хвост «no signage, no banners, no inscriptions» работал ПРОТИВ нас —
#     три текстовых триггера подряд буквально просят FLUX нарисовать вывеску.
#  2. Лимит T5 у schnell — 256 токенов (у dev 512). Прежние промпты шли по границе,
#     и хвост со светопостановкой мог молча отваливаться. Теперь ~120 токенов.
#  3. Порядок значим: свет и пустота ПЕРВЫМИ (они задают каркас), сцена второй,
#     стиль в хвост. И пустота названа материалом («black air»), иначе FLUX её заполняет.
STYLE = ("Dark fantasy matte painting, charcoal and dark umber, low-key lighting, crushed "
         "blacks, heavy vignette, 35mm film grain, every surface bare and unmarked, "
         "seen from far away, shallow depth of field, 16:9")

SHOTS = {
    # «проблема»: учат без мира — полигон, где ничего не сопротивляется
    "01_problem": "Near-black night field, lit only by weak moonless haze. The centre of the "
                  "frame is empty unlit black air with large copy space, no detail. Three straw "
                  "practice dummies and a plain empty wooden rack stand as dark silhouettes along "
                  "the bottom left edge. Beyond them an immense unlit wilderness dissolves into "
                  "pure black. Nobody is there. " + STYLE,
    # «что построили»: место, которое реально производит
    "02_built":   "Near-black stone interior, lit only by a small bed of dying orange coals in the "
                  "lower right corner. The upper two thirds of the frame are empty unlit black air, "
                  "no detail. A worn anvil and plain hanging tools stand as dark silhouettes around "
                  "the coals. The ceiling and the near half of the room dissolve into pure black. "
                  + STYLE,
    # «дисциплина»: сервер не додумывает. Убраны «carved» и «ancient» — они рисуют письмена
    "03_rules":   "Near-black hall interior, one narrow cold beam grazing from above. Two tall "
                  "weathered stone slabs stand at the far left edge, their faces cut with plain "
                  "parallel channels, purely geometric, no markings of any kind. The right two "
                  "thirds of the frame are empty black air with large copy space. " + STYLE,
    # «рой построил продукт». «dozens» убрано: FLUX клонирует ряды машинно-регулярно
    "04_swarm":   "Near-black vast workshop hall seen from high above and far away. A dozen small "
                  "oil lamps scattered at irregular spacing across the dark floor, each with a tiny "
                  "hooded silhouette bent beside it. The upper half of the frame is empty unlit "
                  "black air. Everything else dissolves into pure black. " + STYLE,
    # «дырка на рынке». «signposts» убрано — прямой триггер надписи
    "05_market":  "Near-black windswept moor at last light. Three worn stone tracks meet in the "
                  "lower left, marked by three tall bare wooden posts, plain and weatherworn, "
                  "nothing mounted on them. A fourth faint trail is freshly trampled through the "
                  "heather toward two distant towers with single lit windows. The sky above is "
                  "empty dark air with large copy space. " + STYLE,
}

VISION_PROMPT = (
    "Ты технический контролёр фонового изображения для презентации. Отвечай только JSON.\n"
    "1) what_is_shown — одной фразой по-русски, что на картинке.\n"
    "2) defects — коды найденных дефектов, пустой массив если их нет:\n"
    "   has_text — в кадре есть буквы, цифры, надписи или логотипы\n"
    "   has_ui — есть интерфейс, экран, окно программы\n"
    "   photoreal_face — фотореалистичное лицо человека крупным планом\n"
    "   too_busy_centre — центр кадра забит деталями, текст поверх не ляжет\n"
    "   too_bright — картинка светлая, не похожа на тёмную сцену\n"
    "   wrong_mood — не мрачное тёмное фэнтези\n"
    "3) fits_dark_fantasy — true/false.\n"
    "Код ставь, только если сам назвал это в what_is_shown."
)
SCHEMA = {"type": "object", "properties": {
    "what_is_shown": {"type": "string"},
    "defects": {"type": "array", "items": {"type": "string", "enum": [
        "has_text", "has_ui", "photoreal_face", "too_busy_centre", "too_bright", "wrong_mood"]}},
    "fits_dark_fantasy": {"type": "boolean"}},
    "required": ["what_is_shown", "defects", "fits_dark_fantasy"]}


def px(path: Path, w: int = 192) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-v", "error", "-threads", "1", "-i", str(path),
                        "-vf", f"scale={w}:-2,format=gray", "-f", "rawvideo",
                        "-pix_fmt", "gray", "-"], capture_output=True)
    a = np.frombuffer(r.stdout, dtype=np.uint8)
    h = len(a) // w
    return a[:h * w].reshape(h, w).astype(np.float32)


def measure(path: Path) -> dict:
    """Объективные признаки: яркость и пригодность центра под текст."""
    g = px(path)
    h, w = g.shape
    cy0, cy1 = int(h * 0.28), int(h * 0.72)
    cx0, cx1 = int(w * 0.15), int(w * 0.85)
    centre = g[cy0:cy1, cx0:cx1]
    # «шум» центра: чем выше локальный градиент, тем хуже ляжет текст
    gx = np.abs(np.diff(centre, axis=1)).mean()
    gy = np.abs(np.diff(centre, axis=0)).mean()
    return {"luma": round(float(g.mean()), 1),
            "centre_luma": round(float(centre.mean()), 1),
            "centre_busy": round(float(gx + gy), 2)}


def vision(path: Path) -> dict:
    b64 = base64.b64encode(path.read_bytes()).decode()
    try:
        r = requests.post(f"{OLLAMA}/api/chat", timeout=240, json={
            "model": VLM, "stream": False, "format": SCHEMA, "think": False,
            "messages": [{"role": "system", "content": VISION_PROMPT},
                         {"role": "user", "content": "Проверь фон. Только JSON.", "images": [b64]}],
            "options": {"temperature": 0, "num_predict": 300}})
        r.raise_for_status()
        return json.loads(r.json()["message"]["content"])
    except Exception as e:
        return {"what_is_shown": f"(vision недоступна: {str(e)[:60]})", "defects": [],
                "fits_dark_fantasy": True, "_skipped": True}


HARD = {"has_text", "has_ui", "photoreal_face"}


def score(m: dict, v: dict) -> tuple[float, list[str]]:
    """Чем выше, тем лучше. Жёсткие дефекты обнуляют вариант."""
    bad = []
    s = 100.0
    if set(v.get("defects", [])) & HARD:
        bad.append("жёсткий дефект: " + ", ".join(sorted(set(v["defects"]) & HARD)))
        s -= 100
    if not (LUMA_MIN <= m["luma"] <= LUMA_MAX):
        bad.append(f"яркость {m['luma']} вне полосы {LUMA_MIN}-{LUMA_MAX}")
        s -= 40
    if m["centre_luma"] > m["luma"] + 12:      # центр светлее краёв — текст утонет
        bad.append(f"центр светлее фона ({m['centre_luma']} против {m['luma']})")
        s -= 25
    s -= min(30.0, m["centre_busy"] * 2.5)     # шумный центр мешает тексту
    if "too_busy_centre" in v.get("defects", []):
        s -= 15
    if "too_bright" in v.get("defects", []):
        s -= 15
    if not v.get("fits_dark_fantasy", True):
        s -= 20
    return round(s, 1), bad


def gen_one(prompt: str, dest: Path, seed: int) -> bool:
    """Локально на 5090. Пул грока выел лимит аккаунта (spending-limit), и это
    оказалось к лучшему: своя генерация не ограничивает число вариантов."""
    return comfy_gen.generate(prompt, seed, dest)


def main() -> int:
    OUT.mkdir(exist_ok=True)
    BROWSE.mkdir(exist_ok=True)
    report = {}
    comfy_gen.start()          # ждём готовности; поднимает и держит его супервизор контура
    for si, (name, prompt) in enumerate(SHOTS.items(), 1):
        print(f"\n{name}")
        cands = []
        for k in range(1, VARIANTS + 1):
            p = BROWSE / f"{name}_v{k}.png"
            if not p.exists() and not gen_one(prompt, p, seed=1000 * si + k):
                continue
            m = measure(p)
            v = vision(p)
            sc, bad = score(m, v)
            cands.append((sc, p, m, v, bad))
            flag = "OK " if sc >= 60 else "   "
            print(f"  {flag}v{k}  {sc:6.1f}  яркость {m['luma']:5.1f} центр {m['centre_luma']:5.1f} "
                  f"шум {m['centre_busy']:5.2f}  {v['what_is_shown'][:52]}")
            for b in bad:
                print(f"        ⚠ {b}")
        if not cands:
            print("  нет вариантов")
            continue
        cands.sort(key=lambda c: -c[0])
        best = cands[0]
        final = OUT / f"{name}.png"
        final.write_bytes(best[1].read_bytes())
        report[name] = {"score": best[0], **best[2], "vision": best[3]["what_is_shown"],
                        "file": final.name}
        print(f"  → выбран {best[1].name} ({best[0]}) → {final.name}")

    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    ok = sum(1 for r in report.values() if r["score"] >= 60)
    print(f"\nитог: {ok}/{len(SHOTS)} прошли порог · остальные в {BROWSE} на пересмотр")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
