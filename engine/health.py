"""
🩺 صحة النظام — open EVERY screen of the ERP's menu (and optionally every report) in a few minutes and list the broken ones.

How: log in once with Selenium, read every link of the menu from the home page, then fetch them all from inside the
logged-in page (10 at a time, same cookies) and look at each answer:
  status 500 / 404 / 503 / …, sent back to the login page, a server error page (Server Error, Exception, SqlException),
  or much slower than usual.
The list of broken screens is kept per site (state/health_<site>.json), so every run says:
  🆕 broke since last time · 🔁 still broken · ✅ fixed since last time
and the new / fixed ones are sent right away to Telegram / WhatsApp / webhook (Settings → التنبيهات).
"""
import hashlib
import json
import re
import time
from datetime import datetime

from config import paths
from utils.logger import logger

STATE = paths.STATE_DIR
DEFAULT_SKIP = ["login", "logout", "signout", "tickets", "/support/"]

MENU_JS = r"""
const out = [], seen = new Set();
const txt = e => (e && (e.innerText || e.textContent) || '').replace(/\s+/g, ' ').trim();
document.querySelectorAll('a[href]').forEach(a => {
  const h = a.getAttribute('href') || '';
  if (!h || h[0] === '#' || /^(javascript|mailto|tel):/i.test(h)) return;
  let u; try { u = new URL(h, location.href); } catch (e) { return; }
  if (u.origin !== location.origin) return;
  const p = u.pathname + u.search;
  if (p === '/' || seen.has(p)) return;
  seen.add(p);
  let mod = '', li = a.closest('li'), top = li;
  while (li) { top = li; li = li.parentElement && li.parentElement.closest('li'); }
  if (top && top !== a.closest('li')) { const h2 = top.querySelector(':scope > a, :scope > span, :scope > div'); mod = txt(h2).slice(0, 60); }
  out.push({path: p, name: txt(a).slice(0, 80) || a.getAttribute('title') || p, module: mod});
});
return out;
"""

FETCH_JS = r"""
const [paths, workers, done] = [arguments[0], arguments[1], arguments[arguments.length - 1]];
const ERR = /(server error in|runtime error|unhandled exception|an error occurred while processing|sqlexception|stack trace:|exception details|حدث خطأ غير متوقع|خطأ في الخادم)/i;
const out = {}; let i = 0; const P = new DOMParser();
async function one(p) {
  const t0 = performance.now();
  try {
    const ctl = new AbortController(); const timer = setTimeout(() => ctl.abort(), 30000);
    const r = await fetch(p, {credentials: 'include', signal: ctl.signal}); const html = await r.text(); clearTimeout(timer);
    const login = /\/login/i.test(new URL(r.url).pathname) && !/\/login/i.test(p);
    const body = html.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/gi, ' ');
    const m = body.match(ERR);
    let err = '';
    if (m) { const k = body.indexOf(m[0]); err = body.slice(Math.max(0, k - 40), k + 220).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim(); }
    const title = ((html.match(/<title[^>]*>([\s\S]*?)<\/title>/i) || [])[1] || '').trim().slice(0, 120);
    const ms = Math.round(performance.now() - t0);
    // the screen's data: lists here are rendered by the server -> rows are in the page itself
    let rows = 0, report = /DevExpress|dxrd-|dxbl-|ReportViewer|dx-designer/i.test(html), empty = false;
    if (r.ok && !login && !err) {
      const d = P.parseFromString(html, 'text/html');
      const root = d.querySelector('.content-wrapper, .page-content, main, #content, .main-content, .content') || d.body;
      root.querySelectorAll('table').forEach(t => { if (!t.closest('.modal')) rows = Math.max(rows, t.querySelectorAll('tbody tr').length); });
      const ctrl = p.split('?')[0].replace(/\/(index)?$/i, '').toLowerCase();
      const links = Array.from(root.querySelectorAll('a[href]')).map(a => a.getAttribute('href') || '')
        .filter(h => /addedit|\/create\b|\/add\b|\/new\b/i.test(h) && !/todotask|presencestatus|delete|remove/i.test(h));
      const a = links.find(h => h.toLowerCase().indexOf(ctrl + '/') >= 0);
      if (a) { try { const u = new URL(a, location.origin + p); var addLink = u.pathname + u.search; } catch (e) {} }
      empty = /لا توجد بيانات|لا يوجد بيانات|no data available|no records|لا توجد سجلات/i.test((root.textContent || '').slice(0, 20000)) && rows <= 1;
    }
    out[p] = {s: r.status, ms, login, err, title, size: html.length, rows, report, empty, add: (typeof addLink !== 'undefined' && addLink) || ''};
  } catch (e) { out[p] = {s: 0, ms: Math.round(performance.now() - t0), err: String(e).slice(0, 160)}; }
}
async function w() { while (i < paths.length) { await one(paths[i++]); } }
Promise.all(Array.from({length: workers}, w)).then(() => done(out));
"""


