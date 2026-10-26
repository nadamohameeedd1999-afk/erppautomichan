"""
Numbers for the home dashboard (الرئيسية): KPIs, trend, coverage, failing now,
flaky tests, slowest tests, recent runs, upcoming schedules.

Everything is read from data/runs/results/summary_*.json + the tests registry,
so it needs no database.
"""
import re
from collections import defaultdict
from datetime import datetime, timedelta

from web import data_helper

_KEY_PATTERNS = (r"\[([^\]]+)\]", r"test_screen_(\w+)\.py", r"test_scn_(\w+)\.py")


def test_key(test_path: str) -> str:
    for p in _KEY_PATTERNS:
        m = re.search(p, test_path or "")
        if m:
            return m.group(1)
    return (test_path or "").split("::")[-1]


def run_time(s: dict):
    for k in ("started_at",):
        v = s.get(k)
        if v:
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                pass
    for v in (s.get("timestamp"), s.get("run_id")):
        m = re.search(r"(\d{8})_?(\d{6})", str(v or ""))
        if m:
            try:
                return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
            except ValueError:
                pass
    return None


def run_passed(s: dict) -> bool:
    if "exit_code" in s and s.get("exit_code") is not None:
        return s.get("exit_code") == 0
    return (s.get("failed", 0) + s.get("errors", 0)) == 0 and s.get("total", 0) > 0


def first_failure_message(s: dict) -> str:
    for t in s.get("tests") or []:
        if t.get("outcome") in ("failed", "error") and t.get("message"):
            msg = str(t["message"]).replace("AssertionError:", "").strip()
            return msg.split("\n")[0][:220] + ("\n" + "\n".join(msg.split("\n")[1:3]) if "\n" in msg else "")
    return ""


def _next_run(sch, now):
    try:
        hh, mm = [int(x) for x in str(sch.get("time", "")).split(":")[:2]]
    except Exception:
        return None
    nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return nxt


