"""
🔗 مطابقة الأرصدة الفرعية مع حساب المراقبة — read only, no setup.
Compares the ERP's own sub-ledger reports with the control accounts in the trial balance, on the same date:
  • customers: «أعمار ديون العملاء - الفواتير» (sum of Total)      vs  the receivables control account (الذمم المدينة / العملاء)
  • vendors:   «أعمار ديون الموردين - الحركات المالية» (sum Balance) vs  the payables control account (الذمم الدائنة / الموردين)
A difference usually means: an entry posted straight to the control account, an opening balance not linked to a party,
or receipts / advances not allocated to invoices.
Endpoints found live on NQ ERP (GET, JSON). Every source can be overridden from the check settings (cfg["reconcile_sources"]).
"""
import re
from datetime import date

from utils.logger import logger

TB_URL = "/TrialBalanceWithLevelsTree/GETTrialBalanceWithLevelsTree?from={from}&to={to}&depId="
AGING_Q = "todate={to}&UserId=1&ShowDueOnly=2&ViewFullyPaidInvoice=0"

SOURCES = [
    {"key": "customers", "name": "العملاء", "side": "debit",
     "urls": ["/CustomerInvoiceAgingN/GetSummary?" + AGING_Q],
     "fields": ["Total"], "report": "أعمار ديون العملاء - الفواتير",
     "match": r"الذمم المدينة|ذمم مدينة|^العملاء|عملاء", "exclude": r"مخصص|مصروف|مشكوك|دفعات مقدمة"},
    {"key": "vendors", "name": "الموردين", "side": "credit",
     "urls": ["/VendorMovementAgingN/GetData?" + AGING_Q, "/VendorInvoiceAgingN/GetData?" + AGING_Q],
     "fields": ["Balance", "Total"], "report": "أعمار ديون الموردين - الحركات المالية",
     "match": r"الذمم الدائنة|ذمم دائنة|^الموردين|موردين", "exclude": r"مخصص|مصروف|دفعات مقدمة"},
]

WHY = ("الأسباب المعتادة: قيد اتعمل على حساب المراقبة مباشرة من غير عميل/مورد، رصيد افتتاحي مش مربوط بطرف، "
       "أو سندات قبض/صرف ودفعات مقدمة مش مخصصة على فواتير")


def _n(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _rows(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("rows", "data", "Data", "items"):
            if isinstance(data.get(k), list):
                return data[k]
    return None


def sub_total(rows, fields):
    """sum the first field that exists in the rows"""
    for f in fields:
        if rows and any(f in r for r in rows):
            return round(sum(_n(r.get(f)) for r in rows), 2), f
    return 0.0, fields[0]


def control_account(tb, src, code=None):
    """the top-most trial-balance account for this sub-ledger (or the code set in the settings)"""
    if code:
        return next((x for x in tb if str(x.get("Code")) == str(code)), None)
    m, ex = re.compile(src["match"]), re.compile(src["exclude"])
    cands = [x for x in tb if m.search((x.get("ArName") or "").strip()) and not ex.search(x.get("ArName") or "")]
    if not cands:
        return None
    ids = {x.get("Id") for x in cands}
    tops = [x for x in cands if x.get("ParentId") not in ids]     # drop children of another candidate
    return min(tops or cands, key=lambda x: (_n(x.get("ACCOUNTLEVEL")) or len(str(x.get("Code") or "")), str(x.get("Code"))))


def balance(acc, side):
    d, c = _n(acc.get("BalanceDebit")), _n(acc.get("BalanceCredit"))
    return round(d - c if side == "debit" else c - d, 2)


def compare(tb, fetched, cfg=None):
    """tb: trial balance rows · fetched: {key: (rows | None, url, err)} -> list of (rule, ok, text)"""
    cfg = cfg or {}
    tol = float(cfg.get("rec_tol") or 1)
    codes = cfg.get("control_codes") or {}
    out = []
    for src in cfg.get("reconcile_sources") or SOURCES:
        rule = f"🔗 {src['name']}: أعمار الديون = حساب المراقبة"
        rows, url, err = fetched.get(src["key"], (None, "", "ما اتقراش"))
        if rows is None:
            out.append((rule, None, f"مقدرتش أقرا «{src['report']}» ({err}) — اتخطيت"))
            continue
        acc = control_account(tb, src, codes.get(src["key"]))
        if not acc:
            out.append((rule, None, f"مالقيتش حساب مراقبة لـ{src['name']} في الميزان — حطي كوده في الإعدادات (control_codes)"))
            continue
        sub, f = sub_total(rows, src["fields"])
        gl = balance(acc, src["side"])
        diff = round(sub - gl, 2)
        ok = abs(diff) <= tol
        txt = (f"«{src['report']}» ({len(rows)} طرف): {sub:,.2f} · الحساب {acc.get('Code')} {(acc.get('ArName') or '').strip()}: {gl:,.2f}"
               + ("" if ok else f" · الفرق {diff:+,.2f} — {WHY}"))
        out.append((rule, ok, txt))
    return out


def run(driver, fetch_js, cfg=None):
    """fetch everything inside the logged-in browser (GET only) and compare -> list of (rule, ok, text)"""
    cfg = cfg or {}
    to = date.today().isoformat()            # aging reports are «as of today», so the ledger is read to the same day
    frm = cfg.get("date_from") or f"{date.today().year - 10}-01-01"

    def get(url):
        r = driver.execute_async_script(fetch_js, url.replace("{from}", frm).replace("{to}", to)) or {}
        return _rows(r.get("data")), (r.get("err") or f"HTTP {r.get('s')}")[:120]

    tb, err = get(TB_URL)
    if tb is None:
        return [("🔗 مطابقة الأرصدة الفرعية", None, f"مقدرتش أقرا الميزان لتاريخ {to}: {err}")]
    fetched = {}
    for src in cfg.get("reconcile_sources") or SOURCES:
        last = None
        for u in src["urls"]:
            rows, e = get(u)
            if rows is not None:
                fetched[src["key"]] = (rows, u, "")
                break
            last = e
        else:
            fetched[src["key"]] = (None, "", last)
    res = compare(tb, fetched, cfg)
    logger.info("🔗 مطابقة الأرصدة الفرعية: " + " · ".join(f"{r}: {'✅' if ok else ('—' if ok is None else '❌')}" for r, ok, _ in res))
    return res
