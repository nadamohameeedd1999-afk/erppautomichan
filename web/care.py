"""
💼 NQ Care — the monitoring we built, sold as an annual support package.

Each client site gets: a plan (أساسي / متقدم / ذهبي — names, prices, targets and features editable), contract dates, and
  • a status page of its own, no login (/status/<secret>): working now? 90 days of history, uptime, past incidents with
    their duration, planned maintenance, the version it runs. Client-safe wording only: never an error text or a stack.
  • a monthly report in the approved design: uptime vs the plan's target (met / missed), downtime, incidents, screens
    found broken and fixed by our checks, errors caught inside the system, versions installed during the month.
  • contract alerts: 30 days, 7 days and on the day it ends.
Plus a printable offer sheet of the plans for sales meetings.
Settings: data/settings/care.json
"""
import calendar
import html
import secrets
import threading
import time
from datetime import datetime, timedelta

from config import paths
from config.storage import load_json, save_json

FILE = paths.settings_file("care.json")
PLANS = {
    "basic": {"name": "NQ Care أساسي", "price": "", "uptime": 99.0, "response_h": 24,
              "features": ["مراقبة نظامك كل 15 دقيقة على مدار الساعة", "تنبيه فوري لفريقنا لو النظام وقف أو بطّأ",
                           "صفحة حالة خاصة بشركتك تشوف منها حالة النظام في أي وقت", "تقرير شهري بأداء النظام ونسبة التشغيل"]},
    "pro": {"name": "NQ Care متقدم", "price": "", "uptime": 99.5, "response_h": 8,
            "features": ["كل مميزات الباقة الأساسية", "فحص كل شاشات النظام كل 3 ساعات", "رصد أي خطأ يقابل موظفينك لحظة حدوثه",
                         "متابعة إرسال الفواتير الإلكترونية لزاتكا"]},
    "premium": {"name": "NQ Care ذهبي", "price": "", "uptime": 99.8, "response_h": 4,
                "features": ["كل مميزات الباقة المتقدمة", "اختبار كل تحديث على نظام تجريبي قبل ما يوصلك",
                             "مراجعة صحة قاعدة البيانات والنسخ الاحتياطي", "زيارة تدريب لفريقك كل 3 شهور"]},
}
NONE = ""                                                       # a site with no plan: no status page, no report
_last = {"t": 0.0}


def load():
    c = load_json(FILE, {}) or {}
    plans = {k: {**v, **((c.get("plans") or {}).get(k) or {})} for k, v in PLANS.items()}
    return {"plans": plans, "clients": c.get("clients") or {}, "notices": c.get("notices") or [], "warned": c.get("warned") or {}}


def _save(c):
    save_json(FILE, c)


def save_plans(new):
    c = load()
    for k in PLANS:
        if k in (new or {}):
            p = new[k]
            c["plans"][k] = {"name": str(p.get("name") or PLANS[k]["name"])[:60], "price": str(p.get("price") or "")[:40],
                             "uptime": max(90.0, min(100.0, float(p.get("uptime") or PLANS[k]["uptime"]))),
                             "response_h": max(1, min(168, int(p.get("response_h") or PLANS[k]["response_h"]))),
                             "features": [str(x).strip()[:160] for x in (p.get("features") or []) if str(x).strip()][:12]}
    _save(c)
    return c


def save_client(site_id, new):
    c = load()
    cl = c["clients"].setdefault(site_id, {})
    for k in ("plan", "start", "end", "contact", "email", "show_version"):
        if k in new:
            cl[k] = new[k] if k == "show_version" else str(new[k] or "")[:80]
    if cl.get("plan") and cl["plan"] not in PLANS:
        cl["plan"] = NONE
    if cl.get("plan") and not cl.get("token"):
        cl["token"] = secrets.token_urlsafe(16)
    _save(c)
    return cl


def new_token(site_id):
    c = load()
    c["clients"].setdefault(site_id, {})["token"] = secrets.token_urlsafe(16)
    _save(c)
    return c["clients"][site_id]["token"]


def add_notice(site_id, title, start, end, kind="maintenance"):
    c = load()
    n = {"id": secrets.token_hex(4), "site": site_id or "all", "title": str(title)[:200], "start": str(start)[:16], "end": str(end)[:16],
         "kind": kind if kind in ("maintenance", "info") else "info"}
    c["notices"] = (c["notices"] + [n])[-100:]
    _save(c)
    return n


def delete_notice(nid):
    c = load()
    c["notices"] = [n for n in c["notices"] if n["id"] != nid]
    _save(c)


