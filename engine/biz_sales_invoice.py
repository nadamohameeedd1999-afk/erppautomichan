"""
📋 سيناريو أعمال: «إنشاء فاتورة آجلة بخصم وضريبة ثم حفظها وإعادة فتحها وتعديلها» (19 بند — نموذج المطور)
Runs the developer's Word scenario on NQ ERP's sales invoice exactly like a tester does it by hand (proven on
retcotest 2026-11-10: 17/19 passed), and fills the same Word form with the actual result + evidence of every step.

Parameters (cfg): items [{code, qty, price}] ×2 · qty_edit (new qty of item A) · discount_pct · customer / customer2 (ids,
optional: picked automatically) · department / warehouse (ids, optional) · cases (run 14–18) · readonly_user (19, optional)
The expected values are computed from the parameters (2 items × price, discount, the VAT rate the ERP applies).
Write test: test sites only (engine.guard.require_write).
"""
import base64
import io
import json
import re
import time
from datetime import datetime

from utils.logger import logger

OK, BAD, NA = "ok", "fail", "na"

INSTALL = r"""
window.__nq = window.__nq || {};
const N = window.__nq; N.w = ms => new Promise(r => setTimeout(r, ms));
N.sw = [];
if (window.Swal && !Swal.__nq) {
  const of = Swal.fire.bind(Swal);
  Swal.fire = function (...a) {
    const o = a[0] || {}; const t = (o.title || '') + ' | ' + String(o.text || o.html || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 300);
    N.sw.push(t);
    if (o.showCancelButton && /الحفظ|سند صرف/.test(o.title || '')) return Promise.resolve({isConfirmed: true, value: true});
    return of(...a);
  };
  Swal.__nq = true;
}
window.confirm = m => { N.sw.push('confirm | ' + m); return true; };
window.alert = m => { N.sw.push('alert | ' + m); };
N.v = id => { const e = document.getElementById(id); if (!e) return null;
  return e.tagName === 'SELECT' ? ((e.selectedOptions[0] || {}).textContent || '').trim() : (e.type === 'checkbox' ? e.checked : e.value); };
N.num = id => parseFloat(String($('#' + id).val() || '0').replace(/,/g, '')) || 0;
N.set = async (id, v, ms) => { $('#' + id).val(v).trigger('change'); await N.w(ms || 1200); };
N.opts = id => [...document.querySelectorAll('#' + id + ' option')].filter(o => o.value).map(o => [o.value, o.textContent.trim()]);
N.rows = () => [...document.querySelectorAll('#SalesInvoiceDetails tr')].map(tr => {
  const q = s => { const e = tr.querySelector(s); return e ? (e.tagName === 'SELECT' ? ((e.selectedOptions[0] || {}).textContent || '') : e.value) : ''; };
  return {item: q('.item-name'), qty: parseFloat(q('.quantity')) || 0, unit: q('.item-unit').trim(), eq: parseFloat(q('.unit-equavalent')) || 0,
          price: parseFloat(q('.price')) || 0, total: parseFloat(q('.total')) || 0, id: q('.itemId'), code: q('.barcode')};
}).filter(r => r.item);
N.totals = () => ({total: N.num('Total'), disc: N.num('VoucherDiscountValue'), pct: N.num('VoucherDiscountPercentage'),
                   net: N.num('NetTotal'), tax: N.num('SalesTaxes'), after: N.num('TotalAfterTaxes')});
N.payTable = () => [...document.querySelectorAll('table')].find(t => /طريقة الدفع/.test((t.querySelector('thead') || {}).innerText || ''));
N.pay = () => { const t = N.payTable(); if (!t) return [];
  return [...t.querySelectorAll('tbody tr')].map(tr => ({name: (tr.cells[0] || {}).innerText.trim(),
     amount: parseFloat(([...tr.querySelectorAll('input')].map(i => i.value).find(v => /^-?[\d.,]+$/.test(v) && v.includes('.')) || '0').replace(/,/g, '')) || 0,
     box: [...tr.querySelectorAll('select')].map(s => ((s.selectedOptions[0] || {}).textContent || '').trim()).join('')})); };
N.req = () => [...document.querySelectorAll('input[required],select[required],textarea[required]')]
   .filter(e => (e.type === 'checkbox' ? !e.checked : !String(e.value).trim())).map(e => e.id || e.name);
N.addItem = async (code, qty, price) => {
  const $s = $('#QuickSmartSearch'); $s.val(code); $s.trigger($.Event('keydown', {key: 'Enter'})); await N.w(2500);
  const opts = [...document.querySelectorAll('#QuickSmartSearchHints option')];
  const o = opts.find(x => x.getAttribute('data-barcode') === String(code)) || (opts.length === 1 ? opts[0] : null);
  if (!o) return {err: 'مالقيتش صنف بالكود ' + code + (opts.length ? ' (لقيت ' + opts.length + ' نتيجة)' : '')};
  $s.val(o.value).trigger('change'); await N.w(2500);
  $('#QuickItemQty').val(qty).trigger('input').trigger('change'); await N.w(300);
  $('#QuickItemPrice').val(price).trigger('input').trigger('change'); await N.w(300);
  N.sw.length = 0; $('#QuickItemAddToDetailsBtn').click(); await N.w(3500); $('#QuickSmartSearchClear').click();
  return {picked: o.value, id: o.getAttribute('data-id'), sw: [...N.sw]};
};
N.save = async () => { N.sw.length = 0;
  try { await Promise.race([addEdit(), N.w(15000)]); } catch (e) { N.sw.push('err | ' + e); }
  await N.w(1500); const ok = N.sw.some(s => /^حفظ \|/.test(s));
  return {ok, sw: [...N.sw], req: N.req()}; };
N.get = async (u, ms) => { const ac = new AbortController(); setTimeout(() => ac.abort(), ms || 30000);
  const r = await fetch(u, {credentials: 'include', signal: ac.signal}); return await r.text(); };
N.post = async (u, body, ms) => { const ac = new AbortController(); setTimeout(() => ac.abort(), ms || 35000);
  const r = await fetch(u, {method: 'POST', credentials: 'include', signal: ac.signal, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  return await r.text(); };
N.list = async () => { const d = new DOMParser().parseFromString(await N.get('/SalesInvoice'), 'text/html');
  const tb = [...d.querySelectorAll('table')].find(x => x.querySelectorAll('tbody tr').length > 0); if (!tb) return [];
  return [...tb.querySelectorAll('tbody tr')].slice(0, 15).map(tr => { const a = tr.querySelector('a[href*="SalesInvoice/AddEdit/"]');
    const cells = [...tr.cells].map(c => c.innerText.trim().replace(/\s+/g, ' '));
    return {doc: cells[0], cust: cells[3], total: cells[7], pay: cells[8], id: a ? (a.getAttribute('href').match(/AddEdit\/(\d+)/) || [])[1] : '', text: cells.filter(Boolean).join(' | ').slice(0, 300)}; }); };
N.stock = async (wh, item) => { try { return JSON.parse(await N.get(`/Helper/ItemQuantityOnSystem?warehouseId=${wh}&itemId=${item}&voucherId=0&date=${encodeURIComponent(new Date().toISOString().slice(0, 16))}`)).quantity; } catch (e) { return null; } };
N.balance = async c => { try { return JSON.parse(await N.get('/Helper/GetCustomerDebitBalance/' + c))[0]; } catch (e) { return null; } };
N.journal = async (term, day) => { const f = {DateFrom: day, DateTo: day, BranchId: null, AccountIds: [], AccountId: null, CostCenterId: null, UserId: null,
   IsPosted: null, DebitCreditType: null, SourcePageId: null, ReviewStatus: null, OperationType: null, FlaggedOnly: false, SearchTerm: term || ''};
  for (let i = 0; i < 3; i++) { try { const t = await N.post('/JournalEntriesReview/GetDataJson', f); if (t) return (JSON.parse(t).data || []).map(x => ({je: x.JournalEntryId,
     type: x.DocumentType, doc: x.DocumentNumber, op: x.OperationNumber, acc: (x.AccountCode || '') + ' ' + (x.AccountName || ''), d: +x.Debit || 0, c: +x.Credit || 0,
     posted: x.IsPosted, cust: x.CustomerName || ''})); } catch (e) {} await N.w(2000); }
  return null; };
N.pdf = async u => { const r = await fetch(u, {credentials: 'include'}); const b = new Uint8Array(await r.arrayBuffer());
  let s = ''; for (let i = 0; i < b.length; i += 8192) s += String.fromCharCode.apply(null, b.subarray(i, i + 8192));
  return {type: r.headers.get('content-type'), size: b.length, b64: b.length < 3000000 ? btoa(s) : ''}; };
'installed';
"""


