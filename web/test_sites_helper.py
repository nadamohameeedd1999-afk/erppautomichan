"""
Test Sites Helper - Manage test site profiles (URLs + credentials)
"""
import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
from config import paths
TEST_SITES_FILE = paths.settings_file("test_sites.json")


def _load_json(path, default=None):
    from config.storage import load_json
    return load_json(path, default)

def _save_json(path, data):
    from config.storage import save_json
    save_json(path, data)

def load_all():
    data = _load_json(TEST_SITES_FILE, {"active_profile": None, "profiles": []})
    return data or {"active_profile": None, "profiles": []}


def get_active_profile():
    data = load_all()
    active_id = data.get("active_profile")
    if not active_id:
        return None
    for p in data.get("profiles", []):
        if p.get("id") == active_id:
            return p
    return None


def add_profile(name, base_url, username, password, notes=""):
    data = load_all()
    import uuid
    new_id = "p_" + datetime.now().strftime("%Y%m%d%H%M%S") + uuid.uuid4().hex[:4]     # unique even when two are added in one second
    profile = {
        "id": new_id,
        "name": name,
        "base_url": base_url.rstrip("/"),
        "username": username,
        "password": password,
        "notes": notes,
        "created_at": datetime.now().isoformat(),
    }
    data.setdefault("profiles", []).append(profile)
    if not data.get("active_profile"):
        data["active_profile"] = new_id
    _save_json(TEST_SITES_FILE, data)
    return True, profile


def update_profile(profile_id, **kwargs):
    data = load_all()
    for p in data.get("profiles", []):
        if p.get("id") == profile_id:
            if "name" in kwargs:
                p["name"] = kwargs["name"]
            if "base_url" in kwargs:
                p["base_url"] = kwargs["base_url"].rstrip("/")
            if "username" in kwargs:
                p["username"] = kwargs["username"]
            if "password" in kwargs and kwargs["password"]:
                p["password"] = kwargs["password"]
            if "notes" in kwargs:
                p["notes"] = kwargs["notes"]
            p["updated_at"] = datetime.now().isoformat()
            _save_json(TEST_SITES_FILE, data)
            return True, p
    return False, "Profile not found"


def delete_profile(profile_id):
    data = load_all()
    profiles = data.get("profiles", [])
    new_profiles = [p for p in profiles if p.get("id") != profile_id]
    if len(new_profiles) == len(profiles):
        return False, "Profile not found"
    data["profiles"] = new_profiles
    if data.get("active_profile") == profile_id:
        data["active_profile"] = new_profiles[0]["id"] if new_profiles else None
    _save_json(TEST_SITES_FILE, data)
    return True, "Deleted"


def set_active_profile(profile_id):
    data = load_all()
    for p in data.get("profiles", []):
        if p.get("id") == profile_id:
            data["active_profile"] = profile_id
            _save_json(TEST_SITES_FILE, data)
            return True
    return False
