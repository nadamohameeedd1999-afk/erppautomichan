"""Fast checks without a browser."""
from engine.flows import evaluate_check, normalize_flows
from engine import screen_config as sc


def test_formulas():
    v = {"الصافي": "350.00", "الضريبة": "52.50", "الإجمالي": "٤٠٢٫٥٠", "الحالة": "مرحل نهائي"}
    r = lambda k: v[k]
    assert evaluate_check("{الضريبة} = {الصافي} * 0.15", r)[0]
    assert evaluate_check("{الإجمالي} = {الصافي} + {الضريبة}", r)[0]
    assert not evaluate_check("{الإجمالي} > 1000", r)[0]
    assert evaluate_check("{الحالة} ~ مرحل", r)[0]


def test_flow_validation():
    flows = normalize_flows([{"name": "x", "after": "__after_save__", "steps": [{"do": "check_print"}]}], ["A"], sc.normalize_field)
    assert flows[0]["steps"][0]["target"] == "طباعة"


def test_smart_values():
    from engine.smart_values import describe
    vat = describe("الرقم الضريبي", "VATNumber")
    assert len(vat) == 15 and vat[0] == "3" and vat[-1] == "3"
    assert len(describe("الرمز البريدي", "PostalCode")) == 5
    assert describe("الجوال", "Mobile").startswith("05")
    assert describe("صحيح", "X") is None                       # «حي» inside another word doesn't count


def test_failure_explanations():
    from web.explain import explain
    assert explain("الحسبة مش مظبوطة: 52.00 = 52.50")["kind"] == "bug"
    assert explain("رسالة خطأ: يجب ان تختار الملفات اولا")["kind"] == "setup"
    assert explain("القيمة المطلوبة 'x' مش موجودة (بالظبط)")["kind"] == "data"
    assert explain("InvalidSessionIdException: session deleted")["kind"] == "env"
    assert explain("كل حاجة تمام") is None


def test_queue_same_screen_waits(monkeypatch):
    from web.queue_manager import QueueManager
    qm = QueueManager()
    monkeypatch.setattr(QueueManager, "workers", staticmethod(lambda: 2))
    started = []
    monkeypatch.setattr(QueueManager, "_execute", lambda self, t: started.append(t["task_id"]))
    S = "tests/smoke/test_screen_smoke.py::test_screen_opens"
    qm.add("a", f"{S}[sales_invoice]", "a", extra={"site": "s1"})
    qm.add("b", f"{S}[sales_invoice]", "b", extra={"site": "s2"})          # same screen -> waits
    qm.add("d", f"{S}[stock]", "d", extra={"site": "s1"})                  # same site -> waits (one ERP session per user)
    qm.add("c", f"{S}[cash_receipt]", "c", extra={"site": "s2"})
    import time
    time.sleep(0.3)
    assert sorted(qm.running) == ["a", "c"] and [t["task_id"] for t in qm.queue] == ["b", "d"]


def test_reconcile_control_accounts():
    from engine import reconcile as R
    tb = [{"Id": 1, "ParentId": 0, "Code": "1", "ArName": "الأصول", "BalanceDebit": 9, "BalanceCredit": 0},
          {"Id": 3481, "ParentId": 1, "Code": "10102", "ArName": "الذمم المدينة التجارية", "BalanceDebit": 254599.39, "BalanceCredit": 0},
          {"Id": 3482, "ParentId": 3481, "Code": "1010201", "ArName": "العملاء المحليين", "BalanceDebit": 254347.22, "BalanceCredit": 0},
          {"Id": 3621, "ParentId": 1, "Code": "2010303", "ArName": "مخصصات العملاء", "BalanceDebit": 0, "BalanceCredit": 0},
          {"Id": 3551, "ParentId": 2, "Code": "20101", "ArName": "الذمم الدائنة التجارية", "BalanceDebit": 0, "BalanceCredit": 202204.6},
          {"Id": 3552, "ParentId": 3551, "Code": "2010101", "ArName": "الموردين المحليين", "BalanceDebit": 0, "BalanceCredit": 202204.6}]
    res = R.compare(tb, {"customers": ([{"Total": 254599.39}], "", ""),
                         "vendors": ([{"Balance": 253057.5}], "", "")})
    assert res[0][1] is True and "10102" in res[0][2]
    assert res[1][1] is False and "20101" in res[1][2] and "+50,852.90" in res[1][2]
    assert R.compare(tb, {"customers": (None, "", "404")})[0][1] is None


def test_api_check_safe_and_contract():
    from engine import api_check as A
    st = {"speed": [{"name": "أعمار", "xhr": [{"url": "/CustomerInvoiceAgingN/GetSummary?todate=2025-01-01"},
                                              {"url": "/VendorInvoiceAgingN/SaveLayout"}, {"url": "/Home/SetBranch?id=1"},
                                              {"url": "/CustomerInvoiceAgingN/GetSummary?todate=2024-02-02"}]}]}
    eps = A.endpoints({"seeds": False}, st)
    assert [e["url"].split("?")[0] for e in eps] == ["/CustomerInvoiceAgingN/GetSummary"]
    base = {"ms": 100, "json": True, "top": [], "row": ["Total", "customerid"]}
    ok, txt, _ = A.judge(eps[0], {"s": 200, "ms": 90, "json": True, "n": 3, "shape": {"top": [], "row": ["customerid"]}}, base, {})
    assert ok is False and "Total" in txt
    assert A.judge(eps[0], {"s": 200, "ms": 90, "json": True, "n": 3, "shape": {"top": [], "row": ["Total", "customerid"]}}, base, {})[0] is True
    assert A.judge(eps[0], {"s": 500, "err": "x"}, base, {})[0] is False


def test_sod_conflicts():
    from engine import sod
    d = {"users": [{"user": "a", "name": "A", "group": "مالية", "priv": {"الموردين": ["اضافة"]}},
                   {"user": "b", "name": "B", "group": "", "priv": {"فواتير البيع-مبيعات": ["عرض"]}}],
         "roles": [{"name": "مالية", "priv": {"سند الدفع": ["اضافة"]}}]}
    rows, fails = sod.analyse(d)
    assert fails == ["a — A (مالية): إنشاء مورد + الدفع له"]          # user's own right + his group's right
    assert any(r["ok"] is True and r["cells"][0].startswith("b") for r in rows)
    assert sod.analyse(d, {"allow": ["a|vendor_pay"]})[1] == []


def test_journal_check_rows():
    from engine import journal_check as J

    class D:
        def __init__(self, r): self.r = r
        def execute_async_script(self, *a): return self.r
    bad = [{"id": 1, "doc": "151148", "type": "سندات استلام المخازن", "op": "12070", "date": "2026-11-04", "user": "erpadmin",
            "posted": False, "d": 115679.646, "c": 0, "n": 1, "acc": ["1010301001 مخزون خام"], "diff": 115679.65},
           {"id": 2, "doc": "1", "type": "التحويلات النقدية", "op": "320", "date": "2026-10-22", "user": "erpadmin",
            "posted": True, "d": 0, "c": 100, "n": 1, "acc": [], "diff": -100}]
    rows, fails = J.run(D({"ok": True, "lines": 580, "entries": 199, "bad": bad}), "2016-01-01", "2026-12-31")
    assert rows[0]["ok"] is False and "2 قيد من 199" in rows[0]["cells"][2] and "+115,579.65" in rows[0]["cells"][2]
    assert "151148" in rows[1]["cells"][1] and len(fails) == 1
    rows, fails = J.run(D({"ok": True, "lines": 10, "entries": 4, "bad": []}), "a", "b")
    assert rows[0]["ok"] is True and not fails
    assert J.run(D({"s": 404, "err": "x"}), "a", "b")[0][0]["ok"] is None


def test_test_library(tmp_path, monkeypatch):
    from engine import test_library as L
    import config.screens_catalog as SC
    store = {"screens": []}
    monkeypatch.setattr(L, "discovered", lambda: list(store["screens"]))
    monkeypatch.setattr(L, "save_discovered", lambda s: store.update(screens=s))
    monkeypatch.setattr(L, "all_pages", lambda: {"x_inv": {"url": "/SalesInvoice"}, **{s["key"]: {"url": s["url"]} for s in store["screens"]}})
    assert len(L.LIBRARY) == 20 and len({x[0] for x in L.LIBRARY}) == 20
    assert L.ensure_screen("sales_invoice")[0] == "x_inv"                 # already in the project: reused
    sk, it = L.ensure_screen("vendors")
    assert sk == "lib_vendors" and store["screens"][0]["url"] == "/Vendor"
    assert L.ensure_screen("vendors")[0] == "lib_vendors"                 # not added twice
    its = L.items({"x_inv": {"key": "auto_x_inv"}}, {}, ["/SalesInvoice"])
    assert its[0]["test"] == "auto_x_inv" and its[0]["in_menu"] is True


def test_screen_word_picks_option():
    from engine import auto_test as A
    A.set_hint("سند القبض")
    f = A.build_fields([{"id": "ad", "kind": "select", "label": "التوجيهات المحاسبية", "options": ["2 - دفع", "1 - قبض"], "required": True, "visible": True},
                        {"id": "b", "kind": "select", "label": "الفرع", "options": ["01 - الفرع الاول"], "required": True, "visible": True}], "all", "first")[0]
    assert (f[0]["strategy"], f[0]["value"]) == ("fixed", "1 - قبض") and f[1]["strategy"] == "first"
    A.set_hint("")


def test_stubborn_stops_on_business_rule():
    from engine.stubborn import business_rule
    assert business_rule("رسالة خطأ: تم تجاوز الحد الائتماني للعميل") == "حد الائتمان"
    assert business_rule("لا يمكن الحفظ: الحساب (1010201001) طبيعته مدينة، والحركة المسجلة عليه دائنة.") == "طبيعة الحساب"
    assert business_rule("حقول إجبارية لسه فاضية: بناء على") == ""


