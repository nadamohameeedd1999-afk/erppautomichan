"""
✍️ اختبار القبول مع العميل (UAT) — the client's own people test the system before they receive it, each with a link
(no account on the dashboard): their scenarios step by step, «نجح / فشل / مش منطبق» per step, a note and a screenshot
for a failure; we see the progress live; at the end the client's responsible person signs (name, job, signature drawn
on the screen, decision) and a signed acceptance certificate comes out (approved report design). Failed steps go to
«🎫 دعم المطورين». The idea of Panaya's UAT, fitted to the Kickoff / Sign-off of the implementation team.
"""
import base64
import json
import re
import secrets
from datetime import datetime

from config import paths

RESULTS = ("pass", "fail", "na")
RES_AR = {"pass": "✅ نجح", "fail": "❌ فشل", "na": "➖ مش منطبق", "": "⏳ لسه"}
DECISIONS = {"accept": "✅ مقبول — نستلم النظام", "accept_notes": "⚠️ مقبول بملاحظات — نستلم ويتصلح اللي فشل", "reject": "⛔ مرفوض — لازم يتصلح الأول"}

# ready scenarios: module → [(title, [(step, expected)])]
TEMPLATES = {
    "sales": ("🛒 المبيعات", [
        ("عرض سعر وأمر بيع", [("اعمل عرض سعر لعميل بصنفين", "العرض يتحفظ برقم ويظهر في القايمة"),
                             ("حوّل العرض لأمر بيع", "أمر البيع يتعمل بنفس الأصناف والأسعار")]),
        ("فاتورة بيع آجلة", [("اعمل فاتورة بيع آجلة لعميل بصنفين وخصم", "الإجمالي والخصم والضريبة صح، والفاتورة تتحفظ برقم"),
                             ("افتح الفاتورة تاني", "كل البيانات زي ما اتكتبت"),
                             ("اطبع الفاتورة", "فاتورة ضريبية فيها اسم الشركة والرقم الضريبي وكود QR"),
                             ("شوف رصيد العميل وكمية الصنف في المخزن", "رصيد العميل زاد بقيمة الفاتورة، والكمية نقصت"),
                             ("شوف القيد المحاسبي للفاتورة", "مدين العميل = دائن المبيعات + الضريبة")]),
        ("فاتورة بيع نقدي", [("اعمل فاتورة بيع نقدي", "تتحفظ والخزنة تزيد بقيمتها")]),
        ("مرتجع مبيعات", [("اعمل مرتجع لجزء من فاتورة البيع", "رصيد العميل يقل والكمية ترجع المخزن"),
                          ("اطبع المرتجع", "إشعار دائن بالبيانات الصح")]),
    ]),
    "purchases": ("📥 المشتريات", [
        ("أمر شراء وفاتورة شراء", [("اعمل أمر شراء لمورد", "يتحفظ برقم"),
                                   ("اعمل فاتورة شراء من الأمر", "الكميات والأسعار صح والضريبة محسوبة"),
                                   ("شوف رصيد المورد والمخزن", "رصيد المورد زاد والكمية زادت بالتكلفة الصح")]),
        ("مرتجع مشتريات", [("اعمل مرتجع لجزء من فاتورة الشراء", "رصيد المورد يقل والكمية تقل")]),
    ]),
    "cash": ("💵 الخزنة والبنوك", [
        ("سند قبض", [("اعمل سند قبض من عميل", "يتحفظ ورصيد العميل يقل والخزنة تزيد"),
                     ("اطبع السند", "السند مطبوع بالمبلغ كتابةً ورقمًا")]),
        ("سند دفع", [("اعمل سند دفع لمورد", "يتحفظ ورصيد المورد يقل والخزنة تقل")]),
        ("تحويل بين خزنة وبنك", [("حوّل مبلغ من الخزنة للبنك", "الخزنة تقل والبنك يزيد بنفس المبلغ")]),
    ]),
    "inventory": ("📦 المخازن", [
        ("استلام وصرف", [("اعمل سند استلام مخزني", "الكمية تزيد"), ("اعمل سند صرف مخزني", "الكمية تقل")]),
        ("تحويل بين مخزنين", [("حوّل كمية من مخزن لمخزن", "المخزن الأول يقل والتاني يزيد")]),
        ("الجرد", [("اعمل جرد لصنف بفرق", "تسوية الجرد تتعمل والكمية تبقى زي الجرد")]),
        ("كارت الصنف", [("افتح كارت صنف تحليلي", "كل الحركات اللي اتعملت ظاهرة والرصيد صح")]),
    ]),
    "accounting": ("🧮 الحسابات", [
        ("قيد يدوي", [("اعمل قيد يومية يدوي متزن", "يتحفظ"), ("جرب قيد مش متزن", "النظام يرفضه")]),
        ("التقارير المالية", [("افتح ميزان المراجعة", "المدين = الدائن"), ("افتح الأستاذ العام لحساب", "الحركات والرصيد صح"),
                              ("افتح قائمة الدخل والمركز المالي", "الأرقام منطقية ومتطابقة مع الميزان")]),
    ]),
    "reports": ("📊 التقارير والطباعة", [
        ("تقارير التشغيل", [("افتح تقرير المبيعات بفترة", "الأرقام زي الفواتير اللي اتعملت"),
                            ("افتح كشف حساب عميل ومورد", "الرصيد زي الشاشات"), ("صدّر تقرير Excel و PDF", "الملف بيتفتح والبيانات كاملة")]),
    ]),
    "users": ("👥 المستخدمين والصلاحيات", [
        ("الصلاحيات", [("ادخل بمستخدم صلاحياته محدودة", "يشوف الشاشات المسموحة بس"),
                       ("جرب يعدّل أو يحذف من غير صلاحية", "النظام يمنعه برسالة واضحة")]),
    ]),
    "zatca": ("🇸🇦 الفوترة الإلكترونية (ZATCA)", [
        ("الفاتورة الضريبية", [("اطبع فاتورة ضريبية", "فيها الرقم الضريبي للبايع والمشتري (B2B) وكود QR"),
                               ("امسح كود QR بتطبيق الهيئة", "اسم البايع والرقم الضريبي والتاريخ والإجمالي والضريبة صح"),
                               ("اعمل مرتجع", "إشعار دائن مرتبط بالفاتورة الأصلية")]),
    ]),
}


