# -*- coding: utf-8 -*-
"""Мост TechPulse -> кузница шортсов.

Выбор темы делает ДЕТЕРМИНИРОВАННЫЙ запрос к базе (закон контура: БД до LLM),
а Grok уже пишет сценарий по выбранному.

Отбор построен на ЗАМЕРЕ по нашей базе 27.07 (4638 новостей, окно 17 суток), а не на догадках:
  - узкое место = ДЕТЕКТ (медиана лага источника 7.8 ч), сборка ролика = 32 секунды;
  - полураспад волны 10-12 ч, ждать подтверждения кластером = опоздать (до размера 3 медиана 24.2 ч);
  - relevance_score НЕ предсказывает размер сюжета (2.9% при >=70 против 1.5% при <30 - шум);
  - blogger_relevance_score и метрики Reddit в базе МЕРТВЫ (заполнены у 1 записи из 4638);
  - зато РАБОТАЕТ априор источника: PC Watch 13.0% волн против базовой ставки 1.6%.

Поэтому скор стоит на априорах, а не на подтверждении:
    S = 40*P_src + 25*F + 20*C + 15*B

Подробности и схемы подачи: skills/techpulse-shorts/SKILL.md
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rubrics as RB  # noqa: E402  рубрики и слог (разбор Dyamorph 22.09.2026)
DB = Path(r"C:\CLAUD\services\techpulse\data\news.db")

# Гейт плотности фактов: новость с одним числом физически не наполняет 60 секунд
# ничем, кроме воды. Замер: 12.4% записей вообще без чисел, ещё 15.2% - ровно одно.
DENSITY = ((4, 60), (2, 45), (1, 30))  # (минимум чисел, потолок секунд)

# Маршрут event-ядра в схему подачи. Первое совпадение сверху вниз.
ROUTE = [
    ("leak",                      "V-02 Утечка -> проверка источника -> вердикт"),
    ("price_down|price_up|deal",  "V-03 Было -> стало -> что делать"),
    ("benchmark",                 "V-04 Цифра в лоб -> распаковка -> масштаб"),
    ("failure|security",          "V-08 Ломается -> причина -> как не попасть"),
    ("shortage",                  "V-10 Дедлайн -> что успеть -> что после"),
    ("lawsuit|delay|mna",         "V-09 Шаг 1 -> шаг 2 -> куда ведёт"),
    ("update|overclock|refresh",  "V-12 Тихая новость -> почему важно -> следствие"),
    ("announce",                  "V-06 Обещание -> мелкий шрифт -> цена вопроса"),
    ("launch",                    "V-07 A против B -> по сценариям -> кому что"),
]
FALLBACK = "V-01 Факт -> последствие -> совет"

NUM_RE = re.compile(r"\d")
WORD_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(v) -> datetime | None:
    if not v:
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, timezone.utc)
    s = str(v).strip().replace("Z", "+00:00")
    for cut in (s, s[:19]):
        try:
            d = datetime.fromisoformat(cut)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def source_priors(con: sqlite3.Connection) -> tuple[dict[int, float], float]:
    """Доля новостей источника, доросших до сюжета >=3 материалов.

    Это единственный сигнал триажа, который в замере реально предсказывает волну
    (в 4-8 раз выше базовой ставки у азиатских первопубликаторов).
    """
    rows = con.execute("""
        SELECT n.source_id,
               COUNT(*)                                        AS n,
               SUM(CASE WHEN s.size >= 3 THEN 1 ELSE 0 END)    AS waves
          FROM news n
          LEFT JOIN stories s ON s.id = n.story_id
         WHERE n.duplicate_of IS NULL AND n.source_id IS NOT NULL
      GROUP BY n.source_id
    """).fetchall()
    tot_n = sum(r[1] for r in rows) or 1
    tot_w = sum(r[2] or 0 for r in rows)
    base = tot_w / tot_n
    # сглаживание к базовой ставке: источник с 3 новостями не имеет права на 33%
    K = 25.0
    priors = {r[0]: ((r[2] or 0) + K * base) / (r[1] + K) for r in rows}
    return priors, base


def cores_of(con: sqlite3.Connection, news_id: int) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for axis, core in con.execute(
        "SELECT axis, core FROM news_cores WHERE news_id=?", (news_id,)
    ):
        out.setdefault(axis, []).append(core)
    return out


def pick_schema(events: list[str]) -> str:
    joined = " ".join(events)
    for pattern, schema in ROUTE:
        if any(re.fullmatch(pattern, e) for e in events) or re.search(pattern, joined):
            return schema
    return FALLBACK


def numbers_in(*chunks: str) -> list[str]:
    text = " ".join(c for c in chunks if c)
    return WORD_NUM_RE.findall(text)


def budget_seconds(n_numbers: int) -> int | None:
    for need, sec in DENSITY:
        if n_numbers >= need:
            return sec
    return None  # ролик не делаем


def candidates(con: sqlite3.Connection, hours: int, limit: int) -> list[dict]:
    priors, base = source_priors(con)
    prior_max = max(priors.values()) if priors else base or 1.0
    since = (utcnow() - timedelta(hours=hours)).isoformat()

    rows = con.execute("""
        SELECT n.id, n.source_id, n.title, n.translated_title,
               n.description, n.translated_description,
               n.published_at, n.fetched_at, n.link, n.story_id,
               COALESCE(s.size, 1) AS story_size,
               r.name AS source_name
          FROM news n
          LEFT JOIN stories s     ON s.id = n.story_id
          LEFT JOIN rss_sources r ON r.id = n.source_id
         WHERE n.duplicate_of IS NULL
           AND COALESCE(n.fetched_at, '') >= ?
           AND COALESCE(n.relevance_score, 0) >= 6
      ORDER BY n.fetched_at DESC
         LIMIT 4000
    """, (since,)).fetchall()

    now = utcnow()
    out = []
    for r in rows:
        (nid, src, title, ttitle, desc, tdesc, pub, fetched,
         link, story_id, story_size, source_name) = r

        title_ru = ttitle or title or ""
        desc_ru = tdesc or desc or ""
        if not title_ru or "\ufffd" in title_ru:      # исторические битые кодировки
            continue
        # Непереведённый CJK-заголовок = китайский спам про быт (замер 22.09: вышел первым по скору, холодильники).
        if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", title_ru):   # CJK
            continue

        pub_dt, fetch_dt = parse_ts(pub), parse_ts(fetched)
        lag_h = ((fetch_dt - pub_dt).total_seconds() / 3600) if (pub_dt and fetch_dt) else None
        age_h = ((now - pub_dt).total_seconds() / 3600) if pub_dt else None

        # Отрицательный лаг = published_at в будущем относительно fetched_at (кривые
        # таймзоны у части источников). Такому времени нельзя верить, и давать за него
        # бонус свежести вслепую нельзя - обнуляем сигнал, а не награждаем.
        if lag_h is not None and lag_h < 0:
            lag_h = None

        # ЖЁСТКИЙ ОТСЕКАТЕЛЬ: лаг детекта > 12 ч -> новостной формат запрещён
        # независимо от скора. Срезает ~35% потока, и правильно срезает.
        if lag_h is not None and lag_h > 12:
            continue

        nums = numbers_in(title_ru, desc_ru[:600])
        sec = budget_seconds(len(nums))
        if sec is None:                                # гейт плотности фактов
            continue

        cores = cores_of(con, nid)
        # ЖЕЛЕЗНАЯ ТЕМА, А НЕ ОБЗОР БЫТА. Замер вскрыл, что топ по сюжетам занимает
        # китайский спам про бытовую технику: сюжеты размера 6, склеенные по мусорным
        # ключевикам (та же болезнь дала brand='ekwb' из подстроки "ek").
        # Дискриминатор: у настоящей железной новости есть конкретный бренд или модель,
        # а не только широкий topic.
        if not (cores.get("brand") or cores.get("model")):
            continue

        F = 1.0 if (lag_h is not None and lag_h < 2) else \
            0.6 if (lag_h is not None and lag_h < 6) else \
            0.3 if (lag_h is not None and lag_h < 12) else 0.0
        C = 0.0 if story_size < 2 else (0.5 if story_size == 2 else 1.0)
        P = (priors.get(src, base) / prior_max) if prior_max else 0.0
        B = 0.0   # burst z-score живёт в сервисе, а не в этой таблице; см. ХВОСТ ниже

        S = 40 * P + 25 * F + 20 * C + 15 * B
        # РУБРИКА: углы, которые у Dyamorph держались выше ленты (РФ +69 %, бесплатно +48 %, отнимают +25 %, горит +15 %).
        # Вес умеренный (малая выборка): рубрика поднимает тему в очереди, но не перекрывает свежесть и априор источника.
        rubs = RB.detect(title_ru, desc_ru, cores.get("event", []))
        S += 20 * RB.lift(rubs[0] if rubs else None)
        if age_h is not None:
            S -= min(20.0, 1.2 * max(0.0, age_h - 12) / 6)   # мягкое затухание волны

        out.append({
            "news_id": nid, "score": round(S, 1),
            "title": title_ru, "desc": desc_ru,
            "source": source_name or f"#{src}", "link": link,
            "lag_h": round(lag_h, 1) if lag_h is not None else None,
            "age_h": round(age_h, 1) if age_h is not None else None,
            "story_id": story_id, "story_size": story_size,
            "numbers": len(nums), "seconds": sec,
            "cores": cores,
            "schema": pick_schema(cores.get("event", [])),
            "rubric": rubs[0]["key"] if rubs else None,
        })

    out.sort(key=lambda d: -d["score"])
    return out[:limit]


def build_prompt(c: dict) -> str:
    """Промпт с фактурой из базы и жёсткими запретами.

    Запреты не пожелание: слот 'мнение людей' в базе ПУСТ (реакции Reddit не собираются),
    и без явного запрета генератор заполнит его выдумкой - это самый вероятный
    источник фактического вранья в конвейере.
    """
    brands = ", ".join(c["cores"].get("brand", [])[:4]) or "-"
    models = ", ".join(c["cores"].get("model", [])[:4]) or "-"
    events = ", ".join(c["cores"].get("event", [])) or "-"
    words = {30: "33-36", 45: "61-67", 60: "92-98"}[c["seconds"]]

    return f"""Новостной шортс на русском. Схема подачи: {c['schema']}

