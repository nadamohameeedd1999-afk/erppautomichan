"""Full runs against the fake ERP (Chrome)."""
CUST = {"id": "CustomerId", "label": "العميل", "kind": "select2", "strategy": "fixed", "value": "11 - الريادة"}


def item(match="", cell="css:input.price", price="100"):
    return {"name": "إضافة صنف", "after": "CustomerId", "steps": [
        {"do": "click", "target": "css:span.Add-Button"}, {"do": "wait_popup"}, {"do": "click", "target": "#submitSearch"},
        {"do": "wait_rows", "min": 1}, {"do": "row_click", "target": "css:button[onclick='chooseItem(this)']", "match": match},
        {"do": "close_popup", "optional": True}, {"do": "fill_cell", "cell": cell, "row": "last", "value": price}]}


UPLOAD = {"name": "مرفق", "after": "CustomerId", "steps": [{"do": "upload", "target": "المرفقات", "file": "pdf"}]}


def invoice(key, flows, **kw):
    return {"key": key, "name_ar": key, "list_url": "/SalesInvoice", "add_url": "/SalesInvoice/AddEdit",
            "save_button": "button#save", "fields": [dict(CUST)], "flows": flows, **kw}


def test_items_upload_checks_edit_print(run_cli):
    cfg = invoice("st_full", [item(), item("أسمنت", "السعر", "250"), UPLOAD,
        {"name": "حسابات", "after": "CustomerId", "steps": [
            {"do": "assert", "expr": "{sum:الإجمالي} = {NetTotal}"},
            {"do": "assert", "expr": "{VatTotal} = {NetTotal} * 0.15"},
            {"do": "assert", "expr": "{NetTotal} = 350"}]},
        {"name": "تعديل وطباعة", "after": "__after_save__", "steps": [
            {"do": "row_click", "target": "تعديل", "match": "{var:saved_no}"},
            {"do": "fill", "field": {"id": "Notes", "label": "ملاحظات", "kind": "textarea", "strategy": "fixed", "value": "معدل {var:saved_no}"}},
            {"do": "click", "target": "#save"}, {"do": "wait", "seconds": 2},
            {"do": "expect_text", "target": "معدل {var:saved_no}"},
            {"do": "check_print", "target": "طباعة", "match": "{var:saved_no}"}]}])
    r = run_cli("run", cfg)
    assert r.get("success"), r.get("error")
    assert r["vars"].get("saved_no")


def test_popup_link_documents(run_cli):
    r = run_cli("inspect-popup", invoice("st_pop", []), "--open", "ربط بمستند اخر", "--after", "CustomerId",
                "--choose", "سندات صرف المخازن")
    assert r.get("success"), r.get("error")
    assert r["rows"] >= 1
    labels = [f["label"] for f in r["popup_fields"]]
    assert "نوع المستند" in labels
    cfg = invoice("st_link", [r["flow"]])
    run = run_cli("run", cfg)
    assert run.get("success"), run.get("error")


def test_negative_and_chain(run_cli):
    neg = invoice("st_neg", [], expect_error="يجب إضافة أصناف")
    r = run_cli("run", invoice("st_chain", [item(), UPLOAD], run_before=["st_neg"]), defs=[neg])
    assert r.get("success"), r.get("error")


def test_discover(run_cli):
    r = run_cli("discover", None, "--no-save")
    assert r.get("success"), r.get("error")
    names = [s["name"] for s in r["screens"]]
    assert "العملاء" in names
    assert all(o["name"] != "فواتير البيع" for o in r["other"])
    assert r.get("report_id") and all(s.get("name_en") for s in r["screens"])


def test_edit_print_delete(run_cli):
    """the operations beside «إضافة جديد»: chain add -> edit -> print -> delete on the same new invoice"""
    add = invoice("st_op_add", [item(), UPLOAD])
    edit = {**invoice("st_op_edit", []), "operation": "edit", "target_row": "{var:saved_no}",
            "fields": [{"id": "Notes", "label": "ملاحظات", "kind": "textarea", "strategy": "fixed", "value": "معدل {var:saved_no}"}],
            "verify": {"open_saved": True}}
    prn = {**invoice("st_op_print", []), "operation": "print", "target_row": "{var:saved_no}", "fields": []}
    dele = {**invoice("st_op_del", []), "operation": "delete", "target_row": "{var:saved_no}", "fields": [],
            "run_before": ["st_op_add", "st_op_edit", "st_op_print"]}
    r = run_cli("run", dele, defs=[add, edit, prn])
    assert r.get("success"), r.get("error")
    # negative: a posted invoice can't be deleted
    neg = {**invoice("st_op_neg", []), "operation": "delete", "target_row": "500", "fields": [],
           "expect_error": "لا يمكن حذف فاتورة مرحلة"}
    r = run_cli("run", neg)
    assert r.get("success"), r.get("error")


