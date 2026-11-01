"""
الاختبار الآلي الشامل — any screen of the system (no Screen Builder setup needed), tested every way, in one browser:

  0. read       open the add form ON THE SITE BEING TESTED and read every field: which are required, lists, dates,
                which list depends on which. Required fields come from each client's own database, so they are read
                fresh every run (they differ from client to client / site to site).
  1. reject_empty     save with nothing filled                 -> must be rejected
  2. reject_required  each required field left empty (up to 3) -> must be rejected
  3. add              one or more fill scenarios, each saved and checked every way:
                         the page moved on / no error message · a new first row in the list · open it again and
                         compare every value that was filled
                       scenarios: first      first option in every list + realistic values
                                  random     random options + different values
                                  edge       random options + long texts / big numbers
                       fields: "all" (required + optional) or "required" (required only, + the lists they depend on)
  4. edit             the record of the first scenario: every field gets a NEW value (other options, new texts),
                       save, open it again -> the new values are there
  5. print            a print page / PDF opens, not empty, no server error
  6. delete           every record the test made -> gone from the list

If the screen also has a Screen Builder setup, its item lines / buttons / pop-ups (flows), save button and fixed
values are used too. Result: one table, a row per step.
"""
import copy
import time

from utils.logger import logger

SKIP, OK, BAD = None, True, False

SCENARIOS = {
    "first": ("1️⃣", "أول اختيار في كل قايمة + قيم واقعية"),
    "random": ("🎲", "اختيارات عشوائية + قيم مختلفة"),
    "edge": ("📏", "قيم حدّية: نصوص طويلة وأرقام كبيرة"),
}
LONG_TEXT = "اختبار آلي لقيمة طويلة " * 6


# ---------------------------------------------------------------- where the screen is
def screen_info(key):
    """{key, name, list_url, add_url, add_button, builder} for a catalog page or a Screen Builder screen"""
    from engine import screen_config
    from config.screens_catalog import all_pages
    builder = None
    try:
        builder = screen_config.load(key)
    except Exception:
        pass
    p = all_pages().get(key) or {}
    if not builder and p.get("url"):                       # a Screen Builder setup of the same page (another key)
        u = _u(p["url"])
        builder = next((c for c in screen_config.list_all() if not c.get("error") and _u(c["list_url"]) == u), None)
    if not p and not builder:
        raise AssertionError(f"الشاشة «{key}» مش موجودة في شاشات النظام ولا في منشئ الشاشات")
    return {"key": key, "name": (builder or {}).get("name_ar") or p.get("name_ar") or key,
            "list_url": (builder or {}).get("list_url") or p.get("url", ""),
            "add_url": (builder or {}).get("add_url", ""), "add_button": (builder or {}).get("add_button", ""),
            "builder": builder}


def _u(url):
    return (url or "").split("?")[0].lower().rstrip("/")


def all_screens():
    """every screen of the project: the system's screens (registry + discovered) and the Screen Builder ones"""
    from engine import screen_config
    from config.screens_catalog import all_pages
    out, seen = [], set()
    builders = {c["key"]: c for c in screen_config.list_all() if not c.get("error")}
    b_urls = {_u(c["list_url"]) for c in builders.values()}
    for k, p in all_pages().items():
        if not p.get("url"):
            continue
        out.append({"key": k, "name": p.get("name_ar") or k, "url": p["url"], "module": p.get("module_name") or "",
                    "builder": k in builders or _u(p["url"]) in b_urls})
        seen.add(_u(p["url"]))
    for k, c in builders.items():
        if any(x["key"] == k for x in out) or _u(c["list_url"]) in seen:
            continue
        out.append({"key": k, "name": c["name_ar"], "url": c["list_url"], "module": "🧩 منشئ الشاشات", "builder": True})
    return out


# ---------------------------------------------------------------- fields -> configs
def _usable(fields):
    return [f for f in fields if f.get("visible") and not f.get("disabled") and not f.get("in_table") and f["kind"] != "hidden"]


def _parents(fields, fid):
    by = {x["id"]: x for x in fields}
    out, cur = set(), by.get(fid, {}).get("depends_on")
    while cur and cur in by and cur not in out:
        out.add(cur)
        cur = by[cur].get("depends_on")
    return out


def _children(fields, fid):
    out, changed = {fid}, True
    while changed:
        changed = False
        for x in fields:
            if x.get("depends_on") in out and x["id"] not in out:
                out.add(x["id"])
                changed = True
    return out