def _dir():
    d = paths.SETTINGS_DIR / "uat"
    d.mkdir(parents=True, exist_ok=True)
    return d


def files_dir(sid):
    d = paths.DATA_DIR / "uat_files" / re.sub(r"[^a-z0-9]", "", sid)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _f(sid):
    return _dir() / f"{re.sub(r'[^a-z0-9]', '', sid)}.json"


def load(sid):
    try:
        return json.loads(_f(sid).read_text(encoding="utf-8"))
    except Exception:
        return None


def save(d):
    d["updated"] = datetime.now().isoformat(timespec="seconds")
    _f(d["id"]).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def all_sessions():
    out = []
    for f in sorted(_dir().glob("*.json"), key=lambda x: -x.stat().st_mtime):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return out


def by_token(tok):
    if not tok or len(tok) < 16:
        return None
    for d in all_sessions():
        if secrets.compare_digest(d.get("token", ""), tok):
            return d
    return None


def create(title, client, site_url, modules, testers, by="", custom=None):
    sid = datetime.now().strftime("%Y%m%d%H%M%S") + secrets.token_hex(2)
    scen, n = [], 0
    for m in modules:
        if m not in TEMPLATES:
            continue
        mod_name, lst = TEMPLATES[m]
        for title_, steps in lst:
            n += 1
            scen.append({"id": f"s{n}", "module": mod_name, "title": title_, "assignee": "",
                         "steps": [{"id": f"s{n}_{i}", "text": t, "expect": e, "result": "", "note": "", "file": "", "by": "", "at": ""}
                                   for i, (t, e) in enumerate(steps, 1)]})
    for c in custom or []:
        if not str(c.get("title") or "").strip():
            continue
        n += 1
        scen.append({"id": f"s{n}", "module": c.get("module") or "➕ سيناريوهات إضافية", "title": c["title"].strip()[:200], "assignee": "",
                     "steps": [{"id": f"s{n}_{i}", "text": str(s.get("text") or "")[:400], "expect": str(s.get("expect") or "")[:400], "result": "", "note": "",
                                "file": "", "by": "", "at": ""} for i, s in enumerate(c.get("steps") or [], 1) if str(s.get("text") or "").strip()]})
    testers = [t.strip()[:60] for t in testers if t.strip()][:30]
    for i, s in enumerate(scen):                                   # spread the scenarios over the testers
        s["assignee"] = testers[i % len(testers)] if testers else ""
    d = {"id": sid, "token": secrets.token_urlsafe(18), "title": title.strip()[:200] or "اختبار القبول", "client": client.strip()[:200],
         "site_url": site_url.strip()[:300], "created": datetime.now().isoformat(timespec="seconds"), "by": by, "testers": testers,
         "scenarios": scen, "signoff": None, "status": "open"}
    return save(d)


