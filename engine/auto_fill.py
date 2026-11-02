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


LINE_ITEMS_JS = r"""
const done = arguments[arguments.length - 1];
(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const PH = /^\s*(-+\s*)?(اختر|اختار|إختر|select|choose)/i;
  const txt = e => (e && (e.innerText || e.textContent) || '').replace(/\s+/g, ' ').trim();
  const fire = (e, v) => { if (window.jQuery) { jQuery(e).val(v).trigger('input').trigger('change').trigger('blur'); }
                           else { e.value = v; ['input', 'change', 'blur'].forEach(t => e.dispatchEvent(new Event(t, {bubbles: true}))); } };
  const nm = e => ((e.getAttribute('data-name') || '') + ' ' + (e.name || '') + ' ' + (e.className || '') + ' ' + (e.placeholder || '')).toLowerCase();
  const out = [];
  try {
    // 1) «details» block: an entry row (.newRowData) above an empty table + «إضافة» (.addNewRow) moves it into the table
    for (const box of document.querySelectorAll('.details')) {
      const tb = box.querySelector('table tbody'), btn = box.querySelector('.addNewRow');
      if (!tb || !btn || tb.querySelectorAll('tr').length || btn.getBoundingClientRect().width === 0) continue;
      const ins = Array.from(box.querySelectorAll('.newRowData input, .newRowData select, .newRowData textarea'))
        .filter(e => e.type !== 'hidden' && !e.readOnly && !e.disabled);
      if (!ins.length) continue;
      for (const e of ins) {
        if (e.type === 'checkbox' || (e.value && !(e.tagName === 'SELECT' && PH.test(txt(e.options[e.selectedIndex]))))) continue;
        if (e.tagName === 'SELECT') { const o = Array.from(e.options).find(o => o.value && !PH.test(o.text)); if (o) fire(e, o.value); }
        else if (/date/.test(e.type)) fire(e, new Date().toISOString().slice(0, 10));
        else fire(e, /qty|quantity|كمي|عدد/.test(nm(e)) ? '1' : (/disc|خصم/.test(nm(e)) ? '0' : '100'));
        await sleep(300);
      }
      btn.click(); await sleep(900);
      const n = tb.querySelectorAll('tr').length;
      const head = Array.from(box.querySelectorAll('thead th')).slice(0, 3).map(txt).join(' / ');
      out.push(n ? `أضفت سطر في جدول «${head}»` : `دست «إضافة» في جدول «${head}» بس السطر ما اتضافش`);
    }
    // 2) items grid with an item-search popup (فواتير / أوامر / عروض أسعار): search, choose the first item, quantity 1
    const grid = Array.from(document.querySelectorAll('table')).find(t => t.querySelector('.itemId, .item-name') && t.querySelector('.quantity'));
    const filled = grid && Array.from(grid.querySelectorAll('.itemId')).some(e => e.value);
    if (grid && !filled && document.getElementById('itemSearchModal') && (typeof window.appendSearch === 'function' || document.getElementById('submitSearch'))) {
      if (window.jQuery) jQuery('#itemSearchModal').modal('show');
      await sleep(700);
      if (typeof window.appendSearch === 'function') window.appendSearch(1); else document.getElementById('submitSearch').click();
      let b = null;
      for (let i = 0; i < 40 && !b; i++) { await sleep(400); b = document.querySelector('#itemSearchModal tbody tr button, #items-prices-quantities tr button'); }
      if (!b) { out.push('فتحت بحث الأصناف بس مفيش أصناف ظهرت (اتأكدي إن فيه أصناف ليها سعر في المخزن / الفرع ده)'); }
      else {
        const name = txt(b.closest('tr')).slice(0, 60);
        b.click(); await sleep(2200);
        const sw = document.querySelector('.swal2-confirm'); if (sw && /اول|أول|first/.test(txt(document.querySelector('.swal2-popup')))) sw.click();
        const row = Array.from(grid.querySelectorAll('tr')).reverse().find(tr => tr.querySelector('.itemId') && tr.querySelector('.itemId').value);
        if (!row) out.push(`اخترت «${name}» من بحث الأصناف بس الصنف ما نزلش في الجدول`);
        else {
          const q = row.querySelector('.quantity'), p = row.querySelector('.price');
          if (q && !(parseFloat(String(q.value).replace(/,/g, '')) > 0)) { fire(q, '1'); await sleep(500); }
          if (p && !(parseFloat(String(p.value).replace(/,/g, '')) > 0) && !p.readOnly) { fire(p, '100'); await sleep(500); }
          out.push(`اخترت صنف «${(row.querySelector('.item-name') || {}).value || name}» من بحث الأصناف — الكمية ${q ? q.value : '—'} · السعر ${p ? p.value : '—'}`);
        }
      }
      if (window.jQuery) jQuery('#itemSearchModal').modal('hide');
    }
  } catch (e) { out.push('⚠️ الأصناف: ' + e); }
  done(out);
})();
"""


def add_line_items(r):
    """invoices / orders: put one line in the items table (the ERP rejects a document without lines)"""
    d = r.driver
    try:
        d.set_script_timeout(60)
        did = d.execute_async_script(LINE_ITEMS_JS) or []
    except Exception as e:
        did = [f"⚠️ الأصناف: {str(e).splitlines()[0][:150]}"]
    for x in did:
        (logger.success if not x.startswith("⚠️") and "ما " not in x else logger.warning)(f"🧾 {x}")
        r.filler.steps.append({"id": "__items", "label": "🧾 " + x, "strategy": "flow", "wanted": "", "result": x,
                               "ok": not x.startswith("⚠️") and "ما " not in x and "مفيش" not in x, "seconds": 1, "auto": True})
    try:
        while r.accept_js_alert(timeout=0.8) is not None:
            pass
        r.handle_swals(max_count=2, timeout=1, max_misses=1)
    except Exception:
        pass
    return did


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
    add_line_items(r)
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
