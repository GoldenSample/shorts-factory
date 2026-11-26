#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ГЕЙТ ПЛАТФОРМЕННОЙ СВЯЗНОСТИ (08-22, по требованию Гора).

Ловит то, что покадровый гейт не увидит ПО УСТРОЙСТВУ: ошибку не в кадре, а в
СОЧЕТАНИИ. Процессор AMD законен. Гнездо Intel законно. Процессор AMD в гнезде
Intel невозможен. На вопрос «годен ли кадр» такое отвечает «годен», потому что
каждая половина по отдельности в порядке.

УСТРОЙСТВО, оплаченное замерами 08-22:

1. НЕ ПОДСКАЗЫВАТЬ СУДЬЕ ОТВЕТ. Спрашивать «это AMD в интеловском гнезде?»
   нельзя: модель соглашается с тем, что ей предложили. Спрашиваем нейтрально —
   что видно, — а вывод делает КОД по таблице несовместимостей. Судья
   описывает, логика судит.

2. ОДИН ВОПРОС — ОДИН ПРИЗНАК. ЗАМЕРЕНО: многополевое извлечение эта модель НЕ
   ДЕРЖИТ. На одном и том же кадре она то отвечает по существу, то штампует
   «не видно» по всем семи полям и подмешивает отсебятину вроде «Ответ дан с
   AI». Узкие вопросы с одним выбором устойчивы: счёт гнёзд дал 3/3 без
   разброса на трёх разрешениях.

3. «НЕ ВИДНО» — ЗАКОННЫЙ ОТВЕТ, НО НЕ ПООЩРЯЕМЫЙ. Заставишь выбирать между AMD
   и Intel там, где их нет, — модель выдумает марку, и гейт нарожает
   противоречий на пустом месте. Назовёшь «не видно» нормальным и частым —
   получишь слепой гейт, пропускающий всё. Обе крайности проверены на живом.

4. СЛЕПОТА ОБЯЗАНА БЫТЬ ВИДИМОЙ. Кадры без железа считаются отдельно. Ноль
   ошибок при нуле признаков — это не «чисто», а «гейту не на что было
   смотреть», и он говорит об этом вслух.

5. СЧЁТ. ЗАМЕРЕНО: число жил модель считает неустойчиво — на соседних кадрах
   16 и 12 при одинаковых разъёмах (то считает мелкие сигнальные, то нет), на
   третьем 8/6/8. Поэтому блокируем НЕ «не то число», а число, которого у
   разъёмов не бывает вовсе, и только при единогласии трёх голосов. Ловит
   генератор, нарисовавший семь жил, и молчит на спорном.

6. ДВА УРОВНЯ. ОШИБКА — невозможное сочетание, ролик не уходит. ПОДОЗРЕНИЕ —
   возможное, но странное (ноутбучная планка в сюжете про настольный ПК бывает
   в сравнении): печатается, не блокирует. Флаг --strict блокирует и его.

    platform_gate.py <video.mp4> [--profile p.json] [--script s.json]
                     [--theme t.json] [--step 2.0] [--strict]

exit 0 = связно; exit 1 = найдено несовместимое сочетание.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request

MODEL = "grok-4.20-0309-non-reasoning"

# ---------------------------------------------------------------- знания

# Сокеты настольных платформ. style — где ножки:
#   lga — ножки в гнезде платы, у процессора плоские площадки (Intel всегда,
#         AMD начиная с AM5)
#   pga — ножки снизу на самом процессоре (AMD по AM4 включительно)
SOCKETS = {
    "am5":     {"vendor": "amd",   "style": "lga", "mem": ["ddr5"]},
    "am4":     {"vendor": "amd",   "style": "pga", "mem": ["ddr4"]},
    "lga1700": {"vendor": "intel", "style": "lga", "mem": ["ddr4", "ddr5"]},
    "lga1851": {"vendor": "intel", "style": "lga", "mem": ["ddr5"]},
}

