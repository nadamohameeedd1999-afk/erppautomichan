"""
Where a problem comes from — so only the system's own problems go to the developers.

  🏢 erp  : NQ ERP itself answered with it (its message / server error / wrong numbers / slow after opening)
  👤 data : the system works, the site lacks data, a permission or a setting (empty list, no permission, needs a filter)
  🌐 net  : this computer's internet / the site didn't answer at all (Chrome's ERR_… messages)
  🛠️ tool : the testing tool / the browser couldn't do the step (Selenium messages, «couldn't find / read …»)
  📋 work : too much work on one employee (the company's own organisation)
"""
import re

SOURCES = {
    "erp": {"icon": "🏢", "name": "سيستم NQ ERP", "hint": "مشاكل في السيستم نفسه — دي اللي تتبعت للمطورين", "color": "#C53030"},
    "data": {"icon": "👤", "name": "بيانات / إعداد / صلاحيات", "hint": "السيستم شغال — الموقع ناقصه بيانات أو صلاحية أو إعداد يتظبط من الشاشات", "color": "#B7791F"},
    "net": {"icon": "🌐", "name": "النت / الجهاز", "hint": "الموقع ما ردّش خالص من الجهاز ده — مش عيب في السيستم", "color": "#2B6CB0"},
    "tool": {"icon": "🛠️", "name": "أداة الاختبار", "hint": "الأداة ما عرفتش تعمل الخطوة — مش عيب في السيستم، تتبعت لمطور الأداة", "color": "#6B46C1"},
    "work": {"icon": "📋", "name": "ضغط الشغل", "hint": "تنظيم الشغل بين الموظفين", "color": "#4A5568"},
}
ORDER = ["erp", "data", "net", "tool", "work"]

NET = re.compile(r"ERR_INTERNET|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION|ERR_NETWORK|ERR_TIMED_OUT|ERR_ADDRESS_UNREACHABLE|ERR_PROXY|"
                 r"النت فصل|الموقع مش بيرد|مش واصل للنت", re.I)
TOOL = re.compile(r"element not interactable|NoSuchElement|no such element|stale element|session not created|chromedriver|Chrome binary|"
                  r"WebDriver|InvalidSession|NoSuchWindow|javascript error|Selenium|الأداة|الأداه|مقدرتش (أقرا|أفتح|ألاقي|أدوس)|"
                  r"مالقيتش (زرار|رقم|حقول|لينك|صف)|ما سمحتش بالكتابة|Chrome مش متسطب|نسخة Chrome|"
                  r"مفيش خطأ تقني من الـ ERP|مفيش رسالة خطأ ظاهرة|سجّلي الشاشة بإيدك|مش موجود في الصفحة دي", re.I)
DATA = re.compile(r"مفيش ولا (خيار|اختيار)|بيانات أساسية ناقصة|صلاحي|مش في منيو|محتاج يختار فلتر|مش متربطة|مالوش مستخدم|القايمة فاضية|"
                  r"لا توجد بيانات لتفاصيل|تجاوز الحد الائتماني للمندوب|لا يمكن تعديل (المستودع|المخزن|الفرع)|اختر العميل اول|برجاء ادخال التفاصيل|قم بإضافة علي الأقل عنصر|مطلوب\b|"
                  r"permission|access denied|غير مصرح|Unauthori[sz]ed|/Home/Unauthor", re.I)


def classify(typ, text="", evidence="", tool=False):
    """-> erp | data | net | tool | work"""
    head, t = f"{typ} {text}", f"{typ} {text} {evidence}"     # the message decides; the evidence (long logs) only for net / data
    if typ == "ضغط شغل":
        return "work"
    if NET.search(t):
        return "net"
    if tool or TOOL.search(head):
        return "tool"
    if typ == "صلاحيات" or DATA.search(head) or DATA.search(str(evidence).split("\n")[0]):
        return "data"
    ev = str(evidence)
    if re.search(r"حقول إجبارية لسه فاضية", ev) and re.search(r"محتاج يتملى ومقدرتش: مفيش ولا (خيار|اختيار)", ev) \
            and not re.search(r"\b5\d\d\b|Exception|خطأ سيرفر|ReferenceError|TypeError|SweetAlert", ev):
        return "data"                                          # a required list the site left empty: fill it from the screens
    return "erp"


def label(src):
    s = SOURCES.get(src) or SOURCES["erp"]
    return f"{s['icon']} {s['name']}"


def problem_key(screen, text):
    """one problem across days and pages: the screen + its text with the numbers blanked («فتحت في 12.3 ث» = «فتحت في 14.1 ث»)"""
    return f"{screen}|{re.sub(r'[0-9.,:]+', '#', str(text or ''))[:90]}"
