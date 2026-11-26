# -*- coding: utf-8 -*-
"""Gemini TTS (Google AI, ключ GEMINI_API_KEY из окружения): проба ударений и клон голоса Гора.

Слово Гора 03.10: «а давай попробуем гугл код апи» (после «ударения это салам пополам» у двойника Qwen).
Модели: gemini-3.8-flash-tts (основная), gemini-3.8-flash-lite-tts. Русский поддерживается.
Клон голоса (POST /v1beta/voices, type=replicated) требует ДВЕ живые записи одного взрослого человека:
образец 10-30 с и запись согласия с дословной фразой (ru-RU):
  «Я являюсь владельцем этого голоса и даю согласие Google на использование этого голоса
   для создания модели синтетического голоса.»
Согласие записывает только сам Гор, синтезом его не подделывать (это обход защиты Google).

  py -3.12 gemini_tts.py traps ГОЛОС [МОДЕЛЬ]     20 фраз-ловушек ударений -> work_voice_gor/stress/gemini_<голос>/
  py -3.12 gemini_tts.py say ГОЛОС "текст" out.wav
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
ST = HERE / "work_voice_gor" / "stress"
API = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-3.8-flash-tts"


def _post(url: str, body: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                 headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"],
                                          "Content-Type": "application/json; charset=utf-8"})
    for attempt in range(5):
        try:
            return json.load(urllib.request.urlopen(req, timeout=timeout))
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")
            if e.code in (429, 500, 503) and attempt < 4:
                time.sleep(15 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {msg[:600]}") from None
    raise RuntimeError("не дозвонились")


def tts(text: str, voice: str, model: str = DEFAULT_MODEL, style: str | None = None) -> bytes:
    """-> WAV-байты (24 кГц моно). voice: имя готового голоса, voice_... или voicekey_..."""
    if voice.startswith(("voice_", "voicekey_")):
        vc = {"replicatedVoiceConfig": {"voice": voice}}
    else:
        vc = {"prebuiltVoiceConfig": {"voiceName": voice}}
    prompt = f"{style}: {text}" if style else text
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": vc}}}
    d = _post(f"{API}/models/{model}:generateContent", body)
    part = d["candidates"][0]["content"]["parts"][0]["inlineData"]
    raw = base64.b64decode(part["data"])
    if raw[:4] == b"RIFF":
        return raw
    rate = 24000
    for kv in part.get("mimeType", "").split(";"):
        if kv.strip().startswith("rate="):
            rate = int(kv.split("=")[1])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(raw)
    return buf.getvalue()


def traps(voice: str, model: str = DEFAULT_MODEL, start: int = 0) -> None:
    lines = [l.strip() for l in (ST / "traps.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    tag = "gemini_" + voice.lower() + ("" if model == DEFAULT_MODEL else "_" + model.split("-")[-2])
    out = ST / tag
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    for i, l in enumerate(lines):
        if i < start:
            continue
        p = out / f"p{i:02d}.wav"
        if not p.exists():
            p.write_bytes(tts(l, voice, model))
    print(f"{tag}: {len(lines)} фраз за {time.time() - t0:.0f} с -> {out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1]
    if cmd == "traps":
        traps(sys.argv[2], *(sys.argv[3:4] or []), *[int(x) for x in sys.argv[4:5]])
    elif cmd == "say":
        Path(sys.argv[4]).write_bytes(tts(sys.argv[3], sys.argv[2]))
        print("ok", sys.argv[4])
