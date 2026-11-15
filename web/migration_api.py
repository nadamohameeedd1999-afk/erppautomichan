"""📥 التأكد من نقل الأرصدة الافتتاحية — page + API: two Excel files → columns found → row-by-row comparison → PDF / Excel."""
import io
import json
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, send_file

from web import auth

bp = Blueprint("migration", __name__)


@bp.route("/migration")
@auth.login_required
def page():
    return render_template("migration.html")


@bp.route("/api/migration")
@auth.login_required
def api_list():
    from engine import migration as M
    return jsonify({"success": True, "runs": M.all_runs(), "kinds": M.KINDS, "cols": M.COL_AR})


def _maps():
    out = {}
    for k in ("map_src", "map_erp"):
        try:
            out[k] = json.loads(request.form.get(k) or "null")
        except Exception:
            out[k] = None
    return out


@bp.route("/api/migration/preview", methods=["POST"])
@auth.login_required
def api_preview():
    from engine import migration as M
    out = {}
    mp = _maps()
    for side in ("src", "erp"):
        f = request.files.get(side)
        if not f:
            continue
        try:
            t = M.table(f.read(), f.filename, mp.get("map_" + side))
            out[side] = {"headers": t["headers"], "mapping": t["mapping"], "header_row": t["header_row"], "n": len(t["rows"]), "sample": t["rows"][:5]}
        except Exception as e:
            out[side] = {"error": str(e)[:300]}
    return jsonify({"success": True, **out})


@bp.route("/api/migration/run", methods=["POST"])
@auth.login_required
def api_run():
    from engine import migration as M
    a, b = request.files.get("src"), request.files.get("erp")
    if not a or not b:
        return jsonify({"success": False, "error": "ارفع الملفين: النظام القديم و NQ ERP"}), 400
    mp = _maps()
    kind = request.form.get("kind") if request.form.get("kind") in M.KINDS else "accounts"
    try:
        tol = max(0.0, float(request.form.get("tol") or 0.01))
        src = M.table(a.read(), a.filename, mp.get("map_src"))
        erp = M.table(b.read(), b.filename, mp.get("map_erp"))
        res = M.compare(src, erp, tol, kind)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)[:300]}), 400
    res.update({"at": datetime.now().strftime("%Y-%m-%d %H:%M"), "kind": kind, "tol": tol, "client": (request.form.get("client") or "")[:120],
                "src_file": a.filename, "erp_file": b.filename, "by": (auth.current_user() or {}).get("username", "")})
    M.save(res)
    return jsonify({"success": True, "id": res["id"]})


@bp.route("/api/migration/<rid>")
@auth.login_required
def api_one(rid):
    from engine import migration as M
    d = M.load(rid)
    if not d:
        return jsonify({"success": False, "error": "مش موجود"}), 404
    return jsonify({"success": True, "run": d})


@bp.route("/api/migration/<rid>/export")
@auth.login_required
def api_export(rid):
    from engine import migration as M
    d = M.load(rid)
    if not d:
        return jsonify({"success": False}), 404
    name = f"Migration_{d.get('kind')}_{rid}"
    if request.args.get("fmt") == "xlsx":
        return send_file(io.BytesIO(M.report_xlsx(d)), as_attachment=True, download_name=name + ".xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    html = M.report_html(d, (auth.current_user() or {}).get("username", ""))
    if request.args.get("fmt") == "html":
        return html
    from utils.pdf import html_to_pdf
    return send_file(io.BytesIO(html_to_pdf(html)), as_attachment=True, download_name=name + ".pdf", mimetype="application/pdf")
