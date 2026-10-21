"""
Numbers for the home dashboard (الرئيسية): KPIs, trend, coverage, failing now,
flaky tests, slowest tests, recent runs, upcoming schedules.

Everything is read from reports/results/summary_*.json + the tests registry,
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
    for sch in data_helper.load_schedules() or []:
        if not sch.get("enabled", True):
            continue
        nxt = _next_run(sch, now)
        tid = sch.get("test_id", "")
        upcoming.append({"name": sch.get("name") or tid, "test": tid, "time": sch.get("time", ""),
                         "frequency": sch.get("frequency", ""),
                         "next": nxt.isoformat(timespec="minutes") if nxt else ""})
    upcoming.sort(key=lambda x: x["next"] or "9")

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
        "recent": [{**r, "time": r["time"].isoformat(timespec="minutes")} for r in runs[:10]],
        "upcoming": upcoming[:5],
    }
