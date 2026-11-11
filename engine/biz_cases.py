"""
📚 حزم سيناريوهات المطور (ملفات Word: SAL · PUR · SRT · PRT · CRV · CPV · TRF · COL · ASM)
Reads the developer's case files (templates_biz/cases/*.docx: Case ID · Priority · Basis · Given / When / Then), runs the
cases the engine can execute on a test site with FIXED inputs from the site data file (D1 · W1 · A · C1 · V1 · K1 — never "the
first option"), checks save → reopen → payment → stock → journal, and writes Status / Actual / DocumentId / Evidence back
into a copy of the same Word file.

Statuses (the developer's vocabulary): PASS · FAIL · BLOCKED_DATA (missing site data / prerequisite) ·
BLOCKED_CAPABILITY (the engine can't execute or verify this case yet) · NOT_RUN.
Write test: test sites only (engine.guard.require_write).
"""
import json
import re
import time
from datetime import datetime

from utils.logger import logger

PASS, FAIL, BDATA, BCAP, NOTRUN = "PASS", "FAIL", "BLOCKED_DATA", "BLOCKED_CAPABILITY", "NOT_RUN"
SYMBOLS = [("D1", "رقم القسم/الفرع (DepartmentId)"), ("W1", "رقم المخزن W1 (WarehouseId)"), ("A", "كود/باركود الصنف A"),
           ("C1", "رقم العميل C1"), ("V1", "رقم المورد V1"), ("K1", "رقم الخزينة K1 (CashBoxId)")]

# screens: code → profile (what the engine knows about the screen on NQ ERP)
PROFILES = {
    "SAL": {"path": "/SalesInvoice/AddEdit", "ctrl": "SalesInvoice", "body": "SalesInvoiceDetails", "pay": "SalesInvoicePaymentMethods",
            "save": "addEdit", "party": "VendorOrCustomerId", "sym": "C1", "add": "quick", "sign": -1, "voucher": "StockIssueVoucher",
            "jt": r"بيع", "kind": "invoice", "cash": "d"},
    "PUR": {"path": "/PurchaseInvoice/AddEdit", "ctrl": "PurchaseInvoice", "body": "PurchaseInvoiceDetails", "pay": "PurchaseInvoicePaymentMethods",
            "save": "savePurchaseInvoice", "party": "VendorOrCustomerId", "sym": "V1", "add": "modal", "sign": 1, "voucher": "StockReceiptVoucher",
            "jt": r"شراء", "kind": "invoice", "cash": "c"},
    "SRT": {"path": "/SalesReturn/AddEdit", "ctrl": "SalesReturn", "body": "SalesReturnsDetails", "pay": "SalesReturnPaymentMethods",
            "save": "addEdit", "party": "VendorOrCustomerId", "sym": "C1", "origin": "SAL", "link": "select", "sign": 1,
            "voucher": "StockReceiptVoucher", "jt": r"مرتجع (البيع|المبيعات)", "kind": "return", "cash": "c"},
    "PRT": {"path": "/PurchaseReturn/AddEdit", "ctrl": "PurchaseReturn", "body": "PurchaseReturnsDetails", "pay": "PurchaseReturnPaymentMethods",
            "save": "addEdit", "party": "VendorOrCustomerId", "sym": "V1", "origin": "PUR", "link": "number", "sign": -1,
            "voucher": "StockIssueVoucher", "jt": r"مرتجع (الشراء|المشتريات)", "kind": "return", "cash": "d"},
    "CRV": {"path": "/CashReceiptVoucher/AddEdit", "ctrl": "CashReceiptVoucher", "save": "addEdit", "party": "CustomerId", "sym": "C1",
            "src": "1", "method": "CashReceiptPaymentMethodId", "jt": r"قبض", "kind": "voucher", "cash": "d"},
    "CPV": {"path": "/CashIssueVoucher/AddEdit", "ctrl": "CashIssueVoucher", "save": "addEdit2", "party": "VendorId", "sym": "V1",
            "src": "2", "method": "CashIssuePaymentMethodId", "ajax": "/CashIssueVoucher/SearchVendors", "jt": r"دفع|صرف نقد", "kind": "voucher", "cash": "c"},
}
NAMES = {"SAL": "فاتورة المبيعات", "PUR": "فاتورة المشتريات", "SRT": "مرتجع المبيعات", "PRT": "مرتجع المشتريات", "CRV": "سند القبض",
         "CPV": "سند الدفع", "TRF": "التحويلات المخزنية", "COL": "سند التجميع والإنتاج", "ASM": "مستند التجميع"}
ICONS = {"SAL": "🧾", "PUR": "🛒", "SRT": "↩️", "PRT": "↪️", "CRV": "💰", "CPV": "💸", "TRF": "🔁", "COL": "🏭", "ASM": "🧩"}

MATRIX = re.compile(r"^(NONE|AUTO|ONE|MULTI) ضريبة (\d+) سداد (CREDIT|CASH|MIXED)$")
RETURN = re.compile(r"^(NONE|AUTO|ONE|MULTI) مرتجع جزئي ضريبة (\d+)$")


# ------------------------------------------------------------------ the case files
def _dir():
    from config import paths
    return paths.BASE_DIR / "templates_biz" / "cases"


_CACHE = {}


def catalog():
    """{code: {code, name, icon, title, route, file, cases: [{id, pri, basis, title, given, when, then, auto, why}]}}"""
    out = {}
    for f in sorted(_dir().glob("*.docx")):
        m = re.match(r"\d+_([A-Z]+)$", f.stem)
        if not m:
            continue
        code = m.group(1)
        key = (str(f), f.stat().st_mtime)
        if _CACHE.get(code, (None,))[0] != key:
            _CACHE[code] = (key, _parse(f, code))
        out[code] = _CACHE[code][1]
    return out


def _parse(f, code):
    import docx
    d = docx.Document(str(f))
    ps = d.paragraphs
    title = ps[0].text.strip() if ps else code
    route = next((p.text.split(":", 1)[1].strip() for p in ps if p.text.startswith("Screen route")), "")
    cases, cur, head = [], None, ""
    for p in ps:
        t = p.text.strip()
        if p.style.name.startswith("Heading 2"):
            head = t
        m = re.match(r"Case ID: (\S+)\s*\|\s*Priority: (\S+)\s*\|\s*Basis: (\S+)", t)
        if m:
            cur = {"id": m[1], "pri": m[2], "basis": m[3], "title": head, "given": "", "when": [], "then": ""}
            cases.append(cur)
            continue
        if not cur or not t:
            continue
        if t.startswith("Given"):
            cur["given"] = re.sub(r"^Given\s+الشروط والبيانات\s*", "", t)
        elif t.startswith("When"):
            cur["when"].append(re.sub(r"^When\s*", "", t))
        elif t.startswith("Then"):
            cur["then"] = re.sub(r"^Then\s+النتائج المتوقعة\s*", "", t)
        elif re.match(r"^\d\)", t) and not cur["then"]:
            cur["when"].append(t)
    for c in cases:
        c["auto"], c["why"] = supported(code, c)
    return {"code": code, "name": NAMES.get(code, code), "icon": ICONS.get(code, "📄"), "title": title, "route": route,
            "file": f.name, "cases": cases, "auto_n": sum(1 for c in cases if c["auto"])}


def supported(code, c):
    """(True, '') when the engine runs this case, else (False, why)"""
    if code in ("SAL", "PUR"):
        m = MATRIX.match(c["title"])
        if m and m[1] in ("NONE", "AUTO"):
            return True, ""
        if m:
            return False, "ربط سند مخزني سابق (ONE/MULTI) — المرحلة الجاية"
    if code in ("SRT", "PRT"):
        m = RETURN.match(c["title"])
        if m and m[1] in ("NONE", "AUTO"):
            return True, ""
        if m:
            return False, "ربط سند مخزني مستقل بالمرتجع (ONE/MULTI) — المرحلة الجاية"
    if code in ("CRV", "CPV") and c["title"] == "CASH توزيع NONE":
        return True, ""
    return False, "لسه مش مؤتمتة — هتتضاف على مراحل"


def spec(code, c):
    """the fixed inputs + expected values read from the case text (never from the actual result)"""
    g, w, t = c["given"], " ".join(c["when"]), c["then"]
    num = lambda rx, s, dflt=None: (float(m.group(1)) if (m := re.search(rx, s)) else dflt)
    s = {"code": code, "id": c["id"]}
    if PROFILES[code]["kind"] == "invoice":
        m = MATRIX.match(c["title"])
        s.update({"source": m[1], "tax": float(m[2]), "pay": m[3], "auto": m[1] == "AUTO",
                  "qty": num(r"(\d+(?:\.\d+)?) وحدات من A", w, 10), "price": num(r"بسعر (\d+(?:\.\d+)?)", w, 100),
                  "net": num(r"صافي (\d+(?:\.\d+)?)", t), "vat": num(r"ضريبة (\d+(?:\.\d+)?)", t), "total": num(r"إجمالي (\d+(?:\.\d+)?)", t),
                  "paid": num(r"المدفوع (\d+(?:\.\d+)?)", t, 0), "cash": num(r"نقدي (\d+(?:\.\d+)?)", g, 0) if m[3] == "MIXED" else None})
        s["stock"] = (PROFILES[code]["sign"] * s["qty"]) if s["auto"] else 0.0
    elif PROFILES[code]["kind"] == "return":
        m = RETURN.match(c["title"])
        s.update({"source": m[1], "tax": float(m[2]), "auto": m[1] == "AUTO",
                  "orig_qty": num(r"فاتورة أصلية (\d+(?:\.\d+)?) وحدات", g, 10), "price": num(r"بسعر (\d+(?:\.\d+)?)", g, 100),
                  "qty": num(r"واختر (\d+(?:\.\d+)?) وحدات", w, 4),
                  "net": num(r"صافي المرتجع (\d+(?:\.\d+)?)", t), "vat": num(r"ضريبته (\d+(?:\.\d+)?)", t), "total": num(r"إجماليه (\d+(?:\.\d+)?)", t),
                  "left": num(r"المتاح للإرجاع من الأصل (\d+(?:\.\d+)?)", t)})
        s["stock"] = (PROFILES[code]["sign"] * s["qty"]) if s["auto"] else 0.0
    else:
        s.update({"amount": num(r"مبلغ السند (\d+(?:\.\d+)?)", t, 1150)})
    return s


