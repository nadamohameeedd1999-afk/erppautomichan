"""
Form Inspector — READ ONLY.

Opens the add form of a screen and lists its fields:
id, label, kind, required, Select2 or not, order on the page, current value, options.
It never clicks save. The only thing it touches is the dropdowns (to find which
field depends on which, e.g. project after customer) — nothing is sent to the server
except the normal "load options" requests the page itself makes.
"""
import time
from urllib.parse import urlsplit

from selenium.webdriver.common.by import By

from config.settings import BASE_URL
from pages.base_page import BasePage
from utils.logger import logger
from engine import text_match
from engine.smart_values import guess as smart_guess

SCAN_JS = r"""
var root = arguments[0] || document;
function txt(e){ return (e && (e.innerText || e.textContent) || '').replace(/\s+/g,' ').trim(); }
function visible(e){
  if (!e) return false;
  var r = e.getBoundingClientRect();
  var s = window.getComputedStyle(e);
  return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
}
function labelFor(el){
  var t = '';
  if (el.id) {
    var l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
    if (l) t = txt(l);
  }
  if (!t) {
    // label without for="": the closest label BEFORE the field (not simply the first label of the row,
    // e.g. «الفرع | [..]  نوع المستند | [DocType]» -> DocType gets «نوع المستند»)
    var p = el.parentElement, depth = 0;
    while (p && depth < 4 && !t) {
      var ls = p.querySelectorAll('label'), best = null, after = null;
      for (var k = 0; k < ls.length; k++) {
        var l2 = ls[k];
        if (l2.contains(el) || (l2.htmlFor && l2.htmlFor !== el.id)) continue;
        var pos = l2.compareDocumentPosition(el);
        if (pos & Node.DOCUMENT_POSITION_FOLLOWING) best = l2;          // label is before the field
        else if (!after) after = l2;                                     // first label after it
      }
      var pick = best || after;
      if (pick) t = txt(pick);
      p = p.parentElement; depth++;
    }
  }
  if (!t) t = el.getAttribute('placeholder') || el.getAttribute('aria-label') || el.getAttribute('title') || '';
  return t;
}
var out = [];
// reading the page: fields inside a pop-up window belong to that window (its button reads them), not to the form
var POPUP_SEL = '.modal, [role=dialog], .ui-dialog';
var scanningPopup = root !== document && root.closest && !!root.closest(POPUP_SEL);
var els = root.querySelectorAll('input, select, textarea');
for (var i = 0; i < els.length; i++) {
  var el = els[i];
  var tag = el.tagName.toLowerCase();
  var type = (el.getAttribute('type') || '').toLowerCase();
  if (el.classList.contains('select2-search__field')) continue;
  if (el.closest('.select2-container, .dataTables_filter, .dataTables_length, nav, .navbar, header')) continue;
  if (!scanningPopup && el.closest(POPUP_SEL)) continue;
  if (['submit','button','reset','image','file','search'].indexOf(type) !== -1) continue;
  if (el.name === '__RequestVerificationToken') continue;
  var isS2 = tag === 'select' && (el.classList.contains('select2-hidden-accessible') ||
             !!(el.id && document.getElementById('select2-' + el.id + '-container')));
  var s2box = isS2 && el.id ? document.getElementById('select2-' + el.id + '-container') : null;
  var vis = isS2 ? visible(s2box && s2box.closest('.select2-container')) : visible(el);
  if (type === 'hidden' && !el.hasAttribute('data-val-required')) continue;
  if (!el.id && !el.name) continue;
  var lbl = labelFor(el);
  var req = el.required || el.hasAttribute('data-val-required') || el.getAttribute('aria-required') === 'true' ||
            /\*\s*$/.test(lbl) || !!(el.id && document.querySelector('label[for="' + CSS.escape(el.id) + '"].required'));
  var kind = 'text';
  if (tag === 'select') kind = isS2 ? 'select2' : 'select';
  else if (tag === 'textarea') kind = 'textarea';
  else if (type === 'checkbox' || type === 'radio') kind = 'checkbox';
  else if (type === 'hidden') kind = 'hidden';
  else if (type === 'date' || type === 'datetime-local' || /date|datepicker/i.test(el.className) || /date/i.test(el.id || '')) kind = 'date';
  else if (type === 'number' || /amount|price|qty|quantity/i.test(el.id || '')) kind = 'number';
  var opts = [];
  if (tag === 'select') {
    for (var j = 0; j < el.options.length && j < 60; j++) opts.push(el.options[j].text.replace(/\s+/g,' ').trim());
  }
  var value = '';
  if (tag === 'select') value = el.selectedIndex >= 0 && el.options[el.selectedIndex] ? el.options[el.selectedIndex].text.trim() : '';
  else if (kind === 'checkbox') value = el.checked ? 'true' : 'false';
  else value = el.value || '';
  out.push({
    id: el.id || ("css:[name='" + el.name + "']"),
    name: el.name || '',
    label: lbl.replace(/\s*\*\s*$/, '').trim(),
    kind: kind,
    required: !!req,
    visible: vis,
    disabled: !!(el.disabled || el.readOnly),
    in_table: !!el.closest('table'),
    value: value,
    options: opts,
    option_count: tag === 'select' ? el.options.length : 0,
    dom_order: i,
    validation_msg: el.getAttribute('data-val-required') || ''
  });
}
return out;
"""

