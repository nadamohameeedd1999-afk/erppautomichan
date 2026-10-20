"""
Select2 Helper
"""
import re
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from utils.logger import logger


class Select2Helper:
    # أي نص بعد حذف المسافات والشرطات وتحويله لحروف صغيرة يطابق واحد من الكلمات دي = placeholder.
    # بيغطي عربي وإنجليزي: --اختر-- / -- Select -- / --Select-- / Please select ...
    PLACEHOLDER_WORDS = ("", "اختر", "select", "choose", "pleaseselect", "selectone")

    def __init__(self, driver, timeout=10):
        self.driver = driver
        self.wait = WebDriverWait(driver, timeout)

    @staticmethod
    def _norm(text) -> str:
        return re.sub(r"[\s\-_.]+", "", text or "").lower()

    def _is_placeholder(self, text: str) -> bool:
        return self._norm(text) in self.PLACEHOLDER_WORDS

    def _close_dropdown_fast(self):
        try:
            self.driver.execute_script("""
                if (window.jQuery) {
                    jQuery('.select2-container--open').find('.select2-selection').trigger('blur');
                    jQuery(document.activeElement).blur();
                }
                document.body.click();
            """)
            time.sleep(0.2)
        except Exception:
            pass

    def select_by_id(self, select_id: str, search_text: str) -> bool:
        logger.info(f"Select2 [{select_id}] -> {search_text}")
        self._close_dropdown_fast()
        try:
            container = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.ID, f"select2-{select_id}-container"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", container)
            container.click()
            time.sleep(0.4)

            try:
                search_field = WebDriverWait(self.driver, 3).until(
                    EC.visibility_of_element_located(
                        (By.CSS_SELECTOR,
                         "span.select2-container--open input.select2-search__field")
                    )
                )
                self.driver.execute_script("""
                    var el = arguments[0];
                    el.focus();
                    el.value = arguments[1];
                    if (window.jQuery) {
                        jQuery(el).trigger('input');
                    } else {
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                    }
                """, search_field, search_text)
                time.sleep(0.8)
            except TimeoutException:
                pass

            option_xpath = (
                f"//li[contains(@class,'select2-results__option') "
                f"and contains(normalize-space(.), '{search_text}')]"
            )
            option = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, option_xpath))
            )
            option.click()
            time.sleep(0.3)
            self._close_dropdown_fast()
            logger.success(f"✅ Selected: {search_text}")
            return True
        except TimeoutException:
            logger.warning(f"❌ مش لاقي [{search_text}] في {select_id}")
            self._close_dropdown_fast()
            return False

    def select_first_real_option(self, select_id: str) -> str:
        logger.info(f"Select2 [{select_id}] -> أول عنصر حقيقي")
        self._close_dropdown_fast()
        try:
            container = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.ID, f"select2-{select_id}-container"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", container)
            container.click()
            time.sleep(0.5)

            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR,
                     "span.select2-container--open li.select2-results__option")
                )
            )
            options = self.driver.find_elements(
                By.CSS_SELECTOR,
                "span.select2-container--open li.select2-results__option"
            )
            for opt in options:
                text = opt.text.strip()
                if self._is_placeholder(text):
                    continue
                if opt.is_displayed() and opt.is_enabled():
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", opt)
                    opt.click()
                    time.sleep(0.3)
                    self._close_dropdown_fast()
                    logger.success(f"✅ Selected: {text}")
                    return text
            self._close_dropdown_fast()
            return None
        except TimeoutException:
            return None

    def force_select_value(self, select_id: str, value: str = "") -> bool:
        logger.info(f"force_select [{select_id}] = '{value}'")
        try:
            result = self.driver.execute_script(f"""
                var sel = document.getElementById('{select_id}');
                if (!sel) return 'no-select';
                var searchValue = '{value}';
                var norm = function(t) {{ return (t || '').replace(/[\\s\\-_.]+/g, '').toLowerCase(); }};
                var words = ['', 'اختر', 'select', 'choose', 'pleaseselect', 'selectone'];
                var isPh = function(t) {{ return words.indexOf(norm(t)) !== -1; }};
                var selectedIndex = -1;
                var selectedText = '';

                if (searchValue && searchValue.length > 0) {{
                    for (var i = 0; i < sel.options.length; i++) {{
                        var optText = sel.options[i].text.trim();
                        if (optText.indexOf(searchValue) !== -1 && !isPh(optText)) {{
                            selectedIndex = i;
                            selectedText = optText;
                            break;
                        }}
                    }}
                }}

                if (selectedIndex === -1) {{
                    for (var j = 0; j < sel.options.length; j++) {{
                        var optText2 = sel.options[j].text.trim();
                        if (!optText2 || optText2.length < 3 || isPh(optText2)) {{
                            continue;
                        }}
                        selectedIndex = j;
                        selectedText = optText2;
                        break;
                    }}
                }}

                if (selectedIndex === -1) return 'no-real-option';

                sel.selectedIndex = selectedIndex;
                if (window.jQuery) {{
                    jQuery(sel).trigger('change').trigger('select2:select');
                }} else {{
                    sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                }}
                return 'ok:' + selectedText;
            """)
            if result and result.startswith('ok'):
                selected = result.replace('ok:', '').strip()
                if self._is_placeholder(selected):
                    logger.warning(f"⚠️ اختار placeholder")
                    return False
                logger.success(f"✅ force_select: {selected}")
                time.sleep(0.4)
                return True
            logger.warning(f"❌ فشل: {result}")
            return False
        except Exception as e:
            logger.error(f"خطأ: {e}")
            return False

    def get_selected_text(self, select_id: str) -> str:
        try:
            el = self.driver.find_element(By.ID, f"select2-{select_id}-container")
            return el.text.strip()
        except Exception:
            return ""