"""
🧠 المختبر العنيد — the add test does not give up after one way: like a person, when the save is rejected it changes its
approach and tries again, and stops at the first one that really saves.

  📌 الوصفة الناجحة   the exact values that saved last time on this site (kept per site + screen)
  🙂 الطريقة العادية  the planned fields + smart healing (engine/heal.py)
  📋 نسخ سجل محفوظ    open a record already saved on this screen, read its values, add a new one with the same values
                      (any saved record is a combination the ERP accepts) — only notes / descriptions / dates change
  🔀 اختيارات تانية   other options in the lists (another customer / box / payment way)
  📝 كل الحقول ⇄ الإجباري بس

The verdict:
  ✅ saved — with the way that worked (and that way becomes the recipe)
  ❌ ERP problem — a database / server error (SQL, 500, BEGIN/COMMIT…) shows up: no other way is tried
  📦 missing master data — a list the form needs has no options on this site
  ⚠️ every way was rejected — each attempt and its rejection listed
"""
import hashlib
import json
import re
import time
from datetime import datetime

from config import paths
from utils.logger import logger

RECIPES = paths.STATE_DIR / "recipes"
FREE_TEXT = re.compile(r"ملاحظ|شرح|بيان|وصف|تفاصيل|note|remark|desc|comment|memo|subject|عنوان الرسالة", re.I)
AUTO_NO = re.compile(r"رقم المستند|رقم السند|الرقم|سيريال|serial|docnum|documentnumber|voucherno|\bcode\b|كود|^no$|number$", re.I)


def _key(info):
    from config.settings import BASE_URL, ACTIVITY, BRANCH
    h = hashlib.sha1(f"{BASE_URL}|{ACTIVITY}|{BRANCH}".encode()).hexdigest()[:8]
    return re.sub(r"[^a-zA-Z0-9_]", "_", f"{h}_{info['key']}")[:120]


def load_recipe(info):
    f = RECIPES / f"{_key(info)}.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except Exception:
        return None


def save_recipe(info, way, fields, res, no_flows=False):
    """the values that really saved -> fixed fields for next time"""
    got = {s.get("id"): s for s in (res.get("steps") or []) if s.get("ok") and s.get("id") and not str(s.get("id")).startswith("__")}
    out = []
    for f in fields:
        s = got.get(f["id"])
        if not s or s.get("strategy") in ("upload", "flow") or f["kind"] == "file":
            continue
        val = str(s.get("result") if s.get("result") is not None else "").strip()
        if not val:
            continue
        if f["kind"] in ("select", "select2", "checkbox"):
            out.append({**f, "strategy": "fixed", "value": val, "optional": True, "soft": not f.get("required")})
        elif f["kind"] == "date" or FREE_TEXT.search(f"{f.get('label', '')} {f['id']}") or f.get("strategy") in ("unique", "smart", "today"):
            out.append({**f, "optional": True, "soft": not f.get("required")})          # keep making a fresh value
        else:
            out.append({**f, "strategy": "fixed", "value": val, "optional": True, "soft": not f.get("required")})
    if not out:
        return
    RECIPES.mkdir(parents=True, exist_ok=True)
    (RECIPES / f"{_key(info)}.json").write_text(json.dumps({"way": way, "at": datetime.now().isoformat(timespec="seconds"),
                                                            "screen": info["name"], "fields": out, "no_flows": no_flows}, ensure_ascii=False), encoding="utf-8")
    logger.info(f"📌 اتحفظت «الوصفة الناجحة» لـ «{info['name']}» ({len(out)} حقل) — المرة الجاية هبدأ بيها")


def forget_recipe(info):
    f = RECIPES / f"{_key(info)}.json"
    if f.exists():
        f.unlink()


