"""
Runs the advanced tests of engine/checks.py (cycle / report / permission / perf).

  run_check(driver, credentials, cfg)       -> result dict (with "detail": a table for the report page)
                                              raises AssertionError (with .partial_result) when the check fails
  run_check_test(driver, credentials, key)  -> entry used by tests/checks/test_check_<key>.py

The detail table of a queued run is saved to data/runs/checks/<RUN_ID>.json (the queue passes RUN_ID).
"""
import hashlib
import json
import os
import statistics
import time
from datetime import datetime

from config import paths
from utils.logger import logger

DETAILS_DIR = paths.RUNS_DIR / "checks"
SNAP_DIR = paths.STATE_DIR / "report_snapshots"
PERF_FILE = paths.STATE_DIR / "perf_history.json"


def _base():
    from config.settings import BASE_URL
    return BASE_URL.rstrip("/")


def _site_id():
    return hashlib.sha1(_base().encode("utf-8")).hexdigest()[:10]


def _abs(u):
    return u if u.startswith("http") else _base() + "/" + u.lstrip("/")


def _shot(driver, name):
    from pages.base_page import BasePage
    try:
        p = BasePage(driver).take_screenshot(name)
    except Exception:
        return None
    if p:
        try:
            import allure
            allure.attach.file(p, name=name, attachment_type=allure.attachment_type.PNG)
        except Exception:
            pass
    return p


def _fail(result, msg):
    e = AssertionError(msg)
    e.partial_result = result
    raise e


# ================================================================ report
def _snap_file(key):
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    return SNAP_DIR / f"{key}__{_site_id()}.json"


def load_snapshot(key):
    f = _snap_file(key)
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except Exception:
        return {}


