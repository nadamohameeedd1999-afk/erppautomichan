"""
🏢 Bring the old standalone NQ Simulation (nq-virtual-company) into the dashboard — once.

    python tools\\import_simulation.py "D:\\private\\work\\nq-virtual-company"

  • its sites  -> the dashboard's sites (matched by URL; a missing one is added with the manager's user)
  • employees, company, mode, screen map, each employee's NQ ERP user -> data/settings/simulation.json
    (passwords: decrypted with the old .key, saved again with the dashboard's key)
  • runs/ (days, tickets' pictures, people, problems memory, the documents the company made) -> data/simulation/
  • vc/data/menus.json (who sees which screens) -> data/settings/simulation_menus.json

Nothing in the old folder is changed or deleted. Running it twice is safe (files already there are kept).
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import paths  # noqa: E402
from utils.secret_box import encrypt  # noqa: E402
from web import test_sites_helper as T  # noqa: E402


def main(old):
    old = Path(old)
    s = json.loads((old / "vc" / "data" / "settings.json").read_text(encoding="utf-8"))
    keyf = old / "vc" / "data" / ".key"
    from cryptography.fernet import Fernet
    fer = Fernet(keyf.read_bytes()) if keyf.exists() else None

    def plain(tok):
        try:
            return fer.decrypt(tok.encode()).decode() if (tok and fer) else ""
        except Exception:
            return ""

    mgr = next((e["id"] for e in s.get("employees", []) if e.get("role") == "manager"), "manager")
    profs = T.load_all().get("profiles") or []
    by_url = {p["base_url"].rstrip("/").lower(): p for p in profs}
    remap, site_data = {}, {}
    for x in s.get("sites") or []:
        url = x["url"].rstrip("/")
        p = by_url.get(url.lower())
        if not p:                                                    # a site only the simulation knew: added to the dashboard
            mu = (x.get("users") or {}).get(mgr) or {}
            ok, p = T.add_profile(x.get("name") or url, url, mu.get("user", ""), plain(mu.get("pw", "")), kind=x.get("kind", ""))
            print(f"➕ موقع جديد في اللوحة: {p['name']} ({url})")
        remap[x["id"]] = p["id"]
        site_data[p["id"]] = {"screens": x.get("screens") or {},
                              "users": {eid: {"user": u.get("user", ""), "pw": encrypt(plain(u.get("pw", ""))) if u.get("pw") else ""}
                                        for eid, u in (x.get("users") or {}).items() if u.get("user")}}
        print(f"🔗 {x.get('name') or url} → {p['name']}: {len(site_data[p['id']]['users'])} مستخدم موظف")

    out = {k: v for k, v in s.items() if k not in ("sites", "engine_path", "url", "site_kind", "screens")}
    out["site_data"] = site_data
    out["active_site"] = remap.get(s.get("active_site"), "")
    f = paths.settings_file("simulation.json")
    if f.exists():
        shutil.copy2(f, f.with_suffix(".json.before_import"))
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"⚙️ الإعدادات → {f}")

    menus = old / "vc" / "data" / "menus.json"
    if menus.exists():
        m = json.loads(menus.read_text(encoding="utf-8"))
        m = {f"{remap.get(k.split(':', 1)[0], k.split(':', 1)[0])}:{k.split(':', 1)[1]}" if ":" in k else k: v for k, v in m.items()}
        paths.settings_file("simulation_menus.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
        print(f"🔑 صلاحيات {len(m)} مستخدم")

    src, dst = old / "runs", paths.DATA_DIR / "simulation"
    n = 0
    for p in src.rglob("*") if src.exists() else []:
        if p.is_file():
            t = dst / p.relative_to(src)
            if not t.exists():
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, t)
                n += 1
    led = dst / "created.json"                                       # the documents the company made: under the dashboard's site ids
    if led.exists():
        rows = json.loads(led.read_text(encoding="utf-8"))
        for r in rows if isinstance(rows, list) else []:
            r["site"] = remap.get(r.get("site"), r.get("site"))
        led.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"📁 {n} ملف من runs → {dst}")
    print("✅ خلص — افتح اللوحة ← الشركة الافتراضية")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1])
