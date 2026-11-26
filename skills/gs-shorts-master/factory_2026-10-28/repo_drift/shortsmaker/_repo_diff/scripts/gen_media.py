#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генерация визуала Гроком для shortsmaker. Запускать на VPS питоном hermes:

    /usr/local/lib/hermes-agent/venv/bin/python3 gen_media.py image "промпт" out.jpg
    /usr/local/lib/hermes-agent/venv/bin/python3 gen_media.py video "промпт" out.mp4 --duration 6
    /usr/local/lib/hermes-agent/venv/bin/python3 gen_media.py plan shots.json outdir/

Токен — OAuth подписки из ~/.hermes/auth.json, платный ключ не нужен.
Ссылки на результат временные: скачиваем сразу, в том же запуске.
"""

import argparse
import hashlib
import json
import os
import sys
import time
import uuid

sys.path.insert(0, "/usr/local/lib/hermes-agent")
os.chdir("/usr/local/lib/hermes-agent")

import httpx  # noqa: E402
from tools.xai_http import resolve_xai_http_credentials  # noqa: E402

IMAGE_MODEL = "grok-imagine-image-quality"
VIDEO_MODEL = "grok-imagine-video"
POLL_INTERVAL = 5
POLL_TIMEOUT = 240

CACHE = os.environ.get("SHORTSMAKER_CACHE", "/opt/shorts/scenes")
USAGE_LOG = os.environ.get("SHORTSMAKER_USAGE", "/opt/shorts/usage.jsonl")

# Ровно один вызов за раз. В xai_http нет ни семафора, ни backoff, ни обработки 429,
# а воркеры делят один OAuth-токен и устраивают гонку refresh.
MAX_PARALLEL = 1


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def creds():
    c = resolve_xai_http_credentials() or {}
    key = (c.get("api_key") or "").strip()
    if not key:
        raise SystemExit("нет учётки xAI: ни OAuth-токена, ни XAI_API_KEY")
    return key, (c.get("base_url") or "https://api.x.ai/v1").rstrip("/")


def headers(key, idempotent=False):
    h = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    if idempotent:
        h["x-idempotency-key"] = str(uuid.uuid4())
    return h


def note_usage(kind, model, seconds, body, path):
    """У imagine нет токенов — есть cost_in_usd_ticks и wall-clock."""
    try:
        ticks = ((body or {}).get("usage") or {}).get("cost_in_usd_ticks", 0)
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source": "shortsmaker",
            "kind": kind,
            "model": model,
            "seconds": round(seconds, 1),
            "usd": round(ticks / 1e10, 4),
            "path": path,
        }
        os.makedirs(os.path.dirname(USAGE_LOG), exist_ok=True)
        with open(USAGE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec["usd"]
    except Exception:
        return 0.0


def cache_path(kind, model, prompt, extra=""):
    h = hashlib.sha256(("%s|%s|%s|%s" % (kind, model, prompt, extra)).encode("utf-8")).hexdigest()[:16]
    return os.path.join(CACHE, kind, h)


def fetch(url, dest):
    with httpx.stream("GET", url, timeout=300, follow_redirects=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    return os.path.getsize(dest)


# ---------------------------------------------------------------- картинка

def gen_image(prompt, out, model=IMAGE_MODEL, use_cache=True,
              aspect=None, resolution=None):
    """aspect/resolution необязательны ради обратной совместимости: старые
    вызывающие ничего не передают и получают прежнее поведение. Банку футажа
    нужен высокий кадр 9:16 в 2k, иначе панорамировать в вертикаль не из чего."""
    cp = cache_path("image", model, prompt, "%s|%s" % (aspect or "", resolution or ""))
    if use_cache and os.path.exists(cp) and os.path.getsize(cp) > 10000:
        log("из кэша: %s" % os.path.basename(cp))
        with open(cp, "rb") as s, open(out, "wb") as d:
            d.write(s.read())
        return {"path": out, "usd": 0.0, "cached": True}

    key, base = creds()
    t0 = time.time()
    payload = {"model": model, "prompt": prompt, "n": 1}
    if aspect:
        payload["aspect_ratio"] = aspect
    if resolution:
        payload["resolution"] = resolution
    r = httpx.post(base + "/images/generations", headers=headers(key),
                   json=payload, timeout=300)
    if r.status_code != 200:
        raise SystemExit("картинка: HTTP %s %s" % (r.status_code, r.text[:300]))
    body = r.json()
    data = body.get("data") or []
    if not data:
        raise SystemExit("картинка: пустой ответ %s" % json.dumps(body)[:200])

    url = data[0].get("url") or data[0].get("public_url")
    if url:
        size = fetch(url, out)          # ссылка временная — качаем сразу
    else:
        import base64
        raw = base64.b64decode(data[0]["b64_json"])
        open(out, "wb").write(raw)
        size = len(raw)

    usd = note_usage("image", model, time.time() - t0, body, out)
    if use_cache:
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        with open(out, "rb") as s, open(cp, "wb") as d:
            d.write(s.read())
    log("картинка %s, %d Б, $%.3f" % (os.path.basename(out), size, usd))
    return {"path": out, "usd": usd, "cached": False}


# ---------------------------------------------------------------- видео

def gen_video(prompt, out, duration=6, aspect="9:16", resolution="720p",
              image_url=None, model=VIDEO_MODEL, use_cache=True):
    # image_url -> плагин сам маршрутизирует на grok-imagine-video-1.5
    cp = cache_path("video", model, prompt, "%s|%s|%s|%s" % (duration, aspect, resolution, image_url or ""))
    if use_cache and os.path.exists(cp) and os.path.getsize(cp) > 100000:
        log("из кэша: %s" % os.path.basename(cp))
        with open(cp, "rb") as s, open(out, "wb") as d:
            d.write(s.read())
        return {"path": out, "usd": 0.0, "cached": True}

    key, base = creds()
    payload = {"model": model, "prompt": prompt, "duration": duration,
               "aspect_ratio": aspect, "resolution": resolution}
    if image_url:
        payload["image_url"] = image_url

    t0 = time.time()
    r = httpx.post(base + "/videos/generations", headers=headers(key, idempotent=True),
                   json=payload, timeout=60)
    if r.status_code != 200:
        raise SystemExit("видео: HTTP %s %s" % (r.status_code, r.text[:300]))
    req_id = r.json().get("request_id")
    if not req_id:
        raise SystemExit("видео: ответ без request_id")
    log("задание %s, ждём (до %d с)" % (req_id[:8], POLL_TIMEOUT))

    elapsed, body = 0, {}
    while elapsed < POLL_TIMEOUT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        p = httpx.get("%s/videos/%s" % (base, req_id), headers=headers(key), timeout=30)
        p.raise_for_status()
        body = p.json()
        st = (body.get("status") or "").lower()
        if st == "done":
            break
        if st in {"failed", "error", "expired", "cancelled"}:
            raise SystemExit("видео: статус %s — %s" % (st, json.dumps(body)[:250]))
    else:
        raise SystemExit("видео: не уложилось в %d с" % POLL_TIMEOUT)

    video = body.get("video") or {}
    url = (body.get("file_output") or {}).get("public_url") or video.get("url")
    if not url:
        raise SystemExit("видео: готово, но ссылки нет — %s" % json.dumps(body)[:250])

    size = fetch(url, out)
    usd = note_usage("video", model, time.time() - t0, body, out)
    if use_cache:
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        with open(out, "rb") as s, open(cp, "wb") as d:
            d.write(s.read())
    log("видео %s, %d Б, %.0f с генерации, $%.3f" % (os.path.basename(out), size, time.time() - t0, usd))
    return {"path": out, "usd": usd, "public_url": url, "cached": False}


# ---------------------------------------------------------------- план

def run_plan(plan_file, outdir):
    """shots.json: [{"kind":"image|video","prompt":"...","duration":6}, ...]

    Пошотный фолбэк: упавший видеошот подменяется картинкой той же сцены —
    ролик собирается всё равно, просто беднее.
    """
    shots = json.load(open(plan_file, encoding="utf-8"))
    os.makedirs(outdir, exist_ok=True)
    results, total = [], 0.0

    for i, shot in enumerate(shots):
        kind = shot.get("kind", "image")
        prompt = shot["prompt"]
        try:
            if kind == "video":
                out = os.path.join(outdir, "shot%02d.mp4" % i)
                res = gen_video(prompt, out, duration=shot.get("duration", 6),
                                image_url=shot.get("image_url"))
            else:
                out = os.path.join(outdir, "shot%02d.jpg" % i)
                res = gen_image(prompt, out)
        except SystemExit as e:
            log("шот %d упал (%s), падаю на картинку" % (i, str(e)[:120]))
            try:
                out = os.path.join(outdir, "shot%02d.jpg" % i)
                res = gen_image(prompt, out)
                res["degraded"] = True
            except SystemExit as e2:
                log("шот %d не спасён: %s" % (i, str(e2)[:120]))
                results.append({"index": i, "failed": True})
                continue
        res["index"] = i
        res["kind"] = kind
        results.append(res)
        total += res.get("usd", 0.0)

    manifest = os.path.join(outdir, "manifest.json")
    json.dump({"shots": results, "usd_total": round(total, 3)},
              open(manifest, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = len([r for r in results if not r.get("failed")])
    log("готово %d из %d, потрачено $%.2f, манифест %s" % (ok, len(shots), total, manifest))
    return 0 if ok == len(shots) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["image", "video", "plan"])
    ap.add_argument("arg1")
    ap.add_argument("arg2")
    ap.add_argument("--duration", type=int, default=6)
    ap.add_argument("--aspect", default="9:16")
    ap.add_argument("--resolution", default="720p", choices=["480p", "720p"])
    ap.add_argument("--image-url", default=None)
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args()

    if a.mode == "plan":
        return run_plan(a.arg1, a.arg2)
    if a.mode == "image":
        gen_image(a.arg1, a.arg2, use_cache=not a.no_cache)
    else:
        gen_video(a.arg1, a.arg2, duration=a.duration, aspect=a.aspect,
                  resolution=a.resolution, image_url=a.image_url,
                  use_cache=not a.no_cache)
    return 0


if __name__ == "__main__":
    sys.exit(main())
