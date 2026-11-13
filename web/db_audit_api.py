"""🗄️ فحص قاعدة البيانات — page + API: the connection (a restored copy of the TEST database), run in the background,
import a result made elsewhere, findings, the screen ↔ table ↔ procedure map, PDF / Word."""
import io
import json
import threading
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, send_file

from web import auth

bp = Blueprint("dbaudit", __name__)
_job = {"running": False, "log": [], "error": "", "started": "", "started_at": "", "finished": "", "stop": False}


@bp.route("/db-audit")
@auth.login_required
def page():
    return render_template("db_audit.html")


def _brief(d):
    if not d:
        return None
    f = d.get("findings") or []
    return {"at": d.get("at"), "secs": d.get("secs"), "label": d.get("label"), "info": d.get("info"), "sections": d.get("sections"),
            "fixed": d.get("fixed") or [], "findings": f, "map_n": {"pages": len((d.get("map") or {}).get("pages") or []), "tables": len((d.get("map") or {}).get("tables") or {})}}


@bp.route("/api/dbaudit")
@auth.login_required
def api_state():
    from engine import db_audit as D
    return jsonify({"success": True, "cfg": D.public(), "job": {k: (_job[k][-60:] if k == "log" else _job[k]) for k in _job}, "result": _brief(D.load())})


@bp.route("/api/dbaudit/config", methods=["POST"])
@auth.login_required
def api_config():
    from engine import db_audit as D
    if not auth.is_admin():
        return jsonify({"success": False, "error": "الإعداد ده للأدمن بس"}), 403
    return jsonify({"success": True, "cfg": D.save_cfg(request.get_json(silent=True) or {})})


@bp.route("/api/dbaudit/test", methods=["POST"])
@auth.login_required
def api_test():
    from engine import db_audit as D
    try:
        c = D.connect()
        db = D.DB(c)
        n = db.one("SELECT COUNT(*) FROM sys.tables")
        c.close()
        return jsonify({"success": True, "msg": f"اتوصلت — {n} جدول"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)[:300]}), 400


@bp.route("/api/dbaudit/run", methods=["POST"])
@auth.login_required
def api_run():
    from engine import db_audit as D
    if _job["running"]:
        return jsonify({"success": False, "error": "فيه فحص شغال دلوقتي"}), 409
    _job.update({"running": True, "log": [], "error": "", "started": datetime.now().strftime("%H:%M"),
                 "started_at": datetime.now().isoformat(timespec="seconds"), "finished": "", "stop": False})

    class Stopped(BaseException):
        pass

    def log(m):
        _job["log"].append(f"{datetime.now():%H:%M:%S} {m}")
        if _job.get("stop"):
            raise Stopped()

    def work():
        try:
            conn = D.connect()
            conn.autocommit(True)
            D.run(conn, log=log, label=D.load_cfg().get("label") or "", conn_factory=D.connect_timeout)
        except Stopped:
            _job["error"] = "⏹️ اتوقف بطلبك"
        except Exception as e:
            _job["error"] = str(e)[:400]
        finally:
            _job["running"] = False
            _job["finished"] = datetime.now().isoformat(timespec="seconds")
    threading.Thread(target=work, daemon=True).start()
    return jsonify({"success": True, "bg": "dbaudit"})


@bp.route("/api/dbaudit/import", methods=["POST"])
@auth.login_required
def api_import():
    from engine import db_audit as D
    f = request.files.get("file")
    try:
        d = json.loads((f.read() if f else request.get_data()).decode("utf-8-sig"))
        assert isinstance(d.get("findings"), list) and d.get("info")
    except Exception:
        return jsonify({"success": False, "error": "الملف مش نتيجة فحص قاعدة بيانات (JSON)"}), 400
    D.save_result(d)
    return jsonify({"success": True})


@bp.route("/api/dbaudit/map")
@auth.login_required
def api_map():
    from engine import db_audit as D
    d = D.load() or {}
    mp = d.get("map") or {}
    q = (request.args.get("q") or "").strip().lower()
    if not q:
        return jsonify({"success": True, "rows": []})
    tables = mp.get("tables") or {}
    rows = []
    for p in mp.get("pages") or []:
        if q in " ".join(str(p.get(k) or "") for k in ("ar", "en", "table", "controller")).lower():
            t = tables.get(p.get("table") or "", {})
            rows.append({**p, "read": t.get("read", [])[:60], "write": t.get("write", [])[:60]})
        if len(rows) >= 30:
            break
    if len(rows) < 30:
        seen = {r.get("table") for r in rows}
        for name, t in tables.items():
            if q in name.lower() and name not in seen:
                rows.append({"ar": "", "table": name, "controller": "", "read": t.get("read", [])[:60], "write": t.get("write", [])[:60]})
            if len(rows) >= 30:
                break
    return jsonify({"success": True, "rows": rows})


