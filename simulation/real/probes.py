"""
The test waves on the real NQ ERP site — checks a careful tester does that aren't a plain «add / edit / print / delete»:

  🚫 negative   : the form filled right, then ONE field made wrong just before «حفظ» (required emptied · quantity -5 ·
                  discount 150% · 1000-character text with ' " < > · a supplier invoice number used before)
  ⚡ many lines : the same quotation with 30 lines
  🔐 security   : a screen's link with no login · passwords / keys written inside the pages
  👁️ mobile     : the add screens at phone size (nothing wider than the screen, «حفظ» reachable)
  🌐 English    : the system's English switch, and how much Arabic stays on the screens
  🧮 numbers    : the invoice's journal entry is balanced · the trial balance's totals · approving our own document

Each returns the usual result dict. «notarget» = the field the check needs isn't on this form: nothing was proven.
These run only on a test site (the company's own documents, deleted after).
"""
import re
import time
from pathlib import Path
import urllib.request
from urllib.parse import urljoin

# ------------------------------------------------------------------ one field made wrong, just before the save
MUTATE_JS = r"""
var mode = arguments[0], val = arguments[1], done = arguments[arguments.length - 1], $ = window.jQuery;
var vis = function (e) { return !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length)); };
var fire = function (e) { ['input', 'change', 'keyup', 'blur'].forEach(function (t) { e.dispatchEvent(new Event(t, {bubbles: true})); }); try { if ($) $(e).trigger('change'); } catch (x) {} };
var all = function (sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)).filter(vis); };
var tag = function (e) { return ((e.id || '') + ' ' + (e.name || '') + ' ' + (e.className || '')).toLowerCase(); };
var out = {ok: false, log: [], mode: mode};
try {
  if (mode === 'required') {
    var lab = function (el) { var l = el.id && document.querySelector('label[for="' + el.id + '"]'); if (!l) { var g = el.closest('.form-group, [class*="col-"]'); l = g && g.querySelector('label'); } return l; };
    var shown = function (e) { return vis(e) || (e.classList.contains('select2-hidden-accessible') && e.nextElementSibling && vis(e.nextElementSibling)); };
    var req = Array.prototype.slice.call(document.querySelectorAll('select, input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=button]):not([type=submit])')).filter(function (e) {
      if (!shown(e) || e.closest('table') || e.disabled || e.readOnly) return false; var l = lab(e);
      return e.required || e.getAttribute('data-val-required') || e.getAttribute('aria-required') === 'true' || /required/.test(e.className)
        || (l && (/\*/.test(l.innerText) || l.querySelector('.text-danger, .required, span[style*="red"]'))); });
    var pick = req.filter(function (e) { return /customer|vendor|party|client|عميل|مورد/.test(tag(e)); })[0] || req[0];
    if (!pick) { out.notarget = true; out.log.push('مفيش حقل إجباري ظاهر'); done(out); return; }
    if (pick.tagName === 'SELECT') { pick.value = ''; if ($ && $(pick).data('select2')) $(pick).val(null).trigger('change'); } else pick.value = '';
    fire(pick); var l2 = lab(pick); out.ok = true; out.field = (l2 ? l2.innerText : pick.id).replace(/[*:\s]+/g, ' ').trim(); out.log.push('فضّيت الحقل الإجباري «' + out.field + '»');
  } else if (mode === 'negative') {
    var q = all('table input').filter(function (e) { return /quantity|qty|كمية/.test(tag(e)); });
    if (!q.length) { out.notarget = true; out.log.push('مفيش خانة كمية في السطور'); done(out); return; }
    q.forEach(function (e) { e.value = String(val || -5); fire(e); }); out.ok = true; out.log.push('الكمية = ' + (val || -5) + ' في ' + q.length + ' سطر');
  } else if (mode === 'discount') {
    var d = all('input').filter(function (e) { return /discount|خصم/.test(tag(e)) && !e.readOnly && !e.disabled; });
    if (!d.length) { out.notarget = true; out.log.push('مفيش خانة خصم'); done(out); return; }
    d.forEach(function (e) { e.value = String(val || 150); fire(e); }); out.ok = true; out.log.push('الخصم = ' + (val || 150) + ' في ' + d.length + ' خانة');
  } else if (mode === 'text') {
    var n = all('textarea').concat(all('input[type=text]').filter(function (e) { return /note|remark|descr|statement|بيان|ملاحظ/.test(tag(e)) && !e.closest('table'); }))[0];
    if (!n) { out.notarget = true; out.log.push('مفيش خانة بيان/ملاحظات'); done(out); return; }
    var s = ''; while (s.length < 1000) s += 'اختبار نص طويل \' " < > & ; -- /* */ '; n.value = s.slice(0, 1000); fire(n); out.ok = true; out.log.push('بيان 1000 حرف فيه \' " < > &');
  } else if (mode === 'dupref') {
    var r = all('input[type=text], input:not([type])').filter(function (e) { return /supplier.?inv|vendor.?inv|bill.?no|ref.?no|reference|refno|invoiceno|رقم فاتورة/.test(tag(e)) && !e.closest('table') && !e.readOnly; })[0];
    if (!r) { out.notarget = true; out.log.push('مفيش خانة رقم فاتورة المورد'); done(out); return; }
    r.value = String(val); fire(r); out.ok = true; out.log.push('رقم فاتورة المورد = ' + val);
  } else if (mode === 'lines') {
    var want = +val || 30, sleep = function (ms) { return new Promise(function (ok) { setTimeout(ok, ms); }); };
    var btn = all('button, a, input[type=button]').filter(function (e) { var t = (e.innerText || e.value || e.title || '').trim(); return /إضافة سطر|اضافة سطر|سطر جديد|add row|add line|اضافة صنف|إضافة صنف/i.test(t) || /addrow|add-row|addline|add_row/i.test(tag(e)); })[0];
    var rows0 = function () { return all('table tbody tr').filter(function (tr) { return tr.querySelector('input, select'); }); };
    if (!btn) { out.notarget = true; out.log.push('مالقيتش زرار إضافة سطر'); done(out); return; }
    (async function () {
      var first = rows0()[0]; var vals = first ? Array.prototype.map.call(first.querySelectorAll('input, select'), function (e) { return e.value; }) : [];
      for (var i = 1; i < want; i++) { btn.click(); await sleep(120); var rs = rows0(), tr = rs[rs.length - 1];
        if (tr && tr !== first) Array.prototype.forEach.call(tr.querySelectorAll('input, select'), function (e, k) { if (vals[k] !== undefined && !e.value) { e.value = vals[k]; fire(e); } }); }
      out.ok = rows0().length >= Math.min(want, 5); out.lines = rows0().length; out.log.push('السطور = ' + rows0().length); if (!out.ok) out.notarget = true; done(out);
    })(); return;
  }
} catch (e) { out.log.push('JS: ' + String(e).slice(0, 120)); out.notarget = true; }
done(out);
"""

