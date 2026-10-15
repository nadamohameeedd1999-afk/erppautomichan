"""
Cash Receipt Voucher — القيم الفعلية من الموقع
"""


class CashReceiptDefaults:
    # ===== الحقول الإجبارية بالترتيب =====
    SOURCE_TYPE = None  # None = أول خيار (عميل)
    CUSTOMER = "4 - هوليداى ان العليا"
    PROJECT = "23 - مشروع بناء برج الرياض"
    PAYMENT_METHOD = "1 - نقدى"
    MONEY_AMOUNT = "200"