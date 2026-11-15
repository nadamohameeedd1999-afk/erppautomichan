"""
🚀 اختبار الاستلام (Go-Live) — one button that runs every kind of test on a client's site before it is handed over,
then ONE report for the developers: a Go / No-Go verdict per area, every real problem with its evidence and where it
is in the code, and what still needs a person to confirm.

Stages (each one is a normal saved check, queued first in line on the chosen site):
  1. 🩺 الشاشات        every menu screen opens (500 / 404 / error page / back to login) + its name + its link + the real speed
  2. ⚖️ الحسابات        trial balance balanced, parents = sum of children
  3. 🔬 الأشعة          menu links to the developer's machine / another site, English & code values on Arabic screens,
                        old libraries with known holes, security headers, slow network
  4. 📊 التقارير        every /Report/ in the menu is built (defaults, then the first value of the empty lists)
  5. 🔌 الـ API          the screens' data requests: 200, JSON, speed
  6. 🏋️ الحمل           N users at the same moment (each with its own session) on the slowest screens and requests
  7. 📚 الدورات         the developer's case files (sales / purchases / receipts …) — test documents, only if chosen

Then collect() reads what each stage saved for that site and cross-references it with the 🧬 code twin (the same
product's source code): a broken screen gets its controller, its broken calls and its broken procedures.

Evidence rule: a problem is «مؤكدة في الموقع» only when the site itself answered with it (HTTP 5xx / 404, an ERP error
page, a report that failed on the server, a link that goes outside). Timeouts, a report that needs a filter, the tool
stopping … are «محتاجة تأكيد» — they go to a separate list so the developers never chase the tool's own problems.
"""
import json
import re
from datetime import datetime
from pathlib import Path

from config import paths

STEPS = [
    ("health", "golive_screens", "🩺", "الشاشات — الفتح والأسماء واللينكات والسرعة"),
    ("books", "golive_books", "⚖️", "الحسابات — ميزان المراجعة"),
    ("xray", "golive_xray", "🔬", "أشعة النظام — المنيو والمكتبات والأمان واللغة"),
    ("repcmp", "golive_reports", "📊", "كل التقارير — بناء كل تقرير"),
    ("api", "golive_api", "🔌", "طلبات البيانات (API)"),
    ("load", "golive_load", "🏋️", "اختبار الحمل"),
]
AREAS = ["الشاشات", "الأسماء واللينكات", "التقارير", "السرعة", "الحمل", "الحسابات", "الأمان والمكتبات", "الكود", "الشاشات الرئيسية — اختبار شامل", "الدورات المستندية"]

# 🧪 the main document screens (found by name in the system's screens) → the automatic test with EVERY scenario
KEY_SCREENS = [
    ("فاتورة البيع", r"فاتور[ةه] (?:ال)?(?:بيع|مبيعات)|فواتير (?:ال)?(?:بيع|مبيعات)"),
    ("مرتجع المبيعات", r"مرتجع(?:ات)? (?:ال)?(?:بيع|مبيعات)"),
    ("فاتورة الشراء", r"فاتور[ةه] (?:ال)?(?:شراء|مشتريات)|فواتير (?:ال)?(?:شراء|مشتريات)"),
    ("مرتجع المشتريات", r"مرتجع(?:ات)? (?:ال)?(?:شراء|مشتريات)"),
    ("سند القبض", r"سند(?:ات)? (?:ال)?قبض"),
    ("سند الدفع", r"سند(?:ات)? (?:ال)?(?:دفع|صرف)(?! مخزن)"),
    ("القيد اليومي", r"قيود? (?:ال)?(?:يومي[ةه]|يدوي[ةه]?)|القيود اليومي[ةه]"),
    ("عرض السعر", r"عروض (?:ال)?أسعار|عرض (?:ال)?سعر"),
    ("أمر البيع", r"أوامر (?:ال)?بيع|أمر (?:ال)?بيع|اوامر (?:ال)?بيع|امر (?:ال)?بيع"),
    ("أمر الشراء", r"أوامر (?:ال)?شراء|أمر (?:ال)?شراء|اوامر (?:ال)?شراء|امر (?:ال)?شراء"),
    ("التحويل المخزني", r"تحويل(?:ات)? (?:مخزني|بين (?:ال)?مخازن)"),
    ("صرف مخزن", r"(?:سند|إذن|اذن) صرف مخز"),
    ("استلام مخزن", r"(?:سند|إذن|اذن) (?:استلام|إضافة|اضافة) مخز"),
]
SKIP_NAME = re.compile(r"تقرير|كشف|أرصد|ارصد|إعداد|اعداد|متعدد|استيراد|تحليل|طباعة|اعتماد|ترحيل", re.I)


