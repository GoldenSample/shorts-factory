# -*- coding: utf-8 -*-
"""Drama 3: эталон голоса Гора из архива камеры против старого gor_ref.wav (слово Гора 14.10.2026:
«дообучать драму по массиву камеры D:\\РАИД», «да прямое да», «поехали»). Обучения у Drama 3 в коде fish-speech нет,
поэтому первый шаг = лучший эталон: тот же голос, но живой, много и разный (камера, 2024).

Варианты эталона:
  A  студия     gor_ref.wav (18,5 с из начитки Э01), как сейчас в проде
  B  камера1    один лучший отрезок камеры 12-20 с
  C  камера3    три отрезка камеры с разных дней, около 30 с, все как speaker 0
  D  студия+к   gor_ref.wav + один отрезок камеры
Замер на каждом: похожесть на голос Гора (spk_embed, центр роликов @GSPCS), ошибки слов CER (faster-whisper
large-v3 на процессоре), длина против ожидаемой. Ударение замер не слышит: решает ухо Гора (сборка сравнения в конце).
  <venv fish-speech>/python drama_ab.py gen      # синтез (сервер Drama на :8090)
  <venv qwen-tts>/python drama_ab.py score      # похожесть
  <venv fish-speech>/python drama_ab.py report   # CER, таблица, файл сравнения на слух"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(r"H:\tts_data\gor_camera")
OUT = Path(r"H:\tts-models\drama-3\ab_camera")
REF_A = Path(r"H:\tts-models\drama-3\refs\gor_ref.wav")
URL = "http://127.0.0.1:8090/v1/tts"
WHISPER = r"C:\Apps\whisper\.venv\Scripts\python.exe"
FPS_CODEC = 21.5
VARIANTS = "ABCDE"

# чтения кириллицей (Drama читает латиницу по-английски); ловушки ударений, на которых сыпались прочие модели
LINES = [
    "Сегодня собираем систему на девять тысяч восемьсот пятидесятом, и сразу скажу: водянка тут не для красоты.",
    "Если будете покупать материнскую плату, первым делом смотрите на питание процессора, радиаторы потом.",
    "Включим тест, подождём десять минут и посмотрим, как быстро греется память.",
    "Красивее этой сборки у нас в мастерской пока ничего не было, честно.",
    "Звонят, спрашивают, можно ли дешевле. Можно, но тогда начался бы совсем другой разговор.",
    "Пять и восемь гигагерца на всех ядрах, напряжение один и двадцать пять, температура восемьдесят один градус.",
]
# те же фразы так, как whisper пишет числа: CER = лучшее из двух записей
SCREEN = {
    0: "Сегодня собираем систему на 9850, и сразу скажу, водянка тут не для красоты.",
    2: "Включим тест, подождем 10 минут и посмотрим, как быстро греется память.",
    5: "5,8 ГГц на всех ядрах, напряжение 1,25, температура 81 градус.",
}


def cut(vid: str, s: float, e: float, dst: Path) -> Path:
    w, sr = sf.read(ROOT / "raw" / f"{vid}.wav", dtype="float32")
    a, b = max(0, int((s - 0.1) * sr)), min(len(w), int((e + 0.15) * sr))
    seg = w[a:b]
    peak = float(np.abs(seg).max()) or 1.0
    sf.write(dst, seg * min(1.0, 0.89 / peak), sr)
    return dst


def build_refs() -> dict:
    """Отрезки камеры из candidates.json (camera_refs.py): B = лучший 12-20 с, C = три разных дня, D = A + B."""
    cand = json.loads((ROOT / "candidates.json").read_text(encoding="utf-8"))["picked"]
    # расшифровка эталона должна совпадать со звуком: без цифр и латиницы, с пунктуацией, без повторов whisper
    def tidy(t: str) -> bool:
        w = norm(t).split()
        return (not re.search(r"[0-9A-Za-z]", t) and re.search(r"[,.!?]", t) is not None
                and all(a != b for a, b in zip(w, w[1:])))
    cand = [r for r in cand if tidy(r["t"])] or cand
    day = lambda r: re.search(r"DJI_(\d{8})", r["vid"]).group(1) if re.search(r"DJI_(\d{8})", r["vid"]) else r["vid"]
    long_ = [r for r in cand if 12.0 <= r["dur"] <= 20.0] or cand
    b = long_[0]
    c, seen = [], set()
    for r in cand:
        if day(r) in seen or not 8.0 <= r["dur"] <= 17.0:
            continue
        seen.add(day(r)); c.append(r)
        if len(c) == 3:
            break
    rd = OUT / "refs"; rd.mkdir(parents=True, exist_ok=True)
    mk = lambda r, n: {"wav": str(cut(r["vid"], r["s"], r["e"], rd / f"{n}.wav")), "text": r["t"].strip(), "src": f"{r['vid']} {r['s']:.1f}-{r['e']:.1f}"}
    a = {"wav": str(REF_A), "text": REF_A.with_suffix(".lab").read_text(encoding="utf-8").strip(), "src": "gor_ref.wav"}
    # E: только целые предложения (с заглавной до точки). Замер 14.10: B и C с эталоном, оборванным на запятой,
    # трижды из 12 обрывали фразу после первой части («Включим тест.»), A и D ни разу
    seg = [json.loads(l) for l in (ROOT / "segments.jsonl").read_text(encoding="utf-8").splitlines()]
    full = sorted([s for s in seg if s.get("clean") and 8.0 <= s["dur"] <= 17.0 and s["lp"] > -0.25
                   and re.match(r"^[А-ЯЁ]", s["t"].strip()) and re.search(r"[.!?]$", s["t"].strip())
                   and not re.search(r"[0-9A-Za-z]", s["t"])], key=lambda s: -s["sim"])
    e, seen = [], set()
    for r in full:
        if day(r) in seen:
            continue
        seen.add(day(r)); e.append(r)
        if len(e) == 3:
            break
    # уже синтезированные варианты держат свой эталон из refs.json (кандидаты меняются с каждой новой расшифровкой)
    old = json.loads((OUT / "refs.json").read_text(encoding="utf-8")) if (OUT / "refs.json").exists() else {}
    plan = {"B": lambda: [mk(b, "B0")], "C": lambda: [mk(r, f"C{k}") for k, r in enumerate(c)],
            "D": lambda: [a, mk(b, "B0")], "E": lambda: [mk(r, f"E{k}") for k, r in enumerate(e)]}
    refs = {"A": [a]}
    for v, build in plan.items():
        refs[v] = old[v] if v in old else build()
    (OUT / "refs.json").write_text(json.dumps(refs, ensure_ascii=False, indent=1), encoding="utf-8")
    return refs


def gen() -> int:
    import ormsgpack
    import requests
    refs = build_refs()
    requests.get(URL.rsplit("/v1/", 1)[0] + "/v1/health", timeout=10).raise_for_status()
    log = OUT / "gen.jsonl"
    for v, rl in refs.items():
        payload_refs = [{"audio": Path(r["wav"]).read_bytes(), "text": r["text"], "speaker": 0} for r in rl]
        (OUT / v).mkdir(exist_ok=True)
        for i, text in enumerate(LINES):
            dst = OUT / v / f"{i}.wav"
            if dst.exists():
                continue
            cap = int(FPS_CODEC * (len(text) / 11.0 + 1.5))
            t0 = time.perf_counter()
            r = requests.post(URL, data=ormsgpack.packb({"text": text, "references": payload_refs, "format": "wav",
                                                         "max_new_tokens": cap}),
                              headers={"Content-Type": "application/msgpack"}, timeout=3600)
            if r.status_code != 200:
                print(f"{v}{i}: HTTP {r.status_code} {r.text[:200]}", flush=True); continue
            raw = dst.with_suffix(".raw.wav"); raw.write_bytes(r.content)
            af = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.02,"
                  "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", af, str(dst)], check=True)
            raw.unlink()
            dt = time.perf_counter() - t0
            d = sf.info(dst).duration
            with log.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"v": v, "i": i, "sec": round(dt, 1), "dur": round(d, 2)}) + "\n")
            print(f"{v}{i}: {d:4.1f} с звука за {dt:5.0f} с", flush=True)
    return 0


def score() -> int:
    sys.path.insert(0, str(Path(__file__).parent))
    from spk_embed import SpkEmb
    import librosa
    se = SpkEmb()
    z = np.load(Path(r"C:\CLAUD\projects\shorts-forge\work_voice_gor\centroid_qwen.npz"))
    c, mu = z["centroid"], z["mu"]
    seg = [json.loads(l) for l in (ROOT / "segments.jsonl").read_text(encoding="utf-8").splitlines()]
    out = {}
    for v in VARIANTS:
        for p in sorted((OUT / v).glob("*.wav")):
            w, sr = librosa.load(str(p), sr=24000)
            e = se(w, sr) - mu; e /= np.linalg.norm(e)
            out[f"{v}/{p.stem}"] = round(float(e @ c), 4)
    live = [r["sim"] for r in seg if r.get("clean")]
    out["_live_camera_median"] = round(float(np.median(live)), 4) if live else None
    (OUT / "sim.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return 0


def norm(s: str) -> str:
    s = s.lower().replace("ё", "е")
    return " ".join(re.sub(r"[^a-zа-я0-9 ]+", " ", s).split())


def report() -> int:
    wavs = [str(p) for v in VARIANTS for p in sorted((OUT / v).glob("*.wav"))]
    code = ("import sys,json\nsys.stdout.reconfigure(encoding='utf-8')\nfrom faster_whisper import WhisperModel\n"
            "m=WhisperModel('large-v3',device='cpu',compute_type='int8')\nout={}\n"
            "for p in sys.argv[1:]:\n  segs,_=m.transcribe(p,language='ru',beam_size=5,condition_on_previous_text=False)\n"
            "  out[p]=' '.join(s.text.strip() for s in segs)\nprint(json.dumps(out,ensure_ascii=False))")
    r = subprocess.run([WHISPER, "-c", code, *wavs], capture_output=True, text=True, encoding="utf-8", errors="replace")
    hyp = json.loads(r.stdout.strip().splitlines()[-1])
    sim = json.loads((OUT / "sim.json").read_text(encoding="utf-8"))
    gl = {}
    for l in (OUT / "gen.jsonl").read_text(encoding="utf-8").splitlines():
        g = json.loads(l); gl[f"{g['v']}/{g['i']}"] = g
    rows = []
    for p in wavs:
        v, i = Path(p).parent.name, int(Path(p).stem)
        got = norm(hyp.get(p, ""))
        cer = min(1 - difflib.SequenceMatcher(None, norm(t), got).ratio() for t in (LINES[i], SCREEN.get(i, LINES[i])))
        rows.append({"v": v, "i": i, "cer": round(cer, 3), "sim": sim.get(f"{v}/{i}"), "dur": round(sf.info(p).duration, 2),
                     "expect": round(len(LINES[i]) / 13.0, 1), "sec": gl.get(f"{v}/{i}", {}).get("sec"), "hyp": hyp.get(p, "")})
    (OUT / "report.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"живой Гор на камере к центру: {sim.get('_live_camera_median')}")
    print(f"{'вар':4} {'похож':>6} {'CER':>6} {'длина/ждём':>11} {'синтез, с':>9}")
    for v in VARIANTS:
        rs = [x for x in rows if x["v"] == v]
        if rs:
            print(f"{v:4} {np.mean([x['sim'] for x in rs]):6.3f} {np.mean([x['cer'] for x in rs]):6.3f} "
                  f"{np.mean([x['dur'] / x['expect'] for x in rs]):11.2f} {np.mean([x['sec'] or 0 for x in rs]):9.0f}")
    for x in rows:
        if x["cer"] > 0.12:
            print(f"  ошибки {x['v']}{x['i']} CER {x['cer']}: «{x['hyp'][:90]}»")
    # сравнение на слух: по каждой фразе A, затем остальные варианты, между ними щелчок-пауза
    seq = []
    for i in range(len(LINES)):
        for v in VARIANTS:
            p = OUT / v / f"{i}.wav"
            if p.exists():
                seq.append(p)
    if seq:
        lst = OUT / "concat.txt"
        gap = OUT / "gap.wav"
        sf.write(gap, np.zeros(int(24000 * 0.7), dtype=np.float32), 24000)
        lst.write_text("".join(f"file '{p.as_posix()}'\nfile '{gap.as_posix()}'\n" for p in seq), encoding="utf-8")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-ar", "24000", "-ac", "1",
                        "-af", "loudnorm=I=-16:TP=-1.5", str(OUT / "compare.wav")], check=True)
        print("сравнение на слух:", OUT / "compare.wav")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    raise SystemExit({"gen": gen, "score": score, "report": report}.get(cmd, lambda: print(__doc__) or 2)())
