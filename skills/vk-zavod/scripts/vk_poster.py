# -*- coding: utf-8 -*-
"""ВК-очередь ИИ-завода GSPC: сбор -> подготовка -> публикация. Без рук, с гейтами.

Разведка 18.09.2026: docs/research/vk/{api,law,growth,factory,community}.md.

Режимы (переменные в /opt/shorts/vk.env):
- VK_AUTO=1 и есть ключ админа (vk_user.json) - сам ставит в отложку ВК через wall.post;
- VK_AUTO=0 (по умолчанию) - готовый пакет «текст + файл» уходит в группу GSPC,
  публикует человек; нужен, пока ВК не выдал приложению право wall;
- VK_STORIES=1 и есть ключ сообщества - первые 15 с каждого клипа уходят историей
  (ключ сообщества это умеет официально, без одобрения ВК).
Стоп-кран: файл /opt/shorts/vk.pause (vk_poster.py pause / resume).

Источники: клипы из shorts_log (черновики, прошедшие все гейты), ручные клипы
серий (add-clip), статьи сайта (RSS), «сборка недели» из фида витрины (YML).
Каждый текст пишет модель под правила ВК, затем детерминированные гейты и
обязательный фактчекер (fact_gate.py). Без фактчекера пост не уходит никуда.

    python3 vk_poster.py run [--dry]         # collect + prepare + publish
    python3 vk_poster.py collect|prepare|publish [--dry]
    python3 vk_poster.py add-clip <mp4> --theme theme.json --title "..."
    python3 vk_poster.py status | pause | resume | veto <id>
"""
import argparse
import hashlib
import html
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/opt/shorts")
sys.path.insert(0, "/opt/shorts/vk")


def _load_env(path="/opt/shorts/vk.env"):
    """Крон не читает vk.env: модели писателя и судьи берём оттуда до того, как прочитаны настройки ниже."""
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


_load_env()

DB = os.environ.get("VK_DB", "/opt/shorts/vk.db")
PAUSE = "/opt/shorts/vk.pause"
TMP = "/opt/shorts/vk/tmp"
PROXY = os.environ.get("SHORTSMAKER_PROXY", "http://127.0.0.1:8650/v1/chat/completions")
WRITER = os.environ.get("VK_WRITER_MODEL", "grok-4.3")
RSS = "https://gspc-lab.pro/rss.xml"
YML = "https://gspc-lab.pro/yandex-business.yml"
SITE = "https://gspc-lab.pro"
MSK = timezone(timedelta(hours=3))

# growth.md §2: 1 пост + 1 клип в сутки, слоты МСК, ночью не публикуем
SLOTS = {"weekday": ["18:30", "20:00"], "weekend": ["19:00", "20:00"]}
LIMITS = {"clip": 1, "post": 1}
SALES_SHARE = 0.2                     # продающих не больше 1 из 5 (growth.md §3)
SIGN = "Golden Sample PCs · мастерская сборки и тюнинга ПК · Москва"
PREP_MAX = int(os.environ.get("VK_PREP_MAX", "3"))   # подготовок за прогон: ВК берёт 2 единицы в сутки
EXPIRE_DAYS = 5                                      # не подготовлено за 5 дней - тема остыла

LOG = []


def log(m):
    line = time.strftime("[%H:%M:%S] ") + m
    LOG.append(line)
    print(line, flush=True)


# ---------------------------------------------------------------- база

def db():
    con = sqlite3.connect(DB, timeout=30)
    con.execute("""CREATE TABLE IF NOT EXISTS vk_queue (
        id INTEGER PRIMARY KEY, kind TEXT, ext_id TEXT, created TEXT, status TEXT,
        title TEXT, src TEXT, text TEXT, media TEXT, reason TEXT, slot TEXT,
        post_id INTEGER, sales INTEGER DEFAULT 0, UNIQUE(kind, ext_id))""")
    return con


def enqueue(con, kind, ext_id, title, src, media, sales=0):
    try:
        con.execute("INSERT INTO vk_queue (kind, ext_id, created, status, title, src, media, sales) "
                    "VALUES (?,?,?,?,?,?,?,?)", (kind, str(ext_id), now_msk().isoformat(), "new", title[:200],
                                                 json.dumps(src, ensure_ascii=False), json.dumps(media), sales))
        con.commit()
        log("в очередь: %s %s «%s»" % (kind, ext_id, title[:60]))
        return True
    except sqlite3.IntegrityError:
        return False


def now_msk():
    return datetime.now(MSK)


# ---------------------------------------------------------------- сбор

