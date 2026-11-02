"""
Save like a person would (الحفظ الذكي — used by the automatic test):

  1. press save
  2. rejected? read WHY: the message boxes / alerts, the red field messages, the required fields still empty
  3. fix what the messages point at:
       - a field named in a message («العميل مطلوب») or required and still empty -> fill it
       - a required field the user can't type in (filled by a button, e.g. «بناء على» by «سداد آلي») -> press the
         buttons that fill things (سداد / توزيع / احتساب / جلب …), confirming their message boxes
       - a message about files -> attach a test file and press the upload button
  4. save again — up to 3 tries. Every try and every fix is written in the result.

Also collects the ERP page's own technical errors (JavaScript errors, server 500 / 404 answers) from the browser
console: after an ERP update these are usually the real reason a screen stops saving.
"""
import re
import time

from utils.logger import logger

STATE_JS = r"""
function vis(e){ if (!e) return false; var r = e.getBoundingClientRect(), s = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; }
function txt(e){ return (e && (e.innerText || e.textContent) || '').replace(/\s+/g, ' ').trim(); }
function lbl(e){
  var l = e.id ? document.querySelector('label[for="' + CSS.escape(e.id) + '"]') : null;
  if (!l) { var p = e.parentElement, d = 0; while (p && d < 3 && !l) { l = p.querySelector('label'); p = p.parentElement; d++; } }
  return ((l && txt(l)) || e.getAttribute('placeholder') || e.id || e.name || '').replace(/\s*\*\s*$/, '').trim(); }
var fields = [];
document.querySelectorAll('input, select, textarea').forEach(function(e, i){
  var t = (e.type || '').toLowerCase();
  if (['submit', 'button', 'reset', 'image', 'search', 'checkbox', 'radio'].indexOf(t) !== -1) return;
  if (e.closest('.select2-container, nav, .navbar, header, .dataTables_filter, .modal:not(.show)')) return;
  var isS2 = e.tagName === 'SELECT' && e.classList.contains('select2-hidden-accessible');
  var box = isS2 && e.id ? document.getElementById('select2-' + e.id + '-container') : e;
  if (t === 'hidden' && !isS2) return;
  if (!vis(box && (isS2 ? box.closest('.select2-container') : box))) return;
  if (!e.id) e.id = '__heal_' + i;
  var val = e.tagName === 'SELECT' ? ((e.options[e.selectedIndex] || {}).text || '').trim() : (e.value || '').trim();
  if (e.tagName === 'SELECT' && (!e.value || /^(-+)?\s*(اختر|اختار|--|select|choose)/i.test(val))) val = '';
  fields.push({id: e.id, label: lbl(e), tag: e.tagName, kind: e.tagName === 'SELECT' ? (isS2 ? 'select2' : 'select') :
               (e.tagName === 'TEXTAREA' ? 'textarea' : (t === 'file' ? 'file' : (t === 'number' ? 'number' : (t === 'date' ? 'date' : 'text')))),
               value: val, readonly: !!(e.readOnly || e.disabled),
               required: !!(e.required || e.hasAttribute('data-val-required') || e.getAttribute('aria-required') === 'true'),
               invalid: e.classList.contains('input-validation-error') || e.classList.contains('is-invalid') || e.getAttribute('aria-invalid') === 'true',
               files: t === 'file' ? (e.files ? e.files.length : 0) : 0});
});
var msgs = [];
document.querySelectorAll('.field-validation-error, .invalid-feedback, .text-danger, .alert-danger, .validation-summary-errors li, .toast, .toast-message, .swal2-html-container, .swal2-title').forEach(function(e){
  var t = txt(e); if (t.replace(/[*\s]/g, '').length > 1 && vis(e) && msgs.indexOf(t) === -1) msgs.push(t); });
return {fields: fields, msgs: msgs.slice(0, 15)};
"""

HELPER_BUTTONS_JS = r"""
function vis(e){ var r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; }
var done = arguments[0] || [], save = arguments[1] || '', out = [];
var GOOD = /(سداد|توزيع|احتساب|حساب|جلب|تحميل البيانات|ربط|اعتماد المبلغ|auto ?pay|distribute|calculate)/i;
var BAD = /(حفظ|save|حذف|delete|الغاء|إلغاء|cancel|اغلاق|إغلاق|close|طباعة|print|رجوع|back|خروج|logout|بحث|search)/i;
document.querySelectorAll('button, a.btn, input[type=button]').forEach(function(b, i){
  if (!vis(b) || b.closest('nav, .navbar, header, .modal:not(.show), .select2-container, .dataTables_wrapper')) return;
  try { if (save && b.matches(save)) return; } catch (e) {}
  var t = (b.innerText || b.value || b.getAttribute('title') || '').replace(/\s+/g, ' ').trim();
  if (!t || t.length > 40 || BAD.test(t) || !GOOD.test(t) || done.indexOf(t) !== -1) return;
  if (!b.id) b.id = '__heal_btn_' + i;
  out.push({id: b.id, text: t});
});
return out;
"""


