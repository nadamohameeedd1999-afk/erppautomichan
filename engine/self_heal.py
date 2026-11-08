"""
🩹 Self-healing with a log (ideas: Opkey self-healing «with a full audit trail», Worksoft «Dynamic Relearn»)

When a field's id is not on the page any more (the developers renamed it), the field is looked for by:
  1) the same id in another letter case, or an element whose name = the old id
  2) its label text (<label for=…>, or the input inside / right after the label)
If it is found, this run goes on with the new id, the change is written to the heal log (per site), and the next runs
use the new id straight away. On the Automatic test page you see every heal and can undo one if it was wrong.
"""
import json
import os
import time

from config import paths
from utils.logger import logger

FIND_JS = r"""
const [oldId, label, wantSelect] = arguments;
const N = s => String(s || '').replace(/[ً-ْـ]/g, '').replace(/[أإآ]/g, 'ا').replace(/ة/g, 'ه').replace(/ى/g, 'ي')
  .replace(/[*:：]/g, '').replace(/\s+/g, ' ').trim().toLowerCase();
const ok = e => e && e.id && e.id !== oldId && !/^select2-/.test(e.id) && (!wantSelect || e.tagName === 'SELECT')
  && e.type !== 'hidden' || (e && e.id && e.tagName === 'SELECT');
const els = [...document.querySelectorAll('input, select, textarea')];
let el = els.find(e => e.id && e.id.toLowerCase() === String(oldId).toLowerCase() && e.id !== oldId) || els.find(e => e.name && e.name === oldId && e.id);
if (ok(el)) return {id: el.id, how: 'name / case'};
const want = N(label);
if (!want) return null;
for (const l of document.querySelectorAll('label')) {
  const t = N(l.innerText);
  if (!t || !(t === want || (want.length > 3 && (t.includes(want) || want.includes(t))))) continue;
  let c = (l.htmlFor && document.getElementById(l.htmlFor)) || l.querySelector('input, select, textarea');
  if (!c) { let s = l.nextElementSibling; for (let i = 0; s && i < 3 && !c; i++, s = s.nextElementSibling) c = s.matches('input, select, textarea') ? s : s.querySelector('input, select, textarea'); }
  if (!c) { const box = l.closest('.form-group, .col, [class*=col-], td, .row'); if (box) c = box.querySelector('select, input:not([type=hidden]), textarea'); }
  if (ok(c)) return {id: c.id, how: 'label «' + l.innerText.trim().slice(0, 40) + '»'};
}
return null;
"""


def _file():
    return paths.STATE_DIR / "heals.json"


def _site():
    try:
        from engine.health import _site_key
        return _site_key()
    except Exception:
        return "?"


def load():
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except Exception:
        return {"heals": []}


def _save(d):
    paths.STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _file().with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, _file())


def known(old_id):
    """a heal learned before on this site -> the new id (undone heals are ignored)"""
    s = _site()
    for h in reversed(load()["heals"]):
        if h.get("site") == s and h.get("old") == old_id and not h.get("undone"):
            return h["new"]
    return None


def try_heal(driver, field):
    """-> new id or None. Logs and remembers a heal."""
    fid = field.get("id") or ""
    if not fid or fid.startswith("css:"):
        return None
    try:
        r = driver.execute_script(FIND_JS, fid, field.get("label") or "", field.get("kind") in ("select", "select2")) or None
    except Exception:
        return None
    if not r or not r.get("id"):
        return None
    d = load()
    s = _site()
    h = next((x for x in d["heals"] if x.get("site") == s and x.get("old") == fid and x.get("new") == r["id"]), None)
    if h:
        h["count"] = h.get("count", 1) + 1
        h["last"] = time.strftime("%Y-%m-%d %H:%M")
        h.pop("undone", None)
    else:
        d["heals"].append({"site": s, "old": fid, "new": r["id"], "label": field.get("label") or "", "how": r.get("how", ""),
                           "url": driver.current_url, "at": time.strftime("%Y-%m-%d %H:%M"), "count": 1,
                           "run": os.getenv("RUN_ID", "")})
    d["heals"] = d["heals"][-500:]
    _save(d)
    logger.warning(f"🩹 اتصلّح تلقائي: «{field.get('label') or fid}» الـ id اتغير من {fid} إلى {r['id']} (لقيته بـ {r.get('how')}) — اتسجل في سجل الإصلاحات")
    return r["id"]


def undo(old, new):
    d = load()
    for h in d["heals"]:
        if h.get("old") == old and h.get("new") == new:
            h["undone"] = True
    _save(d)


def listing():
    return list(reversed(load()["heals"]))[:200]
