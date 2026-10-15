"""
Pytest Fixtures — Final version
Auto-detect Docker vs Local
Uses system chromedriver (no webdriver-manager download)
"""
import pytest
import os
import sys
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# ===== Encoding =====
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

# ===== منع webdriver-manager من التحميل =====
# نستخدم المسار اللي إحنا ثبّتناه في Dockerfile
os.environ["WDM_LOCAL"] = "1"
os.environ["WDM_LOG"] = "0"

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import USERNAME, PASSWORD
from utils.logger import logger


SELENIUM_HUB = os.getenv("SELENIUM_HUB", "http://localhost:4444")
USE_GRID = os.getenv("USE_SELENIUM_GRID", "false").lower() == "true"

# ===== اكتشاف البيئة =====
IS_DOCKER = os.path.exists("/.dockerenv") or os.getenv("RAILWAY_ENVIRONMENT") is not None
IS_LINUX = sys.platform.startswith("linux")


def _build_options():
    """Build Chrome options for current environment"""
    options = Options()

    if IS_DOCKER or IS_LINUX:
        logger.info("🐳 Docker/Linux mode: headless Chrome")
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-features=NetworkService")
        # ⚠️ مش بنستخدم --single-process ولا --no-zygote
        # لأنهم بيكسروا Chrome 155

        chrome_bin = os.getenv("CHROME_BIN", "/usr/bin/google-chrome")
        if os.path.exists(chrome_bin):
            options.binary_location = chrome_bin
            logger.info(f"Chrome binary: {chrome_bin}")
    else:
        logger.info("💻 Local mode: visible Chrome")
        options.add_argument("--start-maximized")
        options.add_argument("--window-size=1920,1080")

    # ===== مشترك =====
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--lang=ar-EG")
    options.add_argument("--incognito")

    return options


def _get_chromedriver_service():
    """Get chromedriver service — use system driver if available"""
    if IS_DOCKER or IS_LINUX:
        # في Docker: chromedriver مثبّت في /usr/local/bin من Dockerfile
        path = os.getenv("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
        if os.path.exists(path):
            logger.info(f"✅ Using system chromedriver: {path}")
            return Service(path)
        else:
            logger.warning(f"⚠️ chromedriver not found at {path}")
            # Fallback: webdriver-manager
            from webdriver_manager.chrome import ChromeDriverManager
            logger.info("Falling back to webdriver-manager")
            return Service(ChromeDriverManager().install())
    else:
        # على Windows: chromedriver.exe محلي
        DRIVER_PATH = BASE_DIR / "drivers" / "chromedriver.exe"
        if DRIVER_PATH.exists():
            logger.info(f"✅ Using local chromedriver: {DRIVER_PATH}")
            return Service(str(DRIVER_PATH))
        else:
            from webdriver_manager.chrome import ChromeDriverManager
            return Service(ChromeDriverManager().install())


def _create_driver(options):
    """Create Chrome driver"""
    service = _get_chromedriver_service()
    return webdriver.Chrome(service=service, options=options)


@pytest.fixture(scope="function")
def driver():
    """Create WebDriver"""
    logger.info("=" * 50)
    logger.info(f"Starting Chrome ({'Docker' if IS_DOCKER else 'Local'})...")

    options = _build_options()

    if USE_GRID:
        try:
            driver = webdriver.Remote(command_executor=SELENIUM_HUB, options=options)
            logger.success("✅ Connected to Grid")
        except Exception as e:
            logger.error(f"Grid failed: {e}")
            driver = _create_driver(options)
    else:
        driver = _create_driver(options)

    driver.set_page_load_timeout(60)
    driver.set_script_timeout(60)
    driver.implicitly_wait(3)

    logger.success("✅ Chrome started")

    yield driver

    logger.info("Closing browser...")
    try:
        driver.quit()
    except Exception:
        pass


@pytest.fixture
def credentials():
    return {"username": USERNAME, "password": PASSWORD}