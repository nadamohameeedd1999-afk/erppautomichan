"""
Background jobs for the checks / automatic test pages (python -m engine.cli … in a subprocess).

/api/screens/jobs/<job_id>        GET job status + result + log tail
/api/screens/jobs/<job_id>/stop   POST stop it

(The old «منشئ الاختبارات» screen builder that used to live here was removed from the project.)
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

from flask import Blueprint, jsonify

from web import auth

BASE_DIR = Path(__file__).resolve().parent.parent
from config import paths  # noqa: E402
JOBS_DIR = paths.JOBS_DIR

bp = Blueprint("screens", __name__)
_ANSI = re.compile(r"\x1b\[[0-9;]*m")

_jobs = {}
_lock = threading.Lock()
_running = {"job": None}


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
