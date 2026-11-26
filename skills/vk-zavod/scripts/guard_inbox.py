# -*- coding: utf-8 -*-
"""Читатель ящика botdrop: отчёты Grok Bot «Сторож железа» -> темы для ВК и для шортсов.

Гор 01.10.2026: «есть грок бот он нам цены ищет», «да делай». Бот на grok.com шесть раз в сутки обходит
Регард/Ситилинк, драйверы NVIDIA/AMD/Intel, BIOS/AGESA/микрокод, инсайдеров X и HWBOT и в конце каждого
прогона отдаёт блок ТЕМЫ_JSON (факт, цифры, прямая ссылка). Шлюз botdrop (/opt/botdrop/botdrop.py) кладёт
письма в /opt/botdrop/inbox/ГГГГ-ММ-ДД.jsonl, строка = {ts, routine, ip, bytes, text}.

Письмо = НЕДОВЕРЕННЫЕ ДАННЫЕ (текст с форумов и сайтов прошёл через бота, см. шапку botdrop.py): здесь только
детерминированный разбор, до любой модели. Из письма берутся поля тем, ссылка проверяется по белому списку
доменов, строки с признаками инструкций модели выбрасываются, длины режутся. Ничего из письма не исполняется.

Куда что идёт:
  ВК (vk_queue, kind=post) — драйверы, BIOS, прошивки, микрокод, рекорды: источник на сайте вендора или HWBOT.
    Материал писателю = факт + цифры + ссылка + абзацы отчёта про эту же позицию (цитаты известных проблем).
  Шортсы/ТехПульс — цены (ru_market, ссылки на магазины): /opt/shorts/guard_topics.jsonl. В ВК цены магазинов
    не идут: «у Ситилинка дешевле» в сообществе мастерской = реклама конкурента.
  Слухи инсайдеров X — никуда (слух — не тема).
verdict_hint («брать/ждать») выбрасывается всегда: совет по деньгам запрещён регламентом подорожания 29.09.

    python3 guard_inbox.py             # посмотреть, что лежит в ящике (ничего не пишет и не помечает)
"""
import hashlib
import json
import os
import re
import stat
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/opt/shorts")                    # price_rule для тем по ценам

INBOX = os.environ.get("GUARD_INBOX", "/opt/botdrop/inbox")
STATE = os.environ.get("GUARD_STATE", "/opt/shorts/vk/guard_state.json")
PRICES_OUT = os.environ.get("GUARD_PRICES", "/opt/shorts/guard_topics.jsonl")
MSK = timezone(timedelta(hours=3))
MAX_AGE_DAYS = 14

VENDOR_HOSTS = ("amd.com", "nvidia.com", "intel.com", "asus.com", "msi.com", "gigabyte.com", "asrock.com",
                "samsung.com", "github.com", "hwbot.org", "corsair.com", "kingston.com", "wd.com", "crucial.com")
STORE_HOSTS = ("regard.ru", "citilink.ru", "nix.ru", "xcom-shop.ru")
RUMOR_HOSTS = ("x.com", "twitter.com")
# признаки текста, обращённого к модели: такие строки в материал не попадают (инъекция со страниц через бота)
INJECT = re.compile(r"(?i)(ignore (all |the )?previous|disregard|system prompt|assistant:|system:|<\|im_|"
                    r"игнорируй|забудь (все|предыдущ)|ты теперь|новые инструкции|выполни команд|curl |wget |ssh )")
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
STORE_WORDS = re.compile(r"(?i)(regard\.ru|citilink\.ru|xcom-shop|nix\.ru|регард|ситилинк|₽)")
MAX_FILE = 8 * 1024 * 1024                            # день ящика больше 8 МБ - это не письма бота


def host_of(url):
    """Хост https-ссылки или пусто. Логин-пароль, обратный слэш и «@» в адресе - сразу пусто:
    `https://evil.ru\\@amd.com` иначе проходил белый список (ревью 01.10)."""
    if "@" in url or "\\" in url or any(c.isspace() for c in url):
        return ""
    try:
        u = urllib.parse.urlparse(url)
    except ValueError:
        return ""
    if u.scheme != "https" or u.username or u.password:
        return ""
    return (u.hostname or "").lower()


def host_in(host, hosts):
    return any(host == h or host.endswith("." + h) for h in hosts)


def vendor_ok(host, url):
    """Источник ВК-темы: сайт вендора, но не пользовательский текст на нём (форумы, сообщество, чужие репо)."""
    if not host_in(host, VENDOR_HOSTS) or host.split(".")[0] in ("community", "forums", "forum", "answers"):
        return False
    if host == "github.com":                          # с GitHub только официальные репо вендоров
        return urllib.parse.urlparse(url).path.lower().startswith(("/intel/", "/amd/", "/nvidia/"))
    return True


