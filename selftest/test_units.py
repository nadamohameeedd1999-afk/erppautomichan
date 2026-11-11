"""Fast checks without a browser."""
from engine.flows import evaluate_check, normalize_flows
from engine.recorder import convert
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


def test_recorder_convert():
    ev = [{"type": "change", "id": "CustomerId", "label": "العميل", "kind": "select2", "value": "11", "popup": False, "in_row": False},
          {"type": "click", "text": "ربط", "id": "btnLink", "popup": False, "in_row": False},
          {"type": "popup_open"},
          {"type": "change", "id": "DocType", "label": "نوع", "kind": "select2", "value": "سندات", "popup": True, "in_row": False},
          {"type": "click", "text": "المصفي", "id": "", "popup": True, "in_row": False},
          {"type": "click", "text": "اختيار", "id": "", "popup": True, "in_row": True, "row_key": "I-2"},
          {"type": "popup_close"},
          {"type": "click", "text": "حفظ", "id": "save", "popup": False, "in_row": False}]
    items = convert(ev)
    assert [i["type"] for i in items] == ["field", "action"]
    steps = [s["do"] for s in items[1]["steps"]]
    assert steps == ["click", "wait_popup", "fill", "click", "wait_rows", "row_click", "close_popup"]
    assert items[1]["steps"][5]["match"] == "I-2"


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
