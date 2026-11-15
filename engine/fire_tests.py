"""
🔥 اختبار النار — the extra ways of the automatic test that try to BREAK a screen, the way a careless or a malicious user would:

  reject    🚫  save with nothing filled, then with each required field left empty (up to 3): every one must be refused,
                with a clear message (not a server crash / SQL text)
  negative  ➖  -5 in every amount / quantity box of the header: must be refused
  fire      🔥  quotes, SQL characters, HTML + a harmless script probe, emoji and Arabic diacritics in every text box:
                refused with a clear message = fine · a server error = SQL / code bug · the probe RUNS in the list = XSS hole ·
                the text comes back different = noted · then the record is deleted
  burst     ⚡  5 documents saved back to back: all saved, numbers unique and in order, the time of each — then deleted

All of them write on the site (test documents), so they only run where writing is allowed (engine.guard).
"""
import re
import time

from utils.logger import logger

OK, BAD, SKIP = True, False, None
FIRE_TEXT = "NQ'\"<b>x</b><img src=x onerror=window.__nqx=1>;-- %★€ مُحَمَّد"
TECH = re.compile(r"Exception|Incorrect syntax|Unclosed quotation|SqlException|System\.[A-Z]|Object reference|stack ?trace|Server Error|"
                  r"Invalid (?:column|object)|conversion failed|would be truncated|arithmetic overflow|NullReference|Runtime Error|"
                  r"خطأ في الخادم|\b500\b|A potentially dangerous Request", re.I)
JS_BREAK = re.compile(r"SyntaxError|Unexpected token|Invalid or unexpected token|unterminated", re.I)
XSS_JS = "return !!window.__nqx"


def _run(driver, credentials, cfg):
    from engine.screen_runner import run_screen
    from engine.form_filler import FieldFillError
    try:
        return run_screen(driver, credentials, cfg, save=True, do_login=False), ""
    except (AssertionError, FieldFillError) as e:
        return getattr(e, "partial_result", None) or {}, str(e).split("\n  (Session info")[0]
    except Exception as e:
        return {}, f"{type(e).__name__}: {str(e).splitlines()[0][:200]}"


def _msg(res, err):
    return " | ".join(str(x) for x in (res.get("rejected_with") or [])) or (err.splitlines()[0] if err else "")


def _delete(driver, credentials, plan, no, why):
    if not no:
        return "⚠️ مالقيتش رقم السجل علشان أحذفه — راجع القايمة"
    res, err = _run(driver, credentials, {**plan["delete"], "target_row": str(no)})
    if not err:
        return f"🧹 السجل {no} اتحذف"
    try:
        from engine import cleanup
        cleanup.remember(plan["delete"].get("name_ar") or "", no, plan["delete"], why)
    except Exception:
        pass
    return f"⚠️ مقدرتش أحذف السجل {no} ({err.splitlines()[0][:100]}) — اتسجل في «تنظيف بيانات الاختبار»"


def _first_cell(driver, list_url):
    from engine.screen_runner import FIRST_CELL_JS, _abs
    try:
        driver.get(_abs(list_url))
        time.sleep(2.5)
        return driver.execute_script(FIRST_CELL_JS)
    except Exception:
        return None


# ---------------------------------------------------------------- 🚫 reject
def way_reject(ctx):
    from engine.auto_test import _variant, _keep
    d, cr, base, flds, req_ids = ctx["driver"], ctx["cred"], ctx["base"], ctx["fields"], ctx["req"]
    lines, bad = [], []
    cases = [("كل الحقول فاضية", _variant(base, "fire_empty", fields=[_keep(f) for f in flds], flows=[], before_save=[],
                                       auto_complete=False, expect_error="*", verify={**base["verify"], "new_first_row": False}))]
    for f in [x for x in flds if x["id"] in req_ids and x["strategy"] != "keep"][:3]:
        cases.append((f"«{f['label']}» فاضي (إجباري)", _variant(base, "fire_req", fields=[_keep(x) if x["id"] == f["id"] else x for x in flds],
                                                               auto_complete=False, expect_error="*", verify={**base["verify"], "new_first_row": False})))
    for name, cfg in cases:
        before = _first_cell(d, base["list_url"])
        res, err = _run(d, cr, cfg)
        m = _msg(res, err)
        if res.get("negative_ok"):
            if TECH.search(m):
                lines.append(f"❌ {name}: اترفض بس برسالة تقنية من السيرفر: {m[:160]}")
                bad.append(f"{name}: رسالة تقنية بدل رسالة واضحة")
            else:
                lines.append(f"✅ {name}: اترفض — {m[:120] or 'من غير ما يتحفظ'}")
        elif "اتحفظ — والمفروض" in err:
            after = _first_cell(d, base["list_url"])
            lines.append(f"❌ {name}: اتحفظ! والمفروض يترفض" + (f" — " + _delete(d, cr, ctx["plan"], after, "اتحفظ في اختبار الرفض") if after and after != before else ""))
            bad.append(f"{name}: اتحفظ")
        else:
            lines.append(f"⚪ {name}: مقدرتش أجربه — {err.splitlines()[0][:140] if err else '—'}")
    return "\n".join(lines), (BAD if bad else OK), "؛ ".join(bad)


