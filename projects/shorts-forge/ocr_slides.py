# -*- coding: utf-8 -*-
"""OCR всех слайдов доклада локальной vision-моделью (qwen3-vl на Ollama).

Зачем: машинный текст слайдов нужен (а) для генерации фонов под сценарий —
сцены выводятся из содержимого, (б) для сверки скрипт↔слайд, (в) как поисковый
слой по докладу. Никаких облаков: карта своя, слайды не покидают машину.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import requests

BUILD = Path(r"C:\Users\Administrator\Desktop\build2\build\slides")
OUT = Path(__file__).resolve().parent / "out"
OLLAMA = "http://127.0.0.1:11434"
VLM = "qwen3-vl:8b-instruct"

PROMPT = (
    "Перед тобой слайд презентации. Перепиши ВЕСЬ текст слайда как есть, "
    "по-русски, сверху вниз, сохраняя структуру строками. Числа и латиницу "
    "не искажай. Если на слайде скриншот интерфейса — опиши его одной строкой "
    "в квадратных скобках, а видимый в нём текст не переписывай. Только текст, "
    "без комментариев."
)


def ocr(png: Path) -> str:
    b64 = base64.b64encode(png.read_bytes()).decode()
    r = requests.post(f"{OLLAMA}/api/chat", timeout=300, json={
        "model": VLM, "stream": False, "think": False,
        "messages": [{"role": "user", "content": PROMPT, "images": [b64]}],
        "options": {"temperature": 0, "num_predict": 1200}})
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def main() -> int:
    OUT.mkdir(exist_ok=True)
    report = {}
    for deck in ("course", "game"):
        for png in sorted((BUILD / deck).glob("*.png")):
            key = f"{deck}/{png.stem}"
            try:
                report[key] = ocr(png)
                print(f"  {key}: {len(report[key])} зн.")
            except Exception as e:
                report[key] = f"(ошибка: {str(e)[:80]})"
                print(f"  {key}: ОШИБКА {str(e)[:60]}")
    dest = OUT / "slides_ocr.json"
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    md = OUT / "slides_ocr.md"
    md.write_text("\n\n".join(f"## {k}\n\n{v}" for k, v in report.items()),
                  encoding="utf-8")
    print(f"\nготово: {dest.name}, {md.name} · слайдов {len(report)}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
