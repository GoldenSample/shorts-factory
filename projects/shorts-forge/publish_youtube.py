# -*- coding: utf-8 -*-
r"""ПУБЛИКАЦИЯ НА YOUTUBE (Data API v3) — сменный модуль слоя публикации.
Библиотека (`from publish_youtube import publish`) и CLI одновременно.
Цены и лимиты — в COST и константах ниже (ревизия 01.06.2026, поля сверены с
discovery rev 20260723). captions.insert НЕ зовём: 400 юнитов из общего пула
против 1 вызова бакета, поэтому субтитры вжигаем в кадр.

⛔ ЗАКОН МОДУЛЯ: квота списывается ЗА ВЫЗОВ, а не за созданное видео. Повтор
   упавшей заливки обязан ПРОДОЛЖАТЬ старую resumable-сессию: куски (PUT в
   session URI) бесплатны, платит только POST, открывающий сессию.

Разовая авторизация: python publish_youtube.py auth (дальше headless; service
account для заливки НЕ работает, нужен OAuth владельца канала).
⚠ google-api-python-client есть только в hermes-venv, в системном Python 3.12 нет:
   py -3.12 -m pip install google-api-python-client google-auth google-auth-oauthlib
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
import sys
import time
from datetime import datetime, timedelta, timezone

# токен общий с alchim-channel: одна авторизация служит обоим проектам
SANDBOX = pathlib.Path(os.environ.get("LOCALAPPDATA", r"C:\Users\Administrator\AppData\Local"))
CLIENT_SECRET = SANDBOX / "laplace-sandbox" / "secrets" / "yt_client_secret.json"
TOKEN_STORE = SANDBOX / "laplace-sandbox" / "secrets" / "yt_token.json"
# состояние — в проекте, а не в песочнице: песочницу сносит сброс Claude,
# а потеря счётчика квоты = въезд в потолок вслепую
STATE = pathlib.Path(__file__).resolve().parent / "_state"
LEDGER_F, SESSIONS = STATE / "quota.json", STATE / "sessions"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]
COST = {"videos.insert": 100, "thumbnails.set": 50, "playlistItems.insert": 50,
        "videos.list": 1, "channels.list": 1, "captions.insert": 400}
INSERT_BUCKET_MAX, UNITS_POOL_MAX = 100, 10000  # бакет (вызовы/сутки) и общий пул (юниты)
SAFETY_RESERVE, MAX_SESSIONS_PER_FILE = 300, 2  # резерв пула под диагностику; лимит сессий на файл
CHUNK = 8 * 1024 * 1024                         # кратно 256 КБ

try:
    from zoneinfo import ZoneInfo
    _PT = ZoneInfo("America/Los_Angeles")
except Exception:
    _PT = None              # нет пакета tzdata (системный Python на Windows)

class QuotaExhausted(RuntimeError): """Потолок квоты: ждать сброса, а не ретраить."""
class FatalUpload(RuntimeError): """Ретраить бессмысленно: метаданные, права, файл."""
class AccountBlocked(RuntimeError): """Похоже на бан/страйк канала, а не на квоту."""

def pt_now() -> datetime:
    """Сейчас по Pacific — там полночь сбрасывает квоту. zoneinfo требует tzdata,
    которого в системном Python на Windows НЕТ, отсюда запасное правило США."""
    u = datetime.now(timezone.utc)
    if _PT:
        return u.astimezone(_PT)

    def nth_sunday(month: int, nth: int) -> datetime:
        d = datetime(u.year, month, 1, tzinfo=timezone.utc)
        return d + timedelta(days=(6 - d.weekday()) % 7 + 7 * (nth - 1))
    dst = nth_sunday(3, 2) + timedelta(hours=10) <= u < nth_sunday(11, 1) + timedelta(hours=9)
    return u.astimezone(timezone(timedelta(hours=-7 if dst else -8)))

class Ledger:
    """Счётчик потраченного, ключ = дата по Pacific. Бакет videos.insert (в
    вызовах) и общий пул (в юнитах) считаются РАЗДЕЛЬНО. Пишем атомарно и
    перечитываем перед каждой операцией — иначе параллельные прогоны затрут друг друга."""

    def __init__(self, path: pathlib.Path = LEDGER_F):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict:
        day = pt_now().strftime("%Y-%m-%d")
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            d = {}
        return d if d.get("day") == day else {"day": day, "inserts": 0, "units": 0, "log": []}

    def _write(self, d: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def spend(self, method: str, note: str = "") -> None:
        """Списать ДО вызова. Бросает QuotaExhausted, если не влезаем."""
        d, cost = self._read(), COST.get(method, 1)
        if method == "videos.insert":
            if d["inserts"] + 1 > INSERT_BUCKET_MAX:
                raise QuotaExhausted(f"бакет videos.insert исчерпан: {d['inserts']}/"
                                     f"{INSERT_BUCKET_MAX} за {d['day']} (PT). Сброс {self.until_reset()}.")
            d["inserts"] += 1
            # ⚠ юниты бакета в общий пул НЕ идут (ревизия 01.06.2026): иначе после
            # 100 заливок пул «кончится» ложно и отвалится дешёвая диагностика.
        else:
            if d["units"] + cost > UNITS_POOL_MAX - SAFETY_RESERVE:
                raise QuotaExhausted(f"пул исчерпан: {d['units']}+{cost} при потолке "
                                     f"{UNITS_POOL_MAX}-{SAFETY_RESERVE} резерва.")
            d["units"] += cost
        d["log"] = (d["log"] + [{"t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 "m": method, "note": note}])[-200:]
        self._write(d)

    def refund(self, method: str) -> None:
        """Вернуть слот, только если ДОКАЗАНО, что запрос не дошёл до сервера."""
        d = self._read()
        if method == "videos.insert":
            d["inserts"] = max(0, d["inserts"] - 1)
        else:
            d["units"] = max(0, d["units"] - COST.get(method, 1))
        self._write(d)

    @staticmethod
    def until_reset() -> str:
        now = pt_now()
        nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        h, m = divmod(int((nxt - now).total_seconds()) // 60, 60)
        return f"через {h}ч {m}м"

    def report(self) -> str:
        d = self._read()
        return (f"квота на {d['day']} (PT): insert {d['inserts']}/{INSERT_BUCKET_MAX} · "
                f"пул {d['units']}/{UNITS_POOL_MAX} · сброс {self.until_reset()}")

def _status(e) -> int:
    return getattr(getattr(e, "resp", None), "status", 0) or getattr(e, "status_code", 0) or 0

def _reason(e) -> str:
    """Машинная причина из тела: quotaExceeded, rateLimitExceeded, forbidden..."""
    try:
        body = json.loads((e.content or b"{}").decode("utf-8", "replace"))
        errs = body.get("error", {}).get("errors") or []
        return (errs[0].get("reason") if errs else "") or body.get("error", {}).get("status", "")
    except Exception:
        return ""

RETRY_STATUS = {500, 502, 503, 504}
RETRY_REASONS = {"rateLimitExceeded", "userRateLimitExceeded", "backendError",
                 "internalError", "SERVICE_UNAVAILABLE"}
QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded", "uploadLimitExceeded"}
BAN_REASONS = {"youtubeSignupRequired", "channelClosed", "channelSuspended", "forbidden"}

def classify(e) -> str:
    """-> 'retry' | 'quota' | 'ban' | 'session_gone' | 'fatal'"""
    st, rs = _status(e), _reason(e)
    if st in RETRY_STATUS or rs in RETRY_REASONS:
        return "retry"
    if st == 403:
        return "quota" if rs in QUOTA_REASONS else ("ban" if rs in BAN_REASONS else "fatal")
    if st in (404, 410):
        return "session_gone"      # resumable-сессия протухла
    return "retry" if st == 401 else "fatal"

def backoff(n: int) -> float:
    """Экспонента с полным джиттером, потолок 64с: без джиттера параллельные
    прогоны синхронно долбят сервер после общего сбоя."""
    return random.uniform(0, min(64.0, 2.0 ** n))

def credentials(interactive: bool = False):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    creds = None
    if TOKEN_STORE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_STORE), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_STORE.write_text(creds.to_json(), encoding="utf-8")
    if not creds or not creds.valid:
        if not interactive:
            raise FatalUpload(f"нет валидного OAuth-токена {TOKEN_STORE}. "
                              f"Разовая авторизация: python publish_youtube.py auth")
        from google_auth_oauthlib.flow import InstalledAppFlow
        if not CLIENT_SECRET.exists():
            raise FatalUpload(f"нет {CLIENT_SECRET} (OAuth client ID типа Desktop app)")
        creds = InstalledAppFlow.from_client_secrets_file(
            str(CLIENT_SECRET), SCOPES).run_local_server(port=0)
        TOKEN_STORE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_STORE.write_text(creds.to_json(), encoding="utf-8")
    return creds

def service(interactive: bool = False):
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=credentials(interactive), cache_discovery=False)

def shorts_body(title: str, description: str = "", tags: list | None = None,
                privacy: str = "private", publish_at: str | None = None, category: str = "27",
                ai_made: bool = True, lang: str = "ru", add_hashtag: bool = False) -> dict:
    """Тело videos.insert для вертикального шортса. ШОРТСОМ ролик делают
    вертикаль/квадрат + длительность <=3 мин, и только они: классификация идёт по
    файлу, метаданными не управляется, поэтому #shorts НЕ обязателен и оставлен
    опцией под A/B. ЯРЛЫК ИИ = status.containsSyntheticMedia (поле есть в
    discovery rev 20260723); раскрытие монетизации не вредит, сокрытие даёт
    основание для санкций. publishAt работает ТОЛЬКО при privacyStatus=private."""
    desc = description.rstrip()
    if add_hashtag and "#shorts" not in desc.lower():
        desc = (desc + "\n\n#shorts").strip()
    body = {
        "snippet": {"title": title[:100], "description": desc[:5000],
                    "tags": (tags or [])[:60], "categoryId": category,
                    "defaultLanguage": lang, "defaultAudioLanguage": lang},
        "status": {"privacyStatus": privacy,
                   "selfDeclaredMadeForKids": False,     # объявить обязательно
                   "containsSyntheticMedia": bool(ai_made),
                   "license": "youtube", "embeddable": True},
    }
    if publish_at:
        if privacy != "private":
            raise FatalUpload("publishAt разрешён только при privacyStatus=private")
        body["status"]["publishAt"] = publish_at
    return body

def rfc3339(when: datetime) -> str:
    """Время -> UTC RFC3339, формат publishAt."""
    if when.tzinfo is None:
        when = when.astimezone()
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _session_file(video: pathlib.Path) -> pathlib.Path:
    SESSIONS.mkdir(parents=True, exist_ok=True)
    st = video.stat()
    return SESSIONS / f"{video.stem}_{st.st_size}_{int(st.st_mtime)}.session.json".replace(" ", "_")

def _resume(svc, sess: pathlib.Path):
    """Поднять недокачанный запрос из сохранённой сессии — продолжение БЕСПЛАТНО.
    ⛔ ГРАБЛИ БИБЛИОТЕКИ (проверено на google-api-python-client 2.194.0): to_json()
    кладёт resumable_uri и resumable_progress в JSON, а from_json() собирает
    запрос конструктором, который таких аргументов НЕ ПРИНИМАЕТ, и оба поля молча
    теряются. Запрос выглядит валидным, но сессии у него нет: следующий
    next_chunk() открыл бы НОВУЮ и списал бакет ещё раз."""
    from googleapiclient.http import HttpRequest
    from googleapiclient.model import JsonModel
    raw = sess.read_text(encoding="utf-8")
    req = HttpRequest.from_json(raw, svc._http, JsonModel().response)
    saved = json.loads(raw)
    req.resumable_uri = saved.get("resumable_uri")
    req.resumable_progress = saved.get("resumable_progress") or 0
    if not req.resumable_uri:
        raise ValueError("в сохранённой сессии нет resumable_uri")
    return req

GATES = pathlib.Path(__file__).resolve().parents[2] / "tools"


def posting_gate(video) -> list[str]:
    """POSTLOCK-1024 (аудит 23.10 п.17, совет Grok: замок внутри скрипта отправки, а не только хук браузера):
    viral_gate (упаковка про этот файл, обложка, плашка, петля) и toolkit_gate --posting (карта до рендера, печать, подпись Гора).
    Пустой список = можно. Ошибка или таймаут гейта = нельзя."""
    import subprocess
    fails = []
    for args in ([str(GATES / "viral_gate.py"), str(video)], [str(GATES / "toolkit_gate.py"), "check", str(video), "--posting"]):
        try:
            r = subprocess.run([sys.executable] + args, capture_output=True, text=True, encoding="utf-8", timeout=120)
            if r.returncode != 0:
                fails.append((r.stdout or r.stderr).strip())
        except Exception as e:
            fails.append(f"гейт {pathlib.Path(args[0]).name} не отработал: {e!r}")
    return fails


def upload_video(svc, video: pathlib.Path, body: dict, ledger: Ledger, log=print) -> str:
    """Заливка с продолжаемой сессией -> videoId. Есть сохранённая — продолжаем
    даром; нет — списываем слот ДО вызова и пишем URI на диск после каждого куска;
    протухшая сессия стоит нового слота, отсюда MAX_SESSIONS_PER_FILE."""
    fails = posting_gate(video)
    if fails:
        raise FatalUpload("ГЕЙТ ПОСТИНГА: " + "\n".join(fails))
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    sess, req, fresh = _session_file(video), None, False
    if sess.exists():
        try:
            req = _resume(svc, sess)
            log(f"  продолжаю прежнюю сессию (квота не тронута): {sess.name}")
        except Exception as e:
            log(f"  сохранённая сессия не читается ({e}), открою новую")
            sess.unlink(missing_ok=True)
    used, attempt, resp = 0, 0, None
    while resp is None:
        if req is None:
            if used >= MAX_SESSIONS_PER_FILE:
                raise FatalUpload(f"лимит новых сессий ({MAX_SESSIONS_PER_FILE}) на "
                                  f"{video.name} исчерпан — дальше это жгло бы бакет впустую")
            ledger.spend("videos.insert", note=video.name)   # ПЕССИМИСТИЧНО, до вызова
            used, fresh = used + 1, True
            media = MediaFileUpload(str(video), chunksize=CHUNK, resumable=True,
                                    mimetype="video/mp4")
            req = svc.videos().insert(part="snippet,status", body=body, media_body=media)
            log(f"  открываю сессию #{used} · {ledger.report()}")
        try:
            # ⚠ первый кусок = POST, создающий сессию: num_retries ОБЯЗАН быть 0,
            # иначе библиотека молча пересоздаст сессию и спишет бакет повторно.
            status, resp = req.next_chunk(num_retries=0 if fresh else 3)
            fresh = False
            if resp is None and getattr(req, "resumable_uri", None):
                # пишем после КАЖДОГО куска: на диске всегда свежий offset, значит
                # падение процесса стоит максимум один кусок, а не слот бакета
                sess.write_text(req.to_json(), encoding="utf-8")
            if status:
                log(f"  залито {int(status.progress() * 100)}%")
            attempt = 0
        except HttpError as e:
            kind = classify(e)
            if kind == "quota":
                raise QuotaExhausted(f"403 {_reason(e)} на заливке. {ledger.report()}") from e
            if kind == "ban":
                raise AccountBlocked(f"403 {_reason(e)} — похоже на блокировку канала") from e
            if kind == "session_gone":
                log("  сессия протухла (404/410) — потребуется новая")
                sess.unlink(missing_ok=True)
                req, fresh = None, False
                continue
            if kind != "retry":
                sess.unlink(missing_ok=True)
                raise FatalUpload(f"HTTP {_status(e)} {_reason(e)}: {str(e)[:200]}") from e
            attempt += 1
            if attempt > 6:
                raise FatalUpload("исчерпаны ретраи на временных ошибках") from e
            w, alive = backoff(attempt), bool(getattr(req, "resumable_uri", None))
            log(f"  временная ошибка {_status(e)}, пауза {w:.1f}с "
                f"({'сессия жива, повтор даром' if alive else 'сессия не открылась'})")
            time.sleep(w)
            if not alive:
                req = None   # POST не открыл сессию: новый пойдёт через общий учёт
        except OSError as e:   # ConnectionError — подкласс OSError, ловится сюда же
            # обрыв связи. Если сессия уже открыта — она жива, тянем дальше.
            if fresh and not getattr(req, "resumable_uri", None):
                ledger.refund("videos.insert")   # POST не дошёл, слот не потрачен
                used, req = used - 1, None
                log(f"  обрыв до открытия сессии — слот возвращён ({e})")
            attempt += 1
            if attempt > 6:
                raise FatalUpload(f"сеть не поднялась: {e}") from e
            time.sleep(backoff(attempt))
    sess.unlink(missing_ok=True)
    return resp["id"]

def after_upload(svc, vid: str, ledger: Ledger, thumb=None, playlist=None, log=print) -> None:
    """Обложка (50) и плейлист (50): оба необязательны и НЕ валят публикацию —
    ролик уже залит. Частый штатный отказ обложки = канал не верифицирован."""
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    jobs = []
    if thumb and pathlib.Path(thumb).is_file():
        jobs.append(("thumbnails.set", "обложка", lambda: svc.thumbnails().set(
            videoId=vid, media_body=MediaFileUpload(str(thumb))).execute()))
    if playlist:
        jobs.append(("playlistItems.insert", "плейлист", lambda: svc.playlistItems().insert(
            part="snippet", body={"snippet": {"playlistId": playlist, "resourceId": {
                "kind": "youtube#video", "videoId": vid}}}).execute()))
    for method, name, call in jobs:
        try:
            ledger.spend(method, note=vid)
            call()
            log(f"  {name}: ок")
        except (HttpError, QuotaExhausted) as e:
            log(f"  {name} не прошла: {e}")

def verify(svc, vid: str, ledger: Ledger) -> dict:
    """Судьба ролика. ВАЖНО: бан канала приходит НЕ как 403 на заливке, а именно
    сюда — uploadStatus=rejected + rejectionReason uploaderAccountSuspended /
    uploaderAccountClosed / termsOfUse."""
    ledger.spend("videos.list", note=vid)
    items = svc.videos().list(part="status", id=vid).execute().get("items", [])
    if not items:
        return {"found": False}
    st = items[0]["status"]
    out = {"found": True, "uploadStatus": st.get("uploadStatus"), "privacy": st.get("privacyStatus"),
           "rejectionReason": st.get("rejectionReason"), "failureReason": st.get("failureReason")}
    if out["rejectionReason"] in ("uploaderAccountSuspended", "uploaderAccountClosed"):
        raise AccountBlocked(f"канал заблокирован: {out['rejectionReason']}")
    return out

def diagnose(svc, ledger: Ledger) -> str:
    """Квота или бан, цена 1 юнит. Бакет videos.insert отдельный от пула: если
    дешёвый channels.list проходит, аккаунт жив и токен цел, значит упёрлись в
    квоту; если и он даёт 403 — это доступ/аккаунт."""
    from googleapiclient.errors import HttpError
    try:
        ledger.spend("channels.list", note="diagnose")
        items = svc.channels().list(part="status,snippet", mine=True).execute().get("items", [])
        if not items:
            return "ДИАГНОЗ: токен валиден, но канал не виден — проверь, тем ли аккаунтом вошёл"
        ch = items[0]
        return (f"ДИАГНОЗ: КВОТА, не бан. Канал «{ch['snippet']['title']}» жив "
                f"(isLinked={ch['status'].get('isLinked')}). {ledger.report()}")
    except HttpError as e:
        if _status(e) == 403:
            return (f"ДИАГНОЗ: НЕ квота. 403 {_reason(e)} даже на дешёвом channels.list — "
                    f"это доступ/аккаунт (бан, отозванный токен, выключенный API)")
        return f"ДИАГНОЗ неясен: HTTP {_status(e)} {_reason(e)}"

def publish(video, title: str, description: str = "", tags: list | None = None,
            privacy: str = "private", publish_at: str | None = None,
            thumbnail: str | None = None, playlist_id: str | None = None,
            ai_made: bool = True, add_hashtag: bool = False, log=print) -> dict:
    """Полный цикл: заливка -> обложка -> плейлист -> проверка статуса."""
    video = pathlib.Path(video)
    if not video.is_file():
        raise FatalUpload(f"нет файла {video}")
    ledger, svc = Ledger(), service()
    body = shorts_body(title, description, tags, privacy, publish_at,
                       ai_made=ai_made, add_hashtag=add_hashtag)
    log(f"  {ledger.report()}")
    vid = upload_video(svc, video, body, ledger, log=log)
    log(f"  залито: https://youtu.be/{vid}")
    after_upload(svc, vid, ledger, thumbnail, playlist_id, log=log)
    state = verify(svc, vid, ledger)
    log(f"  статус: {state}")
    return {"video_id": vid, "url": f"https://youtu.be/{vid}", "status": state,
            "quota": ledger.report()}

def main() -> int:
    ap = argparse.ArgumentParser(description="Публикация ролика на YouTube (Data API v3)")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("auth", help="разовая браузерная авторизация -> token.json")
    sub.add_parser("quota", help="показать потраченное за сутки (PT)")
    sub.add_parser("diagnose", help="квота или бан (стоит 1 юнит)")
    up = sub.add_parser("upload", help="залить ролик")
    up.add_argument("video")
    up.add_argument("--title", required=True)
    up.add_argument("--desc", default="")
    up.add_argument("--tags", default="", help="через запятую")
    up.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    up.add_argument("--publish-at", help="RFC3339 UTC, напр. 2026-08-01T15:00:00Z")
    up.add_argument("--in-hours", type=float, help="проще: опубликовать через N часов")
    up.add_argument("--thumb")
    up.add_argument("--playlist")
    up.add_argument("--no-ai-label", action="store_true", help="снять ярлык ИИ-контента")
    up.add_argument("--hashtag", action="store_true", help="дописать #shorts (не обязателен)")
    up.add_argument("--go", action="store_true", help="боевой прогон; без него DRY")
    a = ap.parse_args()
    if a.cmd == "auth":
        credentials(interactive=True)
        return print(f"OK -> {TOKEN_STORE}. Дальше headless.") or 0
    if a.cmd == "quota":
        return print(Ledger().report()) or 0
    if a.cmd == "diagnose":
        return print(diagnose(service(), Ledger())) or 0
    if a.cmd != "upload":
        ap.print_help()
        return 1
    fails = posting_gate(a.video)       # POSTLOCK-1024: до расчёта времени выхода и до DRY-отчёта
    if fails:
        print("ГЕЙТ ПОСТИНГА: НЕЛЬЗЯ\n" + "\n".join(fails))
        return 1
    pub_at = rfc3339(datetime.now(timezone.utc) + timedelta(hours=a.in_hours)) \
        if a.in_hours else a.publish_at
    tags = [t.strip() for t in a.tags.split(",") if t.strip()]
    body = shorts_body(a.title, a.desc, tags, a.privacy, pub_at,
                       ai_made=not a.no_ai_label, add_hashtag=a.hashtag)
    if not a.go:   # DRY по умолчанию — домашнее правило: без --go ничего не жечь
        extra = 1 + (50 if a.thumb else 0) + (50 if a.playlist else 0)
        print(json.dumps(body, ensure_ascii=False, indent=2))
        print(f"\n  {Ledger().report()}")
        print(f"  DRY: квота цела. Боевой прогон = 1 вызов бакета + {extra} юнитов пула. Добавь --go")
        return 0
    try:
        r = publish(a.video, a.title, a.desc, tags, a.privacy, pub_at, a.thumb,
                    a.playlist, ai_made=not a.no_ai_label, add_hashtag=a.hashtag)
    except QuotaExhausted as e:
        print(f"СТОП, КВОТА: {e}\n  " + diagnose(service(), Ledger()))
        return 2
    except AccountBlocked as e:
        return print(f"СТОП, АККАУНТ: {e}") or 3
    except FatalUpload as e:
        return print(f"ОТКАЗ: {e}") or 1
    print(f"\nВЕРДИКТ: ОПУБЛИКОВАНО -> {r['url']}\n  {r['quota']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
