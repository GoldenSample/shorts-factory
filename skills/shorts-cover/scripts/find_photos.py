#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Поиск настоящих фото наших сборок под обложку шортса (скил shorts-cover). pc-store только читается.

    py -3.12 find_photos.py 5090 "9070 XT" 9800X3D          # каждая строка — отдельный поиск
    py -3.12 find_photos.py 5090 9950X3D2 --all             # сборки, где есть все слова сразу (9950X3D не ловит 9950x3D2)
    py -3.12 find_photos.py 5090 --sheet C:/path/sheet.jpg  # контакт-лист найденных фото (PIL), угол Авито обведён
    py -3.12 find_photos.py --push 7361943333-1 7361129981-1 [--dest /opt/shorts/r5090/cover/src/]

Источник: pc-store/data/avito-builds.json (синк витрины) + pc-store/public/builds/<id>-N.jpg.
На каждом снимке витрины в правом нижнем углу знак Авито: печатается зона, которую кроп обязан обойти
(та же формула, что в cover.py: x >= W - max(14% W, 140), y >= H - max(8% H, 70)).
Цену из json не печатаем: на обложку и в ролик цена заказной сборки не идёт (правило no-prices).
--push кладёт файлы на хаб по ключу ~/.ssh/gspc_deploy только в /opt/shorts/r5090/, /opt/shorts/<проект>/cover_skill/
или /tmp/.
Чужой водяной знак на снимке витрины (пример 01.10: SINGULARITY COMPUTERS слева внизу у 4801494117) скрипт не ловит:
смотреть контакт-лист глазами, такой снимок на обложку не брать.
"""
import argparse
import json
import os
import re
import struct
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

GIT = os.environ.get("GSPC_ROOT", r"C:/Users/Administrator/Documents/git")
STORE = os.path.join(GIT, "pc-store")
DATA = os.path.join(STORE, "data", "avito-builds.json")
BUILDS = os.path.join(STORE, "public", "builds")
HUB = "root@<VPS_IP>"
KEY = os.path.expanduser("~/.ssh/gspc_deploy")
DEST = "/opt/shorts/r5090/cover/src/"
DEST_OK = ("/opt/shorts/r5090/", "/tmp/")
DEST_RX = re.compile(r"^/opt/shorts/[^/]+/cover_skill/")   # папка обложки любого проекта


def avito_zone(w, h):
    """Левый верхний угол зоны знака Авито (правый нижний угол снимка витрины)."""
    return w - max(round(0.14 * w), 140), h - max(round(0.08 * h), 70)


def exif_orientation(data):
    i = data.find(b"Exif\x00\x00")
    if i < 0:
        return 1
    t = data[i + 6:]
    try:
        end = "<" if t[:2] == b"II" else ">"
        off = struct.unpack(end + "I", t[4:8])[0]
        n = struct.unpack(end + "H", t[off:off + 2])[0]
        for k in range(n):
            e = off + 2 + 12 * k
            tag = struct.unpack(end + "H", t[e:e + 2])[0]
            if tag == 0x0112:
                return struct.unpack(end + "H", t[e + 8:e + 10])[0]
    except Exception:
        pass
    return 1


def dims(path):
    """(ширина, высота) как их видит ffmpeg и браузер (с поворотом EXIF). stdlib, JPEG и PNG."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        m = data[i + 1]
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        ln = struct.unpack(">H", data[i + 2:i + 4])[0]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            if exif_orientation(data[:i]) in (5, 6, 7, 8):
                w, h = h, w
            return w, h
        i += 2 + ln
    return None


def pattern(q):
    """«9070 XT» ловит 9070XT, 9070 xt, 9070-XT; число не ловится внутри другого числа (5090 не в 15090)."""
    parts = [re.escape(p) for p in re.split(r"[\s\-]+", q.strip()) if p]
    rx = r"[\s\-]*".join(parts)
    # перед числом нельзя только цифру (RX9070XT ловится), перед словом — ни букву, ни цифру
    head = r"(?<![0-9])" if q.strip()[:1].isdigit() else r"(?<![0-9a-zа-яё])"
    return re.compile(head + rx + r"(?![0-9])", re.I)


def load():
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)["builds"]


def files_of(b):
    out = []
    for k, im in enumerate(b.get("images") or []):
        fn = os.path.basename(im)
        p = os.path.join(BUILDS, fn)
        wh = dims(p) if os.path.exists(p) else None
        if not wh and b.get("imageSizes") and k < len(b["imageSizes"]):
            wh = tuple(b["imageSizes"][k])
        out.append((fn, p, wh))
    return out


