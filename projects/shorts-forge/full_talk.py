# -*- coding: utf-8 -*-
"""Полная видеоверсия доклада: авторские слайды (PNG из build2) + голос по
авторскому скрипту (script-part*.md) тем же Chatterbox-рецептом.

Это НЕ монтажный рил (course_reel.py), а честная запись выступления:
слайд стоит, пока звучит его текст, стык — прямой cut, без музыки (это лекция,
а не трейлер). Хронометраж каждого слайда определяется фактической длиной
речи, а не плановыми таймингами из скрипта.

Запуск (питон из чаттербокс-венва, у него torch cu128 и модель):
  C:/Apps/chatterbox/.venv/Scripts/python.exe full_talk.py part2   # полигон
  C:/Apps/chatterbox/.venv/Scripts/python.exe full_talk.py part1   # курс

Звук собирается ЕДИНОЙ WAV-дорожкой (урок рассинхрона из рила: AAC-склейка
копит прайминг, ~40 мс на стык), кодирование одно, на финале.
"""
from __future__ import annotations

import re
import subprocess
import sys
import wave
from pathlib import Path

BUILD = Path(r"C:\Users\Administrator\Desktop\build2\build")
HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
W, H, FPS = 1920, 1080, 30
PAUSE_SENT = 0.28      # пауза между предложениями
PAUSE_SLIDE = 0.9      # дыхание на стыке слайдов
SYL_RATE = 6.5

PARTS = {
    "part1": dict(script="script-part1-course.md", slides="course",
                  out="talk_part1_course.mp4"),
    "part2": dict(script="script-part2-game.md", slides="game",
                  out="talk_part2_game.mp4"),
}

# Голосовые замены — тот же словарь, что в риле, плюс частые в полном скрипте.
sys.path.insert(0, str(HERE))
from course_reel import TTS_FIX  # noqa: E402
from gen_voices_cb import trim_breath, snort_free  # noqa: E402  (срез вдохов Chatterbox)

EXTRA_FIX = {
    "REST": "рэст",
    "API": "апи+",
    "MCP": "эм-си-п+и",
    "curl": "кёрл",
    "JSON": "джейс+он",
    "CSV": "си-эс-в+и",
    "ledger.csv": "л+еджер точка си-эс-в+и",
    "kindomklaster.com": "киндомкл+астер точка ком",
    "LM Studio": "эл-эм ст+удио",
    "Hugging Face": "х+агинг ф+ейс",
    "GPU": "джи-пи-+у",
    "LoRA": "л+ора",
    "QLoRA": "кю-л+ора",
    "GGUF": "г+уф",
    "BPE": "би-пи-+и",
    "nano-GPT": "н+ано джи-пи-т+и",
    "GPT": "джи-пи-т+и",
    "ReAct": "ри+акт",
    "smolagents": "смол-+эйджентс",
    "LlamaIndex": "л+ама-+индекс",
    "LangGraph": "ланг-гр+аф",
    "OpenClaw": "оупен-кл+о",
    "Hermes": "герм+ес",
    "Spaces": "спейсес",
    "House Prices": "х+аус пр+айсес",
    "micrograd": "микрогр+ад",
    "microgpt": "микро-джи-пи-т+и",
    "CatBoost": "кэт-б+уст",
    "OpenRouter": "оупен-р+аутер",
    "vLLM": "ви-эл-эл-+эм",
    "llama.cpp": "л+ама си-пи-пи",
    "Ollama": "ол+ама",
    "Multica": "м+ультика",
    "Paperclip": "п+ейперклип",
    "Screeps": "скрипс",
    "Boot.dev": "бут дев",
    "HF": "хагинг-фейс",
    "422": "четыреста двадцать два",
    "TODO": "ту-д+у",
    "T4": "тэ четыре",
}

