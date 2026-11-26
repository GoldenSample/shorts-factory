#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скриншот статьи-первоисточника для слайда шортса.

    /opt/hermes/venv/bin/python3 news_shot.py <url|file://...> <out.png>

Мобильная колонка 480x854 при масштабе 2.25 = нативные 1080x1920 крупным текстом.
Снимаем до шести экранов — по ним потом едет кроп-панорама.

ПЕРЕПИСАН 02.09.2026. СТАРАЯ СТРАТЕГИЯ БЫЛА ПРОИГРЫШНОЙ: он сносил узлы из DOM
ПОСЛЕ отрисовки и кликал по кнопкам согласия. Так нельзя — стена согласия живёт в
кросс-доменном iframe, document.body её не видит, снесённые элементы возвращаются
сами, а реклама к моменту сноса уже загрузилась и успела перерисоваться.

ЧТО ТЕПЕРЬ. Три рубежа, каждый проверен на живом:

 1. РЕЖЕМ ДО ЗАГРУЗКИ. Запросы к рекламе, аналитике и CMP отбиваются сетевым
    правилом page.route ещё до того, как страница отрисуется. Нечему всплывать
    поверх статьи. Замер на VideoCardz: 10 отбитых запросов, стена не появилась.
    Список доменов один на весь контур — берём из web.py, чтобы не разъезжался.

 2. МАРКЕРЫ БЛОКИРОВКИ. Если вместо статьи приехала капча или «access denied» —
    наружу не пускаем. Текст собираем со ВСЕХ фреймов.

 3. СНИМОК СМОТРИТ ЗРЕНИЕ. Последний рубеж: готовый png проверяет модель на
    рекламу, попапы и стены. Логика обратная — годен только при уверенности,
    сбой судьи = не пускать. Без этого мы уже отправили в выпуск полноэкранную
    рекламу «решение деликатной проблемы без свечей» (21.08), и агент честно
    построил по ней весь сюжет.

Ключ судьи — платный консольный из console.env (в венве с браузером резолвер
подписки отдаёт пустой ключ и судья валится в 401).
"""
import base64
import glob
import json
import os
import sys
import urllib.request

sys.path.insert(0, "/opt/shorts")
from web import BLOCK                      # noqa: E402  единый список доменов

from playwright.sync_api import sync_playwright  # noqa: E402

UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36")
MODEL = "grok-4.20-0309-non-reasoning"

# Вместо статьи приехала заглушка — наружу не пускаем.
BLOCK_MARKERS = (
    "blocked by network security", "whoa there", "are you a robot",
    "verify you are human", "access denied", "just a moment",
    "включите javascript", "enable javascript", "доступ ограничен",
    "проверка браузера", "checking your browser",
    "документ не найден", "страница не найдена", "page not found",
    "ничего не найдено", "материал не найден",
)

Q_SHOT = """Это снимок страницы новостного сайта. Он поедет в ролик как иллюстрация.

ЗАМЕР 02.09.2026: прежняя формулировка браковала два чистых снимка из трёх —
цеплялась за обычное устройство сайта. Строгость нужна только там, где нас жгло.

Ответь БРАК, если ЯВНО видишь одно из этого:
крупный рекламный баннер занимает заметную часть кадра или стоит поверх текста;
согласие на куки — окном поверх страницы ИЛИ полосой внизу либо вверху,
где бы она ни стояла; подписка, вход, затемнение под ними;
капча, проверка браузера, отказ в доступе, «страница не найдена», пустая заглушка;
изображение медицинского, интимного или азартного характера.

НЕ считается браком обычное устройство сайта: шапка с логотипом и меню, строка
поиска, рубрики и теги, кнопки соцсетей, счётчик комментариев, мелкие значки,
служебные кнопки самого издания, ссылки на другие его материалы.

