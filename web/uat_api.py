"""✍️ اختبار القبول مع العميل — our page (sessions, progress, certificate) + the client's link (no login, the token is the key)."""
import io
from datetime import datetime

from flask import Blueprint, abort, jsonify, render_template, request, send_file

from web import auth

bp = Blueprint("uat", __name__)


def _brief(d):
    from engine import uat as U
    return {"id": d["id"], "title": d["title"], "client": d["client"], "site_url": d["site_url"], "created": d["created"], "status": d["status"],
            "testers": d["testers"], "progress": U.progress(d), "link": request.host_url.rstrip("/") + "/uat/s/" + d["token"],
            "signoff": {k: v for k, v in (d.get("signoff") or {}).items() if k != "sig"} or None}


@bp.route("/uat")
@auth.login_required
def page():
    return render_template("uat.html")


@bp.route("/api/uat")
@auth.login_required
def api_list():
    from engine import uat as U
    from web.repcmp_api import _sites
    return jsonify({"success": True, "sessions": [_brief(d) for d in U.all_sessions()], "sites": _sites(),
                    "templates": [{"key": k, "name": v[0], "n": len(v[1]), "steps": sum(len(s[1]) for s in v[1])} for k, v in U.TEMPLATES.items()]})


@bp.route("/api/uat/create", methods=["POST"])
@auth.login_required
def api_create():
    from engine import uat as U
    j = request.get_json(silent=True) or {}
    if not j.get("modules") and not j.get("custom"):
        return jsonify({"success": False, "error": "اختار موديول واحد على الأقل"}), 400
    testers = j.get("testers") or []
    if isinstance(testers, str):
        testers = [x for x in testers.replace("،", ",").split(",")]
    d = U.create(j.get("title") or "", j.get("client") or "", j.get("site_url") or "", j.get("modules") or [], testers,
                 (auth.current_user() or {}).get("username", ""), j.get("custom") or [])
    return jsonify({"success": True, "session": _brief(d)})


@bp.route("/api/uat/<sid>")
@auth.login_required
def api_one(sid):
    from engine import uat as U
    d = U.load(sid)
    if not d:
        return jsonify({"success": False, "error": "مش موجود"}), 404
    return jsonify({"success": True, "session": {**_brief(d), "scenarios": d["scenarios"]}})


@bp.route("/api/uat/<sid>/assign", methods=["POST"])
@auth.login_required
def api_assign(sid):
    from engine import uat as U
    d = U.load(sid)
    if not d:
        return jsonify({"success": False}), 404
    j = request.get_json(silent=True) or {}
    for s in d["scenarios"]:
        if s["id"] == j.get("scenario"):
            s["assignee"] = str(j.get("assignee") or "")[:60]
    U.save(d)
    return jsonify({"success": True})


@bp.route("/api/uat/<sid>/delete", methods=["POST"])
@auth.login_required
def api_delete(sid):
    from engine import uat as U
    if not auth.is_admin():
        return jsonify({"success": False, "error": "للأدمن بس"}), 403
    f = U._f(sid)
    if f.exists():
        f.unlink()
    return jsonify({"success": True})


def _cert(d, fmt):
    from engine import uat as U
    html = U.certificate_html(d, (auth.current_user() or {}).get("username", "") or (d.get("signoff") or {}).get("name", ""))
    if fmt == "html":
        return html
    from utils.pdf import html_to_pdf
    return send_file(io.BytesIO(html_to_pdf(html)), as_attachment=True, download_name=f"UAT_{d['client'] or d['id']}_{datetime.now():%Y%m%d}.pdf",
                     mimetype="application/pdf")


@bp.route("/api/uat/<sid>/certificate")
@auth.login_required
def api_cert(sid):
    from engine import uat as U
    d = U.load(sid)
    if not d:
        abort(404)
    return _cert(d, request.args.get("fmt"))


@bp.route("/uat/file/<sid>/<name>")
@auth.login_required
def api_file(sid, name):
    from engine import uat as U
    import re
    f = U.files_dir(sid) / re.sub(r"[^A-Za-z0-9_.]", "", name)
    if not f.exists():
        abort(404)
    return send_file(f)


# ------------------------------------------------------------------ the client's link (no login)
def _tok(token):
    from engine import uat as U
    d = U.by_token(token)
    if not d:
        abort(404)
    return d


@bp.route("/uat/s/<token>")
def public_page(token):
    d = _tok(token)
    return render_template("uat_public.html", title=d["title"], client=d["client"])


@bp.route("/api/uat/s/<token>")
def public_state(token):
    from engine import uat as U
    d = _tok(token)
    return jsonify({"success": True, **U.public(d, request.args.get("tester") or "")})


@bp.route("/api/uat/s/<token>/step", methods=["POST"])
def public_step(token):
    from engine import uat as U
    d = _tok(token)
    j = request.get_json(silent=True) or {}
    try:
        U.set_step(d, j.get("step"), j.get("result") or "", j.get("note"), j.get("by"))
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "progress": U.progress(d)})


@bp.route("/api/uat/s/<token>/file", methods=["POST"])
def public_file(token):
    from engine import uat as U
    d = _tok(token)
    f = request.files.get("file")
    if not f:
        return jsonify({"success": False, "error": "اختار صورة"}), 400
    try:
        U.attach(d, request.form.get("step"), f.filename or "", f.read())
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True})


@bp.route("/uat/s/<token>/file/<name>")
def public_file_get(token, name):
    from engine import uat as U
    import re
    d = _tok(token)
    f = U.files_dir(d["id"]) / re.sub(r"[^A-Za-z0-9_.]", "", name)
    if not f.exists():
        abort(404)
    return send_file(f)


@bp.route("/api/uat/s/<token>/sign", methods=["POST"])
def public_sign(token):
    from engine import uat as U
    d = _tok(token)
    j = request.get_json(silent=True) or {}
    try:
        U.sign(d, j.get("name"), j.get("job"), j.get("decision"), j.get("notes"), j.get("sig"))
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True})


@bp.route("/uat/s/<token>/certificate")
def public_cert(token):
    d = _tok(token)
    if d["status"] != "signed":
        abort(404)
    return _cert(d, request.args.get("fmt"))
