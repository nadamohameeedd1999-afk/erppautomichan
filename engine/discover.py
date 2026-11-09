"""
Discover the ERP's screens (اكتشاف شاشات النظام): read every link of the side menu after login,
open each one and say what it is: a list screen (has a table), another page (report / dashboard), or an error.
Never clicks add / save / delete.

Progress is written to a JSON file after every step (the dashboard shows it live), and a report of the
whole run is kept in data/runs/discovery/ (Reports page).

Skip filter (فلتر التخطي): any link whose address (or name) contains one of the words is not opened
(e.g. login, logout, tickets). deep=True also collects the links found inside each opened page.
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path

from config import paths
from config.settings import BASE_URL
from utils.logger import logger

MENU_JS = r"""
function txt(e){ return (e && (e.innerText || e.textContent) || '').replace(/\s+/g,' ').trim(); }
var out = [], seen = {};
document.querySelectorAll('a[href]').forEach(function(a){
  var h = a.getAttribute('href') || '';
  if (!h || h[0] === '#' || /^(javascript|mailto|tel):/i.test(h)) return;
  var u; try { u = new URL(h, location.href); } catch(e) { return; }
  if (u.origin !== location.origin) return;
  var path = u.pathname + (u.search || '');
  // never: sign-out (it would end the session) and pages that change / download data
  if (/logout|logoff|signout|\/(addedit|edit|delete|remove|print|details|download|export)\b|\.(pdf|xlsx?|zip|png|jpe?g)$/i.test(path)) return;
  if (path === '/' || seen[path.toLowerCase()]) return;
  var name = txt(a) || a.getAttribute('title') || a.getAttribute('aria-label') || '';
  if (!name || name.length > 60) return;
  var group = '', li = a.closest('li'), up = li && li.parentElement && li.parentElement.closest('li');
  if (up) { var h2 = up.querySelector(':scope > a, :scope > span, :scope > div'); group = txt(h2).slice(0, 40); }
  seen[path.toLowerCase()] = 1;
  out.push({path: path, name: name, group: group, in_menu: !!a.closest('nav, aside, .sidebar, .menu, [class*=menu], [class*=sidebar]')});
});
return out;
"""

CHECK_JS = r"""
var t = (document.body && document.body.innerText) || '';
var tables = Array.prototype.filter.call(document.querySelectorAll('table'), function(x){ var r = x.getBoundingClientRect(); return r.width > 0; });
var rows = 0; tables.forEach(function(tb){ rows = Math.max(rows, tb.querySelectorAll('tbody tr').length); });
var h = document.querySelector('h1, h2, h3, .page-title, .breadcrumb .active, .content-header');
return {title: document.title, heading: h ? (h.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 80) : '',
        tables: tables.length, rows: rows,
        add: !!document.querySelector("a[href*='AddEdit'], a[href*='Create'], a[href*='/Add']"),
        error: /server error|runtime error|404 - |خطأ في الخادم|the resource cannot be found/i.test(t.slice(0, 4000)), url: location.pathname};
