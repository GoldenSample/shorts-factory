# Что переносится на Grok Imagine от других видеомоделей

Дата: 2026-09-10. Ось 3 сборки скила `video-prompting`. Задача: прочитать гайды по промптингу Veo 3 / 3.1, Sora 2, Kling, Runway Gen-4, Luma Ray, Pika и вынуть ТОЛЬКО переносимое на Grok Imagine: структуру промпта по слотам, язык движения камеры и объекта, длительность и темп, работает ли негатив, как заказывают глубину резкости и один источник света, чем промпт на 5 с отличается от промпта на 10 с.

Читателю: Grok Imagine (`grok-imagine-video-1.5`) НЕ имеет полей `negative_prompt`, `seed`, `guidance_scale` (docs.x.ai, проверено в `docs/research/broll/imagine.md` разд. 1.1). Поэтому всё, что у других моделей живёт в отдельном поле или в параметре, у нас переносится либо в текст промпта, либо не переносится вообще. Каждый пункт ниже помечен: **ПЕРЕНОСИТСЯ** / **ПЕРЕНОСИТСЯ С ОГОВОРКОЙ** / **НЕ ПЕРЕНОСИТСЯ**.

Метки достоверности: ЗАМЕРЕНО = цифра или бинарный факт из официальной доки либо из воспроизводимого теста; ПРАКТИКА = рабочий приём без цифр; МНЕНИЕ = оценка без проверки.

Файл пишется по ходу: каждый источник - отдельный блок, синтез в конце.

---

## 1. Источники по ходу

### 1.1. OpenAI Cookbook, Sora 2 Prompting Guide (официальный)
https://developers.openai.com/cookbook/examples/sora/sora2_prompting_guide

- ЗАМЕРЕНО (док): официальный каркас промпта Sora 2 из четырёх именованных блоков, дословно:
```
[Prose scene description]

Cinematography:
Camera shot: [framing and angle]
Mood: [overall tone]

Actions:
- [Action 1: specific beat]
- [Action 2: distinct beat]
- [Action 3: action or dialogue]

Dialogue:
[Brief natural lines matching clip length]
```
  Сам OpenAI пишет, что это «not a one-size-fits-all recipe for success». **ПЕРЕНОСИТСЯ**: подтверждает нашу схему «блоки с именами капсом» из `imagine-prompting` (ЗАМЕРЕНО на картинках: `СВЕТ: СУБЪЕКТ: ПАЛИТРА: КАДР:` не теряются). Три из четырёх блоков Sora у нас уже есть; блок `Dialogue` для перебивок среды не нужен, вместо него у нас ЗАМОК.
- ЗАМЕРЕНО (док): **длительность меняет не слова, а КОЛИЧЕСТВО БИТОВ.** Дословно: «A 4-second shot will usually accommodate one or two short exchanges, while an 8-second clip can support a few more». **ПЕРЕНОСИТСЯ** - это первый найденный численный ответ на вопрос «чем промпт на 5 с отличается от промпта на 10 с»: 4-5 с = один бит, 8-10 с = 2-3 бита. Наш ENV-промпт на 8 с должен нести ровно два движения (главное + вторичное), что совпадает с текущей практикой банка.
- ЗАМЕРЕНО (док): действия писать «beats or counts - small steps, gestures, or pauses». Слабый пример против сильного дословно: «Actor walks across the room» против «Actor takes four steps to the window, pauses, and pulls the curtain in the final second». **ПЕРЕНОСИТСЯ ПРЯМО**: это тот же приём, что даёт наш рабочий кадр «крыльчатка проворачивается на четверть оборота за весь клип» - счёт и привязка ко времени клипа вместо наречия. Формула: [сколько] + [чего] + [к какой секунде].
- ПРАКТИКА (док): оптика указывается форматом «35 mm virtual lens», «40 mm spherical» ПЛЮС фраза глубины резкости с целью изоляции: «shallow focus to isolate the couple from skyline». **ПЕРЕНОСИТСЯ С ОГОВОРКОЙ**: у нас на картинках `f/1.4, shallow depth of field, bokeh background` сработало, а миллиметры перспективу не двигали (замер `imagine-prompting`). Полезен именно хвост «to isolate X from Y» - объяснение, ЧТО отделяем.
- ПРАКТИКА (док): свет задаётся источниками и их ролями плюс палитра якорями: «soft window light with warm lamp fill, cool rim from hallway», «warm key from overhead practical; cool spill from window for contrast», «palette anchors: amber, cream, walnut brown». **ПЕРЕНОСИТСЯ**: совпадает с нашим замером (свет схемой, палитра перечнем). Слово `practical` (источник, видимый в кадре) - готовый термин для наших ламп, подсветки и индикаторов.
- ЗАМЕРЕНО (док): «The prompt controls the content of the video, but certain attributes are governed only by API parameters. You cannot request them in prose, they must be set explicitly in your API call» - это про model, size, seconds, character references. **ПЕРЕНОСИТСЯ**: не писать в тело промпта «10 секунд», «1080p», «вертикально 9:16» вместо параметров `duration`, `resolution`, `aspect`. У нас `ENV_TAIL` содержит «вертикальный кадр девять к шестнадцати» при том, что `aspect="9:16"` уже передан параметром - это дубль, который ест вес промпта. (Оговорка: у Grok замок пропорции в тексте не мерен, отдельным замером стоит проверить, лишний он или страхует.)
- Негатив: в гайде Sora 2 тема отрицаний НЕ обсуждается вообще. **НЕ ПЕРЕНОСИТСЯ** (нечего переносить).

### 1.2. Veo 3 Master Prompting Guide v5.0 (snubroot, GitHub, крупнейший community-свод)
https://github.com/snubroot/Veo-3-Prompting-Guide (читан raw README)

