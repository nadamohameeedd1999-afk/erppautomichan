"""🤝 العرض للعميل — the presenter page, the demo site's day, the leave-behind PDF, and the AI sales employee's feed."""
from flask import Blueprint, abort, jsonify, render_template, request

from web import auth, sales

bp = Blueprint("sales", __name__)


def _user():
    u = auth.current_user() or {}
    return u.get("full_name") or u.get("username") or ""


@bp.route("/sales")
@auth.login_required
def page():
    return render_template("sales.html")


@bp.route("/api/sales")
@auth.login_required
def api_overview():
    return jsonify(sales.overview())


@bp.route("/api/sales/tour/<sector>")
@auth.login_required
def api_tour(sector):
    if sector not in sales.SECTORS:
        abort(404)
    return jsonify({"sector": sales.load()["sectors"][sector], "steps": sales.tour_links(sector)})


@bp.route("/api/sales/start", methods=["POST"])
@auth.login_required
def api_start():
    why = sales.start_day()
    return jsonify({"ok": not why, "error": why})


@bp.route("/api/sales/settings", methods=["POST"])
@auth.login_required
def api_settings():
    return jsonify({"ok": True, "config": sales.save(request.get_json(silent=True) or {})})


@bp.route("/api/sales/key", methods=["POST"])
@auth.login_required
def api_feed_link():
    from web import notify
    base = (notify.load_config().get("dashboard_url") or request.url_root).rstrip("/")
    key = sales.feed_key(new=bool((request.get_json(silent=True) or {}).get("new")))
    return jsonify({"link": f"{base}/api/sales/feed?key={key}"})


@bp.route("/sales/leave")
@auth.login_required
def leave_view():
    return sales.html_leave(request.args.get("sector", "trading"), request.args.get("client", ""), _user())


@bp.route("/sales/leave.pdf")
@auth.login_required
def leave_pdf():
    from web.care_api import _pdf_or_page
    sec, client = request.args.get("sector", "trading"), request.args.get("client", "")
    return _pdf_or_page(sales.html_leave(sec, client, _user(), for_pdf=True), f"nq_erp_{sec}.pdf", "/sales/leave?" + request.query_string.decode())


@bp.route("/api/sales/feed")
def api_feed():
    """open with the key (for n8n / the AI sales employee): no dashboard login"""
    if not sales.key_ok(request.args.get("key", "")):
        abort(404)
    return jsonify(sales.feed())