# ------------------------------------------------------------------ site data file (symbols → real ids), per site
def _data_file():
    from config import paths
    return paths.SETTINGS_DIR / "biz_site_data.json"


def site_key(url):
    return re.sub(r"^https?://", "", str(url or "")).strip("/").lower()


def load_data(url=None):
    try:
        allx = json.loads(_data_file().read_text(encoding="utf-8"))
    except Exception:
        allx = {}
    return allx if url is None else allx.get(site_key(url), {})


def save_data(url, data, names=None, auto=False):
    allx = load_data()
    old = allx.get(site_key(url), {})
    row = {k: str(data.get(k) or "").strip() for k, _ in SYMBOLS}
    nm = dict(old.get("_names") or {})
    for k, _ in SYMBOLS:                      # a hand-changed value drops the auto name next to it
        if row[k] != str(old.get(k) or "") and not (names and k in names):
            nm.pop(k, None)
    nm.update(names or {})
    row["_names"] = {k: v for k, v in nm.items() if row.get(k)}
    row["_auto"] = datetime.now().strftime("%Y-%m-%d %H:%M") if auto else old.get("_auto", "")
    allx[site_key(url)] = row
    _data_file().parent.mkdir(parents=True, exist_ok=True)
    _data_file().write_text(json.dumps(allx, ensure_ascii=False, indent=1), encoding="utf-8")
    return row


# ------------------------------------------------------------------ 🔎 the site data file, discovered (read only — nothing is saved on the ERP)
DISCOVER_RULES = {
    "D1": "أول فرع فيه مخزن عليه صنف مناسب",
    "W1": "المخزن اللي فيه الصنف A برصيد كافي",
    "A": "صنف وحدته معاملها 1، باركوده مش متكرر، مش ذهب، ورصيده 30 أو أكتر (الأعلى رصيدًا)",
    "C1": "أول عميل حده الائتماني يسمح بفاتورة آجلة",
    "V1": "أول مورد يظهر في فاتورة الشراء وفي سند الدفع",
    "K1": "الخزينة اللي اسمها صندوق/خزينة في سطر النقدي",
}


def discover(driver, credentials, cfg, result=None):
    """reads the test site and proposes D1 · W1 · A · C1 · V1 · K1 with their names; saves them to the site data file"""
    from engine.screen_runner import login
    from config.settings import BASE_URL
    result = result if result is not None else {}
    login(driver, credentials)
    _open(driver, "/SalesInvoice/AddEdit")
    a = _js(driver, r"""
      const opts = id => [...document.querySelectorAll('#' + id + ' option')].filter(o => o.value && o.value !== '0').map(o => [o.value, o.textContent.trim()]);
      const out = {checked: 0}; const today = new Date().toISOString();
      for (const [dep, dn] of opts('DepartmentId')) {
        await N.set('DepartmentId', dep, 2000);
        for (const [wh, wn] of opts('WarehouseId').slice(0, 8)) {
          let j; try { j = JSON.parse(await N.get('/Helper/ItemsByDepId?' + new URLSearchParams({departmentId: dep, customerId: '', date: today.slice(0, 10), searchTxt: '', isDefault: false,
                       ItemGroupId: '', ItemCategoryId: '', WarehouseId: wh, pageIndex: 1, pageSize: 60, SalesTransaction: false}), 30000)); } catch (e) { continue; }
          for (const x of (j.Items || []).filter(x => x.BarCode && (+x.Equivalent || 1) === 1 && !x.IsGold).slice(0, 25)) {
            out.checked++;
            let dup = 0; try { dup = JSON.parse(await N.get('/SalesInvoice/GetItemsSmartSearchHints?term=' + encodeURIComponent(x.BarCode))).filter(i => String(i.barcode) === String(x.BarCode)).length; } catch (e) {}
            if (dup !== 1) continue;
            const q = await N.stock(wh, x.Id);
            if (q >= 30 && (!out.A || q > out.Aq)) { out.D1 = [dep, dn]; out.W1 = [wh, wn]; out.A = [x.BarCode, x.ArName + ' — رصيد ' + q]; out.Aq = q; }
          }
          if (out.A) break;
        }
        if (out.A) break;
      }
      if (out.D1) await N.set('DepartmentId', out.D1[0], 2000);
      for (const [c, cn] of opts('VendorOrCustomerId').slice(0, 40)) { const b = await N.balance(c); if (b && b.Result === 'can') { out.C1 = [c, cn]; break; } }
      const cb = [...document.querySelectorAll('.CashBoxId option')].filter(o => o.value).map(o => [o.value, o.textContent.trim()]);
      out.K1 = cb.find(x => /صندوق|خزين|نقد/.test(x[1])) || cb[0] || null;
      return out;
    """)
    _open(driver, "/PurchaseInvoice/AddEdit")
    v = _js(driver, r"""
      const [dep] = A; if (dep) await N.set('DepartmentId', dep, 2000);
      const vs = [...document.querySelectorAll('#VendorOrCustomerId option')].filter(o => o.value && o.value !== '0').map(o => [o.value, o.textContent.trim()]);
      let pay = []; try { for (const t of ['', 'ا', 'م', 'ش']) { pay = pay.concat(JSON.parse(await N.get('/CashIssueVoucher/SearchVendors?' + new URLSearchParams({term: t, departmentId: dep || ''})))); } } catch (e) {}
      const ok = new Set(pay.map(x => String(x.Id)));
      return vs.find(x => ok.has(x[0])) || null;
    """, (a.get("D1") or [""])[0])
    a["V1"] = v
    found = {k: a.get(k) for k, _ in SYMBOLS}
    old = load_data(BASE_URL)
    vals = {k: (found[k][0] if found.get(k) else old.get(k, "")) for k, _ in SYMBOLS}
    names = {k: found[k][1] for k in found if found.get(k)}
    row = save_data(BASE_URL, vals, names, auto=True)
    miss = [k for k, _ in SYMBOLS if not found.get(k)]
    rows = [{"cells": [k, lbl, found[k][0] if found.get(k) else (old.get(k) or "—"), found[k][1] if found.get(k) else "مالقيتش — اكتبيها بإيدك", DISCOVER_RULES[k]],
             "ok": True if found.get(k) else False} for k, lbl in SYMBOLS]
    result["detail"] = {"title": "🔎 ملف بيانات الموقع — اتملى تلقائي (قراءة بس)", "columns": ["الرمز", "معناه", "القيمة", "الاسم في الـ ERP", "اتختار ليه"],
                        "rows": rows, "note": f"اتفحص {a.get('checked', 0)} صنف · " + ("كل الرموز اتملت" if not miss else "ناقص: " + ", ".join(miss))}
    result["biz"] = {"data": row}
    logger.info("🔎 " + " · ".join(f"{k}={vals[k]}" for k, _ in SYMBOLS))
    if miss:
        e = AssertionError("ملف بيانات الموقع: مالقيتش " + ", ".join(miss) + " — اكتبيهم بإيدك في صفحة سيناريوهات الأعمال")
        e.partial_result = result
        raise e
    return result


