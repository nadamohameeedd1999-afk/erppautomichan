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

_secret = os.getenv("SECRET_KEY")
if not _secret:
    if IS_PRODUCTION:
        raise RuntimeError("SECRET_KEY must be set in production (Railway Variables)")
    _secret = secrets.token_hex(32)  # local dev only: changes on every restart


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
    RESULTS_DIR = BASE_DIR / "reports" / "results"
    SCREENSHOTS_DIR = BASE_DIR / "reports" / "screenshots"
    LOGS_DIR = BASE_DIR / "logs"
    SLACK_CONFIG = BASE_DIR / "config" / "slack_config.json"
    EMAIL_CONFIG = BASE_DIR / "config" / "email_config.json"