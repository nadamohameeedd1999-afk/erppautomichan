"""
🆚 مقارنة التقارير — the same DevExpress report (e.g. /Report/ItemCardReport_Polan «كارت صنف تحليلي») on our test site and on
a client's system, with the same scenario (warehouse + item …). The data differ, so what is compared is what the code /
stored procedure decides: parameters, the fields the procedure returns, the report's titles, columns and number formats,
plus rules each site must satisfy on its own data (running balance = previous + in − out, last balance = stock on hand),
controls showing their design name (xrLabel…), parameters without a caption, build time.

Each site is captured by its own read-only run (nothing is saved on the ERP); the page compares the two latest captures.
"""
import base64
import csv
import io
import json
import re
from datetime import datetime

from utils.logger import logger

DEFAULT = {"id": "itemcard", "name": "كارت صنف تحليلي — مخزن + صنف", "report": "/Report/ItemCardReport_Polan",
           "choose": [["WarehouseId", "رقم المخزن"], ["Itemid", "الصنف"]], "sites": {}}


# ------------------------------------------------------------------ scenarios (settings/report_compare.json)
def _file():
    from config import paths
    return paths.SETTINGS_DIR / "report_compare.json"


def site_key(url):
    return re.sub(r"^https?://", "", str(url or "")).strip("/").lower()


def scenarios():
    try:
        d = json.loads(_file().read_text(encoding="utf-8"))
    except Exception:
        d = {}
    sc = d.get("scenarios") or [dict(DEFAULT)]
    return sc


def scenario(sid):
    return next((s for s in scenarios() if s["id"] == sid), None)


def save_scenario(s):
    allx = scenarios()
    allx = [x for x in allx if x["id"] != s["id"]] + [s]
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text(json.dumps({"scenarios": allx}, ensure_ascii=False, indent=1), encoding="utf-8")
    return s


def _snap_file(sid, url):
    from config import paths
    return paths.STATE_DIR / f"repcmp_{re.sub(r'[^a-z0-9_]', '_', sid)}_{re.sub(r'[^a-z0-9]', '_', site_key(url))}.json"


def load_snap(sid, url):
    try:
        return json.loads(_snap_file(sid, url).read_text(encoding="utf-8"))
    except Exception:
        return None


# ------------------------------------------------------------------ capture (one site, read only)
VIEWER = r"""
const done = arguments[arguments.length - 1]; const A = Array.from(arguments).slice(0, -1);
const w = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  let k = null; for (let i = 0; i < 60 && !k; i++) { k = Object.keys(window).find(x => x.startsWith('WebDocumentViewer_')); if (!k) await w(500); }
  if (!k) return {err: 'عارض التقارير (DevExpress) ماظهرش في الصفحة'};
  const v = window[k]; let pm = null; for (let i = 0; i < 40 && !pm; i++) { try { pm = v.GetParametersModel(); } catch (e) {} if (!pm || !pm._parameters) { pm = null; await w(500); } }
  if (!pm) return {err: 'بارامترات التقرير ماتحملتش'};
  const lv = x => { const l = x.lookUpValues; return (Array.isArray(l) ? l : (typeof l === 'function' ? l() : [])) || []; };
  const params = pm._parameters.map(x => { const d = (x.getParameterDescriptor && x.getParameterDescriptor()) || {};
    return {path: x.path, type: x.type, label: d.description || '', visible: d.visible !== false, lookups: lv(x).length}; });
  const lookups = {}; for (const [p] of A[0]) { const x = pm._parameters.find(z => z.path === p); if (x) lookups[p] = lv(x).slice(0, 8000).map(o => [String(o.value), String(o.displayValue ?? o.description ?? o.value)]); }
  return {params, lookups};
})().then(done).catch(e => done({err: String(e)}));
"""

