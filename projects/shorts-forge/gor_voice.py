# -*- coding: utf-8 -*-
"""Боевая озвучка голосом Гора (Qwen3-TTS после SFT на его роликах).

Три шага в трёх venv, потому что каждый движок живёт в своём окружении:
  synth    (venv qwen-tts)   текст -> куски по 1-3 предложения -> N дублей на кусок с разными сидами
  judge    (venv whisper)    whisper large-v3 по каждому дублю: CER к тексту куска + длительность
  assemble (venv chatterbox) лучший дубль каждого куска -> склейка с паузами из распределения пауз Гора

  <qwen>\\python gor_voice.py synth текст.txt ПАПКА [--n 3] [--ckpt ЧЕКПОИНТ]
  <whisper>\\python gor_voice.py judge ПАПКА
  <chatterbox>\\python gor_voice.py assemble ПАПКА итог.wav

Правила из диприсёрча 28.09 (work_voice_gor/RESEARCH_VOICE_DOUBLE_2026-09-28.md, раздел 6):
  куски 1-3 предложения и не короче ~40 знаков (короткие фразы клеятся к соседним: у SFT первые
  1-2 секунды короткой фразы иногда уходят в чужой тембр); non-streaming; max_new_tokens от
  ожидаемой длительности, иначе без EOS модель может не остановиться; best-of-N по разборчивости;
  паузы не метрономом, а из реальных пауз Гора; громкость по EBU R128 на финальном файле.
Язык "Auto": SFT учит только раскладку без токена языка.
Текст подавать так, как его пишет whisper в транскриптах обучения (цифры и латиница как есть,
«RTX 5090», «DDR5»): на такой записи модель и училась. Ударения знаками не размечать.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE / "work_voice_gor"
# v3 = SFT на текстах в произносимой записи (словарь gor_lexicon.tsv); замер 29.09: SIM 0.736, темп 4.71 при живых 4.73
# v4 (03.10) = v3 + обучение на текстах со знаком ударения (Гор: «стало норм»); ударения ставит gor_stress
DEFAULT_CKPT = r"C:\Apps\voice-models\gor-qwen-v4\best"
# веса GigaAM в профиле Administrator: контроллер узла работает от SYSTEM, у него свой домашний каталог
GIGAAM_ROOT = os.environ.get("GIGAAM_ROOT", r"C:\Users\Administrator\.cache\gigaam")
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
VOW = set("аеёиоуыэюяaeiouy")
GOR_RATE = 4.3            # слогов в секунду чистой речи; уточняется замером voice_eval.py


def chunks(text: str, lo: int = 40, hi: int = 220) -> list[str]:
    text = re.sub(r"\s+", " ", text.replace("—", ",").replace("–", ",")).strip()
    sents = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", text) if s.strip()]
    out, cur = [], ""
    for s in sents:
        if not cur:
            cur = s
        elif len(cur) < lo or len(cur) + 1 + len(s) <= hi and len(s) < lo:
            cur += " " + s
        else:
            out.append(cur)
            cur = s
    if cur:
        if out and len(cur) < lo:
            out[-1] += " " + cur
        else:
            out.append(cur)
    return out


def expected_sec(t: str) -> float:
    return sum(ch in VOW for ch in t.lower()) / GOR_RATE + 0.4


def synth(src: Path, out: Path, n: int, ckpt: str, per_line: bool = False, norm: bool = True) -> None:
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel
    out.mkdir(parents=True, exist_ok=True)
    body = src.read_text(encoding="utf-8")
    if per_line:
        parts, lines_of = [], []
        for li, line in enumerate(x for x in body.splitlines() if x.strip()):
            for c in chunks(line):
                parts.append(c)
                lines_of.append(li)
    else:
        parts = chunks(body)
        lines_of = [0] * len(parts)
    m = Qwen3TTSModel.from_pretrained(ckpt, device_map="cuda", dtype=torch.bfloat16, attn_implementation="sdpa")
    man = {"ckpt": ckpt, "normalized": norm, "chunks": []}
    if norm:
        from gor_normalize import normalize, unknown
    stress = (Path(ckpt) / "STRESS_MARKS").exists()          # модель обучена слушаться знака ударения
    if stress:
        from gor_stress import accent
    man["stress_marks"] = stress
    for i, raw in enumerate(parts):
        t = normalize(raw) if norm else raw
        if stress:
            t = accent(t)
        mx = math.ceil(1.6 * expected_sec(t) * 12.5) + 25
        cands = []
        for k in range(n):
            p = out / f"c{i:03d}_{k}.wav"
            if not p.exists():
                torch.manual_seed(1000 * i + k)
                wavs, sr = m.generate_custom_voice(text=t, speaker="gor", language="Auto", max_new_tokens=mx)
                sf.write(p, np.asarray(wavs[0], dtype=np.float32), sr)
            cands.append(p.name)
        man["chunks"].append({"text": t, "raw": raw, "cands": cands, "expected": round(expected_sec(t), 2),
                              "line": lines_of[i]})
        print(f"  кусок {i + 1}/{len(parts)}: {len(t)} знаков", flush=True)
    if norm and unknown():
        man["unknown_latin"] = unknown()
        print("  ВНЕ СЛОВАРЯ (транслит наугад, впиши в gor_lexicon.tsv):", ", ".join(unknown()))
    (out / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")


def judge(out: Path) -> None:
    """GigaAM, если он есть в окружении (пишет словами, как нормализованный текст), иначе whisper."""
    try:
        import gigaam
    except ImportError:
        gigaam = None
    if gigaam is not None:
        return judge_giga(out, gigaam)
    nv = Path(r"C:\Apps\whisper\.venv\Lib\site-packages\nvidia")
    for d in ("cublas", "cudnn"):
        p = nv / d / "bin"
        if p.is_dir():
            os.add_dll_directory(str(p))
            os.environ["PATH"] = str(p) + os.pathsep + os.environ["PATH"]
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio
    sys.path.insert(0, str(HERE))
    from voice_eval import cer_str
    m = WhisperModel("large-v3", device="cuda", compute_type="float16")
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    for ch in man["chunks"]:
        scored = []
        for c in ch["cands"]:
            segs, _ = m.transcribe(str(out / c), language="ru", condition_on_previous_text=False)
            hyp = " ".join(s.text.strip() for s in segs)
            ratio = len(decode_audio(str(out / c), sampling_rate=16000)) / 16000 / ch["expected"]
            penalty = 0.0 if 0.7 <= ratio <= 1.45 else 0.5
            scored.append({"file": c, "cer": round(cer_str(ch["text"], hyp), 4), "ratio": round(ratio, 2),
                           "hyp": hyp, "score": cer_str(ch["text"], hyp) + penalty})
        # консенсус дублей: CER к тексту не отличает «Gen 5» от «генпад», если текст написан словами
        # («ген пять»), а whisper пишет цифрами; дубль, услышанный иначе, чем остальные, скорее брак
        if len(scored) > 1:
            for x in scored:
                others = [cer_str(x["hyp"], y["hyp"]) for y in scored if y is not x]
                x["consensus"] = round(sum(others) / len(others), 4)
                x["score"] += x["consensus"]
        scored.sort(key=lambda x: x["score"])
        ch["judged"] = scored
        ch["best"] = scored[0]["file"]
        flag = "  <- ПРОВЕРИТЬ" if scored[0]["cer"] > 0.08 else ""
        print(f"  {ch['best']}: CER {scored[0]['cer']:.3f}, длит x{scored[0]['ratio']}{flag}")
    (out / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")


def judge_giga(out: Path, gigaam) -> None:
    import soundfile as sf
    sys.path.insert(0, str(HERE))
    from voice_eval import cer_str
    m = gigaam.load_model("v3_rnnt", download_root=GIGAAM_ROOT)
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    for ch in man["chunks"]:
        scored = []
        for c in ch["cands"]:
            hyp = m.transcribe(str(out / c)).text
            ratio = sf.info(str(out / c)).duration / ch["expected"]
            penalty = 0.0 if 0.7 <= ratio <= 1.45 else 0.5
            scored.append({"file": c, "cer": round(cer_str(ch["text"], hyp), 4), "ratio": round(ratio, 2),
                           "hyp": hyp, "score": cer_str(ch["text"], hyp) + penalty})
        if len(scored) > 1:
            for x in scored:
                others = [cer_str(x["hyp"], y["hyp"]) for y in scored if y is not x]
                x["consensus"] = round(sum(others) / len(others), 4)
                x["score"] += 0.5 * x["consensus"]
        scored.sort(key=lambda x: x["score"])
        ch["judged"] = scored
        ch["best"] = scored[0]["file"]
        flag = "  <- ПРОВЕРИТЬ" if scored[0]["cer"] > 0.06 else ""
        print(f"  {ch['best']}: CER {scored[0]['cer']:.3f}, длит x{scored[0]['ratio']}{flag}")
    (out / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")


def gor_pauses() -> list[float]:
    """Паузы между фразами Гора из таймкодов whisper его роликов (0.15..1.2 с)."""
    gaps = []
    for js in (ROOT / "raw").glob("*.json"):
        segs = json.loads(js.read_text(encoding="utf-8"))
        for a, b in zip(segs, segs[1:]):
            g = b["s"] - a["e"]
            if 0.15 <= g <= 1.2:
                gaps.append(g)
    return sorted(gaps)


def assemble_lines(out: Path, dest_dir: Path) -> None:
    """Режим сцен: по файлу на строку исходника (line_XX.wav), громкость -15 LUFS как у озвучки шортсов."""
    import subprocess
    import librosa
    import numpy as np
    import soundfile as sf
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    gaps = gor_pauses()
    dest_dir.mkdir(parents=True, exist_ok=True)
    by_line = {}
    for ch in man["chunks"]:
        by_line.setdefault(ch.get("line", 0), []).append(ch)
    for li, chs in sorted(by_line.items()):
        pieces, sr = [], None
        for j, ch in enumerate(chs):
            w, sr = sf.read(out / ch["best"], dtype="float32")
            w, _ = librosa.effects.trim(w, top_db=45, frame_length=512, hop_length=128)
            f = int(0.008 * sr)
            w[:f] *= np.linspace(0, 1, f)
            w[-f:] *= np.linspace(1, 0, f)
            pieces.append(w)
            if j < len(chs) - 1:
                pieces.append(np.zeros(int(gaps[len(gaps) // 2] * sr) if gaps else int(0.4 * sr), np.float32))
        raw = dest_dir / f"_line_{li:02d}.wav"
        sf.write(raw, np.concatenate(pieces), sr)
        dst = dest_dir / f"line_{li:02d}.wav"
        subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(raw), "-af", "loudnorm=I=-15:TP=-1.5:LRA=11",
                        "-ar", "48000", str(dst)], check=True)
        raw.unlink()
        print(f"  {dst.name}: {sf.info(str(dst)).duration:.1f} с")


def assemble(out: Path, dest: Path) -> None:
    import random
    import subprocess
    import librosa
    import numpy as np
    import soundfile as sf
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    gaps = gor_pauses()
    random.seed(11)
    sr = None
    pieces = []
    for i, ch in enumerate(man["chunks"]):
        w, sr = sf.read(out / ch["best"], dtype="float32")
        w, _ = librosa.effects.trim(w, top_db=45, frame_length=512, hop_length=128)
        f = int(0.008 * sr)
        w[:f] *= np.linspace(0, 1, f)
        w[-f:] *= np.linspace(1, 0, f)
        pieces.append(w)
        if i < len(man["chunks"]) - 1:
            g = gaps[int(random.uniform(0.25, 0.85) * len(gaps))] if gaps else 0.45
            pieces.append(np.zeros(int(max(0.3, g) * sr), np.float32))
    raw = out / "_concat.wav"
    sf.write(raw, np.concatenate(pieces), sr)
    subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(raw), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-ar", "48000", str(dest)], check=True)
    print(f"готово: {dest} ({sf.info(str(dest)).duration:.1f} с)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1]
    if cmd == "synth":
        n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 3
        ck = sys.argv[sys.argv.index("--ckpt") + 1] if "--ckpt" in sys.argv else DEFAULT_CKPT
        synth(Path(sys.argv[2]), Path(sys.argv[3]), n, ck, per_line="--lines" in sys.argv,
              norm="--raw" not in sys.argv)
    elif cmd == "judge":
        judge(Path(sys.argv[2]))
    elif cmd == "assemble":
        assemble(Path(sys.argv[2]), Path(sys.argv[3]))
    elif cmd == "assemble-lines":
        assemble_lines(Path(sys.argv[2]), Path(sys.argv[3]))