# Сколько крупных силовых жил бывает у разъёмов питания. Число вне списка —
# признак, что генератор нарисовал отсебятину.
LEGAL_PINS = {4, 6, 8, 12, 16, 20, 24}

# Слова сценария, выдающие платформу.
TEXT_MARKS = {
    "cpu_amd":   r"(ryzen|райзен|threadripper|\bam4\b|\bam5\b|x3d|x670|x870|b650|b850)",
    "cpu_intel": r"(core ultra|кор ультра|интел|intel|lga\s?17|lga\s?18|z790|z890|b760|b860|arrow lake|raptor lake)",
    "gpu_nv":    r"(geforce|джифорс|nvidia|нвидиа|rtx|dlss|founders)",
    "gpu_amd":   r"(radeon|радеон|rdna|\bfsr\b|rx\s?9\d{3}|rx\s?7\d{3})",
    "laptop":    r"(ноутбук|лэптоп|laptop)",
}

# Есть ли вообще на что смотреть. Дешёвый отсев титров и абстракции.
Q_ANY = ("Виден ли на фотографии КРУПНЫМ ПЛАНОМ компьютерный компонент: "
         "материнская плата, процессор, видеокарта, планка памяти или разъём "
         "питания? Ответь одним словом: ДА или НЕТ.")

# Узкие вопросы: один признак — один вызов. У каждого есть выход «НЕТ».
FIELDS = [
    ("видеокарта",
     "Видна ли на фото видеокарта, и различима ли её марка? "
     "Ответь одним словом: NVIDIA, RADEON, ARC или НЕТ.",
     [("nvidia", "nvidia"), ("geforce", "nvidia"), ("radeon", "amd"), ("arc", "intel")]),
    ("процессор",
     "Виден ли на фото процессор, и различима ли надпись на его крышке? "
     "Ответь одним словом: AMD, INTEL или НЕТ.",
     [("amd", "amd"), ("intel", "intel")]),
    ("плата",
     "Видны ли на материнской плате логотипы или надписи производителя "
     "платформы? Ответь одним словом: AMD, INTEL или НЕТ.",
     [("amd", "amd"), ("intel", "intel")]),
    ("гнездо процессора",
     "Видно ли открытое гнездо процессора? Ответь одним словом: "
     "ГНЕЗДО (тонкие ножки торчат из гнезда платы), "
     "ПРОЦЕССОР (ножки снизу на самом процессоре) или НЕТ.",
     [("гнездо", "lga"), ("процессор", "pga")]),
    ("память",
     "Видны ли модули оперативной памяти? Ответь одним словом: "
     "ДЛИННАЯ (длинная настольная планка), КОРОТКАЯ (короткая ноутбучная), "
     "ПЛОСКАЯ (плоский модуль на винтах) или НЕТ.",
     [("длинн", "dimm"), ("коротк", "sodimm"), ("плоск", "camm2")]),
    # ЗАМЕР 08-22: на крупных планах деталей и на абстракции этот вопрос без
    # оговорки уверенно отвечал «ноутбук» — шесть ложных подозрений на ролике,
    # где ноутбука нет вовсе. Отказ от ответа надо разрешить явно.
    ("форма",
     "Виден ли на фото компьютер ЦЕЛИКОМ — системный блок или ноутбук? "
     "Если это крупный план отдельной детали, платы, разъёма, кабеля, "
     "или абстрактное изображение — отвечай НЕТ. "
     "Ответь одним словом: НАСТОЛЬНЫЙ, НОУТБУК или НЕТ.",
     [("настольн", "desktop"), ("ноутбук", "laptop")]),
    ("разъём питания",
     "Виден ли крупным планом разъём питания с круглыми гнёздами? "
     "Ответь одним словом: ДА или НЕТ.",
     [("да", "есть")]),
]

COUNT_Q = ("На фото разъём питания. Сосчитай ВСЕ КРУПНЫЕ круглые гнёзда, "
           "мелкие сигнальные не считай. Ответь ТОЛЬКО числом.")


def log(m):
    print(m, flush=True)


# ---------------------------------------------------------------- зрение