# ---------------------------------------------------------------- ➖ negative
def way_negative(ctx):
    from engine.auto_test import _variant, build_fields
    d, cr, base = ctx["driver"], ctx["cred"], ctx["base"]
    flds, _ = build_fields(ctx["read"], ctx["mode"], "neg", ctx["builder"])
    neg = [f["label"] for f in flds if f.get("strategy") == "fixed" and f.get("value") == "-5"]
    if not neg:
        return "مفيش خانة مبلغ / كمية في رأس المستند أجرب فيها رقم بالسالب", SKIP, ""
    before = _first_cell(d, base["list_url"])
    res, err = _run(d, cr, _variant(base, "fire_neg", fields=flds, auto_complete=True, expect_error="*", verify={**base["verify"], "new_first_row": False}))
    m = _msg(res, err)
    head = f"كتبت -5 في: {'، '.join(neg[:6])}"
    if res.get("negative_ok"):
        if TECH.search(m):
            return f"{head}\n❌ اترفض بس برسالة تقنية: {m[:160]}", BAD, "رقم بالسالب طلّع رسالة تقنية من السيرفر"
        return f"{head}\n✅ اترفض — {m[:140]}", OK, ""
    if "اتحفظ — والمفروض" in err:
        after = _first_cell(d, base["list_url"])
        tail = _delete(d, cr, ctx["plan"], after, "اتحفظ بأرقام بالسالب") if after and after != before else ""
        return f"{head}\n❌ اتحفظ بأرقام بالسالب!\n{tail}", BAD, f"قبل -5 في {'، '.join(neg[:3])}"
    return f"{head}\n⚪ مقدرتش أجربه — {err.splitlines()[0][:160] if err else '—'}", SKIP, ""


