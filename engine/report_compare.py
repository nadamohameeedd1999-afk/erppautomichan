"""
🆚 مقارنة التقارير — any DevExpress report of NQ ERP (/Report/…) on our test site and on a client's system, with the same
scenario. The data differ, so what is compared is what the CODE and the STORED PROCEDURE decide:

  كود الصفحة      the report exists in the menu, the page opens, the report the server maps it to (reportUrl), DevExpress
                  version / resources, the page's own script files, parameters (name, type, caption, visible, multi, null,
                  default), the values of fixed filter lists (enums)
  الإجراء المخزن   the report builds without a server error, the fields the procedure returns (xlsx export)
  العرض           titles, number of columns, number / date formats, page size + orientation, fonts, controls showing their
                  design name (xrLabel…), parameters without caption, odd values (null / NaN / #Error / 01/01/0001 …)
  المنطق          running balance = previous + in − out, totals = sum of the rows above, sort direction, last balance =
                  stock on hand (item card)
  الأداء          build time

Each site is captured by its own read-only run (nothing is saved on the ERP); a run can capture many reports one after
the other. The page compares the latest capture of each report on both sites and exports one report with every difference.
"""
import base64
import csv
import hashlib
import io
import json
import re
from datetime import datetime

from utils.logger import logger

ITEMCARD = "/Report/ItemCardReport_Polan"
DATE_T = "System.DateTime"
NUM_T = ("Int16", "Int32", "Int64", "Decimal", "Double", "Single", "Byte")
CATS = ["كود الصفحة", "الإجراء المخزن", "العرض", "المنطق", "الأداء"]


# ------------------------------------------------------------------ settings (settings/report_compare.json)
def _file():
    from config import paths
    return paths.SETTINGS_DIR / "report_compare.json"


def site_key(url):
    return re.sub(r"^https?://", "", str(url or "")).strip("/").lower()


def slug(path):
    return re.sub(r"[^a-z0-9]+", "_", str(path or "").lower()).strip("_")[:90]


def norm_path(p):
    p = "/" + str(p or "").strip().split("?")[0].split("#")[0].lstrip("/")
    p = re.sub(r"^/https?://[^/]+", "", p)
    return p.rstrip("/")


def load_cfg():
    try:
        d = json.loads(_file().read_text(encoding="utf-8"))
    except Exception:
        d = {}
    d.setdefault("reports", {})
    d.setdefault("selected", [])
    d.setdefault("auto_pick", True)
    for sc in d.pop("scenarios", None) or []:                       # the first version: one «scenario» per report
        r = d["reports"].setdefault(norm_path(sc.get("report") or ITEMCARD), {})
        r.setdefault("name", sc.get("name", ""))
        r.setdefault("sites", sc.get("sites") or {})
        if sc.get("date_from"):
            r.setdefault("date_from", sc["date_from"])
        for k in ("a", "b"):
            if sc.get(k):
                d.setdefault(k, sc[k])
    if not d["reports"]:
        d["reports"][ITEMCARD] = {"name": "كارت صنف تحليلي", "sites": {}}
    if not d["selected"]:
        d["selected"] = [ITEMCARD]
    return d


def save_cfg(d):
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def report_conf(path, d=None):
    d = d or load_cfg()
    return d["reports"].get(norm_path(path)) or {"sites": {}}


# ------------------------------------------------------------------ state files
def _state(name):
    from config import paths
    return paths.STATE_DIR / name


def _snap_file(path, url):
    return _state(f"repcmp_{slug(path)}_{re.sub(r'[^a-z0-9]', '_', site_key(url))}.json")


def _cat_file(url):
    return _state(f"repcmp_catalog_{re.sub(r'[^a-z0-9]', '_', site_key(url))}.json")


def _read(f):
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write(f, data):
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def load_snap(path, url):
    return _read(_snap_file(path, url))


def load_catalog(url):
    return _read(_cat_file(url)) or {}


# ------------------------------------------------------------------ browser scripts
CATALOG = r"""
const seen = {}, out = [];
for (const a of document.querySelectorAll('a[href]')) {
  let h = (a.getAttribute('href') || '').trim(); const m = h.match(/^(?:https?:\/\/[^\/]+)?(\/Report\/[^?#\s]+)/i); if (!m) continue;
  const local = !/^https?:/i.test(h) || h.startsWith(location.origin); if (!local) continue;
  h = m[1].replace(/\/+$/, ''); const key = h.toLowerCase(); if (seen[key]) continue; seen[key] = 1;
  const li = a.closest('li'); const card = a.closest('.card-body');
  const group = ((card && card.querySelector('.h3, .control-label')) || {}).textContent || ((li && li.parentElement && li.parentElement.closest('li') && li.parentElement.closest('li').querySelector('a')) || {}).textContent || '';
  const col = a.closest('[class*="col-"]'); const sec = ((col && col.querySelector('h4, h5')) || {}).textContent || '';
  out.push({path: h, name: a.textContent.replace(/\s+/g, ' ').trim(), group: group.replace(/\s+/g, ' ').trim(), section: sec.replace(/\s+/g, ' ').trim()});
}
return out;
"""

META = r"""
const done = arguments[arguments.length - 1];
const w = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const body = () => (document.body ? document.body.innerText : '').replace(/\s+/g, ' ').trim().slice(0, 400);
  let k = null; for (let i = 0; i < 50 && !k; i++) { k = Object.keys(window).find(x => x.startsWith('WebDocumentViewer_')); if (!k) await w(500); }
  const fp = {title: document.title, dx: (window.DevExpress && DevExpress.Analytics && DevExpress.Analytics.VERSION) || (window.DevExpress && DevExpress.VERSION) || '',
              dxr: ((Array.from(document.scripts).map(s => s.src).find(s => s.includes('DXR.axd')) || '').match(/[?&]p=([\w]+)/) || [])[1] || '',
              scripts: Array.from(document.scripts).map(s => s.getAttribute('src') || '').filter(s => s && !/^(https?:)?\/\//.test(s) && !s.includes('DXR.axd')).map(s => s.replace(location.origin, ''))};
  if (!k) return {noviewer: true, fp, body: body()};
  const v = window[k]; let pm = null; for (let i = 0; i < 40 && !pm; i++) { try { pm = v.GetParametersModel(); } catch (e) {} if (!pm || !pm._parameters) { pm = null; await w(500); } }
  let p = null; try { p = v.GetReportPreview(); } catch (e) {}
  if (p) { fp.reportUrl = String(p.reportUrl || ''); fp.rtl = !!(typeof p.rtlReport === 'function' ? p.rtlReport() : p.rtlReport); }
  if (!pm) return {noparams: true, fp, body: body()};
  const lv = x => { const l = x.lookUpValues; return (Array.isArray(l) ? l : (typeof l === 'function' ? l() : [])) || []; };
  const str = x => x === null || x === undefined ? '' : (x instanceof Date ? 'تاريخ' : (Array.isArray(x) ? x.join(',') : String(x)));
  const params = [], lookups = {};
  for (const x of pm._parameters) {
    const d = (x.getParameterDescriptor && x.getParameterDescriptor()) || {}; const L = lv(x);
    let def = d.value; if (d.type === 'System.DateTime') def = def ? 'تاريخ' : '';
    params.push({path: x.path, type: d.type || x.type, label: d.description || '', visible: d.visible !== false, enabled: d.enabled !== false,
                 multi: !!d.multiValue, allow_null: !!d.allowNull, has_lookups: !!d.hasLookUpValues || L.length > 0, lookups: L.length, def: str(def),
                 fixed: L.length && L.length <= 30 ? L.map(o => [String(o.value), String(o.displayValue ?? o.description ?? o.value)]) : null});
    if (L.length) lookups[x.path] = L.slice(0, 5000).map(o => [String(o.value), String(o.displayValue ?? o.description ?? o.value)]);
  }
  return {params, lookups, fp};
})().then(done).catch(e => done({err: String(e)}));
"""

