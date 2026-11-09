"""
📘 Documents made from the runs themselves:
  • step guide      (ideas: Opkey Training Agent, Worksoft process documentation) — a passed run becomes a «how to do
                    it» guide: every field and button in order with the screenshots — material for training / the AI trainer
  • report approval (idea: Opkey audit trail / e-signature) — a reviewer approves an evidence report; it shows «approved
                    by … on …», and «changed after approval» if the run's data changes later
  • test summary    (idea: AT*SQA / ISTQB test summary report) — scope, results, coverage, defects by cause, residual
                    risks and a recommendation, for a period, in the approved report design
"""
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from config import paths
from web import auth, data_helper, insights, settings_helper

bp = Blueprint("docs", __name__)
APPROVALS = paths.STATE_DIR / "approvals.json"
_STEP = re.compile(r"\| (?:INFO|SUCCESS)\s*\| (?:[\w.]+:\w+:\d+ \| )?(.*)")


def _co():
    sc = settings_helper.load_site_config()
    return {"name": sc.get("company_name_ar") or "", "cr": sc.get("company_cr") or "", "vat": sc.get("company_vat") or "",
            "logo": sc.get("logo_filename") or ""}


def _user():
    u = auth.current_user() or {}
    return u.get("full_name") or u.get("username") or ""


def _summary(run_id):
    return next((s for s in data_helper.load_summaries() if s.get("run_id") == run_id), None)


# ── step guide ────────────────────────────────────────────────────────────────────────────────────────────────────
def guide_steps(log_lines):
    steps = []
    for line in log_lines:
        m = _STEP.search(line)
        if not m:
            continue
        t = m.group(1).strip()
        if t.startswith("▶ "):
            steps.append({"kind": "title", "text": t[2:].split(" (")[0]})
        elif t.startswith("✅ ") and " = " in t and "اتحفظ" not in t:
            label, val = t[2:].split(" = ", 1)
            steps.append({"kind": "field", "label": label.strip(), "value": val.strip()[:120]})
        elif t.startswith("قبل الحفظ: "):
            steps.append({"kind": "button", "label": t.split(": ", 1)[1].strip()})
        elif "اتحفظ وظهر في القايمة" in t or "الصفحة اتنقلت بعد الحفظ" in t:
            steps.append({"kind": "save"})
        elif t.startswith("🔖 رقم السند الجديد"):
            steps.append({"kind": "number", "value": t.split(":", 1)[1].split("(")[0].strip()})
    out, seen_save = [], False
    for s in steps:                                       # one «save» per screen, no repeated fields
        if s["kind"] == "save":
            if seen_save:
                continue
            seen_save = True
        if s["kind"] == "title":
            seen_save = False
        if out and s == out[-1]:
            continue
        out.append(s)
    return out


@bp.route("/reports/<run_id>/guide")
@auth.login_required
def guide(run_id):
    s = _summary(run_id)
    if not s:
        return redirect(url_for("reports"))
    log = [l["text"] for l in data_helper.read_run_log(run_id)]
    shots = [{"file": f, "label": data_helper.screenshot_label(f)} for f in data_helper.get_screenshots_for_run(run_id, s)
             if "FAILED_" not in f]
    return render_template("guide.html", report=s, steps=guide_steps(log), shots=shots, co=_co(), user=_user(),
                           printed=datetime.now().strftime("%Y-%m-%d %H:%M"), passed=insights.run_passed(s))


# ── approvals ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _hash(s):
    keep = {k: s.get(k) for k in ("run_id", "total", "passed", "failed", "errors", "tests", "exit_code")}
    return hashlib.sha256(json.dumps(keep, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def _approvals():
    try:
        return json.loads(APPROVALS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def approval_of(run_id, summary=None):
    a = _approvals().get(run_id)
    if a and summary is not None:
        a = {**a, "changed": a.get("hash") != _hash(summary)}
    return a


@bp.route("/api/reports/<run_id>/approve", methods=["POST"])
@auth.login_required
def approve(run_id):
    u = auth.current_user() or {}
    if u.get("role") == "viewer":
        return jsonify({"success": False, "error": "مشاهدة بس"}), 403
    s = _summary(run_id)
    if not s:
        return jsonify({"success": False, "error": "التشغيلة مش موجودة"}), 404
    d = _approvals()
    d[run_id] = {"by": u.get("full_name") or u.get("username"), "user": u.get("username"),
                 "at": datetime.now().strftime("%Y-%m-%d %H:%M"), "note": (request.get_json(silent=True) or {}).get("note", "")[:300],
                 "hash": _hash(s)}
    paths.STATE_DIR.mkdir(parents=True, exist_ok=True)
    APPROVALS.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        auth.audit("report_approved", run_id)
    except Exception:
        pass
    return jsonify({"success": True, "approval": d[run_id]})


# ── ISTQB-style test summary ─────────────────────────────────────────────────────────────────────────────────────
@bp.route("/reports/test-summary")
@auth.login_required
def test_summary():
    from web import explain
    days = max(1, min(365, int(request.args.get("days") or 30)))
    since = datetime.now() - timedelta(days=days)
    runs = [s for s in data_helper.load_summaries() if (insights.run_time(s) or datetime.min) >= since]
    by_test = defaultdict(list)
    for s in runs:
        by_test[s.get("test_name") or s.get("test_path") or "—"].append(s)
    tests = []
    for name, rs in by_test.items():
        rs.sort(key=lambda s: insights.run_time(s) or datetime.min)
        ok = sum(1 for s in rs if insights.run_passed(s))
        tests.append({"name": name, "runs": len(rs), "ok": ok, "pct": round(100 * ok / len(rs)), "last_ok": insights.run_passed(rs[-1]),
                      "sites": sorted({s.get("site_name") or "" for s in rs} - {""})})
    tests.sort(key=lambda t: (t["last_ok"], t["pct"]))
    causes, defects = Counter(), []
    for s in runs:
        if insights.run_passed(s):
            continue
        w = explain.for_run(insights.first_failure_message(s), []) or {}
        k = w.get("kind_label") or "غير مصنف"
        causes[k] += 1
        if len(defects) < 40:
            defects.append({"run": s.get("run_id"), "test": s.get("test_name"), "at": (s.get("started_at") or "")[:16].replace("T", " "),
                            "kind": k, "title": w.get("title") or (insights.first_failure_message(s) or "")[:140]})
    from engine import readiness
    ready = readiness.all_sites()
    open_fail = [t for t in tests if not t["last_ok"]]
    total = len(runs)
    ok_runs = sum(1 for s in runs if insights.run_passed(s))
    if any(r["verdict"] == "no" for r in ready) or len(open_fail) > max(2, len(tests) // 5):
        rec = ("no", "مش جاهز للتسليم — فيه مخاطر مفتوحة لازم تتقفل الأول")
    elif open_fail or any(r["verdict"] == "care" for r in ready):
        rec = ("care", "جاهز بحذر — فيه نقاط مفتوحة متابعة")
    else:
        rec = ("go", "جاهز — كل الاختبارات الأخيرة ناجحة والمخاطر مغطاة")
    return render_template("test_summary.html", days=days, since=since.strftime("%Y-%m-%d"), until=datetime.now().strftime("%Y-%m-%d"),
                           tests=tests, total=total, ok_runs=ok_runs, causes=causes.most_common(), defects=defects, ready=ready,
                           open_fail=open_fail, rec=rec, co=_co(), user=_user(), printed=datetime.now().strftime("%Y-%m-%d %H:%M"))