# ------------------------------------------------------------------ browser helpers
INSTALL = r"""
window.__nq = window.__nq || {};
const N = window.__nq; N.w = ms => new Promise(r => setTimeout(r, ms));
N.sw = N.sw || [];
N.log = t => { N.sw.push(t); try { sessionStorage.setItem('__nq_sw', JSON.stringify(N.sw)); } catch (e) {} };
if (window.Swal && !Swal.__nqc) {
  const of = Swal.fire.bind(Swal);
  Swal.fire = function (...a) {
    const o = typeof a[0] === 'string' ? {title: a[0], text: a[1]} : (a[0] || {});
    N.log((o.title || '') + ' | ' + String(o.text || o.html || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 300) + (o.showCancelButton ? ' [?]' : ''));
    if (o.showCancelButton) return Promise.resolve({isConfirmed: true, value: true});
    return of(...a);
  };
  Swal.__nqc = true;
}
if (!XMLHttpRequest.prototype.__nqc) {   // the save request's own answer (some screens save without showing any message)
  const op = XMLHttpRequest.prototype.open, sd = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__m = m; this.__u = u; return op.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function () { if (/post/i.test(this.__m || '') && /addedit|save|create|update/i.test(this.__u || ''))
      this.addEventListener('loadend', () => N.log('xhr | ' + this.status + ' ' + String(this.__u).split('?')[0] + ' ' + String(this.responseText || '').replace(/\s+/g, ' ').slice(0, 400)));
    return sd.apply(this, arguments); };
  XMLHttpRequest.prototype.__nqc = true;
}
window.confirm = m => { N.log('confirm | ' + m); return true; };
window.alert = m => { N.log('alert | ' + m); };
N.num = id => parseFloat(String($('#' + id).val() || '0').replace(/,/g, '')) || 0;
N.f = v => parseFloat(String(v || '0').replace(/,/g, '')) || 0;
N.set = async (id, v, ms) => { $('#' + id).val(v).trigger('change'); await N.w(ms || 1200); };
N.has = (id, v) => [...document.querySelectorAll('#' + id + ' option')].some(o => o.value === String(v));
N.check = async (id, want, ms) => { const e = document.getElementById(id); if (!e) return null; if (e.checked !== !!want) { e.click(); await N.w(ms || 2500); } return e.checked; };
N.req = () => [...document.querySelectorAll('input[required],select[required],textarea[required]')]
   .filter(e => e.offsetParent !== null && !e.classList.contains('tabledit-input') && !String(e.value).trim()).map(e => e.id || e.name);
N.dropEmpty = async body => { let n = 0;   // an empty detail row with required cells blocks the save silently (validateAllRequired)
  for (const tr of [...document.querySelectorAll('#' + body + ' tr')]) {
    if (tr.offsetParent === null || $(tr).find('.item').val() || $(tr).find('.item-name').val()) continue;
    if (![...tr.querySelectorAll('[required]')].some(e => !String(e.value).trim())) continue;
    const d = tr.querySelector('[onclick*="deleteElement"]'); if (d) d.click(); else tr.remove(); n++; await N.w(1200); }
  return n; };
N.get = async (u, ms) => { const ac = new AbortController(); setTimeout(() => ac.abort(), ms || 45000);
  const r = await fetch(u, {credentials: 'include', signal: ac.signal}); return await r.text(); };
N.post = async (u, body, ms) => { const ac = new AbortController(); setTimeout(() => ac.abort(), ms || 45000);
  const r = await fetch(u, {method: 'POST', credentials: 'include', signal: ac.signal, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  return await r.text(); };
N.ids = async ctrl => { const d = new DOMParser().parseFromString(await N.get('/' + ctrl), 'text/html'); const re = new RegExp('/' + ctrl + '/AddEdit\\w*/(\\d+)', 'i');
  const out = {}; d.querySelectorAll('tbody tr').forEach(tr => { const a = [...tr.querySelectorAll('a[href]')].map(x => x.getAttribute('href'));
    const h = a.find(x => re.test(x)); if (!h) return; const id = h.match(re)[1];
    out[id] = {text: [...tr.cells].map(c => c.innerText.trim().replace(/\s+/g, ' ')).filter(Boolean).join(' | ').slice(0, 300), links: a}; });
  return out; };
N.itemId = async code => { try { const l = JSON.parse(await N.get('/SalesInvoice/GetItemsSmartSearchHints?term=' + encodeURIComponent(code)));
  const x = l.find(i => String(i.barcode) === String(code)); return x ? x.id : null; } catch (e) { return null; } };
N.stock = async (wh, item) => { try { return JSON.parse(await N.get(`/Helper/ItemQuantityOnSystem?warehouseId=${wh}&itemId=${item}&voucherId=0&date=${encodeURIComponent(new Date().toISOString().slice(0, 16))}`)).quantity; } catch (e) { return null; } };
N.balance = async c => { try { return JSON.parse(await N.get('/Helper/GetCustomerDebitBalance/' + c))[0]; } catch (e) { return null; } };
N.journal = async day => { const f = {DateFrom: day, DateTo: day, BranchId: null, AccountIds: [], AccountId: null, CostCenterId: null, UserId: null,
   IsPosted: null, DebitCreditType: null, SourcePageId: null, ReviewStatus: null, OperationType: null, FlaggedOnly: false, SearchTerm: ''};
  for (let i = 0; i < 3; i++) { try { const t = await N.post('/JournalEntriesReview/GetDataJson', f, 60000); if (t) return (JSON.parse(t).data || []).map(x => ({je: x.JournalEntryId,
     type: x.DocumentType || '', doc: x.DocumentNumber, op: String(x.OperationNumber || ''), acc: (x.AccountCode || '') + ' ' + (x.AccountName || ''), d: +x.Debit || 0, c: +x.Credit || 0})); } catch (e) {} await N.w(2500); }
  return null; };
N.rows = body => [...document.querySelectorAll('#' + body + ' tr')].map(tr => {
  const q = s => { const e = tr.querySelector(s); return e ? (e.tagName === 'SELECT' ? ((e.selectedOptions[0] || {}).textContent || '') : e.value) : ''; };
  return {item: q('.item-name'), qty: N.f(q('.quantity')), price: N.f(q('.price')), id: q('.itemId'), code: q('.barcode')}; }).filter(r => r.item);
N.buyer = async () => { const filled = [];   // the e-invoice buyer fields a cash sale makes required (test values, not party data)
  const fill = (id, v) => { const e = document.getElementById(id); if (e && e.required && e.offsetParent !== null && !String(e.value).trim()) { $(e).val(v).trigger('input').trigger('change'); filled.push(id); } };
  fill('CommercialRegistrationNumber', '1010101010'); fill('CashCustomerVATNumber', '300000000000003'); fill('BuildingNumber', '1234'); fill('PostalCode', '12345');
  const pick = async (id, rx) => { const e = document.getElementById(id); if (!e || !e.required || e.offsetParent === null || e.value) return;
    const o = [...e.options].filter(x => x.value); const x = o.find(z => rx.test(z.textContent)) || (o.length === 1 ? o[0] : null); if (x) { await N.set(id, x.value, 2000); filled.push(id); } };
  await pick('CountryId', /السعودية|Saudi/); await pick('CityId', /الرياض|Riyadh/); return filled; };
N.payRows = body => [...document.querySelectorAll('#' + body + ' tr')].map(tr => ({m: $(tr).find('.PaymentMethodId').val(), amt: N.f($(tr).find('.PaymentAmount').val()),
   box: $(tr).find('.CashBoxId').val() || ''})).filter(r => r.m);
'ok';
"""


def _js(driver, body, *args):
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
    for _ in range(60):
        try:
            if driver.execute_script("return !!(window.jQuery && document.readyState === 'complete')"):
                break
        except Exception:
            pass
        time.sleep(0.5)
    time.sleep(2.5)


def _save(driver, fn, path_before, times=1):
    """click save through the screen's own function. The page often navigates to the list, and some screens save without any
    message, so the dialogs AND the save request's answer are kept in sessionStorage. → (ok, messages, saved_id, silent)"""
    _js(driver, "sessionStorage.removeItem('__nq_sw'); N.sw = []; for (let i = 0; i < A[1]; i++) setTimeout(() => { try { const f = window[A[0]]; f ? f() : N.log('err | مفيش دالة حفظ ' + A[0]); } catch (e) { N.log('err | ' + e); } }, 50 + i * 300); return 1;", fn, times)
    log, path, t0 = [], path_before, time.time()

    def moved(p):
        return p.rstrip("/").lower() != path_before.rstrip("/").lower()
    while time.time() - t0 < 45:
        time.sleep(1)
        try:
            path, raw = driver.execute_script("return [location.pathname, sessionStorage.getItem('__nq_sw')]")
            log = json.loads(raw or "[]")
        except Exception:
            continue
        if any(_ok(x) for x in log) or any(_err(x) for x in log) or moved(path) or _xhr(log)[0] is not None:
            time.sleep(3)
            try:
                log = json.loads(driver.execute_script("return sessionStorage.getItem('__nq_sw')") or "[]")
            except Exception:
                pass
            break
    xok, xid, xmsg = _xhr(log)
    ui_ok = any(_ok(x) for x in log)
    ok = (xok is True) or ui_ok or (moved(path) and not any(_err(x) for x in log) and xok is not False)
    msgs = [x for x in log if not x.endswith("[?]") and not x.startswith("xhr |")] + ([xmsg] if xok is False and xmsg else [])
    return ok, msgs, xid, bool(ok and not ui_ok and not moved(path))


def _ok(x):
    return bool(re.match(r"^(حفظ|تم الحفظ|تم)\s*\|", x))


def _xhr(log):
    """(True/False/None, saved id, message) from the save request's JSON answer"""
    for x in reversed(log):
        if not x.startswith("xhr |"):
            continue
        m = re.match(r"xhr \| (\d+) (\S+) (.*)$", x)
        if not m:
            continue
        body = m.group(3)
        try:
            j = json.loads(body)
        except Exception:
            j = None
        if j is True or body.strip().strip('"').lower() == "true":
            return True, "", ""
        if isinstance(j, dict):
            succ = str(j.get("success", j.get("Success", ""))).lower()
            sid = j.get("id") or j.get("Id") or j.get("ID") or ""
            if succ in ("true", "1") or (sid and succ != "false"):
                return True, str(sid), ""
            if succ in ("false", "0"):
                return False, "", "رد الحفظ: " + str(j.get("message") or j.get("Message") or j.get("error") or body)[:300]
        if m.group(1) != "200":
            return False, "", f"رد الحفظ HTTP {m.group(1)}"
    return None, "", ""


