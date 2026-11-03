"""
📋 تقرير التشخيص — everything the project printed, in ONE text to copy and paste to Claude:

  • the dashboard server's own console (stdout / stderr, tracebacks) — captured to data/logs/server.log
  • JavaScript errors of the dashboard pages (window.onerror / failed fetch) — data/logs/client_errors.log
  • the runs of the period: passed / failed, the error, the tail of each failed run's log, the failed rows of its detail
  • the test engine's log (errors + warnings), background jobs (discover / try), the queue, system health, leftovers
  • the setup: version, Python, folders, disk, Chrome / driver, the active test site (passwords / tokens hidden)

/diagnostics                 page: pick the period and the parts, copy all / download .txt
/api/diagnostics?hours=24    the text
/api/diag/client-error       POST from base.html when a dashboard page throws
"""
import json
import os
import platform
import re
import shutil
import sys
import threading
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from flask import Blueprint, Response, jsonify, render_template, request

from config import paths
from web import auth

bp = Blueprint("diag", __name__)
SERVER_LOG = paths.APP_LOGS_DIR / "server.log"
CLIENT_LOG = paths.APP_LOGS_DIR / "client_errors.log"
MAX_LOG = 5 * 1024 * 1024
_lock = threading.Lock()


# ---------------------------------------------------------------- capture the server console
def _append(f, text):
    try:
        with _lock:
            f.parent.mkdir(parents=True, exist_ok=True)
            if f.exists() and f.stat().st_size > MAX_LOG:
                old = f.with_suffix(f.suffix + ".1")
                if old.exists():
                    old.unlink()
                f.rename(old)
            with open(f, "a", encoding="utf-8", errors="replace") as fh:
                fh.write(text)
    except Exception:
        pass


class _Tee:
    def __init__(self, stream, tag):
        self.stream, self.tag, self.buf = stream, tag, ""

    def write(self, s):
        try:
            n = self.stream.write(s)
        except Exception:
            n = len(s)
        self.buf += s
        if "\n" in self.buf:
            lines, self.buf = self.buf.rsplit("\n", 1)
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _append(SERVER_LOG, "".join(f"{stamp} {self.tag} {_strip(x)}\n" for x in lines.split("\n") if x.strip()))
        return n

    def flush(self):
        try:
            self.stream.flush()
        except Exception:
            pass

    def __getattr__(self, k):
        return getattr(self.stream, k)


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _strip(s):
    return _ANSI.sub("", s)


def install(app):
    if not isinstance(sys.stdout, _Tee):
        sys.stdout = _Tee(sys.stdout, "OUT")
    if not isinstance(sys.stderr, _Tee):
        sys.stderr = _Tee(sys.stderr, "ERR")
    from flask import got_request_exception

    def on_error(sender, exception, **kw):
        _append(SERVER_LOG, f"{datetime.now():%Y-%m-%d %H:%M:%S} EXC {request.method} {request.path}\n"
                + "".join(traceback.format_exception(type(exception), exception, exception.__traceback__)))
    got_request_exception.connect(on_error, app, weak=False)
    app.register_blueprint(bp)


@bp.route("/api/diag/client-error", methods=["POST"])
def client_error():
    from flask import session
    if "user_id" not in session:
        return ("", 204)
    d = request.get_json(force=True, silent=True) or {}
    _append(CLIENT_LOG, json.dumps({"at": datetime.now().isoformat(timespec="seconds"), "page": str(d.get("page", ""))[:200],
                                    "msg": str(d.get("msg", ""))[:1000], "src": str(d.get("src", ""))[:300],
                                    "stack": str(d.get("stack", ""))[:2000]}, ensure_ascii=False) + "\n")
    return jsonify({"ok": True})


# ---------------------------------------------------------------- the report
SECRET_KEY_RE = re.compile(r"(?i)(password|passwd|pwd|token|secret|api[_-]?key|authorization|cookie)(\"?\s*[:=]\s*\"?)([^\s\"',;&]+)")


def _secrets():
    vals = set()
    try:
        from web import test_sites_helper as ts
        for p in ts.load_all().get("profiles", []):
            if p.get("password"):
                vals.add(p["password"])
    except Exception:
        pass
    try:
        from web import notify
        c = notify.load_config()
        for k in getattr(notify, "SECRET_KEYS", []):
            if c.get(k):
                vals.add(str(c[k]))
    except Exception:
        pass
    for k in ("LOGIN_PASSWORD", "ANTHROPIC_API_KEY", "SECRET_KEY", "TELEGRAM_TOKEN", "GITHUB_TOKEN"):
        if os.getenv(k):
            vals.add(os.getenv(k))
    try:
        from web import settings_helper
        cfg = settings_helper.load_site_config() if hasattr(settings_helper, "load_site_config") else {}
        for k, v in (cfg or {}).items():
            if re.search(r"key|token|secret|password", k, re.I) and v:
                vals.add(str(v))
    except Exception:
        pass
    return [v for v in vals if len(v) >= 4]