def _strategy(f, scenario, editing=False):
    from engine.smart_values import guess
    kind, pre = f["kind"], str(f.get("value") or "").strip()
    smart = bool(guess(f.get("label", ""), f["id"]))
    if kind in ("select", "select2"):
        return ("first", "") if scenario == "first" and not editing else ("random", "")
    if kind == "date":
        return ("keep", "") if pre else ("today", "")
    if kind == "checkbox":
        return ("check", "") if scenario == "edge" else ("keep", "")
    if pre and not editing:                                  # a number the system fills (voucher no., rate…)
        return ("keep", "")
    if kind == "number":
        if scenario == "edge":
            return ("fixed", "999999")
        return ("smart", "") if smart else ("fixed", "{rand}")
    if smart:
        return ("smart", "")
    if editing:
        return ("fixed", "معدّل آلي {ts}")
    if scenario == "edge":
        return ("fixed", (LONG_TEXT + "{ts}") if kind == "textarea" else ("اختبار طويل " * 4 + "{ts}"))
    if kind == "textarea":
        return ("fixed", "اختبار آلي — " + ("عشوائي {rand} " if scenario == "random" else "") + "{ts}")
    return ("unique", ("آلي-{rand}-{ts}" if scenario == "random" else "آلي-{ts}"))


def build_fields(read, mode, scenario, builder=None, editing=False):
    """read fields (from the form) -> config fields for one scenario"""
    usable = _usable(read)
    req = {f["id"] for f in usable if f.get("required")}
    if mode == "required":
        need = set(req)
        for r in list(req):
            need |= _parents(usable, r)
        usable = [f for f in usable if f["id"] in need]
    fixed = {}
    if builder and scenario == "first" and not editing:     # values the Screen Builder setup already chose
        fixed = {f["id"]: f for f in builder["fields"] if f["strategy"] not in ("keep",)}
    ids, out = set(), []
    for f in usable:
        if f["id"] in fixed:
            b = fixed[f["id"]]
            st, val = b["strategy"], b["value"]
        else:
            st, val = _strategy(f, scenario, editing)
        dep = f.get("depends_on") if f.get("depends_on") in ids else None
        out.append({"id": f["id"], "label": f.get("label") or f["id"], "kind": f["kind"], "strategy": st, "value": val,
                    "required": bool(f.get("required")) and st != "keep", "depends_on": dep,
                    "soft": not f.get("required"),          # an optional field that can't be filled is noted, not fatal
                    "format": (fixed.get(f["id"]) or {}).get("format", ""), "timeout": 15, "wait_after": 0.5})
        ids.add(f["id"])
    return out, req


def _base(info, insp):
    b = info["builder"] or {}
    return {"key": info["key"][:80], "name_ar": info["name"], "list_url": info["list_url"],
            "add_url": insp.get("add_url") or info["add_url"], "add_button": insp.get("add_button") or info["add_button"],
            "save_button": b.get("save_button") or insp.get("suggested_save") or "button#save",
            "flows": copy.deepcopy(b.get("flows") or []), "before_save": copy.deepcopy(b.get("before_save") or []),
            "verify": {**(b.get("verify") or {}), "new_first_row": True}, "fields": []}


def _variant(base, suffix, **kw):
    from engine import screen_config
    c = copy.deepcopy(base)
    c.update({"key": (base["key"] + "_" + suffix)[:90], "run_before": [], "run_after": [], "data_file": ""})
    c.update(kw)
    return screen_config.normalize(c)


def _keep(f):
    return {**f, "strategy": "keep", "value": "", "required": False}      # left empty on purpose


def _scenario_for(screen_key, op):
    try:
        from engine import scenario_config
        return next((c for c in scenario_config.list_all(screen_key) if not c.get("error") and c.get("operation") == op), None)
    except Exception:
        return None


# ---------------------------------------------------------------- run
def _filled(res):
    out, skipped = [], []
    for st in res.get("steps") or []:
        if st.get("strategy") == "flow":
            continue
        lbl = str(st.get("label") or st.get("id") or "").replace(" (اتملى تلقائي — ظهر إجباري)", " 🧩")
        if st.get("skipped") or (not st.get("ok") and st.get("error")):
            if st.get("error"):
                skipped.append(f"{lbl}: {str(st['error']).splitlines()[0].split('] ')[-1][:80]}")
            continue
        if st.get("ok") and st.get("result") not in (None, ""):
            out.append(f"{lbl} = {str(st['result'])[:40]}")
    return out, skipped


