"""
Helpers to prove a record was really created:
compare the first row of a list page before and after saving.
"""
import time
from selenium.webdriver.common.by import By
from utils.logger import logger

ROWS = (By.CSS_SELECTOR, "table tbody tr")


def first_row_text(driver, timeout=15, settle=1.0):
    """Text of the first table row, once it stops changing (or None)."""
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            rows = driver.find_elements(*ROWS)
            cur = rows[0].text.strip() if rows else None
        except Exception:
            cur = None
        if cur and cur == last:
            return cur
        last = cur
        time.sleep(settle)
    return last


def wait_for_new_first_row(driver, list_url, previous_text, timeout=60, poll=2):
    """Reload the list until its first row differs from previous_text."""
    end = time.time() + timeout
    attempt = 0
    while time.time() < end:
        attempt += 1
        try:
            driver.get(list_url)
            current = first_row_text(driver, timeout=10)
            if current and current != previous_text:
                logger.info(f"محاولة #{attempt}: ظهر صف جديد: {current[:120]}")
                return current
            logger.info(f"محاولة #{attempt}: لسه مفيش صف جديد")
        except Exception as e:
            logger.warning(f"محاولة #{attempt} فشلت: {str(e)[:100]}")
        time.sleep(poll)
    return None