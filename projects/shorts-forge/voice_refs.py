# -*- coding: utf-8 -*-
"""Шаг 2 голосового датасета Гора: проверка «один ли голос» и отбор чистых кусков.

Запускается из venv chatterbox (C:\\Apps\\chatterbox\\.venv): оттуда берётся VoiceEncoder
(эмбеддинг говорящего, 256 измерений) и librosa.

По каждому сегменту транскрипта длиной 3-16 с:
  sim   косинус эмбеддинга к медианному голосу всех роликов (большинство = Гор);
        низкий sim = другой человек, музыка, вставка из чужого видео;
  flat  медиана спектральной плоскости по громким окнам (шум, музыкальная подложка);
  lp    уверенность whisper (кривая дикция, наложения, мат через бип).
Выход:
  work_voice_gor/segments.jsonl   все сегменты с метриками (датасет для дообучения);
  work_voice_gor/refs/ref_NN.wav  лучшие 8-12 с референсы + refs.json с транскриптами.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import torch

from chatterbox.models.voice_encoder import VoiceEncoder

HERE = Path(__file__).resolve().parent
ROOT = HERE / "work_voice_gor"
RAW = ROOT / "raw"
REFS = ROOT / "refs"
VE_CKPT = Path(r"C:\Users\Administrator\.cache\huggingface\hub\models--ResembleAI--chatterbox"
               r"\snapshots\5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18\ve.pt")
SR = 24000


def flatness(w: np.ndarray) -> float:
    s = np.abs(librosa.stft(w, n_fft=1024, hop_length=256)) + 1e-9
    rms = s.mean(axis=0)
    loud = rms > np.percentile(rms, 40)
    f = librosa.feature.spectral_flatness(S=s)[0]
    return float(np.median(f[loud])) if loud.any() else 1.0


def main() -> int:
    ve = VoiceEncoder()
    ve.load_state_dict(torch.load(VE_CKPT, map_location="cuda", weights_only=True))
    ve.to("cuda").eval()

    rows = []
    for js in sorted(RAW.glob("*.json")):
        wav, _ = sf.read(js.with_suffix(".wav"), dtype="float32")
        segs = json.loads(js.read_text(encoding="utf-8"))
        batch, meta = [], []
        for i, sg in enumerate(segs):
            d = sg["e"] - sg["s"]
            if not 3.0 <= d <= 16.0:
                continue
            w = wav[int(sg["s"] * SR):int(sg["e"] * SR)]
            if len(w) < SR * 2:
                continue
            batch.append(librosa.resample(w, orig_sr=SR, target_sr=16000))
            meta.append((i, sg, w))
        if not batch:
            continue
        with torch.inference_mode():
            emb = ve.embeds_from_wavs(batch, sample_rate=16000)
        for (i, sg, w), e in zip(meta, emb):
            rows.append({"vid": js.stem, "i": i, "s": sg["s"], "e": sg["e"], "t": sg["t"],
                         "lp": sg["lp"], "ns": sg["ns"], "dur": round(sg["e"] - sg["s"], 2),
                         "rms": round(float(np.sqrt(np.mean(w ** 2))), 4),
                         "flat": round(flatness(w), 4), "emb": np.asarray(e, dtype=np.float32)})
        print(f"  {js.stem}: {len(meta)} сегментов")

    E = np.stack([r["emb"] for r in rows])
    E /= np.linalg.norm(E, axis=1, keepdims=True)
    centroid = np.median(E, axis=0)
    centroid /= np.linalg.norm(centroid)
    np.save(ROOT / "centroid.npy", centroid)
    sims = E @ centroid
    for r, s in zip(rows, sims):
        r["sim"] = round(float(s), 4)

    # второй голос: всё, что заметно ниже основной массы
    thr = float(np.percentile(sims, 50) - 3 * (np.percentile(sims, 50) - np.percentile(sims, 16)))
    foreign = [r for r in rows if r["sim"] < thr]
    print(f"\nсегментов {len(rows)}, медиана sim {np.median(sims):.3f}, порог чужого {thr:.3f}, "
          f"чужих {len(foreign)} ({100 * len(foreign) / len(rows):.1f} %)")
    by_vid = {}
    for r in foreign:
        by_vid[r["vid"]] = by_vid.get(r["vid"], 0) + 1
    print("чужие по роликам:", by_vid)
    for r in sorted(foreign, key=lambda x: x["sim"])[:8]:
        print(f"   sim {r['sim']:.3f} {r['vid']} {r['s']:.0f}с: {r['t'][:70]}")

    with (ROOT / "segments.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({k: v for k, v in r.items() if k != "emb"}, ensure_ascii=False) + "\n")

    if (REFS / "refs.json").exists():
        print("refs.json уже есть: референсы не трогаю (пробы клонов на них завязаны)")
        return 0
    # референсы: чистая речь 8-12 с, свой голос, уверенный транскрипт, без подложки
    pool = [r for r in rows if 8.0 <= r["dur"] <= 12.5 and r["sim"] >= thr and r["lp"] > -0.25
            and r["ns"] < 0.1 and r["flat"] < np.percentile([x["flat"] for x in rows], 40)
            and r["rms"] > 0.03]
    pool.sort(key=lambda r: (r["sim"] + r["lp"] * 0.5), reverse=True)
    REFS.mkdir(exist_ok=True)
    picked, used = [], {}
    for r in pool:
        if used.get(r["vid"], 0) >= 2:
            continue
        used[r["vid"]] = used.get(r["vid"], 0) + 1
        wav, _ = sf.read(RAW / f"{r['vid']}.wav", dtype="float32")
        w = wav[int((r["s"] - 0.05) * SR):int((r["e"] + 0.15) * SR)]
        name = f"ref_{len(picked):02d}.wav"
        sf.write(REFS / name, w, SR)
        picked.append({"file": name, **{k: r[k] for k in ("vid", "s", "e", "t", "sim", "lp", "flat", "dur")}})
        if len(picked) >= 10:
            break
    (REFS / "refs.json").write_text(json.dumps(picked, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nреференсов {len(picked)} из пула {len(pool)}:")
    for p in picked:
        print(f"  {p['file']} sim {p['sim']:.3f} lp {p['lp']:.2f} {p['dur']:.1f}с {p['vid']}: {p['t'][:60]}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
