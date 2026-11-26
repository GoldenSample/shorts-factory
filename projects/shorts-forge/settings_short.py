#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Шортс из гайда оптимальных настроек PC Optimized Settings. Живёт на VPS в /opt/shorts, только стандартная библиотека.

Слово Гора 04.10.2026: «да, делай скрипт и Control Resonant первым». Формат «Минус N% FPS: что выключить в <игре>».

    python3 settings_short.py <ссылка на гайд>            тема + постановка сборки в очередь фабрики
    python3 settings_short.py <ссылка> --dry              только показать тему, ничего не запускать
    python3 settings_short.py --list                      свежие гайды из фида

Что делает:
  1. Берёт гайд из фида pcoptimizedsettings.com/feed/ (полный текст), иначе со страницы.
  2. Вынимает фразы о цене настроек: сначала с цифрами (%, FPS, ГБ, мс), потом качественные выводы («заметно медленнее»,
     «без потери картинки»). Цифры гайдов в основном на их графиках, в тексте их единицы; нужна хотя бы одна.
  3. Одним вызовом сильной модели (grok-4.7: текст для публичного ролика) делает тему ОТ ЖЕЛЕЗА: заголовок «какие
     настройки съедают FPS», суть и список фактов по-русски, цифры только из текста. В источник для гейта фактов идут
     русские факты и следом английские оригиналы (гейт видит первые 2000 знаков, поэтому цифры стоят в начале).
  4. Реестр тем topics.check: дубль за срок остывания и полка «мы не канал новостей про игры» (Гор 01.10). Отказ полки
     или дубль = стоп, без обхода.
  5. Ставит build_short.py --theme-json в очередь под замком фабрики (flock ждёт до 2 ч, два прогона в одном work
     затирают друг друга), до трёх попыток при стопе фактчекера, голос xAI как в daily.sh. Готовый ролик фабрика сама
     шлёт в TG-группу на утверждение: каждый рил Гор смотрит сам. Повтор по той же ссылке снимает свой прошлый черновик.

Правила источника: их скриншоты и видео НЕ берём (авторское), только факты со ссылкой. Не больше 2-3 роликов в неделю
(серия по шаблону = «inauthentic content»). В автоотбор фабрики и в ленту TechPulse источник не подключён: только вручную.
"""
import argparse
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

BASE = "/opt/shorts"
FEED = "https://pcoptimizedsettings.com/feed/"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
LLM = os.environ.get("SETTINGS_LLM_URL", "http://127.0.0.1:8650/v1/chat/completions")
# Текст для публичного ролика = сильный ярус (решение Гора 03.10 по ярусам). grok-4.20 без размышлений на сухом
# прогоне 04.10 оставлял факты по-английски дважды подряд.
MODEL = os.environ.get("SETTINGS_MODEL", "grok-4.7")
PY = "/usr/local/lib/hermes-agent/venv/bin/python3"
NUM = re.compile(r"\d+(?:[.,]\d+)?\s?(?:%|percent|fps|FPS|GB|ГБ|ms|мс|x\b)|\b(?:RTX|RX|Arc)\s?\d{3,4}", re.I)
# Цифры гайдов в основном на их графиках (картинки не берём), в тексте их единицы. Поэтому в факты идут и качественные
# выводы о цене настройки: «заметно медленнее», «просадка», «без потери картинки» (замер 04.10: у Control Resonant 1 цифра).
PERF = re.compile(r"\b(?:performance|perf\b|hit|slower|faster|cost|costly|expensive|cheap|impact|frame ?time|fps|vram|"
                  r"overhead|demanding|heavy|stutter|recommend|worth|negligible|minimal|barely|sizable|significant)", re.I)


def get(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def text_of(fragment: str) -> str:
    fragment = re.sub(r"(?is)<(script|style|figure|iframe)[^>]*>.*?</\1>", " ", fragment)
    fragment = re.sub(r"(?i)</(p|h[1-6]|li|tr|div)>", "\n", fragment)
    return re.sub(r"[ \t]+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def feed_items() -> list[dict]:
    x = get(FEED)
    out = []
    for it in re.findall(r"<item>(.*?)</item>", x, re.S):
        def tag(t):
            m = re.search(r"<%s>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</%s>" % (t, t), it, re.S)
            return html.unescape(m.group(1).strip()) if m else ""
        body = re.search(r"<content:encoded><!\[CDATA\[(.*?)\]\]></content:encoded>", it, re.S)
        out.append({"title": tag("title"), "link": tag("link"), "date": tag("pubDate"), "html": body.group(1) if body else ""})
    return out


def guide(url: str) -> dict:
    key = url.rstrip("/").split("?")[0]
    for it in feed_items():
        if it["link"].rstrip("/") == key:
            return it
    page = get(url)                                   # гайд старше фида: берём со страницы
    t = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
    body = re.search(r'(?is)<div[^>]+class="[^"]*entry-content[^"]*"[^>]*>(.*)</article>', page)
    return {"title": text_of(t.group(1)) if t else url, "link": url, "date": "", "html": body.group(1) if body else page}


def key_sentences(body_html: str, limit: int = 30) -> list[str]:
    """Фразы о цене настроек с разделом гайда в скобках: сначала с цифрами, потом качественные выводы.

    Раздел обязателен: «пресеты почти одинаковы, берите Ultra» и «Ultra на 20-25% медленнее» в гайде Control Resonant
    про РАЗНЫЕ настройки, без заголовка модель их склеила (сухой прогон 04.10)."""
    parts = re.split(r"(?is)<h[23][^>]*>(.*?)</h[23]>", body_html)
    num, perf = [], []
    for i in range(0, len(parts), 2):
        head = text_of(parts[i - 1]) if i else ""
        for s in re.split(r"(?<=[.!?])\s+|\n+", text_of(parts[i])):
            s = s.strip()
            if not 25 <= len(s) <= 300:
                continue
            line = ("[%s] %s" % (head[:60], s)) if head else s
            if NUM.search(s):
                num.append(line)
            elif PERF.search(s):
                perf.append(line)
    return list(dict.fromkeys(num + perf))[:limit]


def game_from_title(title: str) -> str:
    """«Control Resonant PC Ray + Path Tracing Settings Optimization» -> «Control Resonant»."""
    return re.split(r"\s+(?:PC\b|\+|–|-)\s*|:\s", title, maxsplit=1)[0].strip()


def ask(prompt: str) -> str:
    body = json.dumps({"model": MODEL, "temperature": 0.2, "max_tokens": 3000,
                       "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
    req = urllib.request.Request(LLM, data=body, headers={"Content-Type": "application/json",
                                                          "Authorization": "Bearer settings-short"})
    with urllib.request.urlopen(req, timeout=600) as r:      # 4.7 думает минутами
        return json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"]


PROMPT = """Гайд оптимальных настроек графики для ПК (PC Optimized Settings). Канал мастерской игровых ПК делает по нему
короткий ролик «что выключить, чтобы вернуть FPS». Мы НЕ канал новостей про игры: подача только от железа и FPS.

