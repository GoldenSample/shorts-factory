# Промпт для LongCat-Avatar 1.5

Источники: README Meituan («User tips for 1.5»), `assets/avatar/*.json`, тред интеграции kijai #1780.
Разбор с цитатами — `shortsmaker/docs/research/longcat/prompting.md`, разделы 1, 2.8, 8.

## Каркас

35–70 слов, одно-три предложения, английский. Слоты по порядку:

1. **Кто + внешность** — `A man in his thirties with short dark hair and a trimmed beard`
2. **Глагол речи** — `is speaking to the camera` (обязателен; в 1.5 официально смягчён, но в образцах есть всегда)
3. **Одежда с одной конкретной деталью** — `wearing a black work T-shirt with a small gold logo on the chest`
4. **Поза** — `standing at a workbench, hands resting on the bench`
5. **Сцена и свет одной фразой** — `in a PC workshop with warm overhead light and a glowing gaming PC behind him`
6. **Хвост про атмосферу** — `creating a calm, confident, hands-on mood`

Официальный образец (одиночный): *«A western man stands on stage under dramatic lighting, holding a microphone close to their mouth. Wearing a vibrant red jacket with gold embroidery, the singer is speaking while smoke swirls around them, creating a dynamic and atmospheric scene.»*

## Правила

- **Кадрирование через предметы, не через камеру.** kijai на жалобу «камера сама наезжает»: опиши то, что не даст наехать — одежду; если ростовой план, то обувь. Негатив-промпт наезд не лечит.
- **Камера первым словом только для двоих:** `Static camera,`. В одиночном образце камеры нет вообще.
- **Постоянный блок внешности ведущего** — один и тот же дословно во всех роликах. Это дешёвый якорь личности вместо файнтюна.
- Не описывать то, чего нет на опорном кадре: модель следует кадру, промпт с ним не спорит, а дополняет (свет, настроение, действие).
- Негатив — вшитый китайский набор `LONGCAT_NEG` из `home_gen.py`: без запрета лиц и рук, они тут предмет съёмки.

## Заготовки GSPC

Ведущий мастерской (поясной план, стол держит кадр):
> A man in his thirties with short dark hair and a trimmed beard is speaking to the camera. He wears a black work T-shirt with a small gold logo on the chest, standing at a metal workbench with his hands resting on it. Behind him a PC workshop with warm overhead light and an open gaming PC glowing softly, creating a calm, confident, hands-on mood.

Разбор новости (ближе, серьёзнее):
> The same man with short dark hair and a trimmed beard is speaking directly to the camera with a serious expression. He wears a black work T-shirt with a small gold logo, his shoulders and collar filling the lower frame. A dark workshop wall with a single warm lamp behind him, creating a focused, editorial mood.

Мотокот (тест 22.09, работает):
> A ginger tabby cat wearing a black leather biker jacket and an open-visor motorcycle helmet sits upright on a sport motorcycle, facing the camera and talking, mouth and whiskers moving in sync with the speech, city street at dusk behind him, neon reflections on the fuel tank, eye-level medium shot, cinematic lighting, realistic fur detail

## Два голоса

- Режим только **с опорным кадром** (ai2v); без кадра двоих модель не умеет.
- `para` — говорят одновременно, дорожки **равной длины** (иначе assert).
- `add` — по очереди: сначала person1, потом person2, длина = сумма реплик, тишина добивается сама.
- Кто где — через `ref_target_masks` из bbox. Формат **[y_min, x_min, y_max, x_max]**, не привычный x1y1x2y2 — частая причина «говорит не тот».
- Без bbox кадр делится пополам по вертикали (лево/право). Для нашей вертикали 9:16 с людьми друг над другом — bbox задавать руками.
- Молчащие на фоне — `bbox.others`, им подаётся тишина, чтобы не шевелили ртом.

## Русская речь

Чужих замеров липсинка на русском нет ни у кого (проверено 22.09). Архитектурный аргумент в нашу пользу: Whisper-large-v3 многоязычный, в отличие от китайского wav2vec2 в 1.0. Наш тест на «мотокоте»: рот ходит в такт, по звукам не попадает. Проверять на «м», «п», «б» (рот должен закрыться) и на «щ», «ж», «ы», «ю». Рычаги по порядку: `audio_scale` 1.2–1.5 → `audio_cfg_scale` 3–4 (×2 времени) → темп речи в TTS медленнее.
