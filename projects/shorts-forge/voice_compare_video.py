# -*- coding: utf-8 -*-
"""Ролик-сравнение голосов для прослушивания с телефона (слово Гора 03.10: «тестовый ролик сравнение голосов
в телеграм канал»). Вертикаль 1080x1920, стиль-библия Golden Sample (tools/gs_style.py: Tektur + Jost, голубой,
золотой, терракот). Каждый клип выравнивается по громкости (-16 LUFS), чтобы громкий голос не казался лучше.

  py -3.12 voice_compare_video.py plan.json out.mp4

plan.json: {"segments": [
  {"card": "ЗАГОЛОВОК", "sub": "подзаголовок", "lines": ["строка", ...], "sec": 4},
  {"wav": "путь.wav", "label": "v4", "tag": "сейчас в канале", "color": "blue|gold|terra|white|muted",
   "text": "фраза на экране", "hl": ["слово", ...], "section": "УДАРЕНИЯ", "foot": "подвал"}, ...]}
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, r"C:\CLAUD\tools")
import gs_style as S  # noqa: E402

W, H = 1080, 1920
FD = Path(S.FONT_DIR)
COL = {"blue": S.BLUE, "gold": S.GOLD, "terra": S.TERRA, "white": S.WHITE, "muted": S.MUTED}
FF = shutil.which("ffmpeg") or "ffmpeg"
FP = shutil.which("ffprobe") or "ffprobe"


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FD / name), size)


def wrap(d: ImageDraw.ImageDraw, text: str, f, width: int) -> list[str]:
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= width:
            cur = t
        else:
            if cur:
                out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out


def base() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGB", (W, H), S.INK)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 10], fill=S.GOLD)
    d.text((60, 70), "GOLDEN SAMPLE", font=font("Tektur-SemiBold.ttf", 34), fill=S.GOLD)
    d.text((60, 116), "двойник голоса Гора", font=font("Jost-Medium.ttf", 34), fill=S.MUTED)
    return im, d


def card(seg: dict, path: Path) -> None:
    im, d = base()
    y = 520
    for ln in wrap(d, seg["card"], font("Tektur-Bold.ttf", 92), W - 120):
        d.text((60, y), ln, font=font("Tektur-Bold.ttf", 92), fill=S.WHITE)
        y += 110
    if seg.get("sub"):
        y += 20
        for ln in wrap(d, seg["sub"], font("Jost-Medium.ttf", 50), W - 120):
            d.text((60, y), ln, font=font("Jost-Medium.ttf", 50), fill=S.BLUE)
            y += 64
    y += 50
    for item in seg.get("lines", []):
        color = S.WHITE
        if isinstance(item, list):
            item, color = item[0], COL.get(item[1], S.WHITE)
        for ln in wrap(d, item, font("Jost-Medium.ttf", 46), W - 120):
            d.text((60, y), ln, font=font("Jost-Medium.ttf", 46), fill=color)
            y += 60
        y += 18
    im.save(path)


def clip_card(seg: dict, path: Path) -> None:
    im, d = base()
    if seg.get("section"):
        d.text((60, 300), seg["section"], font=font("Tektur-SemiBold.ttf", 44), fill=S.MUTED)
    col = COL.get(seg.get("color", "white"), S.WHITE)
    d.rectangle([60, 400, 76, 600], fill=col)
    d.text((110, 395), seg["label"], font=font("Tektur-Bold.ttf", 150), fill=col)
    if seg.get("tag"):
        d.text((114, 570), seg["tag"], font=font("Jost-SemiBold.ttf", 48), fill=S.WHITE)
    f = font("Jost-Medium.ttf", 64)
    hl = {w.lower().strip(".,:;!?«»") for w in seg.get("hl", [])}
    y = 820
    for ln in wrap(d, seg.get("text", ""), f, W - 120):
        x = 60
        for w in ln.split():
            key = w.lower().strip(".,:;!?«»")
            d.text((x, y), w, font=f, fill=S.GOLD if key in hl else S.WHITE)
            x += d.textlength(w + " ", font=f)
        y += 86
    if seg.get("foot"):
        for k, ln in enumerate(wrap(d, seg["foot"], font("Jost-Medium.ttf", 42), W - 120)):
            d.text((60, H - 260 + k * 56), ln, font=font("Jost-Medium.ttf", 42), fill=S.MUTED)
    im.save(path)


def norm_wav(src: str, dst: Path) -> float:
    subprocess.run([FF, "-y", "-v", "error", "-i", src, "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000",
                    "-ac", "1", "-ar", "48000", str(dst)], check=True)
    r = subprocess.run([FP, "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", str(dst)], capture_output=True, text=True)
    return float(r.stdout.strip())


def main() -> int:
    plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = Path(sys.argv[2])
    tmp = Path(tempfile.mkdtemp(prefix="vcmp_"))
    gap = 0.6
    concat_v, concat_a = [], []
    for i, seg in enumerate(plan["segments"]):
        img = tmp / f"s{i:03d}.png"
        if "card" in seg:
            card(seg, img)
            dur = float(seg.get("sec", 3))
            silence = tmp / f"a{i:03d}.wav"
            subprocess.run([FF, "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", str(dur),
                            str(silence)], check=True)
            concat_a.append(silence)
        else:
            clip_card(seg, img)
            a = tmp / f"a{i:03d}.wav"
            d = norm_wav(seg["wav"], a)
            padded = tmp / f"p{i:03d}.wav"       # тишина до и после клипа: ухо успевает переключиться
            subprocess.run([FF, "-y", "-v", "error", "-i", str(a), "-af", f"adelay=300|300,apad=pad_dur={gap}",
                            "-ar", "48000", "-ac", "1", str(padded)], check=True)
            dur = d + 0.3 + gap
            concat_a.append(padded)
        concat_v.append((img, dur))
    vl = tmp / "v.txt"
    with vl.open("w", encoding="utf-8") as f:
        for img, dur in concat_v:
            f.write(f"file '{img.as_posix()}'\nduration {dur:.3f}\n")
        f.write(f"file '{concat_v[-1][0].as_posix()}'\n")
    al = tmp / "a.txt"
    al.write_text("".join(f"file '{a.as_posix()}'\n" for a in concat_a), encoding="utf-8")
    aud = tmp / "all.wav"
    subprocess.run([FF, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(al), "-c", "copy", str(aud)], check=True)
    subprocess.run([FF, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(vl), "-i", str(aud),
                    "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-tune", "stillimage",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], check=True)
    total = sum(d for _, d in concat_v)
    print(f"ГОТОВО {out} ({total:.0f} с, {len(concat_v)} кадров)")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
