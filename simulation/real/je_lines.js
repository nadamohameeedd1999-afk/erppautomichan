// Journal entry (/JournalEntries/AddEdit): two balanced lines the way an accountant types them —
// an expense account (debit nature) on the debit side, a revenue account (credit nature) on the credit side —
// the site refuses a credit on any debit-nature account (even accumulated depreciation), so the credit side is a revenue.
// Accounts come from the site's own chart (GetAccounts), so nothing is invented. Async: arguments[0] = amount, last = callback.
var done = arguments[arguments.length - 1], amount = String(arguments[0] || 150), $ = window.jQuery;
var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
async function pick(terms, prefix, avoid) {
  for (var t of terms) {
    try {
      var j = await (await fetch('/JournalEntries/GetAccounts?term=' + encodeURIComponent(t))).json();
      var c = j.filter(function (x) { var n = String(x.ArName || ''); return n.replace(/\s/g, '').indexOf(prefix) === 0 && !(avoid && avoid.test(n)); });
      for (var a of c.slice(0, 12)) {                      // an account that needs no customer / vendor / employee on the line
        try {
          var q = await (await fetch('/JournalEntries/GetAccountPartyRequirements?accountId=' + a.Id)).json();
          var f = await (await fetch('/JournalEntries/IsCostCenter?id=' + a.Id)).json();
          if (q.IsCustomerAccount || q.IsVendorAccount || q.IsEmployeeAccount || f.IsCustomer || f.IsVendor) continue;
          var v = await (await fetch('/JournalEntries/ValidateAnalyticalEntities', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rows: [{ Index: 0, RowNumber: '1', AccountId: a.Id, CustomerId: null, VendorId: null, EmpId: null }] }) })).json();
          if (v && v.violations && v.violations.length) continue;   // the site's own rule: this account needs a customer / employee
        } catch (e) {}
        return a;
      }
    } catch (e) {}
  }
  return null;
}
(async function () {
  var log = [];
  if (!$ || !$('select.AccountId').length) { done({ ok: false, log: ['no journal lines table'] }); return; }
  var lines = [
    { side: 'd', acc: await pick(['مصروفات', 'مصروف'], '5', /اهلاك|اراض/) || await pick(['مصروف'], '5') },
    { side: 'c', acc: await pick(['ايرادات اخرى', 'ايرادات', 'ايراد'], '4') }
  ];
  for (var i = 0; i < lines.length; i++) {
    var L = lines[i];
    if (!L.acc) { log.push('مفيش حساب للسطر ' + (i + 1)); continue; }
    var rows = $('select.AccountId').closest('tr');
    if (rows.length <= i) { rows.last().find('.addRowBelow').click(); await sleep(500); rows = $('select.AccountId').closest('tr'); }
    var $tr = $(rows[i]), $s = $tr.find('select.AccountId');
    if (!$s.find('option[value="' + L.acc.Id + '"]').length) $s.append(new Option(L.acc.ArName, L.acc.Id, true, true));
    $s.val(String(L.acc.Id)).trigger('change');
    await sleep(2000);                                   // the account's flags (cost center / customer / vendor) come back by ajax
    var m = $tr.find('input.money');
    $(m[L.side === 'd' ? 0 : 1]).val(amount).trigger('input').trigger('change').trigger('keyup');
    $(m[L.side === 'd' ? 1 : 0]).val('0').trigger('change');
    var cc = $tr.find('select.CostCenterId');                 // an ajax list: ask it like select2 does, take the first
    if (cc.length && !cc.val()) {
      try {
        var cs = await (await fetch('/JournalEntries/GetCostCenters?term=')).json();
        if (cs[0]) cc.append(new Option(cs[0].ArName, cs[0].Id, true, true)).val(String(cs[0].Id)).trigger('change');
      } catch (e) {}
    }
    var ex = $tr.find('input').filter(function () { return /شرح|Explain|Desc/i.test((this.className || '') + (this.name || '') + (this.placeholder || '')); }).first();
    if (ex.length && !ex.val()) ex.val('اختبار آلي — قيد تسوية').trigger('change');
    log.push((L.side === 'd' ? 'مدين ' : 'دائن ') + L.acc.ArName + ' = ' + amount);
  }
  $('select.AccountId').closest('tr').filter(function () { return !$(this).find('select.AccountId').val(); })
    .each(function () { $(this).find('.DelBtn').click(); });          // no empty line left under the two
  await sleep(800);
  done({ ok: log.length === 2 && !/مفيش/.test(log.join()), log: log, totals: [$('.TotalDebit').val(), $('.TotalCredit').val()] });
})();
