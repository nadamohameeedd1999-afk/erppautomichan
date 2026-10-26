"""
«فتح الشاشة» — one smoke test for every known screen (registry + discovered):
opens the list page, waits, checks there is a table and no server error, and that the add page opens.
"""
import allure
import pytest

from config.screens_catalog import all_pages
from engine.screen_runner import login
from pages.general_list_page import GeneralListPage

PAGES = all_pages()


@allure.feature("Smoke")
@pytest.mark.smoke
@pytest.mark.parametrize("page_key", list(PAGES.keys()))
def test_screen_opens(driver, credentials, page_key):
    info = PAGES[page_key]
    allure.dynamic.title(f"فتح الشاشة: {info['name_ar']}")
    login(driver, credentials)
    page = GeneralListPage(driver, info["url"])
    r = page.run_smoke_test(page_key, info)
    assert r["loaded"], f"❌ {info['name_ar']}: الصفحة ما اتحملتش ({info['url']})"
    assert not r["has_errors"], f"❌ {info['name_ar']}: فيه رسالة خطأ في الصفحة"
    assert r["has_table"], f"❌ {info['name_ar']}: مفيش جدول في الشاشة"
