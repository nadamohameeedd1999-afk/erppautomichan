"""
🛰️ أخطاء من جوه NQ ERP — NQ ERP itself reports what goes wrong for real users, so you see it before they call.

Each site gets its own secret link (POST /api/telemetry/<token>). The small code in integrations/nq-erp/ (pasted once
by the NQ ERP developers) sends:
  • server  — an exception on the server (the global MVC filter + Application_Error): type, message, screen, user, stack
  • ajax    — a call from a screen that came back 500 (jQuery ajaxError), with the server's answer
  • js      — a JavaScript error on a screen (window.onerror / unhandled promise)
  • start   — the application started (deploy, IIS recycle, crash): version + build date = which version each client runs
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
    fresh = []
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
            typ, msg = _clip(x.get("type"), 150), _clip(x.get("message"), 1000)
            screen = _path(x.get("url"))
            key = hashlib.sha1(f"{kind}|{typ}|{_norm(msg)}|{screen}".encode("utf-8")).hexdigest()[:14]
            e = s["errors"].get(key)
            if not e:
                e = s["errors"][key] = {"kind": kind, "type": typ, "message": msg, "screen": screen, "first": at, "count": 0, "users": [], "urls": []}
                fresh.append(e)
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
    return len(items)


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