def accept_snapshot(key):
    """«اعتمدي الأرقام الجديدة»: the numbers of the last run become the reference"""
    s = load_snapshot(key)
    if not s.get("pending"):
        return False
    s["values"], s["at"] = s["pending"]["values"], s["pending"]["at"]
    s.pop("pending", None)
    _snap_file(key).write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def run_report(driver, credentials, cfg, do_login=True, result=None):
    from engine.screen_runner import ScreenRunner, login, RUN_VARS
    from engine.flows import FlowRunner, ROWS_JS, evaluate_check, to_number, FlowError
    from engine.form_filler import FieldFillError
    result = result if result is not None else {}
    if do_login:
        login(driver, credentials)
    page = ScreenRunner(driver, {"key": cfg["key"], "fields": cfg["fields"], "add_url": cfg["url"]})
    page.vars = page.filler.vars = RUN_VARS
    fr = FlowRunner(page, page.filler)
    driver.get(_abs(cfg["url"]))
    page.wait_for_preloader(timeout=30)
    time.sleep(1)
    logger.info(f"📊 فتحت التقرير: {cfg['url']}")
    try:
        if cfg["fields"]:
            page.filler.fill_all(cfg["fields"])
        if cfg.get("show_button"):
            fr._click({"target": cfg["show_button"], "timeout": 15})
            page.wait_for_preloader(timeout=60)
            time.sleep(1.5)
    except (FieldFillError, FlowError) as e:
        _shot(driver, f"{cfg['key']}_report_check")
        _fail(result, f"مقدرتش أعرض التقرير: {e}")
    rows = 0
    if cfg.get("min_rows"):
        end, info = time.time() + 45, {}
        while time.time() < end:
            info = driver.execute_script(ROWS_JS, None) or {}
            if info.get("rows", 0) >= cfg["min_rows"]:
                break
            time.sleep(0.8)
        rows = info.get("rows", 0)
        if rows < cfg["min_rows"]:
            _shot(driver, f"{cfg['key']}_report_check")
            _fail(result, f"التقرير مظهرش فيه صفوف (المطلوب {cfg['min_rows']} على الأقل)"
                  + (f" — بيقول: «{info.get('empty_text')[:80]}»" if info.get("empty_text") else ""))
    result["rows"] = rows
    result["screenshots"] = [_shot(driver, f"{cfg['key']}_report_check")]
    table, values, problems = [], {}, []
    for v in cfg["values"]:
        try:
            raw = fr._ref(v["ref"])
        except FlowError as e:
            problems.append(f"«{v['name']}»: {e}")
            table.append({"cells": [v["name"], "—", "", "", "مالقيتوش"], "ok": False})
            continue
        try:
            val = round(to_number(raw), 2)
        except ValueError:
            val = raw
        values[v["name"]] = val
    snap = load_snapshot(cfg["key"])
    old = snap.get("values") or {}
    changed = []
    for name, val in values.items():
        prev = old.get(name)
        diff, ok, note = "", True, ""
        if prev is None:
            note = "أول مرة"
        elif isinstance(val, float) and isinstance(prev, (int, float)):
            d = val - prev
            diff = f"{d:+,.2f}" if abs(d) > cfg["tol"] else "0"
            if abs(d) > cfg["tol"]:
                changed.append(f"{name}: {prev:,.2f} ← {val:,.2f}")
                ok, note = (False, "اتغير") if cfg["compare"] == "equal" else (None, "اتغير")
            else:
                note = "زي آخر مرة"
        elif str(prev) != str(val):
            changed.append(f"{name}: «{prev}» ← «{val}»")
            ok, note = (False, "اتغير") if cfg["compare"] == "equal" else (None, "اتغير")
        else:
            note = "زي آخر مرة"
        RUN_VARS[f"{cfg['key']}.{name}"] = val
        fmt = (lambda x: f"{x:,.2f}" if isinstance(x, (int, float)) else (str(x) if x is not None else "—"))
        table.append({"cells": [name, fmt(val), fmt(prev), diff, note], "ok": ok})
    for expr in cfg["asserts"]:
        try:
            ok, detail = evaluate_check(expr, fr._ref, cfg["tol"])
        except Exception as e:
            ok, detail = False, str(e)
        table.append({"cells": ["قاعدة: " + expr, detail, "", "", "✓" if ok else "✗"], "ok": ok})
        if not ok:
            problems.append(f"القاعدة «{expr}» مش متحققة: {detail}")
        logger.info(f"{'✅' if ok else '❌'} {expr}: {detail}")
    result["detail"] = {"title": f"📊 {cfg['name_ar']}", "columns": ["الرقم / القاعدة", "دلوقتي", "آخر مرة", "الفرق", "الحالة"],
                        "rows": table, "note": f"المقارنة: {'لازم يفضل زي ما هو' if cfg['compare'] == 'equal' else ('تنبيه بس' if cfg['compare'] == 'warn' else 'من غير مقارنة')}"}
    result["values"] = values
    now = datetime.now().isoformat(timespec="seconds")
    if cfg["compare"] == "equal" and changed and old:
        snap["pending"] = {"values": values, "at": now}          # keep the reference; «اعتمدي» makes these the new one
        problems.append("الأرقام اتغيرت عن آخر مرة: " + " · ".join(changed))
    else:
        snap = {"values": values, "at": now, "previous": old or None}
    _snap_file(cfg["key"]).write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    if changed and cfg["compare"] == "warn":
        logger.warning("⚠️ الأرقام اتغيرت عن آخر مرة: " + " · ".join(changed))
    if problems:
        _fail(result, "فحص التقرير «" + cfg["name_ar"] + "» فشل:\n   " + "\n   ".join(problems))
    logger.success(f"✅ التقرير «{cfg['name_ar']}» سليم ({len(values)} رقم، {len(cfg['asserts'])} قاعدة)")
    return result


# ================================================================ permission
PAGE_STATE_JS = r"""
var t = ((document.body && document.body.innerText) || '').replace(/\s+/g, ' ').trim();
var st = 0; try { var n = performance.getEntriesByType('navigation')[0]; st = (n && n.responseStatus) || 0; } catch (e) {}
return {url: location.href, text: t.slice(0, 5000), len: t.length, status: st, title: document.title || '',
        table: !!document.querySelector('table'), form: !!document.querySelector('form input:not([type=hidden]), form select')};
"""

MENU_JS = r"""
return Array.prototype.map.call(document.querySelectorAll('a[href]'), function(a){
  var h = a.getAttribute('href') || ''; try { return new URL(h, location.href).pathname.toLowerCase(); } catch (e) { return h.toLowerCase(); } });
"""


def _login_as(driver, user, password):
    from engine import session_cache
    from pages.login_page import LoginPage
    from selenium.common.exceptions import TimeoutException
    old = session_cache.ENABLED
    session_cache.ENABLED = False                 # never reuse / overwrite the admin's saved session
    try:
        page = LoginPage(driver)
        page.load()
        driver.delete_all_cookies()
        page.load()
        try:
            page.login(user, password)
        except TimeoutException:
            raise AssertionError(f"مقدرتش أدخل بالمستخدم «{user}» — اتأكدي من اسم المستخدم وكلمة المرور") from None
    finally:
        session_cache.ENABLED = old


