"""
🔌 اختبار الـ API (+ اختبار حمل اختياري) — no setup, read only.
The endpoints are the data requests the ERP's own screens make (captured by the system-health check while it opens
every screen) + any you add. Only GET requests whose name reads data are called (Get / List / Summary …) — anything
that sounds like it changes data (Save, Delete, Set, Approve …) is skipped, on any site.
For each endpoint: status 200, not sent back to sign-in, valid JSON, response time, and its «contract» (the fields it
returns) compared with the first run: a removed field = a screen or report that will break after an update.
Load test (test sites only): N requests at the same time × rounds on the busiest endpoints -> p50 / p95 / errors.
"""
import json
import re
import time
from datetime import date, datetime
from urllib.parse import urlsplit

from utils.logger import logger

WRITE = {"save", "delete", "remove", "update", "insert", "create", "add", "edit", "post", "posting", "approve", "reject", "cancel",
         "close", "import", "upload", "send", "confirm", "submit", "transfer", "restore", "reset", "recalc", "migrate", "execute",
         "set", "change", "keep", "alive", "logout", "login", "log", "notifications", "notification", "poll", "dial", "online",
         "player", "signal", "track", "lock", "unlock", "generate", "calc", "calculate", "run", "start", "stop", "clear", "move", "copy"}
READ_HINT = re.compile(r"(?i)(get|list|search|lookup|data|load|summary|report|tree|fill|bind|find|select|items|buckets|layout|json)")

FETCH_JS = r"""
const [url, done] = [arguments[0], arguments[arguments.length - 1]];
const t0 = performance.now();
fetch(url, {credentials: 'include', headers: {'X-Requested-With': 'XMLHttpRequest'}}).then(async r => {
  const t = await r.text(); const ms = Math.round(performance.now() - t0);
  let shape = null, json = false, n = null;
  try { const d = JSON.parse(t); json = true;
    const arr = Array.isArray(d) ? d : (d && typeof d === 'object' ? (['rows','data','Data','items','Items','result'].map(k => d[k]).find(Array.isArray) || null) : null);
    n = arr ? arr.length : null;
    const one = arr ? (arr.find(x => x && typeof x === 'object') || null) : d;
    shape = {top: d && !Array.isArray(d) && typeof d === 'object' ? Object.keys(d).slice(0, 60) : [],
             row: one && typeof one === 'object' && !Array.isArray(one) ? Object.keys(one).slice(0, 80) : []};
  } catch (e) {}
  done({s: r.status, ms, kb: Math.round(t.length / 1024), json, n, shape, login: /\/login/i.test(new URL(r.url).pathname),
        err: json ? '' : t.replace(/<script[\s\S]*?<\/script>/gi, ' ').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').slice(0, 160)});
}).catch(e => done({s: 0, ms: Math.round(performance.now() - t0), err: String(e)}));
"""

LOAD_JS = r"""
const [urls, users, rounds, done] = [arguments[0], arguments[1], arguments[2], arguments[arguments.length - 1]];
(async () => {
  const out = [];
  for (const u of urls) {
    const ms = []; let bad = 0; const t0 = performance.now();
    for (let r = 0; r < rounds; r++) {
      await Promise.all(Array.from({length: users}, async () => {
        const a = performance.now();
        try { const x = await fetch(u, {credentials: 'include', headers: {'X-Requested-With': 'XMLHttpRequest'}}); await x.text(); if (!x.ok) bad++; }
        catch (e) { bad++; }
        ms.push(performance.now() - a);
      }));
    }
    ms.sort((a, b) => a - b);
    const q = p => Math.round(ms[Math.min(ms.length - 1, Math.floor(p * ms.length))]);
    out.push({url: u, n: ms.length, bad, p50: q(0.5), p95: q(0.95), max: Math.round(ms[ms.length - 1]),
              rps: Math.round(ms.length / ((performance.now() - t0) / 1000) * 10) / 10});
  }
  done(out);
})();
"""


