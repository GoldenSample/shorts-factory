# coding=utf-8
# На основе QwenLM/Qwen3-TTS finetuning/prepare_data.py (Apache-2.0).
"""Кодирование большого датасета в коды 12 Гц: с продолжением, сортировкой по длине и окном тишины.

Отличия от qwen_prepare.py (03.10, школа 122 ч): штатный проход кодировал 1.5 фразы/с и занимал 31 ГБ VRAM
(пакет 32 фразы до 14 с с дополнением до самой длинной), то есть 13 часов при закрытой карте.
  - фразы сортируются по длительности, пакет набирается до --batch_sec секунд звука (меньше пустых дополнений);
  - bf16 (--bf16): вдвое меньше памяти;
  - результат дописывается после каждого пакета, повторный запуск пропускает готовое;
  - --quiet HH:MM-HH:MM: в этом окне кодирование ставится на паузу (утренний ролик фабрики в 06:00 ждёт
    ~9 ГБ видеопамяти под голос Гора).
  python qwen_prepare2.py --input_jsonl in.jsonl --output_jsonl out.jsonl [--bf16] [--batch_sec 240] [--quiet 05:40-06:40]
"""
import argparse
import datetime as dt
import json
import sys
import time

import soundfile as sf
import torch
from qwen_tts import Qwen3TTSTokenizer

TOKENIZER = r"H:\comfy-models\TTS\Qwen3-TTS-12Hz-1.7B-Base\speech_tokenizer"


def in_quiet(win: str | None) -> bool:
    if not win:
        return False
    a, b = win.split("-")
    now = dt.datetime.now().strftime("%H:%M")
    return a <= now < b if a < b else (now >= a or now < b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input_jsonl", required=True)
    ap.add_argument("--output_jsonl", required=True)
    ap.add_argument("--bf16", action="store_true")
    ap.add_argument("--batch_sec", type=float, default=240.0)
    ap.add_argument("--quiet", default=None)
    args = ap.parse_args()

    done = set()
    try:
        with open(args.output_jsonl, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["audio"])
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    with open(args.input_jsonl, encoding="utf-8") as f:
        lines = [json.loads(x) for x in f if x.strip()]
    todo = [l for l in lines if l["audio"] not in done]
    for l in todo:
        l["_dur"] = sf.info(l["audio"]).duration
    todo.sort(key=lambda l: l["_dur"])
    print(f"всего {len(lines)}, готово {len(done)}, осталось {len(todo)}", flush=True)

    kw = {"device_map": "cuda:0"}
    if args.bf16:
        kw["dtype"] = torch.bfloat16
    tok = Qwen3TTSTokenizer.from_pretrained(TOKENIZER, **kw)
    t0, n = time.time(), 0
    with open(args.output_jsonl, "a", encoding="utf-8") as out:
        i = 0
        while i < len(todo):
            while in_quiet(args.quiet):
                print(f"{dt.datetime.now():%H:%M} окно тишины {args.quiet}: пауза", flush=True)
                time.sleep(120)
            batch, sec = [], 0.0
            while i < len(todo) and (not batch or sec + todo[i]["_dur"] <= args.batch_sec):
                batch.append(todo[i]); sec += todo[i]["_dur"]; i += 1
            enc = tok.encode([b["audio"] for b in batch])
            for code, b in zip(enc.audio_codes, batch):
                b = {k: v for k, v in b.items() if not k.startswith("_")}
                b["audio_codes"] = code.cpu().tolist()
                out.write(json.dumps(b, ensure_ascii=False) + "\n")
            out.flush()
            n += len(batch)
            if n % 2000 < len(batch):
                rate = n / (time.time() - t0)
                print(f"  {len(done) + n}/{len(lines)}  {rate:.1f} фраз/с, осталось ~{(len(todo) - n) / max(rate, 1e-6) / 60:.0f} мин",
                      flush=True)
    print("ГОТОВО", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
