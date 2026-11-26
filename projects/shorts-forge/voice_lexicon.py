# -*- coding: utf-8 -*-
"""Словарь произношения Гора: как он РЕАЛЬНО говорит латиницу, цифры и модели железа.

Whisper пишет «RTX 5090», «LGA 1700», «i9», а как это прозвучало, из его текста не видно.
GigaAM-v3 (v3_rnnt, Сбер, MIT) пишет речь словами, как она звучит: «лг тысяча семьсот», «ай девятым».
Сопоставляем два транскрипта одного и того же куска речи и получаем пары «запись -> произношение».

  <gigaam>\\python voice_lexicon.py giga     GigaAM по всем сегментам с латиницей/цифрами (голос без фона)
  python voice_lexicon.py align              выравнивание whisper<->GigaAM, пары и частоты
  -> work_voice_gor/lexicon/pairs.jsonl      каждая пара с примером (ролик, время, оба текста)
  -> work_voice_gor/lexicon/lexicon_raw.tsv  термин, произношение-лидер, частота, альтернативы
Бренды GigaAM пишет фонетически и с ошибками («интол»), поэтому лидер берётся по частоте
всех вхождений, а итоговый словарь (gor_lexicon.tsv) проходит ручную вычитку.
"""
from __future__ import annotations

import difflib
import json
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE / "work_voice_gor"
RAW = ROOT / "raw"
SEP = ROOT / "sep" / "htdemucs_ft"
LEX = ROOT / "lexicon"
HAS_LD = re.compile(r"[A-Za-z0-9]")


def live_videos() -> list[str]:
    by = defaultdict(list)
    for l in (ROOT / "segments.jsonl").open(encoding="utf-8"):
        r = json.loads(l)
        by[r["vid"]].append(r["sim"])
    return sorted(v for v, s in by.items() if st.median(s) >= 0.78)


def giga() -> None:
    import os
    import tempfile
    import gigaam
    import librosa
    import soundfile as sf
    LEX.mkdir(parents=True, exist_ok=True)
    out_p = LEX / "giga.jsonl"
    done = set()
    if out_p.exists():
        done = {(json.loads(l)["vid"], json.loads(l)["i"]) for l in out_p.open(encoding="utf-8")}
    m = gigaam.load_model("v3_rnnt")
    tmp = os.path.join(tempfile.gettempdir(), "giga_seg.wav")
    n = 0
    with out_p.open("a", encoding="utf-8") as f:
        for vid in live_videos():
            segs = json.loads((RAW / f"{vid}.json").read_text(encoding="utf-8"))
            src = SEP / vid / "vocals.wav"
            wav, sr = librosa.load(str(src if src.exists() else RAW / f"{vid}.wav"), sr=16000)
            for i, s in enumerate(segs):
                if (vid, i) in done or not HAS_LD.search(s["t"]):
                    continue
                a = max(0.0, s["s"] - 0.15)
                b = min(len(wav) / sr, s["e"] + 0.25, a + 24.0)
                sf.write(tmp, wav[int(a * sr):int(b * sr)], sr)
                try:
                    g = m.transcribe(tmp).text
                except Exception as e:           # слишком длинный или пустой кусок
                    g = ""
                    print(f"  {vid} {i}: {type(e).__name__}")
                f.write(json.dumps({"vid": vid, "i": i, "s": s["s"], "e": s["e"], "whisper": s["t"],
                                    "giga": g}, ensure_ascii=False) + "\n")
                n += 1
            print(f"  {vid}: готово", flush=True)
    print(f"новых сегментов: {n}")


TOK = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+(?:[.,/\-+][A-Za-zА-Яа-яЁё0-9]+)*")


def norm_ru(w: str) -> str:
    return w.lower().replace("ё", "е")


def align() -> None:
    rows = [json.loads(l) for l in (LEX / "giga.jsonl").open(encoding="utf-8")]
    pairs = []
    for r in rows:
        wt = TOK.findall(r["whisper"])
        gt = r["giga"].split()
        if not wt or not gt:
            continue
        wk = [norm_ru(t) if not HAS_LD.search(t) else f"<{t}>" for t in wt]
        gk = [norm_ru(t) for t in gt]
        sm = difflib.SequenceMatcher(a=wk, b=gk, autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op != "replace":
                continue
            wspan, gspan = wt[i1:i2], gt[j1:j2]
            if not any(HAS_LD.search(t) for t in wspan):
                continue
            # кириллица по краям спана: whisper и GigaAM разошлись в обычном слове, срезаем
            while wspan and not HAS_LD.search(wspan[0]) and gspan and norm_ru(wspan[0])[:4] == gspan[0][:4]:
                wspan, gspan = wspan[1:], gspan[1:]
            while wspan and not HAS_LD.search(wspan[-1]) and gspan and norm_ru(wspan[-1])[:4] == gspan[-1][:4]:
                wspan, gspan = wspan[:-1], gspan[:-1]
            if not wspan or not gspan or len(wspan) > 4 or len(gspan) > 3 * len(wspan) + 3:
                continue
            if any(not HAS_LD.search(t) for t in wspan):
                continue                       # смешанный спан ненадёжен
            pairs.append({"written": " ".join(wspan), "spoken": " ".join(gspan), "vid": r["vid"],
                          "t": round(r["s"], 1), "whisper": r["whisper"], "giga": r["giga"]})
    with (LEX / "pairs.jsonl").open("w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    agg = defaultdict(Counter)
    for p in pairs:
        agg[p["written"].lower()].update([p["spoken"]])
    lines = ["термин\tпроизношение\tчастота\tвсего\tальтернативы"]
    for k, c in sorted(agg.items(), key=lambda kv: -sum(kv[1].values())):
        best, n = c.most_common(1)[0]
        alts = "; ".join(f"{s} ({m})" for s, m in c.most_common(4)[1:])
        lines.append(f"{k}\t{best}\t{n}\t{sum(c.values())}\t{alts}")
    (LEX / "lexicon_raw.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"сегментов {len(rows)}, пар {len(pairs)}, терминов {len(agg)}")
    for l in lines[1:41]:
        print("  " + l)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    {"giga": giga, "align": align}[sys.argv[1]]()
