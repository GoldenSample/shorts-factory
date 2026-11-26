# -*- coding: utf-8 -*-
"""Итерации стиля Серены на ОДНОМ слайде (метод Вани: крутить до хорошего звука).

Qwen3-TTS CustomVoice принимает `instruct` — свободную инструкцию стиля.
Гоняем первый слайд части 2 с разными инструкциями и температурами,
отдаём пачку mp3 на выбор. Запускать ТОЛЬКО на свободной карте.

Запуск: C:/Apps/qwen-tts/.venv/Scripts/python.exe probe_serena_styles.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from full_talk import BUILD, PARTS, parse_script  # noqa: E402
from full_talk_qwen import clean_fixes  # noqa: E402

OUT = HERE / "work_course"

VARIANTS = [
    ("base",     None, 0.9),
    ("moscow",   "Говори с чистым московским произношением, спокойным низким тоном, "
                 "размеренно, как опытный лектор перед аудиторией.", 0.9),
    ("piter",    "Говори с петербургской интеллигентной манерой, мягко и сдержанно, "
                 "неторопливо, с лёгкими паузами.", 0.9),
    ("calm_t06", "Говори спокойно и уверенно, ровным тоном рассказчика.", 0.6),
    ("warm",     "Тёплый дружеский тон, будто объясняешь коллеге за чашкой кофе, "
                 "без спешки.", 0.85),
]


def main() -> int:
    import subprocess
    import numpy as np
    import torch
    import soundfile as sf
    from qwen_tts import Qwen3TTSModel

    sl = parse_script(BUILD / PARTS["part2"]["script"])[0]
    text = sl["text"]
    for a, b in clean_fixes().items():
        text = text.replace(a, b)
    # первые три предложения слайда — хватает, чтобы услышать характер
    sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()][:3]
    text = " ".join(sents)
    print("текст пробы:", text[:120], "…")

    m = Qwen3TTSModel.from_pretrained("Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
                                      device_map="cuda", dtype=torch.bfloat16)
    for tag, instruct, temp in VARIANTS:
        wavs, sr = m.generate_custom_voice(
            text=text, speaker="Serena", language="Russian",
            instruct=instruct, temperature=temp)
        w = np.asarray(wavs[0] if isinstance(wavs, list) else wavs, dtype=np.float32)
        wav_p = OUT / f"_serena_{tag}.wav"
        sf.write(str(wav_p), w, sr)
        mp3 = OUT / f"_serena_{tag}.mp3"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(wav_p),
                        "-af", "loudnorm=I=-16:TP=-1.5",
                        "-c:a", "libmp3lame", "-b:a", "160k", str(mp3)],
                       capture_output=True)
        print(f"  {tag}: {len(w)/sr:.1f}с")
    print("готово: work_course/_serena_*.mp3")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
