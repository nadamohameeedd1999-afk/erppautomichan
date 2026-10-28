"""
All file locations in one place.

Code lives in the repo; everything the program WRITES lives under DATA_DIR (default: ./data).
On a server, mount ONE volume on DATA_DIR and nothing is ever lost on redeploy.

data/
  runs/        results/ (summary_*.json, raw_*.json)  logs/ (one log per run)  screenshots/  allure-results/  allure-report/
  settings/    users.json  site_config.json  email_config.json  slack_config.json  test_sites.json  tunnel_config.json  secret_key
  state/       session_*.json  screen_jobs/  chrome_profile/
  logs/        daily app/test logs (loguru)
  schedules.json
  backups/     backup_YYYYmmdd_HHMM.zip (automatic + manual)
  history/     older versions of every saved file (last 10 each)
  trash/       anything deleted from the dashboard

Test definitions (screens / scenarios) stay in config/ so they are versioned in git.
Set DEFS_DIR to move them too (e.g. DEFS_DIR=/app/data/defs on a server).
"""
import os
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.getenv("DATA_DIR") or (BASE_DIR / "data")).resolve()

RUNS_DIR = DATA_DIR / "runs"
RESULTS_DIR = RUNS_DIR / "results"
RUN_LOGS_DIR = RUNS_DIR / "logs"
SCREENSHOTS_DIR = RUNS_DIR / "screenshots"
ALLURE_RESULTS_DIR = RUNS_DIR / "allure-results"
ALLURE_REPORT_DIR = RUNS_DIR / "allure-report"

SETTINGS_DIR = DATA_DIR / "settings"
STATE_DIR = DATA_DIR / "state"
JOBS_DIR = STATE_DIR / "screen_jobs"
CHROME_PROFILE_DIR = STATE_DIR / "chrome_profile"
APP_LOGS_DIR = DATA_DIR / "logs"
BACKUPS_DIR = DATA_DIR / "backups"
HISTORY_DIR = DATA_DIR / "history"
TRASH_DIR = DATA_DIR / "trash"
SCHEDULES_FILE = Path(os.getenv("SCHEDULES_FILE") or (DATA_DIR / "schedules.json"))

DEFS_DIR = Path(os.getenv("DEFS_DIR") or (BASE_DIR / "config")).resolve()
SCREENS_DIR = DEFS_DIR / "screens"
SCENARIOS_DIR = DEFS_DIR / "scenarios"


def _seed_defs():
    """DEFS_DIR outside the repo (e.g. /app/data/defs on a server): copy the repo's
    screen/scenario definitions that are missing there. Never overwrites."""
    repo = (BASE_DIR / "config").resolve()
    if DEFS_DIR == repo:
        return
    import shutil
    for sub in ("screens", "scenarios", "checks"):
        for f in (repo / sub).glob("*.json"):
            dest = DEFS_DIR / sub / f.name
            if not dest.exists():
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dest)
                except Exception:
                    pass


def settings_file(name: str) -> Path:
    """data/settings/<name> (users.json, email_config.json, ...)"""
    return SETTINGS_DIR / name


for _d in (RESULTS_DIR, RUN_LOGS_DIR, SCREENSHOTS_DIR, SETTINGS_DIR, STATE_DIR, APP_LOGS_DIR,
           BACKUPS_DIR, HISTORY_DIR, TRASH_DIR, SCREENS_DIR, SCENARIOS_DIR):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
#  One-time migration from the old scattered locations (copy, never delete)
# ---------------------------------------------------------------------------
_OLD = [
    (BASE_DIR / "reports" / "results", RESULTS_DIR),
    (BASE_DIR / "reports" / "logs", RUN_LOGS_DIR),
    (BASE_DIR / "reports" / "screenshots", SCREENSHOTS_DIR),
    (BASE_DIR / "logs", APP_LOGS_DIR),
]
_OLD_FILES = [
    (BASE_DIR / "config" / "users.json", settings_file("users.json")),
    (BASE_DIR / "config" / "site_config.json", settings_file("site_config.json")),
    (BASE_DIR / "config" / "email_config.json", settings_file("email_config.json")),
    (BASE_DIR / "config" / "slack_config.json", settings_file("slack_config.json")),
    (BASE_DIR / "config" / "test_sites.json", settings_file("test_sites.json")),
    (BASE_DIR / "config" / "tunnel_config.json", settings_file("tunnel_config.json")),
    (BASE_DIR / "config" / "schedules" / "schedules.json", SCHEDULES_FILE),
]


def migrate_legacy(verbose=True):
    """Copy data from the old folders into data/ the first time. Old files are left in place."""
    marker = DATA_DIR / ".migrated"
    if marker.exists():
        return 0
    copied = 0
    for src, dst in _OLD_FILES:
        try:
            if src.exists() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
        except Exception:
            pass
    for src, dst in _OLD:
        try:
            if src.exists() and src.is_dir():
                for f in src.iterdir():
                    if f.is_file() and not (dst / f.name).exists():
                        shutil.copy2(f, dst / f.name)
                        copied += 1
        except Exception:
            pass
    try:
        marker.write_text("ok", encoding="utf-8")
    except Exception:
        pass
    if verbose and copied:
        print(f"[paths] نقلت {copied} ملف من الأماكن القديمة إلى {DATA_DIR}", flush=True)
    return copied


migrate_legacy()

try:
    _seed_defs()
except Exception:
    pass
