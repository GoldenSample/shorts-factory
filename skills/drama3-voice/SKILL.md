---
name: drama3-voice
description: "Drama 3 (Fish Audio, открытая TTS 35B MoE, русский, клон по эталону) на главном риге с RTX 5090 32 ГБ: где стоит, как запускать, наш патч «эксперты в ОЗУ», раскладка видеопамяти, конфликт карты с Ollama, проба голосом Гора. Плюс общая озвучка эпизода `projects/shorts-forge/drama_voice.py` (seal, synth, lines, assemble): замок voice_sha1, словарь gor_lexicon.tsv, расшифровка до 4 попыток, темп склейки не выше 1,12, снятие правила линтера цитатой Гора, запасной ход при нехватке ОЗУ. Звать при: Drama 3, fish-speech, клон голоса, озвучка локально, «войс клон», перезапись слова, ударение в озвучке, drama_voice, озвучка эпизода, voice_sha1, печать текста, seal, lint_waivers, gor_lexicon, латиница вне словаря, склейка голоса, voice.wav, voice_timing, сервер :8090 не отвечает, Drama не хватило ОЗУ."
---

# Drama 3 на риге

Поставлено 14.10.2026 по слову Гора («ставь на мэйн риг войс клон»).
⛔ Основной голос контента = Drama 3 (Гор 14.10.2026: «озвучка должна быть драмой»; «мы работаем только с драмой, остальные модели проверку не прошли, у них удАрения крейзи»; «хаи терпимо, но оно платное и слабое, нужна альтернатива, драма лучше хаи»). xAI = терпимый запас, только если Drama невозможна, и сказать Гору. Двойник Qwen, Chatterbox и прочие TTS = брак по ударениям.

## Где что
- Код: `C:\Apps\fish-speech` (официальный fish-speech v3, коммит 5415669), venv `.venv`: torch 2.8.0+cu128, triton-windows 3.4.
- Веса: `H:\tts-models\drama-3` (41,5 ГБ, 8 шардов + codec.pth, sha256 сверены). Докачка/скачивание: `py -3.12 -u C:/CLAUD/tools/hf_pfetch.py fishaudio/drama-3 --root H:/tts-models/drama-3` (свои Range-запросы, Xet тут медленный).
- ⭐ **КАНОН голоса = старый эталон** `H:\tts-models\drama-3\refs\gor_ref.wav` (18,5 с из начитки Э01) + `gor_ref.lab`: им озвучен канон Э04. Гор 15.10.2026: сначала «новый голос драма по камере идет в прод», затем последнее слово: «драма олд пока канон». Замер (сам эталон мерится 0,41 к голосу роликов @GSPCS) Гор знает; решает его ухо.
- Кандидат = камерный эталон `refs/gor_cam_E.json`: три целые фразы `gor_cam_E0-2.wav` (+ .lab) из архива камеры D:\РАИД, в запросе все три в `references`, у каждой `"speaker": 0`. Замер 14.10: похожесть 0,75 против 0,48, ошибок слов 0, темп живой. В прод только новым словом Гора. Сравнение: `projects/shorts-forge/voice_ft/drama_ab.py`, итоги `H:\tts-models\drama-3\ab_camera\report.json`.
- WSL на риге нет, всё нативно под Windows.

## Запуск
1. Карту освободить и закрыть от чужих: `py -3.12 C:/CLAUD/tools/rig_safe.py free-vram`, и на время работы режим тишины `rig-quiet on` на VPS (иначе задания с VPS через Ollama 10.77.0.2:11434 снова грузят Qwen3.6 35B на 22 ГБ, см. «Грабли»).
2. Сервер (из Bash в фоне):
   `cd C:/Apps/fish-speech && FISH_DRAMA3_CUDA_GRAPH=0 FISH_DRAMA3_GPU_EXPERT_LAYERS=<N> .venv/Scripts/python.exe -u tools/api_server.py --listen 127.0.0.1:8090 --llama-checkpoint-path H:/tts-models/drama-3 --decoder-checkpoint-path H:/tts-models/drama-3/codec.pth --device cuda:0 > H:/tts-models/drama-3/_server.log 2>&1`
   Загрузка около 2 минут, прогрев (компиляция ядер triton) ещё около 1-2 минут; готовность = «Uvicorn running» в логе.
