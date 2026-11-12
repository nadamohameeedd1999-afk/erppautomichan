"""🆚 مقارنة التقارير — page + API: the report menus of both sites, per-report scenario (filters per site), run many reports on
both sites, the comparison of each report, one export (PDF / Word / Excel) with every difference."""
import io
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, send_file

from web import auth

bp = Blueprint("repcmp", __name__)
KEY = "repcmp_batch"
CATALOG_KEY = "repcmp_catalog"


def _sites():
    from web import test_sites_helper as ts
    data = ts.load_all()
    return [{"id": p.get("id"), "name": p.get("name") or p.get("id"), "url": (p.get("base_url") or "").rstrip("/"), "kind": ts.site_kind(p)}
            for p in data.get("profiles", [])]


def _pair(d, sites):
    a = next((s for s in sites if s["id"] == d.get("a")), None) or next((s for s in sites if s["kind"] != "client"), None)
    b = next((s for s in sites if s["id"] == d.get("b")), None) or next((s for s in sites if s["kind"] == "client" and (not a or s["id"] != a["id"])), None)
    return a, b


def pair_urls():
    """(test url, client url, client name) — used by the developer-support screen"""
    from engine import report_compare as R
    a, b = _pair(R.load_cfg(), _sites())
    return (a or {}).get("url", ""), (b or {}).get("url", ""), (b or {}).get("name", "")


@bp.route("/report-compare")
@auth.login_required
def page():
    return render_template("report_compare.html")


@bp.route("/api/repcmp")
@auth.login_required
def api_state():
    from engine import report_compare as R
    d = R.load_cfg()
    sites = _sites()
    a, b = _pair(d, sites)
    rows, meta = R.catalog_rows(a["url"], b["url"]) if a and b else ([], {})
    k = {"total": len(rows), "only_a": sum(1 for r in rows if r["in_a"] and r["in_b"] is False), "only_b": sum(1 for r in rows if r["in_b"] and r["in_a"] is False),
         "compared": sum(1 for r in rows if r["ready"]), "same": sum(1 for r in rows if r["ready"] and not r["diff_n"]),
         "diff": sum(1 for r in rows if r["ready"] and r["diff_n"]), "fail_b": sum(1 for r in rows if r["sb"] in ("error", "stuck", "noviewer")),
         "fail_a": sum(1 for r in rows if r["sa"] in ("error", "stuck", "noviewer")), "selected": sum(1 for r in rows if r["selected"])}
    return jsonify({"success": True, "sites": sites, "a": a, "b": b, "rows": rows, "meta": meta, "kpi": k,
                    "glob": {"date_from": d.get("date_from", ""), "date_to": d.get("date_to", ""), "auto_pick": d.get("auto_pick", True), "pdf": d.get("pdf", True)}})


@bp.route("/api/repcmp/report")
@auth.login_required
def api_report():
    from engine import report_compare as R
    path = R.norm_path(request.args.get("path") or R.ITEMCARD)
    d = R.load_cfg()
    a, b = _pair(d, _sites())
    rc = R.report_conf(path, d)
    snaps = {}
    for side, s in (("a", a), ("b", b)):
        if not s:
            continue
        sn = R.load_snap(path, s["url"]) or {}
        lk = sn.get("lookups") or {}
        snaps[side] = {"status": sn.get("status"), "at": sn.get("at"), "fault": sn.get("fault", ""), "chosen_names": sn.get("chosen_names") or {}, "auto": sn.get("auto") or {},
                       "params": [{**{k: p.get(k) for k in ("path", "type", "label", "multi", "def")}, "lookups": lk.get(p["path"]) or []}
                                  for p in sn.get("params") or [] if p.get("visible")],
                       "values": (rc.get("sites") or {}).get(R.site_key(s["url"])) or {}}
    cmp = R.compare(path, a["url"], b["url"]) if a and b else {"ready": False, "rows": []}
    name = rc.get("name") or next((r["name"] for c in (R.load_catalog(a["url"]) if a else {}, R.load_catalog(b["url"]) if b else {})
                                   for r in c.get("reports") or [] if r["path"].lower() == path.lower()), path)
    return jsonify({"success": True, "path": path, "name": name, "conf": {"date_from": rc.get("date_from", ""), "date_to": rc.get("date_to", "")}, "snaps": snaps,
                    "compare": {"ready": cmp["ready"], "rows": cmp["rows"], "diff_n": cmp.get("diff_n", 0), "warn_n": cmp.get("warn_n", 0)}})


