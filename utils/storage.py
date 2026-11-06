"""
🗄️ مساحة السيرفر — what fills the server's disk, and a safe cleanup.

Never touched: test results (pass / fail, messages, timings), settings, test definitions, the system-health state, recipes.
Cleaned (only what is older than N days, never the last hour):
  screenshots · Allure files (raw results + the generated report) · run logs · background job logs · Chrome's cache
  (inside the browser profile — the sign-in stays) · old automatic backups (the last N kept) · trash
Automatic: every few hours (and before a test when the disk is low) the same cleanup runs with the saved policy.
"""
import json
import os
import shutil
import time
from pathlib import Path

from config import paths

POLICY_FILE = paths.SETTINGS_DIR / "storage.json"
DEFAULT_POLICY = {"auto": True, "days": 7, "keep_backups": 10, "cats": ["screenshots", "allure", "logs", "jobs", "chrome_cache", "trash"]}
CHROME_CACHE = ("Cache", "Code Cache", "GPUCache", "ShaderCache", "GrShaderCache", "DawnCache", "DawnGraphiteCache",
                "Service Worker/CacheStorage", "Service Worker/ScriptCache", "component_crx_cache", "optimization_guide_model_store")


def _cats():
    prof = paths.CHROME_PROFILE_DIR
    return {
        "screenshots": ("📸 صور الاختبارات (سكرين شوت)", [paths.SCREENSHOTS_DIR]),
        "allure": ("📊 ملفات Allure (نتايج خام + التقرير المتولد)", [paths.ALLURE_RESULTS_DIR, paths.ALLURE_REPORT_DIR]),
        "logs": ("📜 لوجات التشغيلات (السطور الكاملة لكل اختبار)", [paths.RUN_LOGS_DIR]),
        "jobs": ("🛠️ لوجات التجربة والاكتشاف", [paths.JOBS_DIR]),
        "chrome_cache": ("🌐 كاش متصفح الاختبارات (الدخول المحفوظ بيفضل)", [d for d in (prof.rglob("*") if prof.exists() else [])
                                                                           if d.is_dir() and any(str(d).endswith(c) for c in CHROME_CACHE)]),
        "backups": ("💾 النسخ الاحتياطية التلقائية القديمة", [paths.BACKUPS_DIR]),
        "trash": ("🗑️ سلة المحذوفات", [paths.TRASH_DIR]),
    }


KEEP = {"results": ("✅ نتايج الاختبارات (ناجح / فاشل والرسائل) — مش بتتمسح", [paths.RESULTS_DIR]),
        "settings": ("⚙️ الإعدادات والاختبارات المتعرفة — مش بتتمسح", [paths.SETTINGS_DIR, paths.DEFS_DIR]),
        "state": ("🩺 صحة النظام والوصفات — مش بتتمسح", [paths.STATE_DIR])}


def load_policy():
    try:
        return {**DEFAULT_POLICY, **json.loads(POLICY_FILE.read_text(encoding="utf-8"))}
    except Exception:
        return dict(DEFAULT_POLICY)


def save_policy(p):
    pol = {**DEFAULT_POLICY, **{k: p[k] for k in DEFAULT_POLICY if k in p}}
    pol["days"] = max(0, min(365, int(pol["days"])))
    pol["keep_backups"] = max(1, min(100, int(pol["keep_backups"])))
    pol["cats"] = [c for c in pol["cats"] if c in _cats()]
    POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
    POLICY_FILE.write_text(json.dumps(pol, ensure_ascii=False), encoding="utf-8")
    return pol


def _files(dirs, skip_dirs=()):
    for d in dirs:
        if not Path(d).exists():
            continue
        for root, dn, fn in os.walk(d):
            if skip_dirs and any(root.startswith(str(s)) for s in skip_dirs):
                continue
            for f in fn:
                p = Path(root) / f
                try:
                    st = p.stat()
                    yield p, st.st_size, st.st_mtime
                except Exception:
                    pass


