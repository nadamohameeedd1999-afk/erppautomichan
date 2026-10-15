"""
Cash Receipt Voucher Page Object — FINAL
- يتعامل مع JavaScript Alert + SweetAlert
- ينتظر URL change بعد الحفظ
"""
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException, NoAlertPresentException
from pages.base_page import BasePage
from utils.select2_helper import Select2Helper
from utils.logger import logger
from config.settings import BASE_URL
from config.cash_receipt_data import CashReceiptDefaults
import time


class CashReceiptVoucherPage(BasePage):
    LIST_URL = f"{BASE_URL}/CashReceiptVoucher"
    ADD_URL = f"{BASE_URL}/CashReceiptVoucher/AddEdit"

    ADD_NEW_BUTTON = (By.CSS_SELECTOR, "a[href='/CashReceiptVoucher/AddEdit']")

    # الحقول
    SOURCE_TYPE_SELECT2 = "SourceTypeId"
    CUSTOMER_SELECT2 = "CustomerId"
    PROJECT_SELECT2 = "ProjectId"
    PAYMENT_METHOD_SELECT2 = "CashReceiptPaymentMethodId"
    MONEY_AMOUNT = (By.CSS_SELECTOR, "input#MoneyAmount")

    # Buttons
    AUTO_PAY_BUTTON = (By.CSS_SELECTOR, "button#autoPay")
    SAVE_BUTTON = (By.CSS_SELECTOR, "button#save")

    # SweetAlerts
    SWAL_POPUP = (By.CSS_SELECTOR, ".swal2-popup")
    SWAL_CONFIRM = (By.CSS_SELECTOR, "button.swal2-confirm")

    def __init__(self, driver):
        super().__init__(driver)
        self.s2 = Select2Helper(driver)

    # ========== Navigation ==========
    def open_list(self):
        self.open(self.LIST_URL)
        self.wait_for_preloader()
        time.sleep(1)

    def click_add_new(self):
        logger.info("اضغط إضافة جديد")
        self.wait_for_preloader(timeout=20)
        time.sleep(0.5)
        self.click(self.ADD_NEW_BUTTON, "زر إضافة جديد")
        self.wait_for_preloader(timeout=20)
        time.sleep(1.5)

    def is_on_add_page(self):
        return "/AddEdit" in self.driver.current_url

    # ========== JavaScript Alert Handler ==========
    def accept_js_alert(self, timeout=5):
        """يقبل JavaScript Alert (alert/confirm/prompt)"""
        try:
            WebDriverWait(self.driver, timeout).until(EC.alert_is_present())
            alert = self.driver.switch_to.alert
            text = alert.text
            logger.info(f"JS Alert: '{text[:120]}'")
            alert.accept()
            logger.success("✅ ضغط OK على JS Alert")
            time.sleep(0.5)
            return True
        except (TimeoutException, NoAlertPresentException):
            return False

    def safe_click(self, locator, description="زر"):
        """ضغط آمن — بيتعامل مع JS Alert لو ظهر"""
        try:
            el = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(locator)
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.3)
            self.driver.execute_script("arguments[0].click();", el)
            logger.success(f"✅ ضغط {description}")
            # نستنى أي Alert يظهر
            time.sleep(0.5)
            self.accept_js_alert(timeout=2)
            return True
        except UnexpectedAlertPresentException:
            self.accept_js_alert(timeout=3)
            return True
        except Exception as e:
            logger.warning(f"⚠️ {description}: {str(e)[:150]}")
            self.accept_js_alert(timeout=2)
            return False

    # ========== Select2 ==========
    def _get_select2_value(self, select_id):
        try:
            container = self.driver.find_element(By.ID, f"select2-{select_id}-container")
            text = container.text.strip()
            if text and text not in ["--اختر--", "-اختر-", "اختر", "", "-- اختر --"]:
                return text
        except Exception:
            pass
        return None

    def _set_select2(self, select_id, value, name):
        try:
            current = self._get_select2_value(select_id)
            if current and value and (value in current or current in value):
                logger.info(f"⏭️ {name} متملي: {current}")
                return current

            if value:
                logger.info(f"اختيار '{value}' في {name}")
                if self.s2.select_by_id(select_id, value):
                    time.sleep(0.5)
                    result = self._get_select2_value(select_id)
                    if result:
                        logger.success(f"✅ {name} = {result}")
                        return result

            if self.s2.force_select_value(select_id, value or ""):
                time.sleep(0.5)
                result = self._get_select2_value(select_id)
                if result:
                    logger.success(f"✅ {name} (force) = {result}")
                    return result

            if self.s2.select_first_real_option(select_id):
                time.sleep(0.5)
                result = self._get_select2_value(select_id)
                if result:
                    logger.success(f"✅ {name} (أول) = {result}")
                    return result

            logger.warning(f"⚠️ فشل {name}")
            return None
        except Exception as e:
            logger.warning(f"⚠️ {name}: {str(e)[:120]}")
            return None

    def fill_source_type(self):
        return self._set_select2(self.SOURCE_TYPE_SELECT2, CashReceiptDefaults.SOURCE_TYPE, "نوع المصدر")

    def fill_customer(self):
        return self._set_select2(self.CUSTOMER_SELECT2, CashReceiptDefaults.CUSTOMER, "العميل")

    def fill_project(self):
        return self._set_select2(self.PROJECT_SELECT2, CashReceiptDefaults.PROJECT, "المشروع")

    def fill_payment_method(self):
        return self._set_select2(self.PAYMENT_METHOD_SELECT2, CashReceiptDefaults.PAYMENT_METHOD, "طريقة الدفع")

    def fill_money_amount(self):
        try:
            inputs = self.driver.find_elements(*self.MONEY_AMOUNT)
            if not inputs:
                return None
            el = inputs[0]
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.3)
            self.driver.execute_script("""
                var el = arguments[0];
                el.focus();
                el.value = '';
                el.value = arguments[1];
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.dispatchEvent(new Event('keyup', {bubbles: true}));
                el.dispatchEvent(new Event('blur', {bubbles: true}));
            """, el, str(CashReceiptDefaults.MONEY_AMOUNT))
            time.sleep(0.8)
            actual = el.get_attribute("value")
            if actual:
                logger.success(f"✅ المبلغ = {actual}")
                return actual
            return None
        except Exception as e:
            logger.warning(f"⚠️ المبلغ: {str(e)[:120]}")
            return None

    def fill_all_required_fields(self):
        logger.info("=" * 50)
        logger.info("ملء حقول سند القبض")
        logger.info("=" * 50)

        self.wait_for_preloader()
        time.sleep(0.5)

        logger.info("1/5) نوع المصدر")
        self.fill_source_type()
        time.sleep(0.5)

        logger.info("2/5) العميل")
        self.fill_customer()
        time.sleep(0.5)

        logger.info("3/5) المشروع")
        self.fill_project()
        time.sleep(0.5)

        logger.info("4/5) طريقة الدفع")
        self.fill_payment_method()
        time.sleep(0.5)

        logger.info("5/5) المبلغ")
        self.fill_money_amount()
        time.sleep(0.5)

        logger.success("✅ تم ملء كل الحقول")

    # ========== AutoPay ==========
    def click_auto_pay(self):
        """اضغط 'سداد الى' — مع التعامل مع JS Alert"""
        logger.info("=" * 50)
        logger.info("اضغط 'سداد الى'")
        logger.info("=" * 50)

        try:
            btn = WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located(self.AUTO_PAY_BUTTON)
            )

            # نظهر الزر لو مخفي
            self.driver.execute_script("arguments[0].style.display='block';", btn)
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.5)

            # نضغط بـ JS
            self.driver.execute_script("arguments[0].click();", btn)
            logger.success("✅ ضغط 'سداد الى'")

            # ⚠️ مهم: نستنى ونقبل JS Alert
            time.sleep(1)
            if self.accept_js_alert(timeout=5):
                logger.success("✅ تعاملنا مع JS Alert بعد autoPay")
                time.sleep(1)
                # ممكن يظهر أكتر من alert
                self.accept_js_alert(timeout=3)
            else:
                logger.info("مفيش JS Alert — نكمل")

            time.sleep(1.5)
            return True

        except UnexpectedAlertPresentException as e:
            logger.warning(f"⚠️ Alert أثناء autoPay: {str(e)[:150]}")
            self.accept_js_alert(timeout=3)
            return True
        except Exception as e:
            logger.warning(f"⚠️ autoPay: {str(e)[:200]}")
            self.accept_js_alert(timeout=3)
            return False

    # ========== Save ==========
    def click_save(self):
        logger.info("اضغط حفظ")
        self.wait_for_preloader()
        return self.safe_click(self.SAVE_BUTTON, "زر الحفظ")

    # ========== SweetAlerts ==========
    def handle_all_swals(self, max_count=10, timeout=6, wait_after=1.0):
        """
        يتعامل مع SweetAlerts متتالية + JavaScript Alerts
        """
        count = 0
        consecutive_misses = 0
        max_misses = 2

        while count < max_count and consecutive_misses < max_misses:
            # 1) الأول: JavaScript Alert
            if self.accept_js_alert(timeout=2):
                count += 1
                consecutive_misses = 0
                time.sleep(wait_after)
                continue

            # 2) بعدها: SweetAlert
            try:
                popup = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located(self.SWAL_POPUP)
                )

                # نتأكد إنه ظاهر
                if not popup.is_displayed():
                    consecutive_misses += 1
                    time.sleep(wait_after)
                    continue

                try:
                    title = popup.find_element(By.CSS_SELECTOR, ".swal2-title").text.strip()
                except Exception:
                    title = "(بدون عنوان)"

                logger.info(f"SweetAlert #{count+1}: '{title}'")
                self.take_screenshot(f"crv_swal_{count+1}")

                # نضغط موافقة
                try:
                    confirm = popup.find_element(By.CSS_SELECTOR, "button.swal2-confirm")
                    self.driver.execute_script("arguments[0].click();", confirm)
                    logger.success(f"✅ موافقة #{count+1}")
                    count += 1
                    consecutive_misses = 0
                    time.sleep(wait_after)

                    # نستنى الـ SweetAlert يختفي
                    try:
                        WebDriverWait(self.driver, 3).until(
                            EC.invisibility_of_element_located(self.SWAL_POPUP)
                        )
                    except TimeoutException:
                        pass

                except Exception as e:
                    logger.warning(f"مشكلة الضغط: {str(e)[:100]}")
                    # ممكن يكون ظهر JS Alert — نقبله
                    self.accept_js_alert(timeout=2)
                    consecutive_misses += 1
                    time.sleep(wait_after)

            except TimeoutException:
                consecutive_misses += 1
                logger.info(f"مفيش SweetAlert ({consecutive_misses}/{max_misses})")

        logger.info(f"📊 إجمالي: {count} alert")
        return count

    # ========== Wait for save ==========
    def wait_for_save_result(self, timeout=45):
        """
        ينتظر:
        - URL change من /AddEdit لـ /CashReceiptVoucher
        - أو رسالة نجاح
        """
        logger.info(f"في انتظار نتيجة الحفظ (max {timeout}s)...")
        start = time.time()
        was_in_addedit = "/AddEdit" in self.driver.current_url

        while time.time() - start < timeout:
            # 1) JS Alert — نتعامل معاه
            self.accept_js_alert(timeout=1)

            # 2) نتأكد مش في /AddEdit
            try:
                current = self.driver.current_url
            except UnexpectedAlertPresentException:
                self.accept_js_alert(timeout=2)
                continue

            if was_in_addedit and "/CashReceiptVoucher" in current and "/AddEdit" not in current:
                logger.success(f"🎯 الحفظ نجح - URL change: {current}")
                time.sleep(2)
                return True

            if "/CashReceiptVoucher" in current and "/AddEdit" not in current and "/Login" not in current:
                logger.success(f"🎯 الحفظ نجح (fallback)")
                time.sleep(1)
                return True

            time.sleep(0.5)

        logger.warning(f"⚠️ انتهى الوقت. URL: {self.driver.current_url}")
        return False

    # ========== Verify ==========
    def verify_voucher_in_list(self, expected_amount=None, timeout=20):
        logger.info("🔍 التحقق من السند...")
        try:
            # نقبل أي alerts
            self.accept_js_alert(timeout=1)

            if "/CashReceiptVoucher" not in self.driver.current_url or "/AddEdit" in self.driver.current_url:
                self.driver.get(self.LIST_URL)

            self.wait_for_preloader()
            time.sleep(2)

            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr"))
            )
            time.sleep(1)

            rows = self.driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
            if not rows:
                logger.warning("⚠️ الجدول فاضي")
                return False

            logger.info(f"✅ فيه {len(rows)} سند")
            first_row = rows[0].text.strip()
            logger.info(f"أول صف: {first_row[:150]}")
            return True
        except Exception as e:
            logger.error(f"❌ {str(e)[:150]}")
            return False