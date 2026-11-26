# Фабрика шортсов Golden Sample

Срез из рабочего репозитория: скилы Claude Code и код, которыми собираются вертикальные ролики (шортсы, Reels, клипы VK) для канала про железо.

## С чего начать

1. `skills/gs-shorts-master/SKILL.md`: мастер-пайплайн, вход отсюда.
2. `skills/gs-shorts-master/factory_2026-10-28/CANON.md`: канон конвейера (16 шагов, форматы роликов, решённое и открытые вопросы).
3. `skills/gs-shorts-master/factory_2026-10-28/INVENTORY.md`: какие скилы за какой шаг отвечают и их статус.

## Что внутри

- `skills/`: скилы по шагам конвейера. Тема и сценарий (`shortsmaker`, `gspc-reels-scripting`, `yazyk-vygody`), голос (`gspc-voice-kit`, `drama3-voice`), кадры (`video-prompting`, `imagine-prompting`, `qwen-edit-art`, `media-forge`), перебивки (`chuzhie-futazhi`, `headless-web`), обложка и тексты (`shorts-cover`, `gspc-post-writer`, `gspc-pinned-comment`), площадки (`vk-zavod`, `dzen-master`), приёмка (`video-critic-loop`, `sudya-1000-glaz`), выкат (`deploy-vps`), выбор средств под сцену (`video-toolkit`), операционка (`shorts-forge`).
- `projects/shorts-forge/`: код сборки (сборщики роликов, голос и ударения, QA, публикация).

## Чего здесь нет

- Ключей, токенов и паролей: код читает их из переменных окружения и локальных файлов, которых в срезе нет.
- Адрес сервера заменён на `<VPS_IP>`, телефоны на `+7 (XXX) XXX-XX-XX`.
- Модели, голосовые данные, рабочие папки роликов и медиа.

Пути вида `C:/CLAUD/...`, `H:/...`, `/opt/shorts/...` указывают на машину автора: под себя их надо поменять.
