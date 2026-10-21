"""
Form Filler — fills a form from a screen config.

STRICT RULE: if a fixed / search value is not in the list, it STOPS with a clear
message that lists the options that do exist. It never picks another value silently.
"""
import random
import time
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from utils.logger import logger
from engine import text_match


class FieldFillError(AssertionError):
    """Raised when a field cannot be filled the way the config asks."""

    def __init__(self, field, message, options=None, missing=False):
        self.field = field
        self.options = options or []
        self.missing = missing          # True = the wanted value isn't in the list (data problem)
        label = field.get("label") or field.get("id")
        text = f"[{label} / {field.get('id')}] {message}"
        if options is not None:
            text += f"\n   الخيارات المتاحة: {text_match.preview(options)}"
        super().__init__(text)


OPTIONS_JS = r"""
var s = document.getElementById(arguments[0]);
if (!s) return null;
var out = [];
for (var i = 0; i < s.options.length; i++) out.push([s.options[i].text.replace(/\s+/g,' ').trim(), s.options[i].value]);
return out;
"""

SET_INDEX_JS = r"""
var s = document.getElementById(arguments[0]);
if (!s) return false;
s.selectedIndex = arguments[1];
if (window.jQuery) { jQuery(s).trigger('change'); jQuery(s).trigger({type: 'select2:select', params: {data: {id: s.value, text: s.options[s.selectedIndex].text}}}); }
else { s.dispatchEvent(new Event('change', {bubbles: true})); }
return s.options[s.selectedIndex].text.trim();
"""

SELECTED_TEXT_JS = r"""
var s = document.getElementById(arguments[0]);
if (!s || s.selectedIndex < 0 || !s.options[s.selectedIndex]) return '';
return s.options[s.selectedIndex].text.replace(/\s+/g,' ').trim();
"""

SET_VALUE_JS = r"""
var el = arguments[0], v = arguments[1];
var tag = el.tagName;
if (tag !== 'INPUT' && tag !== 'TEXTAREA') {
  // not a text box (e.g. a wrapper div / span) -> use the input inside it if there is one
  var inner = el.querySelector('input:not([type=hidden]), textarea');
  if (!inner) return '__NOT_INPUT__:' + tag;
  el = inner; tag = el.tagName;
}
try { el.focus(); } catch (e) {}
var proto = tag === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
try { Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v); } catch (e) { el.value = v; }
['input', 'change', 'keyup'].forEach(function (n) { el.dispatchEvent(new Event(n, {bubbles: true})); });
if (window.jQuery) { jQuery(el).trigger('change'); }
el.dispatchEvent(new Event('blur', {bubbles: true}));
return el.value;
"""

SIG_JS = r"""
var s = document.getElementById(arguments[0]);
if (!s) return null;
var t = [];
for (var i = 0; i < s.options.length; i++) t.push(s.options[i].value + '=' + s.options[i].text.trim());
return t.join('|');
"""


def _date_format(field):
    fmt = field.get("format") or ""
    if fmt:
        return fmt
    return "%Y-%m-%d"


