"""
📦 Test-data store with reservation (ideas: Tosca Test Data Management, Worksoft Data Connect)

Per test site, a pool of values that are known to work for each kind of master data:
  customer · vendor · item · cashbox · bank · warehouse · employee · account · cost_center · payment_method
Where the values come from:
  ✋ added by hand (Automatic test page → «بيانات الاختبار»)          — always tried first
  📚 learned: every save that really went through adds the list values it used (+1); a rejected save -1
  ⛔ blocked by hand: never picked (a customer with a credit limit, a closed cash box…)
How it's used: a list field set to «first» / «random» (no values written) whose label is one of the kinds picks from
the pool — the best value that's in the list and not reserved by another running test — instead of blindly the
first option. The pick is reserved for this run (30 min) so two tests never fight over the same record.
"""
import json
import os
import re
import time

from config import paths
from utils.logger import logger

KINDS = {
    "customer": ("العميل", r"عميل|customer|client"),
    "vendor": ("المورد", r"مورد|vendor|supplier"),
    "item": ("الصنف", r"صنف|اصناف|أصناف|item|product|مادة|خامة"),
    "cashbox": ("الخزينة", r"خزين|خزنة|صندوق|cash ?box|treasury|cashbox"),
    "bank": ("البنك", r"بنك|bank"),
    "warehouse": ("المخزن", r"مخزن|مستودع|warehouse|store"),
    "employee": ("الموظف / المندوب", r"موظف|مندوب|employee|sales ?person|salesman"),
    "account": ("الحساب", r"^حساب|حساب (?!بنك)|account"),
    "cost_center": ("مركز التكلفة", r"مركز (?:ال)?تكلف|cost ?cent"),
    "payment_method": ("طريقة الدفع", r"طريقة (?:ال)?دفع|طرق الدفع|payment ?(?:method|type)"),
}
HOLD = 30 * 60


SITE = None          # the dashboard sets a site key per request; tests use the active site


def site_key_of(profile):
    import hashlib
    return hashlib.sha1(f"{profile.get('base_url', '').rstrip('/')}|{profile.get('activity', '')}|{profile.get('branch', '')}".encode()).hexdigest()[:10]


def _key():
    if SITE:
        return SITE
    from engine.health import _site_key
    return _site_key()


def _file():
    return paths.STATE_DIR / f"testdata_{_key()}.json"


def load():
    try:
        d = json.loads(_file().read_text(encoding="utf-8"))
    except Exception:
        d = {}
    d.setdefault("kinds", {})
    d.setdefault("held", {})
    return d


def save(d):
    paths.STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _file().with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, _file())


def kind_of(field):
    text = f"{field.get('label') or ''} {field.get('id') or ''}"
    for k, (_, pat) in KINDS.items():
        if re.search(pat, text, re.I):
            return k
    return None


def _run():
    return os.getenv("RUN_ID") or f"pid{os.getpid()}"


def _entries(d, kind):
    return d["kinds"].setdefault(kind, {"values": {}})["values"]


def _score(e):
    if e.get("blocked"):
        return None
    if e.get("manual"):
        return 1000 + e.get("ok", 0)
    if e.get("fail", 0) >= e.get("ok", 0) + 2:          # rejected more often than it worked
        return None
    return e.get("ok", 0) - e.get("fail", 0)


def pick(field, options):
    """options = [option text…] as in the list. -> index into options, or -1 (nothing in the pool fits)"""
    kind = kind_of(field)
    if not kind:
        return -1
    from engine.text_match import normalize as N, is_placeholder
    d = load()
    now = time.time()
    d["held"] = {k: v for k, v in d["held"].items() if v.get("until", 0) > now}
    taken = {k for k, v in d["held"].items() if v.get("run") != _run()}
    entries = _entries(d, kind)
    ranked = sorted(((s, v) for v, e in entries.items() if (s := _score(e)) is not None), reverse=True)
    norm = [N(t) for t in options]
    for _, v in ranked:
        if f"{kind}|{v}" in taken:
            continue
        try:
            i = norm.index(N(v))
        except ValueError:
            continue
        if is_placeholder(options[i]):
            continue
        d["held"][f"{kind}|{v}"] = {"run": _run(), "until": now + HOLD}
        save(d)
        e = entries[v]
        logger.info(f"📦 {field.get('label') or field['id']}: من بيانات الاختبار → {v}"
                    + (" (متضاف بإيدك)" if e.get("manual") else f" (اتحفظ بيه {e.get('ok', 0)} مرة)"))
        return i
    return -1


def learn(steps, fields, ok):
    """after a save: the list values it used get +1 (saved) or -1 (rejected by the ERP)"""
    try:
        byid = {f["id"]: f for f in fields or []}
        d = load()
        n = 0
        for s in steps or []:
            f = byid.get(s.get("id"))
            if not f or f.get("kind") not in ("select", "select2") or not s.get("ok") or s.get("skipped"):
                continue
            v = str(s.get("result") or "").strip()
            k = kind_of(f)
            if not k or not v:
                continue
            e = _entries(d, k).setdefault(v, {})
            e["ok" if ok else "fail"] = e.get("ok" if ok else "fail", 0) + 1
            e["last"] = time.strftime("%Y-%m-%d %H:%M")
            n += 1
        d["held"] = {k: v for k, v in d["held"].items() if v.get("run") != _run()}
        if n:
            save(d)
    except Exception as e:
        logger.warning(f"test data learn: {e}")


def release():
    d = load()
    d["held"] = {k: v for k, v in d["held"].items() if v.get("run") != _run()}
    save(d)


def set_value(kind, value, manual=None, blocked=None, remove=False):
    if kind not in KINDS or not str(value).strip():
        raise ValueError("نوع أو قيمة مش صح")
    d = load()
    ent = _entries(d, kind)
    v = str(value).strip()
    if remove:
        ent.pop(v, None)
    else:
        e = ent.setdefault(v, {})
        if manual is not None:
            e["manual"] = bool(manual)
        if blocked is not None:
            e["blocked"] = bool(blocked)
    save(d)
    return d


def summary():
    d = load()
    now = time.time()
    out = []
    for k, (label, _) in KINDS.items():
        vals = []
        for v, e in _entries(d, k).items():
            h = d["held"].get(f"{k}|{v}")
            vals.append({"value": v, "ok": e.get("ok", 0), "fail": e.get("fail", 0), "manual": bool(e.get("manual")),
                         "blocked": bool(e.get("blocked")), "last": e.get("last", ""),
                         "held": bool(h and h.get("until", 0) > now), "score": _score(e)})
        vals.sort(key=lambda x: (x["blocked"], -(x["score"] if x["score"] is not None else -999)))
        out.append({"kind": k, "label": label, "values": vals})
    return out
