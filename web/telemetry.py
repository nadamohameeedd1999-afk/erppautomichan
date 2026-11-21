"""
🛰️ أخطاء من جوه NQ ERP — NQ ERP itself reports what goes wrong for real users, so you see it before they call.

Each site gets its own secret link (POST /api/telemetry/<token>). The small code in integrations/nq-erp/ (pasted once
by the NQ ERP developers) sends:
  • server  — an exception on the server (the global MVC filter + Application_Error): type, message, screen, user, stack
  • ajax    — a call from a screen that came back 500 (jQuery ajaxError), with the server's answer
  • js      — a JavaScript error on a screen (window.onerror / unhandled promise)
  • start   — the application started (deploy, IIS recycle, crash): version + build date = which version each client runs
  • usage   — every 10 min: how many times each screen was opened and by whom (60 days kept)
  • zatca   — e-invoices: rejected / failed at once (alert), cleared / reported / warning counted (per day, 90 days)
  • db      — every 6 h, read only: last full / log backup, sizes, recovery model, free disk, failed jobs, slowest queries
              (alert once a day when the last full backup is older than BACKUP_H hours)
The same error is ONE item (numbers / ids blanked): how many times, how many users, first / last time, the latest stack.
A new one → one alert (at most 6 an hour per site, the rest wait on the page) and an item in «دعم المطورين».

Abuse guard (the link is visible in the page's script): 60 reports a minute per site, 20 KB a report, 300 errors kept per site.
Store: data/monitor/telemetry.json
"""
import hashlib
import json
import re
import secrets
import threading
import time
from datetime import datetime, timedelta

from config import paths

FILE = paths.DATA_DIR / "monitor" / "telemetry.json"
KINDS = {"server": "خطأ سيرفر", "ajax": "طلب رجع 500", "js": "خطأ JavaScript"}
KEEP, PER_MIN, ALERTS_PER_HOUR, MAX_BYTES = 300, 60, 6, 20_000
BACKUP_H = 26
ZATCA_AR = {"cleared": "اتقبلت (Clearance)", "reported": "اتبلغت (Reporting)", "warning": "اتقبلت بتحذير", "rejected": "اترفضت", "failed": "فشل الإرسال"}
_lock, _rate, _alerts = threading.Lock(), {}, {}


def _load():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(d):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    tmp.replace(FILE)


# ------------------------------------------------------------------ the per-site links
def tokens():
    from web import monitor
    return dict(monitor.load_config().get("tokens") or {})


def token_for(site_id, new=False):
    """the site's secret link part (made the first time it's asked for; new=True replaces it — the old link stops working)"""
    from web import monitor
    t = tokens()
    if new or not t.get(site_id):
        t[site_id] = secrets.token_urlsafe(18)
        monitor.save_config({"tokens": t})
    return t[site_id]


def site_of(token):
    return next((sid for sid, t in tokens().items() if token and secrets.compare_digest(t, token)), None)


# ------------------------------------------------------------------ receiving
def _norm(s):
    """the same error with other numbers / ids / dates = the same item"""
    s = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "#", str(s or ""), flags=re.I)
    s = re.sub(r"'[^']{0,80}'", "'…'", s)
    return re.sub(r"\d+", "#", s).strip()[:300]


def _path(url):
    p = re.sub(r"^https?://[^/]+", "", str(url or "")).split("#")[0]
    return re.sub(r"/\d+(?=/|$|\?)", "/#", p.split("?")[0])[:200] or "/"


def _clip(v, n):
    return str(v or "")[:n]


