#!/usr/bin/env bash
# Гейт перед отправкой ролика. Ненулевой код возврата = не публиковать.
# Отчитываться об успехе только при exit 0.
#
#   bash verify.sh /opt/shorts/out/short-20260813-1435.mp4

set -u
V="${1:-}"
[ -z "$V" ] && { echo "нужен путь к mp4"; exit 2; }
[ -f "$V" ] || { echo "ПРОВАЛ: файла нет: $V"; exit 2; }

MIN_BYTES=${SHORTSMAKER_MIN_BYTES:-200000}
MIN_DUR=${SHORTSMAKER_MIN_DUR:-8}
MAX_DUR=${SHORTSMAKER_MAX_DUR:-90}
W_WANT=1080
H_WANT=1920

fail=0
say() { printf "  %-34s %s\n" "$1" "$2"; }

SIZE=$(stat -c%s "$V")
if [ "$SIZE" -lt "$MIN_BYTES" ]; then
  say "размер" "ПРОВАЛ ${SIZE} Б (нужно >= ${MIN_BYTES})"; fail=1
else
  say "размер" "ок ${SIZE} Б"
fi

read -r CODEC W H < <(ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,width,height -of csv=p=0 "$V" 2>/dev/null | tr ',' ' ')

if [ "${W:-0}" != "$W_WANT" ] || [ "${H:-0}" != "$H_WANT" ]; then
  say "кадр" "ПРОВАЛ ${W:-?}x${H:-?} (нужно ${W_WANT}x${H_WANT})"; fail=1
else
  say "кадр" "ок ${W}x${H} ${CODEC}"
fi

DUR_V=$(ffprobe -v error -select_streams v:0 -show_entries stream=duration \
  -of default=nw=1:nk=1 "$V" 2>/dev/null | head -1)
DUR_A=$(ffprobe -v error -select_streams a:0 -show_entries stream=duration \
  -of default=nw=1:nk=1 "$V" 2>/dev/null | head -1)

if [ -z "${DUR_A:-}" ] || [ "$DUR_A" = "N/A" ]; then
  say "звук" "ПРОВАЛ аудиопотока нет — озвучка не подмешалась"; fail=1
else
  say "звук" "ок ${DUR_A} с"
fi

if [ -n "${DUR_V:-}" ] && [ "$DUR_V" != "N/A" ]; then
  BAD=$(awk -v d="$DUR_V" -v lo="$MIN_DUR" -v hi="$MAX_DUR" 'BEGIN{print (d<lo||d>hi)?1:0}')
  if [ "$BAD" = "1" ]; then
    say "длительность" "ПРОВАЛ ${DUR_V} с (допуск ${MIN_DUR}..${MAX_DUR})"; fail=1
  else
    say "длительность" "ок ${DUR_V} с"
  fi
  if [ -n "${DUR_A:-}" ] && [ "$DUR_A" != "N/A" ]; then
    SKEW=$(awk -v a="$DUR_V" -v b="$DUR_A" 'BEGIN{d=a-b; print (d<0?-d:d)}')
    BADS=$(awk -v s="$SKEW" 'BEGIN{print (s>0.3)?1:0}')
    if [ "$BADS" = "1" ]; then
      say "рассинхрон" "ПРОВАЛ видео и звук расходятся на ${SKEW} с"; fail=1
    else
      say "рассинхрон" "ок ${SKEW} с"
    fi
  fi
else
  say "длительность" "ПРОВАЛ не читается"; fail=1
fi

# Полный декод — ловит обрыв и битые кадры, которых не видно в метаданных
ERR=$(mktemp)
ffmpeg -v error -xerror -nostdin -i "$V" -f null - 2>"$ERR"
if [ -s "$ERR" ]; then
  say "декод" "ПРОВАЛ $(head -c 160 "$ERR")"; fail=1
else
  say "декод" "ок, битых кадров нет"
fi
rm -f "$ERR"

# Телеграм отдаст документом вместо видео, если moov не в начале
if ffprobe -v error -show_entries format_tags -of default=nw=1 "$V" >/dev/null 2>&1; then
  if command -v mp4file >/dev/null 2>&1; then :; fi
fi
SZ_MB=$((SIZE / 1024 / 1024))
if [ "$SZ_MB" -gt 50 ]; then
  say "лимит телеграма" "ПРОВАЛ ${SZ_MB} МБ (sendVideo принимает до 50)"; fail=1
else
  say "лимит телеграма" "ок ${SZ_MB} МБ"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "ГЕЙТ ПРОЙДЕН: $V"
  exit 0
fi
echo "ГЕЙТ НЕ ПРОЙДЕН: $V — не публиковать"
exit 1
