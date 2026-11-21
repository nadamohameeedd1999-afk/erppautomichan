"""💼 NQ Care — the admin page, the client status page (open, secret link), the monthly report and the offer sheet."""
from datetime import datetime

from flask import Blueprint, Response, abort, jsonify, render_template, request

from web import auth, care

bp = Blueprint("care", __name__)


def _user():
    u = auth.current_user() or {}
    return u.get("full_name") or u.get("username") or ""


def _pdf_or_page(page_html, pdf_name, view_url):
    from web.daily_report import html_to_pdf
    try:
        pdf = html_to_pdf(page_html)
    except Exception as e:
        from web.export_helper import pdf_unavailable
        return pdf_unavailable(view_url, e)
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": f'attachment; filename="{pdf_name}"'})


@bp.route("/care")
@auth.login_required
def page():
    return render_template("care.html")


@bp.route("/api/care")
@auth.login_required
def api_overview():
    return jsonify(care.overview())


@bp.route("/api/care/client/<site_id>", methods=["POST"])
@auth.login_required
def api_client(site_id):
    return jsonify({"ok": True, "client": care.save_client(site_id, request.get_json(silent=True) or {})})


@bp.route("/api/care/client/<site_id>/token", methods=["POST"])
@auth.login_required
def api_token(site_id):
    return jsonify({"ok": True, "token": care.new_token(site_id)})


@bp.route("/api/care/plans", methods=["POST"])
@auth.login_required
def api_plans():
    return jsonify({"ok": True, "plans": care.save_plans(request.get_json(silent=True) or {})["plans"]})


@bp.route("/api/care/notice", methods=["POST"])
@auth.login_required
def api_notice():
    b = request.get_json(silent=True) or {}
    if not str(b.get("title") or "").strip():
        return jsonify({"ok": False, "error": "اكتب عنوان الإعلان"}), 400
    return jsonify({"ok": True, "notice": care.add_notice(b.get("site") or "all", b["title"], b.get("start", ""), b.get("end", ""), b.get("kind", "maintenance"))})


@bp.route("/api/care/notice/<nid>/delete", methods=["POST"])
@auth.login_required
def api_notice_delete(nid):
    care.delete_notice(nid)
    return jsonify({"ok": True})


@bp.route("/api/care/send/<site_id>", methods=["POST"])
@auth.login_required
def api_send(site_id):
    b = request.get_json(silent=True) or {}
    month = b.get("month") or datetime.now().strftime("%Y-%m")
    try:
        ok, _ = care.send_report(site_id, month, b.get("to") or None, _user())
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:200]}), 500
    return jsonify({"ok": bool(ok), "error": "" if ok else "الإيميل مش متظبط في الإعدادات ▸ الإيميل، أو مفيش إيميل للعميل"})


def _month():
    m = request.args.get("month") or datetime.now().strftime("%Y-%m")
    try:
        datetime.strptime(m, "%Y-%m")
    except ValueError:
        abort(400)
    return m


@bp.route("/care/report")
@auth.login_required
def report_view():
    return care.html_monthly(request.args.get("site", ""), _month(), _user())


@bp.route("/care/report.pdf")
@auth.login_required
def report_pdf():
    site, month = request.args.get("site", ""), _month()
    return _pdf_or_page(care.html_monthly(site, month, _user(), for_pdf=True), f"nq_care_{month}.pdf", f"/care/report?site={site}&month={month}")


@bp.route("/care/offer")
@auth.login_required
def offer_view():
    return care.html_offer(_user())


@bp.route("/care/offer.pdf")
@auth.login_required
def offer_pdf():
    return _pdf_or_page(care.html_offer(_user(), for_pdf=True), "nq_care_plans.pdf", "/care/offer")


# ------------------------------------------------------------------ the client's own page: no dashboard login, the secret link is the key
@bp.route("/status/<token>")
def status_page(token):
    sid = care.site_of(token)
    if not sid:
        abort(404)
    from web.daily_report import _company
    return render_template("status.html", token=token, company=_company())


@bp.route("/api/client-status/<token>")      # not /api/status/<id>: that one is the test runner's (routes_runs.task_status)
def status_api(token):
    sid = care.site_of(token)
    if not sid:
        abort(404)
    r = jsonify(care.status(sid))
    r.headers["Cache-Control"] = "no-store"
    return r