def key_screens():
    try:
        from engine.auto_test import all_screens
        scr = all_screens()
    except Exception:
        return []
    out, used = [], set()
    for label, pat in KEY_SCREENS:
        rx = re.compile(pat)
        m = next((s for s in scr if s["key"] not in used and rx.search(s["name"] or "") and not SKIP_NAME.search(s["name"] or "")), None)
        if m:
            used.add(m["key"])
            out.append({"key": m["key"], "name": m["name"], "label": label, "builder": m.get("builder")})
    return out


def fire_key(screen):
    import hashlib
    k = re.sub(r"[^a-z0-9_]", "_", str(screen).lower()).strip("_")[:50] or "s"
    return f"golive_main_{k}_{hashlib.sha1(str(screen).encode()).hexdigest()[:4]}"


def fire_config(screen, name):
    from engine.checks import FIRE_WAYS
    return {"key": fire_key(screen), "type": "auto", "name_ar": f"🧪 شامل: {name}", "screen": screen, "ways": FIRE_WAYS,
            "scenarios": ["first"], "fields_mode": "all"}


SITE_BUG = re.compile(r"XSS|السيرفر وقع|رسالة تقنية|اتحفظ!|اتحفظ بأرقام|مكرر|كسر الجافاسكريبت|رقم المستند اتكرر|الترقيم راجع")
SEV = {"عالية": 0, "متوسطة": 1, "منخفضة": 2, "للعلم": 3}


def _state(name):
    return paths.STATE_DIR / name


def _read(f):
    try:
        return json.loads(Path(f).read_text(encoding="utf-8"))
    except Exception:
        return None


def _skey(url):
    return re.sub(r"[^a-z0-9]", "_", re.sub(r"^https?://", "", str(url or "")).strip("/").lower())


def plan_file(url):
    return _state(f"golive_{_skey(url)}.json")


def load_plan(url):
    return _read(plan_file(url)) or {}


def save_plan(url, d):
    f = plan_file(url)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def configs(opts):
    """the saved checks the run uses (their own keys — the daily checks keep their settings)"""
    users = max(1, min(20, int(opts.get("users") or 5)))
    return {
        "golive_screens": {"key": "golive_screens", "type": "health", "name_ar": "🚀 استلام: الشاشات والسرعة", "reports": True, "forms": True,
                           "fail_on": "any", "workers": 2, "deep_speed": int(opts.get("deep_speed") or 40), "slow_seconds": 0},
        "golive_books": {"key": "golive_books", "type": "books", "name_ar": "🚀 استلام: الحسابات"},
        "golive_xray": {"key": "golive_xray", "type": "xray", "name_ar": "🚀 استلام: أشعة النظام", "pages": int(opts.get("xray_pages") or 150),
                        "shots": True, "shots_n": 12, "slow": True},
        "golive_reports": {"key": "golive_reports", "type": "repcmp", "name_ar": "🚀 استلام: كل التقارير", "catalog": True},
        "golive_api": {"key": "golive_api", "type": "api", "name_ar": "🚀 استلام: طلبات البيانات", "from_health": True, "limit": 150, "max_ms": 4000},
        "golive_load": {"key": "golive_load", "type": "load", "name_ar": f"🚀 استلام: الحمل — {users} مستخدمين", "users": users,
                        "rounds": int(opts.get("rounds") or 3), "screens": 6, "apis": 4, "p95_ms": float(opts.get("p95_ms") or 8000)},
    }


# ------------------------------------------------------------------ reading what each stage saved
def _health_for(url):
    best = None
    for f in paths.STATE_DIR.glob("health_*.json"):
        d = _read(f)
        if d and (d.get("base_url") or "").rstrip("/").lower() == url.rstrip("/").lower():
            if not best or (d.get("at") or "") > (best.get("at") or ""):
                best = {**d, "_key": f.stem[len("health_"):]}
    return best


