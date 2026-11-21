"""
🚀 الإصدارات — a new NQ ERP version goes to the test site first, then to ONE client, and only then to everybody.

For each version you add (its number as NQ ERP reports it — NqTelemetry: Web.config NqVersion, or the DLL version):
  1. البوابة on the test site, from the moment the test site started running that version:
       ⛔ new server / AJAX errors from inside NQ ERP · screens that broke · an error or screen that came back after being
          fixed · the site down · «جاهزية الإصدار» says متنشرش
       ⏳ not long enough yet (soak hours) or the virtual company hasn't worked a day on it yet
       ✅ otherwise — or approved by hand (admin, with a reason)
  2. الموجات: the pilot clients first; each client is watched for «watch_h» hours from the moment it started the version
     (new errors, outages, broken screens) → سليم / فيه مشكلة → «كمل نزّلها للباقي» or «وقّف».
  Alerts: a client got a version that hasn't passed the gate · a client's watch ended (fine / problem).
A client without NqTelemetry can be marked «نزلت» by hand.
Store: data/settings/releases.json
"""
import re
import secrets
import time
from datetime import datetime, timedelta

from config import paths
from config.storage import load_json, save_json

FILE = paths.settings_file("releases.json")
DEFAULTS = {"soak_h": 4, "watch_h": 24}
_last = {"t": 0.0}


def load():
    c = load_json(FILE, {}) or {}
    return {**DEFAULTS, **{k: c[k] for k in DEFAULTS if k in c}, "releases": c.get("releases") or [], "warned": c.get("warned") or {}}


def _save(c):
    save_json(FILE, c)


def add(version, notes="", pilot=None, test_site=""):
    version = str(version or "").strip()[:40]
    if not version:
        raise ValueError("اكتب رقم النسخة")
    c = load()
    if any(r["version"] == version for r in c["releases"]):
        raise ValueError("النسخة دي متضافة قبل كده")
    r = {"id": secrets.token_hex(4), "version": version, "notes": str(notes or "")[:2000], "pilot": list(pilot or [])[:10],
         "test_site": test_site or _default_test(), "created": datetime.now().strftime("%Y-%m-%d %H:%M"), "manual": {}, "approved": None}
    c["releases"] = (c["releases"] + [r])[-50:]
    _save(c)
    return r


def update(rid, new):
    c = load()
    r = next((x for x in c["releases"] if x["id"] == rid), None)
    if not r:
        raise KeyError(rid)
    for k in ("notes", "pilot", "test_site"):
        if k in new:
            r[k] = new[k]
    if "approve" in new:                                           # a hand approval: who, when, why
        r["approved"] = {"by": new.get("by", ""), "at": datetime.now().strftime("%Y-%m-%d %H:%M"), "why": str(new["approve"])[:300]} if new["approve"] else None
    if "mark" in new:                                              # {"site": id, "at": "..."|""} for a client without NqTelemetry
        m = new["mark"]
        if m.get("at"):
            r["manual"][m["site"]] = m["at"][:16].replace("T", " ")
        else:
            r["manual"].pop(m["site"], None)
    if "delete" in new:
        c["releases"] = [x for x in c["releases"] if x["id"] != rid]
    _save(c)
    return r


def _sites():
    from web import monitor
    return monitor._sites({})


def _default_test():
    return next((p["id"] for p in _sites() if p.get("kind") == "test"), "")


def started_at(site_id, version, release=None):
    """when the site started running this version (NqTelemetry «start»), or the hand mark — None if not yet"""
    if release and release.get("manual", {}).get(site_id):
        return release["manual"][site_id]
    from web import telemetry
    s = telemetry._load().get(site_id) or {}
    hit = [x["at"] for x in s.get("starts") or [] if x.get("version") == version or x.get("build") == version]
    if not hit and (s.get("version") or {}).get("version") == version:
        hit = [(s.get("version") or {}).get("at", "")]
    return min(hit)[:16].replace("T", " ") if hit and hit[0] else None


def ended_at(site_id, version, t0):
    """when the site moved on to another version after t0 (None = still on it)"""
    from web import telemetry
    iso = t0.replace(" ", "T")
    later = [x["at"] for x in (telemetry._load().get(site_id) or {}).get("starts") or []
             if x["at"] > iso and x.get("version") != version and x.get("build") != version]
    return min(later)[:16].replace("T", " ") if later else None


