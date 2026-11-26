#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Режиссёрский контур: Клод смотрит каждый кадр сам, Грок исполняет.

Правило Гора 08-20: Грок сдаёт кадр -> Клод ЧИТАЕТ его полностью и осмысляет ->
через несколько итераций собирается КОСТЯК утверждённых кадров -> и только тогда
Грок идёт на видеогенерацию -> потом Клод проверяет снова.

Стадии, каждая отдельным запуском; между ними кадры смотрит Клод:

  shoot   --scene N --prompt "..." [--n 4]   снять дубли сцены
  approve --scene N --pick K                 утвердить дубль в костяк
  status                                     что уже в костяке
  animate --scene N [--seconds 6]            оживить утверждённый кадр (image-to-video)

Всё складывается в /opt/shorts/dir/<slug>/: cand/ дубли, kostyak/ утверждённое,
prev/ уменьшенные превью для просмотра, usage.jsonl расход.
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import uuid

sys.path.insert(0, "/usr/local/lib/hermes-agent")
os.chdir("/usr/local/lib/hermes-agent")

import httpx  # noqa: E402
from tools.xai_http import resolve_xai_http_credentials  # noqa: E402

ROOT = "/opt/shorts/dir"
IMAGE_MODEL = os.environ.get("DIRECTOR_IMAGE_MODEL", "grok-imagine-image-2.0")
VIDEO_MODEL = "grok-imagine-video-1.5"
CONSOLE_ENV = "/opt/shorts/console.env"
W, H, FPS = 1080, 1920, 30


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def run(cmd, **kw):
    kw.setdefault("stdin", subprocess.DEVNULL)
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    return subprocess.run(cmd, **kw)


def oauth():
    c = resolve_xai_http_credentials() or {}
    return c["api_key"], (c.get("base_url") or "https://api.x.ai/v1").rstrip("/")


def note(slug, rec):
    rec["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(os.path.join(ROOT, slug, "usage.jsonl"), "a", encoding="utf-8") as f:
        print(json.dumps(rec, ensure_ascii=False), file=f)


def sdir(slug):
    d = os.path.join(ROOT, slug)
    for sub in ("", "cand", "kostyak", "prev"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    return d


def preview(src, dst, width=420):
    run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", src,
         "-vf", "scale=%d:-1" % width, "-q:v", "4", dst])


# ---------------------------------------------------------------- стадии

def cmd_shoot(a):
    d = sdir(a.slug)
    key, base = oauth()
    h = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    r = httpx.post(base + "/images/generations", headers=h, timeout=300,
                   json={"model": IMAGE_MODEL, "prompt": a.prompt,
                         "n": a.n, "resolution": "2k", "aspect_ratio": "9:16"})
    if r.status_code != 200:
        raise SystemExit("кадр: HTTP %s %s" % (r.status_code, r.text[:300]))
    body = r.json()
    usd = (body.get("usage") or {}).get("cost_in_usd_ticks", 0) / 1e10
    made = []
    for k, item in enumerate(body.get("data") or []):
        p = os.path.join(d, "cand", "s%d_%d.jpg" % (a.scene, k))
        open(p, "wb").write(httpx.get(item["url"], timeout=300).content)
        preview(p, os.path.join(d, "prev", "s%d_%d.jpg" % (a.scene, k)))
        made.append(os.path.basename(p))
    with open(os.path.join(d, "prompts.jsonl"), "a", encoding="utf-8") as f:
        print(json.dumps({"scene": a.scene, "prompt": a.prompt, "n": a.n,
                          "ts": time.strftime("%H:%M:%S")}, ensure_ascii=False), file=f)
    note(a.slug, {"kind": "image", "scene": a.scene, "n": len(made), "usd": round(usd, 3)})
    log("сцена %d: снято %d дублей, $%.2f" % (a.scene, len(made), usd))
    for p in made:
        log("  " + p)


def cmd_approve(a):
    d = sdir(a.slug)
    src = os.path.join(d, "cand", "s%d_%d.jpg" % (a.scene, a.pick))
    if not os.path.exists(src):
        raise SystemExit("нет такого дубля: %s" % src)
    dst = os.path.join(d, "kostyak", "s%d.jpg" % a.scene)
    with open(src, "rb") as f_in, open(dst, "wb") as f_out:
        f_out.write(f_in.read())
    log("сцена %d: дубль %d в костяк" % (a.scene, a.pick))


