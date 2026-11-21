"""
❤️ صحة العملاء — one number out of 100 per client site, so support calls the client before the client calls.

The score (last 7 days) and what each part weighs:
  التشغيل 35   — uptime from the 15-minute check (100% → 35, 95% or less → 0)
  الأخطاء 20   — different errors caught inside NQ ERP (none → 20, 10 or more → 0)
  الشاشات 20   — screens broken right now by the screens check (none → 20, 5 or more → 0)
  السرعة 10    — average answer time (2 s or less → 10, 8 s or more → 0)
  النسخة 10    — runs the newest version among the clients (yes → 10, older → 0, unknown → 5)
  الشهادة 5    — HTTPS certificate (more than 30 days → 5, 14 or less → 0)
85+ سليم · 70–85 محتاج متابعة · under 70 في خطر — with the reasons (the biggest deductions) and the change from 7 days ago.
Plus: a weekly report of all clients (approved design, e-mailed on the chosen day) and a morning summary on WhatsApp / Telegram.
Settings: data/settings/digest.json · daily scores: data/monitor/health.json
"""
import html
import json
import time
from datetime import datetime, timedelta

from config import paths
from config.storage import load_json, save_json

CFG = paths.settings_file("digest.json")
HIST = paths.DATA_DIR / "monitor" / "health.json"
DEFAULTS = {"morning_on": True, "morning_at": "09:00", "weekly_on": True, "weekly_day": 6, "weekly_at": "08:00", "sent": {}}
WEEK_AR = ["الاتنين", "التلات", "الأربع", "الخميس", "الجمعة", "السبت", "الحد"]
_last = {"t": 0.0}


def load_cfg():
    return {**DEFAULTS, **(load_json(CFG, {}) or {})}


def save_cfg(new):
    c = load_cfg()
    for k in ("morning_on", "morning_at", "weekly_on", "weekly_day", "weekly_at"):
        if k in new:
            c[k] = new[k]
    save_json(CFG, c)
    return c


def _clamp(x):
    return max(0.0, min(1.0, x))


def _vkey(v):
    """'2026.11.21' / '1.4.10' → comparable; build dates sort as text"""
    try:
        return tuple(int(x) for x in str(v).replace("-", ".").split(".") if x.strip())
    except ValueError:
        return (0,)


def score(site_id, newest=None):
    from web import monitor, telemetry
    s = monitor._state().get(site_id) or {}
    since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    days = [v for k, v in (s.get("days") or {}).items() if k >= since]
    n, ok = sum(d["n"] for d in days), sum(d["ok"] for d in days)
    up = 100 * ok / n if n else None
    ms = sum(d["ms"] for d in days) / ok if ok else None
    tel = telemetry._load().get(site_id) or {}
    errs = [e for e in (tel.get("errors") or {}).values() if e.get("last", "")[:10] >= since]
    deep = s.get("deep") or {}
    bad = len(deep.get("problems") or []) if deep and not deep.get("error") else None
    ver = (tel.get("version") or {}).get("version") or (tel.get("version") or {}).get("build")
    ssl = (s.get("last") or {}).get("ssl_days")
    parts = [  # (name, got, max, why-if-low)
        ("التشغيل", 35 * _clamp((up - 95) / 5) if up is not None else 17.5, 35,
         f"النظام كان شغال {up:.1f}% بس من الوقت آخر 7 أيام" if up is not None else "لسه مفيش فحوصات"),
        ("الأخطاء", 20 * _clamp(1 - len(errs) / 10) if tel else 10, 20,
         f"{len(errs)} خطأ مختلف قابل المستخدمين جوه البرنامج ({sum(e['count'] for e in errs)} مرة)" if tel else "البرنامج مش متربوط بالمراقبة من جوه"),
        ("الشاشات", 20 * _clamp(1 - bad / 5) if bad is not None else 10, 20,
         f"{bad} شاشة بايظة دلوقتي" if bad else "الشاشات مش بتتفحص"),
        ("السرعة", 10 * _clamp((8000 - ms) / 6000) if ms else 5, 10, f"متوسط الرد {ms / 1000:.1f} ثانية" if ms else "مفيش قياس سرعة"),
        ("النسخة", (10 if not newest or _vkey(ver) >= _vkey(newest) else 0) if ver else 5, 10,
         f"شغال على نسخة {ver} والأحدث {newest}" if ver else "النسخة مش معروفة"),
        ("الشهادة", (5 if ssl > 30 else 5 * _clamp((ssl - 14) / 16)) if ssl is not None else 5, 5,
         f"شهادة HTTPS فاضلها {ssl} يوم" if ssl is not None else ""),
    ]
    total = round(sum(p[1] for p in parts))
    reasons = [p[3] for p in sorted(parts, key=lambda p: p[1] - p[2]) if p[2] - p[1] >= 2 and p[3]][:3]
    return {"score": total, "label": "سليم" if total >= 85 else "محتاج متابعة" if total >= 70 else "في خطر",
            "level": "ok" if total >= 85 else "warn" if total >= 70 else "bad", "reasons": reasons,
            "parts": [{"name": p[0], "got": round(p[1], 1), "max": p[2]} for p in parts],
            "uptime7": round(up, 2) if up is not None else None, "errors7": len(errs), "bad_screens": bad, "version": ver, "state": s.get("v", "none")}


