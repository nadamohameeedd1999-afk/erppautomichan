"""
🌐 Lists the Arabic phrases of the dashboard that have no English yet (web/i18n/ar_en.json).
Run from the project folder:   python tools/i18n_extract.py            -> prints the missing phrases
Add each one to ar_en.json ("Arabic": "English") and the English view shows it.
"""
import re, glob, io, tokenize, json, sys
AR = re.compile(r"[؀-ۿ][؀-ۿً-ْ «»،؟:\-–—…/()0-9٠-٩%.,!?ـ+×÷]*[؀-ۿ»)؟]|[؀-ۿ]")
segs = {}
def add(text, src):
    for m in AR.findall(text):
        m = m.strip()
        if len(m) >= 2 or m in ("و",):
            segs.setdefault(m, set()).add(src)
for f in sorted(glob.glob("web/templates/**/*.html", recursive=True) + glob.glob("web/static/js/*.js")):
    s = open(f, encoding="utf-8").read()
    s = re.sub(r"\{#.*?#\}", "", s, flags=re.S); s = re.sub(r"<!--.*?-->", "", s, flags=re.S)
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S); s = re.sub(r"(?m)^\s*//.*$", "", s)
    s = re.sub(r"(?m)\s//\s.*$", "", s)
    add(s, f)
for f in sorted(glob.glob("web/*.py") + ["engine/risk.py", "engine/readiness.py", "engine/explain.py", "engine/api_check.py", "engine/reconcile.py", "engine/sod.py", "engine/journal_check.py", "engine/test_library.py", "engine/biz_sales_invoice.py", "engine/biz_cases.py", "engine/biz_addons.py", "engine/biz_report.py", "web/pdf_reports.py", "utils/pdf.py"] ):
    try: src = open(f, encoding="utf-8").read()
    except FileNotFoundError: continue
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except Exception as e:
        print("skip", f, e, file=sys.stderr); continue
    for t in toks:
        if t.type == tokenize.STRING:
            v = t.string
            if v.lstrip("rbfuRBFU").startswith(('"""', "'''")): continue
            add(v, f)
        elif t.type == getattr(tokenize, "FSTRING_MIDDLE", -1):
            add(t.string, f)
keys = sorted(segs, key=lambda k: (-len(segs[k]), k))
have = json.load(open("web/i18n/ar_en.json", encoding="utf-8"))
missing = [k for k in keys if k not in have and not re.fullmatch(r"[أإآاةهىيوؤئٱ]{2,6}|[٠-٩٫٬]+", k) and "-" not in k[:3] and k != "العربية"]
if len(sys.argv) > 1:
    json.dump(missing, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(f"{len(missing)} phrase(s) without English")
for k in missing:
    print(" ", k)