def read_saved_record(driver, base, ids):
    """open the first saved record of the list (edit / view page) and read its values -> {id: value}"""
    from engine.screen_runner import OPEN_ROW_JS, READ_VALUES_JS, ScreenRunner, _abs
    from engine.operations import _row_action
    driver.get(_abs(base["list_url"]))
    time.sleep(3)
    end = time.time() + 20
    while time.time() < end and not driver.execute_script("return document.querySelectorAll('table tbody tr td').length > 1"):
        time.sleep(0.8)
    url0 = driver.current_url
    hit = driver.execute_script(OPEN_ROW_JS, "") or {}
    if hit.get("href"):
        driver.get(hit["href"])
    elif not hit.get("clicked"):
        try:                                   # the same way the edit test finds the row's edit button
            r = ScreenRunner(driver, {**base, "operation": "edit"})
            h2 = _row_action(r, {**base, "op_button": ""}, "edit", "")
            if h2.get("href"):
                driver.get(h2["href"])
        except Exception as e:
            logger.info(f"📋 مقدرتش أفتح سجل محفوظ: {str(e).splitlines()[0][:120]}")
            return {}
    time.sleep(4)
    if driver.current_url == url0 and not driver.execute_script("return !!document.querySelector('form input, form select')"):
        return {}
    got = driver.execute_script(READ_VALUES_JS, ids) or {}
    time.sleep(2)                                          # Select2 lists on edit pages load late
    got2 = driver.execute_script(READ_VALUES_JS, ids) or {}
    from engine.text_match import is_placeholder
    out = {}
    for k in ids:
        v = got2.get(k) or got.get(k)
        if v is not None and str(v).strip() and not is_placeholder(v):
            out[k] = str(v).strip()
    return out


def copy_fields(planned, values):
    """planned fields + the values of a saved record -> fields that repeat that record"""
    out, used = [], 0
    for f in planned:
        v = values.get(f["id"])
        lab = f"{f.get('label', '')} {f['id']}"
        if v is None or f["kind"] in ("file",) or f.get("strategy") == "keep":
            out.append(f)
            continue
        if f["kind"] == "date" or FREE_TEXT.search(lab):
            out.append(f)                                  # a fresh date / note
        elif f["kind"] in ("select", "select2"):
            out.append({**f, "strategy": "fixed", "value": v})
            used += 1
        elif f["kind"] == "checkbox":
            out.append({**f, "strategy": "fixed", "value": v})
            used += 1
        elif AUTO_NO.search(lab):
            out.append(f)                                  # document numbers / codes must stay unique
        else:
            out.append({**f, "strategy": "fixed", "value": v})
            used += 1
    return out, used


def other_options(planned):
    return [{**f, "strategy": "random", "value": ""} if f["kind"] in ("select", "select2") and f.get("strategy") in ("first", "fixed") else f
            for f in planned]


def verdict(attempts):
    """-> (kind, line) for the final row when nothing saved"""
    from engine.heal import server_error
    from engine.auto_test import missing_data
    for a in attempts:
        se = server_error(a["err"] + " " + " ".join(a.get("tech") or []))
        if se:
            return "erp", "❌ مشكلة في موقع الـ ERP نفسه — " + se
    md = [missing_data(a["err"]) for a in attempts]
    if md and all(md):
        return "data", f"📦 بيانات أساسية ناقصة في الموقع: «{md[0]}» مفيهاش ولا اختيار — عرّفي واحد وشغّلي تاني"
    reasons = {a["reason"] for a in attempts}
    ours = re.compile(r"مفيش رسالة|Exception|ConfigError|وقف في الإجراء|مالقيتش|مش موجود|selector|خطوة|اتملى|كتبنا", re.I)
    if len(reasons) == 1 and attempts and len(attempts) > 1 and not ours.search(attempts[0]["reason"]):
        return "erp", f"❌ كل الطرق ({len(attempts)}) اترفضت بنفس رسالة الـ ERP: «{attempts[0]['reason']}» — غالبًا قاعدة / مشكلة في الـ ERP"
    return "tool", (f"⚠️ جربت {len(attempts)} طرق ومحدش فيهم اتحفظ ومفيش خطأ تقني من الـ ERP — سجّلي الشاشة بإيدك مرة واحدة"
                    " (منشئ الاختبارات ← تسجيل) وهكرر خطواتك")


