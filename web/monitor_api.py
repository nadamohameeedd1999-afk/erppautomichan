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
    return jsonify({**monitor.summary(), "busy": monitor._busy["on"]})


@bp.route("/api/monitor/run", methods=["POST"])
@auth.login_required
def api_run():
    if not monitor._busy["on"]:
        threading.Thread(target=monitor.run_once, kwargs={"force": True}, name="monitor-now", daemon=True).start()
    return jsonify({"ok": True})


@bp.route("/api/monitor/settings", methods=["POST"])
@auth.login_required
def api_settings():
    return jsonify({"ok": True, "config": monitor.save_config(request.get_json(silent=True) or {})})