def console_errors(driver):
    """the ERP page's own errors since the last call: JavaScript exceptions and failed server requests"""
    try:
        logs = driver.get_log("browser")
    except Exception:
        return []
    out = []
    for e in logs:
        if e.get("level") != "SEVERE":
            continue
        m = re.sub(r"^\S+ \d+:\d+ ", "", str(e.get("message", ""))).strip()
        if "favicon" in m or "ERR_TUNNEL" in m or "cdn." in m:
            continue
        m = re.sub(r'^"?JS error in the ERP page: ', "خطأ JavaScript في الصفحة: ", m).rstrip('"')
        m = m.replace("Uncaught ", "").replace("Failed to load resource: the server responded with a status of", "السيرفر رد")
        m = re.sub(r"https?://[^/\s]+", "", m)[:200]
        if m and m not in out:
            out.append(m)
    return out[:10]


def _n(t):
    from engine.text_match import normalize
    return normalize(t)


def _fill(r, f, value_hint=""):
    from engine.auto_test import _strategy
    st, val = _strategy({**f, "value": ""}, "first")
    field = {"id": f["id"], "label": f["label"] or f["id"], "kind": f["kind"], "strategy": st, "value": val,
             "required": False, "depends_on": None, "format": "", "timeout": 10, "wait_after": 0.6}
    got = r.filler.fill_field(field)
    r.filler.steps.append({"id": f["id"], "label": f"{field['label']} (اتملى بعد رفض الحفظ)", "strategy": st, "wanted": val,
                           "result": got, "ok": True, "seconds": 0, "auto": True})
    return got


def heal(r, cfg, tried):
    """one round of fixes after a rejected save. Returns the list of things it did (empty = nothing left to try)."""
    from engine.flows import sample_file
    from engine.auto_fill import UPLOAD_BTN_JS
    d, did = r.driver, []
    try:
        st = d.execute_script(STATE_JS) or {}
    except Exception:
        return did
    msgs = list(dict.fromkeys((r.error_alerts or []) + [a.replace("SweetAlert: ", "").replace("JS: ", "") for a in (r.alerts or [])[-3:]]
                              + (st.get("msgs") or [])))
    text = _n(" ".join(msgs))
    for f in st.get("fields") or []:
        if f["kind"] == "file" or f["value"] or f["id"] in tried:
            continue
        lb = _n(f["label"])
        named = len(lb) > 2 and lb in text
        if not (named or f["required"] or f["invalid"]):
            continue
        tried.add(f["id"])
        if f["readonly"]:
            continue                                    # filled by a button — below
        try:
            got = _fill(r, f)
            did.append(f"ملّيت «{f['label']}» = {got}" + (" (اتذكر في رسالة الرفض)" if named else ""))
            time.sleep(0.6)
        except Exception as e:
            did.append(f"«{f['label']}» محتاج يتملى ومقدرتش: {str(e).splitlines()[0].split('] ')[-1][:80]}")
    # required boxes nobody can type in -> the page's own buttons fill them (سداد آلي / توزيع …)
    locked = [f for f in st.get("fields") or [] if f["readonly"] and not f["value"] and (f["required"] or f["invalid"] or _n(f["label"]) in text)]
    if locked or any(w in text for w in ("سداد", "توزيع", "اختر الفواتير")):
        done = [x[4:] for x in tried if str(x).startswith("btn:")]
        for b in d.execute_script(HELPER_BUTTONS_JS, done, cfg.get("save_button", "")) or []:
            tried.add("btn:" + b["text"])
            try:
                d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", d.find_element("id", b["id"]))
                time.sleep(1)
                while r.accept_js_alert(timeout=1.5) is not None:
                    pass
                r.handle_swals(max_count=3, timeout=2, max_misses=1)
                did.append(f"دست «{b['text']}»" + (f" عشان يملى «{'، '.join(x['label'] for x in locked[:3])}»" if locked else ""))
                time.sleep(1.5)
            except Exception as e:
                did.append(f"«{b['text']}» ما اتداسش: {str(e).splitlines()[0][:80]}")
    # files the page insists on
    if any(w in text for w in ("الملفات", "ملف", "مرفق", "file")) and "files" not in tried:
        tried.add("files")
        for f in st.get("fields") or []:
            if f["kind"] == "file" and not f["files"]:
                try:
                    d.find_element("id", f["id"]).send_keys(str(sample_file("pdf")))
                    time.sleep(0.8)
                    btn = d.execute_script(UPLOAD_BTN_JS, f["id"])
                    time.sleep(2 if btn else 0.5)
                    r.accept_js_alert(timeout=1)
                    r.handle_swals(max_count=2, timeout=1.5, max_misses=1)
                    did.append("رفعت ملف PDF تجريبي في المرفقات" + (f" ودست «{btn}»" if btn else ""))
                except Exception as e:
                    did.append(f"المرفقات: {str(e).splitlines()[0][:80]}")
    return did