# a local-currency document keeps exchange rate 1 (a random rate makes «الإجمالي بالعملة المحلية» look like the system's mistake)
RATE_JS = r"""
var done = arguments[arguments.length - 1], $ = window.jQuery, out = {ok: true, log: []};
var vis = function (e) { return !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length)); };
var tag = function (e) { return ((e.id || '') + ' ' + (e.name || '') + ' ' + (e.className || '')).toLowerCase(); };
var cur = Array.prototype.filter.call(document.querySelectorAll('select'), function (s) { return /currenc|عملة/.test(tag(s)); })[0];
var txt = cur && cur.selectedIndex >= 0 ? (cur.options[cur.selectedIndex].text || '') : '';
if (!cur || /SAR|ريال|سعودي/i.test(txt) || !txt.trim()) {
  Array.prototype.forEach.call(document.querySelectorAll('input'), function (e) {
    if (e.closest('table') || e.readOnly || e.disabled || !vis(e)) return;
    if (/exchange.?rate|currency.?rate|سعر.?الصرف|\brate\b/.test(tag(e)) && e.value !== '1') { var o = e.value; e.value = '1';
      ['input', 'change', 'keyup', 'blur'].forEach(function (t) { e.dispatchEvent(new Event(t, {bubbles: true})); }); try { if ($) $(e).trigger('change'); } catch (x) {}
      out.log.push('سعر الصرف ' + o + ' ← 1 (عملة محلية)'); }
  });
}
done(out);
"""
RATE_STEP = {"label": "💱 سعر الصرف = 1 للعملة المحلية", "js": RATE_JS, "args": [], "timeout": 15}

LABEL = {"required": "فضّي حقل إجباري قبل الحفظ", "negative": "كمية بالسالب قبل الحفظ", "discount": "خصم 150% قبل الحفظ",
         "text": "بيان 1000 حرف بحروف خاصة", "dupref": "رقم فاتورة مورد متكرر", "lines": "فاتورة/عرض بـ 30 سطر"}


def mutate_step(mode, val=None):
    return {"label": "🧪 " + LABEL.get(mode, mode), "js": MUTATE_JS, "args": [mode, val], "timeout": 90 if mode == "lines" else 30}


# ------------------------------------------------------------------ 🔐 a screen's link with no login
def no_login(base, paths):
    """GET each screen with no cookies: it must end on the login page (or 401/403), never on the screen itself"""
    t0, open_ = time.time(), []
    checked = 0
    for p in paths[:6]:
        url = urljoin(base.rstrip("/") + "/", p.lstrip("/"))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "NQ-Simulation/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                final, body = r.geturl(), r.read(60000).decode("utf-8", "ignore")
            checked += 1
            if not re.search(r"login|signin|account/log", final, re.I) and not re.search(r"type=['\"]?password", body, re.I):
                open_.append(p)
        except urllib.error.HTTPError as e:
            checked += 1
            if e.code not in (401, 403, 302):
                pass
        except Exception:
            continue
    ms = int((time.time() - t0) * 1000)
    if not checked:
        return {"kind": "error", "tool": True, "ms": ms, "msg": "مقدرتش أوصل للموقع من غير متصفح (النت/البروكسي)"}
    if open_:
        return {"kind": "wrong", "ms": ms, "msg": f"شاشات بتفتح من غير تسجيل دخول: {'، '.join(open_)}", "evidence": f"🔐 اتجرب {checked} رابط من غير كوكيز"}
    return {"kind": "ok", "ms": ms, "note": f"🔐 جربت {checked} رابط شاشة من غير تسجيل دخول — كلهم رجعوا لصفحة الدخول ✅"}


# ------------------------------------------------------------------ 🔐 secrets written in the pages
SECRETS_JS = r"""
var paths = arguments[0], done = arguments[arguments.length - 1];
var rx = [/(password|passwd|pwd|unlock\w*|secret|api[_-]?key|token)\s*[:=]\s*['"][^'"\s]{4,}['"]/ig, /(كلمة\s*(السر|المرور))\s*[:=]\s*['"][^'"]{3,}['"]/g];
var found = [], n = 0;
(async function () {
  for (var i = 0; i < paths.length; i++) {
    try { var t = await (await fetch(paths[i], {credentials: 'same-origin'})).text(); n++;
      rx.forEach(function (r) { var m; r.lastIndex = 0; while ((m = r.exec(t))) { var s = m[0]; if (/value=|placeholder|\$\(|\.val\(|password['"]?\s*:\s*['"]password/i.test(s)) continue; found.push(paths[i] + ' ← ' + s.replace(/(['"])[^'"]{2}([^'"]*)(['"])$/, '$1••$3').slice(0, 80)); } });
    } catch (e) {}
  }
  done({n: n, found: found.slice(0, 12)});
})();
"""


