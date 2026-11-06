"""
The server's disk (Railway volume) fills with screenshots, Allure files and logs -> saving anything fails («500»).
free_space(): before each test, when free space is low, the OLDEST screenshots / allure files / run logs / job logs
are deleted until there is room again. Results (pass / fail, messages), settings, tests and backups are never touched.
"""
import shutil
import time

from config import paths

MIN_FREE_MB = 300
MIN_FREE_PCT = 0.12


def _free():
    try:
        u = shutil.disk_usage(paths.DATA_DIR)
        return u.free, u.total
    except Exception:
        return None, None


def low():
    free, total = _free()
    if free is None:
        return False
    return free < MIN_FREE_MB * 2**20 or (total and free / total < MIN_FREE_PCT)


def free_space(log=print):
    if not low():
        return 0
    dirs = [paths.SCREENSHOTS_DIR, paths.ALLURE_RESULTS_DIR, paths.ALLURE_REPORT_DIR, paths.JOBS_DIR, paths.RUN_LOGS_DIR, paths.TRASH_DIR]
    files = []
    for d in dirs:
        if d.exists():
            for f in d.rglob("*"):
                try:
                    if f.is_file():
                        files.append((f.stat().st_mtime, f))
                except Exception:
                    pass
    files.sort()
    removed, cutoff = 0, time.time() - 3600           # never what the last hour produced
    for mt, f in files:
        if mt > cutoff or not low():
            break
        try:
            f.unlink()
            removed += 1
        except Exception:
            pass
    if removed:
        free, _ = _free()
        log(f"[disk] 🧹 removed {removed} old screenshots / logs — free now {free / 2**20:.0f} MB")
    return removed
