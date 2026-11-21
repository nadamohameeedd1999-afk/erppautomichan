"""
🤝 العرض للعميل — the virtual company as a sales demo.

• A demo site (one of your sites, marked «اختبار» so it may be written to) gets its own copy of the virtual company: every
  working morning it runs a real day there (sales orders, invoices, purchases, stock, receipts…), so in a meeting NQ ERP
  shows TODAY's work, not an empty system. Its days are kept apart from the test company's (data/simulation_sales).
• A presenter page for the meeting: the client's sector → the pitch, their pains and NQ ERP's answer, and a guided tour
  whose every step opens the right screen on the demo site, with what to say; live proof from our own monitoring
  (uptime, checks, problems caught) and the NQ Care plans.
• A leave-behind PDF (approved design) for the chosen sector, and a JSON feed of all of it for the AI sales employee (n8n).
Settings: data/settings/sales.json
"""
import html
import json
import re
import secrets
import threading
from datetime import datetime, timedelta

from config import paths
from config.storage import load_json, save_json

FILE = paths.settings_file("sales.json")
RUNS = paths.DATA_DIR / "simulation_sales"
DAYS_AR = ["الاتنين", "التلات", "الأربع", "الخميس", "الجمعة", "السبت", "الحد"]          # Python weekday() order
SECTORS = {
    "trading": {
        "name": "تجارة وتوزيع",
        "pitch": "من عرض السعر لحد التحصيل في دورة واحدة: المندوب يبيع من الموبايل، والمخزن يصرف، والفاتورة تطلع متوافقة مع زاتكا، والحسابات تتقفل لوحدها.",
        "pains": [["المخزون في السيستم مش زي اللي في المخزن", "صرف مخزني مربوط بأمر البيع، وجرد وإعادة تقييم، وتتبع الدفعات والتشغيلات"],
                  ["التحصيل متأخر ومحدش عارف مين عليه كام", "أعمار الديون، وحدود ائتمان بالقيمة وعدد الفواتير، ووكيل تحصيل ذكي"],
                  ["المندوبين بره ومفيش متابعة", "تطبيق المندوب: أقصر مسار للزيارات، وحوافز بتنزل على مسير الرواتب"],
                  ["الفاتورة الإلكترونية والضريبة", "فواتير متوافقة مع زاتكا، ومطابقة الإقرار الضريبي من السيستم"]],
        "tour": [["لوحة المدير: مبيعات النهارده", "الرئيسية", "ده شغل الشركة النهارده، اتعمل الصبح على نفس السيستم اللي هتشتغلوا عليه"],
                 ["أمر بيع وفاتورة مبيعات", "فاتورة مبيعات", "الفاتورة بتتعمل من أمر البيع والصرف المخزني، ومتوافقة مع زاتكا"],
                 ["المخزون والتحويلات", "تحويل", "كل حركة مخزن مربوطة بمستند، فالرصيد دايمًا صح"],
                 ["أعمار الديون", "أعمار الديون", "تعرف مين متأخر وبكام، قبل ما الفلوس تتحبس"],
                 ["التقارير", "تقرير", "أي تقرير بضغطة: مبيعات بالمندوب، بالفرع، بالصنف، وربحية"]]},
    "manufacturing": {
        "name": "تصنيع خفيف",
        "pitch": "من أمر الشغل للمنتج التام: صرف الخامات، والتجميع، والهالك، وتكلفة المنتج الفعلية، وكلها بقيود تلقائية.",
        "pains": [["مش عارف تكلفة المنتج الحقيقية", "سند التجميع ومخزن تحت التشغيل وتوزيع مراكز التكلفة، فالتكلفة بتطلع فعلية"],
                  ["الهالك والفاقد مش متسجل", "الجيد بيتحوّل للتام والهالك بيتصرف بسند، والفرق بيبان"],
                  ["الطلبيات بتتأخر", "أمر بيع ← أمر عمل ← أمر شغل، وكل مرحلة متتبعة"],
                  ["الخامات بتخلص فجأة", "خطة مشتريات بحدود الكمية والسعر، من احتياجات الإنتاج"]],
        "tour": [["أمر عمل من أمر البيع", "أمر عمل", "أمر البيع بيتحوّل لأمر عمل بنفس الأصناف من غير ما حد يكتب تاني"],
                 ["صرف الخامات", "صرف", "الخامات بتتصرف على أمر الشغل، والمخزن بيتخصم لحظتها"],
                 ["سند التجميع", "تجميع", "الإنتاج بيدخل مخزن تحت التشغيل، والجيد بيروح للتام والهالك بيتسجل"],
                 ["تكلفة المنتج", "تكلفة", "تكلفة كل منتج فعلية، من الخامات ومراكز التكلفة"],
                 ["لوحة المدير", "الرئيسية", "كل ده اتعمل النهارده الصبح على السيستم ده"]]},
    "services": {
        "name": "خدمات",
        "pitch": "مشاريع وعقود وموظفين ومصروفات تحت سيطرة واحدة: ربحية كل مشروع وكل مركز تكلفة، ومسير رواتب متوافق مع قوى ومدد.",
        "pains": [["مش عارف أنهي مشروع كسبان وأنهي خسران", "أبعاد محاسبية على كل قيد: مشروع ومركز تكلفة وفرع، وقائمة دخل بمراكز التكلفة"],
                  ["الرواتب والجزاءات بتاخد وقت كبير", "مسير رواتب، وجزاءات حسب نظام العمل، وربط مع قوى ومدد والتأمينات"],
                  ["العهد والمصروفات النثرية", "تصفية العهد ورفع الفواتير بالصورة، والسيستم يكمّل سطور المصروف"],
                  ["الموافقات ماشية على الورق", "دورة موافقات على كل مستند، بصلاحيات لكل موظف"]],
        "tour": [["قيد بأبعاد محاسبية", "قيد", "كل سطر بيتوزع على المشروع ومركز التكلفة، فالربحية بتطلع لوحدها"],
                 ["سند صرف وتحليل المصروفات", "سند صرف", "المصروف بيتحلل بالتصنيف والمشروع ومركز التكلفة"],
                 ["مسير الرواتب", "مسير", "المسير بيتحسب بالحضور والجزاءات والبدلات"],
                 ["قائمة الدخل بمراكز التكلفة", "قائمة الدخل", "تشوف كل قسم أو مشروع كسب كام"],
                 ["لوحة المدير", "الرئيسية", "الشغل ده كله اتعمل النهارده على نفس السيستم"]]},
    "concrete": {
        "name": "مصانع الخرسانة",
        "pitch": "مصنع الخرسانة من الطلب للتوريد: كمية التوريد من سعة الخلاطة، وإحلال الأسمنت، وربحية المتر المكعب من الميزان.",
        "pains": [["أخطاء كميات التوريد", "كمية التوريد بتتحدد لوحدها من سعة الخلاطة"],
                  ["مش عارف ربح المتر المكعب", "شاشة ربحية الخرسانة: الخامات بمتوسط سعرها، ومصاريف التشغيل من ميزان المصروفات"],
                  ["تكلفة الأسمنت عالية", "إعداد إحلال الأسمنت بالسيليكا فيوم بالنسبة اللي تحددها"],
                  ["التحصيل من المقاولين", "أعمار الديون وحدود الائتمان لكل عميل"]],
        "tour": [["التوريدات", "توريد", "التوريد بيتسجل والكمية من سعة الخلاطة، فمفيش غلط في الكمية"],
                 ["ربحية الخرسانة", "ربحية", "ربح كل متر مكعب من الخامات والمصاريف الفعلية"],
                 ["أعمار الديون", "أعمار الديون", "مين من المقاولين متأخر وبكام"],
                 ["لوحة المدير", "الرئيسية", "عملاء زي روائع التشييد شغالين على نفس السيستم"]]},
}
_company, _lock = {"c": None}, threading.Lock()


