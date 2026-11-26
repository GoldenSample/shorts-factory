# -*- coding: utf-8 -*-
"""Видеодоклад ЛАПЛАСА из сданного контекста (laplace-presentation/) — сборка.

Роли по решению Гора 29-07: лаплас-окно сдало SCRIPT_LAPLACE.md (20 слайдов,
аудитория Земцов) + 17 артефактов + PRONOUNCE.md; это окно собирает видео.

Устройство слайда: живой пульс-фон из парка (reel_bg_video/*_safe.mp4) +
HTML-слой с альфой (текст не масштабируется). Типы:
  cover      — титул (слайд 1) с названием машины из шапки скрипта;
  statement  — тезис крупной антиквой;
  telemetry  — приборная панель, ряды берутся ИЗ ФАЙЛА АРТЕФАКТА (строки
               «показатель | число | src» в ```-блоках) — числа не перенабираются;
  artifact   — терминальная выдержка из файла артефакта (blockquote и
               ```-содержимое), моноширинно: «свои кадры» продукта = его файлы.

Голос: Serena (Qwen3-TTS), рецепт full_talk_qwen: по предложениям, фырк-ретрай,
без акутов (PRONOUNCE применяется текстовыми заменами со снятыми ударениями —
поддержка акутов у Qwen не подтверждена, а написание типа «баэций» само ведёт).

⛔ Финал здесь НЕ кодируется — только входы (all_v.txt, voice_all.wav).
Кодирование финала — одиночной командой (закон битых NAL).

Запуск: PATH+=C:/Apps/sox/sox-14.4.2 · C:/Apps/qwen-tts/.venv/Scripts/python.exe laplace_talk.py
"""
from __future__ import annotations

import re
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from full_talk import run, wav_len  # noqa: E402
from course_reel import (  # noqa: E402  — фирменный стиль целиком оттуда
    CSS, row, tel, C_ACCENT, C_MUTED, C_TEXT, C_LINE,
)

SRC = Path(r"C:\CLAUD\projects\laplace-presentation")
SCRIPT = SRC / "SCRIPT_LAPLACE.md"
PRON = SRC / "PRONOUNCE.md"
BGV = HERE / "reel_bg_video"
WORK = HERE / "work_laplace"
OUT = HERE / "out"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
W, H, FPS = 1920, 1080, 30
PAUSE_SENT = 0.28
PAUSE_SLIDE = 0.9
VOICE = "Serena"

TITLE_KICKER = "ЛАПЛАС"
TITLE_H1 = "Машина, которая считает<br>мифологический субстрат носителя"

# Фон на слайд — из парка 11 пульс-петель (выбор по смыслу сцены):
# study=кабинет · problem=пустое поле · rules=скрижали/луч · swarm=рой ламп ·
# market5=перекрёсток+башни · village=деревня · mine=пласты · library=архив ·
# market10=прилавок · twodoors=две двери
BG_MAP = {
    1: "06_study", 2: "01_problem", 3: "03_rules", 4: "08_mine",
    5: "09_library", 6: "03_rules", 7: "05_market", 8: "04_swarm",
    9: "01_problem", 10: "09_library", 11: "04_swarm", 12: "02_built",
    13: "11_twodoors", 14: "02_built", 15: "01_problem", 16: "06_study",
    17: "07_village", 18: "08_mine", 19: "01_problem", 20: "09_library",
}

# Доп. CSS поверх стиля course_reel: терминальная панель выдержек.
CSS_EXTRA = f"""
.term{{margin:auto 0;width:1560px;background:rgba(10,9,8,.72);
  border:1px solid {C_LINE};border-radius:10px;padding:38px 44px;
  font-family:Consolas,monospace;font-size:30px;line-height:1.5;color:{C_TEXT}}}
.term .q{{color:{C_ACCENT}}}
.term .dim{{color:{C_MUTED}}}
.term .hd{{font-size:26px;letter-spacing:.09em;color:{C_MUTED};
  border-bottom:1px solid {C_LINE};padding-bottom:12px;margin-bottom:22px;
  text-transform:uppercase}}
.cnum{{position:absolute;right:160px;top:104px;font-family:Consolas,monospace;
  font-size:30px;color:{C_MUTED};z-index:3}}
"""


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── скрипт и произношение ────────────────────────────────────────────────────

