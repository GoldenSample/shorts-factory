---
name: qwen-edit-art
description: Арт из настоящего фото на домашней 5090 — Qwen Image Edit 2511 в ComfyUI переносит реальный предмет (провод, карта, корпус ПК) на тёмную студию, не меняя геометрию. Найдено в сессии 18.09.2026 (кадр 12VHPWR для ролика DLSS 5). Звать при словах «арт», «обложка по фото», «перенеси на тёмный фон», «сделай кадр из фото железа», «Qwen Edit», при подготовке обложек и первых экранов из реальной съёмки. Внутри — граф, промпт-каркас, параметры, границы (правило «без ИИ-картинок на сайте»).
---

# Qwen Image Edit: арт по настоящему фото

Откуда: сессия 18.09.2026, скрипт `connector_shot.py` (scratchpad f6e5cfbe…, копия ниже в `reference/connector_shot.py`).
Задача была — кадр разъёма 12VHPWR для ролика DLSS 5, после замечания Гора «ужасный кадр, посмотри как выглядит
настоящий провод»: знакомое зрителю железо **не выдумывается моделью**, берётся настоящее фото, Qwen Edit меняет
только фон и свет. Результат: `/opt/shorts/dl5/ref/conn_dark.png`, сравнение `edit_compare.jpg` (белый стол → чёрная студия, разъём и оплётка те же).

## Где что стоит

Домашняя 5090, ComfyUI :8188 через хаб <VPS_IP> (клиент `shortsmaker/vps/home_gen.py`, `hg.COMFY`).
Модели: `diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors`, `text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors`,
`vae/qwen_image_vae.safetensors`. Нода кодировщика — `TextEncodeQwenImageEditPlus` (входы `clip, prompt, vae, image1..3`), 
запасная `TextEncodeQwenImageEdit` (`image`). Замер 18.09: **55 с** на кадр 720×1280.

## Граф (API-формат ComfyUI)

```
UNETLoader(qwen_image_edit_2511_fp8mixed, default)
CLIPLoader(qwen_2.5_vl_7b_fp8_scaled, type=qwen_image)
VAELoader(qwen_image_vae)
LoadImage(<фото, уже кропнутое под нужный формат>)
TextEncodeQwenImageEditPlus(clip, PROMPT, vae, image1=фото)      → positive
TextEncodeQwenImageEditPlus(clip, "",     vae, image1=фото)      → negative
VAEEncode(фото, vae)                                             → latent (правка поверх исходника, denoise 1.0)
ModelSamplingAuraFlow(model, shift 3.0, sampling flow)
KSampler(seed 12, steps 30, cfg 4.0, euler, simple, denoise 1.0)
VAEDecode → SaveImage(gspc/qedit)
```

Фото сначала кропается ffmpeg под целевой формат (9:16 для роликов: `crop=810:1440:645:0,scale=720:1280`),
потом грузится в `input` через `/upload/image` (см. `_comfy_upload` в `home_gen.py`).

## Промпт-каркас

Три части, в этом порядке, по-английски:

1. **Что НЕ трогать** — перечислить предмет по частям: `Keep this exact power cable, connector, pins, latch and braided sleeving unchanged in shape and position.`
2. **Что заменить** — фон и поверхность: `Replace the white table with a dark matte black studio surface and a near-black background.`
3. **Свет** схемой, не прилагательными: `Low-key product lighting: a warm orange rim light from the right edge outlines the connector and the braided cables, soft reflections on the black plastic.` Хвост: `Photorealistic, sharp, no text.`

Чем подробнее перечислен предмет в части 1, тем меньше модель его «улучшает». Слова «beautiful, epic, 8k» — мусор, убирать.

## Для ПК и обложек

- Корпус/сборка: `Keep this exact PC case, glass panel, fans, graphics card, cables and RGB unchanged...` — перечислить всё видимое, иначе модель дорисует лишний вентилятор.
- Палитра сайта — бумага/латунь/графит; для сайта тёмная студия неуместна, там обложка на светлой бумаге: `Replace the background with a plain warm off-white paper backdrop, soft top light, no shadows harder than the object's own`.
- Для обложки рубрики шортса — тёмная студия и один тёплый контровой, как в связке DLSS 5.

## Границы

- **На сайт ИИ-картинки не идут** (ФИДБЕК 15.09 «слоп лютый»: Grok-обложки сняты). Правка настоящего фото — ретушь: фон, свет, чистка. Дорисовка деталей железа — нет. Формулировку «ретушь да, дорисовка нет» согласовать с Гором до первого выката на сайт.
- Кадр без брака (память `no-defect-frames`): грязь, припой, износ на исходнике → сначала чистый исходник, Qwen не лечит.
- Фото с чужим знаком (Авито) на первом экране не показываем; знак можно убрать этой же моделью как ретушь.
- Лицензия исходного фото: свои снимки или Commons с автором в подписи (12VHPWR был Benlisquare, CC BY-SA 4.0).

## Дальше по конвейеру

Отредактированный кадр → Wan i2v (`hg.wan_graph` + `start_image`) для движения, или ffmpeg `zoompan` как запасной наезд без генерации (в скрипте оба пути). Для аватара — опорный кадр в `longcat-avatar`. Апскейл — нейрорендер :7860.
