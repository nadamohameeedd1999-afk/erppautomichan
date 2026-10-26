"""
Daily test report (التقرير اليومي) in the approved design (التصميم المعتمد):
A4 landscape, RTL, Microsoft Sans Serif, 3-zone header, teal divider, light-teal filter strip,
teal table header, light row separators, footer «صفحة X من Y».

  html_report(date_from, date_to, user)  -> HTML page (also shown in the dashboard)
  pdf_report(...)                         -> PDF bytes (Chrome "print to PDF")
  auto_tick(now)                          -> emails the PDF once a day at DAILY_REPORT_HOUR (Settings)
"""
import base64
import html
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from config import paths

TEAL, DARK, LIGHT, BORDER, TEXT = "#0F7C7A", "#0A5654", "#E7F3F2", "#D5E2E1", "#1C2B2A"


def _company():
    from web import settings_helper as sh
    c = sh.load_site_config()
    logo = ""
    if c.get("logo_filename"):
        p = sh.find_upload(c["logo_filename"])
        if p:
            mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
            logo = f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()
    return {"name": c.get("company_name_ar") or c.get("site_name_ar") or "أتمتة اختبارات ERP",
            "cr": c.get("company_cr", ""), "vat": c.get("company_vat", ""), "logo": logo}


def collect(date_from, date_to):
    from web import insights
    rows = []
    for r in insights.all_runs():
        t = r["time"]
        if not t or not (date_from <= t <= date_to):
            continue
        s = r["summary"]
        if s.get("auto_retry"):          # the retry's result is the one that counts
            continue
        rows.append({"time": t, "name": r["name"], "site": s.get("site_name") or "", "passed": r["passed"],
                     "duration": r["duration"], "source": {"schedule": "جدولة", "hook": "بعد تحديث", "retry": "إعادة تلقائية",
                                                          "rerun": "إعادة"}.get(s.get("source"), "يدوي"),
                     "message": (r["message"] or "").split("\n")[0][:160]})
    rows.sort(key=lambda x: x["time"])
    return rows


def html_report(date_from=None, date_to=None, user="", for_pdf=False):
    now = datetime.now()
    date_to = date_to or now
    date_from = date_from or (date_to - timedelta(days=1))
    rows = collect(date_from, date_to)
    co = _company()
    total, ok = len(rows), sum(r["passed"] for r in rows)
    bad = total - ok
    rate = f"{(ok / total * 100):.0f}%" if total else "—"
    e = html.escape

    def cell(v):
        return e(str(v)) if v not in (None, "") else "—"

    body = "".join(f"""
      <tr>
        <td class="c">{i}</td>
        <td>{cell(r['name'])}</td>
        <td>{cell(r['site'])}</td>
        <td class="c ltr">{r['time'].strftime('%Y-%m-%d %H:%M')}</td>
        <td class="c">{r['duration']:,.0f}</td>
        <td class="c">{cell(r['source'])}</td>
        <td class="c"><span class="st {'ok' if r['passed'] else 'bad'}">{'ناجح' if r['passed'] else 'فاشل'}</span></td>
        <td>{cell('' if r['passed'] else r['message'])}</td>
      </tr>""" for i, r in enumerate(rows, 1)) or '<tr><td colspan="8" class="c">— مفيش تشغيلات في الفترة دي —</td></tr>'

    strip = "".join(f'<div class="f"><span class="fl">{k}</span><span class="fv">{v}</span></div>' for k, v in [
        ("من تاريخ", date_from.strftime("%Y-%m-%d %H:%M")), ("إلى تاريخ", date_to.strftime("%Y-%m-%d %H:%M")),
        ("عدد التشغيلات", total), ("ناجح", ok), ("فاشل", bad), ("نسبة النجاح", rate)])

    logo = f'<img src="{co["logo"]}" class="logo">' if co["logo"] else ""
    ids = "".join(f'<div class="grey">{k}: {e(v)}</div>' for k, v in (("س.ت", co["cr"]), ("الرقم الضريبي", co["vat"])) if v)
    return f"""<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>تقرير الاختبارات اليومي</title>
<style>
  @page {{ size: A4 landscape; margin: 12mm 10mm 14mm 10mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: "Microsoft Sans Serif", Tahoma, Arial, sans-serif; color: {TEXT}; font-size: 11px; margin: 0;
         background: {'#fff' if for_pdf else '#eef2f2'}; }}
  .page {{ background: #fff; max-width: 1120px; margin: {'0' if for_pdf else '16px auto'}; padding: {'0' if for_pdf else '18px 22px'}; }}
  .hdr {{ display: grid; grid-template-columns: 1fr 1.2fr 1fr; align-items: center; gap: 10px; }}
  .co {{ display: flex; align-items: center; gap: 10px; }}
  .logo {{ max-height: 56px; max-width: 90px; }}
  .coname {{ color: {DARK}; font-weight: bold; font-size: 15px; }}
  .grey {{ color: #7a8584; font-size: 10.5px; }}
  .ttl {{ text-align: center; }}
  .ttl .ar {{ font-weight: bold; font-size: 20px; color: {TEXT}; }}
  .ttl .en {{ color: {TEAL}; font-size: 13px; margin-top: 2px; }}
  .meta {{ text-align: left; direction: rtl; }}
  .meta div {{ margin: 2px 0; }} .meta b {{ color: {TEXT}; }}
  .line {{ height: 3px; background: {TEAL}; margin: 10px 0 12px; border-radius: 2px; }}
  .strip {{ background: {LIGHT}; border: 1px solid {BORDER}; border-radius: 10px; padding: 8px 12px; display: flex; flex-wrap: wrap; gap: 6px 26px; margin-bottom: 12px; }}
  .f {{ display: flex; gap: 6px; }} .fl {{ color: #6f7b7a; }} .fv {{ font-weight: bold; }}
  table {{ width: 100%; border-collapse: collapse; }}
  thead th {{ background: {TEAL}; color: #fff; font-weight: bold; padding: 7px 6px; text-align: right; }}
  thead th.c {{ text-align: center; }}
  tbody td {{ padding: 6px; border-bottom: 1px solid {BORDER}; text-align: right; vertical-align: top; }}
  tbody tr {{ page-break-inside: avoid; }}
  td.c {{ text-align: center; }} .ltr {{ direction: ltr; }}
  .st {{ font-weight: bold; }} .st.ok {{ color: {TEAL}; }} .st.bad {{ color: #c0392b; }}
  .noprint {{ text-align: center; margin: 10px 0; }}
  @media print {{ .noprint {{ display: none; }} body {{ background: #fff; }} .page {{ margin: 0; padding: 0; }} }}
</style></head><body>
<div class="page">
  <div class="hdr">
    <div class="co">{logo}<div><div class="coname">{e(co['name'])}</div>{ids}</div></div>
    <div class="ttl"><div class="ar">تقرير الاختبارات اليومي</div><div class="en">Daily Test Report</div></div>
    <div class="meta"><div><span class="grey">المستخدم:</span> <b>{e(user or '—')}</b></div>
         <div><span class="grey">تاريخ الطباعة:</span> <b class="ltr">{now.strftime('%Y-%m-%d %H:%M')}</b></div></div>
  </div>
  <div class="line"></div>
  <div class="strip">{strip}</div>
  <table>
    <thead><tr><th class="c" style="width:34px">م</th><th>الاختبار</th><th>الموقع</th><th class="c">وقت التشغيل</th>
      <th class="c">المدة (ث)</th><th class="c">المصدر</th><th class="c">النتيجة</th><th>سبب الفشل</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
</div>
</body></html>"""


