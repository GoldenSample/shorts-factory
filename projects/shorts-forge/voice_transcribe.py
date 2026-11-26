# -*- coding: utf-8 -*-
"""Шаг 1 голосового датасета Гора: транскрипт каждого ролика канала с таймкодами сегментов.

Запускается ТОЛЬКО из venv whisper (C:\\Apps\\whisper\\.venv): там faster-whisper и cuBLAS/cuDNN.
Выход рядом с wav: <id>.json = [{s, e, t, lp, ns}] (начало, конец, текст, avg_logprob, no_speech_prob).
Он же = корпус живого слога для сценариев шортсов (закон «тупой слог»: писать как говорит Гор).
"""
import json
import os
import sys
from pathlib import Path

VENV = Path(r"C:\Apps\whisper\.venv\Lib\site-packages\nvidia")
for d in ("cublas", "cudnn"):
    p = VENV / d / "bin"
    if p.is_dir():
        os.add_dll_directory(str(p))
        os.environ["PATH"] = str(p) + os.pathsep + os.environ["PATH"]

from faster_whisper import WhisperModel  # noqa: E402

RAW = Path(__file__).resolve().parent / "work_voice_gor" / "raw"


def main() -> int:
    model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    for wav in sorted(RAW.glob("*.wav")):
        dest = wav.with_suffix(".json")
        if dest.exists():
            continue
        segs, _ = model.transcribe(str(wav), language="ru", vad_filter=True,
                                   condition_on_previous_text=False)
        out = [{"s": round(s.start, 2), "e": round(s.end, 2), "t": s.text.strip(),
                "lp": round(s.avg_logprob, 3), "ns": round(s.no_speech_prob, 3)} for s in segs]
        dest.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        words = sum(len(o["t"].split()) for o in out)
        print(f"  {wav.stem}: {len(out)} сегментов, {words} слов")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
