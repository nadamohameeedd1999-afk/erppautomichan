"""
PDF attachments for support tickets, in the approved design (A4 landscape · RTL · 3-zone header · teal line ·
light-teal strip · teal table header · thin grey row lines · «—» for empty · صفحة X من Y):
  • issue_pdf(it)        — one ERP problem: where, what, steps, evidence, link
  • run_report_pdf(run)  — the result report of a scenario run, rebuilt from what the run saved
"""
import html as H
from datetime import datetime

CSS = """
@page { size: A4 landscape; }
* { box-sizing: border-box; }
body { font-family: 'Microsoft Sans Serif', 'Noto Sans Arabic', Tahoma, Arial, sans-serif; direction: rtl; color: #1C2B2A; font-size: 11px; margin: 0; }
.hd { display: grid; grid-template-columns: 1fr 1.6fr 1fr; align-items: center; gap: 10px; padding-bottom: 8px; border-bottom: 4px solid #0F7C7A; }
.hd .co { font-weight: 700; color: #0A5654; font-size: 15px; }
.hd .ti { text-align: center; } .hd .ti b { display: block; font-size: 20px; } .hd .ti span { color: #0F7C7A; font-size: 13px; }
.hd .us { text-align: left; line-height: 1.7; } .g { color: #6B7B7A; }
.strip { background: #E7F3F2; border: 1px solid #D5E2E1; border-radius: 10px; padding: 7px 12px; margin: 10px 0; }
.strip span { margin-left: 16px; } .strip b { font-weight: 700; }
h2 { color: #0F7C7A; font-size: 14px; margin: 14px 0 6px; }
.verdict { font-size: 18px; font-weight: 700; margin: 8px 0 2px; }
.ok { color: #1E8E3E; } .bad { color: #C62828; } .na { color: #B26A00; }
table { width: 100%; border-collapse: collapse; margin: 4px 0 10px; page-break-inside: auto; }
th { background: #0F7C7A; color: #fff; font-weight: 700; padding: 6px; text-align: center; }
td { padding: 5px 6px; border-bottom: 1px solid #D5E2E1; vertical-align: top; text-align: right; }
td.c { text-align: center; } tr { page-break-inside: avoid; }
.kv td:first-child { width: 18%; color: #6B7B7A; font-weight: 700; }
.pre { white-space: pre-wrap; }
.case { page-break-before: always; }
.small { font-size: 10px; color: #6B7B7A; }
a { color: #0F7C7A; }
"""


def e(x):
    return "—" if x in (None, "") else H.escape(str(x))


def money(x):
    try:
        return f"{float(x):,.2f}"
    except (TypeError, ValueError):
        return e(x)


def _company():
    try:
        from engine.biz_report import company_name
        return company_name()
    except Exception:
        return "أتمتة اختبارات ERP"


def page(title_ar, title_en, user, body, strip=()):
    st = "".join(f"<span><span class='g'>{e(k)}:</span> <b>{e(v)}</b></span>" for k, v in strip)
    return (f"<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'><style>{CSS}</style></head><body>"
            f"<div class='hd'><div class='co'>{e(_company())}</div><div class='ti'><b>{e(title_ar)}</b><span>{e(title_en)}</span></div>"
            f"<div class='us'><span class='g'>المستخدم:</span> <b>{e(user)}</b><br><span class='g'>تاريخ الطباعة:</span> <b>{datetime.now():%Y-%m-%d %H:%M}</b></div></div>"
            + (f"<div class='strip'>{st}</div>" if st else "") + body + "</body></html>")


