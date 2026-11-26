# -*- coding: utf-8 -*-
"""Клиент локальной генерации картинок на 5090 (ComfyUI API, FLUX.1 schnell).

Зачем свой клиент, а не веб-морда: калибровка требует ДЕСЯТКОВ вариантов с разными
seed и промптами, а потом автоотбора по замеру. Руками в браузере это не гоняют.

Почему FLUX schnell: Apache-2.0 (лицензия чистая и для весов, и для выдачи —
в отличие от FLUX dev, где веса некоммерческие), дистиллят на 4 шага, то есть
вариант считается секундами, а не минутами. Для перебора это решающее.

ComfyUI живёт в C:\Apps\comfy (песочная копия удалена 2026-09-18 как дубль). С того же
дня его держит задача планировщика GSPC-ComfyUI на 10.77.0.2 и 127.0.0.1, так что
отдельно поднимать обычно не нужно; иначе ярлык «Комфи ВКЛ» или start() ниже.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import requests   # ⚠ НЕ urllib: его POST к ComfyUI на этой машине виснет намертво
                  # (GET проходит, curl POST проходит, urllib POST — нет). Час отладки.

COMFY_DIR = Path(
    r"C:\Apps\comfy\ComfyUI_windows_portable")
HOST = "http://127.0.0.1:8188"
CKPT = "flux1-schnell-fp8.safetensors"
OUT_DIR = COMFY_DIR / "ComfyUI" / "output"


def alive(timeout: float = 3) -> bool:
    try:
        return requests.get(f"{HOST}/system_stats", timeout=timeout).ok
    except Exception:
        return False


def start(wait: int = 240) -> None:
    """Дождаться ComfyUI. НЕ поднимает и НЕ гасит его сам — этим занят супервизор контура.

    ⛔ ИСТОРИЯ ЭТОЙ ФУНКЦИИ. Раньше она поднимала ComfyUI через Popen, а вызывающий код
    делал proc.terminate() в finally. Результат: каждый прогон убивал сервер, следующий
    поднимал заново, а после первого же убийства поднять обратно из шелла агента стало
    невозможно вовсе — `python_embeded\python.exe` виснет на 28 МБ, не доходя до
    `import torch`, порт не открывается. Перебраны Popen, nohup, PowerShell Start-Process
    и Планировщик: одинаково. Тот же симптом независимо словили два агента.

    Поэтому ComfyUI теперь ребёнок супервизора КОНТУРа (`kontur/supervisor.mjs`, имя
    `comfy`, проба на /system_stats). Супервизор поднимает его при старте машины,
    перезапускает при падении с растущим отступом и — главное — по пробе ловит зомби,
    который жив процессом, но не отвечает. Задача этой функции сузилась до ожидания.
    """
    for i in range(wait):
        if alive():
            return
        time.sleep(1)
    raise RuntimeError(
        "ComfyUI не отвечает на 8188. Поднимает его супервизор контура: "
        "`node C:/CLAUD/projects/kontur/supervisor.mjs status` покажет состояние, "
        "`... supervisor.mjs` без аргументов поднимет всё."
    )


def workflow(prompt: str, seed: int, w: int = 1280, h: int = 720, steps: int = 8,
             scheduler: str = "beta", hires_w: int = 1920, hires_h: int = 1088,
             hires_denoise: float = 0.30, hires_steps: int = 6) -> dict:
    """Граф FLUX schnell: генерация в НАТИВНОМ разрешении + апскейл вторым проходом.

    ⚑ ПОЧЕМУ БАЗА 1280x720, А НЕ СРАЗУ 1920.
    FLUX обучен на ~1 МП. 1280x720 = 0.92 МП — это его родная зона. 1920x1088 = 2.09 МП,
    то есть за порогом 2 МП, где у FLUX начинаются дубли объектов, второй горизонт и
    белые ореолы на границах свет/тень. Плюс у schnell `shift` жёстко 1.0, а расчётное
    значение для 1920x1088 — 1.84: на большом кадре сэмплер проскакивает область высоких
    сигм, где решается композиция. Генерируя в нативном разрешении, мы обходим обе
    проблемы разом и не тратим время на корректор shift.

    ⚑ АПСКЕЙЛ ПИКСЕЛЬНЫМ ПУТЁМ, А НЕ ЛАТЕНТНЫМ.
    У FLUX VAE 16-канальный (против 4 у SD): интерполяция латента разрушает больше
    смысла, и чинить это приходится высоким denoise (0.55+), на котором FLUX уже
    перекомпоновывает кадр. Пиксельный путь (decode → lanczos → encode) позволяет
    denoise 0.25-0.35: второй проход дорисовывает фактуру, НЕ трогая композицию.

    ⚠ denoise НЕ сокращает шаги: ComfyUI строит расписание на steps/denoise и берёт
    его хвост, так что hires_steps — это реальное число шагов второго прохода.

    Замеры первого прохода (calib_flux.py, сетка 11 прогонов на этой машине):
      · beta против simple при 8 шагах: детали 259 против 174 — берём beta;
      · 12 шагов вместо 8 на simple — плато (174.5 против 174.0), не платим за них;
      · FluxGuidance на schnell НЕ РАБОТАЕТ (guidance 2.0 и 3.5 дали побайтово тот же
        результат) — у schnell guidance_embeds=false;
      · cfg строго 1.0 — свойство дистилляции, а не «сила промпта».

    ⛔ Не добавлять сюда FreeU_V2 (упадёт: читает unet_config["model_channels"], которого
    у FLUX нет) и PerturbedAttentionGuidance (патчит ключи attn1/middle, которых FLUX
    не читает — эффект нулевой, время вдвое).
    """
    g = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": prompt}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": ""}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": w, "height": h, "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                         "latent_image": ["4", 0], "seed": seed, "steps": steps,
                         "cfg": 1.0, "sampler_name": "euler", "scheduler": scheduler,
                         "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
    }
    if not hires_w:                                   # без апскейла — отдать как есть
        g["7"] = {"class_type": "SaveImage",
                  "inputs": {"images": ["6", 0], "filename_prefix": "cog"}}
        return g
    g.update({
        "8": {"class_type": "ImageScale",
              "inputs": {"image": ["6", 0], "upscale_method": "lanczos",
                         "width": hires_w, "height": hires_h, "crop": "disabled"}},
        "9": {"class_type": "VAEEncode", "inputs": {"pixels": ["8", 0], "vae": ["1", 2]}},
        "10": {"class_type": "KSampler",
               "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                          "latent_image": ["9", 0], "seed": seed + 1, "steps": hires_steps,
                          "cfg": 1.0, "sampler_name": "euler", "scheduler": scheduler,
                          "denoise": hires_denoise}},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage",
              "inputs": {"images": ["11", 0], "filename_prefix": "cog"}},
    })
    return g


def generate(prompt: str, seed: int, dest: Path, **kw) -> bool:
    try:
        r = requests.post(f"{HOST}/prompt", json={"prompt": workflow(prompt, seed, **kw)},
                          timeout=120)
        if not r.ok:
            print("   отказ графа:", r.text[:400])
            return False
        pid = r.json()["prompt_id"]
    except Exception as e:
        print("   не отправилось:", str(e)[:200])
        return False

    for _ in range(600):                                   # schnell на 5090 — секунды
        time.sleep(1)
        try:
            hist = requests.get(f"{HOST}/history/{pid}", timeout=30).json()
        except Exception:
            continue
        if pid not in hist:
            continue
        outs = hist[pid].get("outputs", {})
        imgs = [i for o in outs.values() for i in o.get("images", [])]
        if not imgs:
            if hist[pid].get("status", {}).get("status_str") == "error":
                print("   ошибка графа:", str(hist[pid]["status"])[:240])
                return False
            continue
        src = OUT_DIR / imgs[0].get("subfolder", "") / imgs[0]["filename"]
        for _ in range(30):
            if src.exists() and src.stat().st_size > 10000:
                dest.write_bytes(src.read_bytes())
                src.unlink(missing_ok=True)
                return True
            time.sleep(0.5)
    return False


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    proc = start()
    try:
        d = Path(sys.argv[2] if len(sys.argv) > 2 else "test.png")
        t0 = time.time()
        ok = generate(sys.argv[1], 42, d)
        print(f"{'ok' if ok else 'ПУСТО'} · {time.time() - t0:.1f}с · {d}")
    finally:
        if proc:
            proc.terminate()
