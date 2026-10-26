"""
ERP Test Automation - Web Interface v4.2
"""
import sys
import os
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, send_from_directory
)
from config import paths
from web.config import Config
from web.i18n_helper import t, get_current_lang, get_dir
from web import data_helper, settings_helper, auth

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config.from_object(Config)

# ==================== Screen Builder (منشئ الشاشات) ====================
from web.screens_api import bp as screens_bp
app.register_blueprint(screens_bp)

# ==================== Live view (noVNC through the dashboard) ====================
from web import live_vnc
live_vnc.init_app(app)

# ==================== Run center / schedules / compare ====================
from web.ops_api import bp as ops_bp
app.register_blueprint(ops_bp)
from web import scheduler as _scheduler
_scheduler.start()

# ADMIN_PASSWORD in .env = admin's password, always
try:
    from web import settings_helper as _sh_boot
    _sh_boot.sync_env_admin()
except Exception as _e:
    print(f"[startup] admin sync: {_e}", flush=True)

# generated test files for every saved screen / scenario (needed when definitions live in data/)
try:
    from engine import screen_config as _sc, scenario_config as _scn
    _sc.sync_stubs()
    _scn.sync_stubs()
except Exception as _e:
    print(f"[startup] sync_stubs: {_e}", flush=True)


# ==================== Settings / users & runs / exports (moved to their own files) ====================
from web import routes_settings, routes_runs  # noqa: E402
routes_settings.register(app)
routes_runs.register(app)

# ==================== logo / favicon (data/settings/uploads) ====================
@app.route("/media/<path:filename>")
def media(filename):
    from flask import send_file, abort
    p = settings_helper.find_upload(filename)
    if not p:
        abort(404)
    return send_file(str(p), max_age=3600)


# ==================== permissions + activity log ====================
app.before_request(auth.check_permission)
app.after_request(auth.audit_request)


@app.route("/audit")
@auth.login_required
def audit_page():
    rows = auth.read_audit()
    labels = {"/api/screens/": "منشئ الشاشات", "/api/scenarios/": "السيناريوهات", "/api/schedules": "الجدولة",
              "/api/run-test": "تشغيل اختبار", "/api/run-center": "مركز التشغيل", "/settings": "الإعدادات",
              "/users": "المستخدمين", "/api/backups": "النسخ الاحتياطي", "/api/trash": "سلة المحذوفات",
              "/api/hooks": "رابط التشغيل", "/api/datasets": "ملفات البيانات", "/api/stop": "إيقاف"}
    for r in rows:
        r["area"] = next((v for k, v in labels.items() if r["detail"].startswith(k)), "")
    return render_template("audit.html", rows=rows)


# ==================== Context Processors ====================
@app.context_processor
def inject_globals():
    site_config = settings_helper.load_site_config()
    lang = get_current_lang()
    site_name = site_config["site_name_ar"] if lang == "ar" else site_config["site_name_en"]

    return {
        "t": t,
        "current_lang": lang,
        "text_dir": get_dir(),
        "site_name": site_name,
        "site_name_en": site_config["site_name_en"],
        "site_config": site_config,
        "logo": site_config.get("logo_filename", ""),
        "favicon": site_config.get("favicon_filename", ""),
        "current_user": auth.current_user(),
        # المظهر — Settings → المظهر; ?ui= / ?login= preview one look without saving
        "ui_theme": _pick(request.args.get("ui"), site_config.get("ui_theme"), UI_THEMES, "glass"),
        "now_year": datetime.now().year,
        "login_style": _pick(request.args.get("login"), site_config.get("login_style"), LOGIN_STYLES, "terminal"),
    }


UI_THEMES = ("terminal", "teal", "glass", "minimal", "rail")
LOGIN_STYLES = ("network", "aurora", "terminal", "tilt", "teal")


def _pick(preview, saved, allowed, default):
    for v in (preview, saved):
        if v in allowed:
            return v
    return default


# ==================== Language ====================
@app.route("/set-lang/<lang>")
def set_lang(lang):
    if lang in ["ar", "en"]:
        session["lang"] = lang
        session.permanent = True
    return redirect(request.referrer or url_for("index"))


