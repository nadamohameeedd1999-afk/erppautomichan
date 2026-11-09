"""
🧾 القيود اللي مش متزنة — read only.
When the trial balance doesn't balance, «there is a difference» isn't enough: this reads every journal line from
«تقرير مراجعة قيود اليومية» (/JournalEntriesReview/GetDataJson — the same data that screen shows; a POST that only
reads) and lists each entry whose debit ≠ credit: document type and number, date, user, posted or not, and the gap.
Found live on the test site: 11 one-line stock / transfer vouchers = exactly the trial balance's difference.
"""
from utils.logger import logger

URL = "/JournalEntriesReview/GetDataJson"

READ_JS = r"""
const [url, from, to, done] = [arguments[0], arguments[1], arguments[2], arguments[arguments.length - 1]];
const f = {DateFrom: from, DateTo: to, BranchId: null, AccountIds: [], AccountId: null, CostCenterId: null, UserId: null, IsPosted: null,
           DebitCreditType: null, SourcePageId: null, ReviewStatus: null, OperationType: null, FlaggedOnly: false, SearchTerm: ''};
fetch(url, {method: 'POST', credentials: 'include', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(f)})
 .then(async r => { const t = await r.text(); let j; try { j = JSON.parse(t); } catch (e) { return done({s: r.status, err: t.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').slice(0, 200)}); }
   const g = {};
   (j.data || []).forEach(x => { const k = x.JournalEntryId;
     const e = g[k] = g[k] || {id: k, doc: x.DocumentNumber, type: x.OperationType || x.DocumentType, op: x.OperationNumber,
                               date: (x.JournalDate || '').slice(0, 10), user: x.LoginUserName || x.UserName, posted: x.IsPosted, d: 0, c: 0, n: 0, acc: []};
     e.d += +x.Debit || 0; e.c += +x.Credit || 0; e.n++; if (e.acc.length < 3) e.acc.push((x.AccountCode || '') + ' ' + (x.AccountName || '')); });
   const all = Object.values(g);
   done({s: r.status, ok: !!j.success, lines: (j.data || []).length, entries: all.length,
         bad: all.filter(e => Math.abs(e.d - e.c) > 0.01).map(e => ({...e, diff: Math.round((e.d - e.c) * 100) / 100}))});
 }).catch(e => done({s: 0, err: String(e)}));
"""


def run(driver, frm, to):
    """-> report rows ({cells, ok}), list of failure lines"""
    r = driver.execute_async_script(READ_JS, URL, frm, to) or {}
    where = "🧾 القيود"
    if not r.get("ok"):
        return [{"cells": [where, "القيود اللي مش متزنة", f"مقدرتش أقرا «تقرير مراجعة قيود اليومية» ({r.get('s')}): {r.get('err', '')[:150]} — اتخطيت"], "ok": None}], []
    bad = sorted(r.get("bad") or [], key=lambda e: -abs(e["diff"]))
    if not bad:
        return [{"cells": [where, "كل قيد: مدين = دائن", f"{r['entries']} قيد ({r['lines']} سطر) — كلهم متزنين"], "ok": True}], []
    total = round(sum(e["diff"] for e in bad), 2)
    one = sum(1 for e in bad if e["n"] == 1)
    rows = [{"cells": [where, "القيود اللي مش متزنة", f"{len(bad)} قيد من {r['entries']} مش متزن — مجموع الفرق {total:+,.2f}"
                       + (f" · منهم {one} قيد بسطر واحد بس (الطرف التاني ما اتسجلش)" if one else "")], "ok": False}]
    for e in bad[:40]:
        rows.append({"cells": [where, f"{e['type']} رقم {e['doc']}" + (f" (عملية {e['op']})" if e.get("op") else ""),
                               f"{e['date']} · مدين {e['d']:,.2f} · دائن {e['c']:,.2f} · الفرق {e['diff']:+,.2f} · {e['n']} سطر"
                               f" · {'مرحّل' if e.get('posted') else 'مش مرحّل'} · {e.get('user') or ''} · {' / '.join(e.get('acc') or [])}"], "ok": False})
    if len(bad) > 40:
        rows.append({"cells": [where, "…", f"و{len(bad) - 40} قيد كمان"], "ok": None})
    logger.warning(f"🧾 {len(bad)} قيد مش متزن — مجموع الفرق {total:+,.2f}")
    kinds = {}
    for e in bad:
        kinds[e["type"]] = kinds.get(e["type"], 0) + 1
    fails = [f"{len(bad)} قيد مش متزن (الفرق {total:+,.2f}): " + "، ".join(f"{k} ×{v}" for k, v in kinds.items())]
    return rows, fails