ФАКТУРА (использовать только её):
  заголовок: {c['title']}
  описание: {c['desc'][:700]}
  источник: {c['source']}
  ядра: событие={events} | бренд={brands} | модель={models}
  свежесть: {c['age_h']} ч с публикации

ХРОНОМЕТРАЖ: {c['seconds']} сек, заполнять на 90%. Бюджет начитки {words} слов.
Каждое лишнее предложение отнимает 2.7 слова бюджета (пауза 1.3 с).
Числа при подсчёте раскрывать в слоги: "1999" = 11 слогов, "RTX" = 3 слога.

ЗАПРЕЩЕНО:
  - любые формулировки про реакцию людей, комментарии, сообщество, форумы, Reddit -
    данных о реакциях НЕТ, это будет выдумка;
  - числа, которых нет в фактуре. Нет второго числа для сравнения - схема "было/стало"
    недоступна, взять другую;
  - латиница в тексте озвучки: RTX 5090 -> "эр-ти-икс пятьдесят девяносто", TDP -> "теплопакет";
  - концовки "время покажет", "посмотрим", "решать вам", "а что думаете вы".

ОРИГИНАЛЬНЫЙ ВКЛАД обязателен, 25-40% хронометража, ПОСЛЕ фактической части.
Один из: вердикт достоверности по шкале / пересчёт в бытовую единицу (ватты в рубли за год) /
кому НЕ надо / прогноз с датой и условием ошибки / личный порог / названная неопределённость.
Открывать явным маркером мнения ("моя ставка", "я бы"). Признак вклада: в нём можно
оказаться неправым.

