import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))     # the repo root (simulation, engine, web, config)
from simulation.engine import Company  # noqa: E402


def test_full_day_runs_and_reports():
    for seed in range(1, 8):
        c = Company(seed=seed, use_settings=False)
        r = c.run_fast()
        assert r["deals"] == c.cfg["orders_per_day"]
        assert r["closed"] + r["stuck"] + r["open"] == r["deals"]
        assert all(e["status"] == "away" for e in c.emps.values())
        for cm in c.complaints:                      # every complaint carries its evidence
            assert cm["evidence"]
        assert len(c.chat) > 20


def test_report_html():
    from simulation.report import report_html
    r = Company(seed=3, use_settings=False).run_fast()
    assert "تقرير يوم الشركة" in report_html(r)


def test_real_mode_engine_path():
    """the engine with an asynchronous ERP (like the real site): permissions from the menu, denied / errors become complaints"""
    import threading
    from simulation.engine import Company
    from simulation.erp import SimERP
    from simulation.real import guess_map

    class FakeReal(SimERP):
        mode, is_async = "حقيقي", True

        def allowed(self, emp, key):
            return not (emp["role"] == "cashier" and key == "receipt_voucher")      # the cashier's menu lacks the receipt voucher

        def perform_async(self, key, emp, task, cb):
            self.n = getattr(self, "n", 0) + (key == "stock_issue")
            bad = key == "stock_issue" and self.n <= 2                                 # the first deal's stock issue fails twice
            r = {"kind": "error", "ms": 900, "msg": "Server Error in '/' Application"} if bad else {"kind": "ok", "ms": 1200, "msg": ""}
            threading.Thread(target=cb, args=(r,)).start()

    import random
    import time
    c = Company(seed=5, use_settings=False)
    c.make_erp = lambda: FakeReal(random.Random(5))
    c.control("speed", 30)
    c.control("start")
    deadline = time.time() + 45
    while (c.running or not c.report) and time.time() < deadline:
        time.sleep(0.2)
    assert c.report and c.report["mode"] == "حقيقي"
    types = {x["type"] for x in c.complaints}
    assert "صلاحيات" in types and ("خطأ سيستم" in types)
    m = guess_map([{"path": "/SalesInvoice/Index", "name": "فواتير البيع", "module": "المبيعات"}, {"path": "/Report/TrialBalance", "name": "ميزان المراجعة", "module": ""},
                   {"path": "/ReceiptVoucher", "name": "سندات القبض", "module": ""}])
    assert m["sales_invoice"] == "/SalesInvoice/Index" and m["trial_balance"] == "/Report/TrialBalance" and m["receipt_voucher"] == "/ReceiptVoucher"


def test_real_documents_follow_the_deal():
    """add returns the document's number; the deal's edit / print / delete then work on THAT number (never another one)"""
    import random
    import threading
    import time
    from simulation.erp import SimERP
    from simulation.real import PROBE_WRITE

    seen = []

    class FakeWriter(SimERP):
        mode, is_async, real_writes = "حقيقي", True, True

        def allowed(self, emp, key):
            return True

        def pending(self):
            return 0

        def perform_async(self, key, emp, task, cb):
            act = task.get("action") or "open"
            seen.append((key, act, task.get("doc_key") or key, task.get("doc_no")))
            order.append((key, act, (task.get("want") or {}).get("based")))
            r = {"kind": "ok", "ms": 500, "msg": "", "did": "open"}
            if act == "open" and key in ("attendance", "cash_count", "stock_check", "approval", "journal_review", "trial_balance", "sales_report",
                                         "account_statement", "customer_statement"):
                pass                                                   # these screens are only opened
            elif act == "open":
                r["did"] = "write"
                r["doc_no"] = f"{PROBE_WRITE.get(key, (key,))[0]}-{len(seen)}"      # a test document lives on its base screen
                r["facts"] = {"no": r["doc_no"], "party": task.get("want", {}).get("party") or "شركة حقيقية", "item": "صنف من الموقع",
                              "qty": 2.0, "price": 50.0, "total": 115.0}
            threading.Thread(target=cb, args=(r,)).start()

    order, checked = [], []
    for seed in (2, 7, 11):
        seen.clear()
        order.clear()
        c = Company(seed=seed, use_settings=False)
        c.make_erp = lambda: FakeWriter(random.Random(seed))
        c.control("speed", 30)
        c.control("start")
        deadline = time.time() + 45
        while (c.running or not c.report) and time.time() < deadline:
            time.sleep(0.2)
        assert c.report
        ops = [x for x in seen if x[1] in ("edit", "print", "delete")]
        assert ops
        for key, act, dk, no in ops:
            assert no and no.startswith(key + "-"), (key, act, no)       # a number this company made on that screen
        started = [d for d in c.deals.values() if d.get("real") and not d.get("round")]
        assert started and all(d["customer"] == "شركة حقيقية" and d["item"] == "صنف من الموقع" for d in started)
        assert any("سجلت على السيستم" in m["text"] and "شركة حقيقية" in m["text"] for m in c.chat)
        assert not any(cust in m["text"] for m in c.chat for cust in c.cfg["customers"])     # no invented customer in the chat
        said = " ".join(m["text"] for m in c.chat)
        assert "رفعت ملف البصمة" not in said and "الحضور اتسجل" not in said            # only opened → nobody says it was uploaded
        assert "اعتمدتها" not in said and "تمام، الفاتورة معتمدة" not in said
        assert not any(sup in said for sup in c.cfg["suppliers"])                      # no invented supplier either
        # the round's purchase order is made FROM the round's own purchase request, which isn't deleted before that
        pr = next((d for d in c.deals.values() if d.get("round") == "purchase_request"), None)
        po = [i for i, (k, a, b) in enumerate(order) if k == "purchase_order" and a == "open" and b]
        if pr and (pr.get("docs") or {}).get("purchase_request") and any(d.get("round") == "purchase_order" for d in c.deals.values()):
            checked.append(1)
            assert po and order[po[0]][2] == {"FromPurchaseRequest": pr["docs"]["purchase_request"]}
            dels = [i for i, (k, a, b) in enumerate(order) if k == "purchase_request" and a == "delete"]
            assert not dels or dels[0] > po[0]
        for d in c.deals.values():
            if d.get("docs"):
                assert all(v.startswith(k.replace("_dup", "") + "-") for k, v in d["docs"].items())
    assert checked                                                     # the round's request → order chain really ran