# known NQ ERP data endpoints (found live) — tested even before the first system-health check
SEEDS = [
    {"url": "/TrialBalanceWithLevelsTree/GETTrialBalanceWithLevelsTree?from=2016-01-01&to=2026-12-31&depId=", "screen": "ميزان المراجعة بالمستويات"},
    {"url": "/CustomerInvoiceAgingN/GetSummary?todate=2026-01-01&UserId=1&ShowDueOnly=2&ViewFullyPaidInvoice=0", "screen": "أعمار ديون العملاء - الفواتير"},
    {"url": "/CustomerInvoiceAgingN/GetData?todate=2026-01-01&UserId=1&ShowDueOnly=2&ViewFullyPaidInvoice=0", "screen": "أعمار ديون العملاء - الفواتير"},
    {"url": "/VendorInvoiceAgingN/GetData?todate=2026-01-01&UserId=1&ShowDueOnly=2&ViewFullyPaidInvoice=0", "screen": "أعمار ديون الموردين - الفواتير"},
    {"url": "/VendorMovementAgingN/GetData?todate=2026-01-01&UserId=1&ShowDueOnly=2&ViewFullyPaidInvoice=0", "screen": "أعمار ديون الموردين - الحركات المالية"},
]


def readable(url):
    """a GET that reads data (never a save / delete / set …)"""
    p = urlsplit(url).path
    words = {w.lower() for w in re.findall(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+", p)}
    return bool(p) and not (words & WRITE) and bool(READ_HINT.search(p))


def _norm(url):
    """same endpoint with other values = one endpoint; dates become today's date"""
    u = url if url.startswith("/") else ("/" + urlsplit(url).path.lstrip("/") + (("?" + urlsplit(url).query) if urlsplit(url).query else ""))
    # only an «up to» date becomes today (a «from» date stays — from=today&to=today would read one day only)
    u = re.sub(r"(?i)([?&](?:to|todate|date_to|dateto|enddate)=)20\d\d-\d\d-\d\d", lambda m: m.group(1) + date.today().isoformat(), u)
    return re.sub(r"([?&])_=\d+", r"\1", u).rstrip("?&")


def endpoints(cfg, health_state=None):
    seen, out = set(), []
    cands = list(cfg.get("endpoints") or []) + (SEEDS if cfg.get("seeds", True) else [])
    if cfg.get("from_health", True) and health_state:
        for m in health_state.get("speed") or []:
            for x in m.get("xhr") or []:
                cands.append({"url": x.get("url"), "screen": m.get("name")})
    for c in cands:
        url, screen = (c.get("url"), c.get("screen")) if isinstance(c, dict) else (c, "")
        if not url:
            continue
        u = _norm(str(url).strip())
        key = urlsplit(u).path.lower()
        if key in seen or not readable(u):
            continue
        seen.add(key)
        out.append({"url": u, "screen": screen or ""})
    return out[: int(cfg.get("limit") or 80)]


def judge(ep, r, base, cfg):
    """-> (ok, text, record) · ok None = warning only"""
    slow = float(cfg.get("max_ms") or 3000)
    rec = {"ms": r.get("ms"), "json": r.get("json"), "top": (r.get("shape") or {}).get("top") or [],
           "row": (r.get("shape") or {}).get("row") or []}
    if r.get("login"):
        return False, "رجّعني لشاشة الدخول (الجلسة / الصلاحية)", None
    if r.get("s") != 200:
        return False, f"HTTP {r.get('s')}: {r.get('err', '')[:120]}", None
    if not r.get("json"):
        if base and base.get("json"):
            return False, f"كان بيرجّع JSON وبقى بيرجّع صفحة: {r.get('err', '')[:120]}", None
        return None, f"مش JSON ({r.get('kb')} KB) — صفحة HTML، اتسجلت كده", rec
    txt = f"{r['ms']} ms · {r.get('kb')} KB" + (f" · {r['n']} صف" if r.get("n") is not None else "")
    if base:
        gone = [k for k in (base.get("row") or []) if k not in rec["row"]] if rec["row"] or r.get("n") else []
        gone += [k for k in (base.get("top") or []) if k not in rec["top"]]
        new = [k for k in rec["row"] + rec["top"] if k not in (base.get("row") or []) + (base.get("top") or [])]
        if gone:
            return False, f"الحقول دي اختفت من الرد: {', '.join(gone[:12])} — أي شاشة/تقرير بيقرأها هيبوظ ({txt})", {**rec, "row": base.get("row"), "top": base.get("top")}
        if new:
            txt += f" · حقول جديدة: {', '.join(new[:8])}"
        b = base.get("ms") or 0
        if b and r["ms"] > max(1000, 2 * b):
            return None, f"أبطأ من العادي: {r['ms']} ms (كان {b} ms) · {txt}", {**rec, "ms": b}
    if r["ms"] > slow:
        return None, f"بطيء: {txt} (الحد {int(slow)} ms)", rec
    return True, txt, rec


def run_api(driver, credentials, cfg, result=None):
    from engine.screen_runner import login
    from engine.health import STATE, _site_key, load_state
    from config.settings import BASE_URL, READ_ONLY
    result = result if result is not None else {}
    login(driver, credentials)
    driver.get(BASE_URL.rstrip("/") + "/Home")
    driver.set_script_timeout(600)
    eps = endpoints(cfg, load_state())
    if not eps:
        raise AssertionError("مفيش endpoints أختبرها — شغّلي «🩺 صحة النظام» مرة (بيلقط طلبات البيانات بتاعة كل شاشة) أو ضيفي روابط في الإعدادات")
    sf = STATE / f"api_{_site_key()}.json"
    try:
        base_all = json.loads(sf.read_text(encoding="utf-8")) if sf.exists() else {}
    except Exception:
        base_all = {}
    rows, fails, new_base, timed = [], [], dict(base_all), []
    for ep in eps:
        u = ep["url"]
        r = driver.execute_async_script(FETCH_JS, u) or {}
        k = urlsplit(u).path.lower()
        ok, txt, rec = judge(ep, r, base_all.get(k), cfg)
        rows.append({"cells": [ep["screen"] or "—", u[:140], txt], "ok": ok})
        if ok is False:
            fails.append(f"{u[:90]}: {txt}")
        if rec:
            new_base[k] = {**(base_all.get(k) or {}), **rec, "url": u}
        if r.get("s") == 200:
            timed.append((r.get("ms") or 0, u))
    STATE.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps(new_base, ensure_ascii=False), encoding="utf-8")

    users, rounds = int(cfg.get("load_users") or 0), int(cfg.get("load_rounds") or 3)
    if users > 0:
        if READ_ONLY:
            rows.append({"cells": ["🏋️ اختبار الحمل", "—", "اتخطيت: ده نظام عميل — اختبار الحمل على مواقع الاختبار بس"], "ok": None})
        else:
            top = [u for _, u in sorted(timed, reverse=True)[: int(cfg.get("load_endpoints") or 5)]]
            users, rounds = max(1, min(users, 50)), max(1, min(rounds, 10))
            logger.info(f"🏋️ اختبار حمل: {users} طلب في نفس اللحظة × {rounds} مرات على {len(top)} endpoint")
            for x in driver.execute_async_script(LOAD_JS, top, users, rounds) or []:
                bad = x["bad"] / max(1, x["n"])
                ok = bad == 0 and x["p95"] <= float(cfg.get("load_p95_ms") or 5000)
                rows.append({"cells": ["🏋️ حمل", x["url"][:140],
                                       f"{users}×{rounds}: p50 {x['p50']} ms · p95 {x['p95']} ms · أقصى {x['max']} ms · {x['rps']} طلب/ث · أخطاء {x['bad']}/{x['n']}"],
                             "ok": ok})
                if not ok:
                    fails.append(f"الحمل على {x['url'][:80]}: p95 {x['p95']} ms · أخطاء {x['bad']}")
            rows.append({"cells": ["🏋️ ملاحظة", "—", "كل الطلبات من نفس المستخدم — ASP.NET بيرد على طلبات نفس الجلسة واحد ورا التاني، "
                                                        "فالرقم ده أسوأ حالة لمستخدم واحد مش لعدد مستخدمين مختلفين"], "ok": None})
    first = not base_all
    result["detail"] = {"title": "🔌 اختبار الـ API", "columns": ["الشاشة", "الطلب", "النتيجة"], "rows": rows,
                        "note": f"{len(eps)} طلب بيانات (GET قراءة بس) · {datetime.now():%Y-%m-%d %H:%M}"
                                + (" · أول مرة: اتسجل شكل كل رد كأساس للمقارنة" if first else "")}
    if fails:
        e = AssertionError(f"اختبار الـ API: {len(fails)} مشكلة\n   " + "\n   ".join(fails[:12]))
        e.partial_result = result
        raise e
    logger.success(f"✅ {len(eps)} طلب بيانات شغالين")
    return result
