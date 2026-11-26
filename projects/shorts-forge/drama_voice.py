# -*- coding: utf-8 -*-
"""ОБЩАЯ ОЗВУЧКА DRAMA 3 для любого эпизода (аудит 23.10 п.21; Гор 14.10: «озвучка должна быть драмой», «мы работаем только с драмой»).
Одна копия вместо shorts_e/E04, E05 и long/L02 (те остаются историей своих роликов). Сервер fish-speech 127.0.0.1:8090,
эталон H:/tts-models/drama-3/refs/gor_ref.wav + .lab (канон «драма олд», skills/drama3-voice). Подъём сервера и карты: тот же скил.

Что сверх копии Э04:
  словарь  текст реплики проходит gor_normalize.normalize (gor_lexicon.tsv, одна копия; чтения по записям Гора);
           латиница вне словаря = отказ: впиши слово в словарь, голос не угадывает;
  замок    plan.json несёт voice_sha1 текста, прошедшего финальный круг (E05/WORKFLOW шаг 3е); нет или не совпал = отказ;
           печать ставит `seal` после линтера слога (rubrics.lint);
  проверка предел шагов по длине, срез тишины, расшифровка faster-whisper, до 4 попыток; код выхода 0 только без брака;
  склейка  `assemble`: паузы 0,15 с, темп не выше 1,12 (audio-voice.md «не гнать выше 1.12»; Э04 собран на 1,125).

  py -3.12 projects/shorts-forge/drama_voice.py seal <папка эпизода>                 линтер слога и voice_sha1 в plan.json
  py -3.12 projects/shorts-forge/drama_voice.py synth <папка> [--check]               voice_drama/v{i}.wav по сценам plan.json
  py -3.12 projects/shorts-forge/drama_voice.py lines <lines.json> <папка> [--check]  реплики списком (линия И, zhelezki_short)
  py -3.12 projects/shorts-forge/drama_voice.py assemble <папка>                      voice.wav, voice_timing.json, voice.asr.json
Синтез идёт через питон fish-speech (там ormsgpack), расшифровка через venv whisper на процессоре после синтеза (CPU не делить).
"""
import difflib
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "tools"))
import gor_normalize as GN  # noqa: E402
import gpu_slot  # noqa: E402  (аудит 23.10 п.23: синтез под общим слотом 5090)

URL = "http://127.0.0.1:8090/v1/tts"
REF = Path("H:/tts-models/drama-3/refs/gor_ref.wav")
FISH_PY = r"C:\Apps\fish-speech\.venv\Scripts\python.exe"
WHISPER = r"C:\Apps\whisper\.venv\Scripts\python.exe"
FPS_CODEC = 21.5            # кадров кодека на секунду звука
TRIES = 4
GAP, LEAD, MAXLEN = 0.15, 0.08, 55.0
MAXTEMPO = 1.12             # audio-voice.md:231 «не гнать выше 1.12»
LONG_WORDS_E = 165          # канон линии Э 140-160 слов (E05/WORKFLOW 3е снял «больше 110» у rubrics.lint), запас 5

SYNTH = r"""
import json, sys, ormsgpack, requests
a = json.load(open(sys.argv[1], encoding="utf-8"))
ref = {"audio": open(a["ref"], "rb").read(), "text": a["ref_text"]}
r = requests.post(a["url"], data=ormsgpack.packb({"text": a["text"], "references": [ref], "format": "wav", "max_new_tokens": a["cap"]}),
                  headers={"Content-Type": "application/msgpack"}, timeout=1800)
if r.status_code != 200:
    print(f"HTTP {r.status_code} {r.text[:200]}"); sys.exit(1)
open(a["dst"], "wb").write(r.content)
"""


def norm(s):
    s = s.lower().replace("ё", "е")
    return re.sub(r"[^a-zа-я0-9 ]+", " ", s).split()


def sha1(texts):
    return hashlib.sha1("\n".join(t.strip() for t in texts).encode("utf-8")).hexdigest()


def plan_texts(plan):
    return [s.get("voice") or s["text"] for s in plan["scenes"]]


