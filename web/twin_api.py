"""🧬 التوأم الرقمي — page + API: analyse the ERP code (a local folder or an uploaded zip, + the test-database copy when the
database audit connection is set), the code-health dashboard, the screen map, import / export."""
import io
import json
import os
import shutil
import tempfile
import threading
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, send_file

from web import auth

bp = Blueprint("twin", __name__)
JOB = {"running": False, "log": [], "error": "", "started_at": "", "finished": "", "stop": False}


def _cfg_file():
    from config import paths
    return paths.SETTINGS_DIR / "code_twin.json"


def load_cfg():
    try:
        return json.loads(_cfg_file().read_text(encoding="utf-8"))
    except Exception:
        return {}


@bp.route("/twin")
@auth.login_required
def page():
    return render_template("twin.html")


def _brief(d):
    if not d:
        return None
    return {k: d.get(k) for k in ("at", "secs", "label", "counts", "findings", "modules", "fixed")} | {"screens_n": len(d.get("screens") or {})}


@bp.route("/api/twin")
@auth.login_required
def api_state():
    from engine import code_twin as T, db_audit as D
    c = load_cfg()
    return jsonify({"success": True, "cfg": {"path": c.get("path", ""), "label": c.get("label", "")}, "db": D.public(),
                    "job": {k: (JOB[k][-80:] if k == "log" else JOB[k]) for k in JOB}, "result": _brief(T.load())})


@bp.route("/api/twin/screens")
@auth.login_required
def api_screens():
    from engine import code_twin as T
    d = T.load() or {}
    q = (request.args.get("q") or "").strip().lower()
    mod = request.args.get("module") or ""
    only = request.args.get("issues") == "1"
    out = []
    for k, s in (d.get("screens") or {}).items():
        if mod and (s.get("module") or "مش مربوطة بموديول") != mod:
            continue
        if q and q not in (k + " " + (s.get("ar") or "") + " " + " ".join(s.get("tables") or [])[:2000]).lower():
            continue
        bad = sum(1 for c in s["calls"] if not c["ok"]) + len(s.get("broken_procs") or []) + len(s.get("issues") or [])
        if only and not bad:
            continue
        out.append({"key": k, "name": s["name"], "ar": s.get("ar", ""), "module": s.get("module", ""), "bad": bad, "procs": len(s["procs"]), "tables": len(s["tables"])})
    out.sort(key=lambda x: (-x["bad"], x["name"]))
    return jsonify({"success": True, "rows": out[:300], "total": len(out)})


@bp.route("/api/twin/screen/<key>")
@auth.login_required
def api_screen(key):
    from engine import code_twin as T
    d = T.load() or {}
    s = (d.get("screens") or {}).get(key.lower())
    if not s:
        return jsonify({"success": False, "error": "الشاشة مش موجودة في التحليل"}), 404
    issues = [f for f in d.get("findings") or [] if key.lower() in (f.get("screens") or [])]
    mine = []
    for f in issues:
        rows = [r for r in f.get("sample") or [] if str(r.get("الشاشة", "")).lower() == key.lower()] or f.get("sample", [])[:3]
        mine.append({"sev": f["sev"], "title": f["title"], "rows": rows[:6], "fix": f.get("fix", "")})
    return jsonify({"success": True, "screen": {**s, "key": key.lower()}, "issues": mine})


@bp.route("/api/twin/config", methods=["POST"])
@auth.login_required
def api_config():
    if not auth.is_admin():
        return jsonify({"success": False, "error": "الإعداد ده للأدمن بس"}), 403
    j = request.get_json(silent=True) or {}
    c = load_cfg()
    for k in ("path", "label"):
        if k in j:
            c[k] = str(j[k] or "").strip()[:400]
    _cfg_file().parent.mkdir(parents=True, exist_ok=True)
    _cfg_file().write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    return jsonify({"success": True})


def _start(root_getter, label, cleanup=None):
    from engine import code_twin as T, db_audit as D
    JOB.update({"running": True, "log": [], "error": "", "started_at": datetime.now().isoformat(timespec="seconds"), "finished": "", "stop": False})

    class Stopped(BaseException):
        pass

    def log(m):
        JOB["log"].append(f"{datetime.now():%H:%M:%S} {m}")
        if JOB.get("stop"):
            raise Stopped()

    def work():
        conn = None
        try:
            root = root_getter(log)
            if D.load_cfg().get("server"):
                try:
                    conn = D.connect()
                    log("🔌 اتوصل بنسخة قاعدة البيانات")
                except Exception as e:
                    log(f"⚠️ مقدرتش أتوصل بقاعدة البيانات — هحلل الكود لوحده ({str(e)[:120]})")
            else:
                log("ℹ️ مفيش اتصال بقاعدة البيانات (فحص قاعدة البيانات) — هحلل الكود لوحده")
            T.save(T.scan(root, conn=conn, log=log, label=label))
        except Stopped:
            JOB["error"] = "⏹️ اتوقف بطلبك"
        except Exception as e:
            JOB["error"] = str(e)[:400]
        finally:
            JOB["running"] = False
            JOB["finished"] = datetime.now().isoformat(timespec="seconds")
            try:
                conn and conn.close()
            except Exception:
                pass
            if cleanup:
                cleanup()
    threading.Thread(target=work, daemon=True).start()