def is_denied(state, extra_texts=()):
    from engine.text_match import normalize as _n
    url = (state.get("url") or "").lower()
    if state.get("status") in (401, 403):
        return f"السيرفر رد {state['status']}"
    if "/login" in url:
        return "رجّعه لشاشة الدخول"
    for w in ("accessdenied", "access-denied", "unauthorized", "forbidden", "notallowed", "nopermission"):
        if w in url.replace("_", "").replace("/", ""):
            return f"اتحول لـ {url.split('/', 3)[-1][:60]}"
    text = _n(state.get("text") or "") + " " + _n(state.get("title") or "")
    for w in list(extra_texts) + DENY():
        nw = _n(w)
        if not nw:
            continue
        if nw.isdigit() and state.get("len", 0) > 400:      # 403 / 401 only on a short error page
            continue
        if nw in text:
            return f"الصفحة بتقول «{w}»"
    return ""


def DENY():
    from engine.checks import DENY_TEXTS
    return DENY_TEXTS


def run_permission(driver, credentials, cfg, result=None):
    from pages.base_page import BasePage
    result = result if result is not None else {}
    _login_as(driver, cfg["username"], cfg["password"])
    logger.success(f"🔐 دخلت بالمستخدم «{cfg['username']}»")
    menu = set()
    if cfg.get("check_menu"):
        try:
            menu = set(driver.execute_script(MENU_JS) or [])
        except Exception:
            menu = set()
    rows, problems, warnings, shots = [], [], [], []
    bp = BasePage(driver)
    for e in cfg["expect"]:
        driver.get(_abs(e["url"]))
        bp.wait_for_preloader(timeout=20)
        time.sleep(1.2)
        try:
            driver.switch_to.alert.accept()
        except Exception:
            pass
        st = driver.execute_script(PAGE_STATE_JS) or {}
        why = is_denied(st, cfg.get("deny_texts") or [])
        server_err = not why and any(w in (st.get("text") or "").lower()[:2000] for w in ("server error", "exception", "runtime error"))
        opened = not why and not server_err
        want = "مسموحة" if e["allowed"] else "ممنوعة"
        got = "اتفتحت" if opened else (f"اتقفلت ({why})" if why else "خطأ في السيرفر")
        ok = opened == e["allowed"] and not server_err
        in_menu = e["url"].lower().split("?")[0] in menu
        note = ""
        if not e["allowed"] and in_menu:
            note = "الرابط لسه ظاهر في القايمة"
            warnings.append(f"«{e['name']}» ممنوعة بس رابطها ظاهر في القايمة الجانبية")
        if not ok:
            shots.append(_shot(driver, f"perm_{cfg['key']}"))
            if e["allowed"]:
                problems.append(f"«{e['name']}» المفروض تفتح للمستخدم ده بس {got}")
            else:
                problems.append(f"🚨 «{e['name']}» مفتوحة للمستخدم «{cfg['username']}» والمفروض تبقى مقفولة")
        rows.append({"cells": [e["name"], e["url"], want, got, note], "ok": ok})
        logger.info(f"{'✅' if ok else '❌'} {e['name']}: المتوقع {want} — {got}")
    try:
        driver.delete_all_cookies()                # sign the limited user out of this browser
    except Exception:
        pass
    result["screenshots"] = [s for s in shots if s]
    result["detail"] = {"title": f"🔐 صلاحيات «{cfg['username']}»", "columns": ["الشاشة", "الرابط", "المتوقع", "اللي حصل", "ملاحظة"],
                        "rows": rows, "note": " · ".join(warnings)}
    for w in warnings:
        logger.warning("⚠️ " + w)
    if problems:
        _fail(result, f"الصلاحيات مش مظبوطة ({len(problems)} من {len(rows)}):\n   " + "\n   ".join(problems))
    logger.success(f"✅ صلاحيات «{cfg['username']}» مظبوطة في {len(rows)} شاشة")
    return result