@bp.route("/api/repcmp/save", methods=["POST"])
@auth.login_required
def api_save():
    from engine import report_compare as R
    j = request.get_json(silent=True) or {}
    d = R.load_cfg()
    sites = {s["id"]: s for s in _sites()}
    for k in ("a", "b"):
        if j.get(k) in sites:
            d[k] = j[k]
    for k in ("date_from", "date_to"):
        if k in j:
            d[k] = str(j.get(k) or "")[:10]
    for k in ("auto_pick", "pdf"):
        if k in j:
            d[k] = bool(j[k])
    if isinstance(j.get("selected"), list):
        d["selected"] = list(dict.fromkeys(R.norm_path(x) for x in j["selected"] if str(x).strip()))[:400]
    for p in j.get("select_add") or []:
        if R.norm_path(p) not in d["selected"]:
            d["selected"].append(R.norm_path(p))
    for p in j.get("select_remove") or []:
        d["selected"] = [x for x in d["selected"] if x.lower() != R.norm_path(p).lower()]
    rep = j.get("report")
    if rep and rep.get("path"):
        path = R.norm_path(rep["path"])
        rc = d["reports"].setdefault(path, {"sites": {}})
        for k in ("name", "group"):
            if rep.get(k):
                rc[k] = str(rep[k])[:200]
        for k in ("date_from", "date_to"):
            if k in rep:
                rc[k] = str(rep.get(k) or "")[:10]
        if rep.get("site") in sites and isinstance(rep.get("values"), dict):
            cur = rc.setdefault("sites", {}).setdefault(R.site_key(sites[rep["site"]]["url"]), {})
            for p, v in rep["values"].items():
                v = str(v if v is not None else "").strip()[:500]
                if v:
                    cur[str(p)[:80]] = v
                else:
                    cur.pop(str(p)[:80], None)
    R.save_cfg(d)
    return jsonify({"success": True})


@bp.route("/api/repcmp/run", methods=["POST"])
@auth.login_required
def api_run():
    from engine import checks as C, report_compare as R
    j = request.get_json(silent=True) or {}
    d = R.load_cfg()
    a, b = _pair(d, _sites())
    if not a or not b or a["id"] == b["id"]:
        return jsonify({"success": False, "error": "اختار موقعين مختلفين (اختبار + عميل)"}), 400
    reports = [R.norm_path(x) for x in (j.get("reports") or []) if str(x).strip()][:400]
    if j.get("catalog"):
        saved = C.save({"key": CATALOG_KEY, "type": "repcmp", "catalog": True, "reports": [], "name_ar": "🆚 قايمة التقارير"})
    else:
        if not reports:
            return jsonify({"success": False, "error": "اختار تقرير واحد على الأقل"}), 400
        saved = C.save({"key": KEY, "type": "repcmp", "reports": reports, "name_ar": f"🆚 مقارنة {len(reports)} تقرير"})
    from web.queue_manager import get_manager
    from web import sites_api
    out = {"success": True, "count_reports": len(reports)}
    out.update(sites_api.queue_on_sites(get_manager(), C.test_path_for(saved["key"]), saved["name_ar"], [a["id"], b["id"]], source="manual", front=True))
    return jsonify(out)


# ------------------------------------------------------------------ export
def _scope_rows(scope, path):
    from engine import report_compare as R
    d = R.load_cfg()
    a, b = _pair(d, _sites())
    if not a or not b:
        return a, b, [], {}
    rows, meta = R.catalog_rows(a["url"], b["url"])
    if scope == "one":
        rows = [r for r in rows if r["path"].lower() == R.norm_path(path).lower()]
    elif scope == "selected":
        rows = [r for r in rows if r["selected"]]
    elif scope == "diff":
        rows = [r for r in rows if r["ready"] and (r["diff_n"] or r["warn_n"])]
    else:
        rows = [r for r in rows if r["sa"] or r["sb"] or r["in_a"] != r["in_b"]]
    return a, b, rows, meta


ST = {"same": "✓ متطابق", "diff": "✗ مختلف", "both": "✗ مشكلة في الاتنين", "warn": "⚠ تنبيه", "info": "للعلم"}
VERD = lambda r: ("⚪ لسه ماتقارنش" if not r["ready"] else (f"❌ {r['diff_n']} اختلاف" if r["diff_n"] else ("⚠ تنبيهات بس" if r["warn_n"] else "✅ متطابق")))
WHERE = lambda r: "في الاتنين" if r["in_a"] and r["in_b"] else ("في الاختبار بس" if r["in_a"] else ("عند العميل بس" if r["in_b"] else "—"))


def _data(scope, path):
    from engine import report_compare as R
    a, b, rows, meta = _scope_rows(scope, path)
    details = []
    for r in rows:
        c = R.compare(r["path"], a["url"], b["url"])
        details.append((r, c))
    return a, b, rows, details


