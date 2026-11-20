"""The end-of-day report in the approved design (A4 landscape, RTL, teal) — print it to PDF from the browser."""
from datetime import datetime
from html import escape as e


CSS = """
@page { size: A4 landscape; margin: 12mm 12mm 16mm;
        @bottom-center { content: "صفحة " counter(page) " من " counter(pages); font: 10px Tahoma, sans-serif; color: #6b7c7b; } }
body { font-family: "Microsoft Sans Serif", Tahoma, sans-serif; color: #1C2B2A; direction: rtl; margin: 0; font-size: 12px; }
.hd { display: grid; grid-template-columns: 1fr 1.3fr 1fr; align-items: center; border-bottom: 3px solid #0F7C7A; padding-bottom: 8px; }
.co b { color: #0A5654; font-size: 16px; display: block; } .co span { color: #6b7c7b; font-size: 11px; }
.ti { text-align: center; } .ti b { font-size: 20px; display: block; } .ti span { color: #0F7C7A; }
.us { text-align: left; font-size: 11px; } .g { color: #6b7c7b; }
.strip { background: #E7F3F2; border: 1px solid #D5E2E1; border-radius: 8px; padding: 6px 12px; margin: 10px 0; display: flex; gap: 22px; flex-wrap: wrap; }
h2 { color: #0A5654; font-size: 14px; margin: 16px 0 6px; }
table { width: 100%; border-collapse: collapse; margin-bottom: 8px; }
th { background: #0F7C7A; color: #fff; padding: 6px; font-weight: bold; text-align: right; }
td { padding: 6px; border-bottom: 1px solid #D5E2E1; text-align: right; } td.c, th.c { text-align: center; }
.kpi { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; margin: 10px 0; }
.kpi div { border: 1px solid #D5E2E1; border-radius: 8px; padding: 8px; text-align: center; } .kpi b { font-size: 18px; display: block; color: #0A5654; }
.note { color: #B26A00; }
.src { display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; margin: 6px 0 10px; }
.src div { border: 1px solid; border-top-width: 4px; border-radius: 8px; padding: 8px; text-align: center; font-weight: bold; }
.src b { display: block; font-size: 20px; } .src small { display: block; font-weight: normal; color: #6b7c7b; font-size: 10px; margin-top: 3px; } .ft { text-align: center; color: #6b7c7b; font-size: 10px; margin-top: 14px; }
@media screen { body { max-width: 1100px; margin: 20px auto; padding: 0 16px; } .print { position: fixed; bottom: 16px; left: 16px; } }
@media print { .print, .ft { display: none; } }
.tk { border: 1px solid #D5E2E1; border-radius: 8px; margin: 12px 0; break-inside: avoid; }
.tk .th { background: #0F7C7A; color: #fff; padding: 6px 10px; border-radius: 8px 8px 0 0; display: flex; justify-content: space-between; gap: 12px; }
.tk .bd { padding: 8px 10px; display: grid; grid-template-columns: 1.2fr 1fr; gap: 12px; }
.tk dl { margin: 0; display: grid; grid-template-columns: 110px 1fr; gap: 4px 8px; } .tk dt { color: #6b7c7b; } .tk dd { margin: 0; font-weight: bold; word-break: break-word; }
.tk pre { white-space: pre-wrap; background: #E7F3F2; border-radius: 6px; padding: 6px; font: 11px Tahoma, sans-serif; margin: 6px 0 0; max-height: 220px; overflow: auto; }
.tk img { width: 100%; border: 1px solid #D5E2E1; border-radius: 6px; }
"""


def _t(cols, rows, center=()):
    h = "".join(f"<th class='{'c' if i in center else ''}'>{e(str(c))}</th>" for i, c in enumerate(cols))
    b = "".join("<tr>" + "".join(f"<td class='{'c' if i in center else ''}'>{e(str(v if v not in (None, '') else '—'))}</td>" for i, v in enumerate(r)) + "</tr>"
                for r in rows)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>"