def secrets(driver, paths):
    t0 = time.time()
    driver.set_script_timeout(90)
    v = driver.execute_async_script(SECRETS_JS, paths[:25]) or {}
    ms = int((time.time() - t0) * 1000)
    if not v.get("n"):
        return {"kind": "error", "tool": True, "ms": ms, "msg": "مقدرتش أقرا كود الصفحات"}
    if v.get("found"):
        return {"kind": "wrong", "ms": ms, "msg": f"أسرار مكتوبة في كود {len(v['found'])} مكان (كلمات سر/مفاتيح)", "evidence": "🔐 " + "\n".join(v["found"])}
    return {"kind": "ok", "ms": ms, "note": f"🔐 فحصت كود {v['n']} صفحة — مفيش كلمات سر أو مفاتيح مكتوبة ✅"}


# ------------------------------------------------------------------ 👁️ phone size
MOBILE_JS = r"""
var w = window.innerWidth, sw = document.documentElement.scrollWidth;
var save = Array.prototype.filter.call(document.querySelectorAll('button, input[type=submit], a'), function (e) { return /حفظ|save/i.test((e.innerText || e.value || '').trim()); })[0];
var r = save ? save.getBoundingClientRect() : null;
return {w: w, sw: sw, wide: sw > w + 8, save: !!save, saveOut: !!(r && (r.right > w + 4 || r.left < -4))};
"""


def mobile(session, paths):
    d, t0, bad, n = session.driver, time.time(), [], 0
    try:
        size = d.get_window_size()
        d.set_window_size(400, 860)
        for p in paths[:6]:
            try:
                session.open(p)
                time.sleep(1.5)
                v = d.execute_script(MOBILE_JS) or {}
                n += 1
                if v.get("wide") or v.get("saveOut"):
                    bad.append(f"{p} (عرض الصفحة {v.get('sw')} على شاشة {v.get('w')}{' · زرار الحفظ برّه الشاشة' if v.get('saveOut') else ''})")
            except Exception:
                continue
        d.set_window_size(size.get("width", 1366), size.get("height", 900))
    except Exception as e:
        return {"kind": "error", "tool": True, "ms": int((time.time() - t0) * 1000), "msg": f"مقاس الموبايل: {type(e).__name__}"}
    ms = int((time.time() - t0) * 1000)
    if bad:
        return {"kind": "wrong", "ms": ms, "msg": f"{len(bad)} شاشة من {n} مش مظبوطة على الموبايل", "evidence": "📱 " + "\n".join(bad)}
    return {"kind": "ok" if n else "error", "tool": not n, "ms": ms, "note": f"📱 {n} شاشة على مقاس موبايل — مظبوطين ✅", "msg": "" if n else "مقدرتش أفتح الشاشات"}


# ------------------------------------------------------------------ 🌐 the system in English
LANG_JS = r"""
var a = Array.prototype.filter.call(document.querySelectorAll('a, button'), function (e) { var t = (e.innerText || e.title || '').trim(); var h = e.getAttribute('href') || '';
  return /^(english|en)$/i.test(t) || /lang(uage)?=en|culture=en|\/en-us/i.test(h); })[0];
if (!a) return {found: false};
var h = a.getAttribute('href'); if (h && !/^javascript/i.test(h)) return {found: true, href: h};
a.click(); return {found: true, clicked: true};
"""
ARABIC_JS = r"""
// the interface's own words only: data (table rows, dropdown values, inputs, the user / company names) is Arabic in any language
var skip = 'tbody, select, option, textarea, input, .select2-container, .select2-results, .dataTables_info, script, style, noscript, [contenteditable], .user-name, .company-name, .navbar-user, .dropdown-user';
var w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT), n, parts = [];
while ((n = w.nextNode())) {
  var p = n.parentElement, v = (n.nodeValue || '').trim();
  if (!v || !p || p.closest(skip) || !(p.offsetWidth || p.offsetHeight)) continue;
  if (/^(عربي|العربية)$/.test(v)) continue;                   // the switch back to Arabic
  parts.push(v);
}
var t = parts.join(' '); var ar = (t.match(/[؀-ۿ]+/g) || []).join('').length, lat = (t.match(/[A-Za-z]+/g) || []).join('').length;
return {ar: ar, lat: lat, sample: ((t.match(/[؀-ۿ][؀-ۿ\s]{3,30}/g) || []).slice(0, 6))};
"""
BACK_JS = r"""
var a = Array.prototype.filter.call(document.querySelectorAll('a, button'), function (e) { var t = (e.innerText || e.title || '').trim(); var h = e.getAttribute('href') || '';
  return /^(عربي|العربية|arabic|ar)$/i.test(t) || /lang(uage)?=ar|culture=ar/i.test(h); })[0];
if (!a) return false; var h = a.getAttribute('href'); if (h && !/^javascript/i.test(h)) { location.href = h; return true; } a.click(); return true;
"""


def english(session, paths):
    d, t0 = session.driver, time.time()
    session.open(paths[0] if paths else "/")
    v = d.execute_script(LANG_JS) or {}
    if not v.get("found"):
        return {"kind": "skip", "ms": int((time.time() - t0) * 1000), "msg": "مالقيتش زرار تغيير اللغة للإنجليزي في السيستم", "notarget": True}
    if v.get("href"):
        session.open(v["href"])
    time.sleep(2)
    left = []
    for p in paths[:5]:
        try:
            session.open(p)
            time.sleep(1)
            r = d.execute_script(ARABIC_JS) or {}
            if r.get("ar", 0) > max(40, r.get("lat", 0) * .15):
                left.append(f"{p}: {'، '.join(r.get('sample') or [])[:120]}")
        except Exception:
            continue
    try:
        d.execute_script(BACK_JS)
        time.sleep(2)
    except Exception:
        pass
    ms = int((time.time() - t0) * 1000)
    if left:
        return {"kind": "wrong", "ms": ms, "msg": f"{len(left)} شاشة لسه فيها نصوص عربي في الواجهة الإنجليزي", "evidence": "🌐 " + "\n".join(left)}
    return {"kind": "ok", "ms": ms, "note": "🌐 الواجهة الإنجليزي: الشاشات مترجمة ✅"}