# ---------------------------------------------------------------- advanced tests (اختبارات متقدمة)
CRV = {"key": "st_crv", "name_ar": "سند قبض", "list_url": "/CashReceiptVoucher", "add_url": "/CashReceiptVoucher/AddEdit",
       "fields": [{"id": "SourceTypeId", "label": "نوع المصدر", "kind": "select2", "strategy": "fixed", "value": "عميل"},
                  {"id": "CustomerId", "label": "العميل", "kind": "select2", "strategy": "fixed", "value": "11 - الريادة",
                   "depends_on": "SourceTypeId"},
                  {"id": "ProjectId", "label": "المشروع", "kind": "select2", "strategy": "keep"},
                  {"id": "CashReceiptPaymentMethodId", "label": "طريقة الدفع", "kind": "select2", "strategy": "first"},
                  {"id": "MoneyAmount", "label": "المبلغ", "kind": "number", "strategy": "fixed", "value": "250"}]}
JOURNAL = {"name": "القيد", "after": "__after_save__", "steps": [
    {"do": "check_journal", "target": "القيد", "match": "{var:saved_no}", "accounts": "الصندوق, الريادة", "amount": "250"}]}
TRIAL = {"key": "st_trial", "type": "report", "name_ar": "ميزان المراجعة", "url": "/Reports/Trial",
         "fields": [{"id": "DateFrom", "label": "من", "kind": "date", "strategy": "fixed", "value": "2026-01-01"}],
         "show_button": "عرض", "values": [{"name": "مدين", "ref": "sum:مدين"}, {"name": "دائن", "ref": "sum:دائن"}],
         "asserts": ["{sum:مدين} = {sum:دائن}"]}


def _save_check(run_cli_env, cfg):
    import json
    from pathlib import Path
    d = Path(run_cli_env["DEFS_DIR"]) / "checks"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{cfg['key']}.json").write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")


def test_journal_entry(run_cli):
    r = run_cli("run", {**CRV, "flows": [JOURNAL]})
    assert r.get("success"), r.get("error")
    assert "متزن" in str(r["steps"][-1]["result"])
    bad = {**CRV, "key": "st_crv_bad", "flows": [JOURNAL], "fields": CRV["fields"] + [
        {"id": "Notes", "label": "ملاحظات", "kind": "textarea", "strategy": "fixed", "value": "قيد-خطأ"}]}
    r = run_cli("run", bad)
    assert not r.get("success") and "مش متزن" in r.get("error", "")


def test_report_permission_perf_cycle(run_cli, mock_erp):
    r = run_cli("check", {**TRIAL, "asserts": []})
    assert r.get("success"), r.get("error")
    assert r["values"]["مدين"] > 0
    perm = {"key": "st_perm", "type": "permission", "name_ar": "صلاحيات", "username": "viewer", "password": "pw2",
            "expect": [{"url": "/CashReceiptVoucher", "allowed": False}, {"url": "/CashReceiptVoucher/AddEdit", "allowed": False},
                       {"url": "/Customer", "allowed": True}]}
    r = run_cli("check", perm)
    assert r.get("success"), r.get("error")
    r = run_cli("check", {**perm, "expect": [{"url": "/Customer", "allowed": False}]})
    assert not r.get("success") and "مفتوحة" in r.get("error", "")
    perf = {"key": "st_perf", "type": "perf", "name_ar": "سرعة", "pages": [{"url": "/Customer", "name": "العملاء"}], "times": 1}
    assert run_cli("check", perf).get("success")
    import urllib.request
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    op.open("http://127.0.0.1:5055/__slow?ms=2500").read()
    try:
        r = run_cli("check", perf)
    finally:
        op.open("http://127.0.0.1:5055/__slow?ms=0").read()
    assert not r.get("success") and "أبطأ" in r.get("error", "")
    _save_check(mock_erp, {**TRIAL, "asserts": []})
    cyc = {"key": "st_cycle", "type": "cycle", "name_ar": "دورة", "steps": [{"key": "st_crv"}, {"key": "st_trial"}]}
    r = run_cli("check", cyc, defs=[CRV])
    assert r.get("success"), r.get("error")
    assert len(r["detail"]["rows"]) == 2 and all(x["ok"] for x in r["detail"]["rows"])
