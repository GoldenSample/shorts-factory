# -*- coding: utf-8 -*-
"""Шаг 4: датасет для дообучения голоса Гора из транскриптов канала.

Запуск из venv chatterbox (librosa, soundfile). Вход: raw/<id>.wav + raw/<id>.json (все сегменты whisper)
и segments.jsonl (метрики voice_refs.py: sim к голосу Гора, flat, lp).

Отбор, каждый порог с причиной:
  ролик целиком вон, если медиана sim < 0.78: это новостные шортсы канала с СИНТЕТИЧЕСКОЙ озвучкой
      (замер 28.09: 8 роликов с медианой 0.72-0.75 против 0.82-0.91 у живого Гора);
  sim >= 0.80        свой голос без наложений;
  lp > -0.45, ns < 0.3   whisper уверен в тексте, иначе модель учит неправильное произношение;
  7..22 знаков/с     защита от съехавших таймкодов (текст не того куска);
  длина 3..15 с.
Нарезка: границы по сегменту whisper, но не заходя в соседний; края подрезаются по энергии,
потом тишина 0.08 с в начале и 0.15 с в конце; громкость к RMS -20 dBFS с пиком не выше -1 dBFS.
Отложенный тест: 24 сегмента из разных роликов в обучение не идут, на них сравниваются модели
(синтез той же фразы против живой записи Гора).
Подложка: отношение громкости пауз к речи по ролику (музыка под голосом = паузы громкие).
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE / "work_voice_gor"
RAW = ROOT / "raw"
DS = ROOT / "dataset"
WAVS = DS / "wavs"
SR = 24000
SEP = ROOT / "sep" / "htdemucs_ft"


def load_voice(vid: str) -> tuple[np.ndarray, bool]:
    """Голос без фона (demucs htdemucs_ft), если отделён; иначе исходник."""
    v = SEP / vid / "vocals.wav"
    if v.exists():
        w, _ = librosa.load(str(v), sr=SR, mono=True)
        return w.astype(np.float32), True
    w, _ = sf.read(RAW / f"{vid}.wav", dtype="float32")
    return w, False


def rms_db(w: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(w ** 2)) + 1e-9))


def gap_ratio(wav: np.ndarray, segs: list[dict]) -> float:
    """Громкость пауз между сегментами минус громкость речи, дБ."""
    speech, gaps = [], []
    for a, b in zip(segs, segs[1:]):
        speech.append(wav[int(a["s"] * SR):int(a["e"] * SR)])
        if b["s"] - a["e"] >= 0.35:
            gaps.append(wav[int((a["e"] + 0.1) * SR):int((b["s"] - 0.1) * SR)])
    if not gaps or not speech:
        return float("nan")
    return rms_db(np.concatenate(gaps)) - rms_db(np.concatenate(speech))


def main() -> int:
    rows = [json.loads(x) for x in (ROOT / "segments.jsonl").open(encoding="utf-8")]
    by_vid = defaultdict(list)
    for r in rows:
        by_vid[r["vid"]].append(r)
    synthetic = {v for v, rs in by_vid.items() if st.median(x["sim"] for x in rs) < 0.78}
    print(f"роликов {len(by_vid)}, синтетических вон: {len(synthetic)} {sorted(synthetic)}")

    WAVS.mkdir(parents=True, exist_ok=True)
    kept, report = [], []
    for vid, rs in sorted(by_vid.items()):
        if vid in synthetic:
            continue
        segs = json.loads((RAW / f"{vid}.json").read_text(encoding="utf-8"))
        wav, clean = load_voice(vid)
        if not clean:
            print(f"  {vid}: голос не отделён, беру исходник")
        gr = gap_ratio(wav, segs)
        n0 = len(kept)
        for r in rs:
            text = r["t"].strip()
            cps = len(text.replace(" ", "")) / r["dur"]
            if not (r["sim"] >= 0.80 and r["lp"] > -0.45 and r["ns"] < 0.3 and 7 <= cps <= 22
                    and 3.0 <= r["dur"] <= 15.0):
                continue
            i = r["i"]
            lo = segs[i - 1]["e"] if i > 0 else 0.0
            hi = segs[i + 1]["s"] if i + 1 < len(segs) else len(wav) / SR
            a = max(lo, r["s"] - 0.12)
            b = min(hi, r["e"] + 0.25)
            w = wav[int(a * SR):int(b * SR)]
            w, _ = librosa.effects.trim(w, top_db=40, frame_length=1024, hop_length=256)
            if len(w) < SR * 2:
                continue
            w = w * (10 ** ((-20 - rms_db(w)) / 20))
            pk = np.max(np.abs(w))
            if pk > 0.891:
                w = w * (0.891 / pk)
            w = np.concatenate([np.zeros(int(0.08 * SR), np.float32), w.astype(np.float32),
                                np.zeros(int(0.15 * SR), np.float32)])
            name = f"{vid}_{i:04d}.wav"
            sf.write(WAVS / name, w, SR)
            kept.append({"vid": vid, "audio": str((WAVS / name).resolve()), "text": text,
                         "dur": round(len(w) / SR, 2), "sim": r["sim"]})
        report.append((vid, len(kept) - n0, gr))

    print(f"\n{'ролик':14} {'взято':>5}  паузы к речи, дБ (выше -25 = подложка)")
    for vid, n, gr in report:
        flag = "  <- подложка?" if gr == gr and gr > -25 else ""
        print(f"{vid:14} {n:5d}  {gr:6.1f}{flag}")

    random.seed(7)
    per_vid = defaultdict(list)
    for k in kept:
        per_vid[k["vid"]].append(k)
    big = sorted((v for v in per_vid if len(per_vid[v]) >= 20), key=lambda v: -len(per_vid[v]))
    test = []
    for v in big:
        test += random.sample(per_vid[v], min(3, len(per_vid[v])))
        if len(test) >= 24:
            break
    test_ids = {t["audio"] for t in test}
    train = [k for k in kept if k["audio"] not in test_ids]

    refs = json.loads((ROOT / "refs" / "refs.json").read_text(encoding="utf-8"))
    r0 = refs[0]
    rw, _ = load_voice(r0["vid"])
    rw = rw[int((r0["s"] - 0.05) * SR):int((r0["e"] + 0.15) * SR)]
    rw = rw * (10 ** ((-20 - rms_db(rw)) / 20))
    sf.write(DS / "ref_clean.wav", rw.astype(np.float32), SR)
    ref = str((DS / "ref_clean.wav").resolve())
    with (DS / "train_raw.jsonl").open("w", encoding="utf-8") as f:
        for k in train:
            f.write(json.dumps({"audio": k["audio"], "text": k["text"], "ref_audio": ref,
                                "language": "Russian"}, ensure_ascii=False) + "\n")
    with (DS / "test.jsonl").open("w", encoding="utf-8") as f:
        for k in test:
            f.write(json.dumps(k, ensure_ascii=False) + "\n")
    hrs = sum(k["dur"] for k in train) / 3600
    print(f"\nобучение: {len(train)} фраз, {hrs:.2f} ч · тест: {len(test)} фраз")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