- ПРАКТИКА: структура из семи компонентов - Subject, Action, Scene, Style, Dialogue, Sounds, Technical/Negative. **ПЕРЕНОСИТСЯ ЧАСТИЧНО**: для перебивки среды без людей и звука живыми остаются четыре - Subject, Action, Scene (у нас = свет и фон), Style (у нас = оптика, палитра, вид) плюс седьмой Technical/Negative (у нас = ЗАМОК). То есть семислотник схлопывается в наш пятислотник, лишние два слота - речь и звук.
- ЗАМЕРЕНО (гайд): темп по секундам - «2-4 distinct actions with clear transitions» на 8 с, «one major action every 2-3 seconds». **НЕ ПЕРЕНОСИТСЯ ПРЯМО, ЗАПОМНИТЬ КАК ГРАНИЦУ**: это про сюжетный ролик с человеком. Для Grok порог ниже: aihubinfo мерил «four major actions in five seconds usually breaks coherence», а Elser формулирует «one subject, one principal action, one intentional camera move» (см. `imagine.md` 1.14, 1.23). Вывод: у Veo 2-4 действия на 8 с, у Grok потолок 2 (главное + вторичное). Разница моделей, не разница вкуса.
- ПРАКТИКА: движение камеры фразами-шаблонами: «Slow dolly-in from wide to medium shot», «Smooth tracking shot following subject», «Slow right-to-left pan across landscape», «Upward tilt revealing vertical scale», «High crane shot descending to eye level», «360-degree orbit shot around subject». **ПЕРЕНОСИТСЯ**: обрати внимание на конструкцию «ход + ОТ чего + К чему» («from wide to medium», «descending to eye level», «revealing vertical scale») - у Grok это ложится в правило higgsfield «описывать движение через стартовое и конечное положение, а не глаголом» (`cinema.md` S7b). Наши промпты сейчас пишут только глагол.
- ПРАКТИКА: глубина резкости словами «Shallow depth of field with subject in sharp focus, naturally blurred background», «Deep focus maintaining clarity from foreground to background», «Rack focus transition from foreground to background», «Telephoto lens compression effect flattening background». **ПЕРЕНОСИТСЯ**: формула «термин + что именно он делает с фоном». У нас на картинках ЗАМЕРЕНО, что описание результата («фон размыт до мягкой мути») работает надёжнее термина, а связка термин+результат покрывает оба случая.
- ПРАКТИКА: свет как готовая схема: «Professional three-point lighting with warm key light from camera left, subtle fill light softening shadows, rim lighting separating subject from background»; «Dramatic chiaroscuro with stark contrasts between light and shadow». **ПЕРЕНОСИТСЯ С ОГОВОРКОЙ**: трёхточка нам противопоказана (наш «дорогой» вид = один источник плюс negative fill, см. `cinema.md` 3.3), но синтаксис «роль света + сторона + что он делает» правильный. Брать конструкцию, не схему.
- ПРАКТИКА (негатив): рекомендуют один длинный список: «no text overlays, no watermarks, no cartoon effects, no unrealistic proportions, no blurry faces, no distorted hands, no artificial lighting, no oversaturation, no poor audio quality, no lip-sync issues, no camera shake, no compression artifacts». **НЕ ПЕРЕНОСИТСЯ ЦЕЛИКОМ**: у Veo негатив - отдельное поле `negativePrompt`, у Grok его нет, и всё это съело бы вес основного промпта. Переносится ровно тот кусок, что совпадает с нашим замером (слои: text overlays, watermarks) плюс замечание из выдачи Google Cloud-гайда: «only suppress a behavior when that behavior is actively fighting the shot» - подавлять только то, что реально лезет в кадр.
- ЗАМЕРЕНО (структура доков Google): у Veo `negativePrompt` - ОТДЕЛЬНЫЙ параметр API, у Grok Imagine такого параметра нет (docs.x.ai). Значит все Veo-гайды, где негатив вынесен в поле, для нас читаются только как список того, ЧТО обычно ломается, а не как готовый текст.

### 1.3. Luma Labs, официальная дока Dream Machine / Ray 2 (docs.lumalabs.ai)
https://docs.lumalabs.ai/docs/video-generation

- ЗАМЕРЕНО (док): ход камеры у Luma задаётся ЗАКРЫТЫМ СПИСКОМ строк. Дословно из доки: «find supported camera moves by calling the Camera Motions endpoint», эндпоинт возвращает точные строки вида `camera orbit left`. Похожие по смыслу фразы тоже работают, но «sometimes with mismatches». **ПЕРЕНОСИТСЯ КАК ПРИНЦИП, НЕ КАК СПИСОК**: у Grok закрытого списка нет и эндпоинта нет, но вывод тот же - держать СВОЙ фиксированный словарь ходов и не изобретать формулировку на каждый кадр. У нас такой словарь уже есть де-факто (`env_bank.py`, 12 русских фраз, 120/120 прошли судью) - его надо зафиксировать в скиле как закрытый перечень.
- ЗАМЕРЕНО (док): параметры `duration` (пример `"5s"`), `aspect_ratio`, `resolution` из `540p, 720p, 1080p, 4k`, булев `loop`. **ЧАСТИЧНО ПЕРЕНОСИТСЯ**: у Grok есть duration/aspect/resolution, но НЕТ параметра `loop`. Значит бесшовный луп у нас заказывается только текстом и остаётся непроверенным (в `imagine.md` 2.5 «looping» помечен как риск). Просить луп словами - слабая замена булеву флагу, для банка перебивок луп не закладывать.
- Негатива в доке Luma нет. **НЕ ПЕРЕНОСИТСЯ.**

### 1.4. Kling 2.5 Turbo Pro, карточка параметров (fal.ai, официальная схема API)
https://fal.ai/models/fal-ai/kling-video/v2.5-turbo/pro/text-to-video/api