def spoken(texts):
    """Текст для голоса: правила и словарь gor_normalize. Латиница вне словаря = отказ."""
    before = set(GN.unknown())
    out = [GN.normalize(t) for t in texts]
    new = sorted(set(GN.unknown()) - before)
    if new:
        raise SystemExit("ОТКАЗ: латиница вне словаря, впиши в projects/shorts-forge/gor_lexicon.tsv: " + ", ".join(new))
    return out


def asr(paths):
    """faster-whisper small на процессоре (карта занята Drama): текст и конец речи по каждому файлу."""
    code = ("import sys,json\nsys.stdout.reconfigure(encoding='utf-8')\nfrom faster_whisper import WhisperModel\n"
            "m=WhisperModel('small',device='cpu',compute_type='int8')\nout={}\n"
            "for p in sys.argv[1:]:\n  segs,_=m.transcribe(p,language='ru',vad_filter=True)\n  segs=list(segs)\n"
            "  out[p]={'text':' '.join(s.text.strip() for s in segs),'end':(segs[-1].end if segs else 0.0)}\n"
            "print(json.dumps(out,ensure_ascii=False))")
    r = subprocess.run([WHISPER, "-c", code, *map(str, paths)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return json.loads(r.stdout.strip().splitlines()[-1])


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True).stdout or 0)


def verdict(path, voice, screen, res):
    got = " ".join(norm(res["text"]))
    sim = max(difflib.SequenceMatcher(None, " ".join(norm(voice)), got).ratio(),
              difflib.SequenceMatcher(None, " ".join(norm(screen)), got).ratio())
    d = dur(path)
    expect = len(voice) / 13.0                             # около 13 знаков в секунду у живой начитки Гора
    ok = sim >= 0.62 and d <= expect * 1.9 + 1.0 and res["end"] >= d - 1.6
    return ok, f"сходство {sim:.2f}, {d:.1f} с (ждём около {expect:.1f}), речь до {res['end']:.1f} с, «{res['text'][:70]}»"


def synth(text, dst):
    cap = int(FPS_CODEC * (len(text) / 11.0 + 1.5))
    raw = dst.with_suffix(".raw.wav")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"url": URL, "text": text, "ref": str(REF), "ref_text": REF.with_suffix(".lab").read_text(encoding="utf-8").strip(),
                   "cap": cap, "dst": str(raw)}, f, ensure_ascii=False)
    r = subprocess.run([FISH_PY, "-c", SYNTH, f.name], capture_output=True, text=True, encoding="utf-8", errors="replace")
    Path(f.name).unlink(missing_ok=True)
    if r.returncode:
        raise RuntimeError((r.stdout + r.stderr).strip()[-300:])
    af = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.02,"
          "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", af, str(dst)], check=True)
    raw.unlink()


def voice_files(voices, screens, out: Path, check_only: bool) -> int:
    out.mkdir(parents=True, exist_ok=True)
    have = [out / f"v{i}.wav" for i in range(len(voices)) if (out / f"v{i}.wav").exists()]
    res = asr(have) if have else {}
    bad = []
    for i, (v, s) in enumerate(zip(voices, screens)):
        p = out / f"v{i}.wav"
        if str(p) in res:
            ok, why = verdict(p, v, s, res[str(p)])
            print(f"v{i}: {'ГОДЕН' if ok else 'БРАК '} {why}", flush=True)
            if ok:
                continue
        else:
            print(f"v{i}: нет файла", flush=True)
        bad.append(i)
    if check_only or not bad:
        print("брак:", bad or "нет"); return 0 if not bad else 1
    try:
        urllib.request.urlopen(URL.rsplit("/v1/", 1)[0] + "/v1/health", timeout=10)
    except Exception as e:
        raise SystemExit(f"сервер Drama 3 не отвечает ({e!r}): подними по skills/drama3-voice (карта, rig-quiet, api_server :8090)")
    still = []
    try:
        with gpu_slot.slot("drama_voice", wait=1800):
            for i in bad:
                p = out / f"v{i}.wav"
                for k in range(1, TRIES + 1):
                    t0 = time.perf_counter()
                    try:
                        synth(voices[i], p)
                    except Exception as e:  # noqa: BLE001
                        print(f"v{i} попытка {k}: {e}", flush=True); continue
                    ok, why = verdict(p, voices[i], screens[i], asr([p])[str(p)])
                    print(f"v{i} попытка {k}: {time.perf_counter() - t0:5.0f} с, {'ГОДЕН' if ok else 'брак'}: {why}", flush=True)
                    if ok:
                        break
                else:
                    still.append(i)
    except gpu_slot.Busy as e:
        raise SystemExit(f"{e}: ждал 30 мин, озвучку не начинаю")
    print("готово, брак после попыток:", still or "нет")
    return 0 if not still else 1


