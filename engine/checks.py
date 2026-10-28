"""
Advanced tests (اختبارات متقدمة) — one JSON per test in DEFS_DIR/checks/<key>.json:

  cycle       (🔁 دورة كاملة)    : several saved screens / scenarios / report checks one after the other,
                                    same browser and same {var:...} (أمر بيع ← تسليم ← فاتورة ← سند قبض ← أرصدة العميل)
  report      (📊 فحص تقرير)     : open a report with filters, read totals, check rules ({مدين} = {دائن})
                                    and compare the numbers with the last run
  permission  (🔐 صلاحيات)       : sign in with a limited user and check which screens open / are blocked
  perf        (⚡ سرعة الشاشات)   : time how long each screen takes to open and warn when it doubles

Each saved test gets tests/checks/test_check_<key>.py so it runs from the queue / schedules like any other test.
"""
import re
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
from config import paths  # noqa: E402
from config.storage import save_json, load_json, to_trash  # noqa: E402

CHECKS_DIR = paths.DEFS_DIR / "checks"
TESTS_DIR = BASE_DIR / "tests" / "checks"
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,90}$")

TYPES = {
    "cycle": ("🔁", "دورة كاملة", "شاشات ورا بعض في نفس المتصفح (رقم السند بيتنقل من خطوة للي بعدها)"),
    "report": ("📊", "فحص تقرير", "يفتح تقرير بفلتر، يقرا الإجماليات، يتأكد من قواعد (مدين = دائن) ويقارن بآخر مرة"),
    "permission": ("🔐", "صلاحيات مستخدم", "يدخل بمستخدم محدود ويتأكد إن الشاشات الممنوعة مقفولة والمسموحة بتفتح"),
    "perf": ("⚡", "سرعة الشاشات", "يقيس وقت فتح كل شاشة وينبه لو بقت أبطأ من العادي"),
}

# ready-made cycles: each slot = (name, words that find a saved screen with a similar key / name)
CYCLE_TEMPLATES = {
    "sales": {"name": "دورة المبيعات", "icon": "🛒", "slots": [
        ("أمر بيع", ["sales_order", "أمر بيع", "اوامر البيع"]),
        ("تسليم / سند صرف مخزن", ["delivery", "stock_issue", "تسليم", "صرف مخزن", "سند صرف"]),
        ("فاتورة بيع", ["sales_invoice", "فاتورة بيع", "فواتير البيع"]),
        ("سند قبض", ["cash_receipt", "سند قبض", "سند القبض"]),
        ("أرصدة العميل / كشف حساب", ["customer_balance", "كشف حساب", "ارصدة العملاء", "أرصدة العميل"]),
    ]},
    "purchases": {"name": "دورة المشتريات", "icon": "📥", "slots": [
        ("طلب شراء", ["purchase_request", "طلب شراء"]),
        ("أمر شراء", ["purchase_order", "أمر شراء", "اوامر الشراء"]),
        ("سند استلام مخزن", ["stock_receipt", "استلام", "سند استلام"]),
        ("فاتورة شراء", ["purchase_invoice", "فاتورة شراء", "فواتير الشراء"]),
        ("سند دفع للمورد", ["cash_issue", "سند دفع", "سند الدفع"]),
        ("أرصدة المورد / كشف حساب", ["supplier_balance", "كشف حساب مورد", "ارصدة الموردين"]),
    ]},
    "inventory": {"name": "دورة المخازن", "icon": "📦", "slots": [
        ("سند استلام مخزن", ["stock_receipt", "سند استلام"]),
        ("تحويل بين المخازن", ["stock_transfer", "تحويل مخزني", "تحويل بين"]),
        ("سند صرف مخزن", ["stock_issue", "سند صرف مخزن"]),
        ("جرد", ["stocktaking", "جرد"]),
        ("أرصدة الأصناف", ["items_balance", "ارصدة الاصناف", "أرصدة الأصناف"]),
    ]},
    "accounting": {"name": "دورة الحسابات", "icon": "🧮", "slots": [
        ("سند قبض", ["cash_receipt", "سند قبض"]),
        ("سند دفع", ["cash_issue", "سند دفع"]),
        ("قيد يدوي", ["journal_entries", "قيود"]),
        ("ميزان المراجعة", ["trial_balance", "ميزان المراجعة"]),
    ]},
}

DENY_TEXTS = ["ليس لديك صلاحية", "ليس لديك الصلاحية", "لا تملك صلاحية", "لا يوجد لديك صلاحية", "غير مصرح", "غير مسموح",
              "access denied", "unauthorized", "forbidden", "not authorized", "you do not have permission", "403", "401"]


class ConfigError(ValueError):
    pass


