"""
🚦 Release readiness (ideas: Opkey «Release Advisor» readiness score, Tosca / Worksoft go / no-go reporting,
everyone's CI/CD release gate)

One number out of 100 for a site, from what the tool already knows, and a verdict:
  40  risk coverage        screens that open, weighted by importance (engine/risk.py)
  20  accounts             the trial balance is balanced and the tree adds up
  15  speed                no screen slower than 5 s with its data
  15  tests                pass rate of this site's runs in the last 24 h
  10  changes              no field became required since the snapshot before the update
Verdict: ≥ 90 ✅ ينفع ينزل · 75–89 ⚠️ ينزل بحذر · < 75 ⛔ متنشرش — and ⛔ whatever the score if a critical screen is broken
or the accounts don't balance.
"""
import json
from datetime import datetime, timedelta

from config import paths


def sonar_gate():
    """🔍 SonarQube quality gate of the ERP's own code (idea: SonarSource quality gates) — optional:
    SONAR_URL + SONAR_PROJECT (+ SONAR_TOKEN) variables. -> {"status": OK|WARN|ERROR, "failed": [...]} or None"""
    import os
    url, proj = (os.getenv("SONAR_URL") or "").rstrip("/"), os.getenv("SONAR_PROJECT") or ""
    if not url or not proj:
        return None
    import base64
    import urllib.parse
    import urllib.request
    req = urllib.request.Request(f"{url}/api/qualitygates/project_status?projectKey={urllib.parse.quote(proj)}")
    tok = os.getenv("SONAR_TOKEN") or ""
    if tok:
        req.add_header("Authorization", "Basic " + base64.b64encode(f"{tok}:".encode()).decode())
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            ps = json.loads(r.read().decode()).get("projectStatus") or {}
    except Exception as e:
        return {"status": "?", "failed": [f"مقدرتش أوصل لـ SonarQube: {str(e)[:120]}"]}
    names = {"new_reliability_rating": "الاعتمادية", "new_security_rating": "الأمان", "new_maintainability_rating": "قابلية الصيانة",
             "new_coverage": "تغطية الكود بالاختبارات", "new_duplicated_lines_density": "التكرار", "new_security_hotspots_reviewed": "نقاط الأمان"}
    failed = [f"{names.get(c.get('metricKey'), c.get('metricKey'))}: {c.get('actualValue')} (المطلوب {c.get('comparator')} {c.get('errorThreshold')})"
              for c in ps.get("conditions") or [] if c.get("status") == "ERROR"]
    return {"status": ps.get("status") or "?", "failed": failed}


def _health_files():
    return sorted(paths.STATE_DIR.glob("health_*.json"), key=lambda f: -f.stat().st_mtime)


def for_state(d, site_name=""):
    from engine import risk
    names, mods = d.get("names") or {}, d.get("modules") or {}
    pths = d.get("paths") or list(names)
    broken = set(d.get("broken") or {})
    cov = d.get("risk") or risk.coverage([(p, names.get(p, p), mods.get(p, "")) for p in pths], broken)
    man = risk._manual()
    crit = [p for p in broken if risk.level(risk.weight(p, names.get(p, p), mods.get(p, ""), man)) == "حرج"]
    parts, notes = [], []

    pct = cov.get("pct")
    parts.append(("تغطية المخاطر", 40, 40 * (pct or 0) / 100, f"{pct}%" if pct is not None else "ما اتفحصتش"))

    key = d.get("_file", "").replace("health_", "books_")
    books = None
    try:
        books = json.loads((paths.STATE_DIR / key).read_text(encoding="utf-8")) if key else None
    except Exception:
        pass
    if books is None:
        parts.append(("الحسابات", 20, 10, "ما اتفحصتش (نص الدرجة)"))
    else:
        zero = any("فيه حركة" in str((r.get("cells") or ["", ""])[1]) for r in books.get("rows") or [])
        parts.append(("الحسابات", 20, 20 if books.get("ok") else (10 if zero else 0),
                      "متزنة" if books.get("ok") else ("مفيش قيود في الفترة" if zero else "مش متزنة")))
        if not books.get("ok") and not zero:
            notes.append("⛔ ميزان المراجعة مش متزن")

    ss = d.get("speed_stats") or {}
    if ss.get("measured"):
        slow = ss.get("load_over5") or 0
        parts.append(("السرعة", 15, max(0, 15 - 3 * slow), f"{slow} شاشة أبطأ من 5 ث" if slow else "كل الشاشات أقل من 5 ث"))
    else:
        parts.append(("السرعة", 15, 7.5, "ما اتقاستش (نص الدرجة)"))

    since = datetime.now() - timedelta(hours=24)
    ok = tot = 0
    try:
        from web import data_helper, insights
        for s in data_helper.load_summaries(limit=400):
            t = insights.run_time(s)
            if t and t >= since and (not site_name or (s.get("site_name") or "") in ("", site_name)):
                tot += 1
                ok += 1 if insights.run_passed(s) else 0
    except Exception:
        pass
    parts.append(("الاختبارات (24 ساعة)", 15, 15 * ok / tot if tot else 7.5, f"{ok} من {tot} نجحوا" if tot else "مفيش تشغيلات (نص الدرجة)"))

    req = [c for c in d.get("changes") or [] if "بقى إجباري" in c.get("what", "") or "مش بيفتح" in c.get("what", "")]
    parts.append(("التغييرات", 10, 0 if req else 10, f"{len(req)} تغيير مؤثر عن اللقطة" if req else "مفيش تغيير مؤثر"))

    sq = sonar_gate()
    if sq is not None:
        st = sq["status"]
        parts.append(("جودة كود الـ ERP (SonarQube)", 10, 10 if st == "OK" else (5 if st in ("WARN", "?") else 0),
                      "بوابة الجودة ناجحة" if st == "OK" else ("؛ ".join(sq["failed"][:4]) or st)))
        if st == "ERROR":
            notes.append("⛔ بوابة جودة الكود في SonarQube فاشلة: " + "؛ ".join(sq["failed"][:3]))
    score = round(100 * sum(p[2] for p in parts) / sum(p[1] for p in parts))
    if crit:
        notes.insert(0, f"⛔ {len(crit)} شاشة حرجة بايظة: " + "، ".join(names.get(p, p) for p in crit[:6]))
    blocked = bool(crit) or any(n.startswith("⛔") for n in notes)
    verdict = ("no", "⛔ متنشرش") if blocked or score < 75 else (("go", "✅ ينفع ينزل") if score >= 90 else ("care", "⚠️ ينزل بحذر"))
    return {"score": score, "verdict": verdict[0], "verdict_text": verdict[1], "notes": notes,
            "parts": [{"name": n, "max": m, "got": round(g, 1), "text": t} for n, m, g, t in parts],
            "site": d.get("base_url"), "site_name": site_name, "at": d.get("at"), "critical": crit}


def all_sites():
    out = []
    try:
        from web import test_sites_helper as ts
        profs = ts.load_all().get("profiles", [])
    except Exception:
        profs = []
    for f in _health_files():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        d["_file"] = f.name
        name = next((p["name"] for p in profs if p.get("base_url", "").rstrip("/") == (d.get("base_url") or "").rstrip("/")), "")
        out.append(for_state(d, name))
    return out
