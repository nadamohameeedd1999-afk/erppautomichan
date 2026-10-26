"""
Discover the ERP's screens (اكتشاف شاشات النظام): read every link of the side menu after login,
open each one and say what it is: a list screen (has a table), another page (report / dashboard), or an error.
Never clicks add / save / delete.

Progress is written to a JSON file after every step (the dashboard shows it live), and a report of the
whole run is kept in data/runs/discovery/ (Reports page).
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
  if (/logout|logoff|signout|login|\/(addedit|edit|delete|print|details|download|export)\b|\.(pdf|xlsx?|zip|png|jpe?g)$/i.test(path)) return;
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


def discover(driver, check=True, limit=200, known_urls=(), progress=None):
    prog = progress or Progress()
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
    menu = menu[:limit]
    known = {u.split("?")[0].lower().rstrip("/") for u in known_urls}
    logger.info(f"🧭 لقيت {len(menu)} رابط في القايمة")
    prog.step(f"🧭 لقيت {len(menu)} رابط في القايمة — هفتحهم واحد واحد", phase="checking", total=len(menu))
    for i, l in enumerate(menu, 1):
        base = l["path"].split("?")[0].lower().rstrip("/")
        item = {"key": key_for(l["path"]), "name": l["name"], "name_en": english_name(l["path"]), "group": l["group"],
                "url": l["path"], "full_url": BASE_URL.rstrip("/") + l["path"], "known": base in known}
        prog.data["current"] = f"{l['name']} ({l['path']})"
        prog.save()
        if check:
            t0 = time.time()
            try:
                driver.get(item["full_url"])
                time.sleep(2)
                info = driver.execute_script(CHECK_JS) or {}
            except Exception as e:
                t = f"{type(e).__name__} {e}".lower()
                if any(w in t for w in ("invalidsessionid", "disconnected", "session deleted", "chrome not reachable", "tab crashed")):
                    prog.step("⚠️ المتصفح وقع — ببدأ من جديد", phase="retry")
                    raise
                info = {"error": True, "title": str(e)[:80], "tables": 0}
            item.update({"tables": info.get("tables", 0), "rows": info.get("rows", 0), "has_add": info.get("add", False),
                         "error": info.get("error", False), "title": info.get("title", ""), "heading": info.get("heading", ""),
                         "seconds": round(time.time() - t0, 1)})
            item["kind"] = "error" if item["error"] else ("screen" if item["tables"] else "page")
        else:
            item["kind"] = "screen"
        icon = {"screen": "✅", "page": "📄", "error": "⚠️"}[item["kind"]]
        logger.info(f"   {i}/{len(menu)} {icon} {l['name']} ({l['path']}){' — موجودة' if item['known'] else ''}")
        prog.data["items"].append(item)
        prog.data["done"] = i
        prog.save()
    screens = [x for x in prog.data["items"] if x["kind"] == "screen"]
    prog.step(f"🏁 خلصت: {len(screens)} شاشة فيها جدول من {len(menu)} رابط", phase="done")
    prog.save(final=True)
    return {"screens": screens, "other": [x for x in prog.data["items"] if x["kind"] != "screen"],
            "total_links": len(menu), "report_id": prog.id}