def receive(site_id, items, now=None):
    """store a report (one item or a list) -> how many were taken; new errors alert"""
    now = now or time.time()
    win = [t for t in _rate.get(site_id, []) if now - t < 60]
    items = items if isinstance(items, list) else [items]
    room = max(0, PER_MIN - len(win))
    items = [x for x in items if isinstance(x, dict)][:room]
    _rate[site_id] = win + [now] * len(items)
    if not items:
        return 0
    at = datetime.fromtimestamp(now).isoformat(timespec="seconds")
    fresh, back, extra = [], [], []                                  # extra: alert lines from usage / zatca / db
    with _lock:
        d = _load()
        s = d.setdefault(site_id, {"errors": {}, "starts": []})
        for x in items:
            kind = x.get("kind") if x.get("kind") in KINDS or x.get("kind") == "start" else "server"
            ver = {"version": _clip(x.get("version"), 40), "build": _clip(x.get("build"), 40)}
            if ver["version"] or ver["build"]:
                s["version"] = {**ver, "at": at}
            if kind == "start":
                s["starts"] = (s["starts"] + [{"at": at, **ver, "machine": _clip(x.get("machine"), 60)}])[-30:]
                continue
            if x.get("kind") in ("usage", "zatca", "db"):
                extra.extend(globals()["_" + x["kind"]](s, x, at))
                continue
            typ, msg = _clip(x.get("type"), 150), _clip(x.get("message"), 1000)
            screen = _path(x.get("url"))
            key = hashlib.sha1(f"{kind}|{typ}|{_norm(msg)}|{screen}".encode("utf-8")).hexdigest()[:14]
            e = s["errors"].get(key)
            if not e:
                e = s["errors"][key] = {"kind": kind, "type": typ, "message": msg, "screen": screen, "first": at, "count": 0, "users": [], "urls": []}
                fresh.append(e)
            elif _reopen_if_fixed(site_id, key, at):                       # 🔁 marked «اتصلح» and here it is again
                e["regressed"] = (e.get("regressed", []) + [at])[-20:]
                back.append(e)
            e["count"] += 1
            e["last"] = at
            e["message"], e["stack"], e["status"] = msg, _clip(x.get("stack"), 6000), _clip(x.get("status"), 10)
            e["response"] = _clip(x.get("response"), 1500)
            for k, v, n in (("users", _clip(x.get("user"), 80), 20), ("urls", _clip(x.get("url"), 300), 5)):
                if v and v not in e[k]:
                    e[k] = (e[k] + [v])[-n:]
            if ver["version"] or ver["build"]:
                e["version"] = ver["version"] or ver["build"]
        if len(s["errors"]) > KEEP:                                   # oldest go first
            for k in sorted(s["errors"], key=lambda k: s["errors"][k].get("last", ""))[:len(s["errors"]) - KEEP]:
                del s["errors"][k]
        _save(d)
    if fresh:
        _alert(site_id, fresh, now)
    if extra:
        _alert_lines(site_id, extra, now)
    if back:
        from web import monitor
        name = next((x.get("name") for x in monitor._sites({}) if x["id"] == site_id), site_id)
        monitor.broadcast("📡 مراقبة المواقع\n🔁 " + f"{name}: خطأ كان اتصلح ورجع تاني\n"
                          + "\n".join(f"⛔ {e['screen']}: {e['message'][:140]}" for e in back[:5]) + "\nالتذكرة رجعت «جديد» في «دعم المطورين»")
    return len(items)


def _usage(s, x, at):
    day = s.setdefault("usage", {}).setdefault(at[:10], {})
    for screen, v in list((x.get("screens") or {}).items())[:200]:
        screen = _clip(screen, 120)
        if not isinstance(v, dict):
            continue
        u = day.setdefault(screen, {"n": 0, "users": []})
        u["n"] += int(v.get("n") or 0)
        u["users"] = list(dict.fromkeys(u["users"] + [_clip(x, 80) for x in (v.get("users") or [])][:50]))[:50]
    for k in sorted(s["usage"])[:-60]:
        del s["usage"][k]
    return []


def _zatca(s, x, at):
    z = s.setdefault("zatca", {"days": {}, "issues": []})
    day = z["days"].setdefault(at[:10], {k: 0 for k in ZATCA_AR})
    lines = []
    if x.get("counts") is not None or x.get("warnings") is not None:   # the 10-minute summary
        for k, n in (x.get("counts") or {}).items():
            if k in ZATCA_AR:
                day[k] += int(n or 0)
        for w in (x.get("warnings") or [])[:20]:
            z["issues"].append({"at": at, "invoice": _clip(w.get("invoice"), 40), "status": "warning", "message": _clip(w.get("message"), 800)})
    else:                                                                # one rejected / failed invoice
        st = x.get("status") if x.get("status") in ZATCA_AR else "failed"
        day[st] += 1
        z["issues"].append({"at": at, "invoice": _clip(x.get("invoice"), 40), "status": st, "message": _clip(x.get("message"), 800),
                            "amount": x.get("amount") or 0})
        if st in ("rejected", "failed"):
            lines.append(f"🧾 فاتورة {_clip(x.get('invoice'), 40) or '—'} {ZATCA_AR[st]}: {_clip(x.get('message'), 160)}")
    z["issues"] = z["issues"][-100:]
    for k in sorted(z["days"])[:-90]:
        del z["days"][k]
    return lines


