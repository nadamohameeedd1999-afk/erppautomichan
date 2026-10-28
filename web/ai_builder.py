"""
«اوصفي الاختبار بالكلام» — turn a sentence like
    «فاتورة لعميل الريادة فيها صنفين حديد وأسمنت، خصم 10%، والملاحظات تجربة»
into values for the fields the builder already read from the screen.

  build(description, fields)  -> {"fields": [{id, strategy, value, why}], "items": [{name, qty, price}],
                                  "expect_error": "", "row_contains": [], "notes": "", "source": "ai" | "rules",
                                  "unmatched": [...], "warning": ""}
With a Claude key (Settings) Claude reads the sentence; without it a simple Arabic matcher does the obvious parts.
"""
import json
import re

from engine.text_match import normalize as N

_NUM_AR = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")
_COUNT = {"صنف": 1, "صنف واحد": 1, "صنفين": 2, "اتنين": 2, "تلات": 3, "ثلاث": 3, "تلاته": 3, "ثلاثه": 3, "اربع": 4, "خمس": 5}


def _core(option):
    """'11 - الريادة' -> 'الريادة'"""
    return re.sub(r"^\s*[\w\-]{1,12}\s*[-–:]\s*", "", str(option or "")).strip()


def _label_variants(label):
    n = N(label)
    out = {n}
    if n.startswith("ال") and len(n) > 4:
        out.add(n[2:])
    return [x for x in out if len(x) >= 2]


_FLEX = {"ا": "[اأإآٱ]", "ي": "[يىئ]", "ه": "[هة]", "و": "[وؤ]"}


def _flex(norm):
    """regex that finds a normalized word in the original text (أ/ا ى/ي ة/ه …)"""
    return "".join(_FLEX.get(ch, re.escape(ch)) + "ـ*" for ch in norm)


def rules(description, fields):
    orig = str(description or "").translate(_NUM_AR)
    text = N(orig)
    out, used, unmatched = [], set(), []
    # 1) a list option written in the sentence («الريادة» -> العميل = 11 - الريادة)
    for f in fields:
        if f.get("kind") not in ("select", "select2"):
            continue
        best, part = None, None
        for o in f.get("options") or []:
            c = N(_core(o))
            if len(c) >= 3 and c in text and (best is None or len(c) > len(N(_core(best)))):
                best = o
        if not best:                     # «هوليداي إن» for «هوليداي إن العليا»: the first words are enough
            for o in f.get("options") or []:
                words = [w for w in N(_core(o)).split() if len(w) >= 3]
                if words and len(words[0]) >= 4 and " ".join(words[:2]) in text:
                    part = part or o
            best = part
        if best:
            out.append({"id": f["id"], "strategy": "fixed", "value": best, "why": f"«{_core(best)}» مكتوبة في الوصف"})
            used.add(f["id"])
    # 2) «<label> <value>»: numbers for number fields, a phrase for text fields
    for f in fields:
        if f["id"] in used:
            continue
        for lv in _label_variants(f.get("label") or f["id"]):
            m = re.search(_flex(lv) + r"\s*(?:=|:|(?:هو|هي)\s|بـ)?\s*([^،,.\n]+)", orig)
            if not m:
                continue
            val = m.group(1).strip()
            val = re.split(r"\s+و(?=\S)|\s+(?:فيها|فيه|مع)\s", val)[0].strip()
            if f.get("kind") in ("number",) or re.fullmatch(r"[\d.,%]+", val.split(" ")[0] or ""):
                num = re.search(r"-?\d+(?:[.,]\d+)?", val)
                if not num:
                    continue
                val = num.group(0).replace(",", "")
            if f.get("kind") in ("select", "select2"):
                out.append({"id": f["id"], "strategy": "search", "value": val, "why": f"بعد «{lv}»"})
            elif f.get("kind") == "checkbox":
                continue
            else:
                out.append({"id": f["id"], "strategy": "fixed", "value": val, "why": f"بعد «{lv}»"})
            used.add(f["id"])
            break
    # 3) items: «صنفين حديد وأسمنت» / «3 أصناف» / «صنف حديد سعره 50»
    items = []
    m = re.search(r"(\d+)\s*(?:اصناف|صنف)", text)
    count = int(m.group(1)) if m else 0
    for w, n in _COUNT.items():
        if re.search(r"(?<!\S)" + w + r"(?!\S)", text):
            count = max(count, n)
    names = []
    mm = re.search(r"(?:صنفين|اصناف|صنف)\s+([^،,.\n]+)", text)
    if mm:
        names = [x.strip() for x in re.split(r"\s+و|\s*,\s*|\s*،\s*", mm.group(1)) if x.strip() and not re.match(r"^\d", x.strip())][:6]
        names = [re.split(r"\s+(?:سعر|بسعر|كميه|خصم)", x)[0].strip() for x in names]
    price = re.search(r"(?:سعر|بسعر|السعر)\s*(\d+(?:\.\d+)?)", text)
    count = max(count, len(names))
    for i in range(count):
        items.append({"name": names[i] if i < len(names) else "", "qty": "1", "price": price.group(1) if price else "100"})
    expect = ""
    me = re.search(r"(?:المفروض|لازم)\s+(?:يرفض|يترفض|ميحفظش)[^«\"]*[«\"]([^»\"]+)[»\"]", str(description or ""))
    if me:
        expect = me.group(1).strip()
    if not out and not items:
        unmatched.append("مالقيتش أسماء حقول أو قيم من القوائم في الوصف")
    return {"fields": out, "items": items, "expect_error": expect, "row_contains": [], "notes": "", "source": "rules",
            "unmatched": unmatched}


