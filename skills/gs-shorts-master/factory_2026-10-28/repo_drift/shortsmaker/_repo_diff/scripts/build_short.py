#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сборка ролика с генеративным визуалом. Запускать на VPS питоном hermes:

    /usr/local/lib/hermes-agent/venv/bin/python3 build_short.py [--dubles 4] [--no-send]

Тема из базы -> сценарий Гроком -> кадры grok-imagine-image-quality 2k ->
озвучка Grok TTS -> движение камеры ffmpeg -> типографика поверх -> гейт -> телеграм.

Кадры генерируются в 1584x2816 и УМЕНЬШАЮТСЯ до 1080x1920: уменьшенное режет
резче растянутого. Текст генератору не заказываем — он рисует кашу.
"""

import argparse
import io
import json
import os
import re
import subprocess
import sys
import textwrap
import time
import urllib.request
from datetime import datetime

sys.path.insert(0, "/usr/local/lib/hermes-agent")
sys.path.insert(0, "/opt/shorts")

BASE = "/opt/shorts"
OUT = os.path.join(BASE, "out")
WORK = os.path.join(BASE, "work")

PROXY = os.environ.get("SHORTSMAKER_PROXY", "http://127.0.0.1:8650/v1/chat/completions")
SCRIPT_MODEL = os.environ.get("SHORTSMAKER_SCRIPT_MODEL", "grok-4.3")
VOICE = os.environ.get("SHORTSMAKER_VOICE", "eve")
# Кастомный голос живёт в КОНСОЛЬНОЙ команде, не в подписочной: подписочный OAuth его
# не видит (404 Voice not found). Поэтому отдельная ветка с ключом из console.env.
# ГРАБЛЯ: POST /v1/tts отдаёт СЫРОЙ MP3 (content-type audio/mpeg), а не JSON с base64,
# как написано в доках. r.json() на нём падает UnicodeDecodeError.
CUSTOM_VOICE = os.environ.get("SHORTSMAKER_CUSTOM_VOICE", "").strip()
CONSOLE_ENV = os.environ.get("SHORTSMAKER_CONSOLE_ENV", "/opt/shorts/console.env")
# Калибровка голоса Гора 2026-08-20 (три оси, выбор на слух):
#   скорость 1.10; <slow> на ключевой цифре меняет подачу, не длительность;
#   [pause]/[sigh] дают реальные паузы; <whisper> съедает разборчивость — не брать.
TTS_SPEED = float(os.environ.get("SHORTSMAKER_SPEED", "1.10"))
# 2.0 = светотень и фактура (дуэль 08-14 на радиаторе + абляция imagine-prompting);
# quality держит мелкие детали ТЗ. Геометрии врут обе — vision-гейт обязателен.
IMAGE_MODEL = os.environ.get("SHORTSMAKER_IMAGE_MODEL", "grok-imagine-image-2.0")

HERMES_PY = "/usr/local/lib/hermes-agent/venv/bin/python3"
HERMES_DIR = "/usr/local/lib/hermes-agent"
PG = ["docker", "exec", "news_postgres", "psql", "-U", "news_user", "-d", "news_aggregator", "-tAc"]

W, H = 1080, 1920
FPS = 30
ACCENT = "0xE8B84B"
WHITE = "0xF2F4F8"
MUTED = "0x9AA3B2"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

# Выбор визуального регистра по категориям новости (таксономия TechPulse, 30 дней).
# Метафора обязательна там, где явление не снять (цены, утечки, AI) и где фотореализм
# запрещён по существу (отказы железа = «фото брака» намеренно). Ничья -> метафора.
PRODUCT_CATS = {"water_cooling", "cooling", "psu", "memory", "storage", "monitors",
                "peripherals", "premium_cases", "pc_aesthetics", "motherboards",
                "nvidia_gpu", "amd_gpu", "amd_cpu", "intel_cpu", "intel_gpu",
                "overclocking"}
METAPHOR_CATS = {"pricing", "chinese_hardware", "ai_tech", "announcements_leaks",
                 "hardware_failures", "os_errors", "gaming", "compatibility"}


def pick_register(theme):
    cats = set((theme.get("categories") or "").split(",")) - {""}
    prod = len(cats & PRODUCT_CATS)
    meta = len(cats & METAPHOR_CATS)
    reg = "product" if prod > meta else "metaphor"
    log("категории: %s -> регистр %s" % (",".join(sorted(cats)) or "нет", reg))
    return reg


# Стиль канала: приклеивается к каждому кадру. Правки — в references/prompts.md
# Стиль кадра по скилу imagine-prompting: блоки капсом, свет схемой, палитра с замком.
# ЗАПРЕЩЕНО навсегда: пыль, царапины, припой, погнутое, изношенное — состояние заражает
# весь кадр (замер 2.5 скила) и даёт «фото брака». Деталь всегда заводская чистая.
STYLE = ("МАТЕРИАЛ И СОСТОЯНИЕ: деталь новая, только с завода, безупречно чистая: "
         "ни пыли, ни царапин, ни отпечатков, ни следов пайки; чёрный матовый пластик, "
         "шлифованный алюминий, глянцевое стекло.\n"
         "СВЕТ: строго один источник: большой софтбокс слева сверху под сорок пять градусов, "
         "мягкий, с плавной границей тени, нейтральный белый 5600K; справа белая отражающая "
         "карта, тени лёгкие и прозрачные; на металле длинный ровный блик.\n"
         "ПАЛИТРА строго из четырёх цветов: графитово-чёрный, серебристый алюминий, "
         "тёмно-серый фон, холодный белый блик. Других цветов в кадре нет.\n"
         "КАДР: макро, предмет занимает большую часть кадра, фон гладкий тёмно-серый градиент "
         "размыт до мягкой мути, вертикальный кадр девять к шестнадцати. Это фотография "
         "продукта. Никаких надписей, никаких логотипов, никаких людей.")


# Арт-регистр: рукотворная инсталляция из железа, палитра согласована с золотом бренда.
# Заведомо не притворяется фото товара — метафора и есть содержание кадра.
STYLE_ART = ("Рукотворная архитектурная инсталляция из компьютерного железа, невозможная "
             "геометрия допустима и приветствуется, rendered matter-of-factly.\n"
             "МАТЕРИАЛ: настоящий текстолит с медными дорожками, чёрная паяльная маска, "
             "золочёные контакты, алюминиевые рёбра радиаторов, вентиляторы; всё новое, "
             "чистое, без пыли и повреждений.\n"
             "СВЕТ: строго один источник: холодный белый луч сверху слева, жёсткий, "
             "с резкой границей тени; заполняющего света нет, глубина уходит в черноту; "
             "на меди и золоте тёплые блики.\n"
             "ПАЛИТРА строго из четырёх цветов: графитово-чёрный, тёмная медь, "
             "приглушённое золото, холодный белый. Других цветов в кадре нет.\n"
             "КАДР: вертикальный кадр девять к шестнадцати, архитектурный масштаб, "
             "камера внутри пространства. Никаких надписей, никаких логотипов, "
             "никаких людей, никаких экранов с изображением.")


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def run(cmd, **kw):
    kw.setdefault("stdin", subprocess.DEVNULL)
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    return subprocess.run(cmd, **kw)


def sql(q):
    r = run(PG + [q])
    if r.returncode != 0:
        raise SystemExit("psql: %s" % r.stderr.strip()[:300])
    return r.stdout.strip()


# ---------------------------------------------------------------- тема и сценарий

def pick_theme():
    q = """
    SELECT row_to_json(t) FROM (
      SELECT n.id, n.story_id,
             COALESCE(NULLIF(n.translated_title,''), n.title) AS title,
             left(COALESCE(NULLIF(n.translated_description,''), n.description, ''), 700) AS descr,
             n.link, COALESCE(n.relevance_score,0) AS rel,
             v.verdict_json, COALESCE(v.intensity,0) AS intensity,
             (SELECT string_agg(DISTINCT k.category, ',')
              FROM news_keywords nk JOIN keywords k ON k.id = nk.keyword_id
              WHERE nk.news_id = n.id AND k.category IS NOT NULL) AS categories
      FROM news n JOIN vox_reactions v ON v.news_id = n.id
      WHERE n.published_at > now() - interval '7 days'
        AND n.id NOT IN (SELECT COALESCE(news_id,-1) FROM shorts_log WHERE created_at > now() - interval '30 days')
        AND (n.story_id IS NULL OR n.story_id NOT IN
             (SELECT COALESCE(story_id,-1) FROM shorts_log WHERE created_at > now() - interval '30 days'))
      ORDER BY (COALESCE(v.intensity,0)*100 + COALESCE(n.relevance_score,0)) DESC
      LIMIT 1) t;
    """
    raw = sql(q)
    return json.loads(raw) if raw else None


SHOT_RULE_PRODUCT = """Поле shot начинается словами «крупный план».
Кадр — ОБОБЩЁННАЯ иллюстрация категории (радиатор вообще, память вообще), а НЕ
изображение обсуждаемого товара: конкретную модель, узнаваемый дизайн и фирменные
черты НЕ описывать. Деталь новая и чистая."""

SHOT_RULE_METAPHOR = """Поле shot — ОБРАЗ-МЕТАФОРА события из компьютерного железа,
а не изображение товара. Пространство или конструкция, передающая суть сцены:
рост цен — лестница из планок памяти, уходящая вверх в темноту; дефицит — огромный
пустой зал с одним предметом; утечка — приоткрытая дверь в стене из плат; отказ —
разомкнутый мост из текстолита. Придумай СВОЙ образ под сцену, не копируй примеры.
Один образ на весь ролик, сцены — разные точки того же пространства."""


def reaction_link(theme):
    """Ссылка на живое обсуждение: сама новость с реддита, либо сосед по сюжету."""
    link = theme.get("link") or ""
    if "reddit.com" in link:
        return link
    if theme.get("story_id"):
        r = sql("SELECT link FROM news WHERE story_id=%d AND link LIKE '%%reddit.com%%' "
                "ORDER BY COALESCE(comments_count,0) DESC LIMIT 1;" % theme["story_id"])
        if r:
            return r
    return None


PROMPT = """Ты пишешь сценарий вертикального ролика на 35-40 секунд для канала Golden Sample про железо.

