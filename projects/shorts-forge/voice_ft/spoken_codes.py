# -*- coding: utf-8 -*-
"""Коды аудио те же, меняется только текст: train/test_codes.jsonl -> *_spoken_codes.jsonl
по произносимым текстам из voice_spoken_texts.py (перекодировать звук не нужно)."""
import json
import sys
from pathlib import Path

DS = Path(__file__).resolve().parents[1] / "work_voice_gor" / "dataset"


def remap(codes: str, texts: str, dest: str) -> int:
    new = {}
    with open(DS / texts, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            new[r["audio"]] = r["text"]
    n = 0
    with open(DS / codes, encoding="utf-8") as f, open(DS / dest, "w", encoding="utf-8") as g:
        for line in f:
            r = json.loads(line)
            if r["audio"] in new:
                r["text"] = new[r["audio"]]
                g.write(json.dumps(r, ensure_ascii=False) + "\n")
                n += 1
    return n


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print("обучение:", remap("train_codes.jsonl", "train_spoken_raw.jsonl", "train_spoken_codes.jsonl"))
    print("тест:    ", remap("test_codes.jsonl", "test_spoken.jsonl", "test_spoken_codes.jsonl"))
