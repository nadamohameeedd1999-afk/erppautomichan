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


def test_report_perf_cycle(run_cli, mock_erp):
    r = run_cli("check", {**TRIAL, "asserts": []})
    assert r.get("success"), r.get("error")
    assert r["values"]["مدين"] > 0
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


def test_auto_full(run_cli):
    """the automatic full test: rejected empty / required missing, add (required only, all fields), edit, print, delete"""
    inv = invoice("st_auto_inv", [item(), UPLOAD])
    inv["fields"] = [{**CUST, "required": True},
                     {"id": "Notes", "label": "ملاحظات", "kind": "textarea", "strategy": "fixed", "value": "آلي {ts}"}]
    r = run_cli("check", {"key": "st_auto", "type": "auto", "name_ar": "آلي", "screen": "st_auto_inv"}, defs=[inv])
    assert r.get("success"), r.get("error")
    rows = r["detail"]["rows"]
    # read the form · add · numbering · edit · print · delete — all on the same record
    assert len(rows) == 6 and all(x["ok"] for x in rows), rows
    assert "إجباري" in rows[0]["cells"][2] and "العميل" in rows[0]["cells"][2]


def test_auto_like_real_cash_receipt(run_cli, mock_erp):
    """no Screen Builder setup; «العميل» / «بناء على» show up after other choices, the amount's handler throws
    (setEquivalent is not defined), attachments must be chosen and uploaded — add / edit / print / delete must all pass"""
    import json
    from pathlib import Path
    st = Path(mock_erp["DATA_DIR"]) / "settings"
    st.mkdir(parents=True, exist_ok=True)
    (st / "discovered_screens.json").write_text(json.dumps({"screens": [
        {"key": "d_cr2", "name": "سند قبض", "name_en": "CR2", "group": "الحسابات", "url": "/CashReceipt2"}]}, ensure_ascii=False), encoding="utf-8")
    r = run_cli("check", {"key": "st_auto_cr2", "type": "auto", "name_ar": "آلي", "screen": "d_cr2", "fields_mode": "required"})
    assert r.get("success"), r.get("error")
    rows = r["detail"]["rows"]
    assert len(rows) == 6 and all(x["ok"] for x in rows), rows
    assert "الترقيم سليم" in rows[2]["cells"][2] and "اتحذف" in rows[2]["cells"][2], rows[2]
    assert "بناء على" in rows[1]["cells"][2] and "قارنت" in rows[1]["cells"][2]


def _flags(**kw):
    import urllib.request
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    op.open("http://127.0.0.1:5055/__flags?" + "&".join(f"{k}={int(v)}" for k, v in kw.items())).read()


def test_numbering_duplicate(run_cli, mock_erp):
    """the ERP gives the 2nd record the same document number -> the numbering test fails and says so"""
    import json
    from pathlib import Path
    st = Path(mock_erp["DATA_DIR"]) / "settings"
    st.mkdir(parents=True, exist_ok=True)
    (st / "discovered_screens.json").write_text(json.dumps({"screens": [
        {"key": "d_cr2", "name": "سند قبض", "name_en": "CR2", "group": "الحسابات", "url": "/CashReceipt2"}]}, ensure_ascii=False), encoding="utf-8")
    _flags(dupnum=1)
    try:
        r = run_cli("check", {"key": "st_num", "type": "auto", "name_ar": "ترقيم", "screen": "d_cr2", "fields_mode": "required",
                              "ways": ["add", "number"]})
    finally:
        _flags(dupnum=0)
    assert not r.get("success")
    rows = r["detail"]["rows"]
    assert rows[1]["ok"] and not rows[2]["ok"], rows
    assert "اتكرر" in rows[2]["cells"][2], rows[2]


def test_system_health(run_cli, mock_erp):
    """every menu link opened; broken ones (500 / 404) listed, then «fixed» when they come back; activity / branch login"""
    cfg = {"key": "st_health", "type": "health", "name_ar": "صحة"}
    r = run_cli("check", cfg)
    assert r.get("success"), r.get("error")
    assert r["health"]["broken"] == 0 and r["health"]["total"] >= 4, r["health"]
    assert not any("/Support/Tickets" in x["cells"][3] for x in r["detail"]["rows"])        # skipped
    _flags(broken=1)
    try:
        r = run_cli("check", cfg)
    finally:
        _flags(broken=0)
    assert not r.get("success")
    rows = {x["cells"][3]: x for x in r["detail"]["rows"] if not x["cells"][0].startswith("🔀")}
    assert "500" in rows["/RentalAssets/Contracts"]["cells"][4] and "SqlException" in rows["/RentalAssets/Contracts"]["cells"][4], rows
    assert "404" in rows["/GoneScreen"]["cells"][4] and rows["/GoneScreen"]["cells"][0].startswith("🆕"), rows
    r = run_cli("check", cfg)
    assert r.get("success") and len(r["health"]["fixed"]) == 2, r
    # before / after an ERP update: the customer add form gets a new required field
    from engine import health  # noqa
    import json, glob
    f = glob.glob(mock_erp["DATA_DIR"] + "/**/health_*.json", recursive=True)
    assert f, "no health state"
    import subprocess, sys
    _flags(update=1)
    try:
        r = run_cli("check", cfg)
    finally:
        _flags(update=0)
    ch = [x for x in r["detail"]["rows"] if x["cells"][0].startswith("🔀")]
    assert any("الرقم الضريبي" in x["cells"][4] and "/Customer" == x["cells"][3] for x in ch), r["detail"]["rows"]
    # login on another activity / branch (the profile says which; «2» matches «٢»)
    r = run_cli("check", cfg, env={"LOGIN_ACTIVITY": "النخبه", "LOGIN_BRANCH": "الفرع 2"})
    assert r.get("success"), r.get("error")
    assert "النخبه" in r["detail"]["note"]
    r = run_cli("check", cfg, env={"LOGIN_ACTIVITY": "نشاط مش موجود"})
    assert not r.get("success") and "مش موجود" in r.get("error", ""), r.get("error")


def test_books_balanced(run_cli, mock_erp):
    """⚖️ trial balance read from the site: balanced -> pass; an unbalanced entry -> fail with the difference"""
    cfg = {"key": "st_books", "type": "books", "name_ar": "مطابقة"}
    r = run_cli("check", cfg)
    assert r.get("success"), r.get("error")
    assert len(r["detail"]["rows"]) == 4 and all(x["ok"] for x in r["detail"]["rows"])
    _flags(unbalanced=1)
    try:
        r = run_cli("check", cfg)
    finally:
        _flags(unbalanced=0)
    assert not r.get("success")
    assert "الفرق 900.00" in r["error"], r["error"]
