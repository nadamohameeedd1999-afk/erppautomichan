"""
🏋️ اختبار الحمل — several users at the same moment on the site's key screens and data requests (GET only = read only).

How the «users» are made: the browser signs in once (the normal login), then every virtual user gets a copy of the sign-in
cookie WITHOUT the ASP.NET session cookie. ASP.NET then gives each one its own session, so their requests really run in
parallel (requests that share one session are answered one after the other — that would measure one user, not five).
If the site needs its session (the copied users land on the login page), the test falls back to the shared session
and says so in the report.

Stages: 1 user (the baseline) → N users × rounds. For each target: p50 / p95 / max, errors, and how much slower it got
under load (the «degradation» factor). Targets = the slowest screens of the last «صحة النظام» + the busiest data requests
of the last «اختبار الـ API» + the home page.
"""
import json
import statistics
import threading
import time
from datetime import datetime
from urllib.parse import urljoin

from loguru import logger

SESSION_COOKIES = ("asp.net_sessionid",)
LOGIN_WORDS = ("/account/login", "/login")


def _pct(vals, q):
    v = sorted(vals)
    return v[min(len(v) - 1, int(len(v) * q))] if v else 0


def targets(base, health_state, api_state, n_screens=6, n_api=4, n_reports=0):
    out = [{"url": urljoin(base + "/", "Home"), "name": "الصفحة الرئيسية", "kind": "شاشة"}]
    names = (health_state or {}).get("names") or {}
    times = (health_state or {}).get("times") or {}
    broken = set((health_state or {}).get("broken") or {})
    for p, _ in sorted(((p, t) for p, t in times.items() if p not in broken and "/report/" not in p.lower()), key=lambda x: -x[1])[:n_screens]:
        out.append({"url": urljoin(base + "/", p.lstrip("/")), "name": names.get(p, p), "kind": "شاشة"})
    # 🗓️ month end: the heaviest reports too (trial balance, statements, payroll…) — the slowest ones first
    for p, _ in sorted(((p, t) for p, t in times.items() if p not in broken and "/report/" in p.lower()), key=lambda x: -x[1])[:n_reports]:
        out.append({"url": urljoin(base + "/", p.lstrip("/")), "name": names.get(p, p), "kind": "تقرير"})
    apis = sorted(((v.get("ms") or 0, v.get("url")) for v in (api_state or {}).values() if isinstance(v, dict) and v.get("url")), reverse=True)
    for _, u in apis[:n_api]:
        out.append({"url": u if u.startswith("http") else urljoin(base + "/", u.lstrip("/")), "name": u.split("?")[0][-60:], "kind": "طلب بيانات"})
    seen, uniq = set(), []
    for t in out:
        if t["url"] not in seen:
            seen.add(t["url"])
            uniq.append(t)
    return uniq


