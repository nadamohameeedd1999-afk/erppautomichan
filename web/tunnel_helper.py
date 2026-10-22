"""
Tunnel Helper - Manage public tunnel URLs (Cloudflare/ngrok)
"""
import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
from config import paths
TUNNEL_FILE = paths.settings_file("tunnel_config.json")


def _load_json(path, default=None):
    from config.storage import load_json
    return load_json(path, default)

def _save_json(path, data):
    from config.storage import save_json
    save_json(path, data)

def load_config():
    default = {
        "flask_url": "",
        "vnc_url": "",
        "provider": "cloudflare",
        "updated_at": "",
    }
    data = _load_json(TUNNEL_FILE, {}) or {}
    return {**default, **data}


def save_config(flask_url, vnc_url, provider="cloudflare"):
    config = {
        "flask_url": flask_url.strip().rstrip("/"),
        "vnc_url": vnc_url.strip().rstrip("/"),
        "provider": provider,
        "updated_at": datetime.now().isoformat(),
    }
    _save_json(TUNNEL_FILE, config)
    return config


def get_vnc_full_url():
    """يرجع رابط noVNC كامل جاهز للاستخدام في iframe"""
    config = load_config()
    vnc = config.get("vnc_url", "").rstrip("/")
    if not vnc:
        return "http://localhost:7900/vnc.html?autoconnect=true&resize=scale&password=secret"
    return f"{vnc}/vnc.html?autoconnect=true&resize=scale&password=secret&reconnect=true&reconnect_delay=2000"


def get_flask_url():
    return load_config().get("flask_url", "")
