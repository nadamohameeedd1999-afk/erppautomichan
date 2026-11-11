"""
➕ الاختبارات الإضافية — the extra checks of the developer's first form (edit after save, print, double save, required
fields, quantity above stock, invoice discount), turned into switches that work on ANY screen the engine runs.
They run ONCE per screen, after its cases, on the document a passed case made (or a new one made the same way).
Each one comes back as an extra case «<CODE>-ADD-<KEY>» so it shows in the report, the runs table and «دعم المطورين».
"""
import base64
import io
import math
import re

from utils.logger import logger

ADDONS = [
    # key, title, what it checks, screen kinds it works on, only these screens (or None), on by default
    ("edit", "التعديل بعد الحفظ", "تغيير الكمية (أو المبلغ) على مستند محفوظ وحفظه: نفس الرقم ومفيش مستند جديد، والإجماليات والمخزن والقيد اتعدلوا مش اتكرروا",
     ("invoice", "return", "voucher"), None, True),
    ("print", "الطباعة", "صفحة الطباعة بتفتح وفيها نفس رقم المستند والإجمالي", ("invoice", "return", "voucher"), None, False),
    ("double", "الحفظ مرتين بسرعة", "دوستين ورا بعض على الحفظ يطلّعوا مستند واحد بس", ("invoice", "voucher"), None, False),
    ("required", "الحفظ من غير بيانات", "شاشة جديدة فاضية والحفظ لازم يترفض ومفيش مستند يتعمل", ("invoice", "return", "voucher"), None, False),
    ("overstock", "كمية أكبر من الرصيد", "فاتورة بيع بكمية أكبر من رصيد المخزن والصرف التلقائي مفتوح: لازم تترفض والرصيد مايتغيرش", ("invoice",), ("SAL",), False),
    ("discount", "الخصم على الفاتورة", "خصم 10% على الفاتورة: الصافي والضريبة بعد الخصم والقيد متزن", ("invoice",), ("SAL", "PUR"), False),
]
BY_KEY = {a[0]: a for a in ADDONS}


def applies(key, code):
    from engine.biz_cases import PROFILES
    a = BY_KEY.get(key)
    if not a or code not in PROFILES:
        return False
    return PROFILES[code]["kind"] in a[3] and (a[4] is None or code in a[4])


def catalog():
    from engine.biz_cases import PROFILES
    return [{"key": k, "title": t, "desc": d, "default": dflt, "screens": [c for c in PROFILES if applies(k, c)]} for k, t, d, _kinds, _only, dflt in ADDONS]


def _case(code, key):
    a = BY_KEY[key]
    return {"id": f"{code}-ADD-{key.upper()}", "title": "➕ " + a[1], "then": a[2], "given": "", "when": [], "pri": "ADD", "basis": "ADDON"}


def _base_case(cat, title):
    return next((c for c in cat["cases"] if c["title"] == title), None)


def run(driver, cat, out, data, day, keys):
    """→ {case id: Case} for the add-ons that apply to this screen"""
    from engine import biz_cases as B
    code = cat["code"]
    res = {}
    passed = [k for k in out.values() if k.status == B.PASS and k.doc_id and k.spec]
    base = next((k for k in passed if k.spec.get("pay", "CREDIT") == "CREDIT"), passed[0] if passed else None)
    for key in keys:
        if not applies(key, code):
            continue
        c = _case(code, key)
        logger.info(f"➕ {c['id']} — {BY_KEY[key][1]}")
        try:
            if key == "edit":
                k = edit(driver, code, c, base, data, day) if base else B.Case(c).done(B.BDATA, "مفيش حالة نجحت في الشاشة دي علشان أعدّل المستند بتاعها")
            elif key == "print":
                k = print_check(driver, code, c, base) if base else B.Case(c).done(B.BDATA, "مفيش حالة نجحت في الشاشة دي علشان أطبع المستند بتاعها")
            elif key == "required":
                k = required(driver, code, c)
            elif key == "double":
                k = double(driver, cat, code, c, data, day)
            elif key == "discount":
                k = discount(driver, cat, code, c, data, day)
            elif key == "overstock":
                k = overstock(driver, cat, code, c, data, day)
            else:
                continue
        except Exception as e:
            logger.warning(f"{c['id']}: {e}")
            k = B.Case(c).done(B.BCAP, f"المحرك وقف: {str(e)[:300]}")
        k.c = c
        k.plain = f"اختبار إضافي — {BY_KEY[key][1]}: {BY_KEY[key][2]}"
        res[c["id"]] = k
        logger.info(f"{'✅' if k.status == B.PASS else ('❌' if k.status == B.FAIL else '⚪')} {c['id']} {k.status} — {k.actual[:200]}")
    return res