@bp.route("/api/twin/run", methods=["POST"])
@auth.login_required
def api_run():
    from engine import code_twin as T
    if JOB["running"]:
        return jsonify({"success": False, "error": "فيه تحليل شغال دلوقتي"}), 409
    c = load_cfg()
    f = request.files.get("file")
    label = (request.form.get("label") if f else (request.get_json(silent=True) or {}).get("label")) or c.get("label") or ""
    if f:
        tmp = tempfile.mkdtemp(prefix="twin_")
        zp = os.path.join(tmp, "code.zip")
        f.save(zp)

        def get_root(log):
            log("📦 بفك الكود…")
            return T.unpack(zp, os.path.join(tmp, "src"))
        _start(get_root, label or f.filename, cleanup=lambda: shutil.rmtree(tmp, ignore_errors=True))
    else:
        path = c.get("path")
        if not path or not os.path.isdir(path):
            return jsonify({"success": False, "error": "حدد فولدر الكود (على الجهاز اللي الأداة شغالة عليه) أو ارفع ملف ZIP"}), 400
        _start(lambda log: T.find_root(path), label or os.path.basename(path.rstrip("/\\")))
    return jsonify({"success": True, "bg": "twin"})


@bp.route("/api/twin/import", methods=["POST"])
@auth.login_required
def api_import():
    from engine import code_twin as T
    f = request.files.get("file")
    try:
        d = json.loads((f.read() if f else request.get_data()).decode("utf-8-sig"))
        assert isinstance(d.get("findings"), list) and isinstance(d.get("screens"), dict)
    except Exception:
        return jsonify({"success": False, "error": "الملف مش نتيجة تحليل كود (JSON)"}), 400
    T.save(d)
    return jsonify({"success": True})


def _html():
    from engine import code_twin as T
    from web import pdf_reports as P
    d = T.load()
    if not d:
        return P.page("التوأم الرقمي", "Digital twin — code health", "", "<div class='verdict na'>لسه مفيش تحليل</div>")
    f = d["findings"]
    hi = sum(1 for x in f if x["sev"] == "عالية")
    c = d["counts"]
    body = [f"<div class='verdict {'bad' if hi else 'ok'}'>{'❌ ' + str(hi) + ' ملاحظة عالية' if hi else '✅ مفيش ملاحظات عالية'} · {len(f)} ملاحظة</div>",
            "<h2>الملخص</h2>",
            P.table(["#", "النوع", "الخطورة", "الملاحظة", "العدد", "التصليح"], [[i, x["area"], x["sev"], x["title"], x.get("count") or "—", x.get("fix") or "—"] for i, x in enumerate(f, 1)], center=(0, 1, 2, 4)),
            "<h2>حسب الموديول</h2>",
            P.table(["الموديول", "الشاشات", "المشاكل"], [[m["name"], m["screens"], m["issues"]] for m in d.get("modules") or []], center=(1, 2))]
    for i, x in enumerate(f, 1):
        if not x.get("sample"):
            continue
        cols = list(x["sample"][0].keys())
        body.append(f"<div class='case'><h2>{i}. {P.e(x['title'])}</h2><p class='small'>{P.e(x.get('detail'))}</p>"
                    + P.table(cols, [[r.get(k) for k in cols] for r in x["sample"][:40]]) + (f"<p><b>التصليح:</b> {P.e(x['fix'])}</p>" if x.get("fix") else "") + "</div>")
    user = (auth.current_user() or {}).get("username", "")
    return P.page("التوأم الرقمي — صحة الكود", "Digital twin — code health", user, "".join(body),
                  [("الكود", d.get("label") or "—"), ("وقت التحليل", d["at"]), ("الكنترولرات", c.get("controllers")), ("التقارير", c.get("reports")), ("الإجراءات", c.get("procs"))])


@bp.route("/api/twin/export")
@auth.login_required
def api_export():
    from engine import code_twin as T
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    fmt = request.args.get("fmt") or "pdf"
    if fmt == "json":
        return send_file(io.BytesIO(json.dumps(T.load() or {}, ensure_ascii=False, default=list).encode()), as_attachment=True,
                         download_name=f"Code_twin_{stamp}.json", mimetype="application/json")
    html = _html()
    if fmt == "html":
        return html
    from utils.pdf import html_to_pdf
    return send_file(io.BytesIO(html_to_pdf(html)), as_attachment=True, download_name=f"Code_twin_{stamp}.pdf", mimetype="application/pdf")
