"""
Monthly client report (التقرير الشهري للعميل) in the approved design (التصميم المعتمد):
«اختبرنا نظامك X مرة على Y شاشة خلال الشهر، والنتيجة …» — one report per test site (= client) per month.

/reports/monthly                      page: pick the client + month, preview, PDF, email
/reports/monthly/view?site=&month=    the report (HTML)
/reports/monthly.pdf?site=&month=     PDF (A4 landscape, «صفحة X من Y»)
/api/reports/monthly/send             POST {site, month, to}
/api/reports/monthly/settings         GET/POST {auto, day, recipients: {site_id: "a@b.com, …"}}
auto_tick(now)                        on the chosen day of the month: last month's report to each client that has emails
"""
import html
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta

from flask import Blueprint, Response, jsonify, render_template, request

from config import paths
from web import auth
from web.daily_report import TEAL, DARK, LIGHT, BORDER, TEXT, _company, html_to_pdf

bp = Blueprint("monthly", __name__)
SETTINGS = paths.settings_file("monthly_report.json")
MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


def _month_range(month):
    y, m = [int(x) for x in month.split("-")]
    start = datetime(y, m, 1)
    end = datetime(y + (m == 12), (m % 12) + 1, 1)
    return start, end


def month_label(month):
    y, m = [int(x) for x in month.split("-")]
    return f"{MONTHS[m - 1]} {y}"


def _site(site_id):
    from web import sites_api
    profs = sites_api.profiles()
    p = next((x for x in profs if x["id"] == site_id), None) or next((x for x in profs if x["active"]), None)
    if p:
        return p
    from config.settings import BASE_URL
    return {"id": "", "name": "الموقع الأساسي", "base_url": BASE_URL, "active": True}


def collect(site_id, month):
    from web import insights, sites_api
    start, end = _month_range(month)
    site = _site(site_id)
    active = sites_api.active_id()
    runs = []
    for r in insights.all_runs():
        s = r["summary"]
        if s.get("auto_retry") or not (start <= r["time"] < end):
            continue
        sid = s.get("site") or active
        if sid != site["id"] and not (not site["id"] and not s.get("site")):
            continue
        runs.append(r)
    runs.sort(key=lambda r: r["time"])
    per = defaultdict(lambda: {"runs": 0, "passed": 0, "last": None, "last_fail": "", "fails": []})
    names = {}
    for r in runs:
        k = r["key"]
        names[k] = (r["name"] or k).replace("⏰ ", "").split(" · ")[0]
        x = per[k]
        x["runs"] += 1
        x["passed"] += 1 if r["passed"] else 0
        x["last"] = r
        if not r["passed"]:
            x["last_fail"] = (r["message"] or "").split("\n")[0][:150]
            x["fails"].append(r["time"])
    tests = []
    fixed, open_ = [], []
    for k, x in per.items():
        last = x["last"]
        row = {"key": k, "name": names[k], "runs": x["runs"], "passed": x["passed"], "failed": x["runs"] - x["passed"],
               "rate": round(x["passed"] / x["runs"] * 100) if x["runs"] else 0, "last_ok": last["passed"],
               "last_time": last["time"], "reason": x["last_fail"]}
        tests.append(row)
        if x["fails"] and last["passed"]:
            fixed.append({**row, "first_fail": x["fails"][0], "fixed_at": last["time"]})
        elif not last["passed"]:
            open_.append(row)
    tests.sort(key=lambda r: (r["last_ok"], r["rate"], r["name"]))
    total, ok = len(runs), sum(r["passed"] for r in runs)
    # speed (⚡ سرعة الشاشات) in this month
    perf = []
    try:
        from engine.check_runner import load_perf
        hist = load_perf().get((site.get("base_url") or "").rstrip("/"), {})
        for url, pts in hist.items():
            ms = [p["t"] for p in pts if start.isoformat() <= p.get("at", "") < end.isoformat()]
            if ms:
                perf.append({"name": pts[-1].get("name") or url, "url": url, "avg": sum(ms) / len(ms), "max": max(ms), "n": len(ms)})
        perf.sort(key=lambda r: -r["avg"])
    except Exception:
        pass
    return {"site": site, "month": month, "label": month_label(month), "start": start, "end": end, "total": total, "ok": ok,
            "bad": total - ok, "rate": round(ok / total * 100) if total else None, "tests": tests, "fixed": fixed, "open": open_,
            "screens": len(tests), "perf": perf[:25],
            "days": len({r["time"].date() for r in runs}), "minutes": round(sum(r["duration"] for r in runs) / 60)}


