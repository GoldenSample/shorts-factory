# -*- coding: utf-8 -*-
"""«От нуля до своих агентов» — видеоверсия двухчастного дека (курс + полигон).

ОТДЕЛЬНЫЙ ПРОГОН, не правка инвесторского ролика. Исходник другой и голос другой:
деки 28-07 (deck (2/3).html) написаны от первого лица мастера — «писал не как
продукт, нужно было подтянуть друзей», финал не аск, а вопрос «нужно ли это
кому-то, кроме моих друзей и меня». Продавать этим голосом нельзя, им можно
только рассказывать — сценарий ниже это сохраняет.

Машинерия целиком из investor_reel.py (палитра BR2049, слайды с альфой поверх
живых Wan-петель, телеметрия вместо плиток, зерно одним проходом, легальные тени).
Скриншоты продукта — СВЕЖИЕ, вынуты прямо из деков (shots_deck2026/): среди них
главный кадр всей истории — «агент поторопился с ответом», где мир ловит
уверенное враньё агента проверкой по факту.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots_deck2026"
BG = HERE / "reel_bg"
BGV = HERE / "reel_bg_video"   # оживлённые фоны: замкнутые петли из Wan 2.2
WORK = HERE / "work_course"
OUT = HERE / "out"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
W, H, FPS = 1920, 1080, 30

# ── озвучка: Silero v4 локально (модель C:\Apps\comfy\silero4_ru.pt) ──
# edge-tts снят Гором с прогона: «озвучка так себе» плюс сломанное ударение
# «в ноутбукЕ» прямо в первой фразе. Silero даёт ручное ударение знаком «+»
# перед гласной и звучит собраннее. ⚠ Лицензия Silero — CC-BY-NC: для показа
# и фидбека годится, для МОНЕТИЗИРУЕМОГО релиза заменить (чистый путь — ACE-Step
# для музыки не поможет, для речи смотреть Chatterbox MIT).
# Пути ТОЛЬКО прямыми слэшами: обратные уже один раз съели «\v» из
# «v4_ru.pt» при прогоне текста через слои экранирования.
SILERO_PT = "C:/Apps/comfy/silero/v4_ru.pt"
SILERO_PY = "C:/Apps/comfy/ComfyUI_windows_portable/python_embeded/python.exe"
VOICE_NAME = "baya"   # выбор Гора по пробам 29-07 (аидар/евгений/бая)

# Правки ТОЛЬКО для голоса (на экран не попадают): латиница в звучание +
# ручные ударения «+» перед гласной для слов, которых нет в словаре RUAccent
# (транслитерации и неологизмы — их нейрочасть RUAccent как раз и валит,
# см. страховку в gen_voices_cb.py). «+» конвертируется в акут U+0301 до модели.
TTS_FIX = {
    "ноутбуке": "ноутб+уке",
    "ноутбук": "ноутб+ук",
    "MCP": "эм-си-п+и",
    "Kaggle": "к+эгл",
    "GGUF": "локальный формат",
    "в Хаб": "в хаб",
    "Cognopolis": "Когн+ополис",
    "Когнополис": "Когн+ополис",
    "smolagents": "смол-+эйджентс",
    "LangGraph": "ланг-гр+аф",
    "RAG": "р+аг",
    "бэкпрешер": "бэкпр+ешер",
    "дискавери": "диск+авери",
    "кулдаун": "кулд+аун",
    "Кулдаун": "Кулд+аун",
}

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


# ── сценарий: дуга двух деков в 13 блоков, голос от первого лица ─────────────
# Из 50 слайдов в ролик идёт хребет: провал ноутбука → зачем писался курс →
# три пробела → лесоруб → локальная модель как условие задачи → площадки →
# полигон → упражнения в костюме игры → подземье → библиотека →
# «агент врёт, мир не врёт» (кульминация) → честно → вопрос вместо аска.
#
# ⛔ Слово «дырка» не появляется нигде (прямой запрет оператора).
BLOCKS = [
    dict(id="hook",
         # ⛔ Без терминов в ГОЛОСЕ вообще. «Мок» на слух читался как «мог»,
         # «тестовая заглушка» — тот же жаргон в другой обёртке (оба замечания Гора).
         # В деке Вани термин остаётся: на письме его читают глазами.
         voice="В ноутбуке агент не может ошибиться по-настоящему: "
               "учебный пример всегда отвечает так, как задумал автор. "
               "Нет времени, нет отказа, нет чужих. "
               "Мне нужно было место, где сервер спорит с агентом — и где видно, кто из них прав.",
         planes=[
             (6, dict(k="slide", bg="01_problem.png", zoom="in", html="""
                <div class=kick><i>◆</i> ОТ НУЛЯ ДО СВОИХ АГЕНТОВ</div>
                <div class=mid><h1>Мир, который<br>сопротивляется</h1>
                <div class=sub>Курс и полигон: две части одной дороги —
                  от «впервые слышу про токены» до своего роя.</div></div>""")),
         ]),

    dict(id="origin",
         voice="Курс начинался не как продукт. Друзья спросили, с чего начать с агентами, "
               "и я не смог ответить ссылкой: всё, что находилось, кончалось ровно там, "
               "где начинается работа. Пришлось написать то, что я сам хотел бы прочитать.",
         planes=[
             (6, dict(k="slide", bg="02_built.png", zoom="out", html="""
                <div class=kick>Как это началось</div>
                <div class=mid><div class=st>Этот курс писался <em>не как продукт</em>.</div>
                <div class=sub>Нужно было подтянуть друзей и коллег — чтобы с ними можно
                  было работать с агентами всерьёз.</div></div>""")),
         ]),

    dict(id="gaps",
         voice="В существующих курсах не хватало трёх вещей. Мира, который сопротивляется. "
               "Одного сквозного героя вместо набора демок. И честного права пропускать: "
               "критерий не «знаю про это», а «могу показать в своём коде».",
         planes=[
             (6, dict(k="slide", bg="03_rules.png", zoom="in", scrim="full", crt=True, html=tel(
                 "ЧЕГО НЕ БЫЛО НИ В ОДНОМ КУРСЕ", "ТРИ ПРОБЕЛА",
                 row("Мир, который сопротивляется",
                     "01", "в ноутбуке нет последствий: ошибку негде увидеть")
                 + row("Один герой вместо набора демок",
                       "02", "складывать примеры в одну голову приходилось студенту")
                 + row("Честное право пропускать",
                       "03", "критерий: не «знаю про это», а «могу показать в коде»")))),
         ]),

    dict(id="hero",
         voice="Через весь курс идёт один герой — лесоруб. Сначала он функция в ноутбуке. "
               "Потом агент, потом получает умения, начинает говорить по MCP, обзаводится "
               "справочником и воротами, где человек подтверждает опасный шаг. "
               "Меняется не герой — меняется инженерный приём.",
         planes=[
             (5, dict(k="slide", bg="04_swarm.png", zoom="out", scrim="full", crt=True, html=tel(
                 "ПЯТЬ ИНКАРНАЦИЙ ОДНОГО ЛЕСОРУБА", "ОДИН ГЕРОЙ · ОДНА ЛЕСТНИЦА",
                 row("Лесоруб на smolagents", "I", "дизайн инструментов без догадок")
                 + row("Лесоруб с умениями · Skills", "II", "выученный приём вместо простыни в промпте")
                 + row("Лесоруб через MCP", "III", "тот же агент говорит по стандарту")
                 + row("Лесоруб со справочником · RAG", "IV", "читает документацию мира вместо хардкода")
                 + row("Лесоруб на рельсах · LangGraph", "V",
                       "ворота разрешений: человек подтверждает опасный шаг")))),
             (4, dict(k="shot", shot="p1_05_И_вот_он_отвечает.webp",
                      sub="лесоруб отвечает — и проверка сверяет его слова по факту")),
         ]),

    dict(id="local",
         voice="Все пятеро работают на локальной модели, без ключей и без счетов. "
               "Это не экономия, а условие задачи: маленькая модель на семь миллиардов "
               "путается там, где большая догадается. Если твой агент работает на ней — "
               "значит, ты действительно спроектировал инструменты, а не понадеялся "
               "на чужой интеллект.",
         planes=[
             (6, dict(k="slide", bg="03_rules.png", zoom="out", html="""
                <div class=kick>Условие задачи</div>
                <div class=mid><div class=st>Все пять лесорубов работают
                  на <em>локальной модели</em>.</div>
                <div class=sub>Маленькая модель прощает меньше — и именно на ней видно,
                  спроектирован инструмент или нет. В коде так и стоит: температура 0.2,
                  «локальные путаются, держим их на рельсах».</div></div>""")),
         ]),

    dict(id="platforms",
         voice="Практика сдаётся на настоящих площадках. Домашка — прямо на живом "
               "соревновании Kaggle. Своя обученная модель публикуется в Хаб, собирается "
               "в GGUF и запускается локально без интернета. К концу остаётся не конспект, "
               "а профиль с работами: семь запускаемых агентов и четыре опубликованные модели.",
         planes=[
             (4, dict(k="shot", shot="p1_06_Домашка_сдаётся_прямо_на_соревновании.webp",
                      sub="домашка = ноутбук на живом соревновании Kaggle")),
             (3, dict(k="shot", shot="p1_07_Своя_модель__опубликована_и_запускается.png",
                      sub="своя нано-GPT: обучил → выложил → забрал → запустил у себя")),
             (4, dict(k="shot", shot="p1_09_К_концу_остаётся_не_конспект_а_профиль_с.webp",
                      sub="к концу — профиль с работами, а не конспект")),
         ]),

    dict(id="polygon",
         voice="Вторая часть — полигон. Cognopolis: поселение в общем мире, где играют "
               "не мышкой, а кодом. Один житель — один токен — один агент. "
               "Мир один на всех: чужие агенты ходят по той же карте и забирают ту же добычу.",
         planes=[
             (5, dict(k="slide", bg="05_market.png", zoom="in", html="""
                <div class=kick>Часть вторая</div>
                <div class=mid><div class=st>Полигон: мир, где агент может ошибиться
                  <em>по-настоящему</em>.</div>
                <div class=sub>Играют не мышкой, а кодом. Один житель = один токен = один агент.</div></div>""")),
             (4, dict(k="shot", shot="p2_02_Слева__кто_он_в_центре__где_он_справа__ч.webp",
                      sub="зелёное кольцо — свой житель · серые силуэты — чужие агенты")),
         ]),

    dict(id="drills",
         voice="Я шёл не от механики к навыку, а наоборот: сначала называл навык, потом "
               "придумывал, чем зажать человека в мире, чтобы без этого навыка не пройти. "
               "Кулдаун — это бэкпрешер. Строгий отказ — чтение машинных ошибок. "
               "Публичные каталоги — дискавери. Общий мир — идемпотентность. "
               "Это упражнения, замаскированные под игру.",
         planes=[
             (7, dict(k="slide", bg="05_market.png", zoom="out", scrim="full", crt=True, html=tel(
                 "МЕХАНИКА → НАВЫК", "УПРАЖНЕНИЯ В КОСТЮМЕ ИГРЫ",
                 row("Кулдаун после каждого действия", "цикл",
                     "backpressure: посмотрел → решил → сделал → подождал")
                 + row("Отказ приходит структурой violations", "422",
                       "читать машинные ошибки, не додумывать за сервер")
                 + row("Правила мира лежат снаружи", "GET",
                       "discovery: агент спрашивает, а не помнит")
                 + row("Пока шёл к гоблину — гоблина убил чужой", "мир",
                       "идемпотентность и чужие эффекты: в проде это норма")))),
         ]),

    dict(id="mine",
         voice="Подземье — рабочая задача в костюме шахты. Наказ приходит как от заказчика: "
               "текст с доменным словарём, приложенный файл данных и одно число ответа. "
               "Промах стоит здоровья. А решение «глубже или наверх» — это ставка "
               "на частоту ошибок твоего собственного агента.",
         planes=[
             (5, dict(k="shot", shot="p2_05_Задача_приходит_как_от_заказчика_текст_ф.webp",
                      sub="наказ старосты: доменный словарь, метрика словами, файл приложен")),
             (4, dict(k="shot", shot="p2_06_Данные_которые_не_окинуть_глазом__только.png",
                      sub="ledger.csv: скачать и посчитать — на глаз нельзя", sub_top=True)),
         ]),

    dict(id="library",
         voice="И одно место в игре устроено так, что деньги туда не заносятся. "
               "Верхние ступени знания открываются не золотом, а числом честных "
               "неудачных попыток. Не набил шишек — не продадут ни за какие деньги.",
         planes=[
             (6, dict(k="slide", bg="02_built.png", zoom="in", html="""
                <div class=kick>Библиотека</div>
                <div class=mid><div class=st>Знание нельзя купить
                  <em>в обход практики</em>.</div>
                <div class=sub>Между забегами прогрессирует не предмет,
                  а код студента.</div></div>""")),
         ]),

    dict(id="catch", dip=True,
         voice="Вот ради этой строки всё и построено. Агент отчитался: всё сделано. "
               "А мир поймал его по факту: дерево ещё в рюкзаке, житель не дома, "
               "на склад не сдано — агент поторопился с ответом. "
               "Агент врёт уверенно. Мир — нет.",
         planes=[
             (6, dict(k="shot", shot="p2_13_Агент_уверенно_врёт__а_мир_не_врёт.webp",
                      sub="агент врёт уверенно — мир не врёт", sub_top=True)),
         ]),

    dict(id="honest",
         voice="Теперь честно. Пользователей ноль, и двери для них нет физически: "
               "регистрация отвечает отказом, аккаунт выдаёт администратор. "
               "Монетизации нет ни в каком виде. Мир маленький — семь на семь клеток, "
               "и это видно.",
         planes=[
             (6, dict(k="slide", bg="01_problem.png", zoom="out", html="""
                <div class=kick>Чего здесь нет — назову сам</div>
                <div class=mid><div class=st>Пользователей <em>ноль</em>.
                  Монетизации нет. Мир маленький.</div>
                <div class=sub>Это не плохая конверсия — это отсутствие двери:
                  регистрацию открою, когда будет что открывать.</div></div>""")),
         ]),

    dict(id="ask",
         voice="Полигон был условием, а не украшением: без мира, который сопротивляется, "
               "курс остался бы ещё одним курсом. Демо открыто прямо сейчас, вход под "
               "тестовым пользователем. А поговорить я хочу об одном: что достраивать "
               "первым — и нужно ли это кому-то, кроме моих друзей и меня.",
         planes=[
             (4, dict(k="slide", bg="02_built.png", zoom="in", html="""
                <div class=kick>Зачем всё это было</div>
                <div class=mid><div class="st sm">Полигон был <em>условием</em>,
                  а не украшением.</div></div>""")),
             (5, dict(k="slide", bg="02_built.png", zoom="out", html="""
                <div class=kick>Открыто прямо сейчас</div>
                <div class=mid><div class=url>kindomklaster.com</div>
                <div class=sub>Вход под тестовым пользователем, без регистрации.
                  Вопрос, ради которого это показывается: что достраивать первым?</div></div>""")),
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
    """Silero локально + прежняя дикторская обработка ffmpeg."""
    if dest.exists():
        return True
    for a, b in TTS_FIX.items():
        text = text.replace(a, b)
    raw = dest.with_suffix(".raw.wav")
    txt = dest.with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")          # кириллица в argv бьётся
    code = ("import sys, wave, torch\nt = open(sys.argv[1], encoding='utf-8').read()\nimp = torch.package.PackageImporter(SILERO_PT_X)\nm = imp.load_pickle('tts_models', 'model')\nm.to(torch.device('cpu'))\na = m.apply_tts(text=t, speaker='VOICE_X', sample_rate=48000, put_accent=True, put_yo=True)\nw = wave.open(sys.argv[2], 'wb')\nw.setnchannels(1); w.setsampwidth(2); w.setframerate(48000)\nw.writeframes((a * 32767).to(torch.int16).numpy().tobytes()); w.close()"
            .replace("SILERO_PT_X", "r" + chr(39) + SILERO_PT + chr(39))
            .replace("VOICE_X", VOICE_NAME))
    r = run([SILERO_PY, "-c", code, str(txt), str(raw)])
    if not raw.exists() or raw.stat().st_size < 20000:
        print("   tts:", r.stderr.decode("utf-8", "replace")[-260:])
        return False
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
        loop = BGV / (pl["bg"].replace(".png", "_safe.mp4"))   # процедурный пульс света
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
                 # ⚠ fps принудительно: живые петли идут в 24 к/с, кадры в 30,
                 # и concat на смешанном fps растягивает PTS (ловили +18.6 с)
                 "-r", str(FPS),
                 "-c:v", "libx264", "-preset", "medium", "-crf", "15",
                 "-pix_fmt", "yuv420p", str(dest)])
        if r.returncode != 0:
            print("   слайд:", r.stderr.decode("utf-8", "replace")[-400:])
            return None
        return dest

    # ── кадр продукта ──
    # Кроп необязателен: скриншоты из деков уже вырезаны автором по смыслу.
    # Пережимаем в PNG в любом случае — и ради webp (петля -loop с ним капризна),
    # и ради памяти на больших кадрах.
    src = WORK / f"{tag}_crop.png"
    if not src.exists():
        crop = pl.get("crop")
        pre = f"crop={crop[0]}:{crop[1]}:{crop[2]}:{crop[3]}," if crop else ""
        r = run(["ffmpeg", "-y", "-v", "error", "-threads", "1",
                 "-i", str(SHOTS / pl["shot"]),
                 "-vf", f"{pre}scale='min({int(W*1.2)},iw)':-2",
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
             "-r", str(FPS),
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
    return vcat


def block_wav(i: int, vlen: float) -> Path | None:
    """Голос блока, выровненный сэмпль-в-сэмпль под длину ЕГО видео.

    ⛔ Прежняя схема — AAC в каждом блоке и склейка 13 файлов — давала дрейф:
    у AAC в начале каждого файла ~2 кадра прайминга (≈43 мс), склейка их копит,
    и к концу ролика звук уезжал на полсекунды (замечание Вани «рассинхро
    в конце»). Теперь звук существует единой WAV-дорожкой: у WAV прайминга нет,
    каждый блок обрезан/добит тишиной ровно до длины своего видео, кодирование
    в AAC происходит ОДИН раз на финале.
    """
    voice = WORK / f"v{i}.mp3"
    dest = WORK / f"a{i:02d}.wav"
    r = run(["ffmpeg", "-y", "-v", "error", "-i", str(voice),
             "-af", f"aresample=48000,adelay=120|120,apad,atrim=duration={vlen:.6f}",
             "-ac", "2", "-c:a", "pcm_s16le", str(dest)])
    return dest if r.returncode == 0 and dest.exists() else None


def main() -> int:
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    vids, wavs = [], []
    for i, b in enumerate(BLOCKS, 1):
        p = build_block(i, b)
        if not p:
            print(f"  {i:2}  {b['id']} — ПРОПУЩЕН")
            continue
        vlen = dur(p)
        a = block_wav(i, vlen)
        if not a:
            print(f"  {i:2}  {b['id']} — нет звука, ПРОПУЩЕН")
            continue
        print(f"  {i:2}/{len(BLOCKS)}  {b['id']:9} {vlen:5.2f}с  {len(b['planes'])} план(а)")
        vids.append(p)
        wavs.append(a)
    if not vids:
        print("нечего собирать")
        return 1

    # ── видео одной лентой ──
    vlst = WORK / "all_v.txt"
    vlst.write_text("".join(f"file '{p.name}'\n" for p in vids), encoding="utf-8")
    # ── голос одной дорожкой (WAV склеивается сэмпль-точно) ──
    alst = WORK / "all_a.txt"
    alst.write_text("".join(f"file '{p.name}'\n" for p in wavs), encoding="utf-8")
    voice_all = WORK / "voice_all.wav"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(alst),
         "-c", "copy", str(voice_all)], cwd=WORK)

    total = dur(voice_all)
    final = OUT / "agents_course_reel.mp4"
    music = WORK / "music_amb.mp3"

    if music.exists():
        # Микс по замерам скила: музыка −15 дБ под голосом, дакинг сверху
        # (порог/ратио из справочника 10_audio), два такта тишины в конце.
        # ⚑ asplit ДО реверба не нужен: реверба нет; normalize=0 в amix обязателен,
        # иначе громкость делится пополам.
        af = (
            f"[1:a]aresample=48000,atrim=duration={total:.3f},"
            f"afade=t=in:st=0:d=2.5,afade=t=out:st={max(0.0, total-4.0):.3f}:d=4.0,"
            f"volume=-15dB[mus];"
            f"[0:a]asplit=2[vo][vk];"
            f"[mus][vk]sidechaincompress=threshold=0.03:ratio=8:attack=25:release=450:"
            f"makeup=1:knee=4:level_sc=1[duck];"
            f"[vo][duck]amix=inputs=2:duration=first:normalize=0,"
            f"loudnorm=I=-14:TP=-1.5:LRA=11,alimiter=limit=0.89:level=disabled[a]"
        )
        audio_in = ["-i", str(voice_all), "-i", str(music)]
        maps = ["-map", "2:v:0", "-map", "[a]"]
        # входы: 0 голос, 1 музыка, 2 видео-склейка
        r = run(["ffmpeg", "-y", "-v", "error", *audio_in,
                 "-f", "concat", "-safe", "0", "-i", str(vlst),
                 "-filter_complex",
                 f"[2:v]colorlevels=romin=0.0627:gomin=0.0627:bomin=0.0627,"
                 f"{GRAIN},format=yuv420p[v];{af}",
                 "-map", "[v]", "-map", "[a]",
                 "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-tune", "grain",
                 "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_trc", "bt709",
                 "-color_primaries", "bt709", "-color_range", "tv",
                 "-c:a", "aac", "-b:a", "192k",
                 "-movflags", "+faststart", str(final)], cwd=WORK)
    else:
        print("  ⚠ музыки нет (work_course/music_amb.mp3) — собираю без неё")
        r = run(["ffmpeg", "-y", "-v", "error", "-i", str(voice_all),
                 "-f", "concat", "-safe", "0", "-i", str(vlst),
                 "-vf", f"colorlevels=romin=0.0627:gomin=0.0627:bomin=0.0627,"
                        f"{GRAIN},format=yuv420p",
                 "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
                 "-map", "1:v:0", "-map", "0:a:0",
                 "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-tune", "grain",
                 "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_trc", "bt709",
                 "-color_primaries", "bt709", "-color_range", "tv",
                 "-c:a", "aac", "-b:a", "192k",
                 "-movflags", "+faststart", str(final)], cwd=WORK)
    if r.returncode != 0:
        print("сборка:", r.stderr.decode("utf-8", "replace")[-400:])
        return 1
    # контроль синхры: дорожки обязаны совпасть по длине с точностью кадра
    vd = dur(final)
    print(f"\nГОТОВО: {final} · {vd:.1f}с · {final.stat().st_size/1e6:.1f} МБ "
          f"· голос {total:.1f}с · расхождение {abs(vd-total):.2f}с")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
