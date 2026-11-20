"""
One employee's own browser on NQ ERP (Chrome through Selenium): signs in with THEIR user, reads the menu they are allowed
to see (= their permissions on the system), opens screens and measures them, takes a picture of their screen.
"""
import re
import time

from simulation.settings import RUNS

SHOTS = RUNS / "shots"

MENU_JS = r"""
const out = [], seen = new Set();
const txt = e => (e && (e.innerText || e.textContent) || '').replace(/\s+/g, ' ').trim();
document.querySelectorAll('a[href]').forEach(a => {
  const h = a.getAttribute('href') || '';
  if (!h || h[0] === '#' || /^(javascript|mailto|tel):/i.test(h)) return;
  let u; try { u = new URL(h, location.href); } catch (e) { return; }
  if (u.origin !== location.origin) return;
  const p = u.pathname + u.search;
  if (p === '/' || seen.has(p) || /logout|logoff|signout|\/login/i.test(p)) return;
  seen.add(p);
  const name = txt(a).slice(0, 80) || a.getAttribute('title') || '';
  if (!name) return;
  let mod = '', li = a.closest('li'), top = li;
  while (li) { top = li; li = li.parentElement && li.parentElement.closest('li'); }
  if (top && top !== a.closest('li')) { const h2 = top.querySelector(':scope > a, :scope > span, :scope > div'); mod = txt(h2).slice(0, 60); }
  const card = a.closest('.card'); if (!mod && card) { const g = card.querySelector('.card-body .h3, .card-header, h3'); mod = txt(g).slice(0, 60); }
  out.push({path: p, name: name, module: mod});
});
return out;
"""
ERR = re.compile(r"(server error in|runtime error|unhandled exception|an error occurred while processing|sqlexception|stack trace:|exception details|"
                 r"حدث خطأ غير متوقع|خطأ في الخادم)", re.I)
DENIED = re.compile(r"(ليس لديك صلاحية|لا تملك صلاحية|غير مصرح|access denied|unauthori[sz]ed|not authorized|403)", re.I)
ROW_JS = r"""
const row = [...document.querySelectorAll('table tbody tr')].find(r => r.querySelector('a[href], [onclick]') && !r.querySelector('.dataTables_empty'));
if (!row) return null;
const href = a => { const h = a && a.getAttribute('href'); return h && h !== '#' && !/^javascript/i.test(h) ? a.href : ''; };
const by = (sel, test) => [...row.querySelectorAll(sel)].map(e => e.closest('a') || e).find(test || (() => true));
const edit = by('a[href*="AddEdit/" i], a[href*="/Edit/" i], i.fa-edit, i.fa-pencil, i.bi-pencil', a => { const h = href(a); return h && !/TermsAllocation|AddEdit\/0\b/i.test(h); });
const print = by('i.fa-print, a[href*="print=true" i], a[href*="/Report/" i]', a => !!href(a));
const del = by('i.fa-trash, i.fa-trash-alt, i.fa-times, [title*="حذف"], [onclick*="Delete" i]');
return {edit: href(edit), print: href(print), del: !!del, cells: [...row.querySelectorAll('td')].slice(0, 4).map(td => td.innerText.trim().slice(0, 30))};
"""
VIEWER_JS = r"""
const t = document.body ? document.body.innerText : '';
if (/Error when trying to populate the datasource|An error occurred|حدث خطأ/i.test(t)) return 'error:' + (t.match(/(Error when trying to populate the datasource[^\n]*|An error occurred[^\n]*|حدث خطأ[^\n]*)/i) || [''])[0].slice(0, 160);
const vis = e => e && e.getBoundingClientRect().width > 0 && getComputedStyle(e).display !== 'none';
const busy = vis(document.querySelector('.dxrd-preview-progress')) || vis(document.querySelector('.dxrd-report-preview-content-loading-panel'));
// a drawn page: text bricks, or the page picture DevExpress draws
const drawn = !!document.querySelector('.dxrd-report-preview-brick')
  || Array.prototype.some.call(document.querySelectorAll('.dxrd-report-preview img'), i => i.complete && i.naturalWidth > 0 && i.getBoundingClientRect().width > 100);
if (!busy && drawn) return 'ok';
const submit = document.querySelector('.dxrdp-parameters-submit');
if (!busy && vis(submit)) return 'params';
if (!document.querySelector('.dxrd-preview, .dxrd-report-preview') && document.readyState === 'complete' && t.length > 50) return 'ok';
return '';
"""
TIMING_JS = "var t = performance.getEntriesByType('navigation')[0]; return t ? Math.round(t.loadEventEnd || t.duration) : null;"