def progress(d):
    steps = [st for s in d["scenarios"] for st in s["steps"]]
    c = {k: sum(1 for st in steps if st["result"] == k) for k in RESULTS}
    done = c["pass"] + c["fail"] + c["na"]
    return {"steps": len(steps), "done": done, **c, "pct": round(100 * done / len(steps)) if steps else 0,
            "scenarios": len(d["scenarios"]), "scen_done": sum(1 for s in d["scenarios"] if s["steps"] and all(st["result"] for st in s["steps"])),
            "scen_fail": sum(1 for s in d["scenarios"] if any(st["result"] == "fail" for st in s["steps"]))}


def public(d, tester=""):
    """what a client tester sees (no token, no internal fields)"""
    sc = [s for s in d["scenarios"] if not tester or s["assignee"] in ("", tester)]
    return {"title": d["title"], "client": d["client"], "site_url": d["site_url"], "testers": d["testers"], "scenarios": sc,
            "signoff": {k: v for k, v in (d.get("signoff") or {}).items() if k != "sig"} or None, "progress": progress(d), "status": d["status"]}


def set_step(d, step_id, result, note, by):
    if d["status"] != "open":
        raise ValueError("الاختبار اتقفل بعد التوقيع")
    if result not in RESULTS + ("",):
        raise ValueError("نتيجة غلط")
    for s in d["scenarios"]:
        for st in s["steps"]:
            if st["id"] == step_id:
                st.update({"result": result, "note": str(note or "")[:1000], "by": str(by or "")[:60], "at": datetime.now().isoformat(timespec="seconds")})
                return save(d)
    raise ValueError("الخطوة مش موجودة")


def attach(d, step_id, filename, data):
    if d["status"] != "open":
        raise ValueError("الاختبار اتقفل بعد التوقيع")
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext not in ("png", "jpg", "jpeg", "webp") or len(data) > 6 * 1024 * 1024:
        raise ValueError("صورة بس (png / jpg) لحد 6 ميجا")
    for s in d["scenarios"]:
        for st in s["steps"]:
            if st["id"] == step_id:
                name = f"{re.sub(r'[^a-z0-9_]', '', step_id)}_{datetime.now():%H%M%S}.{ext}"
                (files_dir(d["id"]) / name).write_bytes(data)
                st["file"] = name
                return save(d)
    raise ValueError("الخطوة مش موجودة")


