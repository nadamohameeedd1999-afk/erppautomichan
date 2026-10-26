"""
Recorder (سجّلي خطواتك): open the add page in a real Chrome window, the user works on the screen
like she always does, and every change / click is turned into builder rows:
  - a field changed on the form          -> a field row (fixed value)
  - a click on a button                  -> a button row
  - a pop-up that opens after the click  -> its steps (fill, filter, row buttons, «تحديد الكل», close)
  - a value typed in an item line (grid) -> «املى خانة في سطر» (by the column title)
Stops when she presses «⏹ خلصت» (or the save button, or after 20 minutes). Nothing is saved by the recorder:
the click on «حفظ» is blocked and ends the recording.
"""
import time

from utils.logger import logger

REC_JS = r"""
if (window.__rec_on) return 'already';
window.__rec_on = true;
window.__rec = window.__rec || [];
function txt(e){ return (e && (e.innerText || e.textContent || e.value) || '').replace(/\s+/g,' ').trim(); }
function vis(e){ if(!e) return false; var r=e.getBoundingClientRect(), s=getComputedStyle(e);
  return r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none'; }
var POP = '.modal.show, .modal.in, .modal[style*="display: block"], [role=dialog], .ui-dialog';
function popOf(e){ var m = e.closest('.modal, [role=dialog], .ui-dialog'); return m && !m.closest('.swal2-container') ? m : null; }
function labelOf(el){
  if (el.id) { var l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) return txt(l).replace(/\s*\*\s*$/, ''); }
  var p = el.parentElement, d = 0;
  while (p && d < 4) { var ls = p.querySelectorAll('label'), best = null;
    for (var k=0;k<ls.length;k++){ if (ls[k].compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) best = ls[k]; }
    if (best) return txt(best).replace(/\s*\*\s*$/, ''); p = p.parentElement; d++; }
  return el.getAttribute('placeholder') || el.getAttribute('title') || el.id || el.name || '';
}
function colOf(el){
  var td = el.closest('td'), tb = el.closest('table'); if (!td || !tb) return '';
  var idx = 0, c = td; while ((c = c.previousElementSibling)) idx += (c.colSpan || 1);
  var ths = tb.querySelectorAll('thead th, thead td'), k = 0;
  for (var i=0;i<ths.length;i++){ if (k === idx) return txt(ths[i]); k += (ths[i].colSpan || 1); }
  return '';
}
function push(ev){ ev.t = Date.now(); window.__rec.push(ev); }
var last = {};
function onChange(e){
  var el = e.target; if (!el || !el.tagName) return;
  if (el.type === 'file') {
    var fn = el.files && el.files.length ? el.files[0].name : '';
    var ext = (fn.split('.').pop() || 'pdf').toLowerCase();
    push({type: 'upload', id: el.id || '', name: el.name || '', file: ['pdf','png','jpg','jpeg','xlsx','txt'].indexOf(ext) !== -1 ? ext : 'pdf', popup: !!popOf(el)});
    return;
  }
  if (!/^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName) || el.type === 'button' || el.type === 'submit') return;
  if (el.classList.contains('select2-search__field') || el.closest('#__rec_bar')) return;
  var val, kind = 'text';
  if (el.tagName === 'SELECT') { var o = el.options[el.selectedIndex]; val = o ? o.text.trim() : '';
      kind = (el.classList.contains('select2-hidden-accessible') || document.getElementById('select2-' + el.id + '-container')) ? 'select2' : 'select'; }
  else if (el.type === 'checkbox' || el.type === 'radio') { val = el.checked ? 'check' : 'uncheck'; kind = 'checkbox'; }
  else { val = el.value; kind = el.tagName === 'TEXTAREA' ? 'textarea' : (el.type === 'date' || el.type === 'datetime-local' ? 'date' : (el.type === 'number' ? 'number' : 'text')); }
  var sig = (el.id || el.name) + '=' + val;
  if (last.sig === sig && Date.now() - last.t < 800) return; last = {sig: sig, t: Date.now()};
  var inRow = !!el.closest('tbody tr');
  push({type: 'change', id: el.id || '', name: el.name || '', cls: (el.className || '').toString().split(/\s+/).filter(function(c){ return c && !/^(form-control|input-validation|valid|select2)/.test(c); }).slice(0, 3).join('.'),
        label: labelOf(el), kind: kind, value: val, popup: !!popOf(el), in_row: inRow, col: inRow ? colOf(el) : '',
        header_box: el.type === 'checkbox' && !!el.closest('thead'), box_label: el.type === 'checkbox' ? (txt(el.closest('label') || el.parentElement) || '') : ''});
}
document.addEventListener('change', onChange, true);
if (window.jQuery) jQuery(document).on('change', 'select', function(e){ onChange({target: this}); });
document.addEventListener('click', function(e){
  var b = e.target.closest('button, a, .btn, [role=button], [onclick], span.Add-Button');
  if (!b || b.closest('.select2-container, #__rec_bar, .swal2-container')) return;
  if (b.matches('input[type=checkbox]')) return;
  var bt = txt(b);
  if (!popOf(b) && (/^save$/i.test(b.id || '') || /^(حفظ|save|حفظ و جديد|حفظ وجديد)$/i.test(bt))) {
    // the recorder never saves: stop here instead
    e.preventDefault(); e.stopImmediatePropagation();
    push({type: 'click', text: bt, id: b.id || '', cls: '', popup: false, in_row: false});
    window.__rec_stop = true; bar.innerHTML = '✅ وقفت التسجيل عند «حفظ» (من غير ما أحفظ) — ارجعي للوحة التحكم';
    return;
  }
  var row = b.closest('tbody tr');
  push({type: 'click', text: txt(b).slice(0, 50), id: b.id || '', cls: (b.className || '').toString(),
        onclick: (b.getAttribute('onclick') || '').slice(0, 60), popup: !!popOf(b), in_row: !!row,
        row_text: row ? txt(row).slice(0, 80) : '', row_key: row ? txt(row.querySelector('td')).slice(0, 40) : '',
        tag: b.tagName.toLowerCase()});
}, true);
var wasOpen = false;
setInterval(function(){
  var open = Array.prototype.some.call(document.querySelectorAll(POP), function(m){ return !m.closest('.swal2-container') && vis(m.querySelector('.modal-dialog, .modal-content') || m); });
  if (open !== wasOpen) { push({type: open ? 'popup_open' : 'popup_close'}); wasOpen = open; }
}, 300);
var bar = document.createElement('div'); bar.id = '__rec_bar';
bar.innerHTML = '<span style="color:#e11d48;font-size:18px">⏺</span> بسجّل خطواتك… <button type="button" style="margin-inline-start:10px;background:#0F7C7A;color:#fff;border:0;border-radius:8px;padding:6px 14px;cursor:pointer">⏹ خلصت</button>';
bar.style.cssText = 'position:fixed;bottom:16px;left:16px;z-index:2147483647;background:#fff;border:2px solid #0F7C7A;border-radius:12px;padding:8px 12px;font:14px Tahoma,Arial;direction:rtl;box-shadow:0 4px 18px rgba(0,0,0,.2)';
bar.querySelector('button').onclick = function(){ window.__rec_stop = true; bar.innerHTML = '✅ خلصنا — ارجعي للوحة التحكم'; };
document.body.appendChild(bar);
return 'ok';
"""

