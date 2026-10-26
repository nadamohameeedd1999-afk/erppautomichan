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
    qm.add("a", f"{S}[sales_invoice]", "a")
    qm.add("b", f"{S}[sales_invoice]", "b")          # same screen -> waits
    qm.add("c", f"{S}[cash_receipt]", "c")
    import time
    time.sleep(0.3)
    assert sorted(qm.running) == ["a", "c"] and [t["task_id"] for t in qm.queue] == ["b"]
