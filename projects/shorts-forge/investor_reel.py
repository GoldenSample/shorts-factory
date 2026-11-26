# -*- coding: utf-8 -*-
"""Видеопитч Cognopolis для инвестора, вторая версия — собрана по диприсёрчу.

Что изменилось против build_investor.py и ПОЧЕМУ (каждое — из замера, не из вкуса):

1. БЛОКОВ 10, А НЕ 14, И ПРОДУКТ НАЗВАН В ПЕРВОЙ ФРАЗЕ.
   PG и YC об одном: типовая ошибка — не сказать, что делаешь, до середины питча.
   В первой версии продукт назывался на 40-50 секунде. Теперь имя и кадр живого
   сервера стоят в первых десяти секундах, рынок переехал ПОСЛЕ решения (иначе он
   отвечает на вопрос, которого зритель ещё не задал), бенчмарки подняты вплотную
   к решению — это не «часть проблемы», а наш единственный инсайт.

2. ВНУТРИ БЛОКА НЕСКОЛЬКО ПЛАНОВ.
   Средняя длина плана в питч-видео 2.5-4.0 с, у нас в первой версии было 10-18.
   Голос блока непрерывен, а картинка режется — так держится ритм. Соседние планы
   различаются по длине минимум на 40%, иначе монтаж читается метрономом.

3. ЧИСЛА ПОДАЮТСЯ ТЕЛЕМЕТРИЕЙ, А НЕ ПЛИТКАМИ.
   Плашка вокруг числа названа главным тэллом дешёвого дизайна 2026 (и заодно
   сигнатурой ИИ-презентаций: три одинаковые карточки с цветным бордером слева).
   Вместо них — приборная панель: моноширинный шрифт, выравнивание по сетке,
   hairline-линии и один акцентный тон. Это же закрывает просьбу про ретрофутуризм:
   cassette futurism входит как «аналоговая телеметрия мира» (плотный монохромный
   прибор, сканлинии как физика экрана), а не как неон, сетка и закат — последнее
   названо главным китчем жанра.

4. АКЦЕНТ СТРОИТСЯ ЧЕТЫРЬМЯ ПРИЗНАКАМИ, А НЕ ЦВЕТОМ.
   Замерено: золото #d7b06a против текста #e7d4a8 даёт 1.40:1 при пороге
   различимости 3:1, и поднять это нельзя — чтобы золото дало 3:1, текст пришлось
   бы погасить до 5:1 к фону. Поэтому акцент = тон + вес + кегль + hairline снизу.

5. ЗЕРНО СТАТИЧЕСКОЕ, ОДНИМ ПРОХОДОМ, ФЛАГ СТРОГО `u`.
   Тёмный градиент на 8-битном h264 бандится, зерно это лечит. Два замера, которые
   кажутся противоречивыми, но описывают разные режимы:
     · временное зерно (`allf=t+u`) делает каждый кадр уникальным — вес взлетает
       в сотни раз, и `-tune grain` поверх него добавляет ещё 4.4x;
     · статическое (`allf=u`, alls=4) сжимается один раз, и связка с crf 17
       и `-tune grain` даёт CAMBI 0.00 при 3.8 Мбит/с.
   Берём второй режим. ⚠ CAMBI, а не VMAF: без зерна на crf 23 VMAF показывает
   95.5 («отлично»), тогда как CAMBI 18.19 — полосы в тенях видны глазом.

6. KEN BURNS 1.5-3% В СЕКУНДУ.
   5%/с и выше — слайдшоу из 2010 (и это дефолт всех туториалов). Скриншоты
   интерфейса не двигаются вовсе: на тексте любое движение читается как дрожь.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots_cognopolis"
BG = HERE / "reel_bg"
BGV = HERE / "reel_bg_video"   # оживлённые фоны: замкнутые петли из Wan 2.2
WORK = HERE / "work_inv2"
OUT = HERE / "out"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
W, H, FPS = 1920, 1080, 30

VOICE_NAME = "ru-RU-DmitryNeural"
VOICE_RATE = "-4%"

# ── палитра ──────────────────────────────────────────────────────────────────
# Схема снята с грейда Blade Runner 2049 и проверена по APCA, а не подобрана на глаз.
# ⚠ #000000 не берём: чистый чёрный на видео — дыра без фактуры, стробит на OLED
# и не оставляет ступени между фоном и поверхностью. Рабочая яркость 9-12 из 255.
# ⚠ #FFFFFF тоже не берём: Lc -107.7 слепит, даёт гало у людей с астигматизмом
# и заставляет кодек тратить биты на границы букв.
C_BG      = "#0A0908"
C_SURF    = "#16130F"
C_TEXT    = "#E6DCCB"   # 14.57:1 к фону, APCA Lc -85.9 — попадание в коридор
C_ACCENT  = "#E8B85C"   # единственный акцент; H 41°, S 61%, V 91%
C_MUTED   = "#9A968E"
C_LINE    = "#2A241B"

CSS = f"""
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{background:transparent;width:{W}px;height:{H}px;overflow:hidden;
  font-family:'Segoe UI',system-ui,sans-serif;color:{C_TEXT};-webkit-font-smoothing:antialiased}}