def explain(way, res, ok, err=""):
    """the cell «اللي حصل»: what was filled, how the save went, how it was checked — line by line"""
    from engine.screen_runner import RUN_VARS
    lines = []
    filled, skipped = _filled(res)
    flows = [st for st in (res.get("steps") or []) if st.get("strategy") == "flow" and st.get("ok")]
    if way in ("add", "edit"):
        if filled:
            lines.append(f"✍️ اتملى {len(filled)} حقل: " + " · ".join(filled[:14]) + (" …" if len(filled) > 14 else ""))
        if flows:
            lines.append(f"🔗 {len(flows)} خطوة (أصناف / أزرار / مرفقات) اتعملت")
        if skipped:
            lines.append("⏭️ حقول مش إجبارية اتخطت: " + " · ".join(skipped[:5]))
    if ok:
        if way == "add":
            msgs = [str(a).replace("SweetAlert: ", "").replace("JS: ", "").strip() for a in (res.get("alerts") or [])]
            msg = next((m for m in reversed(msgs) if m and not m.startswith("هل ") and "?" not in m and "؟" not in m), "")
            lines.append("💾 اتحفظ" + (f" — رسالة النظام: {msg[:120]}" if msg else " — الصفحة رجعت للقايمة من غير أخطاء"))
            if res.get("first_row_after"):
                lines.append(f"📋 السجل الجديد ظهر أول القايمة: رقم {RUN_VARS.get('saved_no', '—')} — «{str(res['first_row_after'])[:90]}»")
        if way == "edit":
            lines.append(f"💾 التعديل اتحفظ على السجل «{str(res.get('row') or '')[:80]}»")
        chk = res.get("saved_check") or {}
        if chk.get("checked"):
            lines.append(f"🔎 فتحته تاني وقارنت {len(chk.get('rows', []))} قيمة — كلها زي ما اتكتبت ✓")
        elif chk.get("reason"):
            lines.append(f"🔎 مقدرتش أفتحه تاني أقارن القيم: {chk['reason']}")
        if way == "print":
            lines.append("🖨️ صفحة الطباعة فتحت ومش فاضية ومفيهاش خطأ")
        if way == "delete":
            lines.append(f"🗑️ اتحذف ومبقاش في القايمة — «{str(res.get('row') or '')[:80]}»")
    else:
        lines.append("❌ " + {"add": "الإضافة ما نجحتش", "edit": "التعديل ما نجحش", "print": "الطباعة ما نجحتش",
                             "delete": "الحذف ما نجحش"}.get(way, "فشل") + ":")
        lines += ["   " + x.strip() for x in str(err).split("\n") if x.strip()][:8]
    return "\n".join(lines)