BUILD = r"""
const done = arguments[arguments.length - 1]; const [vals, wantPdf] = Array.from(arguments).slice(0, -1);
const w = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const k = Object.keys(window).find(x => x.startsWith('WebDocumentViewer_')); const v = window[k]; const p = v.GetReportPreview(); const pm = v.GetParametersModel();
  const num = t => /Int|Decimal|Double|Single|Byte/.test(t);
  for (const [name, tv] of Object.entries(vals)) { const [t, val, multi] = tv; let x = val;
    const one = s => t === 'System.DateTime' ? new Date(s) : (num(t) ? +s : (t === 'System.Boolean' ? (s === true || s === 'true' || s === '1') : s));
    x = multi ? String(val).split(',').filter(Boolean).map(one) : one(val);
    try { pm[name] = x; } catch (e) {} await w(700); }
  let fault = '', http = 0; const of0 = window.fetch;
  window.fetch = async function (u, o) { const r = await of0.apply(this, arguments);
    try { if (String(u).includes('DXXRDV')) { if (r.status >= 500) http = r.status; const t = await r.clone().text(); if (t && t[0] === '{') { const j = JSON.parse(t); const m = (j.result && j.result.faultMessage) || (j.error && (j.error.message || j.error)); if (m) fault = String(m); } } } catch (e) {}
    return r; };
  const doc0 = p.documentId; const t0 = Date.now(); let started = false;
  try { pm.submit(); } catch (e) { window.fetch = of0; return {err: 'submit: ' + e}; }
  await w(1200);
  while (Date.now() - t0 < 180000) { await w(800); if (p.documentBuilding) started = true;
    if ((p.documentBuilding === false && p.documentId && p.documentId !== doc0) || fault) break;
    if (!started && !p.documentId && Date.now() - t0 > 25000) break; }
  window.fetch = of0;
  const ms = Date.now() - t0;
  if (!fault && p.documentId && p.documentId !== doc0) { const t1 = Date.now(); while (!p.exportOptionsModel && Date.now() - t1 < 20000) await w(500); }
  const pages = (p.pages || []).length;
  if (fault) return {fault, http, ms, pages};
  if (!p.documentId || p.documentId === doc0) return {stuck: true, ms, msg: String(p.errorMessage || '')};
  if (!pages || !p.exportOptionsModel) return {empty: true, ms, pages};
  const grab = async (fmt) => { let buf = null; const of = window.fetch;
    window.fetch = async function (u, o) { const r = await of.apply(this, arguments); try { if (o && String(o.body).includes('getExportResult')) buf = new Uint8Array(await r.clone().arrayBuffer()); } catch (e) {} return r; };
    const wo = window.open; window.open = () => null;
    try { p.exportDocumentTo(fmt); } catch (e) {}
    const t = Date.now(); while (!buf && Date.now() - t < 90000) await w(700);
    window.fetch = of; window.open = wo; if (!buf) return '';
    let s = ''; for (let i = 0; i < buf.length; i += 8192) s += String.fromCharCode.apply(null, buf.subarray(i, i + 8192)); return btoa(s); };
  const c = p.exportOptionsModel && p.exportOptionsModel.csv; if (c) c.encodingType = 'UTF8';
  const csv = await grab('csv'); const xlsx = await grab('xlsx'); const pdf = wantPdf && pages <= 80 ? await grab('pdf') : '';
  return {ms, pages: (p.pages || []).length, csv, xlsx, pdf};
})().then(done).catch(e => done({err: String(e)}));
"""


# ------------------------------------------------------------------ capture (one site, read only)
def capture(driver, credentials, cfg, result=None):
    """one run on one site: read the report menu, then build every requested report and save a snapshot of each"""
    from engine.screen_runner import login
    from config.settings import BASE_URL
    result = result if result is not None else {}
    base = BASE_URL.rstrip("/")
    conf = load_cfg()
    reports = [norm_path(x) for x in (cfg.get("reports") or [])] or ([] if cfg.get("catalog") else list(conf["selected"]))
    login(driver, credentials)
    driver.set_script_timeout(400)
    rows = []
    try:
        cat = driver.execute_script(CATALOG) or []
        _write(_cat_file(base), {"at": _now(), "url": base, "reports": cat})
        logger.info(f"🆚 قايمة التقارير: {len(cat)} تقرير في المنيو")
        rows.append({"cells": ["قايمة التقارير", f"{len(cat)} تقرير /Report/ في المنيو", "", ""], "ok": None})
    except Exception as e:
        logger.warning(f"🆚 مقدرتش أقرا المنيو: {e}")
    names = {c["path"].lower(): c["name"] for c in (load_catalog(base).get("reports") or [])}
    for i, path in enumerate(reports, 1):
        logger.info(f"🆚 [{i}/{len(reports)}] {path}")
        try:
            snap = capture_one(driver, base, path, report_conf(path, conf), conf)
        except Exception as e:
            snap = {"status": "crash", "error": str(e)[:400]}
            _write(_snap_file(path, base), {"site": site_key(base), "url": base, "at": _now(), "report": path, **snap})
        txt = {"ok": f"اتبنى — {snap.get('rows_n', 0)} سطر، {snap.get('pages', 0)} صفحة، {(snap.get('ms') or 0) / 1000:.1f} ث",
               "error": "فشل في البناء: " + str(snap.get("fault", ""))[:200], "empty": "طلع فاضي (مفيش صفحات)",
               "stuck": "ماتبناش — غالبًا فيه فلتر مطلوب فاضي " + str(snap.get("msg", "")), "noviewer": "الصفحة مفيهاش عارض تقارير: " + str(snap.get("body", ""))[:160],
               "crash": "الأداة وقفت: " + str(snap.get("error", ""))}.get(snap.get("status"), snap.get("status"))
        auto = snap.get("auto") or {}
        st_ = snap.get("status")
        (logger.success if st_ == "ok" else logger.error if st_ in ("error", "noviewer", "crash", "stuck") else logger.warning)(
            ("✅ " if st_ == "ok" else "❌ " if st_ in ("error", "noviewer", "crash", "stuck") else "⚪ ") + txt)
        rows.append({"cells": [names.get(path.lower()) or report_conf(path, conf).get("name") or path, path, txt,
                               " · ".join(f"{k}={v}" for k, v in (snap.get("chosen_names") or {}).items()) + (" (اختيار تلقائي)" if auto else "")],
                     "ok": {"ok": True, "error": False, "noviewer": False, "crash": False}.get(snap.get("status"))})
    result["detail"] = {"title": f"🆚 مقارنة التقارير — {site_key(base)}", "columns": ["التقرير", "اللينك", "النتيجة", "السيناريو"], "rows": rows,
                        "note": f"اتقرا {len(reports)} تقرير من الموقع ده (قراءة بس) — افتح «مقارنة التقارير» علشان تشوف الفرق مع الموقع التاني"}
    result["repcmp"] = {"site": site_key(base), "reports": reports}
    return result


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _date_role(p):
    n = p["path"].lower()
    if re.search(r"from|start|begin|bdate|^d1$|من", n):
        return "from"
    if re.search(r"to|end|edate|^d2$|الى|إلى", n):
        return "to"
    return ""


