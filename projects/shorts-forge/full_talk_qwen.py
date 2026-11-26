# -*- coding: utf-8 -*-
"""Переозвучка полного доклада голосом Serena (Qwen3-TTS-12Hz-1.7B, Apache-2.0).

Выбор Гора по пробам 29-07 из четырёх голосов CustomVoice. Логика та же, что
в full_talk.py (слайд стоит, пока звучит его текст; звук единой WAV-дорожкой),
движок другой:
  · Qwen3-TTS стабильнее Chatterbox — зацикливаний не ловили, поэтому ретрай
    один и только по фырк-детектору, без слоговой арифметики;
  · ударения: RUAccent-акуты НЕ подаются (поддержка не подтверждена) — Qwen
    ставит их сам заметно лучше Chatterbox; латиница транслитерируется тем же
    словарём, «+»-метки из него вычищаются;
  · ⛔ кодирование финала здесь НЕ делается. Урок вечера: параллельный тяжёлый
    процесс бьёт поток x264 (оба финала вышли с битыми NAL). Скрипт готовит
    голоса и слайд-видео, а финал кодируется отдельной одиночной командой.

Запуск: C:/Apps/qwen-tts/.venv/Scripts/python.exe full_talk_qwen.py part2
        (PATH должен содержать C:/Apps/sox/sox-14.4.2 — pysox требует бинарь)
"""
from __future__ import annotations

import re
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from full_talk import (  # noqa: E402
    BUILD, PARTS, EXTRA_FIX, W, H, FPS, PAUSE_SENT, PAUSE_SLIDE,
    parse_script, run, wav_len,
)
from course_reel import TTS_FIX  # noqa: E402

VOICE = "Serena"


def clean_fixes() -> dict:
    """Словарь замен без «+»-меток: Qwen сам ставит ударения."""
    out = {}
    for a, b in {**TTS_FIX, **EXTRA_FIX}.items():
        out[a] = b.replace("+", "")
    return out


def main() -> int:
    part = PARTS.get(sys.argv[1] if len(sys.argv) > 1 else "part2")
    if not part:
        print("part1 | part2")
        return 2
    slides_dir = BUILD / "slides" / part["slides"]
    work = HERE / f"work_talk_{part['slides']}_qwen"
    work.mkdir(exist_ok=True)

    slides = parse_script(BUILD / part["script"])
    print(f"{part['script']}: {len(slides)} слайдов, голос {VOICE}")

    import numpy as np
    import torch
    import soundfile as sf
    from qwen_tts import Qwen3TTSModel
    from gen_voices_cb import snort_free

    model = Qwen3TTSModel.from_pretrained(
        "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", device_map="cuda",
        dtype=torch.bfloat16)
    fixes = clean_fixes()

    def say(text: str) -> tuple[np.ndarray, int]:
        for a, b in fixes.items():
            text = text.replace(a, b)
        sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]
        chunks, sr = [], 24000
        for s in sents:
            best = None
            for _ in range(2):                       # ретрай только по фырку
                wavs, sr = model.generate_custom_voice(
                    text=s, speaker=VOICE, language="Russian")
                w = wavs[0] if isinstance(wavs, list) else wavs
                w = np.asarray(w, dtype=np.float32)
                best = w
                if snort_free(torch.from_numpy(w), sr):
                    break
            chunks.append(best)
            chunks.append(np.zeros(int(sr * PAUSE_SENT), dtype=np.float32))
        return np.concatenate(chunks[:-1]) if chunks else np.zeros(sr), sr

    entries = []
    for sl in slides:
        wav_p = work / f"s{sl['num']:02d}.wav"
        png = slides_dir / f"{sl['num']:02d}.png"
        if not png.exists():
            print(f"  {sl['num']:2}: НЕТ PNG — пропуск")
            continue
        if not wav_p.exists():
            audio, sr = say(sl["text"])
            sf.write(str(wav_p), audio, sr)
        d = 0.35 + wav_len(wav_p) + PAUSE_SLIDE
        entries.append((sl, png, wav_p, d))
        print(f"  {sl['num']:2} {sl['title'][:44]:44} {d:6.1f}с", flush=True)

    # слайд-видео и выровненный звук — как в full_talk, финал НЕ кодируем
    vparts = []
    for sl, png, wav_p, d in entries:
        vp = work / f"v{sl['num']:02d}.mp4"
        if not vp.exists():
            r = run(["ffmpeg", "-y", "-v", "error", "-threads", "2",
                     "-loop", "1", "-framerate", str(FPS), "-t", f"{d:.3f}",
                     "-i", str(png),
                     "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=#0c0b08,"
                            f"format=yuv420p,setsar=1",
                     "-r", str(FPS),
                     "-c:v", "libx264", "-preset", "medium", "-crf", "15",
                     "-pix_fmt", "yuv420p", str(vp)])
            if r.returncode != 0:
                print("   видео:", r.stderr.decode("utf-8", "replace")[-200:])
                continue
        vparts.append((vp, wav_p, d))

    awavs = []
    for vp, wav_p, d in vparts:
        ap = work / (vp.stem + "_a.wav")
        run(["ffmpeg", "-y", "-v", "error", "-i", str(wav_p),
             "-af", f"aresample=48000,adelay=350|350,apad,atrim=duration={d:.3f}",
             "-ac", "2", "-c:a", "pcm_s16le", str(ap)])
        awavs.append(ap)

    (work / "all_v.txt").write_text(
        "".join(f"file '{p[0].name}'\n" for p in vparts), encoding="utf-8")
    (work / "all_a.txt").write_text(
        "".join(f"file '{p.name}'\n" for p in awavs), encoding="utf-8")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(work / "all_a.txt"), "-c", "copy",
         str(work / "voice_all.wav")], cwd=work)
    print(f"ВХОДЫ ГОТОВЫ: {work} — финал кодировать одиночной командой")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
