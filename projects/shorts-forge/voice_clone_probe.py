# -*- coding: utf-8 -*-
"""Шаг 3: zero-shot клон голоса Гора, два движка на одних и тех же референсах и фразах.

  qwen        из venv qwen-tts: Qwen3-TTS-12Hz-1.7B-Base (лежит в H:\\comfy-models\\TTS), ICL-режим
              (референс + его транскрипт), Apache-2.0;
  chatterbox  из venv chatterbox: Multilingual, референс-аудио, MIT.

  <venv>\\python voice_clone_probe.py qwen|chatterbox [--refs 0,1,2]
Выход: work_voice_gor/probe/<движок>_ref<NN>_<фраза>.wav. Судит voice_judge.py (whisper + эмбеддинг).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE / "work_voice_gor"
REFS = ROOT / "refs"
PROBE = ROOT / "probe"
QWEN_BASE = r"H:\comfy-models\TTS\Qwen3-TTS-12Hz-1.7B-Base"

LINES = {
    "hook": "Самый быстрый эс-эс-дэ Самсунга внезапно подешевел на треть. "
            "Но прежде чем нести деньги, три вещи, о которых заголовки молчат.",
    "tech": "На платах икс восемьсот семьдесят люди ловят ошибки диска, "
            "а после холодного старта он иногда просто не определяется.",
    "verdict": "Правило одно: плати за скорость, которую твоя система реально умеет использовать, "
               "а не за цифру на коробке.",
}


def run_qwen(refs: list[dict]) -> None:
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel
    model = Qwen3TTSModel.from_pretrained(QWEN_BASE, device_map="cuda", dtype=torch.bfloat16)
    for r in refs:
        prompt = model.create_voice_clone_prompt(ref_audio=str(REFS / r["file"]), ref_text=r["t"])
        for key, text in LINES.items():
            dest = PROBE / f"qwen_{r['file'][:-4]}_{key}.wav"
            if dest.exists():
                continue
            wavs, sr = model.generate_voice_clone(text=text, language="Russian",
                                                  voice_clone_prompt=prompt)
            sf.write(dest, np.asarray(wavs[0], dtype=np.float32), sr)
            print(f"  {dest.name}")


def run_chatterbox(refs: list[dict]) -> None:
    import numpy as np
    import soundfile as sf
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    tts = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
    for r in refs:
        tts.prepare_conditionals(str(REFS / r["file"]), exaggeration=0.5)
        for key, text in LINES.items():
            dest = PROBE / f"chatterbox_{r['file'][:-4]}_{key}.wav"
            if dest.exists():
                continue
            with torch.inference_mode():
                w = tts.generate(text, language_id="ru", cfg_weight=0.5, temperature=0.7)
            sf.write(dest, w.squeeze(0).cpu().numpy().astype(np.float32), tts.sr)
            print(f"  {dest.name}")


def run_vstudio(refs: list[dict]) -> None:
    """VoiceStudio (движок OmniVoice) по HTTP. Только Python: curl из Git Bash портит кириллицу."""
    import requests
    for r in refs:
        for key, text in LINES.items():
            dest = PROBE / f"vstudio_{r['file'][:-4]}_{key}.wav"
            if dest.exists():
                continue
            with open(REFS / r["file"], "rb") as fh:
                resp = requests.post("http://localhost:3900/generate", timeout=600,
                                     data={"text": text, "language": "ru", "ref_text": r["t"]},
                                     files={"ref_audio": (r["file"], fh, "audio/wav")})
            resp.raise_for_status()
            dest.write_bytes(resp.content)
            print(f"  {dest.name}")


def main() -> int:
    engine = sys.argv[1]
    idx = [0, 1, 2]
    if "--refs" in sys.argv:
        idx = [int(x) for x in sys.argv[sys.argv.index("--refs") + 1].split(",")]
    allrefs = json.loads((REFS / "refs.json").read_text(encoding="utf-8"))
    refs = [allrefs[i] for i in idx if i < len(allrefs)]
    PROBE.mkdir(exist_ok=True)
    {"qwen": run_qwen, "chatterbox": run_chatterbox, "vstudio": run_vstudio}[engine](refs)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