def sign(d, name, job, decision, notes, sig_dataurl):
    if d["status"] != "open":
        raise ValueError("اتوقّع قبل كده")
    if decision not in DECISIONS or not str(name).strip():
        raise ValueError("اكتب الاسم واختار القرار")
    m = re.match(r"^data:image/png;base64,([A-Za-z0-9+/=]+)$", sig_dataurl or "")
    if not m or len(m.group(1)) > 400000:
        raise ValueError("ارسم التوقيع")
    base64.b64decode(m.group(1))
    p = progress(d)
    if decision == "accept" and p["fail"]:
        raise ValueError(f"فيه {p['fail']} خطوة فشلت — اختار «مقبول بملاحظات» أو «مرفوض»")
    d["signoff"] = {"name": str(name).strip()[:100], "job": str(job or "").strip()[:100], "decision": decision, "notes": str(notes or "")[:2000],
                    "sig": sig_dataurl, "at": datetime.now().isoformat(timespec="seconds"), "progress": p}
    d["status"] = "signed"
    return save(d)


def certificate_html(d, user=""):
    from web import pdf_reports as P
    e = P.e
    p = progress(d)
    so = d.get("signoff") or {}
    dec = DECISIONS.get(so.get("decision"), "⏳ لسه ما اتوقعش")
    col = {"accept": "ok", "accept_notes": "na", "reject": "bad"}.get(so.get("decision"), "na")
    body = [f"<div class='verdict {col}'>{e(dec)} · {p['pass']} نجح · {p['fail']} فشل · {p['na']} مش منطبق · من {p['steps']} خطوة</div>",
            "<h2>السيناريوهات</h2>",
            P.table(["#", "الموديول", "السيناريو", "المختبر", "الخطوات", "نجح", "فشل", "النتيجة"],
                    [[i, s["module"], s["title"], s["assignee"] or "—", len(s["steps"]), sum(1 for x in s["steps"] if x["result"] == "pass"),
                      sum(1 for x in s["steps"] if x["result"] == "fail"),
                      "❌ فيه فشل" if any(x["result"] == "fail" for x in s["steps"]) else ("✅ نجح" if all(x["result"] for x in s["steps"]) else "⏳ ناقص")]
                     for i, s in enumerate(d["scenarios"], 1)], center=(0, 4, 5, 6, 7))]
    fails = [(s, st) for s in d["scenarios"] for st in s["steps"] if st["result"] == "fail"]
    if fails:
        body.append("<h2>الخطوات اللي فشلت</h2>" + P.table(["السيناريو", "الخطوة", "المتوقع", "ملاحظة المختبر", "بواسطة"],
                    [[s["title"], st["text"], st["expect"], st["note"] or "—", st["by"] or "—"] for s, st in fails]))
    if so:
        body.append("<h2>الاعتماد</h2>" + P.table(["الاسم", "الوظيفة", "القرار", "التاريخ", "التوقيع"],
                    [[so["name"], so.get("job") or "—", dec, so["at"].replace("T", " "),
                      P.Raw(f"<img src='{so['sig']}' style='height:60px'>" if so.get("sig") else "—")]], center=(4,)))
        if so.get("notes"):
            body.append(f"<p><b>ملاحظات العميل:</b> {e(so['notes'])}</p>")
    return P.page("شهادة اختبار القبول والاستلام", "User acceptance & handover certificate", user, "".join(body),
                  [("العميل", d["client"] or "—"), ("الاختبار", d["title"]), ("الموقع", d["site_url"] or "—"), ("بدأ", d["created"][:10])])


def support_issues():
    out = []
    for d in all_sessions():
        for s in d["scenarios"]:
            for st in s["steps"]:
                if st["result"] != "fail":
                    continue
                out.append({"id": f"uat_{d['id']}_{st['id']}", "site": re.sub(r"^https?://", "", d.get("site_url") or "").strip("/") or d["client"],
                            "url": d.get("site_url") or "", "source": "✍️ اختبار القبول مع العميل", "screen": s["title"], "severity": "عالية",
                            "title": f"{s['title']}: {st['text']}"[:200],
                            "details": f"المتوقع: {st['expect']}\nملاحظة المختبر ({st['by'] or '—'}): {st['note'] or '—'}",
                            "evidence": f"/uat/file/{d['id']}/{st['file']}" if st.get("file") else "", "doc": "", "steps": st["text"],
                            "found": (st.get("at") or d["created"])[:10]})
    return out