def _err(x):
    if x.startswith("xhr |"):
        return False
    return x.startswith("alert |") or x.startswith("err |") or bool(re.search(r"لا يمكن|خطأ|تجاوز|مطلوب|غير مسموح|يجب|فشل|error", x, re.I)) and not x.endswith("[?]")


# ------------------------------------------------------------------ one case
EXPECT_TEXT = {"الحفظ": "يتحفظ مرة واحدة من غير رفض", "مستند واحد بس": "مستند جديد واحد", "سند واحد بس": "سند جديد واحد",
               "السند المخزني التابع": "سند مخزني واحد مربوط بالمستند", "مفيش سند مخزني جديد": "مفيش سند مخزني",
               "إعادة الفتح": "نفس الأصناف والكمية والسعر والطرف والمخزن", "القيد متزن": "مدين = دائن",
               "استدعاء الأصل": "سطر الفاتورة الأصلية بكميتها وسعرها", "المستند في القائمة": "يظهر في القائمة",
               "السند في القائمة": "يظهر في القائمة", "المرتجع في القائمة": "يظهر في القائمة", "القيد": "قيد للمستند في مراجعة القيود"}


class Case:
    def __init__(self, c):
        self.c = c
        self.checks = []          # (name, ok, actual, expected)
        self.status = NOTRUN
        self.doc_id = self.doc_no = ""
        self.actual = ""
        self.evidence = []
        self.journal = []
        self.plain = ""
        self.spec = {}

    def chk(self, name, ok, actual, expected=""):
        m = re.search(r"\s*\(المتوقع ([^)]*)\)", actual or "")
        if m and not expected:
            expected, actual = m.group(1), (actual[:m.start()] + actual[m.end():]).strip()
        self.checks.append((name, bool(ok), actual, expected or EXPECT_TEXT.get(name, "")))
        logger.info(f"   {'✅' if ok else '❌'} {name}: {actual}" + (f" (المتوقع {expected})" if expected else ""))
        return ok

    def done(self, status=None, actual=""):
        if status:
            self.status = status
        else:
            self.status = PASS if self.checks and all(c[1] for c in self.checks) else FAIL
        bad = [f"{c[0]}: {c[2]}" + (f" — المتوقع {c[3]}" if c[3] else "") for c in self.checks if not c[1]]
        if actual:
            self.actual = actual[:900]
        elif bad:
            self.actual = " · ".join(bad)[:900]
        else:
            self.actual = f"كل الفحوصات مطابقة ({len(self.checks)} فحص)" + (f" · مستند {self.doc_no}" if self.doc_no else "")
        return self

    def reason(self):
        if self.status == PASS:
            return self.actual
        return self.actual or "—"


def describe(code, c):
    """the case in one plain sentence (for the report a client can read)"""
    try:
        s = spec(code, c)
    except Exception:
        return c.get("title", "")
    name = NAMES.get(code, code)
    kind = PROFILES.get(code, {}).get("kind")
    if kind == "invoice":
        pay = {"CREDIT": "آجل", "CASH": "نقدي", "MIXED": f"متعدد ({s.get('cash') or 0:g} نقدي والباقي آجل)"}.get(s["pay"], s["pay"])
        st = "والسند المخزني بيتولد تلقائي" if s["auto"] else "من غير سند مخزني"
        return f"{name} {pay} بضريبة {s['tax']:g}% — {s['qty']:g} قطعة × {s['price']:g} {st}"
    if kind == "return":
        st = "والسند المخزني بيتولد تلقائي" if s["auto"] else "من غير سند مخزني"
        return f"{name} جزئي: {s['qty']:g} من فاتورة أصلية {s['orig_qty']:g} × {s['price']:g} بضريبة {s['tax']:g}% {st}"
    return f"{name} نقدي بمبلغ {s.get('amount', 0):g} على الحساب من غير تخصيص فواتير"


def _close(a, b, tol=0.011):
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def _f(x):
    try:
        return f"{float(x):,.2f}"
    except (TypeError, ValueError):
        return str(x)


def _missing(data, names):
    return [n for n in names if not str(data.get(n) or "").strip()]