def _runs(plan):
    from web import data_helper
    out = []
    for step in plan.get("tasks") or []:
        s = _read(data_helper.RESULTS_DIR / f"summary_{step['task_id']}.json") if hasattr(data_helper, "RESULTS_DIR") else None
        st = "waiting"
        msg = ""
        if s:
            from web import insights
            st = "pass" if insights.run_passed(s) else "fail"
            msg = insights.first_failure_message(s) or ""
        out.append({**step, "status": st, "msg": msg[:600]})
    return out


def _f(area, sev, title, where="", evidence="", fix="", confirmed=True, screen="", code=None, n=1):
    return {"area": area, "sev": sev, "title": title, "where": where, "evidence": evidence, "fix": fix, "confirmed": confirmed,
            "screen": screen, "code": code or [], "n": n}


def _ctrl(path):
    """/Sales/Index?x=1 or https://host/Sales/Index → «sales» ('' when there is no controller part)"""
    p = re.sub(r"^https?://[^/]+", "", str(path or "")).split("?")[0].split("#")[0]
    seg = [x for x in p.strip("/").split("/") if x]
    return seg[0].lower() if seg else ""


def _twin_for(path, twin):
    """the code chain of a screen path (/Sales/Index → controller «sales»)"""
    if not twin:
        return None
    seg = [x for x in re.sub(r"^https?://[^/]+", "", str(path or "")).split("?")[0].strip("/").split("/") if x]
    if not seg:
        return None
    sc = (twin.get("screens") or {}).get(seg[0].lower())
    if not sc:
        return {"missing": True, "controller": seg[0]}
    act = (seg[1] if len(seg) > 1 else "index").lower()
    return {"controller": sc["name"], "file": sc.get("file"), "action": act, "has_action": act in [a.lower() for a in sc.get("actions") or []] or act == "index",
            "bad_calls": [c["url"] for c in sc.get("calls") or [] if not c.get("ok")][:8], "broken_procs": sc.get("broken_procs") or [],
            "procs": (sc.get("procs") or [])[:8], "issues": sc.get("issues") or []}


def _code_lines(tw):
    if not tw:
        return []
    if tw.get("missing"):
        return [f"مفيش Controller اسمه {tw['controller']}Controller في الكود"]
    out = [f"{tw['controller']}Controller → {tw['action']}" + ("" if tw["has_action"] else " (الـ action ده مش موجود في الكود)") + (f" · {tw['file']}" if tw.get("file") else "")]
    if tw["broken_procs"]:
        out.append("إجراءات مكسورة: " + "، ".join(tw["broken_procs"][:5]))
    if tw["bad_calls"]:
        out.append("طلبات مالهاش action: " + "، ".join(tw["bad_calls"][:5]))
    return out


