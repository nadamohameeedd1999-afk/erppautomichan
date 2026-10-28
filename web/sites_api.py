"""
Many clients (أكتر من عميل): the same tests on every test site (Settings → مواقع الاختبار), and one page that shows
how each client's system is doing.

/sites                       page: a card per site + a matrix test × site with the last result
/api/sites                   GET the site profiles (no passwords)
/api/sites/matrix            GET the matrix
/api/sites/run               POST {tests: [{path, name}], sites: "all" | [ids]} -> queue on each site
queue_on_sites(...)          used by /api/run-test, the advanced tests and schedules
"""
import uuid
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request

from web import auth

bp = Blueprint("sites", __name__)


def profiles():
    from web import test_sites_helper as ts
    data = ts.load_all()
    act = data.get("active_profile")
    return [{"id": p.get("id"), "name": p.get("name") or p.get("id"), "base_url": p.get("base_url", ""),
             "active": p.get("id") == act} for p in data.get("profiles", [])]


def active_id():
    return next((p["id"] for p in profiles() if p["active"]), "")


def resolve_sites(sites):
    """None / "" -> [""] (the active site) · "all" -> every profile · [ids] -> those"""
    if not sites:
        return [""]
    allp = profiles()
    if sites == "all" or sites == ["all"]:
        return [p["id"] for p in allp] or [""]
    if isinstance(sites, str):
        sites = [s for s in sites.split(",") if s.strip()]
    ids = {p["id"] for p in allp}
    out = [s for s in sites if s in ids or s == ""]
    return out or [""]


def site_name(sid):
    if not sid:
        return ""
    p = next((x for x in profiles() if x["id"] == sid), None)
    return p["name"] if p else sid


def queue_on_sites(qm, test_path, test_name, sites=None, source="manual", repeat=1, extra=None):
    ids = resolve_sites(sites)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    task_ids, first = [], None
    for i, sid in enumerate(ids):
        tid = f"run_{stamp}{i:02d}{uuid.uuid4().hex[:3]}"
        name = test_name + (f" · {site_name(sid)}" if sid and len(ids) > 1 else "")
        r = qm.add(tid, test_path, name, repeat=repeat, source=source,
                   extra={**(extra or {}), "site": sid, "site_name": site_name(sid)})
        task_ids.append(tid)
        first = first or {**r, "task_id": tid}
    return {"task_id": task_ids[0], "task_ids": task_ids, "count": len(task_ids),
            "queued": first.get("queued") if first else False, "position": first.get("position") if first else 0}


# ---------------------------------------------------------------- matrix
def matrix(days=30):
    from web import insights
    profs = profiles()
    act = active_id()
    cols = [{"id": p["id"], "name": p["name"], "base_url": p["base_url"], "active": p["active"]} for p in profs]
    if not cols:
        cols = [{"id": "", "name": "الموقع الأساسي", "base_url": "", "active": True}]
    since = datetime.now() - timedelta(days=days)
    cells, names, per_site = {}, {}, {c["id"]: {"runs": 0, "passed": 0, "last": None, "failing": set()} for c in cols}
    for r in insights.all_runs():                       # newest first
        s = r["summary"]
        if s.get("auto_retry"):
            continue
        sid = s.get("site") or act or (cols[0]["id"] if cols else "")
        if sid not in per_site:
            continue
        key = r["key"]
        names.setdefault(key, (r["name"] or key).replace("⏰ ", "").split(" · ")[0])
        if (key, sid) not in cells:
            cells[(key, sid)] = {"passed": r["passed"], "time": r["time"].strftime("%m-%d %H:%M"), "run_id": r["run_id"],
                                 "message": (r["message"] or "").split("\n")[0][:140]}
            if not r["passed"]:
                per_site[sid]["failing"].add(key)
        if r["time"] >= since:
            st = per_site[sid]
            st["runs"] += 1
            st["passed"] += 1 if r["passed"] else 0
            st["last"] = st["last"] or r["time"].strftime("%Y-%m-%d %H:%M")
    keys = sorted(names, key=lambda k: names[k])
    rows = [{"key": k, "name": names[k], "cells": [cells.get((k, c["id"])) for c in cols]} for k in keys]
    for c in cols:
        st = per_site[c["id"]]
        c.update({"runs": st["runs"], "rate": round(st["passed"] / st["runs"] * 100) if st["runs"] else None,
                  "failing": len(st["failing"]), "last": st["last"]})
    return {"sites": cols, "rows": rows, "days": days}


@bp.route("/sites")
@auth.login_required
def sites_page():
    return render_template("sites.html", m=matrix())


@bp.route("/api/sites")
@auth.login_required
def api_sites():
    return jsonify({"success": True, "sites": profiles()})


@bp.route("/api/sites/matrix")
@auth.login_required
def api_matrix():
    return jsonify({"success": True, **matrix(int(request.args.get("days", 30) or 30))})


@bp.route("/api/sites/run", methods=["POST"])
@auth.login_required
def api_run():
    from web.queue_manager import get_manager
    d = request.get_json(silent=True) or {}
    tests = [t for t in d.get("tests") or [] if t.get("path")]
    if d.get("all_full"):
        from web import scheduler
        tests = scheduler.resolve_targets({"mode": "all_full"})
    if not tests:
        return jsonify({"success": False, "error": "اختاري اختبار واحد على الأقل"}), 400
    qm, ids = get_manager(), []
    for t in tests:
        ids += queue_on_sites(qm, t["path"], t.get("name") or t["path"], d.get("sites") or "all")["task_ids"]
    return jsonify({"success": True, "count": len(ids), "task_ids": ids})