def plan_values(params, lookups, chosen, rc, glob, auto):
    """→ ({path: [type, value, multi]}, {path: display}, {path: True when picked automatically})"""
    vals, names, picked = {}, {}, {}
    dates = [p for p in params if p["type"] == DATE_T and p.get("visible")]
    dfrom = rc.get("date_from") or glob.get("date_from") or ""
    dto = rc.get("date_to") or glob.get("date_to") or ""
    for i, p in enumerate(dates):
        role = _date_role(p) or ("from" if i == 0 else "to" if i == 1 else "")
        v = dfrom if role == "from" else dto if role == "to" else ""
        if v:
            vals[p["path"]] = [DATE_T, v, False]
            names[p["label"] or p["path"]] = v
    for p in params:
        v = str((chosen or {}).get(p["path"]) or "").strip()
        if not v:
            continue
        vals[p["path"]] = [p["type"], v, p.get("multi")]
        lk = dict(lookups.get(p["path"]) or [])
        names[p["label"] or p["path"]] = ", ".join(lk.get(x, x) for x in v.split(",")) if p.get("multi") else lk.get(v, v)
    if auto:
        for p in params:
            if p["path"] in vals or not p.get("visible") or not p.get("has_lookups") or p.get("def") not in ("", "null", "undefined"):
                continue
            L = lookups.get(p["path"]) or []
            first = next((x for x in L if x[0] not in ("", "0", "null", "-1")), None) or (L[0] if L else None)
            if first:
                vals[p["path"]] = [p["type"], first[0], p.get("multi")]
                names[p["label"] or p["path"]] = first[1]
                picked[p["path"]] = True
    return vals, names, picked


def capture_one(driver, base, path, rc, glob):
    key = site_key(base)
    driver.get(base + path)
    meta = driver.execute_async_script(META) or {}
    snap = {"site": key, "url": base, "at": _now(), "report": path, "fp": meta.get("fp") or {}}
    if meta.get("err"):
        raise RuntimeError(meta["err"])
    if meta.get("noviewer") or meta.get("noparams"):
        snap.update({"status": "noviewer", "body": meta.get("body", "")})
        _write(_snap_file(path, base), snap)
        return snap
    params, lookups = meta["params"], meta.get("lookups") or {}
    snap.update({"params": params, "lookups": {k: v[:5000] for k, v in lookups.items()}})
    chosen = (rc.get("sites") or {}).get(key) or {}
    vals, names, picked = plan_values(params, lookups, chosen, rc, glob, False)
    b = driver.execute_async_script(BUILD, vals, True) or {}
    if (b.get("empty") or b.get("stuck")) and glob.get("auto_pick", True):
        v2, n2, p2 = plan_values(params, lookups, chosen, rc, glob, True)
        if p2:                                  # empty with the defaults → try the first value of the empty lists
            logger.info("🆚 طلع فاضي بالافتراضي — بجرب أول قيمة في: " + "، ".join(p2))
            b2 = driver.execute_async_script(BUILD, v2, True) or {}
            if not b2.get("err"):
                b, vals, names, picked = b2, v2, n2, p2
    snap.update({"chosen": {k: v[1] for k, v in vals.items()}, "chosen_names": names, "auto": picked})
    if b.get("err"):
        raise RuntimeError(b["err"])
    if b.get("fault"):
        snap.update({"status": "error", "fault": b["fault"], "http": b.get("http") or 0, "ms": b.get("ms")})
    elif b.get("stuck"):
        snap.update({"status": "stuck", "msg": b.get("msg", ""), "ms": b.get("ms")})
    elif b.get("empty"):
        snap.update({"status": "empty", "ms": b.get("ms")})
    else:
        snap.update({"status": "ok", "ms": b.get("ms"), "pages": b.get("pages")})
        snap.update(analyze(b.get("csv") or "", b.get("xlsx") or "", names))
        snap.update(analyze_pdf(b.get("pdf") or ""))
        wh, it = vals.get("WarehouseId"), vals.get("Itemid")
        if path.lower() == ITEMCARD.lower() or (wh and it):
            if wh and it:
                try:
                    snap["stock"] = driver.execute_async_script("""const done = arguments[arguments.length-1]; fetch(`/Helper/ItemQuantityOnSystem?warehouseId=${arguments[0]}&itemId=${arguments[1]}&voucherId=0&date=${encodeURIComponent(new Date().toISOString().slice(0,16))}`, {credentials:'include'}).then(r => r.text()).then(t => { try { done(JSON.parse(t).quantity); } catch (e) { done(null); } }).catch(() => done(null));""", wh[1], it[1])
                except Exception:
                    snap["stock"] = None
    _write(_snap_file(path, base), snap)
    return snap


