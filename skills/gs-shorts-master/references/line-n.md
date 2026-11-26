# Линия Н: ручной шортс рига по WORKFLOW (прод с 13.11.2026, Н01-Н06)

Буква «Н» здесь = номер эпизода папки `H:/shorts/nNN_<тема>/` на риге. Не путать с «Н = ночной шортс VPS» пака 28.10 (`factory_2026-10-28/CANON.md:364`): ночная фабрика выключена с 07.10 (`projects/shaft-visions/QUEUE_OWN.md:3`), её код остаётся под буквой Н в CANON, но эпизодов Н01... она не делает.

## Что это и где живёт
| что | где | источник |
|---|---|---|
| папки эпизодов | риг, `H:/shorts/nNN_<тема>/` (n01_huang, n03_gpushield, n04_pro6000_mc, n05_39faz, n06_predoplata) | `_entry/shorts.md:25-30` |
| правда эпизода | `WORKFLOW.md` в папке эпизода, на диске H:, в репо не лежит | `_entry/shorts.md:25`, `:27`, `:30` |
| журнал вердиктов | `projects/shaft-visions/VERDICTS.md` (строки Н04, Н05) | `projects/shaft-visions/VERDICTS.md:97-98` |
| табло статусов эпизодов | `_entry/shorts.md`, раздел «Остановились на» | `_entry/shorts.md:24-34` |

## Скелет папки эпизода
| путь | что | источник |
|---|---|---|
| `WORKFLOW.md` | план, шапка со словами Гора, разделы шагов, состояние | `_entry/shorts.md:25`, `:30` |
| `WORKFLOW_voice.md` | отдельный план голоса, если голос буксовал (Н01) | `_entry/shorts.md:25` |
| `facts/FACTS.md`, `facts/script.json` | факты и сценарий по фразам | `_entry/shorts.md:30` |
| `voice/voice.wav` | голос Drama 3 | `_entry/shorts.md:30` |
| `reels/CHOICE.md` | лист выбора рилов фонда и чужих кадров, уходит Гору | `_entry/shorts.md:30` |
| `build/build.py` | сборщик эпизода (образец сведения музыки Н03) | `skills/ace-music/SKILL.md:14` |
| `build/TOOLS.json` | карта инструментов: lock до сборки, seal после | `_entry/shorts.md:29-30`, `tools/toolkit_gate.py:11-12` |
| `build/NNN.mp4` | мастер (N03.mp4 46,1 с, N04.mp4 44,0 с, N05.mp4 41,4 с, N06.mp4 50,3 с) | `_entry/shorts.md:27-30` |
| `pack/PACK.md`, `VIRAL.json`, обложка | упаковка (гейт названий 0) | `_entry/shorts.md:28`, `skills/youtube-shorts/SKILL.md:12` |
| `pack/PUBLISHED.md`, `pack/pin_*.txt` | журнал публикаций и закрепы | `_entry/shorts.md:28-29`, `:34` |

## Порядок шагов (каждая стрелка = слово Гора)
| # | шаг | что проверить | источник |
|---|---|---|---|
| 1 | тема по слову Гора («это сюжет для шортс»), `WORKFLOW.md`, скил-гейт одобряет план | судья плана, замечания в WORKFLOW | `_entry/shorts.md:30`, `skills/skill-gate` |
| 2 | факты и сценарий | `facts/FACTS.md`, сценарий принят словом («Да, озвучивай») | `_entry/shorts.md:30` |
| 3 | голос Drama 3 | расшифровка дословно (Н06: 12 из 12), отдан Гору на слух | `_entry/shorts.md:30`, `skills/drama3-voice` |
| 4 | подбор кадров | `reels/CHOICE.md` Гору до сборки; рилы фонда Д без новой генерации, если Гор так сказал (Н04) | `_entry/shorts.md:28`, `:30` |
| 5 | карта инструментов | `py -3.12 tools/toolkit_gate.py lock build/TOOLS.json` до рендера | `tools/toolkit_gate.py:11` |
| 6 | сборка | `build/build.py` -> `build/NNN.mp4`; расшифровка, громкость около -14 LUFS (Н06: 0,99 и -14,8) | `_entry/shorts.md:30` |
| 7 | печать | `py -3.12 tools/toolkit_gate.py seal build/TOOLS.json build/NNN.mp4` | `tools/toolkit_gate.py:12` |
| 8 | вердикт | Гор «Да, упаковывай», строка в `VERDICTS.md` | `projects/shaft-visions/VERDICTS.md:97-98` |
| 9 | упаковка руками (yt_pack.py линию Н не берёт) | `pack/PACK.md`, `VIRAL.json`, `viral_gate.py` = 0 | `_entry/shorts.md:28`, `projects/shaft-visions/yt_pack.py:7` |
| 10 | публикация по слову на каждый канал | шаги `skills/youtube-shorts`, ссылки в `pack/PUBLISHED.md` | `_entry/shorts.md:28-29` |

## Законы и грабли линии
| что | источник |
|---|---|
| Голос только Drama 3; Н01 встал 13.11: Drama 3 не хватило ОЗУ, после перезагрузки 20,2 ГБ свободно | `_entry/shorts.md:25`, `skills/tts/SKILL.md:10-12` |
| Утечка памяти ядра на риге (тег NtFC, 11 ГБ) и запасной ход в патче Drama: `H:/shorts/n05_39faz/WORKFLOW.md` раздел 7 | `_entry/shorts.md:29` |
| Карта, не совпавшая с роликом (Н04: лестница ставит HF на цифры, в ролике рилы по слову Гора), без оформленного допуска не проходит гейт постинга; Н04 шёл по «без гейта» | `projects/shaft-visions/VERDICTS.md:97`, `_entry/shorts.md:28` |
| Доля Monogatari ниже нормы 30 % ± 10 % (Н06 10 %) и чужих выше 25 % решает Гор (waiver), до слова не публиковать | `_entry/shorts.md:30`, раздел 1 SKILL.md (закон 16.10) |
| Avito закрыт проверкой на робота: скрины объявлений не сняты, Chrome ждёт подтверждения Гора на каждое действие | `_entry/shorts.md:30` |
| Второй канал не заливается, если его браузер не подключён (Н05 на @GSPCS) | `_entry/shorts.md:29`, `skills/youtube-shorts/SKILL.md:25` |

не проверено: какой минимум длины Н04 (44,0 с) и Н05 (41,4 с) проходил в `qa_short.py`, у которого окно по умолчанию 45-60 с (`projects/shorts-forge/qa_short.py:98`); вероятно, `--min` ниже, в WORKFLOW эпизода на H:.

## Живо ли
Линия живёт только на H: рига. Из репо видно лишь табло (`_entry/shorts.md:24-34`) и журнал `VERDICTS.md`. Состояние эпизода смотреть в его `WORKFLOW.md` на риге.