FORMS_JS = r"""
const [paths, workers, done] = [arguments[0], arguments[1], arguments[arguments.length - 1]];
const P = new DOMParser(), out = {}; let i = 0;
const txt = e => (e && (e.innerText || e.textContent) || '').replace(/\s+/g, ' ').trim();
const root = d => d.querySelector('.content-wrapper, .page-content, main, #content, .main-content, .content') || d.body;
async function get(u) { try { const r = await fetch(u, {credentials: 'include'}); return {s: r.status, url: r.url, html: await r.text()}; } catch (e) { return {s: 0, html: ''}; } }
function fields(d) {
  const f = {};
  root(d).querySelectorAll('input, select, textarea').forEach(e => {
    const t = (e.type || '').toLowerCase();
    if (['hidden', 'submit', 'button', 'search', 'reset', 'image'].includes(t) || e.closest('.modal, nav, header, .navbar, aside, .sidebar')) return;
    const k = e.id || e.name; if (!k || f[k]) return;
    const l = e.id ? d.querySelector('label[for="' + e.id + '"]') : null;
    const lab = (txt(l) || e.getAttribute('placeholder') || '').slice(0, 40);
    f[k] = {l: lab.replace(/\s*\*$/, ''), r: !!(e.required || e.hasAttribute('data-val-required') || /\*\s*$/.test(lab)),
            t: e.tagName === 'SELECT' ? 'select' : (t === 'checkbox' ? 'checkbox' : (t === 'date' || /date|تاريخ/i.test(k + lab) ? 'date' : (e.tagName === 'TEXTAREA' ? 'textarea' : 'text')))};
  });
  return f;
}
async function one(p) {
  const L = await get(p); if (L.s !== 200) return;
  const d = P.parseFromString(L.html, 'text/html');
  const ctrl = p.split('?')[0].replace(/\/(index)?$/i, '').toLowerCase();
  const links = Array.from(root(d).querySelectorAll('a[href]')).map(a => a.getAttribute('href') || '')
    .filter(h => /addedit|\/create\b|\/add\b|\/new\b/i.test(h) && !/todotask|presencestatus/i.test(h));
  const add = links.find(h => h.toLowerCase().indexOf(ctrl + '/') >= 0) || links[0];
  if (!add) return;
  const u = new URL(add, location.origin + p), A = await get(u.pathname + u.search);
  out[p] = {add: u.pathname + u.search, s: A.s, f: A.s === 200 && !/\/login/i.test(A.url || '') ? fields(P.parseFromString(A.html, 'text/html')) : null};
}
async function w() { while (i < paths.length) { await one(paths[i++]); } }
Promise.all(Array.from({length: workers}, w)).then(() => done(out));
"""


def compare_forms(old, new):
    """add-form changes between two snapshots -> [(path, what, ok)]"""
    out = []
    for p, n in new.items():
        o = old.get(p)
        if not o:
            continue
        if o.get("f") is not None and n.get("f") is None:
            out.append((p, f"فورم الإضافة بقى مش بيفتح ({n.get('s')}) — كان شغال", False))
            continue
        if o.get("f") is None and n.get("f") is not None:
            out.append((p, "فورم الإضافة رجع يفتح ✅", True))
            continue
        of, nf = o.get("f") or {}, n.get("f") or {}
        lab = lambda f, k: f.get(k, {}).get("l") or k
        added = [k for k in nf if k not in of]
        gone = [k for k in of if k not in nf]
        req = [k for k in nf if k in of and nf[k].get("r") and not of[k].get("r")]
        unreq = [k for k in nf if k in of and of[k].get("r") and not nf[k].get("r")]
        if req:
            out.append((p, "⚠️ بقى إجباري: " + "، ".join(lab(nf, k) for k in req[:12]), False))
        if gone:
            out.append((p, "➖ حقول اتشالت: " + "، ".join(lab(of, k) for k in gone[:12]), False))
        if added:
            out.append((p, "➕ حقول جديدة: " + "، ".join(lab(nf, k) for k in added[:12]) + ("  (منهم إجباري: " + "، ".join(lab(nf, k) for k in added if nf[k].get("r"))[:200] + ")" if any(nf[k].get("r") for k in added) else ""), None))
        if unreq:
            out.append((p, "مابقاش إجباري: " + "، ".join(lab(nf, k) for k in unreq[:12]), None))
    return out