def run_invoice(driver, code, c, data, day, opts=None):
    """opts (used by the add-on tests): qty · disc (invoice discount %) · double (save clicked twice) · reject (the save must be refused)"""
    P, s, k = PROFILES[code], spec(code, c), Case(c)
    opts = opts or {}
    if opts.get("qty") or opts.get("disc"):
        s["qty"] = float(opts.get("qty") or s["qty"])
        net = round(s["qty"] * s["price"] * (1 - float(opts.get("disc") or 0) / 100), 2)
        vat = round(net * s["tax"] / 100, 2)
        s.update({"net": net, "vat": vat, "total": round(net + vat, 2), "stock": (P["sign"] * s["qty"]) if s["auto"] else 0.0})
        if s["pay"] == "CASH":
            s["paid"] = s["total"]
    miss = _missing(data, ["D1", "W1", "A", P["sym"]] + (["K1"] if s["pay"] in ("CASH", "MIXED") else []))
    if miss:
        return k.done(BDATA, "ناقص في ملف بيانات الموقع: " + ", ".join(miss))
    logger.info(f"▶ {c['id']} — {c['title']}")
    # snapshot before
    _open(driver, P["path"])
    b = _js(driver, "const [ctrl, code] = A; let dup = 0; try { dup = JSON.parse(await N.get('/SalesInvoice/GetItemsSmartSearchHints?term=' + encodeURIComponent(code))).filter(i => String(i.barcode) === String(code)).length; } catch (e) {} return {ids: Object.keys(await N.ids(ctrl)), dup};",
            P["ctrl"], data["A"])
    if b.get("dup", 0) > 1:
        return k.done(BDATA, f"الباركود «{data['A']}» متسجل على {b['dup']} صنف في الـ ERP — حطي في ملف البيانات باركود الصنف A مايتكررش (الأداة مش هتختار واحد بالتخمين)")
    # header
    h = _js(driver, r"""
      const [P, d, s] = A; const out = {miss: []};
      if (!N.has('DepartmentId', d.D1)) out.miss.push('D1'); else await N.set('DepartmentId', d.D1, 2000);
      if (!N.has('WarehouseId', d.W1)) out.miss.push('W1'); else await N.set('WarehouseId', d.W1, 1200);
      if (!N.has(P.party, d[P.sym])) out.miss.push(P.sym); else await N.set(P.party, d[P.sym], 3000);
      if (document.getElementById('InvoiceTypeId') && N.has('InvoiceTypeId', '1') && P.ctrl === 'SalesInvoice') await N.set('InvoiceTypeId', '1', 600);
      await N.set('PaymentType', '2', 1500);
      if ($('#ItemwithVat').prop('checked')) document.getElementById('ItemwithVat').click();
      out.auto = await N.check('AutoGenerateStockReceiptVoucher', s.auto, 800);
      out.filled = await N.buyer();
      const ad = document.getElementById('AccountingDocumentId'); if (ad && !ad.value) { const o = [...ad.options].find(x => x.value); if (o) { await N.set('AccountingDocumentId', o.value, 600); out.adoc = o.textContent.trim(); } }
      return out;
    """, P, data, s)
    if h["miss"]:
        return k.done(BDATA, "القيم دي مش موجودة في قوائم الشاشة: " + ", ".join(f"{m}={data.get(m)}" for m in h["miss"]))
    if h.get("filled"):
        k.evidence.append("بيانات المشتري للفاتورة الإلكترونية اتملت بقيم اختبار: " + ", ".join(h["filled"]))
    k.evidence.append(f"الرأس: D1={data['D1']} W1={data['W1']} {P['sym']}={data[P['sym']]} · توليد السند المخزني {'مفتوح' if h['auto'] else 'مغلق'}"
                      + (f" · نوع المستند «{h['adoc']}»" if h.get("adoc") else ""))
    # the line
    a = _js(driver, r"""
      const [P, code, qty, price] = A;
      if (P.add === 'quick') {
        const $s = $('#QuickSmartSearch'); $s.val(code); $s.trigger($.Event('keydown', {key: 'Enter'})); await N.w(2500);
        const o = [...document.querySelectorAll('#QuickSmartSearchHints option')].find(x => x.getAttribute('data-barcode') === String(code));
        if (!o) return {err: 'البحث السريع مالقاش الكود'};
        $s.val(o.value).trigger('change'); await N.w(2500);
        $('#QuickItemQty').val(qty).trigger('input').trigger('change'); await N.w(300);
        $('#QuickItemPrice').val(price).trigger('input').trigger('change'); await N.w(300);
        $('#QuickItemAddToDetailsBtn').click(); await N.w(3500); $('#QuickSmartSearchClear').click();
      } else {
        $('#search-items').val(code); appendSearch(1);
        let tr = null; for (let i = 0; i < 20 && !tr; i++) { await N.w(800); tr = [...document.querySelectorAll('#itemSearchModal tbody tr')].find(r => r.querySelector('.barcode') && r.querySelector('.barcode').value === String(code)); }
        if (!tr) return {err: 'نافذة البحث عن الأصناف مالقتش الكود'};
        tr.querySelector('button[onclick*=chooseItem]').click(); await N.w(3000);
        const row = [...document.querySelectorAll('#' + P.body + ' tr')].reverse().find(r => $(r).find('.barcode').val() === String(code));
        if (!row) return {err: 'الصنف ما اتضافش للتفاصيل'};
        $(row).find('.quantity').val(qty).trigger('input').trigger('change'); await N.w(600);
        $(row).find('.price').val(price).trigger('input').trigger('change'); await N.w(1500);
      }
      if (typeof CalculateTotals === 'function') { try { CalculateTotals(); } catch (e) {} await N.w(1500); }
      return {rows: N.rows(P.body)};
    """, P, data["A"], s["qty"], s["price"])
    if a.get("err"):
        return k.done(BCAP, "إضافة السطر: " + a["err"])
    item_id = (a.get("rows") or [{}])[-1].get("id")
    b["item"] = item_id
    b["stock"] = _js(driver, "const [wh, it] = A; return await N.stock(wh, it);", data["W1"], item_id) if item_id else None
    k.evidence.append(f"السطر: {(a.get('rows') or [{}])[-1].get('item', '')} (Id {item_id}) × {s['qty']:g} بسعر {_f(s['price'])} · رصيد W1 قبل الحفظ {b['stock']}")
    if opts.get("disc"):
        dd = _js(driver, r"""
          const [pct] = A; const e = document.getElementById('VoucherDiscountPercentage'); if (!e) return {err: 'خانة خصم الفاتورة % مش موجودة في الشاشة'};
          $(e).val(pct).trigger('input').trigger('change').trigger('keyup').trigger('blur'); await N.w(1500);
          if (typeof CalculateTotals === 'function') { try { CalculateTotals(); } catch (x) {} await N.w(1500); }
          return {disc: N.num('VoucherDiscountValue') || N.num('DiscountValue'), pct: N.num('VoucherDiscountPercentage')};
        """, opts["disc"])
        if dd.get("err"):
            return k.done(BCAP, dd["err"])
        k.evidence.append(f"خصم الفاتورة {opts['disc']:g}% → قيمة الخصم على الشاشة {_f(dd.get('disc'))}")
    # tax + payment
    t = _js(driver, r"""
      const [P, s, box] = A;
      const ht = await N.check('hasTaxes', s.tax > 0, 2500);
      await N.w(1500);
      const after = N.num('TotalAfterTaxes'); const out = {ht};
      if (s.pay === 'CASH' || s.pay === 'MIXED') {
        const pt = s.pay === 'CASH' ? '1' : '3';
        if (!N.has('PaymentType', pt)) return {err: 'طريقة الدفع ' + (s.pay === 'CASH' ? 'نقدي' : 'متعدد') + ' مش موجودة في الشاشة'};
        await N.set('PaymentType', pt, 2500);
        const rows = [...document.querySelectorAll('#' + P.pay + ' tr')];
        const cash = rows.find(r => $(r).find('.PaymentMethodId').val() === '1'), cred = rows.find(r => $(r).find('.PaymentMethodId').val() === '2');
        if (!cash) return {err: 'سطر النقدي مش موجود في جدول طرق الدفع'};
        const sel = $(cash).find('.CashBoxId'); if (!sel.find('option[value="' + box + '"]').length) return {miss: 'K1'};
        sel.val(box).trigger('change'); await N.w(800);
        if (s.pay === 'MIXED') { $(cash).find('.PaymentAmount').val(s.cash).trigger('input').trigger('change'); await N.w(600);
          if (cred) { $(cred).find('.PaymentAmount').val((after - s.cash).toFixed(2)).trigger('input').trigger('change'); await N.w(600); } }
      }
      out.totals = {total: N.num('Total'), net: N.num('NetTotal'), vat: N.num('SalesTaxes'), after: N.num('TotalAfterTaxes')};
      out.filled = await N.buyer(); out.pay = N.payRows(P.pay); out.req = N.req(); return out;
    """, P, s, data.get("K1", ""))
    if t.get("miss"):
        return k.done(BDATA, f"الخزينة K1={data.get('K1')} مش موجودة في سطر النقدي")
    if t.get("err"):
        return k.done(BCAP, t["err"])
    if t.get("filled"):
        k.evidence.append("بعد اختيار طريقة الدفع اتملت بقيم اختبار: " + ", ".join(t["filled"]))
    tt = t["totals"]
    k.chk("قبل الحفظ", _close(tt["net"] or tt["total"], s["net"]) and _close(tt["vat"], s["vat"]) and _close(tt["after"], s["total"]),
          f"صافي {_f(tt['net'] or tt['total'])} · ضريبة {_f(tt['vat'])} · إجمالي {_f(tt['after'])} (المتوقع {_f(s['net'])} / {_f(s['vat'])} / {_f(s['total'])})")
    if t["req"]:
        return k.done(BDATA, "حقول إلزامية فاضية مالهاش قيمة في ملف البيانات: " + ", ".join(t["req"]))
    # save (once — or twice quickly for the double-save add-on)
    ok, log, sid, silent = _save(driver, P["save"], P["path"], times=2 if opts.get("double") else 1)
    if opts.get("reject"):
        n = _js(driver, "const [ctrl, before] = A; const all = await N.ids(ctrl); return Object.keys(all).filter(i => !before.includes(i));", P["ctrl"], b["ids"])
        st = _js(driver, "const [wh, it] = A; return await N.stock(wh, it);", data["W1"], b["item"]) if b.get("item") else None
        msg = " · ".join(log)[:300]
        k.chk("الرفض", not ok and not n, ("اترفض: " + (msg or "من غير رسالة")) if not ok and not n else f"اتحفظ (مستند Id {sid or ', '.join(n)}) — الـ ERP قبل كمية أكبر من الرصيد",
              "الحفظ يترفض ومفيش مستند")
        if b.get("stock") is not None and st is not None:
            k.chk("الرصيد ما اتغيرش", _close(st, b["stock"], 1e-6), f"قبل {b['stock']} · بعد {st}", f"{b['stock']}")
        if ok:
            k.doc_id = sid or (n[0] if n else "")
        return k.done()
    if not ok:
        msg = " · ".join(log)[:400] or "مفيش رد"
        if re.search(r"الحد الائتماني|الائتمان", msg) and code == "SAL":
            return k.done(BDATA, f"العميل C1 حده الائتماني مايسمحش — رسالة الـ ERP: {msg}")
        if re.search(r"الفترة|مغلق", msg):
            return k.done(BDATA, f"الفترة مقفولة — {msg}")
        k.chk("الحفظ", False, f"الـ ERP رفض: {msg}")
        return k.done()
    k.chk("الحفظ", True, "اتحفظ مرة واحدة" + (f" (Id {sid})" if sid else ""))
    if silent:
        k.evidence.append("ملاحظة: الـ ERP حفظ بس الشاشة ماظهرتش رسالة نجاح ولا رجعت للقائمة")
    # the new document
    n = _js(driver, "const [ctrl, before] = A; const all = await N.ids(ctrl); const neu = Object.keys(all).filter(i => !before.includes(i)).sort((x, y) => y - x); return {neu, rows: neu.map(i => all[i])};",
            P["ctrl"], b["ids"])
    if sid and sid not in n["neu"]:
        n["neu"].insert(0, sid)
        n["rows"].insert(0, {"text": "", "links": []})
    if not n["neu"]:
        k.chk("المستند في القائمة", False, "اتحفظ بس مش ظاهر في أول صفحة من القائمة")
        return k.done()
    i0 = n["neu"].index(sid) if sid in n["neu"] else 0
    k.doc_id = n["neu"][i0]
    row = n["rows"][i0]
    k.doc_no = row["text"].split(" | ")[0]
    k.chk("مستند واحد بس", len(n["neu"]) == 1, f"اتعمل {len(n['neu'])} مستند جديد" if len(n["neu"]) > 1 else f"رقم {k.doc_no} · Id {k.doc_id}")
    vlinks = sorted({m.group(1) for x in row["links"] if (m := re.search(rf"/{P['voucher']}/(?:AddEdit\w*/)?(\d+)", x, re.I))})
    if s["auto"]:
        k.chk("السند المخزني التابع", len(vlinks) == 1, f"{len(vlinks)} سند" + (f" (Id {vlinks[0]})" if vlinks else ""))
    else:
        k.chk("مفيش سند مخزني جديد", not vlinks, "مفيش" if not vlinks else f"اتعمل {len(vlinks)} سند رغم إن التوليد مقفول")
    # reopen
    _open(driver, f"/{P['ctrl']}/AddEdit/{k.doc_id}")
    r = _js(driver, "const [P] = A; return {rows: N.rows(P.body), total: N.num('Total'), net: N.num('NetTotal'), vat: N.num('SalesTaxes'), after: N.num('TotalAfterTaxes'), party: $('#' + P.party).val(), wh: $('#WarehouseId').val(), dep: $('#DepartmentId').val(), pay: N.payRows(P.pay), pt: $('#PaymentType').val(), doc: $('#DocumentNumber').val() || ''};", P)
    k.doc_no = k.doc_no or r.get("doc", "")
    ln = r["rows"][0] if r["rows"] else {}
    k.chk("إعادة الفتح", len(r["rows"]) == 1 and _close(ln.get("qty"), s["qty"], 1e-6) and _close(ln.get("price"), s["price"]) and str(r["party"]) == str(data[P["sym"]]) and str(r["wh"]) == str(data["W1"]),
          f"سطور {len(r['rows'])} · كمية {ln.get('qty', '—')} · سعر {_f(ln.get('price'))} · الطرف {r['party']} · المخزن {r['wh']}")
    k.chk("الإجماليات بعد الفتح", _close(r["net"] or r["total"], s["net"]) and _close(r["vat"], s["vat"]) and _close(r["after"], s["total"]),
          f"صافي {_f(r['net'] or r['total'])} · ضريبة {_f(r['vat'])} · إجمالي {_f(r['after'])} (المتوقع {_f(s['net'])} / {_f(s['vat'])} / {_f(s['total'])})")
    cash = sum(p["amt"] for p in r["pay"] if p["m"] == "1")
    paid = cash if r["pay"] else (s["total"] if r["pt"] == "1" else 0)
    k.chk("المدفوع", _close(paid, s["paid"]), f"نقدي {_f(paid)} (المتوقع {_f(s['paid'])})")
    # stock
    st = _js(driver, "const [wh, it] = A; return await N.stock(wh, it);", data["W1"], b["item"])
    if b["stock"] is not None and st is not None:
        dlt = round(float(st) - float(b["stock"]), 6)
        k.chk("كارت الصنف A في W1", _close(dlt, s["stock"], 1e-6), f"قبل {b['stock']} · بعد {st} · الفرق {dlt:g} (المتوقع {s['stock']:g})")
    else:
        k.evidence.append("رصيد الصنف: الـ ERP مارجّعش الكمية")
    # journal
    _journal(driver, k, P, day, k.doc_id, exp_total=None if opts.get("disc") else s["total"], exp_vat=s["vat"], exp_cash=s["paid"])
    k.spec = s
    return k.done()


