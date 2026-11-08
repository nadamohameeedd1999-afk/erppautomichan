"""
🔒 Read-only guard for clients' live systems.

A site marked «client» (Settings -> test sites; every URL without test / demo / staging is a client unless you change it)
can only be opened and read: any test that would save, edit, delete or clean up stops BEFORE touching the site,
with a clear message. The browser itself is also locked (see BLOCK_WRITES_JS, injected by tests/conftest.py):
a save / delete request or a form post from the page is cancelled even if some click reaches it.
"""
import re


class ReadOnlySite(AssertionError):
    pass


def read_only():
    try:
        from config.settings import READ_ONLY
        return bool(READ_ONLY)
    except Exception:
        return False


def require_write(what):
    if read_only():
        from config.settings import BASE_URL
        raise ReadOnlySite(f"🔒 «{what}» اتوقف: الموقع {BASE_URL} متسجل «نظام عميل» (قراءة بس) — مفيش حفظ ولا تعديل ولا حذف عليه.\n"
                           "   لو ده موقع اختبار: الإعدادات ← مواقع الاختبار ← تعديل ← نوع الموقع «موقع اختبار».")


# words in a request URL that mean it changes data (POSTs that only read — lists, reports, lookups — still pass)
WRITE_WORDS = (r"save|delete|remove|update|insert|create|add(?!ress)|edit(?!or)|post(?!al)|approve|reject|cancel|close|"
               r"import|upload|send|confirm|submit|transfer|restore|reset|recalc|migrate|execute|post(?:ing)?")

BLOCK_WRITES_JS = r"""
(() => {
  if (window.__nqReadOnly) return; window.__nqReadOnly = true; window.__nqBlocked = [];
  const W = new RegExp('(^|[/_\\-.?=&])(' + %s + ')', 'i');
  const LOGIN = /\/(login|account\/log|home\/(setactivity|setbranch)|logout)/i;
  const G = /(^|[\/_\-.?=&])(delete|remove|approve|reject|recalc|unpost|post(?:ing)?)(?![a-z])/i;   // even a GET to these changes data
  const bad = (method, url) => {
    method = (method || 'GET').toUpperCase(); url = String(url || '');
    if (LOGIN.test(url) || /^\/?(login|account\/login)?\/?$/i.test(location.pathname)) return false;   // the login page (activity / branch / sign in) is never blocked
    let path = url; try { path = new URL(url, location.href).pathname; } catch (e) {}
    if (method === 'GET' || method === 'HEAD') return G.test(path);
    return W.test(path);
  };
  const note = (m, u) => { window.__nqBlocked.push(m + ' ' + u); console.warn('[NQ read-only] blocked ' + m + ' ' + u); };
  const of = window.fetch;
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url), m = (init && init.method) || (input && input.method) || 'GET';
    if (bad(m, url)) { note(m, url); return Promise.reject(new Error('NQ read-only: blocked')); }
    return of.apply(this, arguments);
  };
  const oo = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__nq = [m, u]; return oo.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function () {
    if (this.__nq && bad(this.__nq[0], this.__nq[1])) { note(this.__nq[0], this.__nq[1]); try { this.abort(); } catch (e) {} return; }
    return os.apply(this, arguments);
  };
  const block = f => { const m = (f.getAttribute('method') || 'GET'), a = f.getAttribute('action') || location.href;
    if (m.toUpperCase() !== 'GET' && bad('POST', '/submit/' + a)) { note('FORM ' + m, a); return true; } return false; };
  document.addEventListener('click', e => { const a = e.target.closest && e.target.closest('a[href]');
    if (a && bad('GET', a.getAttribute('href'))) { note('LINK', a.getAttribute('href')); e.preventDefault(); e.stopImmediatePropagation(); } }, true);
  document.addEventListener('submit', e => { if (block(e.target)) { e.preventDefault(); e.stopImmediatePropagation(); } }, true);
  const fs = HTMLFormElement.prototype.submit;
  HTMLFormElement.prototype.submit = function () { if (!block(this)) return fs.apply(this, arguments); };
})();
""" % repr(WRITE_WORDS).replace("\\\\", "\\")


def lock_browser(driver):
    """inject BLOCK_WRITES_JS into every page this browser opens (Chrome DevTools)"""
    if not read_only():
        return False
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": BLOCK_WRITES_JS})
        driver.execute_cdp_cmd("Page.enable", {})
        return True
    except Exception:
        return False
