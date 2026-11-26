# -*- coding: utf-8 -*-
"""Датчик сообщества ВК без входа и гейт «одна правда».

Замер 18.09.2026 (docs/research/vk/community.md): анонимно API ВК не отвечает
ничем (ошибка 15 даже на groups.getById), но страница vk.ru/<адрес> отдаёт в
HTML предзагрузку window.cur.apiPrefetchCache с полным groups.getById:
участники, счётчики вкладок, телефон, сайт, описание, кнопка, адрес.
vk.com и m.vk.* для датчика не годятся (BadBrowser). Браузер не подделываем.

Гейт «одна правда»: карточка ВК сверяется с каноном сайта. Нейросети (Grok
открывает сообщество напрямую, Алиса берёт vk.ru в источники) пересказывают
карточку как факт, поэтому при расхождении завод не постит, а пишет владельцу,
что поправить и где в меню.

    python3 vk_probe.py            # карточка + сверка, JSON в stdout, строка в журнал
    python3 vk_probe.py --quiet    # только код возврата: 0 чисто, 2 расхождение, 3 датчик ослеп
"""
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

SCREEN = os.environ.get("VK_SCREEN", "goldensamplepcs")
DB = os.environ.get("VK_DB", "/opt/shorts/vk.db")

# Канон - pc-store/app.config.ts и /kontakty (сверено 18.09.2026). Юрлицо не публикуем.
CANON = {
    "phone": "+7 (XXX) XXX-XX-XX",
    "site": "gspc-lab.pro",
    "address_has": ["95", "Аэробус", "46"],
    "status": "Игровые ПК на заказ, Москва",
}
# слова, которые гейты завода запрещают в любом тексте от имени GSPC
BAD_CLAIMS = ["ниже рыночных", "за 24 часа", "гарантия 3 года на все", "stop the fomo",
              "международной торговле", "лучшие цены", "единицы умеют"]


def digits(s):
    return re.sub(r"\D", "", str(s or ""))


def fetch_card(screen=SCREEN):
    r = subprocess.run(["curl", "-s", "--max-time", "30", "https://vk.ru/%s" % screen],
                       capture_output=True, text=True)
    html = r.stdout or ""
    i = html.find("apiPrefetchCache")
    if i < 0:
        return None, "нет apiPrefetchCache в ответе (%d байт)" % len(html)
    j = html.find("=", i)
    dec = json.JSONDecoder()
    k = j + 1
    while k < len(html) and html[k] in " \t\r\n":
        k += 1
    try:
        data, _ = dec.raw_decode(html[k:])
    except ValueError as e:
        return None, "предзагрузка не разобралась: %s" % str(e)[:80]
    group = None

    def walk(x):
        nonlocal group
        if group is not None:
            return
        if isinstance(x, dict):
            if x.get("screen_name") == screen and "members_count" in x:
                group = x
                return
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(data)
    if not group:
        return None, "в предзагрузке нет groups.getById"
    return group, ""


def summarize(g):
    tabs = {}
    for t in g.get("tabs") or []:
        if isinstance(t, dict):
            tabs[t.get("main_type") or t.get("type") or "?"] = t.get("main_type_count", t.get("count"))
    addr = (g.get("addresses") or {}).get("main_address") or {}
    ab = g.get("action_button") or {}
    desc = g.get("description") or ""
    return {
        "id": g.get("id"), "name": g.get("name"), "members": g.get("members_count"),
        "type": g.get("type"), "tabs": tabs, "phone": g.get("phone") or "", "site": g.get("site") or "",
        "status": g.get("status") or "", "action": ab.get("action_type") or "",
        "address": " ".join(str(addr.get(k) or "") for k in ("title", "address", "additional_address")).strip(),
        "hours": addr.get("work_info_status") or "", "desc_len": len(desc),
        "desc_hash": hashlib.sha1(desc.encode("utf-8")).hexdigest()[:12],
        "desc_bad": [w for w in BAD_CLAIMS if w in desc.lower()],
    }


def one_truth(s):
    """Что в карточке ВК расходится с сайтом. Пусто = можно постить."""
    out = []
    if digits(CANON["phone"]) not in digits(s["phone"]):
        out.append("телефон %s, на сайте %s: Управление -> Основная информация -> Телефон"
                   % (s["phone"] or "не указан", CANON["phone"]))
    if CANON["site"] not in s["site"]:
        out.append("сайт %s, должен быть https://%s: Управление -> Основная информация -> Сайт"
                   % (s["site"][:60] or "не указан", CANON["site"]))
    if not all(x in s["address"] for x in CANON["address_has"]):
        out.append("адрес «%s» без ТЦ Аэробус и павильона 46: Управление -> Адреса" % s["address"][:80])
    if s["hours"] in ("", "no_information"):
        out.append("часы работы не заполнены: Управление -> Адреса -> Открыто в указанные часы")
    if s["desc_bad"]:
        out.append("в описании непроверяемые обещания (%s): Управление -> Основная информация -> Описание"
                   % ", ".join(s["desc_bad"]))
    return out


def journal(s, issues):
    try:
        con = sqlite3.connect(DB, timeout=30)
        con.execute("CREATE TABLE IF NOT EXISTS vk_probe (ts TEXT, members INT, posts INT, goods INT, "
                    "phone TEXT, site TEXT, desc_hash TEXT, issues TEXT)")
        con.execute("INSERT INTO vk_probe VALUES (?,?,?,?,?,?,?,?)",
                    (time.strftime("%Y-%m-%d %H:%M:%S"), s["members"], s["tabs"].get("wall"),
                     s["tabs"].get("market"), s["phone"], s["site"], s["desc_hash"], json.dumps(issues,
                                                                                                ensure_ascii=False)))
        con.commit()
        con.close()
    except sqlite3.Error:
        pass


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    g, why = fetch_card()
    if not g:
        # датчик ослеп: значения не обнуляем, тревога
        if "--quiet" not in sys.argv:
            print(json.dumps({"ok": False, "blind": why}, ensure_ascii=False))
        return 3
    s = summarize(g)
    issues = one_truth(s)
    journal(s, issues)
    if "--quiet" not in sys.argv:
        print(json.dumps({"ok": not issues, "card": s, "issues": issues}, ensure_ascii=False, indent=1))
    return 0 if not issues else 2


if __name__ == "__main__":
    sys.exit(main())
