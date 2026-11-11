"""
Advanced tests (اختبارات متقدمة) — dashboard routes.

/checks                         page (cycles, report checks, speed)
/auto-test                      page: the automatic full test of a screen (add / edit / delete / print, every way)
/api/checks                     GET list / POST save {config}
/api/checks/<key>               GET / DELETE
/api/checks/try                 POST {config} -> background job (python -m engine.cli check), poll /api/screens/jobs/<id>
/api/checks/<key>/run           POST -> the queue (like any other test)
/api/checks/<key>/accept        POST report check: the last numbers become the reference
/api/checks/cycle-template/<t>  GET a ready cycle, matched to the saved screens
/api/checks/options             GET what the editors pick from (saved tests, catalog screens)
/api/perf/history               GET timings per screen (for the chart)
"""
import json
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request

from web import auth

bp = Blueprint("checks", __name__)


def _C():
    from engine import checks
    return checks


def _last_results():
    from web import insights
    out = {}
    for r in insights.all_runs():
        k = r["key"]
        if k not in out:
            out[k] = {"passed": r["passed"], "time": r["time"].strftime("%Y-%m-%d %H:%M"), "run_id": r["run_id"],
                      "message": (r["message"] or "").split("\n")[0][:160]}
    return out


@bp.route("/checks")
@auth.login_required
def checks_page():
    C = _C()
    return render_template("checks.html", types=C.TYPES, templates={k: {"name": v["name"], "icon": v["icon"],
                           "slots": [s[0] for s in v["slots"]]} for k, v in C.CYCLE_TEMPLATES.items()})


@bp.route("/api/checks")
@auth.login_required
def api_list():
    C = _C()
    last = _last_results()
    items = []
    for c in C.list_all():
        x = C.public(c)
        x["test_path"] = C.test_path_for(c["key"])
        x["last"] = last.get(c["key"])
        if c.get("type") == "report":
            from engine.check_runner import load_snapshot
            s = load_snapshot(c["key"])
            x["snapshot"] = {"values": s.get("values"), "at": s.get("at"), "pending": s.get("pending")}
        items.append(x)
    return jsonify({"success": True, "checks": items})


@bp.route("/api/checks", methods=["POST"])
@auth.login_required
def api_save():
    C = _C()
    d = request.get_json(silent=True) or {}
    cfg = d.get("config") or d
    try:
        saved = C.save(cfg)
    except C.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    try:
        auth.audit("check_save", f"{saved['type']}:{saved['key']}")
    except Exception:
        pass
    return jsonify({"success": True, "config": C.public(saved), "test_path": C.test_path_for(saved["key"])})


@bp.route("/api/checks/<key>")
@auth.login_required
def api_get(key):
    C = _C()
    try:
        return jsonify({"success": True, "config": C.public(C.load(key))})
    except C.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 404


@bp.route("/api/checks/<key>", methods=["DELETE"])
@auth.login_required
def api_delete(key):
    C = _C()
    if not C.KEY_RE.match(key or ""):
        return jsonify({"success": False, "error": "مفتاح غلط"}), 400
    return jsonify({"success": C.delete(key)})


@bp.route("/api/checks/try", methods=["POST"])
@auth.login_required
def api_try():
    """run the (unsaved) config now in the background and show the result here"""
    C = _C()
    from web.screens_api import _start_job, JOBS_DIR
    d = request.get_json(silent=True) or {}
    cfg = dict(d.get("config") or {})
    try:
        cfg = C.normalize(cfg)
    except C.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = JOBS_DIR / f"check_{cfg['key']}_{uuid.uuid4().hex[:6]}.json"
    tmp.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    job_id, err = _start_job("check", ["check", "--config-file", str(tmp)], {"timeout": 1800})
    if err:
        return jsonify({"success": False, "error": err}), 409
    return jsonify({"success": True, "job_id": job_id})


@bp.route("/api/checks/<key>/run", methods=["POST"])
@auth.login_required
def api_run(key):
    C = _C()
    try:
        cfg = C.load(key)
    except C.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    from web.queue_manager import get_manager
    from web import sites_api
    d = request.get_json(silent=True) or {}
    out = sites_api.queue_on_sites(get_manager(), C.test_path_for(key), f"{C.TYPES[cfg['type']][0]} {cfg['name_ar']}",
                                   d.get("sites"), source="manual")
    return jsonify({"success": True, **out})


@bp.route("/api/checks/<key>/accept", methods=["POST"])
@auth.login_required
def api_accept(key):
    from engine.check_runner import accept_snapshot
    return jsonify({"success": accept_snapshot(key)})


@bp.route("/api/checks/cycle-template/<name>")
@auth.login_required
def api_cycle_template(name):
    C = _C()
    try:
        return jsonify({"success": True, **C.suggest_cycle(name)})
    except C.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 404


@bp.route("/api/checks/options")
@auth.login_required
def api_options():
    C = _C()
    from config.screens_catalog import all_pages
    pages = [{"key": k, "name": p.get("name_ar") or k, "url": p.get("url", ""), "module": p.get("module_name") or p.get("module_key", "")}
             for k, p in all_pages().items() if p.get("url")]
    return jsonify({"success": True, "tests": C.runnable_tests(), "pages": pages})