def html_report(site_id, month, user="", for_pdf=False):
    d = collect(site_id, month)
    co = _company()
    e = html.escape
    now = datetime.now()

    def cell(v):
        return e(str(v)) if v not in (None, "") else "—"

    rate = f"{d['rate']}%" if d["rate"] is not None else "—"
    if d["total"]:
        verdict = ("النظام مستقر — كل الاختبارات شغالة في آخر الشهر" if not d["open"] else
                   f"فيه {len(d['open'])} اختبار لسه بيفشل في آخر الشهر ومتابعينه")
        intro = (f"اختبرنا نظامك <b>{d['total']:,}</b> مرة على <b>{d['screens']}</b> شاشة/سيناريو خلال <b>{d['label']}</b> "
                 f"(على مدار {d['days']} يوم)، ونسبة النجاح <b>{rate}</b>. "
                 + (f"اتلقت واتحلت <b>{len(d['fixed'])}</b> مشكلة قبل ما توصل للمستخدمين. " if d["fixed"] else "")
                 + f"<b>{verdict}</b>.")
    else:
        intro = f"مفيش تشغيلات اتسجلت على الموقع ده في {d['label']}."
    strip = "".join(f'<div class="f"><span class="fl">{k}</span><span class="fv">{v}</span></div>' for k, v in [
        ("العميل / الموقع", e(d["site"]["name"])), ("الشهر", d["label"]), ("عدد التشغيلات", f"{d['total']:,}"),
        ("نسبة النجاح", rate), ("شاشات وسيناريوهات", d["screens"]), ("مشاكل اتحلت", len(d["fixed"])),
        ("لسه مفتوحة", len(d["open"])), ("وقت الاختبار", f"{d['minutes']:,} دقيقة")])
    body = "".join(f"""<tr><td class="c">{i}</td><td>{cell(t['name'])}</td><td class="c">{t['runs']}</td><td class="c">{t['passed']}</td>
        <td class="c">{t['failed']}</td><td class="c">{t['rate']}%</td>
        <td class="c"><span class="st {'ok' if t['last_ok'] else 'bad'}">{'ناجح' if t['last_ok'] else 'فاشل'}</span></td>
        <td class="c ltr">{t['last_time'].strftime('%Y-%m-%d')}</td><td>{cell('' if t['last_ok'] else t['reason'])}</td></tr>"""
                   for i, t in enumerate(d["tests"], 1)) or '<tr><td colspan="9" class="c">—</td></tr>'
    fixed = "".join(f"""<tr><td class="c">{i}</td><td>{cell(t['name'])}</td><td class="c ltr">{t['first_fail'].strftime('%Y-%m-%d')}</td>
        <td class="c ltr">{t['fixed_at'].strftime('%Y-%m-%d')}</td><td>{cell(t['reason'])}</td></tr>""" for i, t in enumerate(d["fixed"], 1))
    perf = "".join(f"""<tr><td class="c">{i}</td><td>{cell(p['name'])}</td><td class="c">{p['avg']:.2f}</td><td class="c">{p['max']:.2f}</td><td class="c">{p['n']}</td></tr>"""
                   for i, p in enumerate(d["perf"], 1))
    logo = f'<img src="{co["logo"]}" class="logo">' if co["logo"] else ""
    ids = "".join(f'<div class="grey">{k}: {e(v)}</div>' for k, v in (("س.ت", co["cr"]), ("الرقم الضريبي", co["vat"])) if v)
    return f"""<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>التقرير الشهري — {e(d['site']['name'])} — {d['label']}</title>
<style>
  @page {{ size: A4 landscape; margin: 12mm 10mm 14mm 10mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: "Microsoft Sans Serif", Tahoma, Arial, sans-serif; color: {TEXT}; font-size: 11px; margin: 0; background: {'#fff' if for_pdf else '#eef2f2'}; }}
  .page {{ background: #fff; max-width: 1120px; margin: {'0' if for_pdf else '16px auto'}; padding: {'0' if for_pdf else '18px 22px'}; }}
  .hdr {{ display: grid; grid-template-columns: 1fr 1.2fr 1fr; align-items: center; gap: 10px; }}
  .co {{ display: flex; align-items: center; gap: 10px; }} .logo {{ max-height: 56px; max-width: 90px; }}
  .coname {{ color: {DARK}; font-weight: bold; font-size: 15px; }} .grey {{ color: #7a8584; font-size: 10.5px; }}
  .ttl {{ text-align: center; }} .ttl .ar {{ font-weight: bold; font-size: 20px; color: {TEXT}; }} .ttl .en {{ color: {TEAL}; font-size: 13px; margin-top: 2px; }}
  .meta {{ text-align: left; direction: rtl; }} .meta div {{ margin: 2px 0; }}
  .line {{ height: 3px; background: {TEAL}; margin: 10px 0 12px; border-radius: 2px; }}
  .strip {{ background: {LIGHT}; border: 1px solid {BORDER}; border-radius: 10px; padding: 8px 12px; display: flex; flex-wrap: wrap; gap: 6px 26px; margin-bottom: 12px; }}
  .f {{ display: flex; gap: 6px; }} .fl {{ color: #6f7b7a; }} .fv {{ font-weight: bold; }}
  .intro {{ font-size: 13px; line-height: 1.9; margin: 0 0 12px; padding: 10px 14px; border-right: 4px solid {TEAL}; background: #fbfdfd; }}
  h3 {{ color: {DARK}; font-size: 13px; margin: 16px 0 6px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  thead th {{ background: {TEAL}; color: #fff; font-weight: bold; padding: 7px 6px; text-align: right; }} thead th.c {{ text-align: center; }}
  tbody td {{ padding: 6px; border-bottom: 1px solid {BORDER}; text-align: right; vertical-align: top; }}
  tbody tr {{ page-break-inside: avoid; }} td.c {{ text-align: center; }} .ltr {{ direction: ltr; }}
  .st {{ font-weight: bold; }} .st.ok {{ color: {TEAL}; }} .st.bad {{ color: #c0392b; }}
  @media print {{ body {{ background: #fff; }} .page {{ margin: 0; padding: 0; }} }}
</style></head><body><div class="page">
  <div class="hdr">
    <div class="co">{logo}<div><div class="coname">{e(co['name'])}</div>{ids}</div></div>
    <div class="ttl"><div class="ar">تقرير جودة النظام الشهري</div><div class="en">Monthly System Quality Report</div></div>
    <div class="meta"><div><span class="grey">المستخدم:</span> <b>{e(user or '—')}</b></div>
         <div><span class="grey">تاريخ الطباعة:</span> <b class="ltr">{now.strftime('%Y-%m-%d %H:%M')}</b></div></div>
  </div>
  <div class="line"></div>
  <div class="strip">{strip}</div>
  <p class="intro">{intro}</p>
  <h3>نتيجة كل شاشة / سيناريو</h3>
  <table><thead><tr><th class="c" style="width:30px">م</th><th>الاختبار</th><th class="c">مرات التشغيل</th><th class="c">ناجح</th><th class="c">فاشل</th>
    <th class="c">نسبة النجاح</th><th class="c">آخر نتيجة</th><th class="c">آخر تشغيل</th><th>سبب آخر فشل</th></tr></thead><tbody>{body}</tbody></table>
  {f'''<h3>مشاكل اتلقت واتحلت خلال الشهر</h3><table><thead><tr><th class="c" style="width:30px">م</th><th>الاختبار</th><th class="c">أول فشل</th>
    <th class="c">اتحلت في</th><th>المشكلة</th></tr></thead><tbody>{fixed}</tbody></table>''' if fixed else ''}
  {f'''<h3>سرعة فتح الشاشات (بالثانية)</h3><table><thead><tr><th class="c" style="width:30px">م</th><th>الشاشة</th><th class="c">المتوسط</th>
    <th class="c">الأبطأ</th><th class="c">عدد القياسات</th></tr></thead><tbody>{perf}</tbody></table>''' if perf else ''}
</div></body></html>"""