# Ударения из ручной проверки пословного отчёта (out/УДАРЕНИЯ_доклада.md):
# RUAccent этих слов не знает, а нейро-TTS на внесловарном гадает. Спорные
# сверены с орфоэпической нормой: сда́но (ср. род), кра́фтить, адми́нка, сгора́ет.
STRESS_FIX = {
    "автодокументация": "автодокумент+ация",
    "админк": "адм+инк",            # адми́нкой/адми́нку
    "бейзлайн": "бейзл+айн",
    "галочк": "г+алочк",
    "датасет": "датас+ет",
    "дворф": "дв+орф",
    "деплой": "депл+ой",
    "дообуча": "дообуч+а",
    "дописани": "допис+ани",
    "запускаем": "запуск+аем",
    "инференс": "инфер+енс",
    "капстоун": "капст+оун",
    "коммит": "комм+ит",
    "крафтить": "кр+афтить",
    "мультиагент": "мультиаг+ент",
    "мультимодальность": "мультимод+альность",
    "непустым": "непуст+ым",
    "оркестраци": "оркестр+аци",
    "приложени": "прилож+ени",
    "промпт": "пр+омпт",
    "проде": "пр+оде",
    "рендерер": "р+ендерер",
    "ростер": "р+остер",
    "сгорает": "сгор+ает",
    "сдано": "сд+ано",
    "семимиллиардн": "семимилли+ардн",
    "статы": "ст+аты",
    "стопка": "ст+опка",
    "токен": "т+окен",
    "фичи": "ф+ичи",
    "чат-шаблон": "чат-шабл+он",
    "эмбеддинг": "эмб+еддинг",
    "моке": "м+оке",
}
EXTRA_FIX.update(STRESS_FIX)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, **kw)


def parse_script(path: Path) -> list[dict]:
    """Слайды из авторского md: ## N. Заголовок, строка таймингов, затем текст."""
    text = path.read_text(encoding="utf-8")
    # ⚠ В файле ДВА разделителя «---»: после шапки и перед приложением
    # («Что держать под рукой»). Слайды живут МЕЖДУ ними: первый split отрезает
    # шапку, второй — приложение. Прежний maxsplit=2 возвращал приложение,
    # и парсер честно видел «0 слайдов».
    body = text.split("---", 1)[1]
    body = body.split("\n---")[0]
    chunks = re.split(r"^## (\d+)\. ", body, flags=re.M)[1:]
    slides = []
    for num, chunk in zip(chunks[0::2], chunks[1::2]):
        lines = chunk.split("\n")
        title = lines[0].strip()
        rest = "\n".join(lines[1:])
        # выбрасываем служебную строку таймингов `0:00 → 0:25` · 25 с · тип `cover`
        rest = re.sub(r"^`[^`]*`\s*·[^\n]*$", "", rest, flags=re.M)
        # РЕМАРКИ В СКОБКАХ-КАПСОМ (ЕСЛИ СПРОСЯТ...) — не читаются вслух
        paras = [p.strip() for p in rest.split("\n") if p.strip()]
        paras = [p for p in paras if not p.startswith("ЕСЛИ ")]
        slides.append(dict(num=int(num), title=title, text=" ".join(paras)))
    return slides


def syllables(s: str) -> int:
    return len(re.findall(r"[аеёиоуыэюя]", s.lower()))