def test_problem_sources():
    """each problem says where it came from — only the system's own go to the developers"""
    from simulation.sources import classify
    assert classify("رفض", "net::ERR_INTERNET_DISCONNECTED") == "net"
    assert classify("النت فصل", "النت فصل عند الجهاز") == "net"
    assert classify("مشكلة في الأداة", "الأداة: element not interactable") == "tool"
    assert classify("خطأ سيستم", "x", tool=True) == "tool"
    assert classify("رفض", "بيانات أساسية ناقصة في الموقع: «انواع عروض الأسعار» مفيهاش ولا اختيار") == "data"
    assert classify("صلاحيات", "مالوش صلاحية على فواتير البيع") == "data"
    assert classify("خطأ سيستم", "Server Error in '/' Application") == "erp"
    assert classify("رفض", "لم يتم الحفظ !") == "erp"
    assert classify("بيانات غلط", "ميزان المراجعة مش متزن — حركة الفترة") == "erp"
    assert classify("بطء", "فتحت في 12.0 ث") == "erp"
    assert classify("ضغط شغل", "عندي 5 مهام") == "work"
    assert classify("رفض", "السيستم رفض: «JS: السداد الالى»", "رسائل السيستم: SweetAlert: تجاوز الحد الائتماني للمندوب") == "data"   # the rep's limit = a setting
    assert classify("رفض", "SweetAlert: لم يتم الحفظ — لا يمكن تعديل المستودع في سند تحويل محفوظ") == "data"                   # NQ ERP's rule, the tool's edit
    assert classify("رفض", "SweetAlert: لقد تجاوز العميل الحد الائتمانى الخاص به") == "erp"
    from simulation.real.probes import LIST_RE, ACTION_RE
    assert LIST_RE.match("/SalesInvoice") and LIST_RE.match("/X/Index") and LIST_RE.match("/DismantlingVoucher/?typeId=1")
    assert not LIST_RE.match("/Report/Sales") and not LIST_RE.match("/X/AddEdit") and not LIST_RE.match("/?show=False")
    assert ACTION_RE.search("/Account/LogOut") and ACTION_RE.search("/BackupandDataRecovery") and not ACTION_RE.search("/SalesInvoice")
    from simulation.report import report_html
    c = Company(seed=4, use_settings=False)
    r = c.run_fast()
    assert all(x.get("source") for x in c.complaints)
    assert sum(x["n"] for x in r["by_source"]) == len(c.complaints)
    assert "المشاكل حسب مصدرها" in report_html(r)


def test_ledger_only_our_documents():
    """the only thing between the tool and other people's documents: exactly our site + screen + number, not deleted"""
    from simulation.real import writer
    from simulation.real.writer import Ledger
    assert str(writer.LEDGER).startswith(os.environ["VC_RUNS"])
    Ledger.add("s1", "quotation", 12, "e1", "D-001")
    assert Ledger.ours("s1", "quotation", "12") and Ledger.ours("s1", "quotation", 12)
    assert not Ledger.ours("s2", "quotation", "12") and not Ledger.ours("s1", "sales_order", "12") and not Ledger.ours("s1", "quotation", "112")
    Ledger.deleted("s1", "quotation", "12")
    assert not Ledger.ours("s1", "quotation", "12")


def test_problem_key_same_everywhere():
    from simulation.sources import problem_key
    assert problem_key("فواتير البيع", "فتحت في 12.3 ث") == problem_key("فواتير البيع", "فتحت في 14.1 ث")
    assert problem_key("فواتير البيع", "x") != problem_key("سندات القبض", "x")