def pdf_report(date_from=None, date_to=None, user=""):
    """PDF bytes via Chrome (same browser the tests use). Footer: صفحة X من Y."""
    from tests.conftest import _build_options, _create_driver
    page = html_report(date_from, date_to, user, for_pdf=True)
    tmp = Path(tempfile.mkdtemp(prefix="daily_report_")) / "report.html"
    tmp.write_text(page, encoding="utf-8")
    opts = _build_options()
    opts.add_argument("--headless=new")
    prof = tempfile.mkdtemp(prefix="report_chrome_")
    opts.add_argument(f"--user-data-dir={prof}")
    d = _create_driver(opts)
    try:
        d.get(tmp.as_uri())
        time.sleep(0.8)
        footer = ('<div style="width:100%;text-align:center;font-size:9px;color:#555;font-family:Tahoma,Arial;direction:rtl">'
                  'صفحة <span class="pageNumber"></span> من <span class="totalPages"></span></div>')
        res = d.execute_cdp_cmd("Page.printToPDF", {
            "landscape": True, "paperWidth": 8.27, "paperHeight": 11.69, "printBackground": True,
            "marginTop": 0.45, "marginBottom": 0.55, "marginLeft": 0.4, "marginRight": 0.4,
            "displayHeaderFooter": True, "headerTemplate": "<div></div>", "footerTemplate": footer,
            "preferCSSPageSize": False})
        return base64.b64decode(res["data"])
    finally:
        try:
            d.quit()
        except Exception:
            pass


# ---------------- daily email ----------------
_state = {"t": 0}


def _cfg():
    from web import settings_helper as sh
    c = sh.load_site_config()
    try:
        hour = int(c.get("daily_report_hour", "") or os.getenv("DAILY_REPORT_HOUR", "") or -1)
    except ValueError:
        hour = -1
    return hour


def send_daily(now=None):
    """Make the PDF for the last 24h and email it (Settings → Email)."""
    from config import emailer
    now = now or datetime.now()
    pdf = pdf_report(now - timedelta(days=1), now, "الجدولة")
    out = paths.DATA_DIR / "reports"
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"daily_{now:%Y%m%d}.pdf"
    f.write_bytes(pdf)
    ok = emailer.send_file(f"📊 تقرير الاختبارات اليومي {now:%Y-%m-%d}",
                           "مرفق تقرير الاختبارات لآخر 24 ساعة.", f)
    print(f"[daily-report] {f.name} {'📧 اتبعت' if ok else '(الإيميل مش متظبط — اتحفظ بس)'}", flush=True)
    return f


def auto_tick(now=None):
    if time.time() - _state["t"] < 120:
        return
    _state["t"] = time.time()
    hour = _cfg()
    now = now or datetime.now()
    if hour < 0 or now.hour != hour:
        return
    marker = paths.STATE_DIR / "daily_report_sent"
    today = now.strftime("%Y-%m-%d")
    if marker.exists() and marker.read_text(encoding="utf-8").strip() == today:
        return
    marker.write_text(today, encoding="utf-8")
    try:
        send_daily(now.replace(tzinfo=None))
    except Exception as e:
        print(f"[daily-report] error: {e}", flush=True)
