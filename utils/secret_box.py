"""
🔐 Secrets at rest — site passwords and alert tokens are saved encrypted ("enc:…"), never as plain text.

key: DATA_KEY env (best: set it on Railway), else SECRET_KEY env, else the local secret_key file the dashboard
already keeps. If the key changes, old values can't be read: decrypt() returns "" and the site asks for its
password again (nothing crashes).
"""
import base64
import hashlib
import os

PREFIX = "enc:"
_fernet = None


def _key_material():
    v = os.getenv("DATA_KEY") or os.getenv("SECRET_KEY")
    if v:
        return v
    try:
        from config import paths
        f = paths.settings_file("secret_key")
        if f.exists():
            return f.read_text(encoding="utf-8").strip()
        import secrets
        v = secrets.token_hex(32)
        f.write_text(v, encoding="utf-8")
        return v
    except Exception:
        return "nq-erp-automation-local"


def _box():
    global _fernet
    if _fernet is None:
        from cryptography.fernet import Fernet
        _fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(_key_material().encode()).digest()))
    return _fernet


def is_encrypted(v):
    return isinstance(v, str) and v.startswith(PREFIX)


def encrypt(v):
    if not v or is_encrypted(v):
        return v
    return PREFIX + _box().encrypt(str(v).encode()).decode()


def decrypt(v):
    if not is_encrypted(v):
        return v or ""
    try:
        return _box().decrypt(v[len(PREFIX):].encode()).decode()
    except Exception:
        return ""                    # saved with another key -> ask for it again


def migrate_once():
    """first start after the update: re-save every settings file that holds a secret (now encrypted) and remove
    their old saved versions in data/history (those still had the plain text)."""
    try:
        from config import paths
        mark = paths.settings_file(".secrets_encrypted")
        if mark.exists():
            return
        from web import test_sites_helper as ts, settings_helper as sh, notify
        d = ts.load_all()
        ts._save_json(ts.TEST_SITES_FILE, d)
        sh.save_site_config(sh.load_site_config())
        if paths.settings_file("email_config.json").exists():
            sh.save_email_config(sh.load_email_config())
        if notify.ALERTS_FILE.exists():
            notify.save_config({})
        import shutil
        from config.storage import _history_dir
        for name in ("test_sites.json", "site_config.json", "email_config.json", "alerts.json"):
            h = _history_dir(paths.settings_file(name))
            if h.exists():
                shutil.rmtree(h, ignore_errors=True)
        mark.write_text("1", encoding="utf-8")
        print("[secrets] 🔐 passwords and tokens are now saved encrypted", flush=True)
    except Exception as e:
        print(f"[secrets] migrate: {e}", flush=True)
