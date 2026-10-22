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