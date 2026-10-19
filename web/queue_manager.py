"""
Queue Manager - Manages running and queued tests
+ Full logging of stdout/stderr
+ History of completed tasks
"""
import threading
import subprocess
import sys
import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "reports" / "logs"
RESULTS_DIR = BASE_DIR / "reports" / "results"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


class QueueManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.current_task = None
        self.queue = []
        self.process = None
        self.stopped = False
        self.current_log_file = None
        # ← جديد: تاريخ آخر 100 مهمة
        self.history = {}

    def is_running(self):
        with self.lock:
            return self.current_task is not None

    def get_status(self):
        with self.lock:
            return {
                "running": self.current_task,
                "queue": list(self.queue),
                "queue_length": len(self.queue),
            }

    def get_task(self, task_id):
        """يرجع مهمة من الحالي/الطابور/التاريخ"""
        with self.lock:
            # الحالي
            if self.current_task and self.current_task.get("task_id") == task_id:
                return dict(self.current_task)
            # الطابور
            for t in self.queue:
                if t.get("task_id") == task_id:
                    return dict(t)
            # التاريخ
            if task_id in self.history:
                return dict(self.history[task_id])
        return None

    def add(self, task_id, test_path, test_name, repeat=1):
        task = {
            "task_id": task_id,
            "test_path": test_path,
            "test_name": test_name,
            "repeat": repeat,
            "added_at": datetime.now().isoformat(),
            "status": "queued",
        }

        with self.lock:
            if self.current_task is None:
                self.current_task = task
                self.stopped = False
                should_start = True
            else:
                self.queue.append(task)
                should_start = False

        if should_start:
            self._run_task(task)
            return {"queued": False, "position": 0}
        else:
            position = len(self.queue)
            return {"queued": True, "position": position}

    def stop_current(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                self.stopped = True
                try:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=5)
                    except Exception:
                        self.process.kill()
                    return True
                except Exception as e:
                    print(f"[stop_current] error: {e}")
                    return False
        return False

    def _run_task(self, task):
        thread = threading.Thread(target=self._execute, args=(task,), daemon=True)
        thread.start()

    def _execute(self, task):
        task_id = task["task_id"]
        log_file = LOGS_DIR / f"{task_id}.log"
        self.current_log_file = log_file
        start_time = datetime.now()

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
                lf.write(f"TEST_REPEAT: {env['TEST_REPEAT']}\n")
                lf.flush()

                self.process = subprocess.Popen(
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

                task["pid"] = self.process.pid
                task["status"] = "running"
                task["started_at"] = start_time.isoformat()
                lf.write(f"PID: {self.process.pid}\n\n")
                lf.flush()

                for line in self.process.stdout:
                    lf.write(line)
                    lf.flush()
                    print(f"[{task_id}] {line}", end="", flush=True)

                self.process.wait()
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()

                lf.write(f"\n===== END {end_time.isoformat()} =====\n")
                lf.write(f"Exit code: {self.process.returncode}\n")
                lf.write(f"Duration: {duration:.1f}s\n")

            # ===== تحديد الحالة النهائية =====
            if self.stopped:
                final_status = "stopped"
                self.stopped = False
            elif self.process.returncode == 0:
                final_status = "completed"
            else:
                final_status = "failed"

            task["status"] = final_status
            task["exit_code"] = self.process.returncode
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
            self.process = None
            self._next()

    def _next(self):
        next_task = None
        with self.lock:
            if self.queue:
                next_task = self.queue.pop(0)
                self.current_task = next_task
                self.stopped = False
            else:
                self.current_task = None

        if next_task:
            self._run_task(next_task)

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