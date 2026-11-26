#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ПОКАДРОВЫЙ ГЕЙТ (требование Гора 08-21).

Режет готовый ролик на кадры раз в 1.5 сек и КАЖДЫЙ смотрит vision-моделью:
нет ли постороннего/недопустимого контента (реклама лекарств, эротика, чужие
бренды-заглушки, мем-дефект, не по теме железа). Один плохой кадр — ролик не
проходит, exit != 0, в телеграм не уходит.

    frame_gate.py <video.mp4> "<тема ролика>"

exit 0 = чисто; exit 1 = найден дефектный кадр (печатает какой и почему).
"""
import base64
import subprocess
import sys
import time

sys.path.insert(0, "/usr/local/lib/hermes-agent")
import os
os.chdir("/usr/local/lib/hermes-agent")
import httpx  # noqa: E402
from tools.xai_http import resolve_xai_http_credentials  # noqa: E402

STEP = 1.5  # секунды между кадрами


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def creds():
    c = resolve_xai_http_credentials() or {}
    return c["api_key"], (c.get("base_url") or "https://api.x.ai/v1").rstrip("/")


def duration(v):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", v], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL)
    return float(r.stdout.strip() or 0)


def grab(v, t, out):
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", "%.2f" % t,
                    "-i", v, "-frames:v", "1", "-vf", "scale=360:-1", "-q:v", "5", out],
                   stdin=subprocess.DEVNULL, capture_output=True)


def judge(png, theme, key, base):
    q = ("Это кадр рекламного ролика про компьютерное железо. Тема ролика: «%s».\n"
         "Ответь СТРОГО одним словом ДА, если на кадре есть ХОТЬ ЧТО-ТО из списка:\n"
         "- реклама или упаковка ЛЕКАРСТВ, БАДов, интимных/медицинских товаров;\n"
         "- эротика, обнажёнка, интимная тематика;\n"
         "- контент НЕ про компьютерное железо и не по теме ролика;\n"
         "- сгоревшая/повреждённая/бракованная деталь;\n"
         "- рекламный баннер поверх контента, всплывашка, «Реклама 18+».\n"
         "Иначе ответь НЕТ. Только одно слово." % theme[:120])
    b64 = base64.b64encode(open(png, "rb").read()).decode()
    r = httpx.post(base + "/chat/completions",
                   headers={"Authorization": "Bearer " + key,
                            "Content-Type": "application/json"},
                   json={"model": "grok-4.20-0309-non-reasoning",
                         "messages": [{"role": "user", "content": [
                             {"type": "image_url",
                              "image_url": {"url": "data:image/jpeg;base64," + b64}},
                             {"type": "text", "text": q}]}],
                         "max_tokens": 8}, timeout=120)
    ans = r.json()["choices"][0]["message"]["content"].strip().upper()
    # ДА = дефект найден
    return ("ДА" in ans) and not ans.startswith("НЕТ"), ans


def main():
    v, theme = sys.argv[1], sys.argv[2]
    key, base = creds()
    dur = duration(v)
    n = max(int(dur / STEP), 1)
    log("покадровый гейт: %.1f сек, %d кадров" % (dur, n))
    bad = []
    for i in range(n):
        t = min(i * STEP + 0.3, dur - 0.2)
        png = "/tmp/fg_%d.jpg" % i
        grab(v, t, png)
        try:
            defect, ans = judge(png, theme, key, base)
        except Exception as e:
            log("  t=%.1f: судья упал (%s) — считаю подозрительным" % (t, str(e)[:50]))
            defect, ans = True, "СБОЙ"
        mark = "БРАК" if defect else "ок"
        log("  t=%4.1f  %s  (%s)" % (t, mark, ans[:20]))
        if defect:
            bad.append((t, ans))
    print("")
    if bad:
        log("ГЕЙТ НЕ ПРОЙДЕН: %d дефектных кадров" % len(bad))
        for t, a in bad:
            log("  на t=%.1f: %s" % (t, a[:40]))
        sys.exit(1)
    log("ГЕЙТ ПРОЙДЕН: все %d кадров чистые" % n)
    sys.exit(0)


if __name__ == "__main__":
    main()