def _js(driver, body, *args):
    """run an async snippet with the helpers installed: body uses N (= window.__nq) and returns a value"""
    script = ("const done = arguments[arguments.length - 1]; const A = Array.from(arguments).slice(0, -1);\n"
              + INSTALL + "\n(async () => { const N = window.__nq; " + body + " })().then(done).catch(e => done({__err: String(e)}));")
    driver.set_script_timeout(240)
    r = driver.execute_async_script(script, *args)
    if isinstance(r, dict) and r.get("__err"):
        raise RuntimeError(r["__err"])
    return r


def _open(driver, path):
    from config.settings import BASE_URL
    driver.get(BASE_URL.rstrip("/") + path)
    for _ in range(30):
        if driver.execute_script("return !!(window.jQuery && document.readyState === 'complete')"):
            break
        time.sleep(0.5)
    time.sleep(2.5)


def _f(x):
    return f"{x:,.2f}"


def _close(a, b, tol=0.011):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


class Run:
    def __init__(self, cfg):
        self.cfg = cfg
        self.steps = {}                 # "01" -> (status, [lines])
        self.facts = {}                 # execution data for the form header
        self.docs = []                  # documents created (left for cleanup)
        self.shots = []

    def put(self, n, status, *lines):
        self.steps[n] = (status, [x for x in lines if x])
        icon = {"ok": "✅", "fail": "❌", "na": "⚪"}[status]
        logger.info(f"{icon} بند {n}: {(lines[0] if lines else '')[:160]}")

    def shot(self, driver, name):
        from engine.check_runner import _shot
        p = _shot(driver, name)
        if p:
            self.shots.append(p)


def expected(items, disc_pct, rate):
    tot = round(sum(i["qty"] * i["price"] for i in items), 2)
    disc = round(tot * disc_pct / 100, 2)
    net = round(tot - disc, 2)
    tax = round(net * rate, 2)
    return {"total": tot, "disc": disc, "net": net, "tax": tax, "after": round(net + tax, 2)}


def _header(driver, run, cust, pay="2"):
    cfg = run.cfg
    return _js(driver, r"""
      const [dep, wh, cust, pay] = A;
      const deps = N.opts('DepartmentId'); await N.set('DepartmentId', dep || (deps[0] || [''])[0], 2000);
      const whs = N.opts('WarehouseId'); await N.set('WarehouseId', wh || (whs[0] || [''])[0], 1200);
      if (cust) await N.set('VendorOrCustomerId', cust, 3000);
      await N.set('InvoiceTypeId', '1', 600); await N.set('PaymentType', pay, 1500);
      if ($('#ItemwithVat').prop('checked')) $('#ItemwithVat').click();
      if (!$('#AutoGenerateStockReceiptVoucher').prop('checked')) $('#AutoGenerateStockReceiptVoucher').click();
      const filled = [];
      const fill = (id, v) => { const e = document.getElementById(id); if (e && e.required && !String(e.value).trim()) { $(e).val(v).trigger('input').trigger('change'); filled.push(id); } };
      fill('CommercialRegistrationNumber', '1010101010'); fill('CashCustomerVATNumber', '300000000000003');
      fill('BuildingNumber', '1234'); fill('PostalCode', '12345');
      if (document.getElementById('CountryId')?.required && !$('#CountryId').val()) { const sa = N.opts('CountryId').find(o => /السعودية|Saudi/.test(o[1])); if (sa) { await N.set('CountryId', sa[0], 2000); filled.push('CountryId'); } }
      if (document.getElementById('CityId')?.required && !$('#CityId').val()) { const c = N.opts('CityId').find(o => /الرياض/.test(o[1])) || N.opts('CityId')[0]; if (c) { await N.set('CityId', c[0], 600); filled.push('CityId'); } }
      return {dep: N.v('DepartmentId'), depId: $('#DepartmentId').val(), wh: N.v('WarehouseId'), whId: $('#WarehouseId').val(), cust: N.v('VendorOrCustomerId'),
              custId: $('#VendorOrCustomerId').val(), inv: N.v('InvoiceTypeId'), pay: N.v('PaymentType'), cur: N.v('CurrencyId'), rate: N.v('CurrencyEquivalent'),
              date: N.v('VoucherDate'), rep: N.v('CustomerRepId'), auto: $('#AutoGenerateStockReceiptVoucher').prop('checked'), filled, req: N.req()};
    """, cfg.get("department") or "", cfg.get("warehouse") or "", cust or "", pay)


