# -*- coding: utf-8 -*-
"""Отпечаток голоса диктора кодировщиком диктора из Qwen3-TTS-12Hz-1.7B-Base (только измеритель, синтеза нет).
Замена удалённому VoiceEncoder Chatterbox и WavLM-ECAPA (весов на диске больше нет, 14.10.2026).
Грузится только ветка speaker_encoder из model.safetensors, вход = mel 128 при 24 кГц как в qwen_dataset.py.
  C:/Apps/qwen-tts/.venv/Scripts/python.exe spk_embed.py check   (Гор к Гору против чужих дикторов)"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import librosa
import numpy as np
import torch
from safetensors.torch import load_file

BASE = Path(r"H:\comfy-models\TTS\Qwen3-TTS-12Hz-1.7B-Base")
GOR_WAVS = Path(r"C:\CLAUD\projects\shorts-forge\work_voice_gor\dataset\wavs")
OTHER_WAVS = Path(r"H:\tts_data\school\wavs")


class SpkEmb:
    def __init__(self, device: str = "cuda"):
        import json
        from qwen_tts.core.models.modeling_qwen3_tts import (Qwen3TTSSpeakerEncoder, Qwen3TTSSpeakerEncoderConfig,
                                                             mel_spectrogram)
        self.mel = mel_spectrogram
        cfg = json.loads((BASE / "config.json").read_text(encoding="utf-8"))["speaker_encoder_config"]
        self.enc = Qwen3TTSSpeakerEncoder(Qwen3TTSSpeakerEncoderConfig(**cfg))
        sd = {k[len("speaker_encoder."):]: v for k, v in load_file(str(BASE / "model.safetensors")).items()
              if k.startswith("speaker_encoder.")}
        self.enc.load_state_dict(sd, strict=True)
        self.enc.to(device, torch.float32).eval()
        self.device = device

    @torch.inference_mode()
    def __call__(self, wav: np.ndarray, sr: int) -> np.ndarray:
        if sr != 24000:
            wav = librosa.resample(wav, orig_sr=sr, target_sr=24000)
        m = self.mel(torch.from_numpy(np.ascontiguousarray(wav, dtype=np.float32)).unsqueeze(0), n_fft=1024, num_mels=128,
                     sampling_rate=24000, hop_size=256, win_size=1024, fmin=0, fmax=12000).transpose(1, 2)
        e = self.enc(m.to(self.device)).float().cpu().numpy()[0]
        return e / np.linalg.norm(e)


def check() -> None:
    se = SpkEmb()
    random.seed(1)
    gor = random.sample(sorted(GOR_WAVS.glob("*.wav")), 60)
    oth = sorted(OTHER_WAVS.glob("*.wav"))
    by = {}
    for p in oth:
        by.setdefault(p.stem.rsplit("_", 1)[0], []).append(p)
    spk = sorted(by)
    oth = [q for k in spk for q in random.sample(by[k], min(5, len(by[k])))]
    half = sum(min(5, len(by[k])) for k in spk[:len(spk) // 2])   # фон = первая половина дикторов, проверка = вторая
    emb = lambda ps: np.stack([se(*librosa.load(str(p), sr=24000)) for p in ps])
    G, O = emb(gor), emb(oth)
    c = np.median(G[:30], axis=0); c /= np.linalg.norm(c)
    g_in, o_in = G[30:] @ c, O @ c
    print(f"дикторов чужих {len(by)}; Гор (вне центра) к центру Гора: мин {g_in.min():.3f} медиана {np.median(g_in):.3f}")
    print(f"чужие к центру Гора: медиана {np.median(o_in):.3f} макс {o_in.max():.3f}")
    print("разделение есть" if g_in.min() > o_in.max() else f"ПЕРЕКРЫТИЕ: {int((o_in >= g_in.min()).sum())} чужих выше худшего Гора")
    # центрирование: вычесть средний голос фона (чужие дикторы), сырой косинус у этого кодировщика сжат к 0.9+
    mu = O[:half].mean(axis=0)
    nz = lambda X: (X - mu) / np.linalg.norm(X - mu, axis=-1, keepdims=True)
    Gc, Oc = nz(G), nz(O[half:])
    cc = np.median(Gc[:30], axis=0); cc /= np.linalg.norm(cc)
    g2, o2 = Gc[30:] @ cc, Oc @ cc
    print(f"центрированно (фон = половина чужих дикторов, проверка на другой половине, {len(Oc)} клипов): Гор мин {g2.min():.3f} медиана {np.median(g2):.3f}; "
          f"чужие медиана {np.median(o2):.3f} макс {o2.max():.3f}")
    mu_all = O.mean(axis=0)
    Gall = (G - mu_all) / np.linalg.norm(G - mu_all, axis=-1, keepdims=True)
    cen = np.median(Gall, axis=0); cen /= np.linalg.norm(cen)
    np.savez(GOR_WAVS.parent.parent / "centroid_qwen.npz", centroid=cen, mu=mu_all)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["check"]:
        check()