def pdf_report(site_id, month, user=""):
    return html_to_pdf(html_report(site_id, month, user, for_pdf=True))


def _safe(name):
    import re
    return re.sub(r"[^\w\-]+", "_", name or "site").strip("_")[:40] or "site"


def save_pdf(site_id, month, user=""):
    d = _site(site_id)
    out = paths.DATA_DIR / "reports"
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"monthly_{_safe(d['name'])}_{month}.pdf"
    f.write_bytes(pdf_report(site_id, month, user))
    return f, d


def send(site_id, month, to=None, user=""):
    from config import emailer
    f, d = save_pdf(site_id, month, user)
    ok = emailer.send_file(f"📊 تقرير جودة النظام — {d['name']} — {month_label(month)}",
                           f"مرفق تقرير اختبارات نظامكم عن شهر {month_label(month)}.", f, to=to or None)
    return ok, f


# ---------------------------------------------------------------- settings + automatic sending
def load_settings():
    from config.storage import load_json
    c = load_json(SETTINGS, {}) or {}
    c.setdefault("auto", False)
    c.setdefault("day", 1)
    c.setdefault("recipients", {})
    return c


_state = {"t": 0}


def auto_tick(now=None):
    if time.time() - _state["t"] < 300:
        return
    _state["t"] = time.time()
    c = load_settings()
    now = now or datetime.now()
    if not c.get("auto") or now.day != int(c.get("day") or 1) or now.hour < 8:
        return
    month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    marker = paths.STATE_DIR / "monthly_report_sent"
    sent = marker.read_text(encoding="utf-8").split() if marker.exists() else []
    for sid, to in (c.get("recipients") or {}).items():
        tag = f"{month}:{sid}"
        if not str(to).strip() or tag in sent:
            continue
        sent.append(tag)
        marker.write_text("\n".join(sent[-200:]), encoding="utf-8")
        try:
            ok, f = send(sid, month, to, "الجدولة")
            print(f"[monthly-report] {f.name} → {to} {'📧' if ok else '(الإيميل مش متظبط)'}", flush=True)
        except Exception as e:
            print(f"[monthly-report] {sid}: {e}", flush=True)