def set_baseline(site_file=None):
    """«اللقطة قبل التحديث»: the last run's screens + forms become the reference until set again"""
    f = site_file or _state_file()
    d = json.loads(f.read_text(encoding="utf-8"))
    d["baseline"] = {"at": d.get("at"), "forms": d.get("forms") or {}, "broken": list((d.get("broken") or {}).keys()),
                     "paths": d.get("paths") or []}
    f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d["baseline"]["at"]


READY_JS = r"""
const vis = e => { const r = e.getBoundingClientRect(); const st = getComputedStyle(e);
  return r.width > 0 && r.height > 0 && st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0'; };
const loaders = Array.from(document.querySelectorAll('#preloader, #status, .loader, .loading, .spinner-border, .dataTables_processing, .blockUI, #pleasewait, .k-loading-mask'))
  .filter(vis).length;
return {ready: document.readyState === 'complete', active: (window.jQuery && jQuery.active) || 0, loaders: loaders};
"""

PERF_JS = r"""
const nav = performance.getEntriesByType('navigation')[0] || {};
const xhr = performance.getEntriesByType('resource').filter(r => r.initiatorType === 'xmlhttprequest' || r.initiatorType === 'fetch')
  .map(r => ({url: r.name.replace(location.origin, '').slice(0, 160), ms: Math.round(r.duration), kb: Math.round((r.transferSize || 0) / 1024)}))
  .sort((a, b) => b.ms - a.ms);
const res = performance.getEntriesByType('resource');
let rows = 0; document.querySelectorAll('table').forEach(t => { if (!t.closest('.modal')) rows = Math.max(rows, t.querySelectorAll('tbody tr').length); });
const xr = performance.getEntriesByType('resource').filter(r => r.initiatorType === 'xmlhttprequest' || r.initiatorType === 'fetch');
const lastEnd = Math.max(nav.loadEventEnd || 0, ...xr.map(r => r.responseEnd || 0));
const sels = Array.from(document.querySelectorAll('select')).map(s => ({id: s.id || s.name || '', n: s.options.length})).sort((a, b) => b.n - a.n);
const inl = Array.from(document.scripts).filter(s => !s.src).reduce((t, s) => t + s.text.length, 0);
return {ttfb: Math.round((nav.responseStart || 0) - (nav.requestStart || 0)), dom: Math.round(nav.domContentLoadedEventEnd || 0),
        all_done: Math.round(lastEnd), page_kb: Math.round((nav.decodedBodySize || 0) / 1024), options: document.querySelectorAll('option').length,
        top_select: sels[0] || null, inline_js_kb: Math.round(inl / 1024), dom_nodes: document.getElementsByTagName('*').length,
        load: Math.round(nav.loadEventEnd || 0), html_kb: Math.round((nav.transferSize || 0) / 1024),
        files: res.length, files_kb: Math.round(res.reduce((t, r) => t + (r.transferSize || 0), 0) / 1024),
        xhr: xhr.slice(0, 8), xhr_n: xhr.length, rows: rows, title: document.title.slice(0, 80),
        error: /server error|runtime error|exception/i.test((document.body && document.body.innerText || '').slice(0, 3000))};
"""


def rate(sec):
    if sec is None:
        return "—"
    return "🟢 سريعة" if sec < 2 else ("🟡 مقبولة" if sec < 5 else ("🟠 بطيئة" if sec < 10 else "🔴 بطيئة جدًا"))