def test_it_speed_round():
    """🐢 Fahd's speed round: slow lists (> 8 s) and lists twice as slow as this morning are problems; fast ones pass"""
    from simulation.real import probes
    menu = [{"path": p} for p in ("/SalesInvoice/Index", "/ItemCard/Index", "/Customer/Index", "/Report/Sales", "javascript:void(0)")]
    am = {"/SalesInvoice/Index": 2000, "/ItemCard/Index": 3000, "/Customer/Index": 1500}
    orig = probes._open_list
    try:
        probes._open_list = lambda s, p, **k: ("rows", am[p], "")
        r, times = probes.it_speed(None, menu)
        assert r["kind"] == "ok" and times == am                                       # the report screen isn't a list
        pm = {**am, "/ItemCard/Index": 9500, "/Customer/Index": 4000}
        probes._open_list = lambda s, p, **k: ("rows", pm[p], "")
        r, _ = probes.it_speed(None, menu, before=am)
        assert r["kind"] == "wrong" and "/ItemCard/Index" in r["evidence"] and "الصبح 1.5" in r["evidence"]
    finally:
        probes._open_list = orig
    c = Company(seed=2, use_settings=False)
    c.run_fast()
    assert any(t.get("probe") == "it_speed" for t in c.timeline)                         # Fahd runs it in the simulated day too


def test_dashboard_pages():
    """inside the dashboard: /simulation behind the login, /demo public (simulation only, no settings), pages call their own prefix"""
    import re
    from web.app import app
    c = app.test_client()
    assert c.get("/simulation/").status_code == 302 and c.get("/simulation/api/state").status_code == 401
    html = c.get("/demo/").get_data(as_text=True)
    assert "/demo/api/state" in html and not re.findall(r"""["'`(]/(?:api/|report|tickets|settings|i18n)""", html)
    assert c.get("/demo/settings").status_code == 403 and c.get("/demo/api/settings").status_code == 403
    demo = app.blueprints["demo"].company
    assert not demo.use_settings and demo.runs.name == "simulation_demo"


def test_problems_to_developer_support():
    """real days' NQ ERP problems → «دعم المطورين»: one item per problem across days, never from a simulated day"""
    import json as _j
    from datetime import date
    from simulation import support as SP
    from simulation.settings import RUNS
    RUNS.mkdir(parents=True, exist_ok=True)
    tk = lambda txt, typ="بيانات غلط": {"screen": "سند القبض", "type": typ, "text": txt, "name": "منى", "job": "أمينة صندوق", "action": "add", "source": "erp"}
    (RUNS / "day_29990101_000001.json").write_text(_j.dumps({"date": str(date.today()), "mode": "حقيقي", "tickets": [tk("الإجمالي '247' اتسجل '1235'"), tk("الإجمالي '304' اتسجل '1520'")]}), encoding="utf-8")
    (RUNS / "day_29990101_000002.json").write_text(_j.dumps({"date": str(date.today()), "mode": "محاكاة", "tickets": [tk("simulated")]}), encoding="utf-8")
    items = [x for x in SP.support_issues() if "اتسجل" in x["title"] or "simulated" in x["title"]]     # other tests' days share this folder
    assert len(items) == 1 and items[0]["times"] == 2 and items[0]["severity"] == "عالية" and items[0]["source"].endswith("الشركة الافتراضية")


def test_books_check():
    """📒 the accountant's daily books: an unbalanced entry and a saved document with no entry are problems; a clean day passes"""
    from datetime import date
    from simulation.real import probes
    from simulation.real.writer import Ledger
    today = date.today().isoformat()
    Ledger.add("bk", "sales_invoice", "901", "e", "D")
    Ledger.add("bk", "receipt_voucher", "902", "e", "D")
    Ledger.add("bk", "quotation", "903", "e", "D")                     # a quotation makes no entry: not asked for

    class Drv:
        def __init__(self, data): self.data = data
        def set_script_timeout(self, s): pass
        def execute_async_script(self, js, *a):
            assert "all: all.map(" in js                              # the journal reader was widened to return every entry
            return self.data

    class Ses:
        def __init__(self, data): self.driver = Drv(data)
        def open(self, p): return {}
    ok = {"ok": True, "s": 200, "all": [{"doc": "901", "type": "فاتورة", "d": 115, "c": 115}, {"doc": "902", "type": "قبض", "d": 50, "c": 50}], "bad": []}
    assert probes.books_check(Ses(ok), "bk", today)["kind"] == "ok"
    bad = {"ok": True, "s": 200, "all": [{"doc": "901", "type": "فاتورة", "d": 115, "c": 100}], "bad": [{"doc": "901", "type": "فاتورة", "d": 115, "c": 100, "diff": 15}]}
    r = probes.books_check(Ses(bad), "bk", today)
    assert r["kind"] == "wrong" and "مش متزن" in r["msg"] and "مالوش قيد" in r["msg"] and "902" in r["evidence"] and "903" not in r["evidence"]
    assert probes.books_check(Ses({"ok": False, "s": 500}), "bk", today)["kind"] == "skip"