"""


# open many pages from inside the logged-in page (fetch + DOMParser): no page loads in the tab -> no «tab crashed»,
# far less memory on the server and ~10x faster than opening every page in Chrome
FETCH_CHECK_JS = r"""
const [paths, workers, deep, done] = [arguments[0], arguments[1], arguments[2], arguments[arguments.length - 1]];
const P = new DOMParser(), out = {}; let i = 0;
const txt = e => (e && (e.innerText || e.textContent) || '').replace(/\s+/g, ' ').trim();
const BAD = /logout|logoff|signout|\/(addedit|edit|delete|remove|print|details|download|export)\b|\.(pdf|xlsx?|zip|png|jpe?g)$/i;
async function one(p) {
  const t0 = performance.now();
  try {
    const ctl = new AbortController(), tm = setTimeout(() => ctl.abort(), 40000);
    const r = await fetch(p, {credentials: 'include', signal: ctl.signal}); const html = await r.text(); clearTimeout(tm);
    const d = P.parseFromString(html, 'text/html');
    const body = (d.body && d.body.textContent || '').slice(0, 6000);
    const tables = Array.from(d.querySelectorAll('table')).filter(t => !t.closest('.modal, nav, header, aside, .sidebar'));
    let rows = 0; tables.forEach(t => { rows = Math.max(rows, t.querySelectorAll('tbody tr').length); });
    const h = d.querySelector('.content-wrapper h1, .content-wrapper h2, .content-wrapper h3, .page-title, .breadcrumb .active, .content-header, h1, h2');
    const res = {s: r.status, ms: Math.round(performance.now() - t0), login: /\/login/i.test(new URL(r.url).pathname) && !/\/login/i.test(p),
      title: txt(d.querySelector('title')).slice(0, 80), heading: h ? txt(h).slice(0, 80) : '', tables: tables.length, rows: rows,
      add: !!d.querySelector("a[href*='AddEdit'], a[href*='Create'], a[href*='/Add']"),
      error: r.status >= 400 || /server error|runtime error|404 - |خطأ في الخادم|the resource cannot be found|compilation error/i.test(body)};
    if (deep && !res.error) {
      const seen = {}; res.links = [];
      const root = d.querySelector('.content-wrapper, main, .page-content, .content') || d.body;
      root.querySelectorAll('a[href]').forEach(a => {
        if (a.closest('nav, aside, header, .sidebar, .navbar')) return;
        const hr = a.getAttribute('href') || ''; if (!hr || hr[0] === '#' || /^(javascript|mailto|tel):/i.test(hr)) return;
        let u; try { u = new URL(hr, location.origin + p); } catch (e) { return; }
        if (u.origin !== location.origin) return;
        const path = u.pathname + (u.search || ''); if (path === '/' || BAD.test(path) || seen[path.toLowerCase()]) return;
        const name = txt(a) || a.getAttribute('title') || ''; if (!name || name.length > 60) return;
        seen[path.toLowerCase()] = 1; res.links.push({path: path, name: name, group: '', in_menu: false});
      });
      res.links = res.links.slice(0, 60);
    }
    out[p] = res;
  } catch (e) { out[p] = {s: 0, ms: Math.round(performance.now() - t0), error: true, title: String(e).slice(0, 80), tables: 0, rows: 0}; }
}
async function w() { while (i < paths.length) { await one(paths[i++]); } }
Promise.all(Array.from({length: workers}, w)).then(() => done(out));
"""

DEFAULT_SKIP = ["login", "tickets"]          # + whatever the user adds (sign-out links are never opened anyway)


# links that are not screens: notification counters / «view all» / action buttons in the top bar
JUNK_NAME = re.compile(r"^(الكل|all|view all.*|عرض الكل|إلغاء الحركة|قراءة الخبر|recover)$|^يوجد\s*:|^تم إنشاء|:\s*\d+$|^\d+$", re.I)


def is_junk(name):
    return bool(JUNK_NAME.search((name or "").strip()))


def skip_word(path, name, skip):
    """the skip word this link matches ('' = keep it)"""
    if is_junk(name):
        return "إشعار / مش شاشة"
    p, n = (path or "").lower(), (name or "").lower()
    for w in skip or ():
        w = str(w).strip().lower()
        if w and (w in p or w in n):
            return w
    return ""


def key_for(path):
    k = re.sub(r"[^a-z0-9]+", "_", path.split("?")[0].lower()).strip("_") or "home"
    q = re.sub(r"[^a-z0-9]+", "_", path.split("?")[1].lower()).strip("_") if "?" in path else ""
    return ("d_" + k + ("_" + q if q else ""))[:60]


def english_name(path):
    """/SalesInvoice -> Sales Invoice, /JournalEntries?type=1 -> Journal Entries (1)"""
    base, _, q = path.partition("?")
    parts = [p for p in base.strip("/").split("/") if p and p.lower() not in ("index", "home")]
    words = " ".join(re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", p).replace("_", " ").replace("-", " ")
                     for p in parts[-2:]) or "Home"
    val = re.findall(r"=([^&]+)", q)
    return words.strip() + (f" ({val[0]})" if val else "")


class Progress:
    """live progress + the report of the run"""

    def __init__(self, progress_file=None):
        self.file = Path(progress_file) if progress_file else None
        self.id = datetime.now().strftime("disc_%Y%m%d_%H%M%S")
        self.data = {"report_id": self.id, "started_at": datetime.now().isoformat(timespec="seconds"),
                     "phase": "login", "message": "بسجّل دخول…", "total": 0, "done": 0, "items": [], "steps": [],
                     "base_url": BASE_URL}
        self.report_dir = paths.RUNS_DIR / "discovery"
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.step(f"🔐 بسجّل دخول على {BASE_URL}")

    def step(self, msg, **kw):
        self.data["steps"].append({"t": datetime.now().strftime("%H:%M:%S"), "msg": msg})
        self.data["message"] = msg
        self.data.update(kw)
        self.save()

    def save(self, final=False):
        self.data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        if final:
            self.data["finished_at"] = self.data["updated_at"]
        txt = json.dumps(self.data, ensure_ascii=False)
        for f in [self.file, self.report_dir / f"{self.id}.json"]:
            if f:
                try:
                    tmp = f.with_suffix(".tmp")
                    tmp.write_text(txt, encoding="utf-8")
                    tmp.replace(f)
                except Exception:
                    pass


def discover(driver, check=True, limit=3000, known_urls=(), progress=None, skip=None, deep=False):
    prog = progress or Progress()
    skip = [s for s in (DEFAULT_SKIP if skip is None else skip) if str(s).strip()]
    prog.data["skip"] = skip
    prog.data["skipped"] = []
    prog.step("✅ دخلت — بقرأ القايمة الجانبية", phase="menu")
    links = []
    for start in ("/", "/Home", "/Home/Index", "/Dashboard"):
        try:
            driver.get(BASE_URL.rstrip("/") + start)
            time.sleep(3)
            links = driver.execute_script(MENU_JS) or []
        except Exception:
            links = []
        if len(links) >= 3:
            break
    menu = [l for l in links if l["in_menu"]] or links
    if deep:                                     # every link on the home page, menu first
        menu = menu + [l for l in links if l not in menu]

    def keep(l):
        w = skip_word(l["path"], l["name"], skip)
        if w:
            prog.data["skipped"].append({"name": l["name"], "url": l["path"], "word": w})
        return not w
    seen = {l["path"].lower() for l in menu}
    menu = [l for l in menu if keep(l)][:limit]
    if skip:
        prog.step(f"🚫 اتخطيت {len(prog.data['skipped'])} رابط فيه: {'، '.join(skip)}")
    known = {u.split("?")[0].lower().rstrip("/") for u in known_urls}
    logger.info(f"🧭 لقيت {len(menu)} رابط في القايمة")
    prog.step(f"🧭 لقيت {len(menu)} رابط في القايمة — هفتحهم واحد واحد", phase="checking", total=len(menu))
    i = 0
    if check:
        driver.set_script_timeout(600)
    while i < len(menu):
        batch = menu[i:i + 40]
        prog.data["current"] = f"{batch[0]['name']} … ({len(batch)} صفحة مع بعض)"
        prog.save()
        res = {}
        if check:
            try:
                res = driver.execute_async_script(FETCH_CHECK_JS, [l["path"] for l in batch], 6, bool(deep)) or {}
            except Exception as e:
                t = f"{type(e).__name__} {e}".lower()
                if any(w in t for w in ("invalidsessionid", "disconnected", "session deleted", "chrome not reachable", "tab crashed")):
                    prog.step("⚠️ المتصفح وقع — ببدأ من جديد", phase="retry")
                    raise
                res = {}
        for l in batch:
            i += 1
            base = l["path"].split("?")[0].lower().rstrip("/")
            item = {"key": key_for(l["path"]), "name": l["name"], "name_en": english_name(l["path"]), "group": l["group"],
                    "url": l["path"], "full_url": BASE_URL.rstrip("/") + l["path"], "known": base in known}
            if check:
                info = res.get(l["path"]) or {"error": True, "title": "مارجعش رد", "tables": 0}
                item.update({"tables": info.get("tables", 0), "rows": info.get("rows", 0), "has_add": info.get("add", False),
                             "error": bool(info.get("error") or info.get("login")), "title": info.get("title", ""),
                             "heading": info.get("heading", ""), "seconds": round((info.get("ms") or 0) / 1000, 1),
                             "status": info.get("s")})
                item["kind"] = "error" if item["error"] else ("screen" if item["tables"] else "page")
                if deep and not item["error"] and len(menu) < limit:
                    for nl in info.get("links") or []:
                        if nl["path"].lower() in seen or len(menu) >= limit:
                            continue
                        seen.add(nl["path"].lower())
                        if keep(nl):
                            nl["group"] = nl.get("group") or l["name"]
                            menu.append(nl)
                    prog.data["total"] = len(menu)
            else:
                item["kind"] = "screen"
            icon = {"screen": "✅", "page": "📄", "error": "⚠️"}[item["kind"]]
            logger.info(f"   {i}/{len(menu)} {icon} {l['name']} ({l['path']}){' — موجودة' if item['known'] else ''}")
            prog.data["items"].append(item)
            prog.data["done"] = i
        prog.save()
    screens = [x for x in prog.data["items"] if x["kind"] == "screen"]
    prog.step(f"🏁 خلصت: {len(screens)} شاشة فيها جدول من {len(menu)} رابط"
              + (f" · اتخطيت {len(prog.data['skipped'])}" if prog.data["skipped"] else ""), phase="done")
    prog.save(final=True)
    return {"screens": screens, "other": [x for x in prog.data["items"] if x["kind"] != "screen"],
            "total_links": len(menu), "report_id": prog.id, "skipped": prog.data["skipped"]}
