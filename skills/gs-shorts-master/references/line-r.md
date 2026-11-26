# Линия Р: переиздание чужого эфира нашим разбором (эталон Р01, 11.11.2026)

Не путать с «Р = ручной v4» пака 28.10 (`factory_2026-10-28/CANON.md`, раздел «Четыре формата»). Здесь Р = серия шортсов-разборов чужого эфира. Законы права и порядок задачи переиздания: `skills/stream-ocr/references/republish.md` (не дублировать).

## Что это и где живёт
| что | где | источник |
|---|---|---|
| эталон в репо (код, планы, отзывы судьи, печати, журналы) | `projects/shaft-visions/shorts_r/R01_cl30_ns/` | `projects/shaft-visions/shorts_r/R01_cl30_ns/README.md:6-9` |
| эфир, кадры OCR, речь | риг, `H:/grab/<id>` (Р01: `H:/grab/oMbO8675yvo`) | `README.md:7` |
| ролик и медиа | риг, `H:/shorts/r01_cl30_ns` (мастер `build/R01_v3.mp4`) | `README.md:8` |
| копия кода в репо | снята побайтно со сверкой sha: правки на H:, потом копировать снова | `README.md:9` |
| журналы контура | `H:/shorts/_publish_log.tsv`, `skills/viral/LEDGER.md`, `skills/video-toolkit/ledger.jsonl` | `README.md:25` |

## Станции (у каждой свой WORKFLOW, судья консультант)
| № | станция | скил | файлы эталона |
|---|---|---|---|
| 1 | выкачка эфира, экран, тайминги, речь и перевод | stream-ocr | `stream/WORKFLOW.md`, `stream/check_gates.py` |
| 2 | факты и расчёт | epistemic-guard, viral §1 | `FACTS.md`, `calc.py` |
| 3 | голос Drama 3, ASR против сценария | drama3-voice | `WORKFLOW_voice.md`, `voice/` |
| 4 | рилы Д: банк, кандидаты, выбор Гора | monogatari-bank, imagine-shorts | `WORKFLOW_reels.md`, `reels/` |
| 5 | карточки «Лаборатория» | `tools/hf_gs.py` | `cards/hf/*.json` |
| 6 | сборка, визуальный гейт, печать инструментария | video-toolkit, visual-gate | `build/` (build_r01.py, check_build.py, TOOLS.json, SEAL.json) |
| 7 | ужатие H.265 под заливку | compress-video | `publish/enc_h265.py`, `publish/enc_verify.py` |
| 8 | упаковка: названия, хук, теги, закрепы, обложка | viral, shorts-cover, gspc-pinned-comment | `publish/mk_viral.py`, `publish/VIRAL.json`, `publish/PACK.md` |
| 9 | заливка в Студию, закреп, журнал | multi-upload, youtube-shorts | `WORKFLOW_publish.md`, `publish/PUBLISHED.md` |
| 10 | пост ТГ «анонс» | tg-typograf, gspc-post-writer | `publish/TG_R01.*` |

Источник таблицы: `projects/shaft-visions/shorts_r/R01_cl30_ns/README.md:11-23`.

## Как вызвать (из папки эталона)
| команда | что делает | источник |
|---|---|---|
| `py -3.12 publish/enc_h265.py [--crf 30]` | H.265 `libx265 -crf 30 -preset veryslow -tag:v hvc1`, вход = сырые кадры мастера; не влезло в 10 МБ = CRF +1 | `publish/enc_h265.py:2-8` |
| `py -3.12 publish/mk_viral.py` | VIRAL.json, viral.json копии, PACK.md, upload_fields.json; цифры только из FACTS.md, calc.py, кадров эфира | `publish/mk_viral.py:1-7` |

## Грабли Р01
| грабля | что делать | источник |
|---|---|---|
| ffmpeg 8.1.2 под нагрузкой кодера даёт ошибки декода | вход кодера = сырые кадры мастера, не mp4 | `README.md:28`, `publish/enc_h265.py:5-6` |
| Студия не принимает угловые скобки в описании («->» молча держит «Далее») | проверка в `publish/mk_viral.py` | `README.md:29` |
| радио «Прямая реклама» больше не стоит по умолчанию | ставить «нет», иначе «Далее» не идёт | `README.md:30` |
| обложка словами Гора длиннее нормы гейта 2-4 слова | поле `cover_owner_quote` с дословной репликой Гора, снимается только счёт слов | `README.md:31` |
| Студия @GoldenSamplePCs: панель подсказок хэштегов сдвигает поле описания | координаты брать заново, текст сверять после ввода | `README.md:33` |
| «CL» и «нс» в названиях и обложке = птичий язык | только в описании и посте с объяснением | `README.md:34` |
| имя автора эфира в названиях (урок 27.10) | не ставить, кредит «Видео: <автор>» со ссылкой в описании | `publish/mk_viral.py:6` |

## Где опубликовано
@GSPCS: https://youtube.com/shorts/tsHS2zI0rV0; @GoldenSamplePCs: https://youtube.com/shorts/mYOVenG87TA (`README.md:3`, `:31`).