# ------------------------------------------------------------------ 🧮 the invoice's journal entry is balanced
JE_JS = r"""
var no = String(arguments[0]).trim(), done = arguments[arguments.length - 1];
var T = function (e) { return (e && e.innerText || '').replace(/\s+/g, ' ').trim(); };
var num = function (s) { var x = parseFloat(String(s).replace(/,/g, '')); return isNaN(x) ? 0 : x; };
function rows() { return Array.prototype.filter.call(document.querySelectorAll('table tbody tr'), function (tr) { return Array.prototype.some.call(tr.querySelectorAll('td'), function (td) { return T(td) === no; }); }); }
(async function () {
  var box = document.querySelector('.dataTables_filter input, input[type=search]');
  if (!rows().length && box) { box.value = no; ['input', 'keyup'].forEach(function (t) { box.dispatchEvent(new Event(t, {bubbles: true})); }); try { jQuery(box).trigger('keyup'); } catch (e) {} await new Promise(function (r) { setTimeout(r, 3500); }); }
  var r = rows()[0]; if (!r) { done({found: false}); return; }
  var a = Array.prototype.filter.call(r.querySelectorAll('a[href]'), function (x) { return /addedit|details|view|edit/i.test(x.getAttribute('href')); })[0];
  done({found: true, href: a ? a.getAttribute('href') : '', row: T(r).slice(0, 160)});
})();
"""
SUM_JS = r"""
var num = function (s) { var x = parseFloat(String(s).replace(/,/g, '')); return isNaN(x) ? 0 : x; };
var dr = 0, cr = 0, n = 0;
Array.prototype.forEach.call(document.querySelectorAll('input'), function (e) { var k = ((e.id || '') + ' ' + (e.name || '') + ' ' + (e.className || '')).toLowerCase();
  if (/total/.test(k)) return; if (/debit|مدين/.test(k)) { dr += num(e.value); n++; } else if (/credit|دائن/.test(k)) { cr += num(e.value); n++; } });
if (!n) { Array.prototype.forEach.call(document.querySelectorAll('table'), function (t) { var hs = Array.prototype.map.call(t.querySelectorAll('thead th'), function (h) { return h.innerText; });
  var di = hs.findIndex(function (h) { return /مدين|debit/i.test(h); }), ci = hs.findIndex(function (h) { return /دائن|credit/i.test(h); });
  if (di < 0 || ci < 0) return; Array.prototype.forEach.call(t.querySelectorAll('tbody tr'), function (tr) { var td = tr.querySelectorAll('td'); if (td[di]) { dr += num(td[di].innerText); cr += num(td[ci].innerText); n++; } }); }); }
return {n: n, dr: Math.round(dr * 100) / 100, cr: Math.round(cr * 100) / 100};
"""


def journal_of(session, list_path, doc_no):
    d, t0 = session.driver, time.time()
    session.open(list_path)
    time.sleep(2)
    d.set_script_timeout(30)
    f = d.execute_async_script(JE_JS, doc_no) or {}
    if not f.get("found") or not f.get("href"):
        return {"kind": "skip", "notarget": True, "ms": int((time.time() - t0) * 1000), "msg": f"مالقيتش قيد مربوط بالمستند {doc_no} في القيود"}
    session.open(f["href"])
    time.sleep(2)
    v = d.execute_script(SUM_JS) or {}
    ms = int((time.time() - t0) * 1000)
    if not v.get("n"):
        return {"kind": "skip", "notarget": True, "ms": ms, "msg": "فتحت القيد بس مالقيتش خانات مدين/دائن أقراها"}
    ev = f"🧾 قيد المستند {doc_no}: مدين {v['dr']:,.2f} / دائن {v['cr']:,.2f} ({v['n']} خانة) · {f.get('row', '')}"
    if abs(v["dr"] - v["cr"]) > 0.01 or not v["dr"]:
        return {"kind": "wrong", "ms": ms, "msg": f"قيد المستند {doc_no} مش متزن: مدين {v['dr']:,.2f} / دائن {v['cr']:,.2f}", "evidence": ev}
    return {"kind": "ok", "ms": ms, "note": f"🧾 قيد المستند {doc_no} متزن: {v['dr']:,.2f} = {v['cr']:,.2f} ✅", "evidence": ev}


# ------------------------------------------------------------------ 🧮 the trial balance's totals
TB_JS = r"""
function docs(w) { var out = [w.document]; Array.prototype.forEach.call(w.document.querySelectorAll('iframe'), function (f) { try { out = out.concat(docs(f.contentWindow)); } catch (e) {} }); return out; }
var num = function (s) { var x = parseFloat(String(s).replace(/[,\s]/g, '').replace(/[()]/g, '')); return isNaN(x) ? null : x; };
var best = null;
docs(window).forEach(function (d) { Array.prototype.forEach.call(d.querySelectorAll('tr, div'), function (r) { var t = (r.innerText || '');
  if (t.length > 400 || !/الإجمالي|الاجمالي|إجمالي|Total/i.test(t)) return; var ns = (t.match(/-?[\d,]+\.\d{2}/g) || []).map(num).filter(function (x) { return x !== null; });
  if (ns.length >= 2) best = {row: t.replace(/\s+/g, ' ').slice(0, 200), ns: ns}; }); });
return best;
"""


def trial_balance(session, path):
    d, t0 = session.driver, time.time()
    session.open(path)
    v, ms = session.wait_report()
    if v.startswith("error:"):
        return {"kind": "reject", "ms": ms, "msg": "ميزان المراجعة: " + v[6:]}
    if v in ("params", "timeout"):
        return {"kind": "skip", "notarget": True, "ms": ms, "msg": "الميزان محتاج فلتر أو ما طلعش — مقدرتش أقرا الأرقام"}
    b = d.execute_script(TB_JS)
    ms = int((time.time() - t0) * 1000)
    if not b:
        return {"kind": "skip", "notarget": True, "ms": ms, "msg": "مالقيتش سطر الإجمالي في الميزان"}
    ns = sorted({abs(x) for x in b["ns"]}, reverse=True)
    dr, cr = (b["ns"][-2], b["ns"][-1]) if len(b["ns"]) >= 2 else (0, 0)
    pairs = [(b["ns"][i], b["ns"][i + 1]) for i in range(0, len(b["ns"]) - 1, 2)]
    ok = any(abs(a - c) < 0.01 and a for a, c in pairs) or (len(ns) >= 2 and abs(ns[0] - ns[1]) < 0.01)
    ev = "⚖️ سطر الإجمالي: " + b["row"]
    if not ok:
        return {"kind": "wrong", "ms": ms, "msg": f"ميزان المراجعة مش متزن: {dr:,.2f} / {cr:,.2f}", "evidence": ev}
    return {"kind": "ok", "ms": ms, "note": "⚖️ ميزان المراجعة متزن ✅", "evidence": ev}