PULL_JS = "var r = window.__rec || []; window.__rec = []; return {events: r, stop: !!window.__rec_stop, on: !!window.__rec_on};"

_SAVE_WORDS = ("حفظ", "save", "حفظ وجديد")
_FILTER_WORDS = ("المصفي", "مصفي", "بحث", "search", "عرض", "filter", "تصفيه", "تصفية")


def _target(ev):
    """how a step finds this button again: its id, else its text"""
    if ev.get("id"):
        return "#" + ev["id"]
    if "Add-Button" in (ev.get("cls") or ""):
        return "css:span.Add-Button"
    return ev.get("text") or ""


def _field(ev):
    kind = ev["kind"] if ev["kind"] in ("select2", "select", "text", "number", "date", "textarea", "checkbox") else "text"
    if kind == "checkbox":
        return {"id": ev["id"], "label": ev["label"] or ev["id"], "kind": "checkbox", "strategy": ev["value"], "value": ""}
    return {"id": ev["id"] or (f"css:[name='{ev['name']}']" if ev.get("name") else ""), "label": ev["label"] or ev["id"],
            "kind": kind, "strategy": "fixed", "value": ev["value"]}


def convert(events):
    """recorded events -> ordered items: {"type": "field", "field": {...}} / {"type": "action", "label", "target", "steps"}"""
    items, cur, in_pop, field_pos = [], None, False, {}

    def end_action():
        nonlocal cur
        if cur and cur["steps"]:
            items.append(cur)
        cur = None

    for ev in events:
        t = ev["type"]
        if t == "popup_open":
            if cur is None:
                cur = {"type": "action", "label": "نافذة", "target": "", "steps": []}
            cur["steps"].append({"do": "wait_popup"})
            in_pop = True
            continue
        if t == "popup_close":
            if cur is not None and in_pop:
                cur["steps"].append({"do": "close_popup", "optional": True})
            in_pop = False
            continue

        if t == "click":
            txt = (ev.get("text") or "").strip()
            if not in_pop and (ev.get("id", "").lower() == "save" or txt in _SAVE_WORDS):
                break                                              # pressing save ends the recording
            if in_pop and cur is not None:
                if ev.get("in_row"):
                    cur["steps"].append({"do": "row_click", "target": _target(ev) if ev.get("id") else (txt or _target(ev)),
                                         "match": ev.get("row_key") or ""})
                else:
                    cur["steps"].append({"do": "click", "target": _target(ev)})
                    if any(w in txt for w in _FILTER_WORDS):
                        cur["steps"].append({"do": "wait_rows", "min": 1})
                continue
            if ev.get("in_row"):                                   # a button inside a line of the form (delete line…)
                end_action()
                items.append({"type": "action", "label": txt or "زرار في سطر", "target": "", "steps": [
                    {"do": "row_click", "target": _target(ev), "match": ""}]})
                continue
            end_action()
            cur = {"type": "action", "label": txt or ev.get("id") or "زرار", "target": _target(ev), "steps": [{"do": "click", "target": _target(ev)}]}
            continue

        if t == "upload":
            step = {"do": "upload", "target": ("css:#" + ev["id"]) if ev.get("id") else (f"css:input[name='{ev['name']}']" if ev.get("name") else ""),
                    "file": ev.get("file") or "pdf"}
            if cur is not None:
                cur["steps"].append(step)
            else:
                items.append({"type": "action", "label": "رفع مرفق", "target": "", "steps": [step]})
            continue

        if t == "change":
            if in_pop and cur is not None:
                if ev["kind"] == "checkbox":
                    if ev.get("header_box") or "كل" in (ev.get("box_label") or ""):
                        cur["steps"].append({"do": "check", "target": ev.get("box_label") or "css:thead input[type=checkbox]"})
                    elif ev.get("in_row"):
                        prev = cur["steps"][-1] if cur["steps"] else {}
                        if prev.get("do") == "pick_rows":
                            prev["count"] += 1
                        else:
                            cur["steps"].append({"do": "pick_rows", "count": 1})
                    continue
                f = _field(ev)
                if f["id"]:
                    if f["kind"] == "date":
                        f["value"] = ev["value"]
                    # same field changed again -> keep the last value
                    if cur["steps"] and cur["steps"][-1].get("do") == "fill" and cur["steps"][-1]["field"]["id"] == f["id"]:
                        cur["steps"][-1]["field"] = f
                    else:
                        cur["steps"].append({"do": "fill", "field": f})
                continue
            if ev.get("in_row") and (ev.get("col") or ev.get("cls")):
                cell = ev["col"] or ("css:input." + ev["cls"].split(".")[0])
                step = {"do": "fill_cell", "cell": cell, "row": "last", "value": ev["value"]}
                if cur is not None and not in_pop:
                    cur["steps"].append(step)
                    continue
                last = items[-1] if items else None
                if last and last["type"] == "action":
                    last["steps"].append(step)
                else:
                    items.append({"type": "action", "label": "سطور الأصناف", "target": "", "steps": [step]})
                continue
            end_action()
            f = _field(ev)
            if not f["id"]:
                continue
            if f["id"] in field_pos:                               # changed again: update, keep the first place
                items[field_pos[f["id"]]]["field"] = f
            else:
                field_pos[f["id"]] = len(items)
                items.append({"type": "field", "field": f})
    end_action()
    # a pop-up step list without the button that opened it (opened by a field) -> first step = that pop-up
    return items