МАТЕРИАЛ
Заголовок: {title}
Суть: {descr}
Замер реакции аудитории: {verdict}

ЗАДАЧА
Четыре сцены с ЖЁСТКИМИ ролями:
1 — ИНФОПОВОД: суть новости и цифра-крючок. На экране будет скрин источника.
2 — ПОЯСНЕНИЕ: механика, почему так вышло. На генеративном фоне.
3 — РЕАКЦИЯ: что говорит аудитория — 1-2 короткие живые цитаты или пересказ
    из замера реакции, ничего не выдумывать. На экране будет скрин обсуждения.
4 — НАШ КОММЕНТАРИЙ: вывод канала и прогноз, что дальше. Здесь можно панч.

ГОЛОС
Спокойно, без продажи и нагнетания. Объясняем, а не пугаем.
Никаких отсылок, которые надо объяснять. Не констатируй настроение людей прямо.
Максимум один панч, только в четвёртой сцене.

Всего 90-110 слов озвучки на весь ролик. Цифры в озвучке — СЛОВАМИ.

Поле shot заполняй ТОЛЬКО для сцены 2 (пояснение), у остальных сцен shot: "".
{shot_rule}
Общее для shot: по-русски, одно предложение. Никаких людей, надписей, логотипов,
экранов с изображением. Свет, палитру и кадр не описывай — их добавит скрипт.
Запрещённые слова: пыль, царапины, припой, изношенный, погнутый, старый, сломанный.

ФОРМАТ — строго JSON:
{{
  "theme": "тема в 3-5 слов",
  "cards": [
    {{"big": "акцент на экран, до 14 знаков, обычно цифра",
      "caption": "подпись на экране, до 70 знаков",
      "voice": "речь диктора, 1-2 предложения, до 170 знаков",
      "shot": "крупный план конкретной детали, по-русски, одно предложение"}}
  ],
  "tg_caption": "подпись к ролику, до 200 знаков"
}}
Ровно 4 сцены."""


def call_grok(prompt, model=SCRIPT_MODEL, max_tokens=2000):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tokens}).encode("utf-8")
    req = urllib.request.Request(PROXY, data=body, headers={
        "Content-Type": "application/json", "X-Meter-Source": "shortsmaker"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"]


def parse_script(raw):
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise SystemExit("Grok не вернул JSON:\n%s" % raw[:400])
    obj = json.loads(m.group(0))
    if len(obj.get("cards", [])) < 3:
        raise SystemExit("мало сцен")
    return obj


# ---------------------------------------------------------------- озвучка

TTS = r"""
import sys, os, json
sys.path.insert(0, "/usr/local/lib/hermes-agent")
os.chdir("/usr/local/lib/hermes-agent")
from tools.tts_tool import _generate_xai_tts
jobs = json.load(open(sys.argv[1], encoding="utf-8"))
cfg = {"xai": {"language": "ru", "voice_id": sys.argv[2]}}
for text, path in jobs:
    _generate_xai_tts(text, path, cfg)
