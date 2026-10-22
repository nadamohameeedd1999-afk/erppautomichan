"""
Screen Builder (منشئ الشاشات) — dashboard routes.

/screens                       page
/api/screens                   GET list of configs
/api/screens/catalog           GET screens from the modules registry (to pick from)
/api/screens/<key>             GET / POST(save) / DELETE
/api/screens/inspect           POST {list_url, add_url?, add_button?}      -> job (read only)
/api/screens/dry-run           POST {config}                              -> job (fill, no save)
/api/screens/jobs/<job_id>     GET job status + result + log tail
"""
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

from web import auth

BASE_DIR = Path(__file__).resolve().parent.parent
from config import paths  # noqa: E402
JOBS_DIR = paths.JOBS_DIR

bp = Blueprint("screens", __name__)
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

_jobs = {}
_lock = threading.Lock()
_running = {"job": None}


def _cfg():
    from engine import screen_config
    return screen_config


# ---------------- page ----------------
@bp.route("/screens")
@auth.login_required
def screens_page():
    sc = _cfg()
    return render_template("screens.html", strategies=sc.STRATEGIES, kinds=sc.KINDS, mode="screen")


@bp.route("/scenarios")
@auth.login_required
def scenarios_page():
    sc = _cfg()
    return render_template("screens.html", strategies=sc.STRATEGIES, kinds=sc.KINDS, mode="scenario")


# ---------------- scenarios ----------------
def _scn():
    from engine import scenario_config
    return scenario_config


@bp.route("/api/scenarios")
@auth.login_required
def api_scn_list():
    S = _scn()
    screen = (request.args.get("screen") or "").strip() or None
    items = []
    for c in S.list_all(screen):
        items.append({
            "key": c["key"], "screen_key": c.get("screen_key"), "scenario_key": c.get("scenario_key"),
            "scenario_name": c.get("scenario_name"), "screen_name": c.get("screen_name", c.get("screen_key")),
            "fields": len(c.get("fields", [])), "updated_at": c.get("updated_at", ""), "error": c.get("error"),
            "test_path": S.test_path_for(c.get("screen_key", ""), c.get("scenario_key", "")),
        })
    return jsonify({"success": True, "scenarios": items})


@bp.route("/api/scenarios/<screen>/<scn>", methods=["GET"])
@auth.login_required
def api_scn_get(screen, scn):
    S = _scn()
    try:
        return jsonify({"success": True, "config": S.load(screen, scn)})
    except S.ScenarioError as e:
        return jsonify({"success": False, "error": str(e)}), 404


@bp.route("/api/scenarios/<screen>/<scn>", methods=["POST"])
@auth.login_required
def api_scn_save(screen, scn):
    S = _scn()
    data = request.get_json(silent=True) or {}
    cfg = data.get("config") or data
    cfg["screen_key"], cfg["scenario_key"] = screen, scn
    try:
        saved = S.save(cfg)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "config": saved, "test_path": S.test_path_for(screen, scn)})


@bp.route("/api/scenarios/<screen>/<scn>", methods=["DELETE"])
@auth.login_required
def api_scn_delete(screen, scn):
    S = _scn()
    if not (S.PART_RE.match(screen or "") and S.PART_RE.match(scn or "")):
        return jsonify({"success": False, "error": "مفتاح غلط"}), 400
    return jsonify({"success": S.delete(screen, scn)})


# ---------------- configs ----------------
@bp.route("/api/screens")
@auth.login_required
def api_list():
    sc = _cfg()
    items = []
    for c in sc.list_all():
        items.append({
            "key": c["key"], "name_ar": c.get("name_ar"), "list_url": c.get("list_url", ""),
            "module_key": c.get("module_key", ""), "fields": len(c.get("fields", [])),
            "updated_at": c.get("updated_at", ""), "error": c.get("error"),
            "test_path": sc.test_path_for(c["key"]),
        })
    return jsonify({"success": True, "screens": items})


@bp.route("/api/screens/catalog")
@auth.login_required
def api_catalog():
    from config.modules_registry import ModulesRegistry
    sc = _cfg()
    have = set(sc.keys())
    out = []
    for mk, m in ModulesRegistry.MODULES.items():
        for pk, p in m.get("pages", {}).items():
            out.append({"module_key": mk, "module_name": m.get("name_ar", mk), "key": pk,
                        "name_ar": p.get("name_ar", pk), "name_en": p.get("name_en", ""),
                        "url": p.get("url", ""), "has_config": pk in have})
    listed = {p["key"] for p in out}
    for c in sc.list_all():
        if not c.get("error") and c["key"] not in listed:
            out.append({"module_key": c.get("module_key", "custom"), "module_name": "شاشات منشئ الشاشات",
                        "key": c["key"], "name_ar": c.get("name_ar", c["key"]), "name_en": c.get("name_en", ""),
                        "url": c.get("list_url", ""), "has_config": True})
    return jsonify({"success": True, "pages": out})


