# -*- coding: utf-8 -*-
"""САМОПРОВЕРКА ШОРТСА ДО ОТПРАВКИ для любого эпизода (аудит 23.10 п.21: у Э05 проверка 97 % кодом не исполнена, факт 0,90;
qa_e04.py считал ok, но всегда выходил с кодом 0). Канон Э04 (gs-shorts-master 5 п.3, istorii-zhelezok 6б, SCHEME_SHORT 5):
faster-whisper large-v3 (CPU) против сценария, распознано не меньше 97 % слов (числа словом и цифрой засчитываются в обе стороны);
blackdetect; хвост тише -18 дБ; длина в окне 45-60 с (решение Гора по вопросу 6 аудита: «45-60 с по канону Э04»);
раскадровка кадр в секунду листами не шире 1280 px.
  py -3.12 projects/shorts-forge/qa_short.py <папка эпизода> [ролик.mp4] [--min 45] [--max 60]
  -> <папка>/qa/qa.json, qa/board_*.jpg; код 0 = чисто, 1 = брак (печатает, что именно)"""
import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image

WHISPER = r"C:\Apps\whisper\.venv\Scripts\python.exe"
RECOGNIZED_MIN, TAIL_MAX_DB = 0.97, -18.0
NUM_ROOT = re.compile(r"^(ноль|нул|один|одн|два|двух|две|двум|три|тр[её]х|четыр|пят|шест|сем|восем|девят|десят|одиннадц|двенадц|"
                      r"тринадц|четырнадц|пятнадц|шестнадц|семнадц|восемнадц|девятнадц|двадц|тридц|сорок|девяност|сто|сот|двест|"
                      r"тысяч|миллион|полтор|процент|первы|втор|трет)")


def words(s):
    s = s.lower().replace("ё", "е").replace("%", " процентов ")
    return [w for w in re.sub(r"[^0-9a-zа-я ]+", " ", s).split() if w]


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def numeric(w):
    return bool(re.fullmatch(r"\d+[a-zа-я]*", w) or NUM_ROOT.match(w))


def check(folder: Path, video: Path, dmin: float, dmax: float) -> dict:
    qa = folder / "qa"; qa.mkdir(exist_ok=True)
    plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    script = " ".join(s["text"] for s in plan["scenes"])
    rep = {"video": video.name}
    dur = float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)]).stdout)
    rep["duration"] = round(dur, 2)
    code = ("import sys,json\nsys.stdout.reconfigure(encoding='utf-8')\nfrom faster_whisper import WhisperModel\n"
            "m=WhisperModel('large-v3',device='cpu',compute_type='int8')\n"
            "segs,_=m.transcribe(sys.argv[1],language='ru',beam_size=5,vad_filter=True)\nprint(' '.join(s.text.strip() for s in segs))")
    asr = run([WHISPER, "-c", code, str(video)]).stdout.strip().splitlines()[-1]
    rep["asr"] = asr
    a, b = words(script), words(asr)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    hit = sum(x.size for x in sm.get_matching_blocks())
    miss = [a[i] for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag in ("replace", "delete") for i in range(i1, i2)]
    soft = [w for w in miss if numeric(w)]          # число словом в сценарии = цифра в ASR и наоборот
    rep["recognized"] = round((hit + len(soft)) / max(1, len(a)), 4)
    rep["missed_words"] = [w for w in miss if not numeric(w)]
    rep["extra_words"] = [b[j] for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag in ("replace", "insert") for j in range(j1, j2)]
    bd = run(["ffmpeg", "-i", str(video), "-vf", "blackdetect=d=0.1:pix_th=0.05", "-an", "-f", "null", "-"]).stderr
    rep["black"] = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", bd)
    lu = run(["ffmpeg", "-i", str(video), "-af", "ebur128=peak=true", "-vn", "-f", "null", "-"]).stderr
    m = (re.findall(r"I:\s+(-?[\d.]+) LUFS", lu) or [None])[-1]; tp = (re.findall(r"Peak:\s+(-?[\d.]+) dBFS", lu) or [None])[-1]
    rep["lufs"] = float(m) if m else None
    rep["true_peak"] = float(tp) if tp else None
    tail = run(["ffmpeg", "-sseof", "-0.6", "-i", str(video), "-af", "volumedetect", "-vn", "-f", "null", "-"]).stderr
    mv = re.search(r"max_volume: (-?[\d.]+) dB", tail)
    rep["tail_max_db"] = float(mv.group(1)) if mv else None
    proc = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", "fps=1,scale=180:320", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                          capture_output=True)
    fb = 180 * 320 * 3
    frames = [Image.frombytes("RGB", (180, 320), proc.stdout[k * fb:(k + 1) * fb]) for k in range(len(proc.stdout) // fb)]
    cols, per = 7, 21
    rep["boards"] = []
    for s in range(0, len(frames), per):
        chunk = frames[s:s + per]; rows = (len(chunk) + cols - 1) // cols
        sh = Image.new("RGB", (cols * 180, rows * 320))
        for i, im in enumerate(chunk): sh.paste(im, ((i % cols) * 180, (i // cols) * 320))
        sh.thumbnail((1280, 1280))
        p = qa / f"board_{s // per + 1}.jpg"; sh.save(p, quality=88); rep["boards"].append(p.name)
    probs = []
    if rep["recognized"] < RECOGNIZED_MIN:
        probs.append(f"распознано {rep['recognized']:.0%} слов сценария, нужно не меньше {RECOGNIZED_MIN:.0%}: {rep['missed_words'][:12]}")
    if rep["black"]:
        probs.append(f"чёрные кадры: {rep['black'][:4]}")
    if rep["tail_max_db"] is None or rep["tail_max_db"] > TAIL_MAX_DB:
        probs.append(f"хвост {rep['tail_max_db']} дБ, нужно тише {TAIL_MAX_DB:.0f}")
    if not dmin <= dur <= dmax:
        probs.append(f"длина {dur:.1f} с вне окна {dmin:.0f}-{dmax:.0f} с")
    rep["problems"], rep["ok"] = probs, not probs
    (qa / "qa.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("folder"); ap.add_argument("video", nargs="?")
    ap.add_argument("--min", type=float, default=45.0); ap.add_argument("--max", type=float, default=60.0)
    a = ap.parse_args()
    folder = Path(a.folder).resolve()
    video = Path(a.video).resolve() if a.video else next(iter(sorted(folder.glob("*_v*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)), None)
    if not video or not video.exists():
        print("нет ролика: укажи путь"); return 2
    rep = check(folder, video, a.min, a.max)
    print(json.dumps({k: v for k, v in rep.items() if k not in ("asr", "boards")}, ensure_ascii=False, indent=1))
    print("ИТОГ:", "чисто" if rep["ok"] else "БРАК: " + "; ".join(rep["problems"]))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
