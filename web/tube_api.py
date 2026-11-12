"""
🎛️ التيوب — one live mini-panel for EVERY run, on every page.

/api/tube                 everything running / waiting / just finished: queue runs (any check: report compare, X-ray,
                          developer cases, health …), background jobs (checks / automatic test trials) and the database
                          audit — each with its name, site, steps (read live from its log), details, a stop action and
                          where its report is
/api/tube/stop            POST {kind, id} → stops that run
"""
import re
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from web import auth

bp = Blueprint("tube", __name__)
_ANSI = re.compile(r"\x1b\[[0-9;]*m|\[\d+(;\d+)*m")
_LINE = re.compile(r"^(?:\S+::\S+\s+)?(?:PASSED|FAILED|ERROR)?\s*(\d{1,2}:\d{2}:\d{2})\s*\|\s*([A-Z]+)\s*\|\s*(.*)$")
_NOISE = re.compile(r"^(=+|-+|Starting Chrome|🐳 Docker mode|✅ Chrome started|Closing browser|Screenshot: |Failure screenshot: |Open: http|PID: )")
RECENT_MIN = 10

# which dashboard page shows the result of a check, from the check key inside the test path
PAGES = [(r"repcmp", "/report-compare", "مقارنة التقارير"), (r"xray", "/xray", "أشعة النظام"), (r"bizcases", "/business-scenarios", "سيناريوهات الأعمال"),
         (r"biz19|bizscen", "/business-scenarios", "سيناريوهات الأعمال"), (r"health", "/health", "صحة النظام"), (r"envcmp", "/env-compare", "مقارنة بيئتين"),
         (r"readiness", "/readiness", "جاهزية الإصدار"), (r"test_check_", "/checks", "الدورات والفحوصات")]


def steps_from_log(lines, limit=30):
    """the readable steps of a run: «HH:MM:SS | LEVEL | message» lines, noise removed"""
    out = []
    for raw in lines:
        s = _ANSI.sub("", raw).strip()
        if not s:
            continue
        if s.startswith("=") and "FAILURES" in s:
            break
        m = _LINE.match(s)
        if not m:
            continue
        t, lvl, msg = m.groups()
        msg = msg.strip()
        if not msg or _NOISE.match(msg):
            continue
        out.append({"t": t, "lvl": {"SUCCESS": "ok", "ERROR": "err", "CRITICAL": "err", "WARNING": "warn"}.get(lvl, "info"), "msg": msg[:300]})
    return out[-limit:]


def _page_for(path):
    for pat, url, name in PAGES:
        if re.search(pat, path or "", re.I):
            return {"url": url, "name": name}
    return None


def _site_name(site_id):
    if not site_id:
        return ""
    try:
        from web import test_sites_helper as ts
        p = next((x for x in ts.load_all().get("profiles", []) if x.get("id") == site_id), None)
        return (p or {}).get("name") or site_id
    except Exception:
        return site_id


def _queue_items():
    from web.queue_manager import get_manager
    qm = get_manager()
    st = qm.get_status()
    items = []
    for t in st.get("running_all") or []:
        log = qm.read_log(t["task_id"], max_lines=400)
        items.append({"kind": "queue", "id": t["task_id"], "name": t.get("test_name") or t.get("test_path"), "site": _site_name(t.get("site")),
                      "status": "running", "started": t.get("started_at") or t.get("added_at"), "steps": steps_from_log(log.get("lines") or []),
                      "page": _page_for(t.get("test_path")), "report": None})
    for i, t in enumerate(st.get("queue") or []):
        items.append({"kind": "queue", "id": t["task_id"], "name": t.get("test_name") or t.get("test_path"), "site": _site_name(t.get("site")),
                      "status": "queued", "position": i + 1, "started": t.get("added_at"), "steps": [], "page": _page_for(t.get("test_path")), "report": None})
    cut = (datetime.now() - timedelta(minutes=RECENT_MIN)).isoformat()
    for t in qm.recent_history(15):
        if (t.get("completed_at") or "") < cut:
            continue
        log = qm.read_log(t["task_id"], max_lines=400)
        items.append({"kind": "queue", "id": t["task_id"], "name": t.get("test_name") or t.get("test_path"), "site": _site_name(t.get("site")),
                      "status": {"completed": "passed"}.get(t.get("status"), t.get("status")), "started": t.get("started_at"), "ended": t.get("completed_at"),
                      "duration": t.get("duration_seconds"), "steps": steps_from_log(log.get("lines") or []), "page": _page_for(t.get("test_path")),
                      "report": f"/reports/{t['task_id']}"})
    return items


