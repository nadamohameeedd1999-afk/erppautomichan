"""
⚙️ إعدادات الشركة الافتراضية — data/settings/simulation.json (with the dashboard's other settings, never in git):
the company name, mode, employees and their NQ ERP users.

The NQ ERP sites are the dashboard's own sites (الإعدادات ← المواقع): URL, kind (test / client) and the site's user,
which is the manager's user when nobody set one for him here. An employee's own user + password are kept per site here,
encrypted with the dashboard's key (utils.secret_box). Passwords are never sent back to the page.
"""
import json
import os
import re
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # the dashboard's packages (config, utils, web)
from config import paths  # noqa: E402

DATA = Path(__file__).parent / "data"
FILE = paths.settings_file("simulation.json")
RUNS = Path(os.getenv("VC_RUNS") or paths.DATA_DIR / "simulation")   # the day files, tickets, pictures (the client demo keeps its own)
ROLES = ["manager", "sales", "accountant", "warehouse", "purchasing", "cashier", "hr", "it"]
DEFAULT_LOOK = {"kind": "man", "skin": "#E0AC82", "hair": "#2d2018", "shirt": "#2B6CB0"}


def encrypt(pw):
    from utils.secret_box import encrypt as _e
    return _e(pw)


def decrypt(token):
    from utils.secret_box import decrypt as _d
    return _d(token or "") if token else ""


def _profiles():
    """the dashboard's NQ ERP sites (passwords decrypted, for the program only) and its active one"""
    try:
        from web import test_sites_helper as T
        d = T.load_all()
        return d.get("profiles") or [], d.get("active_profile")
    except Exception:
        return [], None


def _company():
    return json.loads((DATA / "company.json").read_text(encoding="utf-8"))


def _site_id(url):
    return re.sub(r"[^a-z0-9]", "_", re.sub(r"^https?://", "", url or "").strip("/").lower())[:60] or "site"


def load():
    """the saved settings, or the defaults built from company.json (the sample company)"""
    c = _company()
    try:
        s = json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        s = {}
    s.setdefault("company", c["name"])
    s.setdefault("mode", "sim")                # sim | real
    s.setdefault("show_browsers", False)
    s.setdefault("screen_round", True)
    s.setdefault("lang", "ar")
    s.setdefault("day_type", "normal")         # normal | month_end (📅 آلة الزمن: يوم إقفال الشهر)         # the daily round over the main screens: add · edit · print · delete
    s.setdefault("engine_path", "")            # the testing tool (erp-automation) — its engine saves the real documents
    s.setdefault("orders_per_day", c.get("orders_per_day", 10))
    s.setdefault("approval_limit", c.get("approval_limit", 50000))
    if not s.get("employees"):
        s["employees"] = [{"id": e["id"], "name": e["name"], "job": e["job"], "role": e["role"],
                           "look": e.get("look") or DEFAULT_LOOK, "speed": e["speed"], "accuracy": e["accuracy"], "experience": e["experience"],
                           "patience": e["patience"], "active": e.get("active", True)} for e in c["employees"]]
    # an employee added to the sample company later (🆕 فهد, sales) shows in the list switched off, until the user turns him on
    # Fahd moved from Sales (sales3, off) to his own room: 🖥️ IT support (it1) — the old switched-off entry goes
    s["employees"] = [e for e in s["employees"] if not (e.get("id") == "sales3" and "(جديد)" in str(e.get("job", "")))]
    have = {e["id"] for e in s["employees"]}
    for e in c["employees"]:
        if e["id"] not in have:
            s["employees"].append({"id": e["id"], "name": e["name"], "job": e["job"], "role": e["role"], "look": e.get("look") or DEFAULT_LOOK,
                                   "speed": e["speed"], "accuracy": e["accuracy"], "experience": e["experience"], "patience": e["patience"],
                                   "active": e.get("active", True)})
    # sites = the dashboard's sites; each keeps this program's users for the employees and its screen map
    profs, dash_active = _profiles()
    per = s.get("site_data") or {}
    s["sites"] = [{"id": p["id"], "name": p.get("name") or re.sub(r"^https?://", "", p.get("base_url", "")).split(".")[0],
                   "url": (p.get("base_url") or "").rstrip("/"), "kind": p.get("kind") or "client",
                   "screens": (per.get(p["id"]) or {}).get("screens") or {}, "users": (per.get(p["id"]) or {}).get("users") or {},
                   "site_user": p.get("username") or ""} for p in profs]
    for k in ("url", "site_kind", "screens", "engine_path"):
        s.pop(k, None)
    for e in s["employees"]:
        e.pop("user", None)
        e.pop("pw", None)
    if s.get("active_site") not in [x["id"] for x in s["sites"]]:
        s["active_site"] = dash_active if dash_active in [x["id"] for x in s["sites"]] else (s["sites"][0]["id"] if s["sites"] else "")
    return s