# ------------------------------------------------------------------ edit after save
def edit(driver, code, c, base, data, day):
    from engine import biz_cases as B
    P, s, k = B.PROFILES[code], dict(base.spec), B.Case(c)
    path = f"/{P['ctrl']}/AddEdit/{base.doc_id}"
    k.evidence.append(f"على مستند الحالة {base.c['id']}: رقم {base.doc_no or '—'} · Id {base.doc_id}")
    B._open(driver, path)
    if P["kind"] == "voucher":
        new_amt = round(float(s["amount"]) + 50, 2)
        b = B._js(driver, "const [P] = A; return {ids: Object.keys(await N.ids(P.ctrl)), amount: N.num('MoneyAmount')};", P)
        k.chk("المستند اتفتح", B._close(b["amount"], s["amount"]), f"المبلغ {B._f(b['amount'])}", B._f(s["amount"]))
        B._js(driver, "$('#MoneyAmount').val(A[0]).trigger('input').trigger('change'); await N.w(1200); return 1;", new_amt)
        exp = {"amount": new_amt}
    else:
        new_q = s["qty"] + 2 if P["kind"] == "invoice" else max(s["qty"] - 1, 1)
        net = round(new_q * s["price"], 2)
        vat = round(net * s["tax"] / 100, 2)
        exp = {"qty": new_q, "net": net, "vat": vat, "total": round(net + vat, 2)}
        b = B._js(driver, r"""
          const [P, wh] = A; const rows = N.rows(P.body); const it = rows.length ? rows[0].id : null;
          return {ids: Object.keys(await N.ids(P.ctrl)), rows, item: it, stock: it ? await N.stock(wh, it) : null, total: N.num('TotalAfterTaxes')};
        """, P, data.get("W1"))
        if not k.chk("المستند اتفتح", len(b["rows"]) == 1 and B._close(b["rows"][0]["qty"], s["qty"], 1e-6),
                     f"سطور {len(b['rows'])} · كمية {b['rows'][0]['qty'] if b['rows'] else '—'}", f"سطر واحد بكمية {s['qty']:g}"):
            return k.done()
        t = B._js(driver, r"""
          const [P, q, cash] = A;
          const tr = [...document.querySelectorAll('#' + P.body + ' tr')].find(r => $(r).find('.item-name').val());
          $(tr).find('.quantity').val(q).trigger('input').trigger('change'); await N.w(1500);
          if (P.kind === 'return') await N.dropEmpty(P.body);
          if (typeof CalculateTotals === 'function') { try { CalculateTotals(); } catch (e) {} await N.w(2000); }
          await N.buyer();
          return {net: N.num('NetTotal') || N.num('Total'), vat: N.num('SalesTaxes'), after: N.num('TotalAfterTaxes'), req: N.req()};
        """, P, new_q, s.get("paid", 0))
        k.chk("الحسبة بعد تغيير الكمية", B._close(t["net"], net) and B._close(t["vat"], vat) and B._close(t["after"], exp["total"]),
              f"كمية {new_q:g} · صافي {B._f(t['net'])} · ضريبة {B._f(t['vat'])} · إجمالي {B._f(t['after'])}", f"{B._f(net)} / {B._f(vat)} / {B._f(exp['total'])}")
    ok, log, sid, silent = B._save(driver, P["save"], path)
    if not k.chk("حفظ التعديل", ok, "اتحفظ" if ok else "الـ ERP رفض: " + (" · ".join(log)[:300] or "مفيش رد"), "يتحفظ"):
        return k.done()
    k.chk("نفس المستند", not sid or str(sid) == str(base.doc_id), f"Id {sid or base.doc_id}", f"Id {base.doc_id}")
    neu = B._js(driver, "const [ctrl, before] = A; const all = await N.ids(ctrl); return Object.keys(all).filter(i => !before.includes(i));", P["ctrl"], b["ids"])
    k.chk("مفيش مستند جديد", not neu, "مفيش" if not neu else f"اتعمل مستند جديد Id {', '.join(neu)}", "مفيش")
    B._open(driver, path)
    if P["kind"] == "voucher":
        r = B._js(driver, "return {amount: N.num('MoneyAmount')};")
        k.chk("المبلغ بعد إعادة الفتح", B._close(r["amount"], exp["amount"]), B._f(r["amount"]), B._f(exp["amount"]))
        B._journal(driver, k, P, day, base.doc_id, exp_total=exp["amount"], exp_cash=exp["amount"])
        return k.done()
    r = B._js(driver, "const [P] = A; return {rows: N.rows(P.body), net: N.num('NetTotal') || N.num('Total'), vat: N.num('SalesTaxes'), after: N.num('TotalAfterTaxes')};", P)
    q = r["rows"][0]["qty"] if r["rows"] else None
    k.chk("بعد إعادة الفتح", len(r["rows"]) == 1 and B._close(q, exp["qty"], 1e-6) and B._close(r["after"], exp["total"]),
          f"سطور {len(r['rows'])} · كمية {q} · إجمالي {B._f(r['after'])}", f"كمية {exp['qty']:g} · إجمالي {B._f(exp['total'])}")
    if b.get("item") and b.get("stock") is not None:
        st = B._js(driver, "const [wh, it] = A; return await N.stock(wh, it);", data.get("W1"), b["item"])
        moved = (exp["qty"] - s["qty"]) * P["sign"] if s.get("auto") else 0.0
        if st is not None:
            dl = round(float(st) - float(b["stock"]), 6)
            k.chk("حركة المخزن بعد التعديل", B._close(dl, moved, 1e-6), f"قبل {b['stock']} · بعد {st} · الفرق {dl:g}", f"{moved:g}")
    B._journal(driver, k, P, day, base.doc_id, exp_total=exp["total"], exp_vat=exp["vat"])
    return k.done()


