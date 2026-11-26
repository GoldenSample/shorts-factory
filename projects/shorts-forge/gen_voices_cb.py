# -*- coding: utf-8 -*-
"""Все голоса ролика одним прогоном: Chatterbox + RUAccent + контроль длительности.

Запускать ПИТОНОМ ИЗ C:/Apps/chatterbox/.venv — у него torch cu128 и сама модель:
  C:/Apps/chatterbox/.venv/Scripts/python.exe gen_voices_cb.py

Почему отдельный скрипт, а не внутри course_reel.tts(): модель грузится ~6 с,
и грузить её 13 раз из подпроцессов глупо; здесь один процесс держит модель
и выдаёт все реплики подряд.

РЕЦЕПТ (выведен пробами на этой машине, история — в диалоге 29-07):
  · Silero списан Гором («как из 2013»), edge-tts списан раньше («так себе»).
  · Chatterbox Multilingual (MIT, поколение 2025) на 5090: ~60 ит/с.
  · ⛔ Голая генерация ломает ударения («автОр») — модуль ударений у Chatterbox
    не ставится (пин на несуществующие версии), поэтому размечаем сами:
    RUAccent (MIT, словарь + разбор омографов) → «+» → комбинируемый акут U+0301.
  · ⛔ Длинная размеченная фраза провоцирует зацикливание (ловили дубль 34.6 с
    вместо 5.7). Лечение: генерация ПО ПРЕДЛОЖЕНИЯМ, temperature 0.65,
    cfg_weight 0.6, и авторетрай, если звук длиннее ожидания по слоговой
    скорости (замер русской речи: ~6.5 слога/с; коротким фразам допуск шире —
    они читаются с расстановкой).
"""
from __future__ import annotations

import re
import subprocess
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import course_reel as cr  # noqa: E402  (нужны BLOCKS и TTS_FIX)

import torch  # noqa: E402
# ⚠ ruaccent и chatterbox импортируются ЛЕНИВО внутри main(): этот модуль
# импортируют и из qwen-венва ради trim_breath/snort_free, которым они не нужны.

PAUSE = 0.28          # секунд между предложениями
TEMP = 0.65
CFG_W = 0.6
SYL_RATE = 6.5        # слогов в секунду — по нашим замерам русского TTS


def syllables(s: str) -> int:
    return len(re.findall(r"[аеёиоуыэюя]", s.lower()))


