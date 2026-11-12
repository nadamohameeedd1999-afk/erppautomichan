"""🔬 أشعة النظام — page + API: the latest X-ray of each site, run on one site or more, compare two sites, screenshots, PDF."""
import io
from datetime import datetime

from flask import Blueprint, abort, jsonify, render_template, request, send_file

from web import auth

bp = Blueprint("xray", __name__)
KEY = "xray_scan"


def _sites():
    from web.repcmp_api import _sites as s
    return s()


@bp.route("/xray")
@auth.login_required
def page():
    return render_template("xray.html")


def _summary(d):
    if not d:
        return None
    f = d.get("findings") or []
    return {"at": d.get("at"), "secs": d.get("secs"), "menu": len(d.get("menu") or []), "links": d.get("links_n"), "pages": len(d.get("pages") or {}),
            "high": sum(1 for x in f if x["sev"] == "عالية"), "mid": sum(1 for x in f if x["sev"] == "متوسطة"),
            "low": sum(1 for x in f if x["sev"] == "منخفضة"), "info": sum(1 for x in f if x["sev"] == "للعلم"),
            "new": sum(1 for x in f if x.get("new")), "fixed": len(d.get("fixed") or []),
            "changed": sum(1 for s in d.get("shots") or [] if (s.get("diff") or 0) >= 8)}


@bp.route("/api/xray")
@auth.login_required
def api_state():
    from engine import xray as X
    sites = _sites()
    for s in sites:
        s["xray"] = _summary(X.load(s["url"]))
    sid = request.args.get("site") or next((s["id"] for s in sites if s["xray"]), sites[0]["id"] if sites else "")
    cur = next((s for s in sites if s["id"] == sid), None)
    d = X.load(cur["url"]) if cur else None
    cmp_id = request.args.get("vs") or ""
    other = next((s for s in sites if s["id"] == cmp_id), None)
    cmp_rows = X.compare_sites(d or {}, X.load(other["url"]) or {}) if d and other and X.load(other["url"]) else []
    return jsonify({"success": True, "sites": sites, "site": cur, "data": d, "compare": cmp_rows})


@bp.route("/api/xray/run", methods=["POST"])
@auth.login_required
def api_run():
    from engine import checks as C
    j = request.get_json(silent=True) or {}
    ids = [s["id"] for s in _sites() if s["id"] in (j.get("sites") or [])]
    if not ids:
        return jsonify({"success": False, "error": "اختار موقع واحد على الأقل"}), 400
    saved = C.save({"key": KEY, "type": "xray", "name_ar": "🔬 أشعة النظام", "pages": j.get("pages", 80), "shots": j.get("shots", True),
                    "shots_n": j.get("shots_n", 12), "slow": j.get("slow", True)})
    from web.queue_manager import get_manager
    from web import sites_api
    out = {"success": True}
    out.update(sites_api.queue_on_sites(get_manager(), C.test_path_for(saved["key"]), saved["name_ar"], ids, source="manual", front=True))
    return jsonify(out)


@bp.route("/api/xray/shot")
@auth.login_required
def api_shot():
    from engine import xray as X
    import re
    site = next((s for s in _sites() if s["id"] == request.args.get("site")), None)
    fn = re.sub(r"[^a-z0-9_]", "", request.args.get("f") or "")
    if not site or not fn:
        abort(404)
    f = X.shots_dir(site["url"]) / f"{fn}.png"
    if not f.exists():
        abort(404)
    return send_file(f, mimetype="image/png")


def _html(sid, vs=""):
    from engine import xray as X
    from web import pdf_reports as P
    sites = _sites()
    s = next((x for x in sites if x["id"] == sid), None)
    d = X.load(s["url"]) if s else None
    if not d:
        return P.page("أشعة النظام", "System X-ray", "", "<div class='verdict na'>لسه مفيش فحص للموقع ده</div>")
    sm = _summary(d)
    body = [f"<div class='verdict {'bad' if sm['high'] or sm['mid'] else 'ok'}'>"
            + (f"❌ {sm['high']} ملاحظة عالية · {sm['mid']} متوسطة" if sm['high'] or sm['mid'] else "✅ مفيش ملاحظات عالية أو متوسطة") + "</div>"]
    body.append("<h2>الملاحظات</h2>")
    body.append(P.table(["#", "النوع", "الخطورة", "الملاحظة", "فين", "التصليح"],
                        [[i, f["area"], f["sev"] + (" 🆕" if f.get("new") else ""), f["title"], f.get("where", ""), f.get("fix", "")] for i, f in enumerate(d["findings"], 1)], center=(0, 1, 2)))
    if d.get("libs"):
        body.append("<h2>المكتبات اللي النظام بيحملها</h2>")
        body.append(P.table(["المكتبة", "النسخة"], [[k, v] for k, v in d["libs"].items()], center=(1,)))
    if d.get("shots"):
        body.append("<h2>صور الشاشات مقابل آخر مرة</h2>")
        body.append(P.table(["الشاشة", "اللينك", "نسبة التغيير", "اسكرول أفقي"],
                            [[x["name"], x["path"], "أول مرة" if x.get("diff") is None else f"{x['diff']}%", f"{x['hscroll']}px" if x.get("hscroll", 0) > 20 else "—"] for x in d["shots"]], center=(2, 3)))
    if d.get("slow"):
        body.append("<h2>السرعة على نت ضعيف (3G)</h2>")
        body.append(P.table(["الشاشة", "اللينك", "الوقت"], [[x["name"], x["path"], f"{x['sec']} ث"] for x in d["slow"]], center=(2,)))
    if d.get("fixed"):
        body.append("<h2>اتصلح من آخر فحص</h2>")
        body.append(P.table(["النوع", "الملاحظة"], [[x["area"], x["title"]] for x in d["fixed"]]))
    o = next((x for x in sites if x["id"] == vs), None)
    if o and X.load(o["url"]):
        body.append(f"<h2>مقارنة مع {P.e(o['name'])}</h2>")
        body.append(P.table(["البند", s["name"], o["name"], "النتيجة", "التفاصيل"],
                            [[r["item"], r["a"], r["b"], {"same": "✓ متطابق", "diff": "✗ مختلف", "warn": "⚠ تنبيه"}[r["status"]], r["detail"]] for r in X.compare_sites(d, X.load(o["url"]))], center=(3,)))
    user = (auth.current_user() or {}).get("username", "")
    return P.page("أشعة النظام", "System X-ray", user, "".join(body),
                  [("الموقع", s["name"]), ("وقت الفحص", d["at"]), ("شاشات المنيو", sm["menu"]), ("صفحات اتقرت", sm["pages"])])


@bp.route("/api/xray/export")
@auth.login_required
def api_export():
    html = _html(request.args.get("site") or "", request.args.get("vs") or "")
    if request.args.get("fmt") == "html":
        return html
    from utils.pdf import html_to_pdf
    return send_file(io.BytesIO(html_to_pdf(html)), as_attachment=True, download_name=f"System_xray_{datetime.now():%Y%m%d_%H%M}.pdf", mimetype="application/pdf")
