# Ночная фабрика шортсов VPS: как устроена, если её включат

Статус на 22.11.2026: ВЫКЛЮЧЕНА (шапка `SKILL.md`). Ниже описание по снимку кода 06.10 и аудиту 23.10, живой `/opt/shorts` мог уйти от них.

## Что это и где живёт

| единица | машина, путь | расписание при включении | источник |
|---|---|---|---|
| `daily.sh` (ночной прогон новостной фабрики) | VPS <VPS_IP>, `/opt/shorts/daily.sh`, root crontab | 06:00 UTC (09:00 МСК), до 3 тем за ночь, бюджет 150 мин, `--dubles 1`, запасной продукт `digest_short.py --from-db` | `skills/gs-shorts-master/factory_2026-10-28/CANON.md:368`, `:64`; `_research/tp-factory-audit-2026-10-23/parts/VERIFY_S05.md:12` |
| `queue_run.py` (очередь пульса) | VPS, `/opt/shorts/queue_run.py`, `/etc/cron.d/shorts-queue` | 7:30, 12:30, 18:30 UTC | `CANON.md:56`; `MASTERPROMPT-2026-10-05-gor-voice-vps.md:129` |
| очередь тем | `/opt/news-aggregator/data/shorts_queue/*.json`, кладёт крон Гермеса `viral` (`viral_topics`) | | `services/_vps_patches/shorts_20261006/queue_run.py:3`, `:8` |
| сборщик | `/opt/shorts/build_short.py`, общий для daily и очереди | | `queue_run.py:51`; `MASTERPROMPT-2026-10-05-gor-voice-vps.md:121-122` |
| замок | `/var/lock/shorts.lock`, общий для фабрики | | `queue_run.py:5`, `:41-45`; `CANON.md:368` |
| лог | `/opt/shorts/daily.log` (очередь пишет туда же) | | `queue_run.py:9`, `:50` |
| история выпусков | таблица `shorts_log`, тема занята сразу, исход в конце | | `CANON.md:57` |
| реестр тем | `/opt/shorts/topics.py`, `/opt/shorts/topics.db` | | `CANON.md:58`; `queue_run.py:24-26` |

## Как работает `queue_run.py` (снимок 06.10)

| шаг | что | строка |
|---|---|---|
| порядок | файлы `*.json` по убыванию числа после первого `_` в имени, затем по свежести | `queue_run.py:20` |
| пусто | пишет «пусто» в лог, код 0 | `:21-22` |
| протухла | старше 72 ч -> `skip/` | `:29-32` |
| повтор | `topics.check(..., source="shorts", judge=True)` против истории только шортсов; повтор -> `skip/` | `:26`, `:34-38` |
| замок занят | «фабрика занята, тема остаётся в очереди», код 0 | `:41-45` |
| сборка | `build_short.py --theme-json <файл> --dubles 1` питоном Hermes `/usr/local/lib/hermes-agent/venv/bin/python3`, cwd `/opt/shorts` | `:10`, `:51` |
| раскладка | код 0 -> `done/`, иначе `failed/`; за запуск одна тема | `:53-55` |
| `--dry` | печатает «протухла / отсеял бы / взял бы», файлы не двигает, сборку не зовёт | `:28-40` |

Окружение сборки жёстко в коде: `SHORTSMAKER_VOICE_ENGINE=xai`, `SHORTSMAKER_CUSTOM_VOICE` (облачный клон), громкость музыки и дакинг (`queue_run.py:48-49`). `SHORTSMAKER_VOICE_LINT` очередь не задаёт: если переменная только в `daily.sh`, очередь пойдёт на умолчании (`MASTERPROMPT-2026-10-05-gor-voice-vps.md:130-132`). daily.sh и pending_retry.sh тоже ставят `SHORTSMAKER_VOICE_ENGINE=xai` (`VERIFY_S05.md:75`; `CHANNELS.md:191`).

## Как проверить «живо» (только чтение, только с разрешения на VPS)

| команда | что ждём сейчас (выключено) | источник |
|---|---|---|
| `crontab -l` | строка `# 0 6 * * * /opt/shorts/daily.sh` с решёткой | `VERIFY_S05.md:12` |
| `cat /etc/cron.d/shorts-queue` | `queue_run.py` нет или под комментарием | `VERIFY_S04.md:66`, `VERIFY_S05.md:12` |
| `ls -l /opt/shorts/daily.log` | mtime 2026-10-06 (последний прогон) | `VERIFY_S05.md:12` |