@bp.route("/api/perf/history")
@auth.login_required
def api_perf_history():
    from engine.check_runner import load_perf
    data = load_perf()
    sites = []
    for site, urls in data.items():
        rows = []
        for url, pts in urls.items():
            if not pts:
                continue
            ts = [p["t"] for p in pts]
            rows.append({"url": url, "name": pts[-1].get("name") or url, "last": ts[-1], "avg": round(sum(ts) / len(ts), 2),
                         "max": max(ts), "count": len(ts), "points": [{"t": p["t"], "at": p["at"]} for p in pts[-30:]]})
        rows.sort(key=lambda r: -r["last"])
        sites.append({"site": site, "rows": rows})
    return jsonify({"success": True, "sites": sites, "now": datetime.now().isoformat(timespec="seconds")})


# ======================================================== الاختبار الآلي الشامل (any screen of the system)
def auto_key(screen_key):
    import re
    return ("auto_" + re.sub(r"[^a-z0-9_]", "_", screen_key.lower()))[:90]


@bp.route("/auto-test")
@auth.login_required
def auto_page():
    C = _C()
    from engine.auto_test import SCENARIOS
    return render_template("auto_test.html", ways=C.AUTO_WAYS, scenarios=SCENARIOS)


@bp.route("/api/auto-test/screens")
@auth.login_required
def api_auto_screens():
    """every screen of the project + its automatic test (if saved) + the last result"""
    C = _C()
    from engine.auto_test import all_screens
    last = _last_results()
    autos = {c["screen"]: c for c in C.list_all() if c.get("type") == "auto" and not c.get("error")}
    out = []
    for s in all_screens():
        a = autos.get(s["key"])
        out.append({**s, "auto": C.public(a) if a else None, "last": last.get(a["key"]) if a else None})
    return jsonify({"success": True, "screens": out})


def _auto_cfg(screen, name, d, old=None):
    C = _C()
    return {"key": (old or {}).get("key") or auto_key(screen), "type": "auto", "name_ar": f"🤖 {name}", "screen": screen,
            "ways": d.get("ways") or list(C.AUTO_WAYS), "scenarios": d.get("scenarios") or ["first"],
            "fields_mode": d.get("fields_mode") or "all", "expect_error": d.get("expect_error", ""),
            "edit_button": d.get("edit_button", ""), "print_button": d.get("print_button", ""), "delete_button": d.get("delete_button", "")}


@bp.route("/api/auto-test/save", methods=["POST"])
@auth.login_required
def api_auto_save():
    """save the automatic test of the chosen screens (same options for all) and optionally queue them"""
    C = _C()
    from engine.auto_test import all_screens
    from web.queue_manager import get_manager
    from web import sites_api
    d = request.get_json(silent=True) or {}
    names = {s["key"]: s["name"] for s in all_screens()}
    keys = [k for k in d.get("screens") or [] if k in names]
    if d.get("all"):
        keys = list(names)
    if not keys:
        return jsonify({"success": False, "error": "اختاري شاشة واحدة على الأقل"}), 400
    autos = {c["screen"]: c for c in C.list_all() if c.get("type") == "auto" and not c.get("error")}
    saved, ids = [], []
    for k in keys:
        try:
            c = C.save(_auto_cfg(k, names[k], d, autos.get(k)))
        except C.ConfigError as e:
            return jsonify({"success": False, "error": f"{names[k]}: {e}"}), 400
        saved.append(c["key"])
        if d.get("run"):
            ids += sites_api.queue_on_sites(get_manager(), C.test_path_for(c["key"]), c["name_ar"], d.get("sites"),
                                            source="manual")["task_ids"]
    return jsonify({"success": True, "saved": saved, "queued": len(ids)})


# ======================================================== 📚 مكتبة الاختبارات الجاهزة
@bp.route("/api/test-library")
@auth.login_required
def api_test_library():
    C = _C()
    from engine import test_library as L, health
    autos = {c["screen"]: c for c in C.list_all() if c.get("type") == "auto" and not c.get("error")}
    st = health.load_state()
    menu = st.get("paths") or []
    return jsonify({"success": True, "items": L.items(autos, _last_results(), menu)})


@bp.route("/api/test-library/apply", methods=["POST"])
@auth.login_required
def api_test_library_apply():
    """add the chosen library screens + save their automatic test (optionally queue them)"""
    C = _C()
    from engine import test_library as L
    from web.queue_manager import get_manager
    from web import sites_api
    d = request.get_json(silent=True) or {}
    keys = [x[0] for x in L.LIBRARY] if d.get("all") else [k for k in d.get("keys") or [] if any(x[0] == k for x in L.LIBRARY)]
    if not keys:
        return jsonify({"success": False, "error": "اختاري شاشة واحدة على الأقل"}), 400
    autos = {c["screen"]: c for c in C.list_all() if c.get("type") == "auto" and not c.get("error")}
    saved, ids = [], []
    for k in keys:
        sk, it = L.ensure_screen(k)
        try:
            c = C.save(_auto_cfg(sk, it[1], {"ways": it[5]}, autos.get(sk)))
        except C.ConfigError as e:
            return jsonify({"success": False, "error": f"{it[1]}: {e}"}), 400
        saved.append(c["key"])
        if d.get("run"):
            ids += sites_api.queue_on_sites(get_manager(), C.test_path_for(c["key"]), c["name_ar"], d.get("sites"), source="manual")["task_ids"]
    return jsonify({"success": True, "saved": saved, "queued": len(ids)})