def cmd_status(a):
    d = sdir(a.slug)
    k = sorted(os.listdir(os.path.join(d, "kostyak")))
    c = sorted(os.listdir(os.path.join(d, "cand")))
    log("костяк (%d): %s" % (len(k), ", ".join(k) or "пусто"))
    log("дублей снято: %d" % len(c))
    anims = sorted(x for x in os.listdir(d) if x.startswith("anim"))
    log("оживлено: %s" % (", ".join(anims) or "нет"))
    u = os.path.join(d, "usage.jsonl")
    if os.path.exists(u):
        tot = sum(json.loads(l).get("usd", 0) for l in open(u, encoding="utf-8") if l.strip())
        log("потрачено: $%.2f" % tot)


def cmd_animate(a):
    """Оживляем УТВЕРЖДЁННЫЙ кадр: image-to-video, объект в кадре остаётся тем же."""
    d = sdir(a.slug)
    still = os.path.join(d, "kostyak", "s%d.jpg" % a.scene)
    if not os.path.exists(still):
        raise SystemExit("сцена %d не утверждена — сначала approve" % a.scene)
    key, base = oauth()
    h = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    b64 = base64.b64encode(open(still, "rb").read()).decode()
    payload = {"model": VIDEO_MODEL, "prompt": a.motion,
               "image_url": "data:image/jpeg;base64," + b64,
               "duration": a.seconds, "aspect_ratio": "9:16", "resolution": "720p"}
    t0 = time.time()
    r = httpx.post(base + "/videos/generations",
                   headers={**h, "x-idempotency-key": str(uuid.uuid4())},
                   json=payload, timeout=90)
    if r.status_code != 200:
        raise SystemExit("видео: HTTP %s %s" % (r.status_code, r.text[:300]))
    rid = r.json()["request_id"]
    log("сцена %d: задание %s, жду" % (a.scene, rid[:8]))
    body = {}
    for _ in range(60):
        time.sleep(5)
        body = httpx.get("%s/videos/%s" % (base, rid), headers=h, timeout=30).json()
        if (body.get("status") or "").lower() in ("done", "failed", "error", "expired", "cancelled"):
            break
    if (body.get("status") or "").lower() != "done":
        raise SystemExit("видео: статус %s" % body.get("status"))
    url = (body.get("file_output") or {}).get("public_url") or (body.get("video") or {}).get("url")
    out = os.path.join(d, "anim%d.mp4" % a.scene)
    with httpx.stream("GET", url, timeout=300, follow_redirects=True) as g:
        with open(out, "wb") as f:
            for ch in g.iter_bytes():
                f.write(ch)
    usd = (body.get("usage") or {}).get("cost_in_usd_ticks", 0) / 1e10
    note(a.slug, {"kind": "video", "scene": a.scene, "sec": a.seconds, "usd": round(usd, 3)})
    log("сцена %d: оживлено за %.0f с, $%.2f" % (a.scene, time.time() - t0, usd))
    # контрольные кадры — Клод смотрит их своими глазами после анимации
    for tag, t in (("a", 0.3), ("b", a.seconds / 2.0), ("c", max(a.seconds - 0.4, 0.5))):
        run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", "%.2f" % t, "-i", out,
             "-frames:v", "1", "-vf", "scale=420:-1", "-q:v", "4",
             os.path.join(d, "prev", "anim%d%s.jpg" % (a.scene, tag))])
    log("  контрольные кадры: prev/anim%da.jpg, b, c" % a.scene)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["shoot", "approve", "status", "animate"])
    ap.add_argument("--slug", default="cur")
    ap.add_argument("--scene", type=int, default=0)
    ap.add_argument("--prompt", default="")
    ap.add_argument("--motion", default="Камера очень медленно приближается, лёгкое движение воздуха.")
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--pick", type=int, default=0)
    ap.add_argument("--seconds", type=int, default=6)
    a = ap.parse_args()
    {"shoot": cmd_shoot, "approve": cmd_approve,
     "status": cmd_status, "animate": cmd_animate}[a.stage](a)


if __name__ == "__main__":
    main()