def test_biz_sales_invoice_expected_and_word(tmp_path, monkeypatch):
    from engine import biz_sales_invoice as B
    e = B.expected([{"qty": 10, "price": 100}, {"qty": 5, "price": 200}], 10, 0.15)
    assert e == {"total": 2000.0, "disc": 200.0, "net": 1800.0, "tax": 270.0, "after": 2070.0}
    e2 = B.expected([{"qty": 12, "price": 100}, {"qty": 5, "price": 200}], 10, 0.15)
    assert (e2["disc"], e2["tax"], e2["after"]) == (220.0, 297.0, 2277.0)
    from config import paths
    monkeypatch.setattr(paths, "RESULTS_DIR", tmp_path)
    run = B.Run({})
    for i in range(1, 20):
        run.steps[f"{i:02d}"] = (B.OK if i < 18 else B.NA, [f"الفعلي: بند {i}"])
    run.facts.update({"invoice_no": "126110024", "invoice_id": "14438", "items": [{"code": "201", "item": "بلك", "qty": 10, "price": 100, "total": 1000},
                                                                                   {"code": "202", "item": "بلك 2", "qty": 5, "price": 200, "total": 1000}]})
    out = B.fill_word(run, {B.OK: 17, B.BAD: 0, B.NA: 2})
    import docx
    d = docx.Document(out)
    txt = "\n".join(c.text for t in d.tables for r in t.rows for c in r.cells)
    assert "126110024" in txt and "بند 7" in txt and "☑ ناجح" in txt and "☑ لم يُختبر" in txt


def test_biz_config():
    from engine import checks as C
    c = C.normalize({"key": "biz_x", "type": "biz", "name_ar": "x", "items": [{"code": "201", "qty": 10, "price": 100}, {"code": "202", "qty": "5", "price": "200"}]})
    assert c["qty_edit"] == 12 and c["discount_pct"] == 10 and c["items"][1]["qty"] == 5
    try:
        C.normalize({"key": "biz_y", "type": "biz", "name_ar": "y", "items": [{"code": "201", "qty": 1, "price": 1}]})
        assert False
    except C.ConfigError:
        pass


def test_biz_cases_catalog_spec_and_word(tmp_path, monkeypatch):
    from engine import biz_cases as B
    from config import paths
    cat = B.catalog()
    assert {"SAL", "PUR", "CRV", "CPV", "SRT", "PRT", "TRF", "COL", "ASM"} <= set(cat)
    assert cat["PUR"]["auto_n"] == 12 and cat["SAL"]["auto_n"] == 12
    c = next(x for x in cat["PUR"]["cases"] if x["id"] == "PUR-006")
    s = B.spec("PUR", c)
    assert (s["pay"], s["tax"], s["net"], s["vat"], s["total"], s["paid"], s["cash"], s["stock"]) == ("MIXED", 15, 1000, 150, 1150, 400, 400, 0)
    a = B.spec("SAL", next(x for x in cat["SAL"]["cases"] if x["id"] == "SAL-007"))
    assert a["auto"] and a["stock"] == -10
    monkeypatch.setattr(paths, "RESULTS_DIR", tmp_path)
    k = B.Case(c)
    k.chk("الحفظ", True, "ok")
    k.doc_id, k.doc_no = "785", "13"
    out = {"PUR-006": k.done(), "PUR-001": B.Case(cat["PUR"]["cases"][0]).done(B.BDATA, "ناقص V1")}
    f = B.fill_word(cat["PUR"], out, "https://x.test")
    import docx
    t = "\n".join(p.text for p in docx.Document(f).paragraphs)
    assert "PUR-006  |  Priority: P0  |  Basis: ACCEPTANCE  |  Status: PASS" in t and "BLOCKED_DATA" in t and "785 / 13" in t


def test_biz_cases_config():
    from engine import checks as C
    c = C.normalize({"key": "bizcases_pur", "type": "bizcases", "screen": "pur", "cases": ["PUR-001", ""]})
    assert c["screen"] == "PUR" and c["cases"] == ["PUR-001"]


def test_biz_site_data_names(tmp_path, monkeypatch):
    from engine import biz_cases as B
    monkeypatch.setattr(B, "_data_file", lambda: tmp_path / "d.json")
    r = B.save_data("https://x.test/", {"D1": "51", "A": "1-1"}, {"D1": "الفرع الأول", "A": "ثوب"}, auto=True)
    assert r["_names"] == {"D1": "الفرع الأول", "A": "ثوب"} and r["_auto"]
    r = B.save_data("https://x.test", {"D1": "51", "A": "2-1"})          # changed by hand → its auto name goes
    assert r["_names"] == {"D1": "الفرع الأول"} and B.load_data("http://x.test")["A"] == "2-1"
    c = __import__("engine.checks", fromlist=["x"]).normalize({"key": "bizcases_data", "type": "bizcases", "screen": "DATA", "discover": True})
    assert c["discover"] is True


def test_biz_result_report(tmp_path, monkeypatch):
    from engine import biz_cases as B, biz_report
    import docx
    cat = B.catalog()["PUR"]
    c = next(x for x in cat["cases"] if x["id"] == "PUR-006")
    k = B.Case(c)
    k.chk("قبل الحفظ", True, "صافي 1,000.00 · ضريبة 150.00 · إجمالي 1,150.00 (المتوقع 1,000.00 / 150.00 / 1,150.00)")
    k.chk("ضريبة القيد", False, "0.00 (المتوقع 150.00)")
    k.journal = [{"je": 9, "acc": "5010101002 المشتريات", "d": 1000, "c": 0}, {"je": 9, "acc": "2010101001 موردين", "d": 0, "c": 1000}]
    k.doc_no, k.doc_id = "13", "785"
    k.evidence = ["ملاحظة: الـ ERP حفظ بس الشاشة ماظهرتش رسالة نجاح"]
    k.done()
    k.plain = B.describe("PUR", c)
    assert k.checks[0][3] == "1,000.00 / 150.00 / 1,150.00" and "المتوقع" not in k.checks[0][2]
    assert k.status == B.FAIL and "ضريبة القيد: 0.00 — المتوقع 150.00" in k.actual
    assert "متعدد (400 نقدي والباقي آجل)" in k.plain
    ok = B.Case(cat["cases"][0]).done(B.BDATA, "ناقص V1")
    f = biz_report.build(cat, {"PUR-006": k, "PUR-001": ok}, {"V1": "831", "_names": {"V1": "النخبة"}}, "https://x.test", "admin",
                         tmp_path / "r.docx", B.SYMBOLS, B.NAMES)
    d = docx.Document(f)
    t = "\n".join(p.text for p in d.paragraphs)
    assert "فيه مشاكل — فشل 1 من 1" in t and "ملخص الحالات" in t
    cells = " ".join(c.text for tb in d.tables for r in tb.rows for c in r.cells)
    assert "✗ مختلف" in cells and "النخبة" in cells and "ناقص V1" in cells


def test_biz_multi_screens_config_and_report(tmp_path):
    from engine import checks as C, biz_cases as B, biz_report
    import docx
    c = C.normalize({"key": "bizcases_multi", "type": "bizcases", "screens": [{"screen": "sal", "cases": ["SAL-001"]}, {"screen": "PUR"}, {"screen": "??"}]})
    assert c["screen"] == "SAL" and [x["screen"] for x in c["screens"]] == ["SAL", "PUR"] and c["screens"][1]["cases"] == []
    cat = B.catalog()
    g = []
    for code, cid in (("SAL", "SAL-001"), ("PUR", "PUR-001")):
        case = next(x for x in cat[code]["cases"] if x["id"] == cid)
        k = B.Case(case)
        k.chk("الحفظ", True, "اتحفظ")
        k.done()
        k.plain = B.describe(code, case)
        g.append((cat[code], {cid: k}))
    f = biz_report.build_many(g, {}, "https://x.test", "a", tmp_path / "m.docx", B.SYMBOLS, B.NAMES)
    t = "\n".join(p.text for p in docx.Document(f).paragraphs)
    assert "النتيجة لكل شاشة" in t and "ملخص الحالات — فاتورة المشتريات" in t and "ناجح — الـ 2 حالة" in t


def test_biz_addons_catalog_and_config():
    from engine import biz_addons as A, checks as C
    cat = {a["key"]: a for a in A.catalog()}
    assert cat["edit"]["default"] and set(cat["edit"]["screens"]) >= {"SAL", "PUR", "SRT", "PRT", "CRV", "CPV"}
    assert cat["overstock"]["screens"] == ["SAL"] and set(cat["discount"]["screens"]) == {"SAL", "PUR"}
    assert "SRT" not in cat["double"]["screens"]
    c = C.normalize({"key": "bizcases_sal", "type": "bizcases", "screen": "SAL", "addons": ["edit", "x", "print"]})
    assert c["addons"] == ["edit", "print"]


def test_tickets_login_and_create(tmp_path, monkeypatch):
    from web import tickets as T
    import requests
    monkeypatch.setattr(T, "_file", lambda: tmp_path / "t.json")
    monkeypatch.setattr("utils.secret_box.encrypt", lambda v: "enc:" + v[::-1])
    monkeypatch.setattr("utils.secret_box.decrypt", lambda v: v[4:][::-1] if str(v).startswith("enc:") else v)
    assert T.save({"username": "FSTester", "password": "pw-secret"})["has_password"]
    assert "pw-secret" not in (tmp_path / "t.json").read_text()
    sent = {}

    class R:
        def __init__(self, url, text="", js=None, status=200, headers=None):
            self.url, self.text, self._js, self.status_code, self.headers = url, text, js, status, headers or {}

        def json(self):
            return self._js

    class S:
        headers = {}

        def get(self, url, params=None, timeout=None):
            if "SearchSystemPages" in url:
                return R(url, js={"results": [{"id": 2085, "code": "CashReceiptVoucherDetails_Report"}, {"id": 22, "code": "CashReceiptVoucher"}]})
            if "GetLoginData" in url:
                return R(url, js={"success": True, "deptId": "4", "activityId": "1"})
            if "GetBranches" in url:
                return R(url, js={"isok": 1, "data": [{"code": "4"}]})
            return R(url, '<input name="__RequestVerificationToken" type="hidden" value="TOK123" />')

        def post(self, url, data=None, files=None, timeout=None, allow_redirects=True):
            if "Login" in url:
                sent["login"] = data
                return R("https://nq-ts.premiumasp.net/Tickets/Create", "<form>")
            sent["ticket"] = dict((k, v[1]) for k, v in files if k != "Attachments")
            sent["files"] = [v[0] for k, v in files if k == "Attachments"]
            return R(url, status=302, headers={"Location": "/Tickets/Details/991"})
    monkeypatch.setattr(requests, "Session", S)
    it = {"title": "سند القبض بيترفض", "screen": "سند القبض", "severity": "عالية", "details": "x", "steps": "افتح /CashReceiptVoucher/AddEdit",
          "evidence": "", "site": "erp test", "url": "https://test-site-nq.premiumasp.net/CashReceiptVoucher/AddEdit/55", "count": 1, "last": "2026-11-11"}
    t = T.create(it, "https://dash/reports/r1", [("r.docx", b"PK..", "application/x")])
    assert t["ok"] and t["id"] == "991" and t["url"].endswith("/Tickets/Details/991")
    assert sent["login"]["act"] == "1" and sent["login"]["brn"] == "4" and sent["login"]["password"] == "pw-secret"
    tk = sent["ticket"]
    assert tk["__RequestVerificationToken"] == "TOK123" and tk["Priority"] == "2" and tk["Title"].startswith("[اختبار آلي] سند القبض")
    assert tk["SystemPageId"] == "22"
    assert tk["PageUrl"] == "https://test-site-nq.premiumasp.net/CashReceiptVoucher/AddEdit/55" and "https://dash/reports/r1" in tk["Description"]
    assert sent["files"] == ["r.docx"]
    assert T.page_url({"site": "erp test", "url": "", "steps": "Given/When/Then"}) == ""


