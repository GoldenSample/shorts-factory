# -*- coding: utf-8 -*-
"""Детерминированная проверка текста GSPC под площадку до выдачи Гору.

Только stdlib, сеть не трогает. Деньги и мат проверяет кодом фабрики, если он лежит рядом:
shortsmaker/vps/price_rule.py (регламент подорожания) и rubrics.py (MAT, CHAT, STAMPS).
Путь к ним: переменная GSPC_VPS_DIR или C:/Users/Administrator/Documents/git/shortsmaker/vps.

    py -3 post_lint.py --platform tg post.txt
    py -3 post_lint.py --platform vk-clip - < caption.txt
    py -3 post_lint.py --platform yt-comment comment.txt

Площадки: tg, vk, vk-clip, dzen, dzen-post, max, yt-desc, и закреп/первый комментарий:
tg-comment, vk-comment, yt-comment, dzen-comment.
Код выхода: 0 чисто, 1 есть ОШИБКА (в публикацию не идёт), 2 только ВНИМАНИЕ.
"""
import argparse
import os
import re
import sys

sys.dont_write_bytecode = True  # не сорить .pyc в репо shortsmaker
VPS = os.environ.get("GSPC_VPS_DIR", "C:/Users/Administrator/Documents/git/shortsmaker/vps")
PR = RB = None
if os.path.isdir(VPS):
    sys.path.insert(0, VPS)
    try:
        import price_rule as PR  # noqa: E402
    except Exception:
        PR = None
    try:
        import rubrics as RB  # noqa: E402
    except Exception:
        RB = None

W = r"(?<![а-яёa-z])"
E = r"(?![а-яёa-z])"
SENT = re.compile(r"(?<=[.!?…])\s+")
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2B06\u2194-\u21AA]")
LINK = re.compile(r"(?:https?://|www\.)\S+|(?<![\w@/.])(?:[a-z0-9-]+\.)+(?:ru|com|pro|me|be|net|org|io)\b(?:/\S*)?", re.I)
OTHER_PLATFORMS = re.compile(W + r"(?:telegram|телеграм\w*|тг|tg|ютуб\w*|youtube|rutube|рутуб\w*|дзен\w*|dzen)" + E, re.I)
TG_ONLY = re.compile(W + r"(?:telegram|телеграм\w*|тг|tg|t\.me|@goldensamplepcs|@gspclab)" + E, re.I)
INSTA = re.compile(W + r"(?:instagram|инстаграм\w*|инст[аеу]?|рилс\w*)" + E, re.I)
PRICE = re.compile(r"₽|" + W + r"(?:руб\w*|тыс\.?\s*р\b|смет\w*|прайс\w*)" + E + r"|\d\s*(?:к|тыс\.?|000)\s*(?:₽|р\b|руб)", re.I)
PAY = re.compile(W + r"(?:наличн\w*|налом|за карт\w*|картой дороже|оплат\w* карт\w*)" + E, re.I)
WARRANTY3 = re.compile(r"гаранти\w*\s+(?:до\s+)?(?:3|тр[её]х|три)\s+(?:год|лет)", re.I)
STUBS = re.compile(r"ждут\s+(?:реальных\s+)?тестов|хвалят\s+за|народ\s+ворчит|вызвал\w*\s+спор\w*|может\s+стать|пока\s+рано\s+судить|"
                   r"время\s+покажет|решать\s+вам", re.I)
SUPER = re.compile(W + r"(?:мощн\w*|флагманск\w*|топов\w*|уникальн\w*|невероятн\w*|революцион\w*|нового\s+поколения|лучш(?:ий|ая|ее|ие|его|ей|их|ую|им|ими|ему))" + E, re.I)
PRESSURE = re.compile(W + r"(?:купи|купите|успей\w*|спеши\w*|только\s+сегодня|скидк\w*|акци[яиюей]\w*|ниже\s+рыночн\w*|не\s+упусти\w*)" + E, re.I)
JARGON = re.compile(W + r"(?:скам\w*|имба|топчик|кринж\w*|зашквар\w*|бомбит|лол|кек|изи|рофл\w*)" + E, re.I)
TY = re.compile(W + r"(?:ты|тебя|тебе|тобой|твой|твоя|твоё|твои|твою|твоего|твоей|твоих|напиши|пиши|смотри|бери|ставь|проверь|хочешь|видишь)" + E, re.I)
VY = re.compile(W + r"(?:вы|вас|вам|вами|ваш\w*|напишите|пишите|смотрите|берите|ставьте|проверьте|подпишитесь|подписывайтесь|хотите|видите)" + E, re.I)
SOURCE = re.compile(r"замер\w*\s+мастерской|замеры:|источник\w*:|по\s+данным|видео:|кадры:|вскрытие:|по\s+тесту|research\s+lab", re.I)
UNITS = re.compile(r"\d\s*(?:%|гб|тб|fps|фпс|вт|°|мгц|ггц|мм|в\b|мв|а\b|кадр)", re.I)
APHORISM = re.compile(r"(?:^|[.!?]\s+)Это\s+не\s+[^.!?]{1,30}[.!?]\s+Это\s+[^.!?]{1,30}[.!?]")
CAPS_RU = re.compile(r"(?<![А-ЯЁа-яё])[А-ЯЁ]{4,}(?![А-ЯЁа-яё])")
VK_SIGN = "Golden Sample PCs · мастерская сборки и тюнинга ПК · Москва"

