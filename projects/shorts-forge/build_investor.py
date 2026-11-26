# -*- coding: utf-8 -*-
"""Видеопитч Cognopolis для ИНВЕСТОРА (16:9, ~2 минуты).

Отличие от промо-ролика (build_cognopolis.py): там продают игру игроку, здесь
продают компанию инвестору. Значит другая драматургия — деньги, диагноз рынка,
доказательство зрелости, честный список того, чего нет, и внятный аск.

⚑ ТРИ РЕШЕНИЯ, КОТОРЫЕ ОПРЕДЕЛИЛИ СБОРКУ.

1. ТЕКСТ НИКОГДА НЕ ДВИГАЕТСЯ, ДВИЖЕТСЯ МИР ПОД НИМ.
   Слайд рендерится headless-хромом в PNG с АЛЬФОЙ (--default-background-color=00000000)
   и накладывается вторым слоем поверх фона. Ken Burns applies только к фону.
   Если анимировать слайд целиком, буквы при масштабировании мылятся и дрожат —
   на цифрах питча это выглядит как брак.

2. ГЕНЕРАТИВ — ТОЛЬКО МИР, ПРОДУКТ — ТОЛЬКО СВОИ КАДРЫ.
   Закон скила cognopolis-promo. Фоны из reel_bg/ идут под утверждения и цифры;
   всё, что показывает сам сервис, снято с живого сервера (shots_cognopolis/).

3. ЧИТАЕМОСТЬ ЧЕРЕЗ СКРИМ, А НЕ ЧЕРЕЗ ПРИТУШЕНИЕ ФОНА В НОЛЬ.
   Затемнение живёт в HTML-слое градиентом (слева почти чёрный, справа мир
   проступает). Фон при этом остаётся живым, а контраст под текстом гарантирован
   композицией, а не удачей.

Цифры взяты из script.md (питч на 15 минут) и не досочиняются.
"""
from __future__ import annotations

import html as html_mod
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots_cognopolis"
BG = HERE / "reel_bg"
WORK = HERE / "work_inv"
OUT = HERE / "out"
MEDIA = Path(r"C:\CLAUD\projects\media-forge\media.py")
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
W, H, FPS = 1920, 1080, 30

# ── фирменный стиль дека (палитра и типографика вынуты из deck.html) ──────────
CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:transparent;width:1920px;height:1080px;overflow:hidden;
  font-family:ui-sans-serif,system-ui,'Segoe UI',sans-serif;color:#c7ccd4;
  -webkit-font-smoothing:antialiased}
.slide{position:absolute;inset:0;display:flex;flex-direction:column;
  padding:88px 108px 78px}
/* скрим: под текстом почти чёрный, к правому краю мир проступает */
.slide::before{content:'';position:absolute;inset:0;pointer-events:none;background:
  linear-gradient(100deg, rgba(6,5,4,.94) 0%, rgba(6,5,4,.88) 42%, rgba(6,5,4,.34) 100%)}
.slide.full::before{background:
  linear-gradient(180deg, rgba(6,5,4,.90) 0%, rgba(6,5,4,.93) 100%)}
/* сетка и тёплые засветы — как в деке, поверх скрима */
.slide::after{content:'';position:absolute;inset:0;pointer-events:none;background:
  radial-gradient(120% 90% at 12% 0%, rgba(239,159,39,.10), transparent 60%),
  radial-gradient(90% 80% at 100% 100%, rgba(215,176,106,.07), transparent 55%),
  repeating-linear-gradient(0deg,rgba(26,24,18,.75) 0 1px,transparent 1px 72px),
  repeating-linear-gradient(90deg,rgba(26,24,18,.75) 0 1px,transparent 1px 72px)}