def test_ticket_pdf_html():
    from web import pdf_reports as P
    h = P.issue_html({"title": "سند القبض بيترفض", "screen": "سند القبض", "severity": "عالية", "url": "https://x.test/CashReceiptVoucher/AddEdit", "details": "<b>x</b>"}, "admin")
    assert "href='https://x.test/CashReceiptVoucher/AddEdit'" in h and "&lt;b&gt;x&lt;/b&gt;" in h and "#0F7C7A" in h
    d = {"biz": {"screens": ["SAL"], "cases": {"SAL-001": {"status": "FAIL", "plain": "فاتورة", "checks": [["ضريبة القيد", False, "0.00", "150.00"]], "journal": [], "evidence": []}}}}
    r = P.run_report_html(d, "run_1", "admin")
    assert "فشل 1 من 1" in r and "✗ مختلف" in r and "المتوقع 150.00" in r


def _xlsx_b64(rows):
    import base64, io
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return base64.b64encode(b.getvalue()).decode()


def test_report_compare_analyze_and_compare(tmp_path, monkeypatch):
    import base64, json
    from engine import report_compare as R
    from config import paths
    csv_txt = (";;;;تقرير كارت صنف;;xrLabel2;;\r\n;;11 November 2026;; : التاريخ;;1/1;; : عدد الصفحات;;1-1 - ثوب;; : الصنف\r\n"
               "المخزن;قيمة الرصيد;;الرصيد ;;صادر ;;الوارد ;;نوع المستند;;التاريخ\r\n"
               "-مخزون خام ;0;;1,000.0000;;0.000;;1000.000;;سند استلام;;08/01/2026\r\n"
               "-مخزون خام ;0;;200.0000;;800.000;;0.000;;سند صرف;;15/01/2026\r\n"
               "-مخزون خام ;0;;195.0000;;.000;;0.000;;سند صرف;;19/10/2026\r\n")
    hdr = ["xrTableCell1", "Warehouse", "BalanceQty", "OutgoingQty", "IncomingQty", "MovementType"]
    body = [["م", "م", 1000.0, 0.0, 1000.0, "استلام"], ["م", "م", 200.0, 800.0, 0.0, "صرف"], ["م", "م", 195.0, 5.0, 0.0, "صرف"], ["م", "م", 243.0, 2.0, 50.0, "استلام"]]
    a = R.analyze(base64.b64encode(csv_txt.encode()).decode(), _xlsx_b64([hdr] + body), {"Itemid": "1-1 - ثوب"})
    assert "تقرير كارت صنف" in a["labels"] and "الرصيد" in a["labels"] and "1-1 - ثوب" not in a["labels"]
    assert a["controls"] == ["xrLabel2"] and a["fields"] == ["Warehouse", "BalanceQty", "OutgoingQty", "IncomingQty", "MovementType"]
    assert a["rule"]["found"] and not a["rule"]["bad_rows"] and a["last_balance"] == 243.0 and a["rows_n"] == 3
    assert any("من غير صفر" in f for f in a["formats"]) and a["sort"] == "تصاعدي بالتاريخ"
    body_b = [r[:] for r in body]
    body_b[2][2] = 190.0                      # client: a wrong running balance
    csv_b = csv_txt.replace("الوارد", "وارد").replace("15/01/2026", "20/10/2026")
    b = R.analyze(base64.b64encode(csv_b.encode()).decode(), _xlsx_b64([hdr[:-1] + ["Type"]] + body_b), {})
    monkeypatch.setattr(paths, "STATE_DIR", tmp_path)
    monkeypatch.setattr(paths, "SETTINGS_DIR", tmp_path)
    P = R.ITEMCARD
    par = lambda fx: [{"path": "Itemid", "type": "System.Int32", "label": "الصنف", "visible": True, "has_lookups": True, "def": ""},
                      {"path": "DisplayMethod", "type": "System.Int32", "label": "", "visible": True, "has_lookups": True, "def": "0", "fixed": fx}]
    for url, x, fx, fp in (("https://t.test", a, [["0", "تفصيلي"], ["1", "مجمع"]], {"dx": "23.2.3", "reportUrl": "ItemCard", "scripts": ["/Scripts/a.js?v=1"]}),
                           ("https://c.test", b, [["0", "تفصيلي"], ["1", "إجمالي"]], {"dx": "23.2.3", "reportUrl": "ItemCard", "scripts": ["/Scripts/a.js?v=2"]})):
        snap = {"status": "ok", "url": url, "site": url[8:], "at": "now", "params": par(fx), "fp": fp, **x}
        snap["stock"] = x["last_balance"]
        R._write(R._snap_file(P, url), snap)
    R._write(R._cat_file("https://t.test"), {"at": "now", "reports": [{"path": P, "name": "كارت صنف"}, {"path": "/Report/X", "name": "x"}]})
    R._write(R._cat_file("https://c.test"), {"at": "now", "reports": [{"path": P, "name": "كارت صنف"}]})
    c = R.compare(P, "https://t.test", "https://c.test")
    rows = {r["item"]: r for r in c["rows"]}
    assert c["ready"] and rows["بارامترات التقرير"]["status"] == "same" and rows["موجود في المنيو"]["status"] == "same"
    assert rows["حقول الاستورد"]["status"] == "diff" and "MovementType" in rows["حقول الاستورد"]["detail"]
    assert rows["عناوين التقرير"]["status"] == "diff" and rows["قاعدة الرصيد"]["status"] == "diff" and "العميل" in rows["قاعدة الرصيد"]["detail"]
    assert rows["كنترولات ظاهرة باسمها"]["status"] == "both" and rows["بارامتر من غير عنوان"]["status"] == "both"
    assert rows["قيم الفلاتر الثابتة"]["status"] == "diff" and "إجمالي" in rows["قيم الفلاتر الثابتة"]["detail"]
    assert rows["ملفات الجافاسكربت"]["status"] == "warn" and rows["ترتيب السطور"]["status"] == "diff"
    cat, meta = R.catalog_rows("https://t.test", "https://c.test")
    x = next(r for r in cat if r["path"] == "/Report/X")
    assert x["in_a"] and x["in_b"] is False and meta["n_a"] == 2
    assert next(r for r in cat if r["path"] == P)["diff_n"] == c["diff_n"] > 0
    iss = R.support_issues("https://t.test", "https://c.test")
    assert len(iss) == 1 and iss[0]["url"] == "https://c.test" + P and "حقول الاستورد" in iss[0]["details"]


def test_report_compare_rules_and_values():
    from engine import report_compare as R
    t = R.totals_rule([["أ", 10.0, 1.0], ["ب", 5.0, 2.0], ["الإجمالي", 15.0, 4.0]])
    assert t["found"] and t["checked"] == 2 and len(t["bad"]) == 1 and "عمود 3" in t["bad"][0]
    params = [{"path": "dateFrom", "type": "System.DateTime", "label": "من", "visible": True},
              {"path": "dateTo", "type": "System.DateTime", "label": "إلى", "visible": True},
              {"path": "WarehouseId", "type": "System.Int32", "label": "المخزن", "visible": True, "has_lookups": True, "def": ""},
              {"path": "Itemid", "type": "System.Int32", "label": "الصنف", "visible": True, "has_lookups": True, "def": ""}]
    lk = {"WarehouseId": [["76", "مخزن 1"]], "Itemid": [["0", "الكل"], ["19102", "صنف"]]}
    vals, names, auto = R.plan_values(params, lk, {"WarehouseId": "76"}, {"date_from": "2020-01-01"}, {"date_to": "2026-11-01"}, True)
    assert vals["dateFrom"][1] == "2020-01-01" and vals["dateTo"][1] == "2026-11-01" and vals["WarehouseId"][1] == "76"
    assert vals["Itemid"][1] == "19102" and auto == {"Itemid": True} and names["المخزن"] == "مخزن 1"
    assert R.fmt_sig("(1,200.00)") == "سالب بين قوسين" and R.norm_path("https://x.test/Report/A?x=1") == "/Report/A"


