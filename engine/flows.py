"""
Flows (إجراءات داخل الشاشة) — buttons and pop-up windows in the middle of a form.

Example — Sales invoice «ربط بمستند آخر»:
    click «ربط بمستند اخر» -> wait for the pop-up -> fill its fields (branch, document type, dates)
    -> click «المصفي» -> wait for the table rows -> tick «تحديد الكل» -> click «إضافة» -> close
then the normal test continues (other fields, save, checks).

Config (inside a screen / scenario config):
    "flows": [{
        "name": "ربط بمستند آخر",
        "after": "CustomerId",      # run right after this field ("" = after all fields, before save)
        "optional": false,          # true = if it fails, warn and continue
        "steps": [
            {"do": "click", "target": "ربط بمستند اخر"},
            {"do": "wait_popup"},
            {"do": "fill", "field": {"id": "DocumentType", "kind": "select2", "strategy": "fixed", "value": "سندات صرف المخازن"}},
            {"do": "click", "target": "المصفي"},
            {"do": "wait_rows", "min": 1},
            {"do": "check", "target": "تحديد الكل"},
            {"do": "click", "target": "إضافة"},
            {"do": "close_popup"}
        ]
    }]

A target is the text written on the button / label (Arabic spelling differences like أ/ا ى/ي ة/ه
don't matter) or a CSS selector (starting with # . [ or written as css:...).
While a pop-up is open, targets are searched inside it first.
"""
import re
import time

from utils.logger import logger
from engine.form_filler import FieldFillError

# do -> Arabic label (dashboard + logs)
STEP_TYPES = {
    "click": "اضغط على",
    "wait_popup": "استنى النافذة تفتح",
    "fill": "املى حقل",
    "wait_rows": "استنى صفوف الجدول",
    "check": "علّم على",
    "pick_rows": "اختار أول صفوف",
    "close_popup": "اقفل النافذة",
    "expect_text": "اتأكد إن النص ظاهر",
    "wait": "استنى ثواني",
    "row_click": "اضغط زرار جوه صف",
    "fill_cell": "املى خانة في سطر",
    "upload": "ارفع ملف",
    "remember": "احفظ قيمة في متغير",
    "assert": "اتأكد من حسبة/قيمة",
    "check_print": "اطبع واتأكد إن الطباعة فتحت",
    "check_journal": "افتح القيد واتأكد إنه متزن",
}
NEEDS_TARGET = {"click", "check", "expect_text"}
SAMPLE_FILES = ("pdf", "png", "jpg", "xlsx", "txt")

_CSS_LIKE = re.compile(r"^(css:|[#.\[]|[a-z][a-z0-9-]*[#.\[:])", re.I)

# ---------------------------------------------------------------- JS helpers
COMMON_JS = r"""
function N(t){ return String(t||'').toLowerCase().replace(/[ً-ْٰ]/g,'')
  .replace(/[أإآٱ]/g,'ا').replace(/[ىئ]/g,'ي').replace(/ة/g,'ه').replace(/ؤ/g,'و').replace(/ـ/g,'')
  .replace(/[*:]/g,' ').replace(/\s+/g,' ').trim(); }
function vis(e){ if(!e) return false; var r=e.getBoundingClientRect(), s=getComputedStyle(e);
  return r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none' && s.opacity!=='0'; }
function popups(){
  var sel='.modal.show, .modal.in, .modal[style*="display: block"], [role=dialog], .ui-dialog, .k-window, .bootbox';
  var out=[]; document.querySelectorAll(sel).forEach(function(m){
    if (m.closest('.swal2-container')) return;
    var box = m.querySelector('.modal-dialog, .modal-content') || m;
    if (vis(box) && out.indexOf(m)===-1) out.push(m); });
  out.sort(function(a,b){ return (parseInt(getComputedStyle(a).zIndex)||0)-(parseInt(getComputedStyle(b).zIndex)||0); });
  return out;
}
function topPopup(){ var p=popups(); return p.length ? p[p.length-1] : null; }
function txt(e){ return (e.innerText||e.textContent||e.value||'').replace(/\s+/g,' ').trim(); }
"""

FIND_JS = COMMON_JS + r"""
var target = arguments[0], want = arguments[1];            // want: 'click' | 'check' | 'any'
var pop = topPopup(), scopes = pop ? [pop, document] : [document];
function bycss(sel){
  for (var s=0;s<scopes.length;s++){ var els=scopes[s].querySelectorAll(sel);
    for (var i=0;i<els.length;i++) if (vis(els[i]) || els[i].type==='checkbox') return els[i]; }
  return null; }
function checkboxNear(e){
  if (!e) return null;
  if (e.tagName==='INPUT' && e.type==='checkbox') return e;
  if (e.control && e.control.type==='checkbox') return e.control;
  var c = e.querySelector && e.querySelector('input[type=checkbox]'); if (c) return c;
  var p=e.parentElement, d=0;
  while (p && d<3){ c=p.querySelector('input[type=checkbox]'); if (c) return c; p=p.parentElement; d++; }
  return null; }
var isCss = /^css:/i.test(target);
if (isCss || /^[#.\[]/.test(target) || /^[a-z][a-z0-9-]*[#.\[:]/i.test(target)){
  var el = bycss(isCss ? target.slice(4) : target);
  return want==='check' ? checkboxNear(el) : el; }
var w = N(target); if (!w) return null;
var q = want==='check' ? 'label, th, td, span, div, input[type=checkbox]'
      : (want==='click' ? 'button, a, input[type=button], input[type=submit], .btn, [role=button], [onclick], label, span'
                        : 'body *');
for (var pass=0; pass<2; pass++){                 // 0 = exact text, 1 = contains
  for (var s=0;s<scopes.length;s++){
    var best=null, bestLen=1e9, els=scopes[s].querySelectorAll(q);
    for (var i=0;i<els.length;i++){
      var e=els[i]; if (e.closest('.select2-container, .swal2-container, nav, .navbar, header')) continue;
      var t = N(txt(e) || e.getAttribute('title') || e.getAttribute('aria-label') || '');
      if (!t) continue;
      if (pass===0 ? t!==w : t.indexOf(w)===-1) continue;
      if (want!=='check' && !vis(e)) continue;
      if (t.length < bestLen){ best=e; bestLen=t.length; }   // innermost / shortest match
    }
    if (best){
      if (want==='check') return checkboxNear(best);
      var b = best.closest('button, a, .btn, [role=button]'); return b || best;
    }
  }
}
return null;
"""

