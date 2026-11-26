# -*- coding: utf-8 -*-
"""Синтез фраз-ловушек ударений: v3 (обычный текст) против v4 (текст со знаками ударения).

  <venv qwen-tts>\\python stress_gen.py ЧЕКПОИНТ ТЕГ plain|marked
Выход: work_voice_gor/stress/<ТЕГ>/pNN.wav. Эталон ударений: work_voice_gor/stress/traps_truth.tsv.
"""
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gor_normalize import normalize  # noqa: E402

ST = HERE / "work_voice_gor" / "stress"


def main() -> int:
    ckpt, tag, mode = sys.argv[1:4]
    exam = len(sys.argv) > 4 and sys.argv[4] == "exam"   # 03.10: экзамен 60 фраз (exam_truth.tsv), файлы eNN.wav
    from qwen_tts import Qwen3TTSModel
    if exam:
        rows = [l.split("\t", 1) for l in (ST / "exam_truth.tsv").read_text(encoding="utf-8").splitlines() if l.strip()]
        lines = [t.replace("́", "") for _, t in rows]
    else:
        lines = [l.strip() for l in (ST / "traps.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    if mode == "marked":
        from gor_stress import accent
    m = Qwen3TTSModel.from_pretrained(ckpt, device_map="cuda", dtype=torch.bfloat16, attn_implementation="sdpa")
    out = ST / tag
    out.mkdir(parents=True, exist_ok=True)
    for i, l in enumerate(lines):
        p = out / (f"e{i:02d}.wav" if exam else f"p{i:02d}.wav")
        if p.exists():
            continue
        t = normalize(l)
        if mode == "marked":
            t = accent(t)
        torch.manual_seed(500 + i)
        wavs, sr = m.generate_custom_voice(text=t, speaker="gor", language="Auto")
        sf.write(p, np.asarray(wavs[0], dtype=np.float32), sr)
    print(f"{tag}: {len(lines)} фраз ({mode})")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