BUILD = r"""
const done = arguments[arguments.length - 1]; const [vals] = Array.from(arguments).slice(0, -1);
const w = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const k = Object.keys(window).find(x => x.startsWith('WebDocumentViewer_')); const v = window[k]; const p = v.GetReportPreview(); const pm = v.GetParametersModel();
  for (const [name, val] of Object.entries(vals)) { pm[name] = name.startsWith('date') ? new Date(val) : (isNaN(+val) ? val : +val); await w(1200); }
  const set = {}; for (const name of Object.keys(vals)) set[name] = pm[name];
  let fault = '', http = 0; const of0 = window.fetch;
  window.fetch = async function (u, o) { const r = await of0.apply(this, arguments);
    try { if (String(u).includes('DXXRDV')) { if (r.status >= 500) http = r.status; const t = await r.clone().text(); if (t && t[0] === '{') { const j = JSON.parse(t); const m = (j.result && j.result.faultMessage) || (j.error && (j.error.message || j.error)); if (m) fault = String(m); } } } catch (e) {}
    return r; };
  const t0 = Date.now(); pm.submit(); await w(1500);
  while (Date.now() - t0 < 120000) { await w(1000); if ((p.documentBuilding === false && p.documentId) || fault) break; }
  window.fetch = of0;
  const ms = Date.now() - t0;
  const pages = (p.pages || []).length;
  if (fault) return {fault, http, set, ms, pages};
  if (!p.documentId) return {err: 'التقرير ماخلصش بناء في دقيقتين', set};
  if (!pages || !p.exportOptionsModel) return {empty: true, set, ms, pages};
  const err = (document.querySelector('.dxrd-toast-message, .dx-toast-message, .dxrd-error-message') || {}).innerText || '';
  const grab = async (fmt) => { let buf = null; const of = window.fetch;
    window.fetch = async function (u, o) { const r = await of.apply(this, arguments); try { if (o && String(o.body).includes('getExportResult')) buf = new Uint8Array(await r.clone().arrayBuffer()); } catch (e) {} return r; };
    const wo = window.open; window.open = () => null;
    try { p.exportDocumentTo(fmt); } catch (e) {}
    const t = Date.now(); while (!buf && Date.now() - t < 60000) await w(700);
    window.fetch = of; window.open = wo; if (!buf) return '';
    let s = ''; for (let i = 0; i < buf.length; i += 8192) s += String.fromCharCode.apply(null, buf.subarray(i, i + 8192)); return btoa(s); };
  const c = p.exportOptionsModel && p.exportOptionsModel.csv; if (c) c.encodingType = 'UTF8';
  const csv = await grab('csv'); const xlsx = await grab('xlsx');
  return {set, ms, pages: (p.pages || []).length, csv, xlsx, err};
})().then(done).catch(e => done({err: String(e)}));
"""


