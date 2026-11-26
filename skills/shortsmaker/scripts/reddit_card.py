#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Карточки инфоповода и реакций из reddit-треда через .rss (HTML с VPS блокирован,
RSS открыт — тем же путём живёт новостной конвейер).

    python3 reddit_card.py both <thread_url> <post.html> <comments.html>

Один фетч .rss на обе карточки — реддит отдаёт 429 на частые запросы.

Дальше HTML скринится обычным news_shot.py по file://-адресу.
Это НАША карточка с реальными цитатами и подписью источника — не косплей реддита.
"""

import html
import re
import sys
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

def _cyr_share(t):
    letters = [c for c in t if c.isalpha()]
    if not letters:
        return 1.0
    return sum(1 for c in letters if "\u0400" <= c <= "\u04ff") / len(letters)


def translate(texts):
    """Мнения пользователей на карточках — по-русски (правило Гора 08-14).
    Английский остаётся только на скринах самих медиа. Переводит дешёвая
    non-reasoning через метер; при отказе честно оставляем оригинал."""
    need = [i for i, t in enumerate(texts) if _cyr_share(t) < 0.5]
    if not need:
        return texts
    import json as j
    import re as _re
    import urllib.request
    numbered = "\n".join("%d. %s" % (k + 1, texts[i]) for k, i in enumerate(need))
    body = j.dumps({"model": "grok-4.20-0309-non-reasoning", "max_tokens": 2200,
                    "messages": [{"role": "user", "content":
                        "Переведи реплики на живой разговорный русский, сохраняя тон, "
                        "сленг и резкость. Термины и названия железа оставляй как принято "
                        "в русском комьюнити. Верни СТРОГО JSON-массив строк в том же "
                        "порядке, без пояснений.\n\n" + numbered}]}).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:8650/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json",
                                          "X-Meter-Source": "shortsmaker"})
    try:
        with urllib.request.urlopen(req, timeout=150) as r:
            c = j.load(r)["choices"][0]["message"]["content"]
        m = _re.search(r"\[.*\]", c, _re.S)
        arr = j.loads(m.group(0))
        if len(arr) == len(need):
            out = list(texts)
            for k, i in enumerate(need):
                out[i] = str(arr[k])
            return out
    except Exception as e:
        print("perevod upal, ostavlyayu original:", str(e)[:80])
    return texts


CSS = """
<meta charset="utf-8">
<style>
  body { margin:0; background:#0B0E13; color:#F2F4F8;
         font-family:'DejaVu Sans','Noto Sans',sans-serif; width:480px; }
  .wrap { padding:34px 26px; }
  .src  { color:#E8B84B; font-size:15px; letter-spacing:.08em; margin-bottom:18px;
          text-transform:uppercase; }
  .title{ font-size:27px; font-weight:bold; line-height:1.25; margin-bottom:14px; }
  .body { color:#B8BFCB; font-size:17px; line-height:1.45; }
  .c    { background:#141922; border-left:4px solid #E8B84B; border-radius:8px;
          padding:14px 16px; margin-bottom:14px; }
  .a    { color:#8A93A3; font-size:13px; margin-bottom:6px; }
  .t    { font-size:18px; line-height:1.4; }
  .foot { color:#5A6270; font-size:13px; margin-top:20px; }
</style>
"""


def fetch_rss(url):
    import time
    u = url.rstrip("/") + "/.rss"
    req = urllib.request.Request(u, headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:
                time.sleep(25)
                continue
            raise
    raise SystemExit("rss ne otdalsya")


def entries(rss):
    out = []
    for e in re.findall(r"<entry>(.*?)</entry>", rss, re.S):
        author = re.search(r"<name>\s*/?u?/?(.*?)\s*</name>", e)
        title = re.search(r"<title>(.*?)</title>", e, re.S)
        content = re.search(r"<content[^>]*>(.*?)</content>", e, re.S)
        txt = ""
        if content:
            txt = html.unescape(html.unescape(content.group(1)))
            txt = re.sub(r"<blockquote>.*?</blockquote>", " ", txt, flags=re.S)
            txt = re.sub(r"<[^>]+>", " ", txt)
            txt = re.sub(r"submitted by.*$", "", txt, flags=re.S)
            txt = re.sub(r"\[link\]|\[comments\]|&#32;", " ", txt)
            txt = re.sub(r"\s+", " ", txt).strip()
        out.append({
            "author": html.unescape(author.group(1)) if author else "?",
            "title": html.unescape(html.unescape(title.group(1))).strip() if title else "",
            "text": txt,
        })
    return out


def subreddit(url):
    m = re.search(r"/r/([^/]+)/", url)
    return m.group(1) if m else "reddit"


def esc(s):
    return html.escape(s, quote=False)


def good_comment(c):
    t = c["text"]
    return 15 <= len(t) <= 320 and "http" not in t and c["author"] not in ("?", "AutoModerator")


def main():
    mode = sys.argv[1]
    if mode == "xquotes":
        import json as _json
        data = _json.load(open(sys.argv[2], encoding="utf-8"))
        cs = [c for c in data.get("quotes", []) if (c.get("text") or "").strip()][:4]
        if not cs:
            raise SystemExit("net citat")
        tr = translate([c["text"][:240] for c in cs])
        cs = [dict(c, text=t) for c, t in zip(cs, tr)]
        h = [CSS, '<div class="wrap">',
             '<div class="src">что говорят · X</div>']
        for c in cs:
            h.append('<div class="c"><div class="a">%s</div>'
                     '<div class="t">%s</div></div>'
                     % (esc(c.get("author", "?")), esc(c["text"][:240])))
        h.append('<div class="foot">реакции с X (Twitter)</div>')
        h.append('</div>')
        open(sys.argv[3], "w", encoding="utf-8").write("\n".join(h))
        print("ok x-card (%d citat)" % len(cs))
        return
    url = sys.argv[2]
    ee = entries(fetch_rss(url))
    if not ee:
        raise SystemExit("lenta pusta")
    sub = subreddit(url)

    def render_post(out):
        p = ee[0]
        tr = translate([p["title"][:160], p["text"][:500]])
        p = dict(p, title=tr[0], text=tr[1])
        h = [CSS, '<div class="wrap">',
             '<div class="src">обсуждение · r/%s</div>' % esc(sub),
             '<div class="title">%s</div>' % esc(p["title"][:160]),
             '<div class="body">%s</div>' % esc(p["text"][:500]),
             '<div class="foot">u/%s · reddit.com</div>' % esc(p["author"]),
             '</div>']
        open(out, "w", encoding="utf-8").write("\n".join(h))

    def render_comments(out):
        cs = [c for c in ee[1:] if good_comment(c)][:4]
        if not cs:
            raise SystemExit("net godnyh kommentov")
        tr = translate([c["text"][:240] for c in cs])
        cs = [dict(c, text=t) for c, t in zip(cs, tr)]
        h = [CSS, '<div class="wrap">',
             '<div class="src">что говорят · r/%s</div>' % esc(sub)]
        for c in cs:
            h.append('<div class="c"><div class="a">u/%s</div>'
                     '<div class="t">%s</div></div>' % (esc(c["author"]), esc(c["text"][:240])))
        h.append('<div class="foot">reddit.com · комментарии из обсуждения</div>')
        h.append('</div>')
        open(out, "w", encoding="utf-8").write("\n".join(h))

    if mode == "xquotes":
        pass  # obrabotano vyshe
    elif mode == "both":
        render_post(sys.argv[3])
        render_comments(sys.argv[4])
    elif mode == "post":
        render_post(sys.argv[3])
    else:
        render_comments(sys.argv[3])
    print("ok (%d zapisej)" % len(ee))


if __name__ == "__main__":
    main()