def active_site(s=None, site_id=None):
    s = s or load()
    return next((x for x in s["sites"] if x["id"] == (site_id or s.get("active_site"))), None)


def runtime(site_id=None):
    """the settings + the chosen site (or `site_id`: the sales demo's copy works on its own site), flat (what the real NQ ERP link reads)"""
    s = load()
    a = active_site(s, site_id) or {}
    return {**s, "site_id": a.get("id", ""), "site_name": a.get("name", ""), "url": a.get("url", ""), "site_kind": a.get("kind", "client"),
            "screens": a.get("screens") or {}}


def public(s=None):
    """for the page: no passwords"""
    s = s or load()
    out = {k: v for k, v in s.items() if k not in ("sites", "site_data")}
    out["sites"] = [{**{k: v for k, v in x.items() if k != "users"},
                     "users": {eid: {"user": u.get("user", ""), "has_pw": bool(u.get("pw"))} for eid, u in (x.get("users") or {}).items()}} for x in s["sites"]]
    return out


def save(j):
    """j comes from the page: a password is only replaced when the user typed a new one"""
    old = load()
    s = dict(old)
    for k in ("company", "mode", "show_browsers", "orders_per_day", "approval_limit", "active_site", "screen_round", "day_type", "lang"):
        if k in j:
            s[k] = j[k]
    s["orders_per_day"] = max(1, min(40, int(s.get("orders_per_day") or 10)))
    s["approval_limit"] = max(0, float(s.get("approval_limit") or 0))
    if "employees" in j:
        by_id = {e["id"]: e for e in old["employees"]}
        emps = []
        for e in j["employees"]:
            eid = re.sub(r"[^a-z0-9_]", "", str(e.get("id") or "")) or "e" + secrets.token_hex(3)
            prev = by_id.get(eid, {})
            role = e.get("role") if e.get("role") in ROLES else "sales"
            rec = {"id": eid, "name": str(e.get("name") or "").strip()[:30] or "موظف", "job": str(e.get("job") or "").strip()[:40], "role": role,
                   "look": {**DEFAULT_LOOK, **(e.get("look") or {})}, "active": bool(e.get("active", True))}
            for k, d in (("speed", 1.0), ("accuracy", .95), ("experience", .7), ("patience", .5)):
                rec[k] = max(.1, min(1.5, float(e.get(k, prev.get(k, d)) or d)))
            emps.append(rec)
            e["id"] = eid                      # so the site users below find the new id
        s["employees"] = emps
    if "sites" in j:                           # the page sends each site's users and screen map (the site itself is the dashboard's)
        olds = {x["id"]: x for x in old["sites"]}
        per = dict(old.get("site_data") or {})
        for x in j["sites"]:
            sid = str(x.get("id") or "")
            if sid not in olds:
                continue
            prev = olds[sid]
            users = {}
            for eid, u in (x.get("users") or {}).items():
                pu = (prev.get("users") or {}).get(eid, {})
                rec = {"user": str(u.get("user") or "").strip()[:80], "pw": pu.get("pw", "")}
                if u.get("pw"):
                    rec["pw"] = encrypt(str(u["pw"]))
                if u.get("clear_pw"):
                    rec["pw"] = ""
                if rec["user"]:
                    users[eid] = rec
            per[sid] = {"users": users, "screens": x.get("screens") or prev.get("screens") or {}}
        s["site_data"] = per
    s.pop("sites", None)
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    return public(load())


def company_cfg():
    """company.json + the settings, in the shape the engine reads"""
    c = _company()
    s = load()
    c["name"] = s["company"]
    c["orders_per_day"] = s["orders_per_day"]
    c["approval_limit"] = s["approval_limit"]
    c["screen_round"] = bool(s.get("screen_round", True))
    c["day_type"] = s.get("day_type") if s.get("day_type") in ("normal", "month_end") else "normal"
    c["lang"] = s.get("lang") if s.get("lang") in ("ar", "en") else "ar"      # 🌐 the display language (and the voices)
    old = {e["id"]: e for e in c["employees"]}
    c["employees"] = []
    for e in s["employees"]:
        if not e.get("active", True):
            continue
        base = old.get(e["id"], {})
        c["employees"].append({**base, **{k: v for k, v in e.items() if k not in ("pw",)}, "color": e["look"].get("shirt", "#2B6CB0")})
    return c