- ЗАМЕРЕНО (схема API): `prompt` - «Recommended to keep under 2,500 characters»; `negative_prompt` со ЗНАЧЕНИЕМ ПО УМОЛЧАНИЮ `"blur, distort, and low quality"`; `cfg_scale` по умолчанию `0.5` («how closely the model follows your instructions»); `duration` только `5` или `10` секунд; `aspect_ratio` `16:9, 9:16, 1:1`.
- **ЧТО ЭТО ЗНАЧИТ ДЛЯ НАС.** Три вещи, которые у Kling лежат в параметрах, у Grok Imagine отсутствуют полностью: негатив, сила следования промпту (`cfg_scale`) и, соответственно, рычаг «слушайся буквально». Отсюда прямое правило для нашего скила: **у Grok единственный рычаг силы - формулировка и порядок слов, поэтому нельзя копировать чужие промпты, рассчитанные на `cfg_scale` и отдельный негатив.** Чужой промпт под Kling/Veo приходит «облегчённым», в нём нет того, что автор вынес в поля.
- ЗАМЕРЕНО: дефолтный негатив Kling - три слова про КАЧЕСТВО (`blur, distort, low quality`), а не про содержание. Это косвенно поддерживает наш вывод из `imagine.md` 2.1 п.7: отрицание слоя/качества у моделей с полем негатива - нормальная практика, но у Grok негатив живёт в теле промпта и конкурирует с описанием, поэтому список должен быть коротким.
- ЗАМЕРЕНО: сетка длительностей у Kling ровно 5/10 с. Совпадает по порядку с Veo (4/6/8) и Pika (5/10). **ВЫВОД ДЛЯ НАС**: индустрия пишет промпты под 5 и под 10, и разница между ними - число битов (см. 1.1), а не длина текста. У Grok шаг 1-15 с, то есть можно ставить 8 и 10 - но текст под 10 с должен нести второй бит, иначе вторая половина клипа «доигрывается» моделью произвольно (там и лезет морфинг).

### 1.5. Pika v2.2, схема параметров (fal.ai)
https://fal.ai/models/fal-ai/pika/v2.2/text-to-video/api

- ЗАМЕРЕНО (схема API): `negative_prompt` со значением по умолчанию `"ugly, bad, terrible"`; `seed`; `resolution` `720p`/`1080p` (дефолт 720p); `duration` `5` или `10` (дефолт 5); `aspect_ratio` семь вариантов, включая `9:16`.
- **ЧТО ПЕРЕНОСИТСЯ**: только вывод о разнице классов. У Pika, как и у Kling и Veo, есть и негатив, и `seed` (воспроизводимость). У Grok Imagine нет ни того, ни другого (docs.x.ai, наш замер на картинках: одинаковый промпт даёт разные кадры). Практическое следствие для нашего конвейера: **воспроизводимость у нас достигается только отбором из n, а не сидом** - то есть чужие методики «зафиксируй seed и меняй одну переменную» (higgsfield, `cinema.md` S7b) переносятся лишь наполовину: менять одну переменную можно, но сравнение всегда шумное, нужно n>=2 на каждую ветку.
- МНЕНИЕ: дефолтные негативы у Pika (`ugly, bad, terrible`) и Kling (`blur, distort, and low quality`) - оценочные слова про качество, а не про содержание. Это тот самый класс слов, который у нас на картинках ЗАМЕРЕНО не работает («драматичный», «качественно» без референта). Значит: **не копировать чужие дефолтные негативы в тело промпта Grok** - это чистый холостой ход, который ест вес.

### 1.6. Veo 3, схема параметров (fal.ai) - подтверждение классовой разницы
https://fal.ai/models/fal-ai/veo3/api

- ЗАМЕРЕНО (схема API): `negative_prompt` есть; `seed` есть; `duration` только `4s, 6s, 8s` (дефолт 8s); `resolution` `720p`/`1080p`; `aspect_ratio` `16:9`/`9:16`; `generate_audio` дефолт true; `auto_fix` дефолт true - «Whether to automatically attempt to fix prompts that fail content policy or other validation checks by rewriting them».
- **ПЕРЕНОСИТСЯ (важное)**: у Veo промпт может быть ПЕРЕПИСАН сервисом (по описанию - при провале проверок, но переписывание всё равно чужой рукой), у Grok такого флага в доке нет - наш промпт уходит в модель как есть, и всякая двусмысленность остаётся нашей проблемой, её никто не почистит.
- ЗАМЕРЕНО: сетка Veo 4/6/8 с. Сводка по сеткам (Veo 4/6/8, Kling 5/10, Pika 5/10, Sora 4/8/10/15, Luma 5/9, Grok 1-15): **все конкуренты работают дискретными шагами около 5 и около 10 с, и все гайды написаны под эти два случая.** Наши 8 с - «длинный» режим по чужой мерке, промпт под него должен быть двухбитным.

### 1.7. fal.ai Learn, How to Write Prompts That Work for Sora 2
https://fal.ai/learn/devs/how-to-write-prompts-sora-2

- ПРАКТИКА: три части промпта - Shot Description (начинать с ракурса и хода камеры), Subject and Action (конкретика вместо общего), Visual Style and Atmosphere. Дословно: «Begin with camera angle and movement». **ПЕРЕНОСИТСЯ**: третий независимый источник за то, что слот КАДР идёт первым (совпадает с `imagine.md` 2.2, где слот 1 - кадр и ход камеры).
- ЗАМЕРЕНО (таблица провалов, самое ценное в источнике):
  - «Default motion | Model adds movement automatically | Explicitly state "static shot" or "locked-off camera"» - **ПЕРЕНОСИТСЯ ЧАСТИЧНО**: у Sora дефолт = модель САМА добавляет движение, у Grok дефолт наоборот статика (Replicate, `imagine.md` 1.3). То есть замок «camera not moving» у нас страхует, а не воюет с дефолтом; но фраза `locked-off camera` - ещё один рабочий синоним в копилку.
  - «Temporal drift | Videos beyond 5-10 seconds | Use shorter clips; edit together» - **ПЕРЕНОСИТСЯ**: это ответ, почему наши 8 с безопаснее 12-15 даже там, где API разрешает. Прямое правило: длинную перебивку собирать монтажом из двух коротких, а не просить одну длинную.
  - «Subject morphing | Excessive complexity | Generate simpler shots; composite them» - совпадает с нашим «2-3 элемента среды максимум».
  - «Text rendering | Model limitation | Add text in post-production» - совпадает с нашим замером v6-v9 (псевдобуквы) и с решением класть титры на монтаже.
