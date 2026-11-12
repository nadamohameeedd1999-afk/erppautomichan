"""
🧨 Fresh start — wipe what the dashboard has saved, as if new, to try everything from the beginning.

Always: a FULL backup first (it shows on this page and can be restored), the current admin account is kept (or you
would be locked out), and nothing on any ERP site is touched — this only clears the dashboard's own files.
The admin picks what goes:
  runs        results, logs, screenshots, evidence / check details, Allure, history, trash
  state       system-health checks, accounts checks, recipes, test-data store, heals, risk weights, leftovers
  defs        screen definitions, scenarios, cycles / checks, data files (datasets)
  sites       test sites and their passwords
  settings    alerts (Telegram / WhatsApp), email, Claude key, look & company details
  users       every account except the one doing the reset
"""
import json
import shutil

from flask import Blueprint, jsonify, request

from config import paths
from web import auth

bp = Blueprint("reset", __name__)

GROUPS = {
    "runs": ("التشغيلات والتقارير", "Runs & reports"),
    "state": ("نتايج الفحوصات والتعلم", "Checks & learned data"),
    "defs": ("تعريفات الاختبارات", "Test definitions"),
    "sites": ("المواقع وكلمات السر", "Sites & passwords"),
    "settings": ("الإعدادات", "Settings"),
    "users": ("المستخدمين (غيري)", "Users (except me)"),
}


def _wipe_dir(d, keep=()):
    n = 0
    if not d.exists():
        return 0
    for p in d.iterdir():
        if p.name in keep:
            continue
        try:
            shutil.rmtree(p) if p.is_dir() else p.unlink()
            n += 1
        except Exception:
            pass
    return n


def _rm(f):
    try:
        if f.exists():
            f.unlink()
            return 1
    except Exception:
        pass
    return 0


def wipe(groups, me):
    out = {}
    if "runs" in groups:
        out["runs"] = sum(_wipe_dir(d) for d in (paths.RESULTS_DIR, paths.RUN_LOGS_DIR, paths.SCREENSHOTS_DIR, paths.ALLURE_RESULTS_DIR,
                                                  paths.ALLURE_REPORT_DIR, paths.RUNS_DIR / "checks", paths.HISTORY_DIR, paths.TRASH_DIR,
                                                  paths.APP_LOGS_DIR))
    if "state" in groups:
        out["state"] = _wipe_dir(paths.STATE_DIR, keep=("chrome_profile",)) + _rm(paths.settings_file("risk_weights.json"))
    if "defs" in groups:
        out["defs"] = sum(_wipe_dir(d) for d in (paths.SCREENS_DIR, paths.SCENARIOS_DIR, paths.DEFS_DIR / "checks", paths.DATA_DIR / "datasets"))
        try:                                                     # their generated pytest files too
            from engine import screen_config
            out["defs"] += _wipe_dir(screen_config.TESTS_DIR, keep=("__init__.py",))
        except Exception:
            pass
    if "sites" in groups:
        out["sites"] = _rm(paths.settings_file("test_sites.json"))
    if "settings" in groups:
        out["settings"] = sum(_rm(paths.settings_file(n)) for n in ("alerts.json", "email_config.json", "slack_config.json",
                                                                     "site_config.json", "runs.json", "storage_policy.json"))
    if "users" in groups:
        from web import settings_helper as sh
        users = sh.load_users()
        keep = [u for u in users if u.get("username") == me]
        sh.save_users(keep)
        out["users"] = len(users) - len(keep)
    return out


@bp.route("/api/factory-reset", methods=["POST"])
@auth.login_required
def api_factory_reset():
    u = auth.current_user() or {}
    if u.get("role") != "admin":
        return jsonify({"success": False, "error": "للمدير بس / admins only"}), 403
    d = request.get_json(silent=True) or {}
    groups = [g for g in d.get("groups") or [] if g in GROUPS]
    if not groups:
        return jsonify({"success": False, "error": "اختاري حاجة تتمسح / pick what to wipe"}), 400
    if str(d.get("confirm", "")).strip() not in ("امسح", "RESET"):
        return jsonify({"success": False, "error": "اكتبي «امسح» للتأكيد / type RESET to confirm"}), 400
    from web import backup
    try:
        b = backup.create("before-reset", full=True, shots=True)
    except Exception as e:
        return jsonify({"success": False, "error": f"النسخة الاحتياطية فشلت — ما اتمسحش حاجة: {e}"}), 500
    done = wipe(groups, u.get("username"))
    try:
        auth.audit("factory_reset", json.dumps({"groups": groups, "backup": b["name"], "wiped": done}, ensure_ascii=False))
    except Exception:
        pass
    return jsonify({"success": True, "backup": b["name"], "wiped": done})