# ------------------------------------------------------------------ ✅ approving our own document
APPROVE_JS = r"""
var no = String(arguments[0] || '').trim();
if (!no) return {found: false, n: 0};  // never approve a document that isn't ours
var T = function (e) { return (e && e.innerText || '').replace(/\s+/g, ' ').trim(); };
var rows = Array.prototype.filter.call(document.querySelectorAll('table tbody tr'), function (tr) { return Array.prototype.some.call(tr.querySelectorAll('td'), function (td) { return T(td) === no; }); });
if (!rows.length) return {found: false, n: document.querySelectorAll('table tbody tr').length};
var b = Array.prototype.filter.call(rows[0].querySelectorAll('a, button, input[type=button]'), function (e) { return /اعتماد|موافقة|approve/i.test(T(e) + ' ' + (e.title || '') + ' ' + (e.value || '')); })[0];
if (!b) return {found: true, button: false, row: T(rows[0]).slice(0, 140)};
window.confirm = function () { return true; }; b.click(); return {found: true, button: true, row: T(rows[0]).slice(0, 140)};
"""


def approve(session, path, doc_no=""):
    d, t0 = session.driver, time.time()
    session.open(path)
    time.sleep(2)
    v = d.execute_script(APPROVE_JS, doc_no) or {}
    if not v.get("found"):
        return {"kind": "skip", "notarget": True, "ms": int((time.time() - t0) * 1000),
                "msg": f"مفيش مستند {doc_no or ''} مستني اعتماد في الشاشة ({v.get('n', 0)} سطر)"}
    if not v.get("button"):
        return {"kind": "skip", "notarget": True, "ms": int((time.time() - t0) * 1000), "msg": "مالقيتش زرار اعتماد على المستند"}
    time.sleep(3)
    try:
        al = d.switch_to.alert
        al.accept()
    except Exception:
        pass
    still = d.execute_script(APPROVE_JS.replace("b.click();", ""), doc_no) or {}
    ms = int((time.time() - t0) * 1000)
    if still.get("found") and still.get("button"):
        return {"kind": "wrong", "ms": ms, "msg": "ضغطت اعتماد والمستند لسه في قايمة الانتظار", "evidence": "✅ " + v.get("row", "")}
    return {"kind": "ok", "ms": ms, "note": f"✅ اعتمدت المستند {doc_no} وخرج من قايمة الانتظار", "evidence": v.get("row", "")}


# ------------------------------------------------------------------ 🖥️ IT support: every screen in the menu opens and loads its data
SWEEP_JS = r"""
var paths = arguments[0], done = arguments[arguments.length - 1], out = [];
var bad = /<title>[^<]*(error|exception|not found|404|500|خطأ)[^<]*<\/title>|Server Error in|Runtime Error|The resource cannot be found|Exception Details|حدث خطأ غير متوقع/i;
var next = 0;
async function one(path) {
  var t0 = performance.now(), r = {p: path};
  try {
    var res = await fetch(path, {credentials: 'same-origin', redirect: 'follow'});
    r.st = res.status; r.url = res.url; var t = await res.text(); r.ms = Math.round(performance.now() - t0);
    var m = t.match(bad); if (m) r.err = m[0].replace(/<[^>]+>/g, '').slice(0, 90);
    if (/\/login/i.test(res.url)) r.login = true;
  } catch (e) { r.st = 0; r.err = String(e).slice(0, 80); }
  out.push(r);
}
async function worker() { while (next < paths.length) await one(paths[next++]); }
Promise.all([worker(), worker(), worker(), worker()]).then(function () { done(out); });   // 4 at a time: the whole menu in minutes, gentle on the server
"""
ASSETS_JS = r"""
var done = arguments[arguments.length - 1], out = [];
var srcs = Array.prototype.map.call(document.querySelectorAll('script[src], link[rel=stylesheet][href]'), function (e) { return e.getAttribute('src') || e.getAttribute('href'); })
  .concat(performance.getEntriesByType('resource').filter(function (e) { return /script|link|css/.test(e.initiatorType); }).map(function (e) { return e.name; }))
  .map(function (s) { try { var u = new URL(s, location.href); return u.host === location.host ? u.pathname + u.search : ''; } catch (e) { return ''; } })
  .filter(function (s, i, a) { return s && a.indexOf(s) === i; });   // this site's files only, each once
(async function () {
  for (var i = 0; i < srcs.length && i < 60; i++) {
    try { var r = await fetch(srcs[i], {credentials: 'same-origin', method: 'GET'}); if (r.status >= 400) out.push({src: srcs[i].split('?')[0], st: r.status}); } catch (e) {}
  }
  done(out);
})();
"""
DATA_JS = r"""
var vis = function (e) { return !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length)); };
var proc = Array.prototype.some.call(document.querySelectorAll('.dataTables_processing, .loading, .spinner-border, .k-loading-mask'), vis);
var rows = Array.prototype.filter.call(document.querySelectorAll('table tbody tr'), function (tr) { return vis(tr) && !tr.querySelector('.dataTables_empty'); }).length;
var empty = !!document.querySelector('.dataTables_empty');
var tables = document.querySelectorAll('table').length, report = !!document.querySelector('.dxrd-preview, .dx-designer, iframe[src*="Report"]');
return {proc: proc, rows: rows, empty: empty, tables: tables, report: report};
"""