def run_auto(driver, credentials, cfg, result=None):
    from engine.screen_runner import run_screen, login, RUN_VARS
    from engine.form_filler import FieldFillError
    from engine.form_inspector import FormInspector
    from engine.checks import AUTO_WAYS
    result = result if result is not None else {}
    info = screen_info(cfg["screen"])
    RUN_VARS.clear()
    login(driver, credentials)
    rows, fails = [], []
    result["detail"] = {"title": f"🤖 الاختبار الآلي — {info['name']}", "columns": ["#", "الاختبار", "اللي حصل بالتفصيل", "المدة (ث)"],
                        "rows": rows, "note": ""}
    result["screenshots"] = []

    # ---- read the add form on this site (required fields come from this client's own setup)
    t0 = time.time()
    try:
        insp = FormInspector(driver).inspect(info["list_url"], info["add_url"], info["add_button"], find_dependencies=True)
    except Exception as e:
        rows.append({"cells": [0, "📖 قراءة الشاشة", f"مقدرتش أفتح فورم الإضافة: {type(e).__name__}: {str(e).splitlines()[0][:200]}",
                               round(time.time() - t0, 1)], "ok": BAD})
        e2 = AssertionError(f"الاختبار الآلي لـ «{info['name']}»: مقدرتش أقرا الحقول — {type(e).__name__}: {str(e).splitlines()[0][:200]}")
        e2.partial_result = result
        raise e2
    read = insp.get("fields") or []
    usable = _usable(read)
    req_labels = [f["label"] or f["id"] for f in usable if f.get("required")]
    if insp.get("screenshot"):
        result["screenshots"].append(insp["screenshot"])
    note = f"📖 لقيت {len(usable)} حقل — منهم {len(req_labels)} إجباري على الموقع ده: {'، '.join(req_labels[:10]) or '—'}"
    if info["builder"] and info["builder"].get("flows"):
        note += f"\n🧩 هستخدم من منشئ الشاشات {len(info['builder']['flows'])} خطوة (أصناف / أزرار / نوافذ)"
    rows.append({"cells": [0, "📖 قراءة الشاشة", note, round(time.time() - t0, 1)], "ok": OK if usable else BAD})
    logger.info(note)
    if not usable:
        e = AssertionError(f"الاختبار الآلي لـ «{info['name']}»: مالقيتش حقول في فورم الإضافة ({insp.get('add_url')})")
        e.partial_result = result
        raise e

    base = _base(info, insp)
    mode = cfg.get("fields_mode", "all")
    flds, req = build_fields(read, mode if req_labels else "all", "first", info["builder"])
    edit_flds, _ = build_fields(read, mode if req_labels else "all", "random", None, editing=True)
    edit_flds = [{**f, "optional": True, "soft": True} for f in edit_flds if f["strategy"] != "keep"]
    plan = {
        "add": _variant(base, "auto_add", fields=flds, auto_complete=True,
                        verify={**base["verify"], "new_first_row": True, "open_saved": True}),
        "edit": _variant(base, "auto_edit", operation="edit", target_row="{var:auto_no}", fields=edit_flds or flds[:1], flows=[],
                         auto_complete=True, op_button=cfg.get("edit_button") or (_scenario_for(info["key"], "edit") or {}).get("op_button", ""),
                         verify={**base["verify"], "open_saved": True}),
        "print": _variant(base, "auto_print", operation="print", target_row="{var:auto_no}", fields=[], flows=[],
                          op_button=cfg.get("print_button") or (_scenario_for(info["key"], "print") or {}).get("op_button", "")),
        "delete": _variant(base, "auto_delete", operation="delete", target_row="{var:auto_no}", fields=[], flows=[],
                           op_button=cfg.get("delete_button") or (_scenario_for(info["key"], "delete") or {}).get("op_button", "")),
    }
    n = 0
    for way in [w for w in AUTO_WAYS if w in cfg["ways"]]:
        n += 1
        icon, label = AUTO_WAYS[way][0], AUTO_WAYS[way][1]
        if way != "add" and not RUN_VARS.get("auto_no"):
            rows.append({"cells": [n, f"{icon} {label}", "ما اتشغلش — مفيش سجل اتحفظ في اختبار الإضافة يتعمل عليه " + label.replace("اختبار ", ""), ""],
                         "ok": SKIP})
            continue
        t0, before = time.time(), RUN_VARS.get("saved_no")
        logger.info(f"🤖 {n}. {label}")
        try:
            res = run_screen(driver, credentials, plan[way], save=True, do_login=False)
            ok, err = OK, ""
        except (AssertionError, FieldFillError) as e:
            res = getattr(e, "partial_result", None) or {}
            ok, err = BAD, str(e).split("\n  (Session info")[0]
        except Exception as e:
            res, ok, err = {}, BAD, f"{type(e).__name__}: {str(e).splitlines()[0][:200]}"
        result["screenshots"] += [x for x in (res.get("screenshots") or []) if x][-3:]
        if way == "add" and RUN_VARS.get("saved_no") and RUN_VARS.get("saved_no") != before:
            RUN_VARS["auto_no"] = RUN_VARS["saved_no"]
        if way == "edit" and ok and RUN_VARS.get("saved_no"):
            RUN_VARS["auto_no"] = RUN_VARS["saved_no"]
        what = explain(way, res, ok, err)
        if way == "add" and not ok and RUN_VARS.get("auto_no"):
            what += f"\n(السجل اتحفظ برقم {RUN_VARS['auto_no']} — هكمل عليه التعديل والطباعة والحذف)"
        rows.append({"cells": [n, f"{icon} {label}", what, round(time.time() - t0, 1)], "ok": ok})
        (logger.success if ok else logger.error)(f"{'✅' if ok else '❌'} {label}: {what.splitlines()[-1][:200]}")
        if not ok:
            fails.append(f"{label}: {err.splitlines()[0][:200] if err else ''}")
    done = [r for r in rows[1:] if r["ok"] is not SKIP]
    passed = sum(1 for r in done if r["ok"])
    result["detail"]["note"] = f"نجح {passed} من {len(done)} · الحقول: {'كل الحقول' if mode == 'all' else 'الإجباري بس'}"
    result["vars"] = {k: v for k, v in RUN_VARS.items() if isinstance(v, (str, int, float))}
    if fails:
        e = AssertionError(f"الاختبار الآلي لـ «{info['name']}»: {len(fails)} من {len(done)} فشلوا\n   " + "\n   ".join(fails))
        e.partial_result = result
        raise e
    logger.success(f"✅ الاختبار الآلي لـ «{info['name']}» نجح كله ({passed} من {len(done)})")
    return result
