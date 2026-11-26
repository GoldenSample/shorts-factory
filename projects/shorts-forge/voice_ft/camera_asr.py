# -*- coding: utf-8 -*-
"""Архив камеры Гора (D:\\РАИД, слово Гора 14.10.2026 «дообучать драму по массиву камеры», «да прямое да»):
расшифровка всех дорожек на 5090 (задание asr контроллера рига, faster-whisper large-v3, слова с таймингами).
Вход H:\\tts_data\\gor_camera\\raw\\*.wav (моно 24 кГц), выход H:\\tts_data\\gor_camera\\asr\\<имя>.json; готовые не трогает.
  py -3.12 camera_asr.py"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, r"C:\CLAUD\tools")
from asr_client import transcribe  # noqa: E402

ROOT = Path(r"H:\tts_data\gor_camera")
RAW, OUT = ROOT / "raw", ROOT / "asr"
OUT.mkdir(parents=True, exist_ok=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    files = sorted(RAW.glob("*.wav"), key=lambda p: p.stat().st_size)
    t_all = time.time(); done = 0
    for p in files:
        dst = OUT / (p.stem + ".json")
        if dst.exists():
            continue
        t0 = time.time()
        try:
            res = transcribe(str(p), host="http://10.77.0.2:9099")
        except Exception as e:  # noqa: BLE001
            print(f"ОШИБКА {p.name}: {e}", flush=True); continue
        dst.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        done += 1
        print(f"{p.name}: {res.get('duration_sec', 0) / 60:5.1f} мин звука за {time.time() - t0:5.0f} с, сегментов {len(res.get('segments', []))}",
              flush=True)
    print(f"готово {done} файлов за {(time.time() - t_all) / 60:.1f} мин")


if __name__ == "__main__":
    main()