# ---------------------------------------------------------------- routes
def _args():
    site = request.args.get("site", "")
    month = request.args.get("month") or (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    return site, month


@bp.route("/reports/monthly")
@auth.login_required
def monthly_page():
    from web import sites_api
    now = datetime.now().replace(day=1)
    months = []
    for i in range(0, 13):
        y, mo = now.year, now.month - i
        while mo <= 0:
            mo += 12
            y -= 1
        months.append((f"{y}-{mo:02d}", month_label(f"{y}-{mo:02d}")))
    return render_template("monthly.html", sites=sites_api.profiles(), months=months, settings=load_settings(),
                           default_month=months[1][0] if len(months) > 1 else months[0][0])


@bp.route("/reports/monthly/view")
@auth.login_required
def monthly_view():
    site, month = _args()
    u = auth.current_user() or {}
    return html_report(site, month, u.get("full_name") or u.get("username") or "")


@bp.route("/reports/monthly.pdf")
@auth.login_required
def monthly_pdf():
    site, month = _args()
    u = auth.current_user() or {}
    pdf = pdf_report(site, month, u.get("full_name") or u.get("username") or "")
    from urllib.parse import quote
    name = f"monthly_{_safe(_site(site)['name'])}_{month}.pdf"
    ascii_name = f"monthly_report_{month}.pdf"           # Arabic site names: the real name goes in filename*
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={ascii_name}; filename*=UTF-8''{quote(name)}"})


@bp.route("/api/reports/monthly/send", methods=["POST"])
@auth.login_required
def monthly_send():
    d = request.get_json(silent=True) or {}
    u = auth.current_user() or {}
    try:
        ok, f = send(d.get("site", ""), d.get("month") or _args()[1], d.get("to") or None,
                     u.get("full_name") or u.get("username") or "")
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    if not ok:
        return jsonify({"success": False, "error": "الـ PDF اتعمل بس الإيميل ما اتبعتش — اتأكدي من الإعدادات ← Email"})
    return jsonify({"success": True, "file": f.name})


@bp.route("/api/reports/monthly/settings", methods=["GET", "POST"])
@auth.login_required
def monthly_settings():
    from config.storage import save_json
    if request.method == "POST":
        d = request.get_json(silent=True) or {}
        c = load_settings()
        c["auto"] = bool(d.get("auto"))
        c["day"] = max(1, min(28, int(d.get("day") or 1)))
        c["recipients"] = {str(k): str(v).strip() for k, v in (d.get("recipients") or {}).items()}
        save_json(SETTINGS, c)
    return jsonify({"success": True, "settings": load_settings()})