# ---------------------------------------------------------------- 🔥 hostile text
def way_fire(ctx):
    from engine.auto_test import _variant, build_fields
    from engine.screen_runner import RUN_VARS
    d, cr, base = ctx["driver"], ctx["cred"], ctx["base"]
    flds, _ = build_fields(ctx["read"], ctx["mode"], "fire", ctx["builder"])
    hot = [f["label"] for f in flds if FIRE_TEXT[:6] in str(f.get("value") or "")]
    if not hot:
        return "مفيش خانة نص حر في الشاشة أجرب فيها", SKIP, ""
    before_no = RUN_VARS.get("saved_no")
    res, err = _run(d, cr, _variant(base, "fire_text", fields=flds, auto_complete=True,
                                    verify={**base["verify"], "new_first_row": True, "open_saved": True}))
    head = f"كتبت علامات تنصيص و SQL و HTML وسكريبت تجريبي ورموز وتشكيل في: {'، '.join(hot[:6])}"
    xss = False
    try:
        xss = bool(d.execute_script(XSS_JS))
    except Exception:
        pass
    if err:
        m = (" | ".join(str(a) for a in res.get("alerts") or []) + " " + err)
        if TECH.search(m):
            return f"{head}\n❌ السيرفر وقع / رد برسالة تقنية — غالبًا الاستعلام مش محمي (SQL) أو مفيش validation:\n   {err.splitlines()[0][:220]}", BAD, \
                "نص فيه علامات خاصة وقّع السيرفر"
        if "الحفظ ما نجحش" not in err:
            return f"{head}\n⚪ مقدرتش أكمّل الملء / الحفظ (مش من النص نفسه غالبًا): {err.splitlines()[0][:180]}", SKIP, ""
        return f"{head}\n✅ اترفض برسالة واضحة: {err.splitlines()[0][:160]}", OK, ""
    no = RUN_VARS.get("saved_no") if RUN_VARS.get("saved_no") != before_no else None
    lines, ok, why = [head, f"💾 اتحفظ برقم {no or '—'}"], OK, ""
    if not xss:
        _first_cell(d, base["list_url"])
        try:
            xss = bool(d.execute_script(XSS_JS))
        except Exception:
            pass
    if xss:
        lines.append("❌ ثغرة XSS: السكريبت التجريبي اتنفذ لما الشاشة عرضت النص — النص بيتعرض كـ HTML من غير encoding")
        ok, why = BAD, "ثغرة XSS في عرض النصوص"
    else:
        lines.append("✅ السكريبت التجريبي ما اتنفذش (النص بيتعرض كنص)")
    jsb = [e for e in res.get("tech_errors") or [] if JS_BREAK.search(str(e))]
    if jsb:
        lines.append("❌ النص كسر الجافاسكريبت في الصفحة: " + " | ".join(str(x)[:100] for x in jsb[:2]))
        ok, why = BAD, why or "النص كسر جافاسكريبت الصفحة (مفيش escaping)"
    chk = res.get("saved_check") or {}
    changed = [w for w in chk.get("warnings") or [] if any(h in str(w) for h in hot)]
    if changed:
        lines.append("⚠️ النص رجع مختلف بعد الحفظ (اتنضف أو اتقص): " + " · ".join(str(x)[:60] for x in changed[:4]))
    elif chk.get("checked"):
        lines.append("✅ فتحته تاني والنص زي ما اتكتب بالظبط")
    lines.append(_delete(d, cr, ctx["plan"], no, "سجل اختبار النار"))
    RUN_VARS["saved_no"] = before_no
    return "\n".join(lines), ok, why


# ---------------------------------------------------------------- ⚡ burst
def way_burst(ctx, n=5):
    from engine.screen_runner import RUN_VARS
    d, cr, plan = ctx["driver"], ctx["cred"], ctx["plan"]
    before = RUN_VARS.get("saved_no")
    nos, times, errs = [], [], []
    for i in range(n):
        t0 = time.time()
        prev = RUN_VARS.get("saved_no")
        res, err = _run(d, cr, plan["number"])
        times.append(round(time.time() - t0, 1))
        no = RUN_VARS.get("saved_no") if RUN_VARS.get("saved_no") != prev else None
        if err and not no:
            errs.append(f"{i + 1}: {err.splitlines()[0][:120]}")
            if len(errs) >= 2:
                break
        else:
            nos.append(no)
    lines = [f"حفظت {len(nos)} من {n} مستند ورا بعض · الوقت: " + " · ".join(f"{t} ث" for t in times)]
    if nos:
        lines.append("الأرقام: " + " ← ".join(str(x) for x in nos))
    ok, why = OK, ""
    if errs:
        ok, why = BAD, f"{len(errs)} حفظ فشل ورا بعض"
        lines += ["❌ " + e for e in errs]
    real = [x for x in nos if x]
    if len(set(real)) < len(real):
        ok, why = BAD, "رقم مستند اتكرر في الحفظ السريع"
        lines.append("❌ فيه أرقام مكررة")
    nums = [int(re.findall(r"\d+", str(x))[-1]) for x in real if re.findall(r"\d+", str(x))]
    if nums and nums != sorted(nums):
        ok, why = BAD, why or "الترقيم مش ماشي بالترتيب"
        lines.append("❌ الترقيم مش ماشي بالترتيب")
    elif len(nums) > 1:
        lines.append("✅ الأرقام مختلفة وماشية بالترتيب")
    if times and max(times) > 3 * max(0.1, min(times)) and max(times) > 15:
        lines.append(f"⚠️ الحفظ بقى أبطأ مع التكرار: من {min(times)} لـ {max(times)} ث")
    for no in real:
        lines.append(_delete(d, cr, plan, no, "اختبار الحفظ السريع"))
    RUN_VARS["saved_no"] = before
    return "\n".join(lines), ok, why


WAYS = {"reject": way_reject, "negative": way_negative, "fire": way_fire, "burst": way_burst}