def _report_html(scope, path):
    from web import pdf_reports as P
    a, b, rows, details = _data(scope, path)
    body = []
    n_diff = sum(1 for r in rows if r["ready"] and r["diff_n"])
    body.append(f"<div class='verdict {'bad' if n_diff else 'ok'}'>{'❌ ' + str(n_diff) + ' تقرير فيه اختلافات من ' + str(len(rows)) if n_diff else '✅ مفيش اختلافات في التقارير دي'}</div>")
    body.append("<h2>الملخص</h2>")
    body.append(P.table(["#", "التقرير", "المجموعة", "في المنيو", "الاختبار", "العميل", "الاختلافات", "التنبيهات", "النتيجة"],
                        [[i, f"{r['name']}\n{r['path']}", r["group"], WHERE(r), _sst(r["sa"]), _sst(r["sb"]), r["diff_n"] or "—", r["warn_n"] or "—", VERD(r)]
                         for i, r in enumerate(rows, 1)], center=(0, 3, 4, 5, 6, 7, 8)))
    for r, c in details:
        if not c["rows"]:
            continue
        A, B = c.get("a") or {}, c.get("b") or {}
        body.append(f"<div class='case'><h2>{P.e(r['name'])} — <span dir='ltr'>{P.e(r['path'])}</span></h2>")
        body.append(f"<div class='verdict {'bad' if r['diff_n'] else 'ok'}'>{VERD(r)}</div>")
        chosen = lambda s: " · ".join(f"{k}: {v}" for k, v in (s.get("chosen_names") or {}).items()) or "الافتراضي"
        body.append(P.table(["", "الاختبار", "العميل"], [["الموقع", a["url"], b["url"]], ["السيناريو", chosen(A), chosen(B)], ["وقت اللقطة", A.get("at"), B.get("at")]]))
        body.append(P.table(["النوع", "البند", "بيقارن إيه", "الاختبار", "العميل", "النتيجة", "التفاصيل"],
                            [[x["cat"], x["item"], x["what"], x["a"], x["b"],
                              P.Raw(f"<span class='{'ok' if x['status'] == 'same' else ('na' if x['status'] in ('info', 'warn') else 'bad')}'>{ST[x['status']]}</span>"), x["detail"]]
                             for x in c["rows"]], center=(5,)))
        body.append("</div>")
    user = (auth.current_user() or {}).get("username", "")
    return P.page("تقرير مقارنة التقارير", "Reports comparison — test vs client", user, "".join(body),
                  [("موقع الاختبار", a and a["name"]), ("موقع العميل", b and b["name"]), ("عدد التقارير", len(rows)), ("فيها اختلافات", n_diff)])


def _sst(s):
    from engine import report_compare as R
    return R.ST_TXT.get(s, "—") if s else "—"


def _report_docx(scope, path):
    import tempfile
    from docx.shared import RGBColor
    from engine.docx_design import Report
    from engine.biz_report import company_name
    a, b, rows, details = _data(scope, path)
    user = (auth.current_user() or {}).get("username", "")
    rp = Report(company_name(), "تقرير مقارنة التقارير", "Reports comparison — test vs client", user)
    n_diff = sum(1 for r in rows if r["ready"] and r["diff_n"])
    teal, red, green = RGBColor(0x0F, 0x7C, 0x7A), RGBColor(0xC6, 0x28, 0x28), RGBColor(0x1E, 0x8E, 0x3E)
    col = {"same": green, "diff": red, "both": red, "warn": RGBColor(0xB2, 0x6A, 0x00), "info": RGBColor(0x6B, 0x7B, 0x7A)}
    rp.strip([("موقع الاختبار", a["name"] if a else "—"), ("موقع العميل", b["name"] if b else "—"), ("عدد التقارير", str(len(rows))), ("فيها اختلافات", str(n_diff))])
    rp.para("الملخص", size=12, bold=True, color=teal)
    rp.table([("#", 3), ("التقرير", 22), ("المجموعة", 12), ("في المنيو", 9), ("الاختبار", 10), ("العميل", 10), ("اختلافات", 7), ("تنبيهات", 7), ("النتيجة", 11)],
             [[str(i), f"{r['name']}\n{r['path']}", r["group"] or "—", WHERE(r), _sst(r["sa"]), _sst(r["sb"]), str(r["diff_n"] or "—"), str(r["warn_n"] or "—"), VERD(r)]
              for i, r in enumerate(rows, 1)], center=(0, 3, 4, 5, 6, 7, 8),
             colors=lambda ri, ci, v: (red if "❌" in v else green if "✅" in v else None) if ci == 8 else None)
    for r, c in details:
        if not c["rows"]:
            continue
        A, B = c.get("a") or {}, c.get("b") or {}
        rp.page_break()
        rp.para(f"{r['name']} — {r['path']}", size=12, bold=True, color=teal)
        rp.para(VERD(r), size=11, bold=True, color=red if r["diff_n"] else green)
        chosen = lambda s: " · ".join(f"{k}: {v}" for k, v in (s.get("chosen_names") or {}).items()) or "الافتراضي"
        rp.strip([("سيناريو الاختبار", chosen(A)), ("سيناريو العميل", chosen(B)), ("اللقطات", f"{A.get('at') or '—'} / {B.get('at') or '—'}")])
        sts = [x["status"] for x in c["rows"]]
        rp.table([("النوع", 9), ("البند", 14), ("الاختبار", 20), ("العميل", 20), ("النتيجة", 9), ("التفاصيل", 28)],
                 [[x["cat"], x["item"], str(x["a"] if x["a"] not in (None, "") else "—"), str(x["b"] if x["b"] not in (None, "") else "—"), ST[x["status"]], x["detail"] or "—"] for x in c["rows"]],
                 center=(4,), colors=lambda ri, ci, v: col[sts[ri]] if ci == 4 else None, bold_cols=(1,))
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        tmp = f.name
    rp.save(tmp)
    data = open(tmp, "rb").read()
    import os
    os.unlink(tmp)
    return data


