"""
The company's watchdogs — jobs that test the system's controls, not its screens:

  🕵️ «المختلس»  : a user opens a screen outside his permissions (must be refused) ·
                  a document dated years back (an open old period lets anyone rewrite history)
  🧾 المراجع     : every document the company saved today is still in its list (nothing vanished, nothing doubled)

Each returns the usual result dict; a control that let the wrong thing through is a finding.
"""
import time
from datetime import datetime

from simulation.real.writer import Ledger

SEARCH_JS = r"""
var no = String(arguments[0]).trim(), done = arguments[arguments.length - 1];
var box = document.querySelector('.dataTables_filter input, input[type=search]');
var T = function (e) { return (e && e.innerText || '').replace(/\s+/g, ' ').trim(); };
function rows() {
  return Array.prototype.filter.call(document.querySelectorAll('table tbody tr'), function (tr) {
    return Array.prototype.some.call(tr.querySelectorAll('td'), function (td) { return T(td) === no; });
  }).length;
}
var n0 = rows();
if (n0 || !box) { done({found: n0, searched: false}); return; }
box.value = no;
['input', 'keyup', 'change'].forEach(function (t) { box.dispatchEvent(new Event(t, {bubbles: true})); });
try { if (window.jQuery) jQuery(box).trigger('keyup'); } catch (e) {}
setTimeout(function () { done({found: rows(), searched: true}); }, 3500);
"""


def forbidden_open(session, path, who_role):
    """a user opens a screen of another department: the system must say no"""
    t0 = time.time()
    r = session.open(path)
    url = session.driver.current_url
    ms = int((time.time() - t0) * 1000)
    blocked = "unauthor" in url.lower() or r.get("kind") in ("denied",) or "/login" in url.lower()
    if blocked:
        return {"kind": "ok", "ms": ms, "did": "open", "note": f"🕵️ حاولت أفتح «{path}» وأنا مش من القسم — السيستم منعني ✅"}
    return {"kind": "wrong", "ms": ms, "did": "open", "source": "data",
            "msg": f"صلاحيات مفتوحة: مستخدم {who_role} قدر يفتح «{path}» وهي مش من شغله",
            "evidence": f"🕵️ اختبار المختلس: فتح {session.base}{path} بمستخدم {session.user} ← {url}"}


def _find_row(driver, no, path):
    """the row the writer's own edit / delete would pick (erp-automation's matcher + its list search), after the list has loaded"""
    try:
        from engine.operations import ROW_ACTION_JS, SEARCH_JS as LIST_SEARCH
    except ImportError:                                            # no erp-automation → the plain search
        time.sleep(2.5)
        return bool((driver.execute_async_script(SEARCH_JS, no) or {}).get("found"))
    for i in range(3):
        for _ in range(12):                                        # the list's rows come by ajax after the page
            r = driver.execute_script(ROW_ACTION_JS, str(no), "edit", "", False, path) or {}
            if r.get("error") != "empty":
                break
            time.sleep(1)
        if r.get("ok") or r.get("error") == "no_button":           # the row is there (its button doesn't matter here)
            return True
        if r.get("error") != "no_row" or not driver.execute_script(LIST_SEARCH, str(no)):
            return False
        time.sleep(3)                                              # not on page 1 → the list's own search
    return False


def audit_documents(driver, base, site, paths, names, since=None):
    """every document the company saved (today) and didn't delete is in its list -> {kind, note, missing, evidence}"""
    t0 = time.time()
    since = since or datetime.now().strftime("%Y-%m-%d")
    docs = [x for x in Ledger._all() if x["site"] == site and not x.get("deleted") and str(x.get("at", "")) >= since]
    missing, seen, checked = [], set(), 0
    driver.set_script_timeout(20)
    for x in docs:
        k = (x["screen"], x["no"])
        if k in seen or x["screen"] not in paths:
            continue
        seen.add(k)
        try:
            driver.get(base.rstrip("/") + paths[x["screen"]])
            checked += 1
            if not _find_row(driver, x["no"], paths[x["screen"]]):
                missing.append(f"{names.get(x['screen'], x['screen'])} رقم {x['no']}")
        except Exception:
            continue
    ms = int((time.time() - t0) * 1000)
    ev = f"🧾 المراجع: {checked} مستند من شغل النهارده اتدور عليه في شاشته" + (f"\nمش لاقيه: {'، '.join(missing[:12])}" if missing else "")
    if missing:
        return {"kind": "wrong", "ms": ms, "did": "review", "msg": f"{len(missing)} مستند اتحفظ النهارده ومش ظاهر في شاشته: {'، '.join(missing[:5])}",
                "evidence": ev}
    return {"kind": "ok", "ms": ms, "did": "review", "evidence": ev,
            "note": f"🧾 راجعت {checked} مستند اتعمل النهارده — كلهم موجودين في شاشاتهم" if checked else "🧾 مفيش مستندات النهارده أراجعها"}