def collect_clips(con):
    """Черновики ночного конвейера за 3 дня: они прошли фактчекер и три гейта кадра."""
    try:
        import build_short as bs
        raw = bs.sql("""SELECT row_to_json(t) FROM (SELECT s.id, s.news_id, s.theme, s.script_json, s.video_path,
            COALESCE(NULLIF(n.translated_title,''), n.title) AS title,
            left(COALESCE(NULLIF(n.translated_description,''), n.description, ''), 3000) AS source_text, n.link
            FROM shorts_log s LEFT JOIN news n ON n.id = s.news_id
            WHERE s.status = 'draft' AND s.video_path IS NOT NULL
              AND s.created_at > now() - interval '3 days' ORDER BY s.id) t;""")
    except (Exception, SystemExit) as e:
        log("клипы: база недоступна (%s)" % str(e)[:80])
        return
    for line in (raw or "").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        sc = r.get("script_json") or {}
        if isinstance(sc, str):
            sc = json.loads(sc)
        voice = " ".join(re.sub(r"<[^>]+>", "", c.get("voice", "")) for c in sc.get("cards", []))
        src = {"title": r.get("title") or r.get("theme"), "source_text": r.get("source_text") or "",
               "link": r.get("link") or "", "voice": voice, "caption": sc.get("tg_caption", ""),
               "ext_credits": sc.get("ext_credits") or []}
        enqueue(con, "clip", "shorts_log:%s" % r["id"], src["title"] or "ролик", src, [r["video_path"]])


def page_text(link, cap=4000):
    """Текст статьи со страницы сайта (<main>): в RSS только краткое описание, и посты по нему выходили
    огрызками по 120-280 знаков (01.10). Не открылась страница - пусто, остаётся описание."""
    site = urllib.parse.urlparse(SITE).hostname
    if urllib.parse.urlparse(link).hostname != site:  # только наш сайт: префикс пропускал gspc-lab.pro.evil.ru
        return ""
    try:
        with urllib.request.urlopen(urllib.request.Request(link, headers={"User-Agent": "gspc-vk/1.0"}),
                                    timeout=30) as r:
            if urllib.parse.urlparse(r.geturl()).hostname != site:   # редирект на чужой хост
                return ""
            raw = r.read(2 * 1024 * 1024).decode("utf-8", "replace")
    except Exception:
        return ""
    m = re.search(r"<main\b.*?</main>", raw, re.S)
    body = re.sub(r"<(script|style|svg|nav|footer)\b.*?</\1>", " ", m.group(0) if m else "", flags=re.S)
    body = html.unescape(re.sub(r"<[^>]+>", " ", body))
    return " ".join(body.split())[:cap]


def collect_guard(con):
    """Темы Grok Bot «Сторож железа» из ящика botdrop (guard_inbox.py): драйверы, BIOS, прошивки - в ВК."""
    try:
        import guard_inbox
        vk, _, commit = guard_inbox.harvest(log=log)
        # одна страница заметок вендора = один пост: бот дробит релиз на темы и повторяет его в каждом отчёте
        rel = {}
        for t in vk:
            rel.setdefault(guard_inbox.release_key(t), []).append(t)
        for key, ts in rel.items():
            head = dict(ts[0])
            if len(ts) > 1:
                head["fact"] = "; ".join(dict.fromkeys(x["fact"] for x in ts))[:1200]
                head["numbers"] = list(dict.fromkeys(n for x in ts for n in x["numbers"]))[:12]
            enqueue(con, "post", "guard:%s" % key, ts[0]["fact"][:160],
                    {"title": ts[0]["fact"][:160], "link": head["source_url"],
                     "source_text": guard_inbox.vk_material(head), "kind": "guard"}, [])
        commit()                                      # письма прочитаны только после постановки в очередь
    except Exception as e:
        log("сторож: ящик не разобран (%s)" % str(e)[:100])