SERVER_PATTERNS = [
    (r"Transaction count after EXECUTE|mismatching number of BEGIN and COMMIT",
     "إجراء الحفظ في قاعدة البيانات عمل ROLLBACK جوه transaction مفتوحة (BEGIN/COMMIT مش متطابقين)"),
    (r"(\w+_(Insert|Update|Delete|Save)\w*)\s*:\s*5\d{4}", "إجراء قاعدة البيانات «{1}» رجّع خطأ"),
    (r"\?{3,}", "رسالة الخطأ العربي ظاهرة «????» — الرسالة في قاعدة البيانات مكتوبة varchar مش nvarchar (N'…')"),
    (r"SqlException|Cannot insert|violation of (PRIMARY|UNIQUE) KEY|duplicate key|FOREIGN KEY constraint|deadlock|Timeout expired",
     "خطأ من SQL Server"),
    (r"Server Error|Internal Server Error|Object reference not set|NullReferenceException|status of 500",
     "خطأ في السيرفر (500)"),
]


def server_error(text):
    """the save failed inside the ERP (database / server), not because of the data — a short Arabic diagnosis"""
    found = []
    for pat, msg in SERVER_PATTERNS:
        m = re.search(pat, text or "", re.I)
        if m:
            found.append(msg.replace("{1}", m.group(1) if m.groups() else ""))
    if not found:
        return ""
    raw = re.sub(r"\s+", " ", text or "").strip()[:260]
    return "خطأ تقني من الـ ERP (مش من بيانات الاختبار): " + " · ".join(found) + f" — النص: «{raw}»"


def explain_failure(result):
    """extra lines for the failure message: the tries and the page's technical errors"""
    out = []
    for a in result.get("save_attempts") or []:
        if not a.get("ok") and a.get("did"):
            out.append(f"🔁 محاولة {a['n']} اترفضت ({a['reason'].splitlines()[0][:120]}) → {' · '.join(a['did'])}")
    if result.get("tech_errors"):
        out.append("🐞 أخطاء تقنية في صفحة الـ ERP نفسها: " + " | ".join(result["tech_errors"][:5]))
    return ("\n   " + "\n   ".join(out)) if out else ""


def save_with_healing(r, cfg, result, tries=3):
    """r.save() + r.wait_saved(), and in the automatic test: read why it was rejected, fix it, try again"""
    attempts, tried = [], set()
    pre = console_errors(r.driver)                      # errors while the fields were being filled
    if pre:
        result.setdefault("tech_errors", []).extend(pre)
    ok = False
    for n in range(1, (tries if cfg.get("auto_complete") else 1) + 1):
        r.error_alerts.clear()
        r.save()
        ok = r.wait_saved()
        errs = console_errors(r.driver)
        if ok:
            if attempts:
                attempts.append({"n": n, "ok": True, "errors": errs})
            result.setdefault("tech_errors", []).extend(e for e in errs if e not in result.get("tech_errors", []))
            break
        reason = r.failure_reason()
        server = server_error(" | ".join(r.error_alerts + r.alerts[-3:]) + " " + reason)
        if server:                                     # the database / server failed — filling more fields won't help
            result.setdefault("tech_errors", []).append(server)
            attempts.append({"n": n, "ok": False, "reason": reason, "did": [], "errors": errs, "server": server})
            logger.error(f"🐞 {server}")
            break
        did = heal(r, cfg, tried) if cfg.get("auto_complete") and n < tries else []
        attempts.append({"n": n, "ok": False, "reason": reason, "did": did, "errors": errs})
        result.setdefault("tech_errors", []).extend(e for e in errs if e not in result.get("tech_errors", []))
        logger.warning(f"🔁 الحفظ اترفض (محاولة {n}): {reason.splitlines()[0][:160]}" + (f" → {' · '.join(did)}" if did else ""))
        if not did:
            break
        time.sleep(1)
    result["save_attempts"] = attempts
    return ok