def _url(u):
    u = (u or "").strip()
    if not u:
        return ""
    m = re.match(r"^https?://[^/]+(/.*)?$", u)
    if m:
        u = m.group(1) or "/"
    return u if u.startswith("/") else "/" + u


def _list(v):
    if isinstance(v, str):
        v = re.split(r"[\n,،]", v)
    return [str(x).strip() for x in (v or []) if str(x).strip()]


def normalize(cfg):
    if not isinstance(cfg, dict):
        raise ConfigError("الإعداد لازم يكون object")
    key = str(cfg.get("key") or "").strip().lower()
    if not KEY_RE.match(key):
        raise ConfigError("المفتاح لازم يبدأ بحرف إنجليزي صغير وفيه حروف/أرقام/_ بس، مثال: sales_cycle")
    typ = str(cfg.get("type") or "").strip()
    if typ not in TYPES:
        raise ConfigError(f"نوع الاختبار '{typ}' مش معروف")
    out = {"key": key, "type": typ, "name_ar": str(cfg.get("name_ar") or key).strip(),
           "notes": str(cfg.get("notes") or ""), "updated_at": cfg.get("updated_at") or ""}

    if typ == "cycle":
        steps = []
        for i, st in enumerate(cfg.get("steps") or [], 1):
            st = st if isinstance(st, dict) else {"key": st}
            k = str(st.get("key") or "").strip()
            name = str(st.get("name") or k).strip()
            if not k:
                raise ConfigError(f"خطوة {i} «{name}»: اختاري الشاشة اللي هتتشغل فيها (أو امسحي الخطوة)")
            if k == key:
                raise ConfigError("الدورة مينفعش تشغّل نفسها")
            steps.append({"key": k, "name": name or k, "optional": bool(st.get("optional", False))})
        if not steps:
            raise ConfigError("الدورة محتاجة خطوة واحدة على الأقل")
        out.update({"steps": steps, "template": str(cfg.get("template") or "")})

    elif typ == "report":
        from engine import screen_config
        url = _url(cfg.get("url"))
        if not url:
            raise ConfigError("اكتبي رابط التقرير (زي /Reports/TrialBalance)")
        fields, seen = [], set()
        for i, f in enumerate(cfg.get("fields") or [], 1):
            try:
                fields.append(screen_config.normalize_field(f, i, seen))
            except ValueError as e:
                raise ConfigError(f"فلتر {i}: {e}")
        values = []
        for v in cfg.get("values") or []:
            ref = str(v.get("ref") or "").strip()
            if ref:
                values.append({"name": str(v.get("name") or ref).strip(), "ref": ref})
        asserts = _list(cfg.get("asserts"))
        if not values and not asserts:
            raise ConfigError("حددي رقم واحد على الأقل يتقري (زي sum:مدين) أو قاعدة يتأكد منها (زي {sum:مدين} = {sum:دائن})")
        compare = str(cfg.get("compare") or "warn")
        if compare not in ("equal", "warn", "off"):
            compare = "warn"
        out.update({"url": url, "fields": fields, "show_button": str(cfg.get("show_button") or "").strip(),
                    "min_rows": max(0, int(cfg.get("min_rows", 1) or 0)), "values": values, "asserts": asserts,
                    "compare": compare, "tol": float(cfg.get("tol", 0.01) or 0.01)})

    elif typ == "permission":
        user = str(cfg.get("username") or "").strip()
        if not user:
            raise ConfigError("اكتبي اسم المستخدم المحدود اللي هندخل بيه")
        expect = []
        for e in cfg.get("expect") or []:
            u = _url(e.get("url"))
            if not u:
                continue
            allowed = e.get("allowed")
            allowed = allowed if isinstance(allowed, bool) else str(allowed).lower() in ("1", "true", "yes", "allow", "مسموح")
            expect.append({"url": u, "name": str(e.get("name") or u).strip(), "allowed": allowed})
        if not expect:
            raise ConfigError("ضيفي شاشة واحدة على الأقل وحددي مسموحة ولا ممنوعة")
        out.update({"username": user, "password": str(cfg.get("password") or ""), "expect": expect,
                    "deny_texts": _list(cfg.get("deny_texts")), "check_menu": bool(cfg.get("check_menu", True))})

    elif typ == "perf":
        pages = []
        for p in cfg.get("pages") or []:
            u = _url(p.get("url") if isinstance(p, dict) else p)
            if u:
                pages.append({"url": u, "name": str((p.get("name") if isinstance(p, dict) else "") or u).strip()})
        all_pages = bool(cfg.get("all_pages", False))
        if not pages and not all_pages:
            raise ConfigError("اختاري الشاشات اللي هتتقاس (أو علّمي «كل الشاشات»)")
        out.update({"pages": pages, "all_pages": all_pages,
                    "times": max(1, min(5, int(cfg.get("times", 2) or 2))),
                    "factor": max(1.2, float(cfg.get("factor", 2) or 2)),
                    "max_seconds": max(0.0, float(cfg.get("max_seconds", 0) or 0)),
                    "baseline_runs": max(1, min(20, int(cfg.get("baseline_runs", 5) or 5))),
                    "fail_on_slow": bool(cfg.get("fail_on_slow", True))})
    return out