Если на снимке виден заголовок новости и её текст — отвечай ГОДЕН.
Ответь ОДНИМ словом: ГОДЕН или БРАК."""


# Своя куки-полоса сайта. Против ЧУЖОГО CMP снос бесполезен — он в кросс-доменном
# iframe. Но первосторонняя полоса лежит в этом же документе, и вот её снести можно
# и нужно: сетевое правило её не отбивает, она приезжает вместе с версткой.
SWEEP_OWN_CONSENT = """() => {
  const RE = /(cookie|куки|консент|consent|gdpr|соглаш)/i;
  const TXT = /(файлы cookie|использует cookie|принять|согласие|accept cookies)/i;
  let n = 0;
  for (const el of document.querySelectorAll('div,section,aside,footer,dialog')) {
    const cs = getComputedStyle(el);
    if (cs.position !== 'fixed' && cs.position !== 'sticky') continue;
    const r = el.getBoundingClientRect();
    if (r.width * r.height < 4000) continue;
    const id = (el.id || '') + ' ' + (el.className || '');
    const t = (el.innerText || '').slice(0, 400);
    if (RE.test(id) || (TXT.test(t) && t.length < 400)) {
      try { el.remove(); n++; } catch (e) {}
    }
  }
  return n;
}"""


def log(m):
    print(m, flush=True)


def creds():
    env = "/opt/shorts/console.env"
    if os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            if line.startswith("XAI_CONSOLE_KEY="):
                k = line.split("=", 1)[1].strip().strip('"').strip("'")
                if k:
                    return k, "https://api.x.ai/v1"
    return None, None


def judge_shot(png, key, base, tries=3):
    """(ок, причина). Сбой судьи = не пускать."""
    if not key:
        return False, "нет ключа судьи"
    b64 = base64.b64encode(open(png, "rb").read()).decode()
    body = json.dumps({"model": MODEL, "max_tokens": 8, "temperature": 0,
                       "messages": [{"role": "user", "content": [
                           {"type": "image_url",
                            "image_url": {"url": "data:image/png;base64," + b64}},
                           {"type": "text", "text": Q_SHOT}]}]}).encode()
    for i in range(tries):
        try:
            req = urllib.request.Request(
                base + "/chat/completions", data=body,
                headers={"Authorization": "Bearer " + key,
                         "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                a = json.loads(r.read().decode())["choices"][0]["message"]["content"]
            a = (a or "").strip().upper().strip("* .")
            return ("ГОДЕН" in a and not a.startswith("БРАК")), a[:24]
        except Exception as e:
            if i == tries - 1:
                return False, "судья упал: %s" % str(e)[:40]
    return False, "судья молчит"


def main():
    url, out = sys.argv[1], sys.argv[2]
    exe = (glob.glob("/root/.cache/ms-playwright/chromium-*/chrome-linux*/chrome") + [None])[0]
    blocked = {"n": 0}

    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox"], executable_path=exe)
        pg = b.new_page(viewport={"width": 480, "height": 854},
                        device_scale_factor=2.25,
                        locale="ru-RU", color_scheme="dark", user_agent=UA)

        def router(route):
            if BLOCK.search(route.request.url):
                blocked["n"] += 1
                return route.abort()
            return route.continue_()

        pg.route("**/*", router)             # рубеж 1: режем ДО отрисовки
        resp = pg.goto(url, wait_until="domcontentloaded", timeout=45000)

        # ЗАМЕР 02.09.2026: судья НЕ ловит страницу «документ не найден» — читает
        # меню и ссылки как содержание. Спрашивать модель про 404 глупо, когда
        # сервер сообщает его сам. Код ответа — детерминированный сигнал, он и решает.
        code = resp.status if resp else 0
        if code >= 400 or code == 0:
            b.close()
            raise SystemExit("страница не отдалась, код ответа: %s" % (code or "нет ответа"))
        pg.wait_for_timeout(3000)

        swept = pg.evaluate(SWEEP_OWN_CONSENT)   # рубеж 2: своя полоса согласия
        if swept:
            pg.wait_for_timeout(300)

        # рубеж 3: заглушка вместо статьи. Текст со ВСЕХ фреймов.
        texts = []
        for fr in pg.frames:
            try:
                texts.append((fr.evaluate("document.body && document.body.innerText || ''")
                              or "").lower())
            except Exception:
                continue
        blob = " ".join(texts)
        for marker in BLOCK_MARKERS:
            if marker in blob:
                b.close()
                raise SystemExit("страница не отдалась, маркер: %s" % marker)

        h = min(pg.evaluate("document.body.scrollHeight") or 854, 854 * 6)
        pg.screenshot(path=out, clip={"x": 0, "y": 0, "width": 480, "height": h})
        b.close()

    log("снято %s (отбито запросов: %d, снесено своих полос: %d)"
        % (out, blocked["n"], swept))

    # рубеж 4: снимок смотрит зрение
    key, base = creds()
    ok, why = judge_shot(out, key, base)
    if not ok:
        # Брак НЕ удаляем: без него не понять, судья пережат или страница правда
        # в рекламе. Конвейеру файла всё равно нет — он лежит под другим именем.
        bad = out + ".rejected.png"
        try:
            os.replace(out, bad)
        except Exception:
            bad = "(не сохранён)"
        raise SystemExit("снимок забракован: %s — оставлен как %s" % (why, bad))
    log("снимок чист (%s)" % why)


if __name__ == "__main__":
    main()