def _size(dirs, skip=()):
    n = b = 0
    for _, s, _m in _files(dirs, skip):
        n += 1
        b += s
    return n, b


def usage():
    u = shutil.disk_usage(paths.DATA_DIR)
    cats = _cats()
    out = []
    for k, (label, dirs) in cats.items():
        n, b = _size(dirs)
        out.append({"key": k, "label": label, "files": n, "mb": round(b / 2**20, 1), "clean": True})
    for k, (label, dirs) in KEEP.items():
        skip = [paths.JOBS_DIR, paths.CHROME_PROFILE_DIR] if k == "state" else ()
        n, b = _size(dirs, skip)
        out.append({"key": k, "label": label, "files": n, "mb": round(b / 2**20, 1), "clean": False})
    prof_n, prof_b = _size([paths.CHROME_PROFILE_DIR])
    out.append({"key": "profile", "label": "🌐 باقي بروفايل المتصفح (الدخول المحفوظ)", "files": prof_n, "mb": round(prof_b / 2**20, 1), "clean": False})
    return {"total_mb": round(u.total / 2**20), "used_mb": round(u.used / 2**20), "free_mb": round(u.free / 2**20),
            "free_pct": round(u.free / u.total * 100, 1) if u.total else 0, "cats": out, "policy": load_policy()}


def _targets(cats, days, keep_backups):
    now, cutoff = time.time(), time.time() - max(days, 0) * 86400
    hour = now - 3600
    all_c = _cats()
    for k in cats:
        if k not in all_c:
            continue
        dirs = all_c[k][1]
        if k == "backups":
            autos = sorted((p for p, _s, _m in _files(dirs) if "_auto" in p.name), key=lambda p: p.stat().st_mtime, reverse=True)
            for p in autos[keep_backups:]:
                yield k, p, p.stat().st_size
            continue
        for p, s, m in _files(dirs):
            if m < hour and (k == "chrome_cache" or m < cutoff):
                yield k, p, s


def preview(cats, days, keep_backups):
    agg = {}
    for k, _p, s in _targets(cats, days, keep_backups):
        a = agg.setdefault(k, {"files": 0, "mb": 0.0})
        a["files"] += 1
        a["mb"] += s / 2**20
    return {k: {"files": v["files"], "mb": round(v["mb"], 1)} for k, v in agg.items()}


def chrome_running():
    try:
        from utils.chrome_cleanup import chrome_count
        return chrome_count() > 0
    except Exception:
        return False


def clean(cats, days, keep_backups):
    if "chrome_cache" in cats and chrome_running():
        cats = [c for c in cats if c != "chrome_cache"]           # a browser is open: its cache is in use
    freed = n = 0
    per = {}
    for k, p, s in list(_targets(cats, days, keep_backups)):
        try:
            p.unlink()
            freed += s
            n += 1
            per[k] = per.get(k, 0) + 1
        except Exception:
            pass
    for d in (paths.SCREENSHOTS_DIR, paths.ALLURE_RESULTS_DIR, paths.ALLURE_REPORT_DIR):   # empty folders left behind
        if d.exists():
            for root, dn, fn in sorted(os.walk(d), key=lambda x: -len(x[0])):
                if root != str(d) and not dn and not fn:
                    try:
                        os.rmdir(root)
                    except Exception:
                        pass
    return {"files": n, "mb": round(freed / 2**20, 1), "per": per, "skipped_chrome": "chrome_cache" not in cats}


_LAST = {"t": 0}


def auto_tick(force=False):
    """the saved policy, at most every 6 hours (called before tests)"""
    pol = load_policy()
    if not pol.get("auto") or (not force and time.time() - _LAST["t"] < 6 * 3600):
        return None
    _LAST["t"] = time.time()
    return clean(pol["cats"], pol["days"], pol["keep_backups"])