def _head(r, title, en):
    return (f"<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'><title>{e(title)}</title><style>{CSS}</style></head><body>"
            f"<button class='print' onclick='print()'>🖨️ طباعة / PDF</button>"
            f"<div class='hd'><div class='co'><b>{e(r['company'])}</b><span>NQ Simulation — NQ ERP</span></div>"
            f"<div class='ti'><b>{e(title)}</b><span>{e(en)}</span></div>"
            f"<div class='us'><span class='g'>المستخدم:</span> <b>المدير</b><br><span class='g'>تاريخ الطباعة:</span> <b>{datetime.now():%Y-%m-%d %H:%M}</b></div></div>")


ACT = {"add": "إضافة", "edit": "تعديل", "print": "طباعة", "delete": "حذف", "open": "إضافة", "review": "مراجعة"}


def _repro(g, r):
    """steps a developer repeats by hand + SQL that shows what the database has — the controller is the page's first path part"""
    import re as _re
    from urllib.parse import urlparse
    path = urlparse(g.get("url") or "").path or ""
    ctl = (path.strip("/").split("/") or [""])[0]
    if not _re.match(r"^[A-Za-z_]\w*$", ctl or ""):
        return ""
    act = ACT.get(g.get("action") or "add", g.get("action") or "")
    steps = [f"1. ادخل بمستخدم بنفس صلاحيات «{'، '.join(g['who'])}»", f"2. افتح {path or '/' + ctl}",
             f"3. اعمل «{act}» بنفس البيانات اللي في الدليل فوق", f"4. المتوقع: الحفظ يتم أو رسالة واضحة — اللي حصل: {g['text'][:160]}"]
    sql = (f"-- حركات الشاشة في نفس اليوم (سجل السيستم)\nSELECT TOP 20 Id, LogDate, UserName, ArAction, SelectedItem, CodeOrDocNo\n"
           f"FROM MyLog WHERE ControllerName = '{ctl}' AND CAST(LogDate AS date) = '{r.get('date', '')}' ORDER BY Id DESC;\n"
           f"-- آخر سجلات الجدول (اسم الجدول متوقع من اسم الشاشة — اتأكد منه)\nSELECT TOP 10 * FROM [{ctl}] ORDER BY Id DESC;")
    return f"<p class='g'>🔁 خطوات التكرار</p><pre>{e(chr(10).join(steps))}</pre><p class='g'>🗄️ SQL للتأكد</p><pre dir='ltr'>{e(sql)}</pre>"


