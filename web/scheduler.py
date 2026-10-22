"""
Scheduler (الجدولة) — runs inside the dashboard, no Windows Task Scheduler needed.

data/schedules.json (path can be moved with SCHEDULES_FILE, e.g. onto a Railway volume):
[
  {"id": "sch_...", "name": "كل يوم الصبح", "enabled": true,
   "mode": "list" | "all_full" | "failed",
   "targets": [{"path": "tests/screens/test_screen_cash_receipt.py::test_screen_flow", "name": "سند القبض"}],
   "times": ["09:00", "14:30"], "days": [6, 0, 1, 2, 3],   # 0=Mon .. 6=Sun ; [] = every day
   "repeat": 1,
   "last_fired": "2026-10-21 09:00", "last_batch": ["run_..."]}
]
Old entries {test_id, time, frequency} are converted on read.
"""
import json
import os
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
from config import paths  # noqa: E402
SCHEDULES_FILE = paths.SCHEDULES_FILE
TZ_NAME = os.getenv("SCHEDULE_TZ", "Africa/Cairo")
DAY_NAMES = ["الاتنين", "التلات", "الأربع", "الخميس", "الجمعة", "السبت", "الحد"]   # 0=Mon

_lock = threading.Lock()
_started = False


def now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(TZ_NAME)).replace(tzinfo=None)
    except Exception:
        return datetime.now()


# ---------------- storage ----------------
def _registry_rows():
    try:
        from config.tests_registry_new import TestsRegistry
        return TestsRegistry.get_enriched("ar")
    except Exception:
        return []


def _old_test_path(test_id):
    try:
        from config.tests_registry_new import TestsRegistry
        t = TestsRegistry.get_by_id(test_id)
        if t:
            return t["test_path"], t.get("name_ar", test_id)
    except Exception:
        pass
    return None, test_id


def _normalize(s):
    s = dict(s)
    s.setdefault("id", f"sch_{uuid.uuid4().hex[:8]}")
    s.setdefault("enabled", True)
    s.setdefault("mode", "list")
    if "times" not in s:
        s["times"] = [s["time"]] if s.get("time") else []
    if "days" not in s:
        s["days"] = []                          # old "يومياً" -> every day
    if "targets" not in s:
        s["targets"] = []
        # old entry from the previous schedule page: it never actually ran, so it starts OFF until reviewed
        s["enabled"] = False
        s["migrated"] = True
        if s.get("test_id"):
            path, name = _old_test_path(s["test_id"])
            if path:
                s["targets"] = [{"path": path, "name": name}]
    s["times"] = sorted({t.strip()[:5] for t in s["times"] if t and ":" in t})
    s["days"] = sorted({int(d) for d in s["days"] if str(d).isdigit() and 0 <= int(d) <= 6})
    s["repeat"] = max(1, min(50, int(s.get("repeat") or 1)))
    return s


def load():
    from config.storage import load_json
    data = load_json(SCHEDULES_FILE, []) or []
    return [_normalize(s) for s in data if isinstance(s, dict)]


def save(items):
    from config.storage import save_json
    save_json(SCHEDULES_FILE, items)


def upsert(data):
    with _lock:
        items = load()
        s = _normalize(data)
        if not s.get("name"):
            raise ValueError("اكتبي اسم للجدولة")
        if not s["times"]:
            raise ValueError("حددي ميعاد واحد على الأقل")
        if s["mode"] == "list" and not s["targets"]:
            raise ValueError("اختاري اختبار واحد على الأقل")
        old = next((x for x in items if x["id"] == s["id"]), None)
        if old:
            s["last_fired"] = old.get("last_fired")
            s["last_batch"] = old.get("last_batch", [])
            s["created_at"] = old.get("created_at")
            items = [s if x["id"] == s["id"] else x for x in items]
        else:
            s["created_at"] = now().isoformat(timespec="seconds")
            items.append(s)
        save(items)
        return s