WAIVE_HARD = ("мат",)      # крупные законы цитатой не снимаются (gs-shorts-master §1, закон 16.10)


def waived(plan: dict, probs: list[str]) -> tuple[list[str], list[str]]:
    """Снятие правила линтера на один ролик только дословными словами Гора (audit-lock закон 7; Р01 11.11: Гор на вопрос
    про «нет вердикта» выбрал «Оставить действие»). plan.json `lint_waivers`: [{"rule": начало строки линтера, "key": слово,
    которое обязано стоять в его реплике или в вопросе, на который он ответил, "quote": его слова, "after": ISO-время}].
    Цитату ищет машина в стенограммах (skills/audit-lock/scripts/owner_words.py said), рукой вписанное без его слов не проходит."""
    ws = plan.get("lint_waivers") or []
    if not ws:
        return probs, []
    sys.path.insert(0, str(HERE.parents[1] / "skills" / "audit-lock" / "scripts"))
    import owner_words as OW
    left, notes = list(probs), []
    for w in ws:
        rule, key, quote = str(w.get("rule") or ""), str(w.get("key") or "").lower(), str(w.get("quote") or "")
        hits = [p for p in left if rule and p.startswith(rule)]
        if not hits:
            continue
        if any(h in rule for h in WAIVE_HARD) or not (quote and key and w.get("after")):
            notes.append(f"! снятие «{rule}» не принято: крупный закон или нет quote/key/after"); continue
        r = OW.said(quote, Path.home() / ".claude" / "projects", w["after"])
        if not r or key not in (str(r.get("kind", "")) + " " + str(r.get("text", ""))).lower():
            notes.append(f"! снятие «{rule}» не принято: слов Гора «{quote}» про «{key}» после {w['after']} в стенограммах нет"); continue
        w["found"] = {"ts": r.get("ts"), "session": r.get("session"), "kind": str(r.get("kind", ""))[:120]}
        for h in hits:
            left.remove(h)
            notes.append(f"~ {h} (снято словом Гора «{r.get('text')}», {r.get('ts')})")
    return left, notes


def cmd_seal(folder: Path) -> int:
    import rubrics
    pf = folder / "plan.json"
    plan = json.loads(pf.read_text(encoding="utf-8"))
    probs = rubrics.lint(plan)
    soft = []
    for p in list(probs):
        m = re.match(r"начитка (\d+) слов", p)
        if m and plan.get("line") == "Э" and int(m.group(1)) <= LONG_WORDS_E:
            probs.remove(p); soft.append(p + f" (линия Э: канон 140-160 слов, допуск до {LONG_WORDS_E})")
    for p in soft:
        print("  ~ " + p)
    probs, notes = waived(plan, probs)
    for n in notes:
        print("  " + n)
    if probs:
        print("ОТКАЗ печати: слог не чист\n" + "\n".join("  ! " + p for p in probs)); return 1
    spoken(plan_texts(plan))                     # словарь проверяется до печати, не на синтезе
    plan["voice_sha1"] = sha1(plan_texts(plan))
    pf.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print("печать текста:", plan["voice_sha1"]); return 0


def cmd_synth(folder: Path, check_only: bool) -> int:
    plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    texts = plan_texts(plan)
    if plan.get("voice_sha1") != sha1(texts):
        print("ОТКАЗ замка текста: в plan.json " + ("нет voice_sha1" if not plan.get("voice_sha1") else "voice_sha1 не совпадает с текстом")
              + ". Текст должен пройти финальный круг (линтер, тире, ритм, гейт фактов) и печать: drama_voice.py seal <папка>")
        return 2
    return voice_files(spoken(texts), [s["text"] for s in plan["scenes"]], folder / "voice_drama", check_only)


