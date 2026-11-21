"""
📡 مراقبة المواقع — every site (yours and your clients') checked every few minutes, read only, so you know before the client does.

Each check (plain HTTP, no login, nothing written anywhere):
  • the site answers (status, time to answer)           • the login page renders (it has a password field)
  • NQ ERP's own error page isn't showing                • HTTPS certificate: days left
A site is DOWN after 2 failed checks in a row (one network blip doesn't wake anybody), SLOW after 3 slow ones,
and back UP on the first good one. Each change → one alert on the dashboard's channels (WhatsApp / Telegram / webhook /
e-mail / Slack, Settings ▸ التنبيهات); the certificate warns once a day from 14 days before it expires.

Settings: data/settings/monitor.json · history (last 24 h per site): data/monitor/state.json
"""
import json
import os
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlparse

from config import paths
from config.storage import load_json, save_json

CFG_FILE = paths.settings_file("monitor.json")
STATE_FILE = paths.DATA_DIR / "monitor" / "state.json"
DEFAULTS = {"on": True, "every_min": 15, "slow_ms": 8000, "sites": [], "ssl_days": 14}   # sites: [] = every site in Settings
KEEP = 96                                                     # 24 h of 15-minute checks
ERROR_PAGE = re.compile(r"Server Error in '/' Application|Runtime Error|HTTP Error 50\d|Service Unavailable|The resource cannot be found", re.I)
_lock, _busy, _last = threading.Lock(), {"on": False}, {"t": 0.0}


def load_config():
    return {**DEFAULTS, **(load_json(CFG_FILE, {}) or {})}


def save_config(new):
    c = load_config()
    for k in DEFAULTS:
        if k in new:
            c[k] = new[k]
    c["every_min"] = max(5, min(240, int(c.get("every_min") or 15)))
    c["slow_ms"] = max(1000, int(c.get("slow_ms") or 8000))
    save_json(CFG_FILE, c)
    return c


def _sites(cfg):
    from web import test_sites_helper as T
    profs = T.load_all().get("profiles") or []
    pick = set(cfg.get("sites") or [])
    return [p for p in profs if p.get("base_url") and (not pick or p["id"] in pick)]


