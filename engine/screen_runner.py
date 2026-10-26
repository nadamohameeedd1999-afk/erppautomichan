"""
Generic screen flow, driven by config/screens/<key>.json:

login -> list (remember first row) -> add page -> fill fields (strict)
      -> before-save buttons -> save -> alerts -> saved? -> new first row in list
"""
import time

import allure
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoAlertPresentException, UnexpectedAlertPresentException,
)

from config.settings import BASE_URL
from pages.base_page import BasePage
from pages.login_page import LoginPage
from utils.list_verify import first_row_text, wait_for_new_first_row
from utils.logger import logger
from engine import screen_config
from engine.flows import fill_with_flows
from engine.form_filler import FormFiller, FieldFillError

ERRORS_JS = r"""
function vis(e){ var r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; }
var out = [];
document.querySelectorAll('.field-validation-error, .invalid-feedback, .text-danger, .alert-danger, .toast-error, .validation-summary-errors li').forEach(function(e){
  var t = (e.innerText || '').replace(/\s+/g,' ').trim();
  if (t.replace(/[*\s]/g, '').length < 2) return;   // required-field asterisks
  if (vis(e) && out.indexOf(t) === -1) out.push(t);
});
return out.slice(0, 15);
"""


def _abs(url):
    return url if url.startswith("http") else BASE_URL.rstrip("/") + "/" + url.lstrip("/")


def _shot(page, name):
    path = page.take_screenshot(name)
    if path:
        try:
            allure.attach.file(path, name=name, attachment_type=allure.attachment_type.PNG)
        except Exception:
            pass
    return path


