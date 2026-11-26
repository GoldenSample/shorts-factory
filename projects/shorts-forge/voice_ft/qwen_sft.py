# coding=utf-8
# На основе QwenLM/Qwen3-TTS finetuning/sft_12hz.py (Apache-2.0, см. QWEN3_TTS_LICENSE).
"""SFT голоса Гора поверх Qwen3-TTS-12Hz-1.7B-Base.

Отличия от официального скрипта и зачем:
  - attn_implementation="sdpa": flash-attn на Windows не стоит;
  - open(..., encoding="utf-8"): иначе cp1251 и падение на кириллице;
  - веса в fp32 + автокаст bf16 + 8-битный AdamW (bitsandbytes): в официальном скрипте модель грузится
    в bf16 и оптимизатор шагает прямо по bf16-весам, где шаг lr~1e-5 меньше половины шага сетки bf16
    у весов порядка 0.02, и большинство обновлений округляется в ноль. fp32-мастер это лечит, а 8-битные
    состояния Adam держат память в 32 ГБ;
  - заморожены text_embedding (311 млн параметров словаря, для тембра не нужен) и speaker_encoder;
  - разогрев 5 % шагов и косинус к 10 % lr; eval-лосс на отложенных фразах каждую эпоху;
  - чекпоинт сохраняется в bf16 (формат и размер как у исходной модели).
Инференс чекпоинта: generate_custom_voice(text, speaker=<speaker_name>, language="Auto") —
SFT учит только раскладку «Auto» (без токена языка), с language="Russian" раскладка не совпадёт.
"""
import argparse
import json
import math
import os
import shutil
import sys

import gc

import bitsandbytes as bnb
import torch
import torch.nn.functional as F
from accelerate import Accelerator
from qwen_dataset import TTSDataset
from qwen_tts.inference.qwen3_tts_model import Qwen3TTSModel
from safetensors.torch import save_file
from torch.utils.data import DataLoader
from transformers import AutoConfig

BASE = r"H:\comfy-models\TTS\Qwen3-TTS-12Hz-1.7B-Base"


def in_quiet(win):
    if not win:
        return False
    import datetime as dt
    a, b = win.split("-")
    now = dt.datetime.now().strftime("%H:%M")
    return a <= now < b if a < b else (now >= a or now < b)


def read_jsonl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def step_loss(model, batch, spk_holder):
    input_ids = batch["input_ids"]
    codec_ids = batch["codec_ids"]
    ref_mels = batch["ref_mels"]
    text_embedding_mask = batch["text_embedding_mask"]
    codec_embedding_mask = batch["codec_embedding_mask"]
    attention_mask = batch["attention_mask"]
    codec_0_labels = batch["codec_0_labels"]
    codec_mask = batch["codec_mask"]

    with torch.no_grad():
        speaker_embedding = model.speaker_encoder(ref_mels.to(model.device).to(torch.float32))
    if spk_holder[0] is None:
        spk_holder[0] = speaker_embedding[:1].detach().clone()

    # text_projection обязателен: на инференсе текст всегда идёт через него (PR #278)
    text_emb = model.talker.text_projection(model.talker.model.text_embedding(input_ids[:, :, 0]))
    input_text_embedding = text_emb * text_embedding_mask
    input_codec_embedding = model.talker.model.codec_embedding(input_ids[:, :, 1]) * codec_embedding_mask
    input_codec_embedding[:, 6, :] = speaker_embedding.to(input_codec_embedding.dtype)
    input_embeddings = input_text_embedding + input_codec_embedding
    for i in range(1, 16):
        e = model.talker.code_predictor.get_input_embeddings()[i - 1](codec_ids[:, :, i])
        input_embeddings = input_embeddings + e * codec_mask.unsqueeze(-1)

    # Оба лосса считаются здесь с ОДНИМ сдвигом. Штатный loss_function модели сам сдвигает метки,
    # а официальный скрипт сдвигал их ещё и вручную: модель училась предсказывать токен через один
    # (стартовый CE 7.4 при случайном уровне 7.6; у исправного выравнивания ~0.5-1.6, PR #278/#371).
    outputs = model.talker(inputs_embeds=input_embeddings, attention_mask=attention_mask,
                           output_hidden_states=True)
    logits = outputs.logits[:, :-1, :].float()
    codec0_loss = F.cross_entropy(logits.reshape(-1, logits.shape[-1]), codec_0_labels[:, 1:].reshape(-1),
                                  ignore_index=-100)

    # кадр кодека в позиции p предсказывался скрытым состоянием позиции p-1
    hidden = outputs.hidden_states[0][-1][:, :-1, :]
    talker_hidden = hidden[codec_mask[:, 1:]]
    talker_codec_ids = codec_ids[codec_mask]
    sub_in = [talker_hidden.unsqueeze(1), model.talker.get_input_embeddings()(talker_codec_ids[:, :1])]
    for i in range(1, 15):
        sub_in.append(model.talker.code_predictor.get_input_embeddings()[i - 1](talker_codec_ids[:, i:i + 1]))
    sub_out = model.talker.code_predictor.forward_finetune(inputs_embeds=torch.cat(sub_in, dim=1))
    sub_logits = sub_out.logits.float()
    sub_loss = F.cross_entropy(sub_logits.reshape(-1, sub_logits.shape[-1]), talker_codec_ids[:, 1:].reshape(-1))
    return codec0_loss + 0.3 * sub_loss, codec0_loss.detach(), sub_loss.detach()