.s{{position:absolute;inset:0;display:flex;flex-direction:column;padding:110px 160px 96px}}
.s>*{{position:relative;z-index:2}}
.ser{{font-family:'Palatino Linotype','Book Antiqua',Georgia,serif}}
.mono{{font-family:Consolas,'Cascadia Mono',ui-monospace,monospace}}

/* Скрим лёгкий: мир должен читаться, иначе генератив бессмысленен.
   Тяжёлое затемнение первой версии съедало кадр целиком. */
.s::before{{content:'';position:absolute;inset:0;z-index:1;pointer-events:none;background:
  linear-gradient(100deg, rgba(8,7,5,.90) 0%, rgba(8,7,5,.74) 46%, rgba(8,7,5,.18) 100%)}}
.s.full::before{{background:linear-gradient(180deg,rgba(8,7,5,.86),rgba(8,7,5,.92))}}

/* ⚑ Кегли по замеру, а не по вкусу: НИЖЕ 32 px в 1080p текст не переживает
   ни сжатие YouTube на 4-8 Мбит/с (съедает штрихи тоньше 2 px), ни телефон,
   который ужимает кадр вчетверо. В первой версии служебные подписи были 19-20 px —
   то есть буквально нечитаемы у половины зрителей. Трекинг на прописных
   +0.05...0.12em: плотные капители сливаются в полосу. */
.kick{{font-family:Consolas,monospace;font-size:34px;letter-spacing:.11em;text-transform:uppercase;
  color:{C_MUTED};margin-bottom:34px}}
.kick i{{font-style:normal;color:{C_ACCENT}}}
h1{{font-family:'Palatino Linotype','Book Antiqua',Georgia,serif;font-size:150px;line-height:1.0;
  letter-spacing:-.015em;color:{C_TEXT};font-weight:600;max-width:1480px}}
.st{{font-family:'Palatino Linotype','Book Antiqua',Georgia,serif;font-size:78px;line-height:1.12;
  letter-spacing:-.01em;color:{C_TEXT};max-width:1400px}}
.st.sm{{font-size:62px;line-height:1.16}}
.sub{{margin-top:32px;font-size:40px;line-height:1.4;color:{C_MUTED};max-width:1180px}}
.mid{{margin:auto 0}}
/* Акцент четырьмя признаками: тон + вес + hairline + место. Ни плашек, ни теней:
   drop-shadow и цветной бордер слева — сигнатура шаблонных ИИ-презентаций. */
em{{font-style:normal;color:{C_ACCENT};font-weight:700;
   border-bottom:2px solid rgba(232,184,92,.30);padding-bottom:3px}}
.foot{{margin-top:auto;font-family:Consolas,monospace;font-size:32px;color:{C_MUTED};
  letter-spacing:.04em}}
.url{{font-family:'Palatino Linotype',Georgia,serif;font-size:88px;color:{C_ACCENT};
  letter-spacing:.01em}}

/* ── приборная панель вместо плиток с цифрами ──
   Плашка вокруг числа и три одинаковые карточки с цветным бордером — названный
   маркер и дешёвого дизайна, и генеративных презентаций. Панель строится
   выравниванием и hairline-линиями: тот же смысл, ни одной рамки. */
