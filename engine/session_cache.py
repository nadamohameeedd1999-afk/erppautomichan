"""
Reuse the ERP login between tests (saves ~40 seconds per test).

After a successful login the browser cookies are saved to data/state/session_<id>.json.
The next test loads them into its fresh browser; if the site still accepts them we skip the
login screen, otherwise we log in normally and save the new cookies.

SESSION_REUSE=0           -> turn it off
SESSION_REUSE_MINUTES=25  -> how old a saved session may be
"""
import hashlib
import json
import os
import time
from pathlib import Path

from config.settings import BASE_URL, USERNAME
from utils.logger import logger

from config import paths  # noqa: E402
STATE_DIR = paths.STATE_DIR
ENABLED = os.getenv("SESSION_REUSE", "1") not in ("0", "false", "False")
MAX_AGE = int(os.getenv("SESSION_REUSE_MINUTES", "25")) * 60


def _file():
    h = hashlib.sha1(f"{BASE_URL}|{USERNAME}".encode("utf-8")).hexdigest()[:12]
    return STATE_DIR / f"session_{h}.json"


def save(driver):
    if not ENABLED:
        return
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _file().write_text(json.dumps({"saved_at": time.time(), "cookies": driver.get_cookies()},
                                      ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        logger.debug(f"session save: {e}")


def forget():
    try:
        _file().unlink()
    except Exception:
        pass


def _logged_in(driver):
    url = (driver.current_url or "").lower()
    if "/login" in url:
        return False
    try:
        return not driver.find_elements("id", "userName")
    except Exception:
        return False


def restore(driver):
    """True if the saved session works in this browser."""
    if not ENABLED:
        return False
    f = _file()
    if not f.exists():
        return False
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        forget()
        return False
    if time.time() - float(data.get("saved_at", 0)) > MAX_AGE:
        forget()
        return False
    try:
        driver.get(BASE_URL.rstrip("/") + "/favicon.ico")   # any page on the site (not /Login: it may sign out)
        for c in data.get("cookies", []):
            c = {k: v for k, v in c.items() if k in ("name", "value", "path", "domain", "secure", "httpOnly", "expiry")}
            if "expiry" in c:
                c["expiry"] = int(c["expiry"])
            try:
                driver.add_cookie(c)
            except Exception:
                c.pop("domain", None)
                try:
                    driver.add_cookie(c)
                except Exception:
                    pass
        driver.get(BASE_URL.rstrip("/") + "/")
        time.sleep(1.5)
        if _logged_in(driver):
            return True
    except Exception as e:
        logger.debug(f"session restore: {e}")
    forget()
    return False