"""


def console_key():
    try:
        for line in open(CONSOLE_ENV, encoding="utf-8"):
            if line.strip().startswith("XAI_CONSOLE_KEY="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def synth_custom(cards):
    """Озвучка кастомным голосом через консольный ключ. Платно: $4.20/млн знаков."""
    import httpx
    key = console_key()
    if not key:
        raise SystemExit("нет ключа в %s" % CONSOLE_ENV)
    h = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    out, spent = [], 0
    for i, c in enumerate(cards):
        txt = c["voice"]
        r = httpx.post("https://api.x.ai/v1/tts", headers=h, timeout=200,
                       json={"text": txt, "language": "ru", "voice_id": CUSTOM_VOICE,
                             "speed": TTS_SPEED,
                             "output_format": {"codec": "mp3", "sample_rate": 24000,
                                               "bit_rate": 128000}})
        if r.status_code != 200:
            raise SystemExit("TTS %d: %s %s" % (i, r.status_code, r.text[:200]))
        path = os.path.join(WORK, "v%d.mp3" % i)
        open(path, "wb").write(r.content)          # сырой mp3, не json
        out.append(path)
        spent += len(txt)
    usd = spent / 1_000_000 * 4.20
    log("  озвучено голосом %s: %d знаков, $%.4f" % (CUSTOM_VOICE, spent, usd))
    try:
        with open("/opt/shorts/usage.jsonl", "a", encoding="utf-8") as f:
            print(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                              "source": "shortsmaker", "kind": "tts-custom",
                              "model": CUSTOM_VOICE, "chars": spent,
                              "usd": round(usd, 4)}, ensure_ascii=False), file=f)
    except Exception:
        pass
    return out


def synth(cards):
    jobs = [[c["voice"], os.path.join(WORK, "v%d.mp3" % i)] for i, c in enumerate(cards)]
    jf, sf = os.path.join(WORK, "tts.json"), os.path.join(WORK, "tts.py")
    json.dump(jobs, open(jf, "w", encoding="utf-8"), ensure_ascii=False)
    open(sf, "w", encoding="utf-8").write(TTS)
    r = run([HERMES_PY, sf, jf, VOICE], cwd=HERMES_DIR)
    made = [p for _, p in jobs if os.path.exists(p) and os.path.getsize(p) > 1000]
    if len(made) != len(jobs):
        raise SystemExit("TTS дал %d из %d\n%s" % (len(made), len(jobs), r.stderr[-600:]))
    return [p for _, p in jobs]


def dur(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path])
    return float(r.stdout.strip())


# ---------------------------------------------------------------- кадры

def gen_scenes(cards, dubles=1, register="product"):
    """Кадры в 2k. dubles>1 — снимаем несколько вариантов, берём первый годный."""
    from gen_media import gen_image, note_usage  # noqa: F401
    shots = []
    for i, c in enumerate(cards):
        # реальное фото из магазина всегда важнее генерации: зритель должен
        # видеть настоящий товар, когда он у нас есть
        photo = (c.get("photo") or "").strip()
        if photo and os.path.exists(photo):
            import shutil
            out = os.path.join(WORK, "scene%d.jpg" % i)
            shutil.copyfile(photo, out)
            shots.append(out)
            log("  сцена %d: реальное фото %s" % (i + 1, os.path.basename(photo)))
            continue
        style = STYLE if register == "product" else STYLE_ART
        prompt = "СУБЪЕКТ: %s.\n%s" % ((c.get("shot") or c.get("caption")).rstrip("."), style)
        out = os.path.join(WORK, "scene%d.jpg" % i)
        if dubles > 1:
            picks = gen_image_batch(prompt, WORK, i, dubles)
            best = vision_pick(picks, register)
            os.replace(best, out)
            for p in picks:
                if os.path.exists(p):
                    os.remove(p)
        else:
            gen_image(prompt, out)
        shots.append(out)
        log("  сцена %d готова" % (i + 1))
    return shots


VISION_Q_ART = ("Ответь строго одним словом, ДА или НЕТ. На фото художественная "
                "инсталляция из компьютерного железа. Есть ли на ней: грязь, мусорная "
                "каша из неразличимых деталей, оплавленные потёки, нечитаемый текст, "
                "куски, где непонятно, что изображено?")

VISION_Q = ("Ответь строго одним словом, ДА или НЕТ. На фото деталь компьютера. "
            "Есть ли на ней хоть что-то из списка: грязь, пыль, царапины, потёки припоя, "
            "вмятины, оплавленные или деформированные элементы, физически невозможная "
            "геометрия, мусорный нечитаемый текст?")


def vision_pick(paths, register="product"):
    """Ярус-4 QC: дешёвый vision-судья бракует дубли с дефектами.

    grok-4.20-0309-non-reasoning видит картинки через тот же OAuth (замерено 08-14).
    Отбор по max(размер файла) ЗАПРЕЩЁН: он выбирает самый замусоренный кадр.
    Если чистых нет — берём медианный по размеру и полагаемся на чистый стиль."""
    import base64
    import httpx
    from tools.xai_http import resolve_xai_http_credentials
    c = resolve_xai_http_credentials() or {}
    key = c.get("api_key")
    base = (c.get("base_url") or "https://api.x.ai/v1").rstrip("/")
    clean = []
    for p in paths:
        try:
            b64 = base64.b64encode(open(p, "rb").read()).decode()
            r = httpx.post(base + "/chat/completions",
                           headers={"Authorization": "Bearer " + key,
                                    "Content-Type": "application/json"},
                           json={"model": "grok-4.20-0309-non-reasoning",
                                 "messages": [{"role": "user", "content": [
                                     {"type": "image_url",
                                      "image_url": {"url": "data:image/jpeg;base64," + b64}},
                                     {"type": "text", "text": VISION_Q if register == "product" else VISION_Q_ART}]}],
                                 "max_tokens": 10}, timeout=120)
            ans = r.json()["choices"][0]["message"]["content"].strip().upper()
            verdict = "НЕТ" in ans and "ДА" not in ans.replace("НЕТ", "")
            log("    qc %s: %s" % (os.path.basename(p), "чист" if verdict else "брак"))
            if verdict:
                clean.append(p)
        except Exception as e:
            log("    qc %s: судья упал (%s)" % (os.path.basename(p), str(e)[:60]))
    pool = clean or sorted(paths, key=os.path.getsize)[len(paths) // 2:len(paths) // 2 + 1]
    return pool[0]


def gen_image_batch(prompt, outdir, idx, n):
    from gen_media import note_usage
    """n дублей за один вызов — дешевле и быстрее, чем n вызовов."""
    import httpx
    from tools.xai_http import resolve_xai_http_credentials
    c = resolve_xai_http_credentials() or {}
    key, base = c.get("api_key"), (c.get("base_url") or "https://api.x.ai/v1").rstrip("/")
    # ГРАБЛЯ 08-21: httpx.ReadTimeout на генерации убивал весь прогон вместе с уже
    # оплаченными кадрами. Три попытки с паузой; последняя ошибка пробрасывается.
    body = None
    last = None
    for attempt in (1, 2, 3):
        try:
            r = httpx.post(base + "/images/generations",
                           headers={"Authorization": "Bearer " + key,
                                    "Content-Type": "application/json"},
                           json={"model": IMAGE_MODEL, "prompt": prompt,
                                 "n": n, "resolution": "2k", "aspect_ratio": "9:16"},
                           timeout=420)
            r.raise_for_status()
            body = r.json()
            break
        except Exception as e:
            last = e
            log("  генерация кадра, попытка %d упала: %s" % (attempt, str(e)[:90]))
            if attempt < 3:
                time.sleep(10 * attempt)
    if body is None:
        raise SystemExit("кадр не сгенерирован после 3 попыток: %s" % str(last)[:200])
    paths = []
    for k, item in enumerate(body.get("data") or []):
        p = os.path.join(outdir, "scene%d_d%d.jpg" % (idx, k))
        for dl in (1, 2, 3):
            try:
                open(p, "wb").write(httpx.get(item["url"], timeout=300,
                                              follow_redirects=True).content)
                break
            except Exception as e:
                log("  скачивание кадра, попытка %d: %s" % (dl, str(e)[:70]))
                if dl == 3:
                    raise
                time.sleep(5)
        paths.append(p)
    usd = (body.get("usage") or {}).get("cost_in_usd_ticks", 0) / 1e10
    note_usage("image", IMAGE_MODEL, 0.0,
               {"usage": {"cost_in_usd_ticks": int(usd * 1e10)}}, outdir)
    log("  дублей %d, $%.2f" % (len(paths), usd))
    return paths


def news_screenshot(url, out_png):
    """Скрин статьи-первоисточника мобильной колонкой (venv-shot + playwright)."""
    r = run(["/opt/hermes/venv/bin/python3", "/opt/shorts/news_shot.py", url, out_png],
            timeout=120)
    ok = r.returncode == 0 and os.path.exists(out_png) and os.path.getsize(out_png) > 30000
    if not ok:
        log("  скрин не снялся: %s" % (r.stderr or r.stdout)[-160:])
    return ok


def screenshot_ok(png):
    """Ярус-4 и для скринов: блок-страница/логин/капча в ролик не проходит.
    Урок 08-14: реддит-заглушка «You've been blocked» уехала в выпуск,
    потому что проверялся только размер файла. Смотреть надо всё."""
    import base64
    import httpx
    from tools.xai_http import resolve_xai_http_credentials
    c = resolve_xai_http_credentials() or {}
    key = c.get("api_key")
    base = (c.get("base_url") or "https://api.x.ai/v1").rstrip("/")
    q = ("Это скриншот страницы для слайда ролика.\n"
         "Ответь ГОДЕН, только если видно СОДЕРЖАНИЕ статьи: заголовок и текст новости.\n"
         "Ответь БРАК, если видишь: окно согласия на куки или приватность, кнопки "
         "Accept/Принять, требование войти, регистрацию, капчу, ошибку, блокировку, "
         "рекламный баннер на весь экран, пустую или недогруженную страницу.\n"
         "Сомневаешься — БРАК. Ответь ОДНИМ словом: ГОДЕН или БРАК.")
    try:
        b64 = base64.b64encode(open(png, "rb").read()).decode()
        r = httpx.post(base + "/chat/completions",
                       headers={"Authorization": "Bearer " + key,
                                "Content-Type": "application/json"},
                       json={"model": "grok-4.20-0309-non-reasoning",
                             "messages": [{"role": "user", "content": [
                                 {"type": "image_url",
                                  "image_url": {"url": "data:image/png;base64," + b64}},
                                 {"type": "text", "text": q}]}],
                             "max_tokens": 10}, timeout=120)
        ans = r.json()["choices"][0]["message"]["content"].strip().upper()
        ok = "ГОДЕН" in ans
        log("  qc скрин %s: %s" % (os.path.basename(png), "годен" if ok else "БРАК — " + ans[:20]))
        return ok
    except Exception as e:
        log("  qc скрин: судья упал (%s) — не пускаю" % str(e)[:60])
        return False


def card_lang_ok(png):
    """Наши карточки с мнениями — только по-русски (правило Гора 08-14).
    Гейт ловит молчаливый отказ переводчика: карточка с английскими цитатами
    в ролик не проходит, сцена честно падает на футаж."""
    import base64
    import httpx
    from tools.xai_http import resolve_xai_http_credentials
    c = resolve_xai_http_credentials() or {}
    key = c.get("api_key")
    base = (c.get("base_url") or "https://api.x.ai/v1").rstrip("/")
    q = ("Ответь строго одним словом, ДА или НЕТ. На карточке есть целые фразы "
         "на английском языке? Имена пользователей, названия железа и брендов "
         "(RTX, Ryzen, ASRock) английским НЕ считаются.")
    try:
        b64 = base64.b64encode(open(png, "rb").read()).decode()
        r = httpx.post(base + "/chat/completions",
                       headers={"Authorization": "Bearer " + key,
                                "Content-Type": "application/json"},
                       json={"model": "grok-4.20-0309-non-reasoning",
                             "messages": [{"role": "user", "content": [
                                 {"type": "image_url",
                                  "image_url": {"url": "data:image/png;base64," + b64}},
                                 {"type": "text", "text": q}]}],
                             "max_tokens": 10}, timeout=120)
        ans = r.json()["choices"][0]["message"]["content"].strip().upper()
        ok = "НЕТ" in ans
        log("  qc язык %s: %s" % (os.path.basename(png), "русский" if ok else "АНГЛИЙСКИЙ — брак"))
        return ok
    except Exception as e:
        log("  qc язык: судья упал (%s) — не пускаю" % str(e)[:60])
        return False


def reddit_cards(url, post_png, comm_png):
    """Реддит с VPS отдаёт HTML только заглушкой, зато .rss открыт (путь новостного
    конвейера). Рендерим карточки с реальными цитатами и скриним их локально."""
    ph, ch = os.path.join(WORK, "card_post.html"), os.path.join(WORK, "card_comm.html")
    r = run(["python3", "/opt/shorts/reddit_card.py", "both", url, ph, ch], timeout=120)
    if r.returncode != 0:
        log("  карточки не собрались: %s" % (r.stderr or r.stdout)[-120:])
        return False, False
    ok_p = news_screenshot("file://" + ph, post_png) and card_lang_ok(post_png)
    ok_c = news_screenshot("file://" + ch, comm_png) and card_lang_ok(comm_png)
    return ok_p, ok_c


def make_shot_clip(png, seconds, out, idx, total_shots=2, shot_no=0):
    """Панорама по скрину новости: окно 1080x1920 едет вниз по своей полосе страницы.

    Скрин выше кадра; делим его высоту на полосы по числу скрин-сцен, каждая сцена
    едет по своей полосе — кадры не повторяются. y от t у crop работает (замерено),
    в отличие от w/h.
    """
    import subprocess as sp
    pr = sp.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                 "stream=width,height", "-of", "csv=p=0", png],
                capture_output=True, text=True, stdin=sp.DEVNULL)
    try:
        iw, ih = [int(x) for x in pr.stdout.strip().split(",")[:2]]
    except Exception:
        iw, ih = 1080, 1920
    d = max(seconds, 0.5)
    band = max(ih // max(total_shots, 1), 1920)
    y0 = min(shot_no * band, max(ih - 1920, 0))
    y1 = min(y0 + max(band - 1920, 0), max(ih - 1920, 0))
    vf = ("crop=1080:1920:x='(iw-1080)/2':y='%d+(%d-%d)*t/%0.3f',"
          "setsar=1,eq=saturation=0.97,format=yuv420p" % (y0, y1, y0, d))
    r = run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-loop", "1", "-t", "%.3f" % seconds,
             "-i", png, "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
             "-pix_fmt", "yuv420p", "-r", str(FPS), out])
    if r.returncode != 0:
        raise SystemExit("скрин-клип %d: %s" % (idx, r.stderr[-400:]))
    return out


def gen_footage_clip(prompt_text, seconds, out, register):
    """Генеративный футаж-видео; при отказе — None (падаем на кен-бёрнс от картинки)."""
    from gen_media import gen_video
    dur_v = 4 if seconds <= 5 else 6
    style = STYLE_ART if register == "metaphor" else STYLE
    try:
        res = gen_video("СУБЪЕКТ: %s.\n%s" % (prompt_text.rstrip("."), style), out,
                        duration=dur_v, aspect="9:16", resolution="720p")
        return res.get("path")
    except SystemExit as e:
        log("  видео-футаж упал (%s), падаю на картинку" % str(e)[:100])
        return None


SPEECH_TAG_RE = re.compile(r"</?(?:slow|whisper|singing)>|\[(?:pause|laugh|sigh)\]")


def strip_tags(t):
    """Теги речи живут только в озвучке. На экран не попадают."""
    return SPEECH_TAG_RE.sub("", t or "").replace("  ", " ").strip()


def wrap(t, w):
    return "\n".join(textwrap.wrap(t, width=w)) or t


def txt(path, s):
    open(path, "w", encoding="utf-8").write(s)
    return path


def make_clip(img, seconds, out, idx):
    """ГЕОМЕТРИЯ (04.09): источник РОВНО 1080x1920 — это наша карточка с текстом,
    её панорамировать нельзя. Во-первых, вырезать окно 1188x2112 не из чего и
    ffmpeg падает; во-вторых, буквы не должны ползать. Такой кадр идёт статикой."""
    try:
        pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v",
                             "-show_entries", "stream=width,height", "-of", "csv=p=0", img],
                            capture_output=True, text=True, stdin=subprocess.DEVNULL)
        wh = (pr.stdout or "").strip().strip(",")
        if wh in ("1080,1920", "1080,1920,"):
            r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-loop", "1",
                                "-i", img, "-t", "%.3f" % seconds, "-r", str(FPS),
                                "-vf", "scale=1080:1920,setsar=1,format=yuv420p",
                                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", out],
                               capture_output=True, text=True, stdin=subprocess.DEVNULL)
            if r.returncode == 0:
                return
    except Exception:
        pass
    """Кадр -> клип с движением камеры.

    ГРАБЛЯ: zoompan на этой машине неприменим. Два ядра Xeon; шестисекундный клип
    через zoompan считается 8-10 МИНУТ, и апскейл входа тут ни при чём — при
    подаче исходника 1584x2816 как есть так же плохо. НЕ возвращать zoompan.

    Движение делаем кропом: окно фиксированного размера едет по кадру, x и y
    зависят от t (crop это умеет, а вот w и h — нет, они считаются один раз).
    Исходник крупнее выхода, поэтому путь всегда вниз и дрожать нечему.
    Стоит это почти столько же, сколько статика: 42 с против 37 с.
    """
    d = max(seconds, 0.5)
    # окно 75% кадра — остаётся запас на проезд
    cw, ch = 1188, 2112
    dirs = [("(iw-ow)*t/%0.3f" % d, "(ih-oh)/2"),                    # слева направо
            ("(iw-ow)*(1-t/%0.3f)" % d, "(ih-oh)/2"),                # справа налево
            ("(iw-ow)/2", "(ih-oh)*t/%0.3f" % d),                    # сверху вниз
            ("(iw-ow)*t/%0.3f" % d, "(ih-oh)*(1-t/%0.3f)" % d)]      # по диагонали
    x, y = dirs[idx % len(dirs)]
    vf = ("crop=%d:%d:x='%s':y='%s',scale=%d:%d:flags=bilinear,setsar=1,"
          "vignette=angle=PI/5:mode=forward,eq=saturation=0.95:contrast=1.03,"
          "format=yuv420p" % (cw, ch, x, y, W, H))
    r = run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-loop", "1", "-t", "%.3f" % seconds,
             "-i", img, "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
             "-pix_fmt", "yuv420p", "-r", str(FPS), out])
    if r.returncode != 0:
        raise SystemExit("клип %d: %s" % (idx, r.stderr[-500:]))
    return out


def assemble(clips, cards, spans, audio, out, kinds=None):
    """Склейка жёстким резом + озвучка + типографика поверх."""
    # Петля реплея (замер 08-14: шов клипов 15-27 при шумовом поле 1-3).
    # Лента зациклит ролик: держим в конце статично ПЕРВЫЙ кадр ролика, без
    # затухания — конец склеивается с началом. Голос к этому моменту уже закончил.
    LOOP_TAIL = 1.2
    first_png = os.path.join(WORK, "first.png")
    tail_mp4 = os.path.join(WORK, "tail.mp4")
    run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", clips[0],
         "-frames:v", "1", first_png])
    run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-loop", "1",
         "-t", "%.2f" % LOOP_TAIL, "-i", first_png,
         "-vf", "scale=%d:%d,setsar=1,format=yuv420p" % (W, H),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-pix_fmt", "yuv420p", "-r", str(FPS), tail_mp4])
    lst = os.path.join(WORK, "clips.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for c in clips + ([tail_mp4] if os.path.exists(tail_mp4) else []):
            f.write("file '%s'\n" % c)
    silent = os.path.join(WORK, "silent.mp4")
    r = run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0",
             "-i", lst, "-c", "copy", silent])
    if r.returncode != 0:
        raise SystemExit("склейка: %s" % r.stderr[-500:])

    total = spans[-1][1]
    g = []
    n = 0
    kinds = kinds or ["footage"] * len(cards)
    for i, c in enumerate(cards):
        a, b = spans[i]
        on_shot = kinds[i] in ("news_shot", "reaction_shot")
        big = wrap(strip_tags(c.get("big")), 15)
        cap = wrap(strip_tags(c.get("caption")), 24)
        fb = txt(os.path.join(WORK, "b%d.txt" % i), big)
        fc = txt(os.path.join(WORK, "c%d.txt" % i), cap)
        longest = max((len(x) for x in big.split("\n")), default=1)
        fs = 150 if longest <= 6 else (118 if longest <= 10 else 90)
        ta, tb = a + 0.25, b - 0.15
        src = "[0:v]" if n == 0 else "[v%d]" % n
        if on_shot or not (big or cap.strip()):
            # карточка сама несёт текст: свой не рисуем вовсе (наезд 08-14)
            continue
        # ПОЛОСА ТЕКСТА (03.09.2026). Титр стоял на y=380, то есть на 19.8% высоты.
        # Настоящая безопасная зона НЕ ЗАМЕРЕНА (калибровочная сетка у Гора), но три
        # ходовых кандидата дают полосы 480-1440, 210-1710 и 380-1540. Их ПЕРЕСЕЧЕНИЕ
        # 480-1440: попадая в него, текст цел при любой из гипотез, а y=380 не проходит
        # ни по одной. Ставим верх титра на 560 с запасом; после замера сетки сузим.
        TOP = 560
        g.append("%sdrawtext=fontfile=%s:textfile=%s:fontsize=%d:fontcolor=%s:borderw=7:bordercolor=black@0.85"
                 ":line_spacing=8:x=(w-text_w)/2:y=%d:enable='between(t,%.2f,%.2f)'[v%d]"
                 % (src, FONT_B, fb, fs, ACCENT, TOP, ta, tb, n + 1))
        n += 1
        g.append("[v%d]drawtext=fontfile=%s:textfile=%s:fontsize=54:fontcolor=%s:borderw=6:bordercolor=black@0.85"
                 ":line_spacing=16:x=(w-text_w)/2:y=%d:enable='between(t,%.2f,%.2f)'[v%d]"
                 % (n, FONT_B, fc, WHITE, 380 + fs * (big.count("\n") + 1) + 40, ta, tb, n + 1))
        n += 1

    fbr = txt(os.path.join(WORK, "brand.txt"), "TechPulse · Golden Sample")
    g.append("[v%d]drawtext=fontfile=%s:textfile=%s:fontsize=34:fontcolor=%s@0.75"
             ":x=(w-text_w)/2:y=1770[v%d]" % (n, FONT_R, fbr, MUTED, n + 1))
    n += 1
    g.append("[v%d]drawbox=x=0:y=1876:w='min(iw,iw*t/%.2f)':h=8:color=%s@0.9:t=fill[vout]" % (n, total, ACCENT))

    gf = os.path.join(WORK, "overlay.txt")
    open(gf, "w", encoding="utf-8").write(";\n".join(g))

    r = run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", silent, "-i", audio,
             "-filter_complex_script", gf, "-map", "[vout]", "-map", "1:a:0",
             "-c:v", "libx264", "-preset", "faster", "-crf", "20",
             "-profile:v", "high", "-level", "4.0", "-g", "60", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
             "-af", "apad", "-t", "%.3f" % (total + 1.2),
             "-movflags", "+faststart", out])
    if r.returncode != 0:
        raise SystemExit("финальная сборка: %s" % r.stderr[-800:])
    return out


def concat_audio(parts, out, gap=0.35):
    sil = os.path.join(WORK, "sil.mp3")
    run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi",
         "-i", "anullsrc=r=24000:cl=mono", "-t", str(gap), sil])
    seq = []
    for i, p in enumerate(parts):
        seq.append(p)
        if i < len(parts) - 1:
            seq.append(sil)
    lst = os.path.join(WORK, "aud.txt")
    with open(lst, "w", encoding="utf-8") as f:
        for p in seq:
            f.write("file '%s'\n" % p)
    run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
         "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000",
         "-c:a", "libmp3lame", "-b:a", "192k", out])
    spans, t = [], 0.0
    for i, p in enumerate(parts):
        d = dur(p)
        spans.append((t, t + d + (gap if i < len(parts) - 1 else 0.0)))
        t = spans[-1][1]
    return out, spans


def x_sweep(theme):
    """Свежий грок-дипсерч по X в момент сборки: vox-замер суточной давности,
    петле нужна реакция СЕЙЧАС. Рецепт vox: 4.20-reasoning + web,x_search,no_mcp;
    известный глюк — finish=stop с пустым content, лечится одним ретраем."""
    prompt = ('Найди на X (Twitter) и в вебе свежие реакции на новость: "%s" (%s). '
              'Верни СТРОГО JSON без пояснений: {"intensity": 0.0-1.0, '
              '"emocia": "доминирующая реакция одним словом", '
              '"one_liner": "суть реакции одним предложением по-русски", '
              '"quotes": [{"author": "@хэндл", "text": "цитата до 200 знаков в оригинале"}] '
              '(3-4 реальные живые цитаты), '
              '"objections": ["главные возражения по-русски"]}'
              % (theme["title"][:120], (theme.get("descr") or "")[:200]))
    for attempt in (1, 2):
        try:
            r = run(["hermes", "-z", prompt, "-m", "grok-4.20-0309-reasoning",
                     "-t", "web,x_search,no_mcp", "--cli", "--yolo"], timeout=330)
            m = re.search(r"\{.*\}", r.stdout or "", re.S)
            if m:
                d = json.loads(m.group(0))
                log("  X-свип: %s (int=%s, цитат %d)" % (
                    d.get("emocia", "?"), d.get("intensity", "?"), len(d.get("quotes", []))))
                return d
        except Exception as e:
            log("  X-свип упал: %s" % str(e)[:80])
        if attempt == 1:
            log("  X-свип пуст, ретрай")
    return None


# ---------------------------------------------------------------- нарративная петля
#
# Правило Гора 08-14: слайд производит реакцию, её надо СЧИТАТЬ и строить
# дальнейшее повествование из неё. Поэтому визуал сцены строится РАНЬШЕ её
# текста: слайд -> восприятие (vision) -> реплика, отвечающая на восприятие.

def perceive(png, hint=""):
    """Смотрим на слайд глазами зрителя: что видит, что цепляет, какой вопрос."""
    import base64
    import httpx
    from tools.xai_http import resolve_xai_http_credentials
    c = resolve_xai_http_credentials() or {}
    key = c.get("api_key")
    base = (c.get("base_url") or "https://api.x.ai/v1").rstrip("/")
    q = ("Это слайд вертикального ролика про железо. %s"
         "Опиши глазами зрителя, который видит его первую секунду. Строго JSON: "
         '{"vidit": "что в кадре, одним предложением", '
         '"cepliaet": "за что цепляется взгляд", '
         '"emocia": "какую реакцию рождает: смех/возмущение/узнавание/скепсис/интерес...", '
         '"vopros": "какой вопрос остаётся у зрителя"}' % (hint + " " if hint else ""))
    try:
        b64 = base64.b64encode(open(png, "rb").read()).decode()
        r = httpx.post(base + "/chat/completions",
                       headers={"Authorization": "Bearer " + key,
                                "Content-Type": "application/json"},
                       json={"model": "grok-4.3",
                             "messages": [{"role": "user", "content": [
                                 {"type": "image_url",
                                  "image_url": {"url": "data:image/png;base64," + b64}},
                                 {"type": "text", "text": q}]}],
                             "max_tokens": 400}, timeout=180)
        m = re.search(r"\{.*\}", r.json()["choices"][0]["message"]["content"], re.S)
        pc = json.loads(m.group(0)) if m else {}
        log("  восприятие: %s | %s" % (pc.get("emocia", "?"), (pc.get("vopros") or "")[:60]))
        return pc
    except Exception as e:
        log("  восприятие упало: %s" % str(e)[:80])
        return {}


STORY_RULES = """Ты пишешь закадровый текст вертикального ролика канала Golden Sample про железо.
Голос собран по разбору 139 постов ведущих русских техноканалов (references/voice.md).

