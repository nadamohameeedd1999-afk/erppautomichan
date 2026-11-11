"""🆚 مقارنة التقارير — page + API (scenario, per-site choices, run on both sites, comparison, Word / PDF)."""
import io
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, send_file

from web import auth

bp = Blueprint("repcmp", __name__)
KEY = "repcmp_{}"


def _sites():
    from web import test_sites_helper as ts
    data = ts.load_all()
    return [{"id": p.get("id"), "name": p.get("name") or p.get("id"), "url": (p.get("base_url") or "").rstrip("/"), "kind": ts.site_kind(p)}
            for p in data.get("profiles", [])]


def _pair(sc, sites):
    a = next((s for s in sites if s["id"] == sc.get("a")), None) or next((s for s in sites if s["kind"] != "client"), None)
    b = next((s for s in sites if s["id"] == sc.get("b")), None) or next((s for s in sites if s["kind"] == "client"), None)
    return a, b


@bp.route("/report-compare")
@auth.login_required
def page():
    return render_template("report_compare.html")


@bp.route("/api/repcmp")
@auth.login_required
def api_state():
    from engine import report_compare as R
    sid = request.args.get("scenario") or "itemcard"
    sc = R.scenario(sid) or dict(R.DEFAULT)
    sites = _sites()
    a, b = _pair(sc, sites)
    snaps = {}
    for s in (a, b):
        if s:
            sn = R.load_snap(sid, s["url"]) or {}
            snaps[s["id"]] = {"status": sn.get("status"), "at": sn.get("at"), "lookups": sn.get("lookups") or {},
                              "chosen": (sc.get("sites") or {}).get(R.site_key(s["url"])) or {}, "chosen_names": sn.get("chosen_names") or {}}
    cmp = R.compare(sid, a["url"], b["url"]) if a and b else {"ready": False, "rows": []}
    return jsonify({"success": True, "scenarios": R.scenarios(), "scenario": sc, "sites": sites, "a": a, "b": b, "snaps": snaps,
                    "compare": {"ready": cmp["ready"], "rows": cmp["rows"], "diff_n": cmp.get("diff_n", 0),
                                "a_at": (cmp.get("a") or {}).get("at"), "b_at": (cmp.get("b") or {}).get("at")}})


@bp.route("/api/repcmp/save", methods=["POST"])
@auth.login_required
def api_save():
    from engine import report_compare as R
    d = request.get_json(silent=True) or {}
    sc = R.scenario(d.get("scenario") or "itemcard") or dict(R.DEFAULT)
    sites = {s["id"]: s for s in _sites()}
    for k in ("a", "b"):
        if d.get(k) in sites:
            sc[k] = d[k]
    if "date_from" in d:
        sc["date_from"] = str(d.get("date_from") or "")[:10]
    if d.get("report"):
        sc["report"] = "/" + str(d["report"]).strip().lstrip("/")
    for sid, vals in (d.get("choices") or {}).items():
        if sid in sites:
            sc.setdefault("sites", {})[R.site_key(sites[sid]["url"])] = {p: str(vals.get(p) or "") for p, _ in sc["choose"]}
    R.save_scenario(sc)
    return jsonify({"success": True, "scenario": sc})


@bp.route("/api/repcmp/run", methods=["POST"])
@auth.login_required
def api_run():
    from engine import checks as C, report_compare as R
    d = request.get_json(silent=True) or {}
    sc = R.scenario(d.get("scenario") or "itemcard") or dict(R.DEFAULT)
    a, b = _pair(sc, _sites())
    if not a or not b or a["id"] == b["id"]:
        return jsonify({"success": False, "error": "اختار موقعين مختلفين (اختبار + عميل)"}), 400
    saved = C.save({"key": KEY.format(sc["id"]), "type": "repcmp", "scenario": sc["id"], "name_ar": f"🆚 {sc['name']}"})
    from web.queue_manager import get_manager
    from web import sites_api
    out = {"success": True}
    out.update(sites_api.queue_on_sites(get_manager(), C.test_path_for(saved["key"]), saved["name_ar"], [a["id"], b["id"]], source="manual", front=True))
    return jsonify(out)


def _report_html(sid):
    from engine import report_compare as R
    from web import pdf_reports as P
    sc = R.scenario(sid) or dict(R.DEFAULT)
    a, b = _pair(sc, _sites())
    cmp = R.compare(sid, a["url"], b["url"]) if a and b else {"ready": False, "rows": []}
    A, B = cmp.get("a") or {}, cmp.get("b") or {}
    st = {"same": "✓ متطابق", "diff": "✗ مختلف", "both": "✗ مشكلة في الاتنين", "info": "للعلم"}
    body = []
    n = cmp.get("diff_n", 0)
    body.append(f"<div class='verdict {'bad' if n else 'ok'}'>{'❌ فيه ' + str(n) + ' اختلاف' if n else '✅ التقرير متطابق في الشكل والمنطق'}</div>" if cmp["ready"]
                else "<div class='verdict na'>⚪ لسه مفيش لقطة من الموقعين</div>")
    chosen = lambda s: " · ".join(f"{k}: {v}" for k, v in (s.get("chosen_names") or {}).items())
    body.append(P.table(["", a["name"] if a else "—", b["name"] if b else "—"], [["الموقع", a and a["url"], b and b["url"]], ["السيناريو", chosen(A), chosen(B)],
                                                                             ["وقت اللقطة", A.get("at"), B.get("at")]]))
    body.append("<h2>المقارنة</h2>")
    body.append(P.table(["البند", "بيقارن إيه", "الاختبار", "العميل", "النتيجة", "التفاصيل"],
                        [[r["item"], r["what"], r["a"], r["b"], P.Raw(f"<span class='{'ok' if r['status'] == 'same' else ('na' if r['status'] == 'info' else 'bad')}'>{st[r['status']]}</span>"), r["detail"]]
                         for r in cmp["rows"]], center=(2, 3, 4)))
    user = (auth.current_user() or {}).get("username", "")
    return P.page(f"مقارنة تقرير — {sc['name']}", "Report comparison — test vs client", user, "".join(body),
                  [("التقرير", sc["report"]), ("الاختبار", a and a["name"]), ("العميل", b and b["name"])])


@bp.route("/api/repcmp/export")
@auth.login_required
def api_export():
    sid = request.args.get("scenario") or "itemcard"
    html = _report_html(sid)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    if request.args.get("fmt") == "html":
        return html
    from utils.pdf import html_to_pdf
    return send_file(io.BytesIO(html_to_pdf(html)), as_attachment=True, download_name=f"Report_compare_{sid}_{stamp}.pdf", mimetype="application/pdf")