def _journal(driver, k, P, day, op, exp_total, exp_vat=None, exp_cash=None):
    lines = None
    for _ in range(3):
        lines = _js(driver, "return await N.journal(A[0]);", day)
        mine = [x for x in (lines or []) if x["op"] == str(op) and re.search(P["jt"], x["type"]) and not re.search(r"مخازن|مخزن", x["type"])]
        if mine:
            break
        time.sleep(4)
    if lines is None:
        k.chk("القيد", False, "شاشة مراجعة القيود مارجعتش بيانات")
        return
    if not mine:
        k.chk("القيد", False, f"مفيش قيد للمستند Id {op} في مراجعة القيود النهارده")
        return
    d, c = round(sum(x["d"] for x in mine), 2), round(sum(x["c"] for x in mine), 2)
    k.journal = [{"je": x["je"], "acc": x["acc"].strip(), "d": x["d"], "c": x["c"]} for x in mine]
    k.evidence.append("القيد " + str(mine[0]["je"]) + ": " + " · ".join(f"{x['acc'].strip()[:40]} م{_f(x['d'])} د{_f(x['c'])}" for x in mine if x["d"] or x["c"]))
    k.chk("القيد متزن", _close(d, c), f"مدين {_f(d)} · دائن {_f(c)}")
    if exp_total is not None:
        k.chk("قيمة القيد", _close(d, exp_total), f"{_f(d)} (المتوقع {_f(exp_total)})")
    if exp_vat is not None:
        vat = round(sum(x["d"] + x["c"] for x in mine if re.search(r"ضريب|VAT", x["acc"], re.I)), 2)
        k.chk("ضريبة القيد", _close(vat, exp_vat), f"{_f(vat)} (المتوقع {_f(exp_vat)})")
    if exp_cash:
        side = "d" if P["cash"] == "d" else "c"
        cash = round(sum(x[side] for x in mine if re.search(r"صندوق|خزين|نقد", x["acc"])), 2)
        k.chk("طرف الخزينة", _close(cash, exp_cash), f"{_f(cash)} {'مدين' if side == 'd' else 'دائن'} (المتوقع {_f(exp_cash)})")
    zero = [x for x in mine if not x["d"] and not x["c"]]
    if zero:
        k.evidence.append(f"ملاحظة: {len(zero)} سطر بصفر في القيد ({', '.join(sorted({x['acc'].strip()[:40] for x in zero}))})")


def run_return(driver, code, c, data, day):
    """partial return linked to an original invoice made for this case (the Given fixture): 10 A at 100, tax 0/15, credit"""
    P, s, k = PROFILES[code], spec(code, c), Case(c)
    miss = _missing(data, ["D1", "W1", "A", P["sym"]])
    if miss:
        return k.done(BDATA, "ناقص في ملف بيانات الموقع: " + ", ".join(miss))
    logger.info(f"▶ {c['id']} — {c['title']} (أولًا: الفاتورة الأصلية)")
    vat0 = round(s["orig_qty"] * s["price"] * s["tax"] / 100, 2)
    fx_case = {"id": c["id"] + "-أصل", "title": f"NONE ضريبة {s['tax']:g} سداد CREDIT", "given": "",
               "when": [f"أدخل سطرًا يدويًا {s['orig_qty']:g} وحدات من A بسعر {s['price']:g}."],
               "then": f"صافي {s['orig_qty'] * s['price']:g}؛ ضريبة {vat0:g}؛ إجمالي {s['orig_qty'] * s['price'] + vat0:g}؛ المدفوع 0."}
    fx = run_invoice(driver, P["origin"], fx_case, data, day)
    if not fx.doc_id:
        return k.done(BDATA, f"الفاتورة الأصلية (تجهيز الحالة) ما اتعملتش: {fx.actual[:300]}")
    if not fx.doc_no:
        _open(driver, f"/{PROFILES[P['origin']]['ctrl']}/AddEdit/{fx.doc_id}")
        fx.doc_no = _js(driver, "return $('#DocumentNumber').val() || '';")
    k.evidence.append(f"الفاتورة الأصلية: رقم {fx.doc_no} · Id {fx.doc_id} ({fx.status})")

    def open_linked():
        _open(driver, P["path"])
        return _js(driver, r"""
          const [P, d, no] = A; const out = {miss: []};
          if (!N.has('DepartmentId', d.D1)) out.miss.push('D1'); else await N.set('DepartmentId', d.D1, 2000);
          if (!N.has('WarehouseId', d.W1)) out.miss.push('W1'); else await N.set('WarehouseId', d.W1, 1500);
          if (!N.has(P.party, d[P.sym])) out.miss.push(P.sym); else await N.set(P.party, d[P.sym], 4000);
          if (out.miss.length) return out;
          if (P.link === 'select') {
            let ok = false; for (let i = 0; i < 10 && !ok; i++) { ok = N.has('AvailableSalesInvoices', no); if (!ok) await N.w(1000); }
            if (!ok) return {err: 'الفاتورة الأصلية ' + no + ' مش ظاهرة في «فواتير البيع المتاحة» للعميل'};
            $('#AvailableSalesInvoices').val(no).trigger('change');
          } else { $('#PurchaseInvoiceNo').val(no); if (typeof LinkWithSalesInvoice === 'function') LinkWithSalesInvoice(); else return {err: 'زرار «ربط» مش موجود'}; }
          let rows = []; for (let i = 0; i < 15; i++) { await N.w(1000); rows = N.rows(P.body); if (rows.length) break; }
          await N.w(1500); rows = N.rows(P.body);
          return {rows, ids: Object.keys(await N.ids(P.ctrl))};
        """, P, data, fx.doc_no)

    h = open_linked()
    if h.get("miss"):
        return k.done(BDATA, "القيم دي مش موجودة في قوائم الشاشة: " + ", ".join(h["miss"]))
    if h.get("err"):
        return k.done(BCAP, h["err"])
    r0 = h["rows"]
    if not k.chk("استدعاء الأصل", len(r0) == 1 and _close(r0[0]["qty"], s["orig_qty"], 1e-6) and _close(r0[0]["price"], s["price"]),
                 f"سطور {len(r0)}" + (f" · كمية {r0[0]['qty']:g} · سعر {_f(r0[0]['price'])}" if r0 else "")):
        return k.done()
    item_id = r0[0]["id"]
    t = _js(driver, r"""
      const [P, s, wh, it] = A; const out = {};
      const tr = [...document.querySelectorAll('#' + P.body + ' tr')].find(r => $(r).find('.item-name').val());
      $(tr).find('.quantity').val(s.qty).trigger('input').trigger('change'); await N.w(1500);
      await N.set('PaymentType', '2', 2000);
      out.auto = await N.check('AutoGenerateStockReceiptVoucher', s.auto, 800);
      out.ht = await N.check('hasTaxes', s.tax > 0, 2500);
      const ad = document.getElementById('AccountingDocumentId'); if (ad && !ad.value) { const o = [...ad.options].find(x => x.value); if (o) await N.set('AccountingDocumentId', o.value, 600); }
      out.dropped = await N.dropEmpty(P.body);
      if (typeof CalculateTotals === 'function') { try { CalculateTotals(); } catch (e) {} await N.w(2500); }
      out.totals = {total: N.num('Total'), net: N.num('NetTotal'), vat: N.num('SalesTaxes'), after: N.num('TotalAfterTaxes')};
      out.stock = it ? await N.stock(wh, it) : null; out.req = N.req(); out.filled = await N.buyer(); return out;
    """, P, s, data["W1"], item_id)
    if t.get("dropped"):
        k.evidence.append(f"اتمسح {t['dropped']} سطر فاضي في التفاصيل — كان مانع الحفظ من غير أي رسالة")
    k.evidence.append(f"المرتجع: {s['qty']:g} من {s['orig_qty']:g} · تسوية على حساب الطرف · التوليد {'مفتوح' if t.get('auto') else 'مغلق'} · رصيد W1 قبل الحفظ {t.get('stock')}")
    tt = t["totals"]
    k.chk("قبل الحفظ", _close(tt["net"] or tt["total"], s["net"]) and _close(tt["vat"], s["vat"]) and _close(tt["after"], s["total"]),
          f"صافي {_f(tt['net'] or tt['total'])} · ضريبة {_f(tt['vat'])} · إجمالي {_f(tt['after'])} (المتوقع {_f(s['net'])} / {_f(s['vat'])} / {_f(s['total'])})")
    if t["req"]:
        return k.done(BDATA, "حقول إلزامية فاضية: " + ", ".join(t["req"]))
    ok, log, sid, silent = _save(driver, P["save"], P["path"])
    if not ok:
        k.chk("الحفظ", False, "الـ ERP رفض: " + (" · ".join(log)[:400] or "مفيش رد"))
        return k.done()
    k.chk("الحفظ", True, "اتحفظ مرة واحدة" + (f" (Id {sid})" if sid else ""))
    if silent:
        k.evidence.append("ملاحظة: الـ ERP حفظ بس الشاشة ماظهرتش رسالة نجاح ولا رجعت للقائمة")
    n = _js(driver, "const [ctrl, before] = A; const all = await N.ids(ctrl); const neu = Object.keys(all).filter(i => !before.includes(i)).sort((x, y) => y - x); return {neu, rows: neu.map(i => all[i])};",
            P["ctrl"], h["ids"])
    if sid and sid not in n["neu"]:
        n["neu"].insert(0, sid)
        n["rows"].insert(0, {"text": "", "links": []})
    if not n["neu"]:
        k.chk("المرتجع في القائمة", False, "اتحفظ بس مش ظاهر في أول صفحة من القائمة")
        return k.done()
    i0 = n["neu"].index(sid) if sid in n["neu"] else 0
    k.doc_id, row = n["neu"][i0], n["rows"][i0]
    k.doc_no = row["text"].split(" | ")[0]
    vl = sorted({m.group(1) for x in row["links"] if (m := re.search(rf"/{P['voucher']}/(?:AddEdit\w*/)?(\d+)", x, re.I))})
    if s["auto"]:
        k.chk("السند المخزني التابع", len(vl) == 1, f"{len(vl)} سند" + (f" (Id {vl[0]})" if vl else ""))
    else:
        k.chk("مفيش سند مخزني جديد", not vl, "مفيش" if not vl else f"اتعمل {len(vl)} سند رغم إن التوليد مقفول")
    _open(driver, f"/{P['ctrl']}/AddEdit/{k.doc_id}")
    r = _js(driver, "const [P] = A; return {rows: N.rows(P.body), total: N.num('Total'), net: N.num('NetTotal'), vat: N.num('SalesTaxes'), after: N.num('TotalAfterTaxes'), party: $('#' + P.party).val(), doc: $('#DocumentNumber').val() || ''};", P)
    k.doc_no = k.doc_no or r.get("doc", "")
    ln = r["rows"][0] if r["rows"] else {}
    k.chk("إعادة الفتح", len(r["rows"]) == 1 and _close(ln.get("qty"), s["qty"], 1e-6) and str(r["party"]) == str(data[P["sym"]]),
          f"سطور {len(r['rows'])} · كمية {ln.get('qty', '—')} · الطرف {r['party']}")
    k.chk("الإجماليات بعد الفتح", _close(r["net"] or r["total"], s["net"]) and _close(r["vat"], s["vat"]) and _close(r["after"], s["total"]),
          f"صافي {_f(r['net'] or r['total'])} · ضريبة {_f(r['vat'])} · إجمالي {_f(r['after'])} (المتوقع {_f(s['net'])} / {_f(s['vat'])} / {_f(s['total'])})")
    st = _js(driver, "const [wh, it] = A; return await N.stock(wh, it);", data["W1"], item_id) if item_id else None
    if t.get("stock") is not None and st is not None:
        dlt = round(float(st) - float(t["stock"]), 6)
        k.chk("كارت الصنف A في W1", _close(dlt, s["stock"], 1e-6), f"قبل {t['stock']} · بعد {st} · الفرق {dlt:g} (المتوقع {s['stock']:g})")
    _journal(driver, k, P, day, k.doc_id, exp_total=s["total"], exp_vat=s["vat"])
    k.spec = s
    if s.get("left") is not None:
        h2 = open_linked()
        r2 = h2.get("rows") or []
        k.chk("المتاح للإرجاع من الأصل", len(r2) == 1 and _close(r2[0]["qty"], s["left"], 1e-6),
              (f"{r2[0]['qty']:g}" if r2 else (h2.get("err") or "الأصل مارجعش سطور")) + f" (المتوقع {s['left']:g}) — اتقرا من مرتجع جديد ما اتحفظش")
    return k.done()