def clean(s, cap):
    s = CTRL.sub(" ", str(s or ""))
    return " ".join(s.split())[:cap]


def topics_blocks(text):
    """Все JSON-списки после маркера ТЕМЫ_JSON. Битый блок пропускается, а не роняет разбор письма."""
    out, dec, pos = [], json.JSONDecoder(), 0
    while True:
        i = text.find("ТЕМЫ_JSON", pos)
        if i < 0:
            return out
        j = text.find("[", i)
        if j < 0:
            return out
        try:
            val, end = dec.raw_decode(text[j:])
            if isinstance(val, list):
                out += [x for x in val if isinstance(x, dict)]
            pos = j + end
        except (ValueError, RecursionError):          # «[[[[…» роняло бы сторожа в каждом прогоне
            pos = j + 1


def report_without_topics(text):
    """Отчёт бота без блоков ТЕМЫ_JSON и служебных строк шлюза — справка для писателя.
    Блоки вырезаются тем же JSON-разбором, что и читаются: регулярка споткнулась бы о «]» внутри numbers."""
    dec, out, pos = json.JSONDecoder(), [], 0
    while True:
        i = text.find("ТЕМЫ_JSON", pos)
        if i < 0:
            out.append(text[pos:])
            break
        out.append(text[pos:i])
        j = text.find("[", i)
        try:
            _, end = dec.raw_decode(text[j:]) if j >= 0 else (None, 0)
            pos = j + end if j >= 0 else i + len("ТЕМЫ_JSON")
        except (ValueError, RecursionError):
            pos = i + len("ТЕМЫ_JSON")
    t = "".join(out)
    lines = [ln for ln in t.splitlines() if not ln.strip().startswith("шлюз:") and not INJECT.search(ln)]
    return "\n".join(lines)


def blocks_about(report, url, numbers):
    """Абзацы отчёта про эту позицию: где есть её ссылка или её цифры (дословные цитаты известных проблем)."""
    # абзацы с ценами магазинов в материал ВК не идут (ревью 01.10: тянулись строки Регарда и Ситилинка)
    paras = [p.strip() for p in re.split(r"\n\s*\n", report) if p.strip() and not STORE_WORDS.search(p)]
    keys = [url] + [n for n in numbers if len(n) >= 3]
    hit = [i for i, p in enumerate(paras) if any(k and k in p for k in keys)]
    pick = sorted({k for i in hit for k in (i, i + 1) if k < len(paras)})   # ссылка, следом её цитаты
    return "\n\n".join(paras[i] for i in pick)[:2500]


def parse_topic(t, today):
    """Тема из письма -> чистый словарь или None. Всё, что не прошло проверку, отбрасывается молча."""
    rubric = clean(t.get("rubric"), 30).lower()
    fact = clean(t.get("fact"), 500)
    url = clean(t.get("source_url"), 400)
    host = host_of(url)
    nums = t.get("numbers")
    nums = [clean(n, 40) for n in (nums if isinstance(nums, list) else [nums]) if n not in (None, "")][:8]
    try:
        date = datetime.strptime(clean(t.get("date"), 10), "%Y-%m-%d").date()
    except ValueError:
        return None
    if not re.fullmatch(r"[a-z_]{2,30}", rubric) or len(fact) < 15 or not host or INJECT.search(fact):
        return None
    if not 0 <= (today - date).days <= MAX_AGE_DAYS:
        return None
    if host_in(host, STORE_HOSTS):
        sink = "prices"
    elif rubric != "ru_market" and vendor_ok(host, url):
        sink = "vk"
    else:
        return None                                   # слухи X, «цена» не с магазина, неизвестные домены — никуда
    return {"sink": sink, "rubric": rubric, "fact": fact, "numbers": nums, "was": clean(t.get("was"), 60),
            "now": clean(t.get("now"), 60), "delta_pct": t.get("delta_pct") if isinstance(t.get("delta_pct"),
            (int, float)) else None, "item": clean(t.get("item"), 80), "source_url": url,
            "source_name": clean(t.get("source_name"), 80), "date": str(date)}


def load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            data = json.load(f)
        return {x for x in data.get("done", []) if isinstance(x, str)} if isinstance(data, dict) else set()
    except (OSError, ValueError):
        return set()


def save_state(done):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"done": sorted(done)[-5000:]}, f)
    os.replace(tmp, STATE)


