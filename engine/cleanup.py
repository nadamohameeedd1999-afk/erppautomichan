"""
🧹 تنظيف بيانات الاختبار — every record an automatic test saved and could not delete (the delete test failed / was not
chosen, or the numbering test's 2nd record) is written to state/leftovers.json with the way to delete it.
The cleanup check deletes them all on the site it runs on and keeps only the ones that still fail.
"""
import json
from datetime import datetime

from config import paths
from utils.logger import logger

FILE = paths.STATE_DIR / "leftovers.json"


def _base():
    from config.settings import BASE_URL
    return BASE_URL.rstrip("/")


def load_all():
    try:
        return json.loads(FILE.read_text(encoding="utf-8")) if FILE.exists() else []
    except Exception:
        return []


def _save(items):
    FILE.parent.mkdir(parents=True, exist_ok=True)
    FILE.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")


def remember(screen_name, number, delete_plan, why):
    """called by the automatic test when a record it made stays on the site"""
    if not number:
        return
    items = [x for x in load_all() if not (x["site"] == _base() and x["plan"]["list_url"] == delete_plan["list_url"] and str(x["no"]) == str(number))]
    items.append({"site": _base(), "screen": screen_name, "no": str(number), "why": why,
                  "at": datetime.now().isoformat(timespec="seconds"), "plan": {**delete_plan, "target_row": str(number)}})
    _save(items)
    logger.info(f"🧹 اتسجل للتنظيف: «{screen_name}» رقم {number} ({why})")


def forget(index_keys):
    """index_keys: [(site, list_url, no)] removed by hand from the page"""
    keys = {tuple(k) for k in index_keys}
    _save([x for x in load_all() if (x["site"], x["plan"]["list_url"], x["no"]) not in keys])


def run_cleanup(driver, credentials, cfg, result=None):
    from engine.screen_runner import run_screen, login
    result = result if result is not None else {}
    login(driver, credentials)
    items = load_all()
    mine = [x for x in items if x["site"] == _base()]
    rows, left = [], [x for x in items if x["site"] != _base()]
    for x in mine:
        try:
            run_screen(driver, credentials, x["plan"], save=True, do_login=False)
            rows.append({"cells": [x["screen"], x["no"], x["at"][:16].replace("T", " "), "🗑️ اتحذف"], "ok": True})
        except Exception as e:
            msg = str(e).splitlines()[0][:200]
            if "مالقيتش صف" in msg:                     # deleted already (by hand)
                rows.append({"cells": [x["screen"], x["no"], x["at"][:16].replace("T", " "), "مش موجود أصلًا (اتمسح قبل كده)"], "ok": True})
                continue
            rows.append({"cells": [x["screen"], x["no"], x["at"][:16].replace("T", " "), f"❌ مقدرتش أحذفه: {msg}"], "ok": False})
            left.append({**x, "why": f"التنظيف فشل: {msg}"})
    _save(left)
    bad = [r for r in rows if not r["ok"]]
    result["detail"] = {"title": "🧹 تنظيف بيانات الاختبار", "columns": ["الشاشة", "رقم السجل", "اتعمل في", "النتيجة"], "rows": rows,
                        "note": f"{len(mine)} سجل على {_base()} · اتحذف {len(rows) - len(bad)} · فضل {len(bad)}" if mine else "مفيش سجلات اختبار فاضلة على الموقع ده ✅"}
    if bad:
        e = AssertionError(f"التنظيف: {len(bad)} سجل مقدرتش أحذفه — " + " | ".join(f"{r['cells'][0]} {r['cells'][1]}" for r in bad[:10]))
        e.partial_result = result
        raise e
    logger.success(f"✅ {result['detail']['note']}")
    return result
