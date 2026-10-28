"""
Backups (النسخ الاحتياطي) of everything the program saves.

A backup = one zip in data/backups/ with:
  data/settings/*, data/schedules.json, data/runs/results/*, data/runs/logs/*,
  test definitions (config/screens, config/scenarios), and screenshots of the last 3 days.

Automatic: every day at BACKUP_HOUR (default 03:00) + at start-up if the last one is older than a day.
Keeps the last BACKUP_KEEP automatic backups (default 14); manual ones are kept.
"""
import os
import shutil
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from config import paths

KEEP_AUTO = int(os.getenv("BACKUP_KEEP", "14"))
BACKUP_HOUR = int(os.getenv("BACKUP_HOUR", "3"))
SHOT_DAYS = int(os.getenv("BACKUP_SCREENSHOT_DAYS", "3"))


def _items(full=False):
    """(path on disk, name inside the zip)"""
    out = []
    for root, arc in ((paths.SETTINGS_DIR, "data/settings"), (paths.RESULTS_DIR, "data/runs/results"),
                      (paths.RUN_LOGS_DIR, "data/runs/logs"), (paths.SCREENS_DIR, "defs/screens"),
                      (paths.SCENARIOS_DIR, "defs/scenarios"), (paths.DEFS_DIR / "checks", "defs/checks"), (paths.DATA_DIR / "datasets", "data/datasets")):
        if root.exists():
            for f in root.rglob("*"):
                if f.is_file() and not f.name.endswith(".tmp"):
                    out.append((f, f"{arc}/{f.relative_to(root).as_posix()}"))
    if paths.SCHEDULES_FILE.exists():
        out.append((paths.SCHEDULES_FILE, "data/schedules.json"))
    if paths.SCREENSHOTS_DIR.exists():
        cutoff = time.time() - SHOT_DAYS * 86400
        for f in paths.SCREENSHOTS_DIR.glob("*.png"):
            if full or f.stat().st_mtime >= cutoff:
                out.append((f, f"data/runs/screenshots/{f.name}"))
    return out


def create(kind="manual", full=False):
    paths.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"backup_{datetime.now():%Y%m%d_%H%M%S}_{kind}.zip"
    dest = paths.BACKUPS_DIR / name
    tmp = dest.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for f, arc in _items(full):
            try:
                z.write(f, arc)
            except Exception:
                pass
        z.writestr("BACKUP_INFO.txt", f"created: {datetime.now().isoformat(timespec='seconds')}\nkind: {kind}\n")
    tmp.replace(dest)
    _prune()
    return info(dest)


def info(p: Path):
    st = p.stat()
    kind = p.stem.split("_")[-1] if p.stem.count("_") >= 3 else "manual"
    return {"name": p.name, "size_kb": round(st.st_size / 1024), "kind": kind,
            "created": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes")}


def list_all():
    if not paths.BACKUPS_DIR.exists():
        return []
    return [info(p) for p in sorted(paths.BACKUPS_DIR.glob("backup_*.zip"), reverse=True)]


def path_of(name):
    p = (paths.BACKUPS_DIR / name).resolve()
    if p.parent != paths.BACKUPS_DIR.resolve() or not p.exists() or p.suffix != ".zip":
        return None
    return p


def _prune():
    autos = sorted(paths.BACKUPS_DIR.glob("backup_*_auto.zip"), reverse=True)
    for p in autos[KEEP_AUTO:]:
        try:
            p.unlink()
        except Exception:
            pass


def restore(zip_path):
    """Restore a backup. Takes a safety backup of the current state first."""
    safety = create("before-restore")
    targets = {"data/settings/": paths.SETTINGS_DIR, "data/runs/results/": paths.RESULTS_DIR,
               "data/runs/logs/": paths.RUN_LOGS_DIR, "data/runs/screenshots/": paths.SCREENSHOTS_DIR,
               "defs/screens/": paths.SCREENS_DIR, "defs/scenarios/": paths.SCENARIOS_DIR,
               "defs/checks/": paths.DEFS_DIR / "checks", "data/datasets/": paths.DATA_DIR / "datasets"}
    n = 0
    with zipfile.ZipFile(zip_path) as z:
        for member in z.namelist():
            if member.endswith("/") or ".." in member:
                continue
            if member == "data/schedules.json":
                dest = paths.SCHEDULES_FILE
            else:
                pre = next((k for k in targets if member.startswith(k)), None)
                if not pre:
                    continue
                dest = targets[pre] / member[len(pre):]
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(member) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
            n += 1
    # generated test files for restored definitions
    try:
        from engine import screen_config, scenario_config
        screen_config.sync_stubs()
        scenario_config.sync_stubs()
    except Exception:
        pass
    return {"restored_files": n, "safety_backup": safety["name"]}


# ---------------- automatic ----------------
_last_check = {"t": 0}


def auto_tick(now=None):
    """Called by the scheduler loop every ~20s."""
    if time.time() - _last_check["t"] < 300:
        return
    _last_check["t"] = time.time()
    autos = sorted(paths.BACKUPS_DIR.glob("backup_*_auto.zip"), reverse=True) if paths.BACKUPS_DIR.exists() else []
    newest = datetime.fromtimestamp(autos[0].stat().st_mtime) if autos else None
    now = now or datetime.now()
    due_daily = now.hour == BACKUP_HOUR and (not newest or newest.date() < now.date())
    overdue = not newest or (datetime.now() - newest) > timedelta(hours=26)
    if due_daily or overdue:
        try:
            b = create("auto")
            print(f"[backup] 💾 {b['name']} ({b['size_kb']} KB)", flush=True)
        except Exception as e:
            print(f"[backup] error: {e}", flush=True)


# ---------------- trash ----------------
def trash_list():
    out = []
    if paths.TRASH_DIR.exists():
        for f in sorted(paths.TRASH_DIR.rglob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.is_file():
                rel = f.relative_to(paths.TRASH_DIR).as_posix()
                out.append({"id": rel, "name": f.name, "day": rel.split("/")[0],
                            "where": "/".join(rel.split("/")[1:-1]),
                            "deleted": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="minutes")})
    return out[:200]


def trash_restore(rel):
    src = (paths.TRASH_DIR / rel).resolve()
    if paths.TRASH_DIR.resolve() not in src.parents or not src.exists():
        return False
    parts = rel.split("/")[1:]                 # drop the date folder
    sub = "/".join(parts)
    if sub.startswith("screens/"):
        dest = paths.SCREENS_DIR / sub[len("screens/"):]
    elif sub.startswith("scenarios/"):
        dest = paths.SCENARIOS_DIR / sub[len("scenarios/"):]
    else:
        dest = paths.DATA_DIR / sub
    if dest.exists():
        dest = dest.with_name(f"{dest.stem}_restored{dest.suffix}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    try:
        from engine import screen_config, scenario_config
        screen_config.sync_stubs()
        scenario_config.sync_stubs()
    except Exception:
        pass
    return True
