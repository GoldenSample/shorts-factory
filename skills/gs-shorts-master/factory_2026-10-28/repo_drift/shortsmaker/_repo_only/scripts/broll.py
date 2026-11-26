#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""БАНК ФУТАЖА: наполняет библиотеку по плану, а не под каждую сцену заново.

    /usr/local/lib/hermes-agent/venv/bin/python3 broll.py [--only id,id] [--dubles 4]
    /usr/local/lib/hermes-agent/venv/bin/python3 broll.py --index   # что уже есть

ИНТЕРПРЕТАТОР: только hermes-agent venv — gen_media стоит на httpx, а в венве
с браузером его нет. Перепутать легко, ошибка вылезает лишь при импорте.

ЗАЧЕМ. Конвейер генерировал фон под каждую сцену: кадр случайный, к теме
отношения не имеет, каждый раз новый, и в сумме получалась каша. Кэш сцен делу
не помогал — он привязан к тексту промпта и переиспользуется только при
дословном совпадении.

Здесь наоборот: снимаем ЗАРАНЕЕ по плану, раскладываем по ФУНКЦИИ кадра и
тегам, сборщик тянет из библиотеки и генерирует только чего нет.

ДВА СОРТА ДВИЖЕНИЯ, и это главное решение по деньгам и времени:
  pan — движение делает ffmpeg кроп-панорамой по стиллу 2K. Бесплатно,
        мгновенно, композиция та самая, что прошла судей. Так снимается
        большинство кадров.
  i2v — генерируем 6 секунд из УЖЕ УТВЕРЖДЁННОГО стилла. Только там, где
        движение и есть смысл кадра: лопасти крутятся, руки ставят, свет гаснет.
        Дорого по времени (клип считается около минуты), поэтому по списку.

ОТБОР. На каждый кадр n дублей, дальше три узких судьи (закон сида: два кадра
одного промпта расходятся сильнее, чем кадры разных промптов, поэтому вывод по
одному кадру = шум). Судьи те же, что в атласе: та ли деталь, нет ли дефекта,
не реклама ли. Сбой судьи = не пускать.

Библиотека: /opt/shorts/broll/<fn>/<id>.jpg (+ .mp4 для i2v) и index.json.
"""
import argparse
import base64
import io
import json
import os
import shutil
import sys
import time
import urllib.request

sys.path.insert(0, "/opt/shorts")

BROLL = "/opt/shorts/broll"
PLAN = "/opt/shorts/broll_plan.json"
INDEX = os.path.join(BROLL, "index.json")
MODEL = "grok-4.20-0309-non-reasoning"

Q_IS = """Посмотри на кадр. Он снят по такому заданию:

%s

Ответь ДА, если кадр в целом отвечает заданию: изображён тот предмет и та
крупность, которые заказаны.

Ответь НЕТ, если предмет другой, крупность совсем не та, кадр пустой или
непонятный, либо в кадре люди сверх заказанных рук.

Ответь ОДНИМ словом: ДА или НЕТ."""

Q_OK = """Это кадр для ролика про компьютерное железо.

Ответь БРАК, если ЯВНО видишь одно из:
деталь грязная, поцарапанная, обгоревшая, оплавленная, погнутая или изношенная;
отпечатки пальцев, пыль, следы припоя;
предмет размыт целиком или настолько тёмен, что не разобрать;
искажённая анатомия рук, лишние или сросшиеся пальцы;
бессмысленное нагромождение деталей вместо узнаваемого предмета.

Лёгкая тень, блик на глянце и мягкое размытие фона браком НЕ являются.

Ответь ОДНИМ словом: ГОДЕН или БРАК."""

Q_TEXT = """Посмотри на кадр с компьютерной деталью.

ЗАМЕР 03.09.2026: прежняя формулировка запрещала любой текст и завернула шесть
дублей подряд. Это запрет реальности: на настоящей детали заводская маркировка
есть всегда, и она в кадре уместна. Брак — не текст как таковой, а признак
подделки: крупная надпись, чужой бренд, водяной знак, каша из букв.

Ответь ЕСТЬ, если видишь одно из:
крупную надпись или заголовок, читаемый через весь кадр;
логотип бренда размером с заметную часть детали;
водяной знак или подпись фотографа поверх кадра;
нагромождение бессмысленных букв и цифр, каша вместо надписи.

НЕ считается: мелкая заводская маркировка на самой детали, номер модели,
значки сертификации, штрихкод, обозначения у разъёмов — на настоящем железе
это есть всегда.