def _job_items():
    from web import screens_api as J
    items = []
    cut = (datetime.now() - timedelta(minutes=RECENT_MIN)).isoformat()
    for j in list(J._jobs.values()):
        if j.get("status") != "running" and (j.get("finished_at") or "") < cut:
            continue
        lines = []
        try:
            with open(j["log"], "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception:
            pass
        kind = j.get("kind", "")
        items.append({"kind": "job", "id": j["id"], "name": j.get("title") or {"check": "تجربة فحص", "auto": "الاختبار الآلي"}.get(kind.split("_")[0], kind or "عملية"),
                      "site": "", "status": "running" if j["status"] == "running" else ("stopped" if j["status"] == "stopped" else "done"),
                      "started": j.get("started_at"), "ended": j.get("finished_at"), "steps": steps_from_log(lines),
                      "page": {"url": "/auto-test" if kind.startswith("auto") else "/checks", "name": "النتيجة"}, "report": None})
    return items


def _dbaudit_items():
    try:
        from web.db_audit_api import _job
    except Exception:
        return []
    if not (_job.get("running") or _job.get("log")):
        return []
    steps = []
    for l in _job.get("log", [])[-30:]:
        m = re.match(r"^(\d{2}:\d{2}:\d{2}) (.*)$", l)
        steps.append({"t": m.group(1) if m else "", "lvl": "err" if "⚠️" in l or "❌" in l else "info", "msg": (m.group(2) if m else l)[:300]})
    if _job.get("error"):
        steps.append({"t": "", "lvl": "err", "msg": _job["error"]})
    done = not _job.get("running")
    if done and _job.get("finished") and _job["finished"] < (datetime.now() - timedelta(minutes=RECENT_MIN)).isoformat():
        return []
    return [{"kind": "dbaudit", "id": "dbaudit", "name": "🗄️ فحص قاعدة البيانات", "site": "", "status": "running" if not done else ("failed" if _job.get("error") else "passed"),
             "started": _job.get("started_at") or "", "ended": _job.get("finished") or "", "steps": steps, "page": {"url": "/db-audit", "name": "فحص قاعدة البيانات"},
             "report": "/api/dbaudit/export?fmt=pdf" if done and not _job.get("error") else None}]


@bp.route("/api/tube")
@auth.login_required
def api_tube():
    items = []
    for fn in (_queue_items, _job_items, _dbaudit_items):
        try:
            items += fn()
        except Exception as e:
            items.append({"kind": "err", "id": fn.__name__, "name": "تعذّر قراءة التشغيلات", "status": "failed", "steps": [{"t": "", "lvl": "err", "msg": str(e)[:200]}]})
    order = {"running": 0, "queued": 1}
    items.sort(key=lambda x: (order.get(x["status"], 2), x.get("position") or 0, "" if x["status"] in order else (x.get("ended") or "")), reverse=False)
    fin = [x for x in items if x["status"] not in order]
    fin.sort(key=lambda x: x.get("ended") or "", reverse=True)
    items = [x for x in items if x["status"] in order] + fin
    return jsonify({"success": True, "now": datetime.now().isoformat(timespec="seconds"), "items": items,
                    "active": sum(1 for x in items if x["status"] in order)})


@bp.route("/api/tube/stop", methods=["POST"])
@auth.login_required
def api_tube_stop():
    d = request.get_json(silent=True) or {}
    kind, rid = d.get("kind"), str(d.get("id") or "")
    if kind == "queue":
        from web.queue_manager import get_manager
        qm = get_manager()
        t = qm.get_task(rid) or {}
        if t.get("status") == "queued":
            qm.remove(rid)
            return jsonify({"success": True, "msg": "اتشال من الطابور"})
        return jsonify({"success": bool(qm.stop_current(rid)), "msg": "بيقف…"})
    if kind == "job":
        from web import screens_api as J
        j = J._jobs.get(rid)
        if not j or j.get("status") != "running":
            return jsonify({"success": False, "error": "مفيش عملية شغالة"})
        j["stop_requested"] = True
        p = j.get("proc")
        if p and p.poll() is None:
            p.terminate()
        return jsonify({"success": True, "msg": "بيقف…"})
    if kind == "dbaudit":
        from web.db_audit_api import _job
        if not _job.get("running"):
            return jsonify({"success": False, "error": "مفيش فحص شغال"})
        _job["stop"] = True
        return jsonify({"success": True, "msg": "هيقف بعد الخطوة الحالية…"})
    return jsonify({"success": False, "error": "نوع غير معروف"}), 400
