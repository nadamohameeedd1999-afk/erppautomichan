"""
Why did it fail? (ليه الاختبار فشل) — an Arabic explanation + what to do.

1) Rules (always, no internet): they know the engine's own messages and the usual ERP problems and say
   whose problem it is: a bug in the system, the test setup, the data, or the network / browser.
2) AI (optional): with a Claude API key (Settings → or ANTHROPIC_API_KEY) the failure message, the end of
   the log and the last screenshot are sent to Claude for a fuller explanation. Saved per run (asked once).
"""
import base64
import json
import os
import re
import urllib.request

from config import paths

KIND = {
    "bug": ("🐞 غالبًا مشكلة في النظام نفسه", "danger"),
    "setup": ("🛠️ إعداد الاختبار محتاج تعديل", "warning"),
    "data": ("📦 مشكلة بيانات على موقع الاختبار", "info"),
    "env": ("🌐 مشكلة شبكة / متصفح (مش في الشاشة)", "secondary"),
    "unknown": ("❓ مش واضح", "secondary"),
}

# (pattern, kind, title, explanation, fix)  — {1} = first group of the pattern
RULES = [
    (r"(InvalidSessionId|chrome not reachable|disconnected|session deleted|tab crashed)", "env", "المتصفح وقع",
     "Chrome نفسه وقع أثناء الاختبار — مش مشكلة في الشاشة.",
     "بيتعاد أوتوماتيك مرة. لو بيتكرر على Railway: خلي «في نفس الوقت» = 1 في مركز التشغيل، "
     "أو زوّدي ذاكرة الخدمة (Settings ← Resources)، أو شغّلي من جهازك."),
    (r"(TimeoutException|ERR_CONNECTION|ERR_NAME_NOT_RESOLVED|ERR_TIMED_OUT|Read timed out|Max retries)", "env", "الموقع بطيء أو مش بيرد",
     "الصفحة أخدت وقت أكتر من المسموح أو الموقع ما ردش.",
     "اتأكدي إن موقع الاختبار شغال، وجربي تاني. لو بيتكرر على شاشة معينة يبقى الشاشة بطيئة (بلغي فريق التطوير)."),
    (r"الحسبة مش مظبوطة:?\s*(.*)", "bug", "الحسابات طالعة غلط",
     "الأرقام اللي على الشاشة مش مطابقة للحسبة اللي متوقعة ({1}).",
     "لو الحسبة في الاختبار صح، ده bug في النظام — ابعتيه لفريق التطوير مع لقطة الشاشة."),
    (r"القيم اللي اتسجلت مختلفة", "bug", "اللي اتحفظ مختلف عن اللي اتكتب",
     "بعد الحفظ فتحنا السند ولقينا قيمة اتسجلت غير اللي اتملت.",
     "راجعي الجدول في التقرير (اتملى / اتسجل). لو القيمة اتغيرت فعلًا ده bug في الحفظ."),
    (r"(server error|runtime error|خطأ في الخادم|500 internal|yellow screen)", "bug", "الشاشة طلّعت خطأ من السيرفر",
     "الصفحة نفسها طلعت رسالة خطأ من السيرفر.",
     "ده غالبًا bug في النظام — ابعتي لقطة الشاشة واللوج لفريق التطوير."),
    (r"صفحة الطباعة (فيها خطأ|فاضية)", "bug", "الطباعة مش شغالة",
     "زرار الطباعة فتح صفحة فيها خطأ أو فاضية.",
     "جربي الطباعة بإيدك على نفس السند؛ لو نفس المشكلة يبقى bug في التقرير."),
    (r"اتحفظ — والمفروض كان يترفض", "bug", "النظام قبل بيانات المفروض يرفضها",
     "الاختبار السلبي كان متوقع إن الحفظ يترفض، بس النظام حفظ عادي.",
     "يا إما التحقق (validation) اتشال من الشاشة — bug — يا إما الاختبار السلبي محتاج تحديث."),
    (r"اترفض صح بس الرسالة مختلفة", "setup", "رسالة الرفض اتغيرت",
     "الحفظ اترفض زي ما متوقع، بس بنص مختلف عن اللي في الاختبار.",
     "عدّلي «الرسالة المتوقعة» في اختبارات متقدمة للنص الجديد."),
    (r"يجب ان تختار الملفات|يجب أن تختار الملفات|اختر الملفات اولا|يجب ارفاق", "setup", "الشاشة محتاجة مرفق",
     "الحفظ اترفض لأن الشاشة بتطلب ملف مرفق.",
     "ضيفي «📎 قالب: رفع مرفق» في منشئ الشاشات."),
    (r"يجب إضافة أصناف|يجب اضافة اصناف|لا يوجد أصناف", "setup", "الفاتورة من غير أصناف",
     "الحفظ اترفض لأن مفيش سطور أصناف.",
     "ضيفي «➕ قالب: إضافة صنف» أو سجّلي الخطوات بـ «⏺ سجّلي خطواتك»."),
    (r"حقول إجبارية لسه فاضية:\s*([^\n]+)", "setup", "حقول إجبارية ما اتملتش",
     "الحفظ اترفض لأن الحقول دي إجبارية وفاضية: {1}.",
     "علّمي على الحقول دي في منشئ الشاشات واختاري طريقة تعبئتها."),
    (r"قوائم فاضية وقت الحفظ:\s*([^\n]+)", "setup", "قوايم فضيت قبل الحفظ",
     "القوايم دي كانت فاضية وقت الحفظ: {1} — غالبًا اتمسحت لما اتغير حقل قبلها.",
     "رتّبي الحقول بحيث القايمة تيجي بعد الحقل اللي بتعتمد عليه، أو حددي «بيعتمد على»."),
    (r"\[([^\]]+)\] الحقل مش موجود في الصفحة", "setup", "حقل مش موجود في الصفحة",
     "الحقل «{1}» مش لاقيه بالـ id بتاعه — يا إما الـ id اتغير، يا إما الحقل بيظهر بعد اختيار حاجة قبله.",
     "دوسي «اقرأ الحقول» تاني في منشئ الشاشات، أو تأكدي من ترتيب الحقول."),
    (r"القيمة المطلوبة '([^']*)' مش موجودة", "data", "القيمة مش موجودة في القايمة",
     "القيمة «{1}» مش في القايمة على موقع الاختبار — غالبًا البيانات اتغيرت أو اتمسحت.",
     "اختاري قيمة موجودة، أو «أول خيار حقيقي»، أو «لو مش موجودة: اعملها بـ …»."),
    (r"مفيش ولا خيار في القايمة", "data", "القايمة فاضية",
     "القايمة مفيهاش ولا اختيار — غالبًا بتعتمد على حقل قبلها أو مفيش بيانات.",
     "تأكدي إن الحقل اللي قبلها اتملى، أو إن فيه بيانات على موقع الاختبار."),
    (r"الجدول مظهرش فيه صفوف", "data", "مفيش مستندات بالفلاتر دي",
     "بعد «المصفي» الجدول طلع فاضي.",
     "غيّري التاريخ ({month_start} … {month_end}) أو نوع المستند، أو اعملي مستند الأول بسلسلة «شغّل قبلها»."),
    (r"مفيش صف فيه «([^»]+)»", "data", "الصف المطلوب مش موجود",
     "مفيش صف في الجدول فيه «{1}».",
     "اتأكدي إن البيانات موجودة، أو سيبي «الصف اللي فيه» فاضي عشان ياخد أول صف."),
    (r"النافذة مفتحتش", "setup", "النافذة ما فتحتش",
     "اتداس على الزرار بس النافذة ما ظهرتش.",
     "اتأكدي من الزرار، وإن الحقول اللي قبله (زي العميل) متعلّم عليها وبتتملى قبله."),
    (r"مالقيتش زرار «([^»]+)»", "setup", "زرار مش موجود",
     "الزرار «{1}» مش ظاهر في الصفحة — يا إما اسمه اتغير، يا إما بيظهر بعد خطوة قبله.",
     "اكتبي الـ id بتاعه بـ # بدل الاسم، أو سجّلي الخطوات تاني."),
    (r"مظهرش صف جديد في القايمة", "setup", "اتحفظ بس مظهرش في أول القايمة",
     "الحفظ اتم بس أول صف في القايمة ما اتغيرش — يا إما الترتيب مش بالأحدث، يا إما الحفظ ما تمّش فعلًا.",
     "افتحي القايمة بإيدك. لو الترتيب مختلف شيلي علامة «اتأكد إن صف جديد ظهر أول القايمة»."),
    (r"المتغير «([^»]+)» لسه ما اتحفظش", "setup", "متغير مش موجود",
     "الخطوة بتستخدم {{var:{1}}} وهو لسه ما اتحفظش.",
     "اتأكدي إن خطوة «احفظ قيمة في متغير» قبلها، أو إن الشاشة اللي بتعمله في «شغّل قبلها»."),
    (r"(كلمة المرور غير صحيحة|اسم المستخدم او كلمة المرور|login failed|فشل تسجيل الدخول|مقدرتش أسجل دخول)", "setup", "تسجيل الدخول للـ ERP",
     "الاختبار ما قدرش يدخل موقع الـ ERP.",
     "راجعي اسم المستخدم وكلمة السر في الإعدادات ← مواقع الاختبار (أو .env)."),
]