- ПРАКТИКА: сильный пример против слабого дословно: слабый «A cat playing with a ball», сильный «Close-up shot of a tabby cat batting a red yarn ball across hardwood floors, shallow depth of field with background bokeh, natural window light creating soft shadows, shot on 35mm film». Разбор: крупность -> субъект с действием -> ГРИП с указанием, что именно в боке -> источник света с эффектом -> носитель. **ПЕРЕНОСИТСЯ ПОЛНОСТЬЮ** - это тот же порядок, что у нас в шаблоне из 6 слотов.
- ПРАКТИКА: движение разбивать на этапы-вехи: «A paper airplane being thrown, gliding smoothly through the air, then landing gently on a desk» как «sequential waypoints». **ПЕРЕНОСИТСЯ С ОГОВОРКОЙ**: у Grok цепочки «затем... потом...» ломают когерентность (`imagine.md` 2.5 п.6). Значит вехи писать не цепочкой действий, а через СТАРТ и ФИНИШ одного движения («луч начинается у нижнего края и заканчивает у верхнего»), как советует higgsfield.
- МНЕНИЕ автора: якоря носителя и техники («Shot on Arri Alexa with anamorphic lenses», «16mm documentary style») «leverage visual patterns from training data». У нас НЕ ПРОВЕРЕНО (дыра из `imagine.md` 1.17). Ставить в `alt`, не в основной промпт.

### 1.8. Higgsfield, Sora 2 Prompt Guide
https://higgsfield.ai/sora-2-prompt-guide

- ПРАКТИКА: два режима промпта - «High-Control Format» (задать кадр, ГРИП, действие по битам, схему света и палитру) и «Short Prompt» (короткий описательный, модель сама решает кинематографию, «fast, creative, and low-spec results»). **ПЕРЕНОСИТСЯ**: подтверждает наблюдение jxp по Grok о двух рабочих длинах (1-8 слов либо 20-60 слов) и о вредной середине. Вывод: у нас два режима банка - «дешёвый веер» короткими промптами и «геройский кадр» полным шестислотником; смешивать нельзя.
- ПРАКТИКА: «tie one camera move to one character action per beat» - один ход камеры на один бит действия. **ПЕРЕНОСИТСЯ**: для 8 с с двумя битами это значит, что второй бит должен идти БЕЗ второго хода камеры (иначе два хода в клипе - наш известный убийца), то есть второй бит = движение среды или света.
- ПРАКТИКА: явно называть формат и темп («12-second spots», «Instagram Reels pace»). **НЕ ПЕРЕНОСИТСЯ**: у Grok это будет тот же холостой эпитет, что «cinematic»; темп у нас задаётся словами скорости и счётом (см. 1.1).

### 1.9. Google Cloud Blog, Ultimate prompting guide for Veo 3.1 (официальный, прочитан целиком под эту ось)
https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-veo-3-1

- ЗАМЕРЕНО (док): формула `[Cinematography] + [Subject] + [Action] + [Context] + [Style & Ambiance]`. Кинематография ПЕРВАЯ. **ПЕРЕНОСИТСЯ**: четвёртый независимый источник за порядок «кадр вперёд».
- ЗАМЕРЕНО (док), негатив дословно: «To refine your output, describe what you wish to exclude. For example, specify "a desolate landscape with no buildings or roads" instead of "no man-made structures"». **ПЕРЕНОСИТСЯ ПРЯМО И ЭТО ГЛАВНОЕ ИЗ ВСЕЙ ОСИ**: даже у модели с отдельным полем негатива официальная рекомендация - вшивать исключение В ОПИСАНИЕ СЦЕНЫ и называть конкретные объекты, а не категории. Для Grok, где поля нет вовсе, это единственный законный способ. Переписывание нашего замка по этому правилу: вместо «no added objects» - «на столе только плата и лампа, больше ничего»; вместо «no text» - «поверхность гладкая, без маркировки»; категориальный запрет («людей нет») оставляем только там, где он у нас уже ЗАМЕРЕН рабочим (120/120 по людям и рукам).
- ЗАМЕРЕНО (док): словари. Камера: dolly shot, tracking shot, crane shot, aerial view, slow pan, POV shot. Композиция: wide shot, close-up, extreme close-up, low angle, two-shot. Оптика: shallow depth of field, wide-angle lens, soft focus, **macro lens**, deep focus. **ПЕРЕНОСИТСЯ**: это ядро, которое понимают все модели поколения 2026, включая Grok (проверено по `imagine.art` и Replicate, `imagine.md` 1.22).
- ЗАМЕРЕНО (док): 4, 6 или 8 секунд.
- Пример, который нам ближе всего по устройству (свет как предмет сцены), дословно: «Medium shot, a tired corporate worker, rubbing his temples in exhaustion, in front of a bulky 1980s computer in a cluttered office late at night. The scene is lit by the harsh fluorescent overhead lights and the green glow of the monochrome monitor. Retro aesthetic, shot as if on 1980s color film, slightly grainy». Разбор для нас: свет назван ДВУМЯ конкретными источниками с их характером («harsh fluorescent overhead», «green glow of monochrome monitor»), а «стиль» - это носитель плюс зерно, не эпитет.
- ЗАМЕРЕНО (док): таймкодовый промпт `[00:00-00:02] ... [00:02-00:04] ...` официально поддержан у Veo для мультишотовых сцен, с SFX и эмоцией в каждом блоке. **НЕ ПЕРЕНОСИТСЯ (пока)**: у Grok таймкоды не документированы и не проверены (дыра из `imagine.md` 2.5). Но идея времени внутри промпта переносится в безопасной форме - через фразы «в первой трети / к концу клипа / over the whole clip», которые у нас уже работают.
- ЗАМЕРЕНО (док): звук задаётся тремя разными способами - речь в кавычках, `SFX:`, `Ambient noise:`. **ПЕРЕНОСИТСЯ С ОГОВОРКОЙ**: у Grok звук генерится по умолчанию (`generate_audio` true) и на монтаже выбрасывается, но пустой звуковой слот модель заполняет сама, часто музыкой, а музыка тянет за собой ритм монтажа внутри клипа. Дешёвая страховка - одна строка вида `Ambient noise: quiet room tone. No music.` (у Replicate `no music` числится рабочим).

