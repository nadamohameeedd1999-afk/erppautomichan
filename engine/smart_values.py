"""
Smart test values (قيم ذكية): a realistic value from the field's name, so validation passes and the
data looks real — a new value every run.

  السجل التجاري  -> 10 digits          الرقم الضريبي -> 15 digits starting and ending with 3
  الجوال / الهاتف -> 05xxxxxxxx         البريد       -> test1234@example.com
  الرمز البريدي  -> 5 digits           رقم المبنى / الرقم الفرعي -> 4 digits
  رقم الهوية / الإقامة -> 10 digits    الآيبان      -> SA + 22 digits
  الاسم -> اختبار آلي ####             العنوان / الشارع -> شارع الاختبار ##
  المبلغ / السعر -> 100..999           الكمية -> 1..5      النسبة -> 5..15
  ملاحظات / البيان -> اختبار آلي <time>   رقم المرجع -> REF-<time>
"""
import random
import re
from datetime import datetime

from engine.text_match import normalize


def _d(n):
    return "".join(random.choice("0123456789") for _ in range(n))


RULES = [
    # (words in the label / id, generator)
    (("سجل تجاري", "السجل التجاري", "commercialregistration", "commercial", "crno", "cr_no"), lambda: "10" + _d(8)),
    (("رقم ضريبي", "الرقم الضريبي", "ضريبي", "vatnumber", "vat_no", "vatno", "taxnumber", "tax_no", "trn"), lambda: "3" + _d(13) + "3"),
    (("رمز بريدي", "الرمز البريدي", "postal", "zip", "postcode"), lambda: _d(5)),
    (("جوال", "موبايل", "mobile", "phone", "هاتف", "تليفون", "tel"), lambda: "05" + _d(8)),
    (("بريد الكتروني", "البريد", "ايميل", "email", "e-mail", "mail"), lambda: f"test{_d(4)}@example.com"),
    (("رقم المبني", "رقم المبنى", "building"), lambda: str(random.randint(1000, 9999))),
    (("رقم فرعي", "الرقم الفرعي", "additional"), lambda: str(random.randint(1000, 9999))),
    (("هويه", "هوية", "اقامه", "إقامة", "nationalid", "iqama", "identity"), lambda: random.choice("12") + _d(9)),
    (("ايبان", "آيبان", "iban"), lambda: "SA" + _d(22)),
    (("رقم مرجع", "المرجع", "reference", "refno", "ref_no"), lambda: "REF-" + datetime.now().strftime("%H%M%S")),
    (("ملاحظات", "ملاحظه", "البيان", "بيان", "وصف", "notes", "remark", "description", "desc"),
     lambda: "اختبار آلي " + datetime.now().strftime("%Y-%m-%d %H:%M")),
    (("عنوان", "شارع", "حي", "address", "street", "district"), lambda: f"شارع الاختبار {random.randint(1, 99)}"),
    (("كميه", "كمية", "qty", "quantity"), lambda: str(random.randint(1, 5))),
    (("نسبه", "نسبة", "percent", "rate"), lambda: str(random.randint(5, 15))),
    (("مبلغ", "قيمه", "قيمة", "سعر", "تكلفه", "تكلفة", "amount", "price", "cost", "value"), lambda: str(random.randint(100, 999))),
    (("اسم", "name"), lambda: f"اختبار آلي {_d(4)}"),
]


def guess(label="", field_id=""):
    """the rule that fits this field, or None"""
    split_id = re.sub(r"([a-z])([A-Z])", r"\1 \2", field_id or "")      # CustomerName -> Customer Name
    hay = f" {normalize(label)} {normalize(split_id)} {(field_id or '').lower()} "
    tokens = set(re.split(r"[\s_\-:./]+", hay))
    for words, gen in RULES:
        for w in words:
            nw = normalize(w)
            # short words (حي، tel، trn…) must be a whole word, not part of another one
            if (len(nw) <= 4 and nw in tokens) or (len(nw) > 4 and nw in hay):
                return gen
    return None


def value_for(field):
    """a value for the field, or "" if its name says nothing (then the caller uses a unique value)"""
    gen = guess(field.get("label", ""), field.get("id", ""))
    return gen() if gen else ""


def describe(label="", field_id=""):
    gen = guess(label, field_id)
    return gen() if gen else None
