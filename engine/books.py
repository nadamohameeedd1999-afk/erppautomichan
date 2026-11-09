"""
⚖️ مطابقة الحسابات — no setup: reads the ERP's own trial balance data (the JSON behind «ميزان المراجعة بالمستويات - شجري»)
from inside the logged-in browser and checks:
  1. opening balance: total debit = total credit
  2. the period's movement: total debit = total credit (an unbalanced journal entry shows here)
  3. closing balance: total debit = total credit
  4. the tree: every parent account = the sum of its children (debit and credit)
for the whole year (or from / to), and optionally for each cost center / department too.
"""
import time
from datetime import date

from utils.logger import logger

DEFAULT_URL = "/TrialBalanceWithLevelsTree/GETTrialBalanceWithLevelsTree?from={from}&to={to}&depId={dep}"

FETCH_JS = r"""
const [url, done] = [arguments[0], arguments[arguments.length - 1]];
fetch(url, {credentials: 'include'}).then(async r => {
  const t = await r.text();
  try { done({s: r.status, data: JSON.parse(t)}); } catch (e) { done({s: r.status, err: t.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').slice(0, 300)}); }
}).catch(e => done({s: 0, err: String(e)}));
"""

PAIRS = (("رصيد أول المدة", "ObDebit", "ObCredit"), ("حركة الفترة", "Debit", "Credit"), ("الرصيد الختامي", "BalanceDebit", "BalanceCredit"))


