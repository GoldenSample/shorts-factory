# -*- coding: utf-8 -*-
"""Сборка промо-ролика Cognopolis из РЕАЛЬНЫХ кадров игры.

Формат 16:9 (1920x1080) — намеренно, не вертикаль: ролик идёт в ЧАТЫ (телеграм),
где показывают интерфейс и код, а в 9:16 они нечитаемы.

Закон скила: продукт показывается только своими кадрами. Генератива здесь нет —
все кадры сняты headless-браузером с живого сервера.

Раскадровка: skills/cognopolis-promo/assets/storyboard_chat_50s.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots_cognopolis"
WORK = HERE / "work_cog"
OUT = HERE / "out"
MEDIA = Path(r"C:\CLAUD\projects\media-forge\media.py")
W, H, FPS = 1920, 1080, 30

# Сцена = (кадр, кроп в координатах исходника 2560x1720, зум, голос, субтитр)
# Кроп выбран так, чтобы нужная деталь читалась без мыла: кадры сняты в 2x DPI.
SCENES = [
    dict(shot="hi_world.png",    crop=(1150, 880, 625, 415),  zoom="in",
         voice="Это ММО, в которую нельзя играть руками.",
         sub="ММО, в которую НЕЛЬЗЯ играть руками"),
    dict(shot="hi_world.png",    crop=(560, 950, 60, 420),    zoom="out",
         voice="Ты не водишь персонажа. Ты пишешь агента, и он ходит, рубит и дерётся сам.",
         sub="Ты пишешь агента — он живёт за тебя"),
    dict(shot="hi_world.png",    crop=(760, 640, 780, 480),   zoom="in",
         voice="Мир общий. Серые силуэты на карте — это чужие агенты, прямо сейчас.",
         sub="Серые силуэты — ЧУЖИЕ агенты. Сейчас."),
    dict(shot="chk_codex.png",   crop=(2420, 1010, 70, 340),  zoom="in",
         voice="Мир отдаётся каталогом. Агент читает рецепты и время крафта на старте, а не зашивает их в код.",
         sub="Агент читает мир каталогом, а не зашивает его"),
    dict(shot="hi_diag.png",     crop=(900, 570, 55, 1370),   zoom="in",
         voice="А это игра смотрит за твоим агентом. Кулдаун пуст, действий нет — и она говорит: цикл, возможно, завис.",
         sub="Игра ревьюит твоего агента:\\N«цикл, возможно, думает или завис»", sub_top=True),
    # Ратушу с ростером под-токеном не снять (видно только своего жителя), поэтому
    # мультиагентность показываем через то, что доступно и ценнее: хронику шагов агента.
    dict(shot="hi_world.png",    crop=(630, 1090, 1915, 450),  zoom="out",
         voice="Каждый шаг агента виден в хронике: что он сделал и почему. Жителей может быть несколько, у каждого свой токен и свой агент.",
         sub="Виден каждый шаг агента — и его причина"),
    dict(shot="hi_mine.png",     crop=(2400, 1400, 80, 260),  zoom="in",
         voice="Наверху добычу ограничивает время. В Подземье — только твой код.",
         sub="Наверху решает время. Внизу — код."),
    dict(shot="hi_world.png",    crop=(1150, 880, 625, 415),  zoom="out",
         voice="Карта отдаётся без токена. Проверь одной строкой, не регистрируясь.",
         sub="curl kindomklaster.com/map\\Nбез токена — проверь сам"),
]


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, **kw)


def dur(p: Path) -> float:
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(p)])
    try:
        return float(r.stdout.decode().strip())
    except ValueError:
        return 0.0


def tts(text: str, dest: Path) -> bool:
    """Озвучка через media-forge. Текст идёт файлом: кириллица в argv бьётся."""
    r = run([sys.executable, str(MEDIA), "tts", text, "--out", str(dest), "--lang", "ru"])
    if dest.exists() and dest.stat().st_size > 2000:
        return True
    print("   tts:", r.stdout.decode("utf-8", "replace")[-200:], r.stderr.decode("utf-8", "replace")[-200:])
    return False


def ass_for(sub: str, seconds: float, path: Path, top: bool = False) -> Path:
    """Субтитр вжигается всегда: в чатах смотрят беззвучно.

    Гало-слой отдельным событием — на пёстром интерфейсе одной обводки мало
    (замер: сигнал титра 40 против 1.3 у тонкого стиля).
    """
    al = 8 if top else 2   # 8 = верх-центр, 2 = низ-центр
    head = f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Halo,Arial Black,54,&H00000000,&H00000000,&H00000000,&H00000000,-1,0,0,0,100,100,1,0,1,20,0,{al},120,120,70,204
Style: Main,Arial Black,54,&H00FFFFFF,&H00202020,&H00000000,&HA0000000,-1,0,0,0,100,100,1,0,1,5,3,{al},120,120,70,204

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    end = f"0:00:{seconds:06.3f}".replace(".", ".")
    body = (f"Dialogue: 0,0:00:00.00,{end},Halo,,0,0,0,,{{\\blur14\\1a&HFF&\\3a&H30&}}{sub}\n"
            f"Dialogue: 1,0:00:00.00,{end},Main,,0,0,0,,{{\\fad(180,180)}}{sub}\n")
    path.write_text(head + body, encoding="utf-8")
    return path


def build_scene(i: int, sc: dict) -> Path | None:
    voice = WORK / f"v{i}.mp3"
    if not voice.exists() and not tts(sc["voice"], voice):
        return None
    d = max(1.5, dur(voice) + 0.55)          # хвост на дыхание и затухание титра

    # ⚑ Кроп ОТДЕЛЬНОЙ операцией в файл, а не внутри цепочки анимации.
    # Иначе каждый кадр петли декодируется из исходных 2560x1720 (13 МБ в rgb24),
    # и на загруженной машине сборка падает по памяти. После кропа кадр весит втрое меньше.
    cw, ch, cx, cy = sc["crop"]
    src = WORK / f"crop{i}.png"
    if not src.exists():
        r = run(["ffmpeg", "-y", "-v", "error", "-threads", "1", "-i", str(SHOTS / sc["shot"]),
                 "-vf", f"crop={cw}:{ch}:{cx}:{cy},scale='min({W*1.25:.0f},iw)':-2",
                 "-frames:v", "1", "-update", "1", str(src)])
        if r.returncode != 0 or not src.exists():
            print("   crop:", r.stderr.decode("utf-8", "replace")[-200:])
            return None
    cw = ch = cx = cy = None  # дальше работаем с уже обрезанным кадром

    ass = ass_for(sc["sub"], d, WORK / f"s{i}.ass", top=sc.get("sub_top", False))
    ass_esc = str(ass).replace("\\", "/").replace(":", r"\:")
    dest = WORK / f"scene{i}.mp4"

    # ⛔ Кадр НЕ растягивать под 16:9: панели игры узкие и вертикальные, растяжение
    # ломает пропорции и режет содержимое. Контент вписывается целиком по центру
    # в своих пропорциях, а пустота по бокам заполняется размытой подложкой из
    # него же — тогда кадр читается, а рамка не выглядит дырой.
    k = 0.06                                   # лёгкий Ken Burns на переднем плане
    z = (f"1+{k}*t/{d:.2f}" if sc["zoom"] == "in" else f"{1+k}-{k}*t/{d:.2f}")
    vf = (
        f"split=2[bg][fg];"
        # подложка: тот же кадр на весь экран, сильно размыт и притемнён
        f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        f"gblur=sigma=38,eq=brightness=-0.24:saturation=0.75[bgb];"
        # передний план: вписать целиком (fit), с медленным наездом
        f"[fg]scale=w={W}:h={H}:force_original_aspect_ratio=decrease,"
        f"scale=w='iw*({z})':h='ih*({z})':eval=frame,"
        f"crop=w='min(iw,{W})':h='min(ih,{H})':x='(iw-ow)/2':y='(ih-oh)/2'[fgz];"
        f"[bgb][fgz]overlay=x='(W-w)/2':y='(H-h)/2':shortest=1,"
        f"format=yuv420p,setsar=1,subtitles='{ass_esc}'"
    )
    # ⚑ -threads 1 ОБЯЗАТЕЛЕН и стоит до входа: кадр 2560x1720 в rgb24 весит 13 МБ,
    # многопоточный декодер PNG буферизует их пачкой и падает с "Cannot allocate memory",
    # а наружу это выглядит как загадочная ошибка libx264 "Generic error in external library".
    cmd = ["ffmpeg", "-y", "-v", "error", "-threads", "1",
           "-loop", "1", "-framerate", str(FPS), "-t", f"{d:.2f}", "-i", str(src),
           "-i", str(voice), "-map", "0:v:0", "-map", "1:a:0",
           "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-shortest", str(dest)]
    r = run(cmd)
    if r.returncode != 0:
        print("   ffmpeg:", r.stderr.decode("utf-8", "replace")[-300:])
        return None
    return dest


def main() -> int:
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    parts = []
    for i, sc in enumerate(SCENES, 1):
        p = build_scene(i, sc)
        print(f"  сцена {i}/{len(SCENES)}  {dur(p):5.2f}с  {sc['sub'][:46]}" if p
              else f"  сцена {i} — ПРОПУЩЕНА")
        if p:
            parts.append(p)
    if not parts:
        print("нечего собирать")
        return 1

    lst = WORK / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    final = OUT / "cognopolis_promo_chat.mp4"
    # Громкость к -14 LUFS: телеграм не нормализует, а тихий ролик в чате пролистывают
    r = run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
             "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "libx264", "-preset", "medium",
             "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(final)], cwd=WORK)
    if r.returncode != 0:
        print("concat:", r.stderr.decode("utf-8", "replace")[-300:])
        return 1
    print(f"\nГОТОВО: {final}  ·  {dur(final):.1f}с  ·  {final.stat().st_size/1e6:.1f} МБ")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