def trim_breath(w, sr: int, thr_frac: float = 0.045, pad: float = 0.09):
    """Срез дыхания на краях фразы.

    ⛔ Chatterbox дорисовывает вдохи-выдохи на хвостах сегментов (Гор: «в паузах
    ксенозвуки и криповые вздохи»), а посегментная генерация с паузами их
    оголяет. Дыхание в разы тише речи, поэтому режем всё до первого и после
    последнего сэмпла громче порога от пика, с коротким линейным фейдом на срезах.
    """
    import torch
    a = w.squeeze().abs()
    idx = (a > thr_frac * float(a.max())).nonzero()
    if len(idx) == 0:
        return w.squeeze()
    s = max(0, int(idx.min()) - int(pad * sr))
    e = min(a.shape[-1], int(idx.max()) + int(pad * sr))
    out = w.squeeze()[s:e].clone()
    f = min(int(0.03 * sr), out.shape[-1] // 4)
    if f > 0:
        ramp = torch.linspace(0.0, 1.0, f)
        out[:f] *= ramp
        out[-f:] *= ramp.flip(0)
    return out


def snort_free(w, sr: int) -> bool:
    """Детектор фырков: у речи спектр тональный, у фырка — широкополосный шум.

    Ловит то, что пропускает контроль длительности: шумовой всплеск ВНУТРИ фразы
    (Гор: «пердеть в микрофон на 0:35»; спектрограмма показала кляксу 2-11 кГц
    без гармонической структуры). Порог: >=0.28 с подряд шумных громких окон
    или >22% шумных среди громких.
    """
    import numpy as np, librosa
    y = w.squeeze().float().cpu().numpy()
    if len(y) < sr:
        return True
    S = np.abs(librosa.stft(y, n_fft=1024, hop_length=256))
    flat = librosa.feature.spectral_flatness(S=S)[0]
    rms = librosa.feature.rms(S=S, frame_length=1024)[0]
    loud = rms > np.percentile(rms, 55)
    f = flat[loud]
    if not len(f):
        return True
    noisy = f > 0.35
    run = best = 0
    for v in noisy:
        run = run + 1 if v else 0
        best = max(best, run)
    return best * 256 / sr < 0.28 and noisy.mean() <= 0.22


PLUS_RE = re.compile(r"\+([аеёиоуыэюяАЕЁИОУЫЭЮЯ])")


def plus_to_acute(s: str) -> str:
    return PLUS_RE.sub(lambda m: m.group(1) + "\u0301", s)


def main() -> int:
    from ruaccent import RUAccent
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    acc = RUAccent()
    acc.load(omograph_model_size="turbo3.1", use_dictionary=True, tiny_mode=False)

    # СТРАХОВКА: на внесловарном слове нейромодель RUAccent падает ONNX-ошибкой
    # "Required inputs token_type_ids are missing" (несовместимость версий).
    # Такое слово оставляем как есть - наши экзотизмы уже размечены руками в TTS_FIX.
    from ruaccent import accent_model as _am
    _orig = _am.AccentModel.put_accent

    def _safe(self, word):
        try:
            return _orig(self, word)
        except Exception:
            return word
    _am.AccentModel.put_accent = _safe

    model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
    sr = model.sr

    def mark(s: str) -> str:
        # ручные "+"-метки уходят в акуты ДО RUAccent: он видит уже ударенное
        # слово и не лезет в него нейросетью
        return plus_to_acute(acc.process_all(plus_to_acute(s)))


    cr.WORK.mkdir(exist_ok=True)
    for i, b in enumerate(cr.BLOCKS, 1):
        dest = cr.WORK / f"v{i}.mp3"
        if dest.exists():
            print(f"  {i:2} {b['id']:9} уже есть")
            continue
        text = b["voice"]
        for a, r in cr.TTS_FIX.items():
            text = text.replace(a, r)
        sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]
        chunks: list[torch.Tensor] = []
        for s in sents:
            marked = mark(s)
            need = syllables(s) / SYL_RATE
            best, best_len = None, 1e9
            for attempt in range(4):
                w = model.generate(marked, language_id="ru",
                                   temperature=TEMP, cfg_weight=CFG_W)
                got = w.shape[-1] / sr
                # коротким фразам допуск шире: их читают с расстановкой
                limit = need * 1.45 + (1.6 if need < 3 else 0.8)
                clean = snort_free(w, sr)
                if got < best_len and clean:
                    best, best_len = w, got
                if best is None and got < best_len:
                    best, best_len = w, got      # хоть что-то, если все дубли грязные
                if got <= limit and clean:
                    break
            chunks.append(trim_breath(best, sr))
            chunks.append(torch.zeros(int(sr * PAUSE)))
        audio = torch.cat(chunks[:-1])          # без хвостовой паузы
        raw = cr.WORK / f"v{i}_raw.wav"
        with wave.open(str(raw), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(sr)
            f.writeframes((audio.clamp(-1, 1) * 32767)
                          .to(torch.int16).cpu().numpy().tobytes())
        # дикторская обработка — та же цепочка, что была у прежних движков
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw),
                        "-af", "highpass=f=85,equalizer=f=250:t=q:w=1.2:g=-3,"
                               "equalizer=f=2800:t=q:w=1.4:g=2.5,"
                               "acompressor=threshold=-20dB:ratio=3:attack=12:release=200,"
                               "loudnorm=I=-16:TP=-1.5:LRA=11",
                        "-ar", "48000", "-c:a", "libmp3lame", "-b:a", "192k",
                        str(dest)], capture_output=True)
        raw.unlink(missing_ok=True)
        print(f"  {i:2} {b['id']:9} {len(audio)/sr:5.1f}с · {len(sents)} предл.")
    print("голоса готовы")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
