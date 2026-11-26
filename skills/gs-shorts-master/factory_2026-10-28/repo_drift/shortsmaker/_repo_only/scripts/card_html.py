#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Карточка реакции в дизайне «Терминал», рендер через браузер.

    /opt/hermes/venv/bin/python3 card_html.py <cards.json> <outdir>

ЗАЧЕМ БРАУЗЕР, А НЕ FFMPEG. Прежняя карточка рисовалась drawtext и была стеной:
четыре реплики мелким шрифтом на восемь секунд. Дизайн собран отдельно как
полотно, и повторять его текстовыми фильтрами — терять кернинг, перенос и
шрифт. Браузер уже стоит, отдаёт ровно ту вёрстку, что утверждена.

ГЛАВНОЕ ПРАВИЛО ФОРМАТА: ОДНА РЕПЛИКА НА КАДР. Не четыре. Стена текста была
настоящей причиной, почему карточка выглядела дёшево.

Вход: json со списком {"author": "...", "text": "...", "date": "02.09.2026"}.
Выход: <outdir>/card0.png ... 1080x1920 каждая.
"""
import io
import json
import os
import sys

sys.path.insert(0, "/opt/shorts")

ACCENT = "#E8A33D"

HTML = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap">
<style>
  * { box-sizing: border-box; }
  body { margin:0; width:1080px; height:1920px; background:#0A0C0B;
         font-family:'JetBrains Mono',ui-monospace,monospace; overflow:hidden;
         display:flex; flex-direction:column; justify-content:center; padding:0 52px; }
  .scan { position:absolute; inset:0; opacity:.5;
          background-image:linear-gradient(rgba(255,255,255,.028) 1px, transparent 1px);
          background-size:100% 4px; }
  .win { position:relative; display:flex; flex-direction:column; }
  .bar { display:flex; align-items:center; gap:20px; padding:0 30px; height:76px;
         background:#161A18; border:2px solid ACCENT; border-bottom:none; }
  .bar .dots { display:flex; gap:9px; }
  .bar .dots i { width:13px; height:13px; border-radius:50%; background:#3A443F; display:block; }
  .bar .src { color:#8B968F; font-size:27px; letter-spacing:.04em; flex-grow:1; }
  .bar .tag { color:ACCENT; font-size:25px; font-weight:700; letter-spacing:.16em; }
  .body { border:2px solid ACCENT; background:#101413; padding:70px 62px 60px;
          display:flex; flex-direction:column; gap:44px; }
  .who { display:flex; align-items:baseline; gap:16px; }
  .who b { color:ACCENT; font-size:34px; font-weight:700; }
  .who span { color:#C9D3CD; font-size:32px; font-weight:500; }
  .quote { margin:0; color:#F2F6F4; font-weight:500; line-height:1.34; text-wrap:pretty; }
  .foot { display:flex; align-items:center; gap:18px; }
  .foot i { width:15px; height:34px; background:ACCENT; display:block; }
  .foot span { color:#6E7A74; font-size:27px; letter-spacing:.03em; }
  .rule { display:flex; gap:3px; margin-top:3px; }
  .rule i { height:10px; display:block; }
</style></head><body>
<div class="scan"></div>
<div class="win">
  <div class="bar"><div class="dots"><i></i><i></i><i></i></div>
    <div class="src">SRC</div><div class="tag">РЕАКЦИЯ</div></div>
  <div class="body">
    <div class="who"><b>&gt;</b><span>AUTHOR</span></div>
    <p class="quote" style="font-size:FSpx">TEXT</p>
    <div class="foot"><i></i><span>DATE</span></div>
  </div>
  <div class="rule"><i style="flex-grow:1;background:ACCENT"></i>
    <i style="width:120px;background:#2A322E"></i><i style="width:44px;background:#2A322E"></i></div>
</div>
</body></html>"""


def size_for(text):
    """Кегль от длины: длинная реплика не должна ползти за край окна."""
    n = len(text)
    return 82 if n <= 90 else (74 if n <= 140 else (64 if n <= 200 else 54))


def main():
    cards = json.load(io.open(sys.argv[1], encoding="utf-8"))
    outdir = sys.argv[2]
    os.makedirs(outdir, exist_ok=True)

    import glob
    from playwright.sync_api import sync_playwright
    exe = (glob.glob("/root/.cache/ms-playwright/chromium-*/chrome-linux*/chrome") + [None])[0]

    made = []
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox"], executable_path=exe)
        pg = b.new_page(viewport={"width": 1080, "height": 1920},
                        device_scale_factor=1, color_scheme="dark")
        for i, c in enumerate(cards):
            txt = (c.get("text") or "").strip()
            html = (HTML.replace("ACCENT", ACCENT)
                        .replace("SRC", c.get("src", "x.com"))
                        .replace("AUTHOR", c.get("author", ""))
                        .replace("FS", str(size_for(txt)))
                        .replace("TEXT", txt)
                        .replace("DATE", c.get("date", ""))
)
            f = os.path.join(outdir, "_c%d.html" % i)
            io.open(f, "w", encoding="utf-8").write(html)
            pg.goto("file://" + f, wait_until="load", timeout=30000)
            pg.wait_for_timeout(1200)          # даём шрифту доехать
            out = os.path.join(outdir, "card%d.png" % i)
            pg.screenshot(path=out)
            made.append(out)
            print("карточка %s (%d знаков, кегль %d)" % (out, len(txt), size_for(txt)), flush=True)
            os.remove(f)
        b.close()
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
