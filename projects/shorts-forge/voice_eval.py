# -*- coding: utf-8 -*-
"""Стенд оценки двойника голоса Гора: одни фразы, одни судьи, любой движок.

Тест = 24 фразы, которые Гор реально произнёс в роликах и которые НЕ попали в обучение
(dataset/test.jsonl), плюс 3 фразы из шортса. Для каждой отложенной фразы есть живая запись,
поэтому сходство меряется пара к паре: синтез фразы против Гора, говорящего ту же фразу.

  gen   <движок> --tag ИМЯ [--ckpt ПАПКА]   синтез в eval/ИМЯ/
          qwen_sft    Qwen3-TTS после SFT (venv qwen-tts), speaker gor, language Auto
          qwen_icl    Qwen3-TTS Base zero-shot, чистый референс + его текст (venv qwen-tts)
          vstudio     VoiceStudio/OmniVoice по HTTP, тот же референс (любой venv с requests)
          chatterbox  Chatterbox Multilingual, тот же референс (venv chatterbox)
  cer   whisper large-v3 -> CER к тексту фразы по всем тегам        (venv whisper)
  score SIM-o WavLM-ECAPA к живой записи, UTMOS, сводная таблица   (venv VoiceStudio)

Пороги из практики Seed-TTS-eval: SIM-o живой речи того же человека в другой фразе ~0.7-0.8;
UTMOS живой студийной речи ~4.0-4.4; CER русского у хороших систем < 0.03 (с учётом цифр выше).
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE / "work_voice_gor"
DS = ROOT / "dataset"
EVAL = ROOT / "eval"
sys.path.insert(0, str(HERE))

EXTRA = {
    "l_hook": "Самый быстрый эс-эс-дэ Самсунга внезапно подешевел на треть. "
              "Но прежде чем нести деньги, три вещи, о которых заголовки молчат.",
    "l_tech": "На платах икс восемьсот семьдесят люди ловят ошибки диска, "
              "а после холодного старта он иногда просто не определяется.",
    "l_verdict": "Правило одно: плати за скорость, которую твоя система реально умеет использовать, "
                 "а не за цифру на коробке.",
}


def items(spoken: bool = False) -> list[tuple[str, str, str | None]]:
    """(имя файла, текст, путь к живой записи или None). spoken: тексты в произносимой записи (модель v3)."""
    test = [json.loads(x) for x in (DS / ("test_spoken.jsonl" if spoken else "test.jsonl")).open(encoding="utf-8")]
    out = [(f"t{i:02d}", t["text"], t["audio"]) for i, t in enumerate(test)]
    out += [(k, v, None) for k, v in EXTRA.items()]
    return out


def ref_clean() -> tuple[str, str]:
    refs = json.loads((ROOT / "refs" / "refs.json").read_text(encoding="utf-8"))
    return str(DS / "ref_clean.wav"), refs[0]["t"]


def gen(engine: str, tag: str, ckpt: str | None, spoken: bool = False) -> None:
    import numpy as np
    import soundfile as sf
    dest = EVAL / tag
    dest.mkdir(parents=True, exist_ok=True)
    todo = [(n, t) for n, t, _ in items(spoken) if not (dest / f"{n}.wav").exists()]
    ref_wav, ref_txt = ref_clean()

    if engine in ("qwen_sft", "qwen_icl"):
        import torch
        from qwen_tts import Qwen3TTSModel
        path = ckpt or r"H:\comfy-models\TTS\Qwen3-TTS-12Hz-1.7B-Base"
        m = Qwen3TTSModel.from_pretrained(path, device_map="cuda", dtype=torch.bfloat16, attn_implementation="sdpa")
        prompt = m.create_voice_clone_prompt(ref_audio=ref_wav, ref_text=ref_txt) if engine == "qwen_icl" else None
        for n, t in todo:
            if engine == "qwen_sft":
                wavs, sr = m.generate_custom_voice(text=t, speaker="gor", language="Auto")
            else:
                wavs, sr = m.generate_voice_clone(text=t, language="Russian", voice_clone_prompt=prompt)
            sf.write(dest / f"{n}.wav", np.asarray(wavs[0], dtype=np.float32), sr)
    elif engine == "vstudio":
        import requests
        for n, t in todo:
            with open(ref_wav, "rb") as fh:
                r = requests.post("http://localhost:3900/generate", timeout=600,
                                  data={"text": t, "language": "ru", "ref_text": ref_txt},
                                  files={"ref_audio": ("ref.wav", fh, "audio/wav")})
            r.raise_for_status()
            (dest / f"{n}.wav").write_bytes(r.content)
    elif engine == "chatterbox":
        import torch
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        tts = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
        tts.prepare_conditionals(ref_wav, exaggeration=0.5)
        for n, t in todo:
            with torch.inference_mode():
                w = tts.generate(t, language_id="ru", cfg_weight=0.5, temperature=0.7)
            sf.write(dest / f"{n}.wav", w.squeeze(0).cpu().numpy().astype(np.float32), tts.sr)
    else:
        raise SystemExit(f"неизвестный движок {engine}")
    print(f"{tag}: синтезировано {len(todo)}")


def norm(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[^a-zа-я0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def cer_str(ref: str, hyp: str) -> float:
    a, b = norm(ref), norm(hyp)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / max(1, len(a))


def cer() -> None:
    nv = Path(r"C:\Apps\whisper\.venv\Lib\site-packages\nvidia")
    for d in ("cublas", "cudnn"):
        p = nv / d / "bin"
        if p.is_dir():
            os.add_dll_directory(str(p))
            os.environ["PATH"] = str(p) + os.pathsep + os.environ["PATH"]
    from faster_whisper import WhisperModel
    m = WhisperModel("large-v3", device="cuda", compute_type="float16")
    texts = {n: t for n, t, _ in items()}
    for tagdir in sorted(p for p in EVAL.iterdir() if p.is_dir()):
        out_p = tagdir / "cer.json"
        done = json.loads(out_p.read_text(encoding="utf-8")) if out_p.exists() else {}
        for w in sorted(tagdir.glob("*.wav")):
            if w.stem in done or w.stem not in texts:
                continue
            segs, _ = m.transcribe(str(w), language="ru", condition_on_previous_text=False)
            hyp = " ".join(s.text.strip() for s in segs)
            done[w.stem] = {"cer": round(cer_str(texts[w.stem], hyp), 4), "hyp": hyp}
        out_p.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {tagdir.name}: CER по {len(done)} файлам")


def score() -> None:
    import numpy as np
    import torch
    from omnivoice.eval.models.ecapa_tdnn_wavlm import ECAPA_TDNN_WAVLM
    from omnivoice.eval.models.utmos import UTMOS22Strong
    from omnivoice.eval.utils import load_waveform
    M = Path(r"C:\Apps\tts_eval_models")
    dev = torch.device("cuda")
    sv = ECAPA_TDNN_WAVLM(feat_dim=1024, channels=512, emb_dim=256, sr=16000,
                          ssl_model_path=str(M / "speaker_similarity" / "wavlm_large") + os.sep)
    sv.load_state_dict(torch.load(M / "speaker_similarity" / "wavlm_large_finetune.pth",
                                  map_location="cpu")["model"], strict=False)
    sv.to(dev).eval()
    mos = UTMOS22Strong()
    mos.load_state_dict(torch.load(M / "mos" / "utmos22_strong_step7459_v1.pt", map_location="cpu"))
    mos.to(dev).eval()

    @torch.no_grad()
    def emb(p):
        return sv([load_waveform(str(p), 16000, device=dev, max_seconds=60)])

    @torch.no_grad()
    def utmos(p):
        return float(mos(load_waveform(str(p), 16000, device=dev).unsqueeze(0), 16000))

    import librosa
    vow = set("аеёиоуыэюяaeiouy")

    def speech_len(p):
        w, sr = librosa.load(str(p), sr=16000)
        w, _ = librosa.effects.trim(w, top_db=35)
        return len(w) / sr

    def rate(text, p):
        return sum(ch in vow for ch in text.lower()) / max(0.3, speech_len(p))

    its = items()
    real = {n: a for n, _, a in its if a}
    texts = {n: t for n, t, _ in its}
    real_rate = {n: rate(texts[n], a) for n, a in real.items()}
    real_len = {n: speech_len(a) for n, a in real.items()}
    real_emb = {n: emb(a) for n, a in real.items()}
    allr = torch.cat(list(real_emb.values()))
    centroid = torch.nn.functional.normalize(allr.mean(0, keepdim=True), dim=-1)
    names = list(real_emb)
    cross = [float(torch.nn.functional.cosine_similarity(real_emb[a], real_emb[b])) for i, a in enumerate(names)
             for b in names[i + 1:]]
    real_mos = [utmos(a) for a in real.values()]
    print(f"ЖИВОЙ ГОР: SIM между разными фразами {np.mean(cross):.3f} · UTMOS {np.mean(real_mos):.2f} · "
          f"темп {np.mean(list(real_rate.values())):.2f} слог/с\n")
    print(f"{'модель':26} {'SIM пара':>8} {'SIM цент':>8} {'UTMOS':>6} {'CER тест':>8} {'CER шорт':>8} "
          f"{'темп':>5} {'длит/жив':>8} {'брак':>4}  n")
    rows = []
    for tagdir in sorted(p for p in EVAL.iterdir() if p.is_dir()):
        cers = json.loads((tagdir / "cer.json").read_text(encoding="utf-8")) if (tagdir / "cer.json").exists() else {}
        sp, sc, ms, ct, cs, rt, lr = [], [], [], [], [], [], []
        bad = 0
        for n, _, a in its:
            w = tagdir / f"{n}.wav"
            if not w.exists():
                continue
            if a:
                rt.append(rate(texts[n], w))
                lr.append(speech_len(w) / real_len[n])
                if not 0.7 <= lr[-1] <= 1.4:
                    bad += 1
            e = emb(w)
            sc.append(float(torch.nn.functional.cosine_similarity(e, centroid)))
            ms.append(utmos(w))
            if a:
                sp.append(float(torch.nn.functional.cosine_similarity(e, real_emb[n])))
            c = cers.get(n, {}).get("cer")
            if c is not None:
                (ct if a else cs).append(c)
        f = lambda v: f"{np.mean(v):.3f}" if v else "-"
        rows.append((tagdir.name, f(sp), f(sc), f"{np.mean(ms):.2f}" if ms else "-", f(ct), f(cs),
                     f"{np.mean(rt):.2f}" if rt else "-", f"{np.median(lr):.2f}" if lr else "-", bad, len(sc)))
    for r in rows:
        print(f"{r[0]:26} {r[1]:>8} {r[2]:>8} {r[3]:>6} {r[4]:>8} {r[5]:>8} {r[6]:>5} {r[7]:>8} {r[8]:>4}  {r[9]}")
    (EVAL / "scores.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1]
    if cmd == "gen":
        tag = sys.argv[sys.argv.index("--tag") + 1]
        ck = sys.argv[sys.argv.index("--ckpt") + 1] if "--ckpt" in sys.argv else None
        gen(sys.argv[2], tag, ck, spoken="--spoken" in sys.argv)
    elif cmd == "cer":
        cer()
    elif cmd == "score":
        score()