def mask(text, secrets):
    for v in sorted(secrets, key=len, reverse=True):
        text = text.replace(v, "••••")
    return SECRET_KEY_RE.sub(lambda m: m.group(1) + m.group(2) + "••••", text)


def _tail(f, n):
    try:
        with open(f, "r", encoding="utf-8", errors="replace") as fh:
            return fh.readlines()[-n:]
    except Exception:
        return []


def _since_lines(lines, since, pat=r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"):
    out, keep = [], False
    for ln in lines:
        m = re.match(pat, ln)
        if m:
            try:
                keep = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S") >= since
            except ValueError:
                pass
        if keep:
            out.append(ln)
    return out


def _git_version():
    try:
        head = (paths.BASE_DIR / ".git" / "HEAD").read_text().strip()
        if head.startswith("ref:"):
            ref = paths.BASE_DIR / ".git" / head.split(" ", 1)[1]
            sha = ref.read_text().strip() if ref.exists() else "?"
            return f"{head.split('/')[-1]} @ {sha[:10]}"
        return head[:10]
    except Exception:
        return "?"


def _sec(title):
    return f"\n\n{'=' * 70}\n## {title}\n{'=' * 70}\n"


SECTIONS = {
    "setup": "⚙️ الإعداد والبيئة",
    "queue": "⏳ الطابور",
    "runs": "🧪 التشغيلات (ناجح / فاشل)",
    "failed": "❌ تفاصيل التشغيلات الفاشلة (اللوج + الصفوف الفاشلة)",
    "server": "🖥️ شاشة السيرفر (كل اللي اتطبع + الأخطاء)",
    "client": "🌐 أخطاء صفحات اللوحة (JavaScript)",
    "engine": "🔧 لوج المحرك (أخطاء وتحذيرات)",
    "jobs": "🛠️ المهام في الخلفية (اكتشاف / تجربة)",
    "health": "🩺 صحة النظام والبيانات الفاضلة",
}


def build(hours=24, parts=None, max_failed=15, log_lines=120):
    parts = [p for p in (parts or SECTIONS) if p in SECTIONS]
    now = datetime.now()
    since = now - timedelta(hours=hours)
    L = [f"# تقرير تشخيص — أتمتة اختبارات ERP\nاتعمل: {now:%Y-%m-%d %H:%M:%S} · الفترة: آخر {hours} ساعة (من {since:%Y-%m-%d %H:%M})"]

    if "setup" in parts:
        L.append(_sec(SECTIONS["setup"]))
        try:
            du = shutil.disk_usage(paths.DATA_DIR)
            disk = f"{du.free / 2**30:.1f} GB فاضي من {du.total / 2**30:.1f} GB"
        except Exception:
            disk = "?"
        mem = ""
        try:
            info = dict(x.split(":", 1) for x in open("/proc/meminfo").read().splitlines() if ":" in x)
            kb = lambda k: int(info.get(k, "0 kB").split()[0])
            mem = f"{kb('MemAvailable') / 1024:.0f} MB فاضية من {kb('MemTotal') / 1024:.0f} MB"
            chromes = sum(1 for d in os.listdir("/proc") if d.isdigit() and os.path.exists(f"/proc/{d}/comm")
                          and open(f"/proc/{d}/comm").read().strip() in ("chrome", "chromedriver"))
            mem += f" · عمليات Chrome شغالة دلوقتي: {chromes}"
        except Exception:
            mem = "?"
        L += [f"الذاكرة: {mem}"]
        L += [f"النسخة: {_git_version()}", f"Python: {sys.version.split()[0]} · {platform.platform()}",
              f"المشروع: {paths.BASE_DIR}", f"البيانات: {paths.DATA_DIR} · التعريفات: {paths.DEFS_DIR}", f"الديسك: {disk}",
              f"CHROME_BIN={os.getenv('CHROME_BIN', '')} · CHROMEDRIVER_PATH={os.getenv('CHROMEDRIVER_PATH', '')} · HEADLESS={os.getenv('HEADLESS', '')}"]
        try:
            from web import test_sites_helper as ts
            d = ts.load_all()
            for p in d.get("profiles", []):
                L.append(f"موقع{' (النشط)' if p.get('id') == d.get('active_profile') else ''}: {p.get('name')} · {p.get('base_url')} · "
                         f"مستخدم {p.get('username')} · نشاط «{p.get('activity') or 'أول نشاط'}» · فرع «{p.get('branch') or 'أول فرع'}»")
        except Exception as e:
            L.append(f"المواقع: {e}")
        try:
            from web import notify
            c = notify.load_config()
            L.append(f"التنبيهات: تيليجرام={'✓' if c.get('telegram_on') else '✗'} · واتساب={'✓' if c.get('whatsapp_on') else '✗'} · "
                     f"webhook={'✓' if c.get('webhook_url') else '✗'} · وقت التنبيه={c.get('notify_on')}")
        except Exception:
            pass
        try:
            sched = json.loads(paths.SCHEDULES_FILE.read_text(encoding="utf-8")) if paths.SCHEDULES_FILE.exists() else []
            items = sched.get("schedules", sched) if isinstance(sched, dict) else sched
            L.append(f"الجدولة: {len(items)} جدول")
            for s in items[:20]:
                if isinstance(s, dict):
                    L.append(f"  - {s.get('name') or s.get('test_name') or s.get('id')} · {s.get('cron') or s.get('time') or s.get('days') or ''} · "
                             f"{'شغال' if s.get('enabled', True) else 'موقوف'}")
        except Exception as e:
            L.append(f"الجدولة: {e}")

    if "queue" in parts:
        L.append(_sec(SECTIONS["queue"]))
        try:
            from web.queue_manager import get_manager
            st = get_manager().get_status()
            for t in st.get("running_all") or []:
                L.append(f"▶ شغال: {t.get('test_name')} · {t.get('task_id')} · من {t.get('started_at')}")
            L.append(f"في الانتظار: {st.get('queue_length')}")
            for t in (st.get("queue") or [])[:20]:
                L.append(f"  - {t.get('test_name')} · {t.get('task_id')}")
        except Exception as e:
            L.append(f"الطابور: {e}")

    runs = []
    if "runs" in parts or "failed" in parts:
        try:
            from web import insights
            runs = [r for r in insights.all_runs() if r["time"] >= since]
        except Exception as e:
            L.append(f"\nالتشغيلات: {e}")
    if "runs" in parts:
        L.append(_sec(SECTIONS["runs"]))
        bad = [r for r in runs if not r["passed"]]
        L.append(f"{len(runs)} تشغيل · نجح {len(runs) - len(bad)} · فشل {len(bad)}")
        for r in runs[:200]:
            first = (r["message"] or "").strip().splitlines()[0][:220] if r["message"] else ""
            L.append(f"{'✅' if r['passed'] else '❌'} {r['time']:%m-%d %H:%M} · {r['name']} · {r['duration']:.0f}ث · {r['run_id']}"
                     + (f"\n     ↳ {first}" if first else ""))

    if "failed" in parts:
        L.append(_sec(SECTIONS["failed"]))
        from engine.check_runner import load_detail
        for r in [x for x in runs if not x["passed"]][:max_failed]:
            L.append(f"\n--- ❌ {r['name']} · {r['time']:%Y-%m-%d %H:%M} · {r['run_id']} · {r['summary'].get('test_path', '')}")
            L.append("الخطأ:\n" + (r["message"] or "—")[:3000])
            d = load_detail(r["run_id"])
            if d and d.get("detail"):
                cols = d["detail"].get("columns") or []
                for row in d["detail"].get("rows") or []:
                    if row.get("ok") is False:
                        L.append("  ✗ " + " | ".join(f"{c}: {str(v)[:3000]}" for c, v in zip(cols, row.get("cells") or [])))
            lg = paths.RUN_LOGS_DIR / f"{r['run_id']}.log"
            raw = _tail(lg, 5000)
            eng = [x for x in raw if re.match(r"\s*(\S+::\S+ )?\d\d:\d\d:\d\d \| ", _strip(x)) or re.match(r"\s*(E |FAILED|Exit code|Duration|=====)", _strip(x))]
            tail = (eng or raw)[-log_lines:]
            if tail:
                L.append(f"آخر {len(tail)} سطر من اللوج:")
                L += ["  " + _strip(x.rstrip()) for x in tail]

    if "server" in parts:
        L.append(_sec(SECTIONS["server"]))
        lines = _since_lines(_tail(SERVER_LOG.with_suffix(".log.1"), 3000) + _tail(SERVER_LOG, 6000), since)
        errs = [x for x in lines if re.search(r" ERR | EXC |Traceback|Error|Exception|❌|\b50\d\b", x)]
        L.append(f"{len(lines)} سطر في الفترة · منهم {len(errs)} سطر خطأ")
        noisy = re.compile(r'"(GET|POST) /(static|api/(queue|status|live|screens/jobs|runs/active)|favicon)')
        quiet = [x for x in lines if not noisy.search(x)]
        L += [x.rstrip() for x in quiet[-600:]]

    if "client" in parts:
        L.append(_sec(SECTIONS["client"]))
        n = 0
        for ln in _tail(CLIENT_LOG, 400):
            try:
                d = json.loads(ln)
            except Exception:
                continue
            if d.get("at", "") >= since.isoformat(timespec="seconds"):
                n += 1
                L.append(f"{d['at']} · {d.get('page')} · {d.get('msg')} · {d.get('src')}\n   {d.get('stack', '')[:600]}")
        if not n:
            L.append("مفيش")

    if "engine" in parts:
        L.append(_sec(SECTIONS["engine"]))
        files = sorted(paths.APP_LOGS_DIR.glob("test_*.log"))[-3:]
        got = []
        for f in files:
            for ln in _since_lines(_tail(f, 20000), since):
                if re.search(r"\| (ERROR|WARNING|CRITICAL) ", ln):
                    got.append(ln.rstrip())
        L.append(f"{len(got)} سطر (أخطاء + تحذيرات)")
        L += got[-400:]

    if "jobs" in parts:
        L.append(_sec(SECTIONS["jobs"]))
        jd = paths.JOBS_DIR
        logs = sorted((f for f in jd.glob("*.log") if datetime.fromtimestamp(f.stat().st_mtime) >= since), key=lambda f: f.stat().st_mtime)[-10:] if jd.exists() else []
        if not logs:
            L.append("مفيش")
        for f in logs:
            res = f.with_suffix(".json")
            ok = ""
            try:
                j = json.loads(res.read_text(encoding="utf-8"))
                ok = "✅" if j.get("success") else "❌ " + str(j.get("error", ""))[:400]
            except Exception:
                pass
            L.append(f"\n--- {f.name} · {datetime.fromtimestamp(f.stat().st_mtime):%m-%d %H:%M} · {ok}")
            L += ["  " + _strip(x.rstrip()) for x in _tail(f, 60)]

    if "health" in parts:
        L.append(_sec(SECTIONS["health"]))
        try:
            from engine import health
            for f in sorted(health.STATE.glob("health_*.json")):
                d = json.loads(f.read_text(encoding="utf-8"))
                L.append(f"{d.get('base_url')} ({d.get('activity') or 'أول نشاط'} / {d.get('branch') or 'أول فرع'}) · آخر فحص {d.get('at')} · "
                         f"{len(d.get('broken') or {})} بايظة من {d.get('total')} · {len(d.get('changes') or [])} تغيير")
                for p, b in list((d.get("broken") or {}).items())[:60]:
                    L.append(f"  ✗ {b.get('module')} / {b.get('name')} · {p} · {b.get('why')}")
                for c in (d.get("changes") or [])[:40]:
                    L.append(f"  🔀 {c['path']} · {c['what']}")
        except Exception as e:
            L.append(f"صحة النظام: {e}")
        try:
            from engine import cleanup
            items = cleanup.load_all()
            L.append(f"سجلات اختبار فاضلة: {len(items)}")
            L += [f"  - {x['screen']} رقم {x['no']} · {x['site']} · {x['why']}" for x in items[:30]]
        except Exception:
            pass

    return mask("\n".join(L), _secrets())


@bp.route("/diagnostics")
@auth.login_required
def page():
    return render_template("diagnostics.html", sections=SECTIONS)


@bp.route("/api/diagnostics")
@auth.login_required
def api():
    hours = max(1, min(24 * 30, int(request.args.get("hours", 24) or 24)))
    parts = [p for p in (request.args.get("parts") or "").split(",") if p] or None
    text = build(hours, parts, max_failed=int(request.args.get("failed", 15) or 15), log_lines=int(request.args.get("lines", 120) or 120))
    if request.args.get("download"):
        return Response(text, mimetype="text/plain; charset=utf-8",
                        headers={"Content-Disposition": f"attachment; filename=diagnostics_{datetime.now():%Y%m%d_%H%M}.txt"})
    return jsonify({"success": True, "text": text, "chars": len(text)})