def show(b, where):
    print("  %s  %s  [%s]" % (b["id"], b.get("title", ""), where))
    for fn, p, wh in files_of(b):
        if wh:
            zx, zy = avito_zone(*wh)
            print("     %-18s %4dx%-4d  знак Авито: x>=%d, y>=%d%s" % (fn, wh[0], wh[1], zx, zy,
                  "" if os.path.exists(p) else "  (файла нет локально)"))
        else:
            print("     %-18s размер неизвестен%s" % (fn, "" if os.path.exists(p) else ", файла нет"))


def search(queries, need_all):
    builds = load()
    found = []
    if need_all:
        rx = [pattern(q) for q in queries]
        print("== все сразу: %s" % " + ".join(queries))
        for b in builds:
            t, d = b.get("title", ""), b.get("description", "")
            if all(r.search(t + "\n" + d) for r in rx):
                show(b, "заголовок" if all(r.search(t) for r in rx) else "описание")
                found.append(b)
        if not found:
            print("  ничего")
        return found
    for q in queries:
        rx = pattern(q)
        hits = [(0 if rx.search(b.get("title", "")) else 1, b) for b in builds
                if rx.search(b.get("title", "") + "\n" + b.get("description", ""))]
        hits.sort(key=lambda x: x[0])
        print("== %s: %d" % (q, len(hits)))
        for w, b in hits:
            show(b, "заголовок" if w == 0 else "описание")
            if b not in found:
                found.append(b)
    return found


def sheet(builds, out):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("PIL нет в этом питоне: контакт-лист не собрать (pip не ставить)")
        return
    tiles = []
    for b in builds:
        for fn, p, wh in files_of(b):
            if os.path.exists(p):
                tiles.append((fn, p))
    if not tiles:
        print("контакт-лист: нет файлов")
        return
    th, cols = 360, 4
    cells = []
    for fn, p in tiles:
        im = Image.open(p).convert("RGB")
        w, h = im.size
        zx, zy = avito_zone(w, h)
        d = ImageDraw.Draw(im)
        lw = max(3, w // 200)
        d.rectangle([zx, zy, w - 1, h - 1], outline=(255, 40, 40), width=lw)
        im = im.resize((max(1, round(w * th / h)), th))
        cells.append((fn, im))
    cw = max(im.size[0] for _, im in cells)
    rows = (len(cells) + cols - 1) // cols
    canvas = Image.new("RGB", (cols * (cw + 10) + 10, rows * (th + 40) + 10), (24, 24, 28))
    d = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except Exception:
        font = ImageFont.load_default()
    for k, (fn, im) in enumerate(cells):
        x = 10 + (k % cols) * (cw + 10)
        y = 10 + (k // cols) * (th + 40)
        canvas.paste(im, (x, y + 30))
        d.text((x, y + 4), fn, fill=(255, 230, 80), font=font)
    canvas.save(out, quality=88)
    print("контакт-лист: %s (%d фото; красная рамка = зона знака Авито, кроп её обходит)" % (out, len(cells)))


def push(names, dest):
    dest = dest if dest.endswith("/") else dest + "/"
    if not (dest.startswith(DEST_OK) or DEST_RX.match(dest)) or ".." in dest or "'" in dest:
        sys.exit("--dest %s: только внутри %s или /opt/shorts/<проект>/cover_skill/. Git Bash переписывает /tmp/... "
                 "в путь Windows — запускать с MSYS_NO_PATHCONV=1 или из PowerShell" % (dest, " или ".join(DEST_OK)))
    paths = []
    for n in names:
        fn = n if n.lower().endswith((".jpg", ".jpeg", ".webp", ".png")) else n + ".jpg"
        p = os.path.join(BUILDS, os.path.basename(fn))
        if not os.path.exists(p):
            sys.exit("нет файла %s" % p)
        paths.append(p)
    ssh = ["ssh", "-i", KEY, "-o", "ConnectTimeout=15", HUB, "mkdir -p '%s'" % dest]
    subprocess.run(ssh, check=True)
    subprocess.run(["scp", "-i", KEY, "-o", "ConnectTimeout=15"] + paths + ["%s:%s" % (HUB, dest)], check=True)
    for p in paths:
        print("на хабе: %s%s" % (dest, os.path.basename(p)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("words", nargs="*", help="строки поиска: 5090, \"9070 XT\", 9800X3D")
    ap.add_argument("--all", action="store_true", help="все строки в одной сборке")
    ap.add_argument("--sheet", help="путь jpg контакт-листа найденных фото")
    ap.add_argument("--push", nargs="+", metavar="ID-N", help="скопировать public/builds/<ID-N>.jpg на хаб")
    ap.add_argument("--dest", default=DEST, help="папка на хабе (по умолчанию %s)" % DEST)
    a = ap.parse_args()
    if a.push:
        push(a.push, a.dest)
        return
    if not a.words:
        ap.error("нужны слова поиска или --push")
    found = search(a.words, a.all)
    if a.sheet and found:
        sheet(found, a.sheet)


if __name__ == "__main__":
    main()