def record(driver, max_minutes=20, poll=0.7):
    """inject, collect until «خلصت» / save / timeout. Returns all events."""
    events, end = [], time.time() + max_minutes * 60
    driver.execute_script(REC_JS)
    logger.info("⏺ بسجّل — اشتغلي على الشاشة في نافذة Chrome، ولما تخلصي دوسي «⏹ خلصت» (أو زرار الحفظ)")
    while time.time() < end:
        try:
            res = driver.execute_script(PULL_JS) or {}
        except Exception as e:
            if "alert" in str(e).lower():
                try:
                    driver.switch_to.alert.accept()
                except Exception:
                    pass
                continue
            logger.warning(f"المتصفح اتقفل: {str(e)[:80]}")
            break
        if not res.get("on"):                                      # page changed (reload / navigation): re-inject
            time.sleep(1)
            try:
                driver.execute_script(REC_JS)
            except Exception:
                pass
        for ev in res.get("events") or []:
            events.append(ev)
            if ev["type"] == "change":
                logger.info(f"   ✏️ {ev.get('label') or ev.get('id')} = {str(ev.get('value'))[:40]}")
            elif ev["type"] == "upload":
                logger.info(f"   📎 ملف ({ev.get('file')})")
            elif ev["type"] == "click":
                logger.info(f"   👆 {ev.get('text') or ev.get('id')}")
                if not ev.get("popup") and (ev.get("id", "").lower() == "save" or (ev.get("text") or "").strip() in _SAVE_WORDS):
                    logger.info("💾 دوستي حفظ — وقفت التسجيل")
                    return events
            else:
                logger.info(f"   🪟 {'نافذة اتفتحت' if ev['type'] == 'popup_open' else 'النافذة اتقفلت'}")
        if res.get("stop"):
            logger.info("⏹ خلصتي التسجيل")
            break
        time.sleep(poll)
    return events
