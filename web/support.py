"""
🐞 دعم المطورين  — every ERP problem the tests found (scenario cases that failed, notes found while saving, broken screens,
   unbalanced books, server errors …) in one list with the details a developer needs, + the ones found by hand
   (engine/known_issues.py) + manual entries. Export Word / Excel in the approved report design.
🛠️ دعم الأداة   — every problem of the TOOL itself (engine stopped, step it can't do yet, browser / network, missing site
   data) with the end of the run log, so it can be copied and sent to be fixed.
Statuses + notes are kept per problem (settings/support_status.json); a problem whose subject passed on a later run
is shown as «اتصلحت؟ (آخر تشغيل نجح)».
"""
import hashlib
import io
import json
import re
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request, send_file

from config import paths
from web import auth

bp = Blueprint("support", __name__)

DEV_STATUS = ["جديد", "اتبلغ للمطور", "بيتصلح", "اتصلح", "مش مشكلة"]
TOOL_STATUS = ["جديد", "اتبعت للإصلاح", "اتصلح", "مش مشكلة"]
SEV_ORDER = {"عالية": 0, "متوسطة": 1, "منخفضة": 2}
MAX_DAYS = 60


def _f(name):
    return paths.SETTINGS_DIR / name


def _load(name, dflt):
    try:
        return json.loads(_f(name).read_text(encoding="utf-8"))
    except Exception:
        return dflt


