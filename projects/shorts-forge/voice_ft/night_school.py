# -*- coding: utf-8 -*-
"""Ночной конвейер «русской школы» (слово Гора 03.10: «да обучайся всю ночь»). Запуск системным Python 3.12.

  1. кодирование школы (122 ч, 16 дикторов) в коды 12 Гц            qwen_prepare2.py, ~25 мин
  2. школа: многодикторное дообучение базовой модели на текстах со знаком ударения     qwen_sft.py --multi_speaker
  3. v5: голос Гора поверх школы (те же 1139 фраз с ударениями, рецепт v4)          qwen_sft.py
  4. сравнение v5 с v4 на фразах-ловушках: детектор ударений, разборчивость, пары для прослушивания
Окно тишины 05:40-06:40: кодирование и обучение уходят с карты (сохраняются), утренний ролик фабрики
в 06:00 озвучивается голосом Гора через канал узла, потом конвейер продолжает с места паузы.
v5 в канал НЕ ставится: решение по слуху за Гором. Журнал: H:\\tts_data\\school\\night.log
"""
import datetime as dt
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

PY = r"C:\Apps\qwen-tts\.venv\Scripts\python.exe"
GIGA = r"C:\Apps\gigaam\.venv\Scripts\python.exe"
FT = Path(r"C:\CLAUD\projects\shorts-forge\voice_ft")
FORGE = FT.parent
S = Path(r"H:\tts_data\school")
DS = FORGE / "work_voice_gor" / "dataset"
BASE = r"H:\comfy-models\TTS\Qwen3-TTS-12Hz-1.7B-Base"
SCHOOL = Path(r"C:\Apps\voice-models\gor-school")
V5 = Path(r"C:\Apps\voice-models\gor-qwen-v5")
QUIET = "05:40-06:40"
LOG = S / "night.log"
ENV = dict(os.environ, PATH=r"C:\Apps\sox\sox-14.4.2;" + os.environ.get("PATH", ""),
           PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONUNBUFFERED="1")


def log(msg):
    line = f"{dt.datetime.now():%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def in_quiet():
    a, b = QUIET.split("-")
    now = dt.datetime.now().strftime("%H:%M")
    return a <= now < b


def wait_quiet():
    while in_quiet():
        time.sleep(60)


def run(cmd, out_log, cwd=FT):
    with open(out_log, "ab") as f:
        f.write(f"\n$ {' '.join(map(str, cmd))}\n".encode("utf-8"))
        f.flush()
        return subprocess.run(list(map(str, cmd)), cwd=str(cwd), env=ENV, stdout=f, stderr=subprocess.STDOUT).returncode


def lines(p):
    return sum(1 for _ in open(p, encoding="utf-8"))


def train(out: Path, init: str, train_jsonl, eval_jsonl, lr: float, epochs: int, multi: bool, save_every: int,
          save_from: int, quiet: bool = True):
    """Обучение с паузами на окно тишины: после паузы продолжение с checkpoint-pause до исходного числа шагов."""
    out.mkdir(parents=True, exist_ok=True)
    total = math.ceil(lines(train_jsonl) / 4 / 8) * epochs
    pj = out / "progress.json"
    cur_init, attempt = init, 0
    while True:
        done = json.load(open(pj, encoding="utf-8"))["opt_steps_total"] if pj.exists() else 0
        left = total - done
        if left <= 0:
            return
        wait_quiet()
        cmd = [PY, "qwen_sft.py", "--init_model_path", cur_init, "--output_model_path", out,
               "--train_jsonl", train_jsonl, "--eval_jsonl", eval_jsonl, "--batch_size", 4, "--grad_accum", 8,
               "--lr", lr, "--num_epochs", epochs if done == 0 else max(1, math.ceil(left / (total / epochs))),
               "--save_from_epoch", save_from, "--speaker_name", "gor"]
        if quiet:                      # пауза только у школы: чекпоинт голоса без кодировщика голоса не продолжить
            cmd += ["--quiet", QUIET]
        if done:
            cmd += ["--max_steps", left]
        if multi:
            cmd += ["--multi_speaker", "--ref_sec", 4]
        if save_every:
            cmd += ["--save_every_steps", save_every]
        log(f"{out.name}: старт, сделано {done}/{total} шагов, от {cur_init}")
        rc = run(cmd, out / "stdout.log")
        log(f"{out.name}: выход {rc}")
        if rc == 3:
            cur_init = str(out / "checkpoint-pause")
            continue
        if rc != 0:
            attempt += 1
            if attempt >= 2:
                raise SystemExit(f"{out.name}: обучение падает, код {rc}, смотри {out / 'stdout.log'}")
            continue
        return


