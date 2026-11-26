---
name: media-forge
description: "Медиа-кузница: картинки/озвучка/видео через Grok Imagine на подписке (не метеред), выдача в Google Drive. Воспроизводимый инструмент media.py (image/tts/video/shot/batch) + карта твиков и калибровка пушки (конкурентность видео=1, b64 обязателен). img2video любого локального кадра РАЗГАДАН 09-19 (edits с response_format=url → video-1.5), и video-1.5 говорит реплику по-русски в губы. Под YouTube-конвейер ИИ-рассказов и арт Лиса/EDS. Звать при: сгенерь картинку/видео/озвучку, медиа под ролик, раскадровка в видеоряд, жечь медиа-квоту. Ещё при: флаги media.py (--v2, --q, --aspect, --res, --refs, --last-frame, --hardware, --passport, --origin, --final), image-2.0, R2V, очередь гейта, MEDIA_GATE=off, паспорт кадра, стоп-кран пула, media_log.jsonl, cost_in_usd_ticks, «почему клип не ушёл», «shot не скачал кадр»."
---

# MEDIA-FORGE: кузница медиа на подписке

Суть: `media.py` бьёт прямо в api.x.ai OAuth-токеном Hermes, каждый вызов проходит стоп-кран общего недельного пула (`media.py:51-53`), каждый клип и стилл встаёт в очередь визуального гейта (`media.py:138`, `:263`, `:350`; mp3 из tts не встаёт, `media.py:266-272`) и получает паспорт кадра, если вырос из кадра на диске (`media.py:201-209`).

## Что и где