def _save(name, data):
    _f(name).parent.mkdir(parents=True, exist_ok=True)
    _f(name).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _id(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def _norm(msg):
    """the same problem with other numbers / ids → one signature"""
    t = re.sub(r"\d[\d,.:/-]*", "#", str(msg or ""))
    return re.sub(r"\s+", " ", t).strip()[:160]


def _site(r):
    s = r.get("summary") or {}
    return s.get("site_name") or re.sub(r"^https?://", "", s.get("base_url") or "").strip("/") or "—"


def _site_url(r, d=None):
    """the real ERP address of the run's site (profile base_url) — never the profile's display name"""
    u = ((d or {}).get("biz") or {}).get("url") or ""
    if u:
        return u.rstrip("/")
    sid = (r.get("summary") or {}).get("site") or ""
    try:
        from web import sites_api
        ps = sites_api.profiles()
        p = next((x for x in ps if x["id"] == sid), None) or next((x for x in ps if x["name"] == _site(r)), None) or (next((x for x in ps if x["active"]), None) if not sid else None)
        if p and p.get("base_url"):
            return p["base_url"].rstrip("/")
    except Exception:
        pass
    return ""


def _doc_link(base, code, doc_id):
    """the page of the screen — the document itself when its id is known"""
    try:
        from engine.biz_cases import PROFILES
        P = PROFILES.get(code)
    except Exception:
        P = None
    if not base or not P:
        return base or ""
    return f"{base}/{P['ctrl']}/AddEdit/{doc_id}" if doc_id else base + P["path"]


def _host(x):
    return re.sub(r"^https?://", "", str(x or "")).strip("/").lower()


SEV_WORDS = r"قيد|ضريب|إجمالي|الإجماليات|مخزن|كارت|المدفوع|الحفظ|متزن|المتاح|رصيد|500|server error"


# ------------------------------------------------------------------ collecting
def _runs():
    from web import insights
    since = datetime.now() - timedelta(days=MAX_DAYS)
    return [r for r in insights.all_runs() if r["time"] >= since][:400]


def collect():
    """→ (dev issues, tool issues), newest first"""
    from engine.check_runner import load_detail
    from web import explain
    dev, tool, latest, health_new = {}, {}, {}, {}

    def add(store, iid, base, run, extra=None):
        it = store.get(iid)
        t = run["time"].strftime("%Y-%m-%d %H:%M")
        if not it:
            it = store[iid] = {**base, "id": iid, "count": 0, "first": t, "last": t, "run_id": run["run_id"], "runs": []}
        it["count"] += 1
        it["first"] = t
        if len(it["runs"]) < 6:
            it["runs"].append(run["run_id"])
        if extra:
            for k, v in extra.items():
                it.setdefault(k, v)
        return it

    for r in _runs():
        site, key = _site(r), r["key"]
        d = None
        try:
            d = load_detail(r["run_id"]) or {}
        except Exception:
            d = {}
        det = d.get("detail") or {}
        biz = d.get("biz") or {}
        surl = _site_url(r, d)
        handled = False

        # 📚 developer case files
        if key.startswith("bizcases_") and biz.get("cases") is not None:
            handled = True
            screen = biz.get("screen", "")
            for row in det.get("rows") or []:
                c = row.get("cells") or []
                if len(c) < 6:
                    continue
                cid, title, stname, doc, actual, ev = c[:6]
                screen = cid.split("-")[0] if "-" in cid else biz.get("screen", "")
                st = (biz["cases"].get(cid) or {}).get("status", "")
                subj = (site, "case", cid)
                latest.setdefault(subj, st)
                if st == "FAIL":
                    sev = "عالية" if re.search(SEV_WORDS, actual) else "متوسطة"
                    it = add(dev, _id(site, cid, _norm(actual)), {
                        "site": site, "url": _doc_link(surl, screen, (biz["cases"].get(cid) or {}).get("id")),
                        "source": "سيناريوهات المطور", "screen": _screen_name(screen), "severity": sev,
                        "title": f"{cid} — {title}", "details": actual, "evidence": ev, "doc": doc,
                        "steps": f"حالة {cid} من ملف سيناريوهات {_screen_name(screen)} (Given/When/Then في الملف)"}, r)
                    it["fixed"] = latest.get(subj) == "PASS"
                elif st in ("BLOCKED_CAPABILITY", "BLOCKED_DATA"):
                    planned = re.search(r"لسه مش مؤتمتة|المرحلة الجاية", actual)
                    if st == "BLOCKED_CAPABILITY" and planned:
                        continue
                    kind = "بيانات الموقع" if st == "BLOCKED_DATA" else "خطوة الأداة مقدرتش تعملها"
                    it = add(tool, _id(site, cid, st, _norm(actual)), {
                        "site": site, "kind": kind, "test": f"{cid} — {title}", "title": actual[:200], "message": actual,
                        "severity": "منخفضة" if st == "BLOCKED_DATA" else "عالية"}, r)
                    it["fixed"] = latest.get(subj) == "PASS"
                # notes found while the case ran (even when it passed)
                for note in re.findall(r"(ملاحظة: [^·]+|تنبيه بيانات: [^·]+|اتمسح \d+ سطر فاضي[^·]+)", ev or ""):
                    add(dev, _id(site, screen, _norm(note)), {
                        "site": site, "url": _doc_link(surl, screen, (biz["cases"].get(cid) or {}).get("id")),
                        "source": "ملاحظة أثناء التنفيذ", "screen": _screen_name(screen), "severity": "منخفضة",
                        "title": note.strip()[:160], "details": note.strip(), "evidence": f"{cid} · مستند {doc}", "doc": doc,
                        "steps": f"اتلاحظت وقت تنفيذ {cid}"}, r)

        # 📋 the 19-step sales invoice form
        elif key == "biz_sales_invoice" and biz.get("steps"):
            handled = True
            try:
                from engine.biz_sales_invoice import STEPS
                names = {n: t for n, _g, t, _e in STEPS}
            except Exception:
                names = {}
            for n, v in biz["steps"].items():
                st, lines = (v[0], v[1]) if isinstance(v, (list, tuple)) else (v, [])
                subj = (site, "biz19", n)
                latest.setdefault(subj, st)
                if st == "fail":
                    txt = " · ".join(lines)
                    it = add(dev, _id(site, "biz19", n, _norm(txt)), {
                        "site": site, "url": (surl + "/SalesInvoice/AddEdit/" + str((biz.get("facts") or {}).get("invoice_id") or "")).rstrip("/") if surl else "",
                        "source": "نموذج فاتورة البيع (19 بند)", "screen": "فاتورة البيع", "severity": "عالية" if re.search(SEV_WORDS, txt) else "متوسطة",
                        "title": f"بند {n} — {names.get(n, '')}", "details": txt, "evidence": (biz.get("facts") or {}).get("invoice_no", ""),
                        "doc": (biz.get("facts") or {}).get("invoice_no", ""), "steps": "نموذج المطور — SalesInvoice-Test-Scenario"}, r)
                    it["fixed"] = latest.get(subj) == "ok"

        # 🩺 screens that don't open
        elif det.get("title", "").startswith("🩺"):
            handled = True
            new = site not in health_new
            broken = set()
            for row in det.get("rows") or []:
                c = row.get("cells") or []
                if row.get("ok") is False and len(c) >= 5:
                    url = c[3]
                    broken.add(url)
                    it = add(dev, _id(site, "health", url, _norm(c[4])), {
                        "site": site, "url": (c[3] if str(c[3]).startswith("http") else (surl + "/" + str(c[3]).lstrip("/")) if surl else ""),
                        "source": "صحة النظام", "screen": f"{c[1]} / {c[2]}", "severity": "عالية" if re.search(r"500|خطأ", c[4]) else "متوسطة",
                        "title": f"الشاشة مش بتفتح: {c[2]}", "details": c[4], "evidence": url, "doc": "", "steps": f"افتح {url}"}, r)
                    if not new:
                        it["fixed"] = url not in health_new.get(site, set())
            if new:
                health_new[site] = broken

        # ⚖️ / 🔌 / 📊 rows that failed
        elif det.get("rows") and re.match(r"^(⚖️|🔌|📊)", det.get("title", "")):
            handled = True
            src = det.get("title", "")[:40]
            for row in det["rows"]:
                if row.get("ok") is not False:
                    continue
                c = [str(x) for x in (row.get("cells") or [])]
                txt = " · ".join(c)
                add(dev, _id(site, key, _norm(txt)), {
                    "site": site, "source": src, "screen": c[0] if c else src, "severity": "عالية" if "⚖️" in src else "متوسطة",
                    "title": (c[1] if len(c) > 1 else txt)[:160], "details": txt, "evidence": "", "doc": "", "steps": src}, r)

        # anything else that failed → ERP or tool, by the explanation rules
        if not handled and not r["passed"]:
            msg = r.get("message") or ""
            subj = (site, "test", key)
            latest.setdefault(subj, "pass" if r["passed"] else "fail")
            ex = explain.explain(msg) or {}
            kind = ex.get("kind", "unknown")
            crash = re.search(r"Traceback|Error\b|Exception|المحرك وقف|NoSuchElement|StaleElement|JavascriptException|KeyError|TypeError|AttributeError", msg)
            if kind in ("bug", "data") and not crash:
                it = add(dev, _id(site, key, _norm(msg)), {
                    "site": site, "source": ex.get("kind_label", "اختبار"), "screen": r["name"], "severity": "عالية" if kind == "bug" else "متوسطة",
                    "title": ex.get("title") or msg.splitlines()[0][:160], "details": msg[:1500], "evidence": ex.get("why", ""), "doc": "",
                    "steps": f"الاختبار «{r['name']}»"}, r)
            else:
                it = add(tool, _id(site, key, _norm(msg)), {
                    "site": site, "kind": ex.get("kind_label") or ("المحرك وقف" if crash else "مش واضح"), "test": r["name"],
                    "title": (ex.get("title") or msg.splitlines()[0] if msg else "فشل من غير رسالة")[:200], "message": msg[:2500],
                    "severity": "عالية" if crash else "متوسطة", "fix": ex.get("fix", "")}, r)
            it["fixed"] = latest.get(subj) == "pass"
        elif not handled and r["passed"]:
            latest.setdefault((site, "test", key), "pass")

    for k in __import__("engine.known_issues", fromlist=["KNOWN"]).KNOWN:
        dev.setdefault(k["id"], {**k, "url": k.get("url") or ("https://" + k["site"] + k.get("path", "")), "source": "اتلاحظت يدويًا", "doc": "", "count": 1, "first": k["found"], "last": k["found"], "run_id": "", "runs": []})
    for m in _load("support_manual.json", []):
        dev.setdefault(m["id"], {**m, "source": "اتضافت يدويًا", "count": 1, "first": m.get("found", ""), "last": m.get("found", ""), "run_id": "", "runs": []})
    return _finish(dev, "dev"), _finish(tool, "tool")


def _finish(store, kind):
    st = _load("support_status.json", {})
    out = []
    for it in store.values():
        s = st.get(it["id"]) or {}
        it["status"] = s.get("status") or ("اتصلح" if it.get("fixed") and kind == "dev" else "جديد")
        it["note"] = s.get("note", "")
        it["ticket"] = s.get("ticket")
        it["auto_fixed"] = bool(it.get("fixed"))
        out.append(it)
    out.sort(key=lambda x: x.get("last", ""), reverse=True)
    out.sort(key=lambda x: (x["status"] in ("اتصلح", "مش مشكلة"), SEV_ORDER.get(x.get("severity"), 3)))
    for i, it in enumerate(out, 1):
        it["n"] = i
    return out


def _screen_name(code):
    try:
        from engine.biz_cases import NAMES
        return NAMES.get(code, code)
    except Exception:
        return code


def _log_tail(run_id, n=40):
    from web import data_helper
    lines = [x["text"] for x in data_helper.read_run_log(run_id, 4000) if x["text"].strip()]
    err = [i for i, x in enumerate(lines) if re.search(r"Traceback|ERROR|Error|❌|Exception", x)]
    if err:
        a = max(0, err[-1] - n + 10)
        return lines[a:a + n]
    return lines[-n:]


# ------------------------------------------------------------------ exports (approved design)
def _filter(items, args):
    ids = [x for x in (args.get("ids") or "").split(",") if x]
    if ids:
        return [i for i in items if i["id"] in ids]
    q, site, sev, stt = args.get("q", "").strip(), args.get("site", ""), args.get("sev", ""), args.get("status", "")
    out = []
    for i in items:
        if site and i.get("site") != site:
            continue
        if sev and i.get("severity") != sev:
            continue
        if stt == "open" and i["status"] in ("اتصلح", "مش مشكلة"):
            continue
        if stt and stt != "open" and i["status"] != stt:
            continue
        if q and q not in json.dumps(i, ensure_ascii=False):
            continue
        out.append(i)
    return out


COLS = {
    "dev": [("n", "#", 6), ("severity", "الخطورة", 12), ("site", "الموقع", 16), ("screen", "الشاشة", 16), ("title", "المشكلة", 32),
            ("details", "التفاصيل", 50), ("steps", "خطوات التكرار", 28), ("evidence", "الدليل / المستند", 28),
            ("count", "مرات", 8), ("last", "آخر ظهور", 17), ("status", "الحالة", 14), ("note", "ملاحظات", 22)],
    "tool": [("n", "#", 6), ("severity", "الخطورة", 12), ("kind", "النوع", 16), ("site", "الموقع", 18), ("test", "الاختبار", 26),
             ("title", "المشكلة", 36), ("message", "الرسالة", 55), ("count", "مرات", 6), ("last", "آخر ظهور", 15), ("run_id", "آخر تشغيلة", 22),
             ("status", "الحالة", 12), ("note", "ملاحظات", 22)],
}
TITLES = {"dev": ("مشاكل الـ ERP — لفريق التطوير", "ERP issues — for developers"), "tool": ("مشاكل أداة الاختبار", "Test tool issues")}


def _company():
    try:
        from web import settings_helper
        c = settings_helper.load_site_config()
        return c.get("company_name") or c.get("site_name_ar") or "أتمتة اختبارات ERP"
    except Exception:
        return "أتمتة اختبارات ERP"


def export_xlsx(kind, items, filt_text):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    wb = Workbook()
    ws = wb.active
    ws.title = "المشاكل"
    ws.sheet_view.rightToLeft = True
    cols = COLS[kind]
    ar, en = TITLES[kind]
    ws.append([_company()])
    ws.append([ar])
    ws.append([en])
    ws.append([f"المستخدم: {(auth.current_user() or {}).get('username', '')}   ·   تاريخ الطباعة: {datetime.now():%Y-%m-%d %H:%M}   ·   {filt_text}"])
    ws.append([])
    for r, (sz, color, bold) in zip((1, 2, 3, 4), ((12, "0A5654", True), (16, "1C2B2A", True), (11, "0F7C7A", False), (10, "6B7B7A", False))):
        ws.cell(r, 1).font = Font(name="Microsoft Sans Serif", size=sz, bold=bold, color=color)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=len(cols))
        ws.cell(r, 1).alignment = Alignment(horizontal="center" if r in (2, 3) else "right")
    ws.append([c[1] for c in cols])
    hr = ws.max_row
    thin = Side(style="thin", color="D5E2E1")
    for i, (_, _, w) in enumerate(cols, 1):
        c = ws.cell(hr, i)
        c.fill = PatternFill("solid", fgColor="0F7C7A")
        c.font = Font(name="Microsoft Sans Serif", bold=True, color="FFFFFF")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[c.column_letter].width = w
    for it in items:
        ws.append([("—" if it.get(k) in (None, "") else it.get(k)) for k, _, _ in cols])
        for i in range(1, len(cols) + 1):
            c = ws.cell(ws.max_row, i)
            c.font = Font(name="Microsoft Sans Serif", size=10, color="1C2B2A",
                          bold=(cols[i - 1][0] == "severity" and it.get("severity") == "عالية"))
            c.alignment = Alignment(horizontal="center" if cols[i - 1][0] in ("n", "count", "severity", "last", "status") else "right",
                                    vertical="top", wrap_text=True)
            c.border = Border(bottom=thin)
            if cols[i - 1][0] == "severity" and it.get("severity") == "عالية":
                c.font = Font(name="Microsoft Sans Serif", size=10, bold=True, color="C62828")
    ws.freeze_panes = ws.cell(hr + 1, 1)
    ws.print_options.horizontalCentered = True
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = f"{hr}:{hr}"
    ws.oddFooter.center.text = "صفحة &P من &N"
    bio = io.BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio


def export_docx(kind, items, filt_text):
    import docx
    from docx.enum.section import WD_ORIENT
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor
    TEAL, DARK, GREY, TXT = RGBColor(0x0F, 0x7C, 0x7A), RGBColor(0x0A, 0x56, 0x54), RGBColor(0x6B, 0x7B, 0x7A), RGBColor(0x1C, 0x2B, 0x2A)
    d = docx.Document()
    sec = d.sections[0]
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)
    for m in ("left_margin", "right_margin"):
        setattr(sec, m, Cm(1.3))
    sec.top_margin = sec.bottom_margin = Cm(1.2)
    st = d.styles["Normal"]
    st.font.name = "Microsoft Sans Serif"
    st.font.size = Pt(9)
    st.element.rPr.rFonts.set(qn("w:cs"), "Microsoft Sans Serif")

    def rtl(p):
        pPr = p._p.get_or_add_pPr()
        b = OxmlElement("w:bidi")
        pPr.append(b)
        return p

    def run(p, text, size=9, bold=False, color=TXT):
        r = p.add_run(text)
        r.font.size, r.font.bold, r.font.color.rgb = Pt(size), bold, color
        rPr = r._r.get_or_add_rPr()
        rtl_el = OxmlElement("w:rtl")
        rPr.append(rtl_el)
        cs = OxmlElement("w:szCs")
        cs.set(qn("w:val"), str(int(size * 2)))
        rPr.append(cs)
        if bold:
            rPr.append(OxmlElement("w:bCs"))
        return r

    def shade(cell, hexcolor):
        tcPr = cell._tc.get_or_add_tcPr()
        s = OxmlElement("w:shd")
        s.set(qn("w:val"), "clear")
        s.set(qn("w:color"), "auto")
        s.set(qn("w:fill"), hexcolor)
        tcPr.append(s)

    def borders(table, inside_h="D5E2E1"):
        tblPr = table._tbl.tblPr
        b = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideV"):
            e = OxmlElement(f"w:{edge}")
            e.set(qn("w:val"), "nil")
            b.append(e)
        e = OxmlElement("w:insideH")
        e.set(qn("w:val"), "single" if inside_h else "nil")
        e.set(qn("w:sz"), "4")
        e.set(qn("w:color"), inside_h or "auto")
        b.append(e)
        tblPr.append(b)
        bv = OxmlElement("w:bidiVisual")
        tblPr.append(bv)

    ar, en = TITLES[kind]
    # header: 3 zones (right company · center title · left user/date)
    h = d.add_table(rows=1, cols=3)
    borders(h, None)
    h.alignment = WD_TABLE_ALIGNMENT.CENTER
    c0, c1, c2 = h.rows[0].cells
    h.autofit = False
    for i, wcm in enumerate((7.5, 12.1, 7.5)):
        h.columns[i].width = Cm(wcm)
        h.rows[0].cells[i].width = Cm(wcm)
    p = rtl(c0.paragraphs[0])
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run(p, _company(), 12, True, DARK)
    p = rtl(c1.paragraphs[0])
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run(p, ar, 16, True, TXT)
    p = rtl(c1.add_paragraph())
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run(p, en, 11, False, TEAL)
    p = rtl(c2.paragraphs[0])
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run(p, "المستخدم: ", 9, False, GREY)
    run(p, (auth.current_user() or {}).get("username", "") or "—", 9, True)
    p = rtl(c2.add_paragraph())
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run(p, "تاريخ الطباعة: ", 9, False, GREY)
    run(p, datetime.now().strftime("%Y-%m-%d %H:%M"), 9, True)
    # teal divider
    p = d.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    pb = OxmlElement("w:pBdr")
    bt = OxmlElement("w:bottom")
    bt.set(qn("w:val"), "single")
    bt.set(qn("w:sz"), "18")
    bt.set(qn("w:color"), "0F7C7A")
    pb.append(bt)
    pPr.append(pb)
    # filter strip
    f = d.add_table(rows=1, cols=1)
    borders(f, None)
    shade(f.rows[0].cells[0], "E7F3F2")
    p = rtl(f.rows[0].cells[0].paragraphs[0])
    n_open = sum(1 for i in items if i["status"] not in ("اتصلح", "مش مشكلة"))
    n_high = sum(1 for i in items if i.get("severity") == "عالية")
    run(p, "الفلتر: ", 9, False, GREY)
    run(p, filt_text or "الكل", 9, True)
    run(p, "    ·    العدد: ", 9, False, GREY)
    run(p, f"{len(items)} (مفتوح {n_open} · خطورة عالية {n_high})", 9, True)
    d.add_paragraph()
    # the table
    cols = [c for c in COLS[kind] if c[0] not in ("note",)]
    if kind == "dev":
        cols = [c for c in cols if c[0] not in ("site",)] if len({i.get("site") for i in items}) <= 1 else cols
    t = d.add_table(rows=1, cols=len(cols))
    borders(t)
    t.autofit = False
    tot = sum(c[2] for c in cols)
    for i, (k, lbl, w) in enumerate(cols):
        t.columns[i].width = Cm(27.1 * w / tot)
    for i, (k, lbl, w) in enumerate(cols):
        cell = t.rows[0].cells[i]
        cell.width = Cm(27.1 * w / tot)
        shade(cell, "0F7C7A")
        p = rtl(cell.paragraphs[0])
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run(p, lbl, 9, True, RGBColor(0xFF, 0xFF, 0xFF))
    trPr = t.rows[0]._tr.get_or_add_trPr()
    trPr.append(OxmlElement("w:tblHeader"))
    for it in items:
        cells = t.add_row().cells
        for i, (k, lbl, w) in enumerate(cols):
            cells[i].width = Cm(27.1 * w / tot)
            v = it.get(k)
            v = "—" if v in (None, "") else str(v)
            if k == "message":
                v = v[:900]
            p = rtl(cells[i].paragraphs[0])
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if k in ("n", "count", "severity", "last", "status") else WD_ALIGN_PARAGRAPH.RIGHT
            run(p, v, 8.5, k in ("title", "severity") , RGBColor(0xC6, 0x28, 0x28) if (k == "severity" and v == "عالية") else TXT)
    # tool: the log of each problem (to send for fixing)
    if kind == "tool":
        for it in items:
            if not it.get("run_id"):
                continue
            p = rtl(d.add_paragraph())
            run(p, f"#{it['n']} — {it['title'][:120]}", 10, True, DARK)
            p = rtl(d.add_paragraph())
            run(p, f"التشغيلة {it['run_id']} · {it.get('test', '')} · {it.get('site', '')}", 8.5, False, GREY)
            for line in _log_tail(it["run_id"], 25):
                q = d.add_paragraph()
                r = q.add_run(line[:220])
                r.font.size = Pt(7.5)
                r.font.name = "Consolas"
    # footer: صفحة X من Y
    fp = rtl(sec.footer.paragraphs[0])
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def field(p, code):
        r = p.add_run()
        b = OxmlElement("w:fldChar")
        b.set(qn("w:fldCharType"), "begin")
        r._r.append(b)
        r2 = p.add_run()
        it = OxmlElement("w:instrText")
        it.set(qn("xml:space"), "preserve")
        it.text = code
        r2._r.append(it)
        r3 = p.add_run()
        e = OxmlElement("w:fldChar")
        e.set(qn("w:fldCharType"), "end")
        r3._r.append(e)
    run(fp, "صفحة ", 9, False, GREY)
    field(fp, "PAGE")
    run(fp, " من ", 9, False, GREY)
    field(fp, "NUMPAGES")
    bio = io.BytesIO()
    d.save(bio)
    bio.seek(0)
    return bio


