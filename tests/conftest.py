"""
Pytest Fixtures — Safe flags مع VNC
بدون --single-process (اللي بيكسر Chrome 155)
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
        logger.info("🐳 Docker mode (VNC + safe flags)")

        # ===== Basic =====
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1280,720")

        # ===== Memory optimization (آمنة) =====
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--disable-ipc-flooding-protection")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-extensions")
        options.add_argument("--mute-audio")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-features=TranslateUI,BlinkGenPropertyTrees")
        options.add_argument("--disable-images")
        options.add_argument("--js-flags=--max-old-space-size=256")

        # ❌ مش بنستخدم:
        # --single-process (بيكسر Chrome 155)
        # --no-zygote (بيكسر Chrome 155)
        # --disable-gpu (خفيف كفاية)

        chrome_bin = os.getenv("CHROME_BIN", "/usr/bin/google-chrome")
        if os.path.exists(chrome_bin):
            options.binary_location = chrome_bin

    else:
        logger.info("💻 Local mode")
        options.add_argument("--start-maximized")
        options.add_argument("--window-size=1920,1080")

    options.add_argument("--disable-notifications")
    options.add_argument("--log-level=3")
    options.add_argument("--disable-background-networking")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--lang=ar-EG")

    return options


def _get_service():
    if IS_DOCKER or IS_LINUX:
        path = os.getenv("CHROMEDRIVER_PATH", "/usr/local/bin/chromedriver")
        if os.path.exists(path):
            return Service(path)
        from webdriver_manager.chrome import ChromeDriverManager
        return Service(ChromeDriverManager().install())
    else:
        DRIVER_PATH = BASE_DIR / "drivers" / "chromedriver.exe"
        if DRIVER_PATH.exists():
            return Service(str(DRIVER_PATH))
        from webdriver_manager.chrome import ChromeDriverManager
        return Service(ChromeDriverManager().install())


def _create_driver(options):
    service = _get_service()
    return webdriver.Chrome(service=service, options=options)


@pytest.fixture(scope="function")
def driver(request):
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

    rep = getattr(request.node, "rep_call", None)
    if rep is not None and rep.failed:
        _attach_failure_screenshot(driver, request.node.name)

    logger.info("Closing browser...")
    try:
        driver.quit()
    except Exception:
        pass


@pytest.fixture
def credentials():
    return {"username": USERNAME, "password": PASSWORD}

# ===== Failure screenshots =====
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Store each phase's report on the test item (rep_setup / rep_call / rep_teardown)."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)


def _attach_failure_screenshot(driver, test_name):
    """On test failure: save a screenshot to disk and attach it to Allure."""
    try:
        import re
        import allure
        from datetime import datetime
        from config.settings import SCREENSHOTS_DIR

        png = driver.get_screenshot_as_png()
        safe = re.sub(r"[^\w\-]", "_", test_name)
        allure.attach(png, name=f"FAILED_{safe}", attachment_type=allure.attachment_type.PNG)
        path = SCREENSHOTS_DIR / f"FAILED_{safe}_{datetime.now():%Y%m%d_%H%M%S}.png"
        path.write_bytes(png)
        logger.error(f"Failure screenshot: {path}")
    except Exception as e:
        logger.warning(f"Could not capture failure screenshot: {str(e)[:100]}")

# ===== Repeat option: run each selected test N times =====
def pytest_addoption(parser):
    parser.addoption(
        "--repeat",
        action="store",
        default=None,
        help="Run every selected test N times (fresh browser each time). "
             "Fallback: TEST_REPEAT env var.",
    )


def _repeat_count(config):
    raw = config.getoption("--repeat", default=None)
    if raw is None:
        raw = os.getenv("TEST_REPEAT", "1")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


@pytest.fixture
def repeat_iteration(request):
    return request.param


def pytest_generate_tests(metafunc):
    count = _repeat_count(metafunc.config)
    if count > 1:
        metafunc.fixturenames.append("repeat_iteration")
        metafunc.parametrize(
            "repeat_iteration",
            range(1, count + 1),
            indirect=True,
            ids=lambda i: f"run{i}of{count}",
        )