def tickets_html(r, shot_uri=None):
    """one ticket per distinct problem of the system itself (same screen + same message = one ticket, counted):
    what was done, what the system answered, the requests that failed, the page's picture — ready to send to the developers"""
    groups = {}
    for c in r.get("tickets") or []:
        k = (c["screen"], c["type"], c["text"][:90])
        g = groups.setdefault(k, {**c, "n": 0, "who": [], "at": []})
        g["n"] += 1
        g["who"] = sorted(set(g["who"]) | {c["name"]})
        g["at"].append(c["clock"])
        if not g.get("shot") and c.get("shot"):
            g["shot"], g["url"] = c["shot"], c.get("url", "")
    rows = sorted(groups.values(), key=lambda g: -g["n"])
    body = [f"<div class='strip'><span><span class='g'>التاريخ:</span> <b>{e(r['date'])}</b></span><span><span class='g'>الموقع:</span> <b>{e(r.get('site', '') or r['mode'])}</b></span>"
            f"<span><span class='g'>عدد التذاكر:</span> <b>{len(rows)}</b></span><span><span class='g'>مرات الحدوث:</span> <b>{sum(g['n'] for g in rows)}</b></span></div>"]
    if not rows:
        body.append("<p>مفيش مشاكل من السيستم نفسه النهارده 👍</p>")
    for i, g in enumerate(rows, 1):
        ev = str(g.get("evidence") or "")
        img = shot_uri(g["shot"]) if (shot_uri and g.get("shot")) else None
        body.append(
            f"<div class='tk'><div class='th'><b>#{i} · {e(g['screen'])} — {e(g['type'])}</b><span>اتكررت {g['n']} مرة · {e('، '.join(g['at'][:6]))}</span></div>"
            f"<div class='bd'><div><dl>"
            f"<dt>الشاشة</dt><dd>{e(g['screen'])}</dd>"
            f"<dt>العملية</dt><dd>{e(ACT.get(g.get('action') or 'add', g.get('action') or ''))}</dd>"
            f"<dt>رد السيستم</dt><dd>{e(g['text'])}</dd>"
            f"<dt>الرابط</dt><dd>{e(g.get('url') or '—')}</dd>"
            f"<dt>اتقابل مع</dt><dd>{e('، '.join(g['who']))}</dd>"
            f"<dt>المطلوب</dt><dd>يراجعها المطور: تتكرر بنفس الخطوات اللي تحت، والمتوقع إن العملية تتحفظ أو تطلع رسالة واضحة بالسبب</dd>"
            f"</dl><pre>{e(ev[:2500])}</pre>{_repro(g, r)}</div>"
            f"<div>{f'<img src={chr(39)}{img}{chr(39)} alt=صورة الشاشة>' if img else '<p class=g>مفيش صورة للشاشة</p>'}</div></div></div>")
    return _head(r, "تذاكر المطورين — مشاكل السيستم", "NQ ERP — developer tickets") + "".join(body) + "<div class='ft'>صفحة 1 من 1</div></body></html>"


def _pkey(g):
    """the same problem on two days: same source, screen and message, numbers aside (document numbers, amounts, seconds)"""
    import re
    t = re.sub(r"[\d.,:]+", "#", str(g.get("sample") or g.get("text") or ""))[:80]
    return (g.get("source", "erp"), g.get("screen", ""), g.get("type", ""), t)


def compare_html(cur, prev):
    """today against the day before: what got fixed, what is new, what is still there — and the screen round side by side"""
    from simulation.sources import SOURCES
    a = {_pkey(g): g for g in (prev or {}).get("top") or []}
    b = {_pkey(g): g for g in cur.get("top") or []}
    fixed = [a[k] for k in a if k not in b]
    new = [b[k] for k in b if k not in a]
    still = [b[k] for k in b if k in a]
    lab = lambda g: SOURCES.get(g.get("source", "erp"), SOURCES["erp"])["icon"] + " " + SOURCES.get(g.get("source", "erp"), SOURCES["erp"])["name"]
    body = [f"<div class='strip'><span><span class='g'>اليوم:</span> <b>{e(cur['date'])}</b></span>"
            f"<span><span class='g'>قدام:</span> <b>{e((prev or {}).get('date', '—'))}</b></span>"
            f"<span><span class='g'>✅ اتصلح:</span> <b>{len(fixed)}</b></span><span><span class='g'>🆕 جديد:</span> <b>{len(new)}</b></span>"
            f"<span><span class='g'>⏳ لسه:</span> <b>{len(still)}</b></span></div>"]
    if not prev:
        body.append("<p>ده أول يوم حقيقي متسجل — المقارنة بتبدأ من اليوم الجاي.</p>")
    for title, rows in (("✅ اتصلح من اليوم اللي فات", fixed), ("🆕 مشاكل جديدة النهارده", new), ("⏳ لسه موجودة", still)):
        body.append(f"<h2>{title} ({len(rows)})</h2>" + (_t(["المصدر", "الشاشة", "النوع", "المثال", "المرات"],
                    [[lab(g), g["screen"], g["type"], g["sample"], g["n"]] for g in rows], center=(4,)) if rows else "<p class='g'>—</p>"))
    pr = {x["screen"]: x for x in (prev or {}).get("round") or []}
    if cur.get("round"):
        ok = lambda v: str(v).startswith("✅")
        rows = []
        for x in cur["round"]:
            y = pr.get(x["screen"]) or {}
            move = "".join("⬆️" if ok(x[k]) and y and not ok(y.get(k, "")) else "⬇️" if y and ok(y.get(k, "")) and not ok(x[k]) else ""
                           for k in ("add", "edit", "print", "delete"))
            rows.append([x["screen"]] + [f"{str(y.get(k, '—'))[:40]} ← {str(x[k])[:40]}" if y else str(x[k])[:60] for k in ("add", "edit", "print", "delete")] + [move or "="])
        body.append("<h2>جولة الشاشات: اليوم اللي فات ← النهارده</h2>" + _t(["الشاشة", "إضافة", "تعديل", "طباعة", "حذف", "الاتجاه"], rows, center=(5,)))
    return _head(cur, "مقارنة الأيام", "Day over day — fixed · new · still open") + "".join(body) + "<div class='ft'>صفحة 1 من 1</div></body></html>"


