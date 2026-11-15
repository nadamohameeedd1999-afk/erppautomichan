"""
📥 التأكد من نقل الأرصدة الافتتاحية — the balances that came from the client's old system (Excel) against the same
balances exported from NQ ERP (trial balance / customer / supplier balances / item balances report → Excel), row by row.
(The idea of Tricentis Data Integrity: the data migration is checked, not trusted.)

  • the header row and the columns are found by their names (كود / اسم / مدين / دائن / رصيد / كمية / تكلفة …);
    a wrong guess can be corrected by picking the column
  • value = the «رصيد» column, or مدين − دائن; quantity / cost too for items
  • rows are matched by code (leading zeros and spaces ignored), then by name for rows with no code
  • result: same · different (by more than the tolerance) · in the old system only · in NQ ERP only, and the totals of
    both sides (and whether the old file itself is balanced: debit = credit)
"""
import csv
import io
import json
import re
from datetime import datetime

from config import paths

KINDS = {"accounts": "أرصدة الحسابات (ميزان المراجعة)", "customers": "أرصدة العملاء", "suppliers": "أرصدة الموردين", "items": "أرصدة الأصناف (كميات وتكلفة)"}
COLS = {
    "code": r"^(?:ال)?كود|رقم (?:ال)?(?:حساب|عميل|مورد|صنف)|^(?:ال)?رقم$|code|account\s*(?:no|number|#)|acc(?:ount)?\s*id|item\s*(?:no|code)|^no\.?$|^id$",
    "name": r"^(?:ال)?اسم|البيان|الوصف|اسم (?:ال)?(?:حساب|عميل|مورد|صنف)|name|description|title",
    "debit": r"مدين|debit|^dr\.?$",
    "credit": r"دائن|credit|^cr\.?$",
    "balance": r"(?:ال)?رصيد|balance|^net$|closing",
    "qty": r"(?:ال)?كمي[ةه]|qty|quantity|on\s*hand",
    "value": r"(?:ال)?تكلف[ةه]|(?:ال)?قيم[ةه]|cost|value|amount",
}
COL_AR = {"code": "الكود", "name": "الاسم", "debit": "مدين", "credit": "دائن", "balance": "الرصيد", "qty": "الكمية", "value": "التكلفة / القيمة"}


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,"))
    neg = s.startswith("(") and s.endswith(")") or s.endswith("-")
    s = re.sub(r"[^\d.\-]", "", s.replace(",", ""))
    if s in ("", "-", ".", "-."):
        return None
    try:
        x = float(s)
    except ValueError:
        return None
    return -abs(x) if neg else x


def read_rows(data, filename):
    """[[cell, …], …] of the first sheet (xlsx) or the csv"""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = [[c for c in r] for r in ws.iter_rows(values_only=True)]
        wb.close()
        return rows
    if name.endswith(".csv") or name.endswith(".txt"):
        txt = data.decode("utf-8-sig", "ignore")
        dialect = csv.Sniffer().sniff(txt[:4000], delimiters=",;\t") if txt.strip() else csv.excel
        return [r for r in csv.reader(io.StringIO(txt), dialect)]
    raise ValueError("الملف لازم يكون Excel (xlsx) أو CSV")


def detect(rows):
    """(header_index, headers, mapping {field: col})"""
    best, best_i = None, 0
    for i, r in enumerate(rows[:25]):
        cells = [str(c or "").strip() for c in r]
        m = guess(cells)
        score = len(m) + (2 if "code" in m or "name" in m else 0)
        if best is None or score > best[0]:
            best, best_i = (score, cells, m), i
    if not best or best[0] < 2:
        raise ValueError("مالقيتش صف العناوين (كود / اسم / مدين / دائن / رصيد …) في أول 25 سطر")
    return best_i, best[1], best[2]


def guess(cells):
    m = {}
    for f, rx in COLS.items():
        for j, h in enumerate(cells):
            if j in m.values() or not h:
                continue
            if re.search(rx, h, re.I):
                if f == "balance" and re.search(COLS["debit"] + "|" + COLS["credit"], h, re.I) and not re.search(r"صافي|net", h, re.I):
                    continue                          # «رصيد مدين» = the debit column
                m[f] = j
                break
    for f, rx in (("debit", r"رصيد مدين|debit balance"), ("credit", r"رصيد دائن|credit balance")):
        if f not in m:
            j = next((j for j, h in enumerate(cells) if re.search(rx, h, re.I)), None)
            if j is not None:
                m[f] = j
    return m


def _key(code):
    s = re.sub(r"\s+", "", str(code or "")).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    if isinstance(code, float) and code.is_integer():
        s = str(int(code))
    return s.lstrip("0").lower() or s.lower()


