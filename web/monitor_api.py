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