def test_xray_findings():
    import io
    from PIL import Image
    from engine import xray as X
    links = [{"href": "http://localhost:63733/Report/CostCenters_Get", "name": "تقرير مراكز", "group": "حسابات"},
             {"href": "https://rtconq.premiumasp.net/Report/Concretebookings_Report", "name": "الحجوزات", "group": "خرسانة"},
             {"href": "/Items", "name": "الأصناف", "group": "مخازن"}, {"href": "/Items/", "name": "الأصناف والخدمات", "group": "مخازن"},
             {"href": "/A", "name": "تقرير", "group": "ج"}, {"href": "/B", "name": "تقرير", "group": "ج"}, {"href": "javascript:void(0)", "name": "x", "group": ""}]
    f = X.menu_findings(links, "https://retcotest.runasp.net")
    t = " | ".join(x["title"] for x in f)
    assert "جهاز المطور" in t and "موقع تاني (rtconq.premiumasp.net)" in t and "بـ 2 أسماء" in t and "2 صفحات مختلفة" in t
    assert sum(1 for x in f if x["sev"] == "عالية") == 2
    lf = X.lib_findings({"jQuery": "3.3.1", "moment": "2.30.1", "Bootstrap": "4.1.3", "Knockout": "3.5.1"})
    assert [x["title"].split(" ")[0] for x in lf] == ["jQuery", "Bootstrap"] and lf[0]["sev"] == "عالية"
    pages = {"/": {"s": 200, "h": {"x-aspnet-version": "4.0.30319", "server": "Microsoft-IIS/10.0"}}}
    sf = X.security_findings(pages, ["ASP.NET_SessionId", "lang"], [{"src": "https://cdn.x/a.js", "sri": False}], True)
    st = " | ".join(x["title"] for x in sf)
    assert "Clickjacking" in st and "X-AspNet-Version" in st and "IIS/10.0" in st and "ASP.NET_SessionId" in st and "SRI" in st and "HSTS" in st
    lg = X.language_findings({"/x": {"s": 200, "ar": 500, "en": 9, "words": ["Save", "Cancel"], "odd": ["undefined"]}}, {"/x": "الشاشة"})
    assert len(lg) == 2 and lg[0]["sev"] == "متوسطة"
    def png(color, box=None):
        im = Image.new("RGB", (640, 400), "white")
        if box:
            im.paste(color, box)
        b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()
    assert X.img_diff(png("white"), png("white")) == 0 and X.img_diff(png("white"), png("black", (0, 0, 320, 400))) > 40
    a = {"menu": [{"path": "/Items", "name": "الأصناف"}, {"path": "/X", "name": "x"}], "libs": {"jQuery": "3.3.1"}, "findings": []}
    b = {"menu": [{"path": "/items", "name": "الأصناف والخدمات"}], "libs": {"jQuery": "3.7.1"}, "findings": [{"area": "الأمان", "title": "مفيش HSTS"}]}
    rows = {r["item"]: r for r in X.compare_sites(a, b)}
    assert rows["شاشات المنيو"]["status"] == "diff" and rows["أسماء مختلفة لنفس الصفحة"]["status"] == "warn" and rows["مكتبة jQuery"]["status"] == "diff"


def test_db_audit_pure(tmp_path, monkeypatch):
    import json
    from engine import db_audit as D
    from config import paths
    rows = [{"lines": 100, "ldisc": 0, "Total": 100}, {"lines": 50, "ldisc": 0, "Total": 50}, {"lines": 10, "ldisc": 0, "Total": 1000}]
    name, share, bad = D._dominant(rows, {"a": lambda r: (r["lines"], r["Total"]), "b": lambda r: (r["lines"] - 1, r["Total"])})
    assert name == "a" and round(share, 2) == 0.67 and bad[0][2] == 1000
    assert D.CLUTTER.search("ChartOfAccount_Backup_BeforeFix") and D.CLUTTER.search("Wael_TransactionCancellationJournalLines") and not D.CLUTTER.search("SalesInvoice")
    assert D.MONEY_NAME.search("UnitPrice") and not D.MONEY_NAME.search("Equivalent")
    monkeypatch.setattr(paths, "STATE_DIR", tmp_path)
    D.save_result({"at": "2026-11-12 11:40", "label": "x", "info": {"db": "ErpTest"}, "findings": [
        D.F("الكود", "عالية", "إجراءات مكسورة", "تفاصيل", [{"الكائن": "AI_X", "بيشاور على": "Items"}], 1, fix="صلّح"),
        D.F("الكود", "منخفضة", "cursor")]})
    iss = D.support_issues()
    assert len(iss) == 1 and "AI_X" in iss[0]["details"] and iss[0]["severity"] == "عالية"


def test_db_audit_classify():
    from engine import db_audit as D
    assert D._classify("Invalid object name 'dbo.Files'.")[0] == "جدول / إجراء مش موجود"
    assert D._classify("Divide by zero error encountered.")[1] == "عالية"
    assert D._classify("Conversion failed when converting the nvarchar value 'MTR' to data type int.")[1] == "متوسطة"
    assert D._classify("The column 'TypeName' was specified multiple times for 'X'.")[0] == "عمود متكرر في نفس الاستعلام"
    assert D._classify("Cannot insert the value NULL") == (None, None)
    assert D.SKIP_RUN.search("DeleteSalesInvoiceCommand") and not D.SKIP_RUN.search("Bank")


def test_tube_steps_and_pages():
    from web.tube_api import steps_from_log, _page_for
    lines = ["===== START =====", "tests/x.py::test_check \x1b[32m10:57:09\x1b[0m | \x1b[1mINFO    \x1b[0m | \x1b[36m🆚 [1/3] /Report/A\x1b[0m",
             "10:57:10 | SUCCESS  | ✅ اتبنى", "10:57:10 | INFO     | Screenshot: /x.png", "10:57:11 | ERROR    | ❌ فشل", "=== FAILURES ===", "10:57:12 | INFO | after"]
    st = steps_from_log(lines)
    assert [s["lvl"] for s in st] == ["info", "ok", "err"] and st[0]["msg"] == "🆚 [1/3] /Report/A"
    assert _page_for("tests/checks/test_check_repcmp_batch.py::test_check")["url"] == "/report-compare"
    assert _page_for("tests/checks/test_check_xray_scan.py::test_check")["url"] == "/xray"


def test_code_twin_scan(tmp_path, monkeypatch):
    from engine import code_twin as T
    from config import paths
    monkeypatch.setattr(paths, "STATE_DIR", tmp_path / "st")
    root = tmp_path / "src" / "MyERP"
    (root / "Controllers").mkdir(parents=True)
    (root / "Views" / "Bank").mkdir(parents=True)
    (root / "Reporting" / "Reports").mkdir(parents=True)
    (root / "Controllers" / "BankController.cs").write_text('public partial class BankController : Controller { public ActionResult Index() {} public JsonResult AddEdit(int id) {} }')
    (root / "Controllers" / "BankController.Extra.cs").write_text('public partial class BankController { [ActionName("Delete")] public ActionResult DeleteConfirmed(int id) {} }')
    (root / "Views" / "Bank" / "Index.cshtml").write_text("""<script>$.ajax({url: '/Bank/AddEdit', type:'POST'}); $.post('/Bank/Delete?id=1');
      $.ajax({url: '/Bank/ActivateDeactivate'}); fetch('/Banks/Get?x=1'); @* $.post('/Bank/Old') *@ </script>""")
    (root / "Reporting" / "Reports" / "R1.Designer.cs").write_text('''storedProcQuery1.StoredProcName = "R1_Get";
        this.xrLabel5.ExpressionBindings.AddRange(new DevExpress.XtraReports.UI.ExpressionBinding[] {
        new DevExpress.XtraReports.UI.ExpressionBinding("BeforePrint", "Text", "sumSum([Qty])")});''')
    res = T.scan(T.find_root(tmp_path / "src"), conn=None)
    ids = {f["id"]: f for f in res["findings"]}
    ma = next(f for f in res["findings"] if f["id"].endswith("missing_action"))
    assert ma["count"] == 1 and ma["sample"][0]["الأكشن المطلوب"] == "activatedeactivate"
    assert any(f["id"].endswith("missing_controller") and f["sample"][0]["الطلب"] == "/banks/get" for f in res["findings"])
    assert any(f["id"].endswith("report_summary") for f in res["findings"])
    sc = res["screens"]["bank"]
    assert {"index", "addedit", "delete"} <= set(sc["actions"]) and any(not c["ok"] for c in sc["calls"]) and not any("/old" in c["url"].lower() for c in sc["calls"])


def test_golive_collect_and_report(tmp_path, monkeypatch):
    import json
    from config import paths
    from engine import golive as G
    from engine.load_test import targets
    monkeypatch.setattr(paths, "STATE_DIR", tmp_path)
    url = "https://concrete.example.net"
    (tmp_path / "health_abc.json").write_text(json.dumps({
        "at": "2026-11-15T10:00:00", "base_url": url, "total": 3, "paths": ["/Bank/Index", "/Sales/Index", "/Item/Index"],
        "names": {"/Bank/Index": "البنوك", "/Sales/Index": "المبيعات", "/Item/Index": "الأصناف"},
        "broken": {"/Bank/Index": {"name": "البنوك", "why": "خطأ سيرفر 500", "s": 500, "ms": 900}},
        "times": {"/Sales/Index": 4000, "/Item/Index": 900}, "speed": [{"name": "المبيعات", "path": "/Sales/Index", "load": 7.2, "xhr": []}],
        "speed_stats": {"measured": 2, "load_median": 3.1, "load_over5": 1}}), encoding="utf-8")
    (tmp_path / "books_abc.json").write_text(json.dumps({"at": "x", "ok": True, "rows": []}), encoding="utf-8")
    (tmp_path / "load_abc.json").write_text(json.dumps({"at": "x", "users": 5, "rounds": 3, "n": 30, "bad": 2, "mode": "m",
        "targets": [{"name": "المبيعات", "url": url + "/Sales/Index", "ok": False, "p95": 9000, "bad": 2, "n": 15, "solo": 800, "deg": 4.1, "why": ["HTTP 500"]}]}), encoding="utf-8")
    from engine import report_compare as RC
    RC._write(RC._cat_file(url), {"at": "x", "reports": [{"path": "/Report/A", "name": "تقرير أ"}, {"path": "/Report/B", "name": "تقرير ب"}]})
    RC._write(RC._snap_file("/Report/A", url), {"status": "error", "fault": "Invalid column name 'DiscValue'."})
    RC._write(RC._snap_file("/Report/B", url), {"status": "stuck"})
    d = G.collect(url, "خرسانة")
    a = {x["name"]: x for x in d["areas"]}
    assert d["verdict"] == "no" and a["الشاشات"]["verdict"] == "no" and a["الحسابات"]["verdict"] == "go" and a["الكود"]["verdict"] == "na"
    rep = next(f for f in d["findings"] if f["area"] == "التقارير" and f["confirmed"])
    assert "DiscValue" in rep["title"] and any(f["area"] == "التقارير" and not f["confirmed"] for f in d["findings"])
    assert any(f["area"] == "السرعة" for f in d["findings"]) and any(f["area"] == "الحمل" and f["confirmed"] for f in d["findings"])
    assert "تقرير اختبار الاستلام" in G.report_html(d, "u")
    tg = targets(url, json.loads((tmp_path / "health_abc.json").read_text(encoding="utf-8")), {"/a": {"url": "/Api/Get?x=1", "ms": 300}})
    assert tg[0]["name"] == "الصفحة الرئيسية" and tg[1]["url"].endswith("/Sales/Index") and tg[-1]["kind"] == "طلب بيانات"
    G.save_plan(url, {"last": d})
    assert any(i["source"] == "🚀 اختبار الاستلام" for i in G.support_issues())


