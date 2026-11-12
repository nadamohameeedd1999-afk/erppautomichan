"""
🔬 أشعة النظام — a read-only X-ray of one ERP site, from the outside, safe on a client's live system (GET only, nothing is
filled or saved):

  الروابط       every link of the menu: pointing to localhost / another domain / plain http / empty name / the same page
                under two names / two pages under one name
  المكتبات      the JavaScript libraries the system really loads (read live: jQuery, jQuery UI, Bootstrap, moment,
                Knockout, DevExpress …) and the ones with well-known security problems
  الأمان        passive checks only: security headers (clickjacking, MIME sniffing, HSTS), the server telling its
                version, the login cookie readable from JavaScript
  اللغة         English words / undefined / null / resource keys showing in the Arabic screens
  الصور         a screenshot of the main screens compared with the last run (what changed on screen) + horizontal scroll
  الشبكة الضعيفة  the home page and a few screens opened on a slow (3G-like) connection

Each site keeps its latest X-ray and the one before, so a run says what is new since last time; two sites can be compared
(menu, libraries, security) on the X-ray page.
"""
import base64
import io
import json
import re
import time
from datetime import datetime

from utils.logger import logger

SEV = {"عالية": 0, "متوسطة": 1, "منخفضة": 2, "للعلم": 3}

MENU_JS = r"""
const out = [];
const txt = e => (e && (e.innerText || e.textContent) || '').replace(/\s+/g, ' ').trim();
document.querySelectorAll('a[href]').forEach(a => {
  const h = (a.getAttribute('href') || '').trim();
  if (!h || h[0] === '#' || /^(mailto|tel):/i.test(h)) return;
  if (/\/(tickets|LocalNews|Mail|TodoTask|PresenceStatus)(\/|$)/i.test(h)) return;
  const inMenu = !!a.closest('nav, .navbar, .menu, .sidebar, .side-nav, #sidebar-menu, .metismenu, .topnav, .navbar-custom, .mega-menu, header, li');
  if (!inMenu) return;
  const card = a.closest('.card-body'); let group = ((card && card.querySelector('.h3, .control-label')) || {}).textContent || '';
  if (!group) { let li = a.closest('li'), top = li; while (li) { top = li; li = li.parentElement && li.parentElement.closest('li'); } if (top && top !== a.closest('li')) group = txt(top.querySelector(':scope > a, :scope > span, :scope > div')).slice(0, 60); }
  out.push({href: h, name: txt(a).slice(0, 90), group: group.replace(/\s+/g, ' ').trim().slice(0, 60)});
});
return out;
"""

LIBS_JS = r"""
const v = {}; const t = (k, f) => { try { const x = f(); if (x) v[k] = String(x); } catch (e) {} };
t('jQuery', () => window.jQuery && jQuery.fn && jQuery.fn.jquery);
t('jQuery UI', () => window.jQuery && jQuery.ui && jQuery.ui.version);
t('Bootstrap', () => (window.bootstrap && bootstrap.Tooltip && bootstrap.Tooltip.VERSION) || (window.jQuery && jQuery.fn.tooltip && jQuery.fn.tooltip.Constructor && jQuery.fn.tooltip.Constructor.VERSION));
t('moment', () => window.moment && moment.version);
t('Knockout', () => window.ko && ko.version);
t('SweetAlert2', () => window.Swal && Swal.version);
t('Select2', () => window.jQuery && jQuery.fn.select2 && (jQuery.fn.select2.amd ? '4.x' : '3.x'));
t('DevExtreme', () => window.DevExpress && DevExpress.VERSION);
t('DevExpress Reporting', () => window.DevExpress && DevExpress.Analytics && DevExpress.Analytics.VERSION);
t('Chart.js', () => window.Chart && Chart.version);
t('Lodash', () => window._ && _.VERSION);
t('Vue', () => window.Vue && Vue.version);
t('Angular', () => window.angular && angular.version && angular.version.full);
const cookies = document.cookie.split(';').map(c => c.split('=')[0].trim()).filter(Boolean);
const scripts = Array.from(document.scripts).map(s => s.getAttribute('src') || '').filter(Boolean);
const sri = Array.from(document.scripts).filter(s => /^(https?:)?\/\//.test(s.getAttribute('src') || '') && !(s.getAttribute('src') || '').includes(location.host)).map(s => ({src: s.getAttribute('src'), sri: !!s.integrity}));
return {libs: v, cookies, scripts, cdn: sri, lang: document.documentElement.lang || '', dir: document.documentElement.dir || getComputedStyle(document.body).direction};
"""

