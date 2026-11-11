from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from pages.base_page import BasePage
from utils.logger import logger
from utils.select2_helper import Select2Helper
from config.settings import LOGIN_URL
import time


class LoginPage(BasePage):
    # ==================== Selectors ====================
    USERNAME_INPUT = (By.ID, "userName")
    PASSWORD_INPUT = (By.ID, "password")
    LOGIN_BUTTON = (By.CSS_SELECTOR, "button.btn-login")

    # Select2 dropdowns
    ACTIVITY_SELECT2_ID = "cmbact"       # النشاط الرئيسي
    BRANCH_SELECT2_ID = "cmbbranch"      # الفرع الرئيسي

    # ==================== Basic Actions ====================
    def load(self):
        """فتح صفحة تسجيل الدخول"""
        self.open(LOGIN_URL)

    def enter_username(self, username: str):
        self.type_text(self.USERNAME_INPUT, username, "اسم المستخدم")
        time.sleep(3)

    def enter_password(self, password: str):
        self.type_text(self.PASSWORD_INPUT, password, "كلمة المرور")
        time.sleep(0.5)

    def click_login(self):
        for _ in range(30):                      # the page disables the button while it loads activities / branches
            try:
                if not self.driver.execute_script("var b = document.querySelector('button[type=submit],input[type=submit]'); return !!(b && b.disabled);"):
                    break
            except Exception:
                break
            time.sleep(1)
        self.click(self.LOGIN_BUTTON, "زر تسجيل الدخول")

    # ==================== Select2 Dropdowns ====================
    @staticmethod
    def _norm(t):
        t = (t or "").strip().lower()
        for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ة", "ه"), ("ى", "ي")):
            t = t.replace(a, b)
        t = t.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
        return " ".join(t.split())

    def _select_first_option(self, select2_id: str, label: str, timeout: int = 15, want: str = "") -> bool:
        """
        اختيار أول عنصر حقيقي في Select2 dropdown
        
        Args:
            select2_id: ID الـ select2 (بدون select2- prefix)
            label: اسم الحقل للـ logging
            timeout: مدة الانتظار
            
        Returns:
            True لو نجح، False لو فشل
        """
        logger.info(f"محاولة اختيار أول عنصر في [{label}] (id={select2_id})")
        if not want and not self.driver.find_elements(By.CSS_SELECTOR, f"#{select2_id}, #select2-{select2_id}-container"):
            logger.info(f"⏭️ مفيش [{label}] في شاشة الدخول على الموقع ده — بكمل")      # e.g. aquapure: no 15 s wait for nothing
            return True
        
        self._wait_lookups(select2_id, timeout=max(timeout, 30))
        try:
            # ═══ 1) فتح الـ dropdown ═══
            # الـ container اللي بيتداس عليه
            container_selector = f"#select2-{select2_id}-container"
            
            try:
                container = WebDriverWait(self.driver, timeout).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, container_selector))
                )
            except TimeoutException:
                # no clickable Select2 box (slow site / another Select2 build / hidden): pick in the <select> itself —
                # NQ ERP's login also fills the user's own activity + branch by itself (GetLoginData), which counts as chosen
                logger.info(f"⚠️ [{label}]: مش لاقي صندوق Select2 يتداس — هختار من القايمة نفسها")
                return self._select_first_option_js(select2_id, label, want)
            
            # ندوس على الـ parent (span.select2-selection)
            try:
                parent = container.find_element(
                    By.XPATH, "./ancestor::span[contains(@class, 'select2-selection')]"
                )
                self.driver.execute_script("arguments[0].click();", parent)
            except Exception:
                # fallback: ندوس على الـ container نفسه
                self.driver.execute_script("arguments[0].click();", container)
            
            logger.info(f"✅ فتحت [{label}]")
            time.sleep(1.5)
            
            # ═══ 2) انتظر ظهور القائمة ═══
            try:
                WebDriverWait(self.driver, 5).until(
                    EC.visibility_of_element_located(
                        (By.CSS_SELECTOR, ".select2-container--open .select2-results")
                    )
                )
            except TimeoutException:
                logger.warning(f"⚠️ القائمة مش ظهرت لـ [{label}] — هختار بالـ JavaScript")
                try:
                    self.driver.find_element(By.TAG_NAME, "body").click()
                except Exception:
                    pass
                time.sleep(0.5)
                return self._select_first_option_js(select2_id, label, want)
            
            # ═══ 3) اختار أول عنصر حقيقي (مش placeholder) ═══
            options = self.driver.find_elements(           # this dropdown's own list (another one may still be open)
                By.CSS_SELECTOR, f"#select2-{select2_id}-results .select2-results__option"
            )
            if not options:                              # its list didn't open (another dropdown is open) -> pick in the <select>
                try:
                    self.driver.find_element(By.TAG_NAME, "body").click()
                except Exception:
                    pass
                return self._select_first_option_js(select2_id, label, want)
            
            if not options:
                logger.warning(f"⚠️ مفيش options في [{label}]")
                return False
            
            logger.info(f"عدد الـ options في [{label}]: {len(options)}")
            
            chosen = None
            for opt in options:
                # تجاهل الـ placeholder / "اختر"
                text = opt.text.strip()
                cls = opt.get_attribute("class") or ""
                
                # لو ده الـ placeholder
                if "select2-results__option--disabled" in cls:
                    continue
                if not text:
                    continue
                if any(p in text for p in ["اختر", "بحث", "----"]):
                    continue
                if want and self._norm(want) not in self._norm(text):
                    continue                     # the profile asks for another activity / branch
                
                # ده عنصر حقيقي
                chosen = opt
                logger.info(f"سأختار: '{text}'")
                break
            
            if not chosen and want:
                try:
                    self.driver.find_element(By.TAG_NAME, "body").click()
                except Exception:
                    pass
                if self._select_first_option_js(select2_id, label, want):      # «want» may be the option's value (e.g. «1»)
                    return True
                logger.error(f"❌ مالقيتش «{want}» في [{label}] — الموجود: {[o.text.strip() for o in options if o.text.strip()]}")
                return False
            if not chosen:
                logger.warning(f"⚠️ مفيش عنصر حقيقي في [{label}]")
                # جرب أول عنصر عادي
                for opt in options:
                    if opt.text.strip():
                        chosen = opt
                        break
            
            if not chosen:
                logger.warning(f"⚠️ مش لاقي أي عنصر أختاره في [{label}]")
                return False
            
            # ═══ 4) اضغط على العنصر ═══
            chosen_text = chosen.text.strip()
            self.driver.execute_script("arguments[0].click();", chosen)
            logger.success(f"✅ اخترت [{label}]: '{chosen_text}'")
            time.sleep(1)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ خطأ في اختيار [{label}]: {e}")
            try:
                self.driver.find_element(By.TAG_NAME, "body").click()
            except Exception:
                pass
            return False

    def _wait_lookups(self, select_id: str, timeout: int = 30):
        """slow sites: wait until the login page finished loading the user's activities / branches
        (the <select> has a real option and the sign-in button isn't «busy»)"""
        end = time.time() + timeout
        while time.time() < end:
            try:
                st = self.driver.execute_script(r"""
                    var s = document.getElementById(arguments[0]); if (!s) return 'none';
                    var real = Array.from(s.options).some(function (o) { return o.value && !/اختر|select|----/i.test(o.text); });
                    var btn = document.querySelector('button[type=submit],input[type=submit]');
                    return real && !(btn && btn.disabled) ? 'ready' : 'wait';""", select_id)
            except Exception:
                st = "wait"
            if st in ("ready", "none"):
                return st
            time.sleep(1)
        logger.info(f"⏳ [{select_id}] لسه بيحمّل بعد {timeout} ث — هكمل")
        return "timeout"

    def _select_first_option_js(self, select_id: str, label: str, want: str = "") -> bool:
        """Fallback: يختار أول عنصر حقيقي في الـ <select> نفسه ويبعت change (زي ما Select2 بيعمل)."""
        result = self.driver.execute_script(r"""
            var s = document.getElementById(arguments[0]), want = arguments[1] || '';
            var N = function (t) { return (t || '').trim().toLowerCase().replace(/[أإآ]/g, 'ا').replace(/ة/g, 'ه').replace(/ى/g, 'ي')
                .replace(/[٠-٩]/g, function (d) { return '٠١٢٣٤٥٦٧٨٩'.indexOf(d); }).replace(/\s+/g, ' '); };
            if (!s) return {ok: false, why: 'no-select'};
            var all = Array.from(s.options).map(function (o) { return o.text.trim(); });
            var cur = s.selectedIndex >= 0 && s.options[s.selectedIndex] ? s.options[s.selectedIndex] : null;
            var match = function (o) { return !want || N(o.text).indexOf(N(want)) >= 0 || String(o.value) === String(want).trim(); };   // «1» = the option's value or its text
            if (cur && cur.value && !/اختر|select|----/i.test(cur.text) && match(cur)) return {ok: true, text: cur.text.trim(), already: true, all: all};
            for (var i = 0; i < s.options.length; i++) {
                var o = s.options[i], t = o.text.trim();
                if (!o.value || !t || /اختر|select|بحث|----/i.test(t)) continue;
                if (!match(o)) continue;
                s.selectedIndex = i;
                if (window.jQuery) { jQuery(s).trigger('change'); } else { s.dispatchEvent(new Event('change', {bubbles: true})); }
                return {ok: true, text: t, all: all};
            }
            return {ok: false, why: 'no-real-option', all: all};
        """, select_id, want or "") or {}
        if result.get("ok"):
            how = "كان مختار بالفعل" if result.get("already") else "اتختار بالـ JavaScript"
            logger.success(f"✅ [{label}] = '{result.get('text')}' ({how}) — الخيارات: {result.get('all')}")
            time.sleep(1.5)
            return True
        logger.warning(f"⚠️ [{label}] مفيش عنصر يتختار ({result.get('why')}) — الخيارات: {result.get('all')}")
        return False

    def select_activity(self, timeout: int = 15) -> bool:
        """اختيار النشاط الرئيسي - أول عنصر حقيقي"""
        from config.settings import ACTIVITY
        return self._select_first_option(self.ACTIVITY_SELECT2_ID, "النشاط الرئيسي", timeout, want=ACTIVITY)

    def select_branch(self, timeout: int = 15) -> bool:
        """اختيار الفرع الرئيسي - أول عنصر حقيقي"""
        from config.settings import BRANCH
        return self._select_first_option(self.BRANCH_SELECT2_ID, "الفرع الرئيسي", timeout, want=BRANCH)

    # ==================== Login Flow ====================
    def login(self, username: str, password: str,
              select_activity: bool = True,
              select_branch: bool = True,
              wait_activity: int = 3,
              wait_branch: int = 3):
        """
        تسجيل الدخول الكامل مع اختيار النشاط والفرع
        
        Args:
            username: اسم المستخدم
            password: كلمة المرور
            select_activity: اختيار النشاط الرئيسي
            select_branch: اختيار الفرع الرئيسي
            wait_activity: وقت انتظار ظهور النشاط (ثواني)
            wait_branch: وقت انتظار ظهور الفرع (ثواني)
        """
        # ♻️ لو فيه جلسة دخول محفوظة وصالحة، نستخدمها ونوفّر وقت شاشة الدخول
        try:
            from engine import session_cache
            if session_cache.restore(self.driver):
                logger.success("♻️ استخدمت جلسة الدخول المحفوظة (من غير شاشة الدخول)")
                return True
        except Exception:
            pass

        logger.info("=" * 50)
        logger.info("بدء تسجيل الدخول")
        logger.info("=" * 50)

        # 1) ادخل اليوزر والباسورد
        self.enter_username(username)
        self.enter_password(password)

        # 2) اختار النشاط الرئيسي
        if select_activity:
            logger.info("─── اختيار النشاط الرئيسي ───")
            time.sleep(wait_activity)  # استنى الحقل يظهر بعد اليوزر
            activity_ok = self.select_activity()
            if not activity_ok:
                from config.settings import ACTIVITY
                if ACTIVITY:
                    self.take_screenshot("ERROR_activity_not_found")
                    raise AssertionError(f"شاشة الدخول: النشاط «{ACTIVITY}» المكتوب في إعدادات الموقع مش موجود للمستخدم ده")
                logger.warning("⚠️ فشل اختيار النشاط - بستمر")
        else:
            logger.info("⏭️ تخطي اختيار النشاط")

        # 3) اختار الفرع الرئيسي
        if select_branch:
            logger.info("─── اختيار الفرع الرئيسي ───")
            time.sleep(wait_branch)  # استنى الفرع يعتمد على النشاط
            branch_ok = self.select_branch()
            if not branch_ok:
                from config.settings import BRANCH
                if BRANCH:
                    self.take_screenshot("ERROR_branch_not_found")
                    raise AssertionError(f"شاشة الدخول: الفرع «{BRANCH}» المكتوب في إعدادات الموقع مش موجود في النشاط ده")
                logger.warning("⚠️ فشل اختيار الفرع - بستمر")
        else:
            logger.info("⏭️ تخطي اختيار الفرع")

        # 4) اضغط تسجيل الدخول
        logger.info("─── تسجيل الدخول ───")
        self.click_login()

        # 5) استنى التحويل
        logger.info("في انتظار التحويل...")
        try:
            WebDriverWait(self.driver, 45).until(
                lambda d: "/Login" not in d.current_url
            )
            logger.success(f"✅ تم الدخول! URL: {self.driver.current_url}")
            try:
                from engine import session_cache
                session_cache.save(self.driver)
            except Exception:
                pass
            time.sleep(2)
            self.take_screenshot("login_success")
            return True
        except TimeoutException:
            self.take_screenshot("ERROR_login_failed")
            logger.error(f"❌ فشل التحويل! URL: {self.driver.current_url}")
            raise

    def is_logged_in(self):
        return "/Login" not in self.driver.current_url