def compute_home(lang="ar"):
    now = datetime.now()
    today = now.date()

    # ---------- tests registry ----------
    try:
        from config.tests_registry_new import TestsRegistry
        rows = TestsRegistry.get_enriched(lang)
    except Exception:
        rows = []
    by_key = {r["page_key"]: r for r in rows}
    for r in rows:
        for sc in r.get("scenarios") or []:
            by_key[f"{r['page_key']}__{sc['key']}"] = {**r, "name": f"{r['name']} — {sc['name']}",
                                                     "full_path": sc["full_path"]}

    total_screens = len(rows)
    full_rows = [r for r in rows if r.get("full_available")]
    scenarios_count = sum(len(r.get("scenarios") or []) for r in rows)
    builder_count = sum(1 for r in rows if r.get("builder"))

    # ---------- runs ----------
    runs = []
    for s in data_helper.load_summaries():
        t = run_time(s)
        if not t:
            continue
        key = test_key(s.get("test_path", ""))
        runs.append({
            "run_id": s.get("run_id", ""),
            "name": s.get("test_name") or (by_key.get(key) or {}).get("name") or key,
            "key": key,
            "time": t,
            "passed": run_passed(s),
            "duration": float(s.get("duration_seconds") or 0),
            "message": "" if run_passed(s) else first_failure_message(s),
            "path": s.get("test_path", ""),
            "repeat": s.get("repeat", 1),
        })
    runs.sort(key=lambda r: r["time"], reverse=True)

    def window(days, end_offset=0):
        end = now - timedelta(days=end_offset)
        start = end - timedelta(days=days)
        return [r for r in runs if start < r["time"] <= end]

    last7, prev7 = window(7), window(7, 7)

    def rate(rs):
        return round(100 * sum(r["passed"] for r in rs) / len(rs)) if rs else None

    pass7, pass_prev = rate(last7), rate(prev7)

    # ---------- latest result per test ----------
    latest = {}
    history = defaultdict(list)
    for r in runs:                       # newest first
        latest.setdefault(r["key"], r)
        if len(history[r["key"]]) < 10:
            history[r["key"]].append(r)

    failing = []
    for key, r in latest.items():
        if not r["passed"]:
            row = by_key.get(key) or {}
            failing.append({
                "key": key, "name": row.get("name") or r["name"], "run_id": r["run_id"],
                "when": r["time"].isoformat(timespec="minutes"), "message": r["message"],
                "path": r["path"] or row.get("full_path"),
            })
    failing.sort(key=lambda x: x["when"], reverse=True)

    never_run = [r["name"] for r in full_rows if r["page_key"] not in latest
                 and not any(f"{r['page_key']}__{sc['key']}" in latest for sc in r.get("scenarios") or [])]

    flaky = []
    for key, hs in history.items():
        if len(hs) >= 3:
            p = sum(h["passed"] for h in hs)
            if 0 < p < len(hs):
                flaky.append({"key": key, "name": hs[0]["name"], "pass": p, "total": len(hs),
                              "pct": round(100 * p / len(hs)), "pattern": "".join("✓" if h["passed"] else "✗" for h in reversed(hs))})
    flaky.sort(key=lambda x: x["pct"])

    slow = []
    for key, hs in history.items():
        ds = [h["duration"] / max(1, int(h.get("repeat") or 1)) for h in hs if h["duration"]]
        if ds:
            slow.append({"key": key, "name": hs[0]["name"], "avg": round(sum(ds) / len(ds)), "runs": len(ds)})
    slow.sort(key=lambda x: x["avg"], reverse=True)

    # ---------- got slower than usual (آخر تشغيلة أبطأ من المعتاد) ----------
    slower = []
    for key, hs in history.items():
        ok = [h for h in hs if h["passed"] and h["duration"]]
        if len(ok) < 4:
            continue
        last = ok[0]["duration"] / max(1, int(ok[0].get("repeat") or 1))
        prev = sorted(h["duration"] / max(1, int(h.get("repeat") or 1)) for h in ok[1:])
        med = prev[len(prev) // 2]
        if last > med * 1.5 and last - med > 10:
            slower.append({"key": key, "name": ok[0]["name"], "last": round(last), "usual": round(med),
                           "pct": round(100 * (last - med) / med)})
    slower.sort(key=lambda x: -x["pct"])

    # ---------- trend (14 days) ----------
    trend = {"labels": [], "passed": [], "failed": []}
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        day_runs = [r for r in runs if r["time"].date() == d]
        trend["labels"].append(d.strftime("%d/%m"))
        trend["passed"].append(sum(r["passed"] for r in day_runs))
        trend["failed"].append(sum(not r["passed"] for r in day_runs))

    # ---------- coverage by module ----------
    modules = {}
    for r in rows:
        m = modules.setdefault(r["module_key"], {"name": r.get("module_name", r["module_key"]),
                                                 "icon": r.get("module_icon", ""), "total": 0, "full": 0,
                                                 "passed": 0, "failed": 0, "scenarios": 0})
        m["total"] += 1
        m["full"] += 1 if r.get("full_available") else 0
        m["scenarios"] += len(r.get("scenarios") or [])
        lr = r.get("last_result")
        if lr:
            m["passed" if lr.get("outcome") == "passed" else "failed"] += 1
    for m in modules.values():
        m["coverage"] = round(100 * m["full"] / m["total"]) if m["total"] else 0
    modules = sorted(modules.values(), key=lambda m: -m["total"])

    status_now = {
        "passed": sum(1 for r in rows if (r.get("last_result") or {}).get("outcome") == "passed"),
        "failed": sum(1 for r in rows if (r.get("last_result") or {}).get("outcome") == "failed"),
    }
    status_now["never"] = total_screens - status_now["passed"] - status_now["failed"]

    # ---------- schedules ----------
    upcoming = []
    try:
        from web import scheduler
        for sch in scheduler.load():
            nxt = scheduler.next_run(sch)
            if not nxt:
                continue
            upcoming.append({"name": sch.get("name"), "time": "، ".join(sch.get("times", [])),
                             "frequency": scheduler.describe_days(sch), "next": nxt.isoformat(timespec="minutes")})
    except Exception:
        pass
    upcoming.sort(key=lambda x: x["next"])

    durations7 = [r["duration"] for r in last7 if r["duration"]]
    last = runs[0] if runs else None
    return {
        "now": now.isoformat(timespec="minutes"),
        "kpi": {
            "screens": total_screens,
            "full": len(full_rows),
            "coverage": round(100 * len(full_rows) / total_screens) if total_screens else 0,
            "scenarios": scenarios_count,
            "builder": builder_count,
            "runs_today": sum(1 for r in runs if r["time"].date() == today),
            "runs_7d": len(last7),
            "pass_7d": pass7,
            "pass_delta": (pass7 - pass_prev) if (pass7 is not None and pass_prev is not None) else None,
            "failing": len(failing),
            "never_run": len(never_run),
            "avg_duration": round(sum(durations7) / len(durations7)) if durations7 else None,
            "total_runs": len(runs),
        },
        "last_run": {**last, "time": last["time"].isoformat(timespec="minutes")} if last else None,
        "trend": trend,
        "status_now": status_now,
        "modules": modules,
        "failing": failing[:8],
        "never_run": never_run[:12],
        "flaky": flaky[:6],
        "slow": slow[:6],
        "slower": slower[:6],
        "recent": [{**r, "time": r["time"].isoformat(timespec="minutes")} for r in runs[:10]],
        "upcoming": upcoming[:5],
    }


# =====================================================================
#  Comparison helpers (شاشة المقارنة)
# =====================================================================
_STEP_START = re.compile(r"\|\s*INFO\s*\|\s*(\d+)/(\d+)\)\s*(.+?)\s*\[(\w+)\]\s*(.*)$")
_STEP_OK = re.compile(r"\|\s*SUCCESS\s*\|\s*✅\s*(.+?)\s*=\s*(.*)$")
_STEP_BAD = re.compile(r"\|\s*ERROR\s*\|\s*❌\s*\[(.+?)\s*/\s*([^\]]+)\]\s*(.*)$")


def parse_steps(run_id):
    """Field-by-field fill results from a run's log: [{label, strategy, wanted, result, ok, error}]"""
    lines = [l["text"] for l in data_helper.read_run_log(run_id)]
    steps, cur = [], None
    for line in lines:
        m = _STEP_START.search(line)
        if m:
            cur = {"n": int(m.group(1)), "label": m.group(3).strip(), "strategy": m.group(4),
                   "wanted": m.group(5).strip(), "result": None, "ok": None, "error": ""}
            steps.append(cur)
            continue
        if cur is None:
            continue
        m = _STEP_OK.search(line)
        if m and m.group(1).strip() == cur["label"]:
            cur["result"], cur["ok"] = m.group(2).strip(), True
            continue
        m = _STEP_BAD.search(line)
        if m and m.group(1).strip() == cur["label"]:
            cur["ok"], cur["error"] = False, m.group(3).strip()
    return steps


def all_runs():
    out = []
    for s in data_helper.load_summaries():
        t = run_time(s)
        if not t:
            continue
        out.append({
            "run_id": s.get("run_id", ""), "key": test_key(s.get("test_path", "")),
            "name": s.get("test_name") or test_key(s.get("test_path", "")),
            "time": t, "passed": run_passed(s), "duration": float(s.get("duration_seconds") or 0),
            "message": "" if run_passed(s) else first_failure_message(s), "summary": s,
            "source": s.get("source", "manual"),
        })
    out.sort(key=lambda r: r["time"], reverse=True)
    return out


def run_detail(run_id):
    r = next((x for x in all_runs() if x["run_id"] == run_id), None)
    if not r:
        return None
    shots = data_helper.get_screenshots_for_run(run_id, r["summary"])
    return {**r, "time": r["time"].isoformat(timespec="minutes"), "steps": parse_steps(run_id),
            "shots": [{"file": f, "label": data_helper.screenshot_label(f)} for f in shots],
            "summary": None}


def compare_runs(a_id, b_id):
    a, b = run_detail(a_id), run_detail(b_id)
    if not a or not b:
        return None
    labels = []
    for s in a["steps"] + b["steps"]:
        if s["label"] not in labels:
            labels.append(s["label"])
    amap = {s["label"]: s for s in a["steps"]}
    bmap = {s["label"]: s for s in b["steps"]}
    fields = []
    for lb in labels:
        x, y = amap.get(lb), bmap.get(lb)
        rx = (x or {}).get("result") if (x or {}).get("ok") else ("❌ " + (x or {}).get("error", "")[:80] if x else "—")
        ry = (y or {}).get("result") if (y or {}).get("ok") else ("❌ " + (y or {}).get("error", "")[:80] if y else "—")
        fields.append({"label": lb, "a": rx or "—", "b": ry or "—", "same": (rx or "") == (ry or "")})
    shot_pairs = []
    blabels = {s["label"]: s for s in b["shots"]}
    for s in a["shots"]:
        shot_pairs.append({"label": s["label"], "a": s["file"], "b": (blabels.pop(s["label"], None) or {}).get("file")})
    for lb, s in blabels.items():
        shot_pairs.append({"label": lb, "a": None, "b": s["file"]})
    verdict = []
    if a["passed"] != b["passed"]:
        verdict.append(f"التشغيلة {'أ' if a['passed'] else 'ب'} نجحت والتانية فشلت")
    d = round(b["duration"] - a["duration"])
    if abs(d) >= 5:
        verdict.append(f"ب {'أبطأ' if d > 0 else 'أسرع'} بـ {abs(d)} ثانية ({round(100 * abs(d) / max(1, a['duration']))}%)")
    diff_fields = [f["label"] for f in fields if not f["same"]]
    if diff_fields:
        verdict.append("اختلاف في: " + "، ".join(diff_fields[:6]))
    if not verdict:
        verdict.append("نفس النتيجة تقريباً")
    return {"a": a, "b": b, "fields": fields, "shots": shot_pairs, "verdict": verdict}


def test_history(key, limit=40):
    rs = [r for r in all_runs() if r["key"] == key][:limit]
    rs.reverse()
    if not rs:
        return None
    passed = sum(r["passed"] for r in rs)
    streak, last = 0, rs[-1]["passed"]
    for r in reversed(rs):
        if r["passed"] != last:
            break
        streak += 1
    durs = [r["duration"] for r in rs if r["duration"]]
    return {
        "key": key, "name": rs[-1]["name"],
        "runs": [{"run_id": r["run_id"], "time": r["time"].isoformat(timespec="minutes"),
                  "label": r["time"].strftime("%d/%m %H:%M"), "passed": r["passed"],
                  "duration": r["duration"], "message": r["message"]} for r in rs],
        "pass_pct": round(100 * passed / len(rs)), "total": len(rs),
        "avg": round(sum(durs) / len(durs)) if durs else 0,
        "min": round(min(durs)) if durs else 0, "max": round(max(durs)) if durs else 0,
        "streak": streak, "streak_passed": last,
    }


def week_compare():
    t = datetime.now()
    cur_start, prev_start = t - timedelta(days=7), t - timedelta(days=14)
    groups = defaultdict(lambda: {"cur": [], "prev": [], "name": ""})
    for r in all_runs():
        g = groups[r["key"]]
        g["name"] = g["name"] or r["name"]
        if r["time"] > cur_start:
            g["cur"].append(r)
        elif r["time"] > prev_start:
            g["prev"].append(r)
    rows = []
    for key, g in groups.items():
        if not g["cur"] and not g["prev"]:
            continue

        def st(rs):
            if not rs:
                return None
            ds = [x["duration"] for x in rs if x["duration"]]
            return {"n": len(rs), "pass": round(100 * sum(x["passed"] for x in rs) / len(rs)),
                    "avg": round(sum(ds) / len(ds)) if ds else 0, "last_passed": rs[0]["passed"]}
        c, p = st(g["cur"]), st(g["prev"])
        if c and not p:
            tag = ("جديد", "info")
        elif p and not c:
            tag = ("ما اتشغلش الأسبوع ده", "secondary")
        elif p["last_passed"] and not c["last_passed"]:
            tag = ("بقى فاشل", "danger")
        elif not p["last_passed"] and c["last_passed"]:
            tag = ("اتصلّح", "success")
        elif c["pass"] < p["pass"] - 10 or (p["avg"] and c["avg"] > p["avg"] * 1.25):
            tag = ("اتدهور", "warning")
        elif c["pass"] > p["pass"] + 10 or (p["avg"] and c["avg"] < p["avg"] * 0.8):
            tag = ("اتحسن", "success")
        else:
            tag = ("ثابت", "light")
        rows.append({"key": key, "name": g["name"], "cur": c, "prev": p, "tag": tag[0], "tag_class": tag[1]})
    order = {"بقى فاشل": 0, "اتدهور": 1, "جديد": 2, "اتصلّح": 3, "اتحسن": 4, "ثابت": 5, "ما اتشغلش الأسبوع ده": 6}
    rows.sort(key=lambda r: (order.get(r["tag"], 9), r["name"]))
    return rows