# ------------------------------------------------------------------ analysis of one capture
NUM = re.compile(r"^-?[\d,]*\.?\d+$")
NEG_PAR = re.compile(r"^\([\d,]*\.?\d+\)$")
DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}( \d{1,2}:\d{2}(:\d{2})?( ?[APap][Mm])?)?$|^\d{1,2} [A-Za-z]+ \d{4}$|^\d{4}-\d{2}-\d{2}")
ODD = re.compile(r"^(null|NULL|NaN|undefined|Infinity|-Infinity|#Error|#ERROR|#Name\?|System\.[\w.]+|0?1/0?1/0001|0?1/0?1/1900|0001-01-01.*|\[object Object\])$")
TOTAL = re.compile(r"إجمالي|اجمالي|الإجمالي|الاجمالي|المجموع|مجموع|Total|TOTAL|Sum\b")


def _num(s):
    s = str(s or "").strip()
    if not s:
        return None
    if NEG_PAR.match(s.replace(" ", "")):
        s = "-" + s.strip("()")
    if not NUM.match(s.replace(" ", "")):
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def fmt_sig(s):
    s = str(s or "").strip()
    if not s:
        return ""
    if DATE.match(s):
        return "تاريخ " + re.sub(r"\d", "9", s)
    if NEG_PAR.match(s.replace(" ", "")):
        return "سالب بين قوسين"
    if NUM.match(s.replace(" ", "")):
        dec = len(s.split(".")[1]) if "." in s else 0
        return ("آلاف، " if "," in s else "") + f"{dec} عشري" + (" · من غير صفر قبل العلامة" if s.startswith(".") or s.startswith("-.") else "")
    return "نص"


def _date_val(s):
    s = str(s or "").strip()
    for f in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d %B %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s.split(" ")[0] if "/" in s or "-" in s else s, f)
        except ValueError:
            continue
    return None


