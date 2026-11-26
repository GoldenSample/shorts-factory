# -*- coding: utf-8 -*-
import os, glob, httpx
env = {}
for ln in open("/opt/shorts/console.env", encoding="utf-8"):
    ln = ln.strip()
    if ln and not ln.startswith("#") and "=" in ln:
        k, v = ln.split("=", 1); env[k] = v.strip().strip('"')
h = {"Authorization": "Bearer " + env["XAI_CONSOLE_KEY"], "Content-Type": "application/json"}
total = 0
for tf in sorted(glob.glob("/tmp/deleader/t*.txt")):
    i = int(os.path.basename(tf)[1:3])
    out = "/tmp/deleader/f%02d_igor.mp3" % i
    if os.path.exists(out): continue
    txt = open(tf, encoding="utf-8").read().strip()
    r = httpx.post("https://api.x.ai/v1/tts", headers=h, timeout=200,
                   json={"text": txt, "language": "ru", "voice_id": "xf4r9bqs53rf", "speed": 1.10,
                         "output_format": {"codec": "mp3", "sample_rate": 24000, "bit_rate": 128000}})
    if r.status_code != 200:
        raise SystemExit("TTS %d: %d %s" % (i, r.status_code, r.text[:200]))
    open(out, "wb").write(r.content); total += len(txt)
    print("f%02d ok %d chars" % (i, len(txt)), flush=True)
print("итого знаков:", total, "~$%.3f" % (total / 1e6 * 4.20))