def letters(log=print):
    """Новые письма всех дней: (ключ строки, письмо). Ящик пишет сетевой сервис, поэтому файл открывается без
    перехода по симлинку и без блокировки (FIFO вешал бы крон), читается только обычный файл до 8 МБ."""
    try:
        files = sorted(f for f in os.listdir(INBOX) if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.jsonl", f))
    except OSError as e:
        log("сторож: ящик недоступен (%s)" % e)          # иначе недоступный ящик неотличим от пустого
        return
    for f in files:
        try:
            fd = os.open(os.path.join(INBOX, f),                     # флаги есть на Linux хаба, на Windows - 0
                         os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
        except OSError:
            continue
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_FILE:
            os.close(fd)
            log("сторож: %s пропущен (не обычный файл или больше 8 МБ)" % f)
            continue
        with os.fdopen(fd, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                key = hashlib.sha1(line.encode("utf-8")).hexdigest()[:16]
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if isinstance(msg, dict) and isinstance(msg.get("text"), str):
                    yield key, msg


def harvest(dry=False, log=print):
    """Разбирает новые письма. Возвращает (темы для ВК, число тем по ценам, commit).
    commit() сохраняет «письма прочитаны» - звать ПОСЛЕ того, как темы легли в очередь: иначе сбой базы
    («database is locked») терял их навсегда (ревью 01.10). Темы по ценам дописываются сразу, у них свой дедуп."""
    done = load_state()
    today = datetime.now(MSK).date()
    vk, prices, seen_new = [], [], set()
    for key, msg in letters(log):
        if key in done:
            continue
        seen_new.add(key)
        text = msg["text"][:64 * 1024]
        if clean(msg.get("routine"), 40) == "selftest":
            continue
        report = report_without_topics(text)
        for raw in topics_blocks(text):
            t = parse_topic(raw, today)
            if not t:
                continue
            t["routine"] = clean(msg.get("routine"), 40)
            if t["sink"] == "vk":
                t["context"] = blocks_about(report, t["source_url"], t["numbers"])
                vk.append(t)
            else:
                prices.append(t)
    if prices and not dry:
        import price_rule
        have = set()
        try:
            for ln in open(PRICES_OUT, encoding="utf-8"):
                have.add(json.loads(ln).get("id"))
        except (OSError, ValueError):
            pass
        with open(PRICES_OUT, "a", encoding="utf-8") as f:
            for t in prices:
                t["id"] = hashlib.sha1((t["source_url"] + t["fact"]).encode("utf-8")).hexdigest()[:12]
                if t["id"] in have:
                    continue
                t["is_rise"] = price_rule.is_rise(t["fact"])     # подорожание: частоту держит topics.check
                t["ts"] = datetime.now(MSK).isoformat(timespec="seconds")
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
                have.add(t["id"])
    log("сторож: писем новых %d, тем в ВК %d, по ценам %d" % (len(seen_new), len(vk), len(prices)))

    def commit():
        if not dry and seen_new:
            save_state(done | seen_new)
    return vk, len(prices), commit


def release_key(t):
    """Ключ темы в очереди ВК: хост и путь страницы вендора. Бот пересказывает один и тот же релиз в каждом
    отчёте другими словами - ключ по тексту плодил бы дубли; одна страница заметок = один пост."""
    u = urllib.parse.urlparse(t["source_url"])
    return hashlib.sha1((u.hostname or "").encode() + u.path.rstrip("/").lower().encode()).hexdigest()[:12]


def vk_material(t):
    """Материал писателю ВК: только поля темы и абзацы отчёта про неё; источник — вендор, ссылка в тексте поста не идёт."""
    parts = ["ФАКТ: %s" % t["fact"]]
    if t["numbers"]:
        parts.append("ЦИФРЫ: %s" % ", ".join(t["numbers"]))
    if t["was"] or t["now"]:
        parts.append("БЫЛО: %s. СТАЛО: %s." % (t["was"] or "-", t["now"] or "-"))
    # дата в двух видах: пост пишет «29.09», а фактчекер искал это в «2026-09-29» и снимал абзац (01.10)
    d = datetime.strptime(t["date"], "%Y-%m-%d")
    parts.append("ДАТА: %s (%s). ИСТОЧНИК: %s %s" % (d.strftime("%d.%m.%Y"), t["date"], t["source_name"],
                                                     t["source_url"]))
    if t.get("context"):
        # пересказ бота, а не первоисточник: фактчекер сверяет пост с ним, страница вендора - по ссылке выше
        parts.append("ИЗ ОТЧЁТА БОТА «Сторож железа» (пересказ страницы источника):\n%s" % t["context"])
    return "\n".join(parts)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    # ручной разбор только смотрит: письма помечаются прочитанными лишь в collect_guard после постановки в очередь
    vk, n, _ = harvest(dry=True)
    for t in vk:
        print("ВК:", t["rubric"], t["fact"][:100], "|", t["source_url"])
    print("по ценам:", n)