def test_all_templates_compile():
    import os
    from web.app import app
    bad = []
    for n in os.listdir("web/templates"):
        if n.endswith(".html"):
            try:
                app.jinja_env.get_template(n)
            except Exception as e:
                bad.append(f"{n}: {e}")
    assert not bad, bad


def test_fire_strategies_and_ways():
    from engine import checks as C
    from engine.auto_test import _strategy
    from engine.fire_tests import FIRE_TEXT, TECH, WAYS
    assert _strategy({"kind": "textarea", "label": "ملاحظات", "id": "Notes"}, "fire")[1].startswith(FIRE_TEXT)
    assert _strategy({"kind": "text", "label": "الجوال", "id": "Mobile"}, "fire")[0] == "smart"
    assert _strategy({"kind": "number", "label": "المبلغ", "id": "Amount"}, "neg") == ("fixed", "-5")
    assert all(ord(ch) < 0x10000 for ch in FIRE_TEXT)          # chromedriver types BMP characters only
    assert TECH.search("Incorrect syntax near 'x'") and not TECH.search("من فضلك أدخل اسم العميل")
    assert set(WAYS) <= set(C.AUTO_WAYS) and C.normalize({"key": "a_b", "type": "auto", "screen": "x"})["ways"] == C.CLASSIC_WAYS
    from engine import golive as G
    k = G.fire_key("Sales-Invoice")
    assert C.KEY_RE.match(k) and G.fire_config("Sales-Invoice", "فواتير البيع")["ways"] == C.FIRE_WAYS


def test_golive_odd_states(tmp_path, monkeypatch):
    import json
    from config import paths
    from engine import golive as G
    monkeypatch.setattr(paths, "STATE_DIR", tmp_path)
    url = "https://odd.example.net"
    (tmp_path / "health_x.json").write_text(json.dumps({"base_url": url, "at": "a", "paths": ["/", "/?a=1", "https://odd.example.net/Sales/Index", "#"],
        "names": {"/": "الرئيسية"}, "broken": {"/?a=1": {}}, "speed": [{"load": 9, "xhr": [{}]}], "speed_stats": {"measured": 1}}), encoding="utf-8")
    (tmp_path / "books_x.json").write_text(json.dumps({"ok": False, "rows": [{"cells": ["x"], "ok": False}, {}]}), encoding="utf-8")
    assert G._ctrl("https://h/Sales/Index?x") == "sales" and G._ctrl("/?a") == ""
    d = G.collect(url)
    assert d["verdict"] in ("no", "care") and G.report_html(d)


