# -*- coding: utf-8 -*-
"""Бенч OCR готового ролика на локальных моделях со зрением (Ollama на 5090).

Роль, ради которой держим большой MoE (sudya = qwen3.5:122b): читать текст с кадров ГОТОВЫХ роликов
(плашки, цифры, вшитые субтитры) для приёмки. Эталон известен точно: кадры Samsung-шортса,
текст которых задан в build_samsung_short.py.

Метрика: доля эталонных слов и чисел, найденных в ответе (recall), + лишние числа, которых на кадре нет
(галлюцинации цифр опаснее пропусков), + время на кадр (первый кадр отдельно: загрузка модели).
  py -3.12 bench_video_ocr.py
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
VIDEO = HERE / "out" / "short_samsung_9100_GOR_VOICE.mp4"
WORK = HERE / "work_voice_gor" / "ocr_bench"
OLLAMA = "http://10.77.0.2:11434"
MODELS = ["glm-ocr:latest", "qwen3-vl:8b-instruct", "huihui_ai/Qwen3.6-abliterated:35b-a3b", "sudya:latest"]
PROMPT = ("Перепиши дословно весь текст, который виден на кадре, сверху вниз, строка за строкой. "
          "Ничего не добавляй от себя, не переводи, не объясняй. Цифры переписывай точно как на кадре.")

# (секунда ролика, эталонный текст кадра): середина каждой сцены
FRAMES = [
    (4.0, "ЖЕЛЕЗО БЕЗ ХАЙПА Самый быстрый SSD Самсунга подешевел на треть. Но заголовки молчат о трёх вещах. "
          "Подешевел на треть. Но есть три «но»"),
    (26.0, "ЧТО ВНУТРИ SAMSUNG 9100 PRO 4TB Чтение 14 800 мегабайт в секунду PCIe 5.0 Запись 13 400 мегабайт в секунду "
           "Цена на Woot −36% $619.99 против $972 Гарантия Woot 90 дней своя, не самсунговская 14 800 МБ/с. Гарантия — 90 дней"),
    (36.0, "REDDIT R/BUILDAPC «У меня 990 Pro уже два года — разницы в играх ноль» тред «990 Pro vs 9100 Pro 4TB» "
           "Реддит: «в играх разницы ноль»"),
    (46.0, "ПОДВОХ ПЕРВЫЙ БЕЗ PCIE 5.0 ПЛАТЫ Твоя материнка Gen4? ≈7 000 мегабайт в секунду потолок слота "
           "То есть платишь за ×2 скорость, которую не увидишь На Gen4-плате — те же 7 ГБ/с"),
    (65.0, "ФОРУМ SAMSUNG «BSOD, диск исчезает из BIOS — помогает только передёрнуть питание» "
           "тред про 9100 Pro 4TB прошивка 0B2QNXH7 Форум Samsung: BSOD и исчезающий диск"),
    (75.0, "ИТОГО КОМУ ЧТО БРАТЬ Для игр 990 Pro дешевле, холоднее, разницы не увидишь "
           "Монтаж и большие файлы 9100 Pro если платформа реально Gen5 Игры → 990 Pro. Работа → 9100 Pro"),
]


def toks(s: str) -> list[str]:
    s = s.lower().replace("ё", "е").replace(" ", " ")
    s = re.sub(r"(\d) (\d{3})", r"\1\2", s)              # 14 800 -> 14800
    return re.findall(r"[a-zа-я0-9]+(?:[.,][0-9]+)?", s)


def nums(s: str) -> set[str]:
    return {t for t in toks(s) if re.search(r"\d", t)}


def ask(model: str, img: Path) -> tuple[str, float]:
    body = {"model": model, "stream": False, "think": False, "keep_alive": "10m",
            "options": {"temperature": 0, "num_predict": 700},
            "messages": [{"role": "user", "content": PROMPT,
                          "images": [base64.b64encode(img.read_bytes()).decode()]}]}
    t0 = time.perf_counter()
    r = urllib.request.urlopen(urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"}), timeout=900)
    out = json.loads(r.read())["message"]["content"]
    return out, time.perf_counter() - t0


def unload(model: str) -> None:
    try:
        urllib.request.urlopen(urllib.request.Request(OLLAMA + "/api/generate", data=json.dumps(
            {"model": model, "keep_alive": 0}).encode(), headers={"Content-Type": "application/json"}), timeout=60).read()
    except Exception:
        pass


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    imgs = []
    for sec, ref in FRAMES:
        p = WORK / f"f{int(sec):03d}.png"
        if not p.exists():
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(sec), "-i", str(VIDEO), "-frames:v", "1", str(p)],
                           check=True)
        imgs.append((p, ref))
    report = {}
    for m in MODELS:
        rows = []
        for i, (p, ref) in enumerate(imgs):
            try:
                out, sec = ask(m, p)
            except Exception as e:
                out, sec = f"ОШИБКА {e}", 0.0
            rt, ot = toks(ref), set(toks(out))
            recall = sum(t in ot for t in rt) / len(rt)
            fake = sorted(nums(out) - nums(ref))
            rows.append({"frame": p.name, "recall": round(recall, 3), "fake_nums": fake, "sec": round(sec, 1),
                         "out": out[:400]})
            print(f"  {m:40} {p.name} recall {recall:.2f} лишние числа {fake[:4]} {sec:.1f} с", flush=True)
        warm = [r["sec"] for r in rows[1:]]
        report[m] = {"recall": round(sum(r["recall"] for r in rows) / len(rows), 3),
                     "fake_nums": sum(len(r["fake_nums"]) for r in rows),
                     "first_sec": rows[0]["sec"], "warm_sec": round(sum(warm) / len(warm), 1), "rows": rows}
        unload(m)
    (WORK / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{'модель':42} {'recall':>7} {'лишн.чисел':>10} {'1-й кадр':>9} {'кадр тёплый':>11}")
    for m, r in report.items():
        print(f"{m:42} {r['recall']:7.3f} {r['fake_nums']:10d} {r['first_sec']:8.1f}с {r['warm_sec']:10.1f}с")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