def add_stubbornly(driver, credentials, info, base, plan_add, read, mode, builder, variant, build_fields):
    """-> (res, ok, err, lines). Tries the ways one by one until a real save."""
    from engine.screen_runner import run_screen, RUN_VARS
    from engine.form_filler import FieldFillError
    from engine.heal import server_error
    ladder = []
    rec = load_recipe(info)
    if rec and rec.get("fields"):
        ladder.append(("📌 الوصفة الناجحة من آخر مرة",
                       lambda: {"__no_flows__": True, "fields": rec["fields"]} if rec.get("no_flows") else rec["fields"]))
    ladder.append(("🙂 الطريقة العادية", lambda: plan_add["fields"]))
    copy_note = {}

    def from_saved():
        all_f, _ = build_fields(read, "all", "first", builder)
        vals = read_saved_record(driver, base, [f["id"] for f in all_f if not f["id"].startswith("css:")])
        flds, used = copy_fields(all_f, vals)
        copy_note["used"] = used
        if used < 2:
            raise LookupError("مالقيتش سجل محفوظ أقرا منه قيم (القايمة فاضية أو صفحة السجل مش بتفتح)")
        return flds
    ladder.append(("📋 نسخ قيم سجل محفوظ", from_saved))
    ladder.append(("🔀 اختيارات تانية في القوايم", lambda: other_options(plan_add["fields"])))
    if plan_add.get("flows") or plan_add.get("before_save"):
        ladder.append(("🧩 من غير خطوات منشئ الشاشات (أصناف تلقائي)",
                       lambda: {"__no_flows__": True, "fields": build_fields(read, "all", "first", None)[0]}))
    other = "required" if mode == "all" else "all"
    ladder.append(("📝 " + ("الإجباري بس" if other == "required" else "كل الحقول"), lambda: build_fields(read, other, "first", builder)[0]))

    attempts, lines, last_res, last_err = [], [], {}, ""
    for i, (name, make) in enumerate(ladder, 1):
        before = RUN_VARS.get("saved_no")
        try:
            fields = make()
        except Exception as e:
            lines.append(f"{i}) {name}: ⏭️ {str(e).splitlines()[0][:150]}")
            continue
        if not (fields["fields"] if isinstance(fields, dict) else fields):
            lines.append(f"{i}) {name}: ⏭️ مفيش حقول للطريقة دي")
            continue
        logger.info(f"🧠 محاولة {i}: {name}")
        cfg = {**plan_add, "fields": fields}
        if isinstance(fields, dict):
            cfg = {**plan_add, "fields": fields["fields"], "flows": [], "before_save": []}
        try:
            res = run_screen(driver, credentials, variant(cfg), save=True, do_login=False)
            ok, err = True, ""
        except (AssertionError, FieldFillError) as e:
            res, ok, err = getattr(e, "partial_result", None) or {}, False, str(e).split("\n  (Session info")[0]
        except Exception as e:
            res, ok, err = {}, False, f"{type(e).__name__}: {str(e).splitlines()[0][:200]}"
        saved_anyway = RUN_VARS.get("saved_no") and RUN_VARS.get("saved_no") != before
        last_res, last_err = res, err
        if ok or saved_anyway:
            extra = f" (نسخت {copy_note['used']} قيمة من سجل محفوظ)" if name.startswith("📋") else ""
            lines.append(f"{i}) {name}: ✅ اتحفظ{extra}")
            if i > 1 or not name.startswith("📌"):
                save_recipe(info, name, fields["fields"] if isinstance(fields, dict) else fields, res, no_flows=isinstance(fields, dict))
            return res, ok, err, lines
        reason = next((x.strip() for x in err.splitlines() if x.strip() and "ما نجح" not in x), err[:150])[:170]
        lines.append(f"{i}) {name}: ❌ {reason}")
        attempts.append({"name": name, "err": err, "reason": reason, "tech": res.get("tech_errors") or []})
        if server_error(err + " " + " ".join(res.get("tech_errors") or [])):
            lines.append("⛔ وقفت المحاولات: ده خطأ تقني من الـ ERP نفسه، تغيير البيانات مش هيحله")
            break
        if name.startswith("📌"):
            forget_recipe(info)                            # the recipe stopped working -> learn a new one
    kind, line = verdict(attempts)
    lines.append(line)
    return last_res, False, (line + "\n" + last_err) if last_err else line, lines
