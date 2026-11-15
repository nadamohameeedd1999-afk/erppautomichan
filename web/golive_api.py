"""🚀 اختبار الاستلام — page + API: pick the client's site, run every stage first in line (in order), one verdict, one report."""
import io
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, send_file

from web import auth

bp = Blueprint("golive", __name__)


def _sites():
    from web.repcmp_api import _sites as s
    return s()


def _site(sid):
    return next((s for s in _sites() if s["id"] == sid), None)


@bp.route("/go-live")
@auth.login_required
def page():
    return render_template("golive.html")


def _extra_checks():
    from engine import checks as C
    return [{"key": c["key"], "name": c.get("name_ar") or c["key"], "type": c["type"]} for c in C.list_all()
            if c.get("type") in ("bizcases", "biz", "cycle") and not c.get("error")]


@bp.route("/api/golive")
@auth.login_required
def api_state():
    from engine import golive as G
    sites = _sites()
    for s in sites:
        p = G.load_plan(s["url"])
        s["last"] = {k: (p.get("last") or {}).get(k) for k in ("at", "verdict", "verdict_text")} if p.get("last") else None
    sid = request.args.get("site") or next((s["id"] for s in sites if s.get("last")), next((s["id"] for s in sites if s["kind"] == "client"), sites[0]["id"] if sites else ""))
    cur = next((s for s in sites if s["id"] == sid), None)
    data = None
    if cur:
        data = G.collect(cur["url"], cur["name"])
        p = G.load_plan(cur["url"])
        if p:
            p["last"] = data
            G.save_plan(cur["url"], p)
    return jsonify({"success": True, "sites": sites, "site": cur, "data": data, "extras": _extra_checks(),
                    "stages": [{"type": t, "key": k, "icon": i, "name": n} for t, k, i, n in G.STEPS]})


@bp.route("/api/golive/run", methods=["POST"])
@auth.login_required
def api_run():
    from engine import checks as C
    from engine import golive as G
    from web.queue_manager import get_manager
    j = request.get_json(silent=True) or {}
    site = _site(j.get("site"))
    if not site:
        return jsonify({"success": False, "error": "اختار الموقع"}), 400
    want = set(j.get("stages") or [k for _, k, _, _ in G.STEPS])
    cfgs = G.configs(j)
    stages = []
    for t, k, icon, name in G.STEPS:
        if k in want:
            saved = C.save(cfgs[k])
            stages.append({"key": k, "kind": t, "name": f"{icon} {name}", "path": C.test_path_for(saved["key"])})
    for x in _extra_checks():
        if x["key"] in (j.get("extras") or []):
            stages.append({"key": x["key"], "kind": x["type"], "name": "📚 " + x["name"], "path": C.test_path_for(x["key"])})
    if not stages:
        return jsonify({"success": False, "error": "اختار مرحلة واحدة على الأقل"}), 400
    qm = get_manager()
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    tasks = []
    for i, s in enumerate(stages):
        tid = f"run_{stamp}{i:02d}{uuid.uuid4().hex[:3]}"
        tasks.append({"task_id": tid, "test_path": s["path"], "test_name": f"🚀 استلام · {s['name']}", "repeat": 1, "source": "golive",
                      "added_at": datetime.now().isoformat(), "status": "queued", "site": site["id"], "site_name": site["name"]})
        s["task_id"] = tid
    # first in line, IN ORDER (the screens first: the API and the load test read what it found)
    with qm.lock:
        for i, t in enumerate(tasks):
            qm.queue.insert(i, t)
    qm._pump()
    G.save_plan(site["url"], {"site": site["id"], "name": site["name"], "url": site["url"], "at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                              "by": (auth.current_user() or {}).get("username", ""), "opts": {k: j.get(k) for k in ("users", "rounds", "deep_speed")},
                              "tasks": [{"task_id": s["task_id"], "key": s["key"], "kind": s["kind"], "name": s["name"]} for s in stages]})
    warn = "" if site["kind"] != "client" else ("⚠️ الموقع متسجل «نظام عميل» (قراءة بس): اختبار الحمل والدورات المستندية هيتخطوا. "
                                                "لو ده موقع العميل التجريبي: الإعدادات ← مواقع الاختبار ← نوع الموقع «موقع اختبار».")
    return jsonify({"success": True, "task_ids": [t["task_id"] for t in tasks], "count": len(tasks), "warn": warn})


def _data(sid):
    from engine import golive as G
    s = _site(sid)
    if not s:
        return None
    return G.collect(s["url"], s["name"])


@bp.route("/api/golive/export")
@auth.login_required
def api_export():
    from engine import golive as G
    d = _data(request.args.get("site"))
    if not d:
        return jsonify({"success": False, "error": "اختار الموقع"}), 400
    user = (auth.current_user() or {}).get("username", "")
    host = d["url"].split("//")[-1].split("/")[0].split(".")[0]
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    fmt = request.args.get("fmt") or "pdf"
    if fmt == "json":
        import json
        return send_file(io.BytesIO(json.dumps(d, ensure_ascii=False, default=str).encode()), as_attachment=True,
                         download_name=f"GoLive_{host}_{stamp}.json", mimetype="application/json")
    if fmt == "docx":
        return send_file(io.BytesIO(G.report_docx(d, user)), as_attachment=True, download_name=f"GoLive_{host}_{stamp}.docx",
                         mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    html = G.report_html(d, user)
    if fmt == "html":
        return html
    from utils.pdf import html_to_pdf
    return send_file(io.BytesIO(html_to_pdf(html)), as_attachment=True, download_name=f"GoLive_{host}_{stamp}.pdf", mimetype="application/pdf")