.slide > *{position:relative;z-index:2}
.rule{position:absolute;left:0;right:0;top:0;height:4px;z-index:3;
  background:linear-gradient(90deg,#ef9f27,#d7b06a 45%,transparent)}
.ser{font-family:'Palatino Linotype',Palatino,Georgia,serif}
.kicker{font-family:'Palatino Linotype',Palatino,Georgia,serif;font-size:21px;
  letter-spacing:4px;text-transform:uppercase;color:#a98a3e;margin-bottom:26px}
h1{font-family:'Palatino Linotype',Palatino,Georgia,serif;font-size:104px;line-height:1.04;
  color:#e7d4a8;font-weight:600;letter-spacing:-1px;max-width:1400px}
.st{font-family:'Palatino Linotype',Palatino,Georgia,serif;font-size:72px;line-height:1.16;
  color:#e7d4a8;max-width:1330px}
.st.sm{font-size:58px}
.sub{margin-top:34px;font-size:32px;line-height:1.46;color:#b8bcc2;max-width:1180px}
.sub.q{color:#95998f;font-size:28px}
b{color:#f5c062;font-weight:600}
.mid{margin:auto 0}
.marks{margin-top:50px;display:flex;gap:14px;flex-wrap:wrap}
.mark{font-size:22px;color:#d7b06a;background:rgba(29,26,18,.85);
  border:1px solid #4a3f22;border-radius:999px;padding:11px 24px}
/* плитки с цифрами */
.tiles{display:grid;gap:26px;margin:auto 0;width:100%}
.g2{grid-template-columns:1fr 1fr}.g3{grid-template-columns:repeat(3,1fr)}
.g4{grid-template-columns:repeat(4,1fr)}
.tile{background:rgba(21,20,15,.90);border:1px solid #262219;border-left:4px solid #6a5520;
  border-radius:12px;padding:32px 30px;display:flex;flex-direction:column;justify-content:center}
.v{font-family:'Palatino Linotype',Palatino,Georgia,serif;font-size:76px;line-height:1;color:#d7b06a}
.g4 .v{font-size:60px}
.l{margin-top:16px;font-size:23px;color:#c7ccd4;line-height:1.34}
.g4 .l{font-size:20px}
.n{margin-top:12px;font-size:18px;color:#8a8578;line-height:1.4}
/* список */
.bul{list-style:none;display:flex;flex-direction:column;gap:30px;margin:auto 0;max-width:1420px}
.bul li{position:relative;padding-left:40px}
.bul li::before{content:'';position:absolute;left:0;top:.55em;width:14px;height:14px;
  background:#ef9f27;transform:rotate(45deg)}
.bh{display:block;font-size:36px;color:#f5c062;font-weight:600;margin-bottom:9px}
.bt{display:block;font-size:26px;color:#b8bcc2;line-height:1.4}
.foot{margin-top:auto;font-size:22px;color:#8a8578}
.url{font-family:'Palatino Linotype',Palatino,Georgia,serif;font-size:64px;color:#e7d4a8;
  letter-spacing:1px}
"""


def tile(v: str, l: str, n: str = "") -> str:
    return (f'<div class=tile><div class=v>{v}</div><div class=l>{l}</div>'
            + (f'<div class=n>{n}</div>' if n else "") + '</div>')


def li(h: str, t: str) -> str:
    return f'<li><span class=bh>{h}</span><span class=bt>{t}</span></li>'


# ── раскадровка ──────────────────────────────────────────────────────────────
# Логика инвестора: рынок платит → учиться негде (измерено) → мы построили →
# вот оно живое → вот зрелость → это построил рой → окно закрывается → аск.
#
# ⛔ Слово «дырка» в кадре не появляется ни в каком виде (прямой запрет оператора).
SCENES = [
    dict(k="slide", bg="02_built.png", zoom="in", scrim="",
         html=f"""<div class=kicker>COGNOPOLIS</div>
           <div class=mid><h1>Мир, в который<br>нельзя играть руками</h1>
           <div class=sub>Живая MMO, где каждым жителем управляет
             <b>агент игрока</b>, а не человек. И курс, который учит их писать.</div>
           <div class=marks><span class=mark>REST + MCP</span>
             <span class=mark>боевой сервер</span>
             <span class=mark>41 час курса</span></div></div>""",
         voice="Cognopolis — живой мир, в который нельзя играть руками. "
               "Каждым жителем здесь управляет не человек, а его собственный агент."),

    dict(k="slide", bg="01_problem.png", zoom="out", scrim="",
         html="""<div class=kicker>Проблема</div>
           <div class=mid><div class=st>Навыку, за который платят
             <b>+18 тысяч долларов</b> в год, негде научиться на практике.</div>
           <div class="sub q">Курсов по агентам много, и они неплохие. Но устроены
             одинаково: видео плюс ноутбук. В ноутбуке нет последствий.</div></div>""",
         voice="Рынок уже платит за умение строить агентов. "
               "А учиться этому негде: курс даёт видео и ноутбук, "
               "но в ноутбуке нет последствий."),

    dict(k="slide", bg="01_problem.png", zoom="in", scrim="full",
         html=f"""<div class=kicker>Куда течёт бюджет</div>
           <div class="tiles g4">
             {tile("+29%", "расходы компаний на внешние обучающие продукты за год",
                   "весь рынок обучения за то же время — плюс 5%")}
             {tile("×4", "рост навыка в вакансиях за год", "год назад его почти не было")}
             {tile("+$18K", "к годовой вилке за этот навык", "")}
             {tile("43%", "лучший результат на MCP-Universe",
                   "231 задача на 11 живых MCP-серверах")}
           </div>
           <div class=foot>Вторая цифра — факт по отчётности, не прогноз аналитиков.</div>""",
         voice="Бюджет туда уже течёт. Расходы компаний на внешние продукты выросли "
               "на двадцать девять процентов за год, при росте всего рынка обучения на пять."),

    dict(k="slide", bg="03_rules.png", zoom="out", scrim="",
         html="""<div class=kicker>Диагноз поставлен, лечения нет</div>
           <div class=mid><div class=st>Люди применяют ИИ в <b>60%</b> работы,
             а доверяют агенту целиком — от <b>0 до 20%</b>.</div>
           <div class="sub q">Anthropic называет это разрывом делегирования.
             Бенчмарки измерили провал. Тренажёра, на котором он лечится, нет.</div></div>""",
         voice="И это измерено. На двухстах тридцати одной задаче с живыми серверами "
               "лучшая модель проходит сорок три процента. "
               "Бенчмарки поставили диагноз — тренажёра, на котором это лечится, нет."),

    dict(k="slide", bg="02_built.png", zoom="in", scrim="",
         html="""<div class=kicker>Решение</div>
           <div class=mid><div class=st>Мы его построили: общий постоянный мир,
             в который человек и его агент играют <b>вдвоём</b>.</div>
           <div class=sub>Одна логика — две равноправные двери: обычный REST и MCP,
             тот протокол, которым сегодня говорят все агентные среды.</div></div>""",
         voice="Мы его построили. Общий постоянный мир: у игрока поселение, "
               "а каждым жителем управляет его собственная программа."),

    # ── доказательство: только настоящие кадры боевого сервера ──
    dict(k="shot", shot="hi_world.png", crop=(760, 640, 780, 480), zoom="in",
         sub="Серые силуэты — ЧУЖИЕ агенты. Прямо сейчас.",
         voice="Это боевой сервер, снято сегодня. Серые силуэты на карте — жители "
               "других игроков. То есть чужие агенты, работающие прямо сейчас."),

    dict(k="shot", shot="chk_codex.png", crop=(2420, 1010, 70, 340), zoom="in",
         sub="74 пути REST и 49 MCP-тулов\\Nна одном движке",
         voice="Каталоги мира — цены, рецепты, формулы — отдаются без токена. "
               "Агент не зашивает правила в код, он их спрашивает. "
               "Ровно этот навык нужен в настоящей работе."),

    dict(k="shot", shot="hi_diag.png", crop=(900, 570, 55, 1370), zoom="in", sub_top=True,
         sub="Игра ревьюит твоего агента:\\N«цикл, возможно, думает или завис»",
         voice="А вот главный дифференциатор, и он не в геймплее. "
               "Игра показывает не результат, а ум агента: намерение, такт и ошибки. "
               "Наблюдение за игрой становится отладкой твоего кода."),

    dict(k="slide", bg="04_swarm.png", zoom="out", scrim="full",
         html=f"""<div class=kicker>Что уже стоит в проде</div>
           <div class="tiles g4">
             {tile("1322", "автотеста", "красный тест физически не доезжает до прода")}
             {tile("85", "выкаток за 34 дня", "два с половиной деплоя в день")}
             {tile("20+", "механик, а не одна демка",
                   "экономика, бой, стройка, обучение, шахта")}
             {tile("29", "скриншотов вики с живого сервера",
                   "документация не может отстать молча")}
           </div>""",
         voice="Это не демка. Тысяча триста двадцать два автотеста. "
               "Восемьдесят пять выкаток в прод за тридцать четыре дня."),

    dict(k="slide", bg="03_rules.png", zoom="in", scrim="",
         html=f"""<div class=kicker>Вторая половина продукта</div>
           <ul class=bul>
             {li("50 модулей, 41 час, 8 частей",
                 "44 запускаемых ноутбука и 7 агентов; пять из них ходят в нашу живую игру, а не в мок")}
             {li("Каждая ступень игры равна ступени агента",
                 "скрипт → реактивный → планировщик → LLM с инструментами → староста над роем")}
             {li("Прогресс в мире и есть оценка",
                 "не тест с галочками: состояние мира проверяет, работает ли код студента")}
           </ul>""",
         voice="Вторая половина продукта — курс. Пятьдесят модулей, сорок один час, "
               "сорок четыре ноутбука. Каждая ступень игры равна ступени агента, "
               "поэтому прогресс в мире и есть оценка."),

    dict(k="slide", bg="04_swarm.png", zoom="in", scrim="",
         html="""<div class=kicker>Главное</div>
           <div class=mid><div class=st>Этот продукт построил <b>рой ИИ-агентов</b>.
             Курс продаёт ровно тот конвейер, который его построил.</div>
           <div class=sub>13 ролей с зонами владения · 34 дня от нуля до боевого сервиса ·
             124 записанных решения, каждое можно оспорить по номеру.</div></div>""",
         voice="И теперь главное. Всё, что я показал, построено роем ИИ-агентов. "
               "Тринадцать ролей, тридцать четыре дня, сто двадцать четыре записанных решения. "
               "Мы продаём не пересказ статей, а конвейер, который у нас работает."),

    dict(k="slide", bg="05_market.png", zoom="out", scrim="",
         html="""<div class=kicker>Окно</div>
           <div class=mid><div class="st sm">За полгода два разработчика независимо
             пришли к той же идее — мир для ИИ-агентов через MCP.</div>
           <div class=sub>Категория формируется на глазах. У них — эксперименты одного
             человека. У нас — движок, курс и оценка, привязанная к состоянию мира.</div></div>""",
         voice="Категория формируется на глазах: за полгода два разработчика независимо "
               "выложили миры для агентов по тому же протоколу. "
               "У них эксперименты. У нас движок, курс и проверяемая работа на живом сервере."),

    dict(k="slide", bg="01_problem.png", zoom="in", scrim="full",
         html=f"""<div class=kicker>Честно: чего у нас нет</div>
           <ul class=bul>
             {li("Пользователей ноль — и это не плохая воронка",
                 "публичной регистрации нет физически, аккаунт выдаёт админ. Именно на воронку и нужны деньги")}
             {li("Нагрузку не мерили, мир пока небольшой",
                 "11 модулей из 50 — скелеты, причём именно про рой, который работает лучше, чем описан")}
             {li("Что есть: работающий продукт, проверяемый метод и скорость",
                 "всё, что начинается со слова «пользователи», — это и есть предмет разговора")}
           </ul>""",
         voice="Теперь честно. Пользователей ноль, и это не плохая воронка: "
               "публичной регистрации нет вовсе, аккаунты выдаёт админ. "
               "Есть работающий продукт, проверяемый метод и скорость."),

    dict(k="slide", bg="02_built.png", zoom="out", scrim="",
         html="""<div class=kicker>Что нам нужно</div>
           <div class=mid><div class="st sm">Деньги на воронку &nbsp;·&nbsp;
             первый корпоративный пилот &nbsp;·&nbsp;
             доступ к тем, кто уже покупает обучение</div>
           <div class=sub>Демо открыто прямо сейчас — вход под тестовым пользователем,
             без регистрации.</div>
           <div class=marks style="margin-top:44px">
             <span class=url>kindomklaster.com</span></div></div>""",
         voice="Нужны три вещи: деньги на то, чтобы у продукта появились пользователи, "
               "первый корпоративный пилот и доступ к тем, кто уже покупает внешнее обучение. "
               "Демо открыто прямо сейчас, зайти можно под тестовым пользователем."),
]


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, **kw)


def dur(p: Path | None) -> float:
    if not p:
        return 0.0
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(p)])
    try:
        return float(r.stdout.decode().strip())
    except ValueError:
        return 0.0


VOICE = "ru-RU-DmitryNeural"
RATE = "-6%"      # чуть медленнее нормы: питч читают на слух, а не пролистывают


def tts(text: str, dest: Path) -> bool:
    """Голос локальным движком, а НЕ через media-forge.

    ⛔ media.py tts ходит в xAI и сейчас отдаёт 403: пул аккаунта выел лимит
    (personal-team-blocked). Ждать его — значит не собрать ролик вовсе, поэтому
    озвучка переведена на edge-tts: русские нейроголоса, ~3 с на фразу, без пула.
    ⚠ Голоса Microsoft Edge — сервис MS; для коммерческого выпуска ролика это
    серая зона, замена без переписывания кода (та же функция, другой движок).
    """
    raw = dest.with_suffix(".raw.mp3")
    code = (
        "import asyncio,edge_tts,sys\n"
        "t=open(sys.argv[1],encoding='utf-8').read()\n"
        f"c=edge_tts.Communicate(t,'{VOICE}',rate='{RATE}')\n"
        "asyncio.run(c.save(sys.argv[2]))\n")
    txt = dest.with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")          # кириллица в argv бьётся
    r = run([sys.executable, "-c", code, str(txt), str(raw)])
    if not raw.exists() or raw.stat().st_size < 2000:
        print("   tts:", r.stderr.decode("utf-8", "replace")[-220:])
        return False
    # Дикторская обработка: срез гула ниже 90 Гц, лёгкий подъём разборчивости,
    # мягкая компрессия и приведение к -16 LUFS (речь микшуется под музыку позже).
    r = run(["ffmpeg", "-y", "-v", "error", "-i", str(raw),
             "-af", "highpass=f=90,equalizer=f=3200:t=q:w=1.4:g=2.5,"
                    "acompressor=threshold=-18dB:ratio=3:attack=8:release=180,"
                    "loudnorm=I=-16:TP=-1.5:LRA=11",
             "-c:a", "libmp3lame", "-b:a", "192k", str(dest)])
    if dest.exists() and dest.stat().st_size > 2000:
        raw.unlink(missing_ok=True)
        txt.unlink(missing_ok=True)
        return True
    print("   обработка голоса:", r.stderr.decode("utf-8", "replace")[-220:])
    return False


def render_slide(i: int, sc: dict) -> Path | None:
    """HTML → PNG с альфой. Прозрачный фон обязателен: слайд идёт слоем поверх мира."""
    page = WORK / f"slide{i}.html"
    png = WORK / f"slide{i}.png"
    page.write_text(
        f"<!doctype html><meta charset=utf-8><style>{CSS}</style>"
        f"<div class='slide {sc.get('scrim','')}'><div class=rule></div>{sc['html']}</div>",
        encoding="utf-8")
    if png.exists():
        return png
    r = run([str(CHROME), "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--default-background-color=00000000", f"--window-size={W},{H}",
             "--force-device-scale-factor=1", "--virtual-time-budget=4000",
             f"--screenshot={png}", page.resolve().as_uri()])
    if not png.exists():
        print("   chrome:", r.stderr.decode("utf-8", "replace")[-300:])
        return None
    return png


def ass_for(sub: str, seconds: float, path: Path, top: bool = False) -> Path:
    """Субтитр вжигается на кадрах продукта: их смотрят и без звука.

    Гало отдельным событием — на пёстром интерфейсе одной обводки мало.
    """
    al = 8 if top else 2
    head = f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Halo,Arial Black,50,&H00000000,&H00000000,&H00000000,&H00000000,-1,0,0,0,100,100,1,0,1,20,0,{al},120,120,74,204
Style: Main,Arial Black,50,&H00FFFFFF,&H00202020,&H00000000,&HA0000000,-1,0,0,0,100,100,1,0,1,5,3,{al},120,120,74,204

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    end = f"0:00:{seconds:06.3f}"
    body = (f"Dialogue: 0,0:00:00.00,{end},Halo,,0,0,0,,{{\\blur14\\1a&HFF&\\3a&H30&}}{sub}\n"
            f"Dialogue: 1,0:00:00.00,{end},Main,,0,0,0,,{{\\fad(200,200)}}{sub}\n")
    path.write_text(head + body, encoding="utf-8")
    return path


def kb(zoom: str, d: float, k: float = 0.07) -> str:
    """Ken Burns множителем масштаба: 'in' наезжает, 'out' отъезжает."""
    return f"1+{k}*t/{d:.2f}" if zoom == "in" else f"{1+k}-{k}*t/{d:.2f}"


def build_slide_scene(i: int, sc: dict, d: float, voice: Path) -> Path | None:
    """Фон дышит, текст стоит намертво: слайд накладывается вторым слоем."""
    png = render_slide(i, sc)
    if not png:
        return None
    bgp = BG / sc["bg"]
    z = kb(sc["zoom"], d)
    dest = WORK / f"sc{i:02d}.mp4"
    vf = (
        # мир: заполнить кадр, притемнить, слегка размыть — он подложка, а не сюжет
        f"[0:v]scale={W*2}:-2,crop={W*2}:{int(H*2)}:"
        f"'(iw-ow)/2':'(ih-oh)/2',eq=brightness=-0.06:saturation=0.88,"
        f"scale=w='iw*({z})':h='ih*({z})':eval=frame,"
        f"crop=w={W*2}:h={H*2}:x='(iw-ow)/2':y='(ih-oh)/2',scale={W}:{H}[bg];"
        f"[bg][1:v]overlay=0:0:format=auto,"
        f"fade=t=in:st=0:d=0.45,fade=t=out:st={max(0.1, d-0.45):.2f}:d=0.45,"
        f"format=yuv420p,setsar=1[v]"
    )
    r = run(["ffmpeg", "-y", "-v", "error", "-threads", "1",
             "-loop", "1", "-framerate", str(FPS), "-t", f"{d:.2f}", "-i", str(bgp),
             "-loop", "1", "-framerate", str(FPS), "-t", f"{d:.2f}", "-i", str(png),
             "-i", str(voice),
             "-filter_complex", vf, "-map", "[v]", "-map", "2:a:0",
             "-af", f"afade=t=in:st=0:d=0.2,afade=t=out:st={max(0.1, d-0.35):.2f}:d=0.35",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-shortest", str(dest)])
    if r.returncode != 0:
        print("   ffmpeg:", r.stderr.decode("utf-8", "replace")[-400:])
        return None
    return dest


def build_shot_scene(i: int, sc: dict, d: float, voice: Path) -> Path | None:
    """Кадр продукта: вписать целиком, пустоту закрыть размытой подложкой из него же.

    ⛔ Не растягивать под 16:9 — панели игры узкие и вертикальные.
    ⚑ Кроп ОТДЕЛЬНОЙ операцией в файл: иначе каждый кадр петли декодируется из
    исходных 2560x1720 (13 МБ в rgb24) и сборка падает по памяти, а наружу это
    выглядит как «Generic error in an external library» от libx264.
    """
    cw, ch, cx, cy = sc["crop"]
    src = WORK / f"crop{i}.png"
    if not src.exists():
        r = run(["ffmpeg", "-y", "-v", "error", "-threads", "1",
                 "-i", str(SHOTS / sc["shot"]),
                 "-vf", f"crop={cw}:{ch}:{cx}:{cy},scale='min({int(W*1.25)},iw)':-2",
                 "-frames:v", "1", "-update", "1", str(src)])
        if not src.exists():
            print("   crop:", r.stderr.decode("utf-8", "replace")[-200:])
            return None
    ass = ass_for(sc["sub"], d, WORK / f"s{i}.ass", top=sc.get("sub_top", False))
    ass_esc = str(ass).replace("\\", "/").replace(":", r"\:")
    z = kb(sc["zoom"], d, k=0.06)
    dest = WORK / f"sc{i:02d}.mp4"
    vf = (
        f"split=2[bgs][fg];"
        f"[bgs]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        f"gblur=sigma=38,eq=brightness=-0.24:saturation=0.75[bgb];"
        f"[fg]scale=w={W}:h={H}:force_original_aspect_ratio=decrease,"
        f"scale=w='iw*({z})':h='ih*({z})':eval=frame,"
        f"crop=w='min(iw,{W})':h='min(ih,{H})':x='(iw-ow)/2':y='(ih-oh)/2'[fgz];"
        f"[bgb][fgz]overlay=x='(W-w)/2':y='(H-h)/2':shortest=1,"
        f"fade=t=in:st=0:d=0.4,fade=t=out:st={max(0.1, d-0.4):.2f}:d=0.4,"
        f"format=yuv420p,setsar=1,subtitles='{ass_esc}'"
    )
    r = run(["ffmpeg", "-y", "-v", "error", "-threads", "1",
             "-loop", "1", "-framerate", str(FPS), "-t", f"{d:.2f}", "-i", str(src),
             "-i", str(voice), "-map", "0:v:0", "-map", "1:a:0", "-vf", vf,
             "-af", f"afade=t=in:st=0:d=0.2,afade=t=out:st={max(0.1, d-0.35):.2f}:d=0.35",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-shortest", str(dest)])
    if r.returncode != 0:
        print("   ffmpeg:", r.stderr.decode("utf-8", "replace")[-400:])
        return None
    return dest


def main() -> int:
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    parts = []
    for i, sc in enumerate(SCENES, 1):
        voice = WORK / f"v{i}.mp3"
        if not voice.exists() and not tts(sc["voice"], voice):
            print(f"  сцена {i} — нет голоса, ПРОПУСК")
            continue
        d = max(2.0, dur(voice) + 0.7)          # хвост на дыхание и затухание
        p = (build_slide_scene if sc["k"] == "slide" else build_shot_scene)(i, sc, d, voice)
        label = sc.get("sub", "") or sc["voice"][:52]
        print(f"  {i:2}/{len(SCENES)}  {sc['k']:5}  {dur(p):5.2f}с  {label[:52]}"
              if p else f"  {i:2} — ПРОПУЩЕНА")
        if p:
            parts.append(p)
    if not parts:
        print("нечего собирать")
        return 1

    lst = WORK / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    final = OUT / "cognopolis_investor.mp4"
    r = run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
             "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "libx264", "-preset", "slow",
             "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(final)], cwd=WORK)
    if r.returncode != 0:
        print("concat:", r.stderr.decode("utf-8", "replace")[-300:])
        return 1
    print(f"\nГОТОВО: {final}  ·  {dur(final):.1f}с  ·  {final.stat().st_size/1e6:.1f} МБ")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
