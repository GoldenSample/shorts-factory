# Монтажные рецепты

ffmpeg 6.1.1 на Ubuntu (VPS). Все команды с `-nostdin` — иначе ffmpeg съест остаток bash-скрипта из stdin.

Шрифты с кириллицей на месте: `/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf`, `liberation`, `noto`.

## Картинка → клип с движением камеры

Основной приём. Апскейл ×4 перед `zoompan` обязателен, иначе кадр дрожит.

```bash
T=4
ffmpeg -nostdin -y -loop 1 -t $T -i scene.jpg -filter_complex \
"scale=4320:7680:force_original_aspect_ratio=increase,crop=4320:7680,\
zoompan=z='min(zoom+0.0012,1.20)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=$((30*T)):fps=30:s=1080x1920,setsar=1" \
-c:v libx264 -pix_fmt yuv420p -r 30 clip.mp4
```

Панорама вместо наезда — заменить `x` на `x='(iw-iw/zoom)*on/119'`.

Длительность задаёт `d = fps × секунды`, а не только `-t`.

## Вертикаль из горизонтального исходника

Обрезка по центру, без полос:

```bash
-vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
```

Если центр резать жалко — размытый фон вместо полос:

```bash
-filter_complex "[0:v]split=2[bg][fg];\
[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=25[bgb];\
[fg]scale=1080:-2[fgs];[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1"
```

## Склейка сцен

Жёсткий рез — быстрее и честнее для коротких роликов: `concat`-демуксер.

Кроссфейд, когда нужна мягкость. `xfade` требует одинаковых fps, размера и pix_fmt у всех входов, иначе падает. `offset` = длина первой сцены минус `duration`.

```bash
ffmpeg -nostdin -i a.mp4 -i b.mp4 -filter_complex \
"[0:v]scale=1080:1920,setsar=1,fps=30,format=yuv420p[v0];\
[1:v]scale=1080:1920,setsar=1,fps=30,format=yuv420p[v1];\
[v0][v1]xfade=transition=hblur:duration=0.7:offset=4.3[v]" \
-map "[v]" -r 30 -c:v libx264 -crf 18 -pix_fmt yuv420p out.mp4
```

`transition=hblur` — переход с размытием, `fade` — обычный.

## Кадры разной длительности из списка

```
file '/path/01.jpg'
duration 3.5
file '/path/02.jpg'
duration 2.8
file '/path/02.jpg'
```

Последний кадр продублировать **без** `duration`, иначе он обрежется.

```bash
ffmpeg -nostdin -f concat -safe 0 -i list.txt \
-vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p,fps=30" \
-c:v libx264 -preset medium -crf 18 -movflags +faststart out.mp4
```

## Озвучка поверх видеоряда

```bash
ffmpeg -nostdin -y -i video.mp4 -i voice.mp3 -map 0:v:0 -map 1:a:0 \
-c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
-c:a aac -b:a 192k -shortest -movflags +faststart out.mp4
```

**Клипы Grok Imagine приходят со своим звуком.** Если он нужен фоном под голос — микс вместо замены:

```bash
-filter_complex "[0:a]volume=0.15[amb];[amb][1:a]amix=inputs=2:duration=shortest[a]" -map 0:v -map "[a]"
```

## Нормализация громкости

Стандарт лент ≈ −14 LUFS. Однопроходно:

```bash
-af loudnorm=I=-14:TP=-1.5:LRA=11 -ar 48000
```

Двухпроходно точнее: сперва `print_format=json` в `-f null -`, затем подставить `measured_*`.

## Текст поверх

Появление и уход по альфе:

```bash
drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:\
textfile=/tmp/big.txt:fontcolor=white:fontsize=72:x=(w-text_w)/2:y=h*0.35:\
alpha='if(lt(t,1),t,if(lt(t,4),1,if(lt(t,5),5-t,0)))':enable='between(t,0,5)'
```

Текст подавать через `textfile=`, а не `text=` — иначе экранирование двоеточий, кавычек и процентов превращается в ад. Переносы строк в файле отрисуются как есть.

Цифра на экране: одна за кадр, всегда парой «было → стало», крупная (180–220 px) с обводкой `borderw=8`, подпись-единица под ней ~54 px. Появляется ровно тогда, когда её произносит голос, и висит ещё 1,2 с после конца фразы.

## Субтитры

Дублировать озвучку обязательно — лента стартует без звука.

```bash
-vf "subtitles=subs.srt:fontsdir=/usr/share/fonts:force_style='FontName=DejaVu Sans,\
Fontsize=54,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,\
BorderStyle=1,Outline=4,Shadow=2,Alignment=2,MarginV=380'"
```

`MarginV≈380` держит текст выше зоны интерфейса ленты. `BorderStyle=3` вместо `1` даёт сплошную плашку, если фон совсем пёстрый. Блоки по 2–4 слова, ключевая цифра отдельным блоком.

Тайминги слов ffmpeg не умеет (whisper-фильтр только с 7.x). Нужны караоке-сабы — `faster-whisper` с `word_timestamps=True`.

## Финальный энкод

```bash
ffmpeg -nostdin -y -i in.mp4 \
-vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p" \
-c:v libx264 -preset slow -crf 20 -profile:v high -level 4.0 \
-g 60 -keyint_min 60 -sc_threshold 0 -pix_fmt yuv420p -movflags +faststart \
-c:a aac -b:a 128k -ar 48000 -ac 2 out.mp4
```

Без `+faststart` и `yuv420p` телеграм отдаст ролик документом, а не видео.

Лимит `sendVideo` — 50 МБ. Ролик до минуты в этих настройках весит 8–20 МБ.

## Обложка

```bash
ffmpeg -nostdin -ss 00:00:01.5 -i out.mp4 -frames:v 1 -q:v 2 -update 1 cover.jpg
```

`-ss` ставить **до** `-i` — быстрый поиск.

## Гейт

```bash
ffmpeg -v error -xerror -i out.mp4 -f null - 2>err.log; test ! -s err.log
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height -of csv=p=0 out.mp4
```

Ждём `h264,1080,1920` и пустой `err.log`. У `ffprobe` флага `-nostdin` нет — в питоне закрывать stdin через `DEVNULL`.