# ================================================================ perf
NAV_JS = r"""
try { var n = performance.getEntriesByType('navigation')[0];
  return {server: n.responseEnd - n.startTime, dom: n.domContentLoadedEventEnd - n.startTime, load: n.loadEventEnd - n.startTime}; }
catch (e) { return {}; }
"""
BUSY_JS = r"""
function vis(e){ var r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden'; }
var busy = Array.prototype.some.call(document.querySelectorAll('#preloader, .preloader, .loader, .dataTables_processing, .spinner-border, .blockUI'), vis);
return {busy: busy, ready: document.readyState, rows: document.querySelectorAll('table tbody tr').length};
"""


def load_perf():
    try:
        return json.loads(PERF_FILE.read_text(encoding="utf-8")) if PERF_FILE.exists() else {}
    except Exception:
        return {}


def _save_perf(data):
    PERF_FILE.parent.mkdir(parents=True, exist_ok=True)
    PERF_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def time_page(driver, url):
    t0 = time.time()
    driver.get(_abs(url))
    end = time.time() + 60
    while time.time() < end:
        s = driver.execute_script(BUSY_JS) or {}
        if s.get("ready") == "complete" and not s.get("busy"):
            break
        time.sleep(0.15)
    total = time.time() - t0
    nav = driver.execute_script(NAV_JS) or {}
    return round(total, 2), round((nav.get("server") or 0) / 1000, 2)


def perf_pages(cfg):
    pages = list(cfg.get("pages") or [])
    if cfg.get("all_pages"):
        from config.screens_catalog import all_pages
        have = {p["url"] for p in pages}
        for k, p in all_pages().items():
            if p.get("url") and p["url"] not in have:
                pages.append({"url": p["url"], "name": p.get("name_ar") or k})
                have.add(p["url"])
    return pages[:120]


def run_perf(driver, credentials, cfg, result=None):
    from engine.screen_runner import login
    result = result if result is not None else {}
    login(driver, credentials)
    hist = load_perf()
    site = hist.setdefault(_base(), {})
    rows, slow, now = [], [], datetime.now().isoformat(timespec="seconds")
    for p in perf_pages(cfg):
        times, server = [], []
        try:
            for _ in range(cfg["times"]):
                t, sv = time_page(driver, p["url"])
                times.append(t)
                server.append(sv)
        except Exception as e:
            rows.append({"cells": [p["name"], p["url"], "—", "—", "—", f"مافتحتش: {str(e).splitlines()[0][:80]}"], "ok": False})
            slow.append(f"«{p['name']}» مافتحتش")
            continue
        t = round(statistics.median(times), 2)
        sv = round(statistics.median(server), 2)
        past = [x["t"] for x in site.get(p["url"], [])][-cfg["baseline_runs"]:]
        base = round(statistics.median(past), 2) if past else None
        ok, note = True, "أول قياس — هيبقى الأساس" if base is None else "طبيعي"
        if base is not None and t > base * cfg["factor"] and t - base > 0.8:
            ok, note = False, f"أبطأ {t / base:.1f}× من العادي"
        if cfg["max_seconds"] and t > cfg["max_seconds"]:
            ok, note = False, f"أكتر من الحد ({cfg['max_seconds']:g} ث)"
        if not ok:
            slow.append(f"«{p['name']}»: {t:.1f} ث (العادي {base if base is not None else '—'} ث) — {note}")
        site.setdefault(p["url"], []).append({"t": t, "server": sv, "at": now, "name": p["name"]})
        site[p["url"]] = site[p["url"]][-60:]
        rows.append({"cells": [p["name"], p["url"], f"{t:.2f}", f"{sv:.2f}", "—" if base is None else f"{base:.2f}", note], "ok": ok})
        logger.info(f"{'✅' if ok else '🐢'} {p['name']}: {t:.2f} ث (السيرفر {sv:.2f}) — {note}")
    _save_perf(hist)
    result["detail"] = {"title": "⚡ سرعة الشاشات", "columns": ["الشاشة", "الرابط", "وقت الفتح (ث)", "رد السيرفر (ث)", "العادي (ث)", "الحالة"],
                        "rows": rows, "note": f"كل شاشة اتفتحت {cfg['times']} مرة واتاخد الوسط · «العادي» = وسط آخر {cfg['baseline_runs']} مرات"}
    result["slow"] = slow
    if slow and cfg.get("fail_on_slow", True):
        _fail(result, f"{len(slow)} شاشة بقت أبطأ من العادي:\n   " + "\n   ".join(slow))
    if slow:
        logger.warning("🐢 " + " | ".join(slow))
    logger.success(f"✅ قست {len(rows)} شاشة")
    return result