def load():
    c = load_json(FILE, {}) or {}
    sec = {k: {**v, **((c.get("sectors") or {}).get(k) or {})} for k, v in SECTORS.items()}
    return {"demo_site": c.get("demo_site", ""), "auto_on": bool(c.get("auto_on", False)), "at": c.get("at", "06:30"),
            "days": c.get("days", [6, 0, 1, 2, 3]), "feed_key": c.get("feed_key", ""), "sectors": sec, "last_run": c.get("last_run", "")}


def save(new):
    c = {**(load_json(FILE, {}) or {})}
    for k in ("demo_site", "auto_on", "at", "days"):
        if k in new:
            c[k] = new[k]
    if not re.fullmatch(r"\d\d:\d\d", str(c.get("at", "06:30"))):
        c["at"] = "06:30"
    if "sectors" in new:                                          # only the words: name, pitch, pains, tour
        c["sectors"] = {k: {f: v[f] for f in ("name", "pitch", "pains", "tour") if f in v} for k, v in (new["sectors"] or {}).items() if k in SECTORS}
    save_json(FILE, c)
    return load()


def feed_key(new=False):
    c = {**(load_json(FILE, {}) or {})}
    if new or not c.get("feed_key"):
        c["feed_key"] = secrets.token_urlsafe(18)
        save_json(FILE, c)
    return c["feed_key"]


