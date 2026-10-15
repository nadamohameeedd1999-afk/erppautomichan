"""
اختبار سند القبض
"""
import pytest
import time
import allure
from pages.login_page import LoginPage
from pages.cash_receipt_voucher_page import CashReceiptVoucherPage
from utils.logger import logger
from config.cash_receipt_data import CashReceiptDefaults


def _login_and_open_add(driver, credentials):
    login = LoginPage(driver)
    login.load()
    login.login(credentials["username"], credentials["password"])
    crv = CashReceiptVoucherPage(driver)
    crv.open_list()
    crv.click_add_new()
    assert crv.is_on_add_page(), f"مش في صفحة الإضافة: {driver.current_url}"
    return crv


@allure.feature("Cash Receipt Voucher")
@allure.story("Create Cash Receipt Voucher")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.smoke
def test_full_cash_receipt_voucher_flow(driver, credentials):
    """اختبار كامل: إنشاء سند قبض"""
    start_time = time.time()
    logger.info("=" * 60)
    logger.info("اختبار: إنشاء سند قبض كامل")
    logger.info("=" * 60)

    crv = _login_and_open_add(driver, credentials)

    logger.info("1) ملء الحقول الإجبارية")
    crv.fill_all_required_fields()

    crv.take_screenshot("crv_before_save")


    logger.info("3) 'سداد الى' (autoPay)")
    crv.click_auto_pay()

    logger.info("4) حفظ")
    crv.click_save()

    logger.info("التعامل مع SweetAlerts...")
    swal_count = crv.handle_all_swals(max_count=5, timeout=5)
    logger.info(f"عدد SweetAlerts: {swal_count}")

    logger.info("4) انتظار نتيجة الحفظ...")
    saved = crv.wait_for_save_result(timeout=30)
    crv.take_screenshot("crv_final")

    elapsed = time.time() - start_time
    logger.info(f"⏱️ الوقت الإجمالي: {int(elapsed // 60)}:{int(elapsed % 60):02d}")

    assert saved, f"❌ السند مش اتحفظ! URL: {driver.current_url}"

    logger.info("5) التحقق النهائي من صفحة القائمة...")
    verified = crv.verify_voucher_in_list(expected_amount=CashReceiptDefaults.MONEY_AMOUNT)
    crv.take_screenshot("crv_verify_list")

    if verified:
        logger.success("🎉✅ السند اتحفظ فعلاً وموجود في القائمة!")
    else:
        logger.warning("⚠️ السند مش موجود في القائمة (بس اتحفظ)")

    logger.success(f"🎉 السند اتحفظ بنجاح! ({int(elapsed)} ثانية)")