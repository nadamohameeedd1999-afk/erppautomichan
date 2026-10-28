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
            "operation": c.get("operation", "add"),
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
                proc = subprocess.Popen(cmd, cwd=str(BASE_DIR), stdout=lf, stderr=subprocess.STDOUT, env=env)
                job["proc"] = proc
                proc.wait(timeout=job.get("timeout", 900))
            job["exit_code"] = proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            job["exit_code"] = -1
            job["error"] = "العملية أخدت وقت أكتر من المسموح واتوقفت"
        except Exception as e:
            job["exit_code"] = -1
            job["error"] = str(e)[:300]
        job.pop("proc", None)
        job["status"] = "stopped" if job.get("stop_requested") else "done"
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


@bp.route("/api/screens/inspect-popup", methods=["POST"])
@auth.login_required
def api_inspect_popup():
    """Click a button on the add page, read the pop-up it opens and suggest a flow."""
    sc = _cfg()
    d = request.get_json(silent=True) or {}
    open_target = (d.get("open") or "").strip()
    if not open_target:
        return jsonify({"success": False, "error": "اكتبي اسم الزرار اللي بيفتح النافذة"}), 400
    cfg = dict(d.get("config") or {})
    cfg["flows"] = []                                 # discovering a new one
    if not cfg.get("fields"):
        cfg["fields"] = [{"id": "__none__", "strategy": "keep", "kind": "hidden"}]
    try:
        cfg = sc.normalize(cfg)
    except sc.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    if cfg["fields"] and cfg["fields"][0]["id"] == "__none__":
        cfg["fields"] = []
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = JOBS_DIR / f"popup_{cfg['key']}_{uuid.uuid4().hex[:6]}.json"
    tmp.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    args = ["inspect-popup", "--config-file", str(tmp), "--open", open_target]
    if d.get("after"):
        args += ["--after", str(d["after"])]
    choose = [c.strip() for c in str(d.get("choose") or "").replace("،", ",").replace("\n", ",").split(",") if c.strip()]
    if choose:
        args += ["--choose", "|".join(choose)]
    job_id, err = _start_job("popup", args)
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
    if job["status"] in ("done", "stopped"):
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


# ======================= datasets (بيانات Excel / CSV) =======================
def _dataset_dir():
    from config import paths
    d = paths.DATA_DIR / "datasets"
    d.mkdir(parents=True, exist_ok=True)
    return d


@bp.route("/api/datasets")
@auth.login_required
def api_datasets():
    from engine.screen_runner import _read_dataset
    out = []
    for f in sorted(_dataset_dir().glob("*")):
        if f.suffix.lower() in (".xlsx", ".csv"):
            try:
                n = len(_read_dataset(f.name))
            except Exception:
                n = "?"
            out.append({"name": f.name, "rows": n})
    return jsonify({"success": True, "files": out})


@bp.route("/api/datasets", methods=["POST"])
@auth.login_required
def api_dataset_upload():
    import re as _re
    from engine.screen_runner import _read_dataset
    up = request.files.get("file")
    if not up or not up.filename:
        return jsonify({"success": False, "error": "اختاري ملف"}), 400
    name = Path(up.filename).name
    if Path(name).suffix.lower() not in (".xlsx", ".csv"):
        return jsonify({"success": False, "error": "الملف لازم يكون .xlsx أو .csv"}), 400
    name = _re.sub(r"[^\w.\-\u0600-\u06FF ]", "_", name).strip() or "data.xlsx"
    dest = _dataset_dir() / name
    if dest.exists():
        from config.storage import to_trash
        to_trash(dest)
    up.save(str(dest))
    try:
        rows = _read_dataset(name)
    except Exception as e:
        return jsonify({"success": False, "error": f"مقدرتش أقرا الملف: {e}"}), 400
    if not rows:
        return jsonify({"success": False, "error": "الملف فاضي (لازم أول سطر فيه أسماء الأعمدة)"}), 400
    return jsonify({"success": True, "name": name, "rows": len(rows), "columns": list(rows[0].keys())})


@bp.route("/api/screens/discover", methods=["POST"])
@auth.login_required
def api_discover():
    """Read the ERP side menu, open every link and report what's there (اكتشاف شاشات النظام).
    Nothing is added to the tests until the user picks screens (/api/screens/discovered/add)."""
    d = request.get_json(silent=True) or {}
    limit = max(1, min(400, int(d.get("limit") or 200)))
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    busy = _running["job"] and _jobs.get(_running["job"], {}).get("status") == "running"
    if not busy:
        (JOBS_DIR / "discover_progress.json").unlink(missing_ok=True)      # a fresh start
    job_id, err = _start_job("discover", ["discover", "--limit", str(limit), "--no-save",
                                          "--progress", str(JOBS_DIR / "discover_progress.json")],
                             extra={"timeout": 3600})
    if err:
        return jsonify({"success": False, "error": err}), 409
    _jobs[job_id]["progress"] = str(JOBS_DIR / "discover_progress.json")
    return jsonify({"success": True, "job_id": job_id})


@bp.route("/api/screens/discover/<job_id>")
@auth.login_required
def api_discover_progress(job_id):
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"success": False, "error": "العملية مش موجودة (ممكن السيرفر اتعمله restart)"}), 404
    prog = {}
    try:
        prog = json.loads(Path(job["progress"]).read_text(encoding="utf-8"))
    except Exception:
        pass
    from config.screens_catalog import discovered
    have = {x["key"] for x in discovered()}
    for it in prog.get("items", []):
        it["added"] = it["key"] in have
    err = job.get("error")
    if job["status"] == "done" and not err:
        try:
            res = json.loads(Path(job["out"]).read_text(encoding="utf-8"))
            if not res.get("success"):
                err = res.get("error")
        except Exception:
            pass
    return jsonify({"success": True, "status": job["status"], "error": err, **prog})