def collect(url, name=""):
    from engine import report_compare as RC
    from engine import xray as X
    try:
        from engine import code_twin as T
        twin = T.load()
    except Exception:
        twin = None
    plan = load_plan(url)
    h = _health_for(url) or {}
    hk = h.get("_key")
    books = _read(_state(f"books_{hk}.json")) if hk else None
    load = _read(_state(f"load_{hk}.json")) if hk else None
    xr = X.load(url) or {}
    cat = RC.load_catalog(url) or {}
    findings, areas = [], {}
    names = h.get("names") or {}

    # ---- 1. screens
    broken = h.get("broken") or {}
    for p, b in broken.items():
        why = b.get("why") or ""
        s = b.get("s") or 0
        conf = bool(s and (s >= 500 or s == 404)) or why.startswith("صفحة خطأ")
        tw = _twin_for(p, twin)
        sev = "عالية" if conf else "متوسطة"
        findings.append(_f("الشاشات", sev, f"«{b.get('name') or names.get(p, p)}» مش بتفتح — {why[:160]}", p,
                           f"HTTP {s} · {b.get('ms') or 0} ms" if s else why[:200],
                           "افتح الشاشة وشوف الـ log بتاع السيرفر — " + ("الـ Controller نفسه مش في الكود" if tw and tw.get("missing") else "الكود تحت"),
                           conf, b.get("name") or names.get(p, p), _code_lines(tw)))
    total = h.get("total") or 0
    areas["الشاشات"] = {"ran": bool(h), "ok": total - len(broken), "n": total, "bad": len(broken),
                        "text": f"{total - len(broken)} من {total} شاشة بتفتح" if h else "ما اتفحصتش"}

    # ---- 2. names & links (xray menu + language) + menu changes
    nl = [x for x in xr.get("findings") or [] if x.get("area") in ("الروابط", "اللغة")]
    for x in nl:
        findings.append(_f("الأسماء واللينكات", x.get("sev") or "متوسطة", x.get("title", ""), x.get("where", "") if isinstance(x.get("where"), str) else "",
                           x.get("detail", "") if isinstance(x.get("detail"), str) else "", x.get("fix", ""), True, x.get("group", "")))
    dup = {}
    for p, n in names.items():
        dup.setdefault(re.sub(r"\s+", " ", str(n)).strip(), []).append(p)
    for n, ps in dup.items():
        if len(ps) > 1 and n and len({q.split("?")[0].lower() for q in ps}) > 1:
            findings.append(_f("الأسماء واللينكات", "منخفضة", f"نفس الاسم «{n}» على {len(ps)} لينكات مختلفة في المنيو", " · ".join(ps[:4]),
                               "", "اتأكد إن كل لينك اسمه بيوصف الشاشة", True, n))
    areas["الأسماء واللينكات"] = {"ran": bool(xr or h), "bad": sum(1 for f in findings if f["area"] == "الأسماء واللينكات" and f["sev"] in ("عالية", "متوسطة")),
                                  "text": f"{len(names)} اسم ولينك اتراجعوا" if names else "ما اتفحصتش"}

    # ---- 3. reports
    reps = cat.get("reports") or []
    rstat = {}
    for r in reps:
        sn = RC.load_snap(r["path"], url) or {}
        st = sn.get("status") or "lost"
        rstat[st] = rstat.get(st, 0) + 1
        nm = r.get("name") or r["path"]
        if st == "error":
            fault = str(sn.get("fault") or "")
            m = re.search(r"(Invalid (?:column|object) name '[^']+'|Could not find stored procedure '[^']+'|[A-Za-z_]+ is not a parameter[^.]*|"
                          r"Procedure or function '[^']+' expects parameter '[^']+'|Ambiguous column name '[^']+')", fault)
            sql = m.group(1) if m else ""
            code = []
            if twin:
                key = r["path"].strip("/").split("/")[-1].lower()
                rep = next((x for x in (twin.get("reports") or []) if str(x.get("name", "")).lower() == key), None) if isinstance(twin.get("reports"), list) else None
                if rep and rep.get("sp"):
                    code.append(f"الإجراء: {rep['sp']}")
            findings.append(_f("التقارير", "عالية", f"تقرير «{nm}» بيفشل على السيرفر" + (f" — {sql}" if sql else ""), r["path"],
                               fault[:400] or f"HTTP {sn.get('http')}", "صلّح الإجراء / الاستعلام بتاع التقرير" if sql else "شوف الـ log بتاع السيرفر وقت بناء التقرير",
                               True, nm, code))
        elif st == "noviewer":
            findings.append(_f("التقارير", "متوسطة", f"تقرير «{nm}» الصفحة بتاعته مش بتفتح عارض التقارير", r["path"], (sn.get("body") or "")[:200],
                               "اتأكد إن التقرير موجود ومربوط في المنيو صح", True, nm))
        elif st in ("stuck", "empty", "crash", "lost"):
            findings.append(_f("التقارير", "للعلم", f"تقرير «{nm}» " + {"stuck": "ماتبناش بالقيم الافتراضية (غالبًا محتاج فلتر)", "empty": "طلع فاضي بالقيم الافتراضية",
                                                                    "crash": "الأداة وقفت عنده", "lost": "ما اتبناش (الاختبار ماوصلوش)"}[st],
                               r["path"], str(sn.get("msg") or sn.get("error") or "")[:200], "افتحه بإيدك بفلتر حقيقي واتأكد", False, nm))
    areas["التقارير"] = {"ran": bool(reps), "n": len(reps), "ok": rstat.get("ok", 0), "bad": rstat.get("error", 0) + rstat.get("noviewer", 0), "stat": rstat,
                         "text": (f"{rstat.get('ok', 0)} من {len(reps)} تقرير اتبنى · {rstat.get('error', 0)} فشل على السيرفر" if reps else "ما اتفحصتش")}

    # ---- 4. speed
    ss = h.get("speed_stats") or {}
    slow = [m for m in h.get("speed") or [] if (m.get("load") or 0) >= 5][:15]
    for m in slow:
        findings.append(_f("السرعة", "متوسطة" if (m.get("load") or 0) < 10 else "عالية", f"«{m.get('name')}» بتفتح في {m.get('load') or 0:.1f} ث", m.get("path", ""),
                           "أبطأ طلب: " + ", ".join(f"{x.get('url', '')[-60:]} {x.get('ms')} ms" for x in (m.get("xhr") or [])[:2]),
                           "راجع الاستعلام / الفهارس بتاعة أبطأ طلب", True, m.get("name", ""), _code_lines(_twin_for(m.get("path"), twin))[:1]))
    areas["السرعة"] = {"ran": bool(ss.get("measured")), "bad": len(slow),
                       "text": (f"{ss.get('measured')} شاشة اتقاست · المتوسط {ss.get('load_median')} ث · {len(slow)} أبطأ من 5 ث" if ss.get("measured") else "ما اتقاستش")}

    # ---- 5. load
    if load:
        for t in load.get("targets") or []:
            if not t.get("ok"):
                findings.append(_f("الحمل", "عالية" if t.get("bad") else "متوسطة",
                                   f"«{t['name']}» تحت ضغط {load['users']} مستخدمين: p95 {t['p95']} ms" + (f" · {t['bad']} خطأ من {t['n']}" if t.get("bad") else ""),
                                   t.get("url", ""), f"لوحده {t['solo']} ms ← تحت الضغط ×{t['deg']}" + (f" · {'، '.join(t.get('why') or [])}" if t.get("why") else ""),
                                   "راجع أبطأ استعلام في الشاشة وقفل الجلسة (Session lock)", bool(t.get("bad")), t["name"]))
    areas["الحمل"] = {"ran": bool(load), "bad": sum(1 for t in (load or {}).get("targets") or [] if not t.get("ok")),
                      "text": (f"{load['users']} مستخدمين × {load['rounds']} · {load['n']} طلب · أخطاء {load['bad']} · {load['mode']}" if load else "ما اتعملش")}

    # ---- 6. books
    if books is not None and not books.get("ok"):
        zero = any("فيه حركة" in " ".join(str(c) for c in (r.get("cells") or [])) for r in books.get("rows") or [])
        if not zero:
            bad_rows = [" · ".join(str(c) for c in r.get("cells") or []) for r in books.get("rows") or [] if r.get("ok") is False][:6]
            findings.append(_f("الحسابات", "عالية", "ميزان المراجعة مش متزن", "ميزان المراجعة", " | ".join(bad_rows)[:500],
                               "راجع القيود اللي مدينها ≠ دائنها والحسابات الأب", True, "ميزان المراجعة"))
    areas["الحسابات"] = {"ran": books is not None, "bad": 0 if (books or {}).get("ok") else (1 if books is not None else 0),
                         "text": "متزنة" if (books or {}).get("ok") else ("مش متزنة" if books is not None else "ما اتفحصتش")}

    # ---- 7. security & libraries
    sl = [x for x in xr.get("findings") or [] if x.get("area") in ("الأمان", "المكتبات")]
    for x in sl:
        findings.append(_f("الأمان والمكتبات", x.get("sev") or "متوسطة", x.get("title", ""), x.get("where", "") if isinstance(x.get("where"), str) else "",
                           x.get("detail", "") if isinstance(x.get("detail"), str) else "", x.get("fix", ""), True))
    areas["الأمان والمكتبات"] = {"ran": bool(xr), "bad": sum(1 for x in sl if x.get("sev") == "عالية"), "text": f"{len(sl)} ملاحظة" if xr else "ما اتفحصتش"}

    # ---- 8. code (twin), only for the screens this client really has
    present = {_ctrl(p) for p in (h.get("paths") or [])} - {""}
    code_n = 0
    if twin and present:
        tsc = twin.get("screens") or {}
        fid = {f["id"]: f for f in twin.get("findings") or []}
        hits = {}
        for c in sorted(present):
            sc = tsc.get(c)
            if not sc:
                continue
            bad_calls = [x["url"] for x in sc.get("calls") or [] if not x.get("ok")]
            if sc.get("broken_procs") or bad_calls:
                code_n += 1
                nm = next((names[p] for p in names if _ctrl(p) == c), sc.get("ar") or sc["name"])
                findings.append(_f("الكود", "عالية" if sc.get("broken_procs") else "متوسطة",
                                   f"شاشة «{nm}»: " + " · ".join(x for x in [f"{len(sc.get('broken_procs') or [])} إجراء مكسور" if sc.get("broken_procs") else "",
                                                                             f"{len(bad_calls)} طلب على action مش موجود" if bad_calls else ""] if x),
                                   sc.get("file") or c, "، ".join((sc.get("broken_procs") or [])[:4] + bad_calls[:4]),
                                   "صلّح الإجراء / ضيف الـ action أو شيل الطلب", False, nm,
                                   [f"{sc['name']}Controller · {sc.get('file') or ''}"]))
            for i in sc.get("issues") or []:
                if i in fid:
                    hits.setdefault(i, []).append(c)
        for i, cs in hits.items():
            f = fid[i]
            if f["sev"] in ("عالية", "متوسطة") and f["area"] not in ("الإجراءات",):
                findings.append(_f("الكود", "للعلم", f"{f['title']} — بيمس {len(cs)} شاشة عند العميل", "، ".join(cs[:8]), f.get("detail", "")[:300], f.get("fix", ""), False))
    areas["الكود"] = {"ran": bool(twin), "bad": code_n,
                      "text": (f"{len(present)} شاشة عند العميل اتقارنت بالكود · {code_n} فيها مشكلة" if twin else "التوأم الرقمي ما اتشغلش")}

    # ---- 9. 🧪 the main screens, every scenario (automatic test, every way)
    runs = _runs(plan)
    fire = [r for r in runs if r.get("kind") == "auto"]
    for r in fire:
        if r["status"] != "fail":
            continue
        det = None
        try:
            from engine.check_runner import load_detail
            det = load_detail(r["task_id"])
        except Exception:
            pass
        rows_ = ((det or {}).get("detail") or {}).get("rows") or []
        bad_rows = [x for x in rows_ if x.get("ok") is False]
        scr = r["name"].replace("📚 ", "").replace("🧪 شامل: ", "")
        if not bad_rows:
            findings.append(_f("الشاشات الرئيسية — اختبار شامل", "متوسطة", f"«{scr}» الاختبار فشل", "", r["msg"][:400], "شوف تقرير التشغيل", False, scr))
        for x in bad_rows:
            c = (list(x.get("cells") or []) + ["", "", ""])[:3]
            txt = str(c[2] if len(c) > 2 else "")
            bad_line = next((l.strip() for l in txt.splitlines() if l.strip().startswith("❌")), (txt.splitlines() or [""])[0])
            conf = bool(SITE_BUG.search(txt))
            findings.append(_f("الشاشات الرئيسية — اختبار شامل", "عالية" if conf else "متوسطة", f"«{scr}» — {c[1]}: {bad_line.lstrip('❌ ')[:170]}", "",
                               txt[:500], "", conf, scr))
    areas["الشاشات الرئيسية — اختبار شامل"] = {"ran": bool(fire), "bad": sum(1 for r in fire if r["status"] == "fail"),
                                        "text": (f"{sum(1 for r in fire if r['status'] == 'pass')} من {len(fire)} شاشة نجحت في كل السيناريوهات" if fire else "ما اتختارتش")}

    # ---- 10. business cycles (the plan's extra runs)
    cyc = [r for r in runs if r.get("kind") in ("bizcases", "biz", "cycle")]
    for r in cyc:
        if r["status"] == "fail":
            findings.append(_f("الدورات المستندية", "عالية", f"«{r['name']}» فشلت", "", r["msg"][:400], "شوف تقرير التشغيل", False, r["name"]))
    areas["الدورات المستندية"] = {"ran": bool(cyc), "bad": sum(1 for r in cyc if r["status"] == "fail"),
                                  "text": (f"{sum(1 for r in cyc if r['status'] == 'pass')} من {len(cyc)} نجحت" if cyc else "ما اتختارتش")}

    findings.sort(key=lambda f: (not f["confirmed"], SEV.get(f["sev"], 9), AREAS.index(f["area"]) if f["area"] in AREAS else 99))
    for i, f in enumerate(findings, 1):
        f["no"] = i

    # ---- verdicts
    for a in AREAS:
        e = areas.setdefault(a, {"ran": False, "bad": 0, "text": "—"})
        hi = sum(1 for f in findings if f["area"] == a and f["confirmed"] and f["sev"] == "عالية")
        mid = sum(1 for f in findings if f["area"] == a and f["sev"] in ("عالية", "متوسطة"))
        e["hi"], e["mid"] = hi, mid
        e["verdict"] = "na" if not e["ran"] else ("no" if hi else ("care" if mid else "go"))
    crit_screens = []
    try:
        from engine import readiness
        crit_screens = readiness.for_state({**h, "_file": f"health_{hk}.json"}, name).get("critical") or [] if h else []
    except Exception:
        pass
    ran = [a for a in AREAS if areas[a]["verdict"] != "na"]
    nos = [a for a in ran if areas[a]["verdict"] == "no"]
    if not ran:
        verdict = ("na", "لسه ما اتفحصش")
    elif nos or crit_screens:
        verdict = ("no", "⛔ مينفعش يتسلم دلوقتي")
    elif any(areas[a]["verdict"] == "care" for a in ran):
        verdict = ("care", "⚠️ يتسلم بملاحظات")
    else:
        verdict = ("go", "✅ جاهز للتسليم")
    conf = [f for f in findings if f["confirmed"]]
    return {"url": url, "name": name, "at": datetime.now().strftime("%Y-%m-%d %H:%M"), "plan": plan, "runs": runs,
            "verdict": verdict[0], "verdict_text": verdict[1], "blockers": nos, "critical": [names.get(p, p) for p in crit_screens],
            "areas": [{"name": a, **areas[a]} for a in AREAS], "findings": findings,
            "counts": {"all": len(findings), "confirmed": len(conf), "hi": sum(1 for f in conf if f["sev"] == "عالية"),
                       "check": len(findings) - len(conf), "screens": total, "reports": len(reps)},
            "sources": {"health": h.get("at"), "xray": xr.get("at"), "reports": cat.get("at"), "load": (load or {}).get("at"),
                        "books": (books or {}).get("at"), "twin": (twin or {}).get("at")}}


