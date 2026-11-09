// Generated from engine/recorder.py REC_JS — the same recorder the dashboard uses
function __nqStartRecording(){

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

}