@bp.route("/api/auto-test/try", methods=["POST"])
@auth.login_required
def api_auto_try():
    """one screen, now, with the result shown on the page"""
    from engine.auto_test import all_screens
    d = request.get_json(silent=True) or {}
    s = next((x for x in all_screens() if x["key"] == d.get("screen")), None)
    if not s:
        return jsonify({"success": False, "error": "الشاشة مش موجودة"}), 404
    C = _C()
    from web.screens_api import _start_job, JOBS_DIR
    try:
        cfg = C.normalize(_auto_cfg(s["key"], s["name"], d))
    except C.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = JOBS_DIR / f"check_{cfg['key']}_{uuid.uuid4().hex[:6]}.json"
    tmp.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    job_id, err = _start_job("check", ["check", "--config-file", str(tmp)], {"timeout": 3600})
    if err:
        return jsonify({"success": False, "error": err}), 409
    return jsonify({"success": True, "job_id": job_id})


# ======================================================== 🩺 صحة النظام (every screen of the menu, broken ones + alerts)
HEALTH_KEY = "system_health"
FULL_KEY = "system_health_full"


def _health_cfg():
    C = _C()
    try:
        return C.load(HEALTH_KEY)
    except C.ConfigError:
        return C.normalize({"key": HEALTH_KEY, "type": "health", "name_ar": "🩺 صحة النظام — كل الشاشات"})


@bp.route("/health")
@auth.login_required
def health_page():
    return render_template("health.html")


def _with_risk(rows):
    """add the risk weight / level to screens and sort heaviest first (Tosca-style)"""
    from engine import risk
    man = risk._manual()
    for r in rows:
        r["w"] = risk.weight(r["path"], r.get("name", ""), r.get("module", ""), man)
        r["level"] = risk.level(r["w"])
    rows.sort(key=lambda r: (-r["w"], r.get("module") or "", r.get("name") or ""))
    return rows


def _risk_of(d):
    """risk coverage for a saved check (computed again for checks saved before this feature)"""
    if d.get("risk"):
        return d["risk"]
    from engine import risk
    names, mods = d.get("names") or {}, d.get("modules") or {}
    return risk.coverage([(p, names.get(p, p), mods.get(p, "")) for p in (d.get("paths") or list(names))], set(d.get("broken") or {}))


def _all_screens(d):
    """every screen the check opened -> [{path, name, module, sec, rows, kind, ok}] (by module, then name)"""
    names, mods, times, rows_of = d.get("names") or {}, d.get("modules") or {}, d.get("times") or {}, d.get("rows_of") or {}
    broken = d.get("broken") or {}
    out = []
    for p in (d.get("paths") or list(names)):
        r = rows_of.get(p) or {}
        nm = names.get(p, p)
        kind = "add" if ("➕" in nm or "/addedit" in p.lower()) else ("report" if r.get("report") else "list")
        out.append({"path": p, "name": nm.replace("➕ إضافة — ", ""), "module": mods.get(p, "") or (broken.get(p) or {}).get("module", ""),
                    "sec": round((times.get(p) or 0) / 1000, 2) or None, "rows": r.get("rows") or 0, "kind": kind, "ok": p not in broken,
                    "why": (broken.get(p) or {}).get("why", "")})
    from engine import risk
    man = risk._manual()
    for x in out:
        x["w"] = risk.weight(x["path"], x["name"], x["module"], man)
        x["level"] = risk.level(x["w"])
    out.sort(key=lambda x: (x["module"] or "ي", x["kind"] == "add", x["name"]))
    return out


