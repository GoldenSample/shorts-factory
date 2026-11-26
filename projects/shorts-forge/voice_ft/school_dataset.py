# -*- coding: utf-8 -*-
"""«Русская школа» для двойника: многодикторный датасет с размеченными ударениями.

Зачем (слово Гора 03.10: «давай обучим модель сами на массиве данных», «ударения салам пополам»):
на 2 часах Гора модель учится его тембру, но русские ударения ей нужно показать на сотнях часов
разных дикторов. Все тексты размечаются знаком ударения (70 % многосложных слов, silero-stress), чтобы
модель выучила: знак есть = ударение здесь. Потом поверх школы дообучается голос Гора.

Источники (только с лицензией, разрешающей коммерцию):
  M-AILABS ru_RU   47 ч, лицензия M-AILABS (BSD-подобная)   H:\\tts_data\\mailabs
  Russian LibriSpeech (OpenSLR 96)  98 ч, общественное достояние   H:\\tts_data\\ruls
Выход: H:\\tts_data\\school\\wavs\\*.wav (24 кГц моно, -20 dBFS), school_raw.jsonl и school_eval_raw.jsonl.
Запуск из venv qwen-tts (silero-stress, num2words, librosa).
"""
from __future__ import annotations

import csv
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from gor_normalize import normalize            # noqa: E402
from gor_stress import accent                  # noqa: E402

DATA = Path(r"H:\tts_data")
OUT = DATA / "school"
WAVS = OUT / "wavs"
SR = 24000
LAT = re.compile(r"[A-Za-z]")


def mailabs() -> list[dict]:
    recs = []
    for meta in (DATA / "mailabs").rglob("metadata.csv"):
        spk = meta.parent.parent.name                 # by_book/<пол>/<диктор>/<книга>/metadata.csv
        for row in csv.reader(meta.open(encoding="utf-8"), delimiter="|", quoting=csv.QUOTE_NONE):
            if len(row) < 2:
                continue
            wav = meta.parent / "wavs" / f"{row[0]}.wav"
            text = (row[2] if len(row) > 2 and row[2].strip() else row[1]).strip()
            if wav.exists() and text:
                recs.append({"src": str(wav), "text": text, "spk": "mailabs_" + spk})
    return recs


def ruls() -> list[dict]:
    """RuLS: <split>/manifest.json, строка = {audio_filepath, duration, text, text_no_preprocessing, score};
    текст берём с пунктуацией (text_no_preprocessing), диктор = номер чтеца (первая папка в audio/)."""
    recs = []
    for split in ("train", "dev", "test"):
        man = DATA / "ruls" / split / "manifest.json"
        if not man.exists():
            continue
        for line in man.open(encoding="utf-8"):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            wav = DATA / "ruls" / split / r["audio_filepath"]
            text = (r.get("text_no_preprocessing") or r.get("text") or "").strip()
            spk = Path(r["audio_filepath"]).parts[1] if len(Path(r["audio_filepath"]).parts) > 1 else "x"
            if text and 2.0 <= float(r.get("duration", 0)) <= 14.0:
                recs.append({"src": str(wav), "text": text, "spk": "ruls_" + spk})
    return recs


def main() -> int:
    WAVS.mkdir(parents=True, exist_ok=True)
    src = mailabs() + ruls()
    print("исходных фраз:", len(src))
    by_spk = defaultdict(list)
    kept = []
    rnd = random.Random(7)
    for i, r in enumerate(src):
        try:
            info = sf.info(r["src"])
        except Exception:
            continue
        if not 2.0 <= info.duration <= 14.0:
            continue
        t = normalize(r["text"])
        if LAT.search(t) or len(t) < 8:
            continue
        name = f"{r['spk']}_{i:06d}.wav"
        dst = WAVS / name
        if not dst.exists():
            w, _ = librosa.load(r["src"], sr=SR, mono=True)
            w, _ = librosa.effects.trim(w, top_db=40)
            if len(w) < SR * 1.5:
                continue
            w = w * (10 ** ((-20 - 20 * np.log10(np.sqrt(np.mean(w ** 2)) + 1e-9)) / 20))
            w = np.clip(w, -0.95, 0.95)
            sf.write(dst, np.concatenate([np.zeros(int(0.08 * SR)), w, np.zeros(int(0.15 * SR))]).astype(np.float32), SR)
        rec = {"audio": str(dst), "text": accent(t, share=0.7, seed=i), "spk": r["spk"], "language": "Russian"}
        kept.append(rec)
        by_spk[r["spk"]].append(str(dst))
        if len(kept) % 2000 == 0:
            print(f"  {len(kept)} фраз", flush=True)
    for rec in kept:                                   # образец голоса = другая фраза того же диктора
        pool = by_spk[rec["spk"]]
        rec["ref_audio"] = rnd.choice([p for p in pool if p != rec["audio"]] or pool)
    rnd.shuffle(kept)
    n_eval = max(50, len(kept) // 100)
    for name, part in (("school_eval_raw.jsonl", kept[:n_eval]), ("school_raw.jsonl", kept[n_eval:])):
        with (OUT / name).open("w", encoding="utf-8") as f:
            for r in part:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    hrs = sum(sf.info(r["audio"]).duration for r in kept[:500]) / 500 * len(kept) / 3600
    print(f"итого {len(kept)} фраз, ~{hrs:.0f} ч, дикторов {len(by_spk)}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