def ssl_days(url, timeout=8):
    """days until the HTTPS certificate expires (None for http:// or when it can't be read)"""
    u = urlparse(url)
    if u.scheme != "https":
        return None
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((u.hostname, u.port or 443), timeout=timeout) as s, ctx.wrap_socket(s, server_hostname=u.hostname) as t:
            end = datetime.strptime(t.getpeercert()["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        return (end - datetime.now(timezone.utc)).days
    except ssl.SSLCertVerificationError:
        return -1                                              # expired or invalid: as bad as it gets
    except Exception:
        return None


def _get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "NQ-Monitor/1.0 (read-only uptime check)"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(400_000).decode("utf-8", "ignore")
            return r.status, int((time.time() - t0) * 1000), body, r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, int((time.time() - t0) * 1000), e.read(100_000).decode("utf-8", "ignore") if e.fp else "", url
    except Exception as e:
        return 0, int((time.time() - t0) * 1000), str(getattr(e, "reason", e))[:200], url


def check_site(p, cfg=None, timeout=30):
    """one read-only check of one site -> {"ok", "slow", "status", "ms", "why", "ssl_days", "at"}"""
    cfg = cfg or load_config()
    base = p["base_url"].rstrip("/")
    st, ms, body, final = _get(base + "/", timeout)
    if 400 <= st < 500:                                                # a home page that needs a path: the login page decides
        st, ms2, body, final = _get(base + "/Account/Login", timeout)
        ms += ms2
    why = ""
    if st == 0:
        why = f"الموقع مش بيرد: {body[:120]}"
    elif st >= 500:
        why = f"السيرفر رجّع خطأ {st}"
    elif st >= 400:
        why = f"الصفحة رجّعت {st}"
    elif ERROR_PAGE.search(body):
        why = "صفحة خطأ NQ ERP ظاهرة بدل الموقع"
    elif not re.search(r'type=["\']?password', body, re.I):           # the home page normally sends you to the login form
        st2, ms2, body2, _ = _get(base + "/Account/Login", timeout)
        if st2 == 200 and re.search(r'type=["\']?password', body2, re.I):
            pass
        elif "login" not in final.lower() and not re.search(r"تسجيل الدخول|login", body, re.I):
            why = "صفحة الدخول مش ظاهرة"
    return {"ok": not why, "slow": not why and ms > int(cfg.get("slow_ms", 8000)), "status": st, "ms": ms, "why": why,
            "ssl_days": ssl_days(base), "at": datetime.now().isoformat(timespec="seconds")}


def _state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(s):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    tmp.replace(STATE_FILE)


def _verdict(hist):
    """the site's state from its last checks: down after 2 fails in a row, slow after 3 slow, else up"""
    last = hist[-3:]
    if len(last) >= 2 and not last[-1]["ok"] and not last[-2]["ok"]:
        return "down"
    if len(last) == 3 and all(h["ok"] and h.get("slow") for h in last):
        return "slow"
    if hist and not hist[-1]["ok"]:
        return hist[-2]["v"] if len(hist) > 1 and hist[-2].get("v") else "up"     # one failure: keep what it was
    return "up"


def broadcast(text):
    """one message on every alert channel the dashboard has (each one on its own: a broken channel doesn't stop the others)"""
    from web import notify
    cfg = notify.load_config()
    sent = []
    for name, fn in (("telegram", lambda: cfg.get("telegram_on") and cfg.get("telegram_token") and notify.send_telegram(cfg, text)),
                     ("whatsapp", lambda: cfg.get("whatsapp_on") and notify.send_whatsapp(cfg, text)),
                     ("webhook", lambda: (cfg.get("webhook_url") or os.getenv("ALERT_WEBHOOK")) and notify._webhook(cfg.get("webhook_url") or os.getenv("ALERT_WEBHOOK"), text))):
        try:
            if fn():
                sent.append(name)
        except Exception as e:
            print(f"[monitor] {name}: {e}", flush=True)
    try:
        from config import emailer
        ec = emailer.load_config() or {}
        to = ec.get("recipients") or []
        to = [x.strip() for x in (to if isinstance(to, list) else str(to).replace(";", ",").split(",")) if x.strip()]
        if ec.get("enabled") and to:
            emailer._deliver(ec, to, text.splitlines()[0], "<div dir='rtl' style='font:14px Tahoma'>" + text.replace("\n", "<br>") + "</div>")
            sent.append("email")
    except Exception as e:
        print(f"[monitor] email: {e}", flush=True)
    return sent


def run_once(force=False):
    """check every site now; alert on changes -> the new state"""
    cfg = load_config()
    if not (cfg.get("on") or force):
        return _state()
    with _lock:
        if _busy["on"]:
            return _state()
        _busy["on"] = True
    try:
        st = _state()
        for p in _sites(cfg):
            r = check_site(p, cfg)
            s = st.setdefault(p["id"], {"name": p.get("name"), "url": p["base_url"], "kind": p.get("kind", ""), "hist": [], "v": "up"})
            s.update({"name": p.get("name"), "url": p["base_url"], "kind": p.get("kind", "")})
            s["hist"] = (s["hist"] + [r])[-KEEP:]
            v_old, v = s.get("v", "up"), _verdict(s["hist"])
            r["v"] = v
            s["v"], s["last"] = v, r
            name = p.get("name") or p["base_url"]
            if v != v_old:
                s["since"] = r["at"]
                msg = {"down": f"🔴 {name} واقع — {r['why'] or 'مش بيرد'}\n{p['base_url']}",
                       "slow": f"🟡 {name} بطيء — بيرد في {r['ms'] / 1000:.1f} ث (3 مرات ورا بعض)\n{p['base_url']}",
                       "up": f"🟢 {name} رجع يشتغل — بيرد في {r['ms'] / 1000:.1f} ث"}[v]
                s.setdefault("incidents", []).append({"at": r["at"], "v": v, "why": r["why"]})
                s["incidents"] = s["incidents"][-30:]
                broadcast("📡 مراقبة المواقع\n" + msg)
            d = r.get("ssl_days")
            today = r["at"][:10]
            if d is not None and d <= int(cfg.get("ssl_days", 14)) and s.get("ssl_warned") != today:
                s["ssl_warned"] = today
                broadcast(f"📡 مراقبة المواقع\n🔐 شهادة HTTPS بتاعة {name} " + ("خلصت!" if d < 0 else f"هتخلص بعد {d} يوم") + f"\n{p['base_url']}")
        _save_state(st)
        return st
    finally:
        _busy["on"] = False


def summary():
    """for the page: each site's state, last check, uptime and average time over 24 h, certificate, last incidents"""
    cfg, st, out = load_config(), _state(), []
    for p in _sites(cfg):
        s = st.get(p["id"]) or {}
        h = s.get("hist") or []
        oks = [x for x in h if x["ok"]]
        out.append({"id": p["id"], "name": p.get("name"), "url": p["base_url"], "kind": p.get("kind", ""), "v": s.get("v") if h else "none",
                    "since": s.get("since"), "last": s.get("last"), "checks": len(h),
                    "uptime": round(100 * len(oks) / len(h), 1) if h else None,
                    "avg_ms": int(sum(x["ms"] for x in oks) / len(oks)) if oks else None,
                    "spark": [None if not x["ok"] else x["ms"] for x in h[-48:]],
                    "incidents": list(reversed((s.get("incidents") or [])[-5:]))})
    return {"config": cfg, "sites": out}


def auto_tick(now=None):
    """called by the background ticker every ~20 s: a round every «every_min» minutes, in its own thread"""
    cfg = load_config()
    if not cfg.get("on") or time.time() - _last["t"] < int(cfg.get("every_min", 15)) * 60:
        return
    _last["t"] = time.time()
    threading.Thread(target=run_once, name="monitor", daemon=True).start()