def training_html(d, has_shot=False):
    """🎓 one employee's day as a lesson: each step in order (time, what, how it went), the documents he made, his live screen"""
    rows = [[x.get("clock", ""), ("✅ " if x.get("ok") is True else "❌ " if x.get("ok") is False else "") + str(x.get("text", ""))] for x in d["log"]]
    docs = [[x.get("screen", ""), x.get("no", ""), x.get("party", "") or "—", x.get("total", "") or "—"] for x in d["docs"]]
    body = [f"<div class='strip'><span><span class='g'>الموظف:</span> <b>{e(d['name'])}</b></span><span><span class='g'>الوظيفة:</span> <b>{e(d['job'] or '—')}</b></span>"
            f"<span><span class='g'>التاريخ:</span> <b>{e(d['date'])}</b></span><span><span class='g'>الخطوات:</span> <b>{len(rows)}</b></span></div>",
            "<p>اتفرج على الخطوات بالترتيب واعملها على نفس الشاشات في السيستم بتاعك — العلامة ✅ يعني الخطوة نجحت، ❌ يعني وقفت وليه.</p>"]
    if has_shot:
        body.append(f"<h2>🖥️ آخر شاشة اشتغل عليها</h2><img src='/shot/{e(d.get('eid', ''))}.png' style='max-width:100%;border:1px solid #D5E2E1;border-radius:8px' onerror=\"this.remove()\">")
    if docs:
        body.append("<h2>المستندات اللي عملها</h2>" + _t(["الشاشة", "الرقم", "العميل / المورد", "الإجمالي"], docs, center=(1, 3)))
    body.append("<h2>الخطوات</h2>" + (_t(["الوقت", "الخطوة"], rows, center=(0,)) if rows else "<p class='g'>لسه ما اشتغلش النهارده</p>"))
    return _head(d, f"وضع التدريب — {d['name']}", "Training mode — step by step") + "".join(body) + "<div class='ft'>صفحة 1 من 1</div></body></html>"


