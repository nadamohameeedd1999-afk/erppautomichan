"""Fake NQ ERP (login, cash receipt, customer, sales invoice with items / link documents / attachments, edit, print)
used by selftest/ to check the engine. Run: npm install && python mock_erp.py  (http://127.0.0.1:5055, erpadmin / pw)"""
from pathlib import Path
import json
from datetime import date, timedelta
from flask import Flask, request, redirect, jsonify, send_from_directory, make_response

HERE = Path(__file__).resolve().parent
NM = HERE / "node_modules"
app = Flask(__name__)
VOUCHERS = [{"no": 100, "customer": "11 - الريادة", "amount": "50.00", "data": {}}]

LIBS = """
<link rel="stylesheet" href="/lib/select2/dist/css/select2.min.css">
<script src="/lib/jquery/dist/jquery.min.js"></script>
<script src="/lib/select2/dist/js/select2.min.js"></script>
<script src="/lib/sweetalert2/dist/sweetalert2.all.min.js"></script>
<style>body{font-family:sans-serif} .form-group{margin:10px} .select2-container{min-width:260px}
#preloader{position:fixed;inset:0;background:#fff8;display:none}</style>
"""

CUSTOMERS = {"1": [("4", "4 - هوليداي إن العليا"), ("11", "11 - الريادة"), ("12", "12 - شركة النور")],
             "2": [("201", "201 - مورد الحديد")]}
PROJECTS = {"4": [("23", "23 - مشروع بناء برج الرياض"), ("24", "24 - صيانة الفندق")], "12": [("30", "30 - مشروع النور")]}


@app.route("/lib/<path:p>")
def lib(p):
    return send_from_directory(NM, p)


