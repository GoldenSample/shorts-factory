# -*- coding: utf-8 -*-
"""Судья клонов голоса Гора: разборчивость и сходство, числами, без «на слух показалось».

  C:\\Apps\\whisper\\.venv\\Scripts\\python voice_judge.py cer   whisper large-v3 -> CER к исходной фразе
  C:\\Apps\\chatterbox\\.venv\\Scripts\\python voice_judge.py sim  эмбеддинг -> косинус к голосу Гора + сводка

CER  = доля символьных правок между текстом фразы и тем, что услышал whisper (0 = дословно).
sim  = косинус к медианному голосу Гора по всем роликам (centroid.npy из voice_refs.py);
       для ориентира печатается разброс sim живых сегментов самого Гора.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE / "work_voice_gor"
PROBE = ROOT / "probe"
sys.path.insert(0, str(HERE))


def norm(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[^a-zа-я0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def cer(ref: str, hyp: str) -> float:
    a, b = norm(ref), norm(hyp)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / max(1, len(a))


def do_cer() -> None:
    from voice_clone_probe import LINES
    nv = Path(r"C:\Apps\whisper\.venv\Lib\site-packages\nvidia")
    for d in ("cublas", "cudnn"):
        p = nv / d / "bin"
        if p.is_dir():
            os.add_dll_directory(str(p))
            os.environ["PATH"] = str(p) + os.pathsep + os.environ["PATH"]
    from faster_whisper import WhisperModel
    m = WhisperModel("large-v3", device="cuda", compute_type="float16")
    out = {}
    for w in sorted(PROBE.glob("*.wav")):
        key = w.stem.rsplit("_", 1)[1]
        segs, _ = m.transcribe(str(w), language="ru", condition_on_previous_text=False)
        hyp = " ".join(s.text.strip() for s in segs)
        out[w.name] = {"cer": round(cer(LINES[key], hyp), 3), "hyp": hyp}
    (PROBE / "cer.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"CER посчитан для {len(out)} файлов")


def do_sim() -> None:
    import librosa
    import numpy as np
    import torch
    from chatterbox.models.voice_encoder import VoiceEncoder
    from voice_refs import VE_CKPT
    ve = VoiceEncoder()
    ve.load_state_dict(torch.load(VE_CKPT, map_location="cuda", weights_only=True))
    ve.to("cuda").eval()
    c = np.load(ROOT / "centroid.npy")
    live = [json.loads(x)["sim"] for x in (ROOT / "segments.jsonl").open(encoding="utf-8")]
    cers = json.loads((PROBE / "cer.json").read_text(encoding="utf-8")) if (PROBE / "cer.json").exists() else {}
    rows = []
    for w in sorted(PROBE.glob("*.wav")):
        a, sr = librosa.load(str(w), sr=16000)
        with torch.inference_mode():
            e = ve.embeds_from_wavs([a], sample_rate=16000)[0]
        e = e / np.linalg.norm(e)
        rows.append((w.name, float(e @ c), cers.get(w.name, {}).get("cer"), cers.get(w.name, {}).get("hyp", "")))
    print(f"живой Гор: sim p10 {np.percentile(live, 10):.3f} · медиана {np.median(live):.3f}\n")
    print(f"{'файл':40} {'sim':>6} {'CER':>6}  услышано")
    for name, s, ce, hyp in sorted(rows, key=lambda r: (r[2] if r[2] is not None else 9, -r[1])):
        print(f"{name:40} {s:6.3f} {ce if ce is not None else '-':>6}  {hyp[:70]}")
    agg = {}
    for name, s, ce, _ in rows:
        eng = name.split("_")[0]
        agg.setdefault(eng, []).append((s, ce or 0))
    print()
    for eng, v in agg.items():
        print(f"{eng:12} средний sim {np.mean([x[0] for x in v]):.3f} · средний CER {np.mean([x[1] for x in v]):.3f}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"cer": do_cer, "sim": do_sim}[sys.argv[1]]()