def _since(site_id, t0, t1=None):
    """what went wrong on a site while it ran the version (t0 → t1, or now): new errors inside NQ ERP, outages, screens broken,
    things that came back — a later version's problems are not this one's"""
    from web import monitor, telemetry
    iso, end = t0.replace(" ", "T"), (t1 or "9999").replace(" ", "T")
    inside = lambda t: iso <= (t or "") < end
    tel = telemetry._load().get(site_id) or {}
    errs = [e for e in (tel.get("errors") or {}).values() if inside(e.get("first")) and e["kind"] in ("server", "ajax")]
    js = [e for e in (tel.get("errors") or {}).values() if inside(e.get("first")) and e["kind"] == "js"]
    back = [e for e in (tel.get("errors") or {}).values() if any(inside(x) for x in e.get("regressed") or [])]
    s = monitor._state().get(site_id) or {}
    downs = [i for i in s.get("incidents") or [] if inside(i["at"]) and i["v"] == "down"]
    log = [x for x in s.get("deep_log") or [] if inside(x["at"])]
    broke = sorted({k for x in log for k in x["new"]})
    came_back = sorted({k for x in log for k in x.get("regressed") or []})
    return {"errors": errs, "js": js, "regressed": back, "downs": downs, "broke": broke, "screens_back": came_back,
            "down_now": s.get("v") == "down" and not t1}


def gate(r):
    """the test site's verdict for this version: {"verdict": go|wait|stop|none, "text", "reasons", "facts"}"""
    c, t0 = load(), started_at(r["test_site"], r["version"], r)
    if not t0:
        return {"verdict": "none", "text": "لسه منزلتش على موقع الاختبار", "reasons": ["نزّل النسخة على موقع الاختبار الأول"], "facts": {}, "since": None}
    t1 = ended_at(r["test_site"], r["version"], t0)
    w = _since(r["test_site"], t0, t1)
    stop = []
    if w["errors"]:
        stop.append(f"{len(w['errors'])} خطأ جديد في السيرفر من ساعة ما نزلت: " + "، ".join(e["screen"] for e in w["errors"][:4]))
    if w["broke"]:
        stop.append(f"{len(w['broke'])} شاشة باظت: " + "، ".join(w["broke"][:4]))
    if w["regressed"] or w["screens_back"]:
        stop.append("مشاكل كانت اتصلحت ورجعت: " + "، ".join([e["screen"] for e in w["regressed"]][:3] + w["screens_back"][:3]))
    if w["down_now"]:
        stop.append("موقع الاختبار واقع دلوقتي")
    try:
        from engine import readiness
        base = next((p.get("base_url", "") for p in _sites() if p["id"] == r["test_site"]), "").rstrip("/")
        rd = next((x for x in readiness.all_sites() if (x.get("site") or "").rstrip("/") == base), None)
        if rd and rd.get("verdict") == "no":
            stop.append(f"«جاهزية الإصدار» بتقول متنشرش ({rd.get('score')}/100)")
    except Exception:
        rd = None
    hours = ((datetime.strptime(t1, "%Y-%m-%d %H:%M") if t1 else datetime.now()) - datetime.strptime(t0, "%Y-%m-%d %H:%M")).total_seconds() / 3600
    wait = []
    if hours < c["soak_h"]:
        wait.append(f"نزلت من {hours:.1f} ساعة بس — استنى {c['soak_h']} ساعات على الأقل")
    if not _company_worked_since(t0):
        wait.append("الشركة الافتراضية لسه مشتغلتش يوم على النسخة دي")
    if t1:
        wait = [x for x in wait if "ساعة بس" not in x]                # it ran its course: judged on the hours it had
    facts = {"since": t0, "until": t1, "hours": round(hours, 1), "errors": len(w["errors"]), "js": len(w["js"]), "broke": len(w["broke"]), "downs": len(w["downs"])}
    if stop:
        v = ("stop", "⛔ متنشرش", stop)
    elif r.get("approved"):
        v = ("go", f"✅ اتعتمدت يدوي ({r['approved']['by']}): {r['approved']['why']}", wait)
    elif wait:
        v = ("wait", "⏳ استنى شوية", wait)
    else:
        v = ("go", "✅ ينفع تنزل للعملاء", [])
    return {"verdict": v[0], "text": v[1], "reasons": v[2], "facts": facts, "since": t0}


def _company_worked_since(t0):
    from simulation.settings import RUNS
    day = t0[:10].replace("-", "")
    return any(f.name[4:12] >= day for f in RUNS.glob("day_*.json")) if RUNS.exists() else False