POPUP_JS = COMMON_JS + r"""
var p = topPopup(); if (!p) return null;
var title = p.querySelector('.modal-title, .ui-dialog-title, h4, h5');
return {title: title ? txt(title) : '', count: popups().length};
"""

ROWS_JS = COMMON_JS + r"""
// real data rows of the most relevant table (inside the pop-up if one is open)
var scope = arguments[0] ? document.querySelector(arguments[0]) : (topPopup() || document);
if (!scope) return {rows: 0, tables: 0, empty_text: ''};
var tables = scope.tagName==='TABLE' ? [scope] : Array.prototype.slice.call(scope.querySelectorAll('table'));
var best = 0, emptyText = '';
tables.forEach(function(t){
  if (!vis(t)) return;
  var n = 0;
  t.querySelectorAll('tbody tr').forEach(function(tr){
    if (!vis(tr)) return;
    var tds = tr.querySelectorAll('td');
    if (!tds.length) return;
    if (tds.length===1 && (tds[0].colSpan>1 || tr.querySelector('.dataTables_empty'))) { emptyText = txt(tr); return; }
    var t2 = N(txt(tr));
    if (/لا توجد|لا يوجد|no data|no matching|no records/.test(t2)) { emptyText = txt(tr); return; }
    n++;
  });
  if (n > best) best = n;
});
return {rows: best, tables: tables.length, empty_text: emptyText};
"""

PICK_ROWS_JS = COMMON_JS + r"""
var n = arguments[0], scope = topPopup() || document, done = 0;
var boxes = scope.querySelectorAll('tbody tr input[type=checkbox]');
for (var i=0;i<boxes.length && done<n;i++){ var b=boxes[i]; if (!b.checked) b.click(); if (b.checked) done++; }
return done;
"""

CLOSE_JS = COMMON_JS + r"""
var p = topPopup(); if (!p) return 'none';
var b = p.querySelector('[data-dismiss=modal], [data-bs-dismiss=modal], .close, .btn-close, .ui-dialog-titlebar-close');
if (b && vis(b)) { b.click(); return 'button'; }
if (window.jQuery && jQuery(p).modal) { try { jQuery(p).modal('hide'); return 'jquery'; } catch(e){} }
p.style.display='none'; p.classList.remove('show','in');
document.querySelectorAll('.modal-backdrop').forEach(function(x){ x.remove(); });
document.body.classList.remove('modal-open'); return 'forced';
"""

JOURNAL_JS = COMMON_JS + r"""
// a journal entry table: columns «مدين / Debit» and «دائن / Credit» -> totals + each line (in a pop-up first)
function num(v){ var t = String(v||'').replace(/[٠-٩]/g, function(d){ return '٠١٢٣٤٥٦٧٨٩'.indexOf(d); })
  .replace(/[٬,]/g,'').replace(/٫/g,'.'); var m = t.match(/-?\d+(\.\d+)?/); return m ? parseFloat(m[0]) : 0; }
function cellVal(td){ var f = td.querySelector('input, select'); return f ? (f.value||'') : txt(td); }
var scopes = topPopup() ? [topPopup(), document] : [document];
for (var s=0; s<scopes.length; s++){
  var tables = scopes[s].querySelectorAll('table');
  for (var t=0; t<tables.length; t++){
    var tb = tables[t]; if (!vis(tb)) continue;
    var ths = tb.querySelectorAll('thead th, thead td'); if (!ths.length) ths = (tb.rows[0] ? tb.rows[0].cells : []);
    var dc = -1, cc = -1, idx = 0;
    for (var h=0; h<ths.length; h++){ var x = N(txt(ths[h]));
      if (dc === -1 && /مدين|debit|\bdr\b/.test(x)) dc = idx;
      else if (cc === -1 && /دائن|داين|credit|\bcr\b/.test(x)) cc = idx;
      idx += (ths[h].colSpan || 1); }
    if (dc === -1 || cc === -1) continue;
    var lines = [], dr = 0, cr = 0, total = null;
    Array.prototype.forEach.call(tb.querySelectorAll('tbody tr'), function(tr){
      if (!vis(tr) || tr.closest('thead')) return;
      var tds = tr.children, k = 0, d = null, c = null;
      for (var i=0; i<tds.length; i++){ if (k === dc) d = num(cellVal(tds[i])); if (k === cc) c = num(cellVal(tds[i])); k += (tds[i].colSpan || 1); }
      if (d === null && c === null) return;
      var line = txt(tr);
      if (/^(الاجمالي|الإجمالي|اجمالي|إجمالي|المجموع|total)/.test(N(txt(tds[0])))) { total = {debit: d||0, credit: c||0}; return; }
      dr += d || 0; cr += c || 0; lines.push({text: line.slice(0, 160), debit: d || 0, credit: c || 0});
    });
    if (!lines.length) continue;
    return {found: true, debit: Math.round(dr*100)/100, credit: Math.round(cr*100)/100, lines: lines.slice(0, 60), total: total,
            title: (document.querySelector('h1,h2,h3,h4,.modal-title') ? txt(document.querySelector('.modal.show .modal-title, h1, h2, h3, h4')) : document.title)};
  }
}
return {found: false};
"""

TEXT_PRESENT_JS = COMMON_JS + "return N(document.body.innerText).indexOf(N(arguments[0])) !== -1;"