Ответь ОДНИМ словом: ЕСТЬ или НЕТ."""


def log(m):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def creds():
    env = "/opt/shorts/console.env"
    if os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            if line.startswith("XAI_CONSOLE_KEY="):
                k = line.split("=", 1)[1].strip().strip('"').strip("'")
                if k:
                    return k, "https://api.x.ai/v1"
    return None, None


def ask(img, question, key, base, tries=3):
    b64 = base64.b64encode(open(img, "rb").read()).decode()
    body = json.dumps({"model": MODEL, "max_tokens": 8, "temperature": 0,
                       "messages": [{"role": "user", "content": [
                           {"type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64," + b64}},
                           {"type": "text", "text": question}]}]}).encode()
    for i in range(tries):
        try:
            req = urllib.request.Request(
                base + "/chat/completions", data=body,
                headers={"Authorization": "Bearer " + key,
                         "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                a = json.loads(r.read().decode())["choices"][0]["message"]["content"]
            return (a or "").strip().upper().strip("* .")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def judge(img, brief, key, base):
    """(ок, причина). Три узких вопроса, все три должны пройти.
    Сбой судьи = не пускать: молчаливый сбой не читается как «чисто»."""
    checks = ((Q_IS % brief[:400], "ДА", "не по заданию"),
              (Q_OK, "ГОДЕН", "дефект"),
              (Q_TEXT, "НЕТ", "текст в кадре"))
    for q, need, why in checks:
        try:
            a = ask(img, q, key, base)
        except Exception as e:
            return False, "судья упал: %s" % str(e)[:34]
        if need == "НЕТ":
            if not a.startswith("НЕТ"):
                return False, why
        elif need not in a or a.startswith(("НЕТ", "БРАК")):
            return False, why
    return True, "ок"


def load_index():
    if os.path.exists(INDEX):
        try:
            return json.load(io.open(INDEX, encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_index(ix):
    io.open(INDEX, "w", encoding="utf-8").write(
        json.dumps(ix, ensure_ascii=False, indent=1, sort_keys=True))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--dubles", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--index", action="store_true")
    ap.add_argument("--res", default="", help="1k|2k — принудительно для всех")
    a = ap.parse_args()

    ix = load_index()
    if a.index:
        by_fn = {}
        for k, v in ix.items():
            by_fn.setdefault(v.get("fn", "?"), []).append(k)
        for fn in sorted(by_fn):
            log("%-9s %2d: %s" % (fn, len(by_fn[fn]), ", ".join(sorted(by_fn[fn]))))
        log("всего в банке: %d" % len(ix))
        return 0

    plan = json.load(io.open(PLAN, encoding="utf-8"))
    tail = plan.get("style_tail", "")
    shots = plan["shots"]
    if a.only:
        want = set(s.strip() for s in a.only.split(",") if s.strip())
        shots = [s for s in shots if s["id"] in want]

    key, base = creds()
    if not key:
        raise SystemExit("нет ключа судьи в console.env")

    import gen_media

    todo = [s for s in shots if s["id"] not in ix]
    if a.limit:
        todo = todo[:a.limit]
    log("в плане %d, в банке %d, снимаем %d" % (len(plan["shots"]), len(ix), len(todo)))

    made = 0
    for s in todo:
        sid, fn = s["id"], s["fn"]
        d = os.path.join(BROLL, fn)
        os.makedirs(d, exist_ok=True)
        prompt = s["prompt"] + " " + tail
        log("%s (%s, %s, %s)" % (sid, fn, s["motion"], res))

        # РАЗРЕШЕНИЕ (Гор, 04.09): бережём лимиты, по умолчанию 1k. Оговорка по
        # факту: 1k у Имейджина = 720x1280, а панорама вырезает окно 1188x2112,
        # то есть исходник МЕНЬШЕ окна и его тянут вверх примерно в 1.65 раза.
        # На абстракции и общих планах не видно, на макро видно. Поэтому 2k
        # остаётся там, где резкость и есть содержание кадра: зачины и детали.
        res = a.res or ("2k" if fn in ("hook", "detail") else "1k")
        picked = None
        for k in range(a.dubles):
            tmp = os.path.join(d, "_try_%s_%d.jpg" % (sid, k))
            try:
                gen_media.gen_image(prompt, tmp, use_cache=False,
                                    aspect="9:16", resolution=res)
            except Exception as e:
                log("    дубль %d не снялся: %s" % (k, str(e)[:60]))
                continue
            if not os.path.exists(tmp) or os.path.getsize(tmp) < 20000:
                continue
            ok, why = judge(tmp, s["prompt"], key, base)
            if ok:
                picked = tmp
                log("    дубль %d годен" % k)
                break
            log("    дубль %d отвод: %s" % (k, why))

        # чистим неудачные дубли
        for k in range(a.dubles):
            t = os.path.join(d, "_try_%s_%d.jpg" % (sid, k))
            if os.path.exists(t) and t != picked:
                os.remove(t)

        if not picked:
            log("    НЕ СНЯТ: ни один дубль не прошёл")
            continue

        still = os.path.join(d, sid + ".jpg")
        os.replace(picked, still)
        rec = {"fn": fn, "subj": s["subj"], "motion": s["motion"],
               "tags": s["tags"], "still": still,
               "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}

        if s["motion"] == "i2v":
            mp4 = os.path.join(d, sid + ".mp4")
            try:
                gen_media.gen_video(s["prompt"] + " " + tail, mp4, duration=6,
                                    aspect="9:16", use_cache=False,
                                    image_url="file://" + still)
                if os.path.exists(mp4) and os.path.getsize(mp4) > 50000:
                    rec["clip"] = mp4
                    log("    клип снят")
                else:
                    log("    клип не снялся, остаётся стилл с панорамой")
                    rec["motion"] = "pan"
            except Exception as e:
                log("    клип не снялся (%s), остаётся стилл" % str(e)[:50])
                rec["motion"] = "pan"

        ix[sid] = rec
        save_index(ix)
        made += 1

    log("снято за прогон: %d, в банке всего: %d" % (made, len(ix)))
    miss = [s["id"] for s in plan["shots"] if s["id"] not in ix]
    if miss:
        log("не снято (%d): %s" % (len(miss), ", ".join(miss)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
