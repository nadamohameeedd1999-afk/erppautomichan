// Readiness of one add form: the required lists a person must pick from, and which of them came with nothing to pick.
// A list that loads by search (select2 ajax) or only after another choice is not "empty". Sync, returns a dict.
var vis = function (e) { return !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length); };
var T = function (s) { return String(s || '').replace(/\s+/g, ' ').replace(/[*:：]/g, '').trim(); };
function label(el) {
  var l = el.id && document.querySelector('label[for="' + el.id + '"]');
  if (!l) { var g = el.closest('.form-group, .col-md-3, .col-md-4, .col-md-6, .col-lg-3, .col-sm-6, td, div'); l = g && g.querySelector('label'); }
  return l ? T(l.innerText) : (el.name || el.id || '');
}
function required(el) {
  if (el.required || el.getAttribute('data-parsley-required') === 'true' || /\brequired\b/.test(el.className)) return true;
  var l = el.id && document.querySelector('label[for="' + el.id + '"]');
  if (!l) { var g = el.closest('.form-group, .col-md-3, .col-md-4, .col-md-6, .col-lg-3, .col-sm-6'); l = g && g.querySelector('label'); }
  return !!(l && (/\*/.test(l.innerText) || l.querySelector('.text-danger, .required, span[style*="red"]')));
}
var out = { lists: 0, empty: [], url: location.pathname + location.search, title: document.title };
// a list the page's own script fills later (after the customer / branch is chosen): «$('#X').html(…)» / «.append(…)»
var code = Array.prototype.map.call(document.scripts, function (x) { return x.text || ''; }).join('\n');
function filledLater(id) {
  if (!id) return false;
  var e = id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp("#" + e + "['\"]\\)\\s*\\.\\s*(html|append|empty\\(\\)\\s*\\.\\s*append)\\s*\\(").test(code);
}
Array.prototype.forEach.call(document.querySelectorAll('form select, .card select, select'), function (s) {
  if (s.closest('table')) return;                                       // item lines: filled per line
  var shown = vis(s) || (s.classList.contains('select2-hidden-accessible') && s.nextElementSibling && vis(s.nextElementSibling));
  if (!shown || s.disabled || !required(s)) return;
  out.lists++;
  var real = Array.prototype.filter.call(s.options, function (o) { return o.value && !/^(--|اختر|أختر|select)/i.test(T(o.text)); }).length;
  var ajax = false;
  try { var d = window.jQuery && jQuery(s).data('select2'); ajax = !!(d && d.options && d.options.options && d.options.options.ajax); } catch (e) {}
  if (!real && !ajax && !filledLater(s.id)) out.empty.push({ id: s.id || s.name, label: label(s) });
});
return out;
