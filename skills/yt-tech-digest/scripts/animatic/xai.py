# -*- coding: utf-8 -*-
"""Прямые вызовы api.x.ai OAuth-токеном Hermes (картинки Imagine, TTS). Последовательно, с ретраем на 429/5xx."""
import json, time, base64, urllib.request, urllib.error

AUTH = r"C:\Users\Administrator\AppData\Local\hermes\auth.json"
BASE = "https://api.x.ai/v1"

def token():
    d = json.load(open(AUTH, encoding="utf-8"))
    return d["credential_pool"]["xai-oauth"][0]["access_token"]

def _post(path, body, timeout=300, raw=False):
    for attempt in range(4):
        req = urllib.request.Request(BASE + path, data=json.dumps(body).encode("utf-8"), method="POST")
        req.add_header("Authorization", "Bearer " + token()); req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                return data if raw else json.loads(data.decode("utf-8"))
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "ignore")[:300]
            if e.code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(8 * (attempt + 1)); continue
            raise RuntimeError("HTTP %d %s: %s" % (e.code, path, msg))
    raise RuntimeError("retries exhausted")

def image(prompt, out_prefix, n=2, model="grok-imagine-image-2.0", aspect="16:9", resolution=None):
    """Сохраняет out_prefix_1.jpg .. out_prefix_n.jpg. aspect_ratio пробуем параметром, при 4xx — без него."""
    body = {"model": model, "prompt": prompt, "n": n, "response_format": "b64_json"}
    if aspect: body["aspect_ratio"] = aspect
    if resolution: body["resolution"] = resolution
    try:
        j = _post("/images/generations", body)
    except RuntimeError as e:
        if "aspect" in str(e).lower() or "422" in str(e) or "400" in str(e):
            body.pop("aspect_ratio", None); body.pop("resolution", None)
            j = _post("/images/generations", body)
        else:
            raise
    paths = []
    for i, d in enumerate(j.get("data", []), 1):
        b = d.get("b64_json")
        if not b: continue
        p = "%s_%d.jpg" % (out_prefix, i)
        open(p, "wb").write(base64.b64decode(b)); paths.append(p)
    return paths

def tts(text, out_mp3, voice="orion", language="ru"):
    body = {"text": text, "voice_id": voice, "language": language}
    data = _post("/tts", body, raw=True)
    # ответ либо сырой аудиопоток, либо JSON с b64
    if data[:1] in (b"{", b"["):
        j = json.loads(data.decode("utf-8"))
        b = j.get("audio") or j.get("b64_audio") or j.get("data") or ""
        if isinstance(b, dict): b = b.get("b64_json") or b.get("audio") or ""
        data = base64.b64decode(b)
    open(out_mp3, "wb").write(data)
    return out_mp3