def main():
    S.mkdir(parents=True, exist_ok=True)
    log("=== ночь школы: старт")
    # 1. кодирование
    for raw, codes in (("school_eval_raw.jsonl", "school_eval_codes.jsonl"), ("school_raw.jsonl", "school_codes.jsonl")):
        while True:
            wait_quiet()
            rc = run([PY, "qwen_prepare2.py", "--input_jsonl", S / raw, "--output_jsonl", S / codes,
                      "--bf16", "--batch_sec", 240, "--quiet", QUIET], S / "prep2.log")
            if rc == 0:
                break
            log(f"кодирование {raw}: код {rc}, повтор через минуту")
            time.sleep(60)
        log(f"закодировано {codes}: {lines(S / codes)} фраз")
    # 2. школа: 1 эпоха по 122 ч, lr 5e-6 (школа учит ударения и русскую речь, а не голос)
    train(SCHOOL, BASE, S / "school_codes.jsonl", S / "school_eval_codes.jsonl", 5e-6, 1, True, 500, 0)
    fin = next((SCHOOL / d for d in ("checkpoint-final", "checkpoint-epoch-0") if (SCHOOL / d).exists()), None)
    if fin is None:
        cands = sorted(SCHOOL.glob("checkpoint-step-*"), key=lambda p: int(p.name.split("-")[-1]))
        fin = cands[-1] if cands else SCHOOL / "checkpoint-pause"
    log(f"школа готова: {fin}")
    # 3. v5: голос Гора поверх школы, рецепт v4 (3 эпохи, сохранять каждую)
    train(V5, str(fin), DS / "train_stress_codes.jsonl", DS / "test_stress_codes.jsonl", 2e-6, 3, False, 0, 1, quiet=False)
    for ck in V5.glob("checkpoint-epoch-*"):
        (ck / "STRESS_MARKS").write_text("Обучена на текстах со знаком ударения (gor_stress.accent).", encoding="utf-8")
    log("v5 готова")
    # 4. сравнение с v4 на ловушках
    wait_quiet()
    rep = ["# Утренний отчёт: школа + v5 против v4", ""]
    for ck in sorted(V5.glob("checkpoint-epoch-*")):
        tag = "v5" + ck.name.replace("checkpoint-epoch-", "e") + "_marked"
        run([PY, "stress_gen.py", ck, tag, "marked"], S / "eval.log", cwd=FORGE)
        r = subprocess.run([PY, "stress_detect.py", "eval", FORGE / "work_voice_gor" / "stress" / tag,
                            FORGE / "work_voice_gor" / "stress" / "traps_truth.tsv"],
                           cwd=str(FORGE), env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace")
        rep.append("- " + (r.stdout.strip().splitlines() or ["нет вывода"])[-1])
    r = subprocess.run([PY, "stress_detect.py", "eval", FORGE / "work_voice_gor" / "stress" / "v4e2_marked",
                        FORGE / "work_voice_gor" / "stress" / "traps_truth.tsv"],
                       cwd=str(FORGE), env=ENV, capture_output=True, text=True, encoding="utf-8", errors="replace")
    rep.append("- для сравнения " + (r.stdout.strip().splitlines() or ["нет вывода"])[-1])
    (S / "MORNING_REPORT.md").write_text("\n".join(rep) + "\n", encoding="utf-8")
    log("=== ночь школы: готово, отчёт " + str(S / "MORNING_REPORT.md"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
