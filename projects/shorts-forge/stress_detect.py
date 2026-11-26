# -*- coding: utf-8 -*-
"""Автоматический замер ударений в синтезе (и в живой речи для калибровки).

Идея: в русском ударная гласная заметно длиннее и громче безударных. Звук выравнивается по буквам
(wav2vec2 XLSR-53 Russian, CTC forced alignment torchaudio), для каждой гласной берутся длительность
(от её начала до начала следующей буквы) и громкость; ударной считается гласная с наибольшим
log(длительность) + 0.5*log(громкость). Сравнивается с ударением из текста (знак U+0301).
Не оцениваются: односложные слова, слова с «ё», слова перед знаком препинания и в конце фразы
(там удлиняется последний слог независимо от ударения).

  <venv qwen-tts>\\python stress_detect.py calib            точность детектора на живых записях Гора
  <venv qwen-tts>\\python stress_detect.py eval ПАПКА TSV    точность ударений синтеза (TSV: файл<TAB>текст со знаками)
Точность детектора на живой речи = потолок: синтез с правильными ударениями должен давать столько же.
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import torch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
W2V = r"C:\Users\Administrator\.cache\huggingface\hub\models--jonatasgrosman--wav2vec2-large-xlsr-53-russian\snapshots\2329100508896c6d9b157019803ab5601e6f3406"
PHON = "C:/Users/Administrator/.cache/huggingface/hub/models--facebook--wav2vec2-xlsr-53-espeak-cv-ft/snapshots/2c733782da5604684829819a5eb744c193fe9398"
FULL = ["a", "o", "e", "ɛ", "i", "u", "ɨ", "aː", "oː", "eː", "iː", "uː", "ɑ", "ɔ", "e̞", "o̞"]
RED = ["ɐ", "ə", "ɪ", "ʊ", "ᵻ", "ɐɐ"]
LAM = 0.0          # калибровка 03.10 на живой речи Гора: полнота гласной 74.6 %, с длительностью хуже
ACUTE = "\u0301"
VOW = set("аеиоуыэюя")
_M = {}


def model():
    if not _M:
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
        _M["proc"] = Wav2Vec2Processor.from_pretrained(W2V)
        _M["m"] = Wav2Vec2ForCTC.from_pretrained(W2V).to("cuda").eval().half()
        _M["vocab"] = _M["proc"].tokenizer.get_vocab()
        from transformers import Wav2Vec2FeatureExtractor
        _M["pfe"] = Wav2Vec2FeatureExtractor.from_pretrained(PHON)
        _M["pm"] = Wav2Vec2ForCTC.from_pretrained(PHON).to("cuda").eval().half()
        pv = json.loads((Path(PHON) / "vocab.json").read_text(encoding="utf-8"))
        _M["full_ids"] = [pv[x] for x in FULL if x in pv]
        _M["red_ids"] = [pv[x] for x in RED if x in pv]
    return _M


def phon_post(wav):
    M = model()
    inp = M["pfe"](wav, sampling_rate=16000, return_tensors="pt").input_values.to("cuda").half()
    with torch.inference_mode():
        pr = torch.softmax(M["pm"](inp).logits.float(), dim=-1)[0]
    return pr[:, M["full_ids"]].sum(-1).cpu().numpy(), pr[:, M["red_ids"]].sum(-1).cpu().numpy()


def parse(marked: str):
    """-> список слов: (буквы без знаков, индекс ударной гласной среди гласных или None, перед паузой?)."""
    words = []
    for m in re.finditer(r"[А-Яа-яЁё\u0301]+", marked):
        w = m.group(0).lower()
        bare = w.replace(ACUTE, "")
        stress, vi = None, -1
        for i, ch in enumerate(w):
            if ch == ACUTE:
                stress = vi
            elif ch in VOW or ch == "ё":
                vi += 1
        tail = marked[m.end():m.end() + 2]
        before_pause = bool(re.match(r"\s*[.,!?:;…\-—]", tail)) or m.end() >= len(marked.rstrip()) - 1
        words.append((bare, stress, before_pause))
    return words


def align(wav: np.ndarray, words: list[str]):
    """CTC forced alignment по буквам: -> для каждой буквы (слово, буква, кадр начала); кадр = 20 мс."""
    from torchaudio.functional import forced_align, merge_tokens
    M = model()
    voc = M["vocab"]
    sep = voc.get("|", voc.get(" "))
    toks, meta = [], []
    for wi, w in enumerate(words):
        for ch in w.replace("ё", "е"):
            if ch in voc:
                toks.append(voc[ch])
                meta.append((wi, ch))
        if sep is not None and wi < len(words) - 1:
            toks.append(sep)
            meta.append((wi, "|"))
    inp = M["proc"](wav, sampling_rate=16000, return_tensors="pt").input_values.to("cuda").half()
    with torch.inference_mode():
        lp = torch.log_softmax(M["m"](inp).logits.float(), dim=-1)
    tgt = torch.tensor([toks], dtype=torch.int32, device="cuda")
    ali, scores = forced_align(lp, tgt, blank=M["proc"].tokenizer.pad_token_id)
    spans = merge_tokens(ali[0], scores[0].exp())
    starts = [s.start for s in spans]
    return meta, starts, lp.shape[1]


def word_stress(wav: np.ndarray, marked: str):
    words = parse(marked)
    bare = [w for w, _, _ in words]
    if not bare:
        return []
    meta, starts, n = align(wav, bare)
    if len(starts) != len(meta):
        return []
    hop = len(wav) / max(1, n)
    pf, pr_ = phon_post(wav)
    res = []
    for wi, (w, stress, pause) in enumerate(words):
        idx = [k for k, (mw, ch) in enumerate(meta) if mw == wi and ch in VOW]
        if len(idx) < 2 or stress is None or "ё" in w or pause or len(idx) != sum(ch in VOW for ch in w.replace("ё", "е")):
            continue
        dur_en, full = [], []
        for k in idx:
            a0 = starts[k]
            b0 = max(starts[k + 1] if k + 1 < len(starts) else n, a0 + 1)
            seg = wav[int(a0 * hop):int(b0 * hop)]
            rms = float(np.sqrt(np.mean(seg ** 2)) + 1e-6)
            dur_en.append(math.log(b0 - a0) + 0.5 * math.log(rms))
            lo, hi = max(0, a0 - 1), min(len(pf), b0 + 1)
            f, r = float(pf[lo:hi].sum()), float(pr_[lo:hi].sum())
            full.append(f / (f + r + 1e-4))
        de = np.array(dur_en)
        de = (de - de.mean()) / (de.std() + 1e-6)
        res.append({"word": w, "truth": stress, "full": full, "de": de.tolist()})
    for x in res:
        x["pred"] = int(np.argmax(np.array(x["full"]) + LAM * np.array(x["de"])))
        x["ok"] = x["pred"] == x["truth"]
    return res


def load16(p: str) -> np.ndarray:
    import librosa
    w, _ = librosa.load(p, sr=16000)
    return w.astype(np.float32)


def calib() -> None:
    """Живые записи Гора: тест (24) + 200 фраз обучения; ударения из silero-stress (gor_stress)."""
    from gor_stress import accent
    ds = HERE / "work_voice_gor" / "dataset"
    rows = [json.loads(l) for l in (ds / "test_spoken.jsonl").open(encoding="utf-8")]
    tr = [json.loads(l) for l in (ds / "train_spoken_raw.jsonl").open(encoding="utf-8")]
    rows += tr[::max(1, len(tr) // 200)][:200]
    allw = []
    for r in rows:
        allw += word_stress(load16(r["audio"]), accent(r["text"]))
    print(f"живой Гор: {len(rows)} фраз, оценено слов {len(allw)}")
    for lam in (0.0, 0.1, 0.25, 0.5, 1.0, 100.0):
        ok = sum(int(np.argmax(np.array(x["full"]) + lam * np.array(x["de"]))) == x["truth"] for x in allw)
        print(f"  вес длительности {lam:>5}: совпало с ударением словаря {ok / max(1, len(allw)):.1%}")


def evaluate(folder: str, tsv: str) -> None:
    tot = ok = 0
    bad = []
    for line in Path(tsv).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name, text = line.split("\t", 1)
        p = Path(folder) / f"{name}.wav"
        if not p.exists():
            continue
        res = word_stress(load16(str(p)), text)
        tot += len(res)
        ok += sum(x["ok"] for x in res)
        bad += [f"{name}:{x['word']}" for x in res if not x["ok"]]
    print(f"{Path(folder).name}: оценено слов {tot}, ударение как в словаре {ok / max(1, tot):.1%}; "
          f"мимо: {', '.join(bad[:12])}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1] == "calib":
        calib()
    else:
        evaluate(sys.argv[2], sys.argv[3])
