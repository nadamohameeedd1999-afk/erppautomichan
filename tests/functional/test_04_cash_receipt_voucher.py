"""
اختبار سند القبض
"""
import re
import time
import allure
import pytest
from pages.login_page import LoginPage
from pages.cash_receipt_voucher_page import CashReceiptVoucherPage
from utils.logger import logger
from utils.list_verify import first_row_text, wait_for_new_first_row
from config.cash_receipt_data import CashReceiptDefaults


def _shot(page, name):
    """Take a screenshot and attach it to the Allure report."""
    path = page.take_screenshot(name)
    if path:
        allure.attach.file(path, name=name, attachment_type=allure.attachment_type.PNG)


@allure.feature("Cash Receipt Voucher")
@allure.story("Create Cash Receipt Voucher")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.smoke
def test_full_cash_receipt_voucher_flow(driver, credentials, request):
    """إنشاء سند قبض والتأكد إن سند جديد ظهر في القائمة"""
    start = time.time()
    logger.info(f"▶ {request.node.name}")
    crv = CashReceiptVoucherPage(driver)

    with allure.step("تسجيل الدخول"):
        login = LoginPage(driver)
        login.load()
        login.login(credentials["username"], credentials["password"])

    with allure.step("قراءة أول صف في قائمة السندات قبل الإضافة"):
        crv.open_list()
        before = first_row_text(driver)
        allure.attach(str(before), name="first_row_before")
        logger.info(f"أول صف قبل الإضافة: {str(before)[:120]}")

    with allure.step("فتح صفحة إضافة سند"):
        crv.click_add_new()
        assert crv.is_on_add_page(), f"مش في صفحة الإضافة: {driver.current_url}"

    with allure.step("ملء الحقول الإجبارية"):
        crv.fill_all_required_fields()
        for sid, label in (("SourceTypeId", "نوع المصدر"), ("CustomerId", "العميل"), ("CashReceiptPaymentMethodId", "طريقة الدفع")):
            txt = crv.s2.get_selected_text(sid)
            assert txt and not crv.s2._is_placeholder(txt), (
                f"الحقل [{label}] مش اتملى فعلاً (القيمة: {txt!r}). لو الموقع ظهر بالإنجليزي راجع لغة الموقع"
            )
        _shot(crv, "crv_before_save")

    with allure.step("سداد الى (autoPay)"):
        crv.click_auto_pay()

    with allure.step("حفظ السند"):
        crv.click_save()
        swal_count = crv.handle_all_swals(max_count=5, timeout=5)
        logger.info(f"عدد SweetAlerts: {swal_count}")
        saved = crv.wait_for_save_result(timeout=30)
        _shot(crv, "crv_after_save")
        assert saved, f"السند مش اتحفظ! URL: {driver.current_url}"

    with allure.step("التأكد إن سند جديد ظهر في القائمة"):
        after = wait_for_new_first_row(driver, crv.LIST_URL, before, timeout=60)
        _shot(crv, "crv_list_after_save")
        allure.attach(str(after), name="first_row_after")
        assert after is not None, (
            f"مظهرش سند جديد في القائمة بعد الحفظ. أول صف كان: {str(before)[:120]}"
        )

    with allure.step("فحص المبلغ في الصف الجديد (تسجيل فقط)"):
        amounts = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.\d{2}", after)]
        expected = float(CashReceiptDefaults.MONEY_AMOUNT)
        allure.attach(str(amounts), name="amounts_in_new_row")
        if expected not in amounts:
            logger.warning(f"المبلغ المتوقع {expected} مش ظاهر في الصف الجديد. المبالغ: {amounts}")

    logger.success(f"السند اتحفظ وظهر في القائمة ({int(time.time() - start)} ثانية)")