def capture(driver, credentials, cfg, result=None):
    from engine.screen_runner import login
    from config.settings import BASE_URL
    result = result if result is not None else {}
    sc = scenario(cfg.get("scenario") or "itemcard") or dict(DEFAULT)
    login(driver, credentials)
    driver.set_script_timeout(300)
    driver.get(BASE_URL.rstrip("/") + sc["report"])
    meta = driver.execute_async_script(VIEWER, sc["choose"])
    if meta.get("err"):
        raise AssertionError(f"{sc['report']}: {meta['err']}")
    snap = {"site": site_key(BASE_URL), "url": BASE_URL.rstrip("/"), "at": datetime.now().strftime("%Y-%m-%d %H:%M"), "report": sc["report"],
            "params": meta["params"], "lookups": meta["lookups"]}
    chosen = (sc.get("sites") or {}).get(site_key(BASE_URL)) or {}
    missing = [lbl for p, lbl in sc["choose"] if not str(chosen.get(p) or "").strip()]
    if missing:
        snap["status"] = "choose"
        _save(sc, snap)
        result["detail"] = {"title": f"🆚 {sc['name']} — {site_key(BASE_URL)}", "columns": ["البند", "القيمة"],
                            "rows": [{"cells": ["القوائم", "اتقرت من الموقع — اختار " + " و".join(missing) + " من صفحة مقارنة التقارير وشغّل تاني"], "ok": None}],
                            "note": "اتقرت قوائم البارامترات بس"}
        logger.info("🆚 اتقرت قوائم البارامترات — مستني اختيار " + "، ".join(missing))
        return result
    names = {p: dict(snap["lookups"].get(p) or []).get(str(chosen[p]), str(chosen[p])) for p, _ in sc["choose"]}
    logger.info("🆚 بني التقرير: " + " · ".join(f"{p}={names[p]}" for p in names))
    vals = {p: chosen[p] for p, _ in sc["choose"]}
    if sc.get("date_from"):
        vals["dateFrom"] = sc["date_from"]
    b = driver.execute_async_script(BUILD, vals)
    if b.get("fault") or b.get("empty"):
        snap.update({"status": "error" if b.get("fault") else "empty", "chosen": chosen, "chosen_names": names, "ms": b.get("ms"),
                     "fault": b.get("fault") or "", "http": b.get("http") or 0})
        _save(sc, snap)
        msg = (f"التقرير فشل في البناء: {b['fault']}" + (f" (HTTP {b['http']})" if b.get("http") else "")) if b.get("fault") else "التقرير طلع فاضي (من غير صفحات) للاختيار ده"
        result["detail"] = {"title": f"🆚 {sc['name']} — {site_key(BASE_URL)}", "columns": ["البند", "القيمة"],
                            "rows": [{"cells": ["بناء التقرير", msg], "ok": False if b.get("fault") else None}], "note": msg}
        if b.get("fault"):
            raise AssertionError(f"{sc['report']} على {site_key(BASE_URL)}: {msg}")
        return result
    if b.get("err") and not b.get("csv"):
        raise AssertionError(f"{sc['report']}: {b['err']}")
    snap.update({"status": "ok", "chosen": chosen, "chosen_names": names, "ms": b.get("ms"), "pages": b.get("pages"), "viewer_error": b.get("err") or ""})
    snap.update(analyze(b.get("csv") or "", b.get("xlsx") or "", names))
    # stock on hand for the «last balance» rule
    wh, it = chosen.get("WarehouseId"), chosen.get("Itemid")
    if wh and it:
        try:
            q = driver.execute_async_script("""const done = arguments[arguments.length-1]; fetch(`/Helper/ItemQuantityOnSystem?warehouseId=${arguments[0]}&itemId=${arguments[1]}&voucherId=0&date=${encodeURIComponent(new Date().toISOString().slice(0,16))}`, {credentials:'include'}).then(r => r.text()).then(t => { try { done(JSON.parse(t).quantity); } catch (e) { done(null); } }).catch(() => done(null));""", wh, it)
            snap["stock"] = q
        except Exception:
            snap["stock"] = None
    _save(sc, snap)
    f = features_rows(snap)
    result["detail"] = {"title": f"🆚 {sc['name']} — {site_key(BASE_URL)}", "columns": ["البند", "القيمة"], "rows": [{"cells": [a, b], "ok": ok} for a, b, ok in f],
                        "note": f"لقطة التقرير اتحفظت ({snap.get('rows_n', 0)} سطر) — افتح «مقارنة التقارير» علشان تشوف الفرق مع الموقع التاني"}
    result["repcmp"] = {"scenario": sc["id"], "site": snap["site"]}
    return result


def _save(sc, snap):
    f = _snap_file(sc["id"], snap["url"])
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------ analysis of one capture
NUM = re.compile(r"^-?[\d,]*\.?\d+$")
DATE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$|^\d{1,2} [A-Za-z]+ \d{4}$|^\d{4}-\d{2}-\d{2}")


def _num(s):
    s = str(s or "").strip()
    if not s or not NUM.match(s.replace(" ", "")):
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
    if NUM.match(s.replace(" ", "")):
        dec = len(s.split(".")[1]) if "." in s else 0
        return ("آلاف، " if "," in s else "") + f"{dec} عشري" + (" · من غير صفر قبل العلامة" if s.startswith(".") or s.startswith("-.") else "")
    return "نص"


