"""
Web Config
"""
import os
import secrets
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

IS_PRODUCTION = bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_ENVIRONMENT_NAME"))

from config import paths  # noqa: E402

_secret = os.getenv("SECRET_KEY")
if not _secret:
    if IS_PRODUCTION:
        raise RuntimeError("SECRET_KEY must be set in production (Railway Variables)")
    # local: generate once and keep it, so a restart doesn't log everybody out
    _key_file = paths.settings_file("secret_key")
    try:
        _secret = _key_file.read_text(encoding="utf-8").strip()
    except Exception:
        _secret = ""
    if not _secret:
        _secret = secrets.token_hex(32)
        try:
            _key_file.write_text(_secret, encoding="utf-8")
        except Exception:
            pass


class Config:
    SECRET_KEY = _secret
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = IS_PRODUCTION
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)

    BABEL_DEFAULT_LOCALE = "ar"
    BABEL_DEFAULT_TIMEZONE = "Africa/Cairo"
    LANGUAGES = ["ar", "en"]
    BASE_DIR = BASE_DIR
    RESULTS_DIR = paths.RESULTS_DIR
    SCREENSHOTS_DIR = paths.SCREENSHOTS_DIR
    LOGS_DIR = paths.APP_LOGS_DIR
    SLACK_CONFIG = paths.settings_file("slack_config.json")
    EMAIL_CONFIG = paths.settings_file("email_config.json")