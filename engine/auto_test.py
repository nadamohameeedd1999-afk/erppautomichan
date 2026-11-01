"""
الاختبار الآلي الكامل لشاشة — one saved screen (منشئ الشاشات) tested every way, in one browser:

  1. reject_empty     حفظ فاضي                        -> must be rejected
  2. reject_required  each required field left empty -> must be rejected (up to 3 fields)
  3. add_required     only the required fields       -> saved + a new row in the list
  4. add_full         every field                    -> saved + new row + open it again and compare every value
  5. edit             the record of step 4           -> change a field, save, open again, the change is there
  6. print            the record of step 4           -> a print page / PDF opens, not empty, no server error
  7. delete           the records the test made      -> each one is gone from the list

Everything is built from the screen's own config; an edit / print / delete scenario of the same screen
(its button, its fields) is used when there is one. Result: one table, a row per way.
"""
import copy
import time

from utils.logger import logger

SKIP, OK, BAD = None, True, False


def _scenario_for(screen_key, op):
    try:
        from engine import scenario_config
        return next((c for c in scenario_config.list_all(screen_key) if not c.get("error") and c.get("operation") == op), None)
    except Exception:
        return None


def _parents(fields, f):
    """the fields f depends on (directly or through others) — they must be filled for f to have options"""
    by = {x["id"]: x for x in fields}
    out, cur = set(), f.get("depends_on")
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


def _variant(base, suffix, **kw):
    from engine import screen_config
    c = copy.deepcopy(base)
    c.update({"key": (base["key"] + "_" + suffix)[:90], "run_before": [], "run_after": [], "data_file": ""})
    c.update(kw)
    return screen_config.normalize(c)


def _keep(f):
    return {**f, "strategy": "keep", "value": "", "required": False}      # left empty on purpose


def edit_field(cfg, base):
    """the field the edit step changes: chosen in the page, else a notes / description text field"""
    fields = [f for f in base["fields"] if f["kind"] in ("text", "textarea", "number") and not f["id"].startswith("css:")]
    if cfg.get("edit_field"):
        f = next((x for x in base["fields"] if x["id"] == cfg["edit_field"]), None)
        if f:
            return f
    from engine.text_match import normalize as _n
    for words in (("ملاحظ", "note", "remark", "بيان", "وصف", "description"), ):
        for f in fields:
            if any(w in _n(f["label"]) or w in f["id"].lower() for w in words):
                return f
    return next((f for f in fields if f["kind"] == "textarea"), None) or next((f for f in fields if f["kind"] == "text"), None)


def plan(cfg, base):
    """[(way, label, config or None, note)] — config None = skipped with the note"""
    from engine.checks import AUTO_WAYS
    fields = base["fields"]
    req = [f for f in fields if f.get("required") and f["strategy"] != "keep"]
    expect = cfg.get("expect_error") or "*"
    neg = {"expect_error": expect, "save_timeout": 20, "verify": {**base["verify"], "open_saved": False}}
    out = []
    for way in cfg["ways"]:
        label = AUTO_WAYS[way][1]
        if way == "reject_empty":
            out.append((way, label, _variant(base, "auto_empty", fields=[_keep(f) for f in fields], flows=[], **neg), ""))
        elif way == "reject_required":
            if not req:
                out.append((way, label, None, "مفيش حقول متعلّم عليها «إجباري» في إعداد الشاشة — اقري الحقول تاني من منشئ الشاشات"))
            for f in req[:3]:
                empty = _children(fields, f["id"])
                out.append((way, f"«{f['label']}» فاضي لازم يترفض",
                            _variant(base, "auto_no_" + f["id"].lower().replace("-", "_")[:30],
                                     fields=[_keep(x) if x["id"] in empty else x for x in fields], **neg), ""))
        elif way == "add_required":
            if not req:
                out.append((way, label, None, "مفيش حقول متعلّم عليها «إجباري»"))
                continue
            need = set()
            for f in req:
                need |= {f["id"]} | _parents(fields, f)
            out.append((way, label, _variant(base, "auto_req", fields=[x if x["id"] in need else _keep(x) for x in fields],
                                             verify={**base["verify"], "open_saved": False}), ""))
        elif way == "add_full":
            out.append((way, label, _variant(base, "auto_full", verify={**base["verify"], "new_first_row": True, "open_saved": True}), ""))
        elif way == "edit":
            scn = _scenario_for(base["key"], "edit")
            if scn and not cfg.get("edit_field"):
                c = _variant(base, "auto_edit", operation="edit", target_row="{var:auto_no}", op_button=cfg.get("edit_button") or scn.get("op_button", ""),
                             fields=scn["fields"], flows=[f for f in scn.get("flows") or [] if f["after"] != "__after_save__"],
                             before_save=scn.get("before_save") or [], verify={**scn["verify"], "open_saved": True},
                             add_url=scn.get("add_url") or base["add_url"])
                out.append((way, label + f" (من سيناريو «{scn.get('scenario_name')}»)", c, ""))
                continue
            f = edit_field(cfg, base)
            if not f:
                out.append((way, label, None, "مالقيتش حقل نص أتعدّل فيه — اختاري «حقل التعديل»"))
                continue
            val = cfg.get("edit_value") or ("{rand}" if f["kind"] == "number" else "تعديل آلي {ts}")
            out.append((way, f"تعديل «{f['label']}»", _variant(
                base, "auto_edit", operation="edit", target_row="{var:auto_no}", op_button=cfg.get("edit_button", ""), flows=[],
                fields=[{**f, "strategy": "fixed", "value": val, "depends_on": None, "create_with": ""}],
                verify={**base["verify"], "open_saved": True}), ""))
        elif way == "print":
            scn = _scenario_for(base["key"], "print")
            out.append((way, label, _variant(base, "auto_print", operation="print", target_row="{var:auto_no}", fields=[], flows=[],
                                             op_button=cfg.get("print_button") or (scn or {}).get("op_button", "")), ""))
        elif way == "delete":
            scn = _scenario_for(base["key"], "delete")
            btn = cfg.get("delete_button") or (scn or {}).get("op_button", "")
            out.append((way, label, _variant(base, "auto_delete", operation="delete", target_row="{var:auto_no}",
                                             fields=[], flows=[], op_button=btn), ""))
            out.append((way, "حذف سجل «الإجباري بس»", _variant(base, "auto_delete_req", operation="delete", target_row="{var:auto_req_no}",
                                                              fields=[], flows=[], op_button=btn), "req"))
    return out