def collect_articles(con):
    """Статьи и ответы мастера сайта: лучший источник для стены (factory.md §8)."""
    try:
        x = urllib.request.urlopen(urllib.request.Request(RSS, headers={"User-Agent": "gspc-vk/1.0"}),
                                   timeout=60).read()
        root = ET.fromstring(x)
    except Exception as e:
        log("статьи: RSS недоступен (%s)" % str(e)[:80])
        return
    for it in root.iter("item"):
        guid = (it.findtext("guid") or it.findtext("link") or "").strip()
        title = html.unescape(it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = html.unescape(re.sub(r"<[^>]+>", " ", it.findtext("description") or "")).strip()
        pub = it.findtext("pubDate") or ""
        if not guid or not title:
            continue
        try:
            age = (datetime.now(timezone.utc) - datetime.strptime(pub[:25].strip(), "%a, %d %b %Y %H:%M:%S")
                   .replace(tzinfo=timezone.utc)).days
        except ValueError:
            age = 0
        if age > 14:
            continue
        row = con.execute("SELECT id, status, src FROM vk_queue WHERE kind='post' AND ext_id=?",
                          ("rss:%s" % guid,)).fetchone()
        if row:
            # в очереди с одним описанием из RSS (до 01.10) и ещё не готовилась - подложить текст страницы
            old = json.loads(row[2] or "{}")
            if row[1] == "new" and len(old.get("source_text", "")) < 600 and link.startswith(SITE):
                full = page_text(link)
                if len(full) > len(old.get("source_text", "")):
                    old["source_text"] = full
                    con.execute("UPDATE vk_queue SET src=? WHERE id=?", (json.dumps(old, ensure_ascii=False), row[0]))
                    con.commit()
            continue                                  # уже в очереди: второй раз не ставим
        full = page_text(link) if link.startswith(SITE) else ""
        enqueue(con, "post", "rss:%s" % guid, title, {"title": title, "link": link,
                                                      "source_text": full if len(full) > len(desc) else desc,
                                                      "kind": "article"}, [])


def collect_build(con):
    """«Сборка недели» из фида витрины: настоящие фото, цена в рублях с датой. Раз в неделю."""
    week = now_msk().strftime("%G-W%V")
    if con.execute("SELECT 1 FROM vk_queue WHERE kind='post' AND ext_id LIKE ?", ("build:%s:%%" % week,)).fetchone():
        return
    try:
        x = urllib.request.urlopen(urllib.request.Request(YML, headers={"User-Agent": "gspc-vk/1.0"}),
                                   timeout=60).read()
        root = ET.fromstring(x)
    except Exception as e:
        log("витрина: фид недоступен (%s)" % str(e)[:80])
        return
    used = {r[0] for r in con.execute("SELECT ext_id FROM vk_queue WHERE ext_id LIKE 'build:%'")}
    for off in root.iter("offer"):
        oid = off.get("id") or ""
        name = (off.findtext("name") or "").strip()
        pic = (off.findtext("picture") or "").strip()
        price = (off.findtext("price") or "").strip()
        if not (oid and name and price and pic) or "/covers/" in pic:
            continue                           # только настоящие фото, без ИИ-обложек
        if any(u.endswith(":" + oid) for u in used):
            continue
        desc = html.unescape(re.sub(r"<[^>]+>", " ", off.findtext("description") or "")).strip()
        src = {"title": name, "source_text": "%s. Цена %s рублей на %s. %s" % (name, price,
                                                                          now_msk().strftime("%d.%m.%Y"), desc),
               "link": (off.findtext("url") or "").strip(), "price": price, "kind": "build"}
        enqueue(con, "post", "build:%s:%s" % (week, oid), name, src, [pic], sales=1)
        return


# ---------------------------------------------------------------- подготовка

RULES = """Ты ведёшь сообщество ВКонтакте мастерской Golden Sample PCs (Москва): сборка и тюнинг ПК.
Напиши текст %s по материалу ниже. Правила ВК и мастерской:
- первые 140 знаков - суть: что случилось или что это, с цифрой из материала, если она там есть;
- %s знаков всего, 2-4 коротких абзаца, тон «как с другом», без канцелярита и без капса;
- НИКАКИХ ссылок и адресов сайтов в тексте, никаких упоминаний Telegram, YouTube, TikTok, Rutube, Дзена, @ников;
- числа, модели, цены и даты - ТОЛЬКО из материала; нет в материале - не пиши; цена только в рублях;
- без превосходных степеней («лучший», «самый», «ниже рыночных»), без «купи», «успей», «только сегодня»;
- каждое предложение несёт факт из материала; без пустых оценок («ситуация плохая», «стало хуже», «украсит
  любой интерьер») и без повтора одной мысли разными словами;
- без прогноза цен и без совета, когда покупать и куда девать деньги (регламент мастерской);
- никаких зарубежных магазинов, цен в долларах или евро, VPN, обхода блокировок;
- одно целевое действие в конце (например «напишите нам в сообщения» или «какой вариант взяли бы вы?»);
- в конце %s хэштега по теме через пробел.
Верни строго JSON: {"text": "..."}.

МАТЕРИАЛ:
%s"""

MENTIONS = re.compile(r"(?i)(telegram|t\.me|телеграм|youtube|youtu\.be|ютуб|tiktok|тикток|rutube|рутуб|дзен|"
                      r"https?://|www\.|\.ru\b|\.com\b|\.pro\b|@\w)")
PUSHY = re.compile(r"(?i)(ниже рыночн|лучш|самы[йхм]|купи|успей|только сегодня|скидк\w* до|распродаж|"
                   r"гарантия 3 года на все|за 24 часа)")
MONEY = re.compile(r"(\$|€|долл|евро|usd|eur)", re.I)
# 01.10: материал «Сторожа железа» полон цен Регарда и Ситилинка - в сообществе мастерской это реклама конкурента
STORES = re.compile(r"(?i)(?<![\w-])(regard(\.ru)?|регард\w*|citilink(\.ru)?|ситилинк\w*|dns-shop(\.ru)?|днс|"
                    r"xcom-shop(\.ru)?|никс|nix\.ru|ozon(\.ru)?|озон\w*|wildberries|вайлдберриз\w*|м\.видео|"
                    r"эльдорадо|яндекс маркет\w*|онлайн трейд\w*)(?![\w-])")


def ask(prompt, max_tokens=1200):
    body = json.dumps({"model": WRITER, "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tokens}).encode("utf-8")
    req = urllib.request.Request(PROXY, data=body, headers={"Content-Type": "application/json",
                                                            "X-Meter-Source": "vk-poster"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"]


def text_gates(text, kind, rise=False):
    """Детерминированные правила ВК (growth.md §3-7, law.md). Пусто = годен.
    rise=True - тема про подорожание: регламент 29.09 строже (никакого «когда покупать»)."""
    t = text.strip()
    body = re.sub(r"(#\S+\s*)+$", "", t).strip()
    tags = re.findall(r"#\S+", t)
    lo, hi = (150, 600) if kind == "clip" else (250, 900)   # 01.10: 300 резало почти каждый второй пост Грока
    bad = []
    if not lo <= len(body) <= hi + 150:
        bad.append("длина %d вне %d-%d" % (len(body), lo, hi))
    if MENTIONS.search(t):
        bad.append("ссылка или чужая площадка: %s" % MENTIONS.search(t).group(0))
    if PUSHY.search(t):
        bad.append("давление или превосходная степень: %s" % PUSHY.search(t).group(0))
    if MONEY.search(t):
        bad.append("валюта: %s" % MONEY.search(t).group(0))
    if STORES.search(t):
        bad.append("магазин-конкурент в тексте: %s" % STORES.search(t).group(0))
    if len(tags) > (3 if kind == "clip" else 2):
        bad.append("хэштегов %d" % len(tags))
    caps = [w for w in re.findall(r"\b[А-ЯЁ]{5,}\b", t)]
    if len(caps) > 1:
        bad.append("капс: %s" % ", ".join(caps[:3]))
    try:
        import build_short as bs
        w = bs.dirty(t)
        if w:
            bad.append("стоплист: %s" % w)
    except Exception:
        pass
    import price_rule      # регламент подорожания 29.09: без совета про деньги и прогноза цен, как во всех конвейерах
    w = price_rule.money_talk(t, strict=rise)
    if w:
        bad.append("регламент подорожания (без прогноза цен и совета, когда покупать): %s" % w)
    return bad


def local_judge(text, mat, kind, what, size, ntags, rise=False):
    """Судья дома (sudya, 5090) узкими линзами после писателя-Грока: reject по числам и ценам - пост не выходит,
    fix - одна правка писателем по цитатам и повтор только упавших линз. Дом молчит - судит подписка."""
    import vk_judge
    found, who = vk_judge.judge(text, mat, log=lambda m: log(m))
    hard, fixes = vk_judge.verdict(found)
    log("  судья: %s, находок %d (жёстких %d)" % (who, len(found), len(hard)))
    if hard:
        raise SystemExit("судья (%s): %s" % (who, vk_judge.fix_note(hard)))
    if not fixes:
        return text, "проверил судья: %s, замечаний нет" % who
    raw = ask(RULES % (what, size, ntags, mat) + "\n\nТВОЙ ПРОШЛЫЙ ТЕКСТ:\n" + text +
              "\n\nПРАВКА РЕДАКТОРА (исправь только это, остальное оставь): " + vk_judge.fix_note(fixes))
    m = re.search(r"\{.*\}", raw, re.S)
    new = json.loads(m.group(0)).get("text", "").strip() if m else ""
    if not new or text_gates(new, kind, rise):
        log("  правка по судье не прошла гейты, оставляю прежний текст")
        return text, "проверил судья: %s, правка не легла, замечаний %d" % (who, len(fixes))
    again, who2 = vk_judge.judge(new, mat, log=lambda m: log(m), keys=sorted({f["lens"] for f in fixes} | {"numbers"}))
    # после правки числа и цены строже: любая оставшаяся претензия по ним - пост не выходит
    hard2 = [f for f in again if f["lens"] in vk_judge.HARD]
    fixes2 = [f for f in again if f not in hard2]
    if hard2:
        raise SystemExit("судья после правки (%s): %s" % (who2, vk_judge.fix_note(hard2)))
    log("  правка по судье: было замечаний %d, стало %d" % (len(fixes), len(fixes2)))
    return new, "проверил судья: %s, правок %d, осталось %d" % (who, len(fixes), len(fixes2))


def fact_check(text, src, title):
    """Обязательный фактчекер завода. Абзацы идут как подписи: неисправимый абзац
    снимается; если снят первый (суть) - пост отклоняется целиком."""
    import fact_gate
    fact_gate.REPORT_WORK = "/opt/shorts/vk/fact_gate.json"   # не затирать отчёт ночной сборки
    body = re.sub(r"(#\S+\s*)+$", "", text).strip()
    tags = " ".join(re.findall(r"#\S+", text))
    paras = [p.strip() for p in body.split("\n") if p.strip()]
    cards = [{"caption": p} for p in paras]
    theme = {"id": 0, "title": src.get("title") or title, "source_text": src.get("source_text", ""),
             "link": src.get("link", ""), "published_at": now_msk().strftime("%d.%m.%Y")}
    if src.get("voice"):
        theme["source_text"] += "\nТЕКСТ РОЛИКА (прошёл фактчекер конвейера): " + src["voice"]
    fact_gate.check(cards, theme, None, script={}, log=lambda m: log("  " + m.strip()))
    kept = [c["caption"] for c in cards]
    if not kept or not kept[0]:
        raise SystemExit("фактчекер снял первый абзац")
    out = "\n\n".join(p for p in kept if p)
    return out + ("\n\n" + tags if tags else "")


def prepare(con, dry=False):
    old = (now_msk() - timedelta(days=EXPIRE_DAYS)).isoformat()
    con.execute("UPDATE vk_queue SET status='expired' WHERE status='new' AND created < ?", (old,))
    con.commit()
    # 01.10: статьи сайта первыми (материал с проверенными фактами), клип - один за прогон: у новостных клипов
    # материал тонкий, после фактчекера от текста оставалось «приводим цифры» без цифр
    # одна тема «Сторожа железа» за прогон впереди (факт с цифрой и ссылкой на вендора), дальше статьи и сборка
    # недели: всегда-первые темы бота вытесняли бы статьи до истечения (ревью 01.10)
    rows = con.execute("SELECT id, kind, title, src, sales FROM vk_queue WHERE status='new' AND kind='post' "
                       "AND ext_id LIKE 'guard:%' ORDER BY id DESC LIMIT 1").fetchall()
    rows += con.execute("SELECT id, kind, title, src, sales FROM vk_queue WHERE status='new' AND kind='post' "
                        "AND ext_id NOT LIKE 'guard:%' ORDER BY sales DESC, id DESC LIMIT ?",
                        (max(PREP_MAX - 1 - len(rows), 1),)).fetchall()
    rows += con.execute("SELECT id, kind, title, src, sales FROM vk_queue WHERE status='new' AND kind='clip' "
                        "ORDER BY id DESC LIMIT 1").fetchall()
    for qid, kind, title, src, sales in rows:
        src = json.loads(src)
        try:
            import topics
            bad, why = topics.banned(src.get("title", ""), src.get("source_text", ""), None)
            if bad:
                raise SystemExit("полка: %s" % why)
            what = "описания клипа" if kind == "clip" else ("продающего поста о сборке" if sales else "поста")
            size = "250-600" if kind == "clip" else "400-900"
            ntags = "2-3" if kind == "clip" else "1-2"
            mat = "ЗАГОЛОВОК: %s\nМАТЕРИАЛ: %s\n%s" % (src.get("title", ""), src.get("source_text", "")[:3000],
                                                      ("ТЕКСТ РОЛИКА: " + src["voice"]) if src.get("voice") else "")
            import price_rule
            rise = price_rule.is_rise(src.get("title", ""), src.get("source_text", "")[:2000])
            text, bad = "", []
            for attempt in range(2):
                raw = ask(RULES % (what, size, ntags, mat) + (("\n\nПРАВКА: " + "; ".join(bad)) if bad else ""))
                m = re.search(r"\{.*\}", raw, re.S)
                text = json.loads(m.group(0)).get("text", "").strip() if m else ""
                bad = text_gates(text, kind, rise)
                if not bad:
                    break
            if bad:
                raise SystemExit("гейты текста: %s" % "; ".join(bad))
            text, note = local_judge(text, mat, kind, what, size, ntags, rise)
            text = fact_check(text, src, title)
            # 01.10: правки фактчекера ломали связность («цифры подтверждают стало хуже», три повтора «хуже»).
            # После него судья смотрит связность и начало; рассыпался - одна починка писателем только помеченных
            # предложений, снова фактчекер и судья; не помогло - не публикуем, слотов хватает.
            import vk_judge
            after, who = vk_judge.judge(text, mat, log=lambda m: log(m), keys=["coherence", "lead"])
            # дописывать только слишком короткий текст: длинный «дописка» не лечит (ревью 01.10)
            body_len = len(re.sub(r"(#\S+\s*)+$", "", text.strip()).strip())
            lo_len = 150 if kind == "clip" else 250
            short = ["длина %d меньше %d" % (body_len, lo_len)] if body_len < lo_len else []
            if after or short:
                # фактчекер снимает неподтверждённые строки - текст бывает короче нормы: дописать фактами из материала
                task = ("ПОЧИНИ ТОЛЬКО ЭТИ ПРЕДЛОЖЕНИЯ: удали их или перепиши фактом из материала, новых фактов "
                        "не добавляй, остальное оставь как есть: " + vk_judge.fix_note(after)) if after else ""
                if short:
                    task += ("\n" if task else "") + ("ТЕКСТ КОРОЧЕ НОРМЫ (%s): допиши 1-2 предложения фактами из "
                                                      "материала, без оценок и без повторов" % short[0])
                raw = ask(RULES % (what, size, ntags, mat) + "\n\nТВОЙ ТЕКСТ ПОСЛЕ ФАКТЧЕКЕРА:\n" + text + "\n\n" + task)
                m = re.search(r"\{.*\}", raw, re.S)
                fixed = json.loads(m.group(0)).get("text", "").strip() if m else ""
                if not fixed or text_gates(fixed, kind, rise):
                    why = vk_judge.fix_note(after) or "; ".join(short + text_gates(fixed, kind, rise) if fixed else short)
                    raise SystemExit("после фактчекера текст рассыпался, починка не легла (%s): %s" % (who, why))
                text = fact_check(fixed, src, title)
                again, who = vk_judge.judge(text, mat, log=lambda m: log(m), keys=["coherence", "lead"])
                if again:
                    raise SystemExit("после фактчекера текст рассыпался и после починки (%s): %s"
                                     % (who, vk_judge.fix_note(again)))
                note += ", связность починена после фактчекера"
            bad = text_gates(text, kind, rise)
            if bad:
                raise SystemExit("гейты после фактчекера: %s" % "; ".join(bad))
            text = text + "\n\n" + SIGN
            # Чужие фрагменты в клипе (docs/research/footage-legal.md, ст. 1274 ГК): автор и источник обязательны.
            # Без ссылки и без названия площадки — гейт ВК режет ссылки и упоминания других площадок.
            names = sorted({c.split(" — ")[0].replace("Видео:", "").strip() for c in src.get("ext_credits") or []})
            if names:
                text += "\nВ ролике фрагменты: " + ", ".join(names)
            con.execute("UPDATE vk_queue SET status='ready', text=?, reason=? WHERE id=?", (text, note, qid))
            log("готов #%d %s: %s" % (qid, kind, text[:90].replace("\n", " ")))
        except (Exception, SystemExit) as e:
            if type(e).__name__ == "JudgeDown" or isinstance(e, (OSError, urllib.error.URLError)):
                # судья или прокси недоступны: не отказ, а повтор в следующий прогон
                con.execute("UPDATE vk_queue SET reason=? WHERE id=?", ("повтор: " + str(e)[:300], qid))
                log("отложен #%d %s: %s" % (qid, kind, str(e)[:120]))
                con.commit()
                break
            con.execute("UPDATE vk_queue SET status='rejected', reason=? WHERE id=?", (str(e)[:500], qid))
            log("отклонён #%d %s: %s" % (qid, kind, str(e)[:160]))
        con.commit()


# ---------------------------------------------------------------- публикация

def next_slot(con, kind):
    """Ближайший свободный слот МСК с учётом лимитов на сутки."""
    t = now_msk() + timedelta(minutes=20)
    for day in range(0, 8):
        d = (t + timedelta(days=day)).date()
        wk = "weekend" if d.weekday() >= 5 else "weekday"
        taken = con.execute("SELECT COUNT(*) FROM vk_queue WHERE kind=? AND status IN ('scheduled','sent_tg',"
                            "'published') AND substr(slot,1,10)=?", (kind, d.isoformat())).fetchone()[0]
        if taken >= LIMITS[kind]:
            continue
        for hm in SLOTS[wk]:
            h, m = map(int, hm.split(":"))
            s = datetime(d.year, d.month, d.day, h, m, tzinfo=MSK)
            if s > t:
                busy = con.execute("SELECT 1 FROM vk_queue WHERE slot=?", (s.isoformat(),)).fetchone()
                if not busy:
                    return s
    return None


def fetch_media(path):
    """Файл ролика: локально или с Диска (drive_sync чистит out/ после заливки)."""
    if path.startswith("http"):
        os.makedirs(TMP, exist_ok=True)
        dst = os.path.join(TMP, hashlib.sha1(path.encode()).hexdigest()[:12] + os.path.splitext(path)[1][:5])
        if not os.path.exists(dst):
            urllib.request.urlretrieve(path, dst)
        return dst
    if os.path.exists(path):
        return path
    os.makedirs(TMP, exist_ok=True)
    dst = os.path.join(TMP, os.path.basename(path))
    if not os.path.exists(dst):
        subprocess.run(["rclone", "copyto", "gdrive:GSPC/shorts/out/" + os.path.basename(path), dst],
                       capture_output=True, timeout=600)
    return dst if os.path.exists(dst) else None


def tg(method, fields, files=None):
    import build_short as bs
    env = bs.tg_env()
    tok, chat = env.get("GS_TG_BOT_TOKEN"), env.get("GS_TG_CHAT_ID")
    if not tok or not chat:
        return False
    cmd = ["curl", "-sS", "-o", "/tmp/vk_tg.json", "-w", "%{http_code}",
           "https://api.telegram.org/bot%s/%s" % (tok, method), "-F", "chat_id=%s" % chat]
    for k, v in fields.items():
        cmd += ["-F", "%s=%s" % (k, v)]
    for k, p in (files or {}).items():
        cmd += ["-F", "%s=@%s" % (k, p)]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600).stdout.strip().endswith("200")


def publish(con, dry=False):
    if os.path.exists(PAUSE):
        log("пауза: %s существует, ничего не публикую" % PAUSE)
        return
    from vk_api import VK, VKError
    vk = VK(log=log)
    auto = vk.env.get("VK_AUTO", "0") == "1" and vk.has("user")
    probe_ok = subprocess.run([sys.executable, "/opt/shorts/vk/vk_probe.py", "--quiet"],
                              capture_output=True).returncode
    if auto and probe_ok != 0:
        mark = "/opt/shorts/vk/probe_alert_%s" % now_msk().strftime("%Y%m%d")
        if not os.path.exists(mark) and not dry:
            r = subprocess.run([sys.executable, "/opt/shorts/vk/vk_probe.py"], capture_output=True, text=True)
            try:
                issues = json.loads(r.stdout).get("issues") or ["датчик ослеп"]
            except ValueError:
                issues = ["датчик ослеп"]
            tg("sendMessage", {"text": "ВК: не публикую, карточка сообщества расходится с сайтом "
                                       "(нейросети пересказывают её как факт). Поправить:\n- " + "\n- ".join(issues)})
            open(mark, "w").write("1")
        log("ВК: карточка расходится с сайтом, публикация стоит")
        return
    rows = con.execute("SELECT id, kind, title, text, media, sales, reason FROM vk_queue WHERE status='ready' "
                       "ORDER BY sales, id").fetchall()
    sold = con.execute("SELECT COUNT(*), COALESCE(SUM(sales),0) FROM (SELECT sales FROM vk_queue WHERE status "
                       "IN ('scheduled','sent_tg','published') ORDER BY id DESC LIMIT 5)").fetchone()
    for qid, kind, title, text, media, sales, note in rows:
        if sales and sold[0] and (sold[1] + 1) / max(sold[0] + 1, 5) > SALES_SHARE:
            continue                            # продающих не больше 1 из 5
        slot = next_slot(con, kind)
        if not slot:
            continue
        media = json.loads(media or "[]")
        files = [fetch_media(m) for m in media]
        if media and not all(files):
            con.execute("UPDATE vk_queue SET status='failed', reason='медиа не найдено' WHERE id=?", (qid,))
            con.commit()
            continue
        if dry:
            log("[проба] #%d %s -> %s %s" % (qid, kind, "ВК отложка" if auto else "пакет в группу",
                                             slot.strftime("%d.%m %H:%M")))
            continue
        if auto and probe_ok == 0:
            try:
                att = []
                for f in files:
                    if f.lower().endswith((".mp4", ".mov")):
                        att.append(vk.upload_video(f, title, text[:5000]))
                    else:
                        att.append(vk.upload_wall_photo(f))
                pid = vk.wall_post(text, att, publish_date=int(slot.timestamp()),
                                   guid=hashlib.sha1(("%s:%s" % (qid, kind)).encode()).hexdigest()[:32])
                con.execute("UPDATE vk_queue SET status='scheduled', slot=?, post_id=? WHERE id=?",
                            (slot.isoformat(), pid, qid))
                con.commit()
                tg("sendMessage", {"text": "ВК: отложено на %s МСК, vk.com/wall-%s_%s\n%s" % (
                    slot.strftime("%d.%m %H:%M"), vk.group_id, pid, text[:300])})
                log("ВК: #%d отложен на %s, пост %s" % (qid, slot.isoformat(), pid))
            except VKError as e:
                con.execute("UPDATE vk_queue SET reason=? WHERE id=?", (str(e)[:300], qid))
                con.commit()
                tg("sendMessage", {"text": "ВК-очередь встала: %s" % e})
                if e.fatal or e.pause:
                    open(PAUSE, "w").write("%s %s\n" % (time.strftime("%F %T"), e))
                return
        else:
            head = ("Пакет для ВК #%d на %s МСК (%s). Вставь текст в vk.com/goldensamplepcs, приложи файл, "
                    "поставь в отложку. Сам публиковать не могу: ВК ещё не выдал приложению право wall.\n\n"
                    % (qid, slot.strftime("%d.%m %H:%M"), "клип" if kind == "clip" else "пост"))
            if note:
                head = head.replace("\n\n", "\nТекст: Grok, %s, фактчекер пройден.\n\n" % note, 1)
            ok = tg("sendMessage", {"text": head + text})
            for f in files:
                ok = ok and tg("sendVideo" if f.lower().endswith(".mp4") else "sendPhoto",
                               {"caption": "к пакету ВК #%d" % qid},
                               {"video" if f.lower().endswith(".mp4") else "photo": f})
            if ok:
                con.execute("UPDATE vk_queue SET status='sent_tg', slot=? WHERE id=?", (slot.isoformat(), qid))
                con.commit()
                log("пакет #%d отправлен в группу на %s" % (qid, slot.isoformat()))
        if kind == "clip" and vk.env.get("VK_STORIES") == "1" and vk.has("group") and not dry:
            story_from_clip(vk, files[0] if files else None, qid, con)


def story_from_clip(vk, path, qid, con):
    """Первые 15 с клипа историей ключом сообщества: работает без одобрения ВК."""
    if not path:
        return
    cut = os.path.join(TMP, "story_%d.mp4" % qid)
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", path, "-t", "15", "-c:v", "libx264",
                    "-crf", "22", "-c:a", "aac", "-b:a", "128k", cut], capture_output=True)
    try:
        vk.story(cut, True, "learn_more", SITE + "/?utm_source=vk&utm_medium=story")
        log("история из клипа #%d опубликована" % qid)
    except Exception as e:
        log("история #%d не вышла: %s" % (qid, str(e)[:120]))


# ---------------------------------------------------------------- команды

def add_clip(con, mp4, theme_path, title):
    th = json.load(io.open(theme_path, encoding="utf-8"))
    src = {"title": th.get("title") or title, "source_text": th.get("source_text") or th.get("descr", ""),
           "link": th.get("link", "")}
    scp = os.path.join(os.path.dirname(theme_path), "script.json")
    if os.path.exists(scp):
        sc = json.load(io.open(scp, encoding="utf-8"))
        src["voice"] = " ".join(re.sub(r"<[^>]+>", "", c.get("voice", "")) for c in sc.get("cards", []))
        src["ext_credits"] = sc.get("ext_credits") or []
    h = hashlib.sha1(open(mp4, "rb").read(1 << 20)).hexdigest()[:12]
    return enqueue(con, "clip", "manual:%s" % h, title or src["title"], src, [os.path.abspath(mp4)])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "collect", "prepare", "publish", "add-clip", "status", "pause",
                                    "resume", "veto"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--theme")
    ap.add_argument("--title", default="")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    con = db()
    if a.cmd == "pause":
        open(PAUSE, "w").write(time.strftime("%F %T") + " ручная пауза\n")
        print("пауза включена")
    elif a.cmd == "resume":
        if os.path.exists(PAUSE):
            os.remove(PAUSE)
        print("пауза снята")
    elif a.cmd == "veto":
        con.execute("UPDATE vk_queue SET status='vetoed' WHERE id=?", (int(a.arg),))
        con.commit()
        print("вето на #%s" % a.arg)
    elif a.cmd == "status":
        for r in con.execute("SELECT status, kind, COUNT(*) FROM vk_queue GROUP BY 1,2 ORDER BY 1"):
            print("%-10s %-5s %d" % r)
        for r in con.execute("SELECT id, kind, status, slot, substr(title,1,50), substr(reason,1,80) FROM vk_queue "
                             "ORDER BY id DESC LIMIT 12"):
            print(" #%s %s %s %s «%s» %s" % r)
    elif a.cmd == "add-clip":
        print("в очереди" if add_clip(con, a.arg, a.theme, a.title) else "уже был")
    else:
        if a.cmd in ("run", "collect"):
            collect_clips(con)
            collect_guard(con)
            collect_articles(con)
            collect_build(con)
        if a.cmd in ("run", "prepare"):
            prepare(con, a.dry)
        if a.cmd in ("run", "publish"):
            publish(con, a.dry)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