ACTION_RE = re.compile(r"log_?out|sign_?out|delete|remove|backup|restore|recovery|clear|reset|import", re.I)   # a menu link that DOES something is never opened by a check


def _menu_paths(menu, limit):
    paths = []
    for x in menu or []:
        p = str(x.get("path") or "")
        if p and not p.lower().startswith(("javascript", "#", "http", "mailto")) and not ACTION_RE.search(p) and p not in paths:
            paths.append(p)
    return paths[:limit]


def _open_list(session, p, tries=10, wait=.8):
    """a list screen opened like a person -> (rows | empty | stuck | none | error | fail, ms until its data showed, error)"""
    d, t0 = session.driver, time.time()
    try:
        o = session.open(p)
        if o.get("kind") in ("error", "denied", "login"):
            return "error", 0, o.get("msg", o.get("kind"))
        v = {}
        for _ in range(tries):
            v = d.execute_script(DATA_JS) or {}
            if not v.get("proc") and (v.get("rows") or v.get("empty") or not v.get("tables")):
                break
            time.sleep(wait)
        ms = int((time.time() - t0) * 1000)
        return ("stuck" if v.get("proc") else "rows" if v.get("rows") else "empty" if v.get("empty") else "none"), ms, ""
    except Exception as ex:
        return "fail", 0, str(ex)[:120]


LIST_RE = re.compile(r"^/(?!Report/)[A-Za-z_]\w*(/index)?/?(\?[^/]*)?$", re.I)   # NQ ERP's lists: «/SalesInvoice», «/X/Index», «/X/?typeId=1»
SLOW_MS, WORSE_X = 8000, 2.0          # a list that takes longer than 8 s to show its data · twice as slow as this morning