3. Проба: `.venv/Scripts/python.exe tools/drama3_ref_test.py --url http://127.0.0.1:8090/v1/tts --ref-audio H:/tts-models/drama-3/refs/gor_ref.wav --text "..." --out-dir H:/tts-models/drama-3/out` (расшифровка эталона берётся из .lab рядом).
   Живо: `grep -n "Uvicorn running" H:/tts-models/drama-3/_server.log` даёт строку и `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8090/v1/health` = 200 (`projects/shaft-visions/shorts_r/R01_cl30_ns/WORKFLOW_voice.md:32`). Тот же `/v1/health` `drama_voice.py` спрашивает сам перед синтезом (`projects/shorts-forge/drama_voice.py:141-144`).
4. Самопроверка: расшифровка встроена в `drama_voice.py` (раздел ниже), venv `C:/Apps/whisper/.venv` (`drama_voice.py:40`). Было: здесь стоял `asr_cpu.py`, в `C:/Apps/whisper` его нет (поиск 11.11 = 0, `projects/shaft-visions/shorts_r/R01_cl30_ns/WORKFLOW_voice.md:21`), в репо он лежит только в `projects/shaft-visions/shorts_e/E01_maya_5090/asr_cpu.py` как история Э01. Ударение ASR не слышит: его проверяет Гор на слух.
5. После работы: остановить сервер (TaskStop не гасит дочерний python: `Stop-Process` по командной строке `api_server.py ... 8090`), `rig_safe.py restore`, `rig-quiet off`.

## Озвучка эпизода: `drama_voice.py`
Одна общая копия вместо скриптов Э04, Э05 и L02 (`projects/shorts-forge/drama_voice.py:2-4`). Им озвучены Э04, L02 и Р01 (`projects/shaft-visions/shorts_r/R01_cl30_ns/WORKFLOW_voice.md:16`), `lines` для линии И (`drama_voice.py:16`). Где: риг, из `C:/CLAUD`; сервер :8090 поднят по разделу «Запуск».

| Команда (`py -3.12 projects/shorts-forge/drama_voice.py ...`) | Что делает | Коды выхода | Где правда |
|---|---|---|---|
| `seal <папка>` | `rubrics.lint` по plan.json, снятия `lint_waivers`, проверка словаря, пишет `voice_sha1` | 0 печать, 1 слог не чист или латиница вне словаря (`SystemExit`, `:78`) | `drama_voice.py:199-219` |
| `synth <папка> [--check]` | `voice_drama/v{i}.wav` по сценам plan.json; переозвучивает только брак | 2 замок, 0 без брака, 1 брак остался, сервер не отвечает (`:144`) или слот занят 30 мин (`:163`) | `drama_voice.py:222-229`, `:124-165` |
| `lines <lines.json> <папка> [--check]` | реплики списком (линия И, `zhelezki_short`), без замка voice_sha1 | 0 или 1 (те же отказы, что у `synth`) | `drama_voice.py:16`, `:232-234` |
| `assemble <папка>` | `voice.wav`, `voice_timing.json`, `voice.asr.json` (large-v3 по словам, для титров) | 1 нет реплик `v{i}.wav` (`:242-243`), иначе код whisper | `drama_voice.py:237-278` |
| без аргументов или неверно | печатает справку | 2 | `drama_voice.py:293` |

`--check` = только расшифровать готовые файлы и сказать ГОДЕН или БРАК, сервер не нужен (`drama_voice.py:139-140` раньше проверки сервера `:141`).
Порядок эпизода: `seal`, подъём сервера, `synth`, гашение сервера, `assemble` (`WORKFLOW_voice.md:28-35`).

### Законы инструмента
| Закон | Как устроено | Где правда |
|---|---|---|
| Замок текста | `voice_sha1` = sha1 строк `voice` (или `text`, если `voice` нет) всех сцен; нет или не совпал = `synth` отказ с кодом 2. Ставит только `seal` | `drama_voice.py:64-69`, `:225-228` |
| Словарь | текст идёт через `gor_normalize.normalize` (`gor_lexicon.tsv`); латиница вне словаря = ОТКАЗ, слово вписать в `projects/shorts-forge/gor_lexicon.tsv`, голос не угадывает. Проверяется уже на `seal` | `drama_voice.py:7-8`, `:72-79`, `:216` |
| Попытки | до 4 (`TRIES`) на реплику: синтез, срез тишины, расшифровка faster-whisper small на CPU | `drama_voice.py:42`, `:82-90`, `:150-161` |
| Годность реплики | сходство расшифровки не ниже 0,62 (с `voice` или экранным `text`), длина не больше ожидаемой x1,9 + 1 с, речь до конца файла | `drama_voice.py:98-105` |
| Склейка | паузы 0,15 с, темп не выше 1,12 (audio-voice «не гнать выше 1.12»), цель 55 с; упёрлись в 1,12 = резать текст; выход 48 кГц | `drama_voice.py:12`, `:43-44`, `:244-251`; `skills/shorts-forge/references/audio-voice.md:231` |
| Карта | синтез под общим слотом 5090 `gpu_slot.slot("drama_voice", wait=1800)`; занято 30 мин = отказ. Сервер поднятый с `GPU_SLOT_HELD=<кто>` проходит вложенно | `drama_voice.py:147`, `:162-163`; `tools/gpu_slot.py:17` |
| Линия Э | «начитка N слов» до 165 слов не валит печать (канон 140-160) | `drama_voice.py:45`, `:206-208` |
| Расшифровка | после синтеза, не во время: CPU не делить (см. «Грабли», 91 с вместо 30) | `drama_voice.py:18` |

