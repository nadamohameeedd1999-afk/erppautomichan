"""
📚 مكتبة الاختبارات الجاهزة لـ NQ ERP — the 20 screens that matter most (money, stock, master data), with the
link they have on NQ ERP (found on the test site's menu) and the right automatic test for each, ready in one click.
«apply» = the screen is added to the project's screens if it isn't there yet + its automatic test is saved
(add -> edit -> print -> delete on the same record, stubborn tester on). Nothing runs until you press run;
on a client's live system the read-only guard stops any save anyway.
"""
from config.screens_catalog import all_pages, discovered, save_discovered

ALL = ["add", "edit", "print", "delete"]

# key, name, link on NQ ERP, cycle, risk (1 = highest), ways, note
LIBRARY = [
    ("sales_invoice", "فواتير البيع", "/SalesInvoice", "🛒 المبيعات", 1, ALL, "فيها جدول أصناف — لو الحفظ اترفض لعدم وجود صنف سجّلي خطوة «إضافة صنف» مرة من منشئ الاختبارات"),
    ("sales_return", "مرتجع البيع", "/SalesReturn", "🛒 المبيعات", 2, ALL, "بيحتاج فاتورة بيع قبله"),
    ("sales_order", "أوامر البيع", "/SalesOrder", "🛒 المبيعات", 2, ALL, "فيها جدول أصناف"),
    ("sales_quotation", "عرض سعر بيع", "/SalesQuotation", "🛒 المبيعات", 3, ALL, ""),
    ("cash_receipt", "سند القبض", "/CashReceiptVoucher", "💰 الخزينة", 1, ALL, ""),
    ("multi_customer_receipt", "سند قبض متعدد العملاء", "/MultiCustomerReceiptVoucher", "💰 الخزينة", 2, ALL, ""),
    ("cash_issue", "سند الدفع", "/CashIssueVoucher", "💰 الخزينة", 1, ALL, ""),
    ("cash_transfers", "التحويلات المالية", "/CashTransfers", "💰 الخزينة", 2, ALL, "على موقع الاختبار فيه تحويل اتسجل بطرف واحد (قيد مش متزن) — الاختبار ده بيكشفه لو اتكرر"),
    ("journal_manual", "قيود التسوية اليدوية", "/JournalEntries?type=1", "📒 الحسابات", 1, ALL, "بعد الحفظ شغّلي «⚖️ الحسابات» عشان تتأكدي إن القيد متزن"),
    ("utility_bill", "فاتورة خدمية", "/UtilityBill", "📒 الحسابات", 3, ALL, ""),
    ("purchase_request", "طلب شراء", "/PurchaseRequest", "📥 المشتريات", 3, ALL, ""),
    ("purchase_order", "أوامر الشراء", "/PurchaseOrder", "📥 المشتريات", 2, ALL, "فيها جدول أصناف"),
    ("purchase_invoice", "فواتير الشراء", "/PurchaseInvoice", "📥 المشتريات", 1, ALL, "فيها جدول أصناف"),
    ("purchase_return", "مرتجع الشراء", "/PurchaseReturn", "📥 المشتريات", 2, ALL, "بيحتاج فاتورة شراء قبله"),
    ("stock_receipt", "سندات استلام المخازن", "/StockReceiptVoucher", "📦 المخازن", 1, ALL, "على موقع الاختبار فيه سندات استلام اتسجل قيدها بطرف واحد — بعد الحفظ شغّلي «⚖️ الحسابات»"),
    ("stock_issue", "سندات صرف المخازن", "/StockIssueVoucher?type=1", "📦 المخازن", 1, ALL, "نفس ملاحظة الاستلام: قيد بطرف واحد اتكرر على موقع الاختبار"),
    ("stock_transfer", "سندات تحويل المخازن", "/StockTransferVoucher", "📦 المخازن", 2, ALL, ""),
    ("customers", "العملاء", "/Customers", "🗂️ البيانات الأساسية", 2, ALL, ""),
    ("vendors", "الموردين", "/Vendor", "🗂️ البيانات الأساسية", 2, ALL, ""),
    ("items", "الأصناف", "/Item", "🗂️ البيانات الأساسية", 2, ALL, ""),
]


def _u(url):
    return (url or "").split("#")[0].lower().rstrip("/")


def screen_key_for(url):
    """the project's screen key for this link (catalog / discovered), or None"""
    want = _u(url)
    for k, p in all_pages().items():
        if _u(p.get("url")) == want:
            return k
    return None


def items(autos=None, last=None, menu_paths=None):
    """the library + where each item stands: on the site's menu? test saved? last result"""
    autos, last = autos or {}, last or {}
    menu = {_u(p) for p in (menu_paths or [])}
    out = []
    for key, name, url, cycle, risk, ways, note in LIBRARY:
        sk = screen_key_for(url)
        a = autos.get(sk) if sk else None
        out.append({"key": key, "name": name, "url": url, "cycle": cycle, "risk": risk, "ways": ways, "note": note,
                    "screen": sk, "in_menu": (_u(url) in menu) if menu else None,
                    "test": a["key"] if a else None, "last": last.get(a["key"]) if a else None})
    return out


def ensure_screen(key):
    """make sure the library screen exists in the project's screens -> its screen key"""
    it = next((x for x in LIBRARY if x[0] == key), None)
    if not it:
        raise KeyError(key)
    sk = screen_key_for(it[2])
    if sk:
        return sk, it
    ds = discovered()
    sk = "lib_" + key
    ds.append({"key": sk, "name": it[1], "url": it[2], "group": it[3]})
    save_discovered(ds)
    return sk, it
