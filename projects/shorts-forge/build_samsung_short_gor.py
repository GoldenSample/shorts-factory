# -*- coding: utf-8 -*-
"""Samsung 9100 Pro шортс, озвученный ДВОЙНИКОМ ГОЛОСА ГОРА (Qwen3-TTS SFT на его роликах).

Кадры и субтитры те же, что в build_samsung_short.py (они уже отрендерены в work_short2),
озвучка по сценам из gor_voice.py:
  <qwen>      gor_voice.py synth work_voice_gor/samsung_script.txt work_voice_gor/samsung_gor --n 3 --lines
  <whisper>   gor_voice.py judge work_voice_gor/samsung_gor
  <chatterbox> gor_voice.py assemble-lines work_voice_gor/samsung_gor work_voice_gor/samsung_scenes
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_samsung_short import SCENES, SRC_WOOT
from short2 import WORK, assemble, build_scene, ffdur

VOICES = HERE / "work_voice_gor" / "samsung_scenes_fast"   # atempo 1.12: живой темп Гора не влезает в 90 с


def main() -> int:
    scenes = []
    for li, (tag, _imager, _text, sub) in enumerate(SCENES):
        img = SRC_WOOT if tag == "s02" else WORK / f"{tag}.png"
        voice = VOICES / f"line_{li:02d}.wav"
        if not img.exists() or not voice.exists():
            print(f"  {tag}: нет кадра или голоса ({img.name}, {voice.name})")
            return 1
        sc = build_scene(f"g{tag}", img, voice, sub, kenburns=(tag == "s02"))
        if not sc:
            return 1
        print(f"  {tag}: {ffdur(sc):.1f} с")
        scenes.append(sc)
    print(f"суммарно: {sum(ffdur(s) for s in scenes):.1f} с")
    return 0 if assemble(scenes, "short_samsung_9100_GOR_VOICE.mp4") else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