Заголовок гайда: {title}
Фразы о цене настроек (сначала с цифрами):
{nums}

Текст гайда (начало):
{text}

Название игры ровно такое: {game}

Верни ТОЛЬКО JSON, все текстовые поля ПО-РУССКИ:
{{"title_ru": "заголовок от железа с названием игры «{game}» целиком и главной цифрой цены, например «{game}: Ultra-трассировка съедает 20-25% FPS ради двух отскоков света» (до 110 знаков)",
  "descr_ru": "суть для сценариста, 400-650 знаков: какая настройка сколько стоит, что от неё видно на экране, что снизить без потери картинки; у каждого вывода назови настройку из квадратных скобок",
  "facts_ru": ["Настройка (раздел из скобок): факт, переведённый на русский точно, цифры без округлений", "..."]}}
Правила: каждый факт привязан к СВОЕЙ настройке из квадратных скобок, выводы разных разделов не смешивать; цифры и
названия настроек только из текста выше, ничего не придумывать, проценты не выдумывать; facts_ru от 4 до 10 пунктов,
каждый короче 200 знаков, по-русски (английские только названия настроек и технологий: Ultra, RTXDI, DLSS)."""


NO_MECH = ("Почему настройка тяжёлая, гайд не объясняет: механизм не придумывать, говорить только цену в FPS, что "
           "видно на экране и что выставить.")
TRIES = 3   # как MAX_TRY в daily.sh: фактчекер стоп = новый сценарий, цифры те же


def build_theme(g: dict) -> dict:
    text = text_of(g["html"])
    nums = key_sentences(g["html"])
    game = game_from_title(g["title"])
    if len(nums) < 4 or not any(NUM.search(s) for s in nums):
        sys.exit("в гайде нет цифры цены или меньше четырёх выводов о производительности: формату не на чем стоять (%s)"
                 % g["link"])
    raw = ask(PROMPT.format(title=g["title"], game=game, nums="\n".join("- " + s for s in nums), text=text[:3500]))
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        sys.exit("модель не вернула JSON: %r" % raw[:200])
    j = json.loads(m.group(0))
    facts = [str(f).strip() for f in j.get("facts_ru") or [] if str(f).strip()]
    cyr = sum(len(re.findall(r"[а-яё]", f, re.I)) for f in facts) / max(1, sum(len(f) for f in facts))
    if len(facts) < 4 or cyr < 0.3:
        sys.exit("модель вернула мало фактов или не по-русски (фактов %d, кириллица %.0f%%): %r"
                 % (len(facts), 100 * cyr, facts[:2]))
    if game.lower() not in j["title_ru"].lower():
        sys.exit("в заголовке нет игры «%s» целиком (фабрика возьмёт кадры не той игры): %s" % (game, j["title_ru"]))
    src = ("Гайд PC Optimized Settings «%s» (%s), автор Areej Syed. Факты гайда:\n" % (g["title"], g["date"][:16])
           + "\n".join("- " + f for f in facts)
           + "\nОригинал (англ.):\n" + "\n".join("- " + s for s in nums))
    return {
        "id": None, "story_id": None,
        # Оговорка в конце сути: сценарист любит объяснять механизм («туман считает слои воздуха»), а гайд механизмов не
        # даёт, и фактчекер Silent Hill 04.10 встал на такой реплике после шести переписей.
        "title": j["title_ru"].strip(),
        "descr": re.sub(r"\[([^\]]+)\]:?", r"\1:", j["descr_ru"]).strip() + " " + NO_MECH, "source_text": src,
        "link": g["link"], "rel": 50, "lang": "en",
        "published_at": time.strftime("%d.%m.%Y %H:%M", time.strptime(g["date"][:25], "%a, %d %b %Y %H:%M:%S"))
        if g["date"] else "",
        "verdict_json": {}, "intensity": 0,
        # предметный регистр: кадры карты и железа, а не абстрактные метафоры; сцены игры даёт game_footage
        "categories": "nvidia_gpu,amd_gpu,overclocking",
        "gate_topic": "настройки графики и FPS в %s" % game,
        "settings_game": game,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("--dry", action="store_true", help="только тема, без реестра и сборки")
    ap.add_argument("--list", action="store_true", help="свежие гайды из фида")
    a = ap.parse_args()
    if a.list:
        for it in feed_items():
            print(it["date"][5:16], "|", it["title"][:90], "|", it["link"])
        return 0
    if not a.url:
        ap.error("нужна ссылка на гайд или --list")

    g = guide(a.url)
    theme = build_theme(g)
    print("игра:", theme["settings_game"]); print("тема:", theme["title"]); print("суть:", theme["descr"])
    print("источник для гейта (%d знаков):\n%s" % (len(theme["source_text"]), theme["source_text"][:2000]))
    if a.dry:
        return 0

    sys.path.insert(0, BASE)
    import topics
    slug = re.sub(r"[^a-z0-9]+", "-", (theme["settings_game"] or "game").lower()).strip("-")[:40]
    topics.release("shorts", ["settings-" + slug])    # повтор по той же ссылке: свой прошлый черновик не дубль
    ok, score, like = topics.check(theme["title"], theme["descr"], topics.load(), source="shorts", judge=True, lang="en")
    if not ok:
        print("СТОП реестра тем (%.2f): %s" % (score, like))
        return 3
    tj = os.path.join(BASE, "out", "_settings_%s_theme.json" % slug)
    json.dump(theme, open(tj, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    topics.record(theme["title"], theme["descr"], "shorts", "settings-" + slug, status="draft")

    log = os.path.join(BASE, "settings_%s.log" % slug)
    # Окружение как в daily.sh: голос xAI. Гор 30.09 «переключи на хай войс» из-за ударений двойника, 04.10 повторил
    # («переозвучивай хаи, ударения каша») после ручных прогонов на двойнике. Двойник = только по слову Гора.
    env = dict(os.environ, HOME="/root", SHORTSMAKER_CUSTOM_VOICE="xf4r9bqs53rf", SHORTSMAKER_VOICE_ENGINE="xai",
               SHORTSMAKER_MUSIC_DB="-6", SHORTSMAKER_MUSIC_DUCK="threshold=0.08:ratio=2.5:attack=60:release=600")
    # До TRIES попыток: фабрика занята = ждём замок до 2 ч (два прогона в одном work затирают друг друга); попытка
    # засчитана, когда в её куске лога есть «отправлено на утверждение».
    loop = ('for t in $(seq 1 %d); do off=$(stat -c %%s "$LOG"); echo "$(date "+%%F %%T") попытка $t из %d" >> "$LOG"; '
            'flock -w 7200 /var/lock/shorts.lock %s build_short.py --theme-json "$TJ" >> "$LOG" 2>&1; '
            'tail -c +$((off + 1)) "$LOG" | grep -q "отправлено на утверждение" && break; done' % (TRIES, TRIES, PY))
    open(log, "ab").close()
    p = subprocess.Popen(["bash", "-c", loop], cwd=BASE, env=dict(env, LOG=log, TJ=tj), stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, start_new_session=True)
    print("сборка в очереди фабрики: pid %d, лог %s, тема %s" % (p.pid, log, tj))
    print("готовый ролик придёт в TG-группу фабрики на утверждение")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
