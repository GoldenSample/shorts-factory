#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ПОКАДРОВЫЙ ГЕЙТ, строгий (переписан 08-21 после провала со стеной куки).

СТАРАЯ ЛОГИКА БЫЛА ДЫРЯВОЙ: спрашивала «есть ли на кадре что-то из СПИСКА».
Чего в списке нет — то и проехало (стена согласия на куки уехала в выпуск).

НОВАЯ ЛОГИКА ОБРАТНАЯ: спрашиваем «годится ли кадр в публикацию», и любой
интерфейсный мусор, заглушка, чужой контент или сомнение = ОТКАЗ. Судья обязан
отвечать ГОДЕН только когда кадр однозначно является содержанием ролика.

Два независимых вопроса на каждый кадр, оба должны пройти:
  1) чистота: нет интерфейсного/постороннего/недопустимого
  2) по теме: кадр относится к теме ролика

    frame_gate.py <video.mp4> "<тема ролика>" [--step 1.5]

exit 0 = чисто; exit 1 = найден дефект (печатает какой кадр и почему).
"""
import argparse
import base64
import os
import subprocess
import sys
import time

sys.path.insert(0, "/usr/local/lib/hermes-agent")
os.chdir("/usr/local/lib/hermes-agent")
import httpx  # noqa: E402
from tools.xai_http import resolve_xai_http_credentials  # noqa: E402

MODEL = "grok-4.20-0309-non-reasoning"

Q_CLEAN = """Это кадр из готового ролика для публикации в соцсети.

ЗАМЕР 04.09.2026: прежний белый список составлялся, когда своего футажа не было,
и содержал только «фото железа, карточка, статья, титры». Банк футажа добавил
метафору и среду (полки склада, рабочий стол, мастерская, абстрактная графика),
а карточка цитат оформлена рамкой окна — гейт завернул девять кадров из девяти,
приняв авторский футаж за мусор, а нашу карточку за чужой интерфейс. Список
годного расширен под наш словарь; список брака не ослаблен.

Ответь ГОДЕН, если кадр — ЗАКОНЧЕННОЕ авторское содержание ролика:
- фотография или рендер компьютерного железа, макро детали;
- наша карточка с цитатой: тёмное окно с рамкой, одна реплика, подпись автора;
- титр или крупная надпись на фоне;
- образ-метафора и среда: полки, склад, конвейер, мастерская, рабочий стол,
  чертёж, диаграмма без подписей, абстрактная техно-графика;
- скриншот статьи или поста по теме ролика.

Ответь БРАК, если видишь ХОТЬ ЧТО-ТО из этого:
- окно согласия на куки, приватность, обработку данных, кнопки Accept/Принять;
- требование войти, регистрация, капча, страница ошибки или блокировки;
- интерфейс ЧУЖОГО сайта или приложения: адресная строка, меню навигации,
  боковая панель, лента ссылок, всплывающее окно поверх содержания;
- рекламный баннер, промо-блок, реклама лекарств, БАДов, интимных товаров;
- эротика, обнажённое тело;
- пустой, чёрный, размытый до нечитаемости или явно недогруженный кадр;
- сгоревшая, оплавленная, сломанная, грязная деталь;
- нечитаемая мешанина букв, кривой текст, обрезанный на полуслове заголовок.

Сомневаешься — отвечай БРАК. Ответь ОДНИМ словом: ГОДЕН или БРАК."""

Q_TOPIC = """Кадр из ролика на тему: «%s».

Ответь НЕТ, только если на кадре ЯВНО ЧУЖОЕ содержание: еда, люди крупным планом,
автомобили, животные, пейзаж, одежда, косметика, медицина — то, что к компьютерному
железу отношения не имеет.

Ответь ДА во всех остальных случаях, в том числе:
- любое компьютерное железо, платы, разъёмы, кабели, детали, абстрактная техно-графика;
- ТИТР или ТЕКСТОВАЯ КАРТОЧКА на однотонном фоне (это наши титры, они всегда по теме);
- карточка с цитатами, скриншот статьи по теме.

Ответь ОДНИМ словом: ДА или НЕТ."""


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
                    "-i", v, "-frames:v", "1", "-vf", "scale=420:-1", "-q:v", "4", out],
                   stdin=subprocess.DEVNULL, capture_output=True)


def ask(png, question, key, base):
    b64 = base64.b64encode(open(png, "rb").read()).decode()
    r = httpx.post(base + "/chat/completions",
                   headers={"Authorization": "Bearer " + key,
                            "Content-Type": "application/json"},
                   json={"model": MODEL,
                         "messages": [{"role": "user", "content": [
                             {"type": "image_url",
                              "image_url": {"url": "data:image/jpeg;base64," + b64}},
                             {"type": "text", "text": question}]}],
                         "max_tokens": 8}, timeout=120)
    return r.json()["choices"][0]["message"]["content"].strip().upper()


def check(png, theme, key, base):
    """Вернёт (ok, причина). Любой сбой судьи = не пускать."""
    try:
        a = ask(png, Q_CLEAN, key, base)
    except Exception as e:
        return False, "судья упал: %s" % str(e)[:40]
    if "ГОДЕН" not in a:
        return False, "нечистый кадр (%s)" % a[:16]
    try:
        b = ask(png, Q_TOPIC % theme[:120], key, base)
    except Exception as e:
        return False, "судья упал: %s" % str(e)[:40]
    if "ДА" not in b or b.startswith("НЕТ"):
        return False, "не по теме (%s)" % b[:16]
    return True, "ок"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("theme")
    ap.add_argument("--step", type=float, default=1.5)
    a = ap.parse_args()

    key, base = creds()
    dur = duration(a.video)
    n = max(int(dur / a.step), 1)
    log("покадровый гейт (строгий): %.1f сек, %d кадров" % (dur, n))

    bad = []
    for i in range(n):
        t = min(i * a.step + 0.3, dur - 0.2)
        png = "/tmp/fg_%d.jpg" % i
        grab(a.video, t, png)
        ok, why = check(png, a.theme, key, base)
        log("  t=%5.1f  %s%s" % (t, "ок" if ok else "БРАК", "" if ok else "  — " + why))
        if not ok:
            bad.append((t, why))

    print("")
    if bad:
        log("ГЕЙТ НЕ ПРОЙДЕН: %d дефектных кадров из %d" % (len(bad), n))
        for t, w in bad[:12]:
            log("  t=%.1f: %s" % (t, w))
        sys.exit(1)
    log("ГЕЙТ ПРОЙДЕН: все %d кадров годны" % n)
    sys.exit(0)


if __name__ == "__main__":
    main()
