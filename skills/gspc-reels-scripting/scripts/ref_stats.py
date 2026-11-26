# -*- coding: utf-8 -*-
"""Счёт по чужому референсу для gspc-reels-scripting: хук, темп речи, длина фраз, обращение, склейки.

Вход — папка, которую собрал ref_pull.sh (забрать с хаба asr.json, cuts.txt, meta.json):
    py -3.12 ref_stats.py <папка> [--hook 3.0] [--ours <наш final.json>]
Пишет <папка>/stats.md и печатает его. Только stdlib, работает и на хабе (python3).
С --ours ищет в нашем сценарии цепочки от 5 слов подряд из речи референса: код 3 = заимствование, переписать.

Понимает обе схемы слуха: segs ({"segs":[{"s","e","t","w":[[s,e,слово,p],...]}]}, как zakadr_final.json и запасной
слух хаба) и список слов моста рига ([{"w","s","e","p"}] или {"words":[...]}).
Цифры здесь — счёт, не оценка: что из них взять в наш сценарий, решает разбор (SKILL.md, шаг 4).
"""
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PRON = {
    "ты": r"\b(ты|тебе|тебя|тобой|твой|твоя|твоё|твое|твои|твоих|твоим|you|your|yours)\b",
    "вы": r"\b(вы|вам|вас|вами|ваш|ваша|ваше|ваши|ваших)\b",
    "я": r"\b(я|мне|меня|мной|мой|моя|моё|мое|мои|i|me|my|mine)\b",
    "мы": r"\b(мы|нам|нас|нами|наш|наша|наше|наши|наших|we|us|our|ours)\b",
}
SOFT = r"\b(просто|всего|лишь|just|simply|only)\b"
END = re.compile(r"[.!?…]+[»\"')]*$")


def load_words(path):
    d = json.load(io.open(path, encoding="utf-8"))
    out = []
    if isinstance(d, dict) and "segs" in d:
        for s in d["segs"]:
            ws = s.get("w") or []
            if ws:
                for w in ws:
                    out.append((float(w[0]), float(w[1]), str(w[2]).strip()))
            elif s.get("t"):
                out.append((float(s["s"]), float(s["e"]), s["t"].strip()))
        return out, d.get("dur")
    words = d["words"] if isinstance(d, dict) and "words" in d else d
    for w in words:
        out.append((float(w["s"]), float(w["e"]), str(w["w"]).strip()))
    return out, None


def sentences(words):
    sent, cur = [], []
    for w in words:
        cur.append(w)
        if END.search(w[2]):
            sent.append(cur)
            cur = []
    if cur:
        sent.append(cur)
    return sent


