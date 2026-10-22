"""
Settings for the tests: which ERP site, which user, timeouts.

Site + credentials come from the active test-site profile (Settings page -> data/settings/test_sites.json),
falling back to .env (BASE_URL / LOGIN_USERNAME / LOGIN_PASSWORD).
All folders come from config/paths.py.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

from config import paths  # noqa: E402  (after .env so DATA_DIR from .env is honoured)
from config.storage import load_json  # noqa: E402


def _read_active_profile():
    data = load_json(paths.settings_file("test_sites.json"), {}) or {}
    active_id = data.get("active_profile")
    for p in data.get("profiles", []):
        if active_id and p.get("id") == active_id:
            return p
    return None


def _get(key, env_key, default=""):
    profile = _read_active_profile()
    if profile and profile.get(key):
        return profile[key]
    return os.getenv(env_key, default)


# ==================== Site ====================
BASE_URL = _get("base_url", "BASE_URL", "https://test-site-nq.premiumasp.net")
USERNAME = _get("username", "LOGIN_USERNAME", "erpadmin")
PASSWORD = _get("password", "LOGIN_PASSWORD", "")

LOGIN_URL = BASE_URL + "/Login"
SALES_INVOICE_LIST_URL = BASE_URL + "/SalesInvoice"
SALES_INVOICE_ADD_URL = BASE_URL + "/SalesInvoice/AddEdit"

# ==================== Folders (see config/paths.py) ====================
REPORTS_DIR = paths.RUNS_DIR
RESULTS_DIR = paths.RESULTS_DIR
SCREENSHOTS_DIR = paths.SCREENSHOTS_DIR
LOGS_DIR = paths.APP_LOGS_DIR
DRIVERS_DIR = BASE_DIR / "drivers"
CHROME_PROFILE_DIR = str(paths.CHROME_PROFILE_DIR)

# ==================== Timeouts ====================
DEFAULT_TIMEOUT = 20
SHORT_TIMEOUT = 5
LONG_TIMEOUT = 60
IMPLICIT_WAIT = 3
PAGE_LOAD_TIMEOUT = 60

# ==================== Browser ====================
BROWSER = "chrome"
HEADLESS = False
