"""
Authentication helpers
"""
import time
from functools import wraps
from flask import session, redirect, url_for, request
from web.settings_helper import verify_password

MAX_ATTEMPTS = 5
LOCK_SECONDS = 600
_failed = {}  # (ip, username) -> [timestamps]


def _client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    return fwd.split(",")[0].strip() if fwd else (request.remote_addr or "?")


def _recent_failures(key):
    now = time.time()
    attempts = [t for t in _failed.get(key, []) if now - t < LOCK_SECONDS]
    if attempts:
        _failed[key] = attempts
    else:
        _failed.pop(key, None)
    return attempts


def is_locked(username):
    """seconds left if (ip, username) is locked after too many wrong tries, else 0"""
    key = (_client_ip(), (username or "").lower())
    att = _recent_failures(key)
    if len(att) < MAX_ATTEMPTS:
        return 0
    return int(LOCK_SECONDS - (time.time() - att[0])) + 1


def login_required(f):
    """Decorator: requires login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated_function


def current_user():
    """Get current logged-in user"""
    if "user_id" not in session:
        return None
    return {
        "id": session.get("user_id"),
        "username": session.get("username"),
        "full_name": session.get("full_name"),
        "role": session.get("role"),
    }


def is_admin():
    """Check if current user is admin"""
    return session.get("role") == "admin"


def login_user(username, password):
    """Login user - returns True on success (with brute-force lockout)"""
    key = (_client_ip(), (username or "").lower())
    if len(_recent_failures(key)) >= MAX_ATTEMPTS:
        return False

    user = verify_password(username, password)
    if not user:
        _failed.setdefault(key, []).append(time.time())
        return False

    _failed.pop(key, None)
    lang = session.get("lang")
    session.clear()  # avoid session fixation
    if lang:
        session["lang"] = lang
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["full_name"] = user.get("full_name", user["username"])
    session["role"] = user.get("role", "user")
    session.permanent = True
    return True


def logout_user():
    """Logout"""
    lang = session.get("lang")
    session.clear()
    if lang:
        session["lang"] = lang


# ==================== permissions (الصلاحيات) ====================
# admin  = كل حاجة
# user   = يشغّل ويعدّل الاختبارات (مش الإعدادات ولا المستخدمين)
# viewer = يشوف بس
ROLES = {"admin": "أدمن", "user": "مستخدم", "viewer": "مشاهد"}
_ADMIN_PATHS = ("/settings", "/users", "/audit", "/api/backups/restore", "/api/hooks/token")
_OPEN_PATHS = ("/login", "/logout", "/set-lang", "/health", "/api/hooks/run", "/static", "/novnc", "/media")


def check_permission():
    """before_request: returns a response when the logged-in user may not do this, else None."""
    from flask import jsonify
    path = request.path
    if path.startswith(_OPEN_PATHS) or "user_id" not in session:
        return None
    role = session.get("role", "user")
    deny = None
    if role != "admin" and path.startswith(_ADMIN_PATHS):
        deny = "الصفحة دي للأدمن بس"
    elif role == "viewer" and request.method not in ("GET", "HEAD", "OPTIONS"):
        deny = "صلاحيتك مشاهدة بس — مش هتقدر تشغّل أو تعدّل"
    if not deny:
        return None
    if path.startswith("/api/") or request.is_json:
        return jsonify({"success": False, "error": deny}), 403
    return (f'<div dir="rtl" style="font-family:Tahoma;padding:40px;text-align:center"><h3>🔒 {deny}</h3>'
            f'<a href="/">الرجوع للرئيسية</a></div>'), 403


# ==================== audit log (سجل النشاط) ====================
_SKIP_AUDIT = ("/api/queue", "/api/status", "/api/log", "/api/screens/jobs", "/api/run-center", "/api/live")


def audit(event, detail="", status=""):
    from datetime import datetime
    from config import paths
    try:
        user = session.get("username") or "-"
    except Exception:
        user = "-"
    line = f"{datetime.now().isoformat(timespec='seconds')}\t{user}\t{event}\t{detail}\t{status}\t{_client_ip_safe()}\n"
    try:
        with open(paths.APP_LOGS_DIR / "audit.log", "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def _client_ip_safe():
    try:
        return _client_ip()
    except Exception:
        return "-"


def audit_request(response):
    """after_request: every change (POST/DELETE...) by a logged-in user."""
    try:
        if request.method in ("POST", "PUT", "DELETE", "PATCH") and not request.path.startswith(_SKIP_AUDIT) \
                and request.path != "/login":
            audit(request.method, request.path, response.status_code)
    except Exception:
        pass
    return response


def read_audit(limit=400):
    from config import paths
    f = paths.APP_LOGS_DIR / "audit.log"
    if not f.exists():
        return []
    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    out = []
    for ln in reversed(lines):
        p = ln.split("\t")
        if len(p) >= 5:
            out.append({"time": p[0].replace("T", " "), "user": p[1], "event": p[2], "detail": p[3], "status": p[4],
                        "ip": p[5] if len(p) > 5 else ""})
    return out