def analyze(csv_b64, xlsx_b64, names):
    out = {"labels": [], "fields": [], "formats": [], "rows_n": 0, "cols_n": 0, "controls": [], "rule": None, "last_balance": None,
           "odd": [], "sort": "", "totals": {"found": False}, "blank_cells": 0}
    skip = {re.sub(r"\s+", " ", str(v)).strip() for v in (names or {}).values() if str(v).strip()}
    # CSV = what the user sees (titles + formatted numbers)
    if csv_b64:
        text = base64.b64decode(csv_b64).decode("utf-8-sig", "replace")
        rows = list(csv.reader(io.StringIO(text), delimiter=";"))
        isdata = lambda r: sum(1 for c in r if _num(c) is not None) >= min(4, max(2, len([c for c in r if c.strip()]) // 2))
        start = next((i for i, r in enumerate(rows) if isdata(r) and sum(1 for c in r if _num(c) is not None) >= 2), len(rows))
        labels = []
        for r in rows[:start]:
            for c in r:
                c = re.sub(r"\s+", " ", c).strip().strip(":").strip()
                if not c or c in skip or _num(c) is not None or DATE.match(c) or re.match(r"^\d+/\d+$", c) or c in ("-", "—"):
                    continue
                if any(c.startswith(x) or x.startswith(c) for x in skip if len(x) > 3):
                    continue
                labels.append(c)
        out["labels"] = labels
        out["controls"] = sorted({c.strip() for r in rows for c in r if re.match(r"^\s*xr[A-Z][A-Za-z]*\d*\s*$", c)})
        out["odd"] = sorted({c.strip() for r in rows for c in r if ODD.match(c.strip())})[:15]
        data = [r for r in rows[start:] if isdata(r)]
        out["rows_n"] = len(data)
        width = max((len(r) for r in data), default=0)
        used = [j for j in range(width) if any(j < len(r) and r[j].strip() for r in data)]
        out["cols_n"] = len(used)
        out["blank_cells"] = sum(1 for r in data for j in used if j >= len(r) or not r[j].strip())
        fm = []
        for j in used:
            sigs = [fmt_sig(r[j]) for r in data if j < len(r) and r[j].strip()]
            if sigs:
                main = max(set(sigs), key=sigs.count)
                other = sorted(set(sigs) - {main})
                fm.append(main + (f" (+ {' / '.join(other)})" if other else ""))
        out["formats"] = fm
        # sort direction on the first date column
        for j in used:
            ds = [_date_val(r[j]) for r in data if j < len(r) and DATE.match(r[j].strip() or "x")]
            ds = [d for d in ds if d]
            if len(ds) >= 3:
                up = all(ds[i] <= ds[i + 1] for i in range(len(ds) - 1))
                down = all(ds[i] >= ds[i + 1] for i in range(len(ds) - 1))
                out["sort"] = "تصاعدي بالتاريخ" if up and not down else "تنازلي بالتاريخ" if down and not up else ("تاريخ واحد" if up and down else "مش مترتب بالتاريخ")
                break
    # XLSX (raw data) = the fields the stored procedure returns + the numbers
    if xlsx_b64:
        try:
            from openpyxl import load_workbook
            ws = load_workbook(io.BytesIO(base64.b64decode(xlsx_b64)), data_only=True, read_only=True).active
            grid = [[c for c in r] for r in ws.iter_rows(values_only=True)]
        except Exception as e:
            grid = []
            out["xlsx_error"] = str(e)[:200]
        if grid:
            out["fields"] = [str(h) for h in grid[0] if h and not re.match(r"^xr", str(h))]
            body = [r for r in grid[1:] if sum(1 for c in r if isinstance(c, (int, float))) >= 2]
            out["rule"], out["last_balance"] = running_rule([r for r in body if sum(1 for c in r if isinstance(c, (int, float))) >= 3], grid[0])
            out["totals"] = totals_rule(body)
    return out


def totals_rule(body):
    """rows with «إجمالي / المجموع / Total»: each numeric cell = the sum of the rows above it (since the previous total)"""
    checked, bad, block = 0, [], []
    for i, r in enumerate(body):
        if any(isinstance(c, str) and TOTAL.search(c) for c in r):
            if len(block) >= 2:
                for j, c in enumerate(r):
                    if not isinstance(c, (int, float)):
                        continue
                    col = [x[j] for x in block if j < len(x) and isinstance(x[j], (int, float))]
                    if len(col) < 2 or len(col) < len(block) * 0.6:
                        continue
                    checked += 1
                    s = sum(col)
                    if abs(s - c) > max(0.011, abs(s) * 1e-9) and not (len(set(col)) == 1):
                        bad.append(f"سطر {i + 2} عمود {j + 1}: {c:,.2f} والمجموع {s:,.2f}")
            block = []
        else:
            block.append(r)
    return {"found": checked > 0, "checked": checked, "bad": bad[:10]}


def running_rule(body, header=None):
    """find in / out / balance columns where balance[i] = balance[i-1] + in[i] − out[i]; → (summary, last balance)"""
    if len(body) < 3:
        return {"found": False, "why": "سطور قليلة"}, None
    width = max(len(r) for r in body)
    col = lambda j: [r[j] if j < len(r) and isinstance(r[j], (int, float)) else 0.0 for r in body]
    nums = [j for j in range(width) if sum(1 for r in body if j < len(r) and isinstance(r[j], (int, float))) >= len(body) * 0.8][:25]
    best = None
    for bj in nums:
        B = col(bj)
        if len(set(B)) < 2:
            continue
        for ij in nums:
            if ij == bj:
                continue
            I = col(ij)
            if not any(I):
                continue
            for oj in nums:
                if oj in (ij, bj):
                    continue
                O = col(oj)
                if not any(O):
                    continue
                ok = sum(1 for i in range(1, len(B)) if abs(B[i] - (B[i - 1] + I[i] - O[i])) < 0.0015)
                if not best or ok > best[0]:
                    best = (ok, bj, ij, oj)
    nm = lambda j: str(header[j]) if header and j < len(header) and header[j] else f"عمود {j + 1}"
    if not best or best[0] < (len(body) - 1) * 0.5:
        out = {"found": False, "why": "مفيش أعمدة وارد / صادر / رصيد في التقرير ده"}
        if best:
            ok, bj, ij, oj = best
            B, I, O = col(bj), col(ij), col(oj)
            out["best"] = {"names": [nm(bj), nm(ij), nm(oj)], "rows": len(B) - 1, "ok": ok,
                           "bad_rows": [i + 1 for i in range(1, len(B)) if abs(B[i] - (B[i - 1] + I[i] - O[i])) >= 0.0015][:20]}
        return out, None
    ok, bj, ij, oj = best
    B, I, O = col(bj), col(ij), col(oj)
    bad = [i + 1 for i in range(1, len(B)) if abs(B[i] - (B[i - 1] + I[i] - O[i])) >= 0.0015]
    return {"found": True, "rows": len(B) - 1, "ok": ok, "bad_rows": bad[:20], "cols": [bj, ij, oj], "names": [nm(bj), nm(ij), nm(oj)]}, B[-1]


def analyze_pdf(pdf_b64):
    if not pdf_b64:
        return {}
    try:
        from pypdf import PdfReader
        rd = PdfReader(io.BytesIO(base64.b64decode(pdf_b64)))
        pg = rd.pages[0]
        w, h = float(pg.mediabox.width) * 25.4 / 72, float(pg.mediabox.height) * 25.4 / 72
        fonts = set()
        for p in rd.pages[:5]:
            res = p.get("/Resources") or {}
            for f in ((res.get("/Font") or {}).values() if hasattr(res.get("/Font") or {}, "values") else []):
                try:
                    n = str(f.get_object().get("/BaseFont") or "")
                    fonts.add(re.sub(r"^/?[A-Z]{6}\+", "", n).lstrip("/").split(",")[0])
                except Exception:
                    pass
        size = next((n for n, (a, b) in {"A4": (210, 297), "A3": (297, 420), "A5": (148, 210), "Letter": (216, 279), "Legal": (216, 356)}.items()
                     if abs(min(w, h) - a) < 4 and abs(max(w, h) - b) < 4), f"{min(w, h):.0f}×{max(w, h):.0f} مم")
        return {"page": f"{size} {'عرضي' if w > h else 'طولي'}", "fonts": sorted(f for f in fonts if f)[:12], "pdf_pages": len(rd.pages)}
    except Exception as e:
        return {"pdf_error": str(e)[:200]}


def features_rows(s):
    r = s.get("rule") or {}
    return [("البارامترات", f"{len(s.get('params') or [])}", None), ("حقول الاستورد", f"{len(s.get('fields') or [])}", None),
            ("عناوين التقرير", f"{len(s.get('labels') or [])}", None), ("سطور البيانات", f"{s.get('rows_n', 0)}", None),
            ("قاعدة الرصيد", (f"{r.get('ok')}/{r.get('rows')} سطر صح" if r.get("found") else r.get("why", "—")), bool(r.get("found") and not r.get("bad_rows")) if r.get("found") else None),
            ("كنترولات ظاهرة باسمها", "، ".join(s.get("controls") or []) or "مفيش", not s.get("controls")),
            ("وقت بناء التقرير", f"{(s.get('ms') or 0) / 1000:.1f} ث", None)]


def _same(a, b, tol=0.001):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ the comparison
ST_TXT = {"ok": "اتبنى", "error": "فشل", "empty": "فاضي (مفيش صفحات)", "stuck": "ماتبناش (فلتر مطلوب؟)", "noviewer": "الصفحة مش بتفتح التقرير", "crash": "الأداة وقفت"}
DONE = ("ok", "error", "empty", "stuck", "noviewer")


def _ptxt(p):
    return f"{p['path']} ({str(p.get('type', '')).split('.')[-1]}) «{p.get('label') or 'من غير اسم'}»"


def compare(path, url_a, url_b, A=None, B=None):
    path = norm_path(path)
    A = A if A is not None else load_snap(path, url_a)
    B = B if B is not None else load_snap(path, url_b)
    out = {"a": A, "b": B, "rows": [], "ready": bool(A and B and A.get("status") in DONE and B.get("status") in DONE)}
    rows = out["rows"]

    def add(cat, item, what, a, b, status, detail=""):
        rows.append({"cat": cat, "item": item, "what": what, "a": a, "b": b, "status": status, "detail": detail})

    def pair(cat, item, what, ta, oka, tb, okb, msg=None):
        """oka/okb: True fine, False problem, None not applicable"""
        if oka is None and okb is None:
            return
        if oka is False and okb is False:
            st, d = "both", "مشكلة في الاتنين"
        elif oka is False or okb is False:
            st, d = "diff", "مشكلة في الاختبار بس" if oka is False else "مشكلة عند العميل بس"
        elif oka is None or okb is None:
            st, d = "info", "بتنطبق على موقع واحد بس (حسب الداتا)"
        else:
            st, d = "same", "سليم في الاتنين"
        add(cat, item, what, ta, tb, st, msg or d)

    def setdiff(cat, item, what, la, lb, warn_order=True, info=False):
        sa, sb = list(dict.fromkeys(la)), list(dict.fromkeys(lb))
        only_a, only_b = [x for x in sa if x not in sb], [x for x in sb if x not in sa]
        order = not only_a and not only_b and sa != sb
        detail = []
        if only_a:
            detail.append("في الاختبار بس: " + "، ".join(map(str, only_a[:20])) + (" …" if len(only_a) > 20 else ""))
        if only_b:
            detail.append("عند العميل بس: " + "، ".join(map(str, only_b[:20])) + (" …" if len(only_b) > 20 else ""))
        if order:
            detail.append("نفس العناصر بس الترتيب مختلف")
        st = "same" if not detail else ("info" if info else ("warn" if order and warn_order else "diff"))
        add(cat, item, what, f"{len(sa)}", f"{len(sb)}", st, " · ".join(detail) or "متطابق")

    # 1) the menu (from the latest catalog of each site)
    ca, cb = load_catalog(url_a).get("reports"), load_catalog(url_b).get("reports")
    if ca is not None and cb is not None:
        ia = next((c for c in ca if c["path"].lower() == path.lower()), None)
        ib = next((c for c in cb if c["path"].lower() == path.lower()), None)
        st = "same" if ia and ib else ("both" if not ia and not ib else "diff")
        det = {"same": "موجود في المنيو في الاتنين" + (f" · الاسم مختلف: «{ia['name']}» ↔ «{ib['name']}»" if ia and ib and ia["name"] != ib["name"] else ""),
               "both": "مش موجود في منيو الاتنين (اتفتح باللينك)", "diff": "مش موجود في منيو " + ("العميل" if ia else "الاختبار")}[st]
        if st == "same" and ia["name"] != ib["name"]:
            st = "warn"
        add("كود الصفحة", "موجود في المنيو", "التقرير ظاهر في قايمة التقارير بنفس الاسم", ia["name"] if ia else "مش موجود", ib["name"] if ib else "مش موجود", st, det)
    if not (A and B):
        return out
    sa, sb = A.get("status"), B.get("status")

    # 2) the page
    pair("كود الصفحة", "الصفحة بتفتح التقرير", "صفحة التقرير بتفتح وفيها عارض DevExpress", "بتفتح" if sa != "noviewer" else "لأ: " + A.get("body", "")[:120], sa != "noviewer",
         "بتفتح" if sb != "noviewer" else "لأ: " + B.get("body", "")[:120], sb != "noviewer")
    fa, fb = A.get("fp") or {}, B.get("fp") or {}
    if fa.get("reportUrl") or fb.get("reportUrl"):
        add("كود الصفحة", "تعريف التقرير على السيرفر", "اسم التقرير اللي الصفحة بتطلبه من السيرفر (reportUrl)", fa.get("reportUrl") or "—", fb.get("reportUrl") or "—",
            "same" if fa.get("reportUrl") == fb.get("reportUrl") else "diff", "متطابق" if fa.get("reportUrl") == fb.get("reportUrl") else "الصفحة بتفتح تقرير مختلف على السيرفر")
    if fa.get("title") or fb.get("title"):
        add("كود الصفحة", "عنوان الصفحة", "عنوان تبويب المتصفح", fa.get("title") or "—", fb.get("title") or "—", "same" if fa.get("title") == fb.get("title") else "warn",
            "متطابق" if fa.get("title") == fb.get("title") else "العنوان مختلف")
    dxa, dxb = f"{fa.get('dx') or '—'} · {fa.get('dxr') or '—'}", f"{fb.get('dx') or '—'} · {fb.get('dxr') or '—'}"
    add("كود الصفحة", "نسخة DevExpress", "نسخة عارض التقارير وملفات موارده", dxa, dxb,
        "same" if fa.get("dx") == fb.get("dx") and fa.get("dxr") == fb.get("dxr") else ("diff" if fa.get("dx") != fb.get("dx") else "warn"),
        "متطابق" if dxa == dxb else ("النسخة مختلفة" if fa.get("dx") != fb.get("dx") else "نفس النسخة بس الموارد اتبنت بشكل مختلف (غالبًا نشر مختلف)"))
    if fa.get("scripts") is not None and fb.get("scripts") is not None:
        def base_(s):
            return s.split("?")[0].lower()
        ma, mb = {base_(s): s for s in fa["scripts"]}, {base_(s): s for s in fb["scripts"]}
        only_a = [k for k in ma if k not in mb]
        only_b = [k for k in mb if k not in ma]
        ver = [f"{k}: {ma[k].split('?')[1] if '?' in ma[k] else '—'} ↔ {mb[k].split('?')[1] if '?' in mb[k] else '—'}" for k in ma if k in mb and ma[k] != mb[k]]
        det = [x for x in [only_a and "في الاختبار بس: " + "، ".join(only_a[:10]), only_b and "عند العميل بس: " + "، ".join(only_b[:10]),
                           ver and "نسخة مختلفة: " + "، ".join(ver[:6])] if x]
        add("كود الصفحة", "ملفات الجافاسكربت", "ملفات السكريبت الخاصة بالنظام اللي الصفحة بتحملها", f"{len(ma)}", f"{len(mb)}",
            "same" if not det else ("warn" if not only_a and not only_b else "diff"), " · ".join(det) or "متطابق")
    if sa == "noviewer" or sb == "noviewer":
        out["diff_n"], out["warn_n"] = _count(rows)
        return out

    # 3) parameters
    pa, pb = A.get("params") or [], B.get("params") or []
    setdiff("كود الصفحة", "بارامترات التقرير", "الفلاتر اللي بتظهر للمستخدم: الاسم والنوع والعنوان", [_ptxt(p) for p in pa if p.get("visible")], [_ptxt(p) for p in pb if p.get("visible")])
    setdiff("كود الصفحة", "بارامترات مخفية", "بارامترات بتتبعت للإجراء المخزن من غير ما تظهر", [p["path"] for p in pa if not p.get("visible")], [p["path"] for p in pb if not p.get("visible")])
    mb_ = {p["path"]: p for p in pb}
    props = []
    for p in pa:
        q = mb_.get(p["path"])
        if not q:
            continue
        for k, nm in (("multi", "اختيار متعدد"), ("allow_null", "يقبل فاضي"), ("enabled", "متاح"), ("has_lookups", "قايمة اختيار")):
            if bool(p.get(k)) != bool(q.get(k)):
                props.append(f"{p['path']}: {nm} {'✓' if p.get(k) else '✗'} ↔ {'✓' if q.get(k) else '✗'}")
        static = p.get("visible") and not re.search(r"date|from|to$|user|dept|branch|lang|company", p["path"], re.I)
        if static and not p.get("has_lookups") and p.get("type") != DATE_T and str(p.get("def")) != str(q.get("def")):
            props.append(f"{p['path']}: القيمة الافتراضية «{p.get('def') or 'فاضي'}» ↔ «{q.get('def') or 'فاضي'}»")
    add("كود الصفحة", "خصائص البارامترات", "متعدد / يقبل فاضي / متاح / قايمة اختيار / القيمة الافتراضية", "", "", "diff" if props else "same", " · ".join(props[:12]) or "متطابق")
    fixed = []
    for p in pa:
        q = mb_.get(p["path"])
        if not q or not p.get("fixed") or not q.get("fixed"):
            continue
        if _enum(p["fixed"]) and _enum(q["fixed"]) and p["fixed"] != q["fixed"]:
            fixed.append(f"{p['path']}: {_ftxt(p['fixed'])} ↔ {_ftxt(q['fixed'])}")
        elif _enum(p["fixed"]) and _enum(q["fixed"]) and str(p.get("def")) != str(q.get("def")):
            fixed.append(f"{p['path']}: الافتراضي {p.get('def')} ↔ {q.get('def')}")
    add("كود الصفحة", "قيم الفلاتر الثابتة", "اختيارات القوايم الثابتة في الكود (طريقة العرض، طريقة الحساب …) وقيمتها الافتراضية", "", "", "diff" if fixed else "same", " · ".join(fixed[:8]) or "متطابق")
    na_ = [p["path"] for p in pa if p.get("visible") and not p.get("label")]
    nb_ = [p["path"] for p in pb if p.get("visible") and not p.get("label")]
    pair("العرض", "بارامتر من غير عنوان", "فلتر ظاهر للمستخدم باسمه البرمجي", "، ".join(na_) or "مفيش", not na_, "، ".join(nb_) or "مفيش", not nb_,
         None if (na_ or nb_) else "سليم")

    # 4) the build
    bt = lambda s: ST_TXT.get(s.get("status"), s.get("status")) + (": " + str(s.get("fault") or "")[:200] if s.get("status") == "error" else "")
    if sa == sb == "ok":
        st, d = "same", "اتبنى في الاتنين"
    elif sa == sb and sa in ("error", "stuck"):
        st, d = "both", "مشكلة في الاتنين"
    elif "error" in (sa, sb) or "stuck" in (sa, sb):
        st, d = "diff", "بيفشل عند " + ("العميل" if sb in ("error", "stuck") else "الاختبار") + " بس — غالبًا الإجراء المخزن أو الاستعلام مختلف"
    else:
        st, d = "info", "واحد منهم طلع فاضي — اختار قيم عليها حركات في الفترة"
    add("الإجراء المخزن", "بناء التقرير", "التقرير بيتبني بالسيناريو ده من غير خطأ من السيرفر / الإجراء المخزن", bt(A), bt(B), st, d)
    if sa != "ok" or sb != "ok":
        out["diff_n"], out["warn_n"] = _count(rows)
        return out

    # 5) what the report shows
    setdiff("الإجراء المخزن", "حقول الاستورد", "الأعمدة اللي الإجراء المخزن بيرجّعها (من ملف الإكسل)", A.get("fields") or [], B.get("fields") or [])
    setdiff("العرض", "عناوين التقرير", "النصوص الثابتة في رأس التقرير والجدول", A.get("labels") or [], B.get("labels") or [])
    add("العرض", "عدد أعمدة البيانات", "الأعمدة اللي فيها قيم في جدول التقرير", A.get("cols_n"), B.get("cols_n"),
        "same" if A.get("cols_n") == B.get("cols_n") else "diff", "متطابق" if A.get("cols_n") == B.get("cols_n") else "عدد الأعمدة مختلف")
    fa_, fb_ = A.get("formats") or [], B.get("formats") or []
    fd = [f"عمود {i + 1}: «{x}» ↔ «{y}»" for i, (x, y) in enumerate(zip(fa_, fb_)) if x.split(" (+")[0] != y.split(" (+")[0]]
    add("العرض", "تنسيق الأرقام والتواريخ", "عدد العلامات العشرية، فاصل الآلاف، شكل التاريخ في كل عمود", f"{len(fa_)} عمود", f"{len(fb_)} عمود",
        "same" if not fd and len(fa_) == len(fb_) else "diff", " · ".join(fd[:10]) or ("متطابق" if len(fa_) == len(fb_) else "عدد الأعمدة مختلف"))
    mixed_a = [f"عمود {i + 1}: {x}" for i, x in enumerate(fa_) if "(+" in x or "من غير صفر" in x]
    mixed_b = [f"عمود {i + 1}: {x}" for i, x in enumerate(fb_) if "(+" in x or "من غير صفر" in x]
    pair("العرض", "تنسيق مش ثابت في العمود", "عمود فيه أكتر من تنسيق، أو أرقام من غير صفر قبل العلامة (.000)", "، ".join(mixed_a[:4]) or "سليم", not mixed_a,
         "، ".join(mixed_b[:4]) or "سليم", not mixed_b)
    if A.get("page") or B.get("page"):
        add("العرض", "حجم واتجاه الصفحة", "مقاس الورقة (A4 …) وعرضي / طولي", A.get("page") or "—", B.get("page") or "—",
            "same" if A.get("page") == B.get("page") else "diff", "متطابق" if A.get("page") == B.get("page") else "إعداد الصفحة مختلف")
    if A.get("fonts") or B.get("fonts"):
        setdiff("العرض", "الخطوط", "الخطوط المستخدمة في التقرير (من ملف PDF)", A.get("fonts") or [], B.get("fonts") or [], warn_order=False)
        if rows[-1]["status"] == "diff":
            rows[-1]["status"] = "warn"
    pair("العرض", "كنترولات ظاهرة باسمها", "خانات ظاهرة باسم التصميم (xrLabel…) بدل النص", "، ".join(A.get("controls") or []) or "مفيش", not A.get("controls"),
         "، ".join(B.get("controls") or []) or "مفيش", not B.get("controls"))
    pair("العرض", "قيم غريبة", "null / NaN / #Error / 01/01/0001 / System.… ظاهرة في التقرير", "، ".join(A.get("odd") or []) or "مفيش", not A.get("odd"),
         "، ".join(B.get("odd") or []) or "مفيش", not B.get("odd"))

    # 6) logic
    ra, rb = dict(A.get("rule") or {}), dict(B.get("rule") or {})
    for x, y in ((ra, rb), (rb, ra)):          # the rule holds on one site → judge the other on the same columns
        if x.get("found") and not y.get("found") and (y.get("best") or {}).get("names") == x.get("names"):
            y.update({**y["best"], "found": True})
    pair("المنطق", "قاعدة الرصيد", "الرصيد في كل سطر = اللي قبله + الوارد − الصادر (كل موقع على الداتا بتاعته)", *_rule(ra), *_rule(rb))
    ta, tb = A.get("totals") or {}, B.get("totals") or {}
    pair("المنطق", "قاعدة الإجماليات", "سطر الإجمالي = مجموع السطور اللي فوقه", *_tot(ta), *_tot(tb))
    if A.get("sort") or B.get("sort"):
        so = (A.get("sort") or "—", B.get("sort") or "—")
        st = "same" if so[0] == so[1] else ("info" if "تاريخ واحد" in so or "—" in so else "diff")
        if st == "same" and "مش مترتب" in so[0]:
            st = "both"
        add("المنطق", "ترتيب السطور", "اتجاه الترتيب بالتاريخ", so[0], so[1], st,
            {"same": "نفس الترتيب", "info": "مش كفاية للحكم", "diff": "الترتيب مختلف — غالبًا ORDER BY مختلف في الإجراء المخزن", "both": "مش مترتب في الاتنين"}[st])
    if "stock" in A or "stock" in B:
        pair("المنطق", "آخر رصيد = رصيد المخزن", "آخر رصيد في الكارت = الكمية الفعلية للصنف في المخزن",
             f"{A.get('last_balance')} / {A.get('stock')}", _same(A.get("last_balance"), A.get("stock")) if "stock" in A else None,
             f"{B.get('last_balance')} / {B.get('stock')}", _same(B.get("last_balance"), B.get("stock")) if "stock" in B else None)

    # 7) for info
    ma_, mb2 = (A.get("ms") or 0) / 1000, (B.get("ms") or 0) / 1000
    slow = max(ma_, mb2) > 20 and max(ma_, mb2) > 4 * max(0.5, min(ma_, mb2))
    add("الأداء", "وقت بناء التقرير", "بيتأثر بحجم الداتا — تنبيه لو واحد أبطأ من التاني 4 مرات وأكتر من 20 ثانية", f"{ma_:.1f} ث", f"{mb2:.1f} ث",
        "warn" if slow else "info", "أبطأ بكتير عند " + ("الاختبار" if ma_ > mb2 else "العميل") if slow else "")
    add("الأداء", "عدد الصفحات", "للعلم — الداتا مختلفة", A.get("pages"), B.get("pages"), "info", "")
    add("الأداء", "سطور البيانات", "للعلم — الداتا مختلفة", A.get("rows_n"), B.get("rows_n"), "info", "")
    out["diff_n"], out["warn_n"] = _count(rows)
    return out


def _count(rows):
    return sum(1 for r in rows if r["status"] in ("diff", "both")), sum(1 for r in rows if r["status"] == "warn")


def _enum(fx):
    """a fixed list from the code (0,1,2 … / small codes) rather than a list read from the database"""
    try:
        v = sorted(int(x[0]) for x in fx)
    except ValueError:
        return len(fx) <= 6
    return len(v) <= 12 and v[0] >= -1 and v[-1] <= len(v) + 1


def _ftxt(fx):
    return " / ".join(f"{v}={t}" for v, t in fx[:6])


def _rule(r):
    if not r.get("found"):
        return r.get("why") or "—", None
    return (f"{r['ok']}/{r['rows']} سطر صح" + (f" ({' = '.join(r['names'][:1])} + {r['names'][1]} − {r['names'][2]})" if r.get("names") else "") + (f" — سطور غلط: {', '.join(map(str, r['bad_rows'][:8]))}" if r.get("bad_rows") else "")), not r.get("bad_rows")


def _tot(t):
    if not t.get("found"):
        return "مفيش سطر إجمالي", None
    return (f"{t['checked']} إجمالي اتراجع" + (" — " + " · ".join(t["bad"][:4]) if t.get("bad") else "")), not t.get("bad")


# ------------------------------------------------------------------ all reports
def summary(path, url_a, url_b):
    c = compare(path, url_a, url_b)
    A, B = c["a"] or {}, c["b"] or {}
    return {"ready": c["ready"], "diff_n": c.get("diff_n", 0), "warn_n": c.get("warn_n", 0), "sa": A.get("status"), "sb": B.get("status"),
            "at_a": A.get("at"), "at_b": B.get("at")}


def catalog_rows(url_a, url_b):
    """every report of both menus + the ones configured / captured, with where it exists and the last comparison"""
    d = load_cfg()
    ca, cb = load_catalog(url_a), load_catalog(url_b)
    allr = {}
    for side, cat in (("a", ca), ("b", cb)):
        for c in cat.get("reports") or []:
            r = allr.setdefault(c["path"].lower(), {"path": c["path"], "name": c["name"], "group": c.get("group", ""), "section": c.get("section", ""), "in_a": False, "in_b": False})
            r["in_" + side] = True
            if not r["group"]:
                r["group"] = c.get("group", "")
    for p, rc in d["reports"].items():
        allr.setdefault(p.lower(), {"path": p, "name": rc.get("name") or p, "group": rc.get("group", ""), "section": "", "in_a": None, "in_b": None})
    sel = {x.lower() for x in d["selected"]}
    out = []
    for k, r in allr.items():
        if ca.get("reports") is None:
            r["in_a"] = None
        if cb.get("reports") is None:
            r["in_b"] = None
        r["selected"] = k in sel
        r.update(summary(r["path"], url_a, url_b))
        out.append(r)
    out.sort(key=lambda r: (r["group"] or "ي", r["name"]))
    return out, {"at_a": ca.get("at"), "at_b": cb.get("at"), "n_a": len(ca.get("reports") or []), "n_b": len(cb.get("reports") or [])}


def support_issues(url_a, url_b, name_b=""):
    """differences found by the comparison, for the developer-support screen (one issue per report)"""
    out = []
    if not url_a or not url_b:
        return out
    rows, _ = catalog_rows(url_a, url_b)
    for r in rows:
        if not r["ready"] or not r["diff_n"]:
            continue
        c = compare(r["path"], url_a, url_b)
        bad = [x for x in c["rows"] if x["status"] in ("diff", "both")]
        txt = "\n".join(f"• {x['item']}: {x['detail']} (الاختبار: {x['a']} | العميل: {x['b']})" for x in bad)
        sev = "عالية" if any(x["item"] in ("بناء التقرير", "حقول الاستورد", "قاعدة الرصيد", "قاعدة الإجماليات", "الصفحة بتفتح التقرير") for x in bad) else "متوسطة"
        h = hashlib.md5((r["path"] + txt).encode()).hexdigest()[:10]
        out.append({"id": f"repcmp-{slug(r['path'])}-{h}", "site": site_key(url_b), "url": url_b.rstrip("/") + r["path"], "source": "مقارنة التقارير",
                    "screen": r["name"], "severity": sev, "title": f"تقرير «{r['name']}»: {len(bad)} اختلاف بين موقع الاختبار وموقع العميل",
                    "details": txt, "evidence": f"لقطة الاختبار {r.get('at_a')} · لقطة العميل {r.get('at_b')}", "doc": "",
                    "steps": f"افتح {r['path']} على الموقعين بنفس الفلاتر، أو شاشة «مقارنة التقارير» في الأداة", "found": (r.get("at_b") or "")[:10]})
    return out
