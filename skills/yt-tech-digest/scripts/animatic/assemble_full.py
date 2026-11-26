# -*- coding: utf-8 -*-
"""Полный «Де-лидер 3» голосом Гора: 42 кадра, слайды + Imagine (Ken Burns с плашкой на каждом кадре), 1920x1080."""
import os, sys, io, json, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from PIL import Image, ImageDraw, ImageFont
HERE = os.path.dirname(os.path.abspath(__file__))
F5 = os.path.join(HERE, "first5"); SL = os.path.join(F5, "slides"); IM = os.path.join(F5, "imagine")
IG = os.path.join(F5, "igor"); TMP = os.path.join(F5, "tmp3"); os.makedirs(TMP, exist_ok=True)
OUT = os.path.join(F5, "De-leader-3 - полный аниматик (голос Гора).mp4")
FPS = 30
PICK = json.load(open(os.path.join(F5, "pick.json")))
D = {int(k): v for k, v in json.load(open(os.path.join(IG, "durs.json"))).items()}
GAP = 1.6

def imagine(key):
    src = os.path.join(IM, PICK.get(key, key + "_1.jpg"))
    dst = os.path.join(TMP, key + "_lab.jpg")
    im = Image.open(src).convert("RGB")
    if im.size != (1920, 1080): im = im.resize((1920, 1080), Image.LANCZOS)
    im.save(dst, quality=92); return dst

LABEL_F = ImageFont.truetype(r"C:\Windows\Fonts\segoeui.ttf", 26)
def stamp(fr):
    d = ImageDraw.Draw(fr)
    s = "изображение сгенерировано · иллюстрация"
    l, t, r, b = d.textbbox((0, 0), s, font=LABEL_F)
    d.rectangle([1920 - (r - l) - 48, 1080 - (b - t) - 38, 1920 - 14, 1080 - 10], fill=(0, 0, 0))
    d.text((1920 - (r - l) - 32, 1080 - (b - t) - 32), s, font=LABEL_F, fill=(210, 210, 210))
    return fr

def kenburns_pipe(img, dur, out, zoom_to=1.10):
    src = Image.open(img).convert("RGB"); sw, sh = src.size
    n = max(int(round(dur * FPS)), FPS)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080", "-r", str(FPS), "-i", "-",
           "-vf", "fade=t=in:st=0:d=0.4,fade=t=out:st=%.2f:d=0.4,format=yuv420p" % max(dur - 0.4, 0),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", out]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        z = 1.0 + (zoom_to - 1.0) * i / max(n - 1, 1)
        cw, ch = sw / z, sh / z
        x0, y0 = (sw - cw) / 2.0, (sh - ch) / 2.0
        fr = src.resize((1920, 1080), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))
        pr.stdin.write(stamp(fr).tobytes())
    pr.stdin.close(); pr.wait()
    if pr.returncode: raise RuntimeError("kenburns failed")
    return out

def seg(img, dur, kb, name):
    out = os.path.join(TMP, name + ".mp4")
    if kb: return kenburns_pipe(img, dur, out)
    vf = "scale=1920:1080,fade=t=in:st=0:d=0.3,fade=t=out:st=%.2f:d=0.3,format=yuv420p" % max(dur - 0.3, 0)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", img, "-t", "%.3f" % dur, "-vf", vf, "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", out], check=True)
    return out

def concat(clips, out):
    lst = os.path.join(TMP, os.path.basename(out) + ".txt")
    open(lst, "w", encoding="utf-8").write("".join("file '%s'\n" % c.replace("\\", "/") for c in clips))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], check=True)
    return out

def frame_clip(i, segments, audio):
    key = "h%02d" % i
    vid = concat([seg(img, d_, kb, "%s_%d" % (key, k)) for k, (img, d_, kb) in enumerate(segments)], os.path.join(TMP, key + "_v.mp4"))
    total = sum(d_ for _, d_, _ in segments)
    out = os.path.join(TMP, key + ".mp4")
    if audio:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", vid, "-i", audio, "-filter_complex", "[1:a]apad[a]", "-map", "0:v", "-map", "[a]", "-t", "%.3f" % total, "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", out], check=True)
    else:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", vid, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "%.3f" % total, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", out], check=True)
    return out

def s(name): return os.path.join(SL, name)
def a(i): return os.path.join(IG, "f%02d_igor.mp3" % i)
def T(i, extra=0.0): return D[i] + GAP + extra

# план: (кадр, сегменты [(картинка, доля/сек, kb)], аудио). Доли считаются от T(i).
def parts(i, *items, extra=0.0):
    tot = T(i, extra)
    return [(img, tot * frac, kb) for img, frac, kb in items]

