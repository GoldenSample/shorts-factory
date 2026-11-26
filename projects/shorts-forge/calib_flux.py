# -*- coding: utf-8 -*-
"""Калибровка настроек FLUX на своей машине: сетка параметров → замер → таблица.

Смысл: рекомендации из сети проверяются на НАШЕМ железе и НАШЕЙ задаче
(тёмный фон под текст), а не принимаются на слово. Меряем то, что важно
именно для фона презентации:

  luma        — средняя яркость (палитра игры 19-24/255, фон обязан попасть в полосу)
  centre_busy — локальный градиент в центре: чем выше, тем хуже ляжет текст
  detail      — дисперсия лапласиана по всему кадру: «сколько проработки»
  banding     — гладкие переходы в тенях; на тёмных сценах FLUX любит ступеньки
  seconds     — цена варианта

Дальше эти числа сравниваются между настройками, а не с абстрактным идеалом.
"""
from __future__ import annotations

import itertools
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

import comfy_gen

HERE = Path(__file__).resolve().parent
OUT = HERE / "calib"
PROMPT = ("A stone forge chamber at deep night, viewed from the dark far end of the hall. "
          "A small bed of orange coals under a worn anvil. Finished iron tools hang in neat "
          "rows on the shadowed wall. The near half of the room is pure darkness. "
          "dark fantasy concept art, painterly matte painting, muted charcoal and dark umber "
          "palette, ninety percent of the frame in deep shadow, wide cinematic framing")


def gray(path: Path, w: int = 256) -> np.ndarray:
    r = subprocess.run(["ffmpeg", "-v", "error", "-threads", "1", "-i", str(path),
                        "-vf", f"scale={w}:-2,format=gray", "-f", "rawvideo",
                        "-pix_fmt", "gray", "-"], capture_output=True)
    a = np.frombuffer(r.stdout, dtype=np.uint8)
    h = len(a) // w
    return a[:h * w].reshape(h, w).astype(np.float32)


def measure(path: Path) -> dict:
    g = gray(path)
    h, w = g.shape
    c = g[int(h * .28):int(h * .72), int(w * .15):int(w * .85)]
    lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:])
    dark = g[g < 60]
    return {
        "luma": round(float(g.mean()), 1),
        "centre_busy": round(float(np.abs(np.diff(c, axis=1)).mean()
                                   + np.abs(np.diff(c, axis=0)).mean()), 2),
        "detail": round(float(lap.var()), 1),
        # ступеньки в тенях: мало уникальных уровней на тёмной части = бандинг
        "dark_levels": int(len(np.unique(np.round(dark)))) if dark.size else 0,
        "kb": path.stat().st_size // 1024,
    }


# Сетка: что проверяем. Значения взяты как разумные крайности, чтобы увидеть тренд.
GRID = [
    dict(tag="base_4step_simple",  steps=4,  sched="simple",     guid=None, w=1344, h=768),
    dict(tag="8step_simple",       steps=8,  sched="simple",     guid=None, w=1344, h=768),
    dict(tag="12step_simple",      steps=12, sched="simple",     guid=None, w=1344, h=768),
    dict(tag="4step_beta",         steps=4,  sched="beta",       guid=None, w=1344, h=768),
    dict(tag="8step_beta",         steps=8,  sched="beta",       guid=None, w=1344, h=768),
    dict(tag="8step_klopt",        steps=8,  sched="kl_optimal", guid=None, w=1344, h=768),
    dict(tag="8step_sgm",          steps=8,  sched="sgm_uniform", guid=None, w=1344, h=768),
    dict(tag="8step_beta_guid2",   steps=8,  sched="beta",       guid=2.0, w=1344, h=768),
    dict(tag="8step_beta_guid35",  steps=8,  sched="beta",       guid=3.5, w=1344, h=768),
    dict(tag="8step_beta_1920",    steps=8,  sched="beta",       guid=None, w=1920, h=1088),
    dict(tag="12step_beta_1920",   steps=12, sched="beta",       guid=None, w=1920, h=1088),
]


def workflow(cfg: dict, seed: int) -> dict:
    """Граф с опциональным FluxGuidance между текстом и сэмплером."""
    g = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": comfy_gen.CKPT}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": PROMPT}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["1", 1], "text": ""}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": cfg["w"], "height": cfg["h"], "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                         "latent_image": ["4", 0], "seed": seed, "steps": cfg["steps"],
                         "cfg": 1.0, "sampler_name": "euler", "scheduler": cfg["sched"],
                         "denoise": 1.0}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": "calib"}},
    }
    if cfg["guid"] is not None:
        g["8"] = {"class_type": "FluxGuidance",
                  "inputs": {"conditioning": ["2", 0], "guidance": cfg["guid"]}}
        g["5"]["inputs"]["positive"] = ["8", 0]
    return g


def run_one(cfg: dict, seed: int) -> dict | None:
    dest = OUT / f"{cfg['tag']}_s{seed}.png"
    t0 = time.time()
    if not dest.exists():
        body = json.dumps({"prompt": workflow(cfg, seed)}).encode()
        import urllib.request, urllib.error
        req = urllib.request.Request(f"{comfy_gen.HOST}/prompt", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            pid = json.loads(urllib.request.urlopen(req, timeout=60).read())["prompt_id"]
        except urllib.error.HTTPError as e:
            print("   отказ:", e.read().decode("utf-8", "replace")[:200])
            return None
        for _ in range(900):
            time.sleep(1)
            try:
                hist = json.loads(urllib.request.urlopen(
                    f"{comfy_gen.HOST}/history/{pid}", timeout=30).read())
            except Exception:
                continue
            if pid not in hist:
                continue
            imgs = [i for o in hist[pid].get("outputs", {}).values() for i in o.get("images", [])]
            if imgs:
                src = comfy_gen.OUT_DIR / imgs[0].get("subfolder", "") / imgs[0]["filename"]
                for _ in range(40):
                    if src.exists() and src.stat().st_size > 10000:
                        dest.write_bytes(src.read_bytes())
                        src.unlink(missing_ok=True)
                        break
                    time.sleep(0.5)
                break
            if hist[pid].get("status", {}).get("status_str") == "error":
                print("   ошибка:", str(hist[pid]["status"])[:200])
                return None
    if not dest.exists():
        return None
    m = measure(dest)
    m["seconds"] = round(time.time() - t0, 1)
    m["tag"] = cfg["tag"]
    return m


def main() -> int:
    OUT.mkdir(exist_ok=True)
    comfy_gen.start()
    rows = []
    try:
        for cfg in GRID:
            r = run_one(cfg, seed=777)          # один seed на всю сетку: сравниваем настройки
            if r:
                rows.append(r)
                print(f"  {r['tag']:20} luma {r['luma']:5.1f}  центр {r['centre_busy']:5.2f}  "
                      f"детали {r['detail']:7.1f}  уровней {r['dark_levels']:3}  "
                      f"{r['kb']:5} КБ  {r['seconds']:5.1f}с")
            else:
                print(f"  {cfg['tag']:20} — не собрался")
    finally:
        pass
    (OUT / "calib.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                                    encoding="utf-8")
    print(f"\n{len(rows)}/{len(GRID)} · картинки в {OUT} — смотреть глазами рядом с числами")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