def _nkey(name):
    s = re.sub(r"[ً-ْـ]", "", str(name or "")).strip().lower()
    s = s.translate(str.maketrans("أإآةى", "اااهي"))
    return re.sub(r"\s+", " ", s)


def table(data, filename, mapping=None):
    rows = read_rows(data, filename)
    hi, headers, m = detect(rows)
    if mapping:
        m = {k: int(v) for k, v in mapping.items() if str(v).lstrip("-").isdigit() and int(v) >= 0}
    if "code" not in m and "name" not in m:
        raise ValueError("مالقيتش عمود الكود ولا الاسم — اختارهم بإيدك")
    if not ({"balance", "debit", "credit", "qty", "value"} & set(m)):
        raise ValueError("مالقيتش عمود رصيد ولا مدين / دائن ولا كمية — اختاره بإيدك")
    out = []
    for r in rows[hi + 1:]:
        cell = lambda f: (r[m[f]] if f in m and m[f] < len(r) else None)
        code, name = cell("code"), cell("name")
        if (code in (None, "") and name in (None, "")) or re.search(r"^(?:ال)?إجمال|^(?:ال)?اجمال|^total", str(name or code or ""), re.I):
            continue
        dr, cr, bal = _num(cell("debit")), _num(cell("credit")), _num(cell("balance"))
        if bal is None and (dr is not None or cr is not None):
            bal = (dr or 0) - (cr or 0)
        rec = {"code": "" if code is None else str(int(code) if isinstance(code, float) and code.is_integer() else code).strip(),
               "name": str(name or "").strip(), "debit": dr, "credit": cr, "balance": bal, "qty": _num(cell("qty")), "value": _num(cell("value"))}
        if all(rec[k] is None for k in ("balance", "qty", "value")):
            continue
        out.append(rec)
    return {"headers": headers, "mapping": m, "header_row": hi + 1, "rows": out}


def compare(src, erp, tol=0.01, kind="accounts"):
    def idx(t):
        by_code, by_name = {}, {}
        for r in t["rows"]:
            if r["code"]:
                by_code.setdefault(_key(r["code"]), r)
            elif r["name"]:
                by_name.setdefault(_nkey(r["name"]), r)
        return by_code, by_name
    sc, sn = idx(src)
    ec, en = idx(erp)
    erp_name = {_nkey(r["name"]): r for r in erp["rows"] if r["name"]}
    fields = [f for f in ("balance", "qty", "value") if any(r[f] is not None for r in src["rows"]) and any(r[f] is not None for r in erp["rows"])]
    if not fields:
        raise ValueError("الملفين مفيش بينهم عمود مشترك للمقارنة (رصيد / كمية / تكلفة)")
    rows, used = [], set()

    def diff_of(a, b):
        out = {}
        for f in fields:
            x, y = a.get(f) or 0.0, b.get(f) or 0.0
            if abs(x - y) > tol:
                out[f] = round(y - x, 4)
        return out
    for k, a in list(sc.items()) + [(None, r) for r in sn.values()]:
        b = ec.get(k) if k else None
        how = "الكود"
        if b is None and a["name"]:
            b = erp_name.get(_nkey(a["name"]))
            how = "الاسم"
        if b is None:
            rows.append({"status": "missing", "code": a["code"], "name": a["name"], "src": a, "erp": None, "diff": {}})
            continue
        used.add(id(b))
        d = diff_of(a, b)
        rows.append({"status": "diff" if d else "same", "code": a["code"] or b["code"], "name": a["name"] or b["name"], "src": a, "erp": b, "diff": d,
                     "by": how, "name_diff": bool(a["name"] and b["name"] and _nkey(a["name"]) != _nkey(b["name"]))})
    for r in erp["rows"]:
        if id(r) not in used and any((r.get(f) or 0) != 0 for f in fields):
            rows.append({"status": "extra", "code": r["code"], "name": r["name"], "src": None, "erp": r, "diff": {}})

    def tot(t, f):
        return round(sum((r.get(f) or 0) for r in t["rows"]), 2)
    totals = {f: {"src": tot(src, f), "erp": tot(erp, f)} for f in fields + [x for x in ("debit", "credit") if x not in fields]}
    src_bal = None
    if kind == "accounts" and any(r["debit"] is not None for r in src["rows"]):
        src_bal = abs(totals["debit"]["src"] - totals["credit"]["src"]) <= max(tol, 0.01)
    cnt = {s: sum(1 for r in rows if r["status"] == s) for s in ("same", "diff", "missing", "extra")}
    rows.sort(key=lambda r: ({"diff": 0, "missing": 1, "extra": 2, "same": 3}[r["status"]], -max([abs(v) for v in r["diff"].values()] or [0])))
    ok = cnt["diff"] == 0 and cnt["missing"] == 0 and cnt["extra"] == 0
    return {"fields": fields, "rows": rows, "totals": totals, "counts": cnt, "src_balanced": src_bal, "ok": ok,
            "name_diffs": sum(1 for r in rows if r.get("name_diff"))}


