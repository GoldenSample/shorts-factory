r"""
SHORTS-FORGE: пайплайн «промпт -> готовый вертикальный ролик».

Тема (одна строка) -> Grok-4.3 кует раскадровку (JSON: сцены = визуал + голос)
   слог начитки = голос Гора (rubrics.VOICE, снят с его твиттера) в системном промпте, после раскадровки линтер
-> media.py video (grok-imagine-video-1.5, 9:16) на каждую сцену
-> media.py tts (русский голос) на каждую сцену
-> ffmpeg: голос поверх клипа (видео крутится под длину озвучки) + склейка
-> итог: <out>/short_<стамп>.mp4

Каналы (см. C:\CLAUD\CHANNELS.md): проза = grok-4.3 через прокси :8645,
медиа = media-forge (OAuth-токен Hermes, ПОДПИСКА, не метеред).

⚠ ПУЛ: видео премиум и СГОРАЕТ (Heavy ~30 видео/сутки, счёт в штуках).
Поэтому DRY по умолчанию: печатает раскадровку и смету, ничего не жжёт.
Боевой прогон только с --go.

Запуск:
  python forge.py "тема ролика"                 # раскадровка, пул не тронут
  python forge.py "тема" --scenes 3 --go        # боевой: 3 клипа + голос + сборка
  python forge.py "тема" --go --no-video        # только голос + статичный фон (пул не жжём)
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
MEDIA_PY = Path(r"C:\CLAUD\projects\media-forge\media.py")
PROXY = "http://127.0.0.1:8645/v1"
MODEL = "grok-4.3"
OUT_DIR = HERE / "out"
WORK_DIR = HERE / "work"

SCENARIO_SYSTEM = """Ты режиссёр коротких вертикальных роликов (Shorts/Reels/Clips).
По теме собери раскадровку на {n} сцен.

ЖЁСТКО: верни ТОЛЬКО валидный JSON без markdown-обёрток, вида
{{"title": "...", "hook": "...", "scenes": [{{"visual": "...", "motion": "...", "voice": "...", "seconds": 6}}]}}

Правила:
- title: заголовок ролика до 60 знаков.
- hook: первая фраза, которая держит зрителя в первые 2 секунды.
- visual: промпт для видеогенератора НА АНГЛИЙСКОМ, кинематографично и конкретно
  (что в кадре, план, свет, движение камеры). Без текста и надписей в кадре.
- voice: закадровый текст сцены НА РУССКОМ голосом Гора (блок ГОЛОС ГОРА), 12-25 слов,
  ровно то, что он произнесёт. Без эмодзи и без markdown.
- motion: КРАТКИЙ промпт движения на английском (как оживает кадр): проезд камеры,
  наезд, лёгкое движение объекта. Без смены сцены.