### Снятие правила линтера: `lint_waivers` в plan.json
Формат: `[{"rule": начало строки линтера, "key": слово из реплики Гора или вопроса, "quote": его слова, "after": ISO-время}]` (`drama_voice.py:173-174`).
- Машина ищет цитату в стенограммах `~/.claude/projects` через `skills/audit-lock/scripts/owner_words.py said`; рукой вписанное без его слов не проходит (`drama_voice.py:175`, `:189-191`). Нашлась = в снятие пишется `found` (ts, session) (`:192`).
- Нет quote, key или after = не принято (`:187-188`).
- ⛔ `WAIVE_HARD = ("мат",)`: снятие, в поле `rule` которого есть подстрока «мат», не принимается никогда (`drama_voice.py:168`, `:187`; gs-shorts-master §1, закон 16.10). Строка линтера про мат начинается с «мат:» (`projects/shorts-forge/rubrics.py:433`).
- Общий закон «подпись владельца = его дословные слова»: `skills/audit-lock/SKILL.md:30`, двери и вход по слову: `skills/keymaster/SKILL.md:100` (строка «линтер драмы»: lint_waivers, WAIVE_HARD «мат»).
- Живой пример: Р01, снятие «нет вердикта» словом «Оставить действие» 11.11, контроли `voice/waiver_controls.py` (`WORKFLOW_voice.md:29-30`).

## Наш патч «эксперты в ОЗУ» (пометки `GS patch`)
Модель: 40 слоёв, в каждом 256 экспертов по 3,15 МБ FP8 (эксперты всего 32 ГБ), top-8 на токен. Остальное около 9,5 ГБ bf16.
- `fish_omni/backbone.py` `materialize`: `FISH_DRAMA3_GPU_EXPERT_LAYERS=N` оставляет эксперты первых N слоёв на карте, у остальных они в ОЗУ (на карту их не выделяет вовсе).
- `fish_omni/moe.py` `forward_offloaded`: на каждый шаг `unique` задетых экспертов -> `index_select` в закреплённый буфер -> копия на карту -> FP8-ядро triton (при ошибке triton откат: распаковка в bf16 на карте). Замер одного слоя 14.10: unique 0,8 мс, сборка+копия 2,9 мс, ядро 2,3 мс (распаковка+bmm 0,9 мс быстрее ядра на одном токене).
- `fish_omni/model.py`: при офлоаде FP8-хранение экспертов сохраняется и без triton (иначе 64 ГБ bf16).
- Обновление fish-speech затрёт патч: перед `git pull` сохранить дифф (`git diff > gs_patch.diff`).

## Раскладка 32 ГБ (оптимум, карта целиком под Drama)
- Основа + башня кодеков + кэш: около 11 ГБ (замер 14.10: пик 20,5 ГиБ при 12 слоях экспертов на карте => 20,5 - 12 x 0,8).
- Остаток около 19 ГБ = примерно 23 слоя экспертов целиком на карте (`FISH_DRAMA3_GPU_EXPERT_LAYERS=23`), 17 слоёв в ОЗУ: оценка подвоза около 0,1 с на шаг.
- Следующая ступень, если мало: кэш самых частых экспертов каждого слоя на карте вместо целых слоёв (частоты собрать на прогоне).
- Замер скорости делать только при монополии на карту: при соседе с 22 ГБ драйвер уводит память в системную и шаг растёт до 1,27 с (14.10: RTF 28 на пробе был из-за этого).

