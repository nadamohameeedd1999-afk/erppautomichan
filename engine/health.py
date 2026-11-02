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
const out = {}; let i = 0;
async function one(p) {
  const t0 = performance.now();
  try {
    const ctl = new AbortController(); const timer = setTimeout(() => ctl.abort(), 45000);
    const r = await fetch(p, {credentials: 'include', signal: ctl.signal}); const html = await r.text(); clearTimeout(timer);
    const login = /\/login/i.test(new URL(r.url).pathname) && !/\/login/i.test(p);
    const body = html.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/gi, ' ');
    const m = body.match(ERR);
    let err = '';
    if (m) { const k = body.indexOf(m[0]); err = body.slice(Math.max(0, k - 40), k + 220).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim(); }
    const title = ((html.match(/<title[^>]*>([\s\S]*?)<\/title>/i) || [])[1] || '').trim().slice(0, 120);
    out[p] = {s: r.status, ms: Math.round(performance.now() - t0), login, err, title, size: html.length};
  } catch (e) { out[p] = {s: 0, ms: Math.round(performance.now() - t0), err: String(e).slice(0, 160)}; }
}
async function w() { while (i < paths.length) { await one(paths[i++]); } }
Promise.all(Array.from({length: workers}, w)).then(() => done(out));
"""


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


def pick(links, cfg):
    skip = [s.lower() for s in (DEFAULT_SKIP + list(cfg.get("skip") or [])) if s]
    out = []
    for l in links:
        p = l["path"].lower()
        if any(s in p for s in skip):
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
        res.update(driver.execute_async_script(FETCH_JS, part, int(cfg.get("workers") or 8)) or {})
        logger.info(f"   … {min(i + 200, len(todo))}/{len(todo)}")
    secs = round(time.time() - t0, 1)

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
    _save_state({"at": now, "base_url": base, "activity": ACTIVITY, "branch": BRANCH, "total": len(todo),
                 "broken": broken, "since": since, "history": hist})

    rows = []
    for tag, lst, ok in (("🆕 باظت من آخر مرة", new, False), ("🔁 لسه بايظة", still, False), ("✅ اتصلحت", fixed, True)):
        for p in lst:
            b = broken.get(p) or before.get(p) or {}
            rows.append({"cells": [tag, b.get("module") or "—", b.get("name") or p, p,
                                   "اشتغلت تاني ✅" if ok else b.get("why", ""), (since.get(p) or "")[:16].replace("T", " ") if not ok else "—"],
                         "ok": ok})
    times = sorted(r.get("ms", 0) for r in res.values() if r.get("s") == 200)
    med = times[len(times) // 2] / 1000 if times else 0
    slowest = sorted(((r.get("ms", 0), p) for p, r in res.items() if r.get("s") == 200), reverse=True)[:5]
    names = {l["path"]: l["name"] for l in todo}
    note = (f"فتحت {len(todo)} شاشة في {secs:.0f} ث · سليمة {len(todo) - len(broken)} · بايظة {len(broken)}"
            f" (🆕 {len(new)} · ✅ اتصلحت {len(fixed)}) · متوسط الفتح {med:.1f} ث")
    if slowest:
        note += "\n🐢 أبطأ شاشات: " + "، ".join(f"{names.get(p, p)} ({ms / 1000:.1f} ث)" for ms, p in slowest)
    if ACTIVITY or BRANCH:
        note += f"\n🏢 {ACTIVITY or 'أول نشاط'} · 📍 {BRANCH or 'أول فرع'}"
    result["detail"] = {"title": "🩺 صحة النظام — كل الشاشات", "columns": ["الحالة", "الموديول", "الشاشة", "الرابط", "السبب", "بايظة من"],
                        "rows": rows, "note": note}
    result["health"] = {"total": len(todo), "broken": len(broken), "new": new, "fixed": fixed}
    logger.info(note)

    if (new or fixed) and prev:                               # first run = the starting point, no alert
        lines = [f"🩺 صحة النظام — {base}" + (f" ({ACTIVITY} / {BRANCH})" if ACTIVITY or BRANCH else "")]
        if new:
            lines.append(f"🆕 {len(new)} شاشة باظت:")
            lines += [f"• {broken[p]['name']} ({p}) — {broken[p]['why'][:90]}" for p in new[:15]]
        if fixed:
            lines.append(f"✅ {len(fixed)} شاشة اتصلحت:")
            lines += [f"• {(before.get(p) or {}).get('name', p)} ({p})" for p in fixed[:15]]
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