def test_factory_reset_clears_support(tmp_path, monkeypatch):
    from config import paths
    from web import reset_api, support
    for name in ("RESULTS_DIR", "RUN_LOGS_DIR", "SCREENSHOTS_DIR", "ALLURE_RESULTS_DIR", "ALLURE_REPORT_DIR", "HISTORY_DIR", "TRASH_DIR",
                 "APP_LOGS_DIR", "STATE_DIR", "SETTINGS_DIR"):
        d = tmp_path / name.lower()
        d.mkdir()
        monkeypatch.setattr(paths, name, d)
    monkeypatch.setattr(paths, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(support, "paths", paths)
    from web import data_helper
    monkeypatch.setattr(data_helper, "RESULTS_DIR", paths.RESULTS_DIR)
    (paths.SETTINGS_DIR / "support_manual.json").write_text('[{"id": "m1", "title": "x"}]', encoding="utf-8")
    (paths.STATE_DIR / "xray_a.json").write_text("{}", encoding="utf-8")
    assert len(support.collect()[0]) > 0
    out = reset_api.wipe(["runs", "state"], "admin")
    assert out["runs"] >= 1 and out["state"] >= 1
    left = support.collect()[0]
    assert left == [], [(x.get("source"), x.get("title")) for x in left][:3]
    assert not (paths.STATE_DIR / "xray_a.json").exists()


def test_impact_classify_and_analyse():
    from engine import impact as I
    assert I.classify("MyERP/Controllers/BanksController.cs") == ("controller", "banks")
    assert I.classify("MyERP/Views/Banks/Index.cshtml") == ("view", "banks")
    assert I.classify("MyERP/Views/Shared/_Layout.cshtml")[0] == "global"
    assert I.classify("MyERP/Reporting/Reports/ItemCard.Designer.cs") == ("report", "ItemCard")
    twin = {"screens": {"banks": {"name": "Banks", "procs": ["Bank_Get"], "tables": ["Banks"]}, "cash": {"name": "Cash", "procs": ["Bank_Get"], "tables": []}}}
    files = [{"path": "Controllers/BanksController.cs", "status": "اتعدل", "add": 1, "del": 0, "lines": ["var x = db.Exec(\"Bank_Get\");"]},
             {"path": "Db/fix.sql", "status": "جديد", "add": 2, "del": 0, "lines": ["ALTER PROCEDURE [dbo].[Bank_Get]", "AS SELECT 1"]},
             {"path": "Views/Shared/_Layout.cshtml", "status": "اتعدل", "add": 1, "del": 1, "lines": ["<div>"]}]
    r = I.analyse(files, twin, "t")
    s = {e["key"]: e for e in r["screens"]}
    assert s["banks"]["score"] > s["cash"]["score"] > 0 and r["counts"]["global"] == 1 and r["procs"][0]["name"] == "bank_get"


def test_uat_flow(tmp_path, monkeypatch):
    import base64
    from config import paths
    from engine import uat as U
    monkeypatch.setattr(paths, "SETTINGS_DIR", tmp_path)
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    d = U.create("قبول", "عميل", "https://x", ["cash"], ["أ", "ب"])
    assert U.by_token(d["token"])["id"] == d["id"] and U.by_token("x" * 24) is None
    sid = d["scenarios"][0]["steps"][0]["id"]
    U.set_step(d, sid, "fail", "غلط", "أ")
    png = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n").decode()
    import pytest
    with pytest.raises(ValueError):
        U.sign(d, "م", "", "accept", "", png)
    U.sign(d, "م", "مدير", "accept_notes", "", png)
    assert d["status"] == "signed" and U.support_issues()[0]["severity"] == "عالية" and "شهادة" in U.certificate_html(d)
    with pytest.raises(ValueError):
        U.set_step(d, sid, "pass", "", "أ")


def test_migration_compare():
    from engine import migration as M
    src = {"rows": [{"code": "0101", "name": "الصندوق", "debit": 100, "credit": None, "balance": 100, "qty": None, "value": None},
                    {"code": "", "name": "البنك الأهلي", "debit": 50, "credit": None, "balance": 50, "qty": None, "value": None},
                    {"code": "9", "name": "ناقص", "debit": None, "credit": 150, "balance": -150, "qty": None, "value": None}]}
    erp = {"rows": [{"code": "101", "name": "الصندوق", "debit": 100, "credit": 0, "balance": 100, "qty": None, "value": None},
                    {"code": "77", "name": "البنك الاهلى", "debit": 40, "credit": 0, "balance": 40, "qty": None, "value": None}]}
    r = M.compare(src, erp, 0.01, "accounts")
    st = {x["name"]: x["status"] for x in r["rows"]}
    assert st == {"الصندوق": "same", "البنك الأهلي": "diff", "ناقص": "missing"} and r["src_balanced"] is True and not r["ok"]
    assert M._num("(1,250.50)") == -1250.5 and M._num("٣٠٠") == 300
    assert M.guess(["كود", "اسم الحساب", "رصيد مدين", "رصيد دائن"]) == {"code": 0, "name": 1, "debit": 2, "credit": 3}


def test_site_monitor_states_and_alerts(tmp_path, monkeypatch):
    """📡 down only after 2 fails in a row, slow after 3, one alert per change, certificate once a day; read only (GET)"""
    from web import monitor as M
    monkeypatch.setattr(M, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(M, "load_config", lambda: {**M.DEFAULTS, "slow_ms": 5000})
    monkeypatch.setattr(M, "_sites", lambda cfg: [{"id": "c1", "name": "عميل", "base_url": "https://c.example", "kind": "client"}])
    monkeypatch.setattr(M, "ssl_days", lambda url: 10)
    seq, sent = [], []
    monkeypatch.setattr(M, "broadcast", lambda t: sent.append(t))
    LOGIN = '<form><input type="password"></form>'
    monkeypatch.setattr(M, "_get", lambda url, timeout: seq.pop(0) if url.endswith("/") else (200, 50, LOGIN, url))

    def go(*r):
        seq.extend(r)
        return M.run_once()["c1"]["v"]

    assert go((200, 300, LOGIN, "x")) == "up"
    assert len(sent) == 1 and "شهادة" in sent[0]                 # certificate: 10 days left -> warned once today
    assert go((0, 30000, "timed out", "x")) == "up"              # one blip: no alert
    assert go((503, 200, "", "x")) == "down" and "واقع" in sent[-1] and "503" in sent[-1]
    assert go((500, 200, "", "x")) == "down" and len(sent) == 2   # still down: no repeat
    assert go((200, 400, "<p>ok</p>", "https://c.example/Account/Login")) == "up" and "رجع" in sent[-1]
    for _ in range(2):
        assert go((200, 7000, LOGIN, "x")) == "up"
    assert go((200, 7000, LOGIN, "x")) == "slow" and "بطيء" in sent[-1]
    assert go((200, 200, "Server Error in '/' Application", "x")) == "slow"   # error page: a fail (one so far)
    assert M._state()["c1"]["last"]["why"].startswith("صفحة خطأ")
    s = M.summary()["sites"][0]
    assert s["checks"] == 9 and s["uptime"] is not None and len(s["incidents"]) == 3 and s["incidents"][0]["v"] == "slow"


def test_site_monitor_screens(tmp_path, monkeypatch):
    """📡🖥️ screens: alert on newly broken / fixed screens and a failed sign-in (once); clients only when allowed; items for «دعم المطورين»"""
    from web import monitor as M
    monkeypatch.setattr(M, "STATE_FILE", tmp_path / "state.json")
    cfg = {**M.DEFAULTS}
    monkeypatch.setattr(M, "load_config", lambda: cfg)
    sites = [{"id": "t", "name": "اختبار", "base_url": "https://test.x", "kind": "test", "username": "u", "password": "p"},
             {"id": "c", "name": "عميل", "base_url": "https://c.x", "kind": "client", "username": "u", "password": "p"},
             {"id": "n", "name": "بدون مستخدم", "base_url": "https://n.x", "kind": "test", "username": "", "password": ""}]
    monkeypatch.setattr(M, "_sites", lambda c: sites)
    sent, seen, rounds = [], [], []
    monkeypatch.setattr(M, "broadcast", lambda t: sent.append(t))

    def fake(p, c):
        seen.append(p["id"])
        r = rounds[0]
        return {"at": "2026-11-21T10:00:00", **r} if "error" in r else {"at": "2026-11-21T10:00:00", "screens": 50, "problems": r["p"], "slow": [], "msg": ""}
    monkeypatch.setattr(M, "deep_check", fake)

    def go(r):
        rounds[:] = [r]
        seen.clear()
        M.run_deep()

    go({"p": [["/Sales/index", "HTTP 500"], ["/Stock", "فضلت تحمّل ومطلعتش بيانات"]]})
    assert seen == ["t"]                                          # client not allowed yet, no-user site skipped
    assert len(sent) == 1 and "2 شاشة" in sent[0] and "/Sales/index" in sent[0]
    go({"p": [["/Sales/index", "HTTP 500"], ["/Stock", "فضلت تحمّل ومطلعتش بيانات"]]})
    assert len(sent) == 1                                         # same problems: quiet
    go({"p": [["/Sales/index", "HTTP 500"], ["/HR/index", "HTTP 404"]]})
    assert "جديدة" in sent[-2] and "/HR/index" in sent[-2] and "اتصلحت" in sent[-1] and "/Stock" in sent[-1]
    go({"error": "الدخول ما نجحش: اسم المستخدم أو كلمة السر غلط"})
    assert "مقدرتش أدخل" in sent[-1]
    n = len(sent)
    go({"error": "الدخول ما نجحش"})
    assert len(sent) == n                                         # the same failure: once
    issues = M.support_issues()
    assert {i["screen"] for i in issues} == {"/Sales/index", "/HR/index"}   # kept from the last good look
    assert next(i for i in issues if i["screen"] == "/Sales/index")["severity"] == "عالية"
    assert issues[0]["url"].startswith("https://test.x/")
    cfg["deep_clients"] = True
    go({"p": []})
    assert seen == ["t", "c"] and M.support_issues() == []
    s = {x["id"]: x for x in M.summary()["sites"]}
    assert s["n"]["deep_reason"] and not s["t"]["deep_reason"] and s["t"]["deep"]["screens"] == 50


def test_nq_erp_telemetry(tmp_path, monkeypatch):
    """🛰️ NQ ERP's own errors: secret link per site, same error grouped, rate limit, one alert per new error, version, «دعم المطورين»"""
    from web import monitor as M, telemetry as T
    from web.app import app
    cfg = {**M.DEFAULTS, "tokens": {}}
    monkeypatch.setattr(M, "load_config", lambda: cfg)
    monkeypatch.setattr(M, "save_config", lambda new: cfg.update(new) or cfg)
    monkeypatch.setattr(M, "_sites", lambda c: [{"id": "c1", "name": "عميل", "base_url": "https://c.x", "kind": "client"}])
    monkeypatch.setattr(T, "FILE", tmp_path / "tel.json")
    monkeypatch.setattr(T, "_rate", {})
    monkeypatch.setattr(T, "_alerts", {})
    sent = []
    monkeypatch.setattr(M, "broadcast", lambda t: sent.append(t))
    tok = T.token_for("c1")
    c = app.test_client()
    assert c.post("/api/telemetry/wrong", data="{}").status_code == 404
    assert c.open(f"/api/telemetry/{tok}", method="OPTIONS").headers["Access-Control-Allow-Origin"] == "*"
    err = {"kind": "server", "type": "System.Data.SqlClient.SqlException", "message": "Invalid column name 'Qty2' at row 15",
           "url": "/SalesInvoice/AddEdit/1520?x=1", "user": "ahmed", "stack": "at ...", "version": "2026.11.20"}
    r = c.post(f"/api/telemetry/{tok}", data=__import__("json").dumps(err), content_type="text/plain")   # sendBeacon sends text/plain
    assert r.status_code == 204 and len(sent) == 1 and "SalesInvoice/AddEdit/#" in sent[0] and "ahmed" in sent[0]
    T.receive("c1", {**err, "message": "Invalid column name 'Qty2' at row 99", "url": "/SalesInvoice/AddEdit/77", "user": "sara"})
    T.receive("c1", {"kind": "start", "version": "2026.11.21", "build": "2026-11-21 09:00", "machine": "WEB1"})
    s = T.site_summary("c1")
    assert s["errors_24h"] == 1 and s["hits_24h"] == 2 and s["users_24h"] == 2 and len(sent) == 1   # grouped, no second alert
    assert s["version"]["version"] == "2026.11.21" and s["last_start"]["machine"] == "WEB1"
    T.receive("c1", [{"kind": "js", "message": f"x{i} is not defined", "url": "/HR"} for i in range(100)])
    assert sum(1 for e in __import__("json").loads(T.FILE.read_text())["c1"]["errors"].values()) <= 60   # 60 a minute
    assert len(sent) == 2                                          # a burst of new errors = one alert
    it = [i for i in T.support_issues() if i["screen"] == "/SalesInvoice/AddEdit/#"][0]
    assert it["severity"] == "عالية" and "2 مرة" in it["details"] and "SqlException" in it["evidence"]
    assert "tokens" not in M.summary()["config"]                   # the links never reach the page's JSON


def test_nq_care(tmp_path, monkeypatch):
    """💼 NQ Care: uptime vs the plan's target, outage durations, client-safe status page behind a secret link, contract alerts, reports"""
    import json
    from datetime import datetime, timedelta
    from web import care as C, monitor as M, telemetry as T
    from web.app import app
    monkeypatch.setattr(C, "FILE", tmp_path / "care.json")
    monkeypatch.setattr(M, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(T, "FILE", tmp_path / "tel.json")
    monkeypatch.setattr(M, "_sites", lambda c: [{"id": "c1", "name": "شركة الريان", "base_url": "https://c.x", "kind": "client"}])
    sent = []
    monkeypatch.setattr(M, "broadcast", lambda t: sent.append(t))
    month, today = datetime.now().strftime("%Y-%m"), datetime.now().strftime("%Y-%m-%d")
    st = {"c1": {"hist": [{"ok": True, "ms": 900, "at": today + "T10:00:00"}], "v": "up", "last": {"at": today + "T10:00:00", "ms": 900},
                 "days": {today: {"n": 100, "ok": 98, "ms": 98 * 1000}},
                 "incidents": [{"at": today + "T01:00:00", "v": "down", "why": "السيرفر رجّع خطأ 503 Exception secret"},
                               {"at": today + "T01:45:00", "v": "up", "why": ""}],
                 "deep": {"at": today + "T09:00:00", "screens": 120, "problems": [["/HR", "HTTP 500"]]},
                 "deep_log": [{"at": today + "T03:00:00", "new": ["/HR", "/Stock"], "fixed": []}, {"at": today + "T06:00:00", "new": [], "fixed": ["/Stock"]}]}}
    M._save_state(st)
    T.receive("c1", {"kind": "start", "version": "2026.11.21"})
    assert C.site_of("x") is None
    cl = C.save_client("c1", {"plan": "pro", "start": "2026-01-01", "end": (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d"), "contact": "أ. خالد"})
    assert C.site_of(cl["token"]) == "c1"
    d = C.month_stats("c1", month)
    assert d["uptime"] == 98.0 and d["target"] == 99.5 and d["met"] is False
    assert d["down_min"] == 45 and len(d["outages"]) == 1 and d["found"] == ["/HR", "/Stock"] and d["fixed"] == ["/Stock"]
    assert d["versions"][0]["version"] == "2026.11.21"
    c = app.test_client()
    assert c.get("/status/nope").status_code == 404
    r = c.get(f"/api/status/{cl['token']}")                          # no login: the link is the key
    assert r.status_code == 200
    s = r.get_json()
    assert s["state"] == "up" and s["incidents"][0]["minutes"] == 45 and s["screens"] == {"total": 120, "bad": 1, "at": today + "T09:00:00"}
    assert "503" not in json.dumps(s) and "Exception" not in json.dumps(s) and "/HR" not in json.dumps(s)   # client-safe
    assert c.get(f"/status/{cl['token']}").status_code == 200
    C.add_notice("c1", "تحديث النظام", today + "T00:00", today + "T23:59")
    st["c1"]["v"] = "down"
    M._save_state(st)
    assert C.status("c1")["state"] == "maintenance"                  # down during planned maintenance
    h = C.html_monthly("c1", month, "admin")
    assert "98.0%" in h and "ماتحققش" in h and "45 د" in h and "/Stock" in h and "اتصلحت" in h
    assert "NQ Care متقدم" in C.html_offer() and "خلال 8 ساعة" in C.html_offer()
    C._last["t"] = 0                                                  # the app's background ticker may have used this hour already
    C.auto_tick()
    assert len(sent) == 1 and "هيخلص بعد 5 يوم" in sent[0] and "أ. خالد" in sent[0]
    C._last["t"] = 0
    C.auto_tick()
    assert len(sent) == 1                                             # once per step
    with c.session_transaction() as ss:
        ss["user_id"], ss["role"] = 2, "user"
    assert c.get("/api/care").status_code == 403                      # admin only


def test_sales_demo(tmp_path, monkeypatch):
    """🤝 the sales demo: the virtual company on its own site, tour → the demo site's screens, feed behind a key, leave-behind, daily start"""
    import json
    from datetime import datetime
    from simulation import settings as S
    from web import care as C, monitor as M, sales as SA, telemetry as T
    from web.app import app
    profs = [{"id": "t", "name": "الاختبار", "base_url": "https://test.x", "kind": "test", "username": "u", "password": "p"},
             {"id": "d", "name": "العرض", "base_url": "https://demo.x", "kind": "test", "username": "du", "password": "dp"},
             {"id": "c", "name": "عميل", "base_url": "https://c.x", "kind": "client", "username": "cu", "password": "cp"}]
    monkeypatch.setattr(S, "_profiles", lambda: (profs, "t"))
    monkeypatch.setattr(M, "_sites", lambda c: profs)
    for mod, name in ((SA, "sales.json"), (C, "care.json")):
        monkeypatch.setattr(mod, "FILE", tmp_path / name)
    monkeypatch.setattr(M, "STATE_FILE", tmp_path / "state.json")
    monkeypatch.setattr(T, "FILE", tmp_path / "tel.json")
    monkeypatch.setattr(SA, "RUNS", tmp_path / "runs")
    # the simulation can work on a chosen site without touching the main choice
    assert S.runtime()["url"] == "https://test.x" and S.runtime("d")["url"] == "https://demo.x"
    assert S.credentials("manager", "d")[:2] == ("du", "dp") and S.credentials("manager")[:2] == ("u", "p")
    # the tour opens the demo site's screens from the menu the company read
    menus = tmp_path / "menus.json"
    menus.write_text(json.dumps({"d:du": {"n": 2, "menu": [{"path": "/SalesInvoice/index", "name": "فواتير المبيعات فاتورة مبيعات", "module": "المبيعات"},
                                                           {"path": "/Debt/Ages", "name": "أعمار الديون", "module": "التقارير"}]}}), encoding="utf-8")
    real_sf = SA.paths.settings_file
    monkeypatch.setattr(SA.paths, "settings_file", lambda n: menus if n == "simulation_menus.json" else real_sf(n))
    assert SA.start_day() == "اختار موقع العرض الأول"
    SA.save({"demo_site": "c"})
    assert "اختبار" in SA.start_day()                                 # a client site is never written to
    SA.save({"demo_site": "d"})
    steps = {s["word"]: s for s in SA.tour_links("trading")}
    assert steps["فاتورة مبيعات"]["url"] == "https://demo.x/SalesInvoice/index" and steps["أعمار الديون"]["found"]
    assert steps["تحويل"]["url"] == "https://demo.x/" and not steps["تحويل"]["found"]
    assert steps["الرئيسية"]["found"]
    # the daily start: once a day, only on the chosen days, after the hour
    started = []
    monkeypatch.setattr(SA, "start_day", lambda: started.append(1) or "")
    SA.save({"auto_on": True, "at": "00:00", "days": [datetime.now().weekday()]})
    SA.auto_tick()
    assert started == [1]
    SA.save({**SA.load(), "auto_on": True})
    raw = json.loads(SA.FILE.read_text()); raw["last_run"] = datetime.now().strftime("%Y-%m-%d 06:30"); SA.FILE.write_text(json.dumps(raw))
    SA.auto_tick()
    assert started == [1]
    # the leave-behind and the AI employee's feed
    h = SA.html_leave("manufacturing", "مصنع الإبراهيم")
    assert "تصنيع خفيف" in h and "مصنع الإبراهيم" in h and "NQ Care متقدم" in h and "سند التجميع" in h
    c = app.test_client()
    assert c.get("/api/sales/feed?key=x").status_code == 404
    key = SA.feed_key()
    f = c.get(f"/api/sales/feed?key={key}").get_json()
    assert set(f["sectors"]) == {"trading", "manufacturing", "services", "concrete"} and f["nq_care"][0]["name"] == "NQ Care أساسي"
    assert "proof" in f and f["demo"]["site"] == "https://demo.x"
    with c.session_transaction() as ss:
        ss["user_id"], ss["role"] = 2, "user"
    assert c.post("/api/sales/key").status_code == 403                # the feed link: admin only
    assert c.get("/api/sales").status_code == 200                     # the presenter page: any signed-in user


def test_client_health_and_ticket_deadlines(tmp_path, monkeypatch):
    """❤️ score per client (worst first, reasons, change), morning summary, weekly report; ⏱️ ticket deadline from «اتبلغ للمطور», overdue alert once"""
    import json
    from datetime import datetime, timedelta
    from web import care as C, clients_health as H, monitor as M, support as SP, telemetry as T
    from web.app import app
    profs = [{"id": "a", "name": "شركة سليمة", "base_url": "https://a.x", "kind": "client"},
             {"id": "b", "name": "شركة تعبانة", "base_url": "https://b.x", "kind": "client"},
             {"id": "t", "name": "الاختبار", "base_url": "https://t.x", "kind": "test"}]
    monkeypatch.setattr(M, "_sites", lambda c: profs)
    for mod, attr, name in ((M, "STATE_FILE", "state.json"), (T, "FILE", "tel.json"), (C, "FILE", "care.json"), (H, "CFG", "digest.json"), (H, "HIST", "health.json")):
        monkeypatch.setattr(mod, attr, tmp_path / name)
    sent = []
    monkeypatch.setattr(M, "broadcast", lambda t: sent.append(t))
    d = lambda k: (datetime.now() - timedelta(days=k)).strftime("%Y-%m-%d")
    M._save_state({
        "a": {"v": "up", "hist": [1], "last": {"ssl_days": 200}, "days": {d(k): {"n": 96, "ok": 96, "ms": 96 * 900} for k in range(7)},
              "deep": {"screens": 100, "problems": []}},
        "b": {"v": "down", "hist": [1], "last": {"ssl_days": 10}, "days": {d(k): {"n": 96, "ok": 90, "ms": 90 * 6000} for k in range(7)},
              "deep": {"screens": 100, "problems": [["/x", "HTTP 500"], ["/y", "HTTP 500"], ["/z", "HTTP 404"]]},
              "deep_log": [{"at": d(1) + "T10:00:00", "new": ["/x"], "fixed": []}]}})
    T.receive("a", {"kind": "start", "version": "2026.11.21"})
    T.receive("b", {"kind": "start", "version": "2026.10.01"})
    for i in range(6):
        T.receive("b", {"kind": "server", "type": "E", "message": f"boom kind {chr(97 + i)}", "url": f"/s{chr(97 + i)}"})
    H.HIST.write_text(json.dumps({d(7): {"a": 90, "b": 60}}))
    r = H.all_scores()
    assert [x["id"] for x in r] == ["b", "a"]                      # worst first, client sites only
    a, b = r[1], r[0]
    assert a["score"] >= 95 and a["level"] == "ok" and a["change"] == a["score"] - 90
    assert b["level"] == "bad" and len(b["reasons"]) == 3 and "93.8%" in b["reasons"][0]          # the biggest deductions first
    assert {p["name"]: p["got"] for p in b["parts"]}["النسخة"] == 0                                  # older than the newest client
    txt = H.morning_text()
    assert "واقع دلوقتي: شركة تعبانة" in txt and "1 شاشة باظت" in txt and "عملاء في خطر: شركة تعبانة" in txt
    assert "شركة تعبانة" in H.html_weekly() and "في خطر" in H.html_weekly()
    # ⏱️ deadlines: from «اتبلغ للمطور», per severity
    monkeypatch.setattr(SP, "_f", lambda name: tmp_path / name)
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"], ss["role"], ss["username"] = 1, "admin", "admin"
    c.post("/api/support/status", json={"id": "x1", "status": "اتبلغ للمطور", "dev": "عصام"})
    st = SP._load("support_status.json", {})
    assert st["x1"]["sent_at"] and st["x1"]["dev"] == "عصام"
    st["x1"]["sent_at"] = (datetime.now() - timedelta(hours=30)).strftime("%Y-%m-%d %H:%M")
    SP._save("support_status.json", st)
    it = {"id": "x1", "severity": "عالية", "status": "اتبلغ للمطور", "title": "فاتورة المبيعات بترجع 500"}
    SP._sla(it, st["x1"], SP.sla_cfg(), datetime.now())
    assert it["overdue"] and it["late_h"] == 6
    it2 = {"id": "x2", "severity": "متوسطة", "status": "بيتصلح"}
    SP._sla(it2, {"sent_at": st["x1"]["sent_at"]}, SP.sla_cfg(), datetime.now())
    assert not it2["overdue"] and it2["left_h"] == 42
    monkeypatch.setattr(SP, "collect", lambda: ([{**it, "dev": "عصام"}], []))
    H._last["od"] = 0
    H._overdue_alerts()
    assert "تذاكر عدّت ميعاد الحل" in sent[-1] and "عصام" in sent[-1]
    n = len(sent)
    H._last["od"] = 0
    H._overdue_alerts()
    assert len(sent) == n                                           # once per ticket
    c.post("/api/support/status", json={"id": "x1", "status": "اتصلح"})
    assert SP._load("support_status.json", {})["x1"]["fixed_at"]
    stats = c.get("/api/support/sla").get_json()
    assert stats["config"]["hours"]["عالية"] == 24 and stats["config"]["devs"][0] == "عصام"


def test_releases_gate_rollout_and_regressions(tmp_path, monkeypatch):
    """🚀 a version: gate on the test site → pilot client watched → the rest; alerts; 🔁 errors / screens that come back after «اتصلح»"""
    import time as _t
    from datetime import datetime, timedelta
    from simulation import settings as SS
    from web import monitor as M, releases as R, support as SP, telemetry as T
    profs = [{"id": "t", "name": "الاختبار", "base_url": "https://t.x", "kind": "test", "username": "u", "password": "p"},
             {"id": "c1", "name": "التجريبي", "base_url": "https://c1.x", "kind": "client"},
             {"id": "c2", "name": "عميل تاني", "base_url": "https://c2.x", "kind": "client"}]
    monkeypatch.setattr(M, "_sites", lambda c: profs)
    for mod, attr, name in ((M, "STATE_FILE", "state.json"), (T, "FILE", "tel.json"), (R, "FILE", "rel.json")):
        monkeypatch.setattr(mod, attr, tmp_path / name)
    monkeypatch.setattr(SP, "_f", lambda name: tmp_path / name)
    monkeypatch.setattr(SS, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(T, "_rate", {})
    monkeypatch.setattr(T, "_alerts", {})
    sent = []
    monkeypatch.setattr(M, "broadcast", lambda t: sent.append(t))
    ago = lambda h: _t.time() - h * 3600
    r = R.add("2026.11.25", "ربحية الخرسانة", pilot=["c1"], test_site="t")
    assert R.gate(r)["verdict"] == "none"
    T.receive("t", {"kind": "start", "version": "2026.11.25"}, now=ago(1))
    g = R.gate(r)
    assert g["verdict"] == "wait" and any("ساعة بس" in x for x in g["reasons"]) and any("الشركة الافتراضية" in x for x in g["reasons"])
    T.receive("t", {"kind": "server", "type": "E", "message": "boom", "url": "/SalesInvoice/AddEdit"}, now=ago(0.5))
    assert R.gate(r)["verdict"] == "stop" and "SalesInvoice" in R.gate(r)["reasons"][0]
    assert "متنزلهاش" in R.advice(r, R.gate(r), R.rollout(r))
    # a client gets it before the gate: alert
    T.receive("c2", {"kind": "start", "version": "2026.11.25"}, now=ago(0.2))
    R._last["t"] = 0
    R.auto_tick()
    assert "قبل ما تعدّي البوابة" in sent[-1] and "عميل تاني" in sent[-1]
    # a clean test site after enough hours + a company day → go
    monkeypatch.setattr(T, "FILE", tmp_path / "tel2.json")
    monkeypatch.setattr(T, "_rate", {})
    T.receive("t", {"kind": "start", "version": "2026.11.25"}, now=ago(6))
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / f"day_{datetime.now():%Y%m%d}_090000.json").write_text("{}")
    assert R.gate(r)["verdict"] == "go"
    assert "نزّلها عند العميل التجريبي: التجريبي" in R.advice(r, R.gate(r), R.rollout(r))
    T.receive("c1", {"kind": "start", "version": "2026.11.25"}, now=ago(30))     # pilot 30 h ago, nothing went wrong
    roll = {x["id"]: x for x in R.rollout(r)}
    assert roll["c1"]["status"] == "ok" and roll["c2"]["status"] == "pending"
    assert "كمل نزّلها لباقي العملاء" in R.advice(r, R.gate(r), R.rollout(r))
    R.update(r["id"], {"mark": {"site": "c2", "at": (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M")}})
    assert {x["id"]: x for x in R.rollout(R.load()["releases"][0])}["c2"]["status"] == "watching"
    # 🔁 an error marked «اتصلح» that comes back → alert + ticket back to «جديد»
    T.receive("c1", {"kind": "server", "type": "E", "message": "Invalid column 'Qty'", "url": "/Stock"}, now=ago(10))
    key = next(iter(T._load()["c1"]["errors"]))
    SP._save("support_status.json", {f"tel_c1_{key}"[:40]: {"status": "اتصلح", "at": (datetime.now() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M"), "fixed_at": "x"}})
    T.receive("c1", {"kind": "server", "type": "E", "message": "Invalid column 'Qty'", "url": "/Stock"})
    assert "كان اتصلح ورجع تاني" in sent[-1]
    st = SP._load("support_status.json", {})[f"tel_c1_{key}"[:40]]
    assert st["status"] == "جديد" and "رجع تاني" in st["note"] and "fixed_at" not in st
    assert R.rollout(R.load()["releases"][0])[0]["status"] == "problem"          # the pilot now has a problem that came back
    # 🔁 a screen that was fixed and broke again
    M._save_state({"t": {"hist": [], "v": "up", "deep": {"at": "x", "screens": 5, "problems": []},
                         "deep_log": [{"at": "2026-11-01T10:00:00", "new": ["/HR"], "fixed": []}, {"at": "2026-11-02T10:00:00", "new": [], "fixed": ["/HR"]}]}})
    monkeypatch.setattr(M, "load_config", lambda: {**M.DEFAULTS})
    monkeypatch.setattr(M, "deep_check", lambda p, c: {"at": datetime.now().isoformat(timespec="seconds"), "screens": 5, "problems": [["/HR", "HTTP 500"]], "slow": [], "msg": ""})
    M.run_deep()
    assert "كانت اتصلحت ورجعت: /HR" in sent[-1] and M._state()["t"]["deep_log"][-1]["regressed"] == ["/HR"]


def test_release_judged_only_while_it_ran(tmp_path, monkeypatch):
    """🚀 an older version isn't blamed for an error that happened after the site moved to the next one"""
    import time as _t
    from web import monitor as M, releases as R, telemetry as T
    monkeypatch.setattr(M, "_sites", lambda c: [{"id": "t", "name": "الاختبار", "base_url": "https://t.x", "kind": "test"}])
    for mod, attr, name in ((M, "STATE_FILE", "s.json"), (T, "FILE", "tel.json"), (R, "FILE", "rel.json")):
        monkeypatch.setattr(mod, attr, tmp_path / name)
    monkeypatch.setattr(T, "_rate", {})
    monkeypatch.setattr(M, "broadcast", lambda t: None)
    ago = lambda h: _t.time() - h * 3600
    a, b = R.add("1.0", test_site="t"), R.add("1.1", test_site="t")
    T.receive("t", {"kind": "start", "version": "1.0"}, now=ago(30))
    T.receive("t", {"kind": "start", "version": "1.1"}, now=ago(2))
    T.receive("t", {"kind": "server", "type": "E", "message": "boom", "url": "/x"}, now=ago(1))
    assert R.gate(a)["verdict"] != "stop" and R.gate(a)["facts"]["until"] and R.gate(a)["facts"]["errors"] == 0
    assert R.gate(b)["verdict"] == "stop"


def test_inside_zatca_db_usage(tmp_path, monkeypatch):
    """🔬 NQ ERP's own reports: ZATCA (rejections alert, counts per day), database (old backup alert once a day), screen usage vs other clients"""
    from datetime import datetime, timedelta
    from web import monitor as M, telemetry as T
    from web.app import app
    profs = [{"id": "a", "name": "عميل أ", "base_url": "https://a.x", "kind": "client"}, {"id": "b", "name": "عميل ب", "base_url": "https://b.x", "kind": "client"}]
    monkeypatch.setattr(M, "_sites", lambda c: profs)
    monkeypatch.setattr(T, "FILE", tmp_path / "tel.json")
    monkeypatch.setattr(T, "_rate", {})
    monkeypatch.setattr(T, "_alerts", {})
    sent = []
    monkeypatch.setattr(M, "broadcast", lambda t: sent.append(t))
    T.receive("a", {"kind": "zatca", "invoice": "INV-1001", "status": "rejected", "message": "BR-KSA-37: seller VAT number invalid", "amount": 1150})
    assert "INV-1001 اترفضت" in sent[-1] and "BR-KSA-37" in sent[-1]
    T.receive("a", {"kind": "zatca", "counts": {"cleared": 40, "reported": 9, "warning": 1}, "warnings": [{"invoice": "INV-1002", "message": "rounding"}]})
    old = (datetime.now() - timedelta(hours=40)).strftime("%Y-%m-%d %H:%M")
    T.receive("a", {"kind": "db", "database": "NQ_AQUA", "backup_full": old, "data_mb": 5120.5, "log_mb": 9000, "recovery": "FULL",
                    "slow_error": "VIEW SERVER STATE permission was denied", "slow": None})
    assert "آخر نسخة احتياطية كاملة لقاعدة NQ_AQUA من 40 ساعة" in sent[-1]
    n = len(sent)
    T.receive("a", {"kind": "db", "database": "NQ_AQUA", "backup_full": old, "data_mb": 5121, "slow_error": "VIEW SERVER STATE permission was denied"})
    assert len(sent) == n                                            # once a day
    T.receive("a", {"kind": "usage", "screens": {"SalesInvoice/Index": {"n": 30, "users": ["ahmed", "sara"]}, "Home/Index": {"n": 50, "users": ["ahmed"]}}})
    T.receive("b", {"kind": "usage", "screens": {"StockTransfer/Index": {"n": 25, "users": ["ali"]}, "SalesInvoice/Index": {"n": 10, "users": ["ali"]}}})
    d = T.inside("a")
    assert d["zatca"]["sent"] == 51 and d["zatca"]["total"]["rejected"] == 1 and d["zatca"]["reject_rate"] == 2.0
    assert d["zatca"]["issues"][0]["invoice"] == "INV-1002" and d["zatca"]["issues"][1]["status"] == "rejected"
    assert d["db"]["database"] == "NQ_AQUA" and d["db"]["backup_age_h"] > 39 and d["db"]["not_allowed"]["slow"].startswith("VIEW SERVER STATE")
    assert d["usage"]["top"][0] == {"screen": "Home/Index", "n": 50, "users": 1}
    assert d["usage"]["unused_vs_others"] == [{"screen": "StockTransfer/Index", "n_others": 25}]   # others use it, this client doesn't
    from web import clients_health as H
    monkeypatch.setattr(M, "STATE_FILE", tmp_path / "s.json")
    assert "نسخ احتياطي قديم: عميل أ (40 س)" in H.morning_text()
    c = app.test_client()
    with c.session_transaction() as ss:
        ss["user_id"], ss["role"] = 1, "user"
    assert c.get("/api/inside?site=a").get_json()["data"]["db"]["database"] == "NQ_AQUA"