def bundle(kind, items):
    """plain text to paste in a chat / message"""
    out = [f"# {TITLES[kind][0]} — {datetime.now():%Y-%m-%d %H:%M} ({len(items)})", ""]
    for it in items:
        if kind == "dev":
            out += [f"## {it['n']}) [{it.get('severity')}] {it.get('screen')} — {it['title']}",
                    f"- الموقع: {it.get('site')} · مرات: {it.get('count')} · آخر ظهور: {it.get('last')} · الحالة: {it['status']}",
                    f"- التفاصيل: {it.get('details') or '—'}", f"- خطوات التكرار: {it.get('steps') or '—'}",
                    f"- الدليل: {it.get('evidence') or '—'}" + (f" · المستند {it['doc']}" if it.get("doc") else ""), ""]
        else:
            out += [f"## {it['n']}) [{it.get('kind')}] {it['title']}",
                    f"- الاختبار: {it.get('test')} · الموقع: {it.get('site')} · مرات: {it.get('count')} · آخر ظهور: {it.get('last')} · التشغيلة: {it.get('run_id')}",
                    "- الرسالة:", "```", (it.get("message") or "")[:2000], "```"]
            if it.get("run_id"):
                out += ["- آخر اللوج:", "```", *_log_tail(it["run_id"], 30), "```"]
            out.append("")
    return "\n".join(out)


