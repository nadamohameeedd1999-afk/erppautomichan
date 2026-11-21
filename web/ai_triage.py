"""
🤖 فرز التذاكر بالذكاء — before you send «دعم المطورين» tickets on, each open one gets:
  • its group — tickets with the same root cause (same message with the numbers blanked, same screen family) are one problem
  • the likely cause, in plain words, from the error type / message / stack
  • the developer to give it to — whoever fixed tickets on that screen family before (from the assignments you made)
  • a hint for the fix, and a suggested priority
Rules do this with no key; with the Claude API key (Settings) Claude reads the evidence and writes cause / hint / group.
Also: a message for the client about a ticket («عارفين المشكلة وشغالين عليها، متوقع تتحل خلال …») — Claude or a template.
Store: settings/support_ai.json
"""
import json
import re
from collections import Counter, defaultdict
from datetime import datetime

CAUSES = [  # (pattern in type / message / evidence, the likely cause, a hint)
    (r"Invalid column name|Invalid object name|عمود", "عمود أو جدول ناقص في قاعدة البيانات عند العميل",
     "غالبًا سكريبت تحديث القاعدة متنفذش على نسخة العميل: قارن القاعدة بموقع الاختبار"),
    (r"SqlException|deadlock|Timeout expired|timeout", "مشكلة في الاستعلام أو القاعدة (بطء، قفل، أو مهلة)",
     "شوف الاستعلام البطيء في «من جوه الأنظمة» وضيف index أو قلّل البيانات المرجوعة"),
    (r"NullReference|Object reference not set", "قيمة فاضية الكود مكانش متوقعها (بيانات ناقصة أو حقل مش متختار)",
     "اتأكد من الحقل اللي ممكن يبقى فاضي في الشاشة دي وضيف تحقق قبل الاستخدام"),
    (r"InvalidOperation|Sequence contains no elements", "الكود بيدوّر على سجل مش موجود",
     "استخدم FirstOrDefault واتعامل مع الحالة اللي مفيهاش بيانات"),
    (r"maxJsonLength|JSON", "رد كبير على JSON (قايمة طويلة)", "زوّد maxJsonLength أو رجّع البيانات صفحة صفحة"),
    (r"Format|Conversion|cast|DateTime", "تحويل قيمة (تاريخ أو رقم) بصيغة مش متوقعة", "شوف صيغة التاريخ/الرقم اللي جاية من الشاشة أو من الإعدادات الإقليمية"),
    (r"\b404\b|not found|مش موجود", "الشاشة أو المسار مش موجود", "اتأكد من اللينك في المنيو ومن الـ route"),
    (r"\b40[13]\b|permission|صلاحي|Unauthorized", "صلاحيات: المستخدم مش مسموحله", "راجع صلاحيات الدور على الشاشة دي"),
    (r"فضلت تحمّل|stays loading", "الشاشة بتفضل تحمّل ومبتطلعش بيانات", "غالبًا طلب AJAX بيفشل أو بطيء جدًا: افتح Network في المتصفح"),
    (r"\b5\d\d\b|Server Error|Exception", "خطأ في السيرفر", "شوف الـ stack في الدليل"),
]


def _f():
    from web import support
    return support


def _family(screen):
    """'/SalesInvoice/AddEdit/#' → 'salesinvoice' (a screen family = the controller)"""
    s = re.sub(r"^https?://[^/]+", "", str(screen or "")).strip("/").split("/")[0]
    return re.sub(r"[^a-z؀-ۿ]", "", s.lower())[:40]


def _norm(t):
    return re.sub(r"\d+", "#", re.sub(r"'[^']*'", "'…'", str(t or "")))[:160]


def ownership():
    """screen family → who got its tickets before (your assignments in «دعم المطورين»)"""
    sp = _f()
    st = sp._load("support_status.json", {})
    items = {i["id"]: i for i in sp.collect()[0]}
    own = defaultdict(Counter)
    for iid, s in st.items():
        if s.get("dev") and iid in items:
            own[_family(items[iid].get("screen") or items[iid].get("url"))][s["dev"]] += 2 if s.get("fixed_at") else 1
    return own


def rule_triage(items, devs, own=None):
    own = own if own is not None else ownership()
    groups, out = {}, {}
    for i in items:
        fam = _family(i.get("screen") or i.get("url"))
        text = f"{i.get('title', '')} {i.get('details', '')} {i.get('evidence', '')[:800]}"
        g = groups.setdefault(f"{fam}|{_norm(i.get('title', '').split(':', 1)[-1])}", i["id"])
        cause, hint = next(((c, h) for p, c, h in CAUSES if re.search(p, text, re.I)), ("مش واضح من الدليل", "افتح الشاشة بخطوات التكرار"))
        best = own.get(fam, Counter()).most_common(1)
        load = Counter()                                          # nobody owns it yet: the developer with the fewest open tickets
        for x in items:
            if x.get("dev"):
                load[x["dev"]] += 1
        dev = best[0][0] if best else (min(devs, key=lambda d: load[d]) if devs else "")
        sev = i.get("severity", "متوسطة")
        prio = "عالية" if sev == "عالية" or i.get("count", 1) >= 5 or len(i.get("who") or []) >= 3 else sev
        out[i["id"]] = {"group": g if g != i["id"] else "", "cause": cause, "hint": hint, "dev": dev,
                        "dev_why": f"اشتغل على شاشات {fam} قبل كده" if best else "أقل واحد عنده تذاكر مفتوحة", "priority": prio, "by": "rules"}
    return out


