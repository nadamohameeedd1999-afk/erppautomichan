"""📡 مراقبة المواقع — the page, its state, «افحص دلوقتي», and its settings (admin)."""
import threading

from flask import Blueprint, jsonify, render_template, request

from web import auth, monitor

bp = Blueprint("monitor", __name__)


@bp.route("/monitor")
@auth.login_required
def page():
    return render_template("monitor.html")


@bp.route("/api/monitor")
@auth.login_required
def api_state():
    return jsonify({**monitor.summary(), "busy": monitor._busy["on"], "deep_busy": monitor._busy["deep"]})


@bp.route("/api/monitor/run", methods=["POST"])
@auth.login_required
def api_run():
    deep = bool((request.get_json(silent=True) or {}).get("deep"))       # «افحص الشاشات دلوقتي»: sign in and open the menu (read only)
    if not monitor._busy["deep" if deep else "on"]:
        threading.Thread(target=monitor.run_deep if deep else monitor.run_once, kwargs={"force": True}, name="monitor-now", daemon=True).start()
    return jsonify({"ok": True})


@bp.route("/api/monitor/settings", methods=["POST"])
@auth.login_required
def api_settings():
    return jsonify({"ok": True, "config": monitor.save_config(request.get_json(silent=True) or {})})


# ------------------------------------------------------------------ 🛰️ NQ ERP reports its own errors (web/telemetry.py)
def _cors(r):
    r.headers["Access-Control-Allow-Origin"] = "*"                   # sent from the users' browsers on the client's own domain
    r.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return r


@bp.route("/api/telemetry/<token>", methods=["POST", "OPTIONS"])
def api_telemetry(token):
    """open (no dashboard login): the secret token in the link is the site's key; bad token = 404"""
    import json
    from flask import make_response
    from web import telemetry
    if request.method == "OPTIONS":
        return _cors(make_response("", 204))
    sid = telemetry.site_of(token)
    if not sid:
        return _cors(make_response("", 404))
    raw = request.get_data(cache=False, as_text=True)[:telemetry.MAX_BYTES * 5]
    try:
        body = json.loads(raw)
    except Exception:
        return _cors(make_response("", 400))
    if isinstance(body, list):
        body = [x for x in body if len(json.dumps(x, ensure_ascii=False)) <= telemetry.MAX_BYTES]
    elif len(raw) > telemetry.MAX_BYTES:
        return _cors(make_response("", 413))
    telemetry.receive(sid, body)
    return _cors(make_response("", 204))


@bp.route("/api/monitor/connect")
@auth.login_required
def api_connect():
    """admin: each site's error-report link + the code for the NQ ERP developers"""
    from pathlib import Path
    from web import notify, telemetry
    base = (notify.load_config().get("dashboard_url") or request.url_root).rstrip("/")
    code = Path(__file__).resolve().parent.parent / "integrations" / "nq-erp" / "NqTelemetry.cs"
    return jsonify({"base": base, "local": "127.0.0.1" in base or "localhost" in base,
                    "code": code.read_text(encoding="utf-8") if code.exists() else "",
                    "sites": [{"id": p["id"], "name": p.get("name"), "kind": p.get("kind"), "link": f"{base}/api/telemetry/{telemetry.token_for(p['id'])}",
                               "inside": telemetry.site_summary(p["id"])} for p in monitor._sites({})]})


@bp.route("/api/monitor/connect/<site_id>/new", methods=["POST"])
@auth.login_required
def api_connect_new(site_id):
    """admin: a new link for the site (the old one stops — use when it leaked)"""
    from web import telemetry
    telemetry.token_for(site_id, new=True)
    return api_connect()


# ------------------------------------------------------------------ 🔬 من جوه الأنظمة: ZATCA, the database, screen usage (web/telemetry.py)
@bp.route("/inside")
@auth.login_required
def inside_page():
    return render_template("inside.html")


@bp.route("/api/inside")
@auth.login_required
def api_inside():
    from web import telemetry
    sites = [{"id": p["id"], "name": p.get("name"), "kind": p.get("kind")} for p in monitor._sites({})]
    sid = request.args.get("site") or next((s["id"] for s in sites if s["kind"] == "client"), sites[0]["id"] if sites else "")
    return jsonify({"sites": sites, "site": sid, "data": telemetry.inside(sid, int(request.args.get("days", 30))) if sid else None,
                    "backup_h": telemetry.BACKUP_H})


# ------------------------------------------------------------------ 🎓 the AI trainer (web/trainer.py)
@bp.route("/api/trainer/question", methods=["POST"])
def api_trainer_question():
    """open with the key: the trainer reports a client's question"""
    from web import trainer
    if not trainer.key_ok(request.args.get("key", "")):
        return jsonify({"ok": False}), 404
    try:
        trainer.add(request.get_json(silent=True) or {})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True})


@bp.route("/api/trainer/known")
def api_trainer_known():
    """open with the key: what's known to be broken, in client-safe words"""
    from web import trainer
    if not trainer.key_ok(request.args.get("key", "")):
        return jsonify({"ok": False}), 404
    return jsonify(trainer.known())


@bp.route("/api/inside/trainer")
@auth.login_required
def api_inside_trainer():
    from web import trainer
    return jsonify(trainer.summary(request.args.get("site", ""), int(request.args.get("days", 30))))


@bp.route("/api/inside/trainer-key", methods=["POST"])
@auth.login_required
def api_inside_trainer_key():
    from web import notify, trainer
    base = (notify.load_config().get("dashboard_url") or request.url_root).rstrip("/")
    k = trainer.key(new=bool((request.get_json(silent=True) or {}).get("new")))
    return jsonify({"question": f"{base}/api/trainer/question?key={k}", "known": f"{base}/api/trainer/known?key={k}"})
