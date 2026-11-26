# -*- coding: utf-8 -*-
"""ШОРТС 2.0: новость → вертикаль 1080x1920 БЕЗ видеогенерации.

Урок первого прогона (разнос Гора 09-08, все четыре пункта закрыты здесь):
  «паузы в речи»  → сцена = длина голоса + 0.4 с, хронометраж набирается
                    ПЛОТНЫМ текстом (25-28 слов/сцену), а не тишиной;
  «тупой слог»    → начитка пишется в сценарии руками/грок-проходом под
                    разговорный слог, сборщик текст НЕ сочиняет;
  «уилл смит ест спагетти» → генератива НЕТ. Кадры = реальные скриншоты
                    первоисточников (headless-Chrome) + плашки-телеметрия
                    нашей типографикой. Закон скила: продукт артефактами;
  «поля»          → всё собирается в чистом 1080x1920 с самого начала.

Плюс то, чего в forge не было вовсе: ВШИТЫЕ СУБТИТРЫ (шортсы смотрят без
звука): ASS с гало-слоем, safe-зоны вертикали (низ 320px под UI площадок).

Сцены двух типов:
  shot:  скриншот (файл), по умолчанию статичен (текст внутри картинки),
          Ken Burns только по явному kenburns=True + субтитры;
  panel: тёмная плашка с заголовком и рядами «показатель | число»
          (телеметрия из докладов, вертикальная версия) + субтитры.
          Карточка рендерится двумя слоями: фон (сетка) под медленным Ken Burns
          2 %/с и текст с альфой, который стоит намертво и проявляется за 0.42 с.

Голос: грок-TTS sal (выбор Гора). Финал кодируется ЗДЕСЬ soло, никаких
параллельных тяжёлых процессов рядом (закон битых NAL).
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, r"C:\CLAUD\projects\media-forge")

WORK = HERE / "work_short2"
OUT = HERE / "out"
CHROME_WIN = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
W, H, FPS = 1080, 1920, 30
VOICE = "sal"


def find_chrome() -> Path | None:
    """Chrome: переменная GS_CHROME, затем прежний путь Windows, Chromium Playwright в контейнере, chromium/google-chrome в PATH."""
    cands = [os.environ.get("GS_CHROME", ""), str(CHROME_WIN)]
    cands += sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome"), reverse=True)
    for c in cands:
        if c and Path(c).is_file():
            return Path(c)
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"):
        w = shutil.which(name)
        if w:
            return Path(w)
    return None


CHROME = find_chrome()

# ⛔ Закон Гора 20.09.2026: «палитра и шрифт дефолт клод запрещены». Прежняя «BR2049» (тёплый чёрный, крем, янтарь, засечки,
# моноширинные подписи с ромбиком) снята со ВСЕХ сборок. Айдентика живёт в style_lab.py: Tektur + Jost (выбор Гора 21.09), холодная гамма.
import style_lab as SL
C_BG, C_TEXT, C_ACCENT, C_MUTED, C_LINE = SL.BG, SL.TEXT, SL.ICE, SL.MUTED, SL.LINE
CSS = SL.css(W, H)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, **kw)


def ffdur(p: Path) -> float:
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(p)])
    try:
        return float(r.stdout.decode().strip())
    except ValueError:
        return 0.0


def tts(text: str, dest: Path) -> bool:
    """Грок-TTS напрямую (media-forge call), голос sal, обработка как всюду."""
    if dest.exists():
        return True
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "mf", r"C:\CLAUD\projects\media-forge\media.py")
    mf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mf)
    raw = dest.with_suffix(".raw.mp3")
    try:
        raw.write_bytes(mf.call("/v1/tts", {"text": text, "voice": VOICE,
                                            "language": "ru"}))
    except Exception as e:
        print("   tts:", str(e)[:160])
        return False
    run(["ffmpeg", "-y", "-v", "error", "-i", str(raw),
         "-af", "highpass=f=85,acompressor=threshold=-20dB:ratio=3:attack=12:release=200,"
                "loudnorm=I=-15:TP=-1.5:LRA=11",
         "-ar", "48000", "-c:a", "libmp3lame", "-b:a", "192k", str(dest)])
    raw.unlink(missing_ok=True)
    return dest.exists()


def ass_for(sub: str, seconds: float, path: Path) -> Path:
    """Вшитые сабы: центр нижней трети, над safe-зоной UI площадок (низ 320px)."""
    head = f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Halo,Segoe UI Black,64,&H00000000,&H00000000,&H00000000,&H00000000,-1,0,0,0,100,100,0.4,0,1,22,0,2,70,70,360,204
Style: Main,Segoe UI Black,64,&H00FFFFFF,&H00202020,&H00000000,&HA0000000,-1,0,0,0,100,100,0.4,0,1,5,2,2,70,70,360,204

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    end = f"0:{int(seconds)//60:02d}:{seconds % 60:06.3f}"
    body = (f"Dialogue: 0,0:00:00.00,{end},Halo,,0,0,0,,"
            f"{{\\blur14\\1a&HFF&\\3a&H28&}}{sub}\n"
            f"Dialogue: 1,0:00:00.00,{end},Main,,0,0,0,,{{\\fad(160,160)}}{sub}\n")
    path.write_text(head + body, encoding="utf-8")
    return path


def chrome_shot(page: Path, png: Path, alpha: bool = False) -> Path:
    """Снимок страницы headless-Chrome в 1080x1920. alpha: прозрачное окно, слой кладётся поверх фона."""
    if CHROME is None:
        raise RuntimeError("Chrome не найден: задайте GS_CHROME или поставьте chromium в PATH")
    cmd = [str(CHROME), "--headless=new", "--disable-gpu", "--hide-scrollbars"]
    if sys.platform != "win32":
        cmd.append("--no-sandbox")          # контейнер без user namespaces, иначе Chrome не стартует
    if alpha:
        cmd.append("--default-background-color=00000000")
    cmd += [f"--window-size={W},{H}", "--force-device-scale-factor=1",
            "--virtual-time-budget=3000", f"--screenshot={png}", page.resolve().as_uri()]
    r = run(cmd)
    if not png.exists():
        print("   chrome:", r.stderr.decode("utf-8", "replace")[-300:])
    return png


# Текстовый слой: тот же HTML, но фон и сетка card_css сняты, окно Chrome прозрачное. Без правки gs_style.
TXT_CSS = "html,body{background:transparent !important;background-image:none !important}"
_BG_FRESH: set = set()


def render_bg() -> Path:
    """Фон карточки без текста (заливка и сетка из card_css), один на прогон: его и двигает Ken Burns."""
    png = WORK / "card_bg.png"
    if png not in _BG_FRESH:
        page = WORK / "card_bg.html"
        page.write_text(f"<!doctype html><meta charset=utf-8><style>{CSS}</style><body>", encoding="utf-8")
        chrome_shot(page, png)
        _BG_FRESH.add(png)
    return png


def render_card(tag: str, html: str) -> Path:
    """Карточка тремя PNG: {tag}.png цельная (как прежде, её и возвращаем), {tag}_bg.png фон без текста,
    {tag}_txt.png текст с альфой. build_scene по соседям _bg/_txt узнаёт карточку и двигает только фон."""
    head = f"<!doctype html><meta charset=utf-8><style>{CSS}"
    page = WORK / f"{tag}.html"
    png = WORK / f"{tag}.png"
    page.write_text(f"{head}</style><div class=s>{html}</div>", encoding="utf-8")
    chrome_shot(page, png)
    tpage = WORK / f"{tag}_txt.html"
    tpage.write_text(f"{head}{TXT_CSS}</style><div class=s>{html}</div>", encoding="utf-8")
    chrome_shot(tpage, WORK / f"{tag}_txt.png", alpha=True)
    shutil.copyfile(render_bg(), WORK / f"{tag}_bg.png")
    return png


def layers_of(img) -> tuple[Path, Path | None]:
    """Пара (фон, текст), или {tag}.png с соседями {tag}_bg.png и {tag}_txt.png от render_card; иначе одиночный кадр."""
    if isinstance(img, (tuple, list)):
        return Path(img[0]), Path(img[1])
    img = Path(img)
    bg, txt = img.with_name(img.stem + "_bg.png"), img.with_name(img.stem + "_txt.png")
    if bg.exists() and txt.exists():
        return bg, txt
    return img, None


def render_panel(tag: str, kick: str, title: str, rows: list) -> Path:
    """rows: [(label, value, note?, quiet?)]: телеметрия вертикали."""
    body = ""
    for r in rows:
        lab, num = r[0], r[1]
        note = r[2] if len(r) > 2 else ""
        quiet = (" q" if len(r) > 3 and r[3] else "") + (" win" if len(r) > 4 and r[4] else "")
        body += (f'<div class="row{quiet}"><span class=lab>{lab}'
                 + (f'<small>{note}</small>' if note else "")
                 + f'</span><span class=num>{num}</span></div>')
    html = (SL.kick_html(kick) +
            f'<div class=tel><div class=hdr><span>{title}</span></div>{body}</div>')
    return render_card(tag, html)


def build_scene(tag: str, img, voice_p: Path, sub: str,
                kenburns: bool | None = None) -> Path | None:
    """Кадр + голос + сабы. Длина = голос + 0.4 с.

    Карточка: пара (фон, текст) или {tag}.png с соседями _bg/_txt от render_card. Ken Burns только на фон,
    текстовый слой стоит и проявляется по альфе за 0.42 с. Одиночный PNG (скриншот первоисточника): текст
    внутри картинки, по умолчанию не двигается (05_motion 4.3: скриншот интерфейса не двигать); kenburns=True
    включает наезд явно, kenburns=False гасит его и у карточки.
    """
    bg, txt = layers_of(img)
    if kenburns is None:
        kenburns = txt is not None
    d = max(2.2, ffdur(voice_p) + 0.4)
    dest = WORK / f"{tag}.mp4"
    ass = ass_for(sub, d, WORK / f"{tag}.ass")
    ass_esc = str(ass).replace("\\", "/").replace(":", r"\:")
    # фон: заполнить вертикаль (increase+crop сверху: шапка сайта важнее),
    # медленный наезд 2%/с строго в границах кадра
    z = f"1+{min(0.16, 0.02 * d):.3f}*t/{d:.2f}" if kenburns else "1"
    vf = (f"[0:v]scale={W * 2}:-2,crop={W * 2}:{H * 2}:'(iw-ow)/2':'min(ih-oh,ih*0.06)',"
          f"scale=w='iw*({z})':h='ih*({z})':eval=frame,"
          f"crop=w={W * 2}:h={H * 2}:x='(iw-ow)/2':y='(ih-oh)/2',scale={W}:{H},"
          f"format=yuv420p,setsar=1[bg];")
    inputs = ["-loop", "1", "-framerate", str(FPS), "-t", f"{d:.3f}", "-i", str(bg)]
    if txt is not None:
        # текст проявляется мягко и не двигается вместе с фоном
        inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{d:.3f}", "-i", str(txt)]
        vf += (f"[1:v]format=rgba,fade=t=in:st=0:d=0.42:alpha=1[txt];"
               f"[bg][txt]overlay=0:0:format=auto,format=yuv420p,setsar=1,subtitles='{ass_esc}'[v]")
    else:
        vf += f"[bg]subtitles='{ass_esc}'[v]"
    a_idx = 2 if txt is not None else 1
    r = run(["ffmpeg", "-y", "-v", "error", "-threads", "2", *inputs,
             "-i", str(voice_p),
             "-filter_complex", vf, "-map", "[v]", "-map", f"{a_idx}:a:0",
             "-t", f"{d:.3f}", "-af", "apad",
             "-r", str(FPS),
             "-c:v", "libx264", "-preset", "medium", "-crf", "17",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             str(dest)])
    if r.returncode != 0:
        print(f"   {tag}:", r.stderr.decode("utf-8", "replace")[-220:])
        return None
    return dest


def assemble(scenes: list, final_name: str) -> Path | None:
    lst = WORK / "all.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in scenes), encoding="utf-8")
    final = OUT / final_name
    r = run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
             "-i", str(lst),
             "-vf", "noise=alls=3:allf=u,format=yuv420p",
             "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
             "-c:v", "libx264", "-preset", "medium", "-crf", "19",
             "-pix_fmt", "yuv420p", "-color_range", "tv",
             "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(final)], cwd=WORK)
    if r.returncode != 0:
        print("сборка:", r.stderr.decode("utf-8", "replace")[-250:])
        return None
    chk = run(["ffmpeg", "-v", "error", "-i", str(final), "-f", "null", "-"])
    errs = len(chk.stderr.decode().splitlines())
    print(f"ГОТОВО: {final} · {ffdur(final):.1f}с · декод-ошибок {errs}")
    return final if errs == 0 else None


def render_quote(tag: str, kick: str, quote: str, src: str) -> Path:
    """Цитата первоисточника честной плашкой: НЕ имитация интерфейса, а цитата
    с подписью источника (Reddit/форумы режут headless, подделывать нельзя)."""
    html = (SL.kick_html(kick) +
            f'<div class=mid><div class=st style="font-size:{SL.GS.TYPE_1080['quote']}px">«{quote}»</div>'
            f'<div class=src>{src}</div></div>')
    return render_card(tag, html)


def render_statement(tag: str, kick: str, html_text: str) -> Path:
    """Утверждение: ярлык и одна мысль крупно."""
    return render_card(tag, SL.kick_html(kick) + f"<div class=mid><div class=st>{html_text}</div></div>")
