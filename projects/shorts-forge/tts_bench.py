# -*- coding: utf-8 -*-
"""Бенч всех TTS, что стоят у нас (и облачных эталонов), на одних фразах и одних судьях. 29.09.2026.

Наборы (work_voice_gor/bench/suites.json):
  A     24 фразы Гора вне обучения, текст в произносимой записи; есть живая запись каждой фразы
  Braw  16 железячных фраз как пишет редактор («RTX 5090», «1.30 В»)
  Bnorm те же 16 через словарь Гора (gor_normalize)
Движки (каждый в своём окружении):
  gor_v3 gor_v2 qwen_icl qwen_cv_<Голос>      venv qwen-tts
  chatterbox silero_<голос>                    venv chatterbox
  omnivoice                                    любой python с requests (сервер VoiceStudio на :3900)
  grok_<голос> edge_<голос>                    системный python (media-forge, edge-tts)
  xai_igor                                     генерируется на VPS (ключ консоли там), сюда копией
  voxcpm2                                      venv C:/Apps/voxcpm (OpenBMB, 11.11.2026), клон эталона Э04
  drama3                                       python fish-speech, сервер :8090 поднят по skills/drama3-voice, эталон Э04
Наборы экзамена ударений (11.11): X = exam_truth.tsv (60), T = traps_truth.tsv (20), текст без знаков ударения,
  wav в work_voice_gor/stress/exam_<движок> и <движок>_traps (там их слушает gemini_stress_judge.py voice).
Судьи:
  gcer   (venv gigaam)   CER GigaAM-v3 против произносимого эталона, все наборы
  score  (venv chatterbox + исходники omnivoice) сходство WavLM-ECAPA с Гором, UTMOS, темп — набор A
  report (любой python)  сводная таблица work_voice_gor/bench/REPORT.md

  <venv>\\python tts_bench.py gen <движок> [--suites A,Braw,Bnorm]
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
B = HERE / "work_voice_gor" / "bench"
SUITES = json.loads((B / "suites.json").read_text(encoding="utf-8"))
CKPT = {"gor_v3": r"C:\Apps\voice-models\gor-qwen-v3\best",
        "gor_v2": r"C:\Apps\voice-models\gor-qwen-v2\checkpoint-epoch-2",
        "gor_v4e2": r"C:\Apps\voice-models\gor-qwen-v4\checkpoint-epoch-2",
        "gor_v5e1": r"C:\Apps\voice-models\gor-qwen-v5\checkpoint-epoch-1",
        "gor_v5e2": r"C:\Apps\voice-models\gor-qwen-v5\checkpoint-epoch-2",
        "base": r"H:\comfy-models\TTS\Qwen3-TTS-12Hz-1.7B-Base",
        "cv": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"}
for _e in range(6):                    # 03.10: v5b = школа + голос Гора с lr 5e-6, чекпоинт на каждую эпоху
    CKPT[f"gor_v5b_e{_e}"] = rf"C:\Apps\voice-models\gor-qwen-v5b\checkpoint-epoch-{_e}"
    CKPT[f"gor_v6a_e{_e}"] = rf"C:\Apps\voice-models\gor-qwen-v6a\checkpoint-epoch-{_e}"   # школа + знак на 100 % слов
    CKPT[f"gor_v6b_e{_e}"] = rf"C:\Apps\voice-models\gor-qwen-v6b\checkpoint-epoch-{_e}"   # как v4, знак на 100 % слов
FF = os.environ.get("FFMPEG", "ffmpeg")
DRAMA_REF = Path(r"H:\tts-models\drama-3\refs\gor_ref.wav")      # канон Э04 (drama3-voice: «драма олд пока канон»)
VOX = r"H:\tts-models\voxcpm2"                                     # VoxCPM2 OpenBMB, Apache-2.0 (11.11.2026)
ST = HERE / "work_voice_gor" / "stress"
STRESS_SUITES = {"X": ("exam_truth.tsv", "exam_{}"), "T": ("traps_truth.tsv", "{}_traps")}
for _k, (_tsv, _) in STRESS_SUITES.items():
    SUITES[_k] = [{"name": a, "text": b.replace("\u0301", "")} for a, b in
                  (ln.split("\t", 1) for ln in (ST / _tsv).read_text(encoding="utf-8").splitlines() if ln.strip())]
CONDITIONS: dict = {}            # условия прогона (эталон, флаги движка): timing.json["_conditions"]
OWN_PIDS: set = set()            # свои процессы на карте (стенд и сервер Drama); прочие тяжёлые = чужой сосед


def gpu_foreign() -> list[str]:
    """Чужая работа на карте во время фразы (монополия меряется в прогоне, не со слов). По канону rig_safe free-vram
    ComfyUI и Ollama живут, но пустые: у ComfyUI пустая очередь, у Ollama нет загруженных моделей. Прочий тяжёлый
    процесс на карте (python, llama) = сосед. Опрос упал = монополия не доказана, критерий честно падает."""
    import urllib.request

    def get(url: str) -> dict:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read())
    try:
        r = subprocess.run(["nvidia-smi", "--query-compute-apps=pid,process_name", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=10)
    except Exception as e:
        return [f"nvidia-smi: {type(e).__name__}"]
    own = OWN_PIDS | {os.getpid(), os.getppid()}
    out, ollama_on_gpu = [], False
    for ln in r.stdout.splitlines():
        pid, _, name = ln.partition(",")
        if not pid.strip().isdigit() or int(pid) in own or not re.search(r"python|ollama|llama|comfy", name, re.I):
            continue
        if re.search(r"ollama", name, re.I):
            ollama_on_gpu = True
        elif re.search(r"comfy", name, re.I):
            try:
                q = get("http://127.0.0.1:8188/queue")
                if q.get("queue_running") or q.get("queue_pending"):
                    out.append(f"{pid.strip()} ComfyUI: задач {len(q.get('queue_running', []))}+{len(q.get('queue_pending', []))}")
            except Exception as e:
                out.append(f"{pid.strip()} ComfyUI молчит ({type(e).__name__})")
        else:
            out.append(f"{pid.strip()} {Path(name.strip()).name}")
    try:
        out += [f"Ollama: загружена {m.get('name')}" for m in get("http://10.77.0.2:11434/api/ps").get("models", [])]
    except Exception as e:
        if ollama_on_gpu:
            out.append(f"Ollama на карте молчит ({type(e).__name__})")
    return out


def slot_holder() -> str:
    try:
        return json.loads(Path(r"C:\CLAUD\tools\autostart\_gpu_slot.json").read_text(encoding="utf-8")).get("who", "?")
    except Exception as e:
        return f"нет ({type(e).__name__})"


def vram_used() -> int:
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=10)
        return int(r.stdout.split()[0])
    except Exception:
        return 0


def items(suites: list[str]) -> list[dict]:
    return [it for s in suites for it in SUITES[s]]


def run_engine(engine: str, suites: list[str], synth, base_vram: int | None = None) -> None:
    """synth(text) -> (np.float32 wav, sr). Наборы A/Braw/Bnorm пишутся в bench/<движок>, X и T в stress/ (11.11)."""
    groups: dict = {}
    for s in suites:
        d = ST / STRESS_SUITES[s][1].format(engine) if s in STRESS_SUITES else B / engine
        groups.setdefault(d, []).append(s)
    for d, ss in groups.items():
        _run_dir(d, ss, synth, base_vram)


def _run_dir(d: Path, suites: list[str], synth, base_vram: int | None = None) -> None:
    """Пишет wav и timing.json (секунды счёта против секунд звука) после КАЖДОЙ фразы: падение не теряет таймер."""
    import numpy as np
    import soundfile as sf
    d.mkdir(parents=True, exist_ok=True)
    tpath = d / "timing.json"
    timing = json.loads(tpath.read_text(encoding="utf-8")) if tpath.exists() else {}
    base_vram = timing.get("_vram_before_mb") or base_vram or vram_used()
    timing["_vram_before_mb"] = base_vram
    if CONDITIONS:
        timing["_conditions"] = CONDITIONS
    timing["_slot_start"] = slot_holder()
    foreign = set(timing.get("_foreign_gpu", []))
    peak = timing.get("_vram_peak_mb", 0)
    for it in items(suites):
        p = d / f"{it['name']}.wav"
        if p.exists():
            continue
        t0 = time.time()
        try:
            w, sr = synth(it["text"])
        except Exception as e:
            print(f"  {it['name']}: ОШИБКА {type(e).__name__}: {str(e)[:120]}")
            timing[it["name"]] = {"error": str(e)[:200]}
            continue
        dt = time.time() - t0
        w = np.asarray(w, dtype=np.float32).reshape(-1)
        sf.write(p, w, sr)
        timing[it["name"]] = {"compute": round(dt, 3), "audio": round(len(w) / sr, 3)}
        peak = max(peak, vram_used())
        foreign.update(gpu_foreign())          # сосед на карте во время фразы портит RTF и пик (drama3-voice)
        timing["_vram_peak_mb"], timing["_foreign_gpu"] = peak, sorted(foreign)
        tpath.write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {it['name']}: {dt:.1f} с счёта на {len(w) / sr:.1f} с звука", flush=True)
    timing["_vram_peak_mb"] = peak
    timing["_slot_end"] = slot_holder()
    tpath.write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")


# ------------------------------------------------------------ движки

def eng_qwen(engine: str):
    import torch
    from qwen_tts import Qwen3TTSModel
    if engine.startswith("gor_") and engine in CKPT:
        m = Qwen3TTSModel.from_pretrained(CKPT[engine], device_map="cuda", dtype=torch.bfloat16, attn_implementation="sdpa")
        if (Path(CKPT[engine]) / "STRESS_MARKS").exists():      # v4+: текст как в канале, словарь и знаки ударения
            from gor_normalize import normalize
            from gor_stress import accent
            return lambda t: _first(m.generate_custom_voice(text=accent(normalize(t)), speaker="gor", language="Auto"))
        return lambda t: _first(m.generate_custom_voice(text=t, speaker="gor", language="Auto"))
    if engine == "qwen_icl":
        m = Qwen3TTSModel.from_pretrained(CKPT["base"], device_map="cuda", dtype=torch.bfloat16, attn_implementation="sdpa")
        pr = m.create_voice_clone_prompt(ref_audio=SUITES["ref_wav"], ref_text=SUITES["ref_text"])
        return lambda t: _first(m.generate_voice_clone(text=t, language="Russian", voice_clone_prompt=pr))
    if engine.startswith("qwen_cv_"):
        spk = engine.split("_", 2)[2]
        m = Qwen3TTSModel.from_pretrained(CKPT["cv"], device_map="cuda", dtype=torch.bfloat16, attn_implementation="sdpa")
        return lambda t: _first(m.generate_custom_voice(text=t, speaker=spk, language="Russian"))
    raise SystemExit(engine)


def _first(res):
    wavs, sr = res
    return wavs[0], sr


def eng_chatterbox():
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    tts = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
    tts.prepare_conditionals(SUITES["ref_wav"], exaggeration=0.5)

    def synth(t):
        # хотфикс #504/#455 для 0.1.7: хуки анализатора выравнивания копятся между вызовами и ведут к дрейфу
        try:
            for layer in tts.t3.tfmr.layers:
                layer.self_attn._forward_hooks.clear()
        except Exception:
            pass
        with torch.inference_mode():
            w = tts.generate(t, language_id="ru", cfg_weight=0.5, temperature=0.7)
        return w.squeeze(0).cpu().numpy(), tts.sr
    return synth


def eng_silero(spk: str):
    import torch
    m = torch.package.PackageImporter(r"C:\Apps\comfy\silero\v4_ru.pt").load_pickle("tts_models", "model")
    m.to(torch.device("cpu"))

    def synth(t):
        t = re.sub(r"[A-Za-z0-9]+", "", t) if re.search(r"[A-Za-z0-9]", t) else t   # silero латиницу и цифры не читает
        w = m.apply_tts(text=t[:900] or "пусто", speaker=spk, sample_rate=48000, put_accent=True, put_yo=True)
        return w.numpy(), 48000
    return synth


def eng_omnivoice():
    import io
    import requests
    import soundfile as sf

    def synth(t):
        with open(SUITES["ref_wav"], "rb") as fh:
            r = requests.post("http://localhost:3900/generate", timeout=600,
                              data={"text": t, "language": "ru", "ref_text": SUITES["ref_text"]},
                              files={"ref_audio": ("ref.wav", fh, "audio/wav")})
        r.raise_for_status()
        w, sr = sf.read(io.BytesIO(r.content), dtype="float32")
        return (w.mean(axis=1) if w.ndim > 1 else w), sr
    return synth


def _mp3_to_wav(raw: bytes):
    import io
    import soundfile as sf
    p = subprocess.run([FF, "-v", "error", "-i", "pipe:0", "-f", "wav", "-ar", "24000", "-ac", "1", "pipe:1"],
                       input=raw, capture_output=True, check=True)
    w, sr = sf.read(io.BytesIO(p.stdout), dtype="float32")
    return w, sr


def eng_grok(voice: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location("mf", r"C:\CLAUD\projects\media-forge\media.py")
    mf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mf)
    return lambda t: _mp3_to_wav(mf.call("/v1/tts", {"text": t, "voice": voice, "language": "ru"}))


def eng_edge(voice: str):
    import asyncio
    import edge_tts

    def synth(t):
        async def go():
            buf = b""
            async for ch in edge_tts.Communicate(t, voice).stream():
                if ch["type"] == "audio":
                    buf += ch["data"]
            return buf
        return _mp3_to_wav(asyncio.run(go()))
    return synth


def _ref_cond() -> dict:
    import hashlib
    import soundfile as sf
    return {"ref": str(DRAMA_REF), "ref_sha256": hashlib.sha256(DRAMA_REF.read_bytes()).hexdigest(),
            "ref_dur": round(sf.info(str(DRAMA_REF)).duration, 1), "takes": "одна попытка на фразу, без отбора по ASR"}


def eng_voxcpm2(engine: str):
    """VoxCPM2 клоном «ultimate»: эталон отдельным входом + эталон с текстом продолжением. На Windows нужен
    TORCHINDUCTOR_USE_STATIC_CUDA_LAUNCHER=0 (иначе torch.compile падает OverflowError, дым 11.11)."""
    if os.environ.get("VOXCPM2_BENCH") != "1":     # замок боковой двери: VoxCPM2 только замер, в прод без слова Гора нельзя
        raise SystemExit("VoxCPM2 = только стенд: без VOXCPM2_BENCH=1 не запускаю (прод-голос Drama 3, закон 14.10)")
    import numpy as np
    import torch
    from voxcpm import VoxCPM
    opt = os.environ.get("VOX_OPT", "1") == "1"
    cfg, steps, seed = 2.0, 10, 1111
    m = VoxCPM.from_pretrained(VOX, load_denoiser=False, local_files_only=True, optimize=opt)
    lab = DRAMA_REF.with_suffix(".lab").read_text(encoding="utf-8").strip()
    sr = m.tts_model.sample_rate

    def synth(t):
        w = m.generate(text=t, reference_wav_path=str(DRAMA_REF), prompt_wav_path=str(DRAMA_REF), prompt_text=lab,
                       cfg_value=cfg, inference_timesteps=steps, seed=seed)
        return np.asarray(w, dtype=np.float32), sr
    t0 = time.time()
    for _ in range(2):                  # прогрев: компиляция torch.compile не входит в RTF фраз
        synth("Прогрев модели перед замером, одна короткая фраза.")
    CONDITIONS.update(_ref_cond(), engine=engine, weights=VOX, mode="ultimate: reference_wav + prompt_wav + prompt_text",
                      optimize=opt, cfg=cfg, steps=steps, seed=seed, sr=sr, torch=torch.__version__,
                      TORCHINDUCTOR_USE_STATIC_CUDA_LAUNCHER=os.environ.get("TORCHINDUCTOR_USE_STATIC_CUDA_LAUNCHER"),
                      warmup_s=round(time.time() - t0, 1), gpu=torch.cuda.get_device_name(0))
    return synth


def eng_drama3():
    """Drama 3 через сервер fish-speech :8090 тем же запросом, что прод drama_voice.py (эталон, предел шагов кодека),
    но текст набора как есть, без своей нормализации. Флаги сервера передаются тем же запуском в окружении."""
    import io
    import numpy as np
    import ormsgpack
    import requests
    import soundfile as sf
    url = "http://127.0.0.1:8090/v1/tts"
    ref = {"audio": DRAMA_REF.read_bytes(), "text": DRAMA_REF.with_suffix(".lab").read_text(encoding="utf-8").strip()}
    flags = {k: os.environ.get(k) for k in ("FISH_DRAMA3_GPU_EXPERT_LAYERS", "FISH_DRAMA3_CUDA_GRAPH")}
    if None in flags.values():
        raise SystemExit(f"нет флагов сервера в окружении: {flags}")
    ps = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_Process | Where-Object { "
                         "$_.CommandLine -like '*api_server.py*8090*' } | ForEach-Object { $_.ProcessId }"],
                        capture_output=True, text=True, timeout=120)
    pids = sorted(int(x) for x in ps.stdout.split() if x.strip().isdigit())
    if not pids:
        raise SystemExit("сервер Drama :8090 по командной строке не найден")
    OWN_PIDS.update(pids)                  # процессы сервера свои: соседом на карте не считаются
    CONDITIONS.update(_ref_cond(), engine="drama3", url=url, cap="int(21.5 * (len(text) / 11 + 1.5))",
                      server_pids=pids, **flags)

    def synth(t):
        cap = int(21.5 * (len(t) / 11.0 + 1.5))
        r = requests.post(url, data=ormsgpack.packb({"text": t, "references": [ref], "format": "wav", "max_new_tokens": cap}),
                          headers={"Content-Type": "application/msgpack"}, timeout=1800)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} {r.text[:200]}")
        w, sr = sf.read(io.BytesIO(r.content), dtype="float32")
        return (w.mean(axis=1) if w.ndim > 1 else w), sr
    return synth


def make(engine: str):
    if engine.startswith("voxcpm2"):
        return eng_voxcpm2(engine)
    if engine == "drama3":
        return eng_drama3()
    if engine.startswith(("gor_", "qwen_")):
        return eng_qwen(engine)
    if engine == "chatterbox":
        return eng_chatterbox()
    if engine.startswith("silero_"):
        return eng_silero(engine.split("_", 1)[1])
    if engine == "omnivoice":
        return eng_omnivoice()
    if engine.startswith("grok_"):
        return eng_grok(engine.split("_", 1)[1])
    if engine.startswith("edge_"):
        return eng_edge({"dmitry": "ru-RU-DmitryNeural", "svetlana": "ru-RU-SvetlanaNeural"}[engine.split("_", 1)[1]])
    raise SystemExit(f"нет движка {engine}")


# ------------------------------------------------------------ судьи

def gcer() -> None:
    import gigaam
    from voice_eval import cer_str
    m = gigaam.load_model("v3_rnnt", download_root=r"C:\Users\Administrator\.cache\gigaam")
    refs = {it["name"]: it["ref"] for s in ("A", "Braw", "Bnorm") for it in SUITES[s]}
    for d in sorted(p for p in B.iterdir() if p.is_dir() and not p.name.startswith("_")):
        out_p = d / "cer.json"
        done = json.loads(out_p.read_text(encoding="utf-8")) if out_p.exists() else {}
        for w in sorted(d.glob("*.wav")):
            if w.stem in done or w.stem not in refs:
                continue
            hyp = m.transcribe(str(w)).text
            done[w.stem] = {"cer": round(cer_str(refs[w.stem], hyp), 4), "hyp": hyp}
        out_p.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  {d.name}: CER по {len(done)} файлам")


def score() -> None:
    import librosa
    import numpy as np
    import torch
    from omnivoice.eval.models.ecapa_tdnn_wavlm import ECAPA_TDNN_WAVLM
    from omnivoice.eval.models.utmos import UTMOS22Strong
    from omnivoice.eval.utils import load_waveform
    M = Path(r"C:\Apps\tts_eval_models")
    dev = torch.device("cuda")
    sv = ECAPA_TDNN_WAVLM(feat_dim=1024, channels=512, emb_dim=256, sr=16000,
                          ssl_model_path=str(M / "speaker_similarity" / "wavlm_large") + os.sep)
    sv.load_state_dict(torch.load(M / "speaker_similarity" / "wavlm_large_finetune.pth", map_location="cpu")["model"],
                       strict=False)
    sv.to(dev).eval()
    mos = UTMOS22Strong()
    mos.load_state_dict(torch.load(M / "mos" / "utmos22_strong_step7459_v1.pt", map_location="cpu"))
    mos.to(dev).eval()
    vow = set("аеёиоуыэюя")

    @torch.no_grad()
    def emb(p):
        return sv([load_waveform(str(p), 16000, device=dev, max_seconds=60)])

    def slen(p):
        w, sr = librosa.load(str(p), sr=16000)
        w, _ = librosa.effects.trim(w, top_db=35)
        return len(w) / sr

    A = SUITES["A"]
    real = {it["name"]: emb(it["real"]) for it in A}
    cen = torch.nn.functional.normalize(torch.cat(list(real.values())).mean(0, keepdim=True), dim=-1)
    for d in sorted(p for p in B.iterdir() if p.is_dir() and not p.name.startswith("_")):
        sp, sc, ms, rt = [], [], [], []
        for it in A:
            w = d / f"{it['name']}.wav"
            if not w.exists():
                continue
            e = emb(w)
            sp.append(float(torch.nn.functional.cosine_similarity(e, real[it["name"]])))
            sc.append(float(torch.nn.functional.cosine_similarity(e, cen)))
            with torch.no_grad():
                ms.append(float(mos(load_waveform(str(w), 16000, device=dev).unsqueeze(0), 16000)))
            rt.append(sum(ch in vow for ch in it["text"].lower()) / max(0.3, slen(w)))
        if sp:
            (d / "score.json").write_text(json.dumps({"sim_pair": float(np.mean(sp)), "sim_centroid": float(np.mean(sc)),
                                                      "utmos": float(np.mean(ms)), "tempo": float(np.mean(rt)), "n": len(sp)},
                                                     indent=1), encoding="utf-8")
            print(f"  {d.name}: SIM {np.mean(sp):.3f} / {np.mean(sc):.3f}, UTMOS {np.mean(ms):.2f}, темп {np.mean(rt):.2f}")


LICENSE = {"gor_v3": "Apache-2.0", "gor_v2": "Apache-2.0", "qwen_icl": "Apache-2.0", "qwen_cv": "Apache-2.0",
           "chatterbox": "MIT", "omnivoice": "CC-BY-NC (веса)", "silero": "CC-BY-NC", "grok": "облако xAI (пул)",
           "edge": "облако Microsoft (серо)", "xai": "облако xAI ($15/млн зн.)",
           "voxcpm2": "Apache-2.0 (код и веса)", "drama3": "Fish Audio Community (до 500 тыс. $ в год)"}


def report() -> None:
    import statistics as st
    rows = []
    for d in sorted(p for p in B.iterdir() if p.is_dir() and not p.name.startswith("_")):
        cer = json.loads((d / "cer.json").read_text(encoding="utf-8")) if (d / "cer.json").exists() else {}
        sc = json.loads((d / "score.json").read_text(encoding="utf-8")) if (d / "score.json").exists() else {}
        tm = json.loads((d / "timing.json").read_text(encoding="utf-8")) if (d / "timing.json").exists() else {}

        def mean_cer(pref):
            v = [x["cer"] for k, x in cer.items() if k.startswith(pref)]
            return (sum(v) / len(v), len(v)) if v else (None, 0)
        a, na = mean_cer("t")
        br, _ = mean_cer("h")
        bn, _ = mean_cer("n")
        rtf = [x["compute"] / x["audio"] for k, x in tm.items() if not k.startswith("_") and "compute" in x and x["audio"] > 0]
        fam = next((k for k in LICENSE if d.name.startswith(k)), d.name)
        rows.append({"engine": d.name, "cer_A": a, "cer_Braw": br, "cer_Bnorm": bn, "n": na,
                     "sim_pair": sc.get("sim_pair"), "sim_centroid": sc.get("sim_centroid"), "utmos": sc.get("utmos"),
                     "tempo": sc.get("tempo"), "rtf": st.median(rtf) if rtf else None,
                     "vram": (tm.get("_vram_peak_mb", 0) - tm.get("_vram_before_mb", 0)) if tm.get("_vram_peak_mb") else None,
                     "license": LICENSE.get(fam, "?")})
    REAL_SIM, REAL_TEMPO = 0.686, 4.73        # живой Гор: сходство между его разными фразами и темп (замер 29.09)
    pct = lambda v: "-" if v is None else f"{v * 100:.1f}"
    lines = ["Как читать: «ошибок на 100 букв» = сколько букв распознаватель GigaAM услышал не так (меньше = разборчивее); "
             "«похож на Гора» = сходство тембра с его живой записью той же фразы, 100 % = так же похоже, как сам Гор на себя "
             "в другой фразе; «естественность» по шкале 1-5 (у живых записей Гора 2.7 из-за YouTube-звука); "
             "темп у живого Гора 4.7 слога/с; «секунд счёта на секунду звука»: меньше 1 = быстрее реального времени.",
             "",
             "| движок | похож на Гора | ошибок на 100 букв: фразы Гора | железо сырым текстом | железо через словарь | естественность 1-5 | темп, слог/с | секунд счёта на 1 с звука | лицензия |",
             "|---|---|---|---|---|---|---|---|---|"]
    def num(v, fmt):
        return "-" if v is None else format(v, fmt)

    for r in sorted(rows, key=lambda r: (-(r["sim_pair"] or 0), r["cer_A"] or 9)):
        sim = "-" if r["sim_pair"] is None else "%.0f %%" % (r["sim_pair"] / REAL_SIM * 100)
        vram = "-" if not r["vram"] else "%.1f" % (r["vram"] / 1024)
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["engine"], sim, pct(r["cer_A"]), pct(r["cer_Braw"]), pct(r["cer_Bnorm"]),
            num(r["utmos"], ".2f"), num(r["tempo"], ".2f"), num(r["rtf"], ".2f"), r["license"]))
    (B / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    json.dump(rows, open(B / "report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n".join(lines))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1]
    if cmd == "gen":
        eng = sys.argv[2]
        su = sys.argv[sys.argv.index("--suites") + 1].split(",") if "--suites" in sys.argv else ["A", "Braw", "Bnorm"]
        before = int(os.environ.get("VRAM_BEFORE_MB") or vram_used())    # до загрузки модели или до старта сервера
        run_engine(eng, su, make(eng), base_vram=before)
    elif cmd == "gcer":
        gcer()
    elif cmd == "score":
        score()
    elif cmd == "report":
        report()