Если включили: свежие строки в `daily.log` после 06:00 UTC; для очереди `cd /opt/shorts && /usr/local/lib/hermes-agent/venv/bin/python3 queue_run.py --dry` (файлы не двигает, но `import topics` из `/opt/shorts` и `topics.check(..., judge=True)` зовутся и в dry, то есть может сходить к LLM-судье: `queue_run.py:10`, `:23-24`, `:34`) и после первого запуска `grep -a VOICE_LINT /opt/shorts/daily.log | tail` (`MASTERPROMPT-2026-10-05-gor-voice-vps.md:133-134`).

## Законы и запреты

| закон | источник |
|---|---|
| Включать `daily.sh` и очередь (раскомментировать крон, вернуть `queue_run.py`) только словом Гора: выключены его словом 07.10 | `VERIFY_S05.md:12` |
| `viral_topics` выключен 24.10 (ветка чинилась по слову Гора 24.10); слова Гора про обратное включение в файлах нет, без спроса не включать | `fix/STATE.md:1`, `:10` |
| `daily.sh` и всё, что зовёт крон, руками не запускать; смотреть следующий прогон в `daily.log` | `skills/deploy-vps/SKILL.md:53` |
| Выкат файлов `vps/** -> /opt/shorts/**` только `deploy-vps` по прямому «выкатывай»; юниты и крон этим скилом нельзя | `skills/deploy-vps/SKILL.md:13`, `:15`, `:17` |
| Замок проверять по `/proc/locks`, без захвата: `flock -n` на миг займёт его, и `daily.sh` пропустит ночь | `skills/deploy-vps/SKILL.md:37` |
| Двойник голоса v4-v6 только по слову Гора; окружение daily.sh (xAI) относится к выключенной фабрике | `skills/gs-shorts-master/SKILL.md:40`; `CANON.md:138` |
| Голос контента по закону 14.10 только Drama 3, xAI терпимый запас со словом Гору. `queue_run.py:48` и `daily.sh` жёстко ставят xai, это против закона: при включении фабрики голос решает Гор | `skills/gs-shorts-master/SKILL.md:14`, `:39`; `skills/shorts-forge/SKILL.md:42` |
| Наружу только по «да» Гора | `CANON.md:350` |

## Известные грабли

| грабля | источник |
|---|---|
| Скрипты фабрики (`critic_loop.py`, `fact_gate.py`, `frame_critic.py`, `own_bank.py`) бьют в Ollama рига 10.77.0.2:11434 мимо замков рига. Мина на случай включения | `VERIFY_S04.md:65-66` |
| На тяжёлые прогоны 5090 есть `rig-quiet on` на VPS: режет фабрике доступ к службам рига | `CHANNELS.md:194` |
| Мат в теме очереди: код не 0, тема уходит в `failed/`, следующая только следующим запуском крона; daily берёт следующую тему сразу | `MASTERPROMPT-2026-10-05-gor-voice-vps.md:128-129` |
| `--script-json` и `--resume` обходят `story_step`, блок голоса в промпт не попадает | `MASTERPROMPT-2026-10-05-gor-voice-vps.md:126-127` |
| Гор назвал голос xAI слабым, а `pending_retry.sh` гнал `--resume` именно им в обход «снимаем по своим идеям» (на 24.10 помечен `#OFF-1024`) | `VERIFY_S05.md:86`; `fix/STATE.md:10` |
| Ночь на старом пути: перенос рецепта v4 в `daily.sh` открыт с 03.10 | `CANON.md:376` |

## Что живёт только на VPS и в репо не лежит

| что | где | в репо |
|---|---|---|
| живой `/opt/shorts` (`daily.sh`, `pending_retry.sh`, `topics.py`, гейты, `CLAUDE.md`) | VPS | только снимок 06.10 `services/_vps_patches/shorts_20261006/` (`queue_run.py`, `build_short.py`, `backup_daily.sh`); полный снимок в репо GoldenSample/shortsmaker `vps/` (`CANON.md:338`) |
| очередь `shorts_queue` и её `done/failed/skip` | VPS `/opt/news-aggregator/data/` | нет |
| `daily.log`, `topics.db`, таблица `shorts_log` | VPS | нет |

не проверено: текущее содержимое crontab и `/etc/cron.d/shorts-queue` после 24.10; номера строк снимка на VPS после выкатов сдвинуты (`MASTERPROMPT-2026-10-05-gor-voice-vps.md:119-120`).