def site_of(token):
    return next((sid for sid, cl in load()["clients"].items() if token and cl.get("token") and cl.get("plan")
                 and secrets.compare_digest(cl["token"], token)), None)


# ------------------------------------------------------------------ numbers
def _site(site_id):
    from web import monitor
    return next((p for p in monitor._sites({}) if p["id"] == site_id), None)


def _mon(site_id):
    from web import monitor
    return monitor._state().get(site_id) or {}


def _every():
    from web import monitor
    return int(monitor.load_config().get("every_min", 15))


def outages(site_id, since="", until="9999"):
    """down periods from the monitor's changes: [{"start", "end" (None = still down), "minutes", "why"}]"""
    out, cur = [], None
    for i in _mon(site_id).get("incidents") or []:
        if i["v"] == "down" and not cur:
            cur = {"start": i["at"], "why": i.get("why", "")}
        elif i["v"] != "down" and cur:
            cur["end"] = i["at"]
            out.append(cur)
            cur = None
    if cur:
        out.append({**cur, "end": None})
    out = [o for o in out if o["start"] < until and (o["end"] or "9999") >= since]
    for o in out:                                                     # minutes inside the period only: Oct 31 23:00 → Nov 1 02:00 is split
        s0 = max(datetime.fromisoformat(o["start"]), datetime.fromisoformat(since)) if since else datetime.fromisoformat(o["start"])
        e0 = datetime.fromisoformat(o["end"]) if o["end"] else datetime.now()
        if until != "9999":
            e0 = min(e0, datetime.fromisoformat(until))
        o["minutes"] = max(1, int((e0 - s0).total_seconds() // 60))
    return out


def days_uptime(site_id, n=90):
    """the last n days: [{"day", "uptime" (None = not checked), "ms"}] oldest first"""
    days, today = _mon(site_id).get("days") or {}, datetime.now().date()
    out = []
    for k in range(n - 1, -1, -1):
        d = (today - timedelta(days=k)).isoformat()
        x = days.get(d)
        out.append({"day": d, "uptime": round(100 * x["ok"] / x["n"], 2) if x and x["n"] else None,
                    "ms": int(x["ms"] / x["ok"]) if x and x["ok"] else None})
    return out


def month_stats(site_id, month):
    """month = 'YYYY-MM' -> uptime vs target, downtime, outages, screens found/fixed, inside errors, versions"""
    y, m = map(int, month.split("-"))
    first, last = f"{month}-01", f"{month}-{calendar.monthrange(y, m)[1]:02d}"
    s, c = _mon(site_id), load()
    cl = c["clients"].get(site_id) or {}
    plan = c["plans"].get(cl.get("plan") or "") or {}
    days = {k: v for k, v in (s.get("days") or {}).items() if first <= k <= last}
    n, ok = sum(d["n"] for d in days.values()), sum(d["ok"] for d in days.values())
    up = round(100 * ok / n, 2) if n else None
    outs = outages(site_id, first, last + "T23:59:59")
    log = [x for x in s.get("deep_log") or [] if first <= x["at"][:10] <= last]
    found, fixed = sorted({k for x in log for k in x["new"]}), sorted({k for x in log for k in x["fixed"]})
    from web import telemetry
    tel = telemetry._load().get(site_id) or {}
    errs = [e for e in (tel.get("errors") or {}).values() if first <= e.get("last", "")[:10] and e.get("first", "")[:10] <= last]
    vers = []
    for st in tel.get("starts") or []:
        if first <= st["at"][:10] <= last and (not vers or vers[-1]["version"] != st.get("version")):
            vers.append({"at": st["at"], "version": st.get("version") or st.get("build") or "—"})
    return {"month": month, "first": first, "last": last, "plan": plan, "client": cl, "checks": n, "uptime": up,
            "target": plan.get("uptime"), "met": None if up is None or not plan else up >= plan["uptime"],
            "down_min": sum(o["minutes"] for o in outs), "outages": outs, "days_checked": len(days),
            "avg_ms": int(sum(d["ms"] for d in days.values()) / ok) if ok else None,
            "found": found, "fixed": fixed, "open_now": [p[0] for p in (s.get("deep") or {}).get("problems") or []],
            "errors": sorted(errs, key=lambda e: -e["count"]), "versions": vers}


def status(site_id):
    """everything the client's status page shows — client-safe: states and durations, never an error text"""
    p, s, c = _site(site_id) or {}, _mon(site_id), load()
    cl = c["clients"].get(site_id) or {}
    plan = c["plans"].get(cl.get("plan") or "") or {}
    now = datetime.now().isoformat(timespec="minutes")
    notices = [n for n in c["notices"] if n["site"] in ("all", site_id) and (n.get("end") or "9999") >= now]
    in_maint = any(n["kind"] == "maintenance" and n["start"] <= now <= (n.get("end") or "9999") for n in notices)
    v = s.get("v") if s.get("hist") else "none"
    deep = s.get("deep") or {}
    from web import telemetry
    tel = telemetry._load().get(site_id) or {}
    d30 = [d for d in days_uptime(site_id, 30) if d["uptime"] is not None]
    return {"name": p.get("name") or site_id, "plan": plan.get("name", ""), "target": plan.get("uptime"),
            "state": "maintenance" if in_maint and v != "up" else v, "since": s.get("since"),
            "checked": (s.get("last") or {}).get("at"), "ms": (s.get("last") or {}).get("ms"),
            "screens": None if not deep or deep.get("error") else {"total": deep.get("screens", 0), "bad": len(deep.get("problems") or []), "at": deep.get("at")},
            "uptime30": round(sum(d["uptime"] for d in d30) / len(d30), 2) if d30 else None,
            "days": days_uptime(site_id, 90), "notices": notices,
            "incidents": [{"start": o["start"], "end": o["end"], "minutes": o["minutes"]} for o in reversed(outages(site_id)[-10:])],
            "version": (tel.get("version") or {}) if cl.get("show_version", True) else {}}


# ------------------------------------------------------------------ printed pages (التصميم المعتمد)
def _hm(minutes):
    h, m = divmod(int(minutes or 0), 60)
    return f"{h} س {m} د" if h else f"{m} د"


def html_monthly(site_id, month, user="", for_pdf=False):
    from web.monthly_report import report_shell, month_label
    d, p, e = month_stats(site_id, month), _site(site_id) or {}, html.escape
    name, label = p.get("name") or site_id, month_label(month)
    up = "—" if d["uptime"] is None else f"{d['uptime']}%"
    met = {True: '<span class="st ok">✓ اتحقق</span>', False: '<span class="st bad">✕ ماتحققش</span>', None: "—"}[d["met"]]
    strip = [("العميل", e(name)), ("الباقة", e(d["plan"].get("name", "—"))), ("الشهر", label), ("نسبة التشغيل", up)]
    if d["target"]:
        strip.append(("هدف التشغيل", f"{d['target']}% — {met}"))
    strip += [("وقت التوقف", _hm(d["down_min"])), ("مشاكل اتلقت", len(d["found"]) + len(d["errors"])), ("اتصلحت", len(d["fixed"]))]
    if d["checks"]:
        intro = (f"راقبنا نظامك <b>{d['checks']:,}</b> مرة خلال <b>{label}</b> (كل {_every()} دقيقة على مدار الساعة)، والنظام كان شغال "
                 f"<b>{up}</b> من الوقت" + (f" مقابل هدف <b>{d['target']}%</b> في باقتك — <b>{'اتحقق الهدف ✓' if d['met'] else 'الهدف ماتحققش'}</b>" if d["target"] else "")
                 + f". إجمالي وقت التوقف <b>{_hm(d['down_min'])}</b> في <b>{len(d['outages'])}</b> مرة."
                 + (f" فحوصاتنا لقت <b>{len(d['found'])}</b> شاشة فيها مشكلة واتصلّح منها <b>{len(d['fixed'])}</b>." if d["found"] or d["fixed"] else "")
                 + (f" ورصدنا <b>{len(d['errors'])}</b> خطأ قابل المستخدمين جوه النظام وبلّغنا بيهم فريق التطوير." if d["errors"] else ""))
    else:
        intro = f"لسه مفيش فحوصات متسجلة لنظامك في {label}."
    outs = "".join(f"""<tr><td class="c">{i}</td><td class="c ltr">{o['start'][:16].replace('T', ' ')}</td>
        <td class="c ltr">{(o['end'] or 'لسه')[:16].replace('T', ' ')}</td><td class="c">{_hm(o['minutes'])}</td></tr>""" for i, o in enumerate(d["outages"], 1))
    scr = "".join(f"""<tr><td class="c">{i}</td><td class="ltr">{e(k)}</td><td class="c"><span class="st {'ok' if k in d['fixed'] else 'bad'}">
        {'اتصلحت' if k in d['fixed'] else 'جاري الحل'}</span></td></tr>""" for i, k in enumerate(sorted(set(d["found"]) | set(d["fixed"])), 1))
    K = {"server": "خطأ في السيرفر", "ajax": "عملية رجعت خطأ", "js": "خطأ في الصفحة"}
    errs = "".join(f"""<tr><td class="c">{i}</td><td class="ltr">{e(x['screen'])}</td><td>{K.get(x['kind'], '')}</td><td class="c">{x['count']}</td>
        <td class="c">{len(x.get('users') or [])}</td><td class="c ltr">{x['first'][:10]}</td><td class="c ltr">{x['last'][:10]}</td></tr>""" for i, x in enumerate(d["errors"][:25], 1))
    vers = "".join(f"""<tr><td class="c">{i}</td><td class="c ltr">{v['at'][:16].replace('T', ' ')}</td><td class="c ltr">{e(v['version'])}</td></tr>""" for i, v in enumerate(d["versions"], 1))

    def tbl(title, head, rows):
        return f'<h3>{title}</h3><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>' if rows else ""
    body = f"""<p class="intro">{intro}</p>
  {tbl('مرات توقف النظام', '<th class="c" style="width:30px">م</th><th class="c">من</th><th class="c">لحد</th><th class="c">المدة</th>', outs)}
  {tbl('شاشات لقتها فحوصاتنا فيها مشكلة', '<th class="c" style="width:30px">م</th><th>الشاشة</th><th class="c">الحالة</th>', scr)}
  {tbl('أخطاء قابلت المستخدمين جوه النظام', '<th class="c" style="width:30px">م</th><th>الشاشة</th><th>النوع</th><th class="c">عدد المرات</th><th class="c">عدد المستخدمين</th><th class="c">أول مرة</th><th class="c">آخر مرة</th>', errs)}
  {tbl('تحديثات النظام خلال الشهر', '<th class="c" style="width:30px">م</th><th class="c">التاريخ</th><th class="c">النسخة</th>', vers)}
  <p class="grey" style="margin-top:14px">نسبة التشغيل محسوبة من فحص تلقائي كل {_every()} دقيقة؛ أي فحص فشل محسوب وقت توقف. ممكن تتابع حالة نظامك لحظة بلحظة من صفحة الحالة الخاصة بشركتك.</p>"""
    return report_shell(f"تقرير NQ Care — {e(name)} — {label}", "تقرير خدمة NQ Care الشهري", "NQ Care Monthly Service Report", user, strip, body, for_pdf)


def html_offer(user="", for_pdf=False):
    """the plans side by side, for a sales meeting (approved design)"""
    from web.monthly_report import report_shell
    plans, e = load()["plans"], html.escape
    cols = list(plans.values())
    head = '<th style="width:26%">البند</th>' + "".join(f'<th class="c">{e(p["name"])}</th>' for p in cols)
    rows = [("السعر السنوي", [e(p["price"]) or "—" for p in cols]), ("هدف تشغيل النظام", [f"{p['uptime']}%" for p in cols]),
            ("وقت الاستجابة للمشكلة", [f"خلال {p['response_h']} ساعة" for p in cols])]
    feats = []
    for p in cols:
        for f in p["features"]:
            if f not in feats and not f.startswith("كل مميزات"):
                feats.append(f)
    body_rows = "".join(f'<tr><td><b>{k}</b></td>' + "".join(f'<td class="c">{v}</td>' for v in vals) + "</tr>" for k, vals in rows)
    for f in feats:
        have = []
        for i, p in enumerate(cols):                                  # a plan has what it lists, plus everything of the plans before it
            have.append(any(f in q["features"] for q in cols[:i + 1]))
        body_rows += f'<tr><td>{e(f)}</td>' + "".join(f'<td class="c"><span class="st {"ok" if h else "no"}">{"✓" if h else "—"}</span></td>' for h in have) + "</tr>"
    body = f"""<p class="intro">مع NQ Care فريقنا بيعرف أي مشكلة في نظامك قبل ما تكلمنا: بنراقب النظام على مدار الساعة، وبنفحص الشاشات، وبنرصد أي خطأ يقابل موظفينك
    لحظة حدوثه، وبتوصلك كل شهر تقرير بأداء النظام، ومعاك صفحة حالة خاصة بشركتك تفتحها في أي وقت.</p>
  <table><thead><tr>{head}</tr></thead><tbody>{body_rows}</tbody></table>"""
    return report_shell("باقات NQ Care", "باقات خدمة NQ Care", "NQ Care Support Plans", user, [], body, for_pdf,
                        extra_css=" .st.no { color: #A3AEAD; font-weight: normal; } ")      # not in this plan ≠ bad: grey, not red


# ------------------------------------------------------------------ the admin page and the contracts
def overview():
    from web import monitor
    c, today, month = load(), datetime.now().date(), datetime.now().strftime("%Y-%m")
    rows = []
    for p in monitor._sites({}):
        cl = c["clients"].get(p["id"]) or {}
        st = month_stats(p["id"], month) if cl.get("plan") else None
        left = None
        if cl.get("end"):
            try:
                left = (datetime.strptime(cl["end"], "%Y-%m-%d").date() - today).days
            except ValueError:
                pass
        rows.append({"id": p["id"], "name": p.get("name"), "kind": p.get("kind", ""), "plan": cl.get("plan", ""), "start": cl.get("start", ""),
                     "end": cl.get("end", ""), "contact": cl.get("contact", ""), "email": cl.get("email", ""), "days_left": left, "token": cl.get("token") if cl.get("plan") else "",
                     "show_version": cl.get("show_version", True),
                     "month": {k: st[k] for k in ("uptime", "target", "met", "down_min", "checks")} if st else None})
    return {"plans": c["plans"], "clients": rows, "notices": c["notices"], "month": month}


def send_report(site_id, month, to=None, user=""):
    """the month's PDF by e-mail (to the client's address in NQ Care, or `to`) -> (ok, file)"""
    from config import emailer
    from web.daily_report import html_to_pdf
    from web.monthly_report import month_label
    name = (_site(site_id) or {}).get("name") or site_id
    out = paths.DATA_DIR / "reports" / "care"
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"nq_care_{site_id}_{month}.pdf"
    f.write_bytes(html_to_pdf(html_monthly(site_id, month, user, for_pdf=True)))
    to = to or (load()["clients"].get(site_id) or {}).get("email")
    ok = emailer.send_file(f"تقرير NQ Care — {name} — {month_label(month)}",
                           f"مرفق تقرير خدمة NQ Care لنظامكم عن شهر {month_label(month)}: نسبة تشغيل النظام، ومرات التوقف، "
                           "والمشاكل اللي فحوصاتنا لقتها واتصلحت.", f, to=to or None)
    return ok, f


def auto_tick(now=None):
    """once an hour: contracts ending in 30 days, 7 days, today → one alert each; on the 1st, last month's report to each client"""
    if time.time() - _last["t"] < 3600:
        return
    _last["t"] = time.time()
    try:
        c, today = load(), datetime.now().date()
        changed = False
        c["warned"] = {}                                              # only what this tick adds is merged back
        old = load()["warned"]
        for sid, cl in c["clients"].items():
            if not (cl.get("plan") and cl.get("end")):
                continue
            try:
                left = (datetime.strptime(cl["end"], "%Y-%m-%d").date() - today).days
            except ValueError:
                continue
            step = next((s for s in (0, 7, 30) if left <= s), None)
            key = f"{sid}|{cl['end']}|{step}"
            if step is None or old.get(key):
                continue
            c["warned"][key] = today.isoformat()
            changed = True
            name = (_site(sid) or {}).get("name") or sid
            plan = c["plans"].get(cl["plan"], {}).get("name", "")
            from web import monitor
            monitor.broadcast(f"💼 NQ Care\nعقد {name} ({plan}) " + ("خلص النهارده!" if left <= 0 else f"هيخلص بعد {left} يوم ({cl['end']})")
                              + (f"\nالمسؤول: {cl['contact']}" if cl.get("contact") else "") + "\nوقت التجديد.")
        if datetime.now().day == 1:
            prev = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
            due = [sid for sid, cl in c["clients"].items() if cl.get("plan") and cl.get("email")
                   and not str(old.get(f"report|{sid}|{prev}", "")).startswith(("sent", "fail:3"))]
            if due and not _last.get("reports"):
                _last["reports"] = True                               # PDFs take time: not inside the shared background tick
                threading.Thread(target=_send_reports, args=(due, prev), name="care-reports", daemon=True).start()
        if changed:
            _merge_warned(c["warned"])
    except Exception as e:
        print(f"[care] {e}", flush=True)


def _merge_warned(new):
    """only «warned» is written back: a plan / contract / notice saved meanwhile on the page is kept"""
    cur = load_json(FILE, {}) or {}
    w = {**(cur.get("warned") or {}), **new}
    cur["warned"] = dict(sorted(w.items(), key=lambda kv: str(kv[1]))[-500:])  # never grows without end
    _save(cur)


def _send_reports(sids, month):
    try:
        for sid in sids:
            key = f"report|{sid}|{month}"
            try:
                ok, _ = send_report(sid, month)
            except Exception as e:
                ok = False
                print(f"[care] report {sid}: {e}", flush=True)
            prev = str(load()["warned"].get(key, ""))
            n = int(prev.split(":")[1]) + 1 if prev.startswith("fail:") else 1
            _merge_warned({key: "sent " + datetime.now().strftime("%Y-%m-%d %H:%M") if ok else f"fail:{min(n, 3)}"})
    finally:
        _last["reports"] = False
