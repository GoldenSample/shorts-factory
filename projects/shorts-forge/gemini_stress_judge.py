# -*- coding: utf-8 -*-
"""Судья ударений на Gemini (слушает звук и ставит знак ударения так, как СКАЗАНО, а не как надо).

Зачем: акустический детектор stress_detect.py совпадает с живым Гором только в 65 % слов, им нельзя
мерить двойника. Gemini получает пачку клипов в одном запросе (бесплатная квота считается запросами).
Сравнение: ударение из ответа против эталона (traps_truth.tsv или silero-stress для живых записей).
Оцениваются только многосложные слова без «ё».

  py -3.12 gemini_stress_judge.py dir ПАПКА [МОДЕЛЬ]      фразы-ловушки (эталон traps_truth.tsv)
  py -3.12 gemini_stress_judge.py files TSV [МОДЕЛЬ]      TSV: путь_к_wav<TAB>текст_с_ударениями
"""
from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gemini_tts import API, _post  # noqa: E402

ACUTE = "́"
VOW = set("аеиоуыэюяё")
TRUTH = HERE / "work_voice_gor" / "stress" / "traps_truth.tsv"
MODEL = "gemini-3.8-flash"
PROMPT = """Ты фонетист-носитель русского языка. Тебе даны аудиозаписи, у каждой известен текст.
Для КАЖДОЙ записи перепиши текст и поставь знак ударения (символ U+0301 сразу ПОСЛЕ ударной гласной)
в каждом слове из двух и более слогов ТАК, КАК ДИКТОР РЕАЛЬНО ПРОИЗНЁС, даже если это ошибка
(например, если диктор сказал «гигагерцА», пиши «гигагерца́»). Не исправляй диктора по словарю.
Если ударение в слове не слышно, знак не ставь. Слова не меняй, порядок не меняй.
Ответ: JSON-массив объектов {"id": "...", "text": "..."} в том же порядке, без пояснений."""


def stress_map(marked: str) -> list[tuple[str, int | None]]:
    out = []
    for m in re.finditer(r"[А-Яа-яЁё́]+", marked):
        w = m.group(0).lower()
        vi, st = -1, None
        for ch in w:
            if ch == ACUTE:
                st = vi
            elif ch in VOW:
                vi += 1
        out.append((w.replace(ACUTE, ""), st))
    return out


def _mp3(wav: str) -> bytes:
    """mp3 16 кГц моно: в 10 раз легче wav, в один запрос влезает 40+ клипов (бесплатная квота Gemini = число запросов)."""
    import shutil
    import subprocess
    r = subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-v", "error", "-i", wav, "-ar", "16000", "-ac", "1",
                        "-b:a", "48k", "-f", "mp3", "pipe:1"], capture_output=True, check=True)
    return r.stdout


def judge(items: list[tuple[str, str, str]], model: str = MODEL) -> dict[str, str]:
    """items: (id, wav_path, текст) -> {id: текст с ударениями как услышано}."""
    parts = [{"text": PROMPT}]
    for cid, wav, text in items:
        parts.append({"text": f"Запись id={cid}. Текст: {text.replace(ACUTE, '')}"})
        parts.append({"inlineData": {"mimeType": "audio/mp3", "data": base64.b64encode(_mp3(wav)).decode()}})
    body = {"contents": [{"parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    for attempt in range(6):            # 503 «high demand» у Gemini проходит сам через минуту-другую
        try:
            d = _post(f"{API}/models/{model}:generateContent", body, timeout=600)
            break
        except RuntimeError as e:
            if attempt == 5 or not any(c in str(e) for c in ("HTTP 503", "HTTP 500")):
                raise                   # 429 = кончилась суточная квота модели: повтор только жжёт запросы
            import time
            time.sleep(30 * (attempt + 1))
    txt = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
    return {r["id"]: r["text"] for r in json.loads(txt)}


def score(items: list[tuple[str, str, str]], heard: dict[str, str]) -> tuple[int, int, list[str]]:
    tot = ok = 0
    bad = []
    for cid, _, truth in items:
        t = stress_map(truth)
        h = stress_map(heard.get(cid, ""))
        if len(t) != len(h):
            bad.append(f"{cid}: ответ не совпал по словам")
            continue
        for (w, st), (w2, sh) in zip(t, h):
            if st is None or "ё" in w or sum(c in VOW for c in w) < 2 or sh is None:
                continue
            tot += 1
            if st == sh:
                ok += 1
            else:
                bad.append(f"{cid}:{w}(надо {st + 1}-й слог, слышно {sh + 1}-й)")
    return ok, tot, bad


def run(items: list[tuple[str, str, str]], model: str, label: str, batch: int = 40) -> None:
    heard = {}
    for i in range(0, len(items), batch):
        heard.update(judge(items[i:i + batch], model))
    ok, tot, bad = score(items, heard)
    print(f"{label}: ударение как в эталоне {ok}/{tot} = {ok / max(1, tot):.1%}")
    for b in bad:
        print("   ", b)
    safe = re.sub(r"[^\w]+", "_", label)          # вне f-строки: venv qwen-tts на 3.11
    Path(HERE / "work_voice_gor" / "stress" / f"_heard_{safe}.json").write_text(
        json.dumps(heard, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    mode, arg = sys.argv[1], sys.argv[2]
    model = sys.argv[3] if len(sys.argv) > 3 else MODEL
    if mode in ("dir", "exam"):          # exam: экзамен 60 фраз, эталон exam_truth.tsv (03.10)
        tp = TRUTH.with_name("exam_truth.tsv") if mode == "exam" else TRUTH
        truth = dict(l.split("\t", 1) for l in tp.read_text(encoding="utf-8").splitlines() if l.strip())
        its = [(k, str(Path(arg) / f"{k}.wav"), v) for k, v in truth.items() if (Path(arg) / f"{k}.wav").exists()]
        run(its, model, Path(arg).name + ("" if model == MODEL else "__" + model))   # судья в имени файла ответа
    elif mode == "voice":                # экзамен 60 + ловушки 20 одного голоса за 2 запроса: voice EXAMDIR TRAPSDIR [МОДЕЛЬ]
        traps_dir = sys.argv[3]
        model = sys.argv[4] if len(sys.argv) > 4 else MODEL
        its = []
        for tp, d in ((TRUTH.with_name("exam_truth.tsv"), arg), (TRUTH, traps_dir)):
            truth = dict(l.split("	", 1) for l in tp.read_text(encoding="utf-8").splitlines() if l.strip())
            its += [(k, str(Path(d) / f"{k}.wav"), v) for k, v in truth.items() if (Path(d) / f"{k}.wav").exists()]
        run(its, model, Path(arg).name + "+traps__" + model)
    else:
        its = []
        for i, l in enumerate(Path(arg).read_text(encoding="utf-8").splitlines()):
            if l.strip():
                w, t = l.split("\t", 1)
                its.append((f"c{i:02d}", w, t))
        run(its, model, Path(arg).stem)