def _db(s, x, at):
    keep = ("database", "backup_full", "backup_log", "data_mb", "log_mb", "recovery", "disk_free_gb", "jobs_failed_24h", "sql_version", "error")
    last = {k: x.get(k) for k in keep if x.get(k) is not None}
    last["not_allowed"] = {k[:-6]: _clip(v, 200) for k, v in x.items() if k.endswith("_error") and k != "error"}
    last["slow"] = [{"query": _clip(q.get("query"), 300), "count": q.get("count"), "avg_ms": q.get("avg_ms")} for q in (x.get("slow") or [])[:5]]
    last["at"] = at
    db = s.setdefault("db", {"sizes": {}, "warned": ""})
    db["last"] = last
    if x.get("data_mb") is not None:
        db["sizes"][at[:10]] = x["data_mb"]
        for k in sorted(db["sizes"])[:-120]:
            del db["sizes"][k]
    lines, age = [], backup_age_h(last)
    if age is not None and age > BACKUP_H and db.get("warned") != at[:10]:
        db["warned"] = at[:10]
        lines.append(f"🗄️ آخر نسخة احتياطية كاملة لقاعدة {last.get('database', '')} من {age:.0f} ساعة ({last.get('backup_full')})")
    if not last.get("backup_full") and "backup_full" not in last["not_allowed"] and not x.get("error") and db.get("warned") != at[:10]:
        db["warned"] = at[:10]
        lines.append(f"🗄️ قاعدة {last.get('database', '')} مفيهاش أي نسخة احتياطية كاملة متسجلة")
    return lines


def backup_age_h(last):
    try:
        return (datetime.now() - datetime.strptime(str(last.get("backup_full"))[:16], "%Y-%m-%d %H:%M")).total_seconds() / 3600
    except (TypeError, ValueError):
        return None


def _alert_lines(site_id, lines, now):
    key = f"{site_id}|inside"
    sent = [t for t in _alerts.get(key, []) if now - t < 3600]
    if len(sent) >= ALERTS_PER_HOUR:
        return
    _alerts[key] = sent + [now]
    from web import monitor
    name = next((x.get("name") for x in monitor._sites({}) if x["id"] == site_id), site_id)
    monitor.broadcast(f"📡 مراقبة المواقع\n{name}:\n" + "\n".join(lines[:8]))


def inside(site_id, days=30):
    """the «من جوه الأنظمة» page for one site: ZATCA, the database, screen usage (with the screens other clients use and this one doesn't)"""
    d = _load()
    s = d.get(site_id) or {}
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    z = s.get("zatca") or {}
    zdays = {k: v for k, v in (z.get("days") or {}).items() if k >= since}
    ztot = {k: sum(v.get(k, 0) for v in zdays.values()) for k in ZATCA_AR}
    sent = sum(ztot.values())
    use = {}
    users_day = {}
    for day, scr in (s.get("usage") or {}).items():
        if day < since:
            continue
        users_day[day] = len({u for v in scr.values() for u in v.get("users", [])})
        for k, v in scr.items():
            u = use.setdefault(k, {"screen": k, "n": 0, "users": set()})
            u["n"] += v.get("n", 0)
            u["users"] |= set(v.get("users", []))
    top = sorted(({"screen": k, "n": v["n"], "users": len(v["users"])} for k, v in use.items()), key=lambda x: -x["n"])
    others = {}
    for sid, o in d.items():
        if sid == site_id:
            continue
        for day, scr in (o.get("usage") or {}).items():
            if day >= since:
                for k, v in scr.items():
                    others[k] = others.get(k, 0) + v.get("n", 0)
    unused = sorted(((k, n) for k, n in others.items() if k not in use and n >= 5), key=lambda x: -x[1])[:15]
    mods = {}
    for k, v in use.items():
        mods[k.split("/")[0]] = mods.get(k.split("/")[0], 0) + v["n"]
    db = (s.get("db") or {})
    return {"zatca": {"total": ztot, "sent": sent, "reject_rate": round(100 * (ztot["rejected"] + ztot["failed"]) / sent, 1) if sent else None,
                      "days": dict(sorted(zdays.items())[-14:]), "issues": list(reversed(z.get("issues") or []))[:25], "labels": ZATCA_AR},
            "db": {**(db.get("last") or {}), "backup_age_h": backup_age_h(db.get("last") or {}), "sizes": dict(sorted((db.get("sizes") or {}).items())[-60:])} if db else None,
            "usage": {"top": top[:25], "users_day": dict(sorted(users_day.items())[-14:]), "unused_vs_others": [{"screen": k, "n_others": n} for k, n in unused],
                      "modules": sorted(({"module": k, "n": n} for k, n in mods.items()), key=lambda x: -x["n"]), "screens": len(use)} if use or others else None,
            "connected": bool(s)}