# ------------------------------------------------------------------ routes
@bp.route("/dev-support")
@auth.login_required
def dev_page():
    return render_template("support.html", kind="dev", statuses=DEV_STATUS)


@bp.route("/tool-support")
@auth.login_required
def tool_page():
    return render_template("support.html", kind="tool", statuses=TOOL_STATUS)


@bp.route("/api/support/<kind>")
@auth.login_required
def api_list(kind):
    dev, tool = collect()
    items = dev if kind == "dev" else tool
    sites = sorted({i.get("site") for i in items if i.get("site")})
    return jsonify({"success": True, "items": items, "sites": sites, "statuses": DEV_STATUS if kind == "dev" else TOOL_STATUS})


@bp.route("/api/support/<kind>/log/<run_id>")
@auth.login_required
def api_log(kind, run_id):
    if not re.match(r"^[\w.-]+$", run_id):
        return jsonify({"success": False}), 400
    return jsonify({"success": True, "lines": _log_tail(run_id, 60)})


@bp.route("/api/support/status", methods=["POST"])
@auth.login_required
def api_status():
    d = request.get_json(silent=True) or {}
    st = _load("support_status.json", {})
    for iid in (d.get("ids") or [d.get("id")]):
        if not iid:
            continue
        cur = st.get(iid, {})
        if "status" in d:
            cur["status"] = d["status"]
        if "note" in d:
            cur["note"] = str(d["note"])[:1000]
        cur["by"] = (auth.current_user() or {}).get("username", "")
        cur["at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        st[iid] = cur
    _save("support_status.json", st)
    return jsonify({"success": True})


@bp.route("/api/support/dev/add", methods=["POST"])
@auth.login_required
def api_add():
    d = request.get_json(silent=True) or {}
    if not str(d.get("title") or "").strip():
        return jsonify({"success": False, "error": "اكتب عنوان المشكلة"}), 400
    items = _load("support_manual.json", [])
    it = {k: str(d.get(k) or "").strip()[:3000] for k in ("site", "screen", "title", "details", "steps", "evidence")}
    it.update({"id": "m-" + _id(datetime.now().isoformat(), it["title"]), "severity": d.get("severity") if d.get("severity") in SEV_ORDER else "متوسطة",
               "found": datetime.now().strftime("%Y-%m-%d"), "doc": ""})
    items.append(it)
    _save("support_manual.json", items)
    return jsonify({"success": True, "id": it["id"]})


@bp.route("/api/support/<kind>/export")
@auth.login_required
def api_export(kind):
    dev, tool = collect()
    items = _filter(dev if kind == "dev" else tool, request.args)
    a = request.args
    filt = " · ".join(x for x in [a.get("site") and f"الموقع {a['site']}", a.get("sev") and f"الخطورة {a['sev']}",
                                   a.get("status") == "open" and "المفتوحة بس" or (a.get("status") and f"الحالة {a['status']}"),
                                   a.get("q") and f"بحث «{a['q']}»", a.get("ids") and "المحدد"] if x) or "الكل"
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    name = ("ERP_issues" if kind == "dev" else "Tool_issues") + "_" + stamp
    fmt = a.get("fmt", "docx")
    if fmt == "xlsx":
        return send_file(export_xlsx(kind, items, filt), as_attachment=True, download_name=name + ".xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if fmt == "txt":
        return send_file(io.BytesIO(bundle(kind, items).encode("utf-8")), as_attachment=True, download_name=name + ".md", mimetype="text/markdown")
    return send_file(export_docx(kind, items, filt), as_attachment=True, download_name=name + ".docx",
                     mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@bp.route("/api/support/<kind>/bundle")
@auth.login_required
def api_bundle(kind):
    dev, tool = collect()
    items = _filter(dev if kind == "dev" else tool, request.args)
    return jsonify({"success": True, "text": bundle(kind, items)})


# ------------------------------------------------------------------ 🎫 tickets on the main ERP
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _attachments(it):
    """the latest Word result report of the run the problem came from + a one-problem Word sheet"""
    out = []
    if it.get("run_id"):
        try:
            from engine.check_runner import load_detail
            from pathlib import Path
            w = ((load_detail(it["run_id"]) or {}).get("biz") or {}).get("word") or ""
            f = Path(w)
            if w and f.exists() and f.resolve().is_relative_to(paths.RESULTS_DIR.resolve()):
                out.append((f"Test_result_{it['run_id']}.docx", f.read_bytes(), DOCX))
        except Exception:
            pass
    try:
        out.append((f"ERP_issue_{it['id']}.docx", export_docx("dev", [{**it, "n": 1}], "مشكلة واحدة").getvalue(), DOCX))
    except Exception:
        pass
    return out


@bp.route("/api/support/tickets/config", methods=["GET", "POST"])
@auth.login_required
def api_tickets_config():
    from web import tickets
    if request.method == "POST":
        return jsonify({"success": True, "config": tickets.save(request.get_json(silent=True) or {})})
    return jsonify({"success": True, "config": tickets.public()})


@bp.route("/api/support/tickets/create", methods=["POST"])
@auth.login_required
def api_tickets_create():
    from web import tickets
    d = request.get_json(silent=True) or {}
    ids = [x for x in (d.get("ids") or []) if x][:150]
    if not ids:
        return jsonify({"success": False, "error": "حدد مشكلة واحدة على الأقل"}), 400
    dev, _tool = collect()
    items = {i["id"]: i for i in dev}
    st = _load("support_status.json", {})
    out = []
    for iid in ids:
        it = items.get(iid)
        if not it:
            out.append({"id": iid, "ok": False, "error": "المشكلة مش موجودة"})
            continue
        if (st.get(iid) or {}).get("ticket") and not d.get("again"):
            out.append({"id": iid, "ok": False, "error": "ليها تذكرة قبل كده", "ticket": st[iid]["ticket"]})
            continue
        link = (request.host_url.rstrip("/") + f"/reports/{it['run_id']}") if it.get("run_id") else ""
        try:
            t = tickets.create(it, link, _attachments(it))
        except tickets.TicketError as e:
            out.append({"id": iid, "ok": False, "error": str(e)})
            if "تسجيل الدخول" in str(e) or "اكتب يوزر" in str(e) or "مش بيرد" in str(e):
                break
            continue
        except Exception as e:
            out.append({"id": iid, "ok": False, "error": f"خطأ: {str(e)[:200]}"})
            continue
        cur = st.get(iid, {})
        t["by"] = (auth.current_user() or {}).get("username", "")
        cur["ticket"] = t
        if cur.get("status") in (None, "", "جديد"):
            cur["status"] = "اتبلغ للمطور"
        st[iid] = cur
        _save("support_status.json", st)
        out.append({"id": iid, "ok": True, "ticket": t})
    return jsonify({"success": True, "results": out, "made": sum(1 for x in out if x["ok"])})