def path(key):
    return CHECKS_DIR / f"{key}.json"


def exists(key):
    return bool(key) and path(key).exists()


def load(key):
    p = path(key)
    if not p.exists():
        raise ConfigError(f"مفيش اختبار متقدم بالاسم '{key}'")
    return normalize(load_json(p, {}))


def list_all():
    out = []
    if not CHECKS_DIR.exists():
        return out
    for p in sorted(CHECKS_DIR.glob("*.json")):
        try:
            out.append(normalize(load_json(p, {})))
        except Exception as e:
            out.append({"key": p.stem, "name_ar": p.stem, "type": "?", "error": str(e)[:300]})
    return out


def stub_path(key):
    return TESTS_DIR / f"test_check_{key}.py"


def test_path_for(key):
    return f"tests/checks/test_check_{key}.py::test_check"


STUB = '''"""
Auto-generated for the advanced test: {name}
Config: checks/{key}.json  -- edit it from the dashboard (اختبارات متقدمة), not this file.
"""
import allure
import pytest

from engine.check_runner import run_check_test


@allure.feature("Advanced")
@allure.story("{name}")
@pytest.mark.screen
def test_check(driver, credentials):
    run_check_test(driver, credentials, "{key}")
'''


def write_stub(cfg):
    TESTS_DIR.mkdir(parents=True, exist_ok=True)
    init = TESTS_DIR / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")
    name = cfg["name_ar"].replace('"', "'").replace("\\", "/")
    stub_path(cfg["key"]).write_text(STUB.format(key=cfg["key"], name=name), encoding="utf-8")


def save(cfg):
    old = {}
    if cfg.get("type") == "permission" and not cfg.get("password") and exists(str(cfg.get("key") or "")):
        old = load_json(path(cfg["key"]), {}) or {}          # keep the saved password when the box was left empty
        cfg = {**cfg, "password": old.get("password", "")}
    cfg = normalize(cfg)
    cfg["updated_at"] = datetime.now().isoformat(timespec="seconds")
    CHECKS_DIR.mkdir(parents=True, exist_ok=True)
    save_json(path(cfg["key"]), cfg)
    write_stub(cfg)
    return cfg


def delete(key):
    found = to_trash(path(key))
    if stub_path(key).exists():
        stub_path(key).unlink()
        found = True
    return found


def sync_stubs():
    n = 0
    for c in list_all():
        if not c.get("error") and not stub_path(c["key"]).exists():
            write_stub(c)
            n += 1
    return n


def public(cfg):
    """what the browser sees (no password)"""
    c = dict(cfg)
    if c.get("type") == "permission":
        c["has_password"] = bool(c.get("password"))
        c["password"] = ""
    return c


# ---------------------------------------------------------------- cycle helpers
def runnable_tests():
    """everything a cycle step can run: saved screens, scenarios and report checks"""
    from engine import screen_config, scenario_config
    out = []
    for c in screen_config.list_all():
        if not c.get("error"):
            out.append({"key": c["key"], "name": c["name_ar"], "kind": "screen", "icon": "🧩"})
    for c in scenario_config.list_all():
        if not c.get("error"):
            out.append({"key": c["key"], "name": f"{c.get('screen_name') or c['screen_key']} — {c.get('scenario_name') or ''}",
                        "kind": "scenario", "icon": "🎬"})
    for c in list_all():
        if not c.get("error") and c["type"] == "report":
            out.append({"key": c["key"], "name": c["name_ar"], "kind": "report", "icon": "📊"})
    return out


def suggest_cycle(template):
    """the template's slots, each matched to a saved test when one looks like it"""
    from engine.text_match import normalize as _n
    t = CYCLE_TEMPLATES.get(template)
    if not t:
        raise ConfigError("قالب مش معروف")
    tests = runnable_tests()
    used, slots = set(), []
    for name, words in t["slots"]:
        hit = None
        for w in words:
            nw = _n(w)
            for x in tests:
                if x["key"] in used:
                    continue
                if nw == _n(x["key"]) or nw in _n(x["key"]) or nw in _n(x["name"]):
                    hit = x
                    break
            if hit:
                break
        if hit:
            used.add(hit["key"])
        slots.append({"name": name, "key": hit["key"] if hit else "", "found": hit["name"] if hit else ""})
    return {"name": t["name"], "icon": t["icon"], "steps": slots}
