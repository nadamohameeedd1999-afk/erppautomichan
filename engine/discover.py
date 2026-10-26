"""
Discover the ERP's screens (اكتشاف شاشات النظام): read every link of the side menu after login,
open each one and keep the ones that are real list screens (a table). They get a «فتح الشاشة» test.
Never clicks add / save / delete.
"""
import re
import time

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
  // the menu section (the parent item's title)
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
return {title: document.title, tables: tables.length,
        add: !!document.querySelector("a[href*='AddEdit'], a[href*='Create'], a[href*='/Add']"),
        error: /server error|runtime error|exception|404 - |خطأ في الخادم/i.test(t.slice(0, 4000)), url: location.pathname};
"""


def key_for(path):
    k = re.sub(r"[^a-z0-9]+", "_", path.split("?")[0].lower()).strip("_") or "home"
    q = re.sub(r"[^a-z0-9]+", "_", path.split("?")[1].lower()).strip("_") if "?" in path else ""
    return ("d_" + k + ("_" + q if q else ""))[:60]


def discover(driver, check=True, limit=200, known_urls=()):
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
    known = {u.split("?")[0].lower().rstrip("/") for u in known_urls}
    logger.info(f"🧭 لقيت {len(menu)} رابط في القايمة")
    found, skipped = [], []
    for i, l in enumerate(menu[:limit], 1):
        base = l["path"].split("?")[0].lower().rstrip("/")
        item = {"key": key_for(l["path"]), "name": l["name"], "group": l["group"], "url": l["path"],
                "known": base in known}
        if check:
            try:
                driver.get(BASE_URL.rstrip("/") + l["path"])
                time.sleep(2)
                info = driver.execute_script(CHECK_JS) or {}
            except Exception as e:
                t = f"{type(e).__name__} {e}".lower()
                if any(w in t for w in ("invalidsessionid", "disconnected", "session deleted", "chrome not reachable", "tab crashed")):
                    raise                     # the browser died -> the command retries with a new one
                info = {"error": True, "title": str(e)[:80], "tables": 0}
            item.update({"tables": info.get("tables", 0), "has_add": info.get("add", False), "error": info.get("error", False)})
            kind = "error" if item["error"] else ("screen" if item["tables"] else "page")
            item["kind"] = kind
            logger.info(f"   {i}/{min(len(menu), limit)} {'✅' if kind == 'screen' else '⚠️' if kind == 'error' else '📄'} "
                        f"{l['name']} ({l['path']}){' — موجودة' if item['known'] else ''}")
        (found if not check or item.get("kind") == "screen" else skipped).append(item)
    return {"screens": found, "other": skipped, "total_links": len(menu)}
