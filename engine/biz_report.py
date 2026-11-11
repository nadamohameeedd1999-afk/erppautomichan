"""
📄 تقرير نتيجة الاختبار — the readable result of a developer-scenario run, for the team or the client:
verdict first, then a table of the cases (what was tried · result · why), the test data used, notes for the developers,
and one page per executed case: every check with EXPECTED vs ACTUAL, and the journal entry the ERP made.
The developer's case file (with Status / Actual written in) stays available as a second file for the developers.
"""
from datetime import datetime

from engine.docx_design import AMBER, GREEN, GREY, RED, TEAL, Report, money

ST = {"PASS": ("ناجح", "✅"), "FAIL": ("فاشل", "❌"), "BLOCKED_DATA": ("ناقص بيانات", "⚪"), "BLOCKED_CAPABILITY": ("مش مؤتمت لسه", "⚪"), "NOT_RUN": ("لم يُنفذ", "⚪")}
FRIENDLY = {
    "قبل الحفظ": "الحسبة على الشاشة قبل الحفظ (صافي / ضريبة / إجمالي)",
    "الحفظ": "الحفظ",
    "مستند واحد بس": "اتعمل مستند واحد بس (مفيش تكرار)",
    "سند واحد بس": "اتعمل سند واحد بس (مفيش تكرار)",
    "السند المخزني التابع": "سند المخزن اللي بيتعمل تلقائي",
    "مفيش سند مخزني جديد": "مفيش سند مخزن اتعمل (التوليد مقفول)",
    "إعادة الفتح": "إعادة فتح المستند (الأصناف والطرف والمخزن)",
    "الإجماليات بعد الفتح": "الإجماليات بعد إعادة الفتح",
    "المدفوع": "المدفوع نقدًا",
    "كارت الصنف A في W1": "حركة رصيد الصنف في المخزن",
    "القيد متزن": "القيد متزن",
    "قيمة القيد": "إجمالي القيد",
    "ضريبة القيد": "ضريبة القيمة المضافة في القيد",
    "طرف الخزينة": "مبلغ الخزينة في القيد",
    "استدعاء الأصل": "استدعاء الفاتورة الأصلية",
    "المتاح للإرجاع من الأصل": "الكمية المتاحة للإرجاع بعد المرتجع",
    "دين العميل": "رصيد العميل بعد السند",
}


def build(cat, out, data, url, user, path, symbols, names):
    return build_many([(cat, out)], data, url, user, path, symbols, names)