def _pick_customer(driver, run, exclude=()):
    want = str(run.cfg.get("customer") or "")
    return _js(driver, r"""
      const [want, exclude] = A; const cs = N.opts('VendorOrCustomerId').filter(c => !exclude.includes(c[0]));
      const order = want ? [cs.find(c => c[0] === want)].filter(Boolean).concat(cs) : cs;
      for (const c of order.slice(0, 25)) { const b = await N.balance(c[0]); if (b && b.Result === 'can') return {id: c[0], name: c[1], balance: b.Balance, limit: b.CreditLimitAmount}; }
      return null;
    """, want, list(exclude))


def run_sales_invoice(driver, credentials, cfg, result=None):
    from engine.screen_runner import login
    from engine.guard import require_write
    from config.settings import BASE_URL
    result = result if result is not None else {}
    require_write("سيناريو فاتورة البيع")
    run = Run(cfg)
    items = [{"code": str(i.get("code")), "qty": float(i.get("qty")), "price": float(i.get("price"))} for i in (cfg.get("items") or [])][:2]
    if len(items) < 2:
        raise AssertionError("حددي صنفين (الكود + الكمية + السعر) في إعدادات السيناريو")
    disc_pct = float(cfg.get("discount_pct", 10))
    qty_edit = float(cfg.get("qty_edit", items[0]["qty"] + 2))
    day = datetime.now().strftime("%Y-%m-%d")
    login(driver, credentials)
    run.facts.update({"site": BASE_URL, "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "user": credentials.get("username") or ""})

    # ---------- 01 open a new invoice
    _open(driver, "/SalesInvoice/AddEdit")
    s1 = _js(driver, "return {rows: N.rows().length, total: N.num('Total'), doc: $('#DocumentNumber').val(), cust: $('#VendorOrCustomerId').val(), notes: $('#Notes').val()};")
    clean = s1["rows"] == 0 and not s1["total"] and not s1["doc"] and not s1["cust"] and not s1["notes"]
    run.put("01", OK if clean else BAD, f"الفعلي: سطور {s1['rows']} · الإجمالي {_f(s1['total'])} · رقم المستند «{s1['doc'] or '—'}» · العميل «{s1['cust'] or '—'}» · الملاحظات «{s1['notes'] or '—'}».",
            "الدليل: قراءة الحقول بعد فتح /SalesInvoice/AddEdit")

    # ---------- prep: customer with credit room
    cust = _pick_customer(driver, run)
    if not cust:
        run.put("02", BAD, "متعذر: مفيش عميل حده الائتماني يسمح (فحصت أول 25 عميل)")
        return _finish(driver, run, result, items, disc_pct, qty_edit, fatal="مفيش عميل بحد ائتماني يسمح")
    h = _header(driver, run, cust["id"])
    run.facts.update({"customer": h["cust"], "customer_id": h["custId"], "warehouse": h["wh"], "warehouse_id": h["whId"], "department": h["dep"], "auto_issue": h["auto"]})
    ok2 = not h["req"]
    run.put("02", OK if ok2 else BAD,
            f"الفعلي: الفرع {h['dep']} · المخزن {h['wh']} · العميل {h['cust']} · {h['inv']} · {h['cur']} معامل {h['rate']} · {h['date']} · المندوب {h['rep'] or '—'}.",
            ("ملاحظة: الفاتورة طلبت إجباري وأنا ملّيت قيم اختبار: " + "، ".join(h["filled"])) if h["filled"] else "",
            ("حقول إجبارية لسه فاضية: " + "، ".join(h["req"])) if h["req"] else "", "الدليل: قيم الحقول قبل الحفظ")

    # ---------- 03 items
    added = []
    for it in items:
        r = _js(driver, "return await N.addItem(A[0], A[1], A[2]);", it["code"], str(it["qty"]), str(it["price"]))
        added.append(r)
    rows = _js(driver, "return N.rows();")
    run.facts["items"] = rows
    want_lines = [round(i["qty"] * i["price"], 2) for i in items]
    ok3 = len(rows) == 2 and all(_close(rows[k]["total"], want_lines[k]) for k in range(2)) and all(r["eq"] == 1 for r in rows)
    errs = [a["err"] for a in added if a.get("err")]
    run.put("03", OK if ok3 and not errs else BAD,
            "الفعلي: " + " · ".join(f"{r['item'][:40]} = {r['qty']:g} × {r['price']:g} = {_f(r['total'])} ({r['unit']} معامل {r['eq']:g})" for r in rows)
            + f" · إجمالي البنود {_f(sum(r['total'] for r in rows))}.",
            ("مشكلة: " + "؛ ".join(errs)) if errs else "",
            "انحراف عن التجهيز: وحدة الصنف معاملها مش 1" if rows and any(r["eq"] != 1 for r in rows) else "", "الدليل: سطور الجدول")
    if len(rows) < 2:
        return _finish(driver, run, result, items, disc_pct, qty_edit, fatal="الأصناف ما اتضافتش")

    # ---------- 04/05 discount + tax
    t0 = _js(driver, "await N.w(1500); return N.totals();")
    t = _js(driver, "$('#VoucherDiscountPercentage').val(A[0]).trigger('input').trigger('keyup').trigger('change').trigger('blur'); await N.w(3000); return N.totals();", str(disc_pct))
    rate = round(t["tax"] / t["net"], 4) if t["net"] else 0.15
    exp = expected(items, disc_pct, rate)
    run.facts.update({"rate": rate, "expected": exp})
    run.put("04", OK if _close(t["disc"], exp["disc"]) and _close(t["net"], exp["net"]) else BAD,
            f"الفعلي: نسبة {disc_pct:g}% → الخصم {_f(t['disc'])} (المتوقع {_f(exp['disc'])}) · الصافي {_f(t['net'])} (المتوقع {_f(exp['net'])}).", "الدليل: حقول الإجماليات")
    run.put("05", OK if _close(t["tax"], exp["tax"]) and _close(t["after"], exp["after"]) else BAD,
            f"الفعلي: الضريبة {_f(t['tax'])} ({rate * 100:g}%) · الإجمالي النهائي {_f(t['after'])} (المتوقع {_f(exp['after'])}) — قبل الخصم كانت {_f(t0['tax'])} / {_f(t0['after'])}.",
            "الدليل: حقول الإجماليات")

    # ---------- 06 payment split
    pay = _js(driver, "return N.pay();")
    credit = next((p for p in pay if "آجل" in p["name"]), None)
    others = [p for p in pay if p is not credit and p["amount"]]
    run.put("06", OK if credit and _close(credit["amount"], exp["after"]) and not others else BAD,
            "الفعلي: " + " · ".join(f"{p['name']} {_f(p['amount'])}" for p in pay) + ".", "الدليل: جدول طرق الدفع")

    # ---------- 07 save once
    marker = f"TC-SI-01 سيناريو فاتورة البيع — اختبار آلي {datetime.now():%Y-%m-%d %H:%M}"
    before = _js(driver, "const [wh, a, b, c] = A; return {a: await N.stock(wh, a), b: await N.stock(wh, b), bal: await N.balance(c), list: (await N.list()).slice(0, 3)};",
                 h["whId"], rows[0]["id"], rows[1]["id"], h["custId"])
    run.facts["before"] = before
    sv = _js(driver, "$('#Notes').val(A[0]).trigger('change'); return await N.save();", marker)
    run.shot(driver, "biz_si_after_save")
    time.sleep(2)
    lst = _js(driver, "return await N.list();")
    new = [r for r in lst if r["doc"] not in {x["doc"] for x in before["list"]}][:3]
    inv = new[0] if new else None
    if not (sv["ok"] and inv):
        why = next((s for s in sv["sw"] if not s.startswith(("انشاء سند", "هل تريد"))), "") or ("حقول إجبارية فاضية: " + "، ".join(sv["req"]) if sv["req"] else "مفيش رسالة")
        run.put("07", BAD, f"الفعلي: الفاتورة ما اتحفظتش — {why}", "الدليل: رسالة الحفظ")
        return _finish(driver, run, result, items, disc_pct, qty_edit, fatal="الفاتورة ما اتحفظتش: " + why[:200])
    run.docs.append(f"فاتورة {inv['doc']}")
    run.facts.update({"invoice_no": inv["doc"], "invoice_id": inv["id"], "marker": marker})
    run.put("07", OK if len(new) == 1 else BAD,
            f"الفعلي: اتحفظت من ضغطة واحدة — رقم {inv['doc']} · المعرف {inv['id']} · {inv['total']} {inv['pay']} في أول القايمة."
            + ("" if len(new) == 1 else f" ⚠️ ظهر {len(new)} فواتير جديدة!"), "الدليل: أول صف في قايمة فواتير البيع")

    # ---------- 08 reopen
    _open(driver, f"/SalesInvoice/AddEdit/{inv['id']}")
    r8 = _js(driver, "return {doc: $('#DocumentNumber').val(), cust: $('#VendorOrCustomerId').val(), wh: $('#WarehouseId').val(), rows: N.rows(), t: N.totals(), pay: N.pay(), notes: $('#Notes').val()};")
    same = (r8["doc"] == inv["doc"] and r8["cust"] == h["custId"] and r8["wh"] == h["whId"] and len(r8["rows"]) == 2
            and all(_close(r8["rows"][k]["qty"], items[k]["qty"]) and _close(r8["rows"][k]["price"], items[k]["price"]) for k in range(2))
            and _close(r8["t"]["after"], exp["after"]) and _close(r8["t"]["disc"], exp["disc"]) and marker[:20] in (r8["notes"] or ""))
    run.put("08", OK if same else BAD,
            f"الفعلي: رقم {r8['doc']} · نفس العميل والمخزن · " + " / ".join(f"{r['qty']:g}×{r['price']:g}" for r in r8["rows"])
            + f" · الخصم {_f(r8['t']['disc'])} · الضريبة {_f(r8['t']['tax'])} · النهائي {_f(r8['t']['after'])} · الملاحظة {'موجودة' if marker[:20] in (r8['notes'] or '') else 'مش موجودة'}.",
            "الدليل: الحقول بعد إعادة الفتح")

    # ---------- 09 print
    _step_print(driver, run, inv, exp)

    # ---------- 10 edit qty
    items2 = [dict(items[0], qty=qty_edit), items[1]]
    exp2 = expected(items2, disc_pct, rate)
    run.facts["expected2"] = exp2
    t10 = _js(driver, r"""
      const tr = [...document.querySelectorAll('#SalesInvoiceDetails tr')].find(tr => (tr.querySelector('.itemId') || {}).value === A[0]);
      if (!tr) return {err: 'row'}; $(tr.querySelector('.quantity')).val(A[1]).trigger('input').trigger('keyup').trigger('change').trigger('blur');
      await N.w(3500); return {t: N.totals(), pay: N.pay()};""", rows[0]["id"], str(qty_edit))
    tt = t10.get("t") or {}
    ok10 = all(_close(tt.get(k), exp2[k]) for k in ("total", "disc", "net", "tax", "after"))
    run.put("10", OK if ok10 else BAD,
            f"الفعلي: كمية A {items[0]['qty']:g} → {qty_edit:g}: الإجمالي {_f(tt.get('total', 0))} · الخصم {_f(tt.get('disc', 0))} · الصافي {_f(tt.get('net', 0))} · الضريبة {_f(tt.get('tax', 0))} · النهائي {_f(tt.get('after', 0))}"
            f" (المتوقع {_f(exp2['total'])} / {_f(exp2['disc'])} / {_f(exp2['net'])} / {_f(exp2['tax'])} / {_f(exp2['after'])}).", "الدليل: الإجماليات بعد التعديل")

    # ---------- 11 save the edit, reopen
    s11 = _js(driver, "return await N.save();")
    time.sleep(2)
    lst2 = _js(driver, "return await N.list();")
    _open(driver, f"/SalesInvoice/AddEdit/{inv['id']}")
    r11 = _js(driver, "return {doc: $('#DocumentNumber').val(), rows: N.rows(), t: N.totals()};")
    extra = [r for r in lst2 if r["doc"] not in {x["doc"] for x in lst}]
    q = [r["qty"] for r in r11["rows"]]
    ok11 = s11["ok"] and r11["doc"] == inv["doc"] and not extra and len(q) == 2 and _close(q[0], qty_edit) and _close(q[1], items[1]["qty"]) and _close(r11["t"]["after"], exp2["after"])
    run.put("11", OK if ok11 else BAD,
            f"الفعلي: {'اتحفظ' if s11['ok'] else 'ما اتحفظش'} · بعد الفتح رقم {r11['doc']} (نفس المعرف {inv['id']}) · كمية A {q[0] if q else '—'} وB {q[1] if len(q) > 1 else '—'} · النهائي {_f(r11['t']['after'])}"
            + (" · مفيش فاتورة جديدة في القايمة." if not extra else f" · ⚠️ ظهرت فاتورة جديدة {extra[0]['doc']}"), "الدليل: القايمة + إعادة الفتح")

    # ---------- 12 stock, 13 journal
    after = _js(driver, "const [wh, a, b, c] = A; return {a: await N.stock(wh, a), b: await N.stock(wh, b), bal: await N.balance(c)};", h["whId"], rows[0]["id"], rows[1]["id"], h["custId"])
    da = None if before["a"] is None or after["a"] is None else round(before["a"] - after["a"], 3)
    db = None if before["b"] is None or after["b"] is None else round(before["b"] - after["b"], 3)
    if da is None:
        run.put("12", NA, "لم يُختبر: مقدرتش أقرا رصيد الصنف في المخزن")
    else:
        ok12 = _close(da, qty_edit) and _close(db, items[1]["qty"])
        run.put("12", OK if ok12 else BAD,
                f"الفعلي: رصيد A {before['a']:g} → {after['a']:g} (نقص {da:g}، المتوقع {qty_edit:g}) · B {before['b']:g} → {after['b']:g} (نقص {db:g}، المتوقع {items[1]['qty']:g}).",
                "" if h["auto"] else "ملاحظة: إنشاء سند الصرف الآلي مش متفعل", "الدليل: رصيد الصنف في المخزن قبل وبعد")
    _step_journal(driver, run, inv, exp2, day, before, after)

    # ---------- 14–18
    if cfg.get("cases", True):
        _cases(driver, run, items, cust, rows, h, day)
    if not cfg.get("readonly_user"):
        run.put("19", NA, "الفعلي: لم يُنفذ — محتاج مستخدم من غير صلاحية تعديل (عرّفيه في إعدادات السيناريو)")
    return _finish(driver, run, result, items, disc_pct, qty_edit)


def _step_print(driver, run, inv, exp):
    try:
        p = _js(driver, "return await N.pdf(A[0]);", f"/Report/E_Invoice/{inv['id']}?print=True")
    except Exception as e:
        run.put("09", NA, f"لم يُختبر: مقدرتش أفتح الطباعة ({e})")
        return
    if "pdf" not in (p.get("type") or "") or not p.get("b64"):
        run.put("09", BAD, f"الفعلي: الطباعة رجعت «{p.get('type')}» حجم {p.get('size')} — مش ملف PDF")
        return
    text = ""
    try:
        from pypdf import PdfReader
        rd = PdfReader(io.BytesIO(base64.b64decode(p["b64"])))
        text = " ".join((pg.extract_text() or "") for pg in rd.pages)
    except Exception:
        pass
    flat = text.replace(",", "")
    checks = {"رقم الفاتورة": inv["doc"] in flat, "الإجمالي": f"{exp['total']:.2f}" in flat, "الخصم": f"{exp['disc']:.2f}" in flat,
              "الضريبة": f"{exp['tax']:.2f}" in flat, "المستحق": f"{exp['after']:.2f}" in flat}
    if not text.strip():
        run.put("09", OK, f"الفعلي: الطباعة فتحت ملف PDF ({p['size'] // 1024} KB، صفحة على الأقل).",
                "ملاحظة: الملف صورة مش نص — مقدرتش أقارن القيم آليًا؛ راجعيه من الرابط", f"الدليل: /Report/E_Invoice/{inv['id']}")
        return
    miss = [k for k, v in checks.items() if not v]
    run.put("09", OK if not miss else BAD, f"الفعلي: ملف PDF ({p['size'] // 1024} KB) فيه: " + "، ".join(f"{k} {'✓' if v else '✗'}" for k, v in checks.items()) + ".",
            ("مش لاقي: " + "، ".join(miss)) if miss else "", f"الدليل: /Report/E_Invoice/{inv['id']}")


def _step_journal(driver, run, inv, exp2, day, before, after):
    lines = _js(driver, "return await N.journal(A[0], A[1]);", str(inv["id"]), day)
    if lines is None:
        run.put("13", NA, "لم يُختبر: مقدرتش أقرا «تقرير مراجعة قيود اليومية»")
        return
    je = [x for x in lines if x["op"] == str(inv["id"]) and "فواتير البيع" in (x["type"] or "")] or [x for x in lines if x["op"] == str(inv["id"])]
    ids = sorted({x["je"] for x in je})
    d, c = round(sum(x["d"] for x in je), 2), round(sum(x["c"] for x in je), 2)
    cust_d = round(sum(x["d"] for x in je if x["cust"]), 2)
    vat_c = round(sum(x["c"] for x in je if "ضريبة" in x["acc"]), 2)
    posted = all(x["posted"] for x in je) if je else False
    ok = je and len(ids) == 1 and _close(d, c) and _close(cust_d, exp2["after"]) and _close(vat_c, exp2["tax"])
    stmt = (f"كشف العميل: الرصيد {before.get('bal', {}).get('Balance') if before.get('bal') else '—'} → {after.get('bal', {}).get('Balance') if after.get('bal') else '—'}")
    lines_txt = " · ".join(f"{x['acc'].strip()[:30]} م {_f(x['d'])} د {_f(x['c'])}" for x in je[:6])
    if ok and not posted:
        run.put("13", NA, f"الفعلي: القيد {ids[0]} متزن ({_f(d)} = {_f(c)}) ومرتبط بالفاتورة: {lines_txt}.",
                f"لم يُختبر: القيد «غير مرحّل» فكشف العميل لسه ما اتأثرش ({stmt}) — يتراجع بعد الترحيل.", "الدليل: تقرير مراجعة قيود اليومية")
    else:
        run.put("13", OK if ok else BAD, f"الفعلي: قيود الفاتورة {ids or '—'} · مدين {_f(d)} · دائن {_f(c)} · مدين العميل {_f(cust_d)} (المتوقع {_f(exp2['after'])}) · الضريبة {_f(vat_c)} (المتوقع {_f(exp2['tax'])}) · {stmt}.",
                lines_txt, "الدليل: تقرير مراجعة قيود اليومية")


def _new_invoice(driver, run, cust_id, pay="2"):
    _open(driver, "/SalesInvoice/AddEdit")
    return _header(driver, run, cust_id, pay)


def _cases(driver, run, items, cust, rows, h, day):
    base_docs = {r["doc"] for r in _js(driver, "return await N.list();")}

    # 14 missing required data, each alone
    try:
        res = []
        _open(driver, "/SalesInvoice/AddEdit")
        _header(driver, run, "")
        _js(driver, "return await N.addItem(A[0], '1', A[1]);", items[0]["code"], str(items[0]["price"]))
        a = _js(driver, "return await N.save();")
        res.append(("من غير عميل", a))
        _js(driver, "await N.set('VendorOrCustomerId', A[0], 3000); await N.set('PaymentType', '2', 800); await N.set('WarehouseId', '', 800); return 1;", cust["id"])
        _js(driver, "const f = id => { const e = document.getElementById(id); if (e && e.required && !String(e.value).trim()) $(e).val(id === 'CashCustomerVATNumber' ? '300000000000003' : '1010101010').trigger('change'); }; f('CommercialRegistrationNumber'); f('CashCustomerVATNumber'); return 1;")
        b = _js(driver, "return await N.save();")
        res.append(("من غير مخزن", b))
        _js(driver, "await N.set('WarehouseId', A[0], 1000); document.querySelectorAll('#SalesInvoiceDetails tr a[onclick*=\"deleteElement\"]').forEach(x => x.click()); await N.w(1200); document.querySelectorAll('.swal2-confirm').forEach(x => x.click()); await N.w(800); return 1;", h["whId"])
        c = _js(driver, "return await N.save();")
        res.append(("من غير أصناف", c))
        now = {r["doc"] for r in _js(driver, "return await N.list();")}
        created = now - base_docs
        txt = " · ".join(f"{k}: {'اتمنع' if not v['ok'] else 'اتحفظ!'} ({(next((s for s in v['sw'] if s), '') or 'تعليم الحقول بالأحمر')[:60]})" for k, v in res)
        run.put("14", OK if all(not v["ok"] for _, v in res) and not created else BAD, "الفعلي: " + txt + ".",
                "مفيش فاتورة اتعملت في أي محاولة." if not created else f"⚠️ اتعملت فواتير: {', '.join(created)}", "الدليل: القايمة بعد المحاولات")
        base_docs = now
    except Exception as e:
        run.put("14", NA, f"لم يُكمل: {str(e)[:200]}")

    # 15 swap customer before saving
    try:
        c2 = _pick_customer(driver, run, exclude=[cust["id"]])
        if not c2:
            raise RuntimeError("مفيش عميل تاني بحد ائتماني يسمح")
        _new_invoice(driver, run, cust["id"])
        s = _js(driver, r"""const snap = () => ({cust: N.v('VendorOrCustomerId'), name: $('#CashCustomerName').val(), cr: $('#CommercialRegistrationNumber').val(), bld: $('#BuildingNumber').val()});
          const a = snap(); await N.set('VendorOrCustomerId', A[0], 3000); await N.set('PaymentType', '2', 800);
          const f = (id, v) => { const e = document.getElementById(id); if (e && e.required && !String(e.value).trim()) $(e).val(v).trigger('change'); };
          f('CommercialRegistrationNumber', '1010202020'); f('CashCustomerVATNumber', '300000000000003'); f('BuildingNumber', '2222'); f('PostalCode', '11942');
          return {a, b: snap()};""", c2["id"])
        _js(driver, "return await N.addItem(A[0], '1', A[1]);", items[0]["code"], str(items[0]["price"]))
        sv = _js(driver, "$('#Notes').val('TC-SI-15 استبدال العميل — اختبار آلي').trigger('change'); return await N.save();")
        time.sleep(2)
        lst = _js(driver, "return await N.list();")
        new = [r for r in lst if r["doc"] not in base_docs]
        if not (sv["ok"] and new):
            raise RuntimeError("ما اتحفظتش: " + (" | ".join(sv["sw"]) or "، ".join(sv["req"]))[:150])
        run.docs.append(f"فاتورة {new[0]['doc']}")
        _open(driver, f"/SalesInvoice/AddEdit/{new[0]['id']}")
        r = _js(driver, "return {cust: $('#VendorOrCustomerId').val(), name: N.v('VendorOrCustomerId')};")
        run.put("15", OK if r["cust"] == c2["id"] else BAD,
                f"الفعلي: اخترت «{s['a']['cust']}» ثم «{s['b']['cust']}» قبل الحفظ — بيانات الأول اتشالت (السجل {s['a']['cr'] or '—'} → {s['b']['cr'] or '—'}). اتحفظت {new[0]['doc']} وبعد الفتح العميل «{r['name']}».",
                "الدليل: إعادة فتح الفاتورة")
        base_docs |= {x["doc"] for x in new}
    except Exception as e:
        run.put("15", NA, f"لم يُكمل: {str(e)[:200]}")

    # 16 cash invoice with the original data
    try:
        _new_invoice(driver, run, cust["id"], pay="1")
        for it in items:
            _js(driver, "return await N.addItem(A[0], A[1], A[2]);", it["code"], str(it["qty"]), str(it["price"]))
        _js(driver, "$('#VoucherDiscountPercentage').val(A[0]).trigger('input').trigger('keyup').trigger('change').trigger('blur'); await N.w(3000); return 1;", str(float(run.cfg.get("discount_pct", 10))))
        box = _js(driver, r"""const t = N.payTable(); const s = t && t.querySelector('tbody tr select'); if (!s) return {box: ''};
          const was = s.value; if (!s.value) { const o = [...s.options].find(o => o.value); if (o) $(s).val(o.value).trigger('change'); } await N.w(600);
          return {was, box: ((s.selectedOptions[0] || {}).textContent || '').trim()};""")
        sv = _js(driver, "$('#Notes').val('TC-SI-16 فاتورة نقدية — اختبار آلي').trigger('change'); return await N.save();")
        time.sleep(2)
        lst = _js(driver, "return await N.list();")
        new = [r for r in lst if r["doc"] not in base_docs]
        if not (sv["ok"] and new):
            raise RuntimeError("ما اتحفظتش: " + (" | ".join(sv["sw"]) or "، ".join(sv["req"]))[:150])
        run.docs.append(f"فاتورة {new[0]['doc']}")
        _open(driver, f"/SalesInvoice/AddEdit/{new[0]['id']}")
        r = _js(driver, "return {pay: N.pay(), t: N.totals(), pt: N.v('PaymentType')};")
        cash = next((p for p in r["pay"] if "نقد" in p["name"]), {"amount": 0, "box": ""})
        credit = next((p for p in r["pay"] if "آجل" in p["name"]), {"amount": 0})
        exp = run.facts["expected"]
        run.put("16", OK if _close(cash["amount"], exp["after"]) and not credit["amount"] else BAD,
                f"الفعلي: {new[0]['doc']} — {r['pt']}: نقدي {_f(cash['amount'])} للصندوق «{cash['box'] or '—'}» · آجل {_f(credit['amount'])} · النهائي {_f(r['t']['after'])}.",
                "ملاحظة: الصندوق ما اتحطش تلقائيًا — اخترته أنا" if not box.get("was") else "", "الدليل: جدول الدفع بعد إعادة الفتح")
        base_docs |= {x["doc"] for x in new}
    except Exception as e:
        run.put("16", NA, f"لم يُكمل: {str(e)[:200]}")

    # 17 more than the available quantity
    try:
        _new_invoice(driver, run, cust["id"])
        avail = _js(driver, "return await N.stock(A[0], A[1]);", h["whId"], rows[0]["id"])
        if avail is None:
            raise RuntimeError("مقدرتش أقرا الرصيد المتاح")
        over = max(int(avail), 0) + 50
        _js(driver, "return await N.addItem(A[0], A[1], A[2]);", items[0]["code"], str(over), str(items[0]["price"]))
        sv = _js(driver, "$('#Notes').val('TC-SI-17 كمية أكبر من المتاح — اختبار آلي').trigger('change'); return await N.save();")
        time.sleep(2)
        lst = _js(driver, "return await N.list();")
        new = [r for r in lst if r["doc"] not in base_docs]
        if sv["ok"] and new:
            run.docs.append(f"فاتورة {new[0]['doc']} (رصيد سالب)")
            left = _js(driver, "return await N.stock(A[0], A[1]);", h["whId"], rows[0]["id"])
            run.put("17", OK, f"الفعلي: المتاح {avail:g} · كتبت {over} → اتحفظت {new[0]['doc']} من غير تحذير والرصيد بقى {left}. البيئة دي بتسمح بالمخزون السالب.",
                    "يحتاج تأكيد: لو السياسة المعتمدة «منع» يبقى ده فاشل.", "الدليل: رصيد الصنف بعد الحفظ")
            base_docs |= {x["doc"] for x in new}
        else:
            why = next((s for s in sv["sw"] if not s.startswith(("انشاء سند", "هل تريد"))), "")
            run.put("17", OK if not new else BAD, f"الفعلي: المتاح {avail:g} · كتبت {over} → الحفظ اتمنع: {why or 'من غير رسالة'} · مفيش فاتورة اتعملت.", "الدليل: رسالة الحفظ + القايمة")
    except Exception as e:
        run.put("17", NA, f"لم يُكمل: {str(e)[:200]}")

    # 18 save twice fast
    try:
        _new_invoice(driver, run, cust["id"])
        _js(driver, "return await N.addItem(A[0], '1', A[1]);", items[1]["code"], str(items[1]["price"]))
        _js(driver, r"""$('#Notes').val('TC-SI-18 حفظ مرتين بسرعة — اختبار آلي').trigger('change'); await N.w(1500); N.sw.length = 0;
          const p1 = addEdit(); const p2 = addEdit(); await Promise.race([Promise.all([p1, p2]), N.w(15000)]); await N.w(2500); return N.sw;""")
        time.sleep(2)
        lst = _js(driver, "return await N.list();")
        new = [r for r in lst if r["doc"] not in base_docs]
        for x in new:
            run.docs.append(f"فاتورة {x['doc']}")
        run.put("18", OK if len(new) == 1 else BAD, f"الفعلي: الحفظ اتنادى مرتين ورا بعض → اتعمل {len(new)} فاتورة ({', '.join(x['doc'] for x in new) or '—'}).",
                "الدليل: القايمة بعد الحفظ")
    except Exception as e:
        run.put("18", NA, f"لم يُكمل: {str(e)[:200]}")


def _finish(driver, run, result, items, disc_pct, qty_edit, fatal=""):
    for n in [f"{i:02d}" for i in range(1, 20)]:
        if n not in run.steps:
            run.put(n, NA, "لم يُنفذ — " + (f"متوقف على: {fatal}" if fatal else "مش ضمن التشغيلة دي"))
    counts = {k: sum(1 for s, _ in run.steps.values() if s == k) for k in (OK, BAD, NA)}
    names = {OK: "ناجح", BAD: "فاشل", NA: "لم يُختبر"}
    rows = [{"cells": [n, names[s], " · ".join(lines)], "ok": True if s == OK else (False if s == BAD else None)} for n, (s, lines) in sorted(run.steps.items())]
    doc_path = ""
    try:
        doc_path = fill_word(run, counts)
    except Exception as e:
        logger.warning(f"نموذج الورد ما اتملاش: {e}")
    note = (f"ناجح {counts[OK]} · فاشل {counts[BAD]} · لم يُختبر {counts[NA]} من 19 · فاتورة {run.facts.get('invoice_no', '—')}"
            + (f" · المستندات المتبقية: {', '.join(run.docs)}" if run.docs else ""))
    result["detail"] = {"title": "📋 سيناريو فاتورة البيع الآجلة (19 بند)", "columns": ["البند", "الحالة", "الفعلي والدليل"], "rows": rows, "note": note,
                        "files": [{"name": "نموذج التنفيذ (Word)", "path": doc_path}] if doc_path else []}
    result["screenshots"] = run.shots
    result["biz"] = {"steps": run.steps, "facts": run.facts, "docs": run.docs, "word": doc_path}
    logger.info("📋 " + note)
    if counts[BAD] or fatal:
        e = AssertionError(f"سيناريو فاتورة البيع: فاشل {counts[BAD]} · ناجح {counts[OK]} · لم يُختبر {counts[NA]}"
                           + (f"\n   توقف: {fatal}" if fatal else "") + "".join(f"\n   بند {n}: {l[0][:150]}" for n, (s, l) in sorted(run.steps.items()) if s == BAD))
        e.partial_result = result
        raise e
    return result


# ------------------------------------------------------------------ the developer's Word form, filled
def fill_word(run, counts):
    import copy
    import docx
    from config import paths
    tpl = paths.BASE_DIR / "templates_biz" / "SalesInvoice-Test-Scenario.docx"
    if not tpl.exists():
        return ""
    d = docx.Document(str(tpl))

    def set_cell(cell, lines):
        ps = cell.paragraphs
        for p in ps[1:]:
            p._element.getparent().remove(p._element)
        p = ps[0]
        for r in p.runs[1:]:
            r._element.getparent().remove(r._element)
        for k, line in enumerate(lines or ["—"]):
            if k == 0:
                (p.runs[0] if p.runs else p.add_run()).text = line
            else:
                el = copy.deepcopy(p._element)
                cell._element.append(el)
                q = docx.text.paragraph.Paragraph(el, cell)
                for r in q.runs[1:]:
                    r._element.getparent().remove(r._element)
                q.runs[0].text = line

    f = run.facts
    head = {"اسم المختبِر": "اختبار آلي — أتمتة اختبارات ERP", "تاريخ التنفيذ": f.get("date", ""), "الشركة وقاعدة الاختبار": f.get("site", ""),
            "رابط الموقع أو الإصدار": f.get("site", ""), "المستخدم والفرع": f"{f.get('user', '')} — {f.get('department', '')}",
            "المخزن والعميل": f"{f.get('warehouse', '')} — {f.get('customer', '')}",
            "رقم الفاتورة ومعرفها": f"{f.get('invoice_no', '—')} — المعرف {f.get('invoice_id', '—')}"}
    for r in d.tables[0].rows:
        c = r.cells
        for i in (0, 2):
            k = c[i].text.strip()
            if k in head:
                set_cell(c[i + 1], [head[k]])
            if k.startswith("توليد إذن"):
                set_cell(c[i + 1], ["☑ مفعل" if f.get("auto_issue") else "☑ غير مفعل"])
            if k.startswith("مرحلة إثبات"):
                set_cell(c[i + 1], ["☑ عند الحفظ (غير مرحّل لحد الاعتماد)"])
    its = f.get("items") or []
    bef = f.get("before") or {}
    for k, r in enumerate(d.tables[1].rows[1:3]):
        if k < len(its):
            set_cell(r.cells[1], [f"{its[k]['code'] or ''} {its[k]['item'][:40]}"])
            set_cell(r.cells[2], [f"{bef.get('a' if k == 0 else 'b', '—')} (فعلي قبل الاختبار)"])
            set_cell(r.cells[3], [f"{its[k]['qty']:g}"]); set_cell(r.cells[4], [_f(its[k]["price"])]); set_cell(r.cells[5], [_f(its[k]["total"])])
    mark = {OK: "☑ ناجح", BAD: "☑ فاشل", NA: "☑ لم يُختبر"}
    for t in d.tables[2:5]:
        for r in t.rows[1:]:
            n = r.cells[0].text.strip()
            if n in run.steps:
                s, lines = run.steps[n]
                set_cell(r.cells[3], lines)
                set_cell(r.cells[4], [mark[s]])
    total = "ناجح" if not counts[BAD] and not counts[NA] else ("فاشل" if counts[BAD] else "غير مكتمل")
    for p in d.paragraphs:
        tx = p.text

        def put(x):
            p.runs[0].text = x
            for rr in p.runs[1:]:
                rr.text = ""
        if tx.startswith("تأكيد التجهيز") and p.runs:
            put(f"تأكيد التجهيز ☑ مكتمل — النسبة المعتمدة {f.get('rate', 0.15) * 100:g}%")
        if tx.startswith("النتيجة الإجمالية") and p.runs:
            put(f"النتيجة الإجمالية ☑ {total} — ناجح {counts[OK]} · فاشل {counts[BAD]} · لم يُختبر {counts[NA]} من إجمالي 19 بندًا")
        if tx.startswith("أرقام مستندات الاختبار المتبقية") and p.runs:
            put("أرقام مستندات الاختبار المتبقية: " + (", ".join(run.docs) or "لا يوجد"))
        if tx.startswith("رقم الفاتورة") and "المعرف" in tx and p.runs:
            put(f"رقم الفاتورة {f.get('invoice_no', '—')} · المعرف {f.get('invoice_id', '—')} · ملاحظة الاختبار: {f.get('marker', '')}")
    out = paths.RESULTS_DIR / f"biz_sales_invoice_{datetime.now():%Y%m%d_%H%M%S}.docx"
    d.save(str(out))
    return str(out)
