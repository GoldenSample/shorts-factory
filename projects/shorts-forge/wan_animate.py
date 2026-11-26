# -*- coding: utf-8 -*-
"""Оживление статичных фонов локально: Wan 2.2 TI2V-5B, image-to-video на 5090.

ЗАЧЕМ. Фоны презентации уже отобраны замером (яркость в полосе игры, центр под
текст, vision-контроль) — перегенерировать их видеомоделью значит выбросить этот
отбор. Задача обратная: взять УЖЕ ОДОБРЕННЫЙ кадр и добавить ему жизни —
шевеление тумана, дыхание углей, дрожь ламп — НЕ трогая композицию.

ПОЧЕМУ WAN 2.2, А НЕ LTX ИЛИ HUNYUAN (лицензии весов проверены через HF API):
  · Wan 2.2 TI2V-5B — **apache-2.0**, чисто и для весов, и для выдачи;
  · LTX-2.3 — community-лицензия с порогом выручки, запретом конкуренции и той же
    лицензией НА КОД нод, плюс отдельные условия на текст-энкодер;
  · HunyuanVideo — tencent-community, **не действует в EU/UK/Корее**.
⛔ «Wan 2.5/2.6 с открытыми весами» — вымысел SEO-ферм: потолок официального
репозитория Wan-AI = 2.2.

ГДЕ ЖИВЁТ МОДЕЛЬ. `C:\\Apps\\comfy` — на РЕАЛЬНОМ диске. Раньше ComfyUI лежал в
%LOCALAPPDATA%\\laplace-sandbox, и это была ловушка: путь виртуализуется MSIX-контейнером
Claude, поэтому супервизор (процесс снаружи) видел там пустоту и валился с ENOENT —
именно это выглядело как «ComfyUI опять отвалился».
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
BG = HERE / "reel_bg"
OUT = HERE / "reel_bg_video"
COMFY = Path(r"C:\Apps\comfy\ComfyUI_windows_portable\ComfyUI")
HOST = "http://127.0.0.1:8188"

UNET = "wan2.2_ti2v_5B_fp16.safetensors"
CLIP = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
VAE = "wan2.2_vae.safetensors"

# 1280x704 — родное разрешение шаблона TI2V-5B и ровно наш 16:9 после кропа.
W, H = 1280, 704
LENGTH = 49          # 49 кадров при 24 fps = ~2 с; на петле этого хватает
FPS = 24
STEPS = 20
SHIFT = 8.0

# ⚑ CFG 2.0, А НЕ ШАБЛОННЫЕ 5.0. При 5.0 модель слишком слушает текст и начинает
# ДОРИСОВЫВАТЬ: на месте углей вырастала белая фигура, в воздухе появлялась летящая
# искра. Замер дрейфа (среднее отличие последнего кадра от первого): cfg 5 = 11.55,
# cfg 2 = 1.30. Нам нужен ровно исходный кадр, только дышащий, — значит слушать текст
# надо вполуха.
CFG = 2.0

# ⛔ ГЛАВНАЯ НАХОДКА: WAN НЕ РАБОТАЕТ В ПОЧТИ-ЧЁРНОМ КАДРЕ.
# Наши фоны отобраны под текст и имеют среднюю яркость ~6 из 255 — это вне
# распределения модели, и она заполняет «пустоту» галлюцинациями (первый прогон
# развалил кузницу в цветные блоки, яркость уехала 4.6 → 17.6).
# Лечение: подать кадр с поднятой экспозицией, а результату вернуть исходную.
# Тьма восстанавливается ровно та же, а модель всё это время видела нормальный кадр.
LIFT = "eq=brightness=0.10:gamma=1.75:saturation=1.05"


# ⛔ НЕГАТИВ ОБЯЗАТЕЛЕН И ОБЯЗАН БЫТЬ ПЕРЕПИСАН ПОД НАШУ ЗАДАЧУ.
# Первый прогон шёл с ПУСТЫМ негативом при cfg 5 — к 49-му кадру сцена разваливалась
# в цветные блоки (замер: яркость 4.6 → 17.6, кузница превращалась в мусор).
# ⚠ Но и штатный негатив Wan копировать нельзя: в нём стоят 静态 («статично») и
# 静止不动的画面 («неподвижная картинка») как НЕЖЕЛАТЕЛЬНЫЕ — он заточен под ролики
# с движением и будет разгонять камеру, тогда как нам нужна почти неподвижность.
# Поэтому берём из него только артефакты качества, а «статику» из запретов убираем
# и, наоборот, запрещаем движение камеры и перекомпоновку.
NEG = ("过曝，色调艳丽，细节模糊不清，最差质量，低质量，JPEG压缩残留，丑陋的，畸形的，"
       "毁容的，杂乱的背景，字幕，文字，水印，"
       "camera pan, camera zoom, camera movement, scene change, cut to another shot, "
       "morphing shapes, warping geometry, flickering blocks, colour blocks, "
       "new objects appearing, brightening exposure, washed out")

# ⚑ Позитив описывает И СЦЕНУ, И ДВИЖЕНИЕ. Первая версия описывала только движение —
# без опоры на содержание модель к концу клипа теряла, что вообще изображено.
# Сцена задаётся коротко (кадр и так подан картинкой), движение — конкретным
# перечнем того, что именно шевелится.
# ⚠ Ни одного СОБЫТИЯ и ни одного ОБЪЕКТА в промпте. Формулировки вида «поднимается
# дым», «мерцают угли», «летят искры» модель понимает как задание что-то нарисовать —
# и рисует: так в кадре появилась белая фигура на месте углей и летящее лезвие.
# Работает только описание НЕИЗМЕННОСТИ плюс «дыхание» света как единственная перемена.
STILL = ("unchanged framing, locked camera. Nothing in the scene moves at all. "
         "The only change is the faintest breathing of the light and a barely "
         "visible haze in the air.")
MOTION = {
    "01_problem": "A dim night field with dark silhouettes along the bottom edge, " + STILL,
    "02_built":   "A dim stone forge chamber with an anvil and a low bed of coals, " + STILL,
    "03_rules":   "A dim hall with tall stone slabs and one narrow cold beam, " + STILL,
    "04_swarm":   "A dim vast workshop hall seen from high above with small scattered "
                  "lamps on the floor, " + STILL,
    "05_market":  "A dim windswept moor at last light with bare wooden posts, " + STILL,
}


def graph(image_name: str, prompt: str, seed: int) -> dict:
    """Граф i2v по шаблону video_wan2_2_5B_ti2v, собранный вручную.

    ⚠ Wan22ImageToVideoLatent, а не WanImageToVideo: у TI2V-5B кадр заходит через
    латент, а не через conditioning. Перепутать легко — ноды называются почти одинаково.
    """
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": CLIP, "type": "wan", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "4": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": NEG}},
        "7": {"class_type": "Wan22ImageToVideoLatent",
              "inputs": {"vae": ["3", 0], "width": W, "height": H, "length": LENGTH,
                         "batch_size": 1, "start_image": ["4", 0]}},
        "8": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": SHIFT}},
        "9": {"class_type": "KSampler",
              "inputs": {"model": ["8", 0], "positive": ["5", 0], "negative": ["6", 0],
                         "latent_image": ["7", 0], "seed": seed, "steps": STEPS,
                         "cfg": CFG, "sampler_name": "uni_pc", "scheduler": "simple",
                         "denoise": 1.0}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
        "11": {"class_type": "CreateVideo", "inputs": {"images": ["10", 0], "fps": FPS}},
        "12": {"class_type": "SaveVideo",
               "inputs": {"video": ["11", 0], "filename_prefix": "wanbg/bg",
                          "format": "auto", "codec": "auto"}},
    }


def luma(path: Path, vf: str = "") -> float:
    """Средняя яркость по всему файлу на уменьшённой копии — дёшево и достаточно."""
    chain = (vf + "," if vf else "") + "scale=320:-2,format=gray"
    r = subprocess.run(["ffmpeg", "-v", "error", "-threads", "1", "-i", str(path),
                        "-vf", chain, "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                       capture_output=True)
    if not r.stdout:
        return -1.0
    import array
    a = array.array("B", r.stdout)
    return sum(a) / len(a)


def match_exposure(src_video: Path, target: float, dest: Path) -> bool:
    """Вернуть клипу яркость исходного кадра, подобрав гамму бинарным поиском.

    ⚑ Фиксированный обратный фильтр не годится: `eq` применяет гамму и яркость
    одной операцией, поэтому точного обращения LIFT нет, и разные сцены уезжают
    по-разному (замер: 6.1 → 1.7 на одной и 22.2 → 15.2 на другой — фон исчезал).
    Подбор занимает пять коротких проходов по уменьшенной копии и решает это точно.
    """
    lo, hi, best = 0.30, 1.20, None
    for _ in range(7):
        mid = (lo + hi) / 2
        got = luma(src_video, f"eq=gamma={mid:.4f}")
        if got < 0:
            return False
        best = mid
        if abs(got - target) < 0.3:
            break
        if got < target:
            lo = mid
        else:
            hi = mid
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src_video),
                        "-vf", f"eq=gamma={best:.4f}", "-c:v", "libx264", "-crf", "16",
                        "-preset", "medium", "-pix_fmt", "yuv420p", str(dest)],
                       capture_output=True)
    return r.returncode == 0 and dest.exists()


def run_one(png: Path, prompt: str, seed: int, dest: Path) -> bool:
    # вход осветляем (см. LIFT): модель должна видеть нормальный кадр, а не чёрный лист
    staged = COMFY / "input" / f"_lift_{png.stem}.png"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(png),
                    "-vf", f"scale={W}:{H},{LIFT}", "-frames:v", "1",
                    "-update", "1", str(staged)], capture_output=True)
    if not staged.exists():
        print("   не удалось подготовить кадр")
        return False
    try:
        r = requests.post(f"{HOST}/prompt", json={"prompt": graph(staged.name, prompt, seed)},
                          timeout=120)
    except Exception as e:
        print("   не отправилось:", str(e)[:200])
        return False
    if not r.ok:
        print("   отказ графа:", r.text[:500])
        return False
    pid = r.json()["prompt_id"]

    t0 = time.time()
    for _ in range(1800):                        # первый прогон грузит модель — минуты
        time.sleep(2)
        try:
            hist = requests.get(f"{HOST}/history/{pid}", timeout=30).json()
        except Exception:
            continue
        if pid not in hist:
            continue
        st = hist[pid].get("status", {})
        outs = hist[pid].get("outputs", {})
        vids = [v for o in outs.values() for v in (o.get("images", []) + o.get("videos", []))]
        if vids:
            src = COMFY / "output" / vids[0].get("subfolder", "") / vids[0]["filename"]
            for _ in range(40):
                if src.exists() and src.stat().st_size > 50000:
                    # возвращаем ровно ту тьму, что была у исходного кадра
                    target = luma(png)
                    if not match_exposure(src, target, dest):
                        return False
                    print(f"   яркость: цель {target:.1f} · вышло {luma(dest):.1f}", end="")
                    print(f"   {time.time()-t0:5.0f}с · {dest.stat().st_size/1e6:.1f} МБ")
                    return True
                time.sleep(0.5)
        if st.get("status_str") == "error":
            for m in st.get("messages", []):
                if m and m[0] == "execution_error":
                    print("   ошибка:", json.dumps(m[1], ensure_ascii=False)[:400])
                    return False
            print("   ошибка графа:", str(st)[:300])
            return False
    print("   таймаут")
    return False


def main() -> int:
    OUT.mkdir(exist_ok=True)
    only = sys.argv[1] if len(sys.argv) > 1 else None
    ok = 0
    for i, (name, motion) in enumerate(MOTION.items(), 1):
        if only and only not in name:
            continue
        png = BG / f"{name}.png"
        if not png.exists():
            print(f"  {name}: нет исходника")
            continue
        dest = OUT / f"{name}.mp4"
        if dest.exists():
            print(f"  {name}: уже есть")
            ok += 1
            continue
        print(f"  {name}")
        if run_one(png, motion, seed=4200 + i, dest=dest):
            ok += 1
    print(f"\nготово: {ok}/{len(MOTION)} · {OUT}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
