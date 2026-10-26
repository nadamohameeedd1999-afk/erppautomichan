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
    r = run_cli("discover")
    assert r.get("success"), r.get("error")
    names = [s["name"] for s in r["screens"]]
    assert "العملاء" in names
    assert all(o["name"] != "فواتير البيع" for o in r["other"])
