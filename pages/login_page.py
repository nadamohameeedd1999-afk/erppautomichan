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
        self.click(self.LOGIN_BUTTON, "زر تسجيل الدخول")

    # ==================== Select2 Dropdowns ====================
    def _select_first_option(self, select2_id: str, label: str, timeout: int = 15) -> bool:
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
        
        try:
            # ═══ 1) فتح الـ dropdown ═══
            # الـ container اللي بيتداس عليه
            container_selector = f"#select2-{select2_id}-container"
            
            try:
                container = WebDriverWait(self.driver, timeout).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, container_selector))
                )
            except TimeoutException:
                logger.warning(f"❌ مش لاقي [{label}] - الـ container مش موجود")
                return False
            
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
                logger.warning(f"⚠️ القائمة مش ظهرت لـ [{label}]")
                # جرب نغلقها
                self.driver.find_element(By.TAG_NAME, "body").click()
                time.sleep(0.5)
                return False
            
            # ═══ 3) اختار أول عنصر حقيقي (مش placeholder) ═══
            options = self.driver.find_elements(
                By.CSS_SELECTOR, ".select2-container--open .select2-results__option"
            )
            
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
                
                # ده عنصر حقيقي
                chosen = opt
                logger.info(f"سأختار: '{text}'")
                break
            
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

    def select_activity(self, timeout: int = 15) -> bool:
        """اختيار النشاط الرئيسي - أول عنصر حقيقي"""
        return self._select_first_option(self.ACTIVITY_SELECT2_ID, "النشاط الرئيسي", timeout)

    def select_branch(self, timeout: int = 15) -> bool:
        """اختيار الفرع الرئيسي - أول عنصر حقيقي"""
        return self._select_first_option(self.BRANCH_SELECT2_ID, "الفرع الرئيسي", timeout)

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
                logger.warning("⚠️ فشل اختيار النشاط - بستمر")
        else:
            logger.info("⏭️ تخطي اختيار النشاط")

        # 3) اختار الفرع الرئيسي
        if select_branch:
            logger.info("─── اختيار الفرع الرئيسي ───")
            time.sleep(wait_branch)  # استنى الفرع يعتمد على النشاط
            branch_ok = self.select_branch()
            if not branch_ok:
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
            time.sleep(2)
            self.take_screenshot("login_success")
            return True
        except TimeoutException:
            self.take_screenshot("ERROR_login_failed")
            logger.error(f"❌ فشل التحويل! URL: {self.driver.current_url}")
            raise

    def is_logged_in(self):
        return "/Login" not in self.driver.current_url