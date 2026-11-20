// Stock receipt (/StockReceiptVoucher/AddEdit) with no source document: a storekeeper types an item's barcode in the
// lines table and presses Enter. If the page's own script breaks on it, that is the system's error (and the reason the
// save is refused without a message: the lines table stays empty). Async: arguments[0] = quantity, last = callback.
var done = arguments[arguments.length - 1], qty = String(arguments[0] || 2), $ = window.jQuery;
var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
(async function () {
  var log = [], pageErr = null;
  if (!$ || !$('#StockReceiptVoucherDetails').length) { done({ ok: false, log: ['مفيش جدول أصناف في الصفحة'] }); return; }
  if ($('#StockReceiptVoucherDetails .itemId').filter(function () { return this.value; }).length) { done({ ok: true, log: ['الأصناف موجودة'] }); return; }
  var bar = '', name = '';
  try {
    var r = await (await fetch('/Helper/ItemsByDepId?departmentId=' + encodeURIComponent($('#DepartmentId').val() || '') + '&SalesTransaction=false&pageIndex=1&pageSize=20')).json();
    var list = Array.isArray(r) ? r : (r && (r.Items || r.items)) || [];
    var it = list.filter(function (x) { return x.Barcode && !x.IsGold; })[0];
    if (it) { bar = it.Barcode; name = it.ArName; }
    log.push('أصناف الفرع من السيستم: ' + list.length + (Array.isArray(r) ? '' : ' (رد السيستم كائن مش قايمة)'));
  } catch (e) { log.push('قايمة الأصناف: ' + e); }
  var tr = $('#StockReceiptVoucherDetails tr').last(), b = tr.find('.barcode');
  b.val(bar || '1');
  try { b.trigger($.Event('keydown', { which: 13, keyCode: 13 })); }
  catch (e) { pageErr = String(e && e.message || e); }
  await sleep(1200);
  tr = $('#StockReceiptVoucherDetails tr').filter(function () { return $(this).find('.item').val(); }).first();
  if (tr.length) {
    tr.find('.quantity').val(qty).trigger('change').trigger('keyup');
    if (!parseFloat(tr.find('.float').val())) tr.find('.float').val('10').trigger('change').trigger('keyup');
    log.push('صنف: ' + (name || tr.find('.item-name').val()) + ' × ' + qty);
  }
  if (pageErr) log.push('صفحة السيستم وقعت عند إدخال الصنف: ' + pageErr);
  done({ ok: !!tr.length, erp: pageErr ? 'صفحة سند الاستلام وقعت لما اتكتب باركود الصنف: «' + pageErr + '» — إدخال الأصناف يدوي في السند مش شغال' : null, log: log });
})();