.tel{{margin:auto 0;width:1560px;font-family:Consolas,monospace}}
.tel .hdr{{display:flex;justify-content:space-between;font-size:32px;letter-spacing:.09em;
  color:{C_MUTED};border-bottom:1px solid {C_LINE};padding-bottom:16px;margin-bottom:30px}}
.row{{display:grid;grid-template-columns:1fr auto;align-items:baseline;gap:40px;
  padding:24px 0;border-bottom:1px solid {C_LINE}}}
.row .lab{{font-size:40px;color:{C_TEXT};letter-spacing:0}}
.row .lab small{{display:block;font-size:30px;color:{C_MUTED};margin-top:10px}}
.row .num{{font-family:'Palatino Linotype',Georgia,serif;font-size:88px;line-height:1;
  color:{C_ACCENT};font-weight:600;text-align:right;white-space:nowrap}}
.row.q .num{{color:{C_MUTED}}}
.bar{{grid-column:1/-1;height:3px;background:{C_LINE};margin-top:18px;position:relative}}
.bar i{{position:absolute;left:0;top:0;bottom:0;background:{C_ACCENT};display:block}}
"""


def esc(s: str) -> str:
    return s


def row(lab: str, num: str, note: str = "", bar: int = 0, quiet: bool = False) -> str:
    b = f'<span class=bar><i style="width:{bar}%"></i></span>' if bar else ""
    return (f'<div class="row{" q" if quiet else ""}"><span class=lab>{lab}'
            + (f'<small>{note}</small>' if note else "")
            + f'</span><span class=num>{num}</span>{b}</div>')


def tel(title: str, right: str, rows: str) -> str:
    return (f'<div class=tel><div class=hdr><span>{title}</span><span>{right}</span></div>'
            f'{rows}</div>')


# ── сценарий: 10 блоков, внутри блока планы ──────────────────────────────────
# Каждый блок = один голосовой отрезок. planes = [(вес, визуал), ...]; вес задаёт
# долю длительности блока. Веса соседних планов различаются, чтобы монтаж не стучал.
#
# ⛔ Слово «дырка» не встречается нигде — прямой запрет оператора.
# ⛔ Сумму аска не называем: в исходном питче это осознанная позиция автора.
BLOCKS = [
    dict(id="what",
         voice="Cognopolis — живая MMO, в которую нельзя играть руками. "
               "Каждым жителем здесь управляет агент, которого пишет игрок.",
         planes=[
             (5, dict(k="shot", shot="hi_world.png", crop=(1150, 880, 625, 415), still=True,
                      over=dict(cls="", html=f"""<div class=kick><i>◆</i> COGNOPOLIS</div>
                        <div class=mid><h1>Мир, в который<br>нельзя играть руками</h1></div>
                        <div class=foot>боевой сервер · снято с живого сервера</div>"""))),
             (3, dict(k="shot", shot="hi_world.png", crop=(760, 640, 780, 480), still=True,
                      sub="Каждым жителем управляет агент игрока")),
         ]),

    dict(id="quo",
         voice="Агентов сегодня учат видео и ноутбуком. "
               "А в ноутбуке нет последствий: агент не теряет ресурс и не встречает других агентов.",
         planes=[
             (6, dict(k="slide", bg="01_problem.png", zoom="out", html=f"""
                <div class=kick>Как учат сейчас</div>
                <div class=mid><div class=st>Видео плюс ноутбук.
                  В ноутбуке <em>нет последствий</em>.</div>
                  <div class=sub>Агент не теряет ресурс, не блокируется состоянием мира
                    и никогда не встречает чужого агента.</div></div>""")),
         ]),

    dict(id="insight",
         voice="И это измерено. На двухстах тридцати одной задаче с живыми серверами "
               "лучшая модель проходит сорок три процента. "
               "Диагноз поставлен, а тренажёра, который его лечит, нет.",
         planes=[
             (5, dict(k="slide", bg="03_rules.png", zoom="in", scrim="full", crt=True, html=tel(
                 "ИЗМЕРЕНО НЕ НАМИ", "MCP-UNIVERSE · SALESFORCE",
                 row("Лучшая модель на живых MCP-серверах",
                     "43%", "231 задача · 11 настоящих серверов", bar=43)
                 + row("Люди применяют ИИ в работе", "60%", "", bar=60)
                 + row("Доверяют агенту задачу целиком", "0–20%",
                       "Anthropic называет это разрывом делегирования", bar=14)))),
             (3, dict(k="slide", bg="03_rules.png", zoom="out", html=f"""
                <div class=kick>Вывод</div>
                <div class=mid><div class=st>Бенчмарки поставили диагноз.
                  <em>Тренажёра нет.</em></div></div>""")),
         ]),

    dict(id="solution",
         voice="Мы его построили. Общий постоянный мир, где человек и его агент играют вдвоём. "
               "Серые силуэты на карте — жители других игроков, чужие агенты прямо сейчас. "
               "А каталоги мира отдаются без токена: агент спрашивает правила, а не зашивает их в код.",
         planes=[
             (5, dict(k="slide", bg="02_built.png", zoom="in", html=f"""
                <div class=kick>Решение</div>
                <div class=mid><div class=st>Общий постоянный мир,
                  в который играют <em>вдвоём</em>: человек и его агент.</div>
                  <div class=sub>Одна логика — две равноправные двери: REST и MCP.</div></div>""")),
             (4, dict(k="shot", shot="hi_world.png", crop=(760, 640, 780, 480), still=True,
                      sub="Серые силуэты — чужие агенты. Прямо сейчас.")),
             (5, dict(k="shot", shot="chk_codex.png", crop=(2420, 1010, 70, 340), still=True,
                      sub="74 пути REST · 49 MCP-тулов · каталоги без токена")),
         ]),

    dict(id="diff",
         voice="Дальше главное, и оно не в геймплее. "
               "Игра показывает не результат, а ум агента: намерение, такт и ошибки. "
               "Наблюдение за игрой становится отладкой твоего кода.",
         planes=[
             (4, dict(k="slide", bg="04_swarm.png", zoom="out", html=f"""
                <div class=kick>Дифференциатор</div>
                <div class=mid><div class=st>Смотреть на игру —
                  значит <em>отлаживать свой код</em>.</div></div>""")),
             (6, dict(k="shot", shot="hi_diag.png", crop=(830, 520, 90, 1400), still=True,
                      sub="Игра сама ставит диагноз агенту", sub_top=True)),
         ]),

    dict(id="whynow",
         voice="Почему сейчас. Спецификация протокола обновляется, и курсы под старую "
               "устаревают разом. За полгода два разработчика независимо выложили миры для агентов. "
               "А расходы компаний на внешнее обучение выросли на двадцать девять процентов "
               "при росте всего рынка на пять.",
         planes=[
             (5, dict(k="slide", bg="05_market.png", zoom="in", html=f"""
                <div class=kick>Почему сейчас</div>
                <div class=mid><div class="st sm">За полгода двое независимо пришли
                  к той же идее — мир для ИИ-агентов через MCP.
                  <em>Категория формируется сейчас.</em></div></div>""")),
             (4, dict(k="slide", bg="05_market.png", zoom="out", scrim="full", crt=True, html=tel(
                 "КУДА ТЕЧЁТ БЮДЖЕТ", "ФАКТ ПО ОТЧЁТНОСТИ",
                 row("Расходы компаний на внешние обучающие продукты", "+29%", "за год", bar=29)
                 + row("Весь рынок корпоративного обучения", "+5%", "за тот же период",
                       bar=5, quiet=True)
                 + row("Навык в вакансиях", "×4", "год назад его почти не было", bar=40)))),
         ]),

    dict(id="who_pays",
         voice="Кто платит. Ориентир по подписке — сорок девять долларов в месяц "
               "при миллионе двухстах тысячах зарегистрированных у ближайшего аналога. "
               "Корпоративный контур — около четырёхсот долларов за место в год, "
               "из того самого растущего бюджета.",
         planes=[
             (6, dict(k="slide", bg="02_built.png", zoom="in", scrim="full", crt=True, html=tel(
                 "ОРИЕНТИРЫ РЫНКА", "ЦЕНЫ НЕ НАШИ — СОСЕДЕЙ",
                 row("Подписка на тренажёр (Boot.dev)", "$49", "в месяц · 1.2 млн регистраций")
                 + row("Корпоративное место", "~$400", "в год · бюджет, растущий на 29%")
                 + row("Платное знание внутри игры", "готово",
                       "механика уже в коде, пока за внутриигровое золото", quiet=True)))),
         ]),

    dict(id="speed",
         voice="Про скорость. Тридцать четыре дня от нуля до боевого сервиса, "
               "тысяча триста двадцать два теста, восемьдесят пять выкаток в прод. "
               "Построил это рой ИИ-агентов: тринадцать ролей и сто двадцать четыре записанных решения. "
               "Метод переносимый — он записан, а не в голове.",
         planes=[
             (5, dict(k="slide", bg="04_swarm.png", zoom="out", scrim="full", crt=True, html=tel(
                 "СДЕЛАНО ОТНОСИТЕЛЬНО ВРЕМЕНИ", "34 ДНЯ",
                 row("Автотестов", "1322", "красный тест физически не доезжает до прода")
                 + row("Выкаток в прод", "85", "два с половиной деплоя в день")
                 + row("Записанных решений", "124", "каждое можно оспорить по номеру")))),
             (5, dict(k="slide", bg="04_swarm.png", zoom="in", html=f"""
                <div class=kick>Как это построено</div>
                <div class=mid><div class="st sm">Этот продукт построил
                  <em>рой ИИ-агентов</em>. Курс продаёт ровно тот конвейер,
                  который его построил.</div>
                  <div class=sub>13 ролей с зонами владения. Метод записан и переносится —
                    онбординг это git clone, а не месяц рядом с автором.</div></div>""")),
         ]),

    dict(id="honest", dip=True,
         voice="Теперь честно. Пользователей ноль. "
               "И это не плохая воронка: публичной регистрации нет физически, аккаунт выдаёт админ. "
               "Именно на воронку и нужны деньги.",
         planes=[
             (6, dict(k="slide", bg="01_problem.png", zoom="out", html=f"""
                <div class=kick>Чего у нас нет</div>
                <div class=mid><div class=st>Пользователей <em>ноль</em>.</div>
                  <div class=sub>Публичной регистрации нет физически — аккаунт выдаёт админ.
                    Нагрузку не мерили, мир пока небольшой.
                    Есть работающий продукт, проверяемый метод и скорость.</div></div>""")),
         ]),

    dict(id="ask",
         voice="Три формы участия: деньги на воронку, первый корпоративный пилот "
               "и доступ к тем, кто уже покупает внешнее обучение. "
               "Демо открыто прямо сейчас — вход под тестовым пользователем, без регистрации.",
         planes=[
             (5, dict(k="slide", bg="02_built.png", zoom="in", html=f"""
                <div class=kick>Что нам нужно</div>
                <div class=mid><div class="st sm">Деньги на воронку · первый
                  корпоративный пилот · доступ к тем, кто <em>уже покупает обучение</em></div></div>""")),
             (4, dict(k="slide", bg="02_built.png", zoom="out", html=f"""
                <div class=kick>Следующий шаг</div>
                <div class=mid><div class=url>kindomklaster.com</div>
                  <div class=sub>Вход под тестовым пользователем. Без регистрации,
                    прямо во время разговора.</div></div>""")),
         ]),
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


def tts(text: str, dest: Path) -> bool:
    """edge-tts + дикторская обработка. media-forge отпадает: xAI отдаёт 403."""
    if dest.exists():
        return True
    raw = dest.with_suffix(".raw.mp3")
    txt = dest.with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")        # кириллица в argv бьётся
    code = ("import asyncio,edge_tts,sys\n"
            "t=open(sys.argv[1],encoding='utf-8').read()\n"
            f"c=edge_tts.Communicate(t,'{VOICE_NAME}',rate='{VOICE_RATE}')\n"
            "asyncio.run(c.save(sys.argv[2]))\n")
    r = run([sys.executable, "-c", code, str(txt), str(raw)])
    if not raw.exists() or raw.stat().st_size < 2000:
        print("   tts:", r.stderr.decode("utf-8", "replace")[-200:])
        return False
    # компрессия строго <=3:1 и attack >=10 мс: жёстче звучит как радиореклама
    run(["ffmpeg", "-y", "-v", "error", "-i", str(raw),
         "-af", "highpass=f=85,equalizer=f=250:t=q:w=1.2:g=-3,"
                "equalizer=f=2800:t=q:w=1.4:g=3,"
                "acompressor=threshold=-20dB:ratio=3:attack=12:release=200,"
                "loudnorm=I=-16:TP=-1.5:LRA=11",
         "-c:a", "libmp3lame", "-b:a", "192k", str(dest)])
    if dest.exists():
        raw.unlink(missing_ok=True)
        txt.unlink(missing_ok=True)
        return True
    return False


def render(html: str, name: str, cls: str = "") -> Path | None:
    """HTML → PNG с альфой: слайд идёт слоем поверх картинки, текст не масштабируется."""
    page = WORK / f"{name}.html"
    png = WORK / f"{name}.png"
    page.write_text(f"<!doctype html><meta charset=utf-8><style>{CSS}</style>"
                    f"<div class='s {cls}'>{html}</div>", encoding="utf-8")
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
    """Субтитр на кадрах продукта. Гало отдельным слоем: одной обводки на пёстром мало."""
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
Style: Halo,Segoe UI Semibold,46,&H00000000,&H00000000,&H00000000,&H00000000,-1,0,0,0,100,100,0.6,0,1,18,0,{al},150,150,80,204
Style: Main,Segoe UI Semibold,46,&H00ABC3CD,&H00202020,&H00000000,&HA0000000,-1,0,0,0,100,100,0.6,0,1,4,2,{al},150,150,80,204

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    end = f"0:00:{seconds:06.3f}"
    body = (f"Dialogue: 0,0:00:00.00,{end},Halo,,0,0,0,,{{\\blur12\\1a&HFF&\\3a&H38&}}{sub}\n"
            f"Dialogue: 1,0:00:00.00,{end},Main,,0,0,0,,{{\\fad(220,220)}}{sub}\n")
    path.write_text(head + body, encoding="utf-8")
    return path


# ⚑ ЗЕРНО НАКЛАДЫВАЕТСЯ ОДИН РАЗ, В ФИНАЛЬНОМ ПРОХОДЕ — не на каждом плане.
# Причина: планы потом перекодируются при склейке, и зерно, пережатое дважды,
# частью стирается — а именно оно держит тени от бандинга.
#
# Почему вообще зерно обязательно (замер CAMBI, метрика бандинга Netflix;
# 0 — чисто, 5 — раздражает): наш тёмный градиент без зерна на crf 23 даёт
# CAMBI 18.19 при VMAF 95.5 — то есть VMAF показывает «отлично», а полосы в тенях
# видны глазом. Зерно alls=4 + crf 17 даёт CAMBI 0.00 при 3.8 Мбит/с.
# ⚠ Флаг строго `u` (статическое), не `t+u`: временное зерно разгоняет битрейт
# в десятки раз, потому что каждый кадр становится уникальным.
GRAIN = "noise=alls=4:allf=u"


def crt_layer(d: float) -> str:
    """Сканлинии периодом 6 px через tile+blend.

    ⚑ 6 px, а не 2: при даунскейле 1080→720 период 2 px теряет 92% амплитуды и
    превращается в серую кашу, 4 px даёт муар, 6 px выживает на 93% без муара.
    ⚑ tile+blend вместо geq — та же картинка, но в 24 раза быстрее.
    ⚠ format=gbrp обязателен на обеих ветках, иначе blend множит в YUV 16-235.
    """
    return (f"color=c=white:s={W}x1:d={d:.2f}:r={FPS}[wl];"
            f"color=c=black:s={W}x1:d={d:.2f}:r={FPS}[bl];"
            f"[wl][bl]vstack=inputs=2,scale={W}:6:flags=neighbor,tile=1x{H//6},"
            f"format=gbrp,setsar=1[slraw];")


def plane_video(tag: str, pl: dict, d: float) -> Path | None:
    """Один план: картинка + (для слайда) текстовый слой сверху. Без звука."""
    dest = WORK / f"{tag}.mp4"
    if dest.exists():
        return dest

    if pl["k"] == "slide":
        png = render(pl["html"], f"{tag}_txt", cls=pl.get("scrim", ""))
        if not png:
            return None
        # ⚑ Если для фона есть оживлённая петля — берём её и ОТКЛЮЧАЕМ Ken Burns.
        # Два движения разом (дыхание кадра + наезд камеры) читаются как дрожь;
        # канон прямо запрещает два разнонаправленных дрейфа подряд.
        loop = BGV / (pl["bg"].replace(".png", "_loop.mp4"))
        live = loop.exists()
        src = loop if live else BG / pl["bg"]
        # Ken Burns 2%/с: выше — слайдшоу. Движение уже идёт в первом кадре.
        k = 0.0 if live else min(0.20, 0.02 * d)
        z = (f"1+{k:.3f}*t/{d:.2f}" if pl["zoom"] == "in"
             else f"{1+k:.3f}-{k:.3f}*t/{d:.2f}") if k else "1"
        pre = crt_layer(d) if pl.get("crt") else ""
        crt = ("[bgz][slraw]blend=all_mode=multiply:shortest=1,"
               "format=yuv420p[bgc];" if pl.get("crt") else "")
        vf = (
            f"{pre}"
            # ⚠ force_original_aspect_ratio=increase обязателен: оживлённые петли
            # приходят в 1280x704, и простой scale по ширине давал высоту МЕНЬШЕ кропа —
            # ffmpeg падал с «Could not open encoder before EOF», что читается как
            # ошибка кодека, хотя ломалась геометрия.
            f"[0:v]scale={W*2}:{H*2}:force_original_aspect_ratio=increase,"
            f"crop={W*2}:{H*2}:'(iw-ow)/2':'(ih-oh)/2',"
            f"eq=brightness=0.02:saturation=0.92,"
            f"scale=w='iw*({z})':h='ih*({z})':eval=frame,"
            f"crop=w={W*2}:h={H*2}:x='(iw-ow)/2':y='(ih-oh)/2',scale={W}:{H},"
            f"format=gbrp,setsar=1[bgz];"
            f"{crt}"
            f"[{'bgc' if pl.get('crt') else 'bgz'}]format=yuv420p[bgf];"
            # текст появляется мягко и НИКОГДА не двигается вместе с фоном
            f"[1:v]format=rgba,fade=t=in:st=0.10:d=0.42:alpha=1[txt];"
            f"[bgf][txt]overlay=0:0:format=auto,format=yuv420p,setsar=1[v]"
        )
        bg_in = (["-stream_loop", "-1", "-t", f"{d:.2f}", "-i", str(src)] if live else
                 ["-loop", "1", "-framerate", str(FPS), "-t", f"{d:.2f}", "-i", str(src)])
        r = run(["ffmpeg", "-y", "-v", "error", "-threads", "1", *bg_in,
                 "-loop", "1", "-framerate", str(FPS), "-t", f"{d:.2f}", "-i", str(png),
                 "-filter_complex", vf, "-map", "[v]",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "15",
                 "-pix_fmt", "yuv420p", str(dest)])
        if r.returncode != 0:
            print("   слайд:", r.stderr.decode("utf-8", "replace")[-400:])
            return None
        return dest

    # ── кадр продукта ──
    cw, ch, cx, cy = pl["crop"]
    src = WORK / f"{tag}_crop.png"
    if not src.exists():
        # ⚑ Кроп отдельным файлом: иначе каждый кадр петли декодируется из 2560x1720
        # (13 МБ в rgb24) и сборка падает по памяти, а ffmpeg врёт про libx264.
        r = run(["ffmpeg", "-y", "-v", "error", "-threads", "1",
                 "-i", str(SHOTS / pl["shot"]),
                 "-vf", f"crop={cw}:{ch}:{cx}:{cy},scale='min({int(W*1.2)},iw)':-2",
                 "-frames:v", "1", "-update", "1", str(src)])
        if not src.exists():
            print("   кроп:", r.stderr.decode("utf-8", "replace")[-200:])
            return None

    layers = []
    if pl.get("over"):
        png = render(pl["over"]["html"], f"{tag}_txt", cls=pl["over"].get("cls", ""))
        if png:
            layers.append(png)

    # ⛔ Скриншот интерфейса НЕ двигаем: на мелком тексте Ken Burns читается как дрожь.
    vf = (
        f"[0:v]split=2[bgs][fg];"
        f"[bgs]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        f"gblur=sigma=36,eq=brightness=-0.22:saturation=0.72[bgb];"
        f"[fg]scale=w={W}:h={H}:force_original_aspect_ratio=decrease[fgf];"
        f"[bgb][fgf]overlay=x='(W-w)/2':y='(H-h)/2':shortest=1,"
        f"format=yuv420p,setsar=1[base]"
    )
    ins = ["-loop", "1", "-framerate", str(FPS), "-t", f"{d:.2f}", "-i", str(src)]
    if layers:
        ins += ["-loop", "1", "-framerate", str(FPS), "-t", f"{d:.2f}", "-i", str(layers[0])]
        vf += (f";[1:v]format=rgba,fade=t=in:st=0.10:d=0.42:alpha=1[txt];"
               f"[base][txt]overlay=0:0:format=auto[v]")
        last = "[v]"
    else:
        last = "[base]"
    if pl.get("sub"):
        ass = ass_for(pl["sub"], d, WORK / f"{tag}.ass", top=pl.get("sub_top", False))
        ass_esc = str(ass).replace("\\", "/").replace(":", r"\:")
        vf += f";{last}subtitles='{ass_esc}'[vs]"
        last = "[vs]"
    r = run(["ffmpeg", "-y", "-v", "error", "-threads", "1", *ins,
             "-filter_complex", vf, "-map", last,
             "-c:v", "libx264", "-preset", "medium", "-crf", "15",
             "-pix_fmt", "yuv420p", str(dest)])
    if r.returncode != 0:
        print("   кадр:", r.stderr.decode("utf-8", "replace")[-400:])
        return None
    return dest


def build_block(i: int, b: dict) -> Path | None:
    voice = WORK / f"v{i}.mp3"
    if not tts(b["voice"], voice):
        return None
    total = dur(voice) + 0.75          # хвост: пауза после фразы, а не обрыв
    wsum = sum(w for w, _ in b["planes"])
    parts = []
    for j, (w, pl) in enumerate(b["planes"], 1):
        d = max(1.6, total * w / wsum)
        p = plane_video(f"b{i:02d}p{j}", pl, d)
        if p:
            parts.append(p)
    if not parts:
        return None

    lst = WORK / f"b{i:02d}.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    vcat = WORK / f"b{i:02d}_v.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-c", "copy", str(vcat)], cwd=WORK)
    dest = WORK / f"blk{i:02d}.mp4"
    r = run(["ffmpeg", "-y", "-v", "error", "-i", str(vcat), "-i", str(voice),
             "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
             "-af", "adelay=120|120,apad", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
             "-shortest", str(dest)])
    if r.returncode != 0:
        print("   блок:", r.stderr.decode("utf-8", "replace")[-300:])
        return None
    return dest


def main() -> int:
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    parts = []
    for i, b in enumerate(BLOCKS, 1):
        p = build_block(i, b)
        print(f"  {i:2}/{len(BLOCKS)}  {b['id']:9} {dur(p):5.2f}с  "
              f"{len(b['planes'])} план(а)" if p else f"  {i:2}  {b['id']} — ПРОПУЩЕН")
        if p:
            parts.append(p)
    if not parts:
        print("нечего собирать")
        return 1

    lst = WORK / "all.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts), encoding="utf-8")
    final = OUT / "cognopolis_investor_v2.mp4"
    # ⚠ -color_range СТРОГО tv: с pc почти-чёрный #0A0908 уезжает в код ниже
    # легального 16, и плееры срезают его в чистый ноль — теряется вся фактура теней.
    r = run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
             # ⚑ Чёрная точка поднимается ДО кодирования. Замер готового ролика дал
             # YMIN 8 при легальном пределе 16 для tv-range: часть теней уезжала
             # под нижнюю границу, и плеер срезал бы её в плоский ноль — вместе с
             # фактурой, ради которой мы и не берём #000000.
             "-vf", f"colorlevels=romin=0.0627:gomin=0.0627:bomin=0.0627,{GRAIN},format=yuv420p",
             "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
             "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-tune", "grain",
             "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_trc", "bt709",
             "-color_primaries", "bt709", "-color_range", "tv",
             "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(final)], cwd=WORK)
    if r.returncode != 0:
        print("сборка:", r.stderr.decode("utf-8", "replace")[-400:])
        return 1
    print(f"\nГОТОВО: {final} · {dur(final):.1f}с · {final.stat().st_size/1e6:.1f} МБ")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
