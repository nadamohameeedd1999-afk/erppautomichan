"""🚀 الإصدارات — the page and its API (adding / approving a version is admin)."""
from flask import Blueprint, jsonify, render_template, request

from web import auth, releases

bp = Blueprint("releases", __name__)


@bp.route("/releases")
@auth.login_required
def page():
    return render_template("releases.html")


@bp.route("/api/releases")
@auth.login_required
def api_list():
    return jsonify(releases.overview())


@bp.route("/api/releases/add", methods=["POST"])
@auth.login_required
def api_add():
    b = request.get_json(silent=True) or {}
    if not releases.version_ok(str(b.get("version") or "").strip()):
        return jsonify({"ok": False, "error": "رقم النسخة: حروف وأرقام ونقط بس"}), 400
    try:
        r = releases.add(b.get("version"), b.get("notes", ""), b.get("pilot") or [], b.get("test_site", ""))
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "release": r})


@bp.route("/api/releases/<rid>", methods=["POST"])
@auth.login_required
def api_update(rid):
    b = request.get_json(silent=True) or {}
    b["by"] = (auth.current_user() or {}).get("full_name") or (auth.current_user() or {}).get("username", "")
    try:
        releases.update(rid, b)
    except KeyError:
        return jsonify({"ok": False, "error": "مش موجودة"}), 404
    return jsonify({"ok": True})