def for_run(message, log_lines=()):
    """the failure message first (it is precise); the end of the log only if the message says nothing"""
    return explain(message) or explain("\n".join(list(log_lines)[-60:]))


def explain(text):
    """rule-based explanation of a failure message / log tail"""
    t = text or ""
    for pat, kind, title, why, fix in RULES:
        m = re.search(pat, t, re.I)
        if m:
            g = (m.group(1) if m.groups() else "") or ""
            g = g.strip()[:150]
            label, color = KIND[kind]
            return {"kind": kind, "kind_label": label, "color": color, "title": title,
                    "why": why.replace("{1}", g), "fix": fix.replace("{1}", g), "source": "rules"}
    return None


# ---------------- AI (optional) ----------------
def _api_key():
    from web import settings_helper as sh
    return (sh.load_site_config().get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY", "")).strip()


def ai_available():
    return bool(_api_key())


def _cache(run_id):
    d = paths.RUNS_DIR / "explain"
    d.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w.-]", "_", run_id)
    return d / f"{safe}.json"


def cached_ai(run_id):
    f = _cache(run_id)
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def ask_ai(run_id, message, log_lines, screenshot_path=None):
    key = _api_key()
    if not key:
        raise RuntimeError("مفيش مفتاح Claude API — ضيفيه من الإعدادات")
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    tail = "\n".join(log_lines[-120:])[-12000:]
    prompt = (
        "إنت مهندس اختبار لنظام ERP عربي (NQ ERP، ASP.NET MVC). اختبار آلي (Selenium) فشل.\n"
        "اشرح بالعامية المصرية وباختصار: إيه اللي حصل، وهل ده bug في النظام ولا مشكلة في إعداد الاختبار ولا بيانات ولا شبكة، "
        "وإيه الحل بالظبط. رد JSON بس بالشكل ده: "
        '{"kind": "bug|setup|data|env", "title": "...", "why": "...", "fix": "..."}\n\n'
        f"رسالة الفشل:\n{message[:3000]}\n\nآخر اللوج:\n{tail}")
    content = [{"type": "text", "text": prompt}]
    if screenshot_path and os.path.exists(screenshot_path):
        content.insert(0, {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                       "data": base64.b64encode(open(screenshot_path, "rb").read()).decode()}})
    body = json.dumps({"model": model, "max_tokens": 700, "messages": [{"role": "user", "content": content}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode())
    text = "".join(c.get("text", "") for c in data.get("content", []) if c.get("type") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    try:
        out = json.loads(m.group(0)) if m else {}
    except Exception:
        out = {}
    kind = out.get("kind") if out.get("kind") in KIND else "unknown"
    res = {"kind": kind, "kind_label": KIND[kind][0], "color": KIND[kind][1], "title": out.get("title") or "شرح الذكاء الاصطناعي",
           "why": out.get("why") or text[:800], "fix": out.get("fix") or "", "source": "ai", "model": model}
    _cache(run_id).write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    return res