class ScreenRunner(BasePage):
    SWAL_POPUP = (By.CSS_SELECTOR, ".swal2-popup")

    def __init__(self, driver, cfg):
        super().__init__(driver)
        self.cfg = cfg
        self.filler = FormFiller(driver)
        self.alerts = []          # every alert / SweetAlert text we saw
        self.error_alerts = []    # the ones that look like errors

    # ---------- alerts ----------
    def accept_js_alert(self, timeout=2):
        try:
            WebDriverWait(self.driver, timeout).until(EC.alert_is_present())
            a = self.driver.switch_to.alert
            text = a.text
            a.accept()
            self.alerts.append(f"JS: {text}")
            logger.info(f"JS Alert: {text[:150]}")
            time.sleep(0.5)
            return text
        except (TimeoutException, NoAlertPresentException):
            return None

    def handle_swals(self, max_count=6, timeout=4, max_misses=2):
        count, misses = 0, 0
        while count < max_count and misses < (1 if count else max_misses):
            if self.accept_js_alert(timeout=1) is not None:
                count += 1
                misses = 0
                continue
            try:
                popup = WebDriverWait(self.driver, timeout).until(
                    EC.visibility_of_element_located(self.SWAL_POPUP))
            except TimeoutException:
                misses += 1
                continue
            info = self.driver.execute_script(r"""
                var p = arguments[0];
                function t(s){ var e = p.querySelector(s); return e ? (e.innerText||'').replace(/\s+/g,' ').trim() : ''; }
                var icon = p.querySelector('.swal2-icon.swal2-error, .swal2-icon.swal2-warning');
                var shown = icon && window.getComputedStyle(icon).display !== 'none';
                return {title: t('.swal2-title'), body: t('.swal2-html-container') || t('.swal2-content'),
                        error: !!(shown && icon.classList.contains('swal2-error')),
                        warning: !!(shown && icon.classList.contains('swal2-warning'))};
            """, popup)
            text = " — ".join(x for x in (info.get("title"), info.get("body")) if x)
            self.alerts.append(f"SweetAlert: {text}")
            if info.get("error"):
                self.error_alerts.append(text)
            logger.info(f"SweetAlert #{count + 1}: {text[:150]}")
            _shot(self, f"{self.cfg['key']}_swal_{count + 1}")
            try:
                btn = popup.find_element(By.CSS_SELECTOR, "button.swal2-confirm")
                self.driver.execute_script("arguments[0].click();", btn)
            except Exception:
                self.accept_js_alert(timeout=2)
            count += 1
            misses = 0
            try:
                WebDriverWait(self.driver, 3).until(EC.invisibility_of_element_located(self.SWAL_POPUP))
            except TimeoutException:
                pass
            time.sleep(0.8)
            if not self._on_add_page():   # the page moved on (saved) — nothing more to confirm
                break
        return count

    def page_errors(self):
        try:
            return self.driver.execute_script(ERRORS_JS) or []
        except Exception:
            return []

    # ---------- steps ----------
    def open_list(self):
        self.open(_abs(self.cfg["list_url"]))
        time.sleep(1)

    def open_add(self):
        sel = self.cfg.get("add_button")
        if sel:
            try:
                el = WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                self.driver.execute_script("arguments[0].click();", el)
                self.wait_for_preloader(timeout=20)
                time.sleep(1.5)
                if self._on_add_page():
                    return
                logger.warning(f"زرار الإضافة ({sel}) ما فتحش صفحة الإضافة — هفتح الرابط")
            except TimeoutException:
                logger.warning(f"زرار الإضافة ({sel}) مش موجود — هفتح الرابط")
        self.open(_abs(self.cfg["add_url"]))
        time.sleep(1.5)

    def _add_path(self):
        return self.cfg["add_url"].split("?")[0].lower()

    def _on_add_page(self):
        try:
            return self._add_path() in self.driver.current_url.lower()
        except UnexpectedAlertPresentException:
            self.accept_js_alert()
            return self._add_path() in self.driver.current_url.lower()

    def run_before_save(self):
        for a in self.cfg.get("before_save", []):
            logger.info(f"قبل الحفظ: {a['label']}")
            try:
                el = WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, a["selector"])))
            except TimeoutException:
                raise AssertionError(f"زرار '{a['label']}' ({a['selector']}) مش موجود في الصفحة")
            if a.get("force_visible"):
                self.driver.execute_script(
                    "if (window.getComputedStyle(arguments[0]).display === 'none') arguments[0].style.display = 'inline-block';", el)
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            self.driver.execute_script("arguments[0].click();", el)
            time.sleep(0.5)
            wait = 2
            while self.accept_js_alert(timeout=wait) is not None:
                wait = 1
            self.handle_swals(max_count=3, timeout=1.5, max_misses=1)
            time.sleep(a.get("wait_after", 1.5))

    def save(self):
        sel = self.cfg["save_button"]
        try:
            el = WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
        except TimeoutException:
            raise AssertionError(f"زرار الحفظ ({sel}) مش موجود")
        self.wait_for_preloader()
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.3)
        self.driver.execute_script("arguments[0].click();", el)
        logger.info("ضغطنا حفظ")
        time.sleep(0.8)
        self.handle_swals()

    def wait_saved(self):
        timeout = self.cfg.get("save_timeout", 40)
        end = time.time() + timeout
        while time.time() < end:
            self.accept_js_alert(timeout=1)
            if self.error_alerts:
                return False
            if not self._on_add_page() and "/login" not in self.driver.current_url.lower():
                logger.success(f"🎯 الصفحة اتنقلت بعد الحفظ: {self.driver.current_url}")
                return True
            # page stayed: a validation message means the form was rejected
            if self.page_errors() and time.time() > end - timeout + 6:
                return False
            time.sleep(0.5)
        return False

    def failure_reason(self):
        parts = []
        if self.error_alerts:
            parts.append("رسالة خطأ: " + " | ".join(self.error_alerts))
        errs = self.page_errors()
        if errs:
            parts.append("رسائل التحقق في الفورم: " + " | ".join(errs))
        empty = []
        for f in self.cfg["fields"]:
            if f["kind"] in ("select", "select2") and not f["id"].startswith("css:"):
                try:
                    from engine.text_match import is_placeholder
                    if is_placeholder(self.filler.selected_text(f["id"])):
                        empty.append(f["label"])
                except Exception:
                    pass
        if empty:
            parts.append("قوائم فاضية وقت الحفظ: " + "، ".join(empty))
        try:
            extra = self.driver.execute_script(r"""
                function lbl(e){
                  var l = e.id ? document.querySelector('label[for="' + CSS.escape(e.id) + '"]') : null;
                  return ((l && l.innerText) || e.id || e.name || '').replace(/\s*\*\s*$/, '').trim();
                }
                function vis(e){ var r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; }
                var invalid = [], emptyReq = [], toasts = [];
                document.querySelectorAll('.input-validation-error, [aria-invalid=true], .is-invalid').forEach(function(e){
                  var n = lbl(e); if (n && invalid.indexOf(n) === -1) invalid.push(n);
                });
                document.querySelectorAll('input[data-val-required], select[data-val-required], textarea[data-val-required]').forEach(function(e){
                  if (e.type === 'hidden' && !e.classList.contains('select2-hidden-accessible')) return;
                  var box = e.classList.contains('select2-hidden-accessible') && e.id ? document.getElementById('select2-' + e.id + '-container') : e;
                  if (!box || !vis(box)) return;
                  if (!String(e.value || '').trim()) { var n = lbl(e); if (n && emptyReq.indexOf(n) === -1) emptyReq.push(n); }
                });
                document.querySelectorAll('.toast, .toast-message, .toastr, .noty_body, .notifyjs-corner, .alert').forEach(function(e){
                  var t = (e.innerText || '').replace(/\s+/g, ' ').trim(); if (t && vis(e) && toasts.indexOf(t) === -1) toasts.push(t);
                });
                return {invalid: invalid.slice(0, 15), emptyReq: emptyReq.slice(0, 15), toasts: toasts.slice(0, 5)};
            """) or {}
            if extra.get("invalid"):
                parts.append("حقول متعلّم عليها غلط (أحمر): " + "، ".join(extra["invalid"]))
            if extra.get("emptyReq"):
                parts.append("حقول إجبارية لسه فاضية: " + "، ".join(extra["emptyReq"]))
            if extra.get("toasts"):
                parts.append("رسايل ظاهرة: " + " | ".join(extra["toasts"]))
        except Exception:
            pass
        if self.alerts and not self.error_alerts:
            parts.append("آخر رسالة: " + self.alerts[-1])
        return "\n   ".join(parts) or "مفيش رسالة خطأ ظاهرة"