def rollout(r):
    """each client: when it got the version, its watch window, what went wrong → status"""
    c, now, out = load(), datetime.now(), []
    for p in _sites():
        if p.get("kind") != "client":
            continue
        t0 = started_at(p["id"], r["version"], r)
        row = {"id": p["id"], "name": p.get("name"), "pilot": p["id"] in r.get("pilot", []), "since": t0, "manual": p["id"] in r.get("manual", {})}
        if not t0:
            row.update({"status": "pending", "text": "لسه"})
        else:
            t1 = ended_at(p["id"], r["version"], t0)
            w = _since(p["id"], t0, t1)
            end = datetime.strptime(t0, "%Y-%m-%d %H:%M") + timedelta(hours=c["watch_h"])
            row["until"] = t1
            probs = ([f"{len(w['errors'])} خطأ جديد"] if w["errors"] else []) + ([f"وقع {len(w['downs'])} مرة"] if w["downs"] else []) \
                + ([f"{len(w['broke'])} شاشة باظت"] if w["broke"] else []) + (["مشكلة رجعت تاني"] if w["regressed"] or w["screens_back"] else [])
            try:
                from web import telemetry
                dr = telemetry.drift(p["id"], r["test_site"])
                if dr and (dr["n_missing_cols"] or dr["missing_tables"]):          # the update didn't fully reach its database
                    probs.append(f"القاعدة ناقصها {dr['n_missing_cols']} عمود و{len(dr['missing_tables'])} جدول عن موقع الاختبار")
            except Exception:
                pass
            if probs:
                row.update({"status": "problem", "text": "فيه مشكلة: " + "، ".join(probs)})
            elif now < end:
                row.update({"status": "watching", "text": f"تحت المراقبة لحد {end:%m-%d %H:%M}", "left_h": round((end - now).total_seconds() / 3600, 1)})
            else:
                row.update({"status": "ok", "text": f"سليم بعد {c['watch_h']} ساعة"})
        out.append(row)
    return out


def advice(r, g, roll):
    pilots = [x for x in roll if x["pilot"]]
    if g["verdict"] in ("none", "wait", "stop"):
        return {"none": "نزّلها على موقع الاختبار الأول", "wait": "استنى البوابة قبل أي عميل", "stop": "متنزلهاش لأي عميل — صلّح الأول"}[g["verdict"]]
    if any(x["status"] == "problem" for x in roll):
        return "⛔ وقّف التنزيل — فيه عميل ظهرت عنده مشكلة بعد النسخة دي"
    if not pilots:
        return "اختار عميل تجريبي (أو اتنين) ونزّلها عنده الأول"
    if any(x["status"] == "pending" for x in pilots):
        return "نزّلها عند العميل التجريبي: " + "، ".join(x["name"] for x in pilots if x["status"] == "pending")
    if any(x["status"] == "watching" for x in pilots):
        return "استنى لحد ما مراقبة العميل التجريبي تخلص"
    if all(x["status"] != "pending" for x in roll):
        return "✅ النسخة نزلت عند كل العملاء"
    return "✅ العميل التجريبي سليم — كمل نزّلها لباقي العملاء"


def overview():
    c = load()
    out = []
    for r in reversed(c["releases"]):
        g = gate(r)
        roll = rollout(r)
        out.append({**r, "gate": g, "rollout": roll, "advice": advice(r, g, roll)})
    return {"releases": out, "soak_h": c["soak_h"], "watch_h": c["watch_h"],
            "sites": [{"id": p["id"], "name": p.get("name"), "kind": p.get("kind")} for p in _sites()]}


def auto_tick(now=None):
    """every 5 minutes: a client on a version that hasn't passed the gate; a client's watch window ended"""
    if time.time() - _last["t"] < 300:
        return
    _last["t"] = time.time()
    try:
        c = load()
        warned, msgs = dict(c["warned"]), []
        for r in c["releases"][-5:]:
            g, roll = gate(r), rollout(r)
            for x in roll:
                if x["since"] and g["verdict"] != "go" and not warned.get(f"early|{r['id']}|{x['id']}"):
                    warned[f"early|{r['id']}|{x['id']}"] = x["since"]
                    msgs.append(f"⚠️ نسخة {r['version']} نزلت عند {x['name']} قبل ما تعدّي البوابة ({g['text']})")
                if x["status"] in ("ok", "problem") and not warned.get(f"end|{r['id']}|{x['id']}|{x['status']}"):
                    warned[f"end|{r['id']}|{x['id']}|{x['status']}"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    msgs.append(f"{'✅' if x['status'] == 'ok' else '⛔'} نسخة {r['version']} عند {x['name']}: {x['text']}"
                                + (f"\n→ {advice(r, g, roll)}" if x["pilot"] else ""))
        if msgs:
            from web import monitor
            monitor.broadcast("🚀 الإصدارات\n" + "\n".join(msgs[:10]))
            save_json(FILE, {**(load_json(FILE, {}) or {}), "warned": warned})
    except Exception as e:
        print(f"[releases] {e}", flush=True)


def version_ok(v):
    return bool(re.fullmatch(r"[\w.\- ]{1,40}", v or ""))