| Что | Где | Источник |
|---|---|---|
| Инструмент | риг, `C:\CLAUD\projects\media-forge\media.py` | `CHANNELS.md:41` |
| Токен | `C:/Users/Administrator/AppData/Local/hermes/auth.json`, ключ `providers.xai-oauth` (значение не печатать) | `media.py:18`, `:25-26` |
| Рефреш токена | при 401 пинок локального прокси `http://127.0.0.1:8645/v1/models`, перечитать auth.json | `media.py:23`, `:28-35`, `:60-63` |
| Прокси | по требованию: задача Планировщика `HermesProxy` в Disabled с 03.08 (решение Гора), пустой 8645 значит «не поднят»; поднять `powershell -ExecutionPolicy Bypass -NoProfile -File C:\CLAUD\projects\win-forge\tools\stack.ps1 -Start proxy`, запасной путь `"%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\hermes.exe" proxy start --provider xai` (бинарь не на PATH) | `CHANNELS.md:8-9`; `projects/media-forge/proxy-start.cmd:2-5`; скил `hermes-proxy-service` |
| Медиа мимо прокси | прокси форвардит только 5 текстовых путей | `MEDIA-FORGE.md:13`, `CHANNELS.md:43` |
| Выдача | `G:\Мой диск\media-forge\` (DriveFS), если нет диска G, то `out\` рядом с media.py; имя `ММДД_ЧЧММСС.ext` | `media.py:20-22`, `:106-107`, `CHANNELS.md:44` |
| Журнал | `media_log.jsonl` рядом с media.py (в .gitignore, в репо нет) | `media.py:19`, `:101-104`, `projects/media-forge/.gitignore:3` |
| Счётчик пула | `tools/pool_ledger.py` (`guard`, `log_call`) | `media.py:37-49`, `:66-73` |
| Очередь гейта | `tools/gate_queue.py`, файл `projects/media-forge/gate_queue.jsonl` | `media.py:181-199`, `tools/gate_queue.py:26` |
| Паспорт кадра | `tools/frame_origin.py`, `<кадр>.origin.json` | `media.py:201-216`, `skills/video-toolkit/SKILL.md:54` |

## Как вызвать

```
python media.py image "промпт" [--n 4] [--out f.jpg] [--image-url src]       # старая линия grok-imagine-image, b64
python media.py image "промпт" --v2 [--q low|medium] [--aspect 9:16] [--res 2k]  # grok-imagine-image-2.0
python media.py image "промпт" --quality                                    # тоже image-2.0 (quality medium)
python media.py tts "текст" [--lang ru] [--voice default]                   # озвучка mp3
python media.py video "промпт" [--model grok-imagine-video-1.5] [--duration N] [--resolution 720p] [--aspect 9:16]
python media.py video "промпт" --model grok-imagine-video-1.5 --image-url кадр.jpg [--last-frame конец.jpg]
python media.py video "промпт <IMAGE_1>" --model grok-imagine-video-1.5 --refs облик.png
python media.py shot "промпт-кадра" --anim "движение" [--q medium] [--image-model ...] [--passport ..] [--final]  # текст→кадр→оживление 1.5
python media.py batch очередь.json                                          # строго последовательно
```

| Флаг | Что делает | Источник |
|---|---|---|
| `--v2` | модель `grok-imagine-image-2.0` | `media.py:356`, `:366` |
| `--n` | картинок за вызов, по умолчанию 1, API до 10 | `media.py:356`, `MEDIA-FORGE.md:16` |
| `--quality` | теперь = image-2.0, а не снятый slug image-quality (сняли: с 02.11.2026 slug отвечает 2.0 на low) | `media.py:115-118`, `:308-309` |
| `--model` | перебивает `--v2`/`--quality`; у video выбор `grok-imagine-video`, `-1.5`, `-1.5-lite` | `media.py:114`, `:358` |
| `--q` | quality для 2.x, по умолчанию medium (без поля API даёт low); `high` API отвергает с 10.10, код ставит medium | `media.py:86`, `:92-94` |
| `--aspect`, `--res` | для 2.x кладутся в тело (`aspect_ratio`, `resolution` 1k/2k); у старой линии не кладутся, WARN | `media.py:95-98` |
| `--image-url` (video) | I2V: локальный файл идёт рецептом edits→URL, http как есть | `media.py:165-174`, `:236` |
| `--refs` | R2V: `reference_images`, файл = data-URI, в промпте `<IMAGE_1>..` | `media.py:176-179`, `:237`, `:359` |
| `--last-frame` | закреплённый последний кадр, тем же рецептом URL | `media.py:238` |
| `--hardware` | железо в кадре: ниже 720p ОТКАЗ без `--low-res-reason` (video и shot) | `media.py:226-228`, `:311-313` |
| `--passport`, `--final` (video и shot), `--origin` (только video) | паспорт гейта со строкой ЗАДУМАНО, финалист первым в очереди; `--origin` = стилл с proof, из которого выведен клип | `media.py:359`, `:363`, `tools/gate_queue.py:202` |
| `--confirm` | no-op, флаг совместимости | `media.py:222-223`, `CHANNELS.md:43` |

Batch-JSON: поля `type`, `prompt`/`text`, `model`, `q`, `aspect_ratio`, `resolution`, `image_url`, `refs`, `last_frame`, `hardware`, `low_res_reason`, `passport`, `origin`, `final` (`media.py:283-296`). 1.5 без `image_url` и без `refs` в батче откатывается на `grok-imagine-video` (`media.py:288-289`).

Кириллица в промпте с командной строки Windows иногда бьётся: длинные промпты класть файлом или гнать из git bash.

## Как проверить «живо»

| Команда (на риге, из `C:\CLAUD`) | Ждём | Источник |
|---|---|---|
| `py -3.12 projects\media-forge\media.py image "тест"` | `OK image -> G:\Мой диск\media-forge\....jpg (N байт, пул-эквив ~$...)` и строка «в очереди гейта» | `media.py:131`, `:197` |
| `py -3.12 tools\pool_ledger.py budget show` | оценка пула и остаток до порогов, либо «стоп-кран не взведён» | `tools/pool_ledger.py:14-18`, `:120-123` |
| `py -3.12 tools\gate_queue.py list` | клипы и стиллы со статусами | `tools/gate_queue.py:10` |

Не проверено: живой прогон не подтверждён, дата последнего зелёного прогона в репо не записана. Вид вызова `py -3.12` взят по `tools/gate_queue.py:8-12`; шапка `media.py:6-10` пишет `python`, код только stdlib (`media.py:15`).

## Карта пушки (замеры)

| Канал | Закон | Источник |
|---|---|---|
| Картинки `POST /v1/images/generations` | `response_format: b64_json` обязателен: temp-URL `imgen.x.ai` за Cloudflare, urllib без браузерного UA получает 403 | `media.py:121`, `CHANNELS.md:87` |
| Старая линия `grok-imagine-image` | `aspect_ratio` = 422 (07-07), кадр правит промпт | `media.py:87`, `:119-120` |
| 2.x | quality, aspect_ratio, resolution живые; 2.0 детальнее, ~4x медленнее (23 с против 6 с) | `media.py:81`, `:356` |
| Озвучка `POST /v1/tts` | поле `language` обязательно (иначе 422) | `media.py:268`, `MEDIA-FORGE.md:9` |
| Видео `POST /v1/videos/generations` | `request_id`, поллинг `GET /v1/videos/{id}` раз в 6 с до 900 с, ассет в `video.url` | `media.py:141-158`, `:246` |
| Поле картинки в видео | `image: {url}`, плоское `image_url` отвергается (зонд 07-27) | `media.py:234-236` |
| Модели видео | video ≤10 с (без `--duration` фактически 8 с), 1.5 ≤15 с; разрешения 480p/540p/720p/1080p, по умолчанию 720p; aspect по умолчанию 16:9 | `media.py:231-232`, `MEDIA-FORGE.md:23`, `:29` |
| video-1.5 | T2V, I2V, R2V (до 7 референсов), пин первого и последнего кадра; прежнее «1.5 только image→video» устарело | docs.x.ai reference-to-video по прежней редакции `git show 7120ee95:skills/media-forge/SKILL.md` строка 36; `media.py:237-238` |
| Конкурентность видео | закон кода = 1, батч последовательный (замер 07-07: параллель = 429) | `media.py:275-278` |
| Лимит запросов | заголовок `x-ratelimit-limit-requests: 80`, не узкое место (замер 07-07) | `MEDIA-FORGE.md:28` |

Расхождение: `skills/grok-machine/references/media.md:14` пишет, что за сессию до 4 видеозадач одновременно прошли без 429. Код держит 1 (`media.py:275-278`).

## Разгадано 2026-09-19: img2video любого локального кадра + речь в губы

**Приём:** локальный кадр → `/v1/images/edits` (model `grok-imagine-image-2.0`, prompt «Keep this image exactly as it is... Change nothing.», `image.url` = data-uri, **`response_format: "url"`**) → свежий URL на серверах xAI → сразу в `grok-imagine-video-1.5` как `image.url` (протухает за минуты). Edits держит кадр пиксель-в-пиксель (замер 09-06). Реализовано в `media.py:165-174`. Облик персонажа держит 8-10 с (замер на маскотах).

**Речь:** реплика в промпте («...speaks in Russian, lips clearly synced to the words: «...»» + описание голоса) → video-1.5 сам говорит по-русски в губы. Whisper распознал пробные реплики как ru 1.0, одну дословно. Системные оговорки (одно слово 3 раза из 3) лечатся переписыванием реплики, не перегенерацией.

**Голос закрепляется (19.09, дока + замер):** video-1.5 принимает `reference_audios: [{"voice_id": "eve"}]`, до 3 пресетов из ростера TTS (GET /v1/tts/voices = 28 голосов), в промпте тег `<AUDIO_0>`. Замер CAMPPlus: кот+eve к канону 0.75-0.80, пёс+sal 0.86; без параметра чужой голос, 0.25. Цена $0.08/с. Свой аудиофайл: по доке только trusted partners, id из /v1/custom-voices не проверен end-to-end. Источник: docs.x.ai/developers/model-capabilities/video/reference-to-video. В media.py флага `reference_audios` нет (`media.py:358-359`): это тело REST, реализация `projects/vetclinic/grok_alive.py` (ветка vetclinic; не проверено: ветки vetclinic в этом клоне нет).

Не проверено: `grok-machine/references/media.md:16` пишет, что data-URI теперь принимается в видео напрямую и трюк через edits не нужен. Код по-прежнему идёт через edits (`media.py:165-174`).

Для персонажей это сильнее локального Wan (S2V на мультяшных животных забракован, скил local-gen-stack).

## Законы

| Закон | Источник |
|---|---|
| ПУЛ ОДИН НА ВЕСЬ КОНТУР: с июня 2026 один недельный пул на Chat, Imagine, Voice, Build и API; через него наш OAuth, TechPulse, проза, медиа ветклиники. 16.09 лёг именно он (`spending-limit`). Старое «видео жечь смело, с карты не списывается» снято: жечь осознанно | `CHANNELS.md:46` |
| Стоп-кран на трубе: каждый `call` (кроме повтора после 401) зовёт `pool_ledger.guard` с оценкой: видео сек x 0.14 (480p 0.08, 1080p 0.25), картинка 0.05 x n. Отказ = RuntimeError с текстом СТОП-КРАН ПУЛА; порог от слова Гора 20.09 «оставить 20% в резерве». Снять: `pool_ledger.py budget clear`. Если `tools/pool_ledger.py` не импортировался (нет `tools/` рядом), guard молча пропускает вызов | `media.py:37-53`, `:40-44`, `tools/pool_ledger.py:105-106` |
| В счётчик пишутся image, video, shot (`media_image` :124, `media_video` :261, `media_shot_image` :318, `media_shot_video` :346). tts и edits-рецепт `_live_url` (:172, им идёт каждый I2V и `--last-frame` с локального кадра) мимо журнала: стоп-кран их не видит | `media.py:124`, `:172-173`, `:261`, `:266-272`, `:318`, `:346`, `tools/pool_ledger.py:22` |
| `cost_in_usd_ticks` / **1e10** = доллар-эквивалент (замер 20.09). До правки делили на 1e9 и завышали в 10 раз: старые строки журнала читать с этой поправкой | `media.py:75-78` |
| Клиентское производство на API-ключе в команде клиента, наш OAuth исполнителю не отдавать (ToS xAI) | `CHANNELS.md:46` |
| Очередь гейта по умолчанию: каждый клип video/shot и каждый стилл image сам встаёт в `gate_queue`; генерация не ждёт мозг; без proof не уходит в группу и в публикацию (`gate_queue.py require`) | `media.py:136-138`, `:181-199`, `:263`, `:350`, `CHANNELS.md:42` |
| `MEDIA_GATE=off` только словом Гора «без гейта»: клип ложится в очередь с меткой gate_off, выдачу НЕ открывает; выдачу открывает только дословная цитата Гора в `GATE_WAIVER` | `media.py:184-191`, `tools/gate_queue.py:6`, `:16-19`, `:134` |
| Паспорт кадра (BRICK-1118): результат из кадра на диске (`image_url`, `last_frame`) = derived; из одного текста паспорта нет, для сцены с железом это отказ замка «кирпич»; refs родителем не считаются | `media.py:201-216`, `:262`, `skills/video-toolkit/SKILL.md:59` |
| Железо в кадре не ниже 720p без названной причины | `media.py:224-228`, `CHANNELS.md:42` |
| Оператор не материал: его фото/голос в генерацию только с явного да на задание; клон голоса Гора руками Гора с консоли xAI | `git show 7120ee95:skills/media-forge/SKILL.md` строка 49 |
| Промпт-каркасы (стиль-спека под обложки и арт) готовит Claude как ТЗ: спека решает | `git show 7120ee95:skills/media-forge/SKILL.md` строка 50 |

## Грабли

| Грабля | Что делать | Источник |
|---|---|---|
| `shot`: прямое скачивание temp-URL кадра может дать 403 | уже починено: качает с `User-Agent: Mozilla/5.0`, при сбое печатает «кадр не сохранён» и оживляет по URL дальше. Строка `CHANNELS.md:87` поправлена 22.11 | `media.py:321-331` |
| `shot` не штампует паспорт (кадр не на диске как родитель) | для сцены с железом брать `image` → `video --image-url кадр` | `media.py:350`, `:201-209` |
| Нет `request_id` или ассет не в url | сырой ответ в `video_response.json` рядом с media.py | `media.py:241-243`, `:251-253` |
| 401 и прокси лежит | поднять прокси через `stack.ps1 -Start proxy` (раздел «Что и где») | `media.py:63` |
| `--q high` | API 400 «only low, medium, auto», код сам ставит medium | `media.py:92-93` |
| Фейлы в batch | печатает FAIL, списываются по правилу пула, очередь идёт дальше | `media.py:298-299` |
| Старый slug `grok-imagine-image-quality` | после 02.11.2026 молча отвечает 2.0 на low; старую модель звать явно: `--model` у image, `--image-model` у shot | `media.py:308-309`, `:356`, `:362`, `:366` |

## Где правда

| Вопрос | Файл |
|---|---|
| код и флаги | `projects/media-forge/media.py:1-14`, `:353-374` |
| контракт, твики, очередь применений | `projects/media-forge/MEDIA-FORGE.md` (часть твиков там устарела: `:16` aspect только у старой линии, `:29` «1.5 ТОЛЬКО image→video») |
| роутинг каналов, пул | `CHANNELS.md:40-46` |
| рецепты Imagine по API, цены | `skills/grok-machine/references/media.md` (строка `:16` про 1e9 и quality уже исправлена в коде: `media.py:78`, `:94`) |

Соседи: `grok-machine` (машина Grok, рецепты), `imagine-shorts` (канон клипов), `imagine-prompting` и `video-prompting` (промпты), `visual-gate` (proof), `video-toolkit` (паспорт кадра, замки ролика).

## Только дома, в репо нет

| Что | Где |
|---|---|
| OAuth-токен Hermes | `auth.json` на риге (`media.py:18`) |
| журнал `media_log.jsonl` | рядом с media.py, в .gitignore (`projects/media-forge/.gitignore:3`) |
| выдача | `G:\Мой диск\media-forge\` или `out\` (`media.py:21-22`) |
| процент пула | grok.com → Settings → Usage, называет Гор (`CHANNELS.md:46`, `tools/pool_ledger.py:4-6`) |
| мозг гейта | на риге, работник `gate_queue.py run` (`tools/gate_queue.py:4-6`) |
