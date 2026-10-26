"""
Tests for a record that already exists in the list (beside «إضافة جديد»):

  edit   (تعديل) : list -> the row -> edit button -> change fields -> save -> saved? (+ open it again and compare)
  delete (حذف)   : list -> the row -> delete button -> confirm -> the row is gone from the list
  print  (طباعة) : list -> the row -> print button -> a print page / PDF opened, not empty, no server error

The row: cfg["target_row"] = text in the row (a voucher number, a name, {var:saved_no} from a chain), empty = first row.
The button: cfg["op_button"] = CSS selector or its text/title; empty = found automatically.
"""
import time

import allure

from engine.flows import FlowRunner, resolve_value, fill_with_flows
from engine.form_filler import FieldFillError
from utils.logger import logger

OP_NAMES = {"edit": "تعديل", "delete": "حذف", "print": "طباعة"}

# arguments: match text ('' = first row), kind ('edit'|'delete'|'print'), button (css or text, '' = auto), click(bool)
ROW_ACTION_JS = r"""
function N(t){ return String(t||'').toLowerCase().replace(/[ً-ْٰ]/g,'').replace(/[أإآٱ]/g,'ا').replace(/[ىئ]/g,'ي')
  .replace(/ة/g,'ه').replace(/\s+/g,' ').trim(); }
function cells(r){ return Array.prototype.map.call(r.querySelectorAll('td'), function(td){ return (td.innerText||'').replace(/\s+/g,' ').trim(); }); }
var match = arguments[0], kind = arguments[1], button = arguments[2], doClick = arguments[3];
var rows = Array.prototype.filter.call(document.querySelectorAll('table tbody tr'), function(r){
  return r.querySelectorAll('td').length > 1 && r.getBoundingClientRect().height > 0 && !/dataTables_empty/.test(r.innerHTML); });
if (!rows.length) return {error: 'empty'};
var row = null;
if (!match) row = rows[0];
else {
  var w = N(match);
  for (var i = 0; i < rows.length && !row; i++) if (cells(rows[i]).some(function(c){ return N(c) === w; })) row = rows[i];
  for (var i = 0; i < rows.length && !row; i++) if (N(rows[i].innerText).indexOf(w) !== -1) row = rows[i];
}
if (!row) return {error: 'no_row', count: rows.length};
var c = cells(row), id = c.filter(function(x){ return x; })[0] || '';
var PAT = {
  edit:   "a[href*='Edit'], a[href*='edit'], [onclick*='Edit'], [onclick*='edit'], .btn-edit, .edit, .fa-edit, .fa-pencil, .fa-pen, .bi-pencil, .bi-pencil-square, [title*='تعديل'], [data-original-title*='تعديل'], [title*='Edit']",
  delete: "a[href*='Delete'], a[href*='delete'], [onclick*='Delete'], [onclick*='delete'], [onclick*='Remove'], .btn-delete, .delete, .fa-trash, .fa-trash-o, .fa-trash-alt, .bi-trash, .bi-trash3, [title*='حذف'], [data-original-title*='حذف'], [title*='Delete']",
  print:  "a[href*='Print'], a[href*='print'], [onclick*='Print'], [onclick*='print'], .btn-print, .fa-print, .bi-printer, [title*='طباعة'], [data-original-title*='طباعة'], [title*='Print']"
};
var WORD = {edit: ['تعديل', 'edit'], delete: ['حذف', 'delete'], print: ['طباعه', 'print']};
var el = null;
if (button) {
  if (/^(css:|[#.\[]|[a-z]+[#.\[])/i.test(button)) { try { el = row.querySelector(button.replace(/^css:/i, '')); } catch(e) {} }
  if (!el) { var bw = N(button);
    row.querySelectorAll('a, button, [onclick], i, span').forEach(function(e){ if (el) return;
      var t = N(e.innerText || e.getAttribute('title') || e.getAttribute('data-original-title') || e.getAttribute('aria-label'));
      if (t && (t === bw || t.indexOf(bw) !== -1)) el = e; }); }
} else {
  el = row.querySelector(PAT[kind]);
  if (!el) row.querySelectorAll('a, button, [onclick]').forEach(function(e){ if (el) return;
      var t = N(e.innerText || e.getAttribute('title') || e.getAttribute('data-original-title') || '');
      if (WORD[kind].some(function(k){ return t.indexOf(k) !== -1; })) el = e; });
}
if (!el) return {error: 'no_button', row: N(row.innerText).slice(0, 160), id: id};
var target = el.closest('a, button, [onclick]') || el;
if (kind === 'edit' && target.tagName === 'A') {
  var h = target.getAttribute('href') || '';
  if (h && h !== '#' && h.indexOf('javascript') !== 0) return {ok: true, href: target.href, row: (row.innerText||'').replace(/\s+/g,' ').trim().slice(0, 200), id: id};
}
if (doClick) { target.scrollIntoView({block: 'center'}); target.click(); }
return {ok: true, clicked: !!doClick, row: (row.innerText||'').replace(/\s+/g,' ').trim().slice(0, 200), id: id};
"""

