from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from config.settings import DEFAULT_TIMEOUT, SCREENSHOTS_DIR
from utils.logger import logger
from datetime import datetime
import time


class BasePage:
    PRELOADER = (By.ID, "preloader")

    def __init__(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, DEFAULT_TIMEOUT)

    def wait_for_preloader(self, timeout=20):
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.invisibility_of_element_located(self.PRELOADER)
            )
        except TimeoutException:
            pass
        except Exception:
            pass
        time.sleep(0.3)

    def open(self, url: str):
        logger.info(f"Open: {url}")
        self.driver.get(url)
        self.wait_for_preloader()

    def click(self, locator, description="", retry=True):
        logger.debug(f"Click: {description or locator}")
        self.wait_for_preloader()
        try:
            el = self.wait.until(EC.element_to_be_clickable(locator))
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(0.3)
            el.click()
            return el
        except WebDriverException as e:
            if retry:
                logger.warning(f"محاولة تانية: {str(e)[:100]}")
                self.wait_for_preloader()
                time.sleep(0.5)
                el = self.driver.find_element(*locator)
                self.driver.execute_script("arguments[0].click();", el)
                return el
            raise

    def type_text(self, locator, text, description=""):
        logger.debug(f"Type '{text}' in: {description or locator}")
        self.wait_for_preloader()
        el = self.wait.until(EC.visibility_of_element_located(locator))
        el.clear()
        el.send_keys(text)
        return el

    def is_visible(self, locator, timeout=10):
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.visibility_of_element_located(locator)
            )
            return True
        except TimeoutException:
            return False

    def take_screenshot(self, name="screenshot"):
        try:
            self.driver.set_page_load_timeout(120)
            self.driver.set_script_timeout(120)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = SCREENSHOTS_DIR / f"{name}_{timestamp}.png"
            from utils.mask import shot              # 🙈 a client's data is blurred in the picture
            shot(self.driver, lambda: self.driver.save_screenshot(str(filepath)))
            logger.info(f"Screenshot: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.warning(f"⚠️ فشل Screenshot: {str(e)[:100]}")
            return None