# ================================================================ cycle
def run_cycle(driver, credentials, cfg, result=None):
    from engine import checks
    from engine.screen_runner import run_screen, login, _load_any, RUN_VARS
    from engine.form_filler import FieldFillError
    result = result if result is not None else {}
    RUN_VARS.clear()
    login(driver, credentials)
    rows, n = [], len(cfg["steps"])
    result["detail"] = {"title": f"🔁 {cfg['name_ar']}", "columns": ["#", "الخطوة", "الاختبار", "النتيجة", "المدة (ث)"], "rows": rows}
    for i, st in enumerate(cfg["steps"], 1):
        t0 = time.time()
        logger.info(f"🔁 خطوة {i}/{n}: {st['name']} ({st['key']})")
        try:
            import allure
            ctx = allure.step(f"خطوة {i}: {st['name']}")
        except Exception:
            ctx = None
        try:
            if ctx:
                ctx.__enter__()
            if checks.exists(st["key"]):
                c = checks.load(st["key"])
                if c["type"] != "report":
                    raise AssertionError("جوه الدورة ينفع شاشات وسيناريوهات وفحص تقارير بس")
                r = run_report(driver, credentials, c, do_login=False)
                got = f"{len(r.get('values', {}))} رقم سليم"
            else:
                r = run_screen(driver, credentials, _load_any(st["key"]), save=True, do_login=False)
                got = "اتحفظ" + (f" — رقم {RUN_VARS.get('saved_no')}" if RUN_VARS.get("saved_no") else "")
            rows.append({"cells": [i, st["name"], st["key"], got, round(time.time() - t0, 1)], "ok": True})
            logger.success(f"✅ خطوة {i}/{n} «{st['name']}»: {got}")
        except (AssertionError, FieldFillError, Exception) as e:
            msg = str(e).split("\n  (Session info")[0]
            rows.append({"cells": [i, st["name"], st["key"], msg.splitlines()[0][:160], round(time.time() - t0, 1)], "ok": False})
            if st.get("optional"):
                logger.warning(f"⚠️ خطوة {i} «{st['name']}» فشلت وهي اختيارية — كملت: {msg[:200]}")
                continue
            for j, rest in enumerate(cfg["steps"][i:], i + 1):
                rows.append({"cells": [j, rest["name"], rest["key"], "ما اتشغلتش", ""], "ok": None})
            _fail(result, f"الدورة وقفت عند خطوة {i}/{n} «{st['name']}»:\n   {msg}")
        finally:
            if ctx:
                try:
                    ctx.__exit__(None, None, None)
                except Exception:
                    pass
    result["vars"] = {k: v for k, v in RUN_VARS.items() if isinstance(v, (str, int, float))}
    logger.success(f"✅ الدورة «{cfg['name_ar']}» خلصت كلها ({n} خطوة)")
    return result


# ================================================================ entry points
RUNNERS = {"report": run_report, "permission": run_permission, "perf": run_perf, "cycle": run_cycle}


def run_check(driver, credentials, cfg):
    driver.implicitly_wait(0)
    result = {"key": cfg["key"], "type": cfg["type"], "started_at": datetime.now().isoformat(timespec="seconds")}
    t0 = time.time()
    try:
        RUNNERS[cfg["type"]](driver, credentials, cfg, result=result)
    finally:
        result["seconds"] = round(time.time() - t0, 1)
        save_detail(result)
    return result


def save_detail(result):
    rid = os.getenv("RUN_ID")
    if not rid or not result.get("detail"):
        return
    try:
        DETAILS_DIR.mkdir(parents=True, exist_ok=True)
        (DETAILS_DIR / f"{rid}.json").write_text(json.dumps(result, ensure_ascii=False, default=str), encoding="utf-8")
    except Exception as e:
        logger.debug(f"check detail: {e}")


def load_detail(run_id):
    f = DETAILS_DIR / f"{run_id}.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except Exception:
        return None


def run_check_test(driver, credentials, key):
    from engine import checks
    cfg = checks.load(key)
    icon, label, _ = checks.TYPES[cfg["type"]]
    logger.info(f"▶ {icon} {label}: {cfg['name_ar']} ({key})")
    try:
        import allure
        allure.dynamic.title(cfg["name_ar"])
    except Exception:
        pass
    run_check(driver, credentials, cfg)