def run_voucher(driver, code, c, data, day, opts=None):
    P, s, k = PROFILES[code], spec(code, c), Case(c)
    opts = opts or {}
    miss = _missing(data, ["D1", "K1", P["sym"]])
    if miss:
        return k.done(BDATA, "ناقص في ملف بيانات الموقع: " + ", ".join(miss))
    logger.info(f"▶ {c['id']} — {c['title']}")
    _open(driver, P["path"])
    b = _js(driver, "const [ctrl, cust, isC] = A; return {ids: Object.keys(await N.ids(ctrl)), bal: isC ? await N.balance(cust) : null};",
            P["ctrl"], data[P["sym"]], P["sym"] == "C1")
    h = _js(driver, r"""
      const [P, d, amt] = A; const out = {miss: []};
      if (!N.has('DepartmentId', d.D1)) out.miss.push('D1'); else await N.set('DepartmentId', d.D1, 2000);
      await N.set('SourceTypeId', P.src, 2500);
      const pid = d[P.sym];
      if (P.ajax) { const r = await N.get(P.ajax + '?' + new URLSearchParams({term: '', departmentId: d.D1})); let l = []; try { l = JSON.parse(r); } catch (e) {}
        let x = l.find(v => String(v.Id) === String(pid));
        if (!x) { for (const t of ['ا', 'م', 'ش', '1']) { try { l = JSON.parse(await N.get(P.ajax + '?' + new URLSearchParams({term: t, departmentId: d.D1}))); } catch (e) { l = []; } x = l.find(v => String(v.Id) === String(pid)); if (x) break; } }
        if (!x) out.miss.push(P.sym); else { $('#' + P.party).append(new Option(x.ArName, x.Id, true, true)).trigger('change');
          $('#' + P.party).trigger({type: 'select2:select', params: {data: {id: String(x.Id), text: x.ArName}}}); await N.w(3000); } }
      else if (!N.has(P.party, pid)) out.miss.push(P.sym); else await N.set(P.party, pid, 2500);
      await N.set(P.method, '1', 2500);
      if (!N.has('CashBoxId', d.K1)) out.miss.push('K1'); else await N.set('CashBoxId', d.K1, 1200);
      $('#MoneyAmount').val(amt).trigger('input').trigger('change'); await N.w(1000);
      const ad = document.getElementById('AccountingDocumentId'); if (ad && !ad.value) { const o = [...ad.options].find(x => x.value); if (o) { await N.set('AccountingDocumentId', o.value, 600); out.adoc = o.textContent.trim(); } }
      out.req = N.req(); out.amount = N.num('MoneyAmount'); out.party = $('#' + P.party).val(); return out;
    """, P, data, s["amount"])
    if h["miss"]:
        return k.done(BDATA, "القيم دي مش موجودة في قوائم الشاشة: " + ", ".join(f"{m}={data.get(m)}" for m in h["miss"]))
    if h["req"]:
        return k.done(BDATA, "حقول إلزامية فاضية: " + ", ".join(h["req"]))
    k.evidence.append(f"الطرف {P['sym']}={h['party']} · نقدي من K1={data['K1']} · المبلغ {_f(h['amount'])} · بدون تخصيص فواتير" + (f" · نوع المستند «{h['adoc']}»" if h.get("adoc") else ""))
    ok, log, sid, silent = _save(driver, P["save"], P["path"], times=2 if opts.get("double") else 1)
    if not ok:
        k.chk("الحفظ", False, "الـ ERP رفض: " + (" · ".join(log)[:400] or "مفيش رد"))
        return k.done()
    k.chk("الحفظ", True, "اتحفظ مرة واحدة" + (f" (Id {sid})" if sid else ""))
    n = _js(driver, "const [ctrl, before] = A; const all = await N.ids(ctrl); const neu = Object.keys(all).filter(i => !before.includes(i)).sort((x, y) => y - x); return {neu, rows: neu.map(i => all[i])};",
            P["ctrl"], b["ids"])
    if sid and sid not in n["neu"]:
        n["neu"].insert(0, sid)
        n["rows"].insert(0, {"text": "", "links": []})
    if not n["neu"]:
        k.chk("السند في القائمة", False, "اتحفظ بس مش ظاهر في أول صفحة من القائمة")
        return k.done()
    i0 = n["neu"].index(sid) if sid in n["neu"] else 0
    k.doc_id, k.doc_no = n["neu"][i0], n["rows"][i0]["text"].split(" | ")[0]
    k.chk("سند واحد بس", len(n["neu"]) == 1, f"رقم {k.doc_no} · Id {k.doc_id}")
    _open(driver, f"/{P['ctrl']}/AddEdit/{k.doc_id}")
    r = _js(driver, "const [P] = A; return {amount: N.num('MoneyAmount'), party: $('#' + P.party).val(), box: $('#CashBoxId').val(), doc: $('#DocumentNumber').val() || ''};", P)
    k.doc_no = k.doc_no or r.get("doc", "")
    k.chk("إعادة الفتح", _close(r["amount"], s["amount"]) and str(r["party"]) == str(data[P["sym"]]),
          f"المبلغ {_f(r['amount'])} · الطرف {r['party']} · الخزينة {r['box']}")
    if b.get("bal"):
        a2 = _js(driver, "return await N.balance(A[0]);", data[P["sym"]])
        try:
            dlt = round(float(b["bal"].get("Balance") or 0) - float((a2 or {}).get("Balance") or 0), 2)
            k.chk("دين العميل", _close(dlt, s["amount"]), f"قبل {_f(b['bal'].get('Balance'))} · بعد {_f((a2 or {}).get('Balance'))} · نقص {_f(dlt)}")
        except (TypeError, ValueError):
            pass
    _journal(driver, k, P, day, k.doc_id, exp_total=s["amount"], exp_cash=s["amount"])
    k.spec = s
    return k.done()