def cmd_lines(lines_json: Path, out: Path, check_only: bool) -> int:
    lines = json.loads(lines_json.read_text(encoding="utf-8"))
    return voice_files(spoken(lines), lines, out, check_only)


def cmd_assemble(folder: Path) -> int:
    plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    vd, n = folder / "voice_drama", len(plan["scenes"])
    src = [vd / f"v{i}.wav" for i in range(n)]
    miss = [p.name for p in src if not p.exists()]
    if miss:
        print("нет реплик:", ", ".join(miss)); return 1
    raw = sum(dur(p) for p in src) + GAP * (n - 1) + LEAD
    tempo = min(MAXTEMPO, max(1.0, (raw - GAP * (n - 1) - LEAD) / (MAXLEN - GAP * (n - 1) - LEAD)))
    print(f"сырая длина {raw:.2f} с, темп {tempo:.3f}" + (" (потолок 1,12: длиннее 55 с, резать текст)" if tempo >= MAXTEMPO else ""))
    parts = []
    for i, p in enumerate(src):
        q = vd / f"t{i}.wav"
        af = ("silenceremove=stop_periods=-1:stop_duration=0.15:stop_threshold=-35dB:stop_silence=0.15,"   # паузы внутри реплики до 0,15 с
              + (f"atempo={tempo:.4f}," if tempo > 1.0005 else "") + "aresample=48000")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-af", af, "-ac", "1", str(q)], check=True)
        parts.append(q)
    durs = [round(dur(q), 3) for q in parts]
    starts, t = [], LEAD
    for d in durs:
        starts.append(round(t, 3)); t += d + GAP
    total = round(starts[-1] + durs[-1], 3)
    ins, flt = [], []
    for i, q in enumerate(parts):
        ins += ["-i", str(q)]; flt.append(f"[{i}:a]adelay={int(starts[i] * 1000)}:all=1[a{i}]")
    flt.append("".join(f"[a{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0:duration=longest[o]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(flt), "-map", "[o]", "-ar", "48000", "-ac", "1",
                    str(folder / "voice.wav")], check=True)
    (folder / "voice_timing.json").write_text(json.dumps({"starts": starts, "durs": durs, "total": total, "gap": GAP, "lead": LEAD,
                                                          "tempo": tempo, "voice": "drama3", "voice_sha1": plan.get("voice_sha1")}, indent=1),
                                              encoding="utf-8")
    print(f"голос {total:.2f} с")
    code = ("import sys,json\nsys.stdout.reconfigure(encoding='utf-8')\nfrom faster_whisper import WhisperModel\n"
            "m=WhisperModel('large-v3',device='cpu',compute_type='int8')\n"
            "segs,_=m.transcribe(sys.argv[1],language='ru',word_timestamps=True,vad_filter=False)\nW=[]\nT=[]\n"
            "for s in segs:\n  T.append(s.text.strip())\n  for w in s.words: W.append({'w':w.word.strip(),'s':round(w.start,3),'e':round(w.end,3)})\n"
            "json.dump({'model':'faster-whisper large-v3 cpu','text':' '.join(T),'words':W},open(sys.argv[2],'w',encoding='utf-8'),ensure_ascii=False,indent=1)\n"
            "print(len(W),'слов')")
    r = subprocess.run([WHISPER, "-c", code, str(folder / "voice.wav"), str(folder / "voice.asr.json")], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    print(r.stdout.strip()[-200:], r.stderr.strip()[-300:] if r.returncode else "")
    return r.returncode


def main(a) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    chk = "--check" in a
    a = [x for x in a if x != "--check"]
    if len(a) >= 2 and a[0] == "seal":
        return cmd_seal(Path(a[1]))
    if len(a) >= 2 and a[0] == "synth":
        return cmd_synth(Path(a[1]), chk)
    if len(a) >= 3 and a[0] == "lines":
        return cmd_lines(Path(a[1]), Path(a[2]), chk)
    if len(a) >= 2 and a[0] == "assemble":
        return cmd_assemble(Path(a[1]))
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
