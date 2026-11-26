# coding=utf-8
# На основе QwenLM/Qwen3-TTS finetuning/prepare_data.py (Apache-2.0, см. QWEN3_TTS_LICENSE).
# Правки: utf-8 при чтении и записи (на Windows open() по умолчанию cp1251 и падает на кириллице),
# токенизатор из локальной папки модели, прогресс в консоль.
"""Аудио -> коды 12 Гц токенизатора Qwen3-TTS для SFT.

  python qwen_prepare.py --input_jsonl train_raw.jsonl --output_jsonl train_codes.jsonl
"""
import argparse
import json
import sys

from qwen_tts import Qwen3TTSTokenizer

TOKENIZER = r"H:\comfy-models\TTS\Qwen3-TTS-12Hz-1.7B-Base\speech_tokenizer"
BATCH = 32


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--tokenizer_model_path", default=TOKENIZER)
    ap.add_argument("--input_jsonl", required=True)
    ap.add_argument("--output_jsonl", required=True)
    args = ap.parse_args()

    tok = Qwen3TTSTokenizer.from_pretrained(args.tokenizer_model_path, device_map=args.device)
    with open(args.input_jsonl, encoding="utf-8") as f:
        lines = [json.loads(x) for x in f if x.strip()]

    out = []
    for i in range(0, len(lines), BATCH):
        chunk = lines[i:i + BATCH]
        enc = tok.encode([x["audio"] for x in chunk])
        for code, line in zip(enc.audio_codes, chunk):
            line["audio_codes"] = code.cpu().tolist()
            out.append(line)
        print(f"  {min(i + BATCH, len(lines))}/{len(lines)}", flush=True)

    with open(args.output_jsonl, "w", encoding="utf-8") as f:
        for line in out:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