def creds():
    env = "/opt/shorts/console.env"
    if os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            if line.startswith("XAI_CONSOLE_KEY="):
                k = line.split("=", 1)[1].strip().strip('"').strip("'")
                if k:
                    return k, "https://api.x.ai/v1"
    sys.path.insert(0, "/usr/local/lib/hermes-agent")
    from tools.xai_http import resolve_xai_http_credentials
    c = resolve_xai_http_credentials() or {}
    if not c.get("api_key"):
        raise SystemExit("нет ключа для судьи")
    return c["api_key"], (c.get("base_url") or "https://api.x.ai/v1").rstrip("/")


def ask(png, question, key, base, max_tokens=8, tries=3):
    b64 = base64.b64encode(open(png, "rb").read()).decode()
    body = json.dumps({"model": MODEL, "max_tokens": max_tokens, "temperature": 0,
                       "messages": [{"role": "user", "content": [
                           {"type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64," + b64}},
                           {"type": "text", "text": question}]}]}).encode()
    for i in range(tries):
        try:
            req = urllib.request.Request(base + "/chat/completions", data=body,
                                        headers={"Authorization": "Bearer " + key,
                                                 "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read().decode())
            a = (d["choices"][0]["message"]["content"] or "").strip().lower()
            return a.strip("*_` .")      # модель оборачивает ответ в разметку
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def count_pins(png, key, base, votes=3):
    """Три голоса. Расхождение = счёт неустойчив, молчим."""
    got = []
    for _ in range(votes):
        try:
            m = re.search(r"\d+", ask(png, COUNT_Q, key, base, max_tokens=6))
            got.append(int(m.group()) if m else None)
        except Exception:
            return None
    return got[0] if len(set(got)) == 1 and got[0] is not None else None


def read_frame(png, key, base):
    """Признаки кадра. Пустой словарь = железа в кадре нет, это норма."""
    if "да" not in ask(png, Q_ANY, key, base):
        return {}
    f = {}
    for name, question, vocab in FIELDS:
        a = ask(png, question, key, base)
        if a.startswith("нет"):
            continue
        for needle, code in vocab:
            if needle in a:
                f[name] = code
                break
    if f.get("разъём питания"):
        n = count_pins(png, key, base)
        if n is not None:
            f["_жил"] = n
    return f


# ---------------------------------------------------------------- правила

def check_frame(f, prof):
    bad = []
    cpu, board = f.get("процессор"), f.get("плата")
    gnezdo, form = f.get("гнездо процессора"), f.get("форма")
    mem, gpu, pins = f.get("память"), f.get("видеокарта"), f.get("_жил")

    # --- физически невозможное внутри кадра
    if cpu and board and cpu != board:
        bad.append(("ОШИБКА", "процессор %s на плате %s" % (cpu.upper(), board.upper())))
    if gnezdo == "pga" and board == "intel":
        bad.append(("ОШИБКА", "ножки на процессоре у Intel: настольные Intel всегда LGA"))
    if gnezdo == "pga" and cpu == "intel":
        bad.append(("ОШИБКА", "ножки снизу на процессоре Intel — такого не бывает"))
    if form == "laptop" and mem == "dimm":
        bad.append(("ОШИБКА", "длинная настольная планка внутри ноутбука"))
    if isinstance(pins, int) and pins not in LEGAL_PINS:
        bad.append(("ОШИБКА", "разъём питания на %d крупных жил — такого не бывает "
                              "(бывает 4, 6, 8, 12, 16)" % pins))

    # --- против заявленной платформы ролика
    sock = prof.get("socket")
    if sock:
        s = SOCKETS[sock]
        if cpu and s["vendor"] != cpu:
            bad.append(("ОШИБКА", "процессор %s при заявленном сокете %s"
                        % (cpu.upper(), sock.upper())))
        if board and s["vendor"] != board:
            bad.append(("ОШИБКА", "плата %s при заявленном сокете %s"
                        % (board.upper(), sock.upper())))
        if gnezdo and s["style"] != gnezdo:
            bad.append(("ОШИБКА", "у сокета %s ножки %s, а в кадре наоборот"
                        % (sock.upper(),
                           "в гнезде платы" if s["style"] == "lga" else "на процессоре")))
        if mem == "sodimm":
            bad.append(("ПОДОЗРЕНИЕ",
                        "ноутбучная планка при настольном сокете %s" % sock.upper()))
    for want_key, seen, name in (("cpu", cpu, "процессор"), ("gpu", gpu, "видеокарта")):
        want = prof.get(want_key)
        if want and seen and seen != want:
            bad.append(("ОШИБКА", "%s %s, а ролик заявлен про %s"
                        % (name, seen.upper(), want.upper())))
    if prof.get("form") == "desktop" and form == "laptop":
        bad.append(("ПОДОЗРЕНИЕ", "ноутбук в кадре, а ролик про настольный ПК"))
    if prof.get("form") == "desktop" and mem == "sodimm" and not sock:
        bad.append(("ПОДОЗРЕНИЕ", "ноутбучная короткая планка в сюжете про настольный ПК"))
    return bad


def check_across(frames, prof):
    """Ролик про одну платформу не может показывать две разные марки."""
    bad = []
    for key, name in (("процессор", "процессора"), ("плата", "платы"),
                      ("видеокарта", "видеокарты")):
        pairs = [(t, f[key]) for t, f in frames if f.get(key)]
        if len(set(v for _, v in pairs)) > 1:
            where = ", ".join("%.1fс=%s" % (t, v.upper()) for t, v in pairs)
            bad.append(("ОШИБКА", "в одном ролике две разные марки %s: %s" % (name, where)))
    return bad


def check_script(script, prof):
    bad = []
    txt = " ".join((c.get("voice") or "") + " " + (c.get("big") or "") + " "
                   + (c.get("caption") or "") for c in (script.get("cards") or []))
    low = txt.lower()
    m = dict((k, bool(re.search(v, low))) for k, v in TEXT_MARKS.items())

    if prof.get("cpu") == "amd" and m["cpu_intel"] and not m["cpu_amd"]:
        bad.append(("ОШИБКА", "текст про Intel, а платформа ролика заявлена AMD"))
    if prof.get("cpu") == "intel" and m["cpu_amd"] and not m["cpu_intel"]:
        bad.append(("ОШИБКА", "текст про AMD, а платформа ролика заявлена Intel"))
    if prof.get("gpu") == "nvidia" and m["gpu_amd"] and not m["gpu_nv"]:
        bad.append(("ОШИБКА", "текст про Radeon, а ролик заявлен про NVIDIA"))
    if prof.get("gpu") == "amd" and m["gpu_nv"] and not m["gpu_amd"]:
        bad.append(("ОШИБКА", "текст про GeForce, а ролик заявлен про AMD"))
    if prof.get("form") == "desktop" and m["laptop"]:
        bad.append(("ПОДОЗРЕНИЕ", "текст поминает ноутбук в сюжете про настольный ПК"))

    # У 12V-2x6 двенадцать силовых жил в два ряда по шесть плюс четыре
    # сигнальных, всего шестнадцать контактов. «Шесть жил» — ошибка, на которой
    # уже обжигались.
    if re.search(r"(12vhpwr|12v-?2x6|шестнадцатиконтактн|16-контактн)", low):
        if re.search(r"(шест[ьи]|\b6\b)\s*(контакт|жил|пин)", low):
            bad.append(("ОШИБКА", "разъём 12V-2x6 назван шестиконтактным: у него "
                                  "12 силовых жил в два ряда плюс 4 сигнальных"))
    return bad


# ---------------------------------------------------------------- профиль

def profile_from(theme, override):
    p = {"cpu": None, "gpu": None, "socket": None, "form": "desktop"}
    cats = (theme or {}).get("categories") or ""
    if "nvidia" in cats:
        p["gpu"] = "nvidia"
    if "amd_gpu" in cats or "radeon" in cats:
        p["gpu"] = "amd"
    if "amd_cpu" in cats or "ryzen" in cats:
        p["cpu"] = "amd"
    if "intel" in cats:
        p["cpu"] = "intel"
    if "laptop" in cats or "notebook" in cats:
        p["form"] = "laptop"
    p.update(override or {})
    if p.get("socket"):
        p["socket"] = p["socket"].lower()
        if p["socket"] not in SOCKETS:
            raise SystemExit("неизвестный сокет: %s (знаю %s)"
                             % (p["socket"], ", ".join(SOCKETS)))
        p["cpu"] = p["cpu"] or SOCKETS[p["socket"]]["vendor"]
    return p


# ---------------------------------------------------------------- прогон

def dur(v):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", v], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL)
    return float(r.stdout.strip() or 0)


def grab(v, t, out, w=760):
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", "%.2f" % t,
                    "-i", v, "-frames:v", "1", "-vf", "scale=%d:-1" % w, "-q:v", "3", out],
                   stdin=subprocess.DEVNULL, capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--profile", default="")
    ap.add_argument("--script", default="")
    ap.add_argument("--theme", default="")
    ap.add_argument("--step", type=float, default=2.0)
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()

    theme = json.load(open(a.theme, encoding="utf-8")) if a.theme else {}
    over = json.load(open(a.profile, encoding="utf-8")) if a.profile else {}
    prof = profile_from(theme, over)
    log("платформа ролика: %s" % json.dumps(prof, ensure_ascii=False))

    problems = []
    if a.script:
        for lvl, msg in check_script(json.load(open(a.script, encoding="utf-8")), prof):
            problems.append((lvl, "сценарий", msg))
            log("  %s сценарий: %s" % (lvl, msg))

    key, base = creds()
    d = dur(a.video)
    tmp = tempfile.mkdtemp(prefix="pgate")
    frames, t, i, blind = [], 0.6, 0, 0
    log("смотрю кадры каждые %.1f с (длина %.1f с)" % (a.step, d))
    while t < d - 0.2:
        png = os.path.join(tmp, "f%03d.jpg" % i)
        grab(a.video, t, png)
        if os.path.exists(png) and os.path.getsize(png) > 1000:
            try:
                f = read_frame(png, key, base)
            except Exception as e:
                problems.append(("ОШИБКА", "%.1fс" % t, "судья упал: %s" % str(e)[:60]))
                log("  ОШИБКА %.1fс: судья упал: %s" % (t, str(e)[:60]))
                f = {}
            frames.append((t, f))
            if f:
                log("    %.1fс — %s" % (t, ", ".join(
                    "%s=%s" % ("крупных жил" if k == "_жил" else k, v)
                    for k, v in f.items())))
            else:
                blind += 1
                log("    %.1fс — железа в кадре нет" % t)
            for lvl, msg in check_frame(f, prof):
                problems.append((lvl, "%.1fс" % t, msg))
                log("  %s %.1fс: %s" % (lvl, t, msg))
            os.remove(png)
        t += a.step
        i += 1

    for lvl, msg in check_across(frames, prof):
        problems.append((lvl, "весь ролик", msg))
        log("  %s весь ролик: %s" % (lvl, msg))

    errs = [p for p in problems if p[0] == "ОШИБКА"]
    warns = [p for p in problems if p[0] == "ПОДОЗРЕНИЕ"]
    log("")
    log("кадров: %d, из них с железом: %d, ошибок: %d, подозрений: %d"
        % (len(frames), len(frames) - blind, len(errs), len(warns)))
    for lvl, where, msg in errs + warns:
        log("  %-11s %-11s %s" % (lvl, where, msg))
    if frames and blind == len(frames):
        log("ВНИМАНИЕ: железа не нашлось ни в одном кадре — гейту не на что было "
            "смотреть, его молчание ничего не подтверждает")
    if errs or (a.strict and warns):
        log("ПЛАТФОРМЕННЫЙ ГЕЙТ НЕ ПРОЙДЕН")
        return 1
    log("платформенно связно")
    return 0


if __name__ == "__main__":
    sys.exit(main())