@bp.route("/api/screens/<key>", methods=["GET"])
@auth.login_required
def api_get(key):
    sc = _cfg()
    try:
        return jsonify({"success": True, "config": sc.load(key)})
    except sc.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 404


@bp.route("/api/screens/<key>", methods=["POST"])
@auth.login_required
def api_save(key):
    sc = _cfg()
    data = request.get_json(silent=True) or {}
    cfg = data.get("config") or data
    cfg["key"] = key
    try:
        saved = sc.save(cfg)
    except sc.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "config": saved, "test_path": sc.test_path_for(key)})


@bp.route("/api/screens/<key>", methods=["DELETE"])
@auth.login_required
def api_delete(key):
    sc = _cfg()
    if not sc.KEY_RE.match(key or ""):
        return jsonify({"success": False, "error": "مفتاح غلط"}), 400
    return jsonify({"success": sc.delete(key)})


# ---------------- background jobs ----------------
def _start_job(kind, args, extra=None):
    with _lock:
        cur = _running["job"]
        if cur and _jobs.get(cur, {}).get("status") == "running":
            return None, "فيه عملية تانية شغالة دلوقتي — استنى لما تخلص"
        job_id = f"{kind}_{datetime.now():%Y%m%d%H%M%S}_{uuid.uuid4().hex[:4]}"
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        out = JOBS_DIR / f"{job_id}.json"
        log = JOBS_DIR / f"{job_id}.log"
        job = {"id": job_id, "kind": kind, "status": "running", "started_at": datetime.now().isoformat(),
               "out": str(out), "log": str(log), **(extra or {})}
        _jobs[job_id] = job
        _running["job"] = job_id

    cmd = [sys.executable, "-m", "engine.cli", *args, "--out", str(out)]

    def work():
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        try:
            with open(log, "w", encoding="utf-8") as lf:
                proc = subprocess.run(cmd, cwd=str(BASE_DIR), stdout=lf, stderr=subprocess.STDOUT,
                                      env=env, timeout=900)
            job["exit_code"] = proc.returncode
        except subprocess.TimeoutExpired:
            job["exit_code"] = -1
            job["error"] = "العملية أخدت أكتر من 15 دقيقة واتوقفت"
        except Exception as e:
            job["exit_code"] = -1
            job["error"] = str(e)[:300]
        job["status"] = "done"
        job["finished_at"] = datetime.now().isoformat()

    threading.Thread(target=work, daemon=True).start()
    return job_id, None


@bp.route("/api/screens/inspect", methods=["POST"])
@auth.login_required
def api_inspect():
    d = request.get_json(silent=True) or {}
    list_url = (d.get("list_url") or "").strip()
    if not list_url:
        return jsonify({"success": False, "error": "اكتب رابط شاشة القايمة"}), 400
    args = ["inspect", "--list-url", list_url]
    if d.get("add_url"):
        args += ["--add-url", d["add_url"].strip()]
    if d.get("add_button"):
        args += ["--add-button", d["add_button"].strip()]
    if d.get("no_deps"):
        args.append("--no-deps")
    job_id, err = _start_job("inspect", args)
    if err:
        return jsonify({"success": False, "error": err}), 409
    return jsonify({"success": True, "job_id": job_id})


@bp.route("/api/screens/dry-run", methods=["POST"])
@auth.login_required
def api_dry_run():
    sc = _cfg()
    d = request.get_json(silent=True) or {}
    try:
        cfg = sc.normalize(d.get("config") or {})
    except sc.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = JOBS_DIR / f"draft_{cfg['key']}_{uuid.uuid4().hex[:6]}.json"
    tmp.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    job_id, err = _start_job("dryrun", ["dry-run", "--config-file", str(tmp)])
    if err:
        return jsonify({"success": False, "error": err}), 409
    return jsonify({"success": True, "job_id": job_id})


def _shot_name(p):
    return Path(p).name if p else None


@bp.route("/api/screens/jobs/<job_id>")
@auth.login_required
def api_job(job_id):
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"success": False, "error": "العملية مش موجودة (ممكن السيرفر اتعمله restart)"}), 404
    log_tail = []
    try:
        with open(job["log"], "r", encoding="utf-8", errors="replace") as f:
            lines = [_ANSI.sub("", l.rstrip()) for l in f.readlines()]
        cut = lines.index("@@RESULT@@") if "@@RESULT@@" in lines else len(lines)
        log_tail = lines[:cut][-40:]
    except Exception:
        pass
    resp = {"success": True, "status": job["status"], "kind": job["kind"], "log": log_tail}
    if job["status"] == "done":
        try:
            result = json.loads(Path(job["out"]).read_text(encoding="utf-8"))
        except Exception:
            result = {"success": False, "error": job.get("error") or "مفيش نتيجة — شوف اللوج"}
        if result.get("screenshot"):
            result["screenshot_name"] = _shot_name(result["screenshot"])
        if result.get("screenshots"):
            result["screenshot_names"] = [_shot_name(p) for p in result["screenshots"] if p]
        resp["result"] = result
    return jsonify(resp)
