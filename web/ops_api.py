"""
Run center (مركز التشغيل), comparison (المقارنة), backups and reports — pages + JSON API.
"""
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, send_file

from web import auth, insights
from web.queue_manager import get_manager

bp = Blueprint("ops", __name__)


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
    return jsonify({"success": True, "running": cur, "running_all": st.get("running_all", []), "workers": st.get("workers", 1),
                    "queue": st.get("queue", []), "log": log_tail,
                    "recent": recent, "server_time": datetime.now().isoformat(timespec="seconds")})


@bp.route("/api/run-center/workers", methods=["POST"])
@auth.login_required
def api_rc_workers():
    n = (request.get_json(silent=True) or {}).get("workers", 1)
    qm = get_manager()
    n = qm.set_workers(n)
    qm._pump()                      # free slots start waiting tests right away
    return jsonify({"success": True, "workers": n})


@bp.route("/api/run-center/stop/<task_id>", methods=["POST"])
@auth.login_required
def api_rc_stop(task_id):
    return jsonify({"success": get_manager().stop_current(task_id)})


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
        by_id = {r["run_id"]: r for r in runs}
        test = request.args.get("test") or (by_id[b]["key"] if b in by_id else (runs[0]["key"] if runs else None))
        same = [r for r in runs if r["key"] == test]                      # newest first
        preset = request.args.get("preset", "")
        last_pass = next((r for r in same if r["passed"]), None)
        last_fail = next((r for r in same if not r["passed"]), None)
        if preset == "pass_fail" or (not (a and b) and same):
            # the useful default: what changed between the last time it passed and now
            if b not in by_id:
                b = (last_fail if preset == "pass_fail" and last_fail else same[0])["run_id"] if same else None
            older_pass = next((r for r in same if r["passed"] and by_id.get(b) and r["time"] < by_id[b]["time"]), None)
            if not a or preset == "pass_fail":
                a = (older_pass or (same[1] if len(same) > 1 else None) or {}).get("run_id")
        elif preset == "last2" and len(same) >= 2:
            b, a = same[0]["run_id"], same[1]["run_id"]
        ctx.update({"a": a, "b": b, "test": test, "cmp": insights.compare_runs(a, b) if a and b else None,
                    "test_runs": [{"run_id": r["run_id"], "passed": r["passed"], "label": r["time"].strftime("%d/%m %H:%M"),
                                   "duration": round(r["duration"])} for r in same[:200]],
                    "has_pass": bool(last_pass), "has_fail": bool(last_fail)})
    elif tab == "test":
        key = request.args.get("key") or (ctx["tests"][0]["key"] if ctx["tests"] else None)
        ctx.update({"key": key, "hist": insights.test_history(key) if key else None})
    else:
        ctx.update({"week": insights.week_compare()})
    return render_template("compare.html", **ctx)


# ======================= backups & trash =======================
@bp.route("/backups")
@auth.login_required
def backups_page():
    from config import paths
    return render_template("backups.html", data_dir=str(paths.DATA_DIR))


@bp.route("/api/backups")
@auth.login_required
def api_backups():
    from web import backup
    return jsonify({"success": True, "backups": backup.list_all(), "trash": backup.trash_list(),
                    "keep": backup.KEEP_AUTO, "hour": backup.BACKUP_HOUR})


@bp.route("/api/backups", methods=["POST"])
@auth.login_required
def api_backup_create():
    from web import backup
    full = bool((request.get_json(silent=True) or {}).get("full"))
    return jsonify({"success": True, "backup": backup.create("manual", full=full)})


@bp.route("/backups/download/<name>")
@auth.login_required
def backup_download(name):
    from web import backup
    p = backup.path_of(name)
    if not p:
        return jsonify({"success": False, "error": "مش موجود"}), 404
    return send_file(str(p), as_attachment=True, download_name=p.name)


