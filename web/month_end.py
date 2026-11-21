"""
🗓️ ضغط آخر الشهر — once a month (default: the 25th, at night) the load test runs on every test site the way month end
feels: 20 users at once, 5 rounds, the slowest screens + the busiest data requests + the 5 heaviest reports (read only).
The result is a normal run (التشغيلات) — slow or failing under load = fix it before the clients close their month.
Settings: data/settings/month_end.json
"""
from datetime import datetime

from config import paths
from config.storage import load_json, save_json

CFG = paths.settings_file("month_end.json")
KEY = "month_end_load"
PRESET = {"key": KEY, "type": "load", "name_ar": "🗓️ ضغط آخر الشهر", "users": 20, "rounds": 5, "screens": 8, "apis": 6, "reports": 5, "p95_ms": 10000}


def load_cfg():
    return {"on": True, "day": 25, "at": "22:00", "last": "", **(load_json(CFG, {}) or {})}


def save_cfg(new):
    c = load_cfg()
    for k in ("on", "day", "at"):
        if k in new:
            c[k] = new[k]
    c["day"] = max(1, min(28, int(c.get("day") or 25)))
    save_json(CFG, c)
    return c


def run_now():
    """queue the month-end load test on every test site -> how many runs"""
    from engine import checks as C
    from web import monitor, sites_api
    from web.queue_manager import get_manager
    C.save(PRESET)
    ids = [p["id"] for p in monitor._sites({}) if p.get("kind") == "test"]
    if not ids:
        return 0
    out = sites_api.queue_on_sites(get_manager(), C.test_path_for(KEY), PRESET["name_ar"], ids, source="schedule")
    return out.get("count", 0)


def auto_tick(now=None):
    c, t = load_cfg(), datetime.now()
    month = t.strftime("%Y-%m")
    if not c["on"] or t.day != int(c["day"]) or t.strftime("%H:%M") < c["at"] or c.get("last") == month:
        return
    save_json(CFG, {**(load_json(CFG, {}) or {}), "last": month})
    try:
        run_now()
    except Exception as e:
        print(f"[month-end] {e}", flush=True)
