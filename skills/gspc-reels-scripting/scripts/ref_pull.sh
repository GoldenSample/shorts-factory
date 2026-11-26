#!/usr/bin/env bash
# Чужой референс (Shorts / клип ВК / TikTok / Reels / файл) -> материалы для разбора. Запуск НА ХАБЕ <VPS_IP>.
# gspc-reels-scripting. Пишет только в /opt/shorts/reels_ref/<slug>/. Прод-код /opt/shorts/*.py не трогает.
#
#   bash ref_pull.sh <url | /путь/к/файлу.mp4> <slug> [lang]      lang: ru (умолчание) | en | auto
#
# Что делает:
#   1) meta.json   — метаданные yt-dlp без комментариев (просмотры, лайки, длительность, автор, дата, описание);
#   2) ref.mp4     — ролик до 1280 px по высоте, чанками 5M (грабля 403 на хабе, память game-footage-youtube);
#   3) ref16k.flac — звук для слуха;
#   4) asr.json    — слова с таймкодами: риг 5090 (POST /jobs/asr, faster-whisper large-v3),
#                    если риг молчит — запасной faster-whisper small на хабе (CPU, хуже на терминах);
#   5) cuts.txt    — времена склеек (ffmpeg scene > 0.3), frame0.jpg — первый кадр, sheet_NN.jpg — листы 2 кадра/с.
# Без входа в аккаунты и без cookies: закрытый ролик или Reels с требованием входа = попросить файл у Гора.
set -euo pipefail
SRC="${1:?url или файл}"; SLUG="${2:?slug латиницей}"; LANG_="${3:-ru}"
case "$SLUG" in *[!a-z0-9-]*|"") echo "slug только a-z 0-9 -"; exit 2;; esac
D="/opt/shorts/reels_ref/$SLUG"; mkdir -p "$D"; cd "$D"
RIG="http://10.77.0.2:9099"

if [ -f "$SRC" ]; then
  cp -f "$SRC" ref.mp4; echo '{"source":"file"}' > meta.json
else
  yt-dlp --dump-json --skip-download --no-write-comments --no-playlist "$SRC" > meta.full.json
  python3 - <<'PY'
import json
d = json.load(open("meta.full.json", encoding="utf-8"))
keep = ["id", "webpage_url", "extractor", "title", "uploader", "channel", "channel_url", "upload_date", "duration",
        "view_count", "like_count", "comment_count", "description", "width", "height", "license"]
json.dump({k: d.get(k) for k in keep}, open("meta.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
PY
  rm -f meta.full.json
  yt-dlp -f "bv*[height<=1280]+ba/b[height<=1280]/b" --merge-output-format mp4 --no-part --http-chunk-size 5M \
    --no-playlist -o "ref.%(ext)s" "$SRC"
  [ -f ref.mp4 ] || { f=$(ls ref.* | grep -v -e '\.json$' | head -1); ffmpeg -nostdin -y -v error -i "$f" -c copy ref.mp4; }
fi
DUR=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 ref.mp4)
echo "длительность $DUR с"

ffmpeg -nostdin -y -v error -i ref.mp4 -vn -ac 1 -ar 16000 -sample_fmt s16 -c:a flac ref16k.flac

ASR=""
Q="lang=$LANG_"; [ "$LANG_" = auto ] && Q=""
if curl -s -m 8 -o /dev/null "$RIG/catalog.md"; then
  id=$(curl -s -m 120 --data-binary @ref16k.flac "$RIG/jobs/asr?$Q" | python3 -c 'import json,sys; print(json.load(sys.stdin)["job"])') || id=""
  if [ -n "$id" ]; then
    for i in $(seq 1 120); do
      s=$(curl -s -m 10 "$RIG/jobs/$id" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status"))' || echo "?")
      [ "$s" = done ] && break; [ "$s" = error ] && break; sleep 5
    done
    [ "$s" = done ] && curl -s -m 60 -o asr.json "$RIG/files/$id.json" && ASR="rig large-v3 job $id"
  fi
fi
if [ -z "$ASR" ]; then
  echo "риг не ответил: запасной слух small на хабе"
  LANG_="$LANG_" /opt/shorts/venv/bin/python - <<'PY'
import json, os
from faster_whisper import WhisperModel
lang = os.environ.get("LANG_", "ru")
m = WhisperModel("small", device="cpu", compute_type="int8")
segs, info = m.transcribe("ref16k.flac", language=None if lang == "auto" else lang, word_timestamps=True,
                          vad_filter=True, condition_on_previous_text=False)
out = {"file": "ref", "dur": info.duration, "model": "small-hub", "segs": []}
for s in segs:
    out["segs"].append({"s": s.start, "e": s.end, "t": s.text.strip(),
                        "w": [[w.start, w.end, w.word, w.probability] for w in (s.words or [])]})
json.dump(out, open("asr.json", "w", encoding="utf-8"), ensure_ascii=False)
PY
  ASR="hub small"
fi
echo "слух: $ASR"

ffmpeg -nostdin -v info -i ref.mp4 -vf "select='gt(scene,0.3)',showinfo" -an -f null - 2>&1 \
  | grep -o 'pts_time:[0-9.]*' | cut -d: -f2 > cuts.txt || true
echo "склеек: $(wc -l < cuts.txt)"
ffmpeg -nostdin -y -v error -i ref.mp4 -vf "select=eq(n\,0),scale=540:-2" -frames:v 1 frame0.jpg
ffmpeg -nostdin -y -v error -i ref.mp4 -vf "fps=2,scale=180:-2,tile=8x4:padding=4:color=0x070A12" sheet_%02d.jpg
ls -la "$D"
