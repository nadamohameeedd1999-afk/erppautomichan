"""
Discovery report (تقرير اكتشاف الشاشات) — same approved design as the daily report:
A4 landscape, RTL, teal, 3-zone header, footer «صفحة X من Y» in the PDF.
"""
import html
import json
from datetime import datetime

from config import paths
from web.daily_report import TEAL, DARK, LIGHT, BORDER, TEXT, _company

DIR = paths.RUNS_DIR / "discovery"
KIND = {"screen": "شاشة فيها جدول", "page": "صفحة (تقرير / لوحة)", "error": "خطأ في الفتح"}
PHASE = {"done": "اكتمل", "stopped": "اتوقف يدويًا", "error": "فشل", "checking": "شغال / اتقطع", "menu": "اتقطع", "login": "اتقطع"}


def list_runs(limit=30):
    out = []
    for f in sorted(DIR.glob("disc_*.json"), reverse=True)[:limit]:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        it = d.get("items", [])
        out.append({"id": f.stem, "started_at": d.get("started_at", ""), "phase": PHASE.get(d.get("phase"), d.get("phase", "")),
                    "total": d.get("total", 0), "done": d.get("done", 0),
                    "screens": sum(x.get("kind") == "screen" for x in it), "new": sum(x.get("kind") == "screen" and not x.get("known") for x in it),
                    "added": sum(bool(x.get("added_at")) for x in it)})
    return out


def load(rid):
    rid = "".join(c for c in rid if c.isalnum() or c == "_")
    f = DIR / f"{rid}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def html_report(d, user="", for_pdf=False):
    e = html.escape
    now = datetime.now()
    co = _company()
    items = d.get("items", [])
    base = (d.get("base_url") or "").rstrip("/")
    n_scr = sum(x.get("kind") == "screen" for x in items)

    def dur():
        try:
            a = datetime.fromisoformat(d["started_at"]); b = datetime.fromisoformat(d.get("finished_at") or d.get("updated_at"))
            s = int((b - a).total_seconds()); return f"{s // 60}د {s % 60}ث"
        except Exception:
            return "—"

    def status(x):
        if x.get("added_at"):
            return '<span class="st ok">اتضافت</span>'
        if x.get("known"):
            return '<span class="grey">موجودة قبل كده</span>'
        return '<span class="grey">—</span>'

    body = "".join(f"""
      <tr>
        <td class="c">{i}</td>
        <td>{e(x.get('name') or '—')}</td>
        <td class="ltr">{e(x.get('name_en') or '—')}</td>
        <td>{e(x.get('group') or '—')}</td>
        <td class="ltr"><a href="{e(base + x.get('url', ''))}">{e(x.get('url', ''))}</a></td>
        <td class="c"><span class="st {'ok' if x.get('kind') == 'screen' else ('bad' if x.get('kind') == 'error' else '')}">{KIND.get(x.get('kind'), '—')}</span></td>
        <td class="c">{x.get('tables', '—')}</td>
        <td class="c">{x.get('rows', '—')}</td>
        <td class="c">{'✓' if x.get('has_add') else '—'}</td>
        <td class="c">{x.get('seconds', '—')}</td>
        <td class="c">{status(x)}</td>
      </tr>""" for i, x in enumerate(items, 1)) or '<tr><td colspan="11" class="c">— مفيش روابط اتفحصت —</td></tr>'

    strip = "".join(f'<div class="f"><span class="fl">{k}</span><span class="fv">{v}</span></div>' for k, v in [
        ("الموقع", e(base or "—")), ("البداية", (d.get("started_at") or "").replace("T", " ")), ("المدة", dur()),
        ("الحالة", PHASE.get(d.get("phase"), d.get("phase", ""))), ("روابط القايمة", d.get("total", 0)),
        ("اتفحص", d.get("done", 0)), ("شاشات بجدول", n_scr),
        ("جديدة", sum(x.get("kind") == "screen" and not x.get("known") for x in items)),
        ("صفحات تانية", sum(x.get("kind") == "page" for x in items)), ("أخطاء", sum(x.get("kind") == "error" for x in items)),
        ("اتضاف للاختبارات", sum(bool(x.get("added_at")) for x in items)),
        ("فلتر التخطي", e("، ".join(d.get("skip") or []) or "—")), ("اتخطى", len(d.get("skipped") or []))])
    skipped = "".join(f'<div class="stp">🚫 {e(x.get("name", ""))} — <span class="ltr">{e(x.get("url", ""))}</span> '
                      f'<span class="grey">(فيه «{e(x.get("word", ""))}»)</span></div>' for x in d.get("skipped") or [])
    steps = "".join(f'<div class="stp"><span class="ltr grey">{e(s.get("t", ""))}</span> {e(s.get("msg", ""))}</div>' for s in d.get("steps", []))

    logo = f'<img src="{co["logo"]}" class="logo">' if co["logo"] else ""
    ids = "".join(f'<div class="grey">{k}: {e(v)}</div>' for k, v in (("س.ت", co["cr"]), ("الرقم الضريبي", co["vat"])) if v)
    return f"""<!doctype html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><title>تقرير اكتشاف الشاشات</title>
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
  td.c {{ text-align: center; }} .ltr {{ direction: ltr; unicode-bidi: embed; }}
  td.ltr {{ text-align: left; }} a {{ color: {DARK}; }}
  .st {{ font-weight: bold; }} .st.ok {{ color: {TEAL}; }} .st.bad {{ color: #c0392b; }}
  h3 {{ color: {DARK}; font-size: 13px; margin: 16px 0 6px; }}
  .stp {{ padding: 2px 0; border-bottom: 1px dashed {BORDER}; }}
  @media print {{ .noprint {{ display: none; }} body {{ background: #fff; }} .page {{ margin: 0; padding: 0; }} }}
</style></head><body>
<div class="page">
  <div class="hdr">
    <div class="co">{logo}<div><div class="coname">{e(co['name'])}</div>{ids}</div></div>
    <div class="ttl"><div class="ar">تقرير اكتشاف شاشات النظام</div><div class="en">System Screens Discovery Report</div></div>
    <div class="meta"><div><span class="grey">المستخدم:</span> <b>{e(user or '—')}</b></div>
         <div><span class="grey">تاريخ الطباعة:</span> <b class="ltr">{now.strftime('%Y-%m-%d %H:%M')}</b></div></div>
  </div>
  <div class="line"></div>
  <div class="strip">{strip}</div>
  <table>
    <thead><tr><th class="c" style="width:30px">م</th><th>اسم الشاشة</th><th>English name</th><th>القسم</th><th>الرابط</th>
      <th class="c">النوع</th><th class="c">جداول</th><th class="c">صفوف</th><th class="c">زر إضافة</th><th class="c">ث</th><th class="c">الاختبارات</th></tr></thead>
    <tbody>{body}</tbody>
  </table>
  {('<h3>الروابط اللي اتخطت بالفلتر</h3>' + skipped) if skipped else ''}
  <h3>خطوات التنفيذ</h3>
  {steps or '<div class="grey">—</div>'}
</div>
</body></html>"""