def table(cols, rows, center=()):
    head = "".join(f"<th>{e(c)}</th>" for c in cols)
    body = "".join("<tr>" + "".join(f"<td class='{'c' if i in center else ''}'>{v if isinstance(v, Raw) else e(v)}</td>" for i, v in enumerate(r)) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


class Raw(str):
    pass


# ------------------------------------------------------------------ one problem
def issue_html(it, user=""):
    url = it.get("url") or ""
    rows = [("المشكلة", it.get("title")), ("الشاشة", it.get("screen")), ("الخطورة", it.get("severity")), ("الموقع", it.get("site")),
            ("لينك الشاشة", Raw(f"<a href='{e(url)}' dir='ltr'>{e(url)}</a>") if url else "—"), ("المصدر", it.get("source")),
            ("التفاصيل", Raw(f"<div class='pre'>{e(it.get('details'))}</div>")), ("خطوات التكرار", Raw(f"<div class='pre'>{e(it.get('steps'))}</div>")),
            ("الدليل", Raw(f"<div class='pre'>{e(it.get('evidence'))}</div>")), ("رقم المستند", it.get("doc")),
            ("مرات الظهور", it.get("count")), ("أول ظهور", it.get("first")), ("آخر ظهور", it.get("last")), ("الحالة", it.get("status"))]
    body = "<table class='kv'><tbody>" + "".join(f"<tr><td>{e(k)}</td><td>{v if isinstance(v, Raw) else e(v)}</td></tr>" for k, v in rows) + "</tbody></table>"
    return page("مشكلة في الـ ERP — لفريق التطوير", "ERP issue — for developers", user, body,
                [("الشاشة", it.get("screen")), ("الخطورة", it.get("severity")), ("الموقع", it.get("site"))])


def issue_pdf(it, user=""):
    from utils.pdf import html_to_pdf
    return html_to_pdf(issue_html(it, user))


# ------------------------------------------------------------------ a scenario run's result report
ST = {"PASS": ("✅", "ناجح", "ok"), "FAIL": ("❌", "فاشل", "bad"), "BLOCKED_DATA": ("⚪", "ناقص بيانات", "na"),
      "BLOCKED_CAPABILITY": ("⚪", "مش مؤتمت لسه", "na"), "NOT_RUN": ("⚪", "لم يُنفذ", "na")}


def run_report_html(detail, run_id="", user=""):
    from engine.biz_report import FRIENDLY
    biz = detail.get("biz") or {}
    cases = biz.get("cases") or {}
    try:
        from engine.biz_cases import NAMES, SYMBOLS, catalog
        cat = catalog()
        then = {c["id"]: c.get("then", "") for s in cat.values() for c in s["cases"]}
    except Exception:
        NAMES, SYMBOLS, then = {}, [], {}
    screens = biz.get("screens") or ([biz.get("screen")] if biz.get("screen") else [])
    cnt = {}
    for v in cases.values():
        cnt[v.get("status")] = cnt.get(v.get("status"), 0) + 1
    ran = [(i, v) for i, v in cases.items() if v.get("status") in ("PASS", "FAIL")]
    fail = cnt.get("FAIL", 0)

    def first_problem(v):
        for n, ok, act, exp in v.get("checks") or []:
            if not ok:
                return f"{FRIENDLY.get(n, n)}: الفعلي {act}" + (f" — المتوقع {exp}" if exp else "")
        return v.get("actual") or "—"
    out = []
    if fail:
        out.append(f"<div class='verdict bad'>❌ النتيجة: فيه مشاكل — فشل {fail} من {len(ran)} حالة اتنفذت</div>")
    elif ran:
        out.append(f"<div class='verdict ok'>✅ النتيجة: ناجح — الـ {len(ran)} حالة اللي اتنفذت كل فحوصاتها مطابقة</div>")
    else:
        out.append("<div class='verdict na'>⚪ النتيجة: ما اتنفذتش أي حالة</div>")
    out.append(f"<div class='small'>ناجح {cnt.get('PASS', 0)} · فاشل {fail} · ناقص بيانات {cnt.get('BLOCKED_DATA', 0)} · مش مؤتمت لسه {cnt.get('BLOCKED_CAPABILITY', 0)}</div>")
    for i, v in cases.items():
        if v.get("status") == "FAIL":
            out.append(f"<div>• <b>{e(i)}</b> — {e(v.get('plain'))}: {e(first_problem(v))}</div>")
    out.append("<h2>ملخص الحالات</h2>")
    out.append(table(["#", "الحالة", "اللي اتجرب", "النتيجة", "السبب / التفاصيل", "رقم المستند"],
                     [[n, i, v.get("plain") or v.get("title"), Raw(f"<span class='{ST.get(v.get('status'), ST['NOT_RUN'])[2]}'>{' '.join(ST.get(v.get('status'), ST['NOT_RUN'])[:2])}</span>"),
                       (f"{len(v.get('checks') or [])} فحص مطابق" if v.get("status") == "PASS" else first_problem(v)), v.get("doc")]
                      for n, (i, v) in enumerate(cases.items(), 1)], center=(0, 1, 3, 5)))
    data = biz.get("data") or {}
    if data:
        nm = data.get("_names") or {}
        out.append("<h2>بيانات الاختبار</h2>")
        out.append(table(["الرمز", "معناه", "القيمة", "الاسم"], [[k, l, data.get(k), nm.get(k)] for k, l in SYMBOLS], center=(0, 2)))
    for i, v in ran:
        ic, st, cl = ST[v["status"]]
        out.append(f"<div class='case'><div class='verdict {cl}'>{ic} {e(i)} — {st}</div><div><b>{e(v.get('plain') or v.get('title'))}</b></div>"
                   f"<div class='small'>المتوقع من ملف المطور: {e(then.get(i))}</div>"
                   + (f"<div>المستند اللي اتعمل: رقم <b>{e(v.get('doc'))}</b> · Id {e(v.get('id'))}</div>" if v.get("doc") or v.get("id") else ""))
        out.append(table(["الفحص", "المتوقع", "الفعلي", "النتيجة"],
                         [[FRIENDLY.get(n, n), exp, act, Raw("<span class='ok'>✓ مطابق</span>" if ok else "<span class='bad'>✗ مختلف</span>")]
                          for n, ok, act, exp in v.get("checks") or []], center=(3,)))
        j = [x for x in v.get("journal") or [] if x.get("d") or x.get("c")]
        if j:
            out.append(f"<h2>القيد اللي الـ ERP عمله (رقم {e(j[0].get('je'))})</h2>")
            out.append(table(["الحساب", "مدين", "دائن"], [[x["acc"], money(x["d"]) if x["d"] else "—", money(x["c"]) if x["c"] else "—"] for x in j]
                             + [[Raw("<b>الإجمالي</b>"), money(sum(x["d"] for x in j)), money(sum(x["c"] for x in j))]], center=(1, 2)))
        ev = [x for x in v.get("evidence") or [] if not x.startswith("القيد ")]
        if ev:
            out.append("<div class='small'>" + "<br>".join("• " + e(x) for x in ev) + "</div>")
        out.append("</div>")
    names = " ← ".join(NAMES.get(s, s) for s in screens)
    return page(f"تقرير نتيجة اختبار — {names}", "Test result report — " + " · ".join(screens), user, "".join(out),
                [("الموقع", (biz.get("url") or "").replace("https://", "")), ("الشاشات", names), ("التشغيلة", run_id), ("الحالات", len(cases))])


def run_report_pdf(detail, run_id="", user=""):
    from utils.pdf import html_to_pdf
    return html_to_pdf(run_report_html(detail, run_id, user))