BUTTONS_JS = r"""
var root = arguments[0] || document;
function txt(e){ return (e && (e.innerText || e.textContent || e.value) || '').replace(/\s+/g,' ').trim(); }
var out = [], seen = {};
var fieldsInOrder = Array.prototype.filter.call(document.querySelectorAll('input[id], select[id], textarea[id]'), function(e){
  return !e.closest('.modal, [role=dialog], .select2-container, nav, .navbar, header') && e.type !== 'hidden'; });
var els = root.querySelectorAll('button, input[type=submit], input[type=button], a.btn');
for (var i = 0; i < els.length; i++) {
  var b = els[i];
  if (b.closest('nav, .navbar, header, .select2-container, .dataTables_wrapper, .swal2-container, .modal-footer')) continue;
  var sel = b.id ? (b.tagName.toLowerCase() + '#' + b.id) : '';
  if (!sel) continue;
  if (seen[sel]) continue; seen[sel] = 1;
  var r = b.getBoundingClientRect();
  // the last field before the button on the page -> where it belongs in the order
  var after = '';
  for (var k = 0; k < fieldsInOrder.length; k++) {
    if (fieldsInOrder[k].compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) after = fieldsInOrder[k].id;
    else break;
  }
  out.push({ selector: sel, id: b.id, text: txt(b).slice(0, 60),
             visible: r.width > 0 && r.height > 0, type: (b.getAttribute('type') || '').toLowerCase(),
             in_modal: !!b.closest('.modal, [role=dialog], .ui-dialog'), in_table: !!b.closest('table'),
             after_field: after, onclick: (b.getAttribute('onclick') || '').slice(0, 80) });
}
return out;
"""

FORM_ROOT_JS = r"""
// The add form is the <form> with the most real fields (Select2 lists count double).
// If no form clearly holds the fields (ERP pages often put inputs outside <form>), scan the whole page.
var best = null, bestScore = 0, total = 0;
function score(root){
  var n = 0;
  root.querySelectorAll('input:not([type=hidden]):not([type=search]), select, textarea').forEach(function(e){
    if (e.closest('nav, .navbar, header, .select2-container, .dataTables_wrapper, .modal, [role=dialog], .ui-dialog')) return;
    n += (e.tagName === 'SELECT' ? 2 : 1);
  });
  return n;
}
total = score(document);
document.querySelectorAll('form').forEach(function(f){
  var s = score(f);
  if (s > bestScore) { bestScore = s; best = f; }
});
return (best && bestScore >= total * 0.7) ? best : null;
"""

SIGNATURES_JS = r"""
var ids = arguments[0], out = {};
ids.forEach(function(id){
  var s = document.getElementById(id);
  if (!s) { out[id] = null; return; }
  var t = [];
  for (var i = 0; i < s.options.length; i++) t.push(s.options[i].value + '=' + s.options[i].text.trim());
  out[id] = t.join('|');
});
return out;
"""

PICK_FIRST_JS = r"""
var s = document.getElementById(arguments[0]);
if (!s) return null;
var ph = arguments[1];
for (var i = 0; i < s.options.length; i++) {
  var t = s.options[i].text.replace(/\s+/g,' ').trim();
  if (!t || ph.indexOf(t.toLowerCase()) !== -1 || !s.options[i].value) continue;
  s.selectedIndex = i;
  if (window.jQuery) { jQuery(s).trigger('change'); } else { s.dispatchEvent(new Event('change', {bubbles:true})); }
  return t;
}
return null;
"""


