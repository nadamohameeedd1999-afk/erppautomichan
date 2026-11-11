"""
HTML → PDF with the headless Chrome the tool already ships with (Selenium + CDP Page.printToPDF), so Arabic, RTL and
colours come out exactly like the page. A4 landscape, backgrounds on, footer «صفحة X من Y».
Falls back to Playwright's Chromium when Selenium's Chrome isn't there (local / sandbox).
"""
import base64
import os
import tempfile

FOOTER = ('<div style="width:100%;font-size:8px;color:#6B7B7A;text-align:center;font-family:Tahoma,Arial;direction:rtl">'
          'صفحة <span class="pageNumber"></span> من <span class="totalPages"></span></div>')


def html_to_pdf(html):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        path = f.name
    try:
        try:
            return _selenium(path)
        except Exception as e1:
            try:
                return _playwright(path)
            except Exception as e2:
                raise RuntimeError(f"مقدرتش أطلع PDF: {str(e1)[:120]} / {str(e2)[:120]}")
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _selenium(path):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    o = webdriver.ChromeOptions()
    for a in ("--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"):
        o.add_argument(a)
    svc = Service("/usr/local/bin/chromedriver") if os.path.exists("/usr/local/bin/chromedriver") else Service()
    d = webdriver.Chrome(service=svc, options=o)
    try:
        d.get("file://" + path)
        r = d.execute_cdp_cmd("Page.printToPDF", {"landscape": True, "printBackground": True, "paperWidth": 11.69, "paperHeight": 8.27,
                                                  "marginTop": 0.4, "marginBottom": 0.5, "marginLeft": 0.4, "marginRight": 0.4,
                                                  "displayHeaderFooter": True, "headerTemplate": "<div></div>", "footerTemplate": FOOTER})
        return base64.b64decode(r["data"])
    finally:
        d.quit()


def _playwright(path):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        try:
            pg = b.new_page()
            pg.goto("file://" + path)
            return pg.pdf(format="A4", landscape=True, print_background=True, display_header_footer=True,
                          header_template="<div></div>", footer_template=FOOTER,
                          margin={"top": "10mm", "bottom": "13mm", "left": "10mm", "right": "10mm"})
        finally:
            b.close()