def _ai(items, devs, own, rules):
    from web import explain
    key = explain._api_key()
    if not key:
        return {}
    brief = [{"id": i["id"], "title": i.get("title", "")[:200], "screen": i.get("screen", ""), "severity": i.get("severity"),
              "times": i.get("count", 1), "evidence": (i.get("evidence") or i.get("details") or "")[:700]} for i in items[:40]]
    owners = {fam: [d for d, _ in c.most_common(2)] for fam, c in own.items()}
    prompt = ("إنت مهندس دعم لنظام ERP مكتوب بـ ASP.NET MVC و SQL Server. دي تذاكر مشاكل مفتوحة لقيناها في النظام.\n"
              f"المطورين: {', '.join(devs)}. مين اشتغل على أنهي عائلة شاشات قبل كده: {json.dumps(owners, ensure_ascii=False)}\n"
              "لكل تذكرة رجّع: group (رقم id أول تذكرة ليها نفس السبب الجذري، أو \"\" لو لوحدها)، cause (السبب المحتمل بجملة قصيرة "
              "بالعربي المصري)، hint (تلميح للحل للمطور بجملة)، dev (اسم من المطورين)، priority (عالية/متوسطة/منخفضة)، "
              "client_note (جملة للعميل من غير أي تفاصيل تقنية).\n"
              "رجّع JSON array بس، من غير أي كلام قبله أو بعده.\n\n" + json.dumps(brief, ensure_ascii=False))
    data = explain._call(key, explain._model(), [{"type": "text", "text": prompt}], max_tokens=4000, timeout=120)
    text = "".join(c.get("text", "") for c in data.get("content", []) if c.get("type") == "text")
    m = re.search(r"\[.*\]", text, re.S)
    rows = json.loads(m.group(0)) if m else []
    ids = {i["id"] for i in items}
    out = {}
    for r in rows:
        if isinstance(r, dict) and r.get("id") in ids:
            base = rules.get(r["id"], {})
            out[r["id"]] = {**base, **{k: str(r.get(k) or base.get(k, ""))[:300] for k in ("group", "cause", "hint", "dev", "priority", "client_note")},
                            "by": "claude"}
            if out[r["id"]]["dev"] not in devs:
                out[r["id"]]["dev"] = base.get("dev", "")
            if out[r["id"]]["group"] not in ids:
                out[r["id"]]["group"] = ""
    return out


def run(use_ai=True):
    """triage every open dev ticket → {"n", "by", "error"} (saved to support_ai.json)"""
    sp = _f()
    items = [i for i in sp.collect()[0] if i["status"] not in ("اتصلح", "مش مشكلة")]
    devs = sp.sla_cfg()["devs"]
    own = ownership()
    res = rule_triage(items, devs, own)
    err, by = "", "rules"
    if use_ai:
        try:
            ai = _ai(items, devs, own, res)
            if ai:
                res.update(ai)
                by = "claude"
        except Exception as e:
            err = str(e)[:300]
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    store = sp._load("support_ai.json", {})
    for k, v in res.items():
        store[k] = {**v, "at": stamp}
    sp._save("support_ai.json", store)
    return {"n": len(res), "by": by, "error": err}


def screen_label(screen):
    """a path like '/SalesInvoice/AddEdit/#' → its name in the NQ ERP menu (as the virtual company read it); Arabic names stay"""
    s = str(screen or "").strip()
    if not s.startswith("/"):
        return s or "إحدى شاشات النظام"
    from config import paths
    try:
        menus = json.loads(paths.settings_file("simulation_menus.json").read_text(encoding="utf-8"))
    except Exception:
        menus = {}
    fam = _family(s)
    best = ""
    for v in menus.values():
        for x in v.get("menu") or []:
            if _family(x.get("path")) == fam and x.get("name"):
                if x["path"].split("?")[0].rstrip("/").lower() == s.replace("/#", "").rstrip("/").lower():
                    return x["name"]
                best = best or x["name"]
    return best or "إحدى شاشات النظام"


def client_message(item, eta_h=None):
    """a short message for the client about this ticket (no technical details)"""
    sp = _f()
    eta_h = eta_h or sp.sla_cfg()["hours"].get(item.get("severity"), 72)
    eta = f"خلال {int(eta_h)} ساعة" if eta_h < 48 else f"خلال {round(eta_h / 24)} أيام"
    note = (sp._load("support_ai.json", {}).get(item["id"]) or {}).get("client_note", "")
    screen = screen_label(item.get("screen"))
    from web import explain
    if explain._api_key():
        try:
            prompt = ("اكتب رسالة واتساب قصيرة (3 سطور بالكتير) من فريق دعم NQ ERP لعميل، بالعربي البسيط المهذب، عن مشكلة إحنا اكتشفناها بنفسنا "
                      f"قبل ما يبلّغ عنها. الشاشة: {screen}. المشكلة: {item.get('title', '')[:200]}. متوقع تتحل {eta}. "
                      "من غير أي تفاصيل تقنية أو أسماء جداول أو أكواد. ابدأ بالسلام. رجّع نص الرسالة بس.")
            data = explain._call(explain._api_key(), explain._model(), [{"type": "text", "text": prompt}], max_tokens=300, timeout=60)
            text = "".join(c.get("text", "") for c in data.get("content", []) if c.get("type") == "text").strip()
            if text:
                return {"text": text, "by": "claude"}
        except Exception:
            pass
    where = "في إحدى شاشات النظام" if screen == "إحدى شاشات النظام" else f"في شاشة «{screen}»"
    return {"text": f"السلام عليكم،\nفريق دعم NQ ERP لاحظ مشكلة {where}" + (f" ({note})" if note else "")
                    + f" وبنشتغل على حلها دلوقتي، ومتوقع تتحل {eta}.\nهنبلّغكم أول ما تخلص، وآسفين على أي إزعاج.", "by": "template"}