ROW_CLICK_JS = COMMON_JS + r"""
// click a button inside a table row: the row that contains `match` (or the first row that has the button)
var target = arguments[0] || '', match = arguments[1] || '', scope = topPopup() || document;
var isCss = /^css:/i.test(target) || /^[#.\[]/.test(target) || /^[a-z][a-z0-9-]*[#.\[:]/i.test(target);
var sel = isCss ? target.replace(/^css:/i, '') : null, w = N(target), m = N(match);
function btnIn(tr){
  if (sel) { var b = tr.querySelector(sel); return b && vis(b) ? b : null; }
  var cands = tr.querySelectorAll('button, a, input[type=button], input[type=checkbox], .btn, [onclick]');
  for (var i=0;i<cands.length;i++){ var c=cands[i]; if (!vis(c) && c.type!=='checkbox') continue;
    var t = N(txt(c) || c.getAttribute('title') || c.getAttribute('aria-label') || '');
    if (!w || (t && (t===w || t.indexOf(w)!==-1))) return c; }
  return null; }
var rows = Array.prototype.filter.call(scope.querySelectorAll('tbody tr'), function(tr){ return vis(tr) && tr.querySelector('td'); });
var picked = null, btn = null;
for (var i=0;i<rows.length;i++){
  if (m && N(txt(rows[i])).indexOf(m) === -1) continue;
  var b = btnIn(rows[i]); if (b) { picked = rows[i]; btn = b; break; }
}
if (!btn) return {ok:false, rows: rows.length, matched: m ? rows.filter(function(r){ return N(txt(r)).indexOf(m)!==-1; }).length : rows.length};
btn.scrollIntoView({block:'center'});
if (btn.type === 'checkbox') { if (!btn.checked) btn.click(); } else btn.click();
return {ok:true, row: txt(picked).slice(0, 120), rows: rows.length};
"""

CELL_JS = COMMON_JS + r"""
// the input of a grid cell: by CSS (input.price) or by column header text (السعر), in row 'last' / 'first' / N
var cell = arguments[0], which = String(arguments[1] || 'last'), scope = topPopup() || document;
var isCss = /^css:/i.test(cell) || /^[#.\[]/.test(cell) || /^[a-z][a-z0-9-]*[#.\[:]/i.test(cell);
var FIELD = 'input:not([type=hidden]):not([type=checkbox]):not([type=button]), select, textarea';
function pick(list){
  if (!list.length) return null;
  if (which === 'first') return list[0];
  if (which === 'last') return list[list.length-1];
  var n = parseInt(which, 10); return (n >= 1 && n <= list.length) ? list[n-1] : null;
}
if (isCss) {
  var els = Array.prototype.filter.call(scope.querySelectorAll(cell.replace(/^css:/i, '')), function(e){ return vis(e) || e.tagName==='SELECT'; });
  return {el: pick(els), count: els.length};
}
var w = N(cell), tables = scope.querySelectorAll('table');
for (var t=0;t<tables.length;t++){
  var tb = tables[t]; if (!vis(tb)) continue;
  var ths = tb.querySelectorAll('thead th, thead td'); if (!ths.length) continue;
  var col = -1, idx = 0;
  for (var h=0;h<ths.length;h++){ var tx = N(txt(ths[h]));
    if (col===-1 && tx && (tx===w || tx.indexOf(w)!==-1)) col = idx; idx += (ths[h].colSpan || 1); }
  if (col === -1) continue;
  var rows = Array.prototype.filter.call(tb.querySelectorAll('tbody tr'), function(tr){ return vis(tr) && tr.querySelector(FIELD); });
  var tr = pick(rows); if (!tr) return {el:null, count: rows.length, header: true};
  var k = 0, tds = tr.children;
  for (var c=0;c<tds.length;c++){ if (k === col || (k < col && k + (tds[c].colSpan||1) > col)) {
      var f = tds[c].querySelector(FIELD); return {el: f, count: rows.length, header: true}; }
    k += (tds[c].colSpan || 1); }
  return {el:null, count: rows.length, header: true};
}
return {el:null, count:0, header:false};
"""

READ_REF_JS = COMMON_JS + r"""
// value of a reference: an id, css:..., sum:<column header>, or a label text (value of its field / text next to it)
var ref = String(arguments[0] || '').trim(), scope = topPopup() || document;
function val(e){ if (!e) return null;
  if (e.tagName === 'SELECT') { var o = e.options[e.selectedIndex]; return o ? o.text.trim() : ''; }
  if (e.tagName === 'INPUT' || e.tagName === 'TEXTAREA') return e.type === 'checkbox' ? String(e.checked) : (e.value || '').trim();
  return txt(e); }
if (/^sum:/i.test(ref)) {
  var w = N(ref.slice(4)), total = 0, found = false;
  scope.querySelectorAll('table').forEach(function(tb){
    if (found || !vis(tb)) return;
    var ths = tb.querySelectorAll('thead th, thead td'), col = -1, idx = 0;
    for (var h=0;h<ths.length;h++){ var tx = N(txt(ths[h])); if (col===-1 && tx && (tx===w || tx.indexOf(w)!==-1)) col = idx; idx += (ths[h].colSpan||1); }
    if (col === -1) return; found = true;
    tb.querySelectorAll('tbody tr').forEach(function(tr){ if (!vis(tr)) return; var k = 0;
      for (var c=0;c<tr.children.length;c++){ var td = tr.children[c];
        if (k === col) { var f = td.querySelector('input, select'); var v = f ? val(f) : txt(td);
          var n = parseFloat(String(v).replace(/[٠-٩]/g, function(d){ return '٠١٢٣٤٥٦٧٨٩'.indexOf(d); }).replace(/[^0-9.\-]/g, ''));
          if (!isNaN(n)) total += n; break; }
        k += (td.colSpan || 1); } });
  });
  return found ? String(total) : null;
}
if (/^css:/i.test(ref)) return val(document.querySelector(ref.slice(4)));
var byId = document.getElementById(ref); if (byId) {
  if (byId.classList.contains('select2-hidden-accessible') || byId.tagName==='SELECT') return val(byId);
  return val(byId); }
var w2 = N(ref), best = null, bestLen = 1e9;
document.querySelectorAll('label, th, td, span, div, b, strong, p').forEach(function(e){
  if (!vis(e)) return; var t = N(txt(e)); if (!t || t.length > w2.length + 3) return;
  if ((t === w2 || t.replace(/:$/, '') === w2) && t.length < bestLen) { best = e; bestLen = t.length; } });
if (!best) return null;
if (best.htmlFor) { var f = document.getElementById(best.htmlFor); if (f) return val(f); }
// the field / value right after the label
var nx = best.nextElementSibling;
for (var j = 0; j < 3 && nx; j++, nx = nx.nextElementSibling) {
  var inner = nx.matches('input,select,textarea') ? nx : nx.querySelector('input:not([type=hidden]),select,textarea');
  if (inner) return val(inner); if (txt(nx)) return txt(nx); }
var par = best.parentElement; if (par) { var f2 = par.querySelector('input:not([type=hidden]),select,textarea'); if (f2) return val(f2);
  var rest = txt(par).replace(txt(best), '').trim(); if (rest) return rest; }
return null;
"""

