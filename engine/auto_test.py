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
def _what(res, cfg_v):
    from engine.screen_runner import RUN_VARS
    if res.get("negative_ok"):
        return "اترفض ✓ — " + " | ".join(str(x) for x in (res.get("rejected_with") or []))[:150]
    if res.get("operation") == "print":
        return "صفحة الطباعة فتحت"
    if res.get("operation") == "delete":
        return f"اتحذف ومبقاش في القايمة ({(res.get('row') or '')[:50]})"
    chk = res.get("saved_check") or {}
    filled = sum(1 for s in (res.get("steps") or []) if s.get("ok") and s.get("strategy") != "flow" and s.get("result") not in (None, ""))
    extra = (f" · فتحته تاني وراجعت {len(chk.get('rows', []))} قيمة — كلها صح" if chk.get("checked") else
             (f" · (مقدرتش أفتحه تاني أراجع القيم: {chk.get('reason')})" if chk.get("reason") else ""))
    if res.get("operation") == "edit":
        return f"اتعدل {filled} حقل" + extra
    return f"اتملى {filled} حقل · اتحفظ · ظهر صف جديد في القايمة (رقم {RUN_VARS.get('saved_no', '—')})" + extra


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
    result["detail"] = {"title": f"🤖 الاختبار الآلي — {info['name']}", "columns": ["#", "الخطوة", "اللي حصل", "المدة (ث)"],
                        "rows": rows, "note": ""}
    result["screenshots"] = []

    # ---- 0. read the form on this site
    t0 = time.time()
    try:
        insp = FormInspector(driver).inspect(info["list_url"], info["add_url"], info["add_button"], find_dependencies=True)
    except Exception as e:
        rows.append({"cells": [0, "📖 قراءة الحقول من الشاشة", f"مقدرتش أفتح فورم الإضافة: {str(e).splitlines()[0][:200]}", round(time.time() - t0, 1)], "ok": BAD})
        e2 = AssertionError(f"الاختبار الآلي لـ «{info['name']}»: مقدرتش أقرا الحقول — {type(e).__name__}: {str(e).splitlines()[0][:200]}")
        e2.partial_result = result
        raise e2
    read = insp.get("fields") or []
    usable = _usable(read)
    req_labels = [f["label"] or f["id"] for f in usable if f.get("required")]
    lists = sum(1 for f in usable if f["kind"] in ("select", "select2"))
    deps = sum(1 for f in usable if f.get("depends_on"))
    if insp.get("screenshot"):
        result["screenshots"].append(insp["screenshot"])
    note = (f"{len(usable)} حقل ({len(req_labels)} إجباري: {'، '.join(req_labels[:8]) or '—'}) · {lists} قايمة"
            + (f" · {deps} بتعتمد على غيرها" if deps else "") + (f" · زرار الحفظ: {insp.get('suggested_save')}" if insp.get("suggested_save") else ""))
    if insp.get("warnings"):
        note += "\n⚠️ " + " | ".join(insp["warnings"])
    if info["builder"] and info["builder"].get("flows"):
        note += f"\n🧩 هستخدم من منشئ الشاشات: {len(info['builder']['flows'])} إجراء (أصناف / أزرار / نوافذ)"
    ok_read = bool(usable)
    rows.append({"cells": [0, "📖 قراءة الحقول من الشاشة (على الموقع ده)", note, round(time.time() - t0, 1)], "ok": OK if ok_read else BAD})
    logger.info(f"📖 {info['name']}: {note}")
    if not ok_read:
        e = AssertionError(f"الاختبار الآلي لـ «{info['name']}»: مالقيتش حقول في فورم الإضافة ({insp.get('add_url')})")
        e.partial_result = result
        raise e

    base = _base(info, insp)
    mode = cfg.get("fields_mode", "all")
    expect = cfg.get("expect_error") or "*"
    neg = {"expect_error": expect, "save_timeout": 20, "verify": {**base["verify"], "open_saved": False}}
    first_fields, req = build_fields(read, "all", "first", info["builder"])
    steps = []
    for way in cfg["ways"]:
        label = AUTO_WAYS[way][1]
        if way == "reject_empty":
            steps.append((way, label, _variant(base, "auto_empty", fields=[_keep(f) for f in first_fields], flows=[], **neg)))
        elif way == "reject_required":
            reqf = [f for f in first_fields if f["id"] in req]
            if not reqf:
                steps.append((way, label, "الشاشة دي مفيهاش حقول إجبارية على الموقع ده"))
            for f in reqf[:3]:
                empty = _children(first_fields, f["id"])
                steps.append((way, f"«{f['label']}» فاضي لازم يترفض",
                              _variant(base, "auto_no_" + "".join(c for c in f["id"].lower() if c.isalnum())[:30] or "f",
                                       fields=[_keep(x) if x["id"] in empty else x for x in first_fields], **neg)))
        elif way == "add":
            for sc in cfg.get("scenarios") or ["first"]:
                flds, _ = build_fields(read, mode if req else "all", sc, info["builder"])
                if not flds:
                    steps.append(("add", f"{SCENARIOS[sc][0]} إضافة", "مفيش حقول تتملى"))
                    continue
                steps.append(("add", f"{SCENARIOS[sc][0]} إضافة — {SCENARIOS[sc][1]} ({'كل الحقول' if mode == 'all' else 'الإجباري بس'})",
                              _variant(base, f"auto_add_{sc}", fields=flds,
                                       verify={**base["verify"], "new_first_row": True, "open_saved": True})))
        elif way == "edit":
            scn = _scenario_for(info["key"], "edit")
            flds, _ = build_fields(read, mode, "random", None, editing=True)
            flds = [{**f, "optional": True} for f in flds if f["strategy"] != "keep"]   # the edit page may show fewer fields
            if not flds:
                steps.append((way, label, "مفيش حقول تتعدّل"))
                continue
            steps.append((way, f"{label} ({len(flds)} حقل بقيم جديدة)", _variant(
                base, "auto_edit", operation="edit", target_row="{var:auto_no}", fields=flds,
                flows=[],                                   # item lines / pop-ups are not added again when editing
                op_button=cfg.get("edit_button") or (scn or {}).get("op_button", ""),
                verify={**base["verify"], "open_saved": True})))
        elif way == "print":
            scn = _scenario_for(info["key"], "print")
            steps.append((way, label, _variant(base, "auto_print", operation="print", target_row="{var:auto_no}", fields=[], flows=[],
                                               op_button=cfg.get("print_button") or (scn or {}).get("op_button", ""))))
        elif way == "delete":
            scn = _scenario_for(info["key"], "delete")
            steps.append((way, label, _variant(base, "auto_delete", operation="delete", target_row="{var:auto_del}", fields=[], flows=[],
                                               op_button=cfg.get("delete_button") or (scn or {}).get("op_button", ""))))

    made = []                                    # numbers of the records the test saved (deleted at the end)
    logger.info(f"🤖 الاختبار الآلي لـ «{info['name']}»: {len(steps)} خطوة")
    n = 0
    for way, label, c in steps:
        n += 1
        if isinstance(c, str):
            rows.append({"cells": [n, label, "اتخطت: " + c, ""], "ok": SKIP})
            continue
        targets = [None]
        if way in ("edit", "print") and not RUN_VARS.get("auto_no"):
            rows.append({"cells": [n, label, "ما اتشغلتش — مفيش سجل اتحفظ من الإضافة", ""], "ok": SKIP})
            continue
        if way == "delete":
            targets = list(dict.fromkeys(made))
            if not targets:
                rows.append({"cells": [n, label, "مفيش سجلات اتعملت عشان تتحذف", ""], "ok": SKIP})
                continue
        for tno in targets:
            if tno:
                RUN_VARS["auto_del"] = tno
            lbl = label + (f" — رقم {tno}" if tno and len(targets) > 1 else "")
            t0, before = time.time(), RUN_VARS.get("saved_no")
            logger.info(f"🤖 {n}. {lbl}")
            try:
                res = run_screen(driver, credentials, c, save=True, do_login=False)
                ok, what = OK, _what(res, c)
            except (AssertionError, FieldFillError) as e:
                res = getattr(e, "partial_result", None) or {}
                ok, what = BAD, str(e).split("\n  (Session info")[0]
            except Exception as e:
                res, ok, what = {}, BAD, f"{type(e).__name__}: {str(e).splitlines()[0][:200]}"
            result["screenshots"] += [s for s in (res.get("screenshots") or []) if s][-2:]
            if way == "add" and RUN_VARS.get("saved_no") and RUN_VARS.get("saved_no") != before:
                made.append(RUN_VARS["saved_no"])
                RUN_VARS.setdefault("auto_no", RUN_VARS["saved_no"])
                if not ok:
                    what += f"\n(السجل اتحفظ برقم {RUN_VARS['saved_no']} — هكمل عليه)"
            if way == "edit" and ok and RUN_VARS.get("saved_no") and RUN_VARS.get("saved_no") != RUN_VARS.get("auto_no"):
                made = [RUN_VARS["saved_no"] if x == RUN_VARS.get("auto_no") else x for x in made]
                RUN_VARS["auto_no"] = RUN_VARS["saved_no"]
            rows.append({"cells": [n, lbl, what, round(time.time() - t0, 1)], "ok": ok})
            (logger.success if ok else logger.error)(f"{'✅' if ok else '❌'} {lbl}: {what.splitlines()[0][:200]}")
            if not ok:
                fails.append(f"{lbl}: {what.splitlines()[0][:200]}")
    done = [r for r in rows if r["ok"] is not SKIP]
    passed = sum(1 for r in done if r["ok"])
    result["detail"]["note"] = f"نجح {passed} من {len(done)}" + (f" · اتخطى {len(rows) - len(done)}" if len(rows) > len(done) else "") \
        + f" · الحقول: {'كل الحقول' if mode == 'all' else 'الإجباري بس'}"
    result["vars"] = {k: v for k, v in RUN_VARS.items() if isinstance(v, (str, int, float))}
    if fails:
        e = AssertionError(f"الاختبار الآلي لـ «{info['name']}»: {len(fails)} من {len(done)} فشلوا\n   " + "\n   ".join(fails))
        e.partial_result = result
        raise e
    logger.success(f"✅ الاختبار الآلي لـ «{info['name']}» نجح كله ({passed} من {len(done)})")
    return result
