"""🎯 أثر التغيير — page + API: GitHub compare or two code ZIPs → affected screens / reports / procedures → run their tests."""
import io
import json
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, send_file

from web import auth

bp = Blueprint("impact", __name__)


def _twin():
    try:
        from engine import code_twin as T
        return T.load()
    except Exception:
        return None


@bp.route("/impact")
@auth.login_required
def page():
    return render_template("impact.html")


@bp.route("/api/impact")
@auth.login_required
def api_state():
    from engine import impact as I
    from web.repcmp_api import _sites
    d = I.load()
    tw = _twin()
    return jsonify({"success": True, "cfg": I.public_cfg(), "result": d, "tests": I.tests_for(d) if d else [], "sites": _sites(),
                    "twin": {"at": (tw or {}).get("at"), "screens": len((tw or {}).get("screens") or {})}})


@bp.route("/api/impact/config", methods=["POST"])
@auth.login_required
def api_config():
    from engine import impact as I
    if not auth.is_admin():
        return jsonify({"success": False, "error": "الإعداد ده للأدمن بس"}), 403
    return jsonify({"success": True, "cfg": I.save_cfg(request.get_json(silent=True) or {})})


def _finish(files, meta, label):
    from engine import impact as I
    tw = _twin()
    if not tw:
        return jsonify({"success": False, "error": "شغّل «🧬 التوأم الرقمي» مرة الأول — هو اللي بيعرف كل ملف تبع أنهي شاشة"}), 400
    if not files:
        return jsonify({"success": False, "error": "مفيش أي ملف كود اتغير بين النسختين"}), 400
    d = I.analyse(files, tw, label, meta)
    I.save(d)
    return jsonify({"success": True, "counts": d["counts"]})


@bp.route("/api/impact/github", methods=["POST"])
@auth.login_required
def api_github():
    from engine import impact as I
    j = request.get_json(silent=True) or {}
    c = I.save_cfg({k: j[k] for k in ("repo", "base", "head") if k in j}) if auth.is_admin() else I.public_cfg()
    raw = I.load_cfg()
    repo, base, head = j.get("repo") or c["repo"], j.get("base") or c["base"], j.get("head") or c["head"]
    if not (repo and base and head and "/" in repo):
        return jsonify({"success": False, "error": "اكتب الريبو (owner/repo) والنسخة القديمة والجديدة (فرع / tag / commit)"}), 400
    try:
        files, meta = I.from_github(repo, base, head, raw.get("token", ""))
    except Exception as e:
        return jsonify({"success": False, "error": str(e)[:300]}), 400
    return _finish(files, meta, f"{repo}: {base} ← {head}")


@bp.route("/api/impact/zips", methods=["POST"])
@auth.login_required
def api_zips():
    from engine import impact as I
    a, b = request.files.get("old"), request.files.get("new")
    if not a or not b:
        return jsonify({"success": False, "error": "ارفع النسختين: القديمة والجديدة (ZIP)"}), 400
    try:
        files, meta = I.from_zips(a.read(), b.read())
    except Exception as e:
        return jsonify({"success": False, "error": f"مقدرتش أقرا الملفات: {e}"[:300]}), 400
    return _finish(files, meta, f"{a.filename} ← {b.filename}")