### 1.10. Replicate, How to prompt Veo 3.1
https://replicate.com/blog/veo-3-1

- ПРАКТИКА: четыре рычага - композиция кадра («single shot», «two shot», «over-the-shoulder shot»), фокус и оптика («shallow focus», «deep focus», «soft focus», «macro lens», «wide-angle lens»), жанр как стиль, положение и ход камеры («eye level», «high angle», «worm's eye», «dolly shot», «zoom shot», «pan shot», «tracking shot»). **ПЕРЕНОСИТСЯ**: те же слова, что у Google и у гайдов по Grok - подтверждение, что ядро словаря общее для всех моделей и его можно писать по-английски внутри русского тела промпта.
- Замечание для нас: «жанр как стиль» («sci-fi», «action movie») для перебивок железа не годится - жанр тянет за собой людей, сюжет и монтаж. Наш эквивалент стиля - носитель и фактура («photoreal», «subtle film grain»), а не жанр.

### 1.11. Replicate, How to make remarkable videos with Seedance 2.0
https://replicate.com/blog/seedance-2

- ПРАКТИКА: «The process is something closer to directing than prompting». Мультишотовый вывод до 15 с, официально через таймкоды:
```
[0-4s]: wide establishing shot, static camera
[4-9s]: medium shot, slow push-in
[9-15s]: close-up, orbit shot
```
  **НЕ ПЕРЕНОСИТСЯ НА GROK**, и это важная граница: Seedance/Veo умеют РЕЗАТЬ внутри одного вывода («hard cut to», «seamless morph into»), Grok - нет, у нас склейка внутри клипа = брак (наш замок содержит `no cuts`). Значит чужие «продвинутые» промпты с таймкодами и переходами нельзя копировать: они рассчитаны на мультишот.
- ПРАКТИКА: физика словами - «Water moves with the right viscosity, splashes break apart correctly, surfaces behave like surfaces», «the vehicle bob as it navigates rough terrain». **ПЕРЕНОСИТСЯ КАК ФОРМУЛИРОВКА, НЕ КАК СЮЖЕТ**: конструкция «поверхность ведёт себя как поверхность» полезна («лопасть остаётся жёсткой, кромка не гнётся»), но сами всплески и жидкость у Grok в списке провалов (Vidguru, `imagine.md` 1.8).
- МНЕНИЕ автора (прямо против нашей практики): «Overdescribe» и якоря качества «hyper-realistic, 8k». У Grok «4K, 8K, ultra detailed» отнесены к шуму (jxp, `imagine.md` 2.5 п.9). **НЕ ПЕРЕНОСИТСЯ.** Держать в голове как пример того, что советы между моделями противоречат друг другу и слепой перенос вреден.

### 1.12. Runway, официальные dev-доки: рецепт Product Ad и список моделей
https://docs.dev.runwayml.com/recipes/product-ad/ , https://docs.dev.runwayml.com/guides/models/
(Справочный центр help.runwayml.com с гайдом по промптингу Gen-4 отдаёт 403 на автоматический запрос - взято из dev-доков.)

- ЗАМЕРЕНО (док): у рецепта продуктовой рекламы ДВА РАЗНЫХ текстовых поля: `productInfo` - «Product description and specifications to inform creative direction (max 2500 characters)» и `userConcept` - «brand voice, scene specifics, lighting, camera motion, and narrative (max 3500 characters)». Плюс отдельные референсные изображения продукта и отдельная style reference.
- **ПЕРЕНОСИТСЯ КАК ПРИНЦИП РАЗДЕЛЕНИЯ**: Runway разводит «что это за предмет» и «как это снято» по разным полям. У Grok поле одно, но разделение сохраняем внутри текста двумя блоками (`СУБЪЕКТ:` против `КАДР:`/`СВЕТ:`), и это ровно то, что viw.ai советовал для Grok («отделение блока камеры от блока субъекта предотвращает морфинг»). Совпадение двух независимых источников - основание держать блоки строго раздельными, а не мешать «лопасть в холодном свете медленно поворачивается, камера наезжает» в одну фразу.
- ЗАМЕРЕНО (док): «use `userConcept` to describe the scene and direction - let the product images define what the product looks like». **НЕ ПЕРЕНОСИТСЯ**: у нас image-to-video не работает (наш замер 05.09), поэтому идентичность предмета приходится держать словами. Отсюда практическое следствие: в наших промптах слот СУБЪЕКТ должен быть подробнее, чем в чужих продуктовых рецептах, - ту работу, которую у Runway делает фотография, у нас делает текст.
- ЗАМЕРЕНО (док): длительность рецепта 4-15 с, **дефолт 10**; ход камеры в рекомендациях - «slow dolly moves»; продукт должен быть «clearly isolated from its background».
- ЗАМЕРЕНО (док): `gen4_turbo` принимает только изображение, `gen4.5` - текст или изображение. Полезно знать при чтении чужих гайдов: половина рецептов Runway написана под image-to-video и для нашего text-to-video не годится вообще.

### 1.13. Wan 2.5 (Alibaba), схема параметров (fal.ai)
https://fal.ai/models/fal-ai/wan-25-preview/text-to-video/api

- ЗАМЕРЕНО (схема API): `prompt` «Supports Chinese and English, max 1500 characters»; `negative_prompt` «Max 500 characters»; `seed`; `duration` 5 или 10 (дефолт 5); `resolution` 480p/720p/1080p (дефолт 1080p); `enable_prompt_expansion` по умолчанию **true** - «Whether to enable prompt rewriting using LLM. Improves results for short prompts but increases processing time».
- **ГЛАВНОЕ ПЕРЕНОСИМОЕ**: у Wan (и у Veo через `auto_fix`) короткий промпт ДОПИСЫВАЕТСЯ языковой моделью перед генерацией. У Grok Imagine такого флага в документации нет. Отсюда: **чужие короткие «волшебные» промпты нельзя переносить как есть** - у автора его расширил LLM до нескольких абзацев, а у нас в модель уйдёт голая строка. Практический вывод для скила: наш промпт обязан быть самодостаточным (свет, фон, оптика прописаны явно), потому что за нас их никто не допишет. Это же объясняет, почему в чужих подборках встречаются промпты из шести слов с отличным результатом.
- ЗАМЕРЕНО: официальная поддержка двух языков промпта (китайский и английский) прописана в схеме. Русского в списке нет ни у кого из конкурентов. Наш случай (русское тело + английские термины оптики) остаётся непроверенным нигде, кроме нашего банка, - тем важнее собственный замер языка (дыра из `imagine.md` 1.19).

### 1.14. MiniMax Hailuo (Director-модель), закрытый список команд камеры
https://fal.ai/models/fal-ai/minimax/video-01-director/api , https://fal.ai/models/fal-ai/minimax/hailuo-02/standard/text-to-video/api

- ЗАМЕРЕНО (схема API), дословно: «Camera movement instructions can be added using square brackets (e.g. [Pan left] or [Zoom in]). You can use up to 3 combined movements per prompt. Supported movements: Truck left/right, Pan left/right, Push in/Pull out, Pedestal up/down, Tilt up/down, Zoom in/out, Shake, Tracking shot, Static shot». Комбинация в одной скобке разрешена: `[Truck left, Pan right, Zoom in]`, максимум три на промпт.
- **ПЕРЕНОСИТСЯ КАК ТАКСОНОМИЯ**: это полный список ходов, который производитель считает достаточным для видеомодели. Одиннадцать позиций, из них для перебивок железа годятся девять (Shake отпадает как тряска, Zoom отпадает как оптический зум - у нас он в замке под запретом). Наш русский словарь `env_bank.py` покрывает Push in/Pull out, Truck, Tracking, Static, Pan; НЕ покрыты Pedestal up/down (подъём и опускание камеры без наклона) и Tilt up/down - а именно вертикальные ходы лучше всего читаются в 9:16 (`cinema.md` 3.7). Это конкретная дыра нашего банка, закрывается двумя новыми фразами.
- ЗАМЕРЕНО: `prompt_optimizer` по умолчанию **true** (ещё одна модель, дописывающая промпт за автора); `duration` 6 или 10 с, причём «10 seconds videos are not supported for 1080p resolution».
- МНЕНИЕ: скобочный синтаксис `[Push in]` у Grok не документирован и не проверен; переносить стоит не синтаксис, а правило «не больше трёх ходов, а для нашей задачи - один».

### 1.15. Kling, параметры и `camera_control` (PiAPI, зеркало официальной схемы)
http://piapi.ai/docs/kling-api/create-task
(Официальный портал kling.ai отдаёт только JS-оболочку, поэтому взято зеркало схемы.)

- ЗАМЕРЕНО (схема): `prompt` до 2500 знаков, `negative_prompt` до 2500 знаков, `cfg_scale` «float between 0 and 1, it is strongly recommended to use 0.5», `duration` 5 или 10, `aspect_ratio` 16:9 / 9:16 / 1:1, `mode` std/pro.
- ЗАМЕРЕНО (схема): `camera_control` разложен на ШЕСТЬ ЧИСЛОВЫХ ОСЕЙ: `horizontal`, `vertical`, `pan`, `tilt`, `roll`, `zoom`. **ПЕРЕНОСИТСЯ КАК СПОСОБ ДУМАТЬ**: производитель считает движение камеры набором независимых осей, а не «красивой фразой». Для Grok это значит: описывая ход, называть ОДНУ ось и её направление («камера идёт вбок вправо» = truck, «камера поднимается» = pedestal, «камера доворачивает вправо» = pan), и никогда не смешивать оси в одной фразе. Наш известный убийца «два хода в одном промпте» на языке Kling звучит как «две ненулевые оси» - и это ровно то, чего производитель избегает конструкцией API.
- МНЕНИЕ: `roll` (крен, он же dutch) в нашем банке отсутствует и не нужен - в продуктовом биролe крен читается как дешёвый приём (`cinema.md` 4, п.10).

---

## 2. СИНТЕЗ: что переносится на Grok Imagine, а что нет

### 2.1. Классовая разница, из которой следует всё остальное

| Рычаг | Veo 3 | Sora 2 | Kling | Runway | Luma | Pika | Wan 2.5 | Hailuo | **Grok Imagine** |
|---|---|---|---|---|---|---|---|---|---|
| Отдельное поле негатива | есть | нет | есть (2500 зн.) | нет в t2v | нет | есть | есть (500 зн.) | нет | **НЕТ** |
| `seed` (воспроизводимость) | есть | нет | нет в схеме | нет | нет | есть | есть | нет | **НЕТ** |
| Сила следования (`cfg_scale`) | нет | нет | есть (0.5) | нет | нет | нет | нет | нет | **НЕТ** |
| Автопереписывание промпта | `auto_fix` true | нет | нет | нет | нет | нет | `enable_prompt_expansion` true | `prompt_optimizer` true | **НЕТ (не документировано)** |
| Мультишот внутри клипа | таймкоды | сториборд | нет | Seedance-рецепты | нет | нет | нет | нет | **НЕТ** |
| Сетка длительностей, с | 4/6/8 | 4 и 8 в гайде, 10/15 в приложении | 5/10 | 4-15 (дефолт 10) | 5 (пример в доке) | 5/10 | 5/10 | 6/10 | **1-15** |

Отсюда три правила чтения чужих гайдов, которые надо держать в голове ВСЕГДА:
1. **Чужой промпт приходит к нам неполным.** Всё, что автор вынес в `negative_prompt`, `cfg_scale`, референсные картинки и сид, у нас должно быть либо в тексте, либо принято как потеря. Копирование «как есть» даёт результат слабее, чем у автора.
2. **Чужой короткий промпт мог быть дописан за автора** (`prompt_expansion`, `prompt_optimizer`, `auto_fix` включены по умолчанию у Wan, Hailuo и Veo). У нас дописывать некому: короткий промпт остаётся коротким, и модель заполняет пустые слоты дефолтом (плоский пасмурный свет, серый фон).
3. **Чужой «продвинутый» приём может быть про мультишот.** Таймкоды Veo/Seedance, «hard cut to», «seamless morph into» рассчитаны на модель, которая умеет резать внутри вывода. Grok не умеет; у нас склейка внутри клипа - брак.

### 2.2. Структура промпта: что общего у всех шести моделей

Все официальные и полуофициальные каркасы сводятся к одному порядку. Совпадение источников (Sora Cookbook, Google Cloud Veo, fal Learn, snubroot, Higgsfield, Morphic по Grok):

| Слот | Veo 3.1 | Sora 2 | Seven-part Veo | fal Learn Sora | **Наш слот** |
|---|---|---|---|---|---|
| 1 | Cinematography | Camera shot | Style (кадр, ход) | Shot description | КАДР (крупность + оптика + ОДИН ход) |
| 2 | Subject | Prose scene | Subject | Subject and action | СУБЪЕКТ |
| 3 | Action | Actions (биты) | Action | (внутри 2) | ДВИЖЕНИЕ (главный бит + вторичный) |
| 4 | Context | (внутри prose) | Scene | Visual style and atmosphere | СВЕТ + ФОН |
| 5 | Style & Ambiance | Mood | Style/цвет | (внутри 3) | ПАЛИТРА И ВИД |
| 6 | - | Dialogue | Dialogue + Sounds | - | (нам не нужно; вместо этого ЗАМОК) |

**Вывод: наш шестислотник из `imagine.md` 2.2 совпадает с индустриальным стандартом, кроме одного - у нас вместо речи и звука стоит ЗАМОК.** Это правильная замена: у моделей с полем негатива замок живёт в поле, у нас ему больше негде быть.

Четыре независимых источника (Google Cloud, fal Learn, Higgsfield, Replicate) ставят КАДР первым слотом. Наш замер на картинках говорит, что порядок блоков не рычаг, но на видео это не мерено, а стоимость нулевая - значит кадр первым.

### 2.3. Как задают движение: пять переносимых приёмов

1. **Одна ось на клип.** Kling разложил ход камеры на шесть числовых осей, MiniMax дал закрытый список из одиннадцати команд с лимитом три. У нас - одна ось, названная словом. **ПЕРЕНОСИТСЯ.**
2. **Ход описывается стартом и финишем, а не глаголом.** Veo-шаблоны: «Slow dolly-in from wide to medium shot», «High crane shot descending to eye level», «Upward tilt revealing vertical scale». То же у higgsfield («описывать движение через стартовое и конечное положение»). У нас сейчас пишется только глагол («камера медленно наезжает»). **ПЕРЕНОСИТСЯ, ЭТО ПРЯМОЕ УЛУЧШЕНИЕ**: «камера медленно наезжает от общего плана стойки к крупному на разъёме» вместо «камера медленно наезжает».
3. **Действие - счётом и с привязкой ко времени клипа.** Sora Cookbook: «takes four steps to the window, pauses, and pulls the curtain in the final second». У нас это уже частично есть («четверть оборота за весь клип») - надо сделать правилом для всех сюжетов. **ПЕРЕНОСИТСЯ.**
4. **Второй бит без второго хода камеры.** Higgsfield: один ход камеры на один бит. Для 8-10 с нужно два бита, значит второй бит обязан быть движением света или среды, а не камеры. **ПЕРЕНОСИТСЯ.**
5. **Закрытый словарь ходов вместо импровизации.** Luma держит список строк в API, MiniMax - в описании параметра. У нас словарь должен быть зафиксирован в скиле и не расширяться на ходу. **ПЕРЕНОСИТСЯ.** Дыра: в нашем словаре нет вертикальных ходов (pedestal up/down, tilt up/down), а они лучше всех читаются в 9:16.

### 2.4. Длительность и темп: единственный численный ответ

- Sora Cookbook, ЗАМЕРЕНО: «A 4-second shot will usually accommodate one or two short exchanges, while an 8-second clip can support a few more».
- snubroot по Veo: 2-4 действия на 8 с, «one major action every 2-3 seconds».
- aihubinfo и Elser по Grok (из `imagine.md`): «four major actions in five seconds usually breaks coherence», «one subject, one principal action, one intentional camera move».
- fal Learn по Sora: «Temporal drift | Videos beyond 5-10 seconds | Use shorter clips; edit together».

**Рабочая шкала для Grok (свод, помечен как ПРАКТИКА, у нас не мерен):**

| Длительность | Число битов | Что писать | Чего не писать |
|---|---|---|---|
| 4-6 с | 1 | одно движение (свет ИЛИ предмет ИЛИ камера), финальное состояние названо | второе движение, ход камеры вдобавок к движению предмета |
| 8 с (наш дефолт) | 2 | главный бит + вторичное микродвижение; ОДИН ход камеры или его отсутствие | цепочки «затем», второй ход, склейки |
| 10 с | 2 + фаза | те же два бита плюс явная фаза «в последней трети свет гаснет» | третий бит, смена направления хода |
| 12-15 с | не брать | - | всё: за 10 с начинается temporal drift, дешевле склеить два клипа |

### 2.5. Негатив: сводный вердикт по всем источникам

- ЗАМЕРЕНО: у моделей с полем негатива дефолты - оценочные слова про качество (Kling `blur, distort, and low quality`; Pika `ugly, bad, terrible`). У Grok такие слова в теле промпта = холостой ход (наш замер по эпитетам).
- ЗАМЕРЕНО (Google Cloud Veo 3.1, дословно): «describe what you wish to exclude... specify "a desolate landscape with no buildings or roads" instead of "no man-made structures"». То есть даже при наличии поля правильный способ - **положительное описание сцены с названными объектами**.
- Наш собственный замер (`imagine.md`): отрицание СЛОЯ работает (люди, руки, надписи - 120/120), отрицание части объекта и качества - нет.

**Правило для скила (свод):** замок пишется в три хода, в таком порядке приоритета:
1. Положительно описать, что в кадре есть и чего в нём быть не может по устройству сцены: «на плоскости только плата и лампа», «поверхность гладкая, без маркировки».
2. Коротким перечнем запретить СЛОИ, по которым у нас есть замер: люди, руки, лица, надписи, логотипы, водяные знаки, музыка.
3. Замок постоянства положительной формой: «keep ... centered and structurally unchanged», «one continuous take» (Evolink, imagine.art «preservation language»).
Всё остальное - «no flicker», «no jitter», «no melting edges», «no morphing» - в скил как необязательный хвост не длиннее 5-6 слов; чужие простыни артефактов не копировать, они рассчитаны на отдельное поле.

### 2.6. Глубина резкости и один источник света

- Общий словарь оптики у всех моделей одинаков и работает по-английски: `shallow depth of field`, `deep focus`, `soft focus`, `macro lens`, `wide-angle lens`, `rack focus` (Google Cloud Veo, Replicate Veo, imagine.art по Grok).
- Sora Cookbook добавляет конструкцию с ЦЕЛЬЮ: «shallow focus to isolate the couple from skyline». snubroot - конструкцию с РЕЗУЛЬТАТОМ: «Shallow depth of field with subject in sharp focus, naturally blurred background». **ПЕРЕНОСИТСЯ**: писать термин + что он делает с фоном. Это перекрывает наш замер на картинках, где описание результата («фон размыт до мягкой мути») било голый термин.
- Свет во всех гайдах задаётся ИСТОЧНИКАМИ И ИХ РОЛЯМИ, а не настроением: «warm key from overhead practical; cool spill from window for contrast» (Sora), «harsh fluorescent overhead lights and the green glow of the monochrome monitor» (Veo). Термин `practical` (источник, видимый в кадре) - готовое слово для наших ламп, подсветки, индикаторов.
- Один источник: ни один чужой гайд не советует «единственный источник» прямо - там школа трёхточки. Наш «один источник + заполняющего света нет + negative fill» (из `cinema.md`) чужими гайдами НЕ подтверждается и остаётся нашей линией. **НЕ ПЕРЕНОСИТСЯ ОТ НИХ - ПЕРЕНОСИТСЯ К НИМ.**

### 2.7. Что НЕ переносить (список запретов при чтении чужих гайдов)

1. Таймкоды `[00:00-00:02]` и переходы «hard cut to», «seamless morph into» - мультишот, у Grok не документирован.
2. Дефолтные негативы Kling/Pika и простыни артефактов Veo - рассчитаны на поле, у нас едят вес.
3. Якоря разрешения «hyper-realistic, 8k», «4K» (Seedance советует, Grok-гайды относят к шуму).
4. Жанровые якоря «sci-fi», «action movie» - тянут людей и сюжет.
5. Трёхточечная схема света - противоречит нашей грамматике дорогого предметного кадра.
6. «Overdescribe» (Seedance) - у Grok busy-сцены теряют когерентность, потолок 2-3 элемента среды.
7. Указания параметров прозой («10 seconds», «1080p», «vertical 9:16») - Sora прямо пишет, что прозой это не задаётся; у нас есть параметры `duration`, `resolution`, `aspect`.
8. Промпты под image-to-video (половина рецептов Runway, все «reference-to-video») - у нас i2v не работает.
9. Сид-методики «зафиксируй seed, меняй одну переменную» - без сида сравнение шумное, нужно n>=2 на ветку.

### 2.8. Что добавить в наш конвейер по итогам оси (предложения, не правки)

1. В шаблон слота КАДР добавить «от чего к чему»: ход камеры с начальным и конечным планом.
2. В слот ДВИЖЕНИЕ добавить счёт и привязку ко времени клипа для КАЖДОГО сюжета (сейчас счёт есть в единичных промптах).
3. Зафиксировать закрытый словарь ходов камеры и дополнить его вертикальными ходами (pedestal up/down, tilt up/down) - под 9:16.
4. Переписать `ENV_TAIL` по правилу Veo: сначала положительное описание пустоты сцены, потом короткий перечень слоёв, потом замок постоянства. Убрать дубли параметров («вертикальный кадр девять к шестнадцати» при заданном `aspect`), убрать холостое «Кинематографично».
5. Ввести два режима банка: короткий промпт для дешёвого веера и полный шестислотник для геройских кадров; не смешивать (двухрежимность подтверждена Higgsfield и jxp).
6. Для клипов 10 с явно прописывать фазу второй половины, иначе там начинается drift.
7. Добавить строку звука `Ambient noise: quiet room tone. No music.` - защита от музыкального ритма внутри клипа.

---

## 3. Источники (прочитано под эту ось)

1. developers.openai.com/cookbook - Sora 2 Prompting Guide (официальный)
2. github.com/snubroot/Veo-3-Prompting-Guide - Veo 3 Master Prompting Guide v5.0
3. docs.lumalabs.ai/docs/video-generation - Luma Dream Machine / Ray 2 (официальный)
4. fal.ai - Kling 2.5 Turbo Pro, схема API
5. fal.ai - Pika v2.2, схема API
6. fal.ai - Veo 3, схема API
7. fal.ai/learn/devs - How to Write Prompts That Work for Sora 2
8. higgsfield.ai/sora-2-prompt-guide
9. cloud.google.com/blog - Ultimate prompting guide for Veo 3.1 (официальный)
10. replicate.com/blog/veo-3-1 - How to prompt Veo 3.1
11. replicate.com/blog/seedance-2 - Seedance 2.0
12. docs.dev.runwayml.com/recipes/product-ad - Runway Product Ad (официальный)
13. docs.dev.runwayml.com/guides/models - Runway, список моделей и входов
14. fal.ai - Wan 2.5 preview, схема API
15. fal.ai - MiniMax Hailuo 02 и Video-01-Director, схемы API (закрытый список команд камеры)
16. piapi.ai/docs/kling-api - схема Kling с `camera_control` по шести осям

Не открылись автоматически: help.runwayml.com (403, гайд по промптингу Gen-4), kling.ai/document-api (только JS-оболочка), docs.cloud.google.com (навигация без содержимого), docs.pika.art (нет DNS), lumalabs.ai/learning-hub (404).

(конец файла)