# ------------------------------------------------------------------ the report
VC = {"go": ("#1B7F3B", "✅ مقبول"), "care": ("#B26A00", "⚠️ بملاحظات"), "no": ("#C62828", "⛔ مرفوض"), "na": ("#6B7280", "— ما اتفحصش")}


def report_html(d, user=""):
    from web import pdf_reports as P
    e = P.e
    col = VC.get(d["verdict"], VC["na"])[0]
    body = [f"<div class='verdict' style='border-color:{col};color:{col}'>{e(d['verdict_text'])} · {d['counts']['confirmed']} مشكلة مؤكدة في الموقع"
            f" ({d['counts']['hi']} عالية) · {d['counts']['check']} محتاجة تأكيد</div>"]
    if d.get("critical"):
        body.append(f"<p><b>شاشات حرجة بايظة:</b> {e('، '.join(d['critical'][:12]))}</p>")
    body.append("<h2>النتيجة لكل جزء</h2>")
    body.append(P.table(["الجزء", "الحكم", "التفاصيل", "مشاكل عالية", "إجمالي الملاحظات"],
                        [[a["name"], VC[a["verdict"]][1], a.get("text") or "—", a.get("hi") or "—", a.get("mid") or "—"] for a in d["areas"]], center=(1, 3, 4)))
    conf = [f for f in d["findings"] if f["confirmed"]]
    rest = [f for f in d["findings"] if not f["confirmed"]]

    def rows(lst):
        return [[f["no"], f["area"], f["sev"], f["title"], f.get("where") or "—", f.get("evidence") or "—",
                 P.Raw("<br>".join(e(x) for x in f.get("code") or []) or "—"), f.get("fix") or "—"] for f in lst]
    cols = ["#", "الجزء", "الخطورة", "المشكلة", "المكان / اللينك", "الدليل", "في الكود", "المطلوب"]
    body.append(f"<h2>المشاكل المؤكدة في الموقع ({len(conf)})</h2>")
    body.append(P.table(cols, rows(conf), center=(0, 1, 2)) if conf else "<p>مفيش 👍</p>")
    if rest:
        body.append(f"<h2>محتاجة تأكيد / للعلم ({len(rest)})</h2><p class='small'>ملاحظات الأداة شافتها بس مفيش دليل من السيرفر — تتراجع بالإيد قبل ما تتصلح.</p>")
        body.append(P.table(cols, rows(rest), center=(0, 1, 2)))
    runs = d.get("runs") or []
    if runs:
        body.append("<h2>التشغيلات</h2>" + P.table(["المرحلة", "النتيجة", "رقم التشغيل"],
                                                   [[r["name"], {"pass": "✅ نجح", "fail": "❌ فيه مشاكل", "waiting": "⏳ لسه"}[r["status"]], r["task_id"]] for r in runs], center=(1,)))
    src = d.get("sources") or {}
    return P.page("تقرير اختبار الاستلام", "Go-Live acceptance report", user, "".join(body),
                  [("الموقع", d.get("name") or d["url"]), ("الرابط", d["url"]), ("الشاشات", d["counts"]["screens"]), ("التقارير", d["counts"]["reports"]),
                   ("آخر فحص", src.get("health") or "—")])


