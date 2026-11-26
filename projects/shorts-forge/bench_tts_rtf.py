# -*- coding: utf-8 -*-
"""Бенч скорости локальных TTS: RTF (секунды счёта на секунду речи) на RTX 5090.

Запуск в venv движка:  <venv>\\python bench_tts_rtf.py qwen_sft|qwen_icl|chatterbox
(VoiceStudio меряется отдельно по HTTP: bench_tts_rtf.py vstudio из любого venv с requests).
Протокол: прогрев одной фразой, затем 3 замера на двух фразах (короткая и длинная), медиана.
Выход дописывается в work_voice_gor/bench_rtf.jsonl.
"""
from __future__ import annotations

import json
import statistics as st
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE / "work_voice_gor"
REF = ROOT / "dataset" / "ref_clean.wav"
REF_TEXT = "старого вот этого консольного игродела потому что очевидно что если у тебя есть подписка"

SHORT = "Правило одно: плати за скорость, которую твоя система реально умеет использовать."
LONG = ("Самый быстрый эс эс дэ Самсунга внезапно подешевел на треть. Но прежде чем нести деньги, "
        "три вещи, о которых заголовки молчат. Внутри почти пятнадцать гигабайт в секунду на чтение, "
        "вдвое быстрее прошлого поколения, но без новой платформы вы этого не увидите.")


def audio_sec(w, sr) -> float:
    import numpy as np
    return len(np.asarray(w).reshape(-1)) / sr


def bench(gen) -> dict:
    gen(SHORT)                                    # прогрев: первый вызов держит компиляцию и кэши
    rows = []
    for text in (SHORT, LONG):
        for _ in range(3):
            t0 = time.perf_counter()
            dur = gen(text)
            rows.append((time.perf_counter() - t0, dur))
    rtf = [c / d for c, d in rows]
    return {"rtf_median": round(st.median(rtf), 3), "rtf_min": round(min(rtf), 3),
            "sec_per_10s": round(st.median(rtf) * 10, 2),
            "gen_sec": [round(c, 2) for c, _ in rows], "audio_sec": [round(d, 2) for _, d in rows]}


def main() -> int:
    engine = sys.argv[1]
    if engine in ("qwen_sft", "qwen_icl"):
        import torch
        from qwen_tts import Qwen3TTSModel
        path = r"C:\Apps\voice-models\gor-qwen-v3\best" if engine == "qwen_sft" \
            else r"H:\comfy-models\TTS\Qwen3-TTS-12Hz-1.7B-Base"
        m = Qwen3TTSModel.from_pretrained(path, device_map="cuda", dtype=torch.bfloat16,
                                          attn_implementation="sdpa")
        prompt = m.create_voice_clone_prompt(ref_audio=str(REF), ref_text=REF_TEXT) if engine == "qwen_icl" else None

        def gen(text):
            if engine == "qwen_sft":
                wavs, sr = m.generate_custom_voice(text=text, speaker="gor", language="Auto")
            else:
                wavs, sr = m.generate_voice_clone(text=text, language="Russian", voice_clone_prompt=prompt)
            return audio_sec(wavs[0], sr)
    elif engine == "chatterbox":
        import torch
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        tts = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
        tts.prepare_conditionals(str(REF), exaggeration=0.5)

        def gen(text):
            with torch.inference_mode():
                w = tts.generate(text, language_id="ru", cfg_weight=0.5, temperature=0.7)
            return audio_sec(w.squeeze(0).cpu().numpy(), tts.sr)
    elif engine == "vstudio":
        import io
        import wave
        import requests

        def gen(text):
            r = requests.post("http://localhost:3900/generate", timeout=600,
                              data={"text": text, "language": "ru"})
            r.raise_for_status()
            with wave.open(io.BytesIO(r.content)) as f:
                return f.getnframes() / f.getframerate()
    else:
        raise SystemExit("движки: qwen_sft qwen_icl chatterbox vstudio")

    res = {"engine": engine, **bench(gen)}
    with (ROOT / "bench_rtf.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(res, ensure_ascii=False) + "\n")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
