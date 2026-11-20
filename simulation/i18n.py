"""NQ Simulation in two languages: Arabic (the default) and English — names, screens and the voices."""
import re

ARABIC = re.compile(r"[؀-ۿ]")

NAMES = {"خالد": "Khaled", "أحمد": "Ahmed", "احمد": "Ahmed", "سارة": "Sarah", "ساره": "Sarah", "يوسف": "Youssef", "نورا": "Noura", "نورة": "Noura",
         "محمود": "Mahmoud", "عمر": "Omar", "منى": "Mona", "مني": "Mona", "هبة": "Hiba", "هبه": "Hiba", "محمد": "Mohamed", "علي": "Ali", "فاطمة": "Fatima",
         "مريم": "Mariam", "خديجة": "Khadija", "عبدالله": "Abdullah", "عبد الله": "Abdullah", "ريم": "Reem", "ليلى": "Laila", "سلمى": "Salma",
         "فهد": "Fahd", "سعد": "Saad", "ماجد": "Majed", "طارق": "Tarek", "كريم": "Karim", "حسن": "Hassan", "مصطفى": "Mostafa", "عبدو": "Abdo", "عبده": "Abdo"}

SCREENS = {"عروض الأسعار": "Quotations", "أوامر البيع": "Sales Orders", "كارت الصنف": "Item Card", "أوامر الشراء": "Purchase Orders",
           "سند استلام مخزني": "Stock Receipt", "فواتير الشراء": "Purchase Invoices", "سند صرف مخزني": "Stock Issue", "فواتير البيع": "Sales Invoices",
           "القيود اليومية": "Journal Entries", "اعتماد المستندات": "Document Approval", "سند القبض": "Receipt Voucher", "الحضور والانصراف": "Attendance",
           "جرد الخزينة": "Cash Count", "ميزان المراجعة": "Trial Balance", "تقرير المبيعات اليومي": "Daily Sales Report", "كشف حساب مفصل": "Detailed Account Statement",
           "كشف حساب عميل": "Customer Statement", "مرتجع البيع": "Sales Return", "طلب الشراء": "Purchase Request", "مرتجع الشراء": "Purchase Return",
           "سند الدفع": "Payment Voucher", "سند تحويل مخزني": "Stock Transfer", "قيد يومية": "Journal Entry", "فحص جاهزية الموقع": "Site Readiness Check",
           "اختبار الصلاحيات (المختلس)": "Permissions Test (the Embezzler)", "مراجعة مستندات اليوم": "Today's Documents Audit", "شاشة جديدة في المنيو": "New Menu Screen"}
DATA = {"مؤسسة الريادة": "Al-Riyada Est.", "شركة البناء الحديث": "Modern Building Co.", "مصنع الأمل": "Al-Amal Factory", "مجموعة الفيصل": "Al-Faisal Group",
        "شركة الأفق": "Al-Ofuq Co.", "مؤسسة النور للمقاولات": "Al-Noor Contracting", "خرسانة جاهزة 350": "ready-mix concrete 350", "أسمنت مقاوم": "resistant cement",
        "حديد تسليح 16 مم": "16 mm rebar", "بلوك أسمنتي": "cement blocks", "رمل مغسول": "washed sand", "مصنع الجزيرة": "Al-Jazeera Factory",
        "شركة اليمامة للحديد": "Al-Yamama Steel", "مؤسسة الخليج للتوريد": "Gulf Supply Est.", "شركة الجادة": "Al-Jadda Co."}
ACTIONS = {"تعديل ": "Edit ", "حذف ": "Delete ", "طباعة ": "Print ", "مراجعة ": "Review "}


def name_en(n):
    s = str(n or "")
    s = s.replace("أ. ", "Mr. ").replace("أ.", "Mr. ").replace("م. ", "Eng. ").replace("د. ", "Dr. ")
    for a, b in sorted(NAMES.items(), key=lambda x: -len(x[0])):
        s = s.replace(a, b)
    return s.strip()


def screen_en(n):
    s = str(n or "")
    if s in SCREENS:
        return SCREENS[s]
    for a, b in ACTIONS.items():
        if s.startswith(a) and s[len(a):] in SCREENS:
            return b + SCREENS[s[len(a):]]
    return s


def en(v):
    """a value going into an English sentence: a screen's or a person's Arabic name becomes English (other data stays as the system has it)"""
    s = str(v)
    if s in DATA:
        return DATA[s]
    t = screen_en(s)
    return t if t != s else name_en(s)


# 🔊 English voices: each employee his own accent and pitch (US · UK · Australian · Irish · Indian · Canadian)
VOICE_EN = {
    "manager": ("en-GB-RyanNeural", "-6%", "-4Hz"), "sales2": ("en-US-GuyNeural", "+5%", "+2Hz"), "acc1": ("en-AU-WilliamNeural", "-2%", "-2Hz"),
    "wh1": ("en-US-DavisNeural", "+0%", "-8Hz"), "pur1": ("en-IE-ConnorNeural", "+3%", "+3Hz"),
    "sales1": ("en-US-JennyNeural", "+4%", "+3Hz"), "acc2": ("en-GB-SoniaNeural", "+0%", "+0Hz"), "cash1": ("en-AU-NatashaNeural", "-2%", "-3Hz"),
    "hr1": ("en-US-AriaNeural", "+3%", "+5Hz"), "it1": ("en-IN-PrabhatNeural", "+2%", "+0Hz"),
}
SPARE_EN_M = ["en-IN-PrabhatNeural", "en-CA-LiamNeural", "en-US-ChristopherNeural", "en-GB-ThomasNeural"]
SPARE_EN_F = ["en-IN-NeerjaNeural", "en-CA-ClaraNeural", "en-US-MichelleNeural", "en-GB-LibbyNeural"]


def voice_en(eid, female):
    if eid in VOICE_EN:
        return VOICE_EN[eid]
    h = sum(ord(c) * (i + 7) for i, c in enumerate(str(eid)))
    pool = SPARE_EN_F if female else SPARE_EN_M
    return pool[h % len(pool)], f"{(h % 11) - 5:+d}%", f"{(h % 13) - 6:+d}Hz"