PAGES_JS = r"""
const [paths, done] = [arguments[0], arguments[arguments.length - 1]];
const P = new DOMParser(); const out = {};
const H = ['x-powered-by', 'x-aspnet-version', 'x-aspnetmvc-version', 'server', 'x-frame-options', 'content-security-policy', 'strict-transport-security', 'x-content-type-options', 'referrer-policy'];
const ALLOW = /^(ERP|NQ|PDF|Excel|Word|VAT|QR|ID|SMS|API|ZATCA|Email|E-mail|URL|IBAN|CR|POS|SKU|KPI|HR|GOSI|Mudad|Muqeem|WhatsApp|Google|Microsoft|Windows|Android|iOS|OK|No|Yes|AM|PM|CSV|XML|JSON|HTML|USB|GPS|IT|CEO|CFO|Online|Offline|DevExpress|Copyright|Powered|by|SAR|USD|EGP|EUR|Hijri|NQS|AI|Claude|Telegram|Zoom|Teams|Dashboard)$/i;
async function one(p) {
  const t0 = performance.now();
  try {
    const ctl = new AbortController(); const timer = setTimeout(() => ctl.abort(), 30000);
    const r = await fetch(p, {credentials: 'include', signal: ctl.signal}); const html = await r.text(); clearTimeout(timer);
    const h = {}; H.forEach(k => { const x = r.headers.get(k); if (x !== null) h[k] = x.slice(0, 200); });
    const doc = P.parseFromString(html, 'text/html');
    doc.querySelectorAll('script, style, noscript, template, select option').forEach(e => e.remove());
    const main = doc.querySelector('.content-page, .page-content, main, #wrapper .content, .container-fluid') || doc.body;
    const text = main ? main.textContent.replace(/\s+/g, ' ') : '';
    const ar = (text.match(/[؀-ۿ]/g) || []).length;
    const words = (text.match(/\b[A-Za-z][A-Za-z_]{2,}\b/g) || []).filter(w => !ALLOW.test(w));
    const odd = (text.match(/\b(undefined|NaN|null|\[object Object\]|lbl_\w+|Resources?\.\w+|@\w+\.\w+)\b|\{\{[^}]*\}\}/g) || []);
    const hscroll = 0;
    out[p] = {s: r.status, ms: Math.round(performance.now() - t0), h, ar, en: words.length, words: [...new Set(words)].slice(0, 25), odd: [...new Set(odd)].slice(0, 10),
              title: ((html.match(/<title[^>]*>([\s\S]*?)<\/title>/i) || [])[1] || '').trim().slice(0, 100), url: r.url.replace(location.origin, '')};
  } catch (e) { out[p] = {s: 0, err: String(e).slice(0, 120)}; }
}
(async () => { for (const p of paths) await one(p); done(out); })();
"""

# well-known problems only (CVE numbers that are public and stable); anything else is shown as a version, not judged
VULNS = [
    ("jQuery", "3.5.0", "عالية", "ثغرة XSS في jQuery أقدم من 3.5.0 (CVE-2020-11022 / CVE-2020-11023)"),
    ("jQuery UI", "1.13.0", "متوسطة", "ثغرات XSS في jQuery UI أقدم من 1.13.0 (CVE-2021-41182/41183/41184)"),
    ("Bootstrap", "3.4.1", "متوسطة", "ثغرة XSS في Bootstrap 3 أقدم من 3.4.1 (CVE-2019-8331)", "3."),
    ("Bootstrap", "4.3.1", "متوسطة", "ثغرة XSS في Bootstrap 4 أقدم من 4.3.1 (CVE-2019-8331)", "4."),
    ("moment", "2.29.4", "متوسطة", "ثغرة ReDoS في moment أقدم من 2.29.4 (CVE-2022-31129)"),
    ("Knockout", "3.5.0", "متوسطة", "ثغرة XSS في Knockout أقدم من 3.5.0 (CVE-2019-14862)"),
    ("Lodash", "4.17.21", "متوسطة", "ثغرات Prototype pollution / command injection في Lodash أقدم من 4.17.21 (CVE-2020-8203 / CVE-2021-23337)"),
    ("Angular", "1.8.0", "متوسطة", "AngularJS 1.x انتهى دعمها وفيها ثغرات XSS معروفة", "1."),
]