def measure_real(driver, base, link, max_wait=60):
    """open the screen in the real browser like a user and wait until it is really usable:
    page loaded + no ajax running + no loader on screen -> seconds, the server's first answer, every ajax call"""
    t0 = time.time()
    try:
        driver.get(base + link["path"])
    except Exception as e:
        return {**link, "error": f"مفتحتش: {str(e).splitlines()[0][:120]}", "load": None}
    t_nav = time.time() - t0
    calm, end = 0, time.time() + max_wait
    while time.time() < end:
        try:
            st = driver.execute_script(READY_JS) or {}
        except Exception:
            st = {}
        if st.get("ready") and not st.get("active") and not st.get("loaders"):
            calm += 1
            if calm >= 2:
                break
        else:
            calm = 0
        time.sleep(0.4)
    total = time.time() - t0 - (0.4 if calm >= 2 else 0)
    try:
        perf = driver.execute_script(PERF_JS) or {}
    except Exception:
        perf = {}
    why = []
    if (perf.get("page_kb") or 0) >= 1000:
        why.append(f"الصفحة تقيلة {perf['page_kb'] / 1024:.1f} MB")
    ts = perf.get("top_select") or {}
    if (ts.get("n") or 0) >= 2000:
        why.append(f"قايمة «{ts.get('id')}» فيها {ts['n']:,} اختيار جوه الصفحة")
    if (perf.get("inline_js_kb") or 0) >= 500:
        why.append(f"{perf['inline_js_kb']} KB كود JavaScript جوه الصفحة")
    if (perf.get("xhr_n") or 0) >= 10:
        why.append(f"{perf['xhr_n']} طلب بيانات وقت الفتح (السيرفر بيردّ عليهم واحد ورا التاني لنفس المستخدم)")
    total = max(total, (perf.get("all_done") or 0) / 1000)        # until the last data request answered
    return {**link, "load": round(total, 1), "nav": round(t_nav, 1), "timeout": time.time() >= end, "why": why,
            "dom_ready": round((perf.get("dom") or 0) / 1000, 1), "all_done": round((perf.get("all_done") or 0) / 1000, 1),
            "page_kb": perf.get("page_kb"), "options": perf.get("options"),
            "ttfb": round((perf.get("ttfb") or 0) / 1000, 2), "html_kb": perf.get("html_kb"), "files": perf.get("files"),
            "files_kb": perf.get("files_kb"), "xhr": perf.get("xhr") or [], "xhr_n": perf.get("xhr_n", 0), "rows": perf.get("rows", 0),
            "error": "صفحة خطأ" if perf.get("error") else ""}


def _pct(vals, q):
    vals = sorted(v for v in vals if v is not None)
    return vals[min(len(vals) - 1, int(len(vals) * q))] if vals else None


def _site_key():
    from config.settings import BASE_URL, ACTIVITY, BRANCH
    return hashlib.sha1(f"{BASE_URL}|{ACTIVITY}|{BRANCH}".encode()).hexdigest()[:10]


def _state_file():
    return STATE / f"health_{_site_key()}.json"


def load_state():
    f = _state_file()
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except Exception:
        return {}


def _save_state(d):
    STATE.mkdir(parents=True, exist_ok=True)
    _state_file().write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def is_report(path):
    return bool(re.search(r"/report|_report|reports?/", path, re.I))


# a link whose ACTION (2nd part of the path) does something instead of showing a screen: never opened (read-only check)
ACTION_RE = re.compile(r"^/[^/?]+/(delete|remove|reset|clear|restore|backup|import|sync|recalc|rebuild|migrate|execute|run|post|approve|"
                       r"reject|lock|unlock|generate|send|save|update|create|insert|close|cancel|logout|logoff|setbranch|change|toggle|mark)",
                       re.I)


def pick(links, cfg):
    skip = [s.lower() for s in (DEFAULT_SKIP + list(cfg.get("skip") or [])) if s]
    out = []
    for l in links:
        p = l["path"].lower()
        if any(s in p for s in skip) or ACTION_RE.match(l["path"]):
            continue
        if not cfg.get("reports", True) and is_report(l["path"]):
            continue
        out.append(l)
    return out[: int(cfg.get("limit") or 3000)]


def why_broken(r, slow_ms):
    s = r.get("s")
    if s == 0:
        return "مفتحتش خالص (انتهى الوقت / النت)" + (f": {r['err'][:120]}" if r.get("err") else "")
    if s and s >= 500:
        return f"خطأ سيرفر {s}" + (f" — {r['err'][:180]}" if r.get("err") else "")
    if s == 404:
        return "404 — الصفحة مش موجودة (اللينك في المنيو غلط أو الشاشة اتشالت)"
    if s in (401, 403):
        return f"{s} — ممنوع (صلاحيات)"
    if s and s >= 400:
        return f"خطأ {s}"
    if r.get("login"):
        return "رجّعتني لشاشة الدخول (الجلسة اتقفلت أو الشاشة بتعمل خروج)"
    if r.get("err"):
        return "صفحة خطأ من الـ ERP: " + r["err"][:200]
    if slow_ms and r.get("ms", 0) > slow_ms:
        return f"بطيئة جدًا: {r['ms'] / 1000:.1f} ث"
    return ""