@app.route("/Login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("userName") == "erpadmin" and request.form.get("password") == "pw":
            r = make_response(redirect("/Home"))
            r.set_cookie("auth", "1")
            return r
        return redirect("/Login")
    return f"""<!doctype html><html dir=rtl><head><meta charset=utf-8>{LIBS}</head><body>
    <form method=post action=/Login>
      <input id=userName name=userName><input id=password name=password type=password>
      <select id=cmbact name=act><option value="">اختر</option><option value=1>النشاط الرئيسي</option></select>
      <select id=cmbbranch name=branch><option value="">اختر</option><option value=1>الفرع الرئيسي</option></select>
      <button class="btn-login" type=submit>دخول</button>
    </form><script>$('select').select2();</script></body></html>"""


def guard():
    return request.cookies.get("auth") == "1"


@app.route("/Home")
def home():
    if not guard():
        return redirect("/Login")
    return """<html dir=rtl><head><meta charset=utf-8></head><body>
    <aside class="sidebar"><ul>
      <li><span>المبيعات</span><ul><li><a href="/SalesInvoice">فواتير البيع</a></li><li><a href="/Customer">العملاء</a></li></ul></li>
      <li><span>الحسابات العامة</span><ul><li><a href="/CashReceiptVoucher">سند القبض</a></li><li><a href="/Reports/Trial">ميزان المراجعة</a></li></ul></li>
      <li><a href="#">بدون رابط</a></li><li><a href="/Logout">خروج</a></li>
    </ul></aside><main>home</main></body></html>"""


@app.route("/Reports/Trial")
def trial():
    return "<html><body><h1>ميزان المراجعة</h1><p>تقرير</p></body></html>" if guard() else redirect("/Login")


@app.route("/CashReceiptVoucher")
def crv_list():
    if not guard():
        return redirect("/Login")
    rows = "".join(f"<tr><td>{v['no']}</td><td>{v['customer']}</td><td>{v['amount']}</td><td><a href='/CashReceiptVoucher/AddEdit?id={v['no']}'>تعديل</a></td></tr>" for v in reversed(VOUCHERS))
    return f"""<!doctype html><html dir=rtl><head><meta charset=utf-8></head><body>
    <nav><input type=text id=globalSearch placeholder=بحث></nav>
    <a class="btn" href="/CashReceiptVoucher/AddEdit">إضافة جديد</a>
    <table><thead><tr><th>رقم</th><th>العميل</th><th>المبلغ</th></tr></thead><tbody>{rows}</tbody></table></body></html>"""


@app.route("/api/customers")
def api_customers():
    return jsonify(CUSTOMERS.get(request.args.get("source", ""), []))


@app.route("/api/projects")
def api_projects():
    return jsonify(PROJECTS.get(request.args.get("customer", ""), []))


@app.route("/CashReceiptVoucher/AddEdit", methods=["GET", "POST"])
def crv_add():
    if not guard():
        return redirect("/Login")
    if request.method == "POST":
        f = request.form
        cust = dict(sum(CUSTOMERS.values(), [])).get(f.get("CustomerId"), "?")
        VOUCHERS.append({"no": VOUCHERS[-1]["no"] + 1, "customer": cust, "amount": f"{float(f.get('MoneyAmount') or 0):.2f}", "data": dict(f)})
        return redirect("/CashReceiptVoucher")
    vid = request.args.get("id")
    rec = next((v for v in VOUCHERS if str(v["no"]) == str(vid)), None) if vid else None
    pre = json.dumps((rec or {}).get("data") or {})
    return f"""<!doctype html><html dir=rtl><head><meta charset=utf-8>{LIBS}</head><body>
    <script>window.PREFILL = {pre};</script>
    <div id=preloader></div>
    <form id=frm method=post action="/CashReceiptVoucher/AddEdit">
      <input type=hidden name=__RequestVerificationToken value=x><input type=hidden id=Id name=Id value=0>
      <div class=form-group><label for=VoucherDate>التاريخ</label><input id=VoucherDate name=VoucherDate class=datepicker value="2026-10-20"></div>
      <div class=form-group><label for=SourceTypeId>نوع المصدر <span class=text-danger>*</span></label>
        <select id=SourceTypeId name=SourceTypeId data-val-required="مطلوب"><option value="">--اختر--</option><option value=1>عميل</option><option value=2>مورد</option></select></div>
      <div class=form-group id=custBox style="display:none"><label for=CustomerId>العميل</label>
        <select id=CustomerId name=CustomerId data-val-required="مطلوب"><option value="">--اختر--</option></select></div>
      <div class=form-group><label for=ProjectId>المشروع</label>
        <select id=ProjectId name=ProjectId data-val-required="المشروع مطلوب"><option value="">--اختر--</option></select>
        <span class="field-validation-error" id=projErr style="display:none">المشروع مطلوب</span></div>
      <div class=form-group><label for=CashReceiptPaymentMethodId>طريقة الدفع</label>
        <select id=CashReceiptPaymentMethodId name=CashReceiptPaymentMethodId data-val-required="مطلوب"><option value="">--اختر--</option><option value=1>1 - نقدى</option><option value=2>2 - شيك</option></select></div>
      <div class=form-group><label for=MoneyAmount>المبلغ</label><input id=MoneyAmount name=MoneyAmount type=number data-val-required="مطلوب"></div>
      <div class=form-group><label for=Notes>ملاحظات</label><textarea id=Notes name=Notes></textarea></div>
      <table><tr><td><input id=LineQty name=LineQty></td></tr></table>
    </form>
    <button id=autoPay type=button style="display:none">سداد الى</button>
    <button id=save type=button>حفظ</button>
    <script>
    $('select').select2();
    $('#SourceTypeId').on('change', function () {{
      $('#custBox').toggle(!!this.value);
      $.getJSON('/api/customers', {{source: this.value}}, function (rows) {{
        var s = $('#CustomerId').empty().append('<option value="">--اختر--</option>');
        rows.forEach(function (r) {{ s.append(new Option(r[1], r[0])); }});
        s.trigger('change.select2');
      }});
    }});
    $('#CustomerId').on('change', function () {{
      var v = this.value;
      setTimeout(function () {{
        $.getJSON('/api/projects', {{customer: v}}, function (rows) {{
          var s = $('#ProjectId').empty().append('<option value="">--اختر--</option>');
          rows.forEach(function (r) {{ s.append(new Option(r[1], r[0])); }});
          s.trigger('change.select2');
        }});
      }}, 700);
    }});
    $('#autoPay').on('click', function () {{ alert('تم توزيع المبلغ'); }});
    if (window.PREFILL && PREFILL.SourceTypeId) {{
      $('#SourceTypeId').val(PREFILL.SourceTypeId).trigger('change');
      setTimeout(function () {{ $('#CustomerId').val(PREFILL.CustomerId).trigger('change.select2'); }}, 800);
      $('#CashReceiptPaymentMethodId').val(PREFILL.CashReceiptPaymentMethodId).trigger('change.select2');
      $('#MoneyAmount').val(PREFILL.MoneyAmount);
    }}
    $('#save').on('click', function () {{
      if (!$('#ProjectId').val() && $('#ProjectId option').length > 1) {{ $('#projErr').show(); Swal.fire({{icon: 'error', title: 'خطأ', text: 'برجاء استكمال البيانات'}}); return; }}
      Swal.fire({{icon: 'question', title: 'هل تريد الحفظ؟', showCancelButton: true}}).then(function (r) {{
        if (r.isConfirmed) $('#frm').submit();
      }});
    }});
    </script></body></html>"""


@app.route("/Customer")
def cust_list():
    if not guard():
        return redirect("/Login")
    rows = "".join(f"<tr><td>{n}</td></tr>" for _, n in reversed(CUSTOMERS["1"]))
    return f"""<!doctype html><html dir=rtl><head><meta charset=utf-8></head><body>
    <a class="btn" href="/Customer/AddEdit">إضافة</a><table><tbody>{rows}</tbody></table></body></html>"""


@app.route("/Customer/AddEdit", methods=["GET", "POST"])
def cust_add():
    if not guard():
        return redirect("/Login")
    if request.method == "POST":
        name = request.form.get("Name", "").strip()
        if name:
            CUSTOMERS["1"].append((str(100 + len(CUSTOMERS["1"])), name))
        return redirect("/Customer")
    return f"""<!doctype html><html dir=rtl><head><meta charset=utf-8>{LIBS}</head><body>
    <form id=frm method=post action="/Customer/AddEdit"><label for=Name>اسم العميل</label>
    <input id=Name name=Name data-val-required="مطلوب"></form>
    <button id=save type=button onclick="document.getElementById('frm').submit()">حفظ</button></body></html>"""


INVOICES = [{"no": 500, "customer": "11 - الريادة", "lines": 1}]
D = lambda n: (date.today() - timedelta(days=n)).isoformat()
DOCS = [("SO-901", D(0), "الفرع الاول", "صرف 10 حديد"), ("SO-902", D(1), "الفرع الاول", "صرف 4 أسمنت"),
        ("SO-777", D(120), "الفرع الاول", "قديم")]
ORDERS = [("OR-55", D(0), "الفرع الاول", "أمر بيع 55")]


@app.route("/SalesInvoice")
def si_list():
    if not guard():
        return redirect("/Login")
    rows = "".join(f"<tr><td>{v['no']}</td><td>{v['customer']}</td><td>{v['lines']} سطر</td><td>{v.get('notes','')}</td>"
                   f"<td><a class='btn' title='تعديل' href='/SalesInvoice/Edit/{v['no']}'>تعديل</a> "
                   f"<a class='btn' href='/SalesInvoice/Print/{v['no']}' target='_blank'>طباعة</a> "
                   f"<button type=button class='btn' title='حذف' onclick='delInv({v['no']})'><i class='fa fa-trash'></i></button></td></tr>"
                   for v in reversed(INVOICES))
    return f"""<!doctype html><html dir=rtl><head><meta charset=utf-8>{LIBS}</head><body>
    <a class="btn" href="/SalesInvoice/AddEdit">إضافة</a><table><tbody>{rows}</tbody></table>
    <script>function delInv(no){{ Swal.fire({{title: 'هل أنت متأكد من الحذف؟', icon: 'warning', showCancelButton: true}}).then(function(r){{
      if (!r.isConfirmed) return;
      $.post('/SalesInvoice/Delete/' + no, function(j){{
        Swal.fire({{title: j.ok ? 'تم الحذف' : j.error, icon: j.ok ? 'success' : 'error'}}).then(function(){{ location.reload(); }}); }}); }}); }}</script>
    </body></html>"""


@app.route("/SalesInvoice/Delete/<int:no>", methods=["POST"])
def si_delete(no):
    if not guard():
        return jsonify({"ok": False, "error": "login"})
    if no == 500:
        return jsonify({"ok": False, "error": "لا يمكن حذف فاتورة مرحلة"})
    INVOICES[:] = [x for x in INVOICES if x["no"] != no]
    return jsonify({"ok": True})


@app.route("/SalesInvoice/Print/<int:no>")
def si_print(no):
    if not guard():
        return redirect("/Login")
    v = next((x for x in INVOICES if x["no"] == no), None)
    return f"<html dir=rtl><head><title>طباعة فاتورة {no}</title></head><body><h1>فاتورة بيع رقم {no}</h1><p>{v and v['customer']}</p></body></html>"


@app.route("/SalesInvoice/Edit/<int:no>", methods=["GET", "POST"])
def si_edit(no):
    if not guard():
        return redirect("/Login")
    v = next((x for x in INVOICES if x["no"] == no), None)
    if request.method == "POST":
        v["notes"] = request.form.get("Notes", "")
        return redirect("/SalesInvoice")
    return f"""<html dir=rtl><head><meta charset=utf-8></head><body><form method=post>
      <label for=Notes>ملاحظات</label><textarea id=Notes name=Notes>{v.get('notes','')}</textarea>
      <button id=save type=submit>حفظ</button></form></body></html>"""


@app.route("/api/docs")
def api_docs():
    f, t, typ = request.args.get("from", ""), request.args.get("to", ""), request.args.get("type", "")
    src = DOCS if typ == "5" else (ORDERS if typ == "4" else [])
    out = [d for d in src if f <= d[1] <= t]
    return jsonify(out)


@app.route("/SalesInvoice/AddEdit", methods=["GET", "POST"])
def si_add():
    if not guard():
        return redirect("/Login")
    if request.method == "POST":
        n = len(request.form.getlist("line"))
        INVOICES.append({"no": 500 + len(INVOICES), "customer": request.form.get("cust_text", ""), "lines": n})
        return jsonify({"ok": True})
    return f"""<!doctype html><html dir=rtl><head><meta charset=utf-8>{LIBS}
    <link rel="stylesheet" href="/lib/bootstrap/dist/css/bootstrap.min.css">
    <script src="/lib/bootstrap/dist/js/bootstrap.bundle.min.js"></script></head><body class="p-3">
    <form id=frm>
      <label for=CustomerId>العميل *</label>
      <select id=CustomerId name=CustomerId data-val-required="مطلوب"><option value="">اختر</option>
        {''.join(f'<option value={v}>{n}</option>' for v, n in CUSTOMERS['1'])}</select>
      <div class="mt-3"><button type="button" id="btnOpenLinkWithOtherDocModal" class="btn btn-primary" onclick="return openLinkWithOtherDocModal(event);">
          ربط بمستند اخر
        </button>
        <label><input type=checkbox checked> انشاء سند صرف الى</label></div>
      <table class="table mt-3" id=itemsGrid><thead><tr><th>المستند</th><th>البيان</th></tr></thead><tbody></tbody></table>
      <label for=Notes>ملاحظات</label><textarea id=Notes name=Notes></textarea>
      <div class="mt-3"><span class="Add-Button btn btn-light" style="cursor:pointer">➕</span> الأصناف</div>
      <table class="table" id=linesGrid><thead><tr><th>الصنف</th><th>الكمية</th><th>السعر</th><th>الإجمالي</th></tr></thead><tbody></tbody></table>
      <div>الصافي: <span id=NetTotal>0.00</span> · الضريبة 15%: <span id=VatTotal>0.00</span> · الإجمالي: <span id=GrandTotal>0.00</span></div>
      <div class="mt-2"><label>المرفقات</label> <input type=file id=Attachments name=Attachments style="display:none"><span class="btn btn-sm btn-light">اختر ملف</span></div>
    </form>
    <div class="modal fade" id="itemsModal" tabindex="-1"><div class="modal-dialog modal-lg"><div class="modal-content">
      <div class="modal-header"><h5 class="modal-title">الأصناف</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
      <div class="modal-body"><input id=itemSearch placeholder="بحث"> <button type=button id=submitSearch class="btn btn-primary">بحث</button>
        <table class="table"><thead><tr><th>الكود</th><th>الصنف</th><th></th></tr></thead><tbody id=itemRows></tbody></table></div></div></div></div>
    <button id=save type=button class="btn btn-success">حفظ</button>

    <div class="modal fade" id="docsModal" tabindex="-1"><div class="modal-dialog modal-lg"><div class="modal-content">
      <div class="modal-header"><h5 class="modal-title">ربط بمستند اخر</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
      <div class="modal-body">
        <div class="row mb-2">
          <div class="col-2"><label>الفرع</label></div>
          <div class="col-4"><select id=LinkWithDocModalDepartmentId><option value=1 selected>01 - الفرع الاول</option><option value=2>2 - الفرع ٢</option></select></div>
          <div class="col-2"><label>نوع المستند</label></div>
          <div class="col-4"><select id=DocType><option value="">--اختر--</option><option value=1>عرض سعر بيع</option><option value=2>طلب شراء</option>
            <option value=3>فواتير الشراء</option><option value=4>اوامر البيع</option><option value=5>سندات صرف المخازن</option>
            <option value=6>سندات استلام المخازن</option></select></div>
        </div>
        <div id=secStock class="docsec" style="display:none">
          <div class="row mb-2">
            <div class="col-2"><label>التاريخ من</label></div><div class="col-4"><input type=date id=StockDateFrom class="form-control" value="{date.today().replace(day=1).isoformat()}"></div>
            <div class="col-2"><label>التاريخ إلى</label></div><div class="col-4"><input type=date id=StockDateTo class="form-control" value="{date.today().isoformat()}"></div>
          </div>
          <div class="row mb-2"><div class="col-2"><label>رقم امر البيع</label></div>
            <div class="col-4"><select id=StockSalesOrderId><option value="">--اختر--</option></select></div></div>
          <button type=button class="btn btn-primary" id=btnFilterStockReceipts><i class="bi bi-funnel"></i> المصفي</button>
          <button type=button class="btn btn-secondary"><i class="bi bi-arrow-repeat"></i> مسح</button>
        </div>
        <div id=secOrders class="docsec" style="display:none">
          <div class="row mb-2">
            <div class="col-2"><label>التاريخ من</label></div><div class="col-4"><input type=date id=OrderDateFrom class="form-control" value="{date.today().replace(day=1).isoformat()}"></div>
            <div class="col-2"><label>التاريخ إلى</label></div><div class="col-4"><input type=date id=OrderDateTo class="form-control" value="{date.today().isoformat()}"></div>
          </div>
          <button type=button class="btn btn-primary" id=btnFilterSalesOrders><i class="bi bi-funnel"></i> المصفي</button>
        </div>
        <table class="table mt-2" id=docsTable style="display:none"><thead><tr><th>رقم المستند</th><th>التاريخ</th><th>الفرع</th><th>التفاصيل</th>
          <th><button type=button class="btn btn-success btn-sm" id=btnAddDocs>+ إضافة</button></th>
          <th><input type=checkbox id=chkAll> تحديد الكل</th></tr></thead><tbody></tbody></table>
      </div></div></div></div>
    <script>
    $('#CustomerId').select2({{width:'260px'}});
    $('#LinkWithDocModalDepartmentId, #DocType, #StockSalesOrderId').each(function(){{ $(this).select2({{width:'260px', dropdownParent: $('#docsModal')}}); }});
    var modal = new bootstrap.Modal(document.getElementById('docsModal'));
    function openLinkWithOtherDocModal(e){{ setTimeout(function(){{ modal.show(); }}, 300); return false; }}
    $('#DocType').on('change', function(){{
      $('.docsec').hide(); $('#docsTable').hide(); $('#docsTable tbody').empty();
      var v = $(this).val();
      setTimeout(function(){{ if (v=='5') $('#secStock').show(); if (v=='4') $('#secOrders').show(); }}, 500);
    }});
    function runFilter(type, f, t){{
      var tb = $('#docsTable tbody').empty(); $('#docsTable').hide();
      setTimeout(function(){{
        $.getJSON('/api/docs', {{from: f, to: t, type: type}}, function(rows){{
          $('#docsTable').show();
          if (!rows.length) tb.append('<tr><td colspan=6 class="dataTables_empty">لا توجد بيانات</td></tr>');
          rows.forEach(function(r){{ tb.append('<tr><td>'+r[0]+'</td><td>'+r[1]+'</td><td>'+r[2]+'</td><td>'+r[3]+'</td><td></td><td><input type=checkbox class=rowChk data-no="'+r[0]+'" data-d="'+r[3]+'"></td></tr>'); }});
        }});
      }}, 700);
    }}
    $('#btnFilterStockReceipts').on('click', function(){{ runFilter('5', $('#StockDateFrom').val(), $('#StockDateTo').val()); }});
    $('#btnFilterSalesOrders').on('click', function(){{ runFilter('4', $('#OrderDateFrom').val(), $('#OrderDateTo').val()); }});
    var itemsModal = new bootstrap.Modal(document.getElementById('itemsModal'));
    $(document).on('click', '.Add-Button', function(){{ $('#itemRows').empty(); itemsModal.show(); }});
    $('#submitSearch').on('click', function(){{
      setTimeout(function(){{
        [['I-1','حديد تسليح'],['I-2','أسمنت مقاوم']].forEach(function(it){{
          $('#itemRows').append('<tr><td>'+it[0]+'</td><td>'+it[1]+'</td><td><button type=button class="btn btn-sm btn-success" onclick="chooseItem(this)" data-name="'+it[1]+'">اختيار</button></td></tr>'); }});
      }}, 500);
    }});
    function recalc(){{
      var net = 0;
      $('#linesGrid tbody tr').each(function(){{ var q = parseFloat($(this).find('.qty').val())||0, p = parseFloat($(this).find('.price').val())||0;
        $(this).find('.line-total').text((q*p).toFixed(2)); net += q*p; }});
      $('#NetTotal').text(net.toFixed(2)); $('#VatTotal').text((net*0.15).toFixed(2)); $('#GrandTotal').text((net*1.15).toFixed(2));
    }}
    window.chooseItem = function(b){{
      $('#linesGrid tbody').append('<tr><td>'+$(b).data('name')+'<input type=hidden name=item value="'+$(b).data('name')+'"></td><td><input class="float qty" value="1"></td><td><input class="float price" value="0"></td><td class=line-total>0.00</td></tr>');
      itemsModal.hide(); recalc();
    }};
    $(document).on('change keyup', '#linesGrid input', recalc);
    $('#chkAll').on('change', function(){{ $('.rowChk').prop('checked', this.checked); }});
    $('#btnAddDocs').on('click', function(){{
      var n = 0;
      $('.rowChk:checked').each(function(){{ n++; $('#itemsGrid tbody').append('<tr><td>'+$(this).data('no')+'<input type=hidden name=line value="'+$(this).data('no')+'"></td><td>'+$(this).data('d')+'</td></tr>'); }});
      if (!n) {{ Swal.fire('اختر مستند'); return; }}
      modal.hide();
    }});
    $('#save').on('click', function(){{
      if (!$('#CustomerId').val()) {{ Swal.fire({{icon:'error', text:'اختر العميل'}}); return; }}
      if (!$('#itemsGrid tbody tr').length && !$('#linesGrid tbody tr').length) {{ Swal.fire({{icon:'error', text:'يجب إضافة أصناف'}}); return; }}
      if ($('#linesGrid tbody tr').length && !$('#Attachments')[0].files.length) {{ Swal.fire({{icon:'error', text:'يجب ان تختار الملفات اولا'}}); return; }}
      var bad = $('#linesGrid .price').filter(function(){{ return !(parseFloat(this.value) > 0); }}).length;
      if (bad) {{ Swal.fire({{icon:'error', text:'السعر لازم يكون أكبر من صفر'}}); return; }}
      var fd = $('#frm').serialize() + '&cust_text=' + encodeURIComponent($('#CustomerId option:selected').text());
      $.post('/SalesInvoice/AddEdit', fd, function(){{ location.href = '/SalesInvoice'; }});
    }});
    </script></body></html>"""


if __name__ == "__main__":
    app.run(port=5055, threaded=True)
