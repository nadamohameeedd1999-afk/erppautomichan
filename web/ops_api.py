"""
Run center (مركز التشغيل), schedules (الجدولة) and comparison (المقارنة) — pages + JSON API.
"""
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

from web import auth, insights, scheduler
from web.queue_manager import get_manager

bp = Blueprint("ops", __name__)


def _test_catalog():
    """All runnable full tests (screens + scenarios) for pickers."""
    out = []
    for r in scheduler._registry_rows():
        group = r.get("module_name", "")
        if r.get("full_path"):
            out.append({"path": r["full_path"], "name": r["name"], "group": group, "kind": "full"})
        for sc in r.get("scenarios") or []:
            out.append({"path": sc["full_path"], "name": f"{r['name']} — {sc['name']}", "group": group, "kind": "scenario"})
        if r.get("smoke_path") and not r.get("full_path"):
            out.append({"path": r["smoke_path"], "name": f"{r['name']} (شاشة)", "group": group, "kind": "smoke"})
    return out


# ======================= run center =======================
@bp.route("/queue")
@auth.login_required
def run_center():
    return render_template("queue.html")


@bp.route("/api/run-center")
@auth.login_required
def api_run_center():
    qm = get_manager()
    st = qm.get_status()
    cur = st.get("running")
    log_tail = []
    if cur:
        r = qm.read_log(cur["task_id"], max_lines=25)
        if r.get("success"):
            import re
            ansi = re.compile(r"\x1b\[[0-9;]*m")
            log_tail = [ansi.sub("", l) for l in r["lines"]]
    recent = []
    for r in insights.all_runs()[:25]:
        s = r["summary"]
        recent.append({"run_id": r["run_id"], "name": r["name"], "passed": r["passed"],
                       "time": r["time"].isoformat(timespec="minutes"), "duration": r["duration"],
                       "message": r["message"], "path": s.get("test_path"), "source": s.get("source", "manual"),
                       "retry_of": s.get("retry_of"), "auto_retry": s.get("auto_retry"),
                       "repeat": s.get("repeat", 1)})
    return jsonify({"success": True, "running": cur, "queue": st.get("queue", []), "log": log_tail,
                    "recent": recent, "server_time": datetime.now().isoformat(timespec="seconds")})


@bp.route("/api/run-center/remove/<task_id>", methods=["POST"])
@auth.login_required
def api_rc_remove(task_id):
    return jsonify({"success": get_manager().remove(task_id)})


@bp.route("/api/run-center/move/<task_id>/<int:delta>", methods=["POST"])
@bp.route("/api/run-center/move/<task_id>/-<int:up>", methods=["POST"])
@auth.login_required
def api_rc_move(task_id, delta=None, up=None):
    d = -up if up is not None else delta
    return jsonify({"success": get_manager().move(task_id, d)})


@bp.route("/api/run-center/clear", methods=["POST"])
@auth.login_required
def api_rc_clear():
    return jsonify({"success": True, "removed": get_manager().clear()})


@bp.route("/api/run-center/rerun", methods=["POST"])
@auth.login_required
def api_rc_rerun():
    d = request.get_json(silent=True) or {}
    path = (d.get("path") or "").strip()
    if not path:
        return jsonify({"success": False, "error": "مفيش مسار اختبار"}), 400
    task_id = f"run_{datetime.now():%Y%m%d%H%M%S}"
    r = get_manager().add(task_id, path, d.get("name") or path, repeat=int(d.get("repeat") or 1), source="rerun")
    return jsonify({"success": True, "task_id": task_id, **r})


# ======================= schedules =======================
@bp.route("/schedule")
@auth.login_required
def schedule_page():
    return render_template("schedule.html", day_names=scheduler.DAY_NAMES, tz=scheduler.TZ_NAME)


def _sched_view(s):
    nxt = scheduler.next_run(s)
    last = None
    if s.get("last_batch"):
        ids = set(s["last_batch"])
        runs = [r for r in insights.all_runs() if r["run_id"] in ids]
        if runs:
            last = {"passed": sum(r["passed"] for r in runs), "failed": sum(not r["passed"] for r in runs),
                    "total": len(s["last_batch"]), "done": len(runs)}
    targets = scheduler.resolve_targets(s) if s.get("mode") != "list" else s.get("targets", [])
    return {**s, "next": nxt.isoformat(timespec="minutes") if nxt else None,
            "days_text": scheduler.describe_days(s), "last": last, "target_count": len(targets)}


@bp.route("/api/schedules")
@auth.login_required
def api_sched_list():
    return jsonify({"success": True, "schedules": [_sched_view(s) for s in scheduler.load()],
                    "catalog": _test_catalog(), "now": scheduler.now().isoformat(timespec="minutes"),
                    "tz": scheduler.TZ_NAME})


@bp.route("/api/schedules", methods=["POST"])
@auth.login_required
def api_sched_save():
    try:
        s = scheduler.upsert(request.get_json(silent=True) or {})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "schedule": _sched_view(s)})


@bp.route("/api/schedules/<sch_id>", methods=["DELETE"])
@auth.login_required
def api_sched_delete(sch_id):
    scheduler.delete(sch_id)
    return jsonify({"success": True})


@bp.route("/api/schedules/<sch_id>/toggle", methods=["POST"])
@auth.login_required
def api_sched_toggle(sch_id):
    on = bool((request.get_json(silent=True) or {}).get("enabled"))
    scheduler.set_enabled(sch_id, on)
    return jsonify({"success": True})


@bp.route("/api/schedules/<sch_id>/run", methods=["POST"])
@auth.login_required
def api_sched_run(sch_id):
    s = next((x for x in scheduler.load() if x["id"] == sch_id), None)
    if not s:
        return jsonify({"success": False, "error": "الجدولة مش موجودة"}), 404
    batch = scheduler.fire(s, manual=True)
    return jsonify({"success": True, "queued": len(batch)})


# ======================= compare =======================
@bp.route("/compare")
@auth.login_required
def compare_page():
    tab = request.args.get("tab", "runs")
    runs = insights.all_runs()
    tests = {}
    for r in runs:
        tests.setdefault(r["key"], {"key": r["key"], "name": r["name"], "count": 0})["count"] += 1
    ctx = {"tab": tab, "runs": [{"run_id": r["run_id"], "name": r["name"], "key": r["key"], "passed": r["passed"],
                                 "label": r["time"].strftime("%d/%m %H:%M"), "duration": round(r["duration"])}
                                for r in runs[:300]],
           "tests": sorted(tests.values(), key=lambda t: -t["count"])}
    if tab == "runs":
        a, b = request.args.get("a"), request.args.get("b")
        if not (a and b) and runs:
            # default: the last two runs of the most recent test
            same = [r for r in runs if r["key"] == runs[0]["key"]]
            if len(same) >= 2:
                b, a = same[0]["run_id"], same[1]["run_id"]
        ctx.update({"a": a, "b": b, "cmp": insights.compare_runs(a, b) if a and b else None})
    elif tab == "test":
        key = request.args.get("key") or (ctx["tests"][0]["key"] if ctx["tests"] else None)
        ctx.update({"key": key, "hist": insights.test_history(key) if key else None})
    else:
        ctx.update({"week": insights.week_compare()})
    return render_template("compare.html", **ctx)