def parse() -> list[dict]:
    text = SCRIPT.read_text(encoding="utf-8")
    body = text.split("---", 1)[1].split("\n---")[0]
    chunks = re.split(r"^## (\d+)\. ", body, flags=re.M)[1:]
    slides = []
    for num, chunk in zip(chunks[0::2], chunks[1::2]):
        lines = chunk.split("\n")
        title = lines[0].strip()
        rest = "\n".join(lines[1:])
        typ = (re.search(r"`тип:\s*(\w+)`", rest) or [None, "statement"])[1]
        art = re.search(r"`артефакт:\s*([^`]+)`", rest)
        # начитка: без строк-меток и пометок src
        rest = re.sub(r"^`[^`\n]*`.*$", "", rest, flags=re.M)
        rest = re.sub(r"<!--.*?-->", "", rest, flags=re.S)
        voice = " ".join(p.strip() for p in rest.split("\n") if p.strip())
        slides.append(dict(num=int(num), title=title, typ=typ,
                           art=(SRC / art[1].strip()) if art else None,
                           voice=voice))
    return slides


def pronounce_fixes() -> dict:
    """PRONOUNCE.md → текстовые замены. Акуты и «+» снимаются: письмо ведёт само,
    а поддержка акцент-меток у Qwen не подтверждена ресёрчем."""
    fixes = {}
    for m in re.finditer(r"^(\S[^\n→]*?)\s*→\s*([^\n(]+)", PRON.read_text(encoding="utf-8"), re.M):
        a, b = m.group(1).strip(), m.group(2).strip()
        b = b.replace("\u0301", "").replace("+", "")
        if a and b and a != b and not a.startswith(("тип", "артефакт", "<!--")):
            fixes[a] = b
    return fixes


# ── выдержки артефактов ──────────────────────────────────────────────────────

def artifact_excerpt(path: Path, max_lines: int = 11) -> list[tuple[str, str]]:
    """(класс, строка): blockquote → акцент, ```-контент → обычный.

    ⚠ ФОЛБЭК ОБЯЗАТЕЛЕН: у четырёх артефактов пакета нет ни цитат, ни
    код-блоков — панель выходила пустой (ловили на слайде 15 глазами).
    Если цитатно-кодовой добычи меньше трёх строк, добираем обычными
    абзацами файла: заголовки #, метаданные _курсивом_ и списки src мимо.
    """
    text = path.read_text(encoding="utf-8").split("\n")
    out: list[tuple[str, str]] = []
    in_code = False
    for raw in text:
        s = raw.rstrip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if s.startswith("> "):
            out.append(("q", s[2:].strip().replace("**", "")))
        elif in_code and s.strip():
            out.append(("", s.replace("**", "")))
        if len(out) >= max_lines:
            break
    if len(out) < 3:
        for raw in text:
            s = raw.strip()
            if (not s or s.startswith(("#", "_", "```", "- `", "<!--"))
                    or s.startswith("> ")):
                continue
            out.append(("", s.replace("**", "")))
            if len(out) >= 7:      # фолбэк-абзацы длиннее кода: панель распухает
                break
    return out


def telemetry_rows(path: Path, max_rows: int = 6) -> str:
    rows = ""
    n = 0
    for cls, line in artifact_excerpt(path, max_lines=40):
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2 or not parts[1]:
            continue
        rows += row(esc(parts[0]), esc(parts[1]))
        n += 1
        if n >= max_rows:
            break
    return rows


# ── HTML слайдов ─────────────────────────────────────────────────────────────

def slide_html(sl: dict) -> tuple[str, str]:
    """(html, класс скрима)"""
    num = f'<div class=cnum>{sl["num"]:02d} / 20</div>'
    if sl["num"] == 1:
        return (f'{num}<div class=kick><i>◆</i> {TITLE_KICKER}</div>'
                f'<div class=mid><h1 style="font-size:118px">{TITLE_H1}</h1>'
                f'<div class=sub>{esc(sl["title"])}</div></div>'
                f'<div class=foot>всё в докладе трассируется к файлам на диске</div>', "")
    if sl["typ"] == "telemetry" and sl["art"]:
        return (f'{num}<div class=kick>{TITLE_KICKER} · основание</div>'
                + tel(esc(sl["title"]).upper()[:64], "СЧИТАНО С ДИСКА 12-07",
                      telemetry_rows(sl["art"])), "full")
    if sl["typ"] == "artifact" and sl["art"] and sl["art"].exists():
        body = ""
        for cls, line in artifact_excerpt(sl["art"]):
            # без жёсткой обрезки: CSS переносит сам, длинные дампы — до 200 зн.
            body += (f'<div class="{cls}" style="margin-bottom:14px">{esc(line[:200])}</div>'
                     if cls else f'<div>{esc(line[:200])}</div>')
        return (f'{num}<div class=kick>{TITLE_KICKER}</div>'
                f'<div class=mid><div class="st sm" style="margin-bottom:34px">'
                f'{esc(sl["title"])}</div>'
                f'<div class=term><div class=hd>{esc(sl["art"].name)}</div>{body}</div>'
                f'</div>', "full")
    # statement
    return (f'{num}<div class=kick>{TITLE_KICKER}</div>'
            f'<div class=mid><div class=st>{esc(sl["title"])}</div></div>', "")


