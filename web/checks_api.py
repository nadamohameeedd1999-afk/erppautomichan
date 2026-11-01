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