SEARCH_JS = r"""
var q = arguments[0];
var box = document.querySelector(".dataTables_filter input, input[type=search], input[name*='search' i], input[id*='search' i], input[placeholder*='بحث'], input[placeholder*='Search' i]");
if (!box) return false;
box.focus(); box.value = q;
['input', 'keyup', 'change'].forEach(function(t){ box.dispatchEvent(new Event(t, {bubbles: true})); });
box.dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', keyCode: 13, bubbles: true}));
return true;
"""

ROW_EXISTS_JS = r"""
function N(t){ return String(t||'').toLowerCase().replace(/\s+/g,' ').trim(); }
var w = N(arguments[0]);
return Array.prototype.some.call(document.querySelectorAll('table tbody tr td'), function(td){ return N(td.innerText) === w; });
"""

# a confirm box that is not SweetAlert (bootstrap modal / bootbox): press yes / delete / ok
CONFIRM_JS = r"""
function vis(e){ var r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; }
var box = Array.prototype.filter.call(document.querySelectorAll('.modal.show, .modal.in, .bootbox, [role=dialog]'), function(e){
  return vis(e) && !e.closest('.swal2-container'); }).pop();      // SweetAlert is handled by handle_swals
if (!box) return null;
var btns = box.querySelectorAll('button, a.btn, input[type=button], input[type=submit]');
for (var i = 0; i < btns.length; i++) {
  var t = (btns[i].innerText || btns[i].value || '').trim();
  if (vis(btns[i]) && /^(نعم|موافق|تأكيد|تاكيد|حذف|احذف|yes|ok|confirm|delete)/i.test(t)) { btns[i].click(); return t; }
}
return null;
"""


def _row_action(r, cfg, kind, match, click=True, tries=2):
    d = r.driver
    res = {}
    for i in range(tries):
        res = d.execute_script(ROW_ACTION_JS, match, kind, cfg.get("op_button") or "", click) or {}
        if res.get("ok") or res.get("error") == "no_button":
            break
        if match and res.get("error") == "no_row" and d.execute_script(SEARCH_JS, match):   # not on page 1 -> list search
            logger.info(f"🔎 بدوّر على «{match}» في بحث القايمة")
            time.sleep(2.5)
            r.wait_for_preloader()
            continue
        time.sleep(2)
    if res.get("ok"):
        return res
    err = res.get("error")
    if err == "empty":
        raise AssertionError("القايمة فاضية — مفيش سجل أعمل عليه " + OP_NAMES[kind])
    if err == "no_row":
        raise AssertionError(f"مالقيتش صف فيه «{match}» في القايمة")
    raise AssertionError(f"مالقيتش زرار {OP_NAMES[kind]} في الصف" + (f" (المحدد: «{cfg['op_button']}»)" if cfg.get("op_button") else
                         " — حددي الزرار في «زرار العملية» (selector أو اسمه)") + f"\n   الصف: {res.get('row', '')}")


