"""
Screen configs: config/screens/<key>.json

One file per screen. The generic test (tests/screens/test_screen_<key>.py) is
generated next to it so every screen has its own plain pytest path
(no [param] in the path -> the dashboard repeat box works).
"""
import json
import re
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCREENS_DIR = BASE_DIR / "config" / "screens"
TESTS_DIR = BASE_DIR / "tests" / "screens"

KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,90}$")

KINDS = ("select2", "select", "text", "number", "date", "textarea", "checkbox", "hidden")

# strategy -> short Arabic description (shown in the dashboard)
STRATEGIES = {
    "fixed": "قيمة ثابتة (لازم تتطابق بالظبط)",
    "search": "بحث بنص (أول خيار فيه النص ده)",
    "first": "أول خيار حقيقي",
    "today": "تاريخ النهارده",
    "unique": "قيمة فريدة (رقم/نص متسلسل)",
    "keep": "سيبه زي ما هو",
    "check": "علّم عليه (✓)",
    "uncheck": "شيل العلامة",
}
SELECT_ONLY = {"first"}
NEEDS_VALUE = {"fixed", "search"}

DEFAULT_SAVE_BUTTON = "button#save"


class ConfigError(ValueError):
    pass


_ID_ATTR = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""", re.I)
_SAFE_ID = re.compile(r"^[A-Za-z_][\w\-\.:\[\]]*$")


def clean_field_id(raw) -> str:
    """Accepts a plain id, a pasted HTML element, '#Id', or a Select2 container id
    and returns the real field id (e.g. '<span id="select2-CustomerId-container">' -> 'CustomerId')."""
    fid = str(raw or "").strip()
    if fid.startswith("css:"):
        return fid
    if "<" in fid:
        m = _ID_ATTR.search(fid)
        fid = m.group(1) if m else ""
    fid = fid.lstrip("#").strip()
    m = re.match(r"^select2-(.+?)-(container|results)$", fid)
    if m:
        fid = m.group(1)
    return fid


def clean_label(raw) -> str:
    return re.sub(r"\s*\*\s*$", "", str(raw or "")).strip()


def stub_path(key: str) -> Path:
    return TESTS_DIR / f"test_screen_{key}.py"


def test_path_for(key: str) -> str:
    """pytest target used by the dashboard / queue."""
    return f"tests/screens/test_screen_{key}.py::test_screen_flow"


def _norm_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    if u.startswith("http://") or u.startswith("https://"):
        # keep only the path + query: the base URL comes from the active test site
        m = re.match(r"^https?://[^/]+(/.*)?$", u)
        u = (m.group(1) or "/") if m else u
    if not u.startswith("/"):
        u = "/" + u
    return u


def normalize(cfg: dict) -> dict:
    """Fill defaults and validate. Raises ConfigError with an Arabic message."""
    if not isinstance(cfg, dict):
        raise ConfigError("الإعداد لازم يكون object")

    key = str(cfg.get("key", "")).strip().lower()
    if not KEY_RE.match(key):
        raise ConfigError("المفتاح (key) لازم يبدأ بحرف إنجليزي صغير وفيه حروف/أرقام/_ بس، مثال: cash_receipt")

    list_url = _norm_url(cfg.get("list_url"))
    if not list_url:
        raise ConfigError("لازم تحدد رابط شاشة القايمة (list_url)")
    add_url = _norm_url(cfg.get("add_url")) or (list_url.split("?")[0].rstrip("/") + "/AddEdit")

    fields_in = cfg.get("fields") or []
    if not isinstance(fields_in, list) or not fields_in:
        raise ConfigError("لازم يكون فيه حقل واحد على الأقل")

    fields, seen = [], set()
    for i, f in enumerate(fields_in, 1):
        raw_id = str(f.get("id", "")).strip()
        fid = clean_field_id(raw_id)
        if not fid:
            raise ConfigError(f"الحقل رقم {i}: مفيش id")
        if not fid.startswith("css:") and not _SAFE_ID.match(fid):
            raise ConfigError(f"الحقل رقم {i}: الـ id '{raw_id[:60]}' مش صالح — اكتبي الـ id بس (زي CustomerId)")
        if fid in seen:
            raise ConfigError(f"الحقل {fid} متكرر")
        seen.add(fid)

        kind = f.get("kind") or "text"
        if kind not in KINDS:
            raise ConfigError(f"{fid}: نوع غير معروف '{kind}'")
        strategy = f.get("strategy") or ("first" if kind in ("select", "select2") else "fixed")
        if strategy not in STRATEGIES:
            raise ConfigError(f"{fid}: طريقة تعبئة غير معروفة '{strategy}'")
        if strategy in SELECT_ONLY and kind not in ("select", "select2"):
            raise ConfigError(f"{fid}: 'أول خيار' للقوائم بس")
        value = "" if f.get("value") is None else str(f.get("value"))
        if strategy in NEEDS_VALUE and not value.strip():
            raise ConfigError(f"{fid} ({f.get('label') or ''}): الطريقة '{strategy}' محتاجة قيمة")
        if strategy == "unique" and not value.strip():
            value = "AUTO-{ts}"

        dep = clean_field_id(f.get("depends_on") or "") or None
        if dep and dep not in seen:
            raise ConfigError(f"{fid}: بيعتمد على {dep} لازم {dep} ييجي قبله في الترتيب")

        fields.append({
            "id": fid,
            "label": clean_label(f.get("label")) or fid,
            "kind": kind,
            "strategy": strategy,
            "value": value,
            "format": str(f.get("format") or ""),
            "depends_on": dep,
            "required": bool(f.get("required", False)),
            "wait_after": float(f.get("wait_after", 0.5) or 0),
            # لو القيمة مش موجودة: شغّل الشاشة/السيناريو ده الأول يعملها (مثلاً customer أو customer__new)
            "create_with": str(f.get("create_with") or "").strip(),
            "timeout": float(f.get("timeout", 15) or 15),
        })

    before_save = []
    for a in cfg.get("before_save") or []:
        sel = str(a.get("selector", "")).strip()
        if not sel:
            continue
        before_save.append({
            "action": "click",
            "selector": sel,
            "label": str(a.get("label") or sel),
            "force_visible": bool(a.get("force_visible", True)),
            "wait_after": float(a.get("wait_after", 1.5) or 0),
        })

    verify = cfg.get("verify") or {}
    out = {
        "key": key,
        "name_ar": str(cfg.get("name_ar") or key),
        "name_en": str(cfg.get("name_en") or cfg.get("name_ar") or key),
        "module_key": str(cfg.get("module_key") or "custom"),
        "icon": str(cfg.get("icon") or "🧩"),
        "list_url": list_url,
        "add_url": add_url,
        "add_button": str(cfg.get("add_button") or "").strip(),
        "save_button": str(cfg.get("save_button") or DEFAULT_SAVE_BUTTON).strip(),
        "fields": fields,
        "before_save": before_save,
        "verify": {
            "new_first_row": bool(verify.get("new_first_row", True)),
            "row_contains": [str(x) for x in (verify.get("row_contains") or []) if str(x).strip()],
            "row_contains_strict": bool(verify.get("row_contains_strict", False)),
            # بعد الحفظ: افتح السند الجديد واتأكد إن كل حقل اتسجل بنفس القيمة
            "open_saved": bool(verify.get("open_saved", False)),
            "open_selector": str(verify.get("open_selector") or "").strip(),
            "timeout": int(verify.get("timeout", 60) or 60),
        },
        "save_timeout": int(cfg.get("save_timeout", 40) or 40),
        "status": "complete",
        "notes": str(cfg.get("notes") or ""),
        "updated_at": cfg.get("updated_at") or "",
    }
    return out


def load(key: str) -> dict:
    path = SCREENS_DIR / f"{key}.json"
    if not path.exists():
        raise ConfigError(f"مفيش إعداد للشاشة '{key}' ({path})")
    with open(path, "r", encoding="utf-8-sig") as fp:
        return normalize(json.load(fp))


def list_all() -> list:
    """All valid configs (broken files are returned with an 'error' key)."""
    out = []
    if not SCREENS_DIR.exists():
        return out
    for p in sorted(SCREENS_DIR.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8-sig") as fp:
                out.append(normalize(json.load(fp)))
        except Exception as e:
            out.append({"key": p.stem, "name_ar": p.stem, "error": str(e)[:300], "status": "broken"})
    return out


def keys() -> list:
    return [c["key"] for c in list_all() if not c.get("error")]


STUB_TEMPLATE = '''"""
Auto-generated by the Screen Builder (منشئ الشاشات) for: {name}
Config: config/screens/{key}.json  -- edit the config, not this file.
"""
import allure
import pytest

from engine.screen_runner import run_screen_test


@allure.feature("Screen Builder")
@allure.story("{name}")
@pytest.mark.screen
def test_screen_flow(driver, credentials):
    run_screen_test(driver, credentials, "{key}")
'''


def write_stub(cfg: dict) -> Path:
    TESTS_DIR.mkdir(parents=True, exist_ok=True)
    init = TESTS_DIR / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")
    name = cfg["name_ar"].replace('"', "'").replace("\\", "/")
    path = stub_path(cfg["key"])
    path.write_text(STUB_TEMPLATE.format(key=cfg["key"], name=name), encoding="utf-8")
    return path


def save(cfg: dict) -> dict:
    cfg = normalize(cfg)
    cfg["updated_at"] = datetime.now().isoformat(timespec="seconds")
    SCREENS_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENS_DIR / f"{cfg['key']}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    write_stub(cfg)
    return cfg


def delete(key: str) -> bool:
    found = False
    for p in (SCREENS_DIR / f"{key}.json", stub_path(key)):
        if p.exists():
            p.unlink()
            found = True
    return found


def sync_stubs() -> int:
    """Re-create missing stubs (e.g. after copying configs by hand)."""
    n = 0
    for c in list_all():
        if not c.get("error") and not stub_path(c["key"]).exists():
            write_stub(c)
            n += 1
    return n