def _html():
    from engine import db_audit as D
    from web import pdf_reports as P
    d = D.load()
    if not d:
        return P.page("فحص قاعدة البيانات", "Database audit", "", "<div class='verdict na'>لسه مفيش فحص</div>")
    f = d["findings"]
    hi = sum(1 for x in f if x["sev"] == "عالية")
    body = [f"<div class='verdict {'bad' if hi else 'ok'}'>{'❌ ' + str(hi) + ' ملاحظة عالية' if hi else '✅ مفيش ملاحظات عالية'} · {len(f)} ملاحظة إجمالي</div>",
            "<h2>الملخص</h2>",
            P.table(["#", "النوع", "الخطورة", "الملاحظة", "العدد", "التصليح"], [[i, x["area"], x["sev"], x["title"], x.get("count") or "—", x.get("fix") or "—"] for i, x in enumerate(f, 1)], center=(0, 1, 2, 4))]
    for i, x in enumerate(f, 1):
        if not x.get("sample"):
            continue
        cols = list(x["sample"][0].keys())
        body.append(f"<div class='case'><h2>{i}. {P.e(x['title'])}</h2><p class='small'>{P.e(x.get('detail'))}</p>"
                    + P.table(cols, [[r.get(c) for c in cols] for r in x["sample"]]) + (f"<p><b>التصليح:</b> {P.e(x['fix'])}</p>" if x.get("fix") else "") + "</div>")
    user = (auth.current_user() or {}).get("username", "")
    inf = d["info"]
    return P.page("فحص قاعدة البيانات", "Database audit", user, "".join(body),
                  [("القاعدة", d.get("label") or inf.get("db")), ("وقت الفحص", d["at"]), ("الجداول", inf.get("tables")), ("الإجراءات المخزنة", inf.get("procs"))])


def _docx():
    import tempfile, os
    from docx.shared import RGBColor
    from engine import db_audit as D
    from engine.docx_design import Report
    from engine.biz_report import company_name
    d = D.load() or {"findings": [], "info": {}, "at": ""}
    user = (auth.current_user() or {}).get("username", "")
    rp = Report(company_name(), "فحص قاعدة البيانات", "Database audit", user)
    inf = d["info"]
    rp.strip([("القاعدة", d.get("label") or inf.get("db") or "—"), ("وقت الفحص", d.get("at") or "—"), ("الجداول", str(inf.get("tables", "—"))), ("الإجراءات", str(inf.get("procs", "—")))])
    red, amber, teal = RGBColor(0xC6, 0x28, 0x28), RGBColor(0xB2, 0x6A, 0x00), RGBColor(0x0F, 0x7C, 0x7A)
    col = {"عالية": red, "متوسطة": amber}
    f = d["findings"]
    rp.table([("#", 3), ("النوع", 8), ("الخطورة", 7), ("الملاحظة", 45), ("العدد", 7), ("التصليح", 30)],
             [[str(i), x["area"], x["sev"], x["title"], str(x.get("count") or "—"), x.get("fix") or "—"] for i, x in enumerate(f, 1)],
             center=(0, 1, 2, 4), colors=lambda ri, ci, v: col.get(v) if ci == 2 else None)
    for i, x in enumerate(f, 1):
        if not x.get("sample"):
            continue
        rp.page_break()
        rp.para(f"{i}. {x['title']}", size=12, bold=True, color=teal)
        if x.get("detail"):
            rp.para(x["detail"])
        cols = list(x["sample"][0].keys())
        rp.table([(c, 1) for c in cols], [[str(r.get(c, "")) for c in cols] for r in x["sample"]], size=8)
        if x.get("fix"):
            rp.para("التصليح: " + x["fix"], bold=True)
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as t:
        tmp = t.name
    rp.save(tmp)
    data = open(tmp, "rb").read()
    os.unlink(tmp)
    return data


@bp.route("/api/dbaudit/export")
@auth.login_required
def api_export():
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    fmt = request.args.get("fmt") or "pdf"
    if fmt == "json":
        from engine import db_audit as D
        return send_file(io.BytesIO(json.dumps(D.load() or {}, ensure_ascii=False, default=str).encode()), as_attachment=True,
                         download_name=f"DB_audit_{stamp}.json", mimetype="application/json")
    if fmt == "docx":
        return send_file(io.BytesIO(_docx()), as_attachment=True, download_name=f"DB_audit_{stamp}.docx",
                         mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    html = _html()
    if fmt == "html":
        return html
    from utils.pdf import html_to_pdf
    return send_file(io.BytesIO(html_to_pdf(html)), as_attachment=True, download_name=f"DB_audit_{stamp}.pdf", mimetype="application/pdf")