def _alert(text):
    try:
        from web import notify
        cfg = notify.load_config()
        if cfg.get("telegram_on") and cfg.get("telegram_token"):
            notify.send_telegram(cfg, text)
        if cfg.get("whatsapp_on"):
            notify.send_whatsapp(cfg, text)
        if cfg.get("webhook_url"):
            notify._webhook(cfg["webhook_url"], text)
    except Exception as e:
        logger.debug(f"health alert: {e}")


def run_health(driver, credentials, cfg, result=None):
    from engine.screen_runner import login
    from config.settings import BASE_URL, ACTIVITY, BRANCH
    result = result if result is not None else {}
    login(driver, credentials)
    base = BASE_URL.rstrip("/")
    driver.get(base + (cfg.get("menu_page") or "/Home"))
    time.sleep(2)
    links = driver.execute_script(MENU_JS) or []
    for u in cfg.get("extra") or []:
        links.append({"path": u, "name": u, "module": "إضافي"})
    todo = pick(links, cfg)
    from engine import risk
    todo = risk.order(todo)                          # ⚖️ the most important screens first (Tosca-style risk-based order)
    logger.info(f"🩺 لقيت {len(links)} لينك في المنيو — هفتح {len(todo)} شاشة")
    if not todo:
        e = AssertionError("صحة النظام: مالقيتش ولا لينك في المنيو بعد الدخول (اتأكدي إن الدخول تم وإن المنيو بيظهر في الصفحة الرئيسية)")
        e.partial_result = result
        raise e
    driver.set_script_timeout(60 * 30)
    t0 = time.time()
    res = {}
    for i in range(0, len(todo), 200):                       # chunks: keeps the browser call short and shows progress
        part = [l["path"] for l in todo[i:i + 200]]
        # ONE page at a time: the ERP serves one request per login session at a time, so opening pages in parallel only
        # makes each one wait for the others (measured: 3-7x slower per page, the same total) -> fake «slow» numbers
        res.update(driver.execute_async_script(FETCH_JS, part, 1) or {})
        logger.info(f"   … {min(i + 200, len(todo))}/{len(todo)}")
    # ➕ صفحات الإضافة: every screen's «إضافة جديد» page is its own page (own link, own server code) — open it too
    # (open + read only, nothing is filled or saved)
    add_of = {}
    if cfg.get("adds", True):
        for l in list(todo):
            a = (res.get(l["path"]) or {}).get("add")
            if a and a not in res and a not in add_of.values():
                add_of[l["path"]] = a
        if add_of:
            logger.info(f"➕ بفتح صفحة الإضافة لـ {len(add_of)} شاشة (فتح بس — من غير ما أملى أو أحفظ حاجة)")
            names_ = {l["path"]: l for l in todo}
            add_paths = list(add_of.values())
            for i in range(0, len(add_paths), 200):
                res.update(driver.execute_async_script(FETCH_JS, add_paths[i:i + 200], 1) or {})
            for sp_, a in add_of.items():
                base_l = names_[sp_]
                todo.append({"path": a, "name": f"➕ إضافة — {base_l['name']}", "module": base_l.get("module", ""), "is_add": True})
    forms = {}
    if cfg.get("forms", True) and not int(cfg.get("deep_speed") or 0):   # the client speed check stays light and quick
        screens = [l["path"] for l in todo if not l.get("is_add") and not is_report(l["path"]) and l["path"] in res and res[l["path"]].get("s") == 200]
        logger.info(f"📋 بقرا فورم الإضافة في {len(screens)} شاشة (علشان المقارنة قبل / بعد التحديث)")
        for i in range(0, len(screens), 200):
            forms.update(driver.execute_async_script(FORMS_JS, screens[i:i + 200], int(cfg.get("workers") or 8)) or {})
    # 🔁 a slow answer is measured 2 more times: a one-off spike (seen on a real site: 21 s, then 1.2 s and 1.2 s) is not «slow»
    slow_p = [p_ for p_, r in res.items() if r.get("s") == 200 and (r.get("ms") or 0) >= 3000][:40]
    if slow_p:
        logger.info(f"🔁 بعيد قياس {len(slow_p)} صفحة بطيئة مرتين كمان علشان أتأكد إنه بطء ثابت مش لحظة")
        again = [driver.execute_async_script(FETCH_JS, slow_p, 1) or {}, driver.execute_async_script(FETCH_JS, slow_p, 1) or {}]
        for p_ in slow_p:
            tries = [res[p_].get("ms") or 0] + [(a.get(p_) or {}).get("ms") or 0 for a in again]
            med = sorted(tries)[1]
            res[p_]["tries"] = tries
            res[p_]["spike"] = med < 3000
            res[p_]["first_slow"] = med < 3000 and tries[0] >= 3000 and max(tries[1:]) < 3000
            res[p_]["ms"] = med
    secs = round(time.time() - t0, 1)

    # 🐢 السرعة الحقيقية: the slowest screens (by the server's answer) opened in the real browser, waiting for their data
    speed, deep_n = [], int(cfg.get("deep_speed") or 0)
    if deep_n:
        ok_links = sorted((l for l in todo if (res.get(l["path"]) or {}).get("s") == 200 and not l.get("is_add")),
                          key=lambda l: -(res[l["path"]].get("ms") or 0))
        ok_adds = sorted((l for l in todo if (res.get(l["path"]) or {}).get("s") == 200 and l.get("is_add")),
                         key=lambda l: -(res[l["path"]].get("ms") or 0))
        sample = ([{"path": "/Home", "name": "الصفحة الرئيسية", "module": ""}] + list(cfg.get("speed_paths_links") or [])
                  + ok_links[:deep_n] + ok_adds[:max(5, deep_n // 2)])
        seen_p = set()
        logger.info(f"🐢 بفتح أبطأ {deep_n} شاشة في المتصفح زي المستخدم بالظبط وبستنى بياناتها تحمل")
        for l in sample:
            if l["path"] in seen_p:
                continue
            seen_p.add(l["path"])
            m = measure_real(driver, base, {"path": l["path"], "name": l["name"], "module": l.get("module", ""), "is_add": bool(l.get("is_add"))})
            m["html"] = round(((res.get(l["path"]) or {}).get("ms") or 0) / 1000, 2) or None
            speed.append(m)
            slow_x = (m.get("xhr") or [{}])[0]
            logger.info(f"   {rate(m.get('load'))} {m.get('load')} ث — {l['name']}"
                        + (f" · أبطأ طلب بيانات {slow_x.get('ms', 0) / 1000:.1f} ث ({slow_x.get('url', '')[:60]})" if slow_x.get("url") else ""))
    html_secs = [round(((r.get("ms") or 0) / 1000), 2) for r in res.values() if r.get("s") == 200]
    add_set = set(add_of.values())
    okr = [r for p_, r in res.items() if p_ not in add_set and r.get("s") == 200 and not r.get("err") and not r.get("login")]
    data_stats = {"with_data": sum(1 for r in okr if (r.get("rows") or 0) > 0 and not r.get("report")),
                  "empty": sum(1 for r in okr if not r.get("report") and (r.get("rows") or 0) == 0),
                  "reports": sum(1 for r in okr if r.get("report")),
                  "adds_total": len(add_set),
                  "adds_ok": sum(1 for a in add_set if (res.get(a) or {}).get("s") == 200 and not (res.get(a) or {}).get("err")
                                 and not (res.get(a) or {}).get("login")),
                  "buckets": {"lt1": sum(1 for x in html_secs if x < 1), "1_3": sum(1 for x in html_secs if 1 <= x < 3),
                              "3_5": sum(1 for x in html_secs if 3 <= x < 5), "gt5": sum(1 for x in html_secs if x >= 5)}}
    speed_stats = {"html_median": _pct(html_secs, 0.5), "html_p90": _pct(html_secs, 0.9), "html_max": max(html_secs) if html_secs else None,
                   "html_over5": sum(1 for x in html_secs if x >= 5), "measured": len(speed),
                   "load_median": _pct([m.get("load") for m in speed], 0.5), "load_max": max([m.get("load") or 0 for m in speed], default=None),
                   "load_over5": sum(1 for m in speed if (m.get("load") or 0) >= 5), "ttfb_home": (speed[0].get("ttfb") if speed else None),
                   "seconds": secs}
    xhr_all = sorted(({**x, "screen": m["name"]} for m in speed for x in (m.get("xhr") or [])), key=lambda x: -x["ms"])[:15]
    speed_stats["slow_ajax"] = xhr_all
    speed_stats["data"] = data_stats
    speed_stats["spikes"] = [{"path": p_, "name": next((l["name"] for l in todo if l["path"] == p_), p_), "tries": r.get("tries"),
                              "first_slow": bool(r.get("first_slow"))}
                             for p_, r in res.items() if r.get("spike")][:20]
    times = {p: (r.get("ms") or 0) for p, r in res.items()}
    rows_of = {p: {"rows": r.get("rows") or 0, "report": bool(r.get("report"))} for p, r in res.items() if r.get("s") == 200}

    slow_ms = int(float(cfg.get("slow_seconds") or 0) * 1000)
    broken = {}
    for l in todo:
        r = res.get(l["path"]) or {"s": 0, "err": "مارجعش رد"}
        why = why_broken(r, slow_ms)
        if why:
            broken[l["path"]] = {"name": l["name"], "module": l["module"], "why": why, "s": r.get("s"), "ms": r.get("ms")}

    prev = load_state()
    before = prev.get("broken") or {}
    new = [p for p in broken if p not in before]
    still = [p for p in broken if p in before]
    fixed = [p for p in before if p not in broken]          # opens fine now, or the menu link was removed
    now = datetime.now().isoformat(timespec="seconds")
    hist = (prev.get("history") or [])[-89:] + [{"at": now, "total": len(todo), "broken": len(broken), "new": len(new), "fixed": len(fixed)}]
    since = prev.get("since") or {}
    for p in broken:
        since.setdefault(p, now)
    for p in fixed:
        since.pop(p, None)
    ref = prev.get("baseline") or ({"at": prev.get("at"), "forms": prev.get("forms") or {}, "paths": prev.get("paths") or []} if prev else None)
    changes = compare_forms(ref.get("forms") or {}, forms) if ref and forms else []
    paths_now = [l["path"] for l in todo]
    gone_links = [p for p in (ref or {}).get("paths", []) if p not in set(paths_now)] if ref else []
    new_links = [p for p in paths_now if p not in set((ref or {}).get("paths", []))] if ref and ref.get("paths") else []
    if ref and not any("/addedit" in x.lower() for x in ref.get("paths") or []):
        new_links = [p for p in new_links if "/addedit" not in p.lower()]      # the old snapshot never had add pages: not «new in the menu»
    state = {"at": now, "base_url": base, "activity": ACTIVITY, "branch": BRANCH, "total": len(todo),
             "broken": broken, "since": since, "history": hist, "forms": forms, "paths": paths_now,
             "names": {l["path"]: l["name"] for l in todo}, "modules": {l["path"]: l.get("module", "") for l in todo},
             "risk": {**{k: v for k, v in risk.coverage([(l["path"], l["name"], l.get("module", "")) for l in todo], set(broken)).items() if k != "lost"},
                      "lost": risk.coverage([(l["path"], l["name"], l.get("module", "")) for l in todo], set(broken))["lost"][:30]},
             "changes": [{"path": p, "what": w, "ok": ok} for p, w, ok in changes]
                        + [{"path": p, "what": "➖ اللينك اتشال من المنيو", "ok": None} for p in gone_links]
                        + [{"path": p, "what": "➕ شاشة جديدة في المنيو", "ok": None} for p in new_links],
             "compared_with": (ref or {}).get("at") if ref else None,
             "times": times, "rows_of": rows_of, "speed": sorted(speed, key=lambda m: -(m.get("load") or 0)), "speed_stats": speed_stats}
    if prev.get("baseline"):
        state["baseline"] = prev["baseline"]
    if speed:
        state["speed_at"] = now
    elif prev.get("speed"):                     # a quick check keeps the last real-speed measure (and says when it was)
        state["speed"], state["speed_at"] = prev["speed"], prev.get("speed_at") or prev.get("at")
        state["speed_stats"] = {**(prev.get("speed_stats") or {}), "data": speed_stats.get("data"),
                                "html_median": speed_stats.get("html_median"), "html_p90": speed_stats.get("html_p90"),
                                "html_max": speed_stats.get("html_max"), "html_over5": speed_stats.get("html_over5")}
    _save_state(state)

    rows = []
    for tag, lst, ok in (("🆕 باظت من آخر مرة", new, False), ("🔁 لسه بايظة", still, False), ("✅ اتصلحت", fixed, True)):
        for p in lst:
            b = broken.get(p) or before.get(p) or {}
            rows.append({"cells": [tag, b.get("module") or "—", b.get("name") or p, p,
                                   "اشتغلت تاني ✅" if ok else b.get("why", ""), (since.get(p) or "")[:16].replace("T", " ") if not ok else "—"],
                         "ok": ok})
    nm = {l["path"]: (l["name"], l["module"]) for l in todo}
    for c in state["changes"]:
        n_, m_ = nm.get(c["path"], ((prev.get("names") or {}).get(c["path"], c["path"]), ""))
        rows.append({"cells": ["🔀 اتغيرت", m_ or "—", n_, c["path"], c["what"], "—"], "ok": c["ok"]})
    for m in sorted(speed, key=lambda m: -(m.get("load") or 0)):
        if (m.get("load") or 0) >= 5 or m.get("timeout"):
            x = (m.get("xhr") or [{}])[0]
            rows.append({"cells": ["🐢 بطيئة", m.get("module") or "—", m["name"], m["path"],
                                   f"{rate(m.get('load'))}: {m.get('load')} ث لحد ما الشاشة اشتغلت (رد السيرفر {m.get('ttfb')} ث)"
                                   + (f" · أبطأ طلب بيانات {x['ms'] / 1000:.1f} ث: {x['url'][:70]}" if x.get("url") else "")
                                   + (" · ⏱️ مخلصتش في 60 ث" if m.get("timeout") else ""), "—"], "ok": False if (m.get("load") or 0) >= 10 else None})
    times = sorted(r.get("ms", 0) for r in res.values() if r.get("s") == 200)
    med = times[len(times) // 2] / 1000 if times else 0
    slowest = sorted(((r.get("ms", 0), p) for p, r in res.items() if r.get("s") == 200), reverse=True)[:5]
    names = {l["path"]: l["name"] for l in todo}
    note = (f"فتحت {len(todo)} شاشة في {secs:.0f} ث · سليمة {len(todo) - len(broken)} · بايظة {len(broken)}"
            f" (🆕 {len(new)} · ✅ اتصلحت {len(fixed)}) · متوسط الفتح {med:.1f} ث")
    if slowest:
        note += "\n🐢 أبطأ شاشات: " + "، ".join(f"{names.get(p, p)} ({ms / 1000:.1f} ث)" for ms, p in slowest)
    if speed:
        ss = speed_stats
        note += (f"\n🐢 السرعة الحقيقية (فتحت {len(speed)} شاشة في المتصفح وانتظرت بياناتها): المتوسط {ss['load_median']} ث · الأبطأ {ss['load_max']} ث"
                 f" · {ss['load_over5']} شاشة أبطأ من 5 ث · رد السيرفر على الرئيسية {ss['ttfb_home']} ث")
    if forms:
        note += f"\n📋 قريت فورم الإضافة في {sum(1 for x in forms.values() if x.get('f') is not None)} شاشة"
        if state["compared_with"]:
            note += f" · 🔀 {len(state['changes'])} تغيير عن {'اللقطة قبل التحديث' if prev.get('baseline') else 'آخر فحص'} ({state['compared_with'][:16].replace('T', ' ')})"
    if ACTIVITY or BRANCH:
        note += f"\n🏢 {ACTIVITY or 'أول نشاط'} · 📍 {BRANCH or 'أول فرع'}"
    result["detail"] = {"title": "🩺 صحة النظام — كل الشاشات", "columns": ["الحالة", "الموديول", "الشاشة", "الرابط", "السبب / التغيير", "بايظة من"],
                        "rows": rows, "note": note}
    result["health"] = {"total": len(todo), "broken": len(broken), "new": new, "fixed": fixed, "changes": len(state["changes"])}
    logger.info(note)

    if (new or fixed or any("بقى إجباري" in c["what"] or "مش بيفتح" in c["what"] for c in state["changes"])) and prev:                               # first run = the starting point, no alert
        lines = [f"🩺 صحة النظام — {base}" + (f" ({ACTIVITY} / {BRANCH})" if ACTIVITY or BRANCH else "")]
        if new:
            lines.append(f"🆕 {len(new)} شاشة باظت:")
            lines += [f"• {broken[p]['name']} ({p}) — {broken[p]['why'][:90]}" for p in new[:15]]
        if fixed:
            lines.append(f"✅ {len(fixed)} شاشة اتصلحت:")
            lines += [f"• {(before.get(p) or {}).get('name', p)} ({p})" for p in fixed[:15]]
        req = [c for c in state["changes"] if "بقى إجباري" in c["what"] or "مش بيفتح" in c["what"]]
        if req:
            lines.append(f"🔀 {len(req)} فورم اتغير (حقول بقت إجبارية / مابقاش بيفتح)")
        lines.append(f"الإجمالي: {len(broken)} بايظة من {len(todo)}")
        _alert("\n".join(lines))

    fail_on = cfg.get("fail_on", "any")
    if broken and (fail_on == "any" or (fail_on == "new" and new)):
        lst = new if fail_on == "new" else list(broken)
        e = AssertionError(f"صحة النظام: {len(broken)} شاشة بايظة من {len(todo)} (منهم {len(new)} جديدة)\n   "
                           + "\n   ".join(f"{broken[p]['name']} ({p}): {broken[p]['why'][:120]}" for p in lst[:30]))
        e.partial_result = result
        raise e
    logger.success(f"✅ {note.splitlines()[0]}")
    return result
