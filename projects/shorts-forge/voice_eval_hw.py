# -*- coding: utf-8 -*-
"""Стенд произношения железячной лексики: v2 (текст как у whisper) против v3 (словарь + нормализатор).

Судья: GigaAM-v3 v3_rnnt пишет речь словами, поэтому эталон = normalize(фраза), и «SSD» против
«эс эс дэ» не даёт ложных ошибок, как у whisper.

  <qwen>\\python voice_eval_hw.py gen --tag ИМЯ --ckpt ЧЕКПОИНТ --text raw|norm   синтез в eval_hw/ИМЯ
  <gigaam>\\python voice_eval_hw.py gcer                                             CER по всем тегам
Также gcer считает отложенный тест (eval/<тег>) против произносимых текстов dataset/test_spoken.jsonl.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE / "work_voice_gor"
EH = ROOT / "eval_hw"

HW = [
    "RTX 5090 против RTX 4090: прирост 30% в 4K при 575 Вт.",
    "Ryzen 7 9800X3D на плате ASUS ROG Strix B650E, память DDR5 6000 CL30.",
    "Core i9-14900KS держит 6.2 ГГц на всех ядрах при 1.30 В.",
    "Сокет LGA 1700 и новый LGA 1851 под Core Ultra 285K, чипсет Z890.",
    "Samsung 9100 Pro на 4 ТБ выдаёт 14800 МБ/с на чтение по PCIe 5.0.",
    "RX 9070 XT быстрее RTX 5070 Ti, а DLSS 4 даёт плюс 50 fps.",
    "Включаем XMP или EXPO в BIOS, иначе память работает на частоте JEDEC.",
    "SMT выключаем, PBO ставим в ручной режим, смотрим температуру в CPU-Z.",
    "У NVIDIA драйвер 595.71 снова ломает DLSS, а AMD молчит.",
    "Водоблок Thermal Grizzly на Intel 13900KS снимает до 10 градусов.",
    "В Cinebench R23 процессор набирает 40000 очков за 10 минут.",
    "Корпус под ATX или ITX, блок питания SFX на 850 Вт.",
    "Golden Sample PC собирает системы на Z790 и X870E.",
    "Видеокарта Gigabyte Aorus с GDDR7 и TDP 450 Вт.",
    "Разгон по BCLK на Arrow Lake даёт 5.4 ГГц, а VCCSA держим до 1.30.",
    "Xbox и PlayStation 6 выйдут в 2027 году, Microsoft это подтвердила.",
]


def gen(tag: str, ckpt: str, mode: str) -> None:
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel
    from gor_normalize import normalize
    d = EH / tag
    d.mkdir(parents=True, exist_ok=True)
    m = Qwen3TTSModel.from_pretrained(ckpt, device_map="cuda", dtype=torch.bfloat16, attn_implementation="sdpa")
    for i, s in enumerate(HW):
        p = d / f"h{i:02d}.wav"
        if p.exists():
            continue
        text = normalize(s) if mode == "norm" else s
        torch.manual_seed(100 + i)
        wavs, sr = m.generate_custom_voice(text=text, speaker="gor", language="Auto")
        sf.write(p, np.asarray(wavs[0], dtype=np.float32), sr)
    (d / "mode.txt").write_text(mode, encoding="utf-8")
    print(f"{tag}: {len(HW)} фраз, текст {mode}")


def gcer() -> None:
    import gigaam
    from gor_normalize import normalize
    from voice_eval import cer_str
    m = gigaam.load_model("v3_rnnt")
    refs_hw = {f"h{i:02d}": normalize(s) for i, s in enumerate(HW)}
    test = [json.loads(l) for l in (ROOT / "dataset" / "test_spoken.jsonl").open(encoding="utf-8")]
    refs_t = {f"t{i:02d}": t["text"] for i, t in enumerate(test)}

    def run(d: Path, refs: dict) -> tuple[float, list]:
        res = []
        for name, ref in refs.items():
            w = d / f"{name}.wav"
            if w.exists():
                hyp = m.transcribe(str(w)).text
                res.append((name, cer_str(ref, hyp), ref, hyp))
        return (sum(r[1] for r in res) / len(res) if res else float("nan")), res

    report = {}
    print("ЖЕЛЕЗЯЧНЫЕ ФРАЗЫ (эталон = нормализованный текст):")
    for d in sorted(p for p in EH.iterdir() if p.is_dir()):
        avg, res = run(d, refs_hw)
        report[d.name] = res
        worst = sorted(res, key=lambda r: -r[1])[:3]
        print(f"  {d.name:22} средний CER {avg:.3f}")
        for n, c, ref, hyp in worst:
            print(f"      {n} {c:.2f} | {ref[:70]}\n                  => {hyp[:70]}")
    print("\nОТЛОЖЕННЫЙ ТЕСТ, 24 фразы (эталон = произносимый текст):")
    for d in sorted(p for p in (ROOT / "eval").iterdir() if p.is_dir() and p.name.startswith(("sft_", "v3_", "zs_"))):
        avg, res = run(d, refs_t)
        print(f"  {d.name:22} средний CER {avg:.3f} · медиана {sorted(r[1] for r in res)[len(res) // 2]:.3f}")
    (EH / "gcer.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1] == "gen":
        a = sys.argv
        gen(a[a.index("--tag") + 1], a[a.index("--ckpt") + 1], a[a.index("--text") + 1])
    else:
        gcer()
