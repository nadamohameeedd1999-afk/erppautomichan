"""
Pytest Fixtures — VNC mode (Chrome مرئي في Railway)
"""
import pytest
import os
import sys
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"
os.environ["WDM_LOCAL"] = "1"
os.environ["WDM_LOG"] = "0"

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import USERNAME, PASSWORD
from utils.logger import logger


SELENIUM_HUB = os.getenv("SELENIUM_HUB", "http://localhost:4444")
USE_GRID = os.getenv("USE_SELENIUM_GRID", "false").lower() == "true"

IS_DOCKER = os.path.exists("/.dockerenv") or os.getenv("RAILWAY_ENVIRONMENT") is not None
IS_LINUX = sys.platform.startswith("linux")


def _build_options():
    options = Options()

    if IS_DOCKER or IS_LINUX:
        logger.info("🐳 Docker/Linux mode")
        # نستخدم DISPLAY بدل headless — عشان يظهر في VNC
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-background-networking")

        chrome_bin = os.getenv("CHROME_BIN", "/usr/bin/google-chrome")
        if os.path.exists(chrome_bin):
            options.binary_location = chrome_bin
            logger.info(f"Chrome binary: {chrome_bin}")
    else:
        logger.info("💻 Local mode")
        options.add_argument("--start-maximized")
        options.add_argument("--window-size=1920,1080")

    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--lang=ar-EG")
    options.add_argument("--incognito")

    return options


def _get_chromedriver_service():
    if IS_DOCKER or IS_LINUX:
        path = os.getenv("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
        if os.path.exists(path):
            logger.info(f"✅ Using chromedriver: {path}")
            return Service(path)
        else:
            from webdriver_manager.chrome import ChromeDriverManager
            return Service(ChromeDriverManager().install())
    else:
        DRIVER_PATH = BASE_DIR / "drivers" / "chromedriver.exe"
        if DRIVER_PATH.exists():
            return Service(str(DRIVER_PATH))
        else:
            from webdriver_manager.chrome import ChromeDriverManager
            return Service(ChromeDriverManager().install())


def _create_driver(options):
    service = _get_chromedriver_service()
    return webdriver.Chrome(service=service, options=options)


@pytest.fixture(scope="function")
def driver():
    logger.info("=" * 50)
    logger.info(f"Starting Chrome ({'Docker' if IS_DOCKER else 'Local'})...")

    options = _build_options()

    if USE_GRID:
        try:
            driver = webdriver.Remote(command_executor=SELENIUM_HUB, options=options)
            logger.success("✅ Grid")
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