FILE_INPUT_JS = COMMON_JS + r"""
// the file input: by CSS, or the one near a label / button text, or the only one on the page / in the pop-up
var target = arguments[0] || '', scope = topPopup() || document;
var isCss = /^css:/i.test(target) || /^[#.\[]/.test(target) || /^[a-z][a-z0-9-]*[#.\[:]/i.test(target);
var all = Array.prototype.slice.call(scope.querySelectorAll('input[type=file]'));
if (!all.length && scope !== document) all = Array.prototype.slice.call(document.querySelectorAll('input[type=file]'));
var el = null;
if (isCss) { var x = document.querySelector(target.replace(/^css:/i, '')); el = x && x.tagName==='INPUT' ? x : (x && x.querySelector('input[type=file]')); }
else if (target) {
  var w = N(target);
  for (var i=0;i<all.length && !el;i++){ var p = all[i].parentElement, d = 0;
    while (p && d < 4) { if (N(txt(p)).indexOf(w) !== -1) { el = all[i]; break; } p = p.parentElement; d++; } }
}
if (!el) el = all[0] || null;
if (el) { el.style.display='block'; el.style.visibility='visible'; el.style.opacity='1'; el.style.width='200px'; el.style.height='30px';
          el.removeAttribute('hidden'); }
return {el: el, count: all.length};
"""


START = "__start__"          # flow "after" value: before the first field
AFTER_SAVE = "__after_save__"  # flow "after" value: after the record was saved (from the list page)


class FlowError(AssertionError):
    pass


def resolve_value(value, variables=None):
    """{var:name} + {ts} {date} {rand} + date tokens ({today} {month_start} ...)."""
    import random
    from datetime import datetime
    from engine.form_filler import expand_date_tokens
    v = str(value or "")
    if "{" not in v:
        return v
    for k, val in (variables or {}).items():
        v = v.replace("{var:" + k + "}", str(val))
    now = datetime.now()
    v = v.replace("{ts}", now.strftime("%Y%m%d%H%M%S")).replace("{date}", now.strftime("%Y%m%d"))
    v = v.replace("{rand}", str(random.randint(1000, 9999)))
    return expand_date_tokens(v)


_NUM_AR = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")


def to_number(v):
    t = str(v or "").translate(_NUM_AR).replace(",", "").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    if not m:
        raise ValueError(f"«{v}» مش رقم")
    return float(m.group(0))


def evaluate_check(expr, read_ref, tol=0.01):
    """'{الضريبة} = {الصافي} * 0.15'  /  '{Status} ~ مرحل'  /  '{var:no} != '' '.
    Operators: = == != > < >= <= ~ (contains). Returns (ok, explanation)."""
    import ast
    import operator as op
    m = re.search(r"(==|!=|>=|<=|=|>|<|~)", re.sub(r"\{[^}]*\}", lambda x: "X" * len(x.group(0)), expr))
    if not m:
        raise FlowError("الحسبة لازم فيها = أو != أو > أو < أو ~")
    left, sign, right = expr[:m.start()].strip(), m.group(1), expr[m.end():].strip()
    shown = {}

    def sub(side, numeric):
        def rep(x):
            val = read_ref(x.group(1))
            shown[x.group(1)] = val
            return repr(to_number(val)) if numeric else val
        return re.sub(r"\{([^}]+)\}", rep, side)

    if sign == "~":
        a, b = sub(left, False), sub(right, False)
        ok = b.strip() in a
        return ok, f"«{a[:60]}» {'فيه' if ok else 'مش فيه'} «{b}»"

    ops = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv, ast.USub: op.neg, ast.UAdd: op.pos}

    def calc(text):
        def ev(n):
            if isinstance(n, ast.Expression):
                return ev(n.body)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
                return float(n.value)
            if isinstance(n, ast.BinOp) and type(n.op) in ops:
                return ops[type(n.op)](ev(n.left), ev(n.right))
            if isinstance(n, ast.UnaryOp) and type(n.op) in ops:
                return ops[type(n.op)](ev(n.operand))
            raise FlowError(f"مش فاهم الحسبة: {text}")
        return ev(ast.parse(text, mode="eval"))

    try:
        a, b = calc(sub(left, True)), calc(sub(right, True))
    except ValueError as e:
        # not numbers -> compare as text
        a, b = sub(left, False).strip(), sub(right, False).strip()
        ok = (a == b) if sign in ("=", "==") else (a != b) if sign == "!=" else False
        return ok, f"«{a}» {sign} «{b}»"
    cmp = {"=": abs(a - b) <= tol, "==": abs(a - b) <= tol, "!=": abs(a - b) > tol,
           ">": a > b, "<": a < b, ">=": a >= b - tol, "<=": a <= b + tol}[sign]
    vals = "، ".join(f"{k}={v}" for k, v in shown.items())
    return cmp, f"{a:,.2f} {sign} {b:,.2f}  ({vals})"


