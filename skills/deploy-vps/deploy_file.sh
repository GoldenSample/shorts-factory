#!/usr/bin/env bash
# Выкат файлов shortsmaker на VPS: сверка с историей git -> замок -> проверка синтаксиса -> бэкап -> атомарная замена -> md5.
#
#   bash deploy_file.sh [--plan|--dry] [--new] [--allow-drift] [--force-lock] [--shared-ok] <путь в репо> [...]
#
#   --plan         без сети: локальные проверки и план (что куда, какие команды)
#   --dry          читает сервер (md5, git-хеш, тип, замок), ничего не пишет
#   --new          разрешить файл, которого на сервере ещё нет
#   --allow-drift  заменить, хотя версии сервера нет ни в одной версии файла в git или она только в чужой
#                  ветке (правили руками / не влито; только по слову Гора)
#   --force-lock   выкатывать при занятом замке ночного прогона (только по слову Гора)
#   --shared-ok    правка разрушает данные прода TechPulse (docker rm/prune, DROP; только по слову Гора, глазами проверено)
#
# Куда: vps/X -> /opt/shorts/X, infra/vps-audit/X -> /opt/vps-audit/X. Больше никуда.
# Два прохода: сначала проверки и состояние сервера по ВСЕМ файлам, запись только если все прошли.
# Дрейф (правили на сервере руками) = содержимого сервера нет ни в одной версии файла в git: сервер считает
#   git-хеш блоба (sha1 от "blob <размер>\0" + файл), здесь он ищется по всей истории (git log --raw).
# Бэкап (DEPLOY.md раздел 15): /opt/backups/deploy-<метка>/<полный путь>; откат прогона: cp -a <каталог>/opt/. /opt/
# Окружение: DEPLOY_HOST (root@<VPS_IP>), DEPLOY_KEY (~/.ssh/gspc_deploy), DEPLOY_REPO (корень репо).
set -euo pipefail

HOST=${DEPLOY_HOST:-root@<VPS_IP>}
KEY=${DEPLOY_KEY:-$HOME/.ssh/gspc_deploy}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(realpath -m "${DEPLOY_REPO:-$HERE/../../..}")
TS=$(date +%Y%m%d-%H%M%S)
BAK=/opt/backups/deploy-$TS
SSH=(ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout=15 "$HOST")
SCP=(scp -q -i "$KEY" -o BatchMode=yes -o ConnectTimeout=15)

MODE=apply NEW=0 DRIFT=0 FORCELOCK=0 SHAREDOK=0
FILES=()
for a in "$@"; do
  case "$a" in
    --plan) MODE=plan ;;
    --dry) MODE=dry ;;
    --new) NEW=1 ;;
    --allow-drift) DRIFT=1 ;;
    --force-lock) FORCELOCK=1 ;;
    --shared-ok) SHAREDOK=1 ;;
    -h|--help) sed -n '2,19p' "$0"; exit 0 ;;
    -*) echo "неизвестный флаг: $a" >&2; exit 2 ;;
    *) FILES+=("$a") ;;
  esac