def _report_xlsx(scope, path):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    a, b, rows, details = _data(scope, path)
    wb = Workbook()
    hdr = PatternFill("solid", fgColor="0F7C7A")
    line = Border(bottom=Side(style="thin", color="D5E2E1"))
    fill = {"same": "E6F4EA", "diff": "FDECEC", "both": "FDECEC", "warn": "FFF4E5", "info": "FFFFFF"}

    def sheet(ws, cols, data, widths, status_col=None):
        ws.sheet_view.rightToLeft = True
        ws.append(cols)
        for c in ws[1]:
            c.fill, c.font, c.alignment = hdr, Font(bold=True, color="FFFFFF"), Alignment(horizontal="center", vertical="center", wrap_text=True)
        for r in data:
            ws.append([x if x not in (None, "") else "—" for x in r[0]])
            for c in ws[ws.max_row]:
                c.border, c.alignment = line, Alignment(vertical="top", wrap_text=True)
                if r[1]:
                    c.fill = PatternFill("solid", fgColor=fill[r[1]])
        for i, w in enumerate(widths):
            ws.column_dimensions[chr(65 + i)].width = w
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    ws = wb.active
    ws.title = "الملخص"
    sheet(ws, ["التقرير", "اللينك", "المجموعة", "في المنيو", "الاختبار", "العميل", "اختلافات", "تنبيهات", "النتيجة", "لقطة الاختبار", "لقطة العميل"],
          [([r["name"], r["path"], r["group"], WHERE(r), _sst(r["sa"]), _sst(r["sb"]), r["diff_n"], r["warn_n"], VERD(r), r.get("at_a"), r.get("at_b")],
            ("diff" if r["diff_n"] else "warn" if r["warn_n"] else "same") if r["ready"] else None) for r in rows],
          [34, 34, 22, 14, 18, 18, 10, 10, 18, 16, 16])
    sheet(wb.create_sheet("التفاصيل"), ["التقرير", "النوع", "البند", "بيقارن إيه", "الاختبار", "العميل", "النتيجة", "التفاصيل"],
          [([r["name"], x["cat"], x["item"], x["what"], str(x["a"]), str(x["b"]), ST[x["status"]], x["detail"]], x["status"]) for r, c in details for x in c["rows"]],
          [30, 14, 24, 40, 30, 30, 14, 60])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@bp.route("/api/repcmp/export")
@auth.login_required
def api_export():
    scope, path, fmt = request.args.get("scope") or "all", request.args.get("path") or "", request.args.get("fmt") or "pdf"
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    name = f"Reports_compare_{stamp}"
    if fmt == "docx":
        return send_file(io.BytesIO(_report_docx(scope, path)), as_attachment=True, download_name=name + ".docx",
                         mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    if fmt == "xlsx":
        return send_file(io.BytesIO(_report_xlsx(scope, path)), as_attachment=True, download_name=name + ".xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    html = _report_html(scope, path)
    if fmt == "html":
        return html
    from utils.pdf import html_to_pdf
    return send_file(io.BytesIO(html_to_pdf(html)), as_attachment=True, download_name=name + ".pdf", mimetype="application/pdf")