def delete(sch_id):
    with _lock:
        items = load()
        save([x for x in items if x["id"] != sch_id])


def set_enabled(sch_id, on):
    with _lock:
        items = load()
        for x in items:
            if x["id"] == sch_id:
                x["enabled"] = bool(on)
        save(items)


# ---------------- timing ----------------
def next_run(s, ref=None):
    ref = ref or now()
    if not s.get("enabled", True) or not s.get("times"):
        return None
    for add in range(0, 8):
        day = (ref + timedelta(days=add)).date()
        if s["days"] and day.weekday() not in s["days"]:
            continue
        for t in s["times"]:
            hh, mm = [int(x) for x in t.split(":")]
            cand = datetime(day.year, day.month, day.day, hh, mm)
            if cand > ref:
                return cand
    return None


def describe_days(s):
    if not s.get("days") or len(s["days"]) == 7:
        return "كل يوم"
    if sorted(s["days"]) == [0, 1, 2, 3, 6]:
        return "أيام الشغل (الحد – الخميس)"
    return "، ".join(DAY_NAMES[d] for d in s["days"])


# ---------------- firing ----------------
def resolve_targets(s):
    """Which tests a schedule runs right now."""
    if s.get("mode") == "list":
        return [t for t in s.get("targets", []) if t.get("path")]
    rows = _registry_rows()
    out = []
    if s.get("mode") == "all_full":
        for r in rows:
            if r.get("full_path"):
                out.append({"path": r["full_path"], "name": r["name"]})
            for sc in r.get("scenarios") or []:
                out.append({"path": sc["full_path"], "name": f"{r['name']} — {sc['name']}"})
    elif s.get("mode") == "failed":
        try:
            from web import insights
            for f in insights.compute_home("ar")["failing"]:
                if f.get("path"):
                    out.append({"path": f["path"], "name": f["name"]})
        except Exception:
            pass
    return out


def fire(s, manual=False):
    from web.queue_manager import get_manager
    qm = get_manager()
    batch = []
    stamp = now().strftime("%Y%m%d%H%M%S")
    for i, t in enumerate(resolve_targets(s)):
        task_id = f"run_{stamp}{i:02d}"
        rep = s.get("repeat", 1) if "[" not in t["path"] else 1
        qm.add(task_id, t["path"], f"⏰ {t['name']}", repeat=rep,
               source="manual" if manual else "schedule", extra={"schedule_id": s["id"], "schedule_name": s["name"]})
        batch.append(task_id)
    with _lock:
        items = load()
        for x in items:
            if x["id"] == s["id"]:
                x["last_batch"] = batch
                x["last_run_at"] = now().isoformat(timespec="minutes")
                if not manual:
                    x["last_fired"] = now().strftime("%Y-%m-%d %H:%M")
        save(items)
    return batch


def _tick():
    t = now()
    key = t.strftime("%Y-%m-%d %H:%M")
    hm = t.strftime("%H:%M")
    for s in load():
        if not s.get("enabled", True) or hm not in s.get("times", []):
            continue
        if s["days"] and t.weekday() not in s["days"]:
            continue
        if s.get("last_fired") == key:
            continue
        try:
            print(f"[scheduler] ⏰ {s['name']} @ {key}", flush=True)
            fire(s)
        except Exception as e:
            print(f"[scheduler] error {s.get('name')}: {e}", flush=True)


def _loop():
    while True:
        try:
            _tick()
        except Exception as e:
            print(f"[scheduler] tick error: {e}", flush=True)
        try:
            from web import backup
            backup.auto_tick(now())
        except Exception as e:
            print(f"[backup] tick error: {e}", flush=True)
        time.sleep(20)


def start():
    global _started
    if _started or os.getenv("SCHEDULER", "1") in ("0", "false", "False"):
        return
    _started = True
    threading.Thread(target=_loop, name="scheduler", daemon=True).start()
    print(f"[scheduler] started ({TZ_NAME}) — file: {SCHEDULES_FILE}", flush=True)
