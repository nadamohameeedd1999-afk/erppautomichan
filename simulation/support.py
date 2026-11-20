"""
🎫 The virtual company's problems of NQ ERP itself → «دعم المطورين» (one list with the tests' own problems).

Only real days on a site (never the simulation), only problems of the system itself (source «erp»), one item per problem
across days (problem_key: the screen + its message with the numbers blanked). You review them there and send them on
(status / ticket / Word / Excel are the dashboard's own); a problem that stopped happening is marked as fixed.
"""
import hashlib
import json
import re
from datetime import datetime, timedelta

from simulation.settings import RUNS
from simulation.sources import problem_key

DAYS = 14
ACT = {"add": "إضافة", "edit": "تعديل", "print": "طباعة", "delete": "حذف", "open": "فتح الشاشة", "review": "مراجعة"}
HIGH = re.compile(r"بيانات غلط|خطأ سيستم|\b5\d\d\b|Exception|Server Error|ميزان|اتسجل|انتهى|غلط في", re.I)


def _severity(c):
    if HIGH.search(f"{c.get('type', '')} {c.get('text', '')}"):
        return "عالية"                                        # wrong numbers or the server failing
    return "منخفضة" if c.get("type") == "بطء" else "متوسطة"


def support_issues(days=DAYS):
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        mem = json.loads((RUNS / "regressions.json").read_text(encoding="utf-8"))
    except Exception:
        mem = {}
    out = {}
    for f in sorted(RUNS.glob("day_*.json")) if RUNS.exists() else []:
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if r.get("mode") == "محاكاة" or str(r.get("date", "")) < since:
            continue
        site = re.sub(r"^https?://", "", str(r.get("site") or "")).strip("/") or "موقع الاختبار"
        for c in r.get("tickets") or []:
            k = problem_key(c.get("screen"), c.get("text"))
            iid = "sim_" + hashlib.sha1(k.encode("utf-8")).hexdigest()[:12]
            it = out.get(iid)
            if not it:
                act = ACT.get(c.get("action") or "add", c.get("action") or "")
                it = out[iid] = {
                    "id": iid, "source": "🏢 الشركة الافتراضية", "site": site, "url": c.get("url") or "", "screen": c.get("screen", ""),
                    "severity": _severity(c), "title": f"{c.get('screen', '')}: {str(c.get('text', ''))[:160]}",
                    "details": f"{c.get('type', '')} — {c.get('text', '')}", "evidence": str(c.get("evidence") or "")[:3000], "doc": "",
                    "steps": "\n".join([f"1. ادخل NQ ERP بمستخدم بنفس صلاحيات «{c.get('name', '')}» ({c.get('job', '')})",
                                        f"2. افتح «{c.get('screen', '')}»" + (f": {c['url']}" if c.get("url") else ""),
                                        f"3. {act} زي اللي في الدليل",
                                        "المتوقع: العملية تتم، أو رسالة واضحة بالسبب"]),
                    "found": r.get("date", ""), "who": set(), "days": set(), "times": 0,
                    "fixed": (mem.get(k) or {}).get("status") == "fixed"}
            it["who"].add(c.get("name", ""))
            it["days"].add(r.get("date", ""))
            it["times"] += 1
            it["last_seen"] = r.get("date", "")
            if c.get("evidence"):
                it["evidence"] = str(c["evidence"])[:3000]     # the latest day's evidence
    for it in out.values():
        it["details"] += f"\nاتكررت {it['times']} مرة في {len(it['days'])} يوم · آخر مرة {it.pop('last_seen', '')} · اتقابل مع: {'، '.join(sorted(it['who']))}"
        it["who"], it["days"] = sorted(it["who"]), sorted(it["days"])
    return list(out.values())