def report_html(r):
    kpi = [("الصفقات", r["deals"]), ("اتقفلت", r["closed"]), ("متعطلة", r["stuck"]), ("المبيعات", f"{r['sales']:,}"),
           ("متوسط الدورة (دقيقة)", r["avg_cycle"] or "—"), ("🏢 مشاكل السيستم", r.get("erp_problems", r["complaints"]))]
    body = [f"<div class='kpi'>{''.join(f'<div><b>{e(str(v))}</b>{e(k)}</div>' for k, v in kpi)}</div>"]
    if r.get("tickets"):
        body.append(f"<p>🎫 <a href='/tickets'>تذاكر المطورين ({len(r['tickets'])} مشكلة من السيستم بصورها وأدلتها)</a></p>")
    if r.get("mode") == "محاكاة":
        body.append("<p class='note'>⚠️ وضع المحاكاة: سلوك السيستم تقريبي من ملف الإعدادات — المشاكل هنا للتجربة مش نتايج حقيقية من الموقع.</p>")
    from simulation.sources import SOURCES, ORDER
    bs = r.get("by_source") or []
    if bs:                                                     # where the problems came from — only 🏢 goes to the developers
        body.append("<h2>المشاكل حسب مصدرها</h2><div class='src'>" + "".join(
            f"<div style='border-color:{x['color']}'><b style='color:{x['color']}'>{x['n']}</b>{e(x['icon'])} {e(x['name'])}<small>{e(x['hint'])}</small></div>"
            for x in bs) + "</div>")
    top = r.get("top") or []
    for k in ORDER:
        rows = [g for g in top if g.get("source", "erp") == k]
        if not rows:
            continue
        sd = SOURCES[k]
        body.append(f"<h2 style='color:{sd['color']}'>{e(sd['icon'])} {e(sd['name'])} <span class='g' style='font-size:11px'>— {e(sd['hint'])}</span></h2>"
                    + _t(["#", "النوع", "الشاشة", "عدد المرات", "مين اتقابل معاه", "مثال", "الدليل"],
                         [[i, g["type"], g["screen"], g["n"], "، ".join(g["who"]), g["sample"], g["evidence"]] for i, g in enumerate(rows, 1)], center=(0, 3)))
    if not top:
        body.append("<h2>المشاكل</h2><p>مفيش مشاكل النهارده 👍</p>")
    gd = r.get("guards") or []
    if gd:                                                     # 🕵️ / 🧾 the watchdogs: controls that must say no
        body.append("<h2>🕵️ الرقابة: المختلس والمراجع</h2>" + _t(["الموظف", "الاختبار", "النتيجة", "التفاصيل"],
                    [[g["who"], g["what"], "✅ الرقابة شغالة" if g["kind"] == "ok" else "❌ عدّت" if g["kind"] == "wrong" else g["kind"], g["note"]] for g in gd]))
    bs = r.get("burst")
    if bs:                                                     # ⚡ everyone at once
        body.append(f"<h2>⚡ اختبار الضغط — {bs['n']} موظف فتحوا في نفس اللحظة · متوسط {bs['avg'] / 1000:.1f} ث · أقصى {bs['max'] / 1000:.1f} ث</h2>" +
                    _t(["الشاشة", "الموظف", "تحت الضغط (ث)", "العادي (ث)", "النتيجة"],
                       [[b["screen"], b["who"], f"{b['ms'] / 1000:.1f}", f"{b['normal'] / 1000:.1f}" if b["normal"] else "—", b["kind"]] for b in bs["rows"]], center=(2, 3)))
    fr = r.get("frustration") or []
    if fr:                                                     # 😣 usability
        body.append("<h2>😣 مؤشر الضيق — الشاشات اللي تعبت الموظفين</h2>" + _t(["الشاشة", "المؤشر من 100", "مرات الشغل", "فشلت", "متوسط الوقت (ث)", "شكاوى"],
                    [[x["screen"], x["score"], x["n"], x["fails"], f"{x['avg'] / 1000:.1f}", x["complaints"]] for x in fr], center=(1, 2, 3, 4, 5)))
    ln = r.get("learning") or []
    if ln:                                                     # 🎓 the team learns
        body.append("<h2>🎓 الموظفين بيتعلموا — الخبرة بعد النهارده</h2>" + _t(["الموظف", "أيام الشغل", "الخبرة قبل", "الخبرة بعد", "نجح", "فشل"],
                    [[x["name"], x["days"], f"{x['before']:.0%}", f"{x['after']:.0%}", x["done"], x["failed"]] for x in ln], center=(1, 2, 3, 4, 5)))
    ns = r.get("new_screens") or []
    if ns:
        body.append(f"<h2>🆕 شاشات جديدة في المنيو من آخر مرة ({len(ns)})</h2><p>{e('، '.join(ns[:40]))}</p>")
    rg = r.get("regressions")
    if rg:                                                     # 🧬 memory across days
        body.append(f"<h2>🧬 ذاكرة العيوب — مفتوحة {rg['open']} · اتصلحت {rg['fixed']}</h2>" + _t(["الشاشة", "المشكلة", "أول مرة", "آخر مرة", "عدد الأيام", "الحالة"],
                    [[m["screen"], m["text"][:120], m.get("first", "—"), m.get("last", "—"), len(m.get("days", [])), "⏳ مفتوحة" if m.get("status") == "open" else f"✅ اتصلحت {m.get('fixed', '')}"]
                     for m in rg["items"]], center=(2, 3, 4)))
    rd = r.get("ready")
    if rd:                                                     # before the work: the main add forms' required lists
        nm = rd.get("names") or {}
        rows = [[nm.get(k, k), "، ".join(v)] for k, v in (rd.get("empty") or {}).items()]
        rows += [[nm.get(k, k), "ما اتفتحتش: " + str(v)[:120]] for k, v in (rd.get("bad") or {}).items()]
        body.append(f"<h2>جاهزية الموقع قبل الشغل — اتفتح {rd.get('seen', 0)} فورم إضافة</h2>" +
                    (_t(["الشاشة", "القوايم الإجبارية الفاضية / الملاحظة"], rows) if rows else "<p>كل القوايم الإجبارية فيها اختيارات 👍</p>"))
    if r.get("round"):                                         # the screen round: four scenarios on each main screen
        body.append("<h2>جولة الشاشات الرئيسية — إضافة · تعديل · طباعة · حذف</h2>" + _t(["الشاشة", "الموظف", "إضافة", "تعديل", "طباعة", "حذف"],
                    [[x["screen"], x["who"], x["add"], x["edit"], x["print"], x["delete"]] for x in r["round"]]))
    body.append("<h2>الموظفين</h2>" + _t(["الموظف", "الوظيفة", "مهام اتعملت", "اتعطل", "شكاوى", "الانشغال %", "متبقي"],
                [[x["name"], x["job"], x["done"], x["failed"], x["complaints"], x["load"], x["queue"]] for x in r["employees"]], center=(2, 3, 4, 5, 6)))
    body.append("<h2>أبطأ الشاشات</h2>" + _t(["الشاشة", "المتوسط (ث)", "الأقصى (ث)", "مرات الاستخدام"],
                [[s["screen"], f"{s['avg'] / 1000:.1f}", f"{s['max'] / 1000:.1f}", s["n"]] for s in r["speed"]], center=(1, 2, 3)))
    if r.get("stuck_deals"):
        body.append("<h2>الصفقات المتعطلة</h2>" + _t(["الصفقة", "العميل", "وقفت فين"], [[d["id"], d["customer"], d["where"]] for d in r["stuck_deals"]]))
    return (f"<!doctype html><html lang='ar' dir='rtl'><head><meta charset='utf-8'><title>تقرير يوم الشركة</title><style>{CSS}</style></head><body>"
            f"<button class='print' onclick='print()'>🖨️ طباعة / PDF</button>"
            f"<div class='hd'><div class='co'><b>{e(r['company'])}</b><span>NQ Simulation — NQ ERP</span></div>"
            f"<div class='ti'><b>تقرير يوم الشركة</b><span>Virtual company — daily report</span></div>"
            f"<div class='us'><span class='g'>المستخدم:</span> <b>المدير</b><br><span class='g'>تاريخ الطباعة:</span> <b>{datetime.now():%Y-%m-%d %H:%M}</b></div></div>"
            f"<div class='strip'><span><span class='g'>التاريخ:</span> <b>{e(r['date'])}</b></span><span><span class='g'>الوضع:</span> <b>{e(r['mode'])}</b></span>"
            f"<span><span class='g'>أكتر موظف اتعطل:</span> <b>{e(r['most_blocked'])}</b></span></div>"
            + "".join(body) + "<div class='ft'>صفحة 1 من 1</div></body></html>")