ЧТО ДЕЛАТЬ.
Начинай с факта или странности, а не с темы. Цифру всегда ставь рядом с ориентиром:
было -> стало, либо сравнение с понятной вещью. Короткие предложения, разговорный
порядок слов. Своя позиция — одной фразой и только в финале.

ЧЕГО НЕ ДЕЛАТЬ.
Не писать: сегодня поговорим, разбираемся, в этом видео, дело в том что,
но что же скрывается, давайте разберёмся. Никаких риторических вопросов-интриг.
Никакого капса, многоточий-обрывов, эмодзи, скобок, тире-вставок, ссылок.
Не констатируй настроение людей прямо. Не бери термины, которые требуют объяснения:
объяснять некогда.

РЕЧЬ, А НЕ ТЕКСТ.
Это читает диктор. Максимум одно придаточное, лучше два коротких предложения.
Все цифры словами. Реплика сцены: 1-2 предложения, до 170 знаков.
Панч максимум один и только в финальной сцене.

ИНТОНАЦИЯ.
Ровно ОДНУ ключевую цифру или слово в реплике оберни в <slow>...</slow> — это меняет подачу, не удлиняя фразу. Больше одного раза за реплику нельзя. Другие теги не использовать.

ФОРМА ФИНАЛА.
Финальная сцена: короткое утверждение, двоеточие, причина. Ритм: Ждать снижения до нового года смысла нет: производство расписано вперёд."""


def story_step(theme, history, percept, stage):
    """Одна реплика повествования, построенная из считанной реакции на слайд."""
    ctx = ("МАТЕРИАЛ. Заголовок: %s\nСуть: %s\nЗамер реакции аудитории: %s\n\n"
           % (theme["title"], (theme.get("descr") or "")[:600],
              json.dumps(theme.get("verdict_json") or {}, ensure_ascii=False)[:700]))
    hist = ("УЖЕ СКАЗАНО:\n" + "\n".join("- " + h for h in history) + "\n\n") if history else ""
    pblock = ""
    if percept:
        pblock = ("ЗРИТЕЛЬ СЕЙЧАС ВИДИТ СЛАЙД: %s. Цепляет: %s. Реакция: %s. "
                  "Вопрос зрителя: %s\nСтрой реплику ИЗ этой реакции: не пересказывай "
                  "слайд, а отвечай на реакцию и веди дальше.\n\n"
                  % (percept.get("vidit", ""), percept.get("cepliaet", ""),
                     percept.get("emocia", ""), percept.get("vopros", "")))
    tasks = {
        "hook": ('Сцена 1, крючок. Усиль то, что зритель видит, и оставь вопрос, который '
                 'потянет смотреть дальше. Плюс придумай кадр сцены 2, отвечающий на вопрос '
                 'зрителя: по-русски, «крупный план ...», конкретная деталь железа, новая и '
                 'чистая, без людей/надписей/логотипов/экранов. Строго JSON: '
                 '{"voice": "...", "next_shot": "..."}'),
        "explain": ('Сцена 2, пояснение механики. Ответь на вопрос зрителя из восприятия, '
                    'но ДЕРЖИ главную линию темы: если вопрос зрителя уводит в сторону, '
                    'свяжи его с темой одним ходом и вернись к ней. '
                    'Строго JSON: {"voice": "...", "big": "акцент до 14 знаков, обычно '
                    'цифра", "caption": "подпись до 70 знаков"}'),
        "reaction": ('Сцена 3, реакция аудитории. Зритель видит реальные комментарии на '
                     'слайде — среагируй на конкретные видимые цитаты, не выдумывай новых. '
                     'Строго JSON: {"voice": "..."}'),
        "forecast": ('Сцена 4, финал. Наш комментарий и прогноз канала: что это значит и '
                     'что будет дальше. Здесь можно один панч. Строго JSON: '
                     '{"voice": "...", "big": "тезис/цифра до 14 знаков", '
                     '"caption": "подпись до 70 знаков", "tg_caption": "подпись к ролику до 200 знаков"}'),
    }
    raw = call_grok(STORY_RULES + "\n\n" + ctx + hist + pblock + tasks[stage],
                    max_tokens=900)
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise SystemExit("шаг %s: Grok не вернул JSON\n%s" % (stage, raw[:300]))
    return json.loads(m.group(0))


def tg_env():
    env = {}
    p = "/opt/vps-audit/laplace/tg.env"
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def send(video, caption):
    env = tg_env()
    tok, chat = env.get("GS_TG_BOT_TOKEN"), env.get("GS_TG_CHAT_ID")
    if not tok or not chat:
        log("нет токена — ролик остался на диске")
        return False
    d = dur(video)
    r = run(["curl", "-sS", "-o", "/tmp/tg.json", "-w", "%{http_code}",
             "https://api.telegram.org/bot%s/sendVideo" % tok,
             "-F", "chat_id=%s" % chat, "-F", "supports_streaming=true",
             "-F", "width=%d" % W, "-F", "height=%d" % H, "-F", "duration=%d" % int(d),
             "-F", "caption=%s" % caption[:1000], "-F", "video=@%s" % video])
    return r.stdout.strip().endswith("200")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dubles", type=int, default=4, help="вариантов кадра на сцену")
    ap.add_argument("--no-send", action="store_true")
    ap.add_argument("--reuse-scenes", action="store_true",
                    help="брать готовые work/scene<i>.jpg, не генерировать заново")
    ap.add_argument("--theme-json", default=None, help="взять тему из файла")
    ap.add_argument("--script-json", default=None,
                    help="готовый сценарий: {cards:[{voice,big,caption,shot}], kinds:[...], tg_caption}")
    a = ap.parse_args()

    for d in (OUT, WORK):
        os.makedirs(d, exist_ok=True)

    if a.theme_json:
        theme = json.load(open(a.theme_json, encoding="utf-8"))
        log("тема из файла: %s" % theme["title"][:60])
    else:
        log("выбираю тему")
        theme = pick_theme()
    if not theme:
        log("нет свежих сюжетов — пропускаю")
        return 0
    log("тема: %s (r=%s, intensity=%s)" % (theme["title"][:60], theme["rel"], theme["intensity"]))

    register = pick_register(theme)

    # --- слайды, которые существуют до текста
    shot_png = os.path.join(WORK, "news.png")
    react_png = os.path.join(WORK, "react.png")
    link = theme.get("link") or ""
    rlink = reaction_link(theme)
    have_shot = have_react = False
    if "reddit.com" in link:
        have_shot, have_react = reddit_cards(link, shot_png, react_png)
    else:
        if link:
            have_shot = news_screenshot(link, shot_png) and screenshot_ok(shot_png)
        if rlink:
            _, have_react = reddit_cards(rlink, os.path.join(WORK, "unused.png"), react_png)
    log("слайды: инфоповод %s, реакция %s" % (have_shot, have_react))

    log("свежий X-свип по инфоповоду (дипсерч)")
    fresh = x_sweep(theme)
    if fresh:
        v = dict(theme.get("verdict_json") or {})
        v["fresh_x"] = {k: fresh.get(k) for k in ("intensity", "emocia", "one_liner", "objections")}
        theme["verdict_json"] = v
        if not have_react and fresh.get("quotes"):
            qf = os.path.join(WORK, "xq.json")
            json.dump({"quotes": fresh["quotes"]}, open(qf, "w", encoding="utf-8"),
                      ensure_ascii=False)
            xh = os.path.join(WORK, "card_x.html")
            r = run(["python3", "/opt/shorts/reddit_card.py", "xquotes", qf, xh], timeout=60)
            if (r.returncode == 0 and news_screenshot("file://" + xh, react_png)
                    and card_lang_ok(react_png)):
                have_react = True
                log("слайд реакции: карточка X-цитат")

    if a.script_json:
        # Готовый сценарий: слова и раскадровка пришли извне, петлю не гоняем.
        sc = json.load(open(a.script_json, encoding="utf-8"))
        cards = sc["cards"]
        kinds = sc.get("kinds") or (["news_shot" if have_shot else "footage"] +
                                    ["footage"] * (len(cards) - 1))
        if not have_shot:
            kinds = ["footage" if k == "news_shot" else k for k in kinds]
            log("  скрина инфоповода нет — сцена уходит в футаж")
        if not have_react:
            kinds = ["footage" if k == "reaction_shot" else k for k in kinds]
        script = {"theme": sc.get("theme", theme["title"][:40]), "cards": cards,
                  "tg_caption": sc.get("tg_caption", "")}
        log("сценарий из файла: %d сцен, kinds=%s" % (len(cards), ",".join(kinds)))
        for i, c in enumerate(cards):
            log("  %d [%s] %s" % (i + 1, kinds[i], c["voice"][:60]))
    else:
        # --- нарративная петля
        history = []
        log("сцена 1: восприятие слайда инфоповода")
        p1 = perceive(shot_png, "Это первый слайд — инфоповод.") if have_shot else {}
        s1 = story_step(theme, history, p1, "hook")
        history.append(s1["voice"])
        log("  голос: %s" % s1["voice"][:70])

        log("сцена 2: кадр под вопрос зрителя")
        img2 = os.path.join(WORK, "scene1.jpg")
        picks = gen_image_batch("СУБЪЕКТ: %s.\n%s" % (
            (s1.get("next_shot") or "крупный план радиатора").rstrip("."),
            STYLE if register == "product" else STYLE_ART), WORK, 1, a.dubles)
        os.replace(vision_pick(picks, register), img2)
        for pp in picks:
            if os.path.exists(pp):
                os.remove(pp)
        p2 = perceive(img2, "Это второй слайд — пояснение.")
        s2 = story_step(theme, history, p2, "explain")
        history.append(s2["voice"])
        log("  голос: %s" % s2["voice"][:70])

        log("сцена 3: восприятие реакций")
        p3 = perceive(react_png, "Это слайд с реальными комментариями обсуждения.") if have_react else {}
        s3 = story_step(theme, history, p3, "reaction")
        history.append(s3["voice"])
        log("  голос: %s" % s3["voice"][:70])

        log("сцена 4: прогноз из всей цепочки")
        s4 = story_step(theme, history, {}, "forecast")
        history.append(s4["voice"])
        log("  голос: %s" % s4["voice"][:70])

        cards = [
            {"voice": s1["voice"]},
            {"voice": s2["voice"], "big": s2.get("big", ""), "caption": s2.get("caption", "")},
            {"voice": s3["voice"]},
            {"voice": s4["voice"], "big": s4.get("big", ""), "caption": s4.get("caption", "")},
        ]
        script = {"theme": theme["title"][:40], "cards": cards,
                  "tg_caption": s4.get("tg_caption", "")}
        kinds = ["news_shot" if have_shot else "footage", "footage",
                 "reaction_shot" if have_react else "footage", "comment"]
    log("озвучиваю (%d реплик, %s)" % (len(cards), CUSTOM_VOICE or VOICE))
    parts = synth_custom(cards) if CUSTOM_VOICE else synth(cards)
    audio, spans = concat_audio(parts, os.path.join(WORK, "voice.mp3"))
    total = spans[-1][1]
    log("аудио: %.1f сек" % total)

    # --- клипы по слайдам
    clips = []
    for i, (c, (t0, t1)) in enumerate(zip(cards, spans)):
        span = t1 - t0
        clip = os.path.join(WORK, "clip%d.mp4" % i)
        kind = kinds[i]
        if kind == "news_shot":
            make_shot_clip(shot_png, span, clip, i, total_shots=2, shot_no=0)
        elif kind == "reaction_shot":
            make_shot_clip(react_png, span, clip, i, total_shots=2, shot_no=1)
        elif kind == "comment":
            r = run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi",
                     "-i", "gradients=s=%dx%d:c0=0x101318:c1=0x1C2027:x0=0:y0=0:x1=0:y1=%d:d=%.3f"
                     % (W, H, H, max(span, 0.5)),
                     "-vf", "format=yuv420p", "-r", str(FPS), "-t", "%.3f" % span,
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", clip])
            if r.returncode != 0:
                raise SystemExit("градиент: %s" % r.stderr[-300:])
        else:
            # Кадр сцены: при готовом сценарии берём из card['shot'], иначе — кадр петли.
            img = None
            ready = os.path.join(WORK, "scene%d.jpg" % i)
            if a.reuse_scenes and os.path.exists(ready) and os.path.getsize(ready) > 100000:
                img = ready
                log("  сцена %d: беру готовый кадр (reuse)" % (i + 1))
            shot_txt = (c.get("shot") or "").strip()
            if img is None and shot_txt:
                style = STYLE if register == "product" else STYLE_ART
                prompt = "СУБЪЕКТ: %s.\n%s" % (shot_txt.rstrip("."), style)
                picks = gen_image_batch(prompt, WORK, i, a.dubles)
                if picks:
                    img = os.path.join(WORK, "scene%d.jpg" % i)
                    os.replace(vision_pick(picks, register), img)
                    for pp in picks:
                        if os.path.exists(pp):
                            os.remove(pp)
            if img is None:
                img = locals().get("img2")
            if img is None:
                # нет кадра вовсе — держим градиент, ролик всё равно собирается
                r = run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi",
                         "-i", "gradients=s=%dx%d:c0=0x101318:c1=0x1C2027:x0=0:y0=0:x1=0:y1=%d:d=%.3f"
                         % (W, H, H, max(span, 0.5)),
                         "-vf", "format=yuv420p", "-r", str(FPS), "-t", "%.3f" % span,
                         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", clip])
                if r.returncode != 0:
                    raise SystemExit("градиент-фолбэк: %s" % r.stderr[-300:])
            else:
                make_clip(img, span, clip, i)
        clips.append(clip)

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = os.path.join(OUT, "gen-%s.mp4" % stamp)
    log("собираю")
    assemble(clips, cards, spans, audio, out, kinds)

    log("гейт")
    g = run(["bash", "/opt/shorts/verify.sh", out])
    print(g.stdout)
    if g.returncode != 0:
        log("ГЕЙТ НЕ ПРОЙДЕН — не отправляю")
        return 1

    # ПОКАДРОВЫЙ ГЕЙТ (Гор 08-21): каждый кадр смотрит vision-модель на посторонний
    # контент. Один плохой кадр — ролик НЕ уходит. Ловит рекламу-заглушку, мем-брак,
    # не-по-теме — то, что структурный гейт verify.sh увидеть не может.
    log("покадровый гейт")
    fg = run(["/usr/local/lib/hermes-agent/venv/bin/python3", "/opt/shorts/frame_gate.py",
              out, theme.get("gate_topic")
              or "компьютерное железо и комплектующие ПК: видеокарты, разъёмы, платы, "
                 "память, блоки питания, карточки с текстом по теме"])
    print(fg.stdout[-1500:])
    if fg.returncode != 0:
        log("ПОКАДРОВЫЙ ГЕЙТ НЕ ПРОЙДЕН — ролик НЕ отправляю, оставляю на диске для разбора")
        return 1

    # ГЕЙТ ПЛАТФОРМЕННОЙ СВЯЗНОСТИ (Гор 08-22). Ловит ошибку не в кадре, а в
    # СОЧЕТАНИИ: процессор AMD в гнезде Intel, ноутбучную планку в настольном
    # сюжете, разъём с несуществующим числом жил, расхождение голоса с
    # картинкой. Покадровый гейт такое пропускает по устройству — он спрашивает
    # «годен ли кадр», а каждая половина несовместимой пары годна по отдельности.
    log("платформенный гейт")
    tf = os.path.join(OUT, "_pg_theme.json")
    sf = os.path.join(OUT, "_pg_script.json")
    json.dump(theme, io.open(tf, "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(script, io.open(sf, "w", encoding="utf-8"), ensure_ascii=False)
    pgate = run(["/opt/hermes/venv/bin/python3", "/opt/shorts/platform_gate.py",
                 out, "--theme", tf, "--script", sf, "--step", "3.0"])
    print(pgate.stdout[-1800:])
    if pgate.returncode != 0:
        log("ПЛАТФОРМЕННЫЙ ГЕЙТ НЕ ПРОЙДЕН — ролик НЕ отправляю, оставляю на разбор")
        return 1

    log("готово: %s (%.1f МБ, %.1f сек)" % (out, os.path.getsize(out) / 1048576, total))

    if not a.no_send:
        cap = "%s\n\nЧерновик · %s" % (script.get("tg_caption") or theme["title"], theme.get("link", ""))
        if send(out, cap):
            log("отправлено на утверждение")

    if not a.theme_json:
        sql("""INSERT INTO shorts_log (news_id, story_id, theme, script_json, video_path, duration_sec, status)
               VALUES (%d, %s, $$%s$$, $$%s$$, $$%s$$, %.2f, 'draft');""" % (
        theme["id"], theme["story_id"] if theme.get("story_id") else "NULL",
        script.get("theme", ""), json.dumps(script, ensure_ascii=False), out, total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