# ------------------------------------------------------------------ the run
def run_cases(driver, credentials, cfg, result=None):
    """one screen (cfg.screen + cfg.cases) or several one after the other (cfg.screens = [{screen, cases}])"""
    from engine.screen_runner import login
    from engine.guard import require_write
    from config.settings import BASE_URL
    result = result if result is not None else {}
    if cfg.get("discover"):
        return discover(driver, credentials, cfg, result)
    plan = cfg.get("screens") or [{"screen": cfg.get("screen", ""), "cases": cfg.get("cases") or []}]
    cats = catalog()
    jobs = []
    for p in plan:
        cat = cats.get(str(p.get("screen", "")).upper())
        if not cat:
            logger.warning(f"ملف سيناريوهات {p.get('screen')} مش موجود — اتخطى")
            continue
        want = set(p.get("cases") or [c["id"] for c in cat["cases"] if c["auto"]])
        jobs.append((cat, [c for c in cat["cases"] if c["id"] in want]))
    if not jobs:
        raise AssertionError("مفيش شاشة معروفة في التشغيلة")
    data = load_data(BASE_URL)
    runs_any = any(c["auto"] for _, todo in jobs for c in todo)
    if runs_any and _missing(data, [k for k, _ in SYMBOLS]):
        logger.info("🔎 ملف بيانات الموقع ناقص — بملاه تلقائي من الموقع الأول (قراءة بس)")
        try:
            discover(driver, credentials, {}, {})
        except Exception as e:
            logger.warning(f"التعبئة التلقائية: {str(e)[:200]}")
        data = load_data(BASE_URL)
    day = datetime.now().strftime("%Y-%m-%d")
    if runs_any:
        require_write("سيناريوهات " + " + ".join(cat["name"] for cat, _ in jobs))
        login(driver, credentials)
    groups = []
    for gi, (cat, todo) in enumerate(jobs, 1):
        code = cat["code"]
        logger.info(f"━━━━ {gi}/{len(jobs)} · {cat['icon']} {cat['name']} — {len(todo)} حالة")
        out = {}
        for c in todo:
            if not c["auto"]:
                out[c["id"]] = Case(c).done(BCAP, c["why"])
                out[c["id"]].plain = c["title"]
                continue
            try:
                fn = {"invoice": run_invoice, "return": run_return}.get(PROFILES[code]["kind"], run_voucher)
                out[c["id"]] = fn(driver, code, c, data, day)
            except Exception as e:
                logger.warning(f"{c['id']}: {e}")
                out[c["id"]] = Case(c).done(BCAP, f"المحرك وقف: {str(e)[:300]}")
            k = out[c["id"]]
            k.plain = describe(code, c)
            logger.info(f"{'✅' if k.status == PASS else ('❌' if k.status == FAIL else '⚪')} {c['id']} {k.status} — {k.actual[:200]}")
        keys = [x for x in (cfg.get("addons") or []) if x]
        if keys:
            from engine import biz_addons
            out.update(biz_addons.run(driver, cat, out, data, day, keys))
        groups.append((cat, out))
    return _finish(result, groups, data, BASE_URL, credentials)


def _finish(result, groups, data, url, credentials):
    names = {PASS: "ناجح", FAIL: "فاشل", BDATA: "ناقص بيانات", BCAP: "مش مؤتمت", NOTRUN: "لم يُنفذ"}
    allk = {i: k for _, out in groups for i, k in out.items()}
    counts = {}
    for k in allk.values():
        counts[k.status] = counts.get(k.status, 0) + 1
    specs = {}
    for cat, out in groups:
        try:
            specs[cat["code"]] = fill_word(cat, out, url)
        except Exception as e:
            logger.warning(f"ملف الورد ({cat['code']}) ما اتملاش: {e}")
    report = ""
    try:
        from engine import biz_report
        from config import paths
        tag = "_".join(cat["code"] for cat, _ in groups)
        report = biz_report.build_many(groups, data, url, (credentials or {}).get("username", ""),
                                       paths.RESULTS_DIR / f"biz_report_{tag}_{datetime.now():%Y%m%d_%H%M%S}.docx", SYMBOLS, NAMES)
    except Exception as e:
        logger.warning(f"تقرير النتيجة ما اتعملش: {e}")
    multi = len(groups) > 1
    rows = [{"cells": [k.c["id"], (f"{cat['name']} — " if multi else "") + k.c["title"], names[k.status], k.doc_no or "—", k.actual, " · ".join(k.evidence)[:600]],
             "ok": True if k.status == PASS else (False if k.status == FAIL else None)} for cat, out in groups for k in out.values()]
    title = " + ".join(cat["name"] for cat, _ in groups)
    note = " · ".join(f"{names[s]} {n}" for s, n in counts.items()) + f" — {title} ({len(allk)} حالة)"
    files = ([{"name": "تقرير النتيجة (Word)", "path": report}] if report else []) + \
            [{"name": f"ملف المطور بالحالات — {NAMES.get(c, c)} (Word)", "path": p} for c, p in specs.items() if p]
    result["detail"] = {"title": f"📚 سيناريوهات المطور — {title}", "columns": ["الحالة", "العنوان", "النتيجة", "المستند", "الفعلي", "الدليل"],
                        "rows": rows, "note": note, "files": files}
    result["biz"] = {"screen": groups[0][0]["code"], "screens": [cat["code"] for cat, _ in groups], "url": str(url).rstrip("/"), "word": report or next(iter(specs.values()), ""),
                     "spec_words": specs, "data": data,
                     "cases": {i: {"status": k.status, "doc": k.doc_no, "id": k.doc_id, "actual": k.actual, "plain": k.plain, "title": k.c["title"],
                                   "checks": [list(x) for x in k.checks], "journal": k.journal, "evidence": k.evidence} for i, k in allk.items()}}
    logger.info("📚 " + note)
    if counts.get(FAIL):
        e = AssertionError(f"سيناريوهات {title}: فاشل {counts.get(FAIL, 0)} · ناجح {counts.get(PASS, 0)}"
                           + "".join(f"\n   {i}: {k.actual[:160]}" for i, k in allk.items() if k.status == FAIL))
        e.partial_result = result
        raise e
    return result


# ------------------------------------------------------------------ the developer's Word file, with the results
def fill_word(cat, out, url):
    import docx
    from docx.shared import RGBColor
    from config import paths
    d = docx.Document(str(_dir() / cat["file"]))
    color = {PASS: RGBColor(0x1E, 0x8E, 0x3E), FAIL: RGBColor(0xC6, 0x28, 0x28), BDATA: RGBColor(0xB2, 0x6A, 0x00), BCAP: RGBColor(0x6B, 0x6B, 0x6B)}
    cur = None
    for p in d.paragraphs:
        t = p.text
        m = re.match(r"Case ID: (\S+)", t)
        if m:
            cur = out.get(m[1])
            if cur:
                for r in p.runs:
                    if r.text.strip() == "NOT_RUN":
                        r.text = cur.status
                        r.bold = True
                        if cur.status in color:
                            r.font.color.rgb = color[cur.status]
            continue
        if cur and t.startswith("Actual:") and len(p.runs) >= 8:
            vals = [cur.actual or "—", f"{cur.doc_id or '—'} / {cur.doc_no or '—'}", " · ".join(cur.evidence)[:700] or "—", "—"]
            for i, v in zip((1, 3, 5, 7), vals):
                p.runs[i].text = f" {v}" + ("  |  " if i < 7 else "")
            cur = None
    for p in d.paragraphs[:3]:
        if p.style.name.startswith("Subtitle") and p.runs:
            n = {s: sum(1 for k in out.values() if k.status == s) for s in (PASS, FAIL, BDATA, BCAP)}
            p.add_run(f"  |  تشغيل {datetime.now():%Y-%m-%d %H:%M} على {url} — PASS {n[PASS]} · FAIL {n[FAIL]} · BLOCKED {n[BDATA] + n[BCAP]}")
            break
    o = paths.RESULTS_DIR / f"biz_{cat['code']}_{datetime.now():%Y%m%d_%H%M%S}.docx"
    o.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(o))
    return str(o)