class FormFiller:

    def __init__(self, driver):
        self.driver = driver
        self.steps = []
        self._counter = 0

    # ---------- locating ----------
    def _find(self, field, timeout=10):
        fid = field["id"]
        by = (By.CSS_SELECTOR, fid[4:]) if fid.startswith("css:") else (By.ID, fid)
        try:
            return WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located(by))
        except TimeoutException:
            raise FieldFillError(field, "الحقل مش موجود في الصفحة (اتأكد من الـ id)")

    def options(self, select_id):
        raw = self.driver.execute_script(OPTIONS_JS, select_id)
        return [t for t, _ in (raw or [])]

    def _option_pairs(self, select_id):
        return self.driver.execute_script(OPTIONS_JS, select_id) or []

    def selected_text(self, select_id):
        return self.driver.execute_script(SELECTED_TEXT_JS, select_id) or ""

    def signature(self, select_id):
        try:
            return self.driver.execute_script(SIG_JS, select_id)
        except Exception:
            return None

    def wait_for_real_options(self, field, timeout):
        end = time.time() + timeout
        while time.time() < end:
            if text_match.real_options(self.options(field["id"])):
                return True
            time.sleep(0.4)
        return False

    # ---------- dropdowns ----------
    def _select2_search_pick(self, field, wanted, exact):
        """For Select2 lists that load options by typing (AJAX)."""
        sid = field["id"]
        try:
            box = self.driver.find_element(By.ID, f"select2-{sid}-container")
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", box)
            box.click()
            search = WebDriverWait(self.driver, 3).until(EC.visibility_of_element_located(
                (By.CSS_SELECTOR, "span.select2-container--open input.select2-search__field")))
            search.clear()
            search.send_keys(wanted)
            time.sleep(1.5)
            items = self.driver.find_elements(
                By.CSS_SELECTOR,
                "span.select2-container--open li.select2-results__option:not(.select2-results__message)")
            texts = [i.text.strip() for i in items]
            idx = text_match.find_exact(texts, wanted) if exact else text_match.find_contains(texts, wanted)
            if idx == -1:
                search.send_keys(Keys.ESCAPE)
                return None, texts
            chosen = texts[idx]
            items[idx].click()
            time.sleep(0.4)
            return chosen, texts
        except Exception as e:
            logger.debug(f"select2 search {sid}: {str(e)[:120]}")
            try:
                self.driver.execute_script("document.body.click();")
            except Exception:
                pass
            return None, []

    def fill_select(self, field):
        sid = field["id"]
        if sid.startswith("css:"):
            raise FieldFillError(field, "القوائم لازم يكون ليها id")
        self._find(field)
        strategy = field["strategy"]
        wanted = field.get("value", "")

        if strategy == "keep":
            cur = self.selected_text(sid)
            if field.get("required") and text_match.is_placeholder(cur):
                raise FieldFillError(field, "الحقل إجباري وفاضي (الطريقة 'سيبه زي ما هو')", self.options(sid))
            return cur

        # options may still be loading (dependent list)
        has_options = self.wait_for_real_options(field, field.get("timeout", 15))
        pairs = self._option_pairs(sid)
        texts = [t for t, _ in pairs]

        if strategy == "first":
            if not has_options:
                parent = field.get("depends_on")
                why = f" بعد اختيار {parent}" if parent else ""
                raise FieldFillError(field, f"مفيش ولا خيار في القايمة{why}", texts)
            idx = next(i for i, (t, v) in enumerate(pairs) if not text_match.is_placeholder(t))
        else:
            exact = strategy == "fixed"
            idx = text_match.find_exact(texts, wanted) if exact else text_match.find_contains(texts, wanted)
            if idx == -1:
                # maybe values are matched (e.g. id "4")
                idx = next((i for i, (_, v) in enumerate(pairs) if v and v == wanted.strip()), -1)
            if idx == -1 and field["kind"] == "select2":
                chosen, seen = self._select2_search_pick(field, wanted, exact)
                if chosen:
                    return self._confirm_select(field, chosen)
                texts = texts if text_match.real_options(texts) else seen
            if idx == -1:
                how = "بالظبط" if exact else "يحتوي على"
                why = ""
                if not text_match.real_options(texts) and field.get("depends_on"):
                    why = f" — القايمة فاضية بعد اختيار الحقل اللي قبله ({field['depends_on']})"
                raise FieldFillError(field, f"القيمة المطلوبة '{wanted}' مش موجودة ({how}){why}", texts, missing=True)

        chosen = self.driver.execute_script(SET_INDEX_JS, sid, idx)
        return self._confirm_select(field, chosen)

    def _confirm_select(self, field, chosen):
        time.sleep(0.3)
        actual = self.selected_text(field["id"])
        if text_match.normalize(actual) != text_match.normalize(chosen):
            raise FieldFillError(field, f"اخترنا '{chosen}' بس الحقل فضل '{actual}'")
        return actual

    # ---------- inputs ----------
    def _value_for(self, field):
        s = field["strategy"]
        v = field.get("value", "")
        now = datetime.now()
        if s == "today":
            return now.strftime(_date_format(field))
        if s == "unique":
            self._counter += 1
            return (v or "AUTO-{ts}").format(
                ts=now.strftime("%Y%m%d%H%M%S"), date=now.strftime("%Y%m%d"),
                n=self._counter, rand=random.randint(1000, 9999))
        return v

    def fill_input(self, field):
        el = self._find(field)
        s = field["strategy"]
        if s == "keep":
            cur = el.get_attribute("value") or ""
            if field.get("required") and not cur.strip():
                raise FieldFillError(field, "الحقل إجباري وفاضي (الطريقة 'سيبه زي ما هو')")
            return cur
        if field["kind"] == "checkbox":
            want = s == "check" or (s == "fixed" and str(field.get("value")).lower() in ("1", "true", "yes", "نعم"))
            if el.is_selected() != want:
                self.driver.execute_script("arguments[0].click();", el)
            return "true" if el.is_selected() else "false"
        if s in ("first", "check", "uncheck"):
            raise FieldFillError(field, f"الطريقة '{s}' مش مناسبة لحقل كتابة")

        value = self._value_for(field)
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        try:
            if el.get_attribute("readonly") is None and el.is_enabled() and el.is_displayed():
                el.clear()
                el.send_keys(value)
        except Exception:
            pass
        actual = el.get_attribute("value") or ""
        if actual != value:
            actual = self.driver.execute_script(SET_VALUE_JS, el, value) or ""
            if actual.startswith("__NOT_INPUT__"):
                raise FieldFillError(field, f"الـ id ده مش خانة كتابة (ده عنصر {actual.split(':')[1]}) — "
                                            "اتأكدي إنه id الحقل نفسه")
        if actual.strip() != value.strip():
            # number inputs may reformat (200 -> 200.00)
            try:
                if float(actual.replace(",", "")) == float(value.replace(",", "")):
                    return actual
            except ValueError:
                pass
            raise FieldFillError(field, f"كتبنا '{value}' بس الحقل فيه '{actual}'")
        try:
            el.send_keys(Keys.TAB)
        except Exception:
            pass
        return actual

    # ---------- all ----------
    def fill_field(self, field):
        if field["kind"] in ("select", "select2"):
            return self.fill_select(field)
        # the config says "text" but the element is really a <select> (kind picked wrong) -> treat as a list
        el = self._find(field)
        if el.tag_name.lower() == "select" and not field["id"].startswith("css:"):
            if field["strategy"] in ("unique", "today"):
                raise FieldFillError(field, "الحقل ده قايمة مش خانة كتابة — غيّري النوع لـ قايمة")
            return self.fill_select({**field, "kind": "select2"})
        return self.fill_input(field)

    def fill_all(self, fields):
        dependents = {}
        for f in fields:
            if f.get("depends_on"):
                dependents.setdefault(f["depends_on"], []).append(f)

        total = len(fields)
        for i, field in enumerate(fields, 1):
            label = field.get("label") or field["id"]
            logger.info(f"{i}/{total}) {label} [{field['strategy']}] {field.get('value') or ''}")
            kids = dependents.get(field["id"], [])
            before = {k["id"]: self.signature(k["id"]) for k in kids}
            t0 = time.time()
            try:
                result = self.fill_field(field)
            except FieldFillError as e:
                self.steps.append({"id": field["id"], "label": label, "strategy": field["strategy"],
                                   "wanted": field.get("value", ""), "result": None, "ok": False,
                                   "error": str(e), "seconds": round(time.time() - t0, 1)})
                logger.error(f"❌ {e}")
                raise
            self.steps.append({"id": field["id"], "label": label, "strategy": field["strategy"],
                               "wanted": field.get("value", ""), "result": result, "ok": True,
                               "seconds": round(time.time() - t0, 1)})
            logger.success(f"✅ {label} = {result}")

            # wait for dependent lists to reload after this choice
            if kids:
                end = time.time() + min(8, max(k.get("timeout", 15) for k in kids))
                while time.time() < end:
                    if all(self.signature(k["id"]) != before[k["id"]] for k in kids):
                        break
                    time.sleep(0.4)
                time.sleep(0.5)
            time.sleep(field.get("wait_after", 0.5))
        return self.steps
