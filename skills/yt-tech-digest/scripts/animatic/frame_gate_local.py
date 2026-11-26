# -*- coding: utf-8 -*-
"""Покадровый vision-гейт (правило Гора 08-21, адаптация под полноэкранный ролик):
кадр раз в 1.5с -> grok vision. Брак: нереальное железо (невозможная геометрия, деформации,
грязь/износ/припой, ИИ-артефакты), посторонний контент, битый текст на слайдах.
Один плохой кадр -> ролик не уходит."""
import base64, io, json, os, subprocess, sys, time, urllib.request
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
VIDEO = sys.argv[1]
GDIR = os.path.join(HERE, "first5", "gate"); os.makedirs(GDIR, exist_ok=True)

AUTH = r"C:\Users\Administrator\AppData\Local\hermes\auth.json"
def token():
    return json.load(open(AUTH, encoding="utf-8"))["credential_pool"]["xai-oauth"][0]["access_token"]

# кадры раз в 1.5с
for f in os.listdir(GDIR):
    if f.startswith("fr_"): os.remove(os.path.join(GDIR, f))
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", VIDEO, "-vf", "fps=1/1.5,scale=960:540", "-q:v", "4", os.path.join(GDIR, "fr_%03d.jpg")], check=True)
frames = sorted(f for f in os.listdir(GDIR) if f.startswith("fr_"))
print("кадров на суд:", len(frames))

PROMPT = """Ты покадровый контролёр YouTube-ролика мастерской премиальных ПК. Кадр может быть: (а) тёмная инфографика с цифрами бенчмарков, (б) фото/генеративная иллюстрация компьютерного железа с плашкой «изображение сгенерировано», (в) арт-иллюстрация (звездолёт, музей) с той же плашкой, (г) заглушка с текстом.
БРАК, если хоть одно: 1) железо выглядит нереальным или бракованным: невозможная геометрия, расплавленные/деформированные детали, грязь, припой, царапины, износ, лишние или сросшиеся элементы, кривые разъёмы; 2) посторонний контент: реклама, эротика, лекарства, чужие бренды крупно, не по теме ПК/бенчмарков; 3) битый текст: нечитаемые псевдобуквы, бессмысленные надписи (осмысленный русский/английский текст и цифры — норма); 4) кадр выглядит как реальное продуктовое фото конкретного товара БЕЗ плашки «изображение сгенерировано», хотя это генерация.
Арт-иллюстрации (звездолёт, музей с табличками) браком НЕ считаются, если плашка на месте и контент по теме. Затемнённые/полупрозрачные кадры — это фейд-переход, норма, суди только различимое. «Битый текст» = реально искажённые буквы или бессмыслица; несогласие с формулировкой браком не является.
Лексикон канала, это НЕ опечатки: сток, ПБО, лок, анлим, дейли, контра, низы, кап, скальп, якорь, потолок, сессия, Киберпанк. Плашка «изображение сгенерировано · иллюстрация» — мелкая белая надпись на чёрной подложке в ПРАВОМ НИЖНЕМ углу; смотри туда внимательно, прежде чем писать, что её нет. Запланированные метафоры ролика, ПО ТЕМЕ: рубка звездолёта с голографической кривой (метафора V/F-кривой) и музейный зал с латунными переключателями в витринах (метафора настроек биоса). В reason при браке называй КОНКРЕТНО: какой текст битый (процитируй) или какой элемент нереален. Общие слова без конкретики не принимаются.
Верни строго JSON: {"verdict":"ok"|"brak","reason":"кратко почему"}"""

def judge(path):
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    body = {"model": "grok-4", "messages": [
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64, "detail": "high"}},
            {"type": "text", "text": PROMPT}]}],
        "max_tokens": 200}
    for attempt, model in ((1, "grok-4.20-0309-non-reasoning"), (2, "grok-4"), (3, "grok-4")):
        body["model"] = model
        req = urllib.request.Request("https://api.x.ai/v1/chat/completions", data=json.dumps(body).encode(), method="POST")
        req.add_header("Authorization", "Bearer " + token()); req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                j = json.load(r)
            c = j["choices"][0]["message"].get("content") or ""
            s, e = c.find("{"), c.rfind("}")
            return json.loads(c[s:e + 1])
        except urllib.error.HTTPError as ex:
            err = ex.read().decode("utf-8", "ignore")[:160]
            if attempt == 3: return {"verdict": "error", "reason": err}
            time.sleep(4)
        except Exception as ex:  # noqa: BLE001
            if attempt == 3: return {"verdict": "error", "reason": str(ex)[:160]}
            time.sleep(4)

from PIL import Image
def label_present(path):
    """Наша же плашка: тёмная подложка со светлым текстом в правом нижнем углу. Проверка кодом, не зрением."""
    im = Image.open(path).convert("L")
    w, h = im.size
    box = im.crop((int(w * 0.72), int(h * 0.955), int(w * 0.995), int(h * 0.995)))
    px = list(box.getdata())
    dark = sum(1 for v in px if v < 60) / len(px)
    light = sum(1 for v in px if v > 150) / len(px)
    return dark > 0.4 and light > 0.02

import glob as _glob
def _arr(im):
    px = list(im.convert("L").resize((240, 135)).getdata())
    m = sum(px) / len(px)
    sd = (sum((v - m) ** 2 for v in px) / len(px)) ** 0.5 or 1
    return [(v - m) / sd for v in px]
_SLIDES = {os.path.basename(p): _arr(Image.open(p)) for p in _glob.glob(os.path.join(HERE, "first5", "slides", "s*.png"))}
def match_slide(path):
    """Кадры, пиксельно совпадающие с кодогенерированным слайдом, не судятся зрением за «битый текст»."""
    fa = _arr(Image.open(path))
    best, bn = 0, None
    for n, sa in _SLIDES.items():
        c = sum(x * y for x, y in zip(fa, sa)) / len(fa)
        if c > best: best, bn = c, n
    return bn, best

bad, results = [], []
for i, f in enumerate(frames, 1):
    fp = os.path.join(GDIR, f)
    v = judge(fp)
    if v["verdict"] != "ok" and "плашк" in v.get("reason", "").lower() and label_present(fp):
        v = {"verdict": "ok", "reason": "плашка подтверждена кодом (пиксельная проверка), вердикт зрения снят"}
    if v["verdict"] != "ok" and "бит" in v.get("reason", "").lower():
        n, c = match_slide(fp)
        if c > 0.985:
            v = {"verdict": "ok", "reason": "кадр = слайд %s (corr %.3f), текст задан кодом — «битый текст» исключён детерминированно" % (n, c)}
    results.append({"frame": f, **v})
    mark = "OK " if v["verdict"] == "ok" else "!! "
    if v["verdict"] != "ok": bad.append((f, v))
    print("%s %s %s" % (mark, f, v.get("reason", "")[:110]))
json.dump(results, open(os.path.join(GDIR, "verdicts.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("-" * 50)
if bad:
    print("ГЕЙТ НЕ ПРОЙДЕН: %d кадров" % len(bad)); sys.exit(1)
print("ГЕЙТ ПРОЙДЕН: %d/%d кадров чистые" % (len(frames), len(frames)))