## Грабли
- 14.10: после `free-vram` задание VPS `tg_extract.py` (`/root/direct-channels`) через минуту снова загрузило Qwen3.6 35B в Ollama рига. Без `rig-quiet on` карта не твоя.
- Без CUDA-графов (с офлоадом они невозможны: CPU-операции в шаге) остаются накладные расходы запуска ядер; профиль шага по частям: `C:/Apps/fish-speech/gs_profile.py`, замер слоя: `gs_bench_offload.py`.
- Лицензия Fish Audio Community: коммерция бесплатна до 500 тыс. $ годовой выручки, дальше договор с Fish Audio.
- (14.10) Drama отдаёт wav 44,1 кГц: склейку делать по частоте файла, иначе голос замедлится и сядет.
- (14.10) Эксперты в ОЗУ таскает процессор: при соседней нагрузке на CPU (whisper large-v3 на процессоре) фраза синтезируется в 3 раза дольше (91 с вместо 30). Проверку расшифровкой гонять после синтеза, не во время.
- (14.10) Модель копирует эталон вместе с его порчей: gor_ref.wav сам мерится 0,41 к голосу Гора (сырая начитка Э01 0,60, ролики @GSPCS 0,80-0,85), похоже, вырезан после шумодава. Новые эталоны брать из сырой записи. Гор это знает и 15.10 оставил канон старым («драма олд пока канон»): для прода брать gor_ref.wav, пока Гор не скажет иначе.
- (14.10) Эталон, оборванный на запятой, учит модель обрывать фразу: 3 из 12 фраз кончились после первой части («Включим тест.»). Эталон = целые предложения, от заглавной до точки.
- (14.10) Кода обучения у Drama 3 нет: Fish Audio убрал LoRA и обучение из репо в релизе v3.0.0-beta (ответ Grok со ссылками `_research/drama3_ft/a.md`), общественных дообучений нет. Официальный путь = несколько эталонов. Набор под возможное своё обучение: `H:\tts_data\gor_camera\segments.jsonl` (4,3 ч речи Гора, из них 2,0 ч чистой, чужих голосов 0).
- 13.11 (Н01): голос встал, Drama 3 не хватило ОЗУ; после перезагрузки свободно 20,2 ГБ (`_entry/shorts.md:25`). 19-20.11 в `C:/Apps/fish-speech/fish_speech/models/text2semantic/fish_omni/moe.py` функции `_gather_to` добавлен запасной ход при нехватке ОЗУ (`_entry/infra.md:30`). Сама `_gather_to` = `index_select` в закреплённый буфер и копия на карту (`missions/factory-shorts/history/chapters/14_2026-10-14.md:126`). Не проверено: что именно делает запасной ход; код только на риге, в репо его нет, описание в `H:/shorts/n05_39faz/WORKFLOW.md` раздел 7 (`_entry/shorts.md:29`). Там же 19-20.11 найдена утечка памяти ядра (NtFC около 11 ГБ), лечит перезагрузка (`_entry/infra.md:30`): при нехватке ОЗУ сначала перезагрузка рига.
- Сходство ниже 0,62 при целой фразе: расшифровка пишет цифры. Экранную форму цифрами класть в `text`, словами в `voice`; печать считается по `voice`, голос не меняется (`WORKFLOW_voice.md:27`).
- 27 ГБ свободной карты вместо 32: 23 слоя экспертов не влезут, Р01 шёл на 18 (`WORKFLOW_voice.md:32`).
- (14.10) Измерители похожести Chatterbox и WavLM-ECAPA с диска пропали; замена `projects/shorts-forge/voice_ft/spk_embed.py` (кодировщик диктора Qwen3-TTS Base, только замер).

## Где правда и что живёт только дома
| Что | Где |
|---|---|
| инструмент озвучки | `projects/shorts-forge/drama_voice.py` (в репо) |
| словарь чтений | `projects/shorts-forge/gor_lexicon.tsv`, `gor_normalize.py` (в репо) |
| линтер слога | `projects/shorts-forge/rubrics.py` (в репо) |
| слот карты | `tools/gpu_slot.py`, замок `tools/autostart/_gpu_slot.json` вне git (`tools/gpu_slot.py:13`) |
| эталонный эпизод | `projects/shaft-visions/shorts_r/R01_cl30_ns/WORKFLOW_voice.md` |
| только на риге | сервер и патч `C:/Apps/fish-speech`, веса и эталон `H:/tts-models/drama-3` (`refs/gor_ref.wav` + `.lab`, `drama_voice.py:38`, `:112`), venv `C:/Apps/whisper/.venv`, лог `_server.log`, эпизоды линии Н в `H:/shorts/` (`n01_huang`: `_entry/shorts.md:25`; `n05_39faz`: `_entry/infra.md:30`) |

Память: `project_drama3_voice.md`. Родня: `tts` (роутер движков, Drama = голос контента), `gor-voice` (слог), `gs-shorts-master` (линии и законы шортсов), `istorii-zhelezok` (линия И, `lines`), `keymaster` и `audit-lock` (снятие словом), `media-forge` (xAI), `local-gen-stack`, `bulletproof-bridge` (команда rig-quiet, режим тишины: `skills/vps-ops/SKILL.md:160`).