# ------------------------------------------------------------------ saved checks
def _dir():
    d = paths.STATE_DIR / "migration"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(res):
    rid = datetime.now().strftime("%Y%m%d%H%M%S")
    res["id"] = rid
    (_dir() / f"{rid}.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    for f in sorted(_dir().glob("*.json"))[:-30]:
        f.unlink()
    return res


def load(rid):
    try:
        return json.loads((_dir() / f"{re.sub(r'[^0-9]', '', rid)}.json").read_text(encoding="utf-8"))
    except Exception:
        return None


def all_runs():
    out = []
    for f in sorted(_dir().glob("*.json"), reverse=True):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append({k: d.get(k) for k in ("id", "at", "kind", "client", "src_file", "erp_file", "counts", "ok", "src_balanced")})
        except Exception:
            pass
    return out


ST_AR = {"same": "✅ مطابق", "diff": "❌ مختلف", "missing": "⚠️ ناقص في NQ", "extra": "➕ زيادة في NQ"}
F_AR = {"balance": "الرصيد", "qty": "الكمية", "value": "التكلفة"}


def _fmt(x):
    return "—" if x is None else f"{x:,.2f}"


def report_html(d, user=""):
    from web import pdf_reports as P
    c = d["counts"]
    body = [f"<div class='verdict {'ok' if d['ok'] else 'bad'}'>{'✅ النقل مطابق' if d['ok'] else '❌ فيه فروق'} · {c['same']} مطابق · {c['diff']} مختلف · "
            f"{c['missing']} ناقص في NQ · {c['extra']} زيادة في NQ</div>"]
    if d.get("src_balanced") is False:
        body.append("<p><b>⚠️ ملف النظام القديم نفسه مش متزن: إجمالي المدين ≠ إجمالي الدائن.</b></p>")
    body.append("<h2>الإجماليات</h2>" + P.table(["البند", "النظام القديم", "NQ ERP", "الفرق"],
                [[COL_AR.get(f, F_AR.get(f, f)), _fmt(v["src"]), _fmt(v["erp"]), _fmt(round(v["erp"] - v["src"], 2))] for f, v in d["totals"].items()], center=(1, 2, 3)))
    bad = [r for r in d["rows"] if r["status"] != "same"]
    cols = ["الحالة", "الكود", "الاسم"] + sum([[f"{F_AR[f]} القديم", f"{F_AR[f]} NQ", "الفرق"] for f in d["fields"]], [])
    body.append(f"<h2>الفروق ({len(bad)})</h2>" + (P.table(cols, [[ST_AR[r["status"]], r["code"] or "—", r["name"] or "—"]
                + sum([[_fmt((r["src"] or {}).get(f)), _fmt((r["erp"] or {}).get(f)), _fmt(r["diff"].get(f)) if r["diff"].get(f) is not None else "—"] for f in d["fields"]], [])
                for r in bad[:1500]], center=tuple(range(3, 3 + 3 * len(d["fields"])))) if bad else "<p>مفيش فروق 👍</p>"))
    return P.page("التأكد من نقل الأرصدة الافتتاحية", "Opening-balance migration check", user, "".join(body),
                  [("النوع", KINDS.get(d["kind"], d["kind"])), ("العميل", d.get("client") or "—"), ("النظام القديم", d.get("src_file")), ("NQ ERP", d.get("erp_file")),
                   ("السماحية", d.get("tol"))])


def report_xlsx(d):
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "الفروق"
    ws.sheet_view.rightToLeft = True
    head = ["الحالة", "الكود", "الاسم"] + sum([[f"{F_AR[f]} القديم", f"{F_AR[f]} NQ", "الفرق"] for f in d["fields"]], [])
    ws.append(head)
    for c in ws[1]:
        c.fill, c.font, c.alignment = PatternFill("solid", fgColor="0F7C7A"), Font(bold=True, color="FFFFFF"), Alignment(horizontal="center")
    for r in d["rows"]:
        ws.append([ST_AR[r["status"]], r["code"], r["name"]] + sum([[(r["src"] or {}).get(f), (r["erp"] or {}).get(f), r["diff"].get(f)] for f in d["fields"]], []))
    for col, w in zip("ABCDEFGHIJKL", [16, 14, 40] + [16] * 9):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2, min_col=4):
        for c in row:
            c.number_format = "#,##0.00"
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()