def sample_file(kind="pdf"):
    """A small test file to upload (made once in data/state/samples)."""
    from config import paths
    raw = str(kind or "pdf").strip()
    if "/" in raw or "\\" in raw:                # a real path on the machine
        from pathlib import Path
        p = Path(raw)
        if not p.exists():
            raise FlowError(f"الملف مش موجود: {kind}")
        return p.resolve()
    kind = raw.lower().lstrip(".")
    d = paths.STATE_DIR / "samples"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"sample_test.{kind}"
    if p.exists():
        return p.resolve()
    if kind == "pdf":
        p.write_bytes(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
                      b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")
    elif kind in ("png", "jpg", "jpeg"):
        import base64
        p.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="))
    elif kind == "xlsx":
        try:
            from openpyxl import Workbook
            wb = Workbook(); wb.active.append(["test", 1]); wb.save(p)
        except Exception:
            p.write_text("test,1\n", encoding="utf-8")
    else:
        p.write_text("ERP automation test file\n", encoding="utf-8")
    return p.resolve()


# ---------------------------------------------------------------- config
def normalize_flows(raw, main_field_ids, normalize_field):
    """Validate the flows list. normalize_field(dict, index, seen) -> clean field (from screen_config)."""
    out = []
    for n, fl in enumerate(raw or [], 1):
        if not isinstance(fl, dict):
            continue
        name = str(fl.get("name") or f"إجراء {n}").strip()
        after = str(fl.get("after") or "").strip()
        if after and after not in (START, AFTER_SAVE) and after not in main_field_ids:
            raise ValueError(f"الإجراء «{name}»: الحقل '{after}' اللي بيشتغل بعده مش في الحقول المختارة")
        steps, seen = [], set(main_field_ids)
        for i, st in enumerate(fl.get("steps") or [], 1):
            do = str(st.get("do") or "").strip()
            if do not in STEP_TYPES:
                raise ValueError(f"الإجراء «{name}» خطوة {i}: نوع غير معروف '{do}'")
            s = {"do": do}
            if do in NEEDS_TARGET:
                t = str(st.get("target") or "").strip()
                if not t:
                    raise ValueError(f"الإجراء «{name}» خطوة {i} ({STEP_TYPES[do]}): اكتبي اسم الزرار/النص")
                s["target"] = t
            if do == "fill":
                f = st.get("field") or {}
                try:
                    s["field"] = normalize_field(f, i, seen)
                except Exception as e:
                    raise ValueError(f"الإجراء «{name}» خطوة {i}: {e}")
            if do == "wait_rows":
                s["min"] = max(1, int(st.get("min") or 1))
                s["table"] = str(st.get("table") or "").strip()
            if do == "pick_rows":
                s["count"] = max(1, int(st.get("count") or 1))
            if do == "wait":
                s["seconds"] = min(60.0, max(0.2, float(st.get("seconds") or 1)))
            if do == "row_click":
                s["target"] = str(st.get("target") or "").strip()
                s["match"] = str(st.get("match") or "").strip()
                if not s["target"] and not s["match"]:
                    raise ValueError(f"الإجراء «{name}» خطوة {i}: اكتبي الزرار اللي جوه الصف (زي اختيار) أو نص من الصف")
            if do == "fill_cell":
                s["cell"] = str(st.get("cell") or "").strip()
                if not s["cell"]:
                    raise ValueError(f"الإجراء «{name}» خطوة {i}: اكتبي اسم العمود (زي السعر) أو CSS (زي input.price)")
                s["row"] = str(st.get("row") or "last").strip() or "last"
                s["value"] = "" if st.get("value") is None else str(st.get("value"))
                if not s["value"].strip():
                    raise ValueError(f"الإجراء «{name}» خطوة {i}: اكتبي القيمة")
            if do == "upload":
                s["target"] = str(st.get("target") or "").strip()
                s["file"] = str(st.get("file") or "pdf").strip() or "pdf"
            if do == "remember":
                s["source"] = str(st.get("source") or "").strip()
                s["var"] = re.sub(r"[^\w.]", "_", str(st.get("var") or "").strip())
                if not s["source"] or not s["var"]:
                    raise ValueError(f"الإجراء «{name}» خطوة {i}: اكتبي مكان القيمة واسم المتغير")
            if do == "assert":
                s["expr"] = str(st.get("expr") or "").strip()
                if not s["expr"]:
                    raise ValueError(f"الإجراء «{name}» خطوة {i}: اكتبي الحسبة، مثلاً {{الضريبة}} = {{الصافي}} * 0.15")
                s["tol"] = float(st.get("tol", 0.01) or 0.01)
            if do == "check_print":
                s["target"] = str(st.get("target") or "").strip() or "طباعة"
                s["match"] = str(st.get("match") or "").strip()
            if do == "check_journal":
                s["target"] = str(st.get("target") or "").strip()       # button that opens the entry ("" = it's already showing)
                s["match"] = str(st.get("match") or "").strip()         # the row in the list ({var:saved_no})
                s["accounts"] = str(st.get("accounts") or "").strip()   # accounts that must be in the entry, comma separated
                s["amount"] = str(st.get("amount") or "").strip()       # expected total ({var:..} / number), optional
                s["tol"] = float(st.get("tol", 0.01) or 0.01)
            s["timeout"] = float(st.get("timeout") or (25 if do in ("wait_rows", "wait_popup") else 12))
            s["wait_after"] = float(st.get("wait_after", 0.6) or 0)
            s["optional"] = bool(st.get("optional", False))
            steps.append(s)
        if not steps:
            raise ValueError(f"الإجراء «{name}» مفيهوش خطوات")
        out.append({"name": name, "after": after, "optional": bool(fl.get("optional", False)), "steps": steps})
    return out


def describe(step):
    do = step["do"]
    if do == "fill":
        f = step["field"]
        return f"{STEP_TYPES[do]} «{f['label']}»"
    if do in NEEDS_TARGET:
        return f"{STEP_TYPES[do]} «{step['target']}»"
    if do == "wait_rows":
        return f"{STEP_TYPES[do]} (على الأقل {step['min']})"
    if do == "pick_rows":
        return f"{STEP_TYPES[do]} {step['count']}"
    if do == "wait":
        return f"{STEP_TYPES[do]} {step['seconds']}"
    if do == "row_click":
        return f"{STEP_TYPES[do]} «{step.get('target') or 'أول زرار'}»" + (f" (الصف اللي فيه «{step['match']}»)" if step.get("match") else "")
    if do == "fill_cell":
        return f"{STEP_TYPES[do]} «{step['cell']}» = {step['value']}"
    if do == "upload":
        return f"{STEP_TYPES[do]} ({step.get('file')})"
    if do == "remember":
        return f"{STEP_TYPES[do]} {step['var']} ← «{step['source']}»"
    if do == "assert":
        return f"{STEP_TYPES[do]}: {step['expr']}"
    if do == "check_print":
        return f"{STEP_TYPES[do]} «{step['target']}»"
    if do == "check_journal":
        return STEP_TYPES[do] + (f" (من «{step['target']}»)" if step.get("target") else "")
    return STEP_TYPES[do]


# ---------------------------------------------------------------- runner
class FlowRunner:
    def __init__(self, page, filler):
        self.page = page            # ScreenRunner (BasePage): driver, handle_swals, accept_js_alert, take_screenshot
        self.driver = page.driver
        self.filler = filler
        # values shared by the steps of a run (saved numbers, etc.) — {var:name} in any value
        if not hasattr(page, "vars"):
            try:
                page.vars = {}
            except Exception:
                pass
        self.vars = getattr(page, "vars", {})

    def _js(self, script, *args):
        return self.driver.execute_script(script, *args)

    def _find(self, target, want, timeout):
        end = time.time() + timeout
        while True:
            el = self._js(FIND_JS, target, want)
            if el is not None or time.time() > end:
                return el
            time.sleep(0.4)

    def _alert(self, timeout=0.5):
        fn = getattr(self.page, "accept_js_alert", None)
        if fn:
            return fn(timeout=timeout)
        try:
            a = self.driver.switch_to.alert
            text = a.text
            a.accept()
            return text
        except Exception:
            return None

    def _settle(self):
        self._alert(0.5)
        try:
            self.page.wait_for_preloader(timeout=15)
        except Exception:
            pass

    # ----- step kinds -----
    def _click(self, st):
        st = {**st, "target": resolve_value(st["target"], self.vars)}
        el = self._find(st["target"], "click", st["timeout"])
        if el is None:
            where = "في النافذة ولا في الصفحة" if self._js(POPUP_JS) else "في الصفحة"
            raise FlowError(f"مالقيتش زرار «{st['target']}» {where}")
        self._js("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.2)
        self._js("arguments[0].click();", el)
        time.sleep(0.4)
        self._settle()
        return "اتضغط"

    def _wait_popup(self, st):
        end = time.time() + st["timeout"]
        while time.time() < end:
            p = self._js(POPUP_JS)
            if p:
                time.sleep(0.6)            # fade-in animation + its lists loading
                self._settle()
                return f"اتفتحت «{p.get('title') or 'نافذة'}»"
            self._alert(0.3)
            time.sleep(0.4)
        raise FlowError("النافذة مفتحتش — اتأكدي إن الزرار اللي قبلها صح، أو إن فيه حقل لازم يتملى الأول")

    def _fill(self, st):
        f = st["field"]
        try:
            return self.filler.fill_field(f)
        except FieldFillError as e:
            raise FlowError(str(e))

    def _wait_rows(self, st):
        end = time.time() + st["timeout"]
        info, empty_since = {}, None
        while time.time() < end:
            info = self._js(ROWS_JS, st.get("table") or None) or {}
            if info.get("rows", 0) >= st["min"]:
                time.sleep(0.4)
                info = self._js(ROWS_JS, st.get("table") or None) or info
                return f"ظهر {info['rows']} صف"
            # the table already says "no data" -> don't wait the whole timeout
            if info.get("empty_text"):
                empty_since = empty_since or time.time()
                if time.time() - empty_since > 4:
                    break
            else:
                empty_since = None
            time.sleep(0.5)
        msg = f"الجدول مظهرش فيه صفوف (المطلوب {st['min']} على الأقل)"
        if info.get("empty_text"):
            msg += f" — الجدول بيقول: «{info['empty_text'][:80]}»"
        if not info.get("tables"):
            msg += " — ومفيش جدول ظاهر أصلاً"
        raise FlowError(msg + "\n   غالبًا مفيش مستندات بالفلاتر دي: غيّري التاريخ أو نوع المستند")

    def _check(self, st):
        st = {**st, "target": resolve_value(st["target"], self.vars)}
        box = self._find(st["target"], "check", st["timeout"])
        if box is None:
            raise FlowError(f"مالقيتش علامة ✓ جنب «{st['target']}»")
        if not self._js("return arguments[0].checked;", box):
            self._js("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", box)
            time.sleep(0.4)
        if not self._js("return arguments[0].checked;", box):
            self._js("arguments[0].checked = true; arguments[0].dispatchEvent(new Event('change', {bubbles:true}));"
                     "if (window.jQuery) jQuery(arguments[0]).trigger('change');", box)
        picked = self._js("var s=(arguments[0].closest('table')||document);"
                          "return s.querySelectorAll('tbody input[type=checkbox]:checked').length;", box)
        return f"اتعلّم ({picked} صف متحدد)" if picked else "اتعلّم"

    def _pick_rows(self, st):
        n = self._js(PICK_ROWS_JS, st["count"])
        if not n:
            raise FlowError("مفيش صفوف فيها علامة ✓ أختارها")
        return f"اتحدد {n} صف"

    def _close_popup(self, st):
        how = self._js(CLOSE_JS)
        if how == "none":
            return "كانت اتقفلت لوحدها"
        end = time.time() + 5
        while time.time() < end and self._js(POPUP_JS):
            time.sleep(0.3)
        if self._js(POPUP_JS):
            self._js(CLOSE_JS)
        return "اتقفلت"

    def _expect_text(self, st):
        want = resolve_value(st["target"], self.vars)
        end = time.time() + st["timeout"]
        while time.time() < end:
            if self._js(TEXT_PRESENT_JS, want):
                return "ظاهر"
            time.sleep(0.5)
        raise FlowError(f"النص «{want}» مظهرش في الصفحة")

    def _wait(self, st):
        time.sleep(st["seconds"])
        return "تمام"

    def _row_click(self, st):
        end = time.time() + st["timeout"]
        res = {}
        while time.time() < end:
            res = self._js(ROW_CLICK_JS, st.get("target", ""), resolve_value(st.get("match", ""), self.vars)) or {}
            if res.get("ok"):
                time.sleep(0.5)
                self._settle()
                return f"اتضغط في الصف: {res.get('row', '')[:70]}"
            time.sleep(0.5)
        if not res.get("rows"):
            raise FlowError("مفيش صفوف في الجدول")
        if st.get("match") and not res.get("matched"):
            raise FlowError(f"مفيش صف فيه «{st['match']}» (فيه {res.get('rows')} صف)")
        raise FlowError(f"مالقيتش زرار «{st.get('target')}» جوه الصفوف")

    def _fill_cell(self, st):
        value = resolve_value(st["value"], self.vars)
        end = time.time() + st["timeout"]
        res = {}
        while time.time() < end:
            res = self._js(CELL_JS, st["cell"], st.get("row", "last")) or {}
            if res.get("el") is not None:
                break
            time.sleep(0.5)
        el = res.get("el")
        if el is None:
            if res.get("header") is False:
                raise FlowError(f"مالقيتش عمود «{st['cell']}» في أي جدول")
            raise FlowError(f"مالقيتش خانة «{st['cell']}» في السطر {st.get('row')} (السطور: {res.get('count', 0)})")
        tag = el.tag_name.lower()
        if tag == "select":
            got = self._js("var s=arguments[0], w=arguments[1].trim();"
                           "for (var i=0;i<s.options.length;i++){ if (s.options[i].text.trim()===w || s.options[i].value===w){"
                           " s.selectedIndex=i; s.dispatchEvent(new Event('change',{bubbles:true}));"
                           " if (window.jQuery) jQuery(s).trigger('change'); return s.options[i].text.trim(); } } return null;",
                           el, value)
            if got is None:
                raise FlowError(f"القيمة «{value}» مش في قايمة «{st['cell']}»")
        else:
            from engine.form_filler import SET_VALUE_JS
            self._js("arguments[0].scrollIntoView({block:'center'});", el)
            got = self._js(SET_VALUE_JS, el, value)
            if str(got).startswith("__NOT_INPUT__"):
                raise FlowError(f"خانة «{st['cell']}» مش حقل كتابة")
        time.sleep(0.8)                         # totals recalculate
        return f"{got}"

    def _ref(self, ref):
        ref = ref.strip()
        if ref.startswith("var:"):
            name = ref[4:]
            if name not in self.vars:
                raise FlowError(f"المتغير «{name}» لسه ما اتحفظش (المتاح: {', '.join(self.vars) or 'مفيش'})")
            return str(self.vars[name])
        v = self._js(READ_REF_JS, ref)
        if v is None:
            raise FlowError(f"مالقيتش «{ref}» في الصفحة (اكتبي الـ id أو الاسم اللي جنبه زي ما هو، أو sum:اسم العمود)")
        return str(v)

    def _remember(self, st):
        v = self._ref(st["source"])
        self.vars[st["var"]] = v
        return f"{st['var']} = {v}"

    def _assert(self, st):
        ok, detail = evaluate_check(st["expr"], self._ref, st.get("tol", 0.01))
        if not ok:
            raise FlowError(f"الحسبة مش مظبوطة: {detail}")
        return detail

    def _check_print(self, st):
        d = self.driver
        before = set(d.window_handles)
        url0 = d.current_url
        if st.get("match"):
            res = self._js(ROW_CLICK_JS, st["target"], resolve_value(st["match"], self.vars)) or {}
            if not res.get("ok"):
                raise FlowError(f"مالقيتش زرار «{st['target']}» في الصف اللي فيه «{st['match']}»")
        else:
            self._click({"target": st["target"], "timeout": st["timeout"]})
        return self.verify_print(before, url0, st["timeout"])

    def verify_print(self, before, url0, timeout=15):
        """after a print button was clicked: a new tab / print page / embedded PDF must show up, not empty, no error"""
        d = self.driver
        end = time.time() + max(15, timeout)
        new = None
        while time.time() < end:
            extra = [h for h in d.window_handles if h not in before]
            if extra:
                new = extra[-1]
                break
            if self._js("return !!document.querySelector('iframe[src*=\".pdf\"], embed[type*=pdf], object[type*=pdf], iframe[src*=Print], iframe[src*=Report]')"):
                return "الطباعة ظهرت جوه الصفحة"
            if d.current_url != url0 and ("print" in d.current_url.lower() or "report" in d.current_url.lower()):
                break
            time.sleep(0.5)
        if new is None and d.current_url == url0:
            raise FlowError("ما فتحتش صفحة طباعة ولا ملف PDF بعد الضغط")
        main = d.current_window_handle
        try:
            if new:
                d.switch_to.window(new)
            time.sleep(3)
            info = self._js("var t=(document.body&&document.body.innerText)||''; return {url: location.href, title: document.title,"
                            " len: t.length, ct: document.contentType || '', err: /server error|exception|runtime error|404|500|خطأ في الخادم/i.test(t.slice(0,3000))};") or {}
            self._shot("print_preview")
            if info.get("err"):
                raise FlowError(f"صفحة الطباعة فيها خطأ: {info.get('title') or info.get('url')}")
            if "pdf" not in (info.get("ct") or "").lower() and info.get("len", 0) < 20 and ".pdf" not in (info.get("url") or "").lower():
                raise FlowError("صفحة الطباعة فاضية")
            return f"فتحت: {info.get('title') or info.get('url', '')[:80]}"
        finally:
            if new:
                try:
                    d.close()
                except Exception:
                    pass
                d.switch_to.window(main if main != new else list(before)[0])
            elif d.current_url != url0:
                d.back()

    def _check_journal(self, st):
        """open the entry the saved document made (button in its row / on the page / a new tab) and check
        debit = credit, the expected accounts are there, and (optional) the total equals the document amount"""
        d = self.driver
        before, url0, main = set(d.window_handles), d.current_url, d.current_window_handle
        new = None
        if st.get("target"):
            target = resolve_value(st["target"], self.vars)
            if st.get("match"):
                res = self._js(ROW_CLICK_JS, target, resolve_value(st["match"], self.vars)) or {}
                if not res.get("ok"):
                    raise FlowError(f"مالقيتش زرار «{target}» في الصف اللي فيه «{resolve_value(st['match'], self.vars)}»")
            else:
                self._click({"target": target, "timeout": st["timeout"]})
            end = time.time() + 10
            while time.time() < end:
                extra = [h for h in d.window_handles if h not in before]
                if extra:
                    new = extra[-1]
                    d.switch_to.window(new)
                    break
                if self._js(POPUP_JS) or d.current_url != url0:
                    break
                time.sleep(0.4)
        try:
            end, info = time.time() + max(15, st["timeout"]), {}
            while time.time() < end:
                info = self._js(JOURNAL_JS) or {}
                if info.get("found"):
                    break
                time.sleep(0.6)
            self._shot("journal")
            if not info.get("found"):
                raise FlowError("مالقيتش جدول قيد فيه عمود «مدين» وعمود «دائن» في الصفحة"
                                + (" (اتفتحت صفحة جديدة)" if new else "") + " — اتأكدي من زرار فتح القيد")
            dr, cr, tol = info["debit"], info["credit"], st.get("tol", 0.01)
            self.vars["journal_debit"], self.vars["journal_credit"] = dr, cr
            lines = "؛ ".join(f"{x['text'][:60]}" for x in info.get("lines", [])[:6])
            if dr <= 0 and cr <= 0:
                raise FlowError(f"القيد فاضي (مدين = دائن = صفر). السطور: {lines or 'مفيش'}")
            if abs(dr - cr) > tol:
                raise FlowError(f"القيد مش متزن: مدين {dr:,.2f} ≠ دائن {cr:,.2f} (الفرق {abs(dr - cr):,.2f})\n   السطور: {lines}")
            from engine.text_match import normalize as _n
            all_text = _n(" ".join(x["text"] for x in info.get("lines", [])))
            missing = [a.strip() for a in re.split(r"[,،]", resolve_value(st.get("accounts") or "", self.vars))
                       if a.strip() and _n(a.strip()) not in all_text]
            if missing:
                raise FlowError(f"القيد مفيهوش الحساب: {'، '.join(missing)}\n   السطور: {lines}")
            if st.get("amount"):
                want = to_number(resolve_value(st["amount"], self.vars))
                if abs(dr - want) > tol:
                    raise FlowError(f"إجمالي القيد {dr:,.2f} مش زي المبلغ المتوقع {want:,.2f}")
            return f"متزن: مدين {dr:,.2f} = دائن {cr:,.2f} · {len(info.get('lines', []))} سطر"
        finally:
            if new:
                try:
                    d.close()
                except Exception:
                    pass
                d.switch_to.window(main)
            elif self._js(POPUP_JS):
                self._js(CLOSE_JS)
            elif d.current_url != url0:
                d.back()
                time.sleep(1)

    def _upload(self, st):
        path = sample_file(st.get("file") or "pdf")
        res = self._js(FILE_INPUT_JS, st.get("target", "")) or {}
        el = res.get("el")
        if el is None:
            raise FlowError("مفيش خانة رفع ملفات (input type=file) في الصفحة")
        el.send_keys(str(path))
        self._js("arguments[0].dispatchEvent(new Event('change',{bubbles:true}));"
                 "if (window.jQuery) jQuery(arguments[0]).trigger('change');", el)
        time.sleep(1)
        self._settle()
        name = self._js("return arguments[0].files && arguments[0].files.length ? arguments[0].files[0].name : '';", el)
        if not name:
            raise FlowError("الملف ما اتحطش في الخانة")
        return f"اترفع {name}"

    # ----- one flow -----
    def run(self, flow, key=""):
        name = flow["name"]
        logger.info(f"🔗 إجراء: {name} ({len(flow['steps'])} خطوة)")
        for i, st in enumerate(flow["steps"], 1):
            label = f"🔗 {name} › {describe(st)}"
            t0 = time.time()
            try:
                result = getattr(self, "_" + st["do"])(st)
            except Exception as e:
                msg = str(e).split("\n  (Session info")[0]
                if st.get("optional"):
                    logger.warning(f"⚠️ {label}: {msg} (خطوة اختيارية — كملت)")
                    self.filler.steps.append(self._step(flow, i, st, label, f"⚠️ اتخطت: {msg[:120]}", True, t0))
                    continue
                self.filler.steps.append(self._step(flow, i, st, label, None, False, t0, error=msg))
                shot = self._shot(f"{key}_flow_failed")
                err = FlowError(f"[{name} › خطوة {i}: {describe(st)}] {msg}")
                err.screenshot = shot
                raise err from None
            self.filler.steps.append(self._step(flow, i, st, label, result, True, t0))
            logger.success(f"✅ {label}: {result}")
            if st.get("wait_after"):
                time.sleep(st["wait_after"])
        return True

    def _step(self, flow, i, st, label, result, ok, t0, error=None):
        d = {"id": f"flow:{flow['name']}#{i}", "label": label, "strategy": "flow",
             "wanted": st.get("target") or (st.get("field") or {}).get("value", ""),
             "result": result, "ok": ok, "seconds": round(time.time() - t0, 1)}
        if error:
            d["error"] = error
        return d

    def _shot(self, name):
        try:
            path = self.page.take_screenshot(name)
        except Exception:
            return None
        if path:
            try:
                import allure
                allure.attach.file(path, name=name, attachment_type=allure.attachment_type.PNG)
            except Exception:
                pass
        return path


def fill_with_flows(page, cfg, filler, screenshots=None):
    """Fill the fields in order and run each flow at its place."""
    flows = cfg.get("flows") or []
    if not flows:
        return filler.fill_all(cfg["fields"])
    by_after = {}
    ids = {f["id"] for f in cfg["fields"]}
    for fl in flows:
        if fl["after"] == AFTER_SAVE:
            continue
        key = fl["after"] if (fl["after"] in ids or fl["after"] == START) else ""
        by_after.setdefault(key, []).append(fl)
    runner = FlowRunner(page, filler)

    def run_all(lst):
        for fl in lst:
            try:
                runner.run(fl, cfg.get("key", ""))
            except FlowError as e:
                if screenshots is not None and getattr(e, "screenshot", None):
                    screenshots.append(e.screenshot)
                if fl.get("optional"):
                    logger.warning(f"⚠️ الإجراء «{fl['name']}» فشل وهو اختياري — كملت: {e}")
                    continue
                raise AssertionError(f"وقف في الإجراء: {e}") from None
            if screenshots is not None:
                s = runner._shot(f"{cfg.get('key', '')}_flow_{len(screenshots)}")
                if s:
                    screenshots.append(s)

    run_all(by_after.get(START, []))
    seg = []
    for f in cfg["fields"]:
        seg.append(f)
        if f["id"] in by_after:
            filler.fill_all(seg)
            seg = []
            run_all(by_after[f["id"]])
    if seg:
        filler.fill_all(seg)
    run_all(by_after.get("", []))
    return filler.steps


def run_after_save(page, cfg, filler, screenshots=None):
    """Steps marked «بعد الحفظ» (edit / print / checks on the saved record), run from the list page."""
    flows = [fl for fl in (cfg.get("flows") or []) if fl["after"] == AFTER_SAVE]
    if not flows:
        return
    runner = FlowRunner(page, filler)
    for fl in flows:
        try:
            runner.run(fl, cfg.get("key", ""))
        except FlowError as e:
            if screenshots is not None and getattr(e, "screenshot", None):
                screenshots.append(e.screenshot)
            if fl.get("optional"):
                logger.warning(f"⚠️ «{fl['name']}» بعد الحفظ فشل وهو اختياري — كملت: {e}")
                continue
            raise AssertionError(f"وقف بعد الحفظ في «{fl['name']}»: {e}") from None