LIMITS = {  # (мин, мягкий макс, жёсткий макс) в знаках
    "tg": (20, 1024, 4096), "vk": (400, 900, 4000), "vk-clip": (250, 600, 2000),
    "dzen": (4500, 8000, 40000), "dzen-post": (200, 4096, 4096), "max": (20, 1500, 4000),
    "yt-desc": (50, 1500, 5000),
}
COMMENT = {"tg-comment", "vk-comment", "yt-comment", "dzen-comment"}


def check(text, platform):
    errs, warns, info = [], [], []
    t = text.strip()
    low = t.lower()
    lines = [x for x in t.split("\n") if x.strip()]
    first = lines[0] if lines else ""
    if len(first) > 90 and SENT.search(first):
        first = SENT.split(first)[0]  # пост одним абзацем: крючок — первая фраза
    info.append(f"знаков {len(t)}, непустых строк {len(lines)}, крючок {len(first)}")

    # общие законы
    if PRICE.search(t):
        m = PRICE.search(t).group(0)
        (errs if platform in ("dzen", "dzen-post", "max") or platform in COMMENT else warns).append(
            f"цена/смета «{m}»: заказные сборки и услуги — никогда; во ВК только «сборка недели» из фида с датой")
    if PAY.search(t):
        errs.append(f"способ оплаты «{PAY.search(t).group(0)}»: про наличные и карту не пишем нигде")
    if WARRANTY3.search(t):
        errs.append("«гарантия 3 года» не пишем (dzen-master)")
    if INSTA.search(t):
        errs.append(f"«{INSTA.search(t).group(0)}»: Instagram в материалах не упоминаем")
    if PR:
        strict = bool(PR.is_rise(t))
        m = PR.money_talk(t, strict=strict)
        if m:
            errs.append(f"регламент подорожания{' (тема роста цен)' if strict else ''}: «{m}»")
    else:
        info.append("price_rule.py не найден: регламент подорожания не проверен")
    if RB:
        m = RB.MAT.search(t)
        if m:
            errs.append(f"мат «{m.group(0)}»")
        m = RB.CHAT.search(t)
        if m:
            warns.append(f"чат-маркер «{m.group(0)}»")
        for rx in RB.STAMPS:
            m = re.search(rx, t, re.I)
            if m:
                warns.append(f"штамп пересказа «{m.group(0)}»")
    else:
        info.append("rubrics.py не найден: мат и штампы не проверены")
    for rx, msg in ((STUBS, "заглушка"), (PRESSURE, "давление")):
        m = rx.search(t)
        if m:
            warns.append(f"{msg} «{m.group(0)}»")
    for m in SUPER.finditer(t):
        before = t[:m.start()]
        if before.count("«") > before.count("»") or before.count("„") > before.count("“"):
            continue  # слово вендора в кавычках — приём «вендор против факта»
        warns.append(f"превосходное «{m.group(0)}» без кавычек: факт вместо оценки")
        break
    if APHORISM.search(t):
        warns.append("«Это не X. Это Y.» — парный афоризм, «пишешь как дипсик»")
    ty, vy = len(TY.findall(low)), len(VY.findall(low))
    if ty and vy:
        warns.append(f"смешано обращение: «ты» {ty}, «вы» {vy}")
    elif ty:
        warns.append(f"обращение на «ты» ({ty}): в постах и комментариях на «вы» (Гор 14.10)")
    emo = len(EMOJI.findall(t.replace("▪", "").replace("📌", "")))
    if emo > 1:
        warns.append(f"эмодзи {emo}: не больше одного функционального")
    if "—" in first:
        warns.append("длинное тире в первой строке")
    for p in t.split("\n"):
        if len(p) > 450 and platform not in ("dzen",):
            warns.append(f"абзац {len(p)} знаков: на телефоне больше 8 строк, разбить")
            break
    sents = [len(s.split()) for line in t.split("\n") for s in SENT.split(line.strip()) if s.strip()]
    run = best = 0
    for n in sents:
        run = run + 1 if n <= 4 else 0
        best = max(best, run)
    if best >= 3:
        warns.append(f"{best} коротких фраз подряд: метроном")
    tags = re.findall(r"(?<!\w)#[\wа-яё]+", t, re.I)
    links = LINK.findall(t)

    # площадки
    if platform in LIMITS:
        lo, soft, hard = LIMITS[platform]
        if len(t) > hard:
            errs.append(f"{len(t)} знаков, предел площадки {hard}")
        elif len(t) > soft:
            warns.append(f"{len(t)} знаков, норма до {soft}" + (" (подпись к медиа без Premium — 1024)" if platform == "tg" else ""))
        elif len(t) < lo:
            warns.append(f"{len(t)} знаков, коротко для площадки (от {lo})")
    if platform == "tg":
        if tags:
            warns.append(f"хэштеги {len(tags)}: в канале 0 из 26 постов")
        if len(first) > 90:
            warns.append(f"крючок {len(first)} знаков, норма 40–90")
        if UNITS.search(t) and not SOURCE.search(t):
            warns.append("цифры без строки источника: свои — «Замер мастерской…», чужие — «Замеры: …»")
    if platform in ("vk", "vk-clip", "vk-comment"):
        if links:
            errs.append(f"ссылка во ВК «{links[0]}»: только кнопка и описание сообщества")
        m = OTHER_PLATFORMS.search(t) or re.search(r"(?<![\w.])@\w+", t)
        if m:
            errs.append(f"упоминание другой площадки или @-ника во ВК «{m.group(0)}»")
        if platform != "vk-comment":
            lim = 2 if platform == "vk" else 3
            if len(tags) > lim:
                errs.append(f"хэштегов {len(tags)}, предел {lim}")
            if platform == "vk-clip" and len(tags) < 2:
                warns.append("клипу нужны 2–3 хэштега в конце")
            if not re.search(r"\d", t[:140]):
                warns.append("в первых 140 знаках нет цифры: суть с цифрой из материала")
            if VK_SIGN not in t:
                warns.append(f"нет подписи «{VK_SIGN}» (vk_poster ставит сам, вручную — дописать)")
        if CAPS_RU.search(t):
            warns.append(f"капс «{CAPS_RU.search(t).group(0)}»")
    if platform in ("dzen", "dzen-post", "dzen-comment"):
        head = t[:1000]
        if platform != "dzen-comment" and LINK.search(head):
            errs.append("ссылка в первых 1000 знаках: Дзен режет карточку")
        if len(links) > 1:
            warns.append(f"ссылок {len(links)}: в статье одна, в финале, с UTM")
        if re.search(r"подробн\w*\s+(?:в|на)\s+(?:тг|телеграм\w*|канал\w*|сайт\w*)", t, re.I):
            errs.append("«подробнее в …» — частичный контент, только подписчикам")
        if platform == "dzen-comment" and TG_ONLY.search(t):
            errs.append("Telegram в комментарии Дзена: анонсы в ТГ запрещены")
        if re.search(r"\?!|!!|!\?", t):
            errs.append("«?!» / «!!» — нарушение карточки Дзена")
        m = JARGON.search(t)
        if m:
            warns.append(f"жаргон «{m.group(0)}»: в Дзене карточка не идёт в ленту")
        if CAPS_RU.search(t):
            warns.append(f"капс «{CAPS_RU.search(t).group(0)}»")
        if platform == "dzen" and not (40 <= len(first) <= 100):
            warns.append(f"заголовок {len(first)} знаков, гейт 40–100, цель 50–90")
        if platform == "dzen" and first.rstrip().endswith("."):
            warns.append("точка в конце заголовка")
    if platform == "max":
        if TG_ONLY.search(t) or OTHER_PLATFORMS.search(t):
            m = TG_ONLY.search(t) or OTHER_PLATFORMS.search(t)
            errs.append(f"«{m.group(0)}» в MAX: подписи без Telegram и чужих площадок")
        bad = [x for x in links if "gspc-lab.pro" not in x]
        if bad:
            warns.append("ссылка в MAX не на gspc-lab.pro")
    if platform == "yt-desc":
        if "goldensamplepcs" not in low.split("\n")[0]:
            errs.append("первая строка описания без шапки t.me/goldensamplepcs (publish_pack.HEADER)")
    if platform in COMMENT:
        if len(lines) != 4:
            errs.append(f"строк {len(lines)}, в закрепе ровно 4")
        if not first.startswith("📌"):
            warns.append("первая строка без 📌")
        for i, ln in enumerate(lines, 1):
            if len(ln) > 52:
                warns.append(f"строка {i}: {len(ln)} знаков, предел 50 (+📌)")
        if tags:
            errs.append("хэштеги в закрепе")
        if ";" in t:
            warns.append("точка с запятой: одна строка — одна фраза")
        if platform == "yt-comment" and "goldensamplepcs" not in low:
            warns.append("на YouTube закреп ведёт в канал: @goldensamplepcs")
        if platform == "tg-comment" and len(links) > 1:
            warns.append("больше одной ссылки в первом комментарии")
    return errs, warns, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", required=True,
                    choices=sorted(set(LIMITS) | COMMENT))
    ap.add_argument("file", help="файл с текстом или - для stdin")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    text = sys.stdin.read() if a.file == "-" else open(a.file, encoding="utf-8").read()
    errs, warns, info = check(text, a.platform)
    for x in info:
        print("  ·", x)
    for x in errs:
        print("  ОШИБКА:", x)
    for x in warns:
        print("  ВНИМАНИЕ:", x)
    print("чисто" if not errs and not warns else f"ошибок {len(errs)}, внимания {len(warns)}")
    return 1 if errs else (2 if warns else 0)


if __name__ == "__main__":
    sys.exit(main())