ИСТОЧНИК называть голосом в момент факта: "по данным {c['source']}".

{RB.prompt_block(RB.BY_KEY.get(c.get('rubric') or ''), c['news_id'])}"""


def main() -> int:
    ap = argparse.ArgumentParser(description="TechPulse -> shorts-forge")
    ap.add_argument("--news-id", type=int, help="взять конкретную новость")
    ap.add_argument("--hours", type=int, default=48, help="окно поиска, часов")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--make", action="store_true", help="собрать ролик (иначе только показать)")
    ap.add_argument("--go", action="store_true", help="передать --go в forge.py (жжёт пул)")
    ap.add_argument("--shots", help="папка реальных кадров для Ken Burns")
    args = ap.parse_args()

    if not DB.exists():
        print(f"нет базы: {DB}", file=sys.stderr)
        return 2

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        cands = candidates(con, args.hours, max(args.limit, 60) if args.news_id else args.limit)
        if args.news_id:
            cands = [c for c in cands if c["news_id"] == args.news_id]
            if not cands:
                print(f"news_id={args.news_id} не прошёл гейты или вне окна "
                      f"(лаг >12ч / нет чисел / дубль). Расширь --hours.", file=sys.stderr)
                return 1
    finally:
        con.close()

    if not cands:
        print("кандидатов нет: за окно ничего не прошло гейт свежести и плотности фактов")
        return 1

    print(f"{'скор':>6} {'id':>7} {'лаг':>6} {'сюж':>4} {'чис':>4} {'сек':>4}  {'рубрика':12} схема / тема")
    print("-" * 100)
    for c in cands:
        lag = f"{c['lag_h']}ч" if c["lag_h"] is not None else "?"
        print(f"{c['score']:>6} {c['news_id']:>7} {lag:>6} {c['story_size']:>4} "
              f"{c['numbers']:>4} {c['seconds']:>4}  {(c.get('rubric') or '-'):12} {c['schema'][:22]:22} {c['title'][:52]}")

    best = cands[0]
    prompt = build_prompt(best)
    plan = HERE / "work" / f"tp_{best['news_id']}.txt"
    plan.parent.mkdir(exist_ok=True)
    plan.write_text(prompt, encoding="utf-8")
    print(f"\nпромпт: {plan}")

    if not args.make:
        print("сборка не запускалась (нужен --make)")
        return 0
    rb = RB.BY_KEY.get(best.get("rubric") or "")
    if rb and rb.get("real_photos") and not args.shots:
        print(f"рубрика «{rb['chip']}» идёт только на НАСТОЯЩИХ фото: передай --shots ПАПКА. Генерировать железо запрещено.")
        return 1

    cmd = [sys.executable, str(HERE / "forge.py"), prompt, "--subs"]
    if args.go:
        cmd.append("--go")
    if args.shots:
        cmd += ["--shots", args.shots]
    print(f"\n-> forge.py (id={best['news_id']}, {best['seconds']}с, {best['schema']})")
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
