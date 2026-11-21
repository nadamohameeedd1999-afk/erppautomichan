"""❤️ صحة العملاء — the page, the morning summary (preview / send now) and the weekly report (view / PDF / send now)."""
from flask import Blueprint, jsonify, render_template, request

from web import auth, clients_health as H

bp = Blueprint("clients_health", __name__)


def _user():
    u = auth.current_user() or {}
    return u.get("full_name") or u.get("username") or ""


@bp.route("/clients")
@auth.login_required
def page():
    return render_template("clients_health.html")


@bp.route("/api/clients")
@auth.login_required
def api_scores():
    c = H.load_cfg()
    return jsonify({"clients": H.all_scores(), "config": {k: v for k, v in c.items() if k != "sent"}, "week": H.WEEK_AR})


@bp.route("/api/clients/settings", methods=["POST"])
@auth.login_required
def api_settings():
    c = H.save_cfg(request.get_json(silent=True) or {})
    return jsonify({"ok": True, "config": {k: v for k, v in c.items() if k != "sent"}})


@bp.route("/api/clients/morning", methods=["GET", "POST"])
@auth.login_required
def api_morning():
    """GET = the text as it would go out now; POST = send it now"""
    text = H.morning_text()
    if request.method == "POST":
        from web import monitor
        return jsonify({"ok": True, "sent": monitor.broadcast(text), "text": text})
    return jsonify({"text": text})


@bp.route("/clients/weekly")
@auth.login_required
def weekly_view():
    return H.html_weekly(_user())


@bp.route("/clients/weekly.pdf")
@auth.login_required
def weekly_pdf():
    from web.care_api import _pdf_or_page
    return _pdf_or_page(H.html_weekly(_user(), for_pdf=True), "client_health_weekly.pdf", "/clients/weekly")


@bp.route("/api/clients/weekly/send", methods=["POST"])
@auth.login_required
def api_weekly_send():
    try:
        ok, _ = H.send_weekly()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:200]}), 500
    return jsonify({"ok": bool(ok), "error": "" if ok else "الإيميل مش متظبط في الإعدادات ▸ الإيميل"})


@bp.route("/api/clients/month-end", methods=["GET", "POST"])
@auth.login_required
def api_month_end():
    """🗓️ the month-end load test: GET = settings, POST = save (admin)"""
    from web import month_end
    if request.method == "POST":
        if (auth.current_user() or {}).get("role") != "admin":
            return jsonify({"ok": False, "error": "للأدمن بس"}), 403
        return jsonify({"ok": True, "config": month_end.save_cfg(request.get_json(silent=True) or {})})
    return jsonify({"config": month_end.load_cfg()})


@bp.route("/api/clients/month-end/run", methods=["POST"])
@auth.login_required
def api_month_end_run():
    from web import month_end
    if (auth.current_user() or {}).get("role") != "admin":
        return jsonify({"ok": False, "error": "للأدمن بس"}), 403
    n = month_end.run_now()
    return jsonify({"ok": bool(n), "count": n, "error": "" if n else "مفيش مواقع اختبار"})
