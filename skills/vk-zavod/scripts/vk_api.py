# -*- coding: utf-8 -*-
"""Клиент VK API для завода GSPC: два ключа, загрузка медиа, разбор ошибок.

Разведка 18.09.2026 (shortsmaker/docs/research/vk/api.md, проверено скептиком):
- ключ А - ключ доступа СООБЩЕСТВА (бессрочный, выдаёт владелец в «Управление ->
  Работа с API»): истории, ответы на комментарии, обложка, адрес и часы,
  сообщения, Long Poll. wall.post им НЕЛЬЗЯ (ошибка 27);
- ключ Б - пользовательский ключ админа через своё приложение VK ID (живёт
  1 час, refresh 180 дней, refresh одноразовый): wall.post, загрузка фото и
  видео на стену, статистика. Права wall/photos/video ВК выдаёт «в
  исключительных случаях» по письму в devsupport@corp.vk.com;
- v=5.199, хост api.vk.ru, ключ в заголовке Authorization: Bearer, тело
  form-urlencoded или multipart; ошибка приходит в теле ответа HTTP 200.

Секреты только на VPS: /opt/shorts/vk.env (600) и /opt/shorts/vk_user.json
(600, пара access/refresh + device_id). В лог и чат ключи не печатаются.
"""
import fcntl
import json
import os
import random
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

API = os.environ.get("VK_API_HOST", "https://api.vk.ru/method/")
V = "5.199"
ENV = os.environ.get("VK_ENV", "/opt/shorts/vk.env")
USER_FILE = os.environ.get("VK_USER_FILE", "/opt/shorts/vk_user.json")
LOCK = "/run/vk_user.lock"
CALLS = os.environ.get("VK_CALLS_FILE", "/opt/shorts/vk_calls.json")
VKID = "https://id.vk.ru/oauth2/auth"

# коды, после которых повтор бессмыслен или опасен: стоп и тревога владельцу
FATAL = {3: "неизвестный метод", 7: "нет права у ключа", 8: "неверный запрос", 15: "доступ запрещён",
         17: "нужна валидация админа в браузере", 18: "страница админа удалена или заблокирована",
         27: "метод недоступен с ключом сообщества или ключ недействителен",
         28: "сервисный ключ недействителен", 100: "неверные параметры", 704: "у админа нет 2FA",
         13000: "страйки сообщества: все загрузки остановлены"}
PAUSE_DAY = {29: "количественный лимит метода", 214: "публикация запрещена или лимит постов"}


class VKError(Exception):
    def __init__(self, code, msg, method, fatal=False, pause=None):
        Exception.__init__(self, "VK %s: %s %s" % (method, code, msg))
        self.code, self.msg, self.method, self.fatal, self.pause = code, msg, method, fatal, pause


def load_env(path=ENV):
    env = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