def analyze(csv_b64, xlsx_b64, names):
    out = {"labels": [], "fields": [], "formats": [], "rows_n": 0, "cols_n": 0, "controls": [], "rule": None, "last_balance": None}
    skip = {re.sub(r"\s+", " ", str(v)).strip() for v in (names or {}).values()}
    # CSV = what the user sees (titles + formatted numbers)
    if csv_b64:
        text = base64.b64decode(csv_b64).decode("utf-8-sig", "replace")
        rows = list(csv.reader(io.StringIO(text), delimiter=";"))
        start = next((i for i, r in enumerate(rows) if sum(1 for c in r if _num(c) is not None) >= 4), len(rows))
        labels = []
        for r in rows[:start]:
            for c in r:
                c = re.sub(r"\s+", " ", c).strip().strip(":").strip()
                if not c or c in skip or _num(c) is not None or DATE.match(c) or re.match(r"^\d+/\d+$", c) or c in ("-",):
                    continue
                if any(c.startswith(x) or x.startswith(c) for x in skip if len(x) > 3):
                    continue
                labels.append(c)
        out["labels"] = labels
        out["controls"] = sorted({c for r in rows for c in r if re.match(r"^\s*xr[A-Z][A-Za-z]*\d*\s*$", c)})
        data = [r for r in rows[start:] if sum(1 for c in r if _num(c) is not None) >= 4]
        out["rows_n"] = len(data)
        width = max((len(r) for r in data), default=0)
        out["cols_n"] = sum(1 for j in range(width) if any(j < len(r) and r[j].strip() for r in data))
        fm = []
        for j in range(width):
            sigs = [fmt_sig(r[j]) for r in data if j < len(r) and r[j].strip()]
            if sigs:
                main = max(set(sigs), key=sigs.count)
                other = sorted(set(sigs) - {main})
                fm.append(main + (f" (+ {' / '.join(other)})" if other else ""))
        out["formats"] = fm
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
            out["fields"] = [str(h) for h in grid[0] if h and not re.match(r"^xrTableCell\d+$", str(h)) and not re.match(r"^xr", str(h))]
            body = [r for r in grid[1:] if sum(1 for c in r if isinstance(c, (int, float))) >= 3]
            out["rule"], out["last_balance"] = running_rule(body)
    return out


def running_rule(body):
    """find in / out / balance columns where balance[i] = balance[i-1] + in[i] − out[i]; → (summary, last balance)"""
    if len(body) < 3:
        return {"found": False, "why": "سطور قليلة"}, None
    width = max(len(r) for r in body)
    col = lambda j: [r[j] if j < len(r) and isinstance(r[j], (int, float)) else 0.0 for r in body]
    nums = [j for j in range(width) if sum(1 for r in body if j < len(r) and isinstance(r[j], (int, float))) >= len(body) * 0.8]
    best = None
    for bj in nums:
        B = col(bj)
        if len(set(B)) < 2:
            continue
        for ij in nums:
            if ij == bj:
                continue
            I = col(ij)
            for oj in nums:
                if oj in (ij, bj):
                    continue
                O = col(oj)
                if not any(I) or not any(O):
                    continue
                ok = sum(1 for i in range(1, len(B)) if abs(B[i] - (B[i - 1] + I[i] - O[i])) < 0.0015)
                if not best or ok > best[0]:
                    best = (ok, bj, ij, oj)
    if not best or best[0] < (len(body) - 1) * 0.5:
        return {"found": False, "why": "مالقيتش أعمدة وارد / صادر / رصيد بتمشي على القاعدة"}, None
    ok, bj, ij, oj = best
    bad = []
    B, I, O = col(bj), col(ij), col(oj)
    for i in range(1, len(B)):
        if abs(B[i] - (B[i - 1] + I[i] - O[i])) >= 0.0015:
            bad.append(i + 1)
    return {"found": True, "rows": len(B) - 1, "ok": ok, "bad_rows": bad[:20], "cols": [bj, ij, oj]}, B[-1]


def features_rows(s):
    r = s.get("rule") or {}
    rows = [("البارامترات", f"{len(s.get('params') or [])}", None), ("حقول الاستورد", f"{len(s.get('fields') or [])}", None),
            ("عناوين التقرير", f"{len(s.get('labels') or [])}", None), ("سطور البيانات", f"{s.get('rows_n', 0)}", None),
            ("قاعدة الرصيد", (f"{r.get('ok')}/{r.get('rows')} سطر صح" if r.get("found") else r.get("why", "—")), bool(r.get("found") and not r.get("bad_rows"))),
            ("آخر رصيد / رصيد المخزن", f"{s.get('last_balance')} / {s.get('stock')}", _same(s.get("last_balance"), s.get("stock"))),
            ("كنترولات ظاهرة باسمها", "، ".join(s.get("controls") or []) or "مفيش", not s.get("controls")),
            ("وقت بناء التقرير", f"{(s.get('ms') or 0) / 1000:.1f} ث", None)]
    return rows


