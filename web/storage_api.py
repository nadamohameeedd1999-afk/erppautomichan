"""🗄️ مساحة السيرفر — Settings tab: what fills the disk, preview + safe cleanup, automatic policy."""
from flask import Blueprint, jsonify, request

from web import auth

bp = Blueprint("storage", __name__)


def _args(d):
    from utils import storage
    pol = storage.load_policy()
    return (d.get("cats") or pol["cats"], int(d.get("days", pol["days"])), int(d.get("keep_backups", pol["keep_backups"])))


@bp.route("/api/storage")
@auth.login_required
def api_usage():
    from utils import storage
    return jsonify({"success": True, **storage.usage()})


@bp.route("/api/storage/preview", methods=["POST"])
@auth.login_required
def api_preview():
    from utils import storage
    return jsonify({"success": True, "plan": storage.preview(*_args(request.get_json(silent=True) or {}))})


@bp.route("/api/storage/clean", methods=["POST"])
@auth.login_required
def api_clean():
    from utils import storage
    d = request.get_json(silent=True) or {}
    bk = None
    if d.get("backup"):                            # 📦 everything the program saved (results, settings, tests, health…) except the images
        from web import backup
        try:
            b = backup.create("preclean", shots=False)
            bk = {"name": b.get("name"), "mb": round((b.get("size_kb") or 0) / 1024, 1), "url": f"/backups/download/{b.get('name')}"}
        except OSError as e:
            return jsonify({"success": False, "error": f"مقدرتش آخد نسخة احتياطية قبل المسح ({e}) — مامسحتش حاجة"}), 500
    out = storage.clean(*_args(d))
    out["backup"] = bk
    try:
        auth.audit("storage_clean", f"{out['files']} files, {out['mb']} MB")
    except Exception:
        pass
    return jsonify({"success": True, **out, "usage": storage.usage()})


@bp.route("/api/storage/policy", methods=["POST"])
@auth.login_required
def api_policy():
    from utils import storage
    return jsonify({"success": True, "policy": storage.save_policy(request.get_json(silent=True) or {})})