def key_ok(key):
    real = (load_json(FILE, {}) or {}).get("feed_key", "")
    return bool(key and real and secrets.compare_digest(str(key), real))


def _profiles():
    from web import monitor
    return monitor._sites({})


def demo_site():
    sid = load()["demo_site"]
    return next((p for p in _profiles() if p["id"] == sid), None)


def company():
    """the demo's own copy of the virtual company (made once; follows the chosen demo site)"""
    p = demo_site()
    with _lock:
        c = _company["c"]
        if p and (c is None or c.site_id != p["id"]):
            from simulation.engine import Company
            _company["c"] = Company(use_settings=True, runs=RUNS, site_id=p["id"])
        return _company["c"] if p else None


def start_day():
    """a working day on the demo site now -> "" or why not"""
    p = demo_site()
    if not p:
        return "اختار موقع العرض الأول"
    if p.get("kind") != "test":
        return "موقع العرض لازم يكون نوعه «اختبار» في الإعدادات ▸ المواقع، علشان الشركة تقدر تسجّل فيه"
    c = company()
    if c.running:
        return "الشركة شغالة دلوقتي على موقع العرض"
    c.control("start")
    c.control("speed", 30)                                         # the demo needs the data, not the show
    cfg = {**(load_json(FILE, {}) or {}), "last_run": datetime.now().strftime("%Y-%m-%d %H:%M")}
    save_json(FILE, cfg)
    return ""


def last_days(n=7):
    out = []
    for f in sorted(RUNS.glob("day_*.json"), reverse=True)[:n] if RUNS.exists() else []:
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({"date": r.get("date"), "deals": r.get("deals", 0), "closed": r.get("closed", 0), "sales": r.get("sales", 0),
                    "employees": len(r.get("employees") or []), "mode": r.get("mode"), "problems": r.get("erp_problems", 0)})
    return out