def _same(a, b, tol=0.001):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ the comparison
def compare(sid, url_a, url_b):
    A, B = load_snap(sid, url_a), load_snap(sid, url_b)
    done = ("ok", "error", "empty")
    out = {"a": A, "b": B, "rows": [], "ready": bool(A and B and A.get("status") in done and B.get("status") in done)}
    if not out["ready"]:
        return out
    rows = out["rows"]
    bt = lambda s: {"ok": "اتبنى", "error": "فشل: " + str(s.get("fault") or ""), "empty": "فاضي (مفيش صفحات)"}[s["status"]]
    st_build = "same" if A["status"] == B["status"] == "ok" else ("both" if A["status"] == B["status"] == "error" else ("info" if "error" not in (A["status"], B["status"]) else "diff"))
    rows.append({"item": "بناء التقرير", "what": "التقرير بيتبني بالسيناريو ده من غير خطأ من السيرفر / الإجراء المخزن", "a": bt(A), "b": bt(B), "status": st_build,
                 "detail": {"same": "اتبنى في الاتنين", "both": "فشل في الاتنين", "info": "واحد منهم طلع فاضي — اختار صنف عليه حركات في الفترة",
                            "diff": "بيفشل عند " + ("العميل" if B["status"] == "error" else "الاختبار") + " بس — غالبًا الإجراء المخزن أو الاستعلام مختلف"}[st_build]})
    pa0 = [f"{p['path']} ({p['type'].split('.')[-1]}) «{p['label'] or 'من غير اسم'}»" for p in A["params"] if p.get("visible")]
    pb0 = [f"{p['path']} ({p['type'].split('.')[-1]}) «{p['label'] or 'من غير اسم'}»" for p in B["params"] if p.get("visible")]
    if A["status"] != "ok" or B["status"] != "ok":
        oa, ob = [x for x in pa0 if x not in pb0], [x for x in pb0 if x not in pa0]
        rows.append({"item": "بارامترات التقرير", "what": "الفلاتر اللي بتظهر للمستخدم: الاسم والنوع والعنوان", "a": len(pa0), "b": len(pb0),
                     "status": "same" if not oa and not ob else "diff", "detail": "متطابق" if not oa and not ob else " · ".join(x for x in [oa and "في الاختبار بس: " + "، ".join(oa), ob and "في العميل بس: " + "، ".join(ob)] if x)})
        out["diff_n"] = sum(1 for r in rows if r["status"] in ("diff", "both"))
        return out

    def setdiff(name, la, lb, what):
        sa, sb = list(dict.fromkeys(la)), list(dict.fromkeys(lb))
        only_a, only_b = [x for x in sa if x not in sb], [x for x in sb if x not in sa]
        order = (not only_a and not only_b and sa != sb)
        same = not only_a and not only_b and not order
        detail = []
        if only_a:
            detail.append("في الاختبار بس: " + "، ".join(only_a[:15]))
        if only_b:
            detail.append("في العميل بس: " + "، ".join(only_b[:15]))
        if order:
            detail.append("نفس العناصر بس الترتيب مختلف")
        rows.append({"item": name, "what": what, "a": f"{len(sa)}", "b": f"{len(sb)}", "status": "same" if same else "diff", "detail": " · ".join(detail) or "متطابق"})

    pa = [f"{p['path']} ({p['type'].split('.')[-1]}) «{p['label'] or 'من غير اسم'}»" for p in A["params"] if p.get("visible")]
    pb = [f"{p['path']} ({p['type'].split('.')[-1]}) «{p['label'] or 'من غير اسم'}»" for p in B["params"] if p.get("visible")]
    setdiff("بارامترات التقرير", pa, pb, "الفلاتر اللي بتظهر للمستخدم: الاسم والنوع والعنوان")
    setdiff("حقول الاستورد", A.get("fields") or [], B.get("fields") or [], "الأعمدة اللي الإجراء المخزن بيرجّعها")
    setdiff("عناوين التقرير", A.get("labels") or [], B.get("labels") or [], "النصوص الثابتة في رأس التقرير والجدول")
    rows.append({"item": "عدد أعمدة البيانات", "what": "الأعمدة اللي فيها قيم في جدول التقرير", "a": A.get("cols_n"), "b": B.get("cols_n"),
                 "status": "same" if A.get("cols_n") == B.get("cols_n") else "diff", "detail": "متطابق" if A.get("cols_n") == B.get("cols_n") else "عدد الأعمدة مختلف"})
    fa, fb = A.get("formats") or [], B.get("formats") or []
    fd = [f"عمود {i + 1}: «{x}» ↔ «{y}»" for i, (x, y) in enumerate(zip(fa, fb)) if x.split(" (+")[0] != y.split(" (+")[0]]
    rows.append({"item": "تنسيق الأرقام والتواريخ", "what": "عدد العلامات العشرية، فاصل الآلاف، شكل التاريخ في كل عمود", "a": f"{len(fa)} عمود", "b": f"{len(fb)} عمود",
                 "status": "same" if not fd and len(fa) == len(fb) else "diff", "detail": " · ".join(fd[:10]) or ("متطابق" if len(fa) == len(fb) else "عدد الأعمدة مختلف")})
    for name, what, fn in (("قاعدة الرصيد", "الرصيد في كل سطر = اللي قبله + الوارد − الصادر (كل موقع على الداتا بتاعته)", _rule_txt),
                           ("آخر رصيد = رصيد المخزن", "آخر رصيد في الكارت = الكمية الفعلية للصنف في المخزن", _stock_txt),
                           ("كنترولات ظاهرة باسمها", "خانات ظاهرة باسم التصميم (xrLabel…) بدل النص", _ctl_txt)):
        (ta, oka), (tb, okb) = fn(A), fn(B)
        st = "same" if oka and okb else ("diff" if oka != okb else "both")
        rows.append({"item": name, "what": what, "a": ta, "b": tb, "status": st,
                     "detail": {"same": "سليم في الاتنين", "diff": ("مشكلة عند العميل بس" if oka else "مشكلة في الاختبار بس"), "both": "مشكلة في الاتنين"}[st]})
    na = [p["path"] for p in A["params"] if p.get("visible") and not p.get("label")]
    nb = [p["path"] for p in B["params"] if p.get("visible") and not p.get("label")]
    rows.append({"item": "بارامتر من غير عنوان", "what": "فلتر ظاهر للمستخدم باسمه البرمجي", "a": "، ".join(na) or "مفيش", "b": "، ".join(nb) or "مفيش",
                 "status": "same" if not na and not nb else ("both" if na and nb else "diff"), "detail": "سليم" if not na and not nb else "فيه فلتر من غير عنوان"})
    rows.append({"item": "وقت بناء التقرير", "what": "للعلم — بيتأثر بحجم الداتا", "a": f"{(A.get('ms') or 0) / 1000:.1f} ث", "b": f"{(B.get('ms') or 0) / 1000:.1f} ث", "status": "info", "detail": ""})
    rows.append({"item": "سطور البيانات", "what": "للعلم — الداتا مختلفة", "a": A.get("rows_n"), "b": B.get("rows_n"), "status": "info", "detail": ""})
    out["diff_n"] = sum(1 for r in rows if r["status"] in ("diff", "both"))
    return out


def _rule_txt(s):
    r = s.get("rule") or {}
    if not r.get("found"):
        return r.get("why") or "—", False
    return (f"{r['ok']}/{r['rows']} سطر صح" + (f" — سطور غلط: {', '.join(map(str, r['bad_rows'][:8]))}" if r.get("bad_rows") else "")), not r.get("bad_rows")


def _stock_txt(s):
    ok = _same(s.get("last_balance"), s.get("stock"))
    return f"{s.get('last_balance')} / {s.get('stock')}", bool(ok)


def _ctl_txt(s):
    c = s.get("controls") or []
    return ("، ".join(c) if c else "مفيش"), not c
