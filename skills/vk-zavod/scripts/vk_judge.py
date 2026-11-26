# -*- coding: utf-8 -*-
"""Местный судья ВК-постов: «sudya» (Qwen3.5-122B-A10B) на домашней 5090, линзы «тысячи глаз».

Гор 01.10.2026: «подключи грок и локаль к ведению вк». Роли:
  Grok по подписке (VK_WRITER_MODEL, прокси :8650) пишет текст и правит его по находкам;
  sudya дома (VK_JUDGE_MODEL, Ollama 10.77.0.2:11434) смотрит узкими линзами, каждая претензия с цитатой;
  fact_gate (Grok reasoning) после судьи — обязательный фактчекер, его судья не заменяет.
Дом не отвечает -> те же линзы судит подписка (как у завода сайта: «дом не отвечает, судит подписка»).

Скил sudya-1000-glaz: узкий вопрос вместо составного, признак вместо запрета, цитата на каждую
претензию, итог собирает код, а не модель. Пост ВК короткий (до 900 знаков), размышление выключено
на всех линзах: 01.10 линза чисел с размышлением упёрлась в таймаут, без него ~20 с на вызов;
цифры после судьи ещё раз проверяет фактчекер. Ответ не по схеме - не «чисто», а линза уходит подписке.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

JUDGE_URL = os.environ.get("VK_JUDGE_URL", "http://10.77.0.2:11434/api/chat")
JUDGE_MODEL = os.environ.get("VK_JUDGE_MODEL", "sudya")
PROXY = os.environ.get("SHORTSMAKER_PROXY", "http://127.0.0.1:8650/v1/chat/completions")
FALLBACK_MODEL = os.environ.get("VK_JUDGE_FALLBACK", "grok-4.6")

SYSTEM = ("Ты редактор мастерской Golden Sample PCs (Москва, сборка и тюнинг ПК). Проверяешь пост для "
          "сообщества ВКонтакте. Отвечаешь только JSON по схеме, по-русски, без вступлений. "
          "Единственный источник фактов и чисел — МАТЕРИАЛ ниже. Каждая находка — точная цитата из ТЕКСТА.")

SCHEMA = {"type": "object", "properties": {
    "items": {"type": "array", "items": {"type": "object", "properties": {
        "quote": {"type": "string"}, "verdict": {"type": "string", "enum": ["ok", "fix", "reject"]},
        "why": {"type": "string"}}, "required": ["quote", "verdict", "why"]}},
    "summary": {"type": "string"}}, "required": ["items", "summary"]}

# (ключ, думать, линза, признак). reject в numbers/prices — пост не выходит; fix — одна правка писателем.
LENSES = [
    ("numbers", False,
     "Перечисли ВСЕ числа ТЕКСТА: цифры, проценты, градусы, гигагерцы, ватты, гигабайты, сроки, цены, даты.",
     "Для каждого числа найди в МАТЕРИАЛЕ место, где оно есть. Есть — verdict ok, в why укажи это место. "
     "Нет в материале или в материале другое значение — verdict reject. Модель видеокарты «RTX 5080» — "
     "тоже число: проверь, что она есть в материале."),
    ("prices", False,
     "Найди цены заказной сборки ПК, скидки, бонусы и подарки клиенту, имена и данные клиентов.",
     "Правило мастерской: цены заказных сборок, скидки и имена клиентов в постах не публикуем — verdict "
     "reject. Цена готовой машины с витрины, которая есть в МАТЕРИАЛЕ вместе с датой, и цена услуги «от» "
     "из МАТЕРИАЛА — verdict ok. Нет таких фраз — пустой items."),
    ("pressure", False,
     "Найди фразы давления и рекламного тона.",
     "Признаки: призыв купить или успеть, «лучший», «самый», «гарантируем», «всегда», «любой», «только у "
     "нас», «выгодно», обещание срока или цены, которого нет в МАТЕРИАЛЕ. Каждой — verdict fix. "
     "Спокойное «напишите нам в сообщения» в конце — ok, это не давление."),
    ("machine", False,
     "Найди машинные и канцелярские обороты.",
     "Признаки: «давайте разберёмся», «в современном мире», «стоит отметить», «важно понимать», «не просто "
     "X, а Y», «является», «осуществляет», риторический вопрос в первой строке, восклицательные знаки "
     "подряд, эмодзи вместо слов. Каждому — verdict fix."),
    ("lead", False,
     "Проверь начало: первые 140 знаков ТЕКСТА.",
     "Если в первых 140 знаках нет сути поста и нет ни одной цифры или конкретного факта из МАТЕРИАЛА — "
     "одна находка verdict fix с цитатой этих знаков. Если суть и факт есть — пустой items."),
    ("coherence", False,
     "Найди сломанные и пустые предложения.",
     "Признаки: ошибка согласования или пропущенное слово («цифры подтверждают стало хуже»), оборванная "
     "фраза, одна мысль повторена разными словами («стало хуже», «ситуация плохая»), оценка без факта "
     "(«ситуация плохая», «всё сложно»), абзац, из которого читатель не узнаёт ничего нового, обещание без "
     "содержания («приводим конкретные цифры», а цифр в тексте нет; «рассказываем, почему», а причины нет). "
     "Каждому — verdict fix. Связный текст с фактами — пустой items."),
    ("voice", False,
     "Проверь голос мастерской.",
     "Пишет «мы» мастерской спокойным тоном, как другу. Нарушения: «дорогие подписчики», «друзья!», "
     "сленг, капс, «вы» с большой буквы, обещания от имени производителя. Каждому — verdict fix."),
]
HARD = {"numbers", "prices"}


FORMAT = ('ОТВЕТ строго JSON: {"items": [{"quote": "точная цитата из ТЕКСТА", "verdict": "ok" | "fix" | '
          '"reject", "why": "почему"}], "summary": "итог одной фразой"}. Ключи ровно такие. Нет находок - '
          '"items": []. Пример: {"items": [{"quote": "успейте записаться", "verdict": "fix", "why": "давление '
          'сроком"}], "summary": "одна фраза давления"}')
QUOTE_KEYS = ("quote", "цитата", "text_fragment", "fragment", "text")


def _first(d, keys):
    for k in keys:
        if isinstance(d.get(k), str):
            return d[k]
    return ""


def _items(raw):
    """Ответ модели -> список находок. Непонятная структура - ValueError: линза уходит подписке,
    а не считается «замечаний нет» (01.10: дом вернул findings вместо items, и линза молча прошла)."""
    m = re.search(r"\{.*\}", raw, re.S)
    data = json.loads(m.group(0)) if m else None
    if not isinstance(data, dict):
        raise ValueError("ответ не JSON-объект")
    if isinstance(data.get("items"), list):
        return [x for x in data["items"] if isinstance(x, dict)]
    raise ValueError("ответ не по схеме: ключи %s" % ", ".join(list(data)[:5]))


class JudgeDown(Exception):
    pass


def _ollama(system, user, think):
    body = {"model": JUDGE_MODEL, "stream": False, "keep_alive": "30m", "think": think, "format": SCHEMA,
            "options": ({"temperature": 1.0, "top_p": 0.95, "top_k": 20, "presence_penalty": 1.5} if think else
                        {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 1.5}),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(JUDGE_URL, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=int(os.environ.get("VK_JUDGE_TIMEOUT", "300"))) as r:
        return json.loads(r.read().decode("utf-8"))["message"]["content"]


def _grok(system, user):
    # 1500 токенов обрезали JSON линзы чисел на статье Дзена (02.10) - отказ вместо проверки
    body = {"model": FALLBACK_MODEL, "max_tokens": int(os.environ.get("VK_JUDGE_GROK_TOKENS", "4000")),
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user + "\nСХЕМА ОТВЕТА: " + json.dumps(SCHEMA, ensure_ascii=False)}]}
    data = json.dumps(body).encode("utf-8")
    for attempt in range(3):                          # 02.10: прокси отдавал 502/520 на длинных линзах - повтор
        try:
            req = urllib.request.Request(PROXY, data=data,
                                         headers={"Content-Type": "application/json", "X-Meter-Source": "vk-judge"})
            with urllib.request.urlopen(req, timeout=600) as r:
                return json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == 2:
                raise
        except urllib.error.URLError:
            if attempt == 2:
                raise
        time.sleep(30)


def home_alive():
    try:
        with urllib.request.urlopen(JUDGE_URL.replace("/api/chat", "/api/tags"), timeout=8) as r:
            return JUDGE_MODEL.split(":")[0] in r.read().decode("utf-8")
    except (OSError, urllib.error.URLError, ValueError):
        return False


def lens(key, text, material, local, log=print):
    _, think, what, how = next(l for l in LENSES if l[0] == key)
    cap = int(os.environ.get("VK_JUDGE_MATERIAL_CAP", "6000"))   # Дзен: статья длиннее поста, материал до 12000
    user = "ЛИНЗА: %s\nКАК: %s\n\nМАТЕРИАЛ:\n%s\n\nТЕКСТ:\n%s\n\n%s" % (what, how, material[:cap], text, FORMAT)
    raw = _ollama(SYSTEM, user, think) if local else _grok(SYSTEM, user)
    flat = re.sub(r"\s+", " ", text)
    out = []
    for it in _items(raw):
        q = _first(it, QUOTE_KEYS).strip().strip("«»\"")
        v = _first(it, ("verdict", "вердикт")).lower()
        if v not in ("ok", "fix", "reject"):
            raise ValueError("линза %s: вердикт вне схемы: %r" % (key, v[:40]))
        if v == "ok" or not q:
            continue
        if re.sub(r"\s+", " ", q) not in flat:      # претензия без настоящей цитаты кодом не принимается
            log("    судья %s: цитаты нет в тексте, пропуск: %s" % (key, q[:60]))
            continue
        # 01.10: судья отклонил пост за «Steam Frame», которого «нет в материале», - а он там был.
        # Числа и названия проверяет код: цитата дословно есть в материале - претензия снимается.
        # Только линза чисел: цены сборок бывают и в материале («сколько стоит»), но их не публикуем всё равно.
        # Совпадение по границам слова и числа: «8 ГБ» не находится внутри «128 ГБ», «8» и «80» сами не снимаются.
        qn, mn = re.sub(r"\s+", " ", q).lower(), re.sub(r"\s+", " ", material).lower()
        if key == "numbers" and len(re.sub(r"\W", "", qn)) >= 2 and \
                re.search(r"(?<![\w.,])" + re.escape(qn) + r"(?!\w|[.,]\d)", mn):
            log("    судья %s: цитата есть в материале, претензия снята: %s" % (key, q[:60]))
            continue
        out.append({"lens": key, "verdict": it["verdict"], "quote": q, "why": (it.get("why") or "")[:200]})
    return out


def judge(text, material, log=print, keys=None):
    """Прогоняет линзы. Возвращает (находки, кто судил). JudgeDown — не смог никто."""
    local = home_alive()
    who = "дом (%s)" % JUDGE_MODEL if local else "подписка (%s), дом не отвечает" % FALLBACK_MODEL
    found = []
    for key in keys or [l[0] for l in LENSES]:
        try:
            found += lens(key, text, material, local, log)
        except (OSError, urllib.error.URLError, ValueError, KeyError) as e:
            if local:                                # дом упал посреди прогона — эту линзу судит подписка
                log("    судья %s: дом не ответил (%s), линза уходит подписке" % (key, str(e)[:80]))
                try:
                    found += lens(key, text, material, False, log)
                    continue
                except (OSError, urllib.error.URLError, ValueError, KeyError) as e2:
                    e = e2
            raise JudgeDown("линза %s: %s" % (key, str(e)[:160]))
    return found, who


def verdict(found):
    hard = [f for f in found if f["verdict"] == "reject" and f["lens"] in HARD]
    fixes = [f for f in found if f not in hard]
    return hard, fixes


def fix_note(fixes):
    """Записка писателю: одна строка на цитату (разные линзы часто цепляют одну и ту же фразу)."""
    seen, out = set(), []
    for f in fixes:
        if f["quote"] in seen:
            continue
        seen.add(f["quote"])
        out.append("«%s» — %s" % (f["quote"][:80], f["why"]))
    return "; ".join(out)