PROMPT = """إنت بتبني اختبار آلي لشاشة في نظام ERP عربي. ده وصف الاختبار من المستخدم:
«{desc}»

دي حقول الشاشة (id، الاسم، النوع، وأول اختيارات القوايم):
{fields}

رجّع JSON بس (من غير شرح) بالشكل ده:
{{"fields": [{{"id": "<id من فوق بالظبط>", "strategy": "fixed|search|first|random|today|unique|smart|keep", "value": "<القيمة>", "why": "<ليه باختصار>"}}],
  "items": [{{"name": "<اسم الصنف أو فاضي>", "qty": "1", "price": "100"}}],
  "expect_error": "<لو الوصف بيقول الحفظ المفروض يترفض: نص الرسالة، غير كده فاضي>",
  "row_contains": ["<نص لازم يظهر في صف القايمة بعد الحفظ لو مذكور>"],
  "notes": "<حاجة في الوصف مش قادر تعملها بالحقول دي>"}}
قواعد: في القوايم لو القيمة موجودة في الاختيارات اكتبها زي ما هي بالظبط واستخدم fixed، لو مش متأكد استخدم search بكلمة منها.
التواريخ: {{today}} {{month_start}} {{today-30}}. قيمة مختلفة كل مرة: unique بقيمة زي "عميل {{ts}}".
ماتحطش حقول الوصف ماذكرهاش."""


def build(description, fields):
    description = str(description or "").strip()
    if not description:
        raise ValueError("اكتبي وصف الاختبار الأول")
    fields = [f for f in fields or [] if f.get("id") and f.get("kind") != "action"]
    from web import explain
    base = rules(description, fields)
    if not explain.ai_available():
        base["warning"] = "من غير مفتاح Claude — استخدمت مطابقة بسيطة للكلام. حطي المفتاح في الإعدادات عشان يفهم الوصف أحسن."
        return base
    lines = "\n".join(f"- {f['id']} | {f.get('label') or ''} | {f.get('kind')}"
                      + (f" | اختيارات: {', '.join(map(str, (f.get('options') or [])[:25]))}" if f.get("options") else "") for f in fields[:80])
    try:
        data = explain._call(explain._api_key(), explain._model(),
                             [{"type": "text", "text": PROMPT.format(desc=description[:2000], fields=lines)}], max_tokens=1500, timeout=90)
    except Exception as e:
        base["warning"] = f"Claude مردش ({e}) — استخدمت المطابقة البسيطة"
        return base
    text = "".join(c.get("text", "") for c in data.get("content", []) if c.get("type") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    try:
        out = json.loads(m.group(0)) if m else {}
    except Exception:
        out = {}
    ids = {f["id"]: f for f in fields}
    from engine.screen_config import STRATEGIES
    clean = []
    for x in out.get("fields") or []:
        if x.get("id") in ids and x.get("strategy", "fixed") in STRATEGIES:
            clean.append({"id": x["id"], "strategy": x.get("strategy") or "fixed", "value": str(x.get("value") or ""),
                          "why": str(x.get("why") or "")[:120]})
    if not clean and not out.get("items"):
        base["warning"] = "Claude مافهمش الوصف — استخدمت المطابقة البسيطة"
        return base
    return {"fields": clean, "items": [{"name": str(i.get("name") or ""), "qty": str(i.get("qty") or "1"), "price": str(i.get("price") or "100")}
                                       for i in (out.get("items") or [])[:10]],
            "expect_error": str(out.get("expect_error") or ""), "row_contains": [str(x) for x in out.get("row_contains") or [] if x][:5],
            "notes": str(out.get("notes") or ""), "source": "ai", "unmatched": [], "model": explain._model()}