@bp.route("/api/health")
@auth.login_required
def api_health():
    from engine import health
    states = []
    for f in sorted(health.STATE.glob("health_*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        since = d.get("since") or {}
        d["file"] = f.name
        d["forms_count"] = sum(1 for x in (d.get("forms") or {}).values() if x.get("f") is not None)
        names = d.get("names") or {}
        for c in d.get("changes") or []:
            c["name"] = names.get(c["path"], c["path"])
        d["baseline_at"] = (d.get("baseline") or {}).get("at")
        d["risk"] = _risk_of(d)
        d["all"] = _all_screens(d)
        for k in ("forms", "paths", "names", "baseline", "history_full", "times", "rows_of", "modules"):
            d.pop(k, None)
        bf = health.STATE / f.name.replace("health_", "books_")
        try:
            d["books"] = json.loads(bf.read_text(encoding="utf-8")) if bf.exists() else None
        except Exception:
            d["books"] = None
        d["broken"] = _with_risk([{"path": p, **b, "since": since.get(p, "")} for p, b in (d.get("broken") or {}).items()])
        states.append(d)
    states.sort(key=lambda d: d.get("at") or "", reverse=True)
    C = _C()
    cfg = _health_cfg()
    return jsonify({"success": True, "config": C.public(cfg), "saved": C.exists(HEALTH_KEY), "states": states,
                    "last": _last_results().get(HEALTH_KEY), "default_skip": health.DEFAULT_SKIP})


@bp.route("/api/health/save", methods=["POST"])
@auth.login_required
def api_health_save():
    C = _C()
    d = request.get_json(silent=True) or {}
    cfg = {**(d.get("config") or {}), "key": HEALTH_KEY, "type": "health", "name_ar": "🩺 صحة النظام — كل الشاشات"}
    try:
        saved = C.save(cfg)
    except C.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    out = {"success": True, "config": C.public(saved)}
    if d.get("run"):
        from web.queue_manager import get_manager
        from web import sites_api
        out.update(sites_api.queue_on_sites(get_manager(), C.test_path_for(HEALTH_KEY), saved["name_ar"], d.get("sites"), source="manual",
                                            front=True))
    return jsonify(out)


@bp.route("/api/health/baseline", methods=["POST"])
@auth.login_required
def api_health_baseline():
    """📸 the last check of this site = «قبل التحديث»: the next checks compare with it until it is set again"""
    from engine import health
    name = (request.get_json(silent=True) or {}).get("file") or ""
    f = health.STATE / name
    if not name.startswith("health_") or "/" in name or not f.exists():
        return jsonify({"success": False, "error": "مفيش فحص للموقع ده"}), 404
    return jsonify({"success": True, "at": health.set_baseline(f)})


# ======================================================== ⚖️ مطابقة الحسابات (trial balance, no setup)
BOOKS_KEY = "books_check"
BOOKS_FULL_KEY = "books_check_full"


@bp.route("/api/books")
@auth.login_required
def api_books():
    C = _C()
    try:
        cfg = C.load(BOOKS_KEY)
    except C.ConfigError:
        cfg = C.normalize({"key": BOOKS_KEY, "type": "books", "name_ar": "⚖️ مطابقة الحسابات"})
    return jsonify({"success": True, "config": C.public(cfg), "last": _last_results().get(BOOKS_KEY)})


@bp.route("/api/books/save", methods=["POST"])
@auth.login_required
def api_books_save():
    C = _C()
    d = request.get_json(silent=True) or {}
    try:
        saved = C.save({**(d.get("config") or {}), "key": BOOKS_KEY, "type": "books", "name_ar": "⚖️ مطابقة الحسابات"})
    except C.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    out = {"success": True}
    if d.get("run"):
        from web.queue_manager import get_manager
        from web import sites_api
        out.update(sites_api.queue_on_sites(get_manager(), C.test_path_for(BOOKS_KEY), saved["name_ar"], d.get("sites"), source="manual",
                                            front=True))
    return jsonify(out)


# ======================================================== 🔌 اختبار الـ API (+ الحمل)
API_KEY = "api_check"


@bp.route("/api/api-check")
@auth.login_required
def api_api_check():
    C = _C()
    try:
        cfg = C.load(API_KEY)
    except C.ConfigError:
        cfg = C.normalize({"key": API_KEY, "type": "api", "name_ar": "🔌 اختبار الـ API"})
    return jsonify({"success": True, "config": C.public(cfg), "last": _last_results().get(API_KEY)})


@bp.route("/api/api-check/save", methods=["POST"])
@auth.login_required
def api_api_check_save():
    C = _C()
    d = request.get_json(silent=True) or {}
    try:
        old = C.load(API_KEY) if C.exists(API_KEY) else {}
        saved = C.save({**old, **(d.get("config") or {}), "key": API_KEY, "type": "api", "name_ar": "🔌 اختبار الـ API"})
    except C.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    out = {"success": True}
    if d.get("run"):
        from web.queue_manager import get_manager
        from web import sites_api
        out.update(sites_api.queue_on_sites(get_manager(), C.test_path_for(API_KEY), saved["name_ar"], d.get("sites"), source="manual",
                                            front=True))
    return jsonify(out)


# ======================================================== 🛡️ الصلاحيات والفصل بين المهام
SOD_KEY = "sod_check"


@bp.route("/api/sod")
@auth.login_required
def api_sod():
    C = _C()
    try:
        cfg = C.load(SOD_KEY)
    except C.ConfigError:
        cfg = C.normalize({"key": SOD_KEY, "type": "sod", "name_ar": "🛡️ الصلاحيات والفصل بين المهام"})
    return jsonify({"success": True, "config": C.public(cfg), "last": _last_results().get(SOD_KEY)})


@bp.route("/api/sod/save", methods=["POST"])
@auth.login_required
def api_sod_save():
    C = _C()
    d = request.get_json(silent=True) or {}
    try:
        old = C.load(SOD_KEY) if C.exists(SOD_KEY) else {}
        saved = C.save({**old, **(d.get("config") or {}), "key": SOD_KEY, "type": "sod", "name_ar": "🛡️ الصلاحيات والفصل بين المهام"})
    except C.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    out = {"success": True}
    if d.get("run"):
        from web.queue_manager import get_manager
        from web import sites_api
        out.update(sites_api.queue_on_sites(get_manager(), C.test_path_for(SOD_KEY), saved["name_ar"], d.get("sites"), source="manual",
                                            front=True))
    return jsonify(out)


# ======================================================== 📋 سيناريوهات الأعمال (نموذج المطور)
BIZ_KEY = "biz_sales_invoice"


@bp.route("/business-scenarios")
@auth.login_required
def biz_scenarios_page():
    from engine.biz_sales_invoice import STEPS
    return render_template("scenarios.html", steps=STEPS)


@bp.route("/api/biz/runs")
@auth.login_required
def api_biz_runs():
    """the last business-scenario runs: when, site, invoice, counts, links"""
    from web import insights
    from engine.check_runner import load_detail
    out = []
    for r in insights.all_runs():
        if r["key"] != BIZ_KEY:
            continue
        d = load_detail(r["run_id"]) or {}
        biz = d.get("biz") or {}
        st = biz.get("steps") or {}
        cnt = {k: sum(1 for v in st.values() if (v[0] if isinstance(v, (list, tuple)) else v) == k) for k in ("ok", "fail", "na")}
        out.append({"run_id": r["run_id"], "time": r["time"].strftime("%Y-%m-%d %H:%M"), "passed": r["passed"],
                    "site": (r["summary"] or {}).get("site_name") or (biz.get("facts") or {}).get("site", ""),
                    "invoice": (biz.get("facts") or {}).get("invoice_no", ""), "counts": cnt,
                    "steps": {k: (v[0] if isinstance(v, (list, tuple)) else v) for k, v in st.items()},
                    "word": bool(biz.get("word")), "message": r["message"][:200]})
        if len(out) >= 15:
            break
    from web import test_sites_helper as ts
    data = ts.load_all()
    sites = [{"id": p.get("id"), "name": p.get("name") or p.get("id"), "url": p.get("base_url", ""), "kind": ts.site_kind(p),
              "active": p.get("id") == data.get("active_profile")} for p in data.get("profiles", [])]
    return jsonify({"success": True, "runs": out, "sites": sites})


@bp.route("/api/biz")
@auth.login_required
def api_biz():
    C = _C()
    cfg = C.load(BIZ_KEY) if C.exists(BIZ_KEY) else None
    return jsonify({"success": True, "config": C.public(cfg) if cfg else None, "last": _last_results().get(BIZ_KEY)})


@bp.route("/api/biz/save", methods=["POST"])
@auth.login_required
def api_biz_save():
    C = _C()
    d = request.get_json(silent=True) or {}
    try:
        old = C.load(BIZ_KEY) if C.exists(BIZ_KEY) else {}
        saved = C.save({**old, **(d.get("config") or {}), "key": BIZ_KEY, "type": "biz",
                        "name_ar": "📋 سيناريو: فاتورة بيع آجلة بخصم وضريبة (19 بند)"})
    except C.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    out = {"success": True, "config": C.public(saved)}
    if d.get("run"):
        from web.queue_manager import get_manager
        from web import sites_api
        out.update(sites_api.queue_on_sites(get_manager(), C.test_path_for(BIZ_KEY), saved["name_ar"], d.get("sites"), source="manual", front=True))
    return jsonify(out)


# ======================================================== 📚 حزم سيناريوهات المطور (ملفات الورد)
def _bc_key(code):
    return f"bizcases_{code.lower()}"


@bp.route("/api/bizcases")
@auth.login_required
def api_bizcases():
    """the developer's case files + what the engine runs + last result of every case + the site data file"""
    from engine import biz_cases as B
    from web import insights
    from engine.check_runner import load_detail
    from web import test_sites_helper as ts
    cat = B.catalog()
    last, runs = {}, {}
    for r in insights.all_runs():
        if not r["key"].startswith("bizcases_"):
            continue
        code = r["key"].split("_", 1)[1].upper()
        if len(runs.setdefault(code, [])) >= 8:
            continue
        d = load_detail(r["run_id"]) or {}
        bz = d.get("biz") or {}
        cs = bz.get("cases") or {}
        cnt = {}
        for v in cs.values():
            cnt[v["status"]] = cnt.get(v["status"], 0) + 1
        runs[code].append({"run_id": r["run_id"], "time": r["time"].strftime("%Y-%m-%d %H:%M"), "site": (r["summary"] or {}).get("site_name") or "",
                           "counts": cnt, "word": bool(bz.get("word"))})
        for i, v in cs.items():
            last.setdefault(code, {}).setdefault(i, {**v, "time": r["time"].strftime("%Y-%m-%d %H:%M")})
    data = ts.load_all()
    sites = [{"id": p.get("id"), "name": p.get("name") or p.get("id"), "url": p.get("base_url", ""), "kind": ts.site_kind(p),
              "active": p.get("id") == data.get("active_profile"), "data": B.load_data(p.get("base_url", ""))} for p in data.get("profiles", [])]
    screens = [{k: v for k, v in c.items() if k != "cases"} | {"cases": [{x: y for x, y in cc.items()} for cc in c["cases"]],
               "last": last.get(code, {}), "runs": runs.get(code, [])} for code, c in cat.items()]
    return jsonify({"success": True, "screens": screens, "sites": sites, "symbols": B.SYMBOLS})


@bp.route("/api/bizcases/data", methods=["POST"])
@auth.login_required
def api_bizcases_data():
    from engine import biz_cases as B
    from web import test_sites_helper as ts
    d = request.get_json(silent=True) or {}
    prof = next((p for p in ts.load_all().get("profiles", []) if p.get("id") == d.get("site")), None)
    if not prof:
        return jsonify({"success": False, "error": "اختاري الموقع"}), 400
    return jsonify({"success": True, "data": B.save_data(prof.get("base_url", ""), d.get("data") or {})})


@bp.route("/api/bizcases/run", methods=["POST"])
@auth.login_required
def api_bizcases_run():
    from engine import biz_cases as B
    C = _C()
    d = request.get_json(silent=True) or {}
    code = str(d.get("screen") or "").upper()
    cat = B.catalog().get(code)
    if not cat:
        return jsonify({"success": False, "error": "الشاشة مش معروفة"}), 400
    cases = [c for c in (d.get("cases") or []) if any(x["id"] == c for x in cat["cases"])]
    try:
        saved = C.save({"key": _bc_key(code), "type": "bizcases", "screen": code, "cases": cases,
                        "name_ar": f"{cat['icon']} سيناريوهات {cat['name']} ({len(cases) or cat['auto_n']} حالة)"})
    except C.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    from web.queue_manager import get_manager
    from web import sites_api
    out = {"success": True}
    out.update(sites_api.queue_on_sites(get_manager(), C.test_path_for(saved["key"]), saved["name_ar"], d.get("site"), source="manual", front=True))
    return jsonify(out)


# ======================================================== 🧹 تنظيف بيانات الاختبار
CLEAN_KEY = "test_data_cleanup"


@bp.route("/api/cleanup")
@auth.login_required
def api_cleanup():
    from engine import cleanup
    items = [{k: v for k, v in x.items() if k != "plan"} | {"list_url": x["plan"].get("list_url")} for x in cleanup.load_all()]
    return jsonify({"success": True, "items": items, "last": _last_results().get(CLEAN_KEY)})


@bp.route("/api/cleanup/run", methods=["POST"])
@auth.login_required
def api_cleanup_run():
    C = _C()
    d = request.get_json(silent=True) or {}
    saved = C.save({"key": CLEAN_KEY, "type": "cleanup", "name_ar": "🧹 تنظيف بيانات الاختبار"})
    from web.queue_manager import get_manager
    from web import sites_api
    return jsonify({"success": True, **sites_api.queue_on_sites(get_manager(), C.test_path_for(CLEAN_KEY), saved["name_ar"],
                                                                 d.get("sites"), source="manual")})


@bp.route("/api/cleanup/forget", methods=["POST"])
@auth.login_required
def api_cleanup_forget():
    from engine import cleanup
    cleanup.forget((request.get_json(silent=True) or {}).get("items") or [])
    return jsonify({"success": True})


# ======================================================== 📈 الأخطاء المتكررة (all runs, grouped by the error)
_ERR_KINDS = (
    ("📦 بيانات أساسية ناقصة في الموقع", r"بيانات أساسية ناقصة|مفيش ولا خيار في القايمة"),
    ("🗄️ خطأ قاعدة بيانات / SQL", r"sql|stored procedure|transaction count|begin/commit|_insert|_update|deadlock|constraint|51000"),
    ("💥 خطأ سيرفر", r"\b50[0-9]\b|server error|exception|خطأ سيرفر|internal"),
    ("📜 خطأ JavaScript في الصفحة", r"javascript|is not defined|is not a function|cannot read prop|js error"),
    ("🔢 الترقيم", r"الترقيم|رقم المستند|documentnumber|مكرر"),
    ("⚖️ الحسابات", r"مدين|دائن|ميزان|متزن"),
    ("🔒 الدخول / الصلاحيات", r"login|الدخول|صلاحي|403|401"),
    ("⏱️ بطء / مهلة", r"timeout|timed out|انتهى الوقت|أبطأ|بطيئة"),
    ("📝 حقول / تحقق", r"مطلوب|إجباري|اجباري|required|يجب"),
    ("🔍 عنصر مش موجود", r"no such element|مالقيتش|not found|404|stale"),
)


def _kind(msg):
    import re
    m = msg.lower()
    return next((k for k, rx in _ERR_KINDS if re.search(rx, m, re.I)), "❓ غير ذلك")


def _sig(msg):
    import re
    line = next((x.strip() for x in msg.splitlines() if x.strip()), "")
    line = re.sub(r"«[^»]*»|\"[^\"]*\"|'[^']*'", "«…»", line)
    line = re.sub(r"\d+([.,]\d+)*", "#", line)
    return line[:160]


@bp.route("/api/errors")
@auth.login_required
def api_errors():
    from datetime import datetime, timedelta
    from web import insights
    days = int(request.args.get("days", 30) or 30)
    since = datetime.now() - timedelta(days=days)
    groups, kinds, total, per_day = {}, {}, 0, {}
    for r in insights.all_runs():
        if r["time"] < since or r["passed"] or not r["message"]:
            continue
        total += 1
        sig, kind = _sig(r["message"]), _kind(r["message"])
        g = groups.setdefault(sig, {"sig": sig, "kind": kind, "count": 0, "tests": [], "first": r["time"], "last": r["time"],
                                    "run_id": r["run_id"], "example": r["message"][:300]})
        g["count"] += 1
        g["first"] = min(g["first"], r["time"])
        if r["time"] >= g["last"]:
            g["last"], g["run_id"], g["example"] = r["time"], r["run_id"], r["message"][:300]
        if r["name"] not in g["tests"]:
            g["tests"].append(r["name"])
        kinds[kind] = kinds.get(kind, 0) + 1
        d = r["time"].strftime("%Y-%m-%d")
        per_day[d] = per_day.get(d, 0) + 1
    out = sorted(groups.values(), key=lambda g: (-g["count"], g["last"]))
    for g in out:
        g["first"], g["last"] = g["first"].strftime("%Y-%m-%d %H:%M"), g["last"].strftime("%Y-%m-%d %H:%M")
        g["tests"] = g["tests"][:8]
    days_list = [(since + timedelta(days=i + 1)).strftime("%Y-%m-%d") for i in range(days)]
    return jsonify({"success": True, "total": total, "groups": out[:100], "kinds": sorted(kinds.items(), key=lambda x: -x[1]),
                    "per_day": [{"d": d, "n": per_day.get(d, 0)} for d in days_list]})


def _td_site():
    """📦 the test-data store of the site picked on the page (or the active one)"""
    from engine import test_data
    from web import test_sites_helper as ts
    d = ts.load_all()
    sid = request.args.get("site") or (request.get_json(silent=True) or {}).get("site") or d.get("active_profile")
    p = next((x for x in d.get("profiles", []) if x.get("id") == sid), None)
    test_data.SITE = test_data.site_key_of(p) if p else None
    return test_data, p


@bp.route("/api/test-data")
@auth.login_required
def api_test_data():
    td, p = _td_site()
    try:
        return jsonify({"success": True, "site": (p or {}).get("name", ""), "kind": (p or {}).get("kind", ""), "kinds": td.summary()})
    finally:
        td.SITE = None


@bp.route("/api/test-data", methods=["POST"])
@auth.login_required
def api_test_data_set():
    td, p = _td_site()
    b = request.get_json(silent=True) or {}
    a = b.get("action")
    try:
        td.set_value(b.get("kind"), b.get("value", ""), manual=True if a == "add" else None,
                     blocked={"block": True, "unblock": False}.get(a), remove=a == "remove")
        return jsonify({"success": True, "kinds": td.summary()})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    finally:
        td.SITE = None


@bp.route("/api/screen-library")
@auth.login_required
def api_screen_library():
    from engine import screen_library
    return jsonify({"success": True, "screens": screen_library.report()})


@bp.route("/api/screen-library/apply", methods=["POST"])
@auth.login_required
def api_screen_library_apply():
    from engine import screen_library
    key = (request.get_json(silent=True) or {}).get("key")
    try:
        ch = screen_library.apply(key)
        return jsonify({"success": True, "applied": len(ch), "screens": screen_library.report()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@bp.route("/api/heals")
@auth.login_required
def api_heals():
    from engine import self_heal
    return jsonify({"success": True, "heals": self_heal.listing()})


@bp.route("/api/heals/undo", methods=["POST"])
@auth.login_required
def api_heals_undo():
    from engine import self_heal
    b = request.get_json(silent=True) or {}
    self_heal.undo(b.get("old"), b.get("new"))
    return jsonify({"success": True, "heals": self_heal.listing()})


@bp.route("/api/auto-test/recipes", methods=["DELETE"])
@auth.login_required
def api_recipes_reset():
    from engine.stubborn import RECIPES
    n = 0
    for f in RECIPES.glob("*.json") if RECIPES.exists() else []:
        f.unlink()
        n += 1
    return jsonify({"success": True, "count": n})


@bp.route("/api/health/full", methods=["POST"])
@auth.login_required
def api_health_full():
    """🔎 فحص شامل لموقع عميل: every screen + the real speed of the slowest ones + the accounts (trial balance)"""
    C = _C()
    from web.queue_manager import get_manager
    from web import sites_api
    d = request.get_json(silent=True) or {}
    h = _health_cfg()
    # the full check runs as its own saved check (deep speed on) — the daily «صحة النظام» keeps its own quick settings
    hc = {**C.public(h), **(d.get("config") or {}), "key": FULL_KEY, "type": "health", "name_ar": "🔎 فحص شامل — الشاشات والسرعة"}
    hc["deep_speed"] = int(hc.get("deep_speed") or 25)
    h = C.save(hc)
    # the full check reads ALL entries up to today (no stale dates from the «الحسابات بس» box)
    C.save({"key": BOOKS_FULL_KEY, "type": "books", "name_ar": "⚖️ مطابقة الحسابات — كل الفترات"})
    # first in the queue: a client is waiting — it does not wait behind a long list of other tests
    out2 = sites_api.queue_on_sites(get_manager(), C.test_path_for(BOOKS_FULL_KEY), "🔎 فحص شامل: مطابقة الحسابات", d.get("sites"),
                                    source="manual", front=True)
    out = sites_api.queue_on_sites(get_manager(), C.test_path_for(FULL_KEY), "🔎 فحص شامل: الشاشات والسرعة", d.get("sites"),
                                   source="manual", front=True)
    return jsonify({"success": True, "count": out["count"] + out2["count"], "task_ids": out["task_ids"] + out2["task_ids"]})


@bp.route("/api/readiness")
@auth.login_required
def api_readiness():
    """🚦 readiness score + verdict for every checked site"""
    from engine import readiness
    return jsonify({"success": True, "sites": readiness.all_sites()})


@bp.route("/env-compare")
@auth.login_required
def env_compare_page():
    """🔁 two sites side by side (Opkey-style environment drift)"""
    from engine import env_compare
    st = env_compare.states()
    a, b = request.args.get("a") or (st[0]["file"] if st else ""), request.args.get("b") or (st[1]["file"] if len(st) > 1 else "")
    res, err = None, ""
    if a and b and a != b:
        try:
            res = env_compare.compare(a, b)
        except Exception as e:
            err = str(e)
    return render_template("env_compare.html", states=st, a=a, b=b, r=res, err=err)


@bp.route("/readiness")
@auth.login_required
def readiness_page():
    """🚦 one printable page per site: go / no-go and why (approved report design)"""
    from engine import readiness
    from datetime import datetime as _dt
    from web import settings_helper
    sc = settings_helper.load_site_config()
    u = auth.current_user() or {}
    return render_template("readiness.html", sites=readiness.all_sites(), co={"name": sc.get("company_name_ar") or "",
                           "cr": sc.get("company_cr") or "", "vat": sc.get("company_vat") or "", "logo": sc.get("logo_filename") or ""},
                           user=u.get("full_name") or u.get("username") or "", printed=_dt.now().strftime("%Y-%m-%d %H:%M"))


def _deploy_token_ok():
    import os
    import hmac
    want = os.getenv("DEPLOY_TOKEN") or ""
    got = request.headers.get("X-Deploy-Token") or request.args.get("token") or ""
    return bool(want) and hmac.compare_digest(want, got)


@bp.route("/api/deploy-hook", methods=["POST"])
def api_deploy_hook():
    """🚀 release gate: the ERP's deploy calls this after publishing to the test site (header X-Deploy-Token =
    the DEPLOY_TOKEN variable). It queues the full check first in line; then poll GET /api/deploy-hook/status."""
    if not _deploy_token_ok():
        return jsonify({"success": False, "error": "token"}), 403
    C = _C()
    from web.queue_manager import get_manager
    from web import sites_api
    d = request.get_json(silent=True) or {}
    hc = {**C.public(_health_cfg()), "key": FULL_KEY, "type": "health", "name_ar": "🔎 فحص شامل — الشاشات والسرعة"}
    hc["deep_speed"] = int(hc.get("deep_speed") or 25)
    C.save(hc)
    C.save({"key": BOOKS_FULL_KEY, "type": "books", "name_ar": "⚖️ مطابقة الحسابات — كل الفترات"})
    a = sites_api.queue_on_sites(get_manager(), C.test_path_for(BOOKS_FULL_KEY), "🚀 بعد النشر: الحسابات", d.get("sites"), source="deploy", front=True)
    b = sites_api.queue_on_sites(get_manager(), C.test_path_for(FULL_KEY), "🚀 بعد النشر: الشاشات والسرعة", d.get("sites"), source="deploy", front=True)
    return jsonify({"success": True, "task_ids": b["task_ids"] + a["task_ids"], "version": d.get("version", "")})


@bp.route("/api/deploy-hook/status")
def api_deploy_hook_status():
    """{done, verdict: go | care | no, score} — the deploy waits for done, then publishes to clients only on «go»"""
    if not _deploy_token_ok():
        return jsonify({"success": False, "error": "token"}), 403
    from web.queue_manager import get_manager
    from engine import readiness
    qm = get_manager()
    ids = [x for x in (request.args.get("ids") or "").split(",") if x]
    done = all((qm.get_task(t) or {}).get("status") in ("completed", "failed", "error", "stopped", "done") for t in ids) if ids else True
    sites = readiness.all_sites()
    top = sites[0] if sites else None
    return jsonify({"success": True, "done": done, "verdict": top and top["verdict"], "score": top and top["score"],
                    "verdict_text": top and top["verdict_text"], "notes": top and top["notes"]})


@bp.route("/api/health/tasks")
@auth.login_required
def api_health_tasks():
    """where the checks started from this page are: waiting (and their place), running, done"""
    from web.queue_manager import get_manager
    qm = get_manager()
    st = qm.get_status()
    order = [t.get("task_id") for t in st.get("queue") or []]
    out = []
    for tid in [x for x in (request.args.get("ids") or "").split(",") if x][:20]:
        t = qm.get_task(tid) or {}
        status = t.get("status") or "unknown"
        if tid in order:
            status = "queued"
        out.append({"id": tid, "name": t.get("test_name", ""), "status": status, "place": (order.index(tid) + 1) if tid in order else 0,
                    "started": t.get("started_at"), "run_id": t.get("run_id") or tid})
    return jsonify({"success": True, "tasks": out, "running": [r.get("test_name") for r in st.get("running_all") or []],
                    "waiting": st.get("queue_length", 0)})


@bp.route("/health/report")
@auth.login_required
def health_report():
    """the client's speed & health report (printable, the approved report design)"""
    from engine import health
    from datetime import datetime as _dt
    name = request.args.get("file") or ""
    f = health.STATE / name
    if not name.startswith("health_") or "/" in name or not f.exists():
        return "مفيش فحص للموقع ده", 404
    d = json.loads(f.read_text(encoding="utf-8"))
    bf = health.STATE / name.replace("health_", "books_")
    books = json.loads(bf.read_text(encoding="utf-8")) if bf.exists() else None
    site_name = ""
    try:
        from web import test_sites_helper as ts
        site_name = next((p["name"] for p in ts.load_all().get("profiles", []) if p.get("base_url", "").rstrip("/") == d.get("base_url", "").rstrip("/")), "")
    except Exception:
        pass
    times = d.get("times") or {}
    names = d.get("names") or {}
    is_add = lambda p: "/addedit" in p.lower() or "➕" in names.get(p, "")
    slow_html = sorted(((ms, p) for p, ms in times.items() if ms and not is_add(p)), reverse=True)[:25]
    slow_adds = sorted(((ms, p) for p, ms in times.items() if ms and is_add(p)), reverse=True)[:15]
    since = d.get("since") or {}
    broken = _with_risk([{"path": p, **b, "since": since.get(p, "")} for p, b in (d.get("broken") or {}).items()])
    return render_template("health_report.html", d=d, books=books, site_name=site_name or d.get("base_url"), broken=broken,
                           slow_html=[{"path": p, "name": names.get(p, p), "sec": round(ms / 1000, 2),
                                       **((d.get("rows_of") or {}).get(p) or {})} for ms, p in slow_html],
                           slow_adds=[{"path": p, "name": names.get(p, p).replace("➕ إضافة — ", ""), "sec": round(ms / 1000, 2)} for ms, p in slow_adds],
                           all_screens=_all_screens(d), rk=_risk_of(d),
                           rate=health.rate, user=((auth.current_user() or {}).get("full_name") or (auth.current_user() or {}).get("username") or ""),
                           printed=_dt.now().strftime("%Y-%m-%d %H:%M"))
