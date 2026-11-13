"""
🧬 التوأم الرقمي — reads the ERP source code (ASP.NET MVC: controllers, views, JavaScript, DevExpress reports) and,
when a copy of the test database is connected, ties every screen to its stored procedures and tables:

  screen (controller) → its views → the requests its views / JS send (/Controller/Action) → its actions →
  the stored procedures its code calls → the tables those procedures read / write

and finds, before anyone runs anything:
  الشاشات     buttons / requests calling an action that does not exist in the controller (404), or a controller that does
              not exist at all (typo, leftover sample code)
  المنيو      menu links with an absolute address (localhost, another client's site, plain http), menu links to a page
              that does not exist
  الكود       stored procedures the C# code calls that are missing in the database; SQL built by concatenation in C#
              (injection risk)
  التقارير    reports calling a missing procedure, sending parameters the procedure does not take, total cells that use
              sum…() with no XRSummary
  الإجراءات   broken procedures (from the database audit) and the screens that call them; procedures nothing calls

Read only. The result is saved in state/code_twin.json (and can be exported / imported as JSON).
"""
import json
import os
import re
import time
import zipfile
from datetime import datetime

from utils.logger import logger

SEV = {"عالية": 0, "متوسطة": 1, "منخفضة": 2, "للعلم": 3}
MODULE_NAMES = {"FIN": "الحسابات العامة", "FR": "تقارير الحسابات", "FRE": "تقارير الحسابات", "WR": "تقارير المخازن", "SR": "تقارير المبيعات",
                "PR": "تقارير المشتريات", "HR": "الموارد البشرية", "HRR": "تقارير الموارد البشرية", "SAL": "المبيعات", "PUR": "المشتريات", "MAN": "التصنيع",
                "POS": "نقاط البيع", "CRM": "علاقات العملاء", "CAR": "خدمات السيارات", "MED": "الطبي", "FA": "الأصول الثابتة", "FAR": "تقارير الأصول",
                "PM": "المشاريع", "RM": "العقارات", "MC": "الصيانة", "QA": "الجودة", "TAIL": "التفصيل", "GLD": "الذهب", "GLDR": "تقارير الذهب",
                "CP": "الخرسانة", "CPE": "الخرسانة", "TRA": "التدريب", "LA": "الشؤون القانونية", "KPI": "مؤشرات الأداء", "AI": "الذكاء الاصطناعي",
                "BUD": "الموازنات", "GEN": "عام", "CashMan": "إدارة النقدية", "REV": "الإيرادات", "QUO": "عروض الأسعار", "PRO": "الإنتاج", "TEN": "المناقصات",
                "EM": "المعدات", "ADV": "الإعلانات", "APP": "الاعتمادات", "AR": "الأرشفة", "CAM": "الحملات", "SCA": "المسح الصناعي", "TD": "المهام",
                "RA": "التسويات", "RMD": "التذكيرات", "MQ": "الاستعلامات", "STSupport": "الدعم الفني", "Ecommerce": "المتجر الإلكتروني", "WAR": "المخازن"}
IGNORE_CTRL = {"api", "content", "scripts", "assets", "images", "img", "fonts", "dxxrdv", "uploads", "files", "js", "css", "lib", "libs", "signalr", "bundles", "dxr"}


def _state():
    from config import paths
    return paths.STATE_DIR / "code_twin.json"


def load():
    try:
        return json.loads(_state().read_text(encoding="utf-8"))
    except Exception:
        return None


def save(d):
    f = _state()
    f.parent.mkdir(parents=True, exist_ok=True)
    if f.exists():
        (f.parent / "code_twin_prev.json").write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    f.write_text(json.dumps(d, ensure_ascii=False, default=list), encoding="utf-8")


def F(area, sev, title, detail="", sample=None, count=None, fix="", screens=None, key=""):
    return {"area": area, "sev": sev, "title": title, "detail": detail, "sample": (sample or [])[:40], "count": count, "fix": fix,
            "screens": sorted(set(screens or []))[:400], "id": re.sub(r"\W+", "_", f"{area}_{key or title[:70]}")[:150]}