class ErpSession:
    def __init__(self, base_url, user, password, visible=False):
        self.base, self.user, self._pw, self.visible = base_url.rstrip("/"), user, password, visible
        self.driver = None
        self.menu = []

    # ------------------------------------------------------------------ browser
    def _start(self):
        try:                                             # the dashboard's own Chrome setup: the right chromedriver on the server
            from tests.conftest import _build_options, _create_driver   # (CHROME_BIN / CHROMEDRIVER_PATH), memory-safe flags, crash recovery
            o = _build_options()
            if not self.visible:
                o.add_argument("--headless=new")
            o.add_argument("--window-size=1366,850")
            self.driver = _create_driver(o)
            self.driver.set_page_load_timeout(90)
            return
        except ImportError:
            pass
        from selenium import webdriver
        o = webdriver.ChromeOptions()
        if not self.visible:
            o.add_argument("--headless=new")
        o.add_argument("--window-size=1366,850")
        o.add_argument("--lang=ar")
        o.add_argument("--disable-gpu")
        o.add_argument("--no-first-run")
        o.add_experimental_option("excludeSwitches", ["enable-logging"])
        self.driver = webdriver.Chrome(options=o)        # Selenium Manager brings the matching chromedriver
        self.driver.set_page_load_timeout(90)

    def close(self):
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
        self.driver = None

    # ------------------------------------------------------------------ sign in (NQ ERP: userName / password, activity + branch filled by the site)
    def _wait_ready(self, timeout=25):
        """the page shows a loading cover first: wait until it is gone"""
        d, t0 = self.driver, time.time()
        while time.time() - t0 < timeout:
            try:
                busy = d.execute_script("""
                  if (document.readyState !== 'complete') return true;
                  const p = document.querySelector('#preloader, .preloader, .loader-wrapper, #loader, .page-loader, .pace-active');
                  if (!p) return false;
                  const st = getComputedStyle(p);
                  return st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0' && p.offsetParent !== null;""")
            except Exception:
                busy = True
            if not busy:
                return
            time.sleep(.4)

    def _skip_intro(self, timeout=12):
        """NQ ERP's login page starts with an intro animation (#login-intro) over the form: press «تخطي», or hide it"""
        from selenium.webdriver.common.by import By
        t0 = time.time()
        while time.time() - t0 < timeout:
            intro = [e for e in self.driver.find_elements(By.ID, "login-intro") if e.is_displayed()]
            if not intro:
                return
            for b in self.driver.find_elements(By.CSS_SELECTOR, "#login-intro .li-skip, .li-skip"):
                try:
                    if b.is_displayed():
                        b.click()
                        break
                except Exception:
                    self.driver.execute_script("arguments[0].click();", b)
            time.sleep(.8)
        self.driver.execute_script("const i = document.getElementById('login-intro'); if (i) i.remove();")

    def _visible(self, selectors, timeout=25):
        """the first VISIBLE element among the selectors (pages often have hidden copies)"""
        from selenium.webdriver.common.by import By
        t0 = time.time()
        while time.time() - t0 < timeout:
            for how, sel in selectors:
                for el in self.driver.find_elements(how, sel):
                    try:
                        if el.is_displayed() and el.is_enabled():
                            return el
                    except Exception:
                        pass
            time.sleep(.4)
        return None

    def _type(self, el, text):
        """type like a person; if the browser refuses (covered / animated field) set it by script and fire the events the page listens to"""
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
            el.click()
            el.clear()
            el.send_keys(text)
            return
        except Exception:
            pass
        self.driver.execute_script("""const el = arguments[0], v = arguments[1];
            el.focus(); el.value = v;
            for (const ev of ['input', 'change', 'keyup', 'blur']) el.dispatchEvent(new Event(ev, {bubbles: true}));
            if (window.jQuery) jQuery(el).trigger('input').trigger('change').trigger('keyup').trigger('blur');""", el, text)

    # ------------------------------------------------------------------ sign in (NQ ERP: userName / password, activity + branch filled by the site)
    def login(self):
        from selenium.webdriver.common.by import By
        if not self.driver:
            self._start()
        d = self.driver
        d.get(self.base + "/Login")
        self._wait_ready()
        self._skip_intro()
        u = self._visible([(By.ID, "userName"), (By.CSS_SELECTOR, "input[name*='user' i]"), (By.CSS_SELECTOR, "input[type=email]"), (By.CSS_SELECTOR, "input[type=text]")])
        if not u:
            raise RuntimeError("صفحة الدخول ما ظهرتش (مالقيتش خانة اسم المستخدم) — اتأكد من لينك الموقع")
        self._type(u, self.user)
        time.sleep(3)                                   # the site loads the user's activities and branches
        p = self._visible([(By.ID, "password"), (By.CSS_SELECTOR, "input[type=password]")], 15)
        if not p:
            raise RuntimeError("مالقيتش خانة كلمة السر")
        self._type(p, self._pw)
        time.sleep(1)
        d.execute_script("""for (const id of ['cmbact', 'cmbbranch']) { const s = document.getElementById(id);
              if (s && !s.value) { const o = [...s.options].find(o => o.value); if (o) { s.value = o.value; s.dispatchEvent(new Event('change', {bubbles: true}));
              if (window.jQuery) jQuery(s).trigger('change'); } } }""")
        for _ in range(30):
            if not d.execute_script("var b = document.querySelector('button.btn-login, button[type=submit], input[type=submit]'); return !!(b && b.disabled);"):
                break
            time.sleep(1)
        btn = self._visible([(By.CSS_SELECTOR, "button.btn-login"), (By.CSS_SELECTOR, "button[type=submit]"), (By.CSS_SELECTOR, "input[type=submit]")], 10)
        if not btn:
            raise RuntimeError("مالقيتش زرار الدخول")
        try:
            btn.click()
        except Exception:
            d.execute_script("arguments[0].click();", btn)
        for _ in range(60):
            time.sleep(.5)
            if "/login" not in d.current_url.lower():
                break
        if "/login" in d.current_url.lower():
            msg = d.execute_script("var e = document.querySelector('.validation-summary-errors, .field-validation-error, .alert-danger, .toast-message, .swal2-html-container, .text-danger');"
                                   "return e ? e.innerText.trim() : '';") or "اسم المستخدم أو كلمة السر غلط"
            self.shot("_login_fail")
            raise RuntimeError(f"الدخول ما نجحش: {msg[:150]}")
        self._wait_ready()
        time.sleep(1.5)
        self.menu = d.execute_script(MENU_JS) or []
        return {"menu": self.menu, "url": d.current_url}

    def _alive(self):
        try:
            return self.driver is not None and "/login" not in self.driver.current_url.lower()
        except Exception:
            return False

    # ------------------------------------------------------------------ work on a screen
    def open(self, path, shot_name=""):
        """opens the screen and tells what happened: {kind: ok|slow|error|denied|login, ms, msg}"""
        if not self._alive():
            self.close()
            self.login()
        d = self.driver
        t0 = time.time()
        try:
            d.get(self.base + path if path.startswith("/") else path)
        except Exception as e:
            return {"kind": "error", "ms": int((time.time() - t0) * 1000), "msg": f"الصفحة ما فتحتش: {type(e).__name__}"}
        time.sleep(.8)
        ms = d.execute_script(TIMING_JS) or int((time.time() - t0) * 1000)
        try:
            body = d.execute_script("return document.body ? document.body.innerText.slice(0, 5000) : ''") or ""
        except Exception:
            body = ""
        if shot_name:
            self.shot(shot_name)
        if "/login" in d.current_url.lower():
            return {"kind": "login", "ms": ms, "msg": "رجع لشاشة الدخول"}
        m = DENIED.search(body)
        if m and len(body) < 2500:
            return {"kind": "denied", "ms": ms, "msg": f"النظام قال: {m.group(1)}"}
        m = ERR.search(body)
        if m:
            line = next((l.strip() for l in body.splitlines() if ERR.search(l)), m.group(1))
            return {"kind": "error", "ms": ms, "msg": line[:180]}
        return {"kind": "ok", "ms": ms, "msg": ""}

    def first_row(self, timeout=15):
        """the first document in the list (its edit / print links), waiting for the list to load"""
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                r = self.driver.execute_script(ROW_JS)
            except Exception:
                r = None
            if r:
                return r
            time.sleep(.6)
        return None

    def wait_report(self, timeout=60):
        """a DevExpress report page: when it waits for its filters, press «Submit» (its default dates) like a person,
        then wait until the pages are drawn or an error shows. ms = from the Submit (the report's own time)"""
        t0, pressed = time.time(), False
        while time.time() - t0 < timeout:
            try:
                v = self.driver.execute_script(VIEWER_JS)
            except Exception:
                v = ""
            if v == "params" and not pressed:
                try:
                    self.driver.execute_script("document.querySelector('.dxrdp-parameters-submit').click()")
                    pressed, t0 = True, time.time()
                except Exception:
                    pass
            elif v and v != "params":
                return v, int((time.time() - t0) * 1000)
            elif v == "params" and pressed and time.time() - t0 > 8:
                return "params", int((time.time() - t0) * 1000)       # still wants a filter (an account / a customer)
            time.sleep(1)
        return "timeout", int((time.time() - t0) * 1000)

    def shot(self, name):
        try:
            SHOTS.mkdir(parents=True, exist_ok=True)
            self.driver.save_screenshot(str(SHOTS / f"{name}.png"))
        except Exception:
            pass
