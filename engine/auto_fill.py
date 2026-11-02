"""
Complete the form before saving (الاختبار الآلي): after the planned fields are filled, look again at the page and fill
whatever is STILL required and empty — fields that only show up or become required after another choice
(«العميل» after «من», «بناء على» …) — and attach a test file when an attachment box is marked required.
Up to 3 passes, each one can reveal new fields.
"""
import time

from utils.logger import logger

FILES_JS = r"""
function vis(e){ var r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden'; }
var out = [];
document.querySelectorAll('input[type=file]').forEach(function(f, i){
  if (f.closest('.modal, [role=dialog], .ui-dialog, nav, header')) return;
  if (f.files && f.files.length) return;
  if (!(f.required || f.hasAttribute('data-val-required'))) return;     // optional attachments: only if a save asks (engine/heal.py)
  var box = f.closest('.form-group, .row, div') || f.parentElement;
  if (!vis(f) && !(box && vis(box))) return;
  if (!f.id) f.id = '__auto_file_' + i;
  out.push(f.id);
});
return out;
"""
UPLOAD_BTN_JS = r"""
var f = document.getElementById(arguments[0]); if (!f) return '';
var p = f.parentElement, d = 0;
while (p && d < 4) {
  var bs = p.querySelectorAll('button, a.btn, input[type=button]');
  for (var i = 0; i < bs.length; i++) { var t = (bs[i].innerText || bs[i].value || '').replace(/\s+/g, ' ').trim();
    if (/^(رفع|تحميل|ارفع|upload)/i.test(t) && bs[i].getBoundingClientRect().width > 0) { bs[i].click(); return t; } }
  p = p.parentElement; d++;
}
return '';
"""


def _empty(f):
    from engine.text_match import is_placeholder
    v = str(f.get("value") or "").strip()
    return not v or (f["kind"] in ("select", "select2") and is_placeholder(v))


def complete_required(r, passes=3):
    """r = ScreenRunner after the planned fields were filled. Returns the steps it added."""
    from engine.form_inspector import SCAN_JS, FORM_ROOT_JS
    from engine.auto_test import _strategy
    from engine.form_filler import FieldFillError
    d, added, tried = r.driver, [], set()
    for _ in range(passes):
        try:
            root = d.execute_script(FORM_ROOT_JS)
            found = d.execute_script(SCAN_JS, root) or []
        except Exception:
            break
        todo = [f for f in found if f.get("required") and f.get("visible") and not f.get("disabled") and not f.get("in_table")
                and f["kind"] not in ("hidden", "checkbox") and _empty(f) and f["id"] not in tried]
        if not todo:
            break
        for f in todo:
            tried.add(f["id"])
            st, val = _strategy({**f, "value": ""}, "first")
            field = {"id": f["id"], "label": f.get("label") or f["id"], "kind": f["kind"], "strategy": st, "value": val,
                     "required": True, "depends_on": None, "format": "", "timeout": 10, "wait_after": 0.6}
            t0 = time.time()
            try:
                got = r.filler.fill_field(field)
                ok, err = True, None
                logger.success(f"🧩 كمّلت «{field['label']}» = {got} (كان إجباري وفاضي)")
            except (FieldFillError, Exception) as e:
                got, ok, err = None, False, str(e).splitlines()[0][:200]
                logger.warning(f"⚠️ «{field['label']}» إجباري وفاضي ومقدرتش أملاه: {err}")
            step = {"id": f["id"], "label": field["label"] + " (اتملى تلقائي — ظهر إجباري)", "strategy": st, "wanted": val,
                    "result": got, "ok": ok, "seconds": round(time.time() - t0, 1), "auto": True}
            if err:
                step["error"] = err
            r.filler.steps.append(step)
            added.append(step)
            time.sleep(0.8)
    # attachments the form asks for
    try:
        from engine.flows import sample_file
        for fid in d.execute_script(FILES_JS) or []:
            el = d.find_element("id", fid)
            el.send_keys(str(sample_file("pdf")))
            time.sleep(0.8)
            btn = d.execute_script(UPLOAD_BTN_JS, fid)
            if btn:
                time.sleep(2)
                r.accept_js_alert(timeout=1)
            r.filler.steps.append({"id": fid, "label": "مرفق (ملف PDF تجريبي)" + (f" + «{btn}»" if btn else ""), "strategy": "upload",
                                   "wanted": "", "result": "sample_test.pdf", "ok": True, "seconds": 1, "auto": True})
            logger.success(f"📎 رفعت ملف تجريبي في المرفقات{' ودست «' + btn + '»' if btn else ''}")
    except Exception as e:
        logger.warning(f"⚠️ المرفقات: {str(e).splitlines()[0][:150]}")
    return added