def render_png(sl: dict) -> Path | None:
    page = WORK / f"s{sl['num']:02d}.html"
    png = WORK / f"s{sl['num']:02d}.png"
    html, scrim = slide_html(sl)
    page.write_text(f"<!doctype html><meta charset=utf-8>"
                    f"<style>{CSS}{CSS_EXTRA}</style>"
                    f"<div class='s {scrim}'>{html}</div>", encoding="utf-8")
    if png.exists():
        return png
    r = run([str(CHROME), "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--default-background-color=00000000", f"--window-size={W},{H}",
             "--force-device-scale-factor=1", "--virtual-time-budget=4000",
             f"--screenshot={png}", page.resolve().as_uri()])
    if not png.exists():
        print("   chrome:", r.stderr.decode("utf-8", "replace")[-200:])
        return None
    return png


# ── сборка ───────────────────────────────────────────────────────────────────

def main() -> int:
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    slides = parse()
    print(f"скрипт: {len(slides)} слайдов")
    fixes = pronounce_fixes()
    print(f"произношение: {len(fixes)} замен")

    import numpy as np
    import torch
    import soundfile as sf
    from qwen_tts import Qwen3TTSModel
    from gen_voices_cb import snort_free

    model = Qwen3TTSModel.from_pretrained(
        "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", device_map="cuda",
        dtype=torch.bfloat16)

    def say(text: str) -> tuple[np.ndarray, int]:
        for a, b in fixes.items():
            text = text.replace(a, b)
        sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]
        chunks, sr = [], 24000
        for s in sents:
            best = None
            for _ in range(2):
                wavs, sr = model.generate_custom_voice(
                    text=s, speaker=VOICE, language="Russian")
                w = np.asarray(wavs[0] if isinstance(wavs, list) else wavs,
                               dtype=np.float32)
                best = w
                if snort_free(torch.from_numpy(w), sr):
                    break
            chunks.append(best)
            chunks.append(np.zeros(int(sr * PAUSE_SENT), dtype=np.float32))
        return np.concatenate(chunks[:-1]), sr

    entries = []
    for sl in slides:
        png = render_png(sl)
        if not png:
            print(f"  {sl['num']:2}: слайд не отрисован — СТОП")
            return 1
        wav_p = WORK / f"v{sl['num']:02d}.wav"
        if not wav_p.exists():
            audio, sr = say(sl["voice"])
            sf.write(str(wav_p), audio, sr)
        d = 0.35 + wav_len(wav_p) + PAUSE_SLIDE
        entries.append((sl, png, wav_p, d))
        print(f"  {sl['num']:2} [{sl['typ']:9}] {sl['title'][:42]:42} {d:6.1f}с",
              flush=True)

    vparts = []
    for sl, png, wav_p, d in entries:
        vp = WORK / f"p{sl['num']:02d}.mp4"
        if not vp.exists():
            loop = BGV / f"{BG_MAP[sl['num']]}_safe.mp4"
            vf = (f"[0:v]scale={W}:{H},format=yuv420p,setsar=1[bg];"
                  f"[1:v]format=rgba,fade=t=in:st=0.10:d=0.42:alpha=1[txt];"
                  f"[bg][txt]overlay=0:0:format=auto,format=yuv420p,setsar=1[v]")
            r = run(["ffmpeg", "-y", "-v", "error", "-threads", "2",
                     "-stream_loop", "-1", "-t", f"{d:.3f}", "-i", str(loop),
                     "-loop", "1", "-framerate", str(FPS), "-t", f"{d:.3f}",
                     "-i", str(png),
                     "-filter_complex", vf, "-map", "[v]", "-r", str(FPS),
                     "-c:v", "libx264", "-preset", "medium", "-crf", "15",
                     "-pix_fmt", "yuv420p", str(vp)])
            if r.returncode != 0:
                print("   план:", r.stderr.decode("utf-8", "replace")[-250:])
                return 1
        vparts.append((vp, wav_p, d))

    awavs = []
    for vp, wav_p, d in vparts:
        ap = WORK / (vp.stem + "_a.wav")
        run(["ffmpeg", "-y", "-v", "error", "-i", str(wav_p),
             "-af", f"aresample=48000,adelay=350|350,apad,atrim=duration={d:.3f}",
             "-ac", "2", "-c:a", "pcm_s16le", str(ap)])
        awavs.append(ap)

    (WORK / "all_v.txt").write_text(
        "".join(f"file '{p[0].name}'\n" for p in vparts), encoding="utf-8")
    (WORK / "all_a.txt").write_text(
        "".join(f"file '{p.name}'\n" for p in awavs), encoding="utf-8")
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(WORK / "all_a.txt"), "-c", "copy",
         str(WORK / "voice_all.wav")], cwd=WORK)
    print(f"ВХОДЫ ГОТОВЫ: {WORK} — финал одиночной командой")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
