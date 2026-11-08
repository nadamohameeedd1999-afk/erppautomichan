"""
⚖️ Risk-based priority (idea: Tricentis Tosca «risk-based testing»; Worksoft / Opkey rank by business criticality too)

Every screen gets a weight = importance (1-5) × usage (1-5)  →  1..25
  importance: guessed from the screen's name / module (a sales invoice or a journal entry matters more than a
              definitions screen) — or set by hand in data/settings/risk_weights.json
  usage:      3 by default; set by hand, or later from NQ ERP's own activity log (catalog item 17)

Used to:
  • check the heaviest screens first (a check stopped half way already covered what matters)
  • «risk coverage» = weight of the screens that work ÷ weight of all screens  (not just a count)
  • sort what's broken by how much it hurts: حرج / عالي / متوسط / منخفض
"""
import re

from config import paths

FILE = paths.settings_file("risk_weights.json")

# (pattern on name + module + path, importance)
RULES = [
    (r"فاتور|invoice|سند|voucher|قيد|journal|قبض|صرف|receipt|payment|خزين|treasury|cash|بنك|bank|شيك|cheque|"
     r"رواتب|مرتب|payroll|ضريب|vat|zatca|تحويل|transfer|إقفال|اقفال|close|افتتاحي|opening|ميزان|trial|أستاذ|ledger", 5),
    (r"مخز|stock|inventory|صنف|item|أصناف|جرد|count|استلام|إذن|اذن|warehouse|مشتري|purchase|مبيعات|sales|عقد|contract|"
     r"تكلف|cost|إنتاج|انتاج|production|bom|أصول|asset", 4),
    (r"تقرير|report|كشف|statement|تحليل|analysis|dashboard|لوحة", 3),
    (r"عميل|customer|مورد|vendor|supplier|موظف|employee|حساب|account|مركز تكلفة|cost ?center", 3),
    (r"إعداد|اعداد|setting|config|تعريف|definition|صلاحي|privilege|مستخدم|user|نوع|type|تصنيف|category|مجموع|group|"
     r"وحد|unit|مدن|مدين|city|دول|country|عمل|currency", 2),
]
LEVELS = ((15, "حرج"), (12, "عالي"), (6, "متوسط"), (0, "منخفض"))


def _manual():
    try:
        from config.storage import load_json
        return load_json(FILE, {}) or {}
    except Exception:
        return {}


def importance(path, name="", module=""):
    text = f"{name} {module} {path}"
    for pat, w in RULES:
        if re.search(pat, text, re.I):
            return w
    return 2


def weight(path, name="", module="", manual=None):
    m = (manual if manual is not None else _manual()).get(path) or {}
    imp = int(m.get("importance") or importance(path, name, module))
    use = int(m.get("usage") or 3)
    if "/addedit" in path.lower() or "➕" in name:
        imp = min(5, imp + 0)                              # an add page carries the same business weight as its list
    return max(1, min(5, imp)) * max(1, min(5, use))


def level(w):
    return next(lbl for lim, lbl in LEVELS if w >= lim)


def order(links):
    """heaviest first, stable inside the same weight"""
    man = _manual()
    return sorted(links, key=lambda l: -weight(l["path"], l.get("name", ""), l.get("module", ""), man))


def coverage(paths_names, broken_paths):
    """[(path, name, module)], {broken} -> {"pct", "ok_w", "all_w", "lost": [(w, path)] heaviest first}"""
    man = _manual()
    all_w = ok_w = 0
    lost = []
    for p, n, m in paths_names:
        w = weight(p, n, m, man)
        all_w += w
        if p in broken_paths:
            lost.append((w, p))
        else:
            ok_w += w
    return {"pct": round(100 * ok_w / all_w, 1) if all_w else None, "ok_w": ok_w, "all_w": all_w,
            "lost": sorted(lost, reverse=True)}