def report_docx(d, user=""):
    import os
    import tempfile
    from docx.shared import RGBColor
    from engine.docx_design import Report
    from engine.biz_report import company_name
    rp = Report(company_name(), "تقرير اختبار الاستلام", "Go-Live acceptance report", user)
    rp.strip([("الموقع", d.get("name") or d["url"]), ("الحكم", d["verdict_text"]), ("مشاكل مؤكدة", str(d["counts"]["confirmed"])),
              ("وقت التقرير", d["at"])])
    red, amber, green, teal = RGBColor(0xC6, 0x28, 0x28), RGBColor(0xB2, 0x6A, 0x00), RGBColor(0x1B, 0x7F, 0x3B), RGBColor(0x0F, 0x7C, 0x7A)
    vcol = {"✅ مقبول": green, "⚠️ بملاحظات": amber, "⛔ مرفوض": red}
    rp.table([("الجزء", 18), ("الحكم", 14), ("التفاصيل", 50), ("عالية", 8), ("الملاحظات", 10)],
             [[a["name"], VC[a["verdict"]][1], a.get("text") or "—", str(a.get("hi") or "—"), str(a.get("mid") or "—")] for a in d["areas"]],
             center=(1, 3, 4), colors=lambda ri, ci, v: vcol.get(v) if ci == 1 else None)
    scol = {"عالية": red, "متوسطة": amber}
    for title, lst in (("المشاكل المؤكدة في الموقع", [f for f in d["findings"] if f["confirmed"]]),
                       ("محتاجة تأكيد / للعلم", [f for f in d["findings"] if not f["confirmed"]])):
        if not lst:
            continue
        rp.page_break()
        rp.para(f"{title} ({len(lst)})", size=12, bold=True, color=teal)
        rp.table([("#", 3), ("الجزء", 9), ("الخطورة", 7), ("المشكلة", 28), ("المكان", 15), ("الدليل", 18), ("في الكود", 12), ("المطلوب", 12)],
                 [[str(f["no"]), f["area"], f["sev"], f["title"], f.get("where") or "—", f.get("evidence") or "—", "\n".join(f.get("code") or []) or "—",
                   f.get("fix") or "—"] for f in lst], size=7, center=(0, 1, 2), colors=lambda ri, ci, v: scol.get(v) if ci == 2 else None)
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as t:
        tmp = t.name
    rp.save(tmp)
    data = open(tmp, "rb").read()
    os.unlink(tmp)
    return data


def support_issues():
    """the confirmed problems of the last go-live of every site → «🎫 دعم المطورين»"""
    out = []
    for f in paths.STATE_DIR.glob("golive_*.json"):
        p = _read(f) or {}
        d = p.get("last")
        if not d:
            continue
        host = re.sub(r"^https?://", "", d["url"]).strip("/")
        for x in d.get("findings") or []:
            if not x.get("confirmed") or x["sev"] not in ("عالية", "متوسطة"):
                continue
            out.append({"id": "golive_" + re.sub(r"\W+", "_", f"{host}_{x['area']}_{x['title'][:80]}")[:150], "site": host,
                        "url": d["url"].rstrip("/") + x["where"] if str(x.get("where", "")).startswith("/") else d["url"],
                        "source": "🚀 اختبار الاستلام", "screen": x.get("screen") or x["area"], "severity": x["sev"], "title": x["title"][:200],
                        "details": (x.get("evidence") or "") + ("\n" + "\n".join(x.get("code") or []) if x.get("code") else ""),
                        "evidence": x.get("evidence") or "", "doc": "", "steps": x.get("fix") or "", "found": d.get("at", "")[:10]})
    return out