def build_many(groups, data, url, user, path, symbols, names):
    """groups = [(screen catalog, {case id: Case})] run one after the other → one report"""
    from engine.biz_cases import BCAP, BDATA, FAIL, PASS
    allk = [k for _, out in groups for k in out.values()]
    ran = [k for k in allk if k.status in (PASS, FAIL)]
    cnt = {s: sum(1 for k in allk if k.status == s) for s in (PASS, FAIL, BDATA, BCAP)}
    multi = len(groups) > 1
    title = groups[0][0]["name"] if not multi else f"{len(groups)} شاشات"
    r = Report(company_name(), f"تقرير نتيجة اختبار — {title}", "Test result report — " + " · ".join(c["code"] for c, _ in groups), user)
    host = str(url).replace("https://", "").replace("http://", "").strip("/")
    r.strip([("الموقع", host), ("الشاشات", " ← ".join(c["name"] for c, _ in groups)), ("وقت التشغيل", datetime.now().strftime("%Y-%m-%d %H:%M")),
             ("الحالات", str(len(allk)))])

    # ---- the verdict
    if cnt[FAIL]:
        r.para(f"❌ النتيجة: فيه مشاكل — فشل {cnt[FAIL]} من {len(ran)} حالة اتنفذت", 15, True, RED)
    elif ran:
        r.para(f"✅ النتيجة: ناجح — الـ {len(ran)} حالة اللي اتنفذت كل فحوصاتها مطابقة", 15, True, GREEN)
    else:
        r.para("⚪ النتيجة: ما اتنفذتش أي حالة", 15, True, AMBER)
    r.para(f"ناجح {cnt[PASS]}   ·   فاشل {cnt[FAIL]}   ·   ناقص بيانات {cnt[BDATA]}   ·   مش مؤتمت لسه {cnt[BCAP]}", 10, False, GREY)
    for k in allk:
        if k.status == FAIL:
            r.para(f"• {k.c['id']} — {k.plain}: {first_problem(k)}", 9.5, False)
    r.para("كل حالة بتتعمل على الموقع فعلًا: الأداة بتدخل المستند وتحفظه، وبعدين تفتحه تاني وتراجع الإجماليات والمدفوع وحركة المخزن والقيد المحاسبي اللي الـ ERP عمله، "
           "وتقارن كل رقم بالمتوقع المكتوب في ملف المطور.", 9, False, GREY, space_before=4)

    color = {"✅": GREEN, "❌": RED}
    if multi:
        r.para("النتيجة لكل شاشة", 12, True, TEAL, space_before=8)
        srow = []
        for i, (cat, out) in enumerate(groups, 1):
            ks = list(out.values())
            p_, f_ = sum(1 for k in ks if k.status == PASS), sum(1 for k in ks if k.status == FAIL)
            b_ = len(ks) - p_ - f_
            srow.append([i, f"{cat['icon']} {cat['name']}", len(ks), p_, f_, b_, "❌ فيه مشاكل" if f_ else ("✅ ناجح" if p_ else "⚪ ما اتنفذتش")])
        r.table([("#", 3), ("الشاشة", 26), ("الحالات", 8), ("ناجح", 8), ("فاشل", 8), ("ما اتنفذتش", 10), ("النتيجة", 14)], srow,
                center=(0, 2, 3, 4, 5, 6), colors=lambda ri, ci, v: color.get(v[:1]) if ci == 6 else None)

    # ---- the cases at a glance (per screen)
    for cat, out in groups:
        r.para(("ملخص الحالات — " + cat["name"]) if multi else "ملخص الحالات", 12, True, TEAL, space_before=8)
        rows = [[i, k.c["id"], k.plain or k.c["title"], f"{ST[k.status][1]} {ST[k.status][0]}", first_problem(k) if k.status != PASS else f"{len(k.checks)} فحص مطابق",
                 k.doc_no or "—"] for i, k in enumerate(out.values(), 1)]
        r.table([("#", 3), ("الحالة", 7), ("اللي اتجرب", 34), ("النتيجة", 9), ("السبب / التفاصيل", 32), ("رقم المستند", 10)], rows,
                center=(0, 1, 3, 5), colors=lambda ri, ci, v: color.get(v[:1]) if ci == 3 else None)

    # ---- the test data
    r.para("بيانات الاختبار (ملف بيانات الموقع)", 12, True, TEAL, space_before=6)
    nm = (data or {}).get("_names") or {}
    r.table([("الرمز", 6), ("معناه", 22), ("القيمة في الـ ERP", 12), ("الاسم", 40)],
            [[k, lbl, (data or {}).get(k) or "—", nm.get(k) or "—"] for k, lbl in symbols], center=(0, 2))

    # ---- notes for the developers (seen while running, even on passed cases)
    notes = [[k.c["id"], e] for k in allk for e in k.evidence if e.startswith(("ملاحظة", "تنبيه", "اتمسح"))]
    if notes:
        r.para("ملاحظات للمطور اتلاحظت أثناء التنفيذ", 12, True, TEAL, space_before=6)
        r.table([("الحالة", 8), ("الملاحظة", 70)], notes, center=(0,))

    # ---- one page per executed case
    for k in ran:
        r.page_break()
        st, ic = ST[k.status]
        r.para(f"{ic} {k.c['id']} — {st}", 14, True, GREEN if k.status == PASS else RED)
        r.para(k.plain or k.c["title"], 11, True)
        r.para("المتوقع من ملف المطور: " + (k.c.get("then") or "—"), 9, False, GREY)
        if k.doc_no or k.doc_id:
            r.para(f"المستند اللي اتعمل: رقم {k.doc_no or '—'} · Id {k.doc_id or '—'}", 9, True)
        crow = [[FRIENDLY.get(n, n), exp or "—", act or "—", "✓ مطابق" if ok else "✗ مختلف"] for n, ok, act, exp in k.checks]
        r.table([("الفحص", 26), ("المتوقع", 22), ("الفعلي", 30), ("النتيجة", 9)], crow, center=(3,),
                colors=lambda ri, ci, v: (GREEN if v.startswith("✓") else RED) if ci == 3 else None)
        if k.journal:
            r.para(f"القيد اللي الـ ERP عمله (رقم {k.journal[0].get('je', '—')})", 10, True, TEAL)
            jl = [[x["acc"], money(x["d"]) if x["d"] else "—", money(x["c"]) if x["c"] else "—"] for x in k.journal if x["d"] or x["c"]]
            jl.append(["الإجمالي", money(sum(x["d"] for x in k.journal)), money(sum(x["c"] for x in k.journal))])
            r.table([("الحساب", 50), ("مدين", 14), ("دائن", 14)], jl, center=(1, 2))
        other = [e for e in k.evidence if not e.startswith("القيد ")]
        if other:
            r.para("تفاصيل التنفيذ", 10, True, TEAL)
            for e in other:
                r.para("• " + e, 8.5, False, GREY)

    # ---- what wasn't run
    left = [k for k in allk if k.status in (BDATA, BCAP)]
    if left:
        r.page_break()
        r.para("الحالات اللي ما اتنفذتش وليه", 12, True, TEAL)
        r.table([("الحالة", 8), ("العنوان", 30), ("السبب", 40)], [[k.c["id"], k.c["title"], k.actual] for k in left], center=(0,))
    return r.save(path)


def first_problem(k):
    for n, ok, act, exp in k.checks:
        if not ok:
            return f"{FRIENDLY.get(n, n)}: الفعلي {act}" + (f" — المتوقع {exp}" if exp else "")
    return k.actual or "—"


def company_name():
    try:
        from web import settings_helper
        c = settings_helper.load_site_config()
        return c.get("company_name") or c.get("site_name_ar") or "أتمتة اختبارات ERP"
    except Exception:
        return "أتمتة اختبارات ERP"