def main() -> int:
    part = PARTS.get(sys.argv[1] if len(sys.argv) > 1 else "part2")
    if not part:
        print("part1 | part2")
        return 2
    slides_dir = BUILD / "slides" / part["slides"]
    script = BUILD / part["script"]
    work = HERE / f"work_talk_{part['slides']}"
    work.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)

    slides = parse_script(script)
    print(f"{script.name}: {len(slides)} слайдов")

    import torch
    from ruaccent import RUAccent
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    acc = RUAccent()
    acc.load(omograph_model_size="turbo3.1", use_dictionary=True, tiny_mode=False)
    from ruaccent import accent_model as _am          # страховка от ONNX-падения
    _orig = _am.AccentModel.put_accent
    _am.AccentModel.put_accent = lambda self, w: _safe_put(_orig, self, w)

    model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
    sr = model.sr

    # ⛔ ДЕГРАДАЦИЯ РУССКОГО: у Chatterbox документировано (issue #360), что после
    # ~5 генераций подряд язык уезжает в английский акцент — кондиционалы копят
    # дрейф. Доклад — это 200+ фраз одним процессом, без лечения к середине
    # голос станет иностранцем. Лечение: снапшот кондиционалов после загрузки
    # и жёсткий откат к нему каждые несколько фраз.
    import copy
    _conds0 = copy.deepcopy(model.conds)
    _gen_count = [0]

    def _fresh_conds():
        _gen_count[0] += 1
        if _gen_count[0] % 4 == 0:
            model.conds = copy.deepcopy(_conds0)

    plus = re.compile(r"\+([аеёиоуыэюяАЕЁИОУЫЭЮЯ])")

    def acute(s: str) -> str:
        return plus.sub(lambda m: m.group(1) + "\u0301", s)

    def say(text: str) -> "torch.Tensor":
        for a, b in {**TTS_FIX, **EXTRA_FIX}.items():
            text = text.replace(a, b)
        sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]
        chunks = []
        for s in sents:
            marked = acute(acc.process_all(acute(s)))
            need = syllables(s) / SYL_RATE
            best, best_len = None, 1e9
            for _ in range(4):
                _fresh_conds()
                w = model.generate(marked, language_id="ru",
                                   temperature=0.65, cfg_weight=0.6)
                got = w.shape[-1] / sr
                clean = snort_free(w, sr)
                if got < best_len and clean:
                    best, best_len = w, got
                if best is None and got < best_len:
                    best, best_len = w, got
                if got <= need * 1.45 + (1.6 if need < 3 else 0.8) and clean:
                    break
            chunks.append(trim_breath(best, sr))
            chunks.append(torch.zeros(int(sr * PAUSE_SENT)))
        return torch.cat(chunks[:-1]) if chunks else torch.zeros(sr)

    # ── голоса по слайдам ──
    entries = []
    for sl in slides:
        wav_p = work / f"s{sl['num']:02d}.wav"
        png = slides_dir / f"{sl['num']:02d}.png"
        if not png.exists():
            print(f"  {sl['num']:2}: НЕТ PNG — пропуск")
            continue
        if not wav_p.exists():
            audio = say(sl["text"])
            with wave.open(str(wav_p), "wb") as f:
                f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr)
                f.writeframes((audio.clamp(-1, 1) * 32767)
                              .to(torch.int16).cpu().numpy().tobytes())
        d = 0.35 + wav_len(wav_p) + PAUSE_SLIDE
        entries.append((sl, png, wav_p, d))
        print(f"  {sl['num']:2} {sl['title'][:44]:44} {d:6.1f}с")

    # ── видео: каждый слайд картинкой на свою длительность ──
    vparts = []
    for sl, png, wav_p, d in entries:
        vp = work / f"v{sl['num']:02d}.mp4"
        if not vp.exists():
            r = run(["ffmpeg", "-y", "-v", "error", "-threads", "2",
                     "-loop", "1", "-framerate", str(FPS), "-t", f"{d:.3f}",
                     "-i", str(png),
                     "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=#0c0b08,"
                            f"format=yuv420p,setsar=1",
                     "-r", str(FPS),
                     "-c:v", "libx264", "-preset", "medium", "-crf", "15",
                     "-pix_fmt", "yuv420p", str(vp)])
            if r.returncode != 0:
                print("   видео:", r.stderr.decode("utf-8", "replace")[-200:])
                continue
        vparts.append((vp, wav_p, d))

    # ── звук единой дорожкой: тишина 0.35с + голос + пауза до длины слайда ──
    awavs = []
    for vp, wav_p, d in vparts:
        ap = work / (vp.stem + "_a.wav")
        run(["ffmpeg", "-y", "-v", "error", "-i", str(wav_p),
             "-af", f"aresample=48000,adelay=350|350,apad,atrim=duration={d:.3f}",
             "-ac", "2", "-c:a", "pcm_s16le", str(ap)])
        awavs.append(ap)

    vlst = work / "all_v.txt"
    vlst.write_text("".join(f"file '{p[0].name}'\n" for p in vparts), encoding="utf-8")
    alst = work / "all_a.txt"
    alst.write_text("".join(f"file '{p.name}'\n" for p in awavs), encoding="utf-8")
    voice_all = work / "voice_all.wav"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(alst), "-c", "copy", str(voice_all)], cwd=work)

    final = OUT / part["out"]
    r = run(["ffmpeg", "-y", "-v", "error", "-i", str(voice_all),
             "-f", "concat", "-safe", "0", "-i", str(vlst),
             "-vf", "noise=alls=3:allf=u,format=yuv420p",
             "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
             "-map", "1:v:0", "-map", "0:a:0",
             "-c:v", "libx264", "-preset", "slow", "-crf", "17",
             "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_trc", "bt709",
             "-color_primaries", "bt709", "-color_range", "tv",
             "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(final)], cwd=work)
    if r.returncode != 0:
        print("сборка:", r.stderr.decode("utf-8", "replace")[-300:])
        return 1
    vd, ad = ffdur(final), ffdur(voice_all)
    print(f"\nГОТОВО: {final} · {vd:.1f}с · {final.stat().st_size/1e6:.1f} МБ "
          f"· расхождение {abs(vd-ad):.2f}с")
    return 0


def _safe_put(orig, self, word):
    try:
        return orig(self, word)
    except Exception:
        return word


def wav_len(p: Path) -> float:
    with wave.open(str(p), "rb") as f:
        return f.getnframes() / f.getframerate()


def ffdur(p: Path) -> float:
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(p)])
    try:
        return float(r.stdout.decode().strip())
    except ValueError:
        return -1.0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
