"""
Selenium Opener — مع Session Persistence
- أول مرة: يسجّل دخول ويحفظ الـ Profile
- بعد كده: يفتح Chrome بنفس الـ Profile (بدون Login)
"""
import sys
import time
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# مسار الـ Chrome Profile
from config import paths  # noqa: E402
PROFILE_DIR = paths.CHROME_PROFILE_DIR
PROFILE_DIR.mkdir(parents=True, exist_ok=True)


def _is_logged_in(driver):
    """يتأكد إن المستخدم مسجل دخول (مش في /Login)"""
    try:
        current = driver.current_url
        return "/Login" not in current and "/login" not in current
    except Exception:
        return False


def _try_open_with_profile(url_path, wait_seconds, driver):
    """يحاول يفتح الشاشة باستخدام الـ profile الحالي"""
    from config.settings import BASE_URL
    full_url = f"{BASE_URL}{url_path}" if not url_path.startswith("http") else url_path

    driver.get(full_url)
    time.sleep(2)

    # لو اتحول لـ Login → الـ session انتهت
    if "/Login" in driver.current_url:
        return False

    # تمام، استنى الباقي
    time.sleep(wait_seconds)
    return True


def open_page_simple(url_path, wait_seconds=5, force_login=False):
    """
    يفتح شاشة في المتصفح:
    - يحمّل Chrome Profile المحفوظ
    - لو مسجّل دخول → يفتح الشاشة على طول
    - لو مش مسجّل → يعمل Login، يحفظ، وبعدين يفتح الشاشة
    """
    result = {
        "success": False,
        "url": "",
        "login_ok": False,
        "login_skipped": False,
        "waited_seconds": 0,
        "error": "",
        "screenshot": "",
        "current_url": "",
        "profile_used": str(PROFILE_DIR),
    }

    driver = None
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from config.settings import BASE_URL, USERNAME, PASSWORD

        # ===== Chrome Options مع Profile =====
        options = Options()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--lang=ar-EG")
        options.add_argument(f"--user-data-dir={PROFILE_DIR}")
        options.add_argument("--profile-directory=Default")

        # ===== ChromeDriver محلي =====
        driver_path = BASE_DIR / "drivers" / "chromedriver.exe"
        if driver_path.exists():
            service = Service(str(driver_path))
            driver = webdriver.Chrome(service=service, options=options)
        else:
            driver = webdriver.Chrome(options=options)

        driver.set_page_load_timeout(60)

        # ===== 1) نجرّب نفتح الشاشة على طول =====
        if not force_login:
            try:
                full_url = f"{BASE_URL}{url_path}" if not url_path.startswith("http") else url_path
                result["url"] = full_url
                driver.get(full_url)
                time.sleep(3)

                if "/Login" not in driver.current_url and "/login" not in driver.current_url:
                    # ✅ مسجّل دخول بالفعل — تخطينا Login!
                    result["login_ok"] = True
                    result["login_skipped"] = True
                    result["waited_seconds"] = wait_seconds
                    result["current_url"] = driver.current_url

                    time.sleep(wait_seconds)

                    # صورة
                    _save_screenshot(driver, result)
                    result["success"] = True
                    return result
            except Exception as e:
                print(f"[Profile check warning] {e}")

        # ===== 2) محتاجين نسجّل دخول =====
        try:
            from pages.login_page import LoginPage
            login_page = LoginPage(driver)
            login_page.load()
            login_page.login(USERNAME, PASSWORD)
            time.sleep(3)

            if "/Login" in driver.current_url:
                result["error"] = f"Login failed — still on: {driver.current_url}"
                return result

            result["login_ok"] = True

        except Exception as e:
            result["error"] = f"Login: {str(e)[:200]}"
            return result

        # ===== 3) فتح الشاشة =====
        full_url = f"{BASE_URL}{url_path}" if not url_path.startswith("http") else url_path
        result["url"] = full_url
        driver.get(full_url)

        # ===== 4) استنى =====
        time.sleep(wait_seconds)
        result["waited_seconds"] = wait_seconds
        result["current_url"] = driver.current_url

        # ===== 5) صورة =====
        _save_screenshot(driver, result)

        result["success"] = True

    except Exception as e:
        result["error"] = str(e)[:200]

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    return result


def _save_screenshot(driver, result):
    """يحفظ صورة"""
    try:
        from datetime import datetime
        screenshots_dir = paths.SCREENSHOTS_DIR
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        filename = f"opened_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        driver.save_screenshot(str(screenshots_dir / filename))
        result["screenshot"] = filename
    except Exception:
        pass


def clear_profile():
    """يمسح الـ Chrome Profile (لتسجيل دخول جديد)"""
    import shutil
    try:
        if PROFILE_DIR.exists():
            shutil.rmtree(PROFILE_DIR, ignore_errors=True)
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except Exception as e:
        print(f"[clear_profile] {e}")
        return False


def get_profile_status():
    """حالة الـ Profile"""
    exists = PROFILE_DIR.exists()
    files = []
    if exists:
        try:
            files = [f.name for f in PROFILE_DIR.iterdir()][:10]
        except Exception:
            pass
    return {
        "path": str(PROFILE_DIR),
        "exists": exists,
        "files_count": len(list(PROFILE_DIR.iterdir())) if exists else 0,
        "sample_files": files,
    }


def get_opener():
    """للتوافق"""
    return None