# ------------------------------------------------------------------ print
def print_check(driver, code, c, base):
    from engine import biz_cases as B
    P, k = B.PROFILES[code], B.Case(c)
    B._open(driver, f"/{P['ctrl']}/AddEdit/{base.doc_id}")
    links = B._js(driver, "const [ctrl, id] = A; const all = await N.ids(ctrl); return (all[id] || {}).links || [];", P["ctrl"], str(base.doc_id))
    url = next((l for l in links if re.search(r"/Report/|print=True|Preview", l, re.I) and str(base.doc_id) in l), None)
    if not url:
        return k.done(B.BCAP, "مالقيتش رابط الطباعة للمستند في القائمة")
    k.evidence.append(f"رابط الطباعة: {url}")
    r = B._js(driver, r"""
      const [u] = A; const res = await fetch(u, {credentials: 'include'}); const t = res.headers.get('content-type') || '';
      const b = new Uint8Array(await res.arrayBuffer()); let s = ''; for (let i = 0; i < b.length; i += 8192) s += String.fromCharCode.apply(null, b.subarray(i, i + 8192));
      return {status: res.status, type: t, size: b.length, b64: b.length < 4000000 ? btoa(s) : ''};
    """, url)
    if not k.chk("صفحة الطباعة بتفتح", r["status"] == 200 and r["size"] > 500, f"HTTP {r['status']} · {r['type'] or '—'} · {r['size']:,} بايت", "HTTP 200 وفيها محتوى"):
        return k.done()
    raw = base64.b64decode(r["b64"]) if r.get("b64") else b""
    text = ""
    if "pdf" in (r["type"] or "").lower() or raw[:4] == b"%PDF":
        try:
            from pypdf import PdfReader
            text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(raw)).pages)
        except Exception as e:
            return k.done(B.BCAP, f"مقدرتش أقرا الـ PDF: {e}")
    else:
        text = re.sub(r"<[^>]+>", " ", raw.decode("utf-8", "replace"))
    flat = re.sub(r"\s+", "", text)
    s = base.spec
    total = s.get("total") or s.get("amount")
    forms = {f"{total:,.2f}", f"{total:.2f}", f"{total:g}"} if total is not None else set()
    k.chk("رقم المستند في الطباعة", bool(base.doc_no) and str(base.doc_no) in flat, "موجود" if base.doc_no and str(base.doc_no) in flat else "مش لاقيه", str(base.doc_no or "—"))
    k.chk("الإجمالي في الطباعة", any(f.replace(",", "") in flat.replace(",", "") for f in forms), "موجود" if any(f.replace(",", "") in flat.replace(",", "") for f in forms) else "مش لاقيه", B._f(total))
    if s.get("vat"):
        vf = f"{s['vat']:.2f}"
        k.chk("الضريبة في الطباعة", vf in flat.replace(",", ""), "موجودة" if vf in flat.replace(",", "") else "مش لاقيها", B._f(s["vat"]))
    return k.done()