def fmt(t):
    return "%d:%04.1f" % (int(t // 60), t % 60)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    d = sys.argv[1]
    hook_s = float(sys.argv[sys.argv.index("--hook") + 1]) if "--hook" in sys.argv else 3.0
    words, dur = load_words(os.path.join(d, "asr.json"))
    meta = {}
    if os.path.exists(os.path.join(d, "meta.json")):
        meta = json.load(io.open(os.path.join(d, "meta.json"), encoding="utf-8"))
    dur = float(meta.get("duration") or dur or (words[-1][1] if words else 0))
    cuts = []
    if os.path.exists(os.path.join(d, "cuts.txt")):
        cuts = [float(x) for x in io.open(os.path.join(d, "cuts.txt"), encoding="utf-8").read().split() if x.strip()]
    if not words:
        print("в asr.json нет слов: ролик без речи или слух не сработал")
        return 1

    text = " ".join(w[2] for w in words)
    low = text.lower()
    sent = sentences(words)
    nwords = len(words)
    speech = sum(w[1] - w[0] for w in words)
    first = words[0][0]
    hook_words = [w for w in words if w[0] < hook_s]
    s1 = sent[0]
    pauses = [(words[i][1], words[i + 1][0] - words[i][1]) for i in range(len(words) - 1)
              if words[i + 1][0] - words[i][1] >= 0.6]
    shots = len(cuts) + 1

    L = []
    L.append("# Счёт референса: %s" % (meta.get("title") or os.path.basename(os.path.abspath(d))))
    if meta.get("webpage_url"):
        L.append("")
        L.append("- ссылка: %s" % meta["webpage_url"])
    for k, name in (("uploader", "автор"), ("upload_date", "дата"), ("view_count", "просмотры"),
                    ("like_count", "лайки"), ("comment_count", "комментарии (число)")):
        if meta.get(k) is not None:
            L.append("- %s: %s" % (name, meta[k]))
    L.append("")
    L.append("## Хук")
    L.append("- первое слово на %.2f с" % first)
    L.append("- первые %.0f с: %d слов — «%s»" % (hook_s, len(hook_words), " ".join(w[2] for w in hook_words)))
    L.append("- первая фраза: %d слов, кончается на %.1f с — «%s»" % (len(s1), s1[-1][1], " ".join(w[2] for w in s1)))
    L.append("")
    L.append("## Речь")
    L.append("- длительность ролика %.1f с, слов %d, знаков %d" % (dur, nwords, len(text)))
    L.append("- темп: %.2f слова/с по всему ролику, %.2f слова/с по чистой речи" % (
        nwords / dur if dur else 0, nwords / speech if speech else 0))
    L.append("- фраз %d, средняя %.1f слова, самая длинная %d" % (
        len(sent), nwords / len(sent), max(len(s) for s in sent)))
    L.append("- обращение: " + ", ".join("%s %d" % (k, len(re.findall(rx, low))) for k, rx in PRON.items()))
    L.append("- смягчители (просто/всего/лишь/just): %d" % len(re.findall(SOFT, low)))
    L.append("- паузы от 0,6 с: %d%s" % (len(pauses), (" (" + ", ".join("%s %.1f с" % (fmt(t), p) for t, p in pauses[:8])
                                                     + ")") if pauses else ""))
    L.append("")
    L.append("## Монтаж")
    if cuts:
        L.append("- склеек %d (порог scene 0,3 — мягкие склейки на одном фоне не видит, сверять с листами), "
                 "планов %d, средний план %.1f с" % (len(cuts), shots, dur / shots))
        L.append("- первая склейка на %.1f с" % cuts[0])
    else:
        L.append("- склеек не найдено (cuts.txt пуст или нет): один план или мягкие переходы, смотреть листы")
    L.append("")
    L.append("## Раскладка по фразам")
    L.append("")
    L.append("| время | слов | планов | фраза |")
    L.append("|---|---|---|---|")
    for s in sent:
        a, b = s[0][0], s[-1][1]
        n_sh = 1 + sum(1 for c in cuts if a < c < b)
        L.append("| %s–%s | %d | %d | %s |" % (fmt(a), fmt(b), len(s), n_sh, " ".join(w[2] for w in s)))
    rc = 0
    if "--ours" in sys.argv:
        # наш сценарий не повторяет чужие фразы: общая цепочка от 5 слов подряд = брак (переписать своими словами)
        ours = json.load(io.open(sys.argv[sys.argv.index("--ours") + 1], encoding="utf-8"))
        lines = ours["lines"] if isinstance(ours, dict) else ours
        norm = lambda s: re.findall(r"[a-zа-яё0-9]+", s.lower().replace("ё", "е"))
        ref = norm(text)
        grams = {tuple(ref[i:i + 5]) for i in range(len(ref) - 4)}
        hits = []
        for k, l in enumerate(lines):
            v = norm(l.get("voice", ""))
            for i in range(len(v) - 4):
                if tuple(v[i:i + 5]) in grams:
                    hits.append("реплика %d: «%s»" % (k + 1, " ".join(v[i:i + 5])))
        L.append("")
        L.append("## Заимствования в нашем сценарии")
        L.append("- общих цепочек от 5 слов: %d" % len(hits) + ("" if not hits else " — БРАК, переписать: " + "; ".join(hits[:6])))
        rc = 3 if hits else 0
    out = "\n".join(L) + "\n"
    io.open(os.path.join(d, "stats.md"), "w", encoding="utf-8", newline="\n").write(out)
    print(out)
    return rc


if __name__ == "__main__":
    sys.exit(main())
