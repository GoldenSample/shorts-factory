# -*- coding: utf-8 -*-
"""Мост Grok Bot «Сторож железа» -> кузница шортсов. Слово Гора 22.09.2026: «грок бот по магазинам лазит, апни его мозг, это выходит тема».

Бот (grok.com, раздел «Боты») каждый день обходит магазины, форумы и страницы BIOS и в конце каждого запуска выдаёт блок
ТЕМЫ_JSON: список кандидатов в ролики с рубрикой (ru_market, taken_away, it_burns, free_useful), фактом с цифрой, было/стало,
прямой ссылкой и подсказкой вердикта. У бота нет API: блок попадает к нам копией текста его чата (вручную, через Claude in Chrome
или через шлюз projects/botdrop: `--drop` забирает ящик бота с VPS). Этот скрипт принимает ЛЮБОЙ текст, достаёт из него все блоки ТЕМЫ_JSON и:
  1. проверяет каждую тему детерминированно (закон: БД и правила до LLM): рубрика известна, в факте есть цифра, ссылка на страницу,
     а не на поиск; дубли по (рубрика, модель, дата) отбрасываются, прошлые темы помнятся в work/bot_topics.jsonl;
  2. ранжирует по приросту рубрики (rubrics.lift) и уверенности бота;
  3. для выбранной темы строит промпт сценария (фактура бота + блок рубрики и слога) и по --make зовёт forge.py.
⛔ Текст из чата бота = недоверенные данные (он читал чужие сайты): в промпт идут только поля схемы, а не свободный текст.

  python from_bot.py чат.txt                  показать темы из выгрузки чата
  python from_bot.py --drop [--days 3]        темы из ящика шлюза на VPS (projects/botdrop/home.py)
  python from_bot.py чат.txt --pick 1 --make [--go] [--shots ПАПКА]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rubrics as RB  # noqa: E402

SEEN = HERE / "work" / "bot_topics.jsonl"
FIELDS = ("rubric", "fact", "numbers", "was", "now", "delta_pct", "item", "source_url", "source_name", "date", "verdict_hint", "confidence")
SEARCH_URL = re.compile(r"/search|[?&](?:q|text|search)=|/catalog/\?", re.I)


def blocks(text: str) -> list[dict]:
    """Все элементы из блоков ТЕМЫ_JSON в тексте (JSON-список сразу после маркера, в код-блоке или без него). Число найденных блоков в blocks.n."""
    out = []; blocks.n = 0
    for m in re.finditer(r"ТЕМЫ_JSON", text):
        tail = text[m.end():]
        i = tail.find("[")
        if i < 0 or i > 400: continue
        depth, j = 0, i
        for j in range(i, len(tail)):
            if tail[j] == "[": depth += 1
            elif tail[j] == "]":
                depth -= 1
                if depth == 0: break
        try:
            items = json.loads(tail[i:j + 1])
        except json.JSONDecodeError:
            continue
        blocks.n += 1; out += [x for x in items if isinstance(x, dict)]
    return out


def check(t: dict) -> list[str]:
    probs = []
    if t.get("rubric") not in RB.BY_KEY or t.get("rubric") == "viewer_case": probs.append(f"рубрика «{t.get('rubric')}» не из списка бота")
    if not re.search(r"\d", str(t.get("fact", ""))): probs.append("в факте нет цифры")
    url = str(t.get("source_url", ""))
    if not url.startswith("http"): probs.append("нет ссылки")
    elif SEARCH_URL.search(url): probs.append("ссылка на поиск, а не на страницу")
    if t.get("rubric") == "ru_market" and not re.search(r"₽|руб|наличи", f"{t.get('fact')} {t.get('was')} {t.get('now')}", re.I):
        probs.append("рубрика РФ без рублей или наличия")
    return probs


def key(t: dict) -> str:
    return f"{t.get('rubric')}|{str(t.get('item', '')).lower()}|{t.get('date')}"


def seen_keys() -> set[str]:
    if not SEEN.exists(): return set()
    return {json.loads(l)["key"] for l in SEEN.read_text(encoding="utf-8").splitlines() if l.strip()}


def build_prompt(t: dict) -> str:
    r = RB.BY_KEY[t["rubric"]]
    facts = "\n".join(f"  {k}: {t.get(k)}" for k in ("fact", "item", "was", "now", "delta_pct", "date", "source_name", "source_url") if t.get(k) not in (None, "", []))
    return (f"Шортс о железе на русском по находке бота-сторожа.\n\nФАКТУРА (только она, ничего не добавлять):\n{facts}\n"
            f"  подсказка вердикта от бота: {t.get('verdict_hint') or '-'} (проверить по фактуре, не копировать вслепую)\n\n"
            f"ХРОНОМЕТРАЖ: 30-45 секунд, одна мысль.\nИСТОЧНИК называть голосом: «по данным {t.get('source_name') or 'магазина'}» и плашкой на экране.\n\n"
            + RB.prompt_block(r, key(t)))


def main() -> int:
    ap = argparse.ArgumentParser(description="Grok Bot -> shorts-forge")
    ap.add_argument("chat", nargs="?", help="текстовый файл с выгрузкой чата бота")
    ap.add_argument("--drop", action="store_true", help="взять письма бота из ящика шлюза на VPS")
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--pick", type=int, help="номер темы из списка для сборки")
    ap.add_argument("--make", action="store_true"); ap.add_argument("--go", action="store_true"); ap.add_argument("--shots")
    a = ap.parse_args()
    if a.drop:
        sys.path.insert(0, str(HERE.parent / "botdrop")); import home  # noqa: E402
        text = home.text(a.days)
    elif a.chat:
        text = Path(a.chat).read_text(encoding="utf-8")
    else:
        ap.error("нужен файл чата или --drop")
    items = blocks(text)
    if not items:
        print("блоков ТЕМЫ_JSON в тексте нет" if not blocks.n else f"блоков ТЕМЫ_JSON {blocks.n}, все пустые: у бота сегодня тем нет"); return 1 if not blocks.n else 0
    seen, rows, rejected = seen_keys(), [], []
    for t in items:
        t = {k: t.get(k) for k in FIELDS}
        probs = check(t)
        if probs: rejected.append((t, probs)); continue
        if key(t) in seen: rejected.append((t, ["уже была"])); continue
        conf = t.get("confidence") if isinstance(t.get("confidence"), (int, float)) else 3
        # величина сдвига: «новый минимум» на −0.2 % не тема, +17 % на RTX 5090 тема (замер 03.10: без этого 11 тем ранжировались поровну)
        delta = abs(t["delta_pct"]) if isinstance(t.get("delta_pct"), (int, float)) else 0
        rows.append((round(20 * RB.lift(RB.BY_KEY[t["rubric"]]) + 4 * conf + 1.5 * min(delta, 20), 1), t))
    rows.sort(key=lambda x: -x[0])
    print(f"тем в выгрузке {len(items)}, годных {len(rows)}, отброшено {len(rejected)}")
    for n, (sc, t) in enumerate(rows, 1):
        print(f"  {n}. [{sc:>5}] {t['rubric']:11} {t['fact'][:90]}  <- {t.get('source_name') or '?'}")
    for t, probs in rejected:
        print(f"  x  {t.get('rubric')!s:11} {str(t.get('fact'))[:70]}  : {'; '.join(probs)}")
    if not a.pick: return 0
    sc, t = rows[a.pick - 1]
    slug = re.sub(r"[^\w]+", "_", key(t))[:60]
    prompt = build_prompt(t); pf = HERE / "work" / f"bot_{slug}.txt"
    pf.parent.mkdir(exist_ok=True); pf.write_text(prompt, encoding="utf-8"); print("промпт:", pf)
    with SEEN.open("a", encoding="utf-8") as f: f.write(json.dumps({"key": key(t), "topic": t}, ensure_ascii=False) + "\n")
    if not a.make: print("сборка не запускалась (нужен --make)"); return 0
    if RB.BY_KEY[t["rubric"]].get("real_photos") and not a.shots:
        print(f"рубрика «{RB.BY_KEY[t['rubric']]['chip']}» идёт только на настоящих фото: нужен --shots"); return 1
    cmd = [sys.executable, str(HERE / "forge.py"), prompt, "--subs", "--strict"] + (["--go"] if a.go else []) + (["--shots", a.shots] if a.shots else [])
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