def it_speed(session, menu, before=None, limit=40):
    """🐢 Fahd's speed round: the list screens opened like a person, timed until their data shows; the slowest first,
    and (after lunch) the screens that got much slower than this morning. -> result, {path: ms} to compare with later"""
    t0 = time.time()
    lists = [p for p in _menu_paths(menu, 2000) if LIST_RE.match(p)]
    lists = lists[::max(1, len(lists) // limit)][:limit]                 # spread over the whole menu, not only its first module
    if not lists:
        return {"kind": "skip", "notarget": True, "ms": 0, "msg": "مفيش شاشات قوايم في المنيو أقيس سرعتها"}, {}
    times = {}
    for p in lists:
        st, ms, _ = _open_list(session, p, tries=40, wait=.5)          # waits up to 20 s for the data
        if st in ("rows", "empty", "stuck"):
            times[p] = ms if st != "stuck" else max(ms, 20000)
    if not times:
        return {"kind": "skip", "ms": int((time.time() - t0) * 1000), "msg": "ولا شاشة قوايم فتحت عشان أقيسها"}, {}
    ranked = sorted(times.items(), key=lambda kv: -kv[1])
    slow = [(p, ms) for p, ms in ranked if ms > SLOW_MS]
    worse = [(p, ms, before[p]) for p, ms in ranked if before and before.get(p) and ms > 3000 and ms >= before[p] * WORSE_X]
    avg = sum(times.values()) / len(times) / 1000
    lines = [f"⏱️ قست {len(times)} شاشة قوايم لحد ما البيانات ظهرت — المتوسط {avg:.1f} ث"]
    lines += [f"{'🐢' if ms > SLOW_MS else '·'} {p} → {ms / 1000:.1f} ث" for p, ms in ranked[:10]]
    lines += [f"📉 {p} → {ms / 1000:.1f} ث (الصبح {b / 1000:.1f} ث)" for p, ms, b in worse[:8]]
    r = {"ms": int((time.time() - t0) * 1000), "evidence": "\n".join(lines)}
    if slow or worse:
        msg = (f"{len(slow)} شاشة بتاخد أكتر من {SLOW_MS // 1000} ث عشان تظهر بياناتها (الأبطأ {ranked[0][0]}: {ranked[0][1] / 1000:.1f} ث)" if slow else "")
        if worse:
            msg += (" · " if msg else "") + f"{len(worse)} شاشة بقت أبطأ من الصبح ×{WORSE_X:g} أو أكتر"
        return {**r, "kind": "wrong", "msg": msg}, times
    return {**r, "kind": "ok", "note": f"⏱️ كل الـ {len(times)} شاشة قوايم بتظهر بياناتها في أقل من {SLOW_MS // 1000} ث — المتوسط {avg:.1f} ث ✅"}, times


def it_sweep(session, menu, limit=2000):
    """1) every menu link fetched inside the signed-in session: 404 / 500 / error page / sent back to login
       2) the list screens opened like a person: their table fills (rows), shows «no data», or stays loading"""
    d, t0 = session.driver, time.time()
    paths = _menu_paths(menu, limit)
    if not paths:
        return {"kind": "skip", "notarget": True, "ms": 0, "msg": "مفيش منيو للمستخدم أفتح منه الشاشات"}
    session.open(paths[0])
    d.set_script_timeout(max(120, len(paths) * 2))
    res = d.execute_async_script(SWEEP_JS, paths) or []
    broken = [r for r in res if r.get("st", 0) >= 400 or r.get("st") == 0 or r.get("err")]
    login = [r for r in res if r.get("login")]
    lists = [r["p"] for r in res if r not in broken and not r.get("login") and LIST_RE.match(r["p"])][:25]
    stuck, emptyl, filled = [], [], 0
    for p in lists:
        st, _, err = _open_list(session, p)
        if st == "error":
            broken.append({"p": p, "st": 200, "err": err})
        elif st == "stuck":
            stuck.append(p)
        elif st == "rows":
            filled += 1
        elif st == "empty":
            emptyl.append(p)
    assets = {}
    for p in [paths[0]] + lists[:1] + [q for q in paths if "/AddEdit" in q][:1]:   # the files the home / a list / a form load: a missing script = errors on every screen
        try:
            session.open(p)
            for a in d.execute_async_script(ASSETS_JS) or []:
                assets.setdefault(a["src"], a)
        except Exception:
            continue
    assets = list(assets.values())
    ms = int((time.time() - t0) * 1000)
    slow = [r for r in res if r.get("ms", 0) > 8000]
    lines = [f"🖥️ فتحت {len(res)} شاشة من المنيو: {len(res) - len(broken) - len(login)} سليمة"]
    if lists:
        lines.append(f"📋 {len(lists)} شاشة قوايم: {filled} حمّلت بيانات · {len(emptyl)} فاضية (مفيش بيانات) · {len(stuck)} فضلت تحمّل")
    for r in broken[:15]:
        lines.append(f"⛔ {r['p']} → {('HTTP ' + str(r['st'])) if r.get('st') else 'ما فتحتش'}{(' · ' + r['err']) if r.get('err') else ''}")
    for p in stuck[:8]:
        lines.append(f"⏳ {p} → فضلت تحمّل ومطلعتش بيانات")
    for r in slow[:6]:
        lines.append(f"🐢 {r['p']} → {r['ms'] / 1000:.1f} ث")
    if login:
        lines.append(f"🔑 {len(login)} شاشة رجّعت لصفحة الدخول (جلسة/صلاحية)")
    for a in assets[:8]:
        lines.append(f"🧩 ملف بتحمّله كل الصفحات مش موجود: {a['src']} → HTTP {a['st']}")
    ev = "\n".join(lines)
    if assets and not (broken or stuck):
        return {"kind": "wrong", "ms": ms, "evidence": ev,
                "msg": f"كل الـ {len(res)} شاشة بتفتح، بس {len(assets)} ملف بتحمّله الصفحات مش موجود ({', '.join(a['src'] for a in assets[:3])}) — بيطلّع أخطاء في كل شاشة"}
    if broken or stuck:
        n404 = sum(1 for r in broken if r.get("st") == 404)
        n500 = sum(1 for r in broken if r.get("st", 0) >= 500)
        return {"kind": "wrong", "ms": ms, "evidence": ev,
                "msg": f"من {len(res)} شاشة: {len(broken)} فيها مشكلة" + (f" ({n404}× 404" if n404 else " (") + (f"، {n500}× خطأ سيرفر" if n500 else "") + ")"
                       + (f" و{len(stuck)} مش بتحمّل بيانات" if stuck else "")}
    return {"kind": "ok", "ms": ms, "evidence": ev, "note": f"🖥️ فتحت كل الـ {len(res)} شاشة في المنيو — كلها شغالة، و{filled} شاشة قوايم حمّلت بياناتها ✅"}


# ---------------------------------------------------------------- 📒 the accountant's daily books check (read only)
POSTS = {"sales_invoice", "purchase_invoice", "receipt_voucher", "payment_voucher", "sales_return", "purchase_return", "journal_entry"}   # screens that make a journal entry


def books_check(session, site, since):
    """today's journal from «مراجعة قيود اليومية» (the same JSON that screen reads; a POST that only reads):
    1) every entry: debit = credit   2) every document the company saved today on a posting screen has its entry"""
    from engine.journal_check import READ_JS, URL
    from simulation.real.writer import Ledger
    d, t0 = session.driver, time.time()
    session.open("/")
    d.set_script_timeout(60)
    js = READ_JS.replace("bad: all.filter(", "all: all.map(e => ({doc: String(e.doc || ''), type: e.type, d: e.d, c: e.c})), bad: all.filter(")
    r = d.execute_async_script(js, URL, since, since) or {}
    ms = int((time.time() - t0) * 1000)
    if not r.get("ok"):
        return {"kind": "skip", "notarget": True, "ms": ms, "msg": f"مقدرتش أقرا «مراجعة قيود اليومية» ({r.get('s')}): {str(r.get('err', ''))[:120]}"}
    entries, bad = r.get("all") or [], r.get("bad") or []
    nums = {e["doc"].strip() for e in entries if e.get("doc")}
    ours = [x for x in Ledger._all() if x["site"] == site and x["screen"] in POSTS and not x.get("deleted") and str(x.get("at", ""))[:10] >= since]
    missing = [x for x in ours if str(x["no"]).strip() not in nums]
    lines = [f"📒 قيود النهارده: {len(entries)} قيد · {len(bad)} مش متزن · مستنداتنا اللي بتعمل قيد: {len(ours)} · من غير قيد: {len(missing)}"]
    lines += [f"⚖️ {e.get('type')} رقم {e.get('doc')}: مدين {e['d']:,.2f} · دائن {e['c']:,.2f} · الفرق {e['diff']:+,.2f}" for e in bad[:10]]
    lines += [f"❓ {x['screen']} رقم {x['no']} اتحفظ ومالوش قيد في قيود اليوم" for x in missing[:10]]
    ev = "\n".join(lines)
    if bad or missing:
        msg = "، ".join(p for p in (f"{len(bad)} قيد مش متزن (مجموع الفرق {sum(e['diff'] for e in bad):+,.2f})" if bad else "",
                                       f"{len(missing)} مستند اتحفظ ومالوش قيد" if missing else "") if p)
        return {"kind": "wrong", "ms": ms, "msg": msg, "evidence": ev}
    return {"kind": "ok", "ms": ms, "evidence": ev, "note": f"📒 {len(entries)} قيد النهارده كلهم متزنين، وكل مستند من {len(ours)} مستند ليه قيده ✅"}


# ---------------------------------------------------------------- 🖼️ Fahd's UI round: look changes · accessibility · page timing (read only)
AXE = Path(__file__).parent / "vendor" / "axe.min.js"          # axe-core 4.10 (Deque, MPL-2.0): the accessibility checker the big sites use
MASK_JS = r"""                                                  // the data changes every day, the screen's shape shouldn't: hide the data, keep the layout
var st = document.getElementById('__nqmask') || document.createElement('style'); st.id = '__nqmask';
st.textContent = 'tbody td, tbody td *, .dataTables_info, input, textarea, select, .select2-selection__rendered, time, .badge, .toast, .swal2-container, .loading, [class*=spinner] { color: transparent !important; caret-color: transparent !important; } img[src*=avatar], canvas { visibility: hidden !important; } * { animation: none !important; transition: none !important; }';
document.head.appendChild(st); window.scrollTo(0, 0); return true;
"""
TIMING_JS = r"""
var n = performance.getEntriesByType('navigation')[0] || {}, rs = performance.getEntriesByType('resource');
var kb = rs.reduce(function (a, r) { return a + (r.transferSize || 0); }, n.transferSize || 0) / 1024;
return {ttfb: Math.round(n.responseStart || 0), dom: Math.round(n.domContentLoadedEventEnd || 0), load: Math.round(n.loadEventEnd || 0), requests: rs.length + 1, kb: Math.round(kb)};
"""
AXE_RUN_JS = r"""
var done = arguments[arguments.length - 1];
if (!window.axe) { done({err: 'axe not loaded'}); return; }
axe.run(document, {runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa']}, resultTypes: ['violations']}).then(function (r) {
  done({v: r.violations.filter(function (v) { return v.impact === 'critical' || v.impact === 'serious'; })
    .map(function (v) { return {id: v.id, impact: v.impact, help: v.help, n: v.nodes.length}; })});
}).catch(function (e) { done({err: String(e).slice(0, 120)}); });
"""
DIFF_PIXEL, DIFF_SHARE = 40, 0.04       # a pixel counts when it moved by > 40 (of 255); a screen «changed» when > 4% of it did


def look_change(old_png, new_png):
    """share of the screen that changed between two screenshots (0..1); None when they can't be compared (another size = the layout moved)"""
    from PIL import Image, ImageChops
    a, b = Image.open(old_png).convert("L"), Image.open(new_png).convert("L")
    if a.size != b.size:
        return None
    d = ImageChops.difference(a, b).point(lambda p: 255 if p > DIFF_PIXEL else 0)
    return sum(d.histogram()[255:]) / float(a.size[0] * a.size[1])


def ui_audit(session, menu, folder, limit=15):
    """🖼️ each list screen like a person (data hidden): its picture against the last day's, axe (serious / critical only), and its timing.
    -> result; pictures kept in folder/<date>/ so tomorrow compares with today"""
    import datetime as _dt
    t0, d = time.time(), session.driver
    today = folder / _dt.date.today().isoformat()
    today.mkdir(parents=True, exist_ok=True)
    before = sorted(p for p in folder.iterdir() if p.is_dir() and p.name < today.name)[-1:] if folder.exists() else []
    lists = [p for p in _menu_paths(menu, 2000) if LIST_RE.match(p)]
    lists = lists[::max(1, len(lists) // limit)][:limit]
    axe_src = AXE.read_text(encoding="utf-8") if AXE.exists() else ""
    rows, changed, a11y, slow = [], [], {}, []
    for p in lists:
        st, ms, _ = _open_list(session, p, tries=30, wait=.5)
        if st in ("error", "fail"):
            continue
        slug = re.sub(r"[^A-Za-z0-9]+", "_", p).strip("_")[:60] or "home"
        try:
            tm = d.execute_script(TIMING_JS) or {}
            d.execute_script(MASK_JS)
            time.sleep(.4)
            shot = today / f"{slug}.png"
            d.save_screenshot(str(shot))
            ch = None
            if before and (before[0] / f"{slug}.png").exists():
                ch = look_change(before[0] / f"{slug}.png", shot)
                if ch is None or ch > DIFF_SHARE:
                    changed.append((p, ch))
            if axe_src:
                d.execute_script(axe_src)
                d.set_script_timeout(40)
                for v in (d.execute_async_script(AXE_RUN_JS) or {}).get("v") or []:
                    a = a11y.setdefault(v["id"], {**v, "screens": 0})
                    a["screens"] += 1
            if (tm.get("load") or 0) > 8000:
                slow.append((p, tm["load"]))
            rows.append((p, tm, ch))
        except Exception:
            continue
    if not rows:
        return {"kind": "skip", "notarget": True, "ms": int((time.time() - t0) * 1000), "msg": "ولا شاشة قوايم فتحت عشان أراجع شكلها"}
    crit = [a for a in a11y.values() if a["impact"] == "critical"]
    lines = [f"🖼️ راجعت {len(rows)} شاشة" + (f" وقارنتها بصور {before[0].name}" if before else " (أول يوم: الصور دي هي الأساس للمقارنة بكرة)")]
    lines += [f"🔀 {p}: " + ("المقاس اتغير — التصميم اتحرك" if ch is None else f"{ch:.0%} من الشاشة شكله اتغير") for p, ch in changed[:10]]
    lines += [f"♿ {a['help']} ({a['impact']}) — في {a['screens']} شاشة" for a in sorted(a11y.values(), key=lambda a: (a["impact"] != "critical", -a["screens"]))[:8]]
    lines += [f"⏱️ {p}: أول بايت {tm.get('ttfb', 0)}ms · الصفحة {tm.get('load', 0) / 1000:.1f}ث · {tm.get('requests', 0)} طلب · {tm.get('kb', 0)}KB" for p, tm, _ in rows[:6]]
    r = {"ms": int((time.time() - t0) * 1000), "evidence": "\n".join(lines)}
    if changed or crit:
        msg = "، ".join(x for x in (f"{len(changed)} شاشة شكلها اتغير عن آخر يوم — اتأكد إنه مقصود" if changed else "",
                                    f"{len(crit)} مشكلة سهولة استخدام حرجة" if crit else "") if x)
        return {**r, "kind": "wrong", "msg": msg}
    note = f"🖼️ {len(rows)} شاشة: " + ("مفيش شاشة شكلها اتغير" if before else "الصور اتحفظت كأساس للمقارنة") + (f" · {len(a11y)} ملاحظة سهولة استخدام (مش حرجة)" if a11y else " · مفيش مشاكل سهولة استخدام") + " ✅"
    return {**r, "kind": "ok", "note": note}
