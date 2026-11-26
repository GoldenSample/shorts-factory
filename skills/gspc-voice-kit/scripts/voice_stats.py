# -*- coding: utf-8 -*-
"""Счёт сигналов голоса по выборке ТГ-канала (выход gspc-post-scorer/scripts/tg_views.py).

Только stdlib, сеть не трогает. Делит посты на «руку Гора» (id списком) и «завод» (остальные)
и считает то, что voice.md пишет цифрами: длина фразы, удары до 4 слов, длинные от 15 слов,
«ты»/«вы», эмодзи, хэштеги, ссылки, длинные тире, маркеры списка, длина первой строки и поста.

    py -3 voice_stats.py samples/tg-2026-10-14.json --hand 670,679,682,683,688,689
    py -3 voice_stats.py a.json b.json --hand 683 --skip 710

Несколько файлов склеиваются, дубли по id отбрасываются. Пустые посты (только медиа) не считаются.
"""
import argparse
import json
import re
import statistics
import sys

SENT = re.compile(r"(?<=[.!?…])\s+")
TY = re.compile(r"(?<![а-яё])(?:ты|тебя|тебе|тобой|твой|твоя|твоё|твои|твою|твоего|твоей|твоих|"
                r"напиши|пиши|смотри|бери|ставь|проверь|глянь|держи|хочешь|теряешь|платишь|видишь)(?![а-яё])")
VY = re.compile(r"(?<![а-яё])(?:вы|вас|вам|вами|ваш|ваша|ваше|ваши|вашу|вашего|вашей|ваших|"
                r"напишите|пишите|смотрите|берите|ставьте|проверьте|подпишитесь|подписывайтесь|хотите|видите)(?![а-яё])")
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⬆↔-↪]")
LINK = re.compile(r"https?://|(?<![\w@])(?:t\.me|youtu\.be|youtube\.com|dzen\.ru|vk\.com|gspc-lab\.pro)/", re.I)


def load(paths):
    seen = {}
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for post in json.load(f).get("posts", []):
                if (post.get("text") or "").strip():
                    seen[post["id"]] = post
    return [seen[k] for k in sorted(seen)]


def stats(posts):
    lens, chars, first = [], [], []
    c = dict(ty=0, vy=0, emoji=0, hashtags=0, links=0, dash=0, list_marks=0)
    for p in posts:
        t = p["text"].strip()
        chars.append(len(t))
        first.append(len(t.split("\n")[0]))
        for line in t.split("\n"):
            for s in SENT.split(line.strip()):
                w = len(s.split())
                if w:
                    lens.append(w)
        low = t.lower()
        c["ty"] += len(TY.findall(low))
        c["vy"] += len(VY.findall(low))
        c["emoji"] += len(EMOJI.findall(t.replace("▪", "")))
        c["hashtags"] += len(re.findall(r"(?<!\w)#[\wа-яё]", t, re.I))
        c["links"] += len(LINK.findall(t))
        c["dash"] += t.count("—")
        c["list_marks"] += t.count("▪") + len(re.findall(r"^\s*(?:[-•]|\d+[.)])\s", t, re.M))
    n = len(lens) or 1
    return {
        "posts": len(posts),
        "sentences": len(lens),
        "words_per_sentence": round(sum(lens) / n, 1),
        "punch_le4_pct": round(100 * sum(x <= 4 for x in lens) / n),
        "long_ge15_pct": round(100 * sum(x >= 15 for x in lens) / n),
        "chars_median": int(statistics.median(chars)) if chars else 0,
        "chars_min_max": [min(chars), max(chars)] if chars else [0, 0],
        "first_line_median": int(statistics.median(first)) if first else 0,
        **c,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json", nargs="+", help="выход tg_views.py")
    ap.add_argument("--hand", default="", help="id постов руки Гора через запятую")
    ap.add_argument("--skip", default="", help="id служебных постов (закреп, репост) через запятую")
    a = ap.parse_args()
    hand = {int(x) for x in a.hand.split(",") if x.strip()}
    skip = {int(x) for x in a.skip.split(",") if x.strip()}
    posts = [p for p in load(a.json) if p["id"] not in skip]
    groups = {"рука Гора": [p for p in posts if p["id"] in hand],
              "завод": [p for p in posts if p["id"] not in hand]}
    out = {k: stats(v) for k, v in groups.items() if v}
    out["диапазон id"] = [posts[0]["id"], posts[-1]["id"]] if posts else []
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
