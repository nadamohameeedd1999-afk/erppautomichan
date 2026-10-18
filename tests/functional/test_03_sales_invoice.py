import re
import time
import allure
import pytest
from selenium.webdriver.common.by import By
from pages.login_page import LoginPage
from pages.sales_invoice_page import (
    SalesInvoicePage,
    get_latest_invoice_number,
    wait_for_new_invoice,
)
from utils.logger import logger
from config.invoice_data import InvoiceDefaults

PRICE = "10000"
VAT_RATE = 0.15  # ضريبة القيمة المضافة
EXPECTED_TOTAL = round(float(PRICE) * (1 + VAT_RATE), 2)  # 11500.0
ESSENTIAL_FIELDS = [
    "comm_reg", "vat", "postal", "building",
    "payment", "project", "cost_center",
]


def _shot(page, name):
    """Take a screenshot and attach it to the Allure report."""
    path = page.take_screenshot(name)
    if path:
        allure.attach.file(path, name=name, attachment_type=allure.attachment_type.PNG)


def _amounts_in_first_row(driver):
    """المبالغ العشرية (مثل 11500.00) في أول صف من القائمة - من غير رقم الفاتورة."""
    rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
    if not rows:
        return []
    found = re.findall(r"\d[\d,]*\.\d{2}", rows[0].text)
    return [float(x.replace(",", "")) for x in found]


@allure.feature("Sales Invoice")
@allure.story("Create Full Invoice")
@allure.severity(allure.severity_level.CRITICAL)
@pytest.mark.smoke
def test_full_sales_invoice_flow(driver, credentials):
    """اختبار كامل: إنشاء فاتورة بيع والتأكد من ظهورها برقم جديد وإجمالي صحيح"""
    start = time.time()
    invoice = SalesInvoicePage(driver)

    with allure.step("تسجيل الدخول"):
        login = LoginPage(driver)
        login.load()
        login.login(credentials["username"], credentials["password"])

    with allure.step("قراءة أحدث رقم فاتورة قبل الإضافة"):
        invoice.open_list()
        previous = get_latest_invoice_number(driver)
        if previous is None:
            logger.warning("مقدرتش أقرأ آخر رقم فاتورة (القائمة فاضية؟) - هعتبره 0")
        previous = previous or 0
        allure.attach(str(previous), name="previous_invoice_number")

    with allure.step("فتح صفحة إضافة فاتورة"):
        invoice.click_add_new()
        assert invoice.is_on_add_page(), f"مش في صفحة الإضافة: {driver.current_url}"

    with allure.step("اختيار العميل"):
        invoice.select_customer()

    with allure.step("إضافة صنف"):
        invoice.click_plus_button()
        invoice.wait_for_item_modal(timeout=20)
        invoice.click_search_btn_in_modal()
        invoice.wait_for_items_results(timeout=20)
        invoice.click_add_item_by_name()

    with allure.step(f"كتابة السعر {PRICE}"):
        invoice.set_price_for_last_item(PRICE)

    with allure.step("ملء الحقول الإجبارية"):
        invoice.fill_required_text_fields()
        invoice.fill_required_select2_fields()
        if InvoiceDefaults.UNCHECK_AUTO_VOUCHER:
            invoice.uncheck_auto_voucher()

    with allure.step("التحقق من الحقول قبل الحفظ"):
        _shot(invoice, "inv_before_save")
        status = invoice.get_all_required_status()
        logger.info(f"حالة الحقول: {status}")
        missing = [k for k in ESSENTIAL_FIELDS if status.get(k) in ["(فاضي)", "(مش موجود)"]]
        assert not missing, f"حقول ناقصة: {missing}"

    with allure.step("حفظ الفاتورة"):
        invoice.click_save()
        swal_count = invoice.handle_all_swals(max_count=3, timeout=5)
        logger.info(f"عدد SweetAlerts: {swal_count}")
        saved = invoice.wait_for_save_result(timeout=45)
        _shot(invoice, "inv_after_save")
        assert saved, f"الفاتورة مش اتحفظت! URL: {driver.current_url}"

    with allure.step("التأكد إن فاتورة جديدة ظهرت في القائمة"):
        new_number = wait_for_new_invoice(driver, previous, timeout=60)
        _shot(invoice, "inv_list_after_save")
        assert new_number is not None, (
            f"مظهرتش فاتورة جديدة بعد الحفظ (آخر رقم قبل الحفظ كان {previous})"
        )
        assert new_number > previous
        allure.attach(str(new_number), name="new_invoice_number")

    with allure.step(f"التحقق من إجمالي الفاتورة = {EXPECTED_TOTAL}"):
        amounts = _amounts_in_first_row(driver)
        allure.attach(str(amounts), name="amounts_in_first_row")
        assert EXPECTED_TOTAL in amounts, (
            f"إجمالي الفاتورة {EXPECTED_TOTAL} مش موجود في أول صف. المبالغ الموجودة: {amounts}"
        )

    logger.success(f"الفاتورة رقم {new_number} اتحفظت ({int(time.time() - start)} ثانية)")