def _open_list(r, cfg):
    from engine.screen_runner import _abs
    r.driver.get(_abs(cfg["list_url"]))
    r.wait_for_preloader()
    time.sleep(1.5)


def run_operation(r, cfg, result, save, start):
    """r = ScreenRunner (already logged in). Returns the result dict, raises AssertionError on failure."""
    from engine.screen_runner import RUN_VARS, _shot, _same, READ_VALUES_JS
    op = cfg["operation"]
    d = r.driver
    match = resolve_value(cfg.get("target_row") or "", RUN_VARS)
    result["operation"] = op
    who = f"«{match}»" if match else "أول صف"

    with allure.step(f"فتح القايمة واختيار السجل ({who})"):
        _open_list(r, cfg)

    # ------------------------------------------------------------- print
    if op == "print":
        with allure.step("طباعة"):
            before, url0 = set(d.window_handles), d.current_url
            hit = _row_action(r, cfg, "print", match)
            logger.info(f"🖨️ ضغطت طباعة في الصف: {hit.get('row', '')[:100]}")
            try:
                msg = FlowRunner(r, r.filler).verify_print(before, url0, 20)
            except Exception as e:
                result["screenshots"].append(_shot(r, f"{cfg['key']}_print_failed"))
                raise AssertionError(f"الطباعة فشلت: {e}") from None
        result.update({"printed": True, "row": hit.get("row"), "seconds": round(time.time() - start, 1)})
        logger.success(f"✅ {cfg['name_ar']}: {msg} ({result['seconds']} ثانية)")
        return result

    # ------------------------------------------------------------- delete
    if op == "delete":
        hit = _row_action(r, cfg, "delete", match, click=save)
        rid = hit.get("id") or ""
        result["row"] = hit.get("row")
        logger.info(f"🗑️ السجل: {hit.get('row', '')[:120]}")
        if not save:
            result["screenshots"].append(_shot(r, f"{cfg['key']}_delete_target"))
            logger.success("لقيت السجل وزرار الحذف (تجربة — ماحذفتش)")
            result["seconds"] = round(time.time() - start, 1)
            return result
        with allure.step("تأكيد الحذف"):
            time.sleep(0.8)
            end, handled = time.time() + 8, 0          # confirm box, then the result message (may come late)
            while time.time() < end and handled < 6:
                n = r.handle_swals(max_count=1, timeout=1.5, max_misses=1)
                t = d.execute_script(CONFIRM_JS)
                if t:
                    logger.info(f"ضغطت «{t}» في نافذة التأكيد")
                    time.sleep(1)
                if n or t:
                    handled += 1
                    end = max(end, time.time() + 4)
                else:
                    time.sleep(0.5)
            result["screenshots"].append(_shot(r, f"{cfg['key']}_after_delete"))
        seen = " | ".join(r.alerts)
        if cfg.get("expect_error"):
            from engine.text_match import normalize as _n
            if _n(cfg["expect_error"]) in _n(seen + " " + " ".join(r.page_errors())):
                result.update({"negative_ok": True, "seconds": round(time.time() - start, 1)})
                logger.success(f"✅ الحذف اترفض صح بالرسالة «{cfg['expect_error']}»")
                return result
            raise AssertionError(f"المفروض الحذف يترفض برسالة «{cfg['expect_error']}» — اللي ظهر: {seen or 'مفيش رسالة'}")
        if r.error_alerts:
            raise AssertionError("الحذف اترفض: " + " | ".join(r.error_alerts))
        with allure.step("التأكد إن السجل اتشال من القايمة"):
            gone = False
            for _ in range(6):
                _open_list(r, cfg)
                key = match or rid
                if match:
                    d.execute_script(SEARCH_JS, match)
                    time.sleep(2)
                if not key or not d.execute_script(ROW_EXISTS_JS, key):
                    gone = True
                    break
                time.sleep(2)
            result["screenshots"].append(_shot(r, f"{cfg['key']}_list_after_delete"))
            if not gone:
                raise AssertionError(f"السجل «{match or rid}» لسه موجود في القايمة بعد الحذف" + (f"\n   الرسايل: {seen}" if seen else ""))
        result.update({"deleted": True, "seconds": round(time.time() - start, 1)})
        logger.success(f"✅ {cfg['name_ar']}: «{match or rid}» اتحذف ومبقاش في القايمة ({result['seconds']} ثانية)")
        return result

    # ------------------------------------------------------------- edit
    with allure.step("فتح التعديل"):
        hit = _row_action(r, cfg, "edit", match)
        rid = hit.get("id") or ""
        result["row"] = hit.get("row")
        if hit.get("href"):
            d.get(hit["href"])
        r.wait_for_preloader(timeout=20)
        time.sleep(2.5)
        r.accept_js_alert(timeout=1)
        from urllib.parse import urlparse
        r.form_path = urlparse(d.current_url).path.lower()
        logger.info(f"✏️ فتحت تعديل: {hit.get('row', '')[:100]} → {d.current_url}")

    with allure.step("تعديل الحقول"):
        try:
            fill_with_flows(r, cfg, r.filler, result["screenshots"])
        except Exception as e:
            result["steps"] = r.filler.steps
            e.partial_result = result
            raise
        result["steps"] = r.filler.steps
        result["screenshots"].append(_shot(r, f"{cfg['key']}_before_save"))
    if not save:
        logger.success("تم التعديل في الفورم (تجربة بدون حفظ)")
        result["seconds"] = round(time.time() - start, 1)
        return result

    with allure.step("حفظ التعديل"):
        r.run_before_save()
        r.save()
        ok = r.wait_saved()
        result["screenshots"].append(_shot(r, f"{cfg['key']}_after_save"))
        if not ok:
            raise AssertionError(f"حفظ التعديل ما نجحش. URL: {d.current_url}\n   {r.failure_reason()}")
        result["saved"] = True
    if rid:
        RUN_VARS["saved_no"] = rid
        RUN_VARS[f"{cfg['key']}.saved_no"] = rid

    if cfg["verify"].get("open_saved"):
        with allure.step("فتح السجل تاني ومراجعة التعديل"):
            want = {s["id"]: s for s in result["steps"] if s.get("ok") and s.get("result") not in (None, "")}
            _open_list(r, cfg)
            again = _row_action(r, cfg, "edit", rid or match)
            if again.get("href"):
                d.get(again["href"])
            r.wait_for_preloader(timeout=20)
            time.sleep(2.5)
            got = d.execute_script(READ_VALUES_JS, list(want)) or {}
            rows, bad = [], []
            for k, s in want.items():
                v = got.get(k)
                ok = v is None or _same(s["result"], v)
                rows.append({"label": s["label"], "filled": s["result"], "saved": v, "ok": ok})
                logger.info(f"{'✅' if ok else '❌'} مراجعة {s['label']}: اتملى '{s['result']}' — اتسجل '{v}'")
                if not ok:
                    bad.append(f"{s['label']}: اتعدل لـ '{s['result']}' بس اتسجل '{v}'")
            result["saved_check"] = {"checked": True, "rows": rows, "mismatches": bad}
            _shot(r, f"{cfg['key']}_edited_record")
            if bad:
                raise AssertionError("التعديل ما اتسجلش صح:\n   " + "\n   ".join(bad))

    result["seconds"] = round(time.time() - start, 1)
    logger.success(f"✅ {cfg['name_ar']}: اتعدل واتحفظ ({result['seconds']} ثانية)")
    return result