def save_base(accelerator, model, final_dir, base):
    """Многодикторная «школа»: модель остаётся базовой (клон по образцу работает), голос не вшивается."""
    out_dir = final_dir + ".tmp"
    shutil.rmtree(out_dir, ignore_errors=True)
    shutil.copytree(base, out_dir, ignore=lambda d, names: ["model.safetensors"] if os.path.samefile(d, base) else [])
    sd = {k: v.detach().to("cpu", torch.bfloat16) for k, v in accelerator.unwrap_model(model).state_dict().items()}
    save_file(sd, os.path.join(out_dir, "model.safetensors"))
    del sd
    gc.collect()
    shutil.rmtree(final_dir, ignore_errors=True)
    os.rename(out_dir, final_dir)


def save_ckpt(accelerator, model, final_dir, speaker_name, spk_emb, base):
    out_dir = final_dir + ".tmp"
    shutil.rmtree(out_dir, ignore_errors=True)
    # исключается только верхний model.safetensors (его перепишем); веса speech_tokenizer/ нужны
    shutil.copytree(base, out_dir, ignore=lambda d, names: ["model.safetensors"]
                    if os.path.samefile(d, base) else [])
    with open(os.path.join(base, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["tts_model_type"] = "custom_voice"
    tc = cfg.get("talker_config", {})
    tc["spk_id"] = {speaker_name: 3000}
    tc["spk_is_dialect"] = {speaker_name: False}
    cfg["talker_config"] = tc
    with open(os.path.join(out_dir, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    sd = {k: v.detach().to("cpu", torch.bfloat16) for k, v in accelerator.unwrap_model(model).state_dict().items()
          if not k.startswith("speaker_encoder")}
    sd["talker.model.codec_embedding.weight"][3000] = spk_emb[0].to("cpu", torch.bfloat16)
    save_file(sd, os.path.join(out_dir, "model.safetensors"))
    del sd
    gc.collect()
    shutil.rmtree(final_dir, ignore_errors=True)
    os.rename(out_dir, final_dir)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init_model_path", default=BASE)
    ap.add_argument("--output_model_path", required=True)
    ap.add_argument("--train_jsonl", required=True)
    ap.add_argument("--eval_jsonl", default=None)
    ap.add_argument("--batch_size", type=int, default=4)
    ap.add_argument("--grad_accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--num_epochs", type=int, default=6)
    ap.add_argument("--save_from_epoch", type=int, default=1)
    ap.add_argument("--speaker_name", default="gor")
    ap.add_argument("--multi_speaker", action="store_true",
                    help="у каждой фразы свой образец голоса (ref_audio), образец режется до --ref_sec; сохраняется БАЗОВАЯ модель без вшитого голоса")
    ap.add_argument("--ref_sec", type=float, default=4.0)
    ap.add_argument("--save_every_steps", type=int, default=0)
    ap.add_argument("--quiet", default=None, help="HH:MM-HH:MM: в окне сохраниться и выйти с кодом 3 (карта нужна фабрике)")
    ap.add_argument("--max_steps", type=int, default=0, help="предел шагов оптимизатора (продолжение после паузы)")
    args = ap.parse_args()

    accelerator = Accelerator(gradient_accumulation_steps=args.grad_accum, mixed_precision="bf16")
    qwen = Qwen3TTSModel.from_pretrained(args.init_model_path, torch_dtype=torch.float32,
                                         attn_implementation="sdpa")
    config = AutoConfig.from_pretrained(args.init_model_path)
    model = qwen.model
    for n, p in model.named_parameters():
        if n.startswith("speaker_encoder") or "text_embedding" in n:
            p.requires_grad_(False)
    trainable = [p for p in model.parameters() if p.requires_grad]
    accelerator.print(f"обучаемых параметров: {sum(p.numel() for p in trainable) / 1e6:.0f} млн")

    rs = args.ref_sec if args.multi_speaker else None
    train_ds = TTSDataset(read_jsonl(args.train_jsonl), qwen.processor, config, ref_sec=rs)
    train_dl = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, collate_fn=train_ds.collate_fn)
    eval_dl = None
    if args.eval_jsonl:
        eval_ds = TTSDataset(read_jsonl(args.eval_jsonl), qwen.processor, config, ref_sec=rs)
        eval_dl = DataLoader(eval_ds, batch_size=args.batch_size, shuffle=False, collate_fn=eval_ds.collate_fn)

    opt = bnb.optim.AdamW8bit(trainable, lr=args.lr, weight_decay=0.01, betas=(0.9, 0.98))
    total = math.ceil(len(train_dl) / args.grad_accum) * args.num_epochs
    warm = max(1, int(0.05 * total))
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: (s + 1) / warm if s < warm else 0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * (s - warm) / max(1, total - warm))))
    model, opt, train_dl, sched = accelerator.prepare(model, opt, train_dl, sched)
    if eval_dl is not None:
        eval_dl = accelerator.prepare(eval_dl)
    accelerator.print(f"шагов оптимизатора: {total}, разогрев {warm}")

    spk = [None]
    os.makedirs(args.output_model_path, exist_ok=True)
    log = open(os.path.join(args.output_model_path, "train_log.txt"), "a", encoding="utf-8")
    step = 0
    for epoch in range(args.num_epochs):
        model.train()
        for batch in train_dl:
            with accelerator.accumulate(model):
                loss, l0, ls = step_loss(model, batch, spk)
                accelerator.backward(loss)
                if accelerator.sync_gradients:
                    accelerator.clip_grad_norm_(trainable, 1.0)
                opt.step()
                sched.step()
                opt.zero_grad()
            step += 1
            opt_steps = step // args.grad_accum
            stop_quiet = in_quiet(args.quiet) and step % args.grad_accum == 0
            stop_max = args.max_steps and opt_steps >= args.max_steps and step % args.grad_accum == 0
            if (stop_quiet or stop_max) and accelerator.is_main_process:
                d = os.path.join(args.output_model_path, "checkpoint-pause" if stop_quiet else "checkpoint-final")
                (save_base(accelerator, model, d, args.init_model_path) if args.multi_speaker else
                 save_ckpt(accelerator, model, d, args.speaker_name, spk[0], args.init_model_path))
                prev = 0
                pj = os.path.join(args.output_model_path, "progress.json")
                if os.path.exists(pj):
                    prev = json.load(open(pj, encoding="utf-8")).get("opt_steps_total", 0)
                json.dump({"opt_steps_total": prev + opt_steps, "last": d, "reason": "quiet" if stop_quiet else "max"},
                          open(pj, "w", encoding="utf-8"))
                accelerator.print(f"{'окно тишины: пауза' if stop_quiet else 'предел шагов'}, сохранён {d}", flush=True)
                sys.exit(3 if stop_quiet else 0)
            if args.save_every_steps and step % (args.save_every_steps * args.grad_accum) == 0 and accelerator.is_main_process:
                d = os.path.join(args.output_model_path, f"checkpoint-step-{step // args.grad_accum}")
                (save_base(accelerator, model, d, args.init_model_path) if args.multi_speaker else
                 save_ckpt(accelerator, model, d, args.speaker_name, spk[0], args.init_model_path))
                accelerator.print(f"сохранён {d}", flush=True)
            if step % 20 == 0:
                msg = (f"эпоха {epoch} шаг {step} loss {loss.item():.4f} (codec0 {l0.item():.4f} sub {ls.item():.4f}) "
                       f"lr {sched.get_last_lr()[0]:.2e} vram {torch.cuda.max_memory_allocated() / 2**30:.1f} ГБ")
                accelerator.print(msg, flush=True)
                log.write(msg + "\n"); log.flush()
        if eval_dl is not None:
            model.eval()
            tot, n = 0.0, 0
            with torch.no_grad():
                for batch in eval_dl:
                    l, _, _ = step_loss(model, batch, spk)
                    tot += l.item(); n += 1
            msg = f"=== эпоха {epoch}: eval loss {tot / max(1, n):.4f}"
            accelerator.print(msg, flush=True)
            log.write(msg + "\n"); log.flush()
        if epoch >= args.save_from_epoch and accelerator.is_main_process:
            d = os.path.join(args.output_model_path, f"checkpoint-epoch-{epoch}")
            if args.multi_speaker:
                save_base(accelerator, model, d, args.init_model_path)
            else:
                save_ckpt(accelerator, model, d, args.speaker_name, spk[0], args.init_model_path)
            accelerator.print(f"сохранён {d}", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
