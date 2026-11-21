"""
🎓 المدرب الذكي ↔ the dashboard — what clients ask the AI trainer shows which screens confuse them; what we know is broken
lets the trainer say «دي مشكلة معروفة وبتتحل» instead of a wrong answer.

  POST /api/trainer/question?key=…   {"question", "screen"?, "site"? (base URL or site id), "user"?, "answered"? true/false}
  GET  /api/trainer/known?key=…      the open problems per screen, in client-safe words, with the expected fix time
The key is made in «من جوه الأنظمة» (admin). Questions are kept 2,000 at most (data/monitor/questions.json).
"""
import json
import re
import secrets
import threading
from collections import Counter
from datetime import datetime, timedelta

from config import paths
from config.storage import load_json, save_json

CFG = paths.settings_file("trainer.json")
FILE = paths.DATA_DIR / "monitor" / "questions.json"
_lock = threading.Lock()


def key(new=False):
    c = load_json(CFG, {}) or {}
    if new or not c.get("key"):
        c["key"] = secrets.token_urlsafe(18)
        save_json(CFG, c)
    return c["key"]


def key_ok(k):
    real = (load_json(CFG, {}) or {}).get("key", "")
    return bool(k and real and secrets.compare_digest(str(k), real))


def _load():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _site_id(v):
    from web import monitor
    v = str(v or "").strip().rstrip("/").lower()
    for p in monitor._sites({}):
        if v and (v == p["id"].lower() or v == (p.get("base_url") or "").rstrip("/").lower() or v in (p.get("base_url") or "").lower()):
            return p["id"]
    return ""


def add(b):
    q = {"at": datetime.now().isoformat(timespec="seconds"), "question": str(b.get("question") or "")[:600].strip(),
         "screen": re.sub(r"^https?://[^/]+", "", str(b.get("screen") or ""))[:120], "site": _site_id(b.get("site")),
         "user": str(b.get("user") or "")[:60], "answered": b.get("answered") is not False}
    if not q["question"]:
        raise ValueError("question is empty")
    with _lock:
        d = _load()[-1999:] + [q]
        FILE.parent.mkdir(parents=True, exist_ok=True)
        FILE.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return q


def summary(site_id="", days=30):
    since = (datetime.now() - timedelta(days=days)).isoformat()
    qs = [q for q in _load() if q["at"] >= since and (not site_id or q["site"] == site_id)]
    by_screen = Counter(q["screen"] or "—" for q in qs)
    open_q = Counter(q["screen"] or "—" for q in qs if not q["answered"])
    return {"total": len(qs), "unanswered": sum(not q["answered"] for q in qs),
            "screens": [{"screen": s, "n": n, "unanswered": open_q.get(s, 0)} for s, n in by_screen.most_common(12)],
            "recent": list(reversed(qs))[:15]}


def known():
    """open dev tickets → per screen, client-safe: no messages, no stacks"""
    from web import support
    cfg = support.sla_cfg()
    out = []
    for i in support.collect()[0]:
        if i["status"] in ("اتصلح", "مش مشكلة"):
            continue
        note = (i.get("ai") or {}).get("client_note") or "فيه مشكلة معروفة في الشاشة دي والفريق بيصلحها"
        out.append({"site": i.get("site", ""), "screen": i.get("screen", ""), "note": note, "status": i["status"],
                    "expected_hours": i.get("left_h") if i.get("left_h") is not None else cfg["hours"].get(i.get("severity"), 72)})
    return {"known": out, "generated": datetime.now().isoformat(timespec="seconds")}