class VK:
    """Один поток на ключ, темп с запасом: 2 запроса/с пользователь, 10/с сообщество."""

    def __init__(self, env=None, log=print):
        self.env = env if env is not None else load_env()
        self.log = log
        self.group_id = int(self.env.get("VK_GROUP_ID", "229049334"))
        self.owner_id = -self.group_id
        self._last = {"user": 0.0, "group": 0.0, "service": 0.0}

    # ---------------------------------------------------------------- ключи
    def has(self, kind):
        if kind == "group":
            return bool(self.env.get("VK_COMMUNITY_TOKEN"))
        if kind == "service":
            return bool(self.env.get("VK_SERVICE_TOKEN"))
        return os.path.exists(USER_FILE) and bool(self._user().get("refresh_token"))

    def _user(self):
        try:
            return json.load(open(USER_FILE, encoding="utf-8"))
        except Exception:
            return {}

    def _user_token(self):
        """Ключ Б с ротацией. Один владелец рефреша: блокировка файла, атомарная
        запись новой пары ДО первого использования нового access_token.
        Повтор старого refresh VK ID считает атакой и убивает всю сессию."""
        u = self._user()
        if u.get("access_token") and time.time() < float(u.get("expires_at", 0)) - 120:
            return u["access_token"]
        os.makedirs(os.path.dirname(LOCK), exist_ok=True)
        with open(LOCK, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            u = self._user()                      # мог обновить соседний процесс
            if u.get("access_token") and time.time() < float(u.get("expires_at", 0)) - 120:
                return u["access_token"]
            if not u.get("refresh_token"):
                raise VKError(5, "нет refresh_token: нужна первичная авторизация владельцем", "vkid",
                              fatal=True)
            body = {"grant_type": "refresh_token", "refresh_token": u["refresh_token"],
                    "client_id": self.env.get("VK_CLIENT_ID", ""), "device_id": u.get("device_id", ""),
                    "state": secrets.token_urlsafe(32)}
            if self.env.get("VK_CLIENT_SERVICE_TOKEN"):
                body["service_token"] = self.env["VK_CLIENT_SERVICE_TOKEN"]
            req = urllib.request.Request(VKID, data=urllib.parse.urlencode(body).encode(),
                                         headers={"Content-Type": "application/x-www-form-urlencoded"})
            try:
                d = json.loads(urllib.request.urlopen(req, timeout=60).read())
            except urllib.error.HTTPError as e:
                d = json.loads(e.read() or b"{}")
            if "access_token" not in d:
                err = d.get("error", "?")
                fatal = err in ("invalid_grant", "invalid_token", "access_denied")
                raise VKError(5, "VK ID refresh: %s" % err, "vkid", fatal=fatal)
            u.update(access_token=d["access_token"], refresh_token=d.get("refresh_token", u["refresh_token"]),
                     expires_at=time.time() + int(d.get("expires_in", 3600)),
                     refreshed_at=time.strftime("%Y-%m-%d %H:%M:%S"))
            tmp = USER_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(u, f)
            os.chmod(tmp, 0o600)
            os.replace(tmp, USER_FILE)
            return u["access_token"]

    def token(self, kind):
        if kind == "group":
            t = self.env.get("VK_COMMUNITY_TOKEN")
        elif kind == "service":
            t = self.env.get("VK_SERVICE_TOKEN")
        else:
            t = self._user_token()
        if not t:
            raise VKError(5, "нет ключа %s" % kind, "config", fatal=True)
        return t

    # ---------------------------------------------------------------- вызов
    def count(self):
        """Месячный счётчик вызовов: с 07.09.2026 до подтверждения бизнес-профиля
        приложению VK ID дают 10 000 вызовов в месяц (api.md, F06). Один общий
        счётчик на все ключи; на 80 % - тревога в лог, на 100 % - стоп."""
        month = time.strftime("%Y-%m")
        try:
            c = json.load(open(CALLS, encoding="utf-8"))
        except Exception:
            c = {}
        n = int(c.get(month, 0)) + 1
        c = {month: n}
        try:
            with open(CALLS + ".tmp", "w", encoding="utf-8") as f:
                json.dump(c, f)
            os.replace(CALLS + ".tmp", CALLS)
        except OSError:
            pass
        lim = int(self.env.get("VK_MONTHLY_LIMIT", "10000"))
        if n == int(lim * 0.8):
            self.log("  VK: израсходовано 80%% месячного лимита вызовов (%d из %d)" % (n, lim))
        if n > lim:
            raise VKError(29, "месячный лимит вызовов %d исчерпан" % lim, "counter", pause=86400)
        return n

    def call(self, method, params=None, kind="user", files=None):
        self.count()
        gap = 0.5 if kind == "user" else 0.1
        wait = self._last[kind] + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        p = {k: v for k, v in (params or {}).items() if v is not None}
        p["v"] = V
        backoff = [2, 8, 30]
        tries6 = 0
        refreshed = False
        while True:
            self._last[kind] = time.time()
            body, ctype = _encode(p, files)
            req = urllib.request.Request(API + method, data=body, headers={
                "Authorization": "Bearer " + self.token(kind), "Content-Type": ctype})
            try:
                d = json.loads(urllib.request.urlopen(req, timeout=120).read())
            except (urllib.error.URLError, OSError, ValueError) as e:
                if backoff:
                    time.sleep(backoff.pop(0))
                    continue
                raise VKError(-1, "сеть: %s" % str(e)[:120], method)
            if "response" in d:
                return d["response"]
            err = d.get("error") or {}
            code, msg = int(err.get("error_code", -1)), str(err.get("error_msg", ""))[:300]
            self.log("  VK %s -> ошибка %s %s" % (method, code, msg[:120]))
            if code in (1, 10) and backoff:
                time.sleep(backoff.pop(0))
                continue
            if code == 6 and tries6 < 3:
                tries6 += 1
                time.sleep(1 + random.random())
                continue
            if code == 5 and kind == "user" and not refreshed:
                refreshed = True
                u = self._user()
                u["expires_at"] = 0
                json.dump(u, open(USER_FILE, "w", encoding="utf-8"))
                continue
            if code == 14:
                # капчу не решаем и не обходим: стоп метода на час, тревога
                raise VKError(code, "капча: стоп метода на час", method, pause=3600)
            if code == 9:
                raise VKError(code, "flood control: метод на паузу час", method, pause=3600)
            if code in PAUSE_DAY:
                raise VKError(code, PAUSE_DAY[code] + ": " + msg, method, pause=86400)
            if code in FATAL or code == 5:
                raise VKError(code, FATAL.get(code, msg), method, fatal=True)
            raise VKError(code, msg, method)

    # ---------------------------------------------------------------- медиа
    def upload_wall_photo(self, path, caption=None):
        """photos.getWallUploadServer -> POST (поле photo) -> photos.saveWallPhoto. Ключ Б."""
        for attempt in range(2):
            srv = self.call("photos.getWallUploadServer", {"group_id": self.group_id})
            up = _post_file(srv["upload_url"], "photo", path)
            try:
                saved = self.call("photos.saveWallPhoto", {"group_id": self.group_id, "photo": up["photo"],
                                                           "server": up["server"], "hash": up["hash"],
                                                           "caption": caption})
                ph = saved[0]
                return "photo%s_%s" % (ph["owner_id"], ph["id"])
            except VKError as e:
                if e.code in (22, 114, 118, 121) and attempt == 0:
                    continue
                raise

    def upload_video(self, path, name, description="", repeat=0):
        """video.save -> POST (поле video_file). Ролик доступен «спустя некоторое время». Ключ Б."""
        s = self.call("video.save", {"group_id": self.group_id, "name": name[:128],
                                     "description": description[:5000], "wallpost": 0,
                                     "no_comments": 0, "repeat": repeat})
        _post_file(s["upload_url"].replace("\\", ""), "video_file", path)
        return "video%s_%s" % (s["owner_id"], s["video_id"])

    def wall_post(self, message, attachments=(), publish_date=None, guid=None, close_comments=0):
        """Пост от имени сообщества. mark_as_ads завод не ставит никогда (см. law.md)."""
        r = self.call("wall.post", {"owner_id": self.owner_id, "from_group": 1, "message": message,
                                    "attachments": ",".join(attachments) or None,
                                    "publish_date": publish_date, "guid": guid, "signed": 0,
                                    "close_comments": close_comments})
        return r["post_id"]

    def reply_comment(self, post_id, comment_id, message, guid=None):
        """Ответ от имени сообщества ключом А."""
        return self.call("wall.createComment", {"owner_id": self.owner_id, "post_id": post_id,
                                                "reply_to_comment": comment_id, "from_group": self.group_id,
                                                "message": message, "guid": guid}, kind="group")

    def story(self, path, is_video=True, link_text=None, link_url=None):
        """История ключом А: getVideo/PhotoUploadServer -> POST -> stories.save."""
        m = "stories.getVideoUploadServer" if is_video else "stories.getPhotoUploadServer"
        srv = self.call(m, {"add_to_news": 1, "group_id": self.group_id, "link_text": link_text,
                            "link_url": link_url}, kind="group")
        up = _post_file(srv["upload_url"], "video_file" if is_video else "file", path)
        res = up.get("response", up).get("upload_result")
        return self.call("stories.save", {"upload_results": res}, kind="group")

    def server_time(self):
        req = urllib.request.Request(API + "utils.getServerTime", data=urllib.parse.urlencode({"v": V}).encode())
        return int(json.loads(urllib.request.urlopen(req, timeout=30).read())["response"])

    def permissions(self):
        """Самопроверка ключей: что реально разрешено. Ничего не публикует."""
        out = {}
        if self.has("group"):
            try:
                out["group"] = self.call("groups.getTokenPermissions", {}, kind="group")
            except VKError as e:
                out["group"] = "ошибка %s %s" % (e.code, e.msg)
        if self.has("user"):
            try:
                out["user"] = self.call("account.getAppPermissions", {}, kind="user")
            except VKError as e:
                out["user"] = "ошибка %s %s" % (e.code, e.msg)
        return out


def _encode(params, files=None):
    if not files:
        return urllib.parse.urlencode({k: str(v) for k, v in params.items()}).encode(), \
            "application/x-www-form-urlencoded"
    boundary = "----vk%s" % uuid.uuid4().hex
    chunks = []
    for k, v in params.items():
        chunks.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                       % (boundary, k, v)).encode())
    for field, path in files.items():
        chunks.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                       "Content-Type: application/octet-stream\r\n\r\n"
                       % (boundary, field, os.path.basename(path))).encode() + open(path, "rb").read() + b"\r\n")
    chunks.append(("--%s--\r\n" % boundary).encode())
    return b"".join(chunks), "multipart/form-data; boundary=%s" % boundary


def _post_file(url, field, path):
    body, ctype = _encode({}, {field: path})
    req = urllib.request.Request(url, data=body, headers={"Content-Type": ctype})
    d = json.loads(urllib.request.urlopen(req, timeout=900).read())
    if isinstance(d, dict) and d.get("error"):
        raise VKError(22, "загрузка: %s" % str(d)[:200], "upload")
    return d


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    vk = VK()
    print("ключ сообщества:", vk.has("group"), "| ключ админа:", vk.has("user"),
          "| сервисный:", vk.has("service"))
    print("время сервера ВК:", vk.server_time())
    print("права:", json.dumps(vk.permissions(), ensure_ascii=False))