def credentials(eid, site_id=None):
    """(user, password, through the manager?) on the chosen site — an employee with no user of their own works with the manager's"""
    s = load()
    site = active_site(s, site_id) or {}
    users = site.get("users") or {}
    u = users.get(eid) or {}
    if u.get("user") and u.get("pw"):
        return u["user"], decrypt(u["pw"]), False
    mgr = next((e for e in s["employees"] if e.get("role") == "manager" and e.get("active", True)), None)
    m = users.get(mgr["id"]) if mgr else None
    if m and m.get("user") and m.get("pw"):
        return m["user"], decrypt(m["pw"]), mgr["id"] != eid
    p = next((p for p in _profiles()[0] if p["id"] == site.get("id")), None)    # the dashboard's own user on that site = the manager's
    if p and p.get("username") and p.get("password"):
        return p["username"], p["password"], not (mgr and mgr["id"] == eid)
    return "", "", False


def site_credentials(site_id, eid):
    s = load()
    for x in s["sites"]:
        if x["id"] == site_id:
            u = (x.get("users") or {}).get(eid) or {}
            if u.get("user"):
                return u["user"], decrypt(u.get("pw", ""))
            if any(e["id"] == eid and e.get("role") == "manager" for e in s["employees"]):     # the manager: the site's own user
                p = next((p for p in _profiles()[0] if p["id"] == site_id), {})
                return p.get("username", ""), p.get("password", "")
    return "", ""


# ---------------------------------------------------------------- 📦 move the company to another copy of the dashboard
# (your PC -> Railway): each copy encrypts with its own key, so the file carries the passwords under a code YOU type on both sides

def _code_box(code):
    import base64
    import hashlib
    from cryptography.fernet import Fernet
    key = hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), b"nq-simulation-move", 200_000)
    return Fernet(base64.urlsafe_b64encode(key))


def export_bundle(code):
    """the company + every site's employee users (sites by URL, passwords under the code) -> dict to save as a file"""
    if len(code or "") < 6:
        raise ValueError("اكتب كود 6 حروف أو أكتر — هتكتبه تاني في النسخة التانية")
    s, box = load(), _code_box(code)
    out = {k: v for k, v in s.items() if k not in ("sites", "site_data", "active_site")}
    out["active_url"] = (active_site(s) or {}).get("url", "")
    out["sites"] = [{"url": x["url"], "screens": x.get("screens") or {},
                     "users": {eid: {"user": u["user"], "pw": box.encrypt(decrypt(u.get("pw", "")).encode()).decode() if u.get("pw") else ""}
                               for eid, u in (x.get("users") or {}).items() if u.get("user")}} for x in s["sites"]]
    return {"nq_simulation_move": 1, **out}


def import_bundle(b, code):
    """the file from export_bundle -> this copy (sites matched by URL to this dashboard's sites). -> (imported users, sites not found here)"""
    if not isinstance(b, dict) or b.get("nq_simulation_move") != 1:
        raise ValueError("الملف ده مش ملف نقل الشركة الافتراضية")
    box, s = _code_box(code or ""), load()
    by_url = {x["url"].rstrip("/").lower(): x["id"] for x in s["sites"]}
    per, n, missing = dict(s.get("site_data") or {}), 0, []
    for x in b.get("sites") or []:
        sid = by_url.get(str(x.get("url", "")).rstrip("/").lower())
        if not sid:
            missing.append(x.get("url", ""))
            continue
        users = {}
        for eid, u in (x.get("users") or {}).items():
            try:
                pw = box.decrypt(u["pw"].encode()).decode() if u.get("pw") else ""
            except Exception:
                raise ValueError("الكود غلط — اكتب نفس الكود اللي صدّرت بيه") from None
            users[eid] = {"user": u["user"], "pw": encrypt(pw) if pw else ""}
            n += 1
        per[sid] = {"users": users, "screens": x.get("screens") or {}}
    keep = {k: v for k, v in b.items() if k in ("company", "mode", "show_browsers", "orders_per_day", "approval_limit", "screen_round", "day_type", "lang", "employees")}
    s.update(keep)
    s["site_data"] = per
    s["active_site"] = by_url.get(str(b.get("active_url", "")).rstrip("/").lower(), s.get("active_site", ""))
    s.pop("sites", None)
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    return n, missing