def login(driver, credentials):
    from engine import session_cache
    if session_cache.restore(driver):
        logger.success("♻️ استخدمت جلسة الدخول المحفوظة (من غير شاشة الدخول)")
        return
    page = LoginPage(driver)
    page.load()
    page.login(credentials["username"], credentials["password"])   # saves the session itself


def _load_any(key):
    """'cash_receipt' (screen) or 'customer__new' (scenario) -> config."""
    from engine import scenario_config
    if scenario_config.SEP in key:
        return scenario_config.load_by_full_key(key)
    return screen_config.load(key)


READ_VALUES_JS = r"""
var out = {};
arguments[0].forEach(function (id) {
  var el = id.indexOf('css:') === 0 ? document.querySelector(id.slice(4)) : document.getElementById(id);
  if (!el) { out[id] = null; return; }
  if (el.tagName === 'SELECT') {
    var o = el.options[el.selectedIndex]; out[id] = o ? o.text.replace(/\s+/g, ' ').trim() : '';
  } else if (el.type === 'checkbox') { out[id] = el.checked ? 'true' : 'false'; }
  else { out[id] = (el.value || '').trim(); }
});
return out;
"""

OPEN_ROW_JS = r"""
var sel = arguments[0];
var row = document.querySelector('table tbody tr');
if (!row) return null;
var cands = sel ? row.querySelectorAll(sel) : row.querySelectorAll(
  "a[href*='AddEdit'], a[href*='Edit'], a[href*='Details'], a[href*='View'], a[href*='Show'], a[title*='تعديل'], a[title*='عرض']");
for (var i = 0; i < cands.length; i++) {
  var h = cands[i].getAttribute('href') || '';
  if (h && h !== '#' && h.indexOf('javascript') !== 0 && h.indexOf('Delete') === -1) return {href: cands[i].href};
}
var b = row.querySelector("[onclick*='Edit'], [onclick*='edit'], .btn-edit, .fa-edit, .fa-pencil, .bi-pencil");
if (b) { (b.closest('a,button') || b).click(); return {clicked: true}; }
return null;
"""


def _same(a, b):
    from engine.text_match import normalize
    a, b = normalize(a), normalize(b)
    if a == b:
        return True
    try:
        return float(a.replace(",", "")) == float(b.replace(",", ""))
    except ValueError:
        return bool(a) and bool(b) and (a in b or b in a)


