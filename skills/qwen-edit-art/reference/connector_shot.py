# -*- coding: utf-8 -*-
"""VPS: финальный кадр по настоящему фото 12VHPWR (Benlisquare, Commons, CC BY-SA 4.0).

Вертикальный кроп вокруг разъёма -> Qwen Image Edit 2511 переносит тот же провод
на тёмную студию (геометрию не трогать) -> Wan 2.2 оживляет. Запасной путь -
плавный наезд ffmpeg по отредактированному кадру."""
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.path.insert(0, "/opt/shorts")
import home_gen as hg

D = "/opt/shorts/dl5"
R = D + "/ref"
log = lambda m: print(time.strftime("[%H:%M:%S] ") + m, flush=True)


def ff(args):
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error"] + args, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("ffmpeg: " + r.stderr[-600:])


# 1. вертикаль 9:16 вокруг разъёма и хвостов
ff(["-i", R + "/ref2.jpg", "-vf", "crop=810:1440:645:0,scale=720:1280", R + "/ref2_v.png"])


def upload(path, name):
    boundary = "----gspc%s" % uuid.uuid4().hex
    data = open(path, "rb").read()
    body = (("--%s\r\nContent-Disposition: form-data; name=\"image\"; filename=\"%s\"\r\n"
             "Content-Type: image/png\r\n\r\n" % (boundary, name)).encode() + data +
            ("\r\n--%s\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n--%s--\r\n"
             % (boundary, boundary)).encode())
    req = urllib.request.Request(hg.COMFY + "/upload/image", data=body,
                                 headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())["name"]


oi = json.loads(urllib.request.urlopen(hg.COMFY + "/object_info", timeout=60).read())
enc = next((n for n in ("TextEncodeQwenImageEditPlus", "TextEncodeQwenImageEdit") if n in oi), None)
log("узел кодировщика: %s; CFGNorm: %s; ImageScaleToTotalPixels: %s"
    % (enc, "CFGNorm" in oi, "ImageScaleToTotalPixels" in oi))
if enc:
    log("входы %s: %s" % (enc, list((oi[enc]["input"].get("required") or {}).keys())
                          + list((oi[enc]["input"].get("optional") or {}).keys())))

src_name = upload(R + "/ref2_v.png", "gspc_ref2_v.png")
PROMPT = ("Keep this exact power cable, connector, pins, latch and braided sleeving unchanged in shape and "
          "position. Replace the white table with a dark matte black studio surface and a near-black background. "
          "Low-key product lighting: a warm orange rim light from the right edge outlines the connector and the "
          "braided cables, soft reflections on the black plastic. Photorealistic, sharp, no text.")
img_key = "image1" if enc == "TextEncodeQwenImageEditPlus" else "image"
g = {
    "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "qwen_image_edit_2511_fp8mixed.safetensors",
                                                 "weight_dtype": "default"}},
    "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
                                                 "type": "qwen_image", "device": "default"}},
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
    "4": {"class_type": "LoadImage", "inputs": {"image": src_name}},
    "5": {"class_type": enc, "inputs": {"clip": ["2", 0], "prompt": PROMPT, "vae": ["3", 0], img_key: ["4", 0]}},
    "6": {"class_type": enc, "inputs": {"clip": ["2", 0], "prompt": "", "vae": ["3", 0], img_key: ["4", 0]}},
    "7": {"class_type": "VAEEncode", "inputs": {"pixels": ["4", 0], "vae": ["3", 0]}},
    "8": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.0, "sampling": "flow"}},
    "9": {"class_type": "KSampler", "inputs": {"model": ["8", 0], "seed": 12, "steps": 30, "cfg": 4.0,
                                               "sampler_name": "euler", "scheduler": "simple", "positive": ["5", 0],
                                               "negative": ["6", 0], "latent_image": ["7", 0], "denoise": 1.0}},
    "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
    "11": {"class_type": "SaveImage", "inputs": {"images": ["10", 0], "filename_prefix": "gspc/qedit"}},
}
r = hg.comfy_run(g, R + "/conn_dark.png", "images", log=log, ext=".png")
log("qwen edit: %.0f с" % r["sec"])

# 3. движение Wan из отредактированного кадра
dark_name = upload(R + "/conn_dark.png", "gspc_conn_dark.png")
wg = hg.wan_graph("Slow smooth camera push-in toward the power connector, the warm rim light glides along "
                  "the braided cables.", width=704, height=1280, frames=121, steps=25, seed=91, prefix="gspc/conn")
wg["30"] = {"class_type": "LoadImage", "inputs": {"image": dark_name}}
wg["31"] = {"class_type": "ImageScale", "inputs": {"image": ["30", 0], "upscale_method": "lanczos",
                                                   "width": 704, "height": 1280, "crop": "center"}}
wg["7"]["inputs"]["start_image"] = ["31", 0]
r2 = hg.comfy_run(wg, D + "/cable_real.mp4", "images", log=log, ext=".mp4")
log("wan по кадру: %.0f с" % r2["sec"])

# 4. запасной: наезд по кадру без генерации движения
ff(["-loop", "1", "-i", R + "/conn_dark.png", "-vf",
    "scale=1296:2304,zoompan=z='min(1+0.0016*on,1.2)':x='iw/2-(iw/zoom/2)':y='ih*0.55-(ih/zoom/2)':d=150:s=1080x1920:fps=30,format=yuv420p",
    "-t", "5", "-c:v", "libx264", "-crf", "16", D + "/cable_push.mp4"])
for n in ("cable_real", "cable_push"):
    ff(["-i", "%s/%s.mp4" % (D, n), "-vf", "select='eq(n\\,5)+eq(n\\,60)+eq(n\\,115)',scale=240:-2,tile=3x1",
        "-frames:v", "1", "-vsync", "vfr", "%s/peek_%s.jpg" % (D, n)])
ff(["-i", R + "/ref2_v.png", "-i", R + "/conn_dark.png", "-filter_complex",
    "[0:v]scale=360:640[a];[1:v]scale=360:640[b];[a][b]hstack", R + "/edit_compare.jpg"])
log("ГОТОВО")