plan = [
    (0,  [(s("s00_intro.png"), 5.0, False)], None),
    (1,  parts(1, (imagine("f01_stand"), .45, True), (s("s01_rules.png"), .55, False)), a(1)),
    (2,  parts(2, (imagine("f02_judge"), .35, True), (s("s02_judge.png"), .65, False)), a(2)),
    (3,  [(s("s03_profiles.png"), T(3), False)], a(3)),
    (4,  parts(4, (imagine("f04_starship"), .35, True), (s("s04_physics.png"), .65, False)), a(4)),
    (5,  parts(5, (s("s05_bios_count.png"), .38, False), (imagine("f05_museum"), .22, True), (s("s06_bios_traps.png"), .40, False)), a(5)),
    (6,  parts(6, (imagine("f06_vrm"), .5, True), (s("s07_ladder_empty.png"), .5, False)), a(6)),
    (7,  parts(7, (s("s08_stock.png"), .75, False), (imagine("f07_loop"), .25, True), extra=6), a(7)),
    (8,  parts(8, (s("s09_pbo_cfg.png"), .40, False), (s("s10_pbo.png"), .60, False), extra=6), a(8)),
    (9,  parts(9, (s("s11_lok_cfg.png"), .55, False), (s("s12_lok.png"), .45, False)), a(9)),
    (10, [(s("s13_lok_repeat.png"), T(10), False)], a(10)),
    (11, parts(11, (s("s14_lok_games.png"), 1.0, False), extra=4), a(11)),
    (12, [(s("s15_anl_cfg.png"), T(12), False)], a(12)),
    (13, parts(13, (s("s16_anl.png"), 1.0, False), extra=6), a(13)),
    (14, [(s("s17_hwbot.png"), T(14), False)], a(14)),
    (15, [(s("s18_session.png"), T(15), False)], a(15)),
    (16, [(s("s19_ladder_full.png"), T(16), False)], a(16)),
    (17, parts(17, (imagine("f08_b650"), .45, True), (s("s20_b650_intro.png"), .55, False)), a(17)),
    (18, parts(18, (s("s21_b650_stock.png"), 1.0, False), extra=5), a(18)),
    (19, parts(19, (s("s22_b650_pbo.png"), 1.0, False), extra=5), a(19)),
    (20, parts(20, (s("s23_b650_lok.png"), 1.0, False), extra=5), a(20)),
    (21, parts(21, (s("s24_b650_anl.png"), 1.0, False), extra=5), a(21)),
    (22, [(s("s25_b650_anl_games.png"), T(22), False)], a(22)),
    (23, [(s("s26_two_ladders.png"), T(23), False)], a(23)),
    (24, [(s("s27_payoff.png"), T(24), False)], a(24)),
    (25, [(s("s28_hwinfo.png"), T(25), False)], a(25)),
    (26, [(s("s29_edc.png"), T(26), False)], a(26)),
    (27, [(s("s30_matrix.png"), T(27), False)], a(27)),
    (28, [(s("s31_deltas.png"), T(28), False)], a(28)),
    (29, parts(29, (imagine("f09_quiet"), .45, True), (s("s32_cs2_intro.png"), .55, False)), a(29)),
    (30, parts(30, (s("s33_rec_daily.png"), 1.0, False), extra=5), a(30)),
    (31, [(s("s34_cs2_deltas.png"), T(31), False)], a(31)),
    (32, [(s("s35_fork.png"), T(32), False)], a(32)),
    (33, [(s("s36_lyoha.png"), T(33), False)], a(33)),
    (34, parts(34, (s("s37_mem.png"), 1.0, False), extra=3), a(34)),
    (35, [(s("s38_cap.png"), T(35), False)], a(35)),
    (36, [(s("s39_final.png"), T(36), False)], a(36)),
    (37, [(s("s40_who.png"), T(37), False)], a(37)),
    (38, [(s("s41_table.png"), T(38), False)], a(38)),
    (39, [(s("s42_persona.png"), T(39), False)], a(39)),
    (40, [(s("s43_goose.png"), T(40, 3), False)], a(40)),
    (41, parts(41, (imagine("f10_scope"), .6, True), (s("s44_next.png"), .4, False), extra=2), a(41)),
]
clips = []
for i, segs, audio in plan:
    clips.append(frame_clip(i, segs, audio)); print("кадр %d (%.1f с)" % (i, sum(d_ for _, d_, _ in segs)))
concat(clips, OUT)
r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", OUT], capture_output=True, text=True)
print("OK ->", OUT, "| %.1f с = %s" % (float(r.stdout.strip()), "%d:%02d" % (float(r.stdout.strip()) // 60, float(r.stdout.strip()) % 60)))