def _abs(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http"):
        return url
    return BASE_URL.rstrip("/") + "/" + url.lstrip("/")


def _path_only(url: str) -> str:
    """https://host/CashReceiptVoucher/AddEdit?x=1 -> /CashReceiptVoucher/AddEdit?x=1"""
    if not url.startswith("http"):
        return url
    p = urlsplit(url)
    return (p.path or "/") + (("?" + p.query) if p.query else "")


class FormInspector(BasePage):

    def __init__(self, driver):
        super().__init__(driver)

    # ---------- open the add page ----------
    def open_add_page(self, list_url: str, add_url: str = "", add_button: str = ""):
        """Returns (add_url_used, add_button_used)."""
        list_path = _path_only(list_url).split("?")[0].rstrip("/")
        self.open(_abs(list_url))
        time.sleep(1)

        candidates = [add_button] if add_button else []
        candidates += [f"a[href='{list_path}/AddEdit']", f"a[href^='{list_path}/AddEdit']",
                       f"a[href*='{list_path}/AddEdit']", "a[href*='/AddEdit']"]
        for sel in candidates:
            try:
                els = [e for e in self.driver.find_elements(By.CSS_SELECTOR, sel) if e.is_displayed()]
            except Exception:
                els = []
            if els:
                logger.info(f"زرار الإضافة: {sel}")
                href = (els[0].get_attribute("href") or "").strip()
                if href and not href.lower().startswith("javascript") and not href.endswith("#"):
                    # a real link: open it like the test runner does (a JS click on a link
                    # right after restoring a saved session can crash Chrome's page)
                    self.open(href)
                else:
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", els[0])
                    self.driver.execute_script("arguments[0].click();", els[0])
                self.wait_for_preloader(timeout=20)
                time.sleep(1.5)
                return self.driver.current_url, sel

        target = add_url or f"{list_path}/AddEdit"
        logger.info(f"مفيش زرار إضافة ظاهر — هفتح الرابط مباشرة: {target}")
        self.open(_abs(target))
        time.sleep(1.5)
        return self.driver.current_url, ""

    # ---------- scanning ----------
    def _root(self):
        try:
            return self.driver.execute_script(FORM_ROOT_JS)
        except Exception:
            return None

    def scan_fields(self):
        return self.driver.execute_script(SCAN_JS, self._root()) or []

    def scan_buttons(self):
        # whole page: the save / autoPay buttons are often outside the <form>
        return self.driver.execute_script(BUTTONS_JS, None) or []

    def detect_dependencies(self, fields, settle=1.5):
        """Pick the first real option in each dropdown (in page order) and see
        which later dropdowns change their options. Returns {child_id: parent_id}."""
        # all dropdowns, even hidden ones: a list can appear / fill up after an earlier choice
        selects = [f["id"] for f in fields
                   if f["kind"] in ("select", "select2") and not f["id"].startswith("css:")
                   and not f["disabled"]]
        deps = {}
        ph = sorted(text_match.PLACEHOLDERS)
        for i, sid in enumerate(selects):
            later = selects[i + 1:]
            if not later:
                break
            before = self.driver.execute_script(SIGNATURES_JS, later)
            picked = self.driver.execute_script(PICK_FIRST_JS, sid, ph)
            if not picked:
                continue
            end = time.time() + settle + 3
            changed = []
            time.sleep(settle)
            while time.time() < end:
                after = self.driver.execute_script(SIGNATURES_JS, later)
                changed = [c for c in later if after.get(c) != before.get(c)]
                if changed:
                    time.sleep(0.5)
                    after = self.driver.execute_script(SIGNATURES_JS, later)
                    changed = [c for c in later if after.get(c) != before.get(c)]
                    break
                time.sleep(0.5)
            for c in changed:
                deps.setdefault(c, sid)
            if changed:
                logger.info(f"🔗 {', '.join(changed)} بيتغيّر بعد اختيار {sid} ({picked})")
        return deps

    def inspect(self, list_url, add_url="", add_button="", find_dependencies=True):
        used_url, used_button = self.open_add_page(list_url, add_url, add_button)
        warnings = []
        if "/login" in used_url.lower():
            warnings.append("الصفحة رجعت لتسجيل الدخول — اتأكد من بيانات الدخول")

        first = self.scan_fields()
        deps = {}
        if find_dependencies:
            try:
                deps = self.detect_dependencies(first)
            except Exception as e:
                warnings.append(f"تحديد الاعتماديات وقف: {str(e)[:120]}")
        final = self.scan_fields() if find_dependencies else first

        first_visible = {f["id"] for f in first if f["visible"]}
        fields = []
        for f in final:
            f = dict(f)
            f["depends_on"] = deps.get(f["id"])
            f["appears_after_choice"] = f["visible"] and f["id"] not in first_visible
            f["suggested_include"] = bool(f["visible"] and not f["disabled"] and not f["in_table"]
                                          and (f["required"] or f["depends_on"]))
            if f["kind"] in ("select", "select2"):
                f["suggested_strategy"] = "first"
            elif f["kind"] == "date":
                f["suggested_strategy"] = "keep" if f["value"] else "today"
            elif f["kind"] == "checkbox":
                f["suggested_strategy"] = "keep"
            elif f["kind"] == "number":
                f["suggested_strategy"] = "smart" if smart_guess(f["label"], f["id"]) else "fixed"
            else:
                f["suggested_strategy"] = "keep" if f["value"] else ("smart" if smart_guess(f["label"], f["id"]) else "unique")
            f["options"] = text_match.real_options(f.get("options"))[:40]
            fields.append(f)

        if not fields:
            warnings.append("مالقيتش ولا حقل في الصفحة — اتأكدي إن رابط الإضافة بيفتح الفورم (شوفي اللقطة)")
        elif not any(f["required"] for f in fields):
            warnings.append("مالقيتش حقول إجبارية متعلّم عليها — علّمي على الحقول المهمة بنفسك")
        if any(f["in_table"] and f["visible"] for f in fields):
            warnings.append("الشاشة فيها جدول أصناف/سطور — استخدمي «➕ قالب: إضافة صنف» أو «⏺ سجّلي خطواتك» للسطور")

        buttons = self.scan_buttons()
        save = next((b["selector"] for b in buttons if b["id"].lower() in ("save", "btnsave")), "")
        if not save:
            save = next((b["selector"] for b in buttons if "حفظ" in b["text"] or "save" in b["text"].lower()), "")

        shot = self.take_screenshot("inspect")
        return {
            "list_url": _path_only(list_url),
            "add_url": _path_only(used_url).split("#")[0],
            "add_button": used_button,
            "title": self.driver.title,
            "fields": fields,
            "buttons": buttons,
            "suggested_save": save or "button#save",
            "warnings": warnings,
            "screenshot": shot,
        }


# ======================================================================
#  Pop-up discovery (اكتشاف النافذة) — for flows like «ربط بمستند آخر»
# ======================================================================
POPUP_BUTTONS_JS = r"""
var root = arguments[0];
function txt(e){ return (e.innerText || e.textContent || e.value || '').replace(/\s+/g,' ').trim(); }
function vis(e){ var r=e.getBoundingClientRect(), s=getComputedStyle(e);
  return r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none'; }
var out = [], seen = {};
root.querySelectorAll('button, a.btn, input[type=button], input[type=submit], [role=button]').forEach(function(b){
  if (!vis(b) || b.closest('.select2-container')) return;
  var t = txt(b) || b.getAttribute('title') || b.getAttribute('aria-label') || '';
  var cls = (b.className || '').toString();
  if (!t && /close/.test(cls)) t = '×';
  if (!t || seen[t]) return; seen[t] = 1;
  out.push({text: t.slice(0, 50), id: b.id || '', close: /close|dismiss/.test(cls) || b.hasAttribute('data-dismiss') || b.hasAttribute('data-bs-dismiss')});
});
var selectAll = '';
root.querySelectorAll('label, th, span, div').forEach(function(e){
  if (selectAll || !vis(e)) return;
  var t = txt(e);
  if (t.length < 25 && /(تحديد|اختيار)\s*(ال)?كل|select all/i.test(t) && (e.querySelector('input[type=checkbox]') ||
      (e.parentElement && e.parentElement.querySelector('input[type=checkbox]')))) selectAll = t;
});
var headBox = !selectAll && root.querySelector('thead input[type=checkbox]');
return {buttons: out, select_all: selectAll, head_checkbox: !!headBox};
"""

_FILTER_WORDS = ("المصفي", "مصفي", "تصفيه", "فلتر", "بحث", "عرض", "filter", "search", "show")
_ADD_WORDS = ("اضافه", "إضافة", "اضافة", "add", "اختيار", "تاكيد", "تأكيد", "موافق", "ok", "select", "ادراج")
_SKIP_WORDS = ("مسح", "clear", "reset", "الغاء", "إلغاء", "cancel", "اغلاق", "إغلاق", "close")


def _classify(text):
    n = text_match.normalize(text)
    if any(text_match.normalize(w) in n for w in _SKIP_WORDS):
        return "skip"
    if any(text_match.normalize(w) == n or text_match.normalize(w) in n for w in _FILTER_WORDS):
        return "filter"
    if any(text_match.normalize(w) in n for w in _ADD_WORDS):
        return "add"
    return ""


def _date_token(label):
    n = text_match.normalize(label)
    if any(w in n for w in ("الي", "to", "نهايه", "end")):
        return "{month_end}"
    if any(w in n for w in ("من", "from", "بدايه", "start")):
        return "{month_start}"
    return "{today}"


def inspect_popup(driver, cfg, open_target, after="", choose=None):
    """Open the add page, fill the fields that come before `after`, click `open_target`,
    read the pop-up (fields + buttons), press its filter button to see the table, and
    return a ready-to-use flow. It never presses add / save."""
    from engine import flows as F
    from engine.form_filler import FormFiller

    page = FormInspector(driver)
    used_url, _ = page.open_add_page(cfg["list_url"], cfg.get("add_url", ""), cfg.get("add_button", ""))
    warnings, filler = [], FormFiller(driver)

    before = []
    if after:
        for f in cfg.get("fields", []):
            before.append(f)
            if f["id"] == after:
                break
    if before:
        logger.info(f"بملى {len(before)} حقل قبل الزرار (لحد {after})")
        try:
            filler.fill_all(before)
        except Exception as e:
            warnings.append(f"ملء الحقول اللي قبل الزرار وقف: {str(e)[:200]}")

    runner = F.FlowRunner(page, filler)
    open_step = {"do": "click", "target": open_target, "timeout": 12, "wait_after": 0.6}
    runner._click(open_step)
    runner._wait_popup({"timeout": 20})
    popup = driver.execute_script(F.COMMON_JS + "return topPopup();")
    title = (driver.execute_script(F.POPUP_JS) or {}).get("title", "")

    def scan():
        pf = driver.execute_script(SCAN_JS, popup) or []
        pf = [f for f in pf if f["visible"] and not f["disabled"] and f["kind"] != "hidden"]
        for f in pf:
            f["options"] = text_match.real_options(f.get("options"))[:40]
        inf = driver.execute_script(POPUP_BUTTONS_JS, popup) or {}
        flt = next((b["text"] for b in inf.get("buttons", []) if _classify(b["text"]) == "filter"), "")
        return pf, inf, flt

    def same(a, b):
        a, b = text_match.normalize(a), text_match.normalize(b)
        return a == b or (len(b) > 2 and b in a)

    def pick(f, wanted=""):
        val = filler.fill_field({**f, "label": f["label"] or f["id"], "strategy": "fixed" if wanted else "first",
                                 "value": wanted, "timeout": 8, "required": False, "wait_after": 0.3})
        picked[f["id"]] = val
        time.sleep(1.5)                     # sections / lists that depend on this choice
        return val

    pfields, info, filt = scan()
    picked = {}

    # 1) the values she asked for (e.g. نوع المستند = سندات صرف المخازن)
    for want in [c.strip() for c in (choose or []) if c and c.strip()]:
        f = next((x for x in pfields if x["kind"] in ("select", "select2") and x["id"] not in picked
                  and any(same(o, want) for o in x["options"])), None)
        if not f:
            warnings.append(f"«{want}» مش موجودة في أي قايمة في النافذة")
            continue
        try:
            exact = next(o for o in f["options"] if same(o, want))
            pick(f, exact)
        except Exception as e:
            warnings.append(f"مقدرتش أختار «{want}» في «{f['label']}»: {str(e)[:120]}")
        pfields, info, filt = scan()

    def try_filter(flt):
        try:
            runner._click({"target": flt, "timeout": 8})
            res = runner._wait_rows({"min": 1, "timeout": 12})
            return (int(res.split()[1]) if res.split()[1].isdigit() else 1), ""
        except Exception as e:
            return 0, str(e).splitlines()[0][:160]

    rows, last_err = 0, ""
    if filt:
        rows, last_err = try_filter(filt)

    # 2) auto: a list like «نوع المستند» opens the filter section and decides the data ->
    #    try its options one by one until the filter shows rows (never presses add / save)
    auto_pick = None
    if not rows and not choose:
        cands = [x for x in pfields if x["kind"] in ("select", "select2") and x["options"]
                 and text_match.is_placeholder(x["value"])
                 and not any(w in text_match.normalize(x["label"]) for w in ("رقم", "no", "number", "كود"))]
        first_with_filter = None
        for f in cands[:2]:
            for opt in f["options"][:12]:
                try:
                    pick(f, opt)
                except Exception:
                    continue
                pfields, info, flt2 = scan()
                if not flt2:
                    continue
                first_with_filter = first_with_filter or (f, opt)
                n, err = try_filter(flt2)
                if n:
                    rows, filt, auto_pick, last_err = n, flt2, (f, opt), ""
                    break
                last_err = err
            if rows:
                break
        if not rows and first_with_filter:
            f, opt = first_with_filter
            try:
                pick(f, opt)
                pfields, info, filt = scan()
                auto_pick = first_with_filter
            except Exception:
                pass
    if auto_pick:
        f, opt = auto_pick
        warnings.append(f"اخترت «{f['label'] or f['id']}» = «{opt}» "
                        + ("لأنه أول اختيار ظهر فيه مستندات" if rows else "عشان زرار المصفي يظهر")
                        + " — لو عايزة نوع تاني غيّري القيمة في الخطوات، أو اعملي سيناريو لكل نوع")
    if filt:
        info = driver.execute_script(POPUP_BUTTONS_JS, popup) or info   # buttons that appear with the table
        if not rows:
            warnings.append(f"بعد «{filt}»: {last_err or 'مظهرش صفوف'} — غالبًا مفيش مستندات بالفلاتر دي")
    else:
        warnings.append("مالقيتش زرار بحث/مصفي في النافذة حتى بعد ما جربت الاختيارات — ضيفيه بنفسك لو موجود")
    buttons = info.get("buttons", [])

    add = next((b["text"] for b in buttons if _classify(b["text"]) == "add"), "")
    shot = page.take_screenshot("inspect_popup")

    # ---- the suggested flow ----
    steps = [{"do": "click", "target": open_target}, {"do": "wait_popup"}]
    for f in pfields:
        if f["kind"] in ("select", "select2"):
            if f["value"] and not text_match.is_placeholder(f["value"]):
                step = {"do": "fill", "field": {"id": f["id"], "label": f["label"] or f["id"], "kind": f["kind"],
                                                "strategy": "fixed", "value": f["value"]}}
                if f["id"] in picked:
                    step["field"]["wait_after"] = 1.5      # it opens more fields / the filter button
                steps.append(step)
            elif f["required"]:
                steps.append({"do": "fill", "field": {"id": f["id"], "label": f["label"] or f["id"], "kind": f["kind"],
                                                      "strategy": "first", "value": ""}})
        elif f["kind"] == "date":
            steps.append({"do": "fill", "field": {"id": f["id"], "label": f["label"] or f["id"], "kind": "date",
                                                  "strategy": "fixed", "value": _date_token(f["label"])}})
        elif f["kind"] in ("text", "number", "textarea") and f["required"] and not f["value"]:
            steps.append({"do": "fill", "field": {"id": f["id"], "label": f["label"] or f["id"], "kind": f["kind"],
                                                  "strategy": "fixed", "value": "1" if f["kind"] == "number" else "test"}})
    if filt:
        steps += [{"do": "click", "target": filt}, {"do": "wait_rows", "min": 1}]
    if info.get("select_all"):
        steps.append({"do": "check", "target": info["select_all"]})
    elif info.get("head_checkbox"):
        steps.append({"do": "check", "target": "css:thead input[type=checkbox]"})
    else:
        steps.append({"do": "pick_rows", "count": 1})
    if add:
        steps.append({"do": "click", "target": add})
    else:
        warnings.append("مالقيتش زرار «إضافة» في النافذة — ضيفي خطوة الضغط عليه بنفسك")
    steps.append({"do": "close_popup", "optional": True})

    try:
        F.FlowRunner(page, filler)._close_popup({})
    except Exception:
        pass
    return {
        "add_url": _path_only(used_url).split("#")[0],
        "popup_title": title,
        "popup_fields": pfields,
        "buttons": buttons,
        "rows": rows,
        "flow": {"name": title or open_target, "after": after, "optional": False, "steps": steps},
        "warnings": warnings,
        "screenshot": shot,
    }