- seconds: 5-10, целое.
- Сцены связаны одной мыслью: зацепка -> суть -> вывод.
- Не выдумывай фактов, которых нет в теме."""


def log(msg: str):
    print(f"  {msg}", flush=True)


def plan(topic: str, n: int, mv: dict | None = None) -> dict:
    """Раскадровка через Grok-4.3 (прокси 8645). Возвращает dict сценария. mv = ходы ролика (rubrics.assign_moves)."""
    import rubrics as RB
    # Голос Гора в системном промпте для любой темы; мосты (from_techpulse, from_bot, case) кладут его в тему сами, дважды не даём.
    system = SCENARIO_SYSTEM.format(n=n) + ("" if "ГОЛОС ГОРА" in topic else "\n\n" + RB.voice_block())
    # Ходы ролика (аудит 22.11): мосты кладут блок ХОДЫ в тему сами (prompt_block), голой теме он идёт сюда.
    if mv and "ХОДЫ:" not in topic:
        system += "\n\n" + RB.moves_block(mv)
    with httpx.Client(timeout=180.0) as c:
        r = c.post(
            f"{PROXY}/chat/completions",
            headers={"Authorization": "Bearer local", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Тема ролика: {topic}"},
                ],
            },
        )
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"].strip()

    # снимаем markdown-обёртку, если модель всё же обернула
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
    m = re.search(r"\{.*\}", raw, flags=re.S)
    if not m:
        raise SystemExit(f"FAIL: раскадровка не JSON:\n{raw[:400]}")
    data = json.loads(m.group(0))
    if not data.get("scenes"):
        raise SystemExit("FAIL: в раскадровке нет сцен")
    return data


def media(args: list[str], timeout: int = 1500, want_ext: str = "") -> tuple[bool, str]:
    """Вызов media.py. Возвращает (успех, путь к файлу нужного типа или лог).

    shot печатает ДВА пути (кадр .jpg, затем видео .mp4): берём последний
    подходящий по расширению, иначе подхватывается картинка вместо ролика."""
    proc = subprocess.run(
        [sys.executable, str(MEDIA_PY), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    hits = re.findall(r"OK \S+ -> (.+?) \(", out)
    if want_ext:
        hits = [h for h in hits if h.lower().endswith(want_ext)]
    return (bool(hits), hits[-1] if hits else out.strip()[-300:])


def ffprobe_dur(path: Path) -> float:
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float((p.stdout or "0").strip())
    except ValueError:
        return 0.0


def build_scene(clip: Path, voice: Path, dest: Path, seamless: bool = True,
                min_sec: float = 0.0) -> bool:
    """Голос поверх клипа; длина сцены = max(озвучка + пауза, min_sec).

    ⚠ ПОЧЕМУ НЕ ПРОСТО -shortest ПО ГОЛОСУ (замер 30-07): грок-TTS читает
    быстро: 4.3 с на фразу при клипе 7-9 с, и ролик из 11 сцен вышел 53 с
    вместо заказанных 85. Плюс встык, без воздуха между репликами, шортс
    читается как скороговорка. Теперь сцена держит заданную длину, а голос
    ложится в начало и добивается тишиной.

    ⚑ Клип сначала ЗАМЫКАЕТСЯ БЕСШОВНО (seamless.py), иначе на каждом обороте виден
    скачок. Замер на живом грок-футаже: тупая петля даёт стык в 24 раза грубее обычного
    межкадрового хода, и на 24-секундной сцене это два видимых рывка ровно на границах
    повтора. После замыкания ноль скачков, максимум x1.7.
    """
    src = clip
    if seamless:
        try:
            from seamless import make_loop
            looped = clip.with_name(clip.stem + "_seam.mp4")
            rep = make_loop(clip, looped, mode="auto", verbose=False)
            if looped.exists() and rep.get("chosen"):
                src = looped
        except Exception:
            pass          # замыкание не удалось: крутим как есть, сцену не теряем
    dur = max(ffprobe_dur(voice) + 0.45, min_sec)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-stream_loop", "-1", "-i", str(src),
        "-i", str(voice),
        "-map", "0:v:0", "-map", "1:a:0",
        "-t", f"{dur:.3f}",
        "-af", "apad",                       # добить тишиной до длины сцены
        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
        str(dest),
    ]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def build_still(voice: Path, dest: Path, color: str = "black") -> bool:
    """Без видео-пула: статичный фон под озвучку (для дешёвых прогонов)."""
    dur = max(1.0, ffprobe_dur(voice))
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c={color}:s=1080x1920:r=30:d={dur:.2f}",
        "-i", str(voice),
        "-map", "0:v:0", "-map", "1:a:0", "-shortest",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
        str(dest),
    ]
    return subprocess.run(cmd, capture_output=True).returncode == 0


KB_W, KB_H, KB_FPS, KB_ZOOM = 1080, 1920, 30, 0.25     # кадр, частота и потолок наезда Кена Бёрнса
KB_RATE = 0.02                                          # наезд за секунду (05_motion.md: 1.5-3 %/с), как в investor_reel
_KB_BACKEND: str | None = None                          # кэш: "placebo" | "zoompan", один раз на процесс


def _placebo_ok() -> bool:
    """Есть ли libplacebo в сборке ffmpeg И поднимается ли Vulkan: пробный рендер 2 кадров из lavfi."""
    try:
        f = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True,
                           errors="replace", timeout=30)
        if "libplacebo" not in (f.stdout or ""):
            return False
        probe = subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-init_hw_device", "vulkan=vk", "-filter_hw_device", "vk",
            "-f", "lavfi", "-i", "color=c=gray:s=64x64:r=30", "-frames:v", "2",
            "-vf", "format=rgba,hwupload,libplacebo=w=32:h=32:format=yuv420p,hwdownload,format=yuv420p",
            "-f", "null", "-",
        ], capture_output=True, timeout=60)
        return probe.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def kenburns_backend() -> str:
    """Путь Кена Бёрнса: FORGE_KB=placebo|zoompan принудительно, иначе автоопределение (кэш на процесс)."""
    global _KB_BACKEND
    forced = os.environ.get("FORGE_KB", "").strip().lower()
    if forced in ("placebo", "zoompan"):
        return forced
    if _KB_BACKEND is None:
        _KB_BACKEND = "placebo" if _placebo_ok() else "zoompan"
    return _KB_BACKEND


def kenburns_vf(backend: str, frames: int, zoom_in: bool, zoom: float = KB_ZOOM) -> str:
    """Строка фильтра: наезд 1.0 -> 1+zoom (или отъезд) ровно за frames кадров, центр кадра на месте.

    placebo: кроп по float на GPU (visual-fx.md), ни одного замороженного кадра.
    zoompan: кроп округляется до целого пикселя, поэтому сначала scale 4x по ширине выхода
    (lanczos), иначе на медленном движении кадры стоят и дёргаются (замер visual-fx.md:7-40)."""
    zs = f"{zoom:g}"
    if backend == "placebo":
        k = f"(1+{zs}*n/{frames})" if zoom_in else f"(1+{zs}-{zs}*n/{frames})"
        return (
            f"format=rgba,hwupload,libplacebo=w={KB_W}:h={KB_H}"
            f":crop_w='iw/{k}':crop_h='ih/{k}':crop_x='(iw-cw)/2':crop_y='(ih-ch)/2'"
            f":upscaler=ewa_lanczos:format=yuv420p,hwdownload,format=yuv420p,setsar=1"
        )
    z = (f"min(1+{zs},1+{zs}*on/{frames})" if zoom_in
         else f"max(1,1+{zs}-{zs}*on/{frames})")
    return (
        f"scale={KB_W * 4}:-2:flags=lanczos,zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)'"
        f":y='ih/2-(ih/zoom/2)':s={KB_W}x{KB_H}:fps={KB_FPS},setsar=1"
    )


def _kenburns_cmd(backend: str, image: Path, voice: Path, dest: Path, dur: float, zoom_in: bool) -> list[str]:
    frames = max(1, int(dur * KB_FPS))
    zoom = min(KB_ZOOM, round(KB_RATE * dur, 4))      # 2 %/с, потолок 1.25 (от 12.5 с озвучки)
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if backend == "placebo":
        cmd += ["-init_hw_device", "vulkan=vk", "-filter_hw_device", "vk",
                "-loop", "1", "-framerate", str(KB_FPS), "-t", f"{dur:.2f}", "-i", str(image)]
    else:
        cmd += ["-loop", "1", "-i", str(image)]
    cmd += [
        "-i", str(voice), "-map", "0:v:0", "-map", "1:a:0", "-shortest",
        "-vf", kenburns_vf(backend, frames, zoom_in, zoom), "-t", f"{dur:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", str(dest),
    ]
    return cmd


def build_kenburns(image: Path, voice: Path, dest: Path, zoom_in: bool = True) -> bool:
    """Оживление СТАТИЧНОГО кадра (скриншот продукта) под длину озвучки.

    Генератив рисует «похожее», а не твой продукт, поэтому для презентаций
    визуал = реальные кадры + медленный наезд/отъезд (эффект Кена Бёрнса).
    Наезд 2 %/с за всю озвучку (0.06 за 3 с, потолок 1.25). Путь: libplacebo (Vulkan), без него
    scale 4x -> zoompan (на CPU примерно вдвое дольше старого голого zoompan, цена lanczos 4x);
    FORGE_KB=placebo|zoompan выбирает путь принудительно (тогда запасного нет)."""
    dur = max(1.0, ffprobe_dur(voice))
    backend = kenburns_backend()
    forced = backend if os.environ.get("FORGE_KB", "").strip().lower() == backend else ""
    label = {"placebo": "libplacebo (Vulkan)", "zoompan": "scale 4x -> zoompan"}[backend]
    log(f"кен бёрнс: {label}" + (" [FORGE_KB]" if forced else ""))
    proc = subprocess.run(_kenburns_cmd(backend, image, voice, dest, dur, zoom_in), capture_output=True)
    if proc.returncode != 0 and backend == "placebo" and not forced:
        err = [s for s in proc.stderr.decode("utf-8", errors="replace").splitlines() if s.strip()]
        log("кен бёрнс: libplacebo упал, запасной путь scale 4x -> zoompan" + (f" ({err[-1].strip()})" if err else ""))
        proc = subprocess.run(_kenburns_cmd("zoompan", image, voice, dest, dur, zoom_in), capture_output=True)
    return proc.returncode == 0


def srt_time(t: float) -> str:
    h, r = divmod(t, 3600)
    m, sec = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{sec:06.3f}".replace(".", ",")


def burn_subs(video: Path, lines: list[tuple[float, float, str]], dest: Path) -> bool:
    """Вжечь субтитры: ролики смотрят без звука, текст обязан быть в кадре."""
    srt = WORK_DIR / "subs.srt"
    blocks = []
    for i, (a, b, txt) in enumerate(lines, 1):
        blocks.append(str(i))
        blocks.append(f"{srt_time(a)} --> {srt_time(b)}")
        blocks.append(txt)
        blocks.append("")
    srt.write_text("\n".join(blocks), encoding="utf-8")

    style = (
        "FontName=Arial,FontSize=13,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=140"
    )
    esc = srt.as_posix().replace(":", "\\:")
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(video),
        "-vf", f"subtitles='{esc}':force_style='{style}'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
        "-c:a", "copy", str(dest),
    ]
    return subprocess.run(cmd, capture_output=True).returncode == 0

def concat(parts: list[Path], dest: Path) -> bool:
    lst = WORK_DIR / "concat.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
           "-i", str(lst), "-c", "copy", str(dest)]
    if subprocess.run(cmd, capture_output=True).returncode == 0:
        return True
    # разные параметры потоков -> пересобрать с перекодировкой
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", str(dest)]
    return subprocess.run(cmd, capture_output=True).returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Промпт -> вертикальный ролик")
    ap.add_argument("topic", help="тема ролика")
    ap.add_argument("--voice", default="sal",
                    help="голос грок-TTS: default|ara|rex|eve|leo|sal (проба 30-07: sal взрослый)")
    ap.add_argument("--scenes", type=int, default=3, help="сколько сцен (деф 3)")
    ap.add_argument("--go", action="store_true", help="боевой прогон (жжёт пул), иначе только раскадровка")
    ap.add_argument("--no-video", action="store_true", help="без видео-пула: голос на статичном фоне")
    ap.add_argument("--resolution", default="720p", choices=["480p", "540p", "720p", "1080p"])
    ap.add_argument("--shots", help="папка с РЕАЛЬНЫМИ кадрами (png/jpg): визуал = продукт, не генератив")
    ap.add_argument("--subs", action="store_true", help="вжечь субтитры (ролики смотрят без звука)")
    ap.add_argument("--out", help="итоговый файл")
    ap.add_argument("--strict", action="store_true", help="не собирать, если линтер слога нашёл проблемы")
    a = ap.parse_args()

    if not MEDIA_PY.is_file():
        return print(f"FAIL: нет {MEDIA_PY}") or 1
    if not shutil.which("ffmpeg"):
        return print("FAIL: ffmpeg не на PATH") or 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n=== РАСКАДРОВКА (grok-4.3): {a.topic}", flush=True)
    import hashlib
    import rubrics as RB
    # ХОДЫ РОЛИКА (аудит 22.11): назначение из темы моста или по журналу канала для голой темы; id от темы, перегенерация не плодит строк.
    roll_id = f"forge:{hashlib.sha1(a.topic.encode('utf-8')).hexdigest()[:10]}"
    mv = RB.parse_moves(a.topic) or RB.assign_moves(roll_id, "новости")
    mv["id"] = mv.get("id") or roll_id
    sc = plan(a.topic, a.scenes, mv)
    sc["moves"] = mv
    scenes = sc["scenes"][: a.scenes]
    print(f"  title: {sc.get('title', '-')}")
    print(f"  hook:  {sc.get('hook', '-')}")
    for i, s in enumerate(scenes, 1):
        print(f"  [{i}] {s.get('seconds', 6)}с | визуал: {s['visual'][:70]}")
        print(f"      голос: {s['voice'][:70]}")

    # ЛИНТЕР СЛОГА (rubrics.py): штампы пересказа, эмодзи, нет цифры в зацепке, нет вердикта, перебор слов;
    # голос Гора: мат, чат-маркеры, «вы» вместо «ты», ритм без ударов или метроном.
    # Рубрику кузница узнаёт по строке «РУБРИКА: ключ» в теме (её ставят from_techpulse.py и rubrics.py case).
    import rubrics as RB
    m_rub = re.search(r"РУБРИКА:\s*(\w+)", a.topic)
    sc["lint"] = RB.lint(sc, m_rub.group(1) if m_rub else None, moves=mv)
    if sc["lint"]:
        print("  СЛОГ:")
        for pr in sc["lint"]:
            print(f"    ! {pr}")
    (WORK_DIR / f"plan_{stamp}.json").write_text(
        json.dumps(sc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rb = RB.BY_KEY.get(m_rub.group(1)) if m_rub else None
    if rb and rb.get("real_photos") and a.go and not a.shots:
        print(f"  рубрика «{rb['chip']}» идёт только на НАСТОЯЩИХ фото: нужен --shots ПАПКА. Генерировать железо запрещено.")
        return 1
    if sc["lint"] and a.strict:
        print("  --strict: слог не чист, сборка остановлена (пул не тронут). Перегенерируй раскадровку.")
        return 1
    if a.go:
        # Дверь в сборку: ходы и частоты по журналу канала. Отказ = стоп и без --strict: это замок, а не совет (аудит 22.11).
        try:
            RB.record_moves(mv, " ".join(s.get("voice", "") for s in scenes))
        except RB.MovesRefused as e:
            print(f"  замок ходов: {e}. Перегенерируй раскадровку (пул не тронут).")
            return 1

    if not a.go:
        n_vid = 0 if a.no_video else len(scenes)
        print(f"\n  DRY: пул не тронут. Боевой прогон сожжёт {n_vid} видео + {len(scenes)} озвучек.")
        print(f"  Запуск: python forge.py \"{a.topic}\" --scenes {a.scenes} --go")
        return 0

    shots = sorted([q for q in Path(a.shots).glob('*') if q.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')]) if a.shots else []
    if a.shots and not shots:
        return print(f'FAIL: в {a.shots} нет картинок') or 1
    if shots:
        print(f'  кадров продукта: {len(shots)}')
    parts: list[Path] = []
    sub_lines: list[tuple[float, float, str]] = []
    clock = 0.0
    for i, s in enumerate(scenes, 1):
        print(f"\n=== СЦЕНА {i}/{len(scenes)}", flush=True)
        voice_p = WORK_DIR / f"{stamp}_s{i}_voice.mp3"
        ok, res = media(["tts", s["voice"], "--out", str(voice_p),
                         "--lang", "ru", "--voice", a.voice], want_ext=".mp3")
        if not ok or not voice_p.is_file():
            log(f"голос FAIL: {res}")
            continue
        log(f"голос: {voice_p.name} ({ffprobe_dur(voice_p):.1f}с)")

        scene_out = WORK_DIR / f"{stamp}_s{i}.mp4"
        if shots:
            shot_img = shots[(i - 1) % len(shots)]
            ok_s = build_kenburns(shot_img, voice_p, scene_out, zoom_in=(i % 2 == 1))
            log(f"кадр продукта: {shot_img.name} (наезд камеры)")
        elif a.no_video:
            ok_s = build_still(voice_p, scene_out)
            log("фон: статичный (пул не тронут)")
        else:
            clip_p = WORK_DIR / f"{stamp}_s{i}_clip.mp4"
            # shot = кадр (image-quality) -> оживление (video-1.5 по image_url).
            # Прямой text-to-video модель НЕ поддерживает: API отвечает
            # "Text-to-video is not supported for this model" (замер 07-27).
            ok, res = media([
                "shot", s["visual"], "--out", str(clip_p),
                "--anim", s.get("motion") or "camera slowly pushes in, subtle natural motion",
                "--aspect", "9:16", "--resolution", a.resolution,
                "--duration", str(int(s.get("seconds", 6))),
            ], want_ext=".mp4")
            if not ok or not clip_p.is_file():
                log(f"клип FAIL: {res} -> статичный фон")
                ok_s = build_still(voice_p, scene_out)
            else:
                log(f"клип: {clip_p.name} ({ffprobe_dur(clip_p):.1f}с)")
                ok_s = build_scene(clip_p, voice_p, scene_out,
                               min_sec=float(s.get("seconds", 0) or 0))
        if ok_s and scene_out.is_file():
            d = ffprobe_dur(scene_out)
            sub_lines.append((clock, clock + d, s["voice"]))
            clock += d
            parts.append(scene_out)
            log(f"сцена собрана: {scene_out.name} ({ffprobe_dur(scene_out):.1f}с)")
        else:
            log("сцена FAIL (ffmpeg)")
        time.sleep(1)

    if not parts:
        print("\nВЕРДИКТ: ни одной сцены не собралось")
        return 1

    final = Path(a.out) if a.out else OUT_DIR / f"short_{stamp}.mp4"
    print("\n=== СБОРКА", flush=True)
    if not concat(parts, final):
        print("ВЕРДИКТ: склейка не удалась")
        return 1

    if a.subs and sub_lines:
        subbed = WORK_DIR / f"{stamp}_subbed.mp4"
        if burn_subs(final, sub_lines, subbed):
            shutil.copy2(subbed, final)
            log("субтитры вжжены")
        else:
            log("субтитры не легли (ролик без них)")

    size_mb = final.stat().st_size / 1024 / 1024
    print("\n" + "=" * 46)
    print(f"  сцен собрано: {len(parts)}/{len(scenes)}")
    print(f"  длительность: {ffprobe_dur(final):.1f}с | размер: {size_mb:.1f}МБ | 1080x1920")
    print("=" * 46)
    print(f"ВЕРДИКТ: РОЛИК ГОТОВ -> {final}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