def _hist():
    try:
        return json.loads(HIST.read_text(encoding="utf-8"))
    except Exception:
        return {}


def all_scores(save=False):
    """every client site, worst first, with the change from 7 days ago"""
    from web import monitor, telemetry
    sites = [p for p in monitor._sites({}) if p.get("kind") == "client"]
    vers = [((telemetry._load().get(p["id"]) or {}).get("version") or {}).get("version") for p in sites]
    newest = max((v for v in vers if v), key=_vkey, default=None)
    h, today = _hist(), datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    old = h.get(week_ago) or {}
    out = []
    for p in sites:
        r = score(p["id"], newest)
        r.update({"id": p["id"], "name": p.get("name"), "url": p.get("base_url"),
                  "change": r["score"] - old[p["id"]] if p["id"] in old else None})
        out.append(r)
    out.sort(key=lambda r: r["score"])
    if save:
        h[today] = {r["id"]: r["score"] for r in out}
        for k in sorted(h)[:-120]:
            del h[k]
        HIST.parent.mkdir(parents=True, exist_ok=True)
        HIST.write_text(json.dumps(h), encoding="utf-8")
    return out


# ------------------------------------------------------------------ the morning summary and the weekly report
def morning_text():
    from web import care, monitor, telemetry
    st, y = monitor._state(), (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    sites = monitor._sites({})
    down = [p.get("name") for p in sites if (st.get(p["id"]) or {}).get("v") == "down"]
    slow = [p.get("name") for p in sites if (st.get(p["id"]) or {}).get("v") == "slow"]
    tel = telemetry._load()
    new_errs = sum(1 for s in tel.values() for e in (s.get("errors") or {}).values() if e.get("first", "")[:10] == y)
    log = [x for s in st.values() for x in s.get("deep_log") or [] if x["at"][:10] == y]
    broke, fixed = sum(len(x["new"]) for x in log), sum(len(x["fixed"]) for x in log)
    risk = [r for r in all_scores() if r["level"] == "bad"]
    c, today = care.load(), datetime.now().date()
    ending = []
    for sid, cl in c["clients"].items():
        try:
            left = (datetime.strptime(cl.get("end", ""), "%Y-%m-%d").date() - today).days
        except ValueError:
            continue
        if cl.get("plan") and 0 <= left <= 30:
            ending.append(f"{next((p.get('name') for p in sites if p['id'] == sid), sid)} ({left} يوم)")
    lines = [f"☀️ صباح الخير — ملخص {datetime.now():%Y-%m-%d}",
             ("🔴 واقع دلوقتي: " + "، ".join(down)) if down else f"🟢 كل المواقع شغالة ({len(sites)})",
             ("🟡 بطيء: " + "، ".join(slow)) if slow else "",
             f"🛰️ امبارح: {new_errs} خطأ جديد من جوه البرنامج" if new_errs else "🛰️ امبارح: مفيش أخطاء جديدة من جوه البرنامج",
             f"🖥️ امبارح: {broke} شاشة باظت · {fixed} اتصلحت" if broke or fixed else "",
             ("❤️ عملاء في خطر: " + "، ".join(f"{r['name']} ({r['score']})" for r in risk)) if risk else "❤️ مفيش عملاء في خطر",
             ("💼 عقود بتخلص: " + "، ".join(ending)) if ending else ""]
    overdue = _overdue_tickets()
    if overdue:
        lines.append(f"⏱️ {len(overdue)} تذكرة متأخرة عن ميعاد الحل في «دعم المطورين»")
    return "\n".join(x for x in lines if x)


def _overdue_tickets():
    try:
        from web import support
        return [i for i in support.collect()[0] if i.get("overdue")]
    except Exception:
        return []


def html_weekly(user="", for_pdf=False):
    from web.monthly_report import report_shell
    e, rows = html.escape, all_scores()
    lvl = {"ok": "ok", "warn": "warn", "bad": "bad"}
    body_rows = "".join(f"""<tr><td class="c">{i}</td><td><b>{e(r['name'] or '')}</b></td>
        <td class="c"><span class="st {lvl[r['level']]}">{r['score']}</span></td><td class="c">{e(r['label'])}</td>
        <td class="c">{'—' if r['change'] is None else f'<span class="st {"ok" if r["change"] > 0 else "bad" if r["change"] < 0 else ""}">' + ('▲ ' if r['change'] > 0 else '▼ ' if r['change'] < 0 else '') + str(abs(r['change'])) + '</span>'}</td>
        <td class="c">{'—' if r['uptime7'] is None else str(r['uptime7']) + '%'}</td><td class="c">{r['errors7']}</td>
        <td class="c">{'—' if r['bad_screens'] is None else r['bad_screens']}</td><td>{e('، '.join(r['reasons'])) or '—'}</td></tr>"""
                        for i, r in enumerate(rows, 1)) or '<tr><td colspan="9" class="c">—</td></tr>'
    risk, warn = sum(r["level"] == "bad" for r in rows), sum(r["level"] == "warn" for r in rows)
    avg = round(sum(r["score"] for r in rows) / len(rows)) if rows else None
    strip = [("الأسبوع", f"{(datetime.now() - timedelta(days=7)):%Y-%m-%d} ← {datetime.now():%Y-%m-%d}"), ("عدد العملاء", len(rows)),
             ("متوسط الصحة", avg if avg is not None else "—"), ("في خطر", risk), ("محتاج متابعة", warn)]
    intro = (f"<b>{risk}</b> عميل في خطر و<b>{warn}</b> محتاج متابعة من <b>{len(rows)}</b>. ابدأ بالعملاء اللي فوق: "
             "كلّمهم أو ابعتلهم المطور قبل ما يشتكوا.") if rows else "لسه مفيش مواقع عملاء في الإعدادات."
    body = f"""<p class="intro">{intro}</p>
  <table><thead><tr><th class="c" style="width:30px">م</th><th>العميل</th><th class="c">الدرجة</th><th class="c">الحالة</th><th class="c">التغيير عن الأسبوع اللي فات</th>
    <th class="c">التشغيل</th><th class="c">أخطاء</th><th class="c">شاشات بايظة</th><th>ليه</th></tr></thead><tbody>{body_rows}</tbody></table>
  <p class="grey" style="margin-top:12px">الدرجة من 100: التشغيل 35 · الأخطاء 20 · الشاشات 20 · السرعة 10 · النسخة 10 · الشهادة 5. 85 أو أكتر سليم · من 70 لـ 85 محتاج متابعة · أقل من 70 في خطر.</p>"""
    return report_shell("تقرير صحة العملاء الأسبوعي", "تقرير صحة العملاء الأسبوعي", "Weekly Client Health Report", user, strip, body, for_pdf,
                        extra_css=" .st.warn { color: #B7791F; } ")


def send_weekly(to=None):
    from config import emailer
    from web.daily_report import html_to_pdf
    out = paths.DATA_DIR / "reports" / "health"
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"client_health_{datetime.now():%Y%m%d}.pdf"
    f.write_bytes(html_to_pdf(html_weekly(for_pdf=True)))
    return emailer.send_file("❤️ تقرير صحة العملاء الأسبوعي", "مرفق ترتيب العملاء حسب صحة أنظمتهم الأسبوع ده، واللي محتاج تتابعه.", f, to=to), f


def auto_tick(now=None):
    """the daily score snapshot, the morning summary at «morning_at», the weekly report on «weekly_day» at «weekly_at»"""
    if time.time() - _last["t"] < 60:
        return
    _last["t"] = time.time()
    try:
        c, t = load_cfg(), datetime.now()
        today, hm, sent = t.strftime("%Y-%m-%d"), t.strftime("%H:%M"), dict(c.get("sent") or {})
        changed = False
        if sent.get("snapshot") != today:
            all_scores(save=True)
            sent["snapshot"], changed = today, True
        if c["morning_on"] and hm >= c["morning_at"] and sent.get("morning") != today:
            sent["morning"], changed = today, True
            from web import monitor
            monitor.broadcast(morning_text())
        if c["weekly_on"] and t.weekday() == int(c["weekly_day"]) and hm >= c["weekly_at"] and sent.get("weekly") != today:
            sent["weekly"], changed = today, True
            try:
                send_weekly()
            except Exception as e:
                print(f"[health] weekly: {e}", flush=True)
        _overdue_alerts()
        if changed:
            save_json(CFG, {**(load_json(CFG, {}) or {}), "sent": sent})
    except Exception as e:
        print(f"[health] {e}", flush=True)


def _overdue_alerts():
    """a ticket past its deadline → one alert (checked at most once an hour)"""
    if time.time() - _last.get("od", 0) < 3600:
        return
    _last["od"] = time.time()
    from web import support
    items = [i for i in support.collect()[0] if i.get("overdue")]
    warned = support._load("support_sla_warned.json", {})
    new = [i for i in items if not warned.get(i["id"])]
    if new:
        from web import monitor
        monitor.broadcast("⏱️ تذاكر عدّت ميعاد الحل\n" + "\n".join(
            f"⛔ {i['title'][:90]} — {i.get('dev') or 'مش متعيّنة لمطور'} · متأخرة {i['late_h']} س" for i in new[:8]))
        for i in new:
            warned[i["id"]] = datetime.now().strftime("%Y-%m-%d %H:%M")
        support._save("support_sla_warned.json", warned)