@bp.route("/api/impact/run", methods=["POST"])
@auth.login_required
def api_run():
    from engine import checks as C
    from engine import impact as I
    from web.queue_manager import get_manager
    from web import sites_api
    from web.repcmp_api import _sites
    j = request.get_json(silent=True) or {}
    site = next((s for s in _sites() if s["id"] == j.get("site")), None)
    if not site:
        return jsonify({"success": False, "error": "اختار الموقع"}), 400
    d = I.load() or {}
    names = {t["screen"]: t["name"] for t in I.tests_for(d)}
    qm, ids = get_manager(), []
    if j.get("health"):
        from web.checks_api import _health_cfg
        h = _health_cfg()
        C.save({**C.public(h), "key": h["key"], "type": "health"})
        ids += sites_api.queue_on_sites(qm, C.test_path_for(h["key"]), "🎯 أثر التغيير: صحة النظام", [site["id"]], source="impact")["task_ids"]
    for s in [x for x in j.get("screens") or [] if x in names][:40]:
        saved = C.save({"key": I.check_key(s), "type": "auto", "name_ar": f"🎯 متأثرة: {names[s]}", "screen": s, "ways": C.CLASSIC_WAYS})
        ids += sites_api.queue_on_sites(qm, C.test_path_for(saved["key"]), saved["name_ar"], [site["id"]], source="impact")["task_ids"]
    if not ids:
        return jsonify({"success": False, "error": "اختار اختبار واحد على الأقل"}), 400
    warn = "⚠️ الموقع «نظام عميل» (قراءة بس): الاختبار الآلي بيضيف ويعدّل — هيتوقف قبل الحفظ. شغّله على موقع اختبار." if site["kind"] == "client" else ""
    return jsonify({"success": True, "task_ids": ids, "count": len(ids), "warn": warn})


def _html(d, user):
    from web import pdf_reports as P
    c = d["counts"]
    body = [f"<div class='verdict {'bad' if c['high'] or c['global'] else 'ok'}'>{c['files']} ملف اتغير · {c['screens']} شاشة متأثرة ({c['high']} تأثير عالي) · "
            f"{c['reports']} تقرير · {c['procs']} إجراء مخزن</div>"]
    if d.get("global"):
        body.append("<p><b>⚠️ ملفات عامة اتغيرت — بتأثر على كل الشاشات:</b> " + P.e("، ".join(d["global"][:10])) + "</p>")
    body.append("<h2>الشاشات المتأثرة</h2>" + P.table(["#", "الشاشة", "الموديول", "التأثير", "الدرجة", "ليه"],
                [[i, (s.get("ar") or s["name"]), s.get("module") or "—", s["level"], s["score"], P.Raw("<br>".join(P.e(w) for w in s["why"][:6]))]
                 for i, s in enumerate(d["screens"][:300], 1)], center=(0, 3, 4)))
    if d.get("reports"):
        body.append("<h2>التقارير المتأثرة</h2>" + P.table(["التقرير", "الرابط", "الملفات"], [[r["name"], r["path"], "، ".join(r["files"][:3])] for r in d["reports"]]))
    if d.get("procs"):
        body.append("<h2>الإجراءات المخزنة اللي اتغيرت</h2>" + P.table(["الإجراء", "بيتنادي من", "في"],
                    [[p["name"], "، ".join(p["screens"][:8]) or "—", "، ".join(p["files"][:2])] for p in d["procs"]]))
    body.append("<h2>الملفات</h2>" + P.table(["الملف", "النوع", "الحالة", "+", "−", "الشاشات"],
                [[f["path"], f.get("kind_ar", ""), f["status"], f["add"], f["del"], "، ".join(f.get("screens") or []) or "—"] for f in d["files"][:500]], center=(2, 3, 4)))
    return P.page("أثر التغيير", "Change impact analysis", user, "".join(body),
                  [("المقارنة", d.get("label") or "—"), ("وقت التحليل", d["at"]), ("خريطة الكود من", d.get("twin_at") or "—")])


@bp.route("/api/impact/export")
@auth.login_required
def api_export():
    from engine import impact as I
    d = I.load()
    if not d:
        return jsonify({"success": False, "error": "لسه مفيش تحليل"}), 400
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    if request.args.get("fmt") == "json":
        return send_file(io.BytesIO(json.dumps(d, ensure_ascii=False).encode()), as_attachment=True, download_name=f"Impact_{stamp}.json", mimetype="application/json")
    html = _html(d, (auth.current_user() or {}).get("username", ""))
    if request.args.get("fmt") == "html":
        return html
    from utils.pdf import html_to_pdf
    return send_file(io.BytesIO(html_to_pdf(html)), as_attachment=True, download_name=f"Impact_{stamp}.pdf", mimetype="application/pdf")