def check_saved_values(r, cfg, steps):
    """Open the newly saved record and compare each filled field with what we filled."""
    driver = r.driver
    driver.get(_abs(cfg["list_url"]))
    r.wait_for_preloader()
    time.sleep(1.5)
    hit = driver.execute_script(OPEN_ROW_JS, cfg["verify"].get("open_selector") or "")
    if not hit:
        logger.warning("مالقيتش لينك فتح/تعديل في أول صف — مش هقدر أراجع القيم (حددي selector في الإعداد)")
        return {"checked": False, "reason": "مفيش لينك فتح في أول صف"}
    if hit.get("href"):
        driver.get(hit["href"])
    r.wait_for_preloader(timeout=20)
    time.sleep(2.5)
    want = {s["id"]: s for s in steps if s.get("ok") and s.get("result") not in (None, "")}
    if not want:
        return {"checked": False, "reason": "مفيش قيم أقارنها"}
    got = driver.execute_script(READ_VALUES_JS, list(want.keys())) or {}
    bad = [k for k in want if got.get(k) is not None and not _same(want[k]["result"], got.get(k))]
    if bad:                                   # Select2 lists on edit pages sometimes load late
        time.sleep(2.5)
        got = driver.execute_script(READ_VALUES_JS, list(want.keys())) or {}
    rows, mismatches = [], []
    for k, s in want.items():
        v = got.get(k)
        ok = v is None or _same(s["result"], v)
        rows.append({"label": s["label"], "filled": s["result"], "saved": v, "ok": ok})
        if not ok:
            mismatches.append(f"{s['label']}: اتملى '{s['result']}' بس اتسجل '{v}'")
    _shot(r, f"{cfg['key']}_saved_record")
    return {"checked": True, "rows": rows, "mismatches": mismatches}