def _session(cookies, keep_session, ua):
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": ua or "Mozilla/5.0 NQ-load", "Accept": "text/html,application/json,*/*"})
    for c in cookies:
        if not keep_session and c["name"].lower() in SESSION_COOKIES:
            continue
        s.cookies.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path") or "/")
    return s


def _hit(s, url, timeout=60):
    t0 = time.time()
    try:
        r = s.get(url, timeout=timeout, allow_redirects=True)
        ms = int((time.time() - t0) * 1000)
        login = any(w in r.url.lower() for w in LOGIN_WORDS)
        bad = r.status_code >= 400 or login
        return {"ms": ms, "s": r.status_code, "bad": bad, "why": "رجع لشاشة الدخول" if login else (f"HTTP {r.status_code}" if bad else "")}
    except Exception as e:
        return {"ms": int((time.time() - t0) * 1000), "s": 0, "bad": True, "why": type(e).__name__}


def run_load(driver, credentials, cfg, result=None):
    from engine.screen_runner import login
    from engine.health import STATE, _site_key, load_state
    from config.settings import BASE_URL, READ_ONLY
    result = result if result is not None else {}
    users, rounds = max(1, min(int(cfg.get("users") or 5), 20)), max(1, min(int(cfg.get("rounds") or 3), 10))
    base = BASE_URL.rstrip("/")
    if READ_ONLY:
        result["detail"] = {"title": "🏋️ اختبار الحمل", "columns": ["الهدف", "النتيجة"],
                            "rows": [{"cells": ["—", "اتخطيت: الموقع متسجل «نظام عميل» — اختبار الحمل على مواقع الاختبار بس "
                                                     "(الإعدادات ← مواقع الاختبار ← نوع الموقع «موقع اختبار»)"], "ok": None}]}
        logger.warning("🏋️ اتخطيت: نظام عميل")
        return result
    login(driver, credentials)
    driver.get(base + "/Home")
    cookies = driver.get_cookies()
    ua = driver.execute_script("return navigator.userAgent")
    try:
        api_state = json.loads((STATE / f"api_{_site_key()}.json").read_text(encoding="utf-8"))
    except Exception:
        api_state = {}
    tg = targets(base, load_state(), api_state, int(cfg.get("screens") or 6), int(cfg.get("apis") or 4), int(cfg.get("reports") or 0))

    # can every user have its own session?
    probe = _hit(_session(cookies, False, ua), tg[0]["url"])
    own = not probe["bad"]
    mode = "جلسة منفصلة لكل مستخدم (متوازي فعلًا)" if own else "جلسة واحدة مشتركة (الموقع محتاج الجلسة — أسوأ حالة)"
    logger.info(f"🏋️ {len(tg)} هدف · {users} مستخدم × {rounds} مرات · {mode}")

    sessions = [_session(cookies, not own, ua) for _ in range(users)]
    for s in sessions:                                    # warm up: each user opens home once (session + cache)
        _hit(s, tg[0]["url"])
    rows, out, fails = [], [], []
    t_all = time.time()
    total_n = total_bad = 0
    for i, t in enumerate(tg, 1):
        solo = [_hit(sessions[0], t["url"])["ms"] for _ in range(2)]
        base_ms = min(solo)
        res, lock = [], threading.Lock()

        def user(s):
            for _ in range(rounds):
                r = _hit(s, t["url"])
                with lock:
                    res.append(r)
        t0 = time.time()
        th = [threading.Thread(target=user, args=(s,)) for s in sessions]
        [x.start() for x in th]
        [x.join() for x in th]
        wall = max(0.001, time.time() - t0)
        ms = [r["ms"] for r in res]
        bad = [r for r in res if r["bad"]]
        p50, p95 = _pct(ms, .5), _pct(ms, .95)
        deg = round(p50 / max(1, base_ms), 1)
        x = {"name": t["name"], "kind": t["kind"], "url": t["url"], "solo": base_ms, "p50": p50, "p95": p95, "max": max(ms) if ms else 0,
             "avg": int(statistics.mean(ms)) if ms else 0, "n": len(res), "bad": len(bad), "why": sorted({b["why"] for b in bad})[:3],
             "rps": round(len(res) / wall, 1), "deg": deg}
        total_n += x["n"]
        total_bad += x["bad"]
        ok = x["bad"] == 0 and p95 <= float(cfg.get("p95_ms") or 8000)
        out.append({**x, "ok": ok})
        rows.append({"cells": [f"{t['kind']}: {t['name']}", f"لوحده {base_ms} ms", f"p50 {p50} · p95 {p95} · أقصى {x['max']} ms",
                               f"×{deg}", f"{x['bad']}/{x['n']}" + (f" ({'، '.join(x['why'])})" if x["why"] else "")], "ok": ok})
        logger.info(f"🏋️ [{i}/{len(tg)}] {t['name']}: p95 {p95} ms · أخطاء {x['bad']}")
        if not ok:
            fails.append(f"{t['name']}: p95 {p95} ms · أخطاء {x['bad']}/{x['n']}")
    secs = round(time.time() - t_all, 1)
    summ = {"at": datetime.now().isoformat(timespec="seconds"), "base_url": base, "users": users, "rounds": rounds, "mode": mode, "own_sessions": own,
            "targets": out, "n": total_n, "bad": total_bad, "secs": secs,
            "p95_all": _pct([t["p95"] for t in out], .5) if out else 0, "worst": max(out, key=lambda t: t["p95"]) if out else None}
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / f"load_{_site_key()}.json").write_text(json.dumps(summ, ensure_ascii=False), encoding="utf-8")
    result["load"] = summ
    result["detail"] = {"title": "🏋️ اختبار الحمل", "columns": ["الهدف", "مستخدم واحد", f"{users} مستخدمين", "التباطؤ", "أخطاء"],
                        "rows": rows, "note": f"{mode} · {users} مستخدم × {rounds} مرات · {total_n} طلب في {secs} ث · GET بس (قراءة)"}
    if fails:
        e = AssertionError(f"اختبار الحمل: {len(fails)} هدف فيه مشكلة\n   " + "\n   ".join(fails[:10]))
        e.partial_result = result
        raise e
    logger.success(f"✅ الحمل: {total_n} طلب، مفيش أخطاء")
    return result
