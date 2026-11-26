# -*- coding: utf-8 -*-
"""Архив камеры Гора -> чистая речь Гора и кандидаты эталона Drama 3 (по образцу voice_refs.py, venv qwen-tts).

Отличие от voice_refs.py: на камере говорят и другие (Лёха, клиенты), поэтому голос Гора меряется к готовому
медианному голосу его роликов @GSPCS (work_voice_gor/centroid_qwen.npz от spk_embed.py check: кодировщик диктора
Qwen3-TTS Base, отпечаток минус средний голос чужих дикторов; чистый Гор к центру >= 0.60, чужие <= 0.20).
По каждому сегменту расшифровки 3-20 с: sim (к голосу Гора), flat (шум, подложка), lp и ns (уверенность whisper).
Выход H:\\tts_data\\gor_camera\\segments.jsonl (все с метриками) и candidates.json (лучшие 8-20 с для эталона).
  C:/Apps/qwen-tts/.venv/Scripts/python.exe camera_refs.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from spk_embed import SpkEmb

ROOT = Path(r"H:\tts_data\gor_camera")
RAW, ASR = ROOT / "raw", ROOT / "asr"
CENTROID = Path(r"C:\CLAUD\projects\shorts-forge\work_voice_gor\centroid_qwen.npz")


def flatness(w: np.ndarray) -> float:
    s = np.abs(librosa.stft(w, n_fft=1024, hop_length=256)) + 1e-9
    rms = s.mean(axis=0)
    loud = rms > np.percentile(rms, 40)
    f = librosa.feature.spectral_flatness(S=s)[0]
    return float(np.median(f[loud])) if loud.any() else 1.0


def main() -> int:
    se = SpkEmb()
    z = np.load(CENTROID)
    c, mu = z["centroid"], z["mu"]
    rows = []
    for js in sorted(ASR.glob("*.json")):
        wavp = RAW / (js.stem + ".wav")
        if not wavp.exists():
            continue
        wav, sr = sf.read(wavp, dtype="float32")
        res = json.loads(js.read_text(encoding="utf-8"))
        n = 0
        for i, sg in enumerate(res.get("segments", [])):
            d = sg["e"] - sg["s"]
            if not 3.0 <= d <= 20.0:
                continue
            w = wav[int(sg["s"] * sr):int(sg["e"] * sr)]
            if len(w) < sr * 2:
                continue
            e = se(w, sr) - mu; e /= np.linalg.norm(e)
            rows.append({"vid": js.stem, "i": i, "s": sg["s"], "e": sg["e"], "t": sg.get("t", ""), "lp": sg.get("lp", 0.0),
                         "ns": sg.get("ns", 0.0), "dur": round(d, 2), "rms": round(float(np.sqrt(np.mean(w ** 2))), 4),
                         "flat": round(flatness(w), 6), "sim": round(float(e @ c), 4)})
            n += 1
        print(f"  {js.stem}: {n} сегментов", flush=True)
    if not rows:
        print("нет сегментов"); return 1
    sims = np.array([r["sim"] for r in rows])
    # порог по проверке spk_embed: чужие дикторы не выше 0.20, чистый Гор не ниже 0.60; камера (другой микрофон)
    # даёт Гору 0.46-0.82, поэтому 0.40, а полоса 0.20-0.40 считается спорной и в набор не идёт
    hist, edges = np.histogram(sims, bins=40, range=(-0.2, 1.0))
    thr = 0.40
    print(f"спорных 0.20-0.40: {int(((sims >= 0.2) & (sims < thr)).sum())}, чужих ниже 0.20: {int((sims < 0.2).sum())}")
    gor = [r for r in rows if r["sim"] >= thr]
    flat_med = float(np.percentile([x["flat"] for x in gor], 50)) if gor else 0.0
    clean = [r for r in gor if r["lp"] > -0.35 and r["ns"] < 0.2 and r["rms"] > 0.02 and r["flat"] < flat_med]
    hrs = lambda xs: round(sum(x["dur"] for x in xs) / 3600, 2)
    print(f"\nсегментов {len(rows)} ({hrs(rows)} ч), медиана sim {np.median(sims):.3f}, порог Гора {thr:.3f}")
    print("гистограмма sim:", " ".join(f"{edges[k]:.2f}:{hist[k]}" for k in range(len(hist)) if hist[k]))
    print(f"голос Гора {len(gor)} ({hrs(gor)} ч), из них чистые {len(clean)} ({hrs(clean)} ч)")
    ids = {(r["vid"], r["i"]) for r in clean}
    with (ROOT / "segments.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(dict(r, gor=r["sim"] >= thr, clean=(r["vid"], r["i"]) in ids), ensure_ascii=False) + "\n")
    cand = sorted([r for r in clean if 8.0 <= r["dur"] <= 20.0 and r["lp"] > -0.25],
                  key=lambda r: r["sim"] + 0.5 * r["lp"] - 2 * r["flat"], reverse=True)
    picked, per = [], {}
    for r in cand:                                         # не больше 3 с одной записи: разные дни, свет, настроение
        if per.get(r["vid"], 0) >= 3:
            continue
        per[r["vid"]] = per.get(r["vid"], 0) + 1
        picked.append(r)
        if len(picked) >= 40:
            break
    (ROOT / "candidates.json").write_text(json.dumps({"thr": thr, "picked": picked}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"кандидатов эталона {len(picked)}:")
    for r in picked[:12]:
        print(f"  sim {r['sim']:.3f} lp {r['lp']:.2f} flat {r['flat']:.5f} {r['dur']:.1f}с {r['vid'][-30:]}: {r['t'][:60]}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
