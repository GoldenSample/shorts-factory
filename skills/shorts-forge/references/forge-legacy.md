# forge.py: исторический замер 27.07 (ЗАПАС, не прод)

Конвейер `projects/shorts-forge/forge.py` сейчас запас: прод в линиях Н, Р, И, Г (`skills/gs-shorts-master/SKILL.md:49-53`),
автоновости VPS выключены 07.10 (`projects/shaft-visions/QUEUE_OWN.md:13`). Ниже замер 27.07, по коду заново не сверен.

```
python forge.py "тема"                                  # раскадровка, пул НЕ жжётся
python forge.py "тема" --scenes 9 --go --subs           # боевой: генератив + голос + сборка
python forge.py "тема" --go --shots ПАПКА --subs        # визуал = РЕАЛЬНЫЕ кадры (Ken Burns)
python forge.py "тема" --go --no-video                  # голос на фоне (пул не тронут)
```
Цепь: grok-4.3 кует раскадровку JSON -> `media.py shot` или Ken Burns по кадрам -> `media.py tts` ->
ffmpeg (голос поверх клипа, scale+crop 1080x1920) -> concat -> `out/`.

**Замеренные тайминги:** раскадровка 16-20с · TTS 3-5с/сцена · видеогенерация **44с/сцена** ·
картинка+Ken Burns 24с · **2 сцены Ken Burns end-to-end = 32 секунды**.
Ролик на 6 сцен с генерацией ≈ 5.5 мин последовательно, ~2 мин при параллели.

⚠ **Долги конвейера, вскрытые замерами:** `build_kenburns` на голом zoompan (замораживает 90 кадров
из 149, чинится libplacebo, `references/visual-fx.md`); `burn_subs` на SRT+`force_style` (держится
на том, что ffmpeg подставляет `PlayResY: 288`, не даёт ни пословной подсветки, ни гало-слоя).

Сверка с кодом 22.11: долг zoompan закрыт, `build_kenburns` сам выбирает libplacebo или `scale 4x -> zoompan` (`forge.py:188`, `:211-217`, `:261-268`, переключатель `FORGE_KB`); `burn_subs` по-прежнему SRT + `force_style` (`forge.py:288`, `:306`).
