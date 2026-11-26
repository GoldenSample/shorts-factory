# -*- coding: utf-8 -*-
"""СЛОГ ГОРА ИЗ СТАРОГО ТВИТТЕРА: замер корпуса для голоса шортсов. Вшито 04.10.2026 словом Гора
«тащи стиль из старого твиттера для голоса в шортсах».

Архив твиттера (@1nnersun, 2010-2026, аккаунт закрыт) -> только его собственный голос -> счётные метрики слога.
Выводы и перенос в шортсы: skills/gor-voice/references/slog-twitter.md. В промпт сценария идут через rubrics.VOICE.
⛔ Архив в репо не кладётся: в нём личка, IP-аудит, контакты. Корпус выгружается только в work/ (в .gitignore).

Что считается голосом Гора, а что нет:
  - ретвиты, автопостинг приложений (цитатники «... [url] @ник», «I've just», «Я снял это с помощью», #nowplaying), цитаты в кавычках,
    голые ссылки и чистый английский = НЕ голос, выкидываются;
  - собственные твиты и ответы = голос, считаются раздельно (ответ ближе к разговорной речи, твит к реплике со сцены).

  python twitter_slog.py АРХИВ.zip|ПАПКА               отчёт по эпохам
  python twitter_slog.py АРХИВ.zip --dump               + корпус в work/twitter_slog/ (голос, ответы, железячный подкорпус)
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
import zipfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rubrics as RB  # noqa: E402  мат и ритм меряются тем же, чем линтер шортсов

HERE = Path(__file__).resolve().parent
OUT = HERE / "work" / "twitter_slog"

APP = re.compile(r"\.\.\. \S*t\.co/\S+ @\w+$|^I've just|^I am listening|^Awesome! I've|^Just applied|^Styled my profile|^I flew \d|"
                 r"^Я снял это с помощью|^Я нажал\(а\)|SwiftKey|#nowpla|Мои политические координаты|^I'm at |via @\w+$|через @\w+$|с помощью$|^Мой результат на это", re.I)
QUOTE = re.compile(r'^\s*["«“]')
LATIN_W = re.compile(r"\b[a-z]{3,}\b", re.I)
CYR = re.compile(r"[а-яё]", re.I)
HW = re.compile(r"видеокарт|процессор|ноут|ультрабук|айпа[дт]|ipad|iphone|айфон|андро[йи]д|android|xperia|ксперии|htc|samsung|sgs|"
                r"батаре|зарядк|прошивк|роутер|вайфай|wi-?fi|блютуз|rgb|подсветк|мак ?прошк|macbook|алиенвар|alienware|\bбп\b|"
                r"\bсц\b|сервис|гаджет|девайс|приставк|консол|винд|windows|т9|автозаполнен|вирусн|антивирус|апп ?стор|appstore|"
                r"\bfps\b|геймпле|графон|драйвер|монитор|клавиатур|мышк|наушник|уши с", re.I)
SENT = re.compile(r"(?<=[.!?…])\s+|\s+/\s+|\n+")
WORD = re.compile(r"[\w\-]+", re.U)


def load(src: Path) -> list[dict]:
    if src.is_dir():
        raw = (src / "data" / "tweets.js").read_text(encoding="utf-8")
    else:
        with zipfile.ZipFile(src) as z:
            raw = z.read("data/tweets.js").decode("utf-8")
    rows = []
    for d in json.loads(raw[raw.index("["):]):
        t = d["tweet"]
        rows.append({"date": datetime.strptime(t["created_at"], "%a %b %d %H:%M:%S %z %Y").date().isoformat(),
                     "text": t["full_text"], "lang": t.get("lang"), "fav": int(t["favorite_count"]),
                     "reply": bool(t.get("in_reply_to_status_id_str"))})
    return rows


def clean(t: str) -> str:
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"^(?:@\w+\s*)+", "", t)          # адресаты ответа
    t = re.sub(r"@\w+", "", t)
    return re.sub(r"[ \t]+", " ", t).strip()


def own_voice(r: dict) -> str | None:
    t = r["text"]
    if t.startswith("RT @") or APP.search(t) or QUOTE.match(clean(t)):
        return None
    c = clean(t)
    if APP.search(c) or len(WORD.findall(c)) < 2 or not CYR.search(c):
        return None
    return c


def sents(t: str) -> list[list[str]]:
    out = []
    for s in SENT.split(t):
        w = WORD.findall(s)
        if w: out.append(w)
    return out


def pct(a: int, b: int) -> str:
    return f"{a / b:.0%}" if b else "-"


def q(xs: list[int], p: float) -> int:
    xs = sorted(xs); return xs[min(len(xs) - 1, int(p * len(xs)))] if xs else 0


def report(name: str, tw: list[str]) -> dict:
    n = len(tw)
    wpt = [len(WORD.findall(t)) for t in tw]
    ss = [s for t in tw for s in sents(t)]; wps = [len(s) for s in ss]
    multi = [sents(t) for t in tw if len(sents(t)) >= 2]
    deflate = sum(1 for m in multi if len(m[-1]) < len(m[-2]))
    m = {
        "твитов": n,
        "слов в твите медиана / p75 / p90": f"{st.median(wpt):.0f} / {q(wpt, .75)} / {q(wpt, .9)}",
        "слов в предложении медиана / p90": f"{st.median(wps):.0f} / {q(wps, .9)}" if wps else "-",
        "предложений до 4 слов (удар)": pct(sum(x <= 4 for x in wps), len(wps)),
        "предложений от 15 слов (движение)": pct(sum(x >= 15 for x in wps), len(wps)),
        "многофразных твитов": pct(len(multi), n),
        "  из них последняя фраза короче предпоследней": pct(deflate, len(multi)),
        "с маленькой буквы": pct(sum(t[:1].islower() for t in tw), n),
        "без точки в конце": pct(sum(not re.search(r"[.!?…)]$", t) for t in tw), n),
        "мат": pct(sum(bool(RB.MAT.search(t)) for t in tw), n),
        "рамка «Слово: ...» в начале": pct(sum(bool(re.match(r"^[А-ЯЁA-Z][\w\- ]{2,30}: ", t)) for t in tw), n),
        "тире-определение «X - Y»": pct(sum(bool(re.search(r"\S\s[-\u2013\u2014]\s\S", t)) for t in tw), n),
        "сравнение «как/словно/будто»": pct(sum(bool(re.search(r"\b(?:как будто|словно|будто|как)\b", t, re.I)) for t in tw), n),
        "перечень от 3 пунктов через запятую": pct(sum(bool(re.search(r"(?:[^,.!?]{2,30},){2,}[^,.!?]{2,30}", t)) for t in tw), n),
        "вопрос": pct(sum("?" in t for t in tw), n),
        "открывает «Когда»": pct(sum(bool(re.match(r"когда\b", t, re.I)) for t in tw), n),
        "обобщённое «ты»": pct(sum(bool(re.search(r"\b(?:ты|тебе|тебя|твой|твоя|твоё)\b", t, re.I)) for t in tw), n),
        "смайл-скобки / ахаха / лол": pct(sum(bool(re.search(r"\)\)|ах[ах]{2,}|\bлол\b|хаха", t, re.I)) for t in tw), n),
        "английское слово внутри русского": pct(sum(bool(LATIN_W.search(t)) for t in tw), n),
        "железо и гаджеты": pct(sum(bool(HW.search(t)) for t in tw), n),
    }
    print(f"\n== {name}")
    for k, v in m.items(): print(f"  {k:48} {v}")
    return m


def main() -> int:
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help"):
        print(__doc__); return 2
    rows = load(Path(a[0]))
    print(f"архив: {len(rows)} записей, ретвитов {sum(r['text'].startswith('RT @') for r in rows)}")
    voice = [(r, own_voice(r)) for r in rows]; voice = [(r, c) for r, c in voice if c]
    eras = {"2010-2015 (ранний)": lambda d: d < "2016", "2018-2026 (поздний)": lambda d: d >= "2016"}
    for en, f in eras.items():
        report(f"{en}, твиты", [c for r, c in voice if f(r["date"]) and not r["reply"]])
        report(f"{en}, ответы", [c for r, c in voice if f(r["date"]) and r["reply"]])
    report("всё, твиты и ответы", [c for _, c in voice])
    if "--dump" in a:
        OUT.mkdir(parents=True, exist_ok=True)
        for fn, sel in [("voice.txt", lambda r, c: not r["reply"]), ("replies.txt", lambda r, c: r["reply"]),
                        ("hardware.txt", lambda r, c: bool(HW.search(c)))]:
            lines = [f"{r['date']} [{r['fav']}] {c.replace(chr(10), ' / ')}" for r, c in voice if sel(r, c)]
            (OUT / fn).write_text("\n".join(lines) + "\n", encoding="utf-8"); print(f"выгружено {len(lines):5} -> {OUT / fn}")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32": sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