@bp.route("/api/backups/restore", methods=["POST"])
@auth.login_required
def api_backup_restore():
    from web import backup
    from config import paths
    if not auth.is_admin():
        return jsonify({"success": False, "error": "الاسترجاع للأدمن بس"}), 403
    up = request.files.get("file")
    if up and up.filename:
        tmp = paths.STATE_DIR / "upload_restore.zip"
        up.save(str(tmp))
        target = tmp
    else:
        target = backup.path_of((request.form.get("name") or (request.get_json(silent=True) or {}).get("name") or ""))
    if not target:
        return jsonify({"success": False, "error": "اختاري نسخة"}), 400
    try:
        r = backup.restore(target)
    except Exception as e:
        return jsonify({"success": False, "error": f"الملف ده مش نسخة سليمة: {e}"}), 400
    return jsonify({"success": True, **r})


@bp.route("/api/trash/restore", methods=["POST"])
@auth.login_required
def api_trash_restore():
    from web import backup
    rel = (request.get_json(silent=True) or {}).get("id", "")
    return jsonify({"success": backup.trash_restore(rel)})


# ======================= daily report (التقرير اليومي) =======================
def _report_range():
    from datetime import datetime, timedelta
    def parse(v, default):
        try:
            return datetime.fromisoformat(v) if v else default
        except ValueError:
            return default
    now = datetime.now()
    to = parse(request.args.get("to"), now)
    frm = parse(request.args.get("from"), to - timedelta(days=1))
    return frm, to


@bp.route("/reports/daily")
@auth.login_required
def daily_report_page():
    from web import daily_report
    frm, to = _report_range()
    page = daily_report.html_report(frm, to, (auth.current_user() or {}).get("full_name", ""))
    q = request.query_string.decode()
    bar = (f'<div class="noprint" style="font-family:Tahoma;text-align:center;margin:10px">'
           f'<a href="/reports/daily.pdf?{q}" style="background:#0F7C7A;color:#fff;padding:8px 16px;border-radius:8px;text-decoration:none">⬇️ PDF</a> '
           f'<a href="javascript:print()" style="margin-inline-start:8px">🖨️ طباعة</a> '
           f'<a href="/reports" style="margin-inline-start:8px">↩ التقارير</a></div>')
    return page.replace("<body>", "<body>" + bar, 1)


@bp.route("/reports/daily.pdf")
@auth.login_required
def daily_report_pdf():
    from flask import Response
    from web import daily_report
    frm, to = _report_range()
    pdf = daily_report.pdf_report(frm, to, (auth.current_user() or {}).get("full_name", ""))
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="daily_report_{to:%Y%m%d}.pdf"'})


@bp.route("/reports/discovery/<rid>")
@auth.login_required
def discovery_report_page(rid):
    from flask import abort
    from web import discovery_report as dr
    d = dr.load(rid)
    if not d:
        abort(404)
    page = dr.html_report(d, (auth.current_user() or {}).get("full_name", ""))
    bar = (f'<div class="noprint" style="font-family:Tahoma;text-align:center;margin:10px">'
           f'<a href="/reports/discovery/{rid}.pdf" style="background:#0F7C7A;color:#fff;padding:8px 16px;border-radius:8px;text-decoration:none">⬇️ PDF</a> '
           f'<a href="javascript:print()" style="margin-inline-start:8px">🖨️ طباعة</a> '
           f'<a href="/reports#discovery" style="margin-inline-start:8px">↩ التقارير</a></div>')
    return page.replace("<body>", "<body>" + bar, 1)


@bp.route("/reports/discovery/<rid>.pdf")
@auth.login_required
def discovery_report_pdf(rid):
    from flask import Response, abort
    from web import discovery_report as dr, daily_report
    d = dr.load(rid)
    if not d:
        abort(404)
    pdf = daily_report.html_to_pdf(dr.html_report(d, (auth.current_user() or {}).get("full_name", ""), for_pdf=True))
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": f'inline; filename="{rid}.pdf"'})


@bp.route("/api/reports/discovery")
@auth.login_required
def discovery_report_list():
    from web import discovery_report as dr
    return jsonify({"success": True, "runs": dr.list_runs()})


@bp.route("/api/reports/daily/send", methods=["POST"])
@auth.login_required
def daily_report_send():
    from web import daily_report
    try:
        f = daily_report.send_daily()
        return jsonify({"success": True, "file": f.name})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