def _n(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def analyse(rows, tol=0.01):
    """-> list of (rule, ok, text)"""
    out = []
    top = [x for x in rows if x.get("ParentId") in (None, 0, "")]
    for name, d, c in PAIRS:
        sd, sc = sum(_n(x.get(d)) for x in top), sum(_n(x.get(c)) for x in top)
        diff = round(sd - sc, 2)
        ok = abs(diff) <= tol
        out.append((f"{name}: مدين = دائن", ok, f"مدين {sd:,.2f} · دائن {sc:,.2f}" + ("" if ok else f" · الفرق {diff:,.2f}")))
    kids = {}
    for x in rows:
        if x.get("ParentId") not in (None, 0, ""):
            kids.setdefault(x["ParentId"], []).append(x)
    bad = []
    for p in rows:
        ch = kids.get(p.get("Id"))
        if not ch:
            continue
        for k in ("Debit", "Credit"):
            s = sum(_n(x.get(k)) for x in ch)
            if abs(s - _n(p.get(k))) > tol:
                bad.append(f"{p.get('Code')} {p.get('ArName')}: {'مدين' if k == 'Debit' else 'دائن'} {_n(p.get(k)):,.2f} ومجموع الفرعي {s:,.2f}")
    if all(_n(x.get(k)) == 0 for x in top for _, d, c in PAIRS for k in (d, c)):
        out = [("📥 فيه حركة في الفترة؟", False, f"كل الأرصدة والحركة رجعت صفر لـ {len(rows)} حساب — يا الفترة مفيهاش قيود، يا الميزان ما اتقراش صح"
                                                 " (جربي فترة تانية أو افتحي ميزان المراجعة بإيدك) — مينفعش نقول إنه متزن")]
        return out, top
    out.append(("الحساب الأب = مجموع الحسابات الفرعية", not bad,
                f"{len(rows)} حساب سليم" if not bad else f"{len(bad)} حساب مش متطابق: " + " | ".join(bad[:8])))
    # where the difference is: the main groups (assets, liabilities, …) with their own movement
    return out, top


def run_books(driver, credentials, cfg, result=None):
    from engine.screen_runner import login
    from config.settings import BASE_URL
    result = result if result is not None else {}
    login(driver, credentials)
    driver.get(BASE_URL.rstrip("/") + "/Home")
    driver.set_script_timeout(180)
    y = date.today().year
    # empty = everything up to the end of this year (a fixed old «to» date silently hid every newer entry -> all zeros)
    frm, to = cfg.get("date_from") or f"{y - 10}-01-01", cfg.get("date_to") or f"{y}-12-31"
    tmpl = cfg.get("url") or DEFAULT_URL
    rows_out, fails = [], []
    deps = [""] + list(cfg.get("departments") or [])
    for dep in deps:
        url = tmpl.replace("{from}", frm).replace("{to}", to).replace("{dep}", str(dep))
        t0 = time.time()
        r = driver.execute_async_script(FETCH_JS, url) or {}
        where = f"الفرع / الإدارة {dep}" if dep else "كل الشركة"
        if not isinstance(r.get("data"), list):
            msg = f"مقدرتش أقرا ميزان المراجعة ({r.get('s')}): {r.get('err', '')[:200]}"
            rows_out.append({"cells": [where, "📥 قراءة الميزان", msg], "ok": False})
            fails.append(f"{where}: {msg}")
            continue
        checks, top = analyse(r["data"], float(cfg.get("tol") or 0.01))
        for rule, ok, text in checks:
            rows_out.append({"cells": [where, rule, text], "ok": ok})
            if not ok:
                fails.append(f"{where} — {rule}: {text}")
        if not all(ok for _, ok, _ in checks[:3]):
            groups = " · ".join(f"{x.get('Code')} {x.get('ArName')}: {_n(x.get('Debit')) - _n(x.get('Credit')):+,.2f}" for x in top)
            rows_out.append({"cells": [where, "🔎 صافي الحركة لكل مجموعة", groups], "ok": None})
        if not dep and cfg.get("journals", True):  # 🧾 which entries exactly (document type, number, date, gap)
            try:
                from engine import journal_check
                j_rows, j_fails = journal_check.run(driver, frm, to)
                rows_out += j_rows
                fails += j_fails
            except Exception as e:
                rows_out.append({"cells": ["🧾 القيود", "القيود اللي مش متزنة", f"اتخطيت: {e}"[:200]], "ok": None})
        logger.info(f"⚖️ {where}: {len(r['data'])} حساب في {time.time() - t0:.1f} ث")
    if cfg.get("reconcile", True):                # sub-ledgers (customers / vendors aging) vs their control accounts
        try:
            from engine import reconcile
            for rule, ok, text in reconcile.run(driver, FETCH_JS, cfg):
                rows_out.append({"cells": ["كل الشركة — اليوم", rule, text], "ok": ok})
                if ok is False:
                    fails.append(f"{rule}: {text}")
        except Exception as e:
            rows_out.append({"cells": ["كل الشركة — اليوم", "🔗 مطابقة الأرصدة الفرعية", f"اتخطيت: {e}"[:200]], "ok": None})
    result["detail"] = {"title": "⚖️ مطابقة الحسابات — ميزان المراجعة", "columns": ["النطاق", "القاعدة", "النتيجة"],
                        "rows": rows_out, "note": f"الفترة {frm} → {to} · من بيانات «ميزان المراجعة بالمستويات» على الموقع نفسه"}
    try:                                           # kept per site for the client's speed & health report
        from engine.health import _site_key, STATE
        import json as _j
        from datetime import datetime as _dt
        STATE.mkdir(parents=True, exist_ok=True)
        (STATE / f"books_{_site_key()}.json").write_text(_j.dumps({"at": _dt.now().isoformat(timespec="seconds"), "from": frm, "to": to,
                                                                   "rows": rows_out, "ok": not fails}, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    if fails:
        e = AssertionError("مطابقة الحسابات: " + str(len(fails)) + " مشكلة\n   " + "\n   ".join(fails[:10])
                           + "\n   (لو مدين ≠ دائن في حركة الفترة يبقى فيه قيد مش متزن اتحفظ — راجعي القيود اللي اتعملت في الفترة)")
        e.partial_result = result
        raise e
    logger.success("✅ ميزان المراجعة متزن والشجرة متطابقة")
    return result