done
[ ${#FILES[@]} -gt 0 ] || { echo "нужен хотя бы один путь, например vps/say.py" >&2; exit 2; }
[ -d "$REPO/.git" ] || { echo "не нашёл репо: $REPO (задай DEPLOY_REPO)" >&2; exit 2; }

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

say() { printf '%s\n' "$*"; }
die() { printf 'СТОП: %s\n' "$*" >&2; exit 1; }

rel_path() {
  local p=$1
  command -v cygpath >/dev/null 2>&1 && p=$(cygpath -u "$p" 2>/dev/null || printf '%s' "$p")
  case "$p" in
    /*) p=$(realpath -m --relative-to="$REPO" "$p") ;;
    *) [ -e "$p" ] && [ ! -e "$REPO/$p" ] && p=$(realpath -m --relative-to="$REPO" "$(realpath "$p")") ;;
  esac
  printf '%s' "${p#./}"
}

# Путь подставляется в команду на сервере: никаких .., кавычек, пробелов, $, `, \.
bad_path() {
  case "$1" in
    *..*|*\ *|*\'*|*\"*|*\$*|*\`*|*\\*|*\;*|*\&*|*\|*) return 0 ;;
  esac
  return 1
}

remote_path() {
  case "$1" in
    vps/*) printf '/opt/shorts/%s' "${1#vps/}" ;;
    infra/vps-audit/*) printf '/opt/vps-audit/%s' "${1#infra/vps-audit/}" ;;
    *) return 1 ;;
  esac
}

refuse_reason() {
  case "$1" in
    *.env|*console.env|*auth.json|*vk_user.json|*rclone.conf|*.pem|*.key|*.p12|*.token|*id_rsa*|*google_*.json|*service_account*.json)
      echo "секреты в git и на сервер этим путём не ездят" ;;
    infra/systemd/*) echo "юнит: нужен daemon-reload и restart, см. docs/DEPLOY.md раздел 7" ;;
    infra/cron.d/*|infra/crontab.root) echo "крон: правка через crontab/cron.d и строка PATH, см. docs/DEPLOY.md раздел 11" ;;
    infra/memora/*) echo "memora: после выката нужен патч кириллицы, см. память memora-mcp" ;;
    *) remote_path "$1" >/dev/null || echo "путь вне vps/ и infra/vps-audit/: этот скрипт его не выкатывает (сайт - только scripts/deploy.sh своего репо)" ;;
  esac
}

kind_of() {
  case "$1" in
    *.py) echo py ;;
    *.sh) echo sh ;;
    *.json) echo json ;;
    *) echo other ;;
  esac
}

# Добавленные строки правки ($1 = база, $2 = новый файл), которые РАЗРУШАЮТ данные прода TechPulse.
# 06.10.2026 Гор: «прода Вани не существует, это мой прод» - перезапуск, exec, psql, /opt/news-aggregator не ловим.
# Ловим: удаление контейнеров и образов, чистку, тома, DELETE/TRUNCATE/DROP по таблице news, DROP базы/схемы.
shared_hits() {
  local base=$1 new=$2 f=$3 re
  re='docker(-compose)?["'"'"', ]+(rm|rmi|kill|system|volume|builder|image["'"'"', ]+(rm|prune))([^a-z_]|$)'
  re+='|(DELETE[[:space:]]+FROM|TRUNCATE([[:space:]]+TABLE)?|DROP[[:space:]]+TABLE)[[:space:]]+(public\.)?news([^a-z_]|$)'
  re+='|DROP[[:space:]]+(DATABASE|SCHEMA)'
  # номер строки - в новом файле
  diff --old-line-format='' --unchanged-line-format='' --new-line-format='%dn: %L' "$base" "$new" \
    | grep -E "^[0-9]+: .*($re)" | cut -c1-140 || true
}

# Последний коммит, в котором файл стал блобом $2 (git-хеш содержимого сервера). Вся история, без лимита:
# сначала история HEAD, потом остальные ветки. Печатает "<коммит> head" или "<коммит> other"; не нашёл - пусто.
# awk без раннего exit: под pipefail SIGPIPE у git уронил бы подстановку.
blob_commit() {
  local f=$1 b=$2 c scope
  for scope in HEAD --all; do
    c=$(git -C "$REPO" log --full-history -m --format='C %H' --raw --no-abbrev "$scope" -- "$f" 2>/dev/null \
      | awk -v b="$b" '$1 == "C" {c = $2; next} !hit && /^:/ && $4 == b {print c; hit = 1}')
    if [ -n "$c" ]; then
      [ "$scope" = HEAD ] && printf '%s head' "$c" || printf '%s other' "$c"
      return 0
    fi
  done
}

REL=() TGT=() KIND=() MD5=() ACT=()
i=0
# ---------- проход 1: проверки, ничего не пишет ----------
for raw in "${FILES[@]}"; do
  f=$(rel_path "$raw")
  say "== $f"
  ! bad_path "$f" || die "$f: в пути .., пробел, кавычка или спецсимвол - такой путь не выкатываю"
  why=$(refuse_reason "$f" || true)
  [ -z "$why" ] || die "$f: $why"
  [ -f "$REPO/$f" ] || die "$f: нет такого файла в репо"
  t=$(remote_path "$f")
  kind=$(kind_of "$f")

  # grep в Git Bash без -U молча срезает \r и CRLF не видит, поэтому tr
  # 01.10 так лежали 25 файлов vps/: в индексе LF, в рабочей копии CRLF (core.autocrlf=true)
  if [ "$(tr -cd '\r' < "$REPO/$f" | wc -c)" -gt 0 ]; then
    if git -C "$REPO" diff --quiet -- "$f" 2>/dev/null && git -C "$REPO" cat-file -e "HEAD:$f" 2>/dev/null \
       && [ "$(git -C "$REPO" show "HEAD:$f" | tr -cd '\r' | wc -c)" -eq 0 ]; then
      die "$f: в рабочей копии CRLF, а в git LF (старый чекаут). Вернуть LF: git -C $REPO checkout -- $f"
    fi
    die "$f: в файле CRLF, на Linux bash, крон и шебанг сломаются; перевести в LF"
  fi
  md5_local=$(md5sum "$REPO/$f" | cut -d' ' -f1)
  if git -C "$REPO" cat-file -e "HEAD:$f" 2>/dev/null; then
    md5_head=$(git -C "$REPO" show "HEAD:$f" | md5sum | cut -d' ' -f1)
    git -C "$REPO" show "HEAD:$f" > "$WORK/head.$i"
  else
    md5_head=untracked
    : > "$WORK/head.$i"
  fi
  say "   сервер:   $HOST:$t"
  say "   локально: $md5_local   HEAD: $md5_head"
  if [ "$md5_head" = untracked ]; then
    say "   внимание: файла нет в git (новый). Это твой файл? После выката закоммитить (commit)"
  elif [ "$md5_local" != "$md5_head" ]; then
    say "   внимание: файл не закоммичен ($(git -C "$REPO" diff --shortstat HEAD -- "$f" 2>/dev/null | sed 's/^ *//')). Это твоя правка? Чужую незакоммиченную работу не выкатывать. После выката закоммитить (commit)"
  fi

  if [ "$MODE" = plan ]; then
    hits=$(shared_hits "$WORK/head.$i" "$REPO/$f" "$f")
    [ -z "$hits" ] || say "   внимание: относительно HEAD правка разрушает данные прода TechPulse - при выкате будет СТОП без --shared-ok:
$(printf '%s\n' "$hits" | sed 's/^/      /')"
    say "   план: md5, git-хеш и замок на сервере -> версия сервера в истории git? -> scp в $t.deploy-new -> md5 -> проверка ($kind) -> копия в $BAK$t -> mv -> md5"
    i=$((i + 1)); continue
  fi

  # состояние сервера (только чтение): md5 (или ABSENT/SYMLINK), замок без захвата, git-хеш блоба,
  # git-хеш того же файла без \r (01.10 на сервере лежали CRLF-копии 25 файлов vps/, залитых из старого чекаута)
  checklock=0
  case "$t" in /opt/shorts/*) checklock=1 ;; esac
  state=$("${SSH[@]}" bash -s -- "$t" "$checklock" <<'STATE'
t=$1; checklock=$2; blob=-; lfblob=-
if [ -L "$t" ]; then echo SYMLINK
elif [ -f "$t" ]; then
  md5sum "$t" | cut -d' ' -f1
  blob=$({ printf 'blob %s\0' "$(stat -c %s "$t")"; cat "$t"; } | sha1sum | cut -d' ' -f1)
  if [ "$(tr -cd '\r' < "$t" | wc -c)" -gt 0 ]; then
    lfblob=$({ printf 'blob %s\0' "$(sed 's/\r$//' "$t" | wc -c)"; sed 's/\r$//' "$t"; } | sha1sum | cut -d' ' -f1)
  fi
elif [ -e "$t" ]; then echo NOTFILE
else echo ABSENT; fi
st=LOCK_FREE
if [ "$checklock" = 1 ]; then
  # смотрим, держит ли кто-то flock, НЕ захватывая его: daily.sh делает flock -n и при занятом замке пропускает ночь
  for L in /var/lock/shorts.lock /var/lock/own.lock; do
    [ -e "$L" ] || continue
    if [ -r /proc/locks ]; then
      ino=$(stat -c %i "$L")
      grep -qE ":$ino[[:space:]]" /proc/locks && st="LOCK_BUSY($L)"
    else
      st="LOCK_UNKNOWN"
    fi
  done
fi
echo "$st"
echo "$blob"
echo "$lfblob"
STATE
) || die "$f: ssh не ответил"
  md5_remote=$(printf '%s\n' "$state" | sed -n 1p)
  lock=$(printf '%s\n' "$state" | sed -n 2p)
  blob_remote=$(printf '%s\n' "$state" | sed -n 3p)
  blob_lf=$(printf '%s\n' "$state" | sed -n 4p)
  say "   на сервере: $md5_remote $lock"

  [ "$md5_remote" != SYMLINK ] || die "$f: на сервере $t - симлинк, mv заменит его обычным файлом. Выкатывать руками"
  [ "$md5_remote" != NOTFILE ] || die "$f: на сервере $t - не обычный файл (каталог?). Выкатывать руками"
  case "$lock" in
    LOCK_FREE) ;;
    *) [ $FORCELOCK -eq 1 ] || die "$f: $lock - идёт ночной прогон или ручная сборка (или /proc/locks не читается). Ждать. --force-lock только по слову Гора." ;;
  esac

  base="$WORK/head.$i"
  if [ "$md5_remote" = "$md5_local" ]; then
    say "   уже на сервере, пропуск"; act=skip
  elif [ "$md5_remote" = ABSENT ]; then
    [ $NEW -eq 1 ] || die "$f: на сервере файла нет; если это новый файл - повторить с --new"
    : > "$base"; act=new
  else
    case "$blob_remote" in
      [0-9a-f][0-9a-f][0-9a-f][0-9a-f]*) ;;
      *) die "$f: сервер не отдал git-хеш файла ($blob_remote), сверить с историей нечем" ;;
    esac
    found=$(blob_commit "$f" "$blob_remote")
    lf_local=0 crlf=0
    # на сервере CRLF и как есть в git не нашлось: сверяем версию без \r (локальная правка или версия из git).
    # Это не ручной дрейф, а scp из старого чекаута Windows
    case "$found:$blob_lf" in
      :[0-9a-f][0-9a-f][0-9a-f][0-9a-f]*)
        if [ "$blob_lf" = "$(git -C "$REPO" hash-object --no-filters -- "$f")" ]; then
          lf_local=1 crlf=1
        else
          found=$(blob_commit "$f" "$blob_lf")
          [ -z "$found" ] || crlf=1
        fi ;;
    esac
    [ $crlf -eq 0 ] || say "   на сервере CRLF-копия (scp из старого чекаута Windows); без \\r совпала с версией ниже, выкат положит LF"
    hit=${found% *} where=${found#* }
    if [ $lf_local -eq 1 ]; then
      cp "$REPO/$f" "$base"
      say "   сервер = локальный файл, отличается только CRLF"
      act=replace
    elif [ -n "$found" ] && [ "$where" = head ]; then
      git -C "$REPO" show "$hit:$f" > "$base"
      n_after=$(git -C "$REPO" rev-list --count "$hit..HEAD" -- "$f")
      if [ "$n_after" -gt 0 ]; then
        say "   сервер на версии коммита ${hit:0:9}; выкат принесёт и $n_after коммит(а) после неё:"
        git -C "$REPO" log --format='      %h %ad %<(70,trunc)%s' --date=format:'%d.%m' "$hit..HEAD" -- "$f" | sed 's/ *$//'
      else
        say "   сервер = HEAD (${hit:0:9})"
      fi
      act=replace
    elif [ -n "$found" ]; then
      [ $DRIFT -eq 1 ] || die "$f: на сервере версия из коммита ${hit:0:9}, которого нет в истории HEAD (другая ветка, не влита).
   выкат затрёт правки той ветки: сначала влить её в текущую ветку, потом выкат. --allow-drift только по слову Гора."
      git -C "$REPO" show "$hit:$f" > "$base"
      say "   --allow-drift: версия сервера из другой ветки (${hit:0:9}), заменяю; копия будет в бэкапе"
      act=replace
    else
      [ $DRIFT -eq 1 ] || die "$f: содержимого сервера нет ни в одной версии файла в git - на сервере правили руками.
   забрать и сравнить: scp -i $KEY $HOST:$t ./$(basename "$f").server && diff ./$(basename "$f").server $REPO/$f
   слить в репо, закоммитить, потом выкат. --allow-drift только по слову Гора."
      say "   --allow-drift: версия сервера неизвестна, заменяю (ручные правки на сервере пропадут, копия будет в бэкапе)"
      act=replace
    fi
  fi

  if [ "$act" != skip ]; then
    hits=$(shared_hits "$base" "$REPO/$f" "$f")
    if [ -n "$hits" ]; then
      [ $SHAREDOK -eq 1 ] || die "$f: добавленные строки разрушают данные прода TechPulse (docker rm/prune, DROP):
$(printf '%s\n' "$hits" | sed 's/^/      /')
   выкат только по прямому слову Гора после проверки глазами: --shared-ok"
      say "   --shared-ok: разрушительная правка разрешена словом Гора"
    fi
  fi

  REL+=("$f") TGT+=("$t") KIND+=("$kind") MD5+=("$md5_local") ACT+=("$act")
  i=$((i + 1))
done

if [ "$MODE" = plan ]; then say "готово (plan)"; exit 0; fi
if [ "$MODE" = dry ]; then
  for k in "${!REL[@]}"; do
    case "${ACT[$k]}" in
      skip) say "dry: ${REL[$k]} - пропуск" ;;
      new) say "dry: ${REL[$k]} - новый файл, бэкапа нет (откат = rm -f ${TGT[$k]})" ;;
      *) say "dry: ${REL[$k]} - ${ACT[$k]}, бэкап в $BAK${TGT[$k]}" ;;
    esac
  done
  say "готово (dry)"; exit 0
fi

# ---------- проход 2: запись (все проверки уже прошли) ----------
DONE=()
rollback_hint() {
  [ ${#DONE[@]} -eq 0 ] && return 0
  printf 'уже заменены (откат каждого):\n' >&2
  printf '   %s\n' "${DONE[@]}" >&2
}
for k in "${!REL[@]}"; do
  f=${REL[$k]} t=${TGT[$k]} kind=${KIND[$k]} md5_local=${MD5[$k]}
  [ "${ACT[$k]}" != skip ] || continue
  say "== запись $f"
  "${SCP[@]}" "$REPO/$f" "$HOST:$t.deploy-new" || { rollback_hint; die "$f: scp не прошёл"; }
  out=$("${SSH[@]}" bash -s -- "$t" "$md5_local" "$BAK" "$kind" <<'REMOTE'
set -euo pipefail
t=$1; want=$2; bak=$3; kind=$4; new="$t.deploy-new"; ok=0; tmpd=""
cleanup() { [ "$ok" = 1 ] || rm -f "$new"; [ -z "$tmpd" ] || rm -rf "$tmpd"; }
trap cleanup EXIT
got=$(md5sum "$new" | cut -d' ' -f1)
[ "$got" = "$want" ] || { echo "FAIL md5 после scp: $got"; exit 3; }
[ ! -L "$t" ] || { echo "FAIL $t - симлинк"; exit 5; }
case "$kind" in
  py)
    # компилируем каждым интерпретатором, который гоняет конвейер: синтаксис 3.12 упадёт ночью под 3.11
    tmpd=$(mktemp -d); n=0
    for py in /usr/local/lib/hermes-agent/venv/bin/python3 /opt/shorts/venv/bin/python3 /usr/bin/python3; do
      [ -x "$py" ] || continue
      n=$((n + 1))
      if ! err=$("$py" -c 'import py_compile,sys; py_compile.compile(sys.argv[1], cfile=sys.argv[2], doraise=True)' "$new" "$tmpd/c.pyc" 2>&1); then
        echo "FAIL py_compile ($py): $(printf '%s' "$err" | tail -1)"; exit 4
      fi
    done
    [ "$n" -gt 0 ] || { echo "FAIL нет python3 для проверки"; exit 4; } ;;
  sh) bash -n "$new" 2>/dev/null || { echo "FAIL bash -n"; exit 4; } ;;
  json) python3 -m json.tool "$new" >/dev/null 2>&1 || { echo "FAIL json"; exit 4; } ;;
esac
if [ -e "$t" ]; then
  mkdir -p "$bak$(dirname "$t")"
  cp -a "$t" "$bak$t"
  chmod --reference="$t" "$new"
  chown --reference="$t" "$new"
else
  case "$t" in *.sh) chmod 755 "$new" ;; *) chmod 644 "$new" ;; esac
fi
mv -f "$new" "$t"
ok=1
echo "OK $(md5sum "$t" | cut -d' ' -f1)"
REMOTE
) || { rollback_hint; die "$f: на сервере не прошло: ${out:-нет ответа} (старый файл не тронут, временный убран)"; }
  say "   $out"
  case "$out" in "OK $md5_local") ;; *) rollback_hint; die "$f: md5 после замены не совпал: $out" ;; esac
  if [ "${ACT[$k]}" = new ]; then
    say "   новый файл; откат: ssh -i $KEY $HOST \"rm -f $t\""
    DONE+=("$f: ssh -i $KEY $HOST \"rm -f $t\"")
  else
    say "   бэкап: $BAK$t"
    say "   откат: ssh -i $KEY $HOST \"cp -a $BAK$t $t\""
    DONE+=("$f: ssh -i $KEY $HOST \"cp -a $BAK$t $t\"")
  fi
done
for k in "${!ACT[@]}"; do
  [ "${ACT[$k]}" != replace ] || { say "каталог бэкапа прогона: $BAK"; break; }
done
say "готово ($MODE)"