def _what(way, res, cfg_v):
    from engine.screen_runner import RUN_VARS
    if res.get("negative_ok"):
        return "اترفض ✓ — " + " | ".join(str(x) for x in (res.get("rejected_with") or []))[:150]
    if res.get("operation") == "print":
        return "صفحة الطباعة فتحت"
    if res.get("operation") == "delete":
        return f"اتحذف ومبقاش في القايمة ({(res.get('row') or '')[:50]})"
    chk = res.get("saved_check") or {}
    extra = f" · راجعت {len(chk.get('rows', []))} قيمة بعد ما فتحته — كلها صح" if chk.get("checked") else ""
    if res.get("operation") == "edit":
        f = cfg_v["fields"][0] if cfg_v["fields"] else {}
        return f"اتعدل «{f.get('label', '')}»" + extra
    return f"اتحفظ — رقم {RUN_VARS.get('saved_no', '—')}" + extra


def run_auto(driver, credentials, cfg, result=None):
    from engine import screen_config
    from engine.screen_runner import run_screen, login, RUN_VARS
    from engine.form_filler import FieldFillError
    result = result if result is not None else {}
    base = screen_config.load(cfg["screen"])
    RUN_VARS.clear()
    login(driver, credentials)
    rows, fails, steps = [], [], plan(cfg, base)
    result["detail"] = {"title": f"🤖 الاختبار الآلي — {base['name_ar']}", "columns": ["#", "الطريقة", "اللي حصل", "المدة (ث)"],
                        "rows": rows, "note": ""}
    result["screenshots"] = []
    logger.info(f"🤖 الاختبار الآلي لـ «{base['name_ar']}»: {len(steps)} خطوة")
    for i, (way, label, c, note) in enumerate(steps, 1):
        if c is None:
            rows.append({"cells": [i, label, "اتخطت: " + note, ""], "ok": SKIP})
            logger.warning(f"⏭️ {label}: {note}")
            continue
        needs = "auto_req_no" if note == "req" else ("auto_no" if way in ("edit", "print", "delete") else None)
        if needs and not RUN_VARS.get(needs):
            if note == "req" and "add_required" not in cfg["ways"]:
                continue
            rows.append({"cells": [i, label, "ما اتشغلتش — الإضافة اللي قبلها ما حفظتش سجل", ""], "ok": SKIP})
            continue
        t0, before = time.time(), RUN_VARS.get("saved_no")
        logger.info(f"🤖 {i}/{len(steps)} {label}")
        try:
            res = run_screen(driver, credentials, c, save=True, do_login=False)
            ok, what = OK, _what(way, res, c)
        except (AssertionError, FieldFillError) as e:
            res = getattr(e, "partial_result", None) or {}
            ok, what = BAD, str(e).split("\n  (Session info")[0]
        except Exception as e:                                   # the browser itself — record it and go on
            res, ok, what = {}, BAD, f"{type(e).__name__}: {str(e).splitlines()[0][:200]}"
        result["screenshots"] += [s for s in (res.get("screenshots") or []) if s][-2:]
        if way in ("add_full", "add_required") and RUN_VARS.get("saved_no") and RUN_VARS.get("saved_no") != before:
            RUN_VARS["auto_no" if way == "add_full" else "auto_req_no"] = RUN_VARS["saved_no"]
            if not ok:
                what += f"\n(السجل اتحفظ برقم {RUN_VARS['saved_no']} — هكمل عليه التعديل والطباعة والحذف)"
        if way == "edit" and ok and RUN_VARS.get("saved_no"):
            RUN_VARS["auto_no"] = RUN_VARS["saved_no"]
        rows.append({"cells": [i, label, what, round(time.time() - t0, 1)], "ok": ok})
        (logger.success if ok else logger.error)(f"{'✅' if ok else '❌'} {label}: {what.splitlines()[0][:200]}")
        if not ok:
            fails.append(f"{label}: {what.splitlines()[0][:200]}")
    done = [r for r in rows if r["ok"] is not SKIP]
    passed = sum(1 for r in done if r["ok"])
    result["detail"]["note"] = f"نجح {passed} من {len(done)}" + (f" · اتخطى {len(rows) - len(done)}" if len(rows) > len(done) else "")
    result["vars"] = {k: v for k, v in RUN_VARS.items() if isinstance(v, (str, int, float))}
    if fails:
        e = AssertionError(f"الاختبار الآلي لـ «{base['name_ar']}»: {len(fails)} من {len(done)} فشلوا\n   " + "\n   ".join(fails))
        e.partial_result = result
        raise e
    if not done:
        e = AssertionError("مفيش ولا طريقة اتشغلت — شوفي سبب التخطي في الجدول")
        e.partial_result = result
        raise e
    logger.success(f"✅ الاختبار الآلي لـ «{base['name_ar']}» نجح كله ({passed} من {len(done)})")
    return result