def _read(p):
    try:
        with open(p, encoding="utf-8-sig", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def find_root(path):
    """the folder that holds Controllers/ (the MVC project) inside an unpacked repository"""
    for d, dirs, _ in os.walk(path):
        if "Controllers" in dirs and ("Views" in dirs or "Reporting" in dirs):
            return d
        if d.count(os.sep) - str(path).count(os.sep) > 4:
            dirs[:] = []
    raise RuntimeError("مش لاقي مشروع MVC (فولدر Controllers + Views) جوه الكود")


def unpack(zip_path, dest):
    keep = (".cs", ".cshtml", ".js", ".sql", ".config", ".csproj")
    with zipfile.ZipFile(zip_path) as z:
        for i in z.infolist():
            n = i.filename
            if i.is_dir() or not n.lower().endswith(keep) or n.lower().endswith(".min.js") or re.search(r"/(bin|obj|packages|node_modules)/", n, re.I) or i.file_size > 8_000_000:
                continue
            target = os.path.realpath(os.path.join(dest, n))
            if not target.startswith(os.path.realpath(dest) + os.sep):
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(i) as src, open(target, "wb") as out:
                out.write(src.read())
    return find_root(dest)


# ------------------------------------------------------------------ scan
ACT_RE = re.compile(r"public\s+(?:async\s+)?(?:virtual\s+)?(?:override\s+)?(?:Task<\s*)?[\w.]+(?:<[^>]+>)?\s*>?\s+(\w+)\s*\(")
EP_RE = re.compile(r'''(?:url\s*[:=]\s*|\$\.(?:get|post|getJSON|ajax)\(\s*|fetch\(\s*|href\s*=\s*|action\s*=\s*|location(?:\.href)?\s*=\s*|window\.open\(\s*)["'`]/(\w+)/(\w+)(?=[/?"'`#])''')
URLACT_RE = re.compile(r'Url\.Action\(\s*"(\w+)"\s*,\s*"(\w+)"')
SQLCAT_RE = re.compile(r'(?:new\s+SqlCommand|ExecuteSqlCommand|SqlQuery<[^>]*>|ExecuteStoreQuery|\.Query(?:<[^>]*>)?|\.Execute)\s*\(\s*(?:\$"[^"]*\{|"[^"]*"\s*\+\s*(?!"))', re.I)
TOK_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")


def scan(root, conn=None, log=None, label=""):
    log = log or (lambda m: logger.info(m))
    t0 = time.time()
    rel = lambda p: os.path.relpath(p, root).replace("\\", "/")
    files = []
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if x.lower() not in ("bin", "obj", "packages", "node_modules", ".vs", "libs")]
        for f in fs:
            if f.endswith((".cs", ".cshtml", ".js")) and not f.endswith(".min.js"):
                files.append(os.path.join(d, f))
    log(f"🧬 {len(files):,} ملف كود")
    # ---------- controllers + actions (with [ActionName] and base controllers)
    ctrl, bases, texts = {}, {}, {}
    for p in files:
        if not p.endswith(".cs"):
            continue
        s = _read(p)
        if "Controller" not in s:
            continue
        for m in re.finditer(r"class\s+(\w+)(?:\s*:\s*([\w.]+))?", s):
            cls, base = m.group(1), (m.group(2) or "").split(".")[-1]
            acts = {a.lower() for a in ACT_RE.findall(s)} | {a.lower() for a in re.findall(r'ActionName\(\s*"(\w+)"', s)}
            if cls.endswith("Controller") and cls != "Controller":
                k = cls[:-10].lower()
                e = ctrl.setdefault(k, {"name": cls[:-10], "file": rel(p), "actions": set(), "base": base, "views": [], "calls": {}, "procs": set()})
                e["actions"] |= acts
                if base and not e.get("base"):
                    e["base"] = base
                if os.path.basename(p).lower() == cls.lower() + ".cs":
                    e["file"] = rel(p)
                texts[k] = texts.get(k, "") + s
            if base in ("Controller", "ApiController", "AsyncController") or cls.endswith("BaseController"):
                bases[cls] = acts
    for e in ctrl.values():
        b, seen = e["base"], 0
        while b in bases and seen < 4:
            e["actions"] |= bases[b]
            seen += 1
            b = next((x["base"] for x in ctrl.values() if x["name"] + "Controller" == b), None)
    log(f"🧬 {len(ctrl):,} كنترولر")
    # ---------- database: procedures, their parameters, tables they touch, broken ones (from the DB audit)
    procs, pparams, ptables, broken = {}, {}, {}, {}
    if conn is not None:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sys.procedures WHERE is_ms_shipped=0")
        procs = {r[0].lower(): r[0] for r in cur.fetchall()}
        cur.execute("SELECT OBJECT_NAME(object_id), LOWER(REPLACE(name,'@','')) FROM sys.parameters WHERE object_id IN (SELECT object_id FROM sys.procedures)")
        for o, n in cur.fetchall():
            pparams.setdefault(o.lower(), set()).add(n)
        cur.execute("""SELECT DISTINCT LOWER(OBJECT_NAME(d.referencing_id)), d.referenced_entity_name FROM sys.sql_expression_dependencies d
                       JOIN sys.tables t ON t.object_id=d.referenced_id JOIN sys.procedures p ON p.object_id=d.referencing_id""")
        for o, t in cur.fetchall():
            ptables.setdefault(o, set()).add(t)
        cur.execute("SELECT DISTINCT LOWER(referenced_entity_name) FROM sys.sql_expression_dependencies d JOIN sys.procedures p ON p.object_id=d.referencing_id")
        proc_deps = {r[0] for r in cur.fetchall() if r[0]}
        cur.execute("SELECT LOWER(name) FROM sys.objects")
        all_objs = {r[0] for r in cur.fetchall()}
        pages, page_module = [], {}
        try:
            cur.execute("SELECT Id, ArName, ControllerName FROM SystemPage WHERE ISNULL(IsDeleted,0)=0 AND ControllerName IS NOT NULL")
            pages = cur.fetchall()
            cur.execute(""";WITH t AS (SELECT Id, ParentId, ControllerName, Id AS root, 0 lvl FROM SystemPage WHERE ISNULL(IsDeleted,0)=0
                              UNION ALL SELECT t.Id, p.ParentId, t.ControllerName, p.Id, lvl + 1 FROM t JOIN SystemPage p ON p.Id=t.ParentId WHERE lvl < 8)
                           SELECT LOWER(t.ControllerName), r.ArName FROM t JOIN SystemPage r ON r.Id=t.root
                           WHERE (t.ParentId IS NULL OR t.ParentId=0) AND t.ControllerName IS NOT NULL""")
            for cn, mod in cur.fetchall():
                page_module.setdefault(cn, mod)
        except Exception as e:
            log(f"⚠️ SystemPage: {e}")
        log(f"🧬 قاعدة البيانات: {len(procs):,} إجراء")
    else:
        proc_deps, all_objs, pages, page_module = set(), set(), [], {}
    try:
        from engine import db_audit
        da = db_audit.load() or {}
        for f in da.get("findings") or []:
            if f["area"] in ("الكود", "التشغيل") and f["sev"] == "عالية":
                for r in f.get("sample") or []:
                    n = r.get("الكائن") or r.get("الإجراء")
                    if n:
                        broken[n.lower()] = r.get("بيشاور على (مش موجود)") or r.get("الخطأ") or r.get("الرسالة") or r.get("المشكلة") or ""
    except Exception:
        pass
    arname = {}
    for pid, ar, cn in pages:
        arname.setdefault(str(cn).lower(), ar)
    # ---------- token index (which file mentions which name) + views / JS requests
    tokens_of, calls, menu_abs, menu_links = {}, {}, [], []
    findings = []
    sqlcat = []
    for p in files:
        s = _read(p)
        r = rel(p)
        toks = {t.lower() for t in TOK_RE.findall(s)}
        tokens_of[r] = toks
        if p.endswith((".cshtml", ".js")):
            s = re.sub(r"@\*.*?\*@|<!--.*?-->|/\*.*?\*/", " ", s, flags=re.S)          # commented-out code doesn't call anything
            s = re.sub(r"(?m)^\s*//.*$", " ", s)
            owner = None
            m = re.match(r"Views/([^/]+)/", r)
            if m:
                owner = m.group(1).lower()
                if owner in ctrl:
                    ctrl[owner]["views"].append(r)
            for cn, an in [(m.group(1), m.group(2)) for m in EP_RE.finditer(s)] + [(m.group(2), m.group(1)) for m in URLACT_RE.finditer(s)]:
                calls.setdefault((cn.lower(), an.lower()), set()).add(r)
                if owner and owner in ctrl:
                    ctrl[owner]["calls"].setdefault(f"/{cn}/{an}", set()).add(r)
            if "/Shared/Modules/" in r or r.endswith("_Layout.cshtml"):
                mod = re.sub(r"Module$", "", os.path.splitext(os.path.basename(r))[0].lstrip("_"))
                for m in re.finditer(r'href="(https?://[^"]+|//[^"]+)"', s):
                    u = m.group(1)
                    if not re.search(r"(cdn|fonts\.googleapis|bootstrapcdn|jsdelivr|cloudflare|wa\.me|whatsapp|facebook|twitter|linkedin|youtube|google\.com/maps)", u, re.I):
                        menu_abs.append({"الموديول": mod, "اللينك": u, "الملف": r})
                for m in re.finditer(r'href="/(\w+)/(\w+)', s):
                    menu_links.append((m.group(1).lower(), m.group(2).lower(), mod, r))
                    if m.group(1).lower() in ctrl:
                        ctrl[m.group(1).lower()].setdefault("module", mod)
        else:
            for m in SQLCAT_RE.finditer(s):
                line = s.count("\n", 0, m.start()) + 1
                sqlcat.append({"الملف": r, "السطر": line})
    log("🧬 بربط الشاشات بالإجراءات…")
    # ---------- controller → procedures (names of existing procedures mentioned in its code)
    if procs:
        for k, e in ctrl.items():
            e["procs"] = {procs[t] for t in {x.lower() for x in TOK_RE.findall(texts.get(k, ""))} if t in procs}
    # ---------- findings: screens
    miss_act, miss_ctrl = {}, []
    for (cn, an), fl in calls.items():
        if cn in IGNORE_CTRL:
            continue
        if cn not in ctrl:
            miss_ctrl.append({"الطلب": f"/{cn}/{an}", "من": ", ".join(sorted(fl)[:3]), "عدد الملفات": len(fl)})
        elif an not in ctrl[cn]["actions"] and an not in ("index",):
            miss_act.setdefault(an, []).append((ctrl[cn]["name"], sorted(fl)))
    n_act = sum(len(v) for v in miss_act.values())
    if miss_act:
        rows = []
        screens = []
        for an, lst in sorted(miss_act.items(), key=lambda x: -len(x[1])):
            for cn, fl in lst:
                rows.append({"الشاشة": cn, "الأكشن المطلوب": an, "بيتنادي من": ", ".join(fl[:2])})
                screens.append(cn.lower())
        top = sorted(miss_act.items(), key=lambda x: -len(x[1]))[:3]
        findings.append(F("الشاشات", "عالية", f"{n_act} نداء من الشاشات لأكشن مش موجود في الكنترولر (الزرار هيرجع 404 أو مش هيعمل حاجة)",
                          "أكتر حاجة متكررة: " + "، ".join(f"{a} ({len(l)} شاشة)" for a, l in top), rows, n_act,
                          fix="ضيف الأكشن للكنترولر أو صلّح اسم الطلب في الفيو", screens=screens, key="missing_action"))
    for an, lst in sorted(miss_act.items(), key=lambda x: -len(x[1]))[:6]:
        if len(lst) >= 5:
            findings.append(F("الشاشات", "عالية", f"{len(lst)} شاشة بتنادي «{an}» ومش موجود في الكنترولر بتاعها", "نفس الزرار في كل الشاشات دي مش هيشتغل",
                              [{"الشاشة": c, "من": ", ".join(fl[:2])} for c, fl in lst], len(lst), fix=f"ضيف {an} (أو ورّثه من كنترولر أساسي)",
                              screens=[c.lower() for c, _ in lst], key=f"missing_{an}"))
    if miss_ctrl:
        miss_ctrl.sort(key=lambda x: -x["عدد الملفات"])
        findings.append(F("الشاشات", "عالية", f"{len(miss_ctrl)} طلب لكنترولر مش موجود أصلًا (اسم غلط أو كود تجريبي متساب)", "", miss_ctrl, len(miss_ctrl),
                          fix="صلّح اسم الكنترولر في الفيو", key="missing_controller"))
    # ---------- findings: menu
    if menu_abs:
        local = [x for x in menu_abs if re.search(r"//(localhost|127\.|10\.|192\.168\.)", x["اللينك"])]
        findings.append(F("المنيو", "عالية" if local else "متوسطة", f"{len(menu_abs)} لينك في ملفات المنيو بعنوان كامل بدل مسار نسبي" + (f" — {len(local)} منهم على جهاز المطور" if local else ""),
                          "اللينك ده هيودّي كل العملاء على نفس العنوان (localhost / موقع عميل تاني / موقع الاختبار) بدل نظامهم", menu_abs, len(menu_abs),
                          fix="غيّر اللينك لمسار نسبي /Controller/Action", key="menu_absolute"))
    dead_menu = [{"الموديول": mod, "اللينك": f"/{c}/{a}", "الملف": r} for c, a, mod, r in menu_links
                 if c not in IGNORE_CTRL and c != "report" and (c not in ctrl or (a not in ctrl[c]["actions"] and a != "index"))]
    rep_ctrl = ctrl.get("report")
    dead_menu += [{"الموديول": mod, "اللينك": f"/Report/{a}", "الملف": r} for c, a, mod, r in menu_links if c == "report" and rep_ctrl and a not in rep_ctrl["actions"]]
    if dead_menu:
        uniq = {x["اللينك"]: x for x in dead_menu}
        findings.append(F("المنيو", "متوسطة", f"{len(uniq)} عنصر في المنيو بيودّي على صفحة مش موجودة في الكود", "", list(uniq.values()), len(uniq),
                          fix="شيل العنصر أو صلّح اللينك", key="menu_dead"))
    # ---------- findings: code
    if procs:
        cs_texts = [(r, t) for r, t in tokens_of.items() if r.endswith(".cs")]
        missing = {}
        call_re = re.compile(r'(?:StoredProcedure|EXEC(?:UTE)?\s|SqlQuery|ExecuteSqlCommand|SqlCommand\(|QueryMultiple|\.Query<|\.Execute\()', re.I)
        for p in files:
            if not p.endswith(".cs") or "/Reporting/Reports/" in p.replace("\\", "/") or "/Properties/" in p.replace("\\", "/"):
                continue
            lines = _read(p).splitlines()
            for i, l in enumerate(lines):
                if not call_re.search(" ".join(lines[max(0, i - 3): i + 4])):
                    continue
                for m in re.finditer(r'"\s*(?:EXEC(?:UTE)?\s+)?(?:\[?dbo\]?\.)?\[?((?:SP_|sp_|Get|Insert|Update|Delete|Save)\w{3,80})\]?', l):
                    nm = m.group(1)
                    if nm.lower() not in all_objs:
                        missing.setdefault(nm, []).append(f"{rel(p)}:{i + 1}")
        if missing:
            findings.append(F("الكود", "عالية", f"الكود بينادي {len(missing)} إجراء مخزن مش موجود في قاعدة البيانات",
                              "الشاشة اللي بتستخدمهم هتقع وقت الحفظ / الفتح", [{"الإجراء": k, "فين": ", ".join(v[:3])} for k, v in sorted(missing.items())], len(missing),
                              fix="شغّل سكريبت الإجراء على القاعدة أو صلّح الاسم", key="code_missing_proc"))
    if sqlcat:
        findings.append(F("الكود", "متوسطة", f"{len(sqlcat)} مكان في الـ C# بيبني SQL بالدمج مع متغيرات (خطر SQL Injection)", "", sqlcat, len(sqlcat),
                          fix="استخدم SqlParameter / بارامترات Dapper", key="code_sql_concat"))
    # ---------- findings: reports
    rep_dir = os.path.join(root, "Reporting", "Reports")
    rep_missing, rep_params, rep_sum, n_reports = [], [], [], 0
    if os.path.isdir(rep_dir):
        for f in sorted(os.listdir(rep_dir)):
            if not f.endswith(".Designer.cs"):
                continue
            n_reports += 1
            s = _read(os.path.join(rep_dir, f))
            name = f[:-12]
            sps = sorted(set(re.findall(r'StoredProcName\s*=\s*"([^"]+)"', s)))
            qp = {x.lstrip("@").lower() for x in re.findall(r'queryParameter\d*\.Name\s*=\s*"(@?\w+)"', s)}
            for sp in sps:
                if procs and sp.lower() not in procs:
                    rep_missing.append({"التقرير": name, "الإجراء": sp})
            if procs and len(sps) == 1 and sps[0].lower() in procs:
                extra = sorted(p for p in qp if p not in pparams.get(sps[0].lower(), set()))
                if extra:
                    rep_params.append({"التقرير": name, "الإجراء": sps[0], "بارامترات مش موجودة في الإجراء": ", ".join(extra)})
            for m in re.finditer(r'this\.(xr\w+)\.ExpressionBindings\.AddRange\(new [^{]+\{\s*new DevExpress\.XtraReports\.UI\.ExpressionBinding\("BeforePrint", "Text", "(sum\w+)\(', s):
                if not re.search(r"this\." + m.group(1) + r"\.Summary\s*=", s):
                    rep_sum.append({"التقرير": name, "الخانة": m.group(1), "الدالة": m.group(2)})
    if rep_missing:
        findings.append(F("التقارير", "عالية", f"{len(rep_missing)} تقرير بينادي إجراء مخزن مش موجود", "التقرير هيقع أول ما يتفتح", rep_missing, len(rep_missing),
                          fix="رجّع الإجراء أو صلّح اسمه في التقرير", key="report_missing_proc"))
    if rep_params:
        findings.append(F("التقارير", "متوسطة", f"{len(rep_params)} تقرير بيبعت بارامترات الإجراء مش بيستقبلها", "", rep_params, len(rep_params), key="report_params"))
    if rep_sum:
        findings.append(F("التقارير", "متوسطة", f"{len(rep_sum)} خانة إجمالي بتستخدم sum…() من غير XRSummary في {len({x['التقرير'] for x in rep_sum})} تقرير",
                          "الخانة ممكن تطلع فاضية أو باسمها بدل الرقم", rep_sum, len(rep_sum), fix="عرّف Summary للخانة (Running = Report / Group)", key="report_summary"))
    # ---------- findings: procedures
    if broken:
        callers = {}
        for b in broken:
            for r, toks in tokens_of.items():
                if b in toks:
                    callers.setdefault(b, []).append(r)
        used = [{"الإجراء": b, "المشكلة": broken[b][:120], "بيتنادي من": ", ".join(v[:3])} for b, v in callers.items()]
        if used:
            scr = []
            for b, v in callers.items():
                for r in v:
                    m = re.match(r"(?:Views|Controllers)/(?:[^/]+/)*?(\w+?)(?:Controller\.cs|/)", r)
                    if m:
                        scr.append(m.group(1).lower())
            findings.append(F("الإجراءات", "عالية", f"{len(used)} إجراء مكسور بيتنادي فعلًا من الكود — الشاشات دي هتقع",
                              "الإجراء مكسور في قاعدة البيانات (من فحص قاعدة البيانات) والكود ده بيناديه", used, len(used), fix="صلّح الإجراء", screens=scr, key="broken_called"))
    if procs:
        all_tokens = set().union(*tokens_of.values()) if tokens_of else set()
        dead = sorted(v for k, v in procs.items() if k not in all_tokens and k not in proc_deps)
        if dead:
            findings.append(F("الإجراءات", "للعلم", f"{len(dead):,} إجراء مخزن محدش بيناديه (لا الكود ولا التقارير ولا إجراء تاني)",
                              "غالبًا نسخ قديمة — بتلخبط وبتكبّر القاعدة", [{"الإجراء": x} for x in dead], len(dead), fix="راجعهم وامسح اللي مش مستخدم", key="dead_procs"))
    # ---------- screens map
    screens = {}
    for k, e in ctrl.items():
        tbls = set()
        for pn in e["procs"]:
            tbls |= ptables.get(pn.lower(), set())
        calls_ = [{"url": u, "ok": (lambda c, a: c in IGNORE_CTRL or (c in ctrl and (a in ctrl[c]["actions"] or a == "index")))(*u.strip("/").lower().split("/")[:2]),
                   "from": sorted(v)[:2]} for u, v in sorted(e["calls"].items())]
        screens[k] = {"name": e["name"], "ar": arname.get(k, ""), "file": e["file"], "module": page_module.get(k) or MODULE_NAMES.get(e.get("module", ""), e.get("module", "")), "views": sorted(e["views"])[:30],
                      "actions": sorted(e["actions"])[:120], "calls": calls_[:120], "procs": sorted(e["procs"])[:120],
                      "broken_procs": sorted(p for p in e["procs"] if p.lower() in broken)[:30], "tables": sorted(tbls)[:120]}
    for f in findings:
        for s in f["screens"]:
            if s in screens:
                screens[s].setdefault("issues", []).append(f["id"])
    modules = {}
    for k, sc in screens.items():
        m = sc["module"] or "أخرى"
        e = modules.setdefault(m, {"code": m, "name": m if m != "أخرى" else "مش مربوطة بموديول", "screens": 0, "issues": 0})
        e["screens"] += 1
        e["issues"] += len(sc.get("issues", [])) + sum(1 for c in sc["calls"] if not c["ok"]) + len(sc["broken_procs"])
    findings.sort(key=lambda f: (SEV.get(f["sev"], 9), f["area"]))
    prev = load() or {}
    old = {f["id"] for f in prev.get("findings") or []}
    for f in findings:
        f["new"] = bool(prev) and f["id"] not in old
    res = {"at": datetime.now().strftime("%Y-%m-%d %H:%M"), "secs": round(time.time() - t0), "label": label,
           "counts": {"files": len(files), "controllers": len(ctrl), "views": sum(len(e["views"]) for e in ctrl.values()), "reports": n_reports,
                      "procs": len(procs), "calls": len(calls), "db": bool(procs)},
           "findings": findings, "modules": sorted(modules.values(), key=lambda m: -m["issues"]), "screens": screens,
           "fixed": [{"area": f["area"], "title": f["title"]} for f in prev.get("findings") or [] if f["id"] not in {x["id"] for x in findings}]}
    log(f"🧬 خلص في {res['secs']} ث — " + " · ".join(f"{s}: {sum(1 for f in findings if f['sev'] == s)}" for s in SEV))
    return res


def support_issues():
    d = load()
    if not d:
        return []
    out = []
    for f in d.get("findings") or []:
        if f["sev"] not in ("عالية", "متوسطة"):
            continue
        lines = "\n".join(" · ".join(f"{k}: {v}" for k, v in r.items()) for r in (f.get("sample") or [])[:15])
        out.append({"id": "twin-" + f["id"][:120], "site": d.get("label") or "الكود", "url": "", "source": "التوأم الرقمي", "screen": f["area"],
                    "severity": f["sev"], "title": f["title"][:200], "details": (f.get("detail") or "") + ("\n\n" + lines if lines else "") + ("\n\nالتصليح: " + f["fix"] if f.get("fix") else ""),
                    "evidence": f"تحليل الكود {d['at']}", "doc": "", "steps": "افتح «التوأم الرقمي» في الأداة", "found": d["at"][:10]})
    return out