@bp.route("/api/screens/jobs/<job_id>/stop", methods=["POST"])
@auth.login_required
def api_job_stop(job_id):
    job = _jobs.get(job_id)
    if not job or job.get("status") != "running":
        return jsonify({"success": False, "error": "مفيش عملية شغالة"}), 404
    job["stop_requested"] = True
    p = job.get("proc")
    if p and p.poll() is None:
        p.terminate()
        try:
            p.wait(timeout=8)
        except Exception:
            p.kill()
    if job.get("progress"):                       # keep what was found so far + mark the report
        try:
            from datetime import datetime as _dt
            pf = Path(job["progress"])
            prog = json.loads(pf.read_text(encoding="utf-8"))
            prog.update({"phase": "stopped", "message": f"⏹️ اتوقف — اتفحص {prog.get('done', 0)} من {prog.get('total', 0)}",
                         "finished_at": _dt.now().isoformat(timespec="seconds")})
            prog.setdefault("steps", []).append({"t": _dt.now().strftime("%H:%M:%S"), "msg": prog["message"]})
            txt = json.dumps(prog, ensure_ascii=False)
            pf.write_text(txt, encoding="utf-8")
            if prog.get("report_id"):
                (paths.RUNS_DIR / "discovery" / f"{prog['report_id']}.json").write_text(txt, encoding="utf-8")
        except Exception:
            pass
    return jsonify({"success": True})


@bp.route("/api/screens/discovered")
@auth.login_required
def api_discovered_list():
    from config.screens_catalog import discovered
    return jsonify({"success": True, "screens": discovered()})


@bp.route("/api/screens/discovered/add", methods=["POST"])
@auth.login_required
def api_discovered_add():
    """add the screens the user picked to the tests page (each gets a «فتح الشاشة» test)"""
    from config.screens_catalog import discovered, save_discovered
    items = (request.get_json(silent=True) or {}).get("items") or []
    cur = {x["key"]: x for x in discovered()}
    added = 0
    for it in items:
        key = str(it.get("key") or "").strip()
        if not key or not str(it.get("url") or "").startswith("/"):
            continue
        added += key not in cur
        cur[key] = {"key": key, "name": str(it.get("name") or key)[:80], "name_en": str(it.get("name_en") or "")[:80],
                    "group": str(it.get("group") or "")[:60], "url": it["url"]}
    save_discovered(list(cur.values()))
    rid = re.sub(r"[^a-zA-Z0-9_]", "", str((request.get_json(silent=True) or {}).get("report_id") or ""))
    if rid:                                       # the discovery report says what was added
        try:
            from datetime import datetime as _dt
            rf = paths.RUNS_DIR / "discovery" / f"{rid}.json"
            rep = json.loads(rf.read_text(encoding="utf-8"))
            keys = {str(it.get("key")) for it in items}
            for it in rep.get("items", []):
                if it["key"] in keys:
                    it["added_at"] = _dt.now().isoformat(timespec="seconds")
            rep.setdefault("steps", []).append({"t": _dt.now().strftime("%H:%M:%S"),
                                                "msg": f"➕ اتضاف {len(keys)} شاشة لصفحة الاختبارات"})
            rf.write_text(json.dumps(rep, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    return jsonify({"success": True, "added": added, "total": len(cur)})


@bp.route("/api/screens/discovered/remove", methods=["POST"])
@auth.login_required
def api_discovered_remove():
    from config.screens_catalog import discovered, save_discovered
    keys = set((request.get_json(silent=True) or {}).get("keys") or [])
    left = [x for x in discovered() if x["key"] not in keys]
    save_discovered(left)
    return jsonify({"success": True, "total": len(left)})


@bp.route("/api/screens/record", methods=["POST"])
@auth.login_required
def api_record():
    """Open the add page in Chrome and record what the user does there (سجّلي خطواتك)."""
    sc = _cfg()
    d = request.get_json(silent=True) or {}
    cfg = dict(d.get("config") or {})
    cfg["flows"] = []
    if not cfg.get("fields"):
        cfg["fields"] = [{"id": "__none__", "strategy": "keep", "kind": "hidden"}]
    try:
        cfg = sc.normalize(cfg)
    except sc.ConfigError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = JOBS_DIR / f"record_{cfg['key']}_{uuid.uuid4().hex[:6]}.json"
    tmp.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    stop = JOBS_DIR / f"{tmp.stem}.stop"
    job_id, err = _start_job("record", ["record", "--config-file", str(tmp), "--stop-file", str(stop)], extra={"timeout": 1500})
    if err:
        return jsonify({"success": False, "error": err}), 409
    _jobs[job_id]["stop_file"] = str(stop)
    from web import live_vnc
    return jsonify({"success": True, "job_id": job_id, "on_server": live_vnc.frames_available(),
                    "control": live_vnc.control_available()})


@bp.route("/api/screens/record/<job_id>/finish", methods=["POST"])
@auth.login_required
def api_record_finish(job_id):
    """«⏹ خلصت» from the dashboard: the recorder stops and returns what it caught (nothing is lost)"""
    job = _jobs.get(job_id)
    if not job or not job.get("stop_file"):
        return jsonify({"success": False, "error": "مفيش تسجيل شغال"}), 404
    Path(job["stop_file"]).write_text("stop", encoding="utf-8")
    return jsonify({"success": True})