def run_screen(driver, credentials, key_or_cfg, save=True, do_login=True, _depth=0):
    """Runs the flow. Returns a result dict; raises AssertionError on failure."""
    cfg = key_or_cfg if isinstance(key_or_cfg, dict) else screen_config.load(key_or_cfg)
    cfg = screen_config.normalize(cfg)
    driver.implicitly_wait(0)   # the engine uses explicit waits; implicit waits slow every "is it there?" check
    r = ScreenRunner(driver, cfg)
    result = {"key": cfg["key"], "saved": False, "steps": [], "alerts": r.alerts,
              "first_row_before": None, "first_row_after": None, "screenshots": []}
    start = time.time()

    with allure.step("تسجيل الدخول"):
        if do_login:
            login(driver, credentials)

    if save and cfg["verify"]["new_first_row"]:
        with allure.step("قراءة أول صف قبل الإضافة"):
            r.open_list()
            result["first_row_before"] = first_row_text(driver)
            logger.info(f"أول صف قبل: {str(result['first_row_before'])[:120]}")

    with allure.step("فتح صفحة الإضافة"):
        r.open_add()
        assert r._on_add_page(), f"مش في صفحة الإضافة: {driver.current_url}"

    with allure.step("ملء الحقول"):
        created = []
        while True:
            try:
                fill_with_flows(r, cfg, r.filler, result["screenshots"])
                break
            except FieldFillError as e:
                f = e.field or {}
                maker = f.get("create_with")
                if e.missing and maker and not save:
                    result["steps"] = r.filler.steps
                    e.partial_result = result
                    raise AssertionError(f"{e}\n   (في التجربة بدون حفظ مش بنعمل بيانات — في التشغيل الكامل هتتعمل بـ «{maker}»)") from None
                if not (e.missing and maker and maker not in created and _depth < 2):
                    result["steps"] = r.filler.steps
                    result["screenshots"].append(_shot(r, f"{cfg['key']}_before_save"))
                    e.partial_result = result      # so the dashboard can still show which fields passed
                    raise
                # البيانات المطلوبة مش موجودة -> نعملها بالشاشة/السيناريو المحدد وبعدين نرجع
                logger.warning(f"🧩 {f.get('label')}: '{f.get('value')}' مش موجود — هعمله الأول بـ «{maker}»")
                with allure.step(f"تجهيز البيانات: {maker}"):
                    try:
                        pre = run_screen(driver, credentials, _load_any(maker), save=True,
                                         do_login=False, _depth=_depth + 1)
                    except Exception as pe:
                        raise AssertionError(f"كنت محتاج أعمل '{f.get('value')}' بـ «{maker}» وده فشل:\n   {pe}") from None
                created.append(maker)
                result.setdefault("created_data", []).append({"field": f.get("label"), "with": maker,
                                                              "value": f.get("value"), "ok": pre.get("saved")})
                logger.success(f"✅ اتعمل بـ «{maker}» — هرجع أكمّل {cfg['name_ar']}")
                r.filler = FormFiller(driver)
                if save and cfg["verify"]["new_first_row"]:
                    r.open_list()
                    result["first_row_before"] = first_row_text(driver)
                r.open_add()
                assert r._on_add_page(), f"مش في صفحة الإضافة: {driver.current_url}"
            except Exception as e:
                result["steps"] = r.filler.steps
                e.partial_result = result
                raise
        result["steps"] = r.filler.steps
        result["screenshots"].append(_shot(r, f"{cfg['key']}_before_save"))

    if not save:
        logger.success("تمت التعبئة (تجربة بدون حفظ)")
        result["seconds"] = round(time.time() - start, 1)
        return result

    with allure.step("أزرار قبل الحفظ"):
        r.run_before_save()

    with allure.step("حفظ"):
        r.save()
        ok = r.wait_saved()
        result["screenshots"].append(_shot(r, f"{cfg['key']}_after_save"))
        if not ok:
            raise AssertionError(
                f"الحفظ ما نجحش ({cfg['name_ar']}). URL: {driver.current_url}\n   {r.failure_reason()}")
        result["saved"] = True

    if cfg["verify"]["new_first_row"]:
        with allure.step("التأكد إن صف جديد ظهر في القايمة"):
            after = wait_for_new_first_row(driver, _abs(cfg["list_url"]), result["first_row_before"],
                                           timeout=cfg["verify"]["timeout"])
            result["first_row_after"] = after
            result["screenshots"].append(_shot(r, f"{cfg['key']}_list_after_save"))
            assert after is not None, (
                f"مظهرش صف جديد في القايمة بعد الحفظ. أول صف كان: {str(result['first_row_before'])[:120]}")
            missing = [t for t in cfg["verify"]["row_contains"] if t not in after]
            if missing:
                msg = f"الصف الجديد مش فيه: {missing} — الصف: {after[:150]}"
                if cfg["verify"]["row_contains_strict"]:
                    raise AssertionError(msg)
                logger.warning(msg)

    if cfg["verify"].get("open_saved"):
        with allure.step("فتح السند المحفوظ ومراجعة القيم"):
            chk = check_saved_values(r, cfg, result["steps"])
            result["saved_check"] = chk
            if chk.get("checked"):
                for row in chk["rows"]:
                    mark = "✅" if row["ok"] else "❌"
                    logger.info(f"{mark} مراجعة {row['label']}: اتملى '{row['filled']}' — اتسجل '{row['saved']}'")
                if chk["mismatches"]:
                    raise AssertionError("القيم اللي اتسجلت مختلفة عن اللي اتملت:\n   " + "\n   ".join(chk["mismatches"]))
                logger.success("✅ كل القيم اتسجلت صح")

    result["seconds"] = round(time.time() - start, 1)
    logger.success(f"✅ {cfg['name_ar']}: اتحفظ وظهر في القايمة ({result['seconds']} ثانية)")
    return result


def run_screen_test(driver, credentials, key):
    """Entry used by the generated pytest files."""
    cfg = screen_config.load(key)
    logger.info(f"▶ منشئ الشاشات: {cfg['name_ar']} ({key}) — {len(cfg['fields'])} حقل")
    try:
        allure.dynamic.title(cfg["name_ar"])
    except Exception:
        pass
    try:
        run_screen(driver, credentials, cfg, save=True)
    except FieldFillError as e:
        raise AssertionError(f"وقف عند حقل: {e}") from None


def run_scenario_test(driver, credentials, screen_key, scenario_key):
    """Entry used by the generated scenario pytest files."""
    from engine import scenario_config
    cfg = scenario_config.load(screen_key, scenario_key)
    logger.info(f"▶ سيناريو: {cfg['name_ar']} ({cfg['key']}) — {len(cfg['fields'])} حقل")
    try:
        allure.dynamic.title(cfg["name_ar"])
    except Exception:
        pass
    try:
        run_screen(driver, credentials, cfg, save=True)
    except FieldFillError as e:
        raise AssertionError(f"وقف عند حقل: {e}") from None