# ------------------------------------------------------------------ required fields
def required(driver, code, c):
    from engine import biz_cases as B
    P, k = B.PROFILES[code], B.Case(c)
    B._open(driver, P["path"])
    before = B._js(driver, "return Object.keys(await N.ids(A[0]));", P["ctrl"])
    ok, log, sid, silent = B._save(driver, P["save"], P["path"])
    marks = 0
    try:
        marks = driver.execute_script("return document.querySelectorAll('.required-empty, .is-invalid, .input-validation-error').length")
    except Exception:
        pass
    neu = B._js(driver, "const [ctrl, before] = A; const all = await N.ids(ctrl); return Object.keys(all).filter(i => !before.includes(i));", P["ctrl"], before)
    msg = " · ".join(log)[:300]
    k.chk("الحفظ اترفض", not ok and not neu, ("اترفض: " + (msg or (f"من غير رسالة — اتعلّم على {marks} خانة" if marks else "من غير أي رسالة")))
          if not ok and not neu else f"اتحفظ مستند فاضي (Id {sid or ', '.join(neu)})", "يترفض ومفيش مستند")
    if not ok and not neu and not msg and not marks:
        k.evidence.append("ملاحظة: الحفظ من غير بيانات اترفض بس الشاشة ماقالتش للمستخدم أي حاجة")
    return k.done()


# ------------------------------------------------------------------ a new document the same way, with a twist
def _template(cat, code, auto=False, tax=15):
    from engine import biz_cases as B
    if B.PROFILES[code]["kind"] == "voucher":
        return next((c for c in cat["cases"] if c["auto"]), None)
    return _base_case(cat, f"{'AUTO' if auto else 'NONE'} ضريبة {tax} سداد CREDIT")


def double(driver, cat, code, c, data, day):
    from engine import biz_cases as B
    t = _template(cat, code)
    if not t:
        return B.Case(c).done(B.BCAP, "مفيش حالة أساس للشاشة دي")
    fn = B.run_invoice if B.PROFILES[code]["kind"] == "invoice" else B.run_voucher
    k = fn(driver, code, {**t, "id": c["id"]}, data, day, {"double": True})
    k.evidence.insert(0, f"نفس حالة {t['id']} بس الحفظ اتداس مرتين ورا بعض")
    return k


def discount(driver, cat, code, c, data, day):
    from engine import biz_cases as B
    t = _template(cat, code)
    if not t:
        return B.Case(c).done(B.BCAP, "مفيش حالة أساس للشاشة دي")
    k = B.run_invoice(driver, code, {**t, "id": c["id"]}, data, day, {"disc": 10})
    k.evidence.insert(0, f"نفس حالة {t['id']} + خصم 10% على الفاتورة")
    return k


def overstock(driver, cat, code, c, data, day):
    from engine import biz_cases as B
    t = _template(cat, code, auto=True)
    if not t:
        return B.Case(c).done(B.BCAP, "مفيش حالة أساس للشاشة دي")
    B._open(driver, B.PROFILES[code]["path"])
    st = B._js(driver, "const [code, wh] = A; const id = await N.itemId(code); return id ? {id, q: await N.stock(wh, id)} : null;", data.get("A"), data.get("W1"))
    if not st or st.get("q") is None:
        return B.Case(c).done(B.BDATA, "مقدرتش أقرا رصيد الصنف A")
    q = max(math.ceil(float(st["q"])), 0) + 50
    k = B.run_invoice(driver, code, {**t, "id": c["id"]}, data, day, {"qty": q, "reject": True})
    k.evidence.insert(0, f"رصيد الصنف {st['q']} → الفاتورة بكمية {q} والصرف التلقائي مفتوح")
    msg = " ".join(x[2] for x in k.checks)
    if re.search(r"الحد الائتماني|الائتمان", msg):
        return k.done(B.BDATA, "اترفضت بسبب الحد الائتماني للعميل مش بسبب الرصيد — محتاجة عميل حده يسمح بالمبلغ ده")
    return k