def _menu(site_id):
    """the demo site's menu as the virtual company read it: [{path, name, module}]"""
    try:
        m = json.loads(paths.settings_file("simulation_menus.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    best = max((v for k, v in m.items() if k.startswith(f"{site_id}:")), key=lambda v: v.get("n", 0), default={})
    return best.get("menu") or []


def tour_links(sector):
    """each tour step -> the demo site's screen whose menu name holds the step's word ("" = home)"""
    p, sec = demo_site(), load()["sectors"].get(sector) or {}
    base = (p or {}).get("base_url", "").rstrip("/")
    menu = _menu(p["id"]) if p else []
    out = []
    for title, word, say in sec.get("tour", []):
        hit = next((x for x in menu if word and word != "الرئيسية" and word in x.get("name", "")), None)
        out.append({"title": title, "word": word, "say": say, "url": base + (hit["path"] if hit else "/") if base else "",
                    "screen": hit["name"] if hit else ("الرئيسية" if word == "الرئيسية" else ""), "found": bool(hit) or word == "الرئيسية"})
    return out


def proof():
    """our own numbers as proof, across every client site (no names)"""
    from web import care, monitor, telemetry
    st, ups, outs, checks = monitor._state(), [], 0, 0
    since = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    for sid, s in st.items():
        d = [v for k, v in (s.get("days") or {}).items() if k >= since]
        n, ok = sum(x["n"] for x in d), sum(x["ok"] for x in d)
        checks += n
        if n and s.get("kind") == "client":
            ups.append(100 * ok / n)
        outs += len([o for o in care.outages(sid, since)])
    log = [x for s in st.values() for x in s.get("deep_log") or [] if x["at"][:10] >= since]
    fixed = sum(len(x["fixed"]) for x in log)
    tel = telemetry._load()
    caught = sum(1 for s in tel.values() for e in (s.get("errors") or {}).values() if e.get("first", "")[:10] >= since)
    return {"clients": sum(1 for p in _profiles() if p.get("kind") == "client"), "uptime30": round(sum(ups) / len(ups), 2) if ups else None,
            "checks30": checks, "screens_fixed30": fixed, "errors_caught30": caught, "outages30": outs,
            "every_min": monitor.load_config().get("every_min", 15)}


def overview():
    c, p = load(), demo_site()
    co = company() if p else None
    return {"config": {k: v for k, v in c.items() if k not in ("feed_key", "sectors")}, "sectors": c["sectors"],
            "sites": [{"id": x["id"], "name": x.get("name"), "kind": x.get("kind")} for x in _profiles()],
            "demo": {"id": p["id"], "name": p.get("name"), "url": p.get("base_url"), "kind": p.get("kind"),
                     "running": bool(co and co.running), "menu": len(_menu(p["id"]))} if p else None,
            "days": last_days(), "proof": proof(), "days_ar": DAYS_AR}


def html_leave(sector, client="", user="", for_pdf=False):
    """the leave-behind after the meeting (approved design): the pitch, their pains and our answers, the tour, NQ Care"""
    from web import care
    from web.monthly_report import report_shell
    e, sec = html.escape, load()["sectors"].get(sector) or SECTORS["trading"]
    pr, plans = proof(), care.load()["plans"]
    pains = "".join(f'<tr><td class="c">{i}</td><td>{e(a)}</td><td>{e(b)}</td></tr>' for i, (a, b) in enumerate(sec["pains"], 1))
    tour = "".join(f'<tr><td class="c">{i}</td><td><b>{e(t)}</b></td><td>{e(s)}</td></tr>' for i, (t, w, s) in enumerate(sec["tour"], 1))
    pl = "".join(f'<tr><td><b>{e(p["name"])}</b></td><td class="c">{e(p["price"]) or "—"}</td><td class="c">{p["uptime"]}%</td>'
                 f'<td class="c">خلال {p["response_h"]} ساعة</td></tr>' for p in plans.values())
    facts = [f"بنراقب أنظمة عملائنا كل {pr['every_min']} دقيقة على مدار الساعة"]
    if pr["uptime30"]:
        facts.append(f"متوسط تشغيل أنظمة عملائنا آخر 30 يوم: {pr['uptime30']}%")
    if pr["screens_fixed30"] or pr["errors_caught30"]:
        facts.append(f"آخر 30 يوم: لقينا وصلّحنا {pr['screens_fixed30'] + pr['errors_caught30']} مشكلة قبل ما العميل يبلّغ عنها")
    body = f"""<p class="intro"><b>{e(sec['name'])}:</b> {e(sec['pitch'])}</p>
  <h3>اللي بيتعبك، وإزاي NQ ERP بيحله</h3>
  <table><thead><tr><th class="c" style="width:30px">م</th><th>المشكلة</th><th>الحل في NQ ERP</th></tr></thead><tbody>{pains}</tbody></table>
  <h3>اللي شفناه في العرض</h3>
  <table><thead><tr><th class="c" style="width:30px">م</th><th>الشاشة</th><th>ليه مهمة</th></tr></thead><tbody>{tour}</tbody></table>
  <h3>الدعم بعد التشغيل: NQ Care</h3>
  <table><thead><tr><th>الباقة</th><th class="c">السعر السنوي</th><th class="c">هدف التشغيل</th><th class="c">الاستجابة</th></tr></thead><tbody>{pl}</tbody></table>
  <p class="grey" style="margin-top:12px">{' · '.join(e(f) for f in facts)}</p>"""
    strip = [("القطاع", e(sec["name"]))] + ([("العميل", e(client))] if client else []) + [("التاريخ", datetime.now().strftime("%Y-%m-%d"))]
    return report_shell(f"ملخص العرض — {e(client or sec['name'])}", "ملخص عرض NQ ERP", "NQ ERP — Meeting Summary", user, strip, body, for_pdf)


def feed():
    """everything the AI sales employee needs, in one JSON"""
    from web import care
    c, p = load(), demo_site()
    return {"product": "NQ ERP", "market": "السعودية — شركات متوسطة في الخدمات والتجارة والتصنيع الخفيف",
            "sectors": {k: {"name": v["name"], "pitch": v["pitch"], "pains": [{"pain": a, "answer": b} for a, b in v["pains"]],
                            "tour": [{"screen": t, "say": s} for t, w, s in v["tour"]]} for k, v in c["sectors"].items()},
            "nq_care": [{"name": x["name"], "price": x["price"], "uptime_target": x["uptime"], "response_hours": x["response_h"], "features": x["features"]}
                        for x in care.load()["plans"].values()],
            "proof": proof(), "demo": {"site": (p or {}).get("base_url", ""), "last_days": last_days(3)},
            "generated": datetime.now().isoformat(timespec="seconds")}


def auto_tick(now=None):
    """a working day on the demo site every chosen morning (once a day)"""
    try:
        c, t = load(), datetime.now()
        if not (c["auto_on"] and c["demo_site"]) or t.weekday() not in c["days"] or t.strftime("%H:%M") < c["at"]:
            return
        if c["last_run"][:10] == t.strftime("%Y-%m-%d"):
            return
        why = start_day()
        if why:
            cfg = {**(load_json(FILE, {}) or {}), "last_run": t.strftime("%Y-%m-%d %H:%M")}     # don't retry every 20 s
            save_json(FILE, cfg)
            print(f"[sales] {why}", flush=True)
    except Exception as e:
        print(f"[sales] {e}", flush=True)