def _reopen_if_fixed(site_id, key, at):
    """the error's ticket was set «اتصلح» before `at` → back to «جديد» with a note; True when it was"""
    from web import support
    iid = f"tel_{site_id}_{key}"[:40]
    st = support._load("support_status.json", {})
    cur = st.get(iid) or {}
    if cur.get("status") != "اتصلح" or (cur.get("at") or "") > at.replace("T", " ")[:16]:
        return False
    cur.update({"status": "جديد", "note": (f"🔁 رجع تاني {at[:16].replace('T', ' ')} بعد ما اتعلّم اتصلح {cur.get('at', '')}. " + cur.get("note", ""))[:1000]})
    cur.pop("fixed_at", None)
    cur.pop("sent_at", None)
    st[iid] = cur
    support._save("support_status.json", st)
    return True


def _alert(site_id, fresh, now):
    sent = [t for t in _alerts.get(site_id, []) if now - t < 3600]
    if len(sent) >= ALERTS_PER_HOUR:
        return
    _alerts[site_id] = sent + [now]
    from web import monitor
    p = next((x for x in monitor._sites({}) if x["id"] == site_id), {})
    name = p.get("name") or site_id
    lines = [f"🛰️ {name}: {len(fresh)} خطأ جديد من جوه البرنامج"]
    for e in fresh[:5]:
        lines.append(f"⛔ {KINDS[e['kind']]} في {e['screen']}: {(e['type'] + ' — ') if e['type'] else ''}{e['message'][:160]}"
                     + (f" (المستخدم: {e['users'][0]})" if e["users"] else ""))
    lines.append("التفاصيل في «دعم المطورين»")
    monitor.broadcast("📡 مراقبة المواقع\n" + "\n".join(lines))


# ------------------------------------------------------------------ reading
def site_summary(site_id, hours=24):
    s = _load().get(site_id) or {}
    since = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
    errs = [e for e in (s.get("errors") or {}).values() if e.get("last", "") >= since]
    errs.sort(key=lambda e: (-e["count"], e["last"]))
    starts = s.get("starts") or []
    return {"connected": bool(s), "version": s.get("version"), "last_start": starts[-1] if starts else None,
            "starts_24h": sum(1 for x in starts if x["at"] >= since), "errors_24h": len(errs), "hits_24h": sum(e["count"] for e in errs),
            "users_24h": len({u for e in errs for u in e.get("users", [])}),
            "top": [{k: e.get(k) for k in ("kind", "type", "message", "screen", "count", "last")} for e in errs[:4]]}


def support_issues(days=14):
    from web import monitor
    names = {p["id"]: p for p in monitor._sites({})}
    since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    out = []
    for sid, s in _load().items():
        p = names.get(sid) or {}
        site = re.sub(r"^https?://", "", p.get("base_url") or sid).strip("/")
        for key, e in (s.get("errors") or {}).items():
            if e.get("last", "") < since:
                continue
            ev = "\n".join(x for x in [e.get("type", ""), e.get("message", ""), (f"رد السيرفر: {e['response']}" if e.get("response") else ""),
                                       e.get("stack", "")] if x)
            out.append({"id": f"tel_{sid}_{key}"[:40], "source": "🛰️ من جوه NQ ERP", "site": site, "screen": e["screen"],
                        "url": (e.get("urls") or [""])[-1], "severity": "عالية" if e["kind"] in ("server", "ajax") else "متوسطة",
                        "title": f"{e['screen']}: {KINDS[e['kind']]} — {(e.get('type') or '').split('.')[-1]} {e.get('message', '')}"[:200],
                        "details": f"{KINDS[e['kind']]} حصل {e['count']} مرة لـ {len(e.get('users') or [])} مستخدم · من {e['first'][:16].replace('T', ' ')} لحد {e['last'][:16].replace('T', ' ')}"
                                   + (f" · النسخة {e['version']}" if e.get("version") else "") + (f"\nالمستخدمين: {'، '.join(e['users'])}" if e.get("users") else ""),
                        "evidence": ev[:3000], "doc": "", "found": e["first"][:10], "fixed": False,
                        "steps": "\n".join([f"1. ادخل {p.get('base_url') or site}" + (f" بالمستخدم {e['users'][-1]}" if e.get("users") else ""),
                                            f"2. افتح {(e.get('urls') or [e['screen']])[-1]}", "3. اعمل نفس العملية اللي كان بيعملها المستخدم",
                                            "المتوقع: العملية تتم من غير خطأ، أو رسالة واضحة بالسبب"])})
    return out
