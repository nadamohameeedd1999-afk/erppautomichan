"""
All screens we know (للـ «فتح الشاشة» smoke test):
  - the modules registry (config/modules_registry.py)
  - screens found by «اكتشاف شاشات النظام» (data/settings/discovered_screens.json)
"""
from config import paths
from config.storage import load_json, save_json

DISCOVERED_FILE = paths.settings_file("discovered_screens.json")
SMOKE_TEST = "tests/smoke/test_screen_smoke.py::test_screen_opens"


def smoke_path(page_key):
    return f"{SMOKE_TEST}[{page_key}]"


def discovered():
    return load_json(DISCOVERED_FILE, {"screens": []}).get("screens", [])


def save_discovered(screens):
    save_json(DISCOVERED_FILE, {"screens": screens})


def all_pages():
    """page_key -> {name_ar, name_en, url, module_key, module_name}"""
    from config.modules_registry import ModulesRegistry
    out = {}
    for mk, m in ModulesRegistry.MODULES.items():
        for pk, p in m["pages"].items():
            out[pk] = {"name_ar": p.get("name_ar", pk), "name_en": p.get("name_en", pk), "url": p.get("url", ""),
                       "module_key": mk, "module_name": m.get("name_ar", mk)}
    known = {v["url"].split("?")[0].lower().rstrip("/") for v in out.values()}
    for s in discovered():
        if s.get("key") in out or s.get("url", "").split("?")[0].lower().rstrip("/") in known:
            continue
        out[s["key"]] = {"name_ar": s.get("name") or s["key"], "name_en": s.get("name") or s["key"], "url": s["url"],
                         "module_key": "discovered", "module_name": s.get("group") or "🧭 شاشات مكتشفة"}
    return out
