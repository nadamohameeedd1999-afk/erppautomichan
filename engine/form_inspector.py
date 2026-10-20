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
    var p = el.parentElement, depth = 0;
    while (p && depth < 4 && !t) {
      var l2 = p.querySelector('label');
      if (l2 && !l2.contains(el)) t = txt(l2);
      p = p.parentElement; depth++;
    }
  }
  if (!t) t = el.getAttribute('placeholder') || el.getAttribute('aria-label') || el.getAttribute('title') || '';
  return t;
}
var out = [];
var els = root.querySelectorAll('input, select, textarea');
for (var i = 0; i < els.length; i++) {
  var el = els[i];
  var tag = el.tagName.toLowerCase();
  var type = (el.getAttribute('type') || '').toLowerCase();
  if (el.classList.contains('select2-search__field')) continue;
  if (el.closest('.select2-container, .dataTables_filter, .dataTables_length, nav, .navbar, header')) continue;
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
var els = root.querySelectorAll('button, input[type=submit], input[type=button], a.btn');
for (var i = 0; i < els.length; i++) {
  var b = els[i];
  if (b.closest('nav, .navbar, header, .select2-container, .dataTables_wrapper, .swal2-container, .modal-footer')) continue;
  var sel = b.id ? (b.tagName.toLowerCase() + '#' + b.id) : '';
  if (!sel) continue;
  if (seen[sel]) continue; seen[sel] = 1;
  var r = b.getBoundingClientRect();
  out.push({ selector: sel, id: b.id, text: txt(b).slice(0, 60),
             visible: r.width > 0 && r.height > 0, type: (b.getAttribute('type') || '').toLowerCase() });
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
    if (e.closest('nav, .navbar, header, .select2-container, .dataTables_wrapper')) return;
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
                f["suggested_strategy"] = "fixed"
            else:
                f["suggested_strategy"] = "keep" if f["value"] else "unique"
            f["options"] = text_match.real_options(f.get("options"))[:40]
            fields.append(f)

        if not fields:
            warnings.append("مالقيتش ولا حقل في الصفحة — اتأكدي إن رابط الإضافة بيفتح الفورم (شوفي اللقطة)")
        elif not any(f["required"] for f in fields):
            warnings.append("مالقيتش حقول إجبارية متعلّم عليها — علّمي على الحقول المهمة بنفسك")
        if any(f["in_table"] and f["visible"] for f in fields):
            warnings.append("الشاشة فيها جدول أصناف/سطور — حقول الجدول لسه مش مدعومة في المحرك العام")

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
