"""
Queue Manager - Manages running and queued tests
+ Full logging of stdout/stderr
+ History of completed tasks
"""
import os
import re
import threading
import subprocess
import sys
import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
from config import paths  # noqa: E402
LOGS_DIR = paths.RUN_LOGS_DIR
RESULTS_DIR = paths.RESULTS_DIR
LOGS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# إعادة تلقائية مرة واحدة لو الفشل شكله من البيئة (بطء/انقطاع/المتصفح وقع) مش من الشاشة نفسها
AUTO_RETRY = os.getenv("AUTO_RETRY", "1") not in ("0", "false", "False")
INFRA_PATTERNS = re.compile(
    r"TimeoutException|WebDriverException|InvalidSessionIdException|SessionNotCreated|"
    r"chrome not reachable|disconnected|tab crashed|session deleted|ERR_CONNECTION|ERR_NAME_NOT_RESOLVED|ERR_TIMED_OUT|"
    r"net::ERR_|Read timed out|Max retries exceeded|ConnectionResetError|RemoteDisconnected",
    re.I)


class QueueManager:
    """Runs queued tests. Several at the same time when «workers» > 1 (مركز التشغيل),
    but never two tests of the same screen together (they would see each other's new rows)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.queue = []
        self.running = {}          # task_id -> task (in start order)
        self.procs = {}            # task_id -> Popen
        self.stopped_ids = set()
        self.history = {}

    # ----- settings -----
    @staticmethod
    def workers():
        from config.storage import load_json
        try:
            n = int((load_json(paths.settings_file("runs.json"), {}) or {}).get("workers") or os.getenv("QUEUE_WORKERS", "1"))
        except ValueError:
            n = 1
        return max(1, min(4, n))

    @staticmethod
    def set_workers(n):
        from config.storage import save_json
        n = max(1, min(4, int(n)))
        save_json(paths.settings_file("runs.json"), {"workers": n})
        return n

    # ----- compatibility: «the» running task = the oldest one -----
    @property
    def current_task(self):
        return next(iter(self.running.values()), None)

    def is_running(self):
        with self.lock:
            return bool(self.running)

    def get_status(self):
        with self.lock:
            run = [dict(t) for t in self.running.values()]
            return {
                "running": run[0] if run else None,
                "running_all": run,
                "workers": self.workers(),
                "queue": list(self.queue),
                "queue_length": len(self.queue),
            }

    def get_task(self, task_id):
        """يرجع مهمة من الشغال/الطابور/التاريخ"""
        with self.lock:
            if task_id in self.running:
                return dict(self.running[task_id])
            for t in self.queue:
                if t.get("task_id") == task_id:
                    return dict(t)
            if task_id in self.history:
                return dict(self.history[task_id])
        return None

    def add(self, task_id, test_path, test_name, repeat=1, source="manual", front=False, extra=None):
        task = {
            "task_id": task_id,
            "test_path": test_path,
            "test_name": test_name,
            "repeat": repeat,
            "source": source,            # manual / schedule / retry / rerun / hook
            "added_at": datetime.now().isoformat(),
            "status": "queued",
            **(extra or {}),
        }
        with self.lock:
            if front:
                self.queue.insert(0, task)
            else:
                self.queue.append(task)
        started = self._pump()
        if task_id in started:
            return {"queued": False, "position": 0}
        with self.lock:
            pos = next((i + 1 for i, t in enumerate(self.queue) if t["task_id"] == task_id), len(self.queue))
        return {"queued": True, "position": pos}

    @staticmethod
    def _screen(task):
        try:
            from web.insights import test_key
            return test_key(task.get("test_path", ""))
        except Exception:
            return task.get("test_path", "")

    def _pump(self):
        """start queued tasks while there are free workers"""
        started = []
        with self.lock:
            busy = {self._screen(t) for t in self.running.values()}
            i = 0
            while len(self.running) < self.workers() and i < len(self.queue):
                t = self.queue[i]
                if self._screen(t) in busy:          # same screen already running -> wait
                    i += 1
                    continue
                self.queue.pop(i)
                self.running[t["task_id"]] = t
                busy.add(self._screen(t))
                started.append(t)
        for t in started:
            threading.Thread(target=self._execute, args=(t,), daemon=True).start()
        return [t["task_id"] for t in started]

    # ---------- queue editing ----------
    def remove(self, task_id):
        with self.lock:
            before = len(self.queue)
            self.queue = [t for t in self.queue if t.get("task_id") != task_id]
            return len(self.queue) < before

    def move(self, task_id, delta):
        with self.lock:
            i = next((k for k, t in enumerate(self.queue) if t.get("task_id") == task_id), None)
            if i is None:
                return False
            j = max(0, min(len(self.queue) - 1, i + int(delta)))
            self.queue.insert(j, self.queue.pop(i))
            return True

    def clear(self):
        with self.lock:
            n = len(self.queue)
            self.queue = []
            return n

    def recent_history(self, limit=30):
        with self.lock:
            items = sorted(self.history.values(), key=lambda t: t.get("completed_at") or "", reverse=True)
            return [dict(t) for t in items[:limit]]

    def _should_retry(self, task, log_file):
        if not AUTO_RETRY or task.get("source") == "retry" or task.get("retried"):
            return None
        try:
            tail = log_file.read_text(encoding="utf-8", errors="replace")[-20000:]
        except Exception:
            return None
        m = INFRA_PATTERNS.search(tail)
        return m.group(0) if m else None

    def stop_current(self, task_id=None):
        """stop one running task (or all of them)"""
        stopped = False
        with self.lock:
            items = [(k, p) for k, p in self.procs.items() if task_id in (None, k)]
        for k, p in items:
            if p.poll() is None:
                self.stopped_ids.add(k)
                try:
                    p.terminate()
                    try:
                        p.wait(timeout=5)
                    except Exception:
                        p.kill()
                    stopped = True
                except Exception as e:
                    print(f"[stop] error: {e}")
        return stopped

    def _execute(self, task):
        task_id = task["task_id"]
        log_file = LOGS_DIR / f"{task_id}.log"
        start_time = datetime.now()
        end_time, duration, proc = start_time, 0.0, None

        try:
            cmd = [
                sys.executable, "-m", "pytest",
                task["test_path"],
                "-v",
                "-s",
                "--json-report",
                f"--json-report-file={RESULTS_DIR}/raw_{task_id}.json",
                "--tb=long",
                "--log-cli-level=INFO",
            ]

            with open(log_file, "w", encoding="utf-8") as lf:
                lf.write(f"===== START {start_time.isoformat()} =====\n")
                lf.write(f"CMD: {' '.join(cmd)}\n")
                lf.write(f"CWD: {BASE_DIR}\n")
                lf.write("=" * 60 + "\n\n")
                lf.flush()

                # ← مهم: نمرر environment مع UTF-8
                import os
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                env["PYTHONUTF8"] = "1"
                env["TEST_REPEAT"] = str(task.get("repeat", 1) or 1)
                env["RUN_ID"] = task_id                          # advanced tests save their detail table under this id
                if task.get("site"):
                    env["SITE_PROFILE"] = str(task["site"])      # run on another test site (Settings → المواقع)
                    lf.write(f"SITE: {task.get('site_name') or task['site']}\n")
                lf.write(f"TEST_REPEAT: {env['TEST_REPEAT']}\n")
                lf.flush()

                proc = subprocess.Popen(
                    cmd,
                    cwd=str(BASE_DIR),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    env=env,
                )

                with self.lock:
                    self.procs[task_id] = proc
                task["pid"] = proc.pid
                task["status"] = "running"
                task["started_at"] = start_time.isoformat()
                lf.write(f"PID: {proc.pid}\n\n")
                lf.flush()

                for line in proc.stdout:
                    lf.write(line)
                    lf.flush()
                    print(f"[{task_id}] {line}", end="", flush=True)

                proc.wait()
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()

                lf.write(f"\n===== END {end_time.isoformat()} =====\n")
                lf.write(f"Exit code: {proc.returncode}\n")
                lf.write(f"Duration: {duration:.1f}s\n")

            # ===== تحديد الحالة النهائية =====
            if task_id in self.stopped_ids:
                final_status = "stopped"
                self.stopped_ids.discard(task_id)
            elif proc.returncode == 0:
                final_status = "completed"
            else:
                final_status = "failed"

            retry_reason = self._should_retry(task, log_file) if final_status == "failed" else None
            if retry_reason:
                task["auto_retry"] = f"{task_id}_r"
                task["retry_reason"] = retry_reason
            try:
                summ = self._write_summary({**task, "status": final_status}, start_time, end_time, duration,
                                           proc.returncode)
                if final_status != "stopped":
                    from web import notify
                    notify.notify_async(summ)
            except Exception as e:
                print(f"[{task_id}] summary error: {e}", flush=True)
            task["status"] = final_status
            task["exit_code"] = proc.returncode
            task["completed_at"] = end_time.isoformat()
            task["duration_seconds"] = round(duration, 1)

            # نحفظ في التاريخ
            with self.lock:
                self.history[task_id] = dict(task)
                # نحدّ الحد الأقصى بـ 100
                if len(self.history) > 100:
                    oldest = sorted(self.history.keys())[:20]
                    for k in oldest:
                        del self.history[k]

        except Exception as e:
            task["status"] = "error"
            task["error"] = str(e)[:500]
            try:
                with open(log_file, "a", encoding="utf-8") as lf:
                    lf.write(f"\n\n[FATAL ERROR] {str(e)}\n")
            except Exception:
                pass
            with self.lock:
                self.history[task_id] = dict(task)

        finally:
            with self.lock:
                self.procs.pop(task_id, None)
                self.running.pop(task_id, None)
            if task.get("auto_retry"):
                # إعادة مرة واحدة أول الطابور
                self.add(task["auto_retry"], task["test_path"], f"{task.get('test_name', '')} (إعادة تلقائية)",
                         repeat=task.get("repeat", 1), source="retry", front=True,
                         extra={"retry_of": task_id, "retried": True})
            self._pump()

    def _next(self):
        self._pump()

    def read_log(self, task_id, max_lines=200):
        log_file = LOGS_DIR / f"{task_id}.log"
        if not log_file.exists():
            return {"success": False, "error": "Log not found", "task_id": task_id}

        try:
            with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            tail = lines[-max_lines:] if len(lines) > max_lines else lines
            return {
                "success": True,
                "task_id": task_id,
                "total_lines": len(lines),
                "lines": [l.rstrip() for l in tail],
                "log_file": str(log_file),
            }
        except Exception as e:
            return {"success": False, "error": str(e)[:200]}

    def _write_summary(self, task, start_time, end_time, duration, exit_code):
        """يكتب data/runs/results/summary_<task_id>.json — ده اللي صفحة التقارير بتقراه."""
        task_id = task["task_id"]
        raw = RESULTS_DIR / f"raw_{task_id}.json"
        data = {"summary": {}, "tests": []}
        if raw.exists():
            try:
                with open(raw, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        s = data.get("summary", {}) or {}

        def _message(t):
            for phase in ("setup", "call", "teardown"):
                ph = t.get(phase) or {}
                if ph.get("outcome") in ("failed", "error"):
                    crash = ph.get("crash") or {}
                    msg = crash.get("message") or (ph.get("longrepr") or "")
                    return str(msg)[-800:]
            return ""

        summary = {
            "run_id": task_id,
            "timestamp": start_time.strftime("%Y%m%d_%H%M%S"),
            "started_at": start_time.isoformat(timespec="seconds"),
            "finished_at": end_time.isoformat(timespec="seconds"),
            "test_path": task.get("test_path", ""),
            "test_name": task.get("test_name", ""),
            "repeat": task.get("repeat", 1),
            "source": task.get("source", "manual"),
            "retry_of": task.get("retry_of"),
            "auto_retry": task.get("auto_retry"),
            "retry_reason": task.get("retry_reason"),
            "site": task.get("site") or "",
            "site_name": task.get("site_name") or "",
            "schedule_id": task.get("schedule_id"),
            "duration_seconds": round(duration, 2),
            "total": s.get("total", 0),
            "passed": s.get("passed", 0),
            "failed": s.get("failed", 0),
            "errors": s.get("error", 0),
            "skipped": s.get("skipped", 0),
            "exit_code": exit_code,
            "status": task.get("status"),
            "tests": [
                {
                    "name": t["nodeid"].split("::")[-1],
                    "file": t["nodeid"].split("::")[0],
                    "outcome": t.get("outcome"),
                    "duration": round(sum((t.get(p) or {}).get("duration", 0) for p in ("setup", "call", "teardown")), 2),
                    "message": _message(t),
                }
                for t in data.get("tests", [])
            ],
        }
        # pytest crashed before running anything (no json report): still record the run as failed
        if not summary["total"] and exit_code not in (0, None):
            summary["errors"] = 1
            summary["total"] = 1
        with open(RESULTS_DIR / f"summary_{task_id}.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        return summary

    def read_summary(self, task_id):
        """يقرأ ملف summary JSON لو موجود"""
        summary_file = RESULTS_DIR / f"summary_{task_id}.json"
        if not summary_file.exists():
            return None
        try:
            with open(summary_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None


_manager = None


def get_manager():
    global _manager
    if _manager is None:
        _manager = QueueManager()
    return _manager