def _ver(s):
    return tuple(int(x) for x in re.findall(r"\d+", str(s))[:3]) or (0,)


def lib_findings(libs):
    out = []
    for row in VULNS:
        name, fixed, sev, msg = row[:4]
        pref = row[4] if len(row) > 4 else ""
        v = libs.get(name)
        if not v or (pref and not str(v).startswith(pref)):
            continue
        if _ver(v) < _ver(fixed):
            out.append({"area": "المكتبات", "sev": sev, "title": f"{name} {v} — {msg}", "fix": f"حدّث {name} لـ {fixed} أو أحدث", "where": "كل الصفحات"})
    return out


# ------------------------------------------------------------------ analysis (pure, unit-tested)
def menu_findings(links, origin):
    host = re.sub(r"^https?://", "", origin).split("/")[0].lower()
    out, by_path, by_name = [], {}, {}
    for l in links:
        h = l["href"]
        name = l.get("name") or ""
        if re.match(r"^javascript:", h, re.I):
            continue
        m = re.match(r"^(https?:)?//([^/]+)", h, re.I)
        if m:
            dom = m.group(2).lower()
            if re.match(r"^(localhost|127\.|10\.|192\.168\.)", dom):
                out.append({"area": "الروابط", "sev": "عالية", "title": f"«{name}» رايح على جهاز المطور ({dom})", "where": h, "group": l.get("group", ""),
                            "fix": "غيّر اللينك لمسار نسبي زي /Report/..."})
                continue
            if dom != host:
                out.append({"area": "الروابط", "sev": "عالية", "title": f"«{name}» رايح على موقع تاني ({dom})", "where": h, "group": l.get("group", ""),
                            "fix": "اللينك لازم يفضل جوه نظام العميل نفسه"})
                continue
            if h.lower().startswith("http://"):
                out.append({"area": "الروابط", "sev": "متوسطة", "title": f"«{name}» بـ http مش https", "where": h, "group": l.get("group", ""), "fix": "استخدم مسار نسبي"})
        path = re.sub(r"^(https?:)?//[^/]+", "", h).split("#")[0] or "/"
        if not name.strip():
            out.append({"area": "الروابط", "sev": "منخفضة", "title": "لينك في المنيو من غير اسم", "where": path, "group": l.get("group", ""), "fix": "ضيف اسم للعنصر"})
            continue
        by_path.setdefault(path.lower().rstrip("/"), set()).add(name)
        by_name.setdefault((l.get("group", ""), name), set()).add(path.lower().rstrip("/"))
    for p, names in by_path.items():
        if len(names) > 1:
            out.append({"area": "الروابط", "sev": "للعلم", "title": f"نفس الصفحة بـ {len(names)} أسماء: " + " / ".join(sorted(names)[:4]), "where": p, "fix": "اتأكد إن ده مقصود"})
    for (g, n), ps in by_name.items():
        if len(ps) > 1:
            out.append({"area": "الروابط", "sev": "منخفضة", "title": f"«{n}» في نفس المجموعة رايح على {len(ps)} صفحات مختلفة", "where": " · ".join(sorted(ps)[:4]),
                        "group": g, "fix": "اسم واحد لصفحة واحدة علشان المستخدم ميتلخبطش"})
    return out


def security_findings(pages, cookies, cdn, https):
    out = []
    homes = [r for r in pages.values() if r.get("s") == 200]
    if not homes:
        return out
    h = {}
    for r in homes:
        for k, v in (r.get("h") or {}).items():
            h.setdefault(k, v)
    miss = lambda k: all(k not in (r.get("h") or {}) for r in homes)
    if miss("x-frame-options") and not any("frame-ancestors" in (r.get("h") or {}).get("content-security-policy", "") for r in homes):
        out.append({"area": "الأمان", "sev": "متوسطة", "title": "الصفحات ممكن تتحط جوه iframe في موقع تاني (Clickjacking) — مفيش X-Frame-Options ولا frame-ancestors",
                    "fix": "ضيف X-Frame-Options: SAMEORIGIN في web.config", "where": "كل الصفحات"})
    if miss("x-content-type-options"):
        out.append({"area": "الأمان", "sev": "منخفضة", "title": "مفيش X-Content-Type-Options: nosniff", "fix": "ضيفه في web.config", "where": "كل الصفحات"})
    if https and miss("strict-transport-security"):
        out.append({"area": "الأمان", "sev": "منخفضة", "title": "مفيش HSTS (Strict-Transport-Security)", "fix": "ضيف Strict-Transport-Security", "where": "كل الصفحات"})
    if miss("content-security-policy"):
        out.append({"area": "الأمان", "sev": "للعلم", "title": "مفيش Content-Security-Policy", "fix": "سياسة CSP بتقلل أثر أي ثغرة XSS", "where": "كل الصفحات"})
    for k, nm in (("x-powered-by", "X-Powered-By"), ("x-aspnet-version", "X-AspNet-Version"), ("x-aspnetmvc-version", "X-AspNetMvc-Version")):
        if k in h:
            out.append({"area": "الأمان", "sev": "منخفضة", "title": f"السيرفر بيقول نسخته: {nm}: {h[k]}", "fix": f"شيل {nm} من الردود (web.config / Global.asax)", "where": "كل الصفحات"})
    if re.search(r"\d", h.get("server", "")):
        out.append({"area": "الأمان", "sev": "منخفضة", "title": f"السيرفر بيقول نسخته: Server: {h['server']}", "fix": "خبّي نسخة السيرفر", "where": "كل الصفحات"})
    auth = [c for c in cookies if re.match(r"^(\.ASPXAUTH|ASP\.NET_SessionId|\.AspNet\.\w+|__RequestVerificationToken_\w*Auth|auth|token|jwt)", c, re.I)]
    if auth:
        out.append({"area": "الأمان", "sev": "عالية", "title": "كوكي الدخول بتتقري من الجافاسكربت (مش HttpOnly): " + "، ".join(auth[:4]),
                    "fix": "خلي الكوكي HttpOnly و Secure (httpCookies في web.config)", "where": "الجلسة"})
    nosri = [c["src"] for c in cdn or [] if not c.get("sri")]
    if nosri:
        out.append({"area": "الأمان", "sev": "للعلم", "title": f"{len(nosri)} سكريبت من CDN خارجي من غير integrity (SRI)", "fix": "ضيف integrity + crossorigin للسكريبتات الخارجية",
                    "where": " · ".join(nosri[:4])})
    return out


def language_findings(pages, names):
    out = []
    for p, r in pages.items():
        if r.get("s") != 200:
            continue
        nm = names.get(p) or r.get("title") or p
        if r.get("odd"):
            out.append({"area": "اللغة", "sev": "متوسطة", "title": f"«{nm}»: قيم برمجية ظاهرة للمستخدم: " + "، ".join(r["odd"][:6]), "where": p, "fix": "اعرض نص مفهوم بدل القيمة الفاضية"})
        if r.get("ar", 0) > 200 and r.get("en", 0) >= 6:
            out.append({"area": "اللغة", "sev": "منخفضة", "title": f"«{nm}»: {r['en']} كلمة إنجليزي في شاشة عربي: " + "، ".join(r["words"][:10]), "where": p, "fix": "ترجم النصوص"})
    return out


def img_diff(a_png, b_png):
    """% of the picture that changed (0–100) between two screenshots, on small grey thumbnails"""
    from PIL import Image, ImageChops
    A = Image.open(io.BytesIO(a_png)).convert("L").resize((320, 200))
    B = Image.open(io.BytesIO(b_png)).convert("L").resize((320, 200))
    d = ImageChops.difference(A, B).point(lambda x: 255 if x > 40 else 0)
    hist = d.histogram()
    return round(100.0 * hist[255] / (320 * 200), 1)


def compare_sites(a, b):
    """two X-rays side by side: menu, libraries, security headers"""
    rows = []
    pa = {l["path"].lower(): l for l in a.get("menu") or []}
    pb = {l["path"].lower(): l for l in b.get("menu") or []}
    only_a = [pa[k] for k in pa if k not in pb]
    only_b = [pb[k] for k in pb if k not in pa]
    renamed = [(pa[k], pb[k]) for k in pa if k in pb and pa[k]["name"] != pb[k]["name"]]
    rows.append({"item": "شاشات المنيو", "a": len(pa), "b": len(pb), "status": "same" if not only_a and not only_b else "diff",
                 "detail": " · ".join(x for x in [only_a and f"في الأول بس ({len(only_a)}): " + "، ".join(l["name"] for l in only_a[:12]),
                                                  only_b and f"في التاني بس ({len(only_b)}): " + "، ".join(l["name"] for l in only_b[:12])] if x) or "نفس الشاشات"})
    rows.append({"item": "أسماء مختلفة لنفس الصفحة", "a": "", "b": "", "status": "same" if not renamed else "warn",
                 "detail": " · ".join(f"«{x['name']}» ↔ «{y['name']}»" for x, y in renamed[:10]) or "متطابق"})
    la, lb = a.get("libs") or {}, b.get("libs") or {}
    for k in sorted(set(la) | set(lb)):
        rows.append({"item": f"مكتبة {k}", "a": la.get(k, "—"), "b": lb.get(k, "—"), "status": "same" if la.get(k) == lb.get(k) else "diff",
                     "detail": "نفس النسخة" if la.get(k) == lb.get(k) else "النسخة مختلفة — غالبًا النشر مختلف"})
    ta = {f["title"].split(" —")[0][:70] for f in a.get("findings") or [] if f["area"] == "الأمان"}
    tb = {f["title"].split(" —")[0][:70] for f in b.get("findings") or [] if f["area"] == "الأمان"}
    rows.append({"item": "ملاحظات الأمان", "a": len(ta), "b": len(tb), "status": "same" if ta == tb else "diff",
                 "detail": " · ".join(x for x in [ta - tb and "في الأول بس: " + "، ".join(sorted(ta - tb)[:4]), tb - ta and "في التاني بس: " + "، ".join(sorted(tb - ta)[:4])] if x) or "نفس الملاحظات"})
    return rows


# ------------------------------------------------------------------ state
def site_key(url):
    return re.sub(r"^https?://", "", str(url or "")).strip("/").lower()


def _file(url, prev=False):
    from config import paths
    return paths.STATE_DIR / f"xray_{re.sub(r'[^a-z0-9]', '_', site_key(url))}{'_prev' if prev else ''}.json"


def shots_dir(url):
    from config import paths
    d = paths.STATE_DIR / "xray_shots" / re.sub(r"[^a-z0-9]", "_", site_key(url))
    d.mkdir(parents=True, exist_ok=True)
    return d


def load(url, prev=False):
    try:
        return json.loads(_file(url, prev).read_text(encoding="utf-8"))
    except Exception:
        return None


def _save(url, data):
    f = _file(url)
    f.parent.mkdir(parents=True, exist_ok=True)
    if f.exists():
        _file(url, True).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def fid(f):
    return re.sub(r"\W+", "_", f"{f['area']}_{f['title'][:60]}_{f.get('where', '')[:60]}")[:150]


# ------------------------------------------------------------------ the run
def run_xray(driver, credentials, cfg, result=None):
    from engine.screen_runner import login
    from config.settings import BASE_URL
    result = result if result is not None else {}
    base = BASE_URL.rstrip("/")
    login(driver, credentials)
    driver.set_script_timeout(60 * 20)
    t0 = time.time()
    driver.get(base + "/")
    time.sleep(3)
    raw = driver.execute_script(MENU_JS) or []
    menu, seen = [], set()
    for l in raw:
        p = re.sub(r"^(https?:)?//[^/]+", "", l["href"]) if l["href"].lower().startswith(base.lower()) or l["href"].startswith("/") else l["href"]
        if p.startswith("/") and p.lower() not in seen and not re.match(r"^/(login|logout|account/log)", p, re.I):
            seen.add(p.lower())
            menu.append({"path": p.split("#")[0], "name": l["name"], "group": l["group"]})
    logger.info(f"🔬 المنيو: {len(raw)} لينك ({len(menu)} صفحة جوه النظام)")
    findings = menu_findings(raw, base)
    live = driver.execute_script(LIBS_JS) or {}
    libs = live.get("libs") or {}
    findings += lib_findings(libs)
    logger.info("🔬 المكتبات: " + " · ".join(f"{k} {v}" for k, v in libs.items()))
    # pages: home + a spread of the menu (first of each group, then the rest) — fetched one at a time, read only
    n = max(10, min(400, int(cfg.get("pages") or 80)))
    groups, sample = {}, ["/"]
    for l in menu:
        groups.setdefault(l["group"], []).append(l["path"])
    while len(sample) < n and any(groups.values()):
        for g in list(groups):
            if groups[g]:
                p = groups[g].pop(0)
                if p not in sample:
                    sample.append(p)
            if len(sample) >= n:
                break
    pages = {}
    for i in range(0, len(sample), 40):
        pages.update(driver.execute_async_script(PAGES_JS, sample[i:i + 40]) or {})
        logger.info(f"   … {min(i + 40, len(sample))}/{len(sample)} صفحة")
    names = {l["path"]: l["name"] for l in menu}
    findings += security_findings(pages, live.get("cookies") or [], live.get("cdn") or [], base.startswith("https"))
    findings += language_findings(pages, names)
    # 📸 screenshots of the main screens vs last time
    shots = []
    if cfg.get("shots", True):
        k = max(0, min(40, int(cfg.get("shots_n") or 12)))
        targets = ["/"] + [p for p in sample[1:] if (pages.get(p) or {}).get("s") == 200 and not re.search(r"/Report/", p, re.I)][:k - 1]
        d = shots_dir(base)
        driver.set_window_size(1440, 900)
        for p in targets:
            try:
                driver.get(base + p)
                time.sleep(2.5)
                png = driver.get_screenshot_as_png()
                hs = driver.execute_script("return document.documentElement.scrollWidth - document.documentElement.clientWidth") or 0
                fn = re.sub(r"[^a-z0-9]+", "_", p.lower()).strip("_") or "home"
                old = d / f"{fn}.png"
                diff = None
                if old.exists():
                    try:
                        diff = img_diff(old.read_bytes(), png)
                        (d / f"{fn}_prev.png").write_bytes(old.read_bytes())
                    except Exception:
                        diff = None
                old.write_bytes(png)
                shots.append({"path": p, "name": names.get(p) or "الصفحة الرئيسية", "file": fn, "diff": diff, "hscroll": int(hs)})
                if hs > 20:
                    findings.append({"area": "الشاشات", "sev": "منخفضة", "title": f"«{names.get(p) or p}»: الشاشة أعرض من المتصفح بـ {hs}px (اسكرول أفقي على شاشة 1440)",
                                     "where": p, "fix": "راجع عرض الجداول / العناصر في RTL"})
            except Exception as e:
                logger.warning(f"📸 {p}: {e}")
        logger.info(f"📸 {len(shots)} صورة — اتغير منهم {sum(1 for s in shots if (s['diff'] or 0) >= 8)}")
    # 🐢 slow network (CDP), then back to normal
    slow = []
    if cfg.get("slow", True):
        try:
            driver.execute_cdp_cmd("Network.enable", {})
            driver.execute_cdp_cmd("Network.emulateNetworkConditions", {"offline": False, "latency": 300, "downloadThroughput": 750 * 1024 / 8, "uploadThroughput": 250 * 1024 / 8})
            for p in (["/"] + [s["path"] for s in shots[1:4]])[:4]:
                t1 = time.time()
                driver.get(base + p)
                for _ in range(120):
                    if driver.execute_script("return document.readyState === 'complete' && (!window.jQuery || jQuery.active === 0)"):
                        break
                    time.sleep(0.5)
                sec = round(time.time() - t1, 1)
                slow.append({"path": p, "name": names.get(p) or "الصفحة الرئيسية", "sec": sec})
                if sec > 20:
                    findings.append({"area": "الشبكة الضعيفة", "sev": "متوسطة", "title": f"«{names.get(p) or 'الصفحة الرئيسية'}» بتاخد {sec} ث على نت ضعيف (3G)",
                                     "where": p, "fix": "قلل حجم السكريبتات / حمّل الحاجات المتأخرة بعد الفتح"})
        except Exception as e:
            logger.warning(f"🐢 محاكاة النت الضعيف: {e}")
        finally:
            try:
                driver.execute_cdp_cmd("Network.emulateNetworkConditions", {"offline": False, "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1})
            except Exception:
                pass
    prev = load(base) or {}
    old_ids = {fid(f) for f in prev.get("findings") or []}
    for f in findings:
        f["id"] = fid(f)
        f["new"] = bool(prev) and f["id"] not in old_ids
    findings.sort(key=lambda f: (SEV.get(f["sev"], 9), f["area"]))
    fixed = [f for f in prev.get("findings") or [] if f["id"] not in {x["id"] for x in findings}]
    data = {"site": site_key(base), "url": base, "at": datetime.now().strftime("%Y-%m-%d %H:%M"), "secs": round(time.time() - t0),
            "menu": menu, "links_n": len(raw), "libs": libs, "lang": live.get("lang"), "dir": live.get("dir"),
            "pages": {p: {k: r.get(k) for k in ("s", "ms", "title", "en", "ar")} for p, r in pages.items()}, "headers": next((r.get("h") for r in pages.values() if r.get("s") == 200), {}),
            "shots": shots, "slow": slow, "findings": findings, "fixed": [{"title": f["title"], "area": f["area"]} for f in fixed]}
    _save(base, data)
    cnt = {s: sum(1 for f in findings if f["sev"] == s) for s in SEV}
    result["detail"] = {"title": f"🔬 أشعة النظام — {site_key(base)}", "columns": ["النوع", "الخطورة", "الملاحظة", "فين", "التصليح"],
                        "rows": [{"cells": [f["area"], f["sev"] + (" 🆕" if f.get("new") else ""), f["title"], f.get("where", ""), f.get("fix", "")],
                                  "ok": False if f["sev"] in ("عالية", "متوسطة") else None} for f in findings],
                        "note": f"{len(menu)} شاشة في المنيو · {len(pages)} صفحة اتقرت · {len(shots)} صورة · " + " · ".join(f"{k}: {v}" for k, v in cnt.items() if v)
                                + (f" · اتصلح من آخر مرة: {len(fixed)}" if fixed else "")}
    logger.info(f"🔬 خلص في {data['secs']} ث — " + " · ".join(f"{k} {v}" for k, v in cnt.items()))
    return result


def support_issues():
    """X-ray findings (high / medium) of every site, for the developer-support screen"""
    from config import paths
    out = []
    for f in sorted(paths.STATE_DIR.glob("xray_*.json")):
        if f.name.endswith("_prev.json"):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for x in d.get("findings") or []:
            if x["sev"] not in ("عالية", "متوسطة"):
                continue
            where = x.get("where", "")
            url = (d["url"] + where) if where.startswith("/") else (where if where.startswith("http") else d["url"])
            out.append({"id": "xray-" + d["site"].replace(".", "_") + "-" + x["id"][:80], "site": d["site"], "url": url, "source": "أشعة النظام",
                        "screen": x["area"], "severity": x["sev"], "title": x["title"][:200], "details": x["title"] + ("\nالتصليح: " + x["fix"] if x.get("fix") else ""),
                        "evidence": f"فحص {d['at']}", "doc": "", "steps": f"افتح {url}" if url else "أشعة النظام", "found": d["at"][:10]})
    return out
