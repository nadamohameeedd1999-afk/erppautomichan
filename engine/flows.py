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
}
NEEDS_TARGET = {"click", "check", "expect_text"}

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

TEXT_PRESENT_JS = COMMON_JS + "return N(document.body.innerText).indexOf(N(arguments[0])) !== -1;"


class FlowError(AssertionError):
    pass


# ---------------------------------------------------------------- config
def normalize_flows(raw, main_field_ids, normalize_field):
    """Validate the flows list. normalize_field(dict, index, seen) -> clean field (from screen_config)."""
    out = []
    for n, fl in enumerate(raw or [], 1):
        if not isinstance(fl, dict):
            continue
        name = str(fl.get("name") or f"إجراء {n}").strip()
        after = str(fl.get("after") or "").strip()
        if after and after not in main_field_ids:
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
    return STEP_TYPES[do]


# ---------------------------------------------------------------- runner
class FlowRunner:
    def __init__(self, page, filler):
        self.page = page            # ScreenRunner (BasePage): driver, handle_swals, accept_js_alert, take_screenshot
        self.driver = page.driver
        self.filler = filler

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
        end = time.time() + st["timeout"]
        while time.time() < end:
            if self._js(TEXT_PRESENT_JS, st["target"]):
                return "ظاهر"
            time.sleep(0.5)
        raise FlowError(f"النص «{st['target']}» مظهرش في الصفحة")

    def _wait(self, st):
        time.sleep(st["seconds"])
        return "تمام"

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
        by_after.setdefault(fl["after"] if fl["after"] in ids else "", []).append(fl)
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