# ==================== Auth ====================
def _safe_next(url):
    """Allow only same-site relative paths after login (prevents open redirect)"""
    if not url or not url.startswith("/") or url.startswith("//") or "\\" in url:
        return url_for("index")
    return url

@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session and not request.args.get("login"):
        return redirect(url_for("index"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if auth.login_user(username, password):
            auth.audit("دخول", username, "ok")
            next_url = request.args.get("next", url_for("index"))
            return redirect(_safe_next(next_url))
        else:
            auth.audit("دخول غلط", username, "fail")
            from web import settings_helper as _sh
            left = auth.is_locked(username)
            ar = get_current_lang() == "ar"
            if left:
                error = (f"اتقفل الدخول مؤقتًا بعد {auth.MAX_ATTEMPTS} محاولات غلط — جربي تاني بعد {(left + 59) // 60} دقيقة "
                         f"(أو اقفلي البرنامج وشغليه تاني)") if ar else f"Too many attempts, try again in {(left + 59) // 60} min"
            elif not _sh.get_user(username):
                error = (f"مفيش مستخدم اسمه '{username}' في لوحة التحكم. ده دخول لوحة التحكم مش الـ ERP — "
                         f"المستخدم الأساسي اسمه admin") if ar else f"No dashboard user '{username}'"
            else:
                error = ("كلمة المرور غلط. لو نسيتيها: اكتبي ADMIN_PASSWORD=... في ملف .env وشغّلي البرنامج تاني"
                         ) if ar else "Wrong password (set ADMIN_PASSWORD in .env and restart to reset)"

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    auth.logout_user()
    return redirect(url_for("login"))


# ==================== Main ====================
@app.route("/")
@auth.login_required
def index():
    from web import insights
    lang = get_current_lang()
    return render_template("index.html", home=insights.compute_home(lang))


@app.route("/tests")
@auth.login_required
def tests():
    lang = get_current_lang()
    tests_list = data_helper.get_tests_registry(lang)
    return render_template("tests.html", tests=tests_list)


@app.route("/reports")
@auth.login_required
def reports():
    status_filter = request.args.get("status", "all")
    category_filter = request.args.get("category", "all")
    search_query = request.args.get("search", "").strip()

    summaries = data_helper.load_summaries()

    filtered = []
    for s in summaries:
        passed = s.get("passed", 0)
        failed = s.get("failed", 0) + s.get("errors", 0)

        if status_filter == "passed" and failed > 0:
            continue
        if status_filter == "failed" and failed == 0:
            continue

        if search_query:
            text = (s.get("test_name", "") + s.get("run_id", "")).lower()
            if search_query.lower() not in text:
                continue

        filtered.append(s)

    # Chart data
    trend_labels = []
    trend_passed = []
    trend_failed = []
    trend_duration = []

    for s in reversed(filtered[:20]):
        ts = s.get("timestamp") or s.get("run_id", "")
        label = f"{ts[9:11]}:{ts[11:13]}" if len(ts) >= 13 else ts
        trend_labels.append(label)
        trend_passed.append(s.get("passed", 0))
        trend_failed.append(s.get("failed", 0) + s.get("errors", 0))
        trend_duration.append(int(s.get("duration_seconds", 0)))

    total_passed = sum(s.get("passed", 0) for s in filtered)
    total_failed = sum(s.get("failed", 0) + s.get("errors", 0) for s in filtered)
    total_runs = len(filtered)
    success_rate = round((total_passed / (total_passed + total_failed) * 100)
                        if (total_passed + total_failed) > 0 else 0, 1)

    chart_data = {
        "trend_labels": trend_labels,
        "trend_passed": trend_passed,
        "trend_failed": trend_failed,
        "trend_duration": trend_duration,
        "donut_passed": total_passed,
        "donut_failed": total_failed,
        "total_runs": total_runs,
        "success_rate": success_rate,
    }

    return render_template(
        "reports.html",
        reports=filtered,
        status_filter=status_filter,
        category_filter=category_filter,
        search_query=search_query,
        chart_data=chart_data,
    )


@app.route("/reports/<run_id>")
@auth.login_required
def report_detail(run_id):
    summaries = data_helper.load_summaries()
    report = next((s for s in summaries if s.get("run_id") == run_id), None)
    if not report:
        return redirect(url_for("reports"))
    screenshots = data_helper.get_screenshots_for_run(run_id, report)
    shots = [{"file": f, "label": data_helper.screenshot_label(f)} for f in screenshots]
    log_lines = data_helper.read_run_log(run_id)
    from web import explain, insights
    why = ai = None
    if not insights.run_passed(report):
        texts = [str(l.get("text", l) if isinstance(l, dict) else l) for l in log_lines]
        why = explain.for_run(insights.first_failure_message(report), texts)
        ai = explain.cached_ai(run_id)
    return render_template("report_detail.html", report=report, screenshots=screenshots,
                           shots=shots, log_lines=log_lines, why=why, ai=ai, ai_on=explain.ai_available(),
                           failed=not insights.run_passed(report))


@app.route("/api/explain/<run_id>", methods=["POST"])
@auth.login_required
def api_explain(run_id):
    """ask Claude why this run failed (optional — needs an API key)"""
    from web import explain, insights
    report = next((s for s in data_helper.load_summaries() if s.get("run_id") == run_id), None)
    if not report:
        return jsonify({"success": False, "error": "التشغيلة مش موجودة"}), 404
    lines = [str(l.get("text", l) if isinstance(l, dict) else l) for l in data_helper.read_run_log(run_id)]
    shots = data_helper.get_screenshots_for_run(run_id, report)
    fail_shot = next((f for f in reversed(shots) if "FAILED" in f or "failed" in f), shots[-1] if shots else None)
    shot_path = str(paths.SCREENSHOTS_DIR / fail_shot) if fail_shot else None
    try:
        return jsonify({"success": True, **explain.ask_ai(run_id, insights.first_failure_message(report), lines, shot_path)})
    except Exception as e:
        return jsonify({"success": False, "error": f"مقدرتش أسأل الذكاء الاصطناعي: {e}"}), 502


# ==================== Screenshots ====================
@app.route("/screenshots/<filename>")
def serve_screenshot(filename):
    return send_from_directory(str(Config.SCREENSHOTS_DIR), filename)


@app.route("/live")
@auth.login_required
def live_viewer():
    from web import tunnel_helper
    config = tunnel_helper.load_config()
    from web import live_vnc
    ext = (config.get("vnc_url") or "").strip()
    return render_template(
        "live_viewer.html",
        vnc_full_url=tunnel_helper.get_vnc_full_url() if ext else "",
        tunnel_config=config,
        vnc_password=live_vnc.VNC_PASSWORD,
    )


# ==================== Health Check ====================
@app.route("/health")
def health():
    """Health check endpoint for Railway"""
    import os
    from datetime import datetime

    # تحقق من Grid
    grid_status = "unknown"
    if os.environ.get("USE_SELENIUM_GRID", "false").lower() == "true":
        grid_status = "configured"

    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "port": os.environ.get("PORT", "5000"),
        "grid": grid_status,
    }), 200



if __name__ == "__main__":
    import os
    import sys
    from datetime import datetime

    # معلومات التشغيل
    print("=" * 60, flush=True)
    print(f"  ERP Test Automation - Web Interface v4.2", flush=True)
    print(f"  Started: {datetime.now().isoformat()}", flush=True)
    print(f"  Python: {sys.version.split()[0]}", flush=True)
    print(f"  Mode: {'Production' if os.environ.get('FLASK_ENV') == 'production' else 'Development'}", flush=True)
    print(f"  Debug: {os.environ.get('FLASK_DEBUG', 'false')}", flush=True)
    print("=" * 60, flush=True)

    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    print(f"  Port: {port}", flush=True)
    print(f"  Debug: {debug_mode}", flush=True)
    print("=" * 60, flush=True)

    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug_mode,
        use_reloader=False,
        threaded=True,
    )


