"""
🗄️ فحص قاعدة البيانات — reads a COPY of an ERP database (a restored backup of the TEST site, never a client's live
database) and finds what the screens can't show:

  الهيكل      tables without a primary key, «…Id» columns with no foreign key + how many rows point to nothing,
              disabled / untrusted constraints and triggers, leftover backup / temp tables, money stored as float
  الكود       stored procedures / views / functions that reference objects or columns that don't exist (they fail when
              called — e.g. «Error when trying to populate the datasource»), dynamic SQL built by concatenation
              (injection risk), SELECT *, cursors, NOLOCK, several versions of the same procedure
  الداتا      unbalanced journal entries, journal lines with debit and credit together / both zero / negative,
              journals without lines, journals pointing to a deleted or missing document, posted documents without a
              journal, duplicate document numbers, future dates, and the «shadow accountant»: every sales / purchase
              invoice recomputed from its lines and compared with the totals the ERP saved
  الحسابات    trial balance in total, journal lines on parent / deleted / inactive accounts, accounts that need a cost centre,
              customer accounts without the customer (sub-ledger ≠ ledger)
  التشغيل     every report / read procedure EXECuted for real on the COPY with typical filters (this year, the rest empty)
              inside a transaction that is always rolled back: the ones that crash (missing table / column, divide by zero,
              ambiguous / duplicate column, conversion) and the slow ones
  الخريطة     SystemPage (screen → table → controller) + which procedures read / write each table — the seed of the
              digital twin: search a screen or a table and see the code around it

Everything is SELECT-only, except sp_refreshsqlmodule on views / functions, which only refreshes metadata of the COPY.
The connection is kept in settings/db_audit.json (password encrypted); the result in state/db_audit.json.
"""
import json
import re
import time
from datetime import datetime

from utils.logger import logger

SEV = {"عالية": 0, "متوسطة": 1, "منخفضة": 2, "للعلم": 3}
MONEY_NAME = re.compile(r"(Price|Total|Amount|Value|Cost|Debit|Credit|Balance|Paid|Tax|Discount|Salary|Fees|Commission)$", re.I)
CLUTTER = re.compile(r"(backup|_bak\b|bak$|_old\b|old$|_temp|temp$|tmp|_copy|copy$|_test\b|test$|_\d{6,}|backupxw|_before|beforefix|_v\d+$|^wael_)", re.I)


# ------------------------------------------------------------------ connection / settings
def _cfg_file():
    from config import paths
    return paths.SETTINGS_DIR / "db_audit.json"


def _state_file():
    from config import paths
    return paths.STATE_DIR / "db_audit.json"


def load_cfg():
    try:
        return json.loads(_cfg_file().read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cfg(d):
    from utils.secret_box import encrypt, is_encrypted
    cur = load_cfg()
    for k in ("server", "port", "user", "database", "label"):
        if k in d:
            cur[k] = str(d[k] or "").strip()
    if d.get("password"):
        cur["password"] = d["password"] if is_encrypted(d["password"]) else encrypt(d["password"])
    _cfg_file().parent.mkdir(parents=True, exist_ok=True)
    _cfg_file().write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
    return public(cur)


def public(c=None):
    c = c if c is not None else load_cfg()
    return {k: c.get(k, "") for k in ("server", "port", "user", "database", "label")} | {"has_password": bool(c.get("password"))}


def connect(c=None):
    import pymssql
    from utils.secret_box import decrypt
    c = c or load_cfg()
    if not c.get("server") or not c.get("database"):
        raise RuntimeError("حدد السيرفر وقاعدة البيانات الأول (من صفحة فحص قاعدة البيانات)")
    return pymssql.connect(server=c["server"], port=int(c.get("port") or 1433), user=c.get("user") or None,
                           password=decrypt(c.get("password") or "") or None, database=c["database"], login_timeout=15, timeout=600, charset="UTF-8")


def connect_timeout(timeout):
    import pymssql
    from utils.secret_box import decrypt
    c = load_cfg()
    conn = pymssql.connect(server=c["server"], port=int(c.get("port") or 1433), user=c.get("user") or None, password=decrypt(c.get("password") or "") or None,
                           database=c["database"], login_timeout=15, timeout=int(timeout), charset="UTF-8")
    conn.autocommit(True)
    return conn


def load():
    try:
        return json.loads(_state_file().read_text(encoding="utf-8"))
    except Exception:
        return None


def save_result(d):
    f = _state_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    if f.exists():
        (f.parent / "db_audit_prev.json").write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    f.write_text(json.dumps(d, ensure_ascii=False, default=str), encoding="utf-8")


# ------------------------------------------------------------------ helpers
class DB:
    def __init__(self, conn):
        self.c = conn

    def rows(self, sql, *args):
        cur = self.c.cursor(as_dict=True)
        cur.execute(sql, args or None)
        out = cur.fetchall() if cur.description else []
        cur.close()
        return out

    def one(self, sql, *args):
        cur = self.c.cursor()
        cur.execute(sql, args or None)
        r = cur.fetchone() if cur.description else None
        cur.close()
        return r[0] if r else None

    def has(self, table, col=None):
        if col:
            return bool(self.one("SELECT COUNT(*) FROM sys.columns WHERE object_id=OBJECT_ID(%s) AND name=%s", table, col))
        return bool(self.one("SELECT COUNT(*) FROM sys.tables WHERE name=%s", table))


def F(area, sev, title, detail="", sample=None, count=None, where="", fix="", key=""):
    return {"area": area, "sev": sev, "title": title, "detail": detail, "sample": (sample or [])[:25], "count": count, "where": where, "fix": fix,
            "id": re.sub(r"\W+", "_", f"{area}_{key or title[:80]}")[:160]}


def _q(name):
    return "[" + str(name).replace("]", "]]") + "]"


# ------------------------------------------------------------------ 1) structure
def check_structure(db, log):
    out = []
    rows = {r["t"]: r["n"] for r in db.rows("""SELECT t.name t, SUM(p.rows) n FROM sys.tables t JOIN sys.partitions p ON p.object_id=t.object_id AND p.index_id IN (0,1)
                                               WHERE t.is_ms_shipped=0 GROUP BY t.name""")}
    nopk = db.rows("""SELECT t.name FROM sys.tables t WHERE t.is_ms_shipped=0 AND NOT EXISTS
                      (SELECT 1 FROM sys.key_constraints k WHERE k.parent_object_id=t.object_id AND k.type='PK') ORDER BY t.name""")
    nopk = sorted(({"الجدول": r["name"], "السطور": rows.get(r["name"], 0)} for r in nopk), key=lambda x: -x["السطور"])
    if nopk:
        used = [x for x in nopk if x["السطور"]]
        out.append(F("الهيكل", "متوسطة" if used else "منخفضة", f"{len(nopk)} جدول من غير مفتاح أساسي (Primary key) — {len(used)} منهم فيهم داتا",
                     "جدول من غير مفتاح أساسي ممكن يتكرر فيه نفس السطر، والتعديل / الحذف ممكن يمس أكتر من سطر", nopk, len(nopk),
                     fix="ضيف عمود Id IDENTITY PRIMARY KEY للجداول المستخدمة"))
    # «…Id» columns without a foreign key → orphans
    tables = {t.lower(): t for t in rows}
    cols = db.rows("""SELECT t.name t, c.name c FROM sys.columns c JOIN sys.tables t ON t.object_id=c.object_id JOIN sys.types ty ON ty.user_type_id=c.user_type_id
                      WHERE t.is_ms_shipped=0 AND c.name LIKE '%Id' AND c.name <> 'Id' AND ty.name IN ('int','bigint','smallint')
                        AND NOT EXISTS (SELECT 1 FROM sys.foreign_key_columns f WHERE f.parent_object_id=c.object_id AND f.parent_column_id=c.column_id)
                        AND NOT EXISTS (SELECT 1 FROM sys.index_columns ic JOIN sys.key_constraints k ON k.parent_object_id=ic.object_id AND k.unique_index_id=ic.index_id AND k.type='PK'
                                        WHERE ic.object_id=c.object_id AND ic.column_id=c.column_id)""")
    cand = []
    for r in cols:
        if not rows.get(r["t"]):
            continue
        base = r["c"][:-2]
        tgt = next((tables[x] for x in (base.lower(), base.lower() + "s", base.lower() + "es", base.lower().rstrip("y") + "ies") if x in tables), None)
        if tgt and tgt != r["t"] and db.has(tgt, "Id"):
            cand.append((r["t"], r["c"], tgt))
    log(f"🗄️ {len(cand)} عمود Id من غير Foreign key — بعد السطور اليتيمة")
    orph, unsure, t0 = [], [], time.time()
    for t, c, tgt in sorted(cand, key=lambda x: -rows.get(x[0], 0))[:400]:
        if time.time() - t0 > 240:
            break
        try:
            n = db.one(f"SELECT COUNT(*) FROM {_q(t)} a WHERE a.{_q(c)} IS NOT NULL AND a.{_q(c)} <> 0 AND NOT EXISTS (SELECT 1 FROM {_q(tgt)} b WHERE b.Id=a.{_q(c)})")
            tot = db.one(f"SELECT COUNT(*) FROM {_q(t)} a WHERE a.{_q(c)} IS NOT NULL AND a.{_q(c)} <> 0") if n else 0
        except Exception:
            continue
        if n:
            row = {"الجدول": t, "العمود": c, "المفروض يشاور على": tgt, "سطور بتشاور على حاجة مش موجودة": n, "من": tot}
            (unsure if n == tot else orph).append(row)
    orph.sort(key=lambda x: -x["سطور بتشاور على حاجة مش موجودة"])
    unsure.sort(key=lambda x: -x["سطور بتشاور على حاجة مش موجودة"])
    if unsure:
        out.append(F("الهيكل", "للعلم", f"{len(unsure)} عمود كل قيمه مش موجودة في الجدول اللي باسمه — غالبًا بيشاور على جدول تاني (أو جدول تشخيص متنقل من قاعدة تانية)",
                     "راجعهم: لو الجدول الصح مختلف يبقى مفيش مشكلة، ولو ده الجدول الصح يبقى الداتا كلها يتيمة", unsure, len(unsure)))
    if orph:
        out.append(F("الهيكل", "عالية", f"{len(orph)} عمود بيشاور على سجلات مش موجودة (داتا يتيمة) — {sum(x['سطور بتشاور على حاجة مش موجودة'] for x in orph):,} سطر",
                     "العمود ده من غير Foreign key، فاتمسح السجل الأصلي وفضل السطر يشاور على حاجة مش موجودة — ده بيطلع في التقارير كأصناف / عملاء من غير اسم أو أرقام ناقصة",
                     orph, len(orph), fix="نضّف السطور اليتيمة وضيف Foreign key"))
    out.append(F("الهيكل", "للعلم", f"{len(cand)} عمود «…Id» من غير Foreign key (من غير ما يكون فيه سطور يتيمة دلوقتي)",
                 "مفيش حماية من قاعدة البيانات — أي حذف ممكن يسيب داتا يتيمة", [{"الجدول": t, "العمود": c, "الجدول المقصود": g} for t, c, g in cand[:25]], len(cand)))
    bad = db.rows("""SELECT OBJECT_NAME(parent_object_id) t, name, 'Foreign key' k, is_disabled d, is_not_trusted u FROM sys.foreign_keys WHERE is_disabled=1 OR is_not_trusted=1
                     UNION ALL SELECT OBJECT_NAME(parent_object_id), name, 'Check', is_disabled, is_not_trusted FROM sys.check_constraints WHERE is_disabled=1 OR is_not_trusted=1""")
    if bad:
        out.append(F("الهيكل", "متوسطة", f"{len(bad)} قيد (Foreign key / Check) متعطل أو مش متراجع على الداتا الموجودة",
                     "اتعمل WITH NOCHECK أو اتقفل — الداتا القديمة ممكن تكون مخالفة له", [{"الجدول": r["t"], "القيد": r["name"], "النوع": r["k"], "متعطل": "✓" if r["d"] else "", "مش متراجع": "✓" if r["u"] else ""} for r in bad], len(bad),
                     fix="ALTER TABLE … WITH CHECK CHECK CONSTRAINT …"))
    trg = db.rows("SELECT OBJECT_NAME(parent_id) t, name FROM sys.triggers WHERE is_disabled=1 AND parent_class=1")
    if trg:
        out.append(F("الهيكل", "متوسطة", f"{len(trg)} Trigger متقفل", "Trigger متقفل يعني منطق مش شغال — اتأكد إنه مقصود", [{"الجدول": r["t"], "Trigger": r["name"]} for r in trg], len(trg)))
    clut = sorted(({"الجدول": t, "السطور": n} for t, n in rows.items() if CLUTTER.search(t)), key=lambda x: -x["السطور"])
    if clut:
        out.append(F("الهيكل", "منخفضة", f"{len(clut)} جدول نسخ احتياطي / مؤقت / تجربة متساب في قاعدة البيانات",
                     "بيكبّر الباك أب، بيلخبط المطورين، وممكن إجراء يكتب في الجدول الغلط", clut, len(clut), fix="انقلهم لقاعدة أرشيف أو امسحهم بعد التأكد"))
    fl = db.rows("""SELECT t.name t, c.name c, ty.name ty FROM sys.columns c JOIN sys.tables t ON t.object_id=c.object_id JOIN sys.types ty ON ty.user_type_id=c.user_type_id
                    WHERE t.is_ms_shipped=0 AND ty.name IN ('float','real')""")
    fl = [{"الجدول": r["t"], "العمود": r["c"], "النوع": r["ty"]} for r in fl if MONEY_NAME.search(r["c"]) and rows.get(r["t"])]
    if fl:
        out.append(F("الهيكل", "متوسطة", f"{len(fl)} عمود فلوس / أسعار متخزن float (بيعمل فروق تقريب)",
                     "float مش بيخزن الكسور العشرية بالظبط (0.1 + 0.2 ≠ 0.3) — ده بيعمل فروق هللات في الإجماليات والقيود",
                     fl, len(fl), fix="decimal(18,4) أو money للفلوس، decimal(18,6) للكميات"))
    return out, rows


# ------------------------------------------------------------------ 2) code
def check_code(db, log):
    out = []
    unresolved = db.rows("""SELECT DISTINCT OBJECT_SCHEMA_NAME(d.referencing_id) s, OBJECT_NAME(d.referencing_id) o, o.type_desc t, d.referenced_entity_name r
                            FROM sys.sql_expression_dependencies d JOIN sys.objects o ON o.object_id=d.referencing_id
                            WHERE d.referenced_id IS NULL AND d.referenced_server_name IS NULL AND d.referenced_database_name IS NULL
                              AND d.is_ambiguous=0 AND d.referenced_class=1 AND d.referenced_entity_name NOT LIKE '#%'
                              AND OBJECT_ID(ISNULL(d.referenced_schema_name,'dbo') + '.' + d.referenced_entity_name) IS NULL
                              AND NOT EXISTS (SELECT 1 FROM sys.types ty WHERE ty.name=d.referenced_entity_name)""")
    if unresolved:
        by = {}
        for r in unresolved:
            by.setdefault(r["o"], {"الكائن": r["o"], "النوع": r["t"].replace("SQL_", "").replace("_", " ").lower(), "بيشاور على (مش موجود)": []})["بيشاور على (مش موجود)"].append(r["r"])
        lst = sorted(by.values(), key=lambda x: x["الكائن"])
        for x in lst:
            x["بيشاور على (مش موجود)"] = "، ".join(sorted(set(x["بيشاور على (مش موجود)"]))[:6])
        out.append(F("الكود", "عالية", f"{len(lst)} إجراء / فيو / فانكشن بيستخدم جداول أو إجراءات مش موجودة — هيقع أول ما يتنادى",
                     "ده نوع الخطأ اللي بيظهر في التقارير كـ «Error when trying to populate the datasource» أو في الشاشات كخطأ سيرفر", lst, len(lst),
                     fix="رجّع الجدول الناقص أو صلّح الإجراء — وقارن بقاعدة موقع الاختبار"))
    # columns that don't exist: the engine resolves each module's references (errors = broken module)
    mods = db.rows("""SELECT o.object_id i, OBJECT_SCHEMA_NAME(o.object_id) s, o.name n, o.type_desc t FROM sys.objects o
                      WHERE o.is_ms_shipped=0 AND o.type IN ('P','V','FN','IF','TF')""")
    log(f"🗄️ بتأكد من {len(mods)} إجراء / فيو / فانكشن إن كل الأعمدة اللي بيستخدمها موجودة")
    broken, t0 = [], time.time()
    cur = db.c.cursor()
    for m in mods:
        if time.time() - t0 > 420:
            log("🗄️ وقف فحص الأعمدة بعد 7 دقايق (الباقي يتفحص المرة الجاية)")
            break
        try:
            cur.execute(f"SELECT COUNT(*) FROM sys.dm_sql_referenced_entities(N'{m['s']}.{m['n'].replace(chr(39), chr(39) * 2)}', N'OBJECT')")
            cur.fetchall()
        except Exception as e:
            msg = re.sub(r"\s+", " ", str(e))
            mm = re.search(r"Invalid column name '([^']+)'|Invalid object name '([^']+)'|could not be bound|ambiguous column name '([^']+)'", msg, re.I)
            if mm:
                broken.append({"الكائن": m["n"], "النوع": m["t"].replace("SQL_", "").replace("_", " ").lower(), "الخطأ": (mm.group(0))[:160]})
            try:
                db.c.rollback()
            except Exception:
                pass
    cur.close()
    if broken:
        out.append(F("الكود", "عالية", f"{len(broken)} إجراء / فيو / فانكشن بيستخدم أعمدة أو أسماء مش موجودة",
                     "الإجراء اتكتب على شكل قديم للجدول (عمود اتشال أو اتغير اسمه) — هيقع وقت التشغيل", broken, len(broken), fix="صلّح أسماء الأعمدة في الإجراء"))
    defs = db.rows("""SELECT o.name n, o.type_desc t, m.definition d FROM sys.sql_modules m JOIN sys.objects o ON o.object_id=m.object_id WHERE o.is_ms_shipped=0""")
    dyn, star, curs, nolock = [], [], [], 0
    for r in defs:
        d = r["d"] or ""
        body = re.sub(r"--[^\n]*|/\*.*?\*/", " ", d, flags=re.S)
        if re.search(r"EXEC(UTE)?\s*\(\s*@", body, re.I) and re.search(r"'\s*\+\s*@\w+\s*\+\s*'", body):
            dyn.append({"الإجراء": r["n"]})
        body2 = re.sub(r"EXISTS\s*\(\s*SELECT\s+\*", "EXISTS(SELECT 1", body, flags=re.I)
        if re.search(r"SELECT\s+\*\s+(INTO|FROM)\s+(?!#|@|\()", body2, re.I):
            star.append(r["n"])
        if re.search(r"\bDECLARE\s+\w+\s+CURSOR\b|\bCURSOR\s+(LOCAL|FAST_FORWARD|FOR)\b", body, re.I):
            curs.append(r["n"])
        nolock += len(re.findall(r"\bNOLOCK\b", body, re.I))
    if dyn:
        out.append(F("الكود", "عالية", f"{len(dyn)} إجراء بيبني SQL بالدمج مع بارامترات وبينفذه بـ EXEC() — خطر SQL Injection",
                     "لو البارامتر جاي من شاشة، مستخدم يقدر يكتب أوامر SQL جوه الفلتر", dyn, len(dyn), fix="sp_executesql مع بارامترات، أو QUOTENAME للأسماء"))
    if curs:
        out.append(F("الكود", "منخفضة", f"{len(curs)} إجراء بيستخدم CURSOR (بطيء مع الداتا الكبيرة)", "", [{"الإجراء": x} for x in curs], len(curs), fix="استبدله بـ set-based UPDATE / INSERT … SELECT"))
    if star:
        out.append(F("الكود", "منخفضة", f"{len(star)} إجراء فيه SELECT * من جداول حقيقية", "أي عمود يتضاف للجدول بيغيّر شكل النتيجة وممكن يكسر تقرير أو شاشة",
                     [{"الإجراء": x} for x in star], len(star)))
    if nolock:
        out.append(F("الكود", "للعلم", f"NOLOCK مستخدمة {nolock:,} مرة", "بتقرا داتا لسه ماتحفظتش نهائي (dirty read) — ممكن تقرير يطلع رقم مؤقت", count=nolock))
    names = [r["n"] for r in defs if r["t"] == "SQL_STORED_PROCEDURE"]
    base = {}
    for n in names:
        b = re.sub(r"(_?(old|new|bak|backup|copy|test|temp|tmp)\d*|_?v\d+|\d+)$", "", n, flags=re.I)
        base.setdefault(b.lower(), []).append(n)
    vers = [{"الإجراء": k, "النسخ": "، ".join(sorted(v)[:6]), "العدد": len(v)} for k, v in base.items() if len(v) > 2]
    vers.sort(key=lambda x: -x["العدد"])
    if vers:
        out.append(F("الكود", "منخفضة", f"{len(vers)} إجراء ليه 3 نسخ أو أكتر بأسماء متقاربة (_V2، _old، 2 …)", "مين فيهم اللي الشاشة بتستخدمه فعلًا؟ ده سبب شائع لاختلاف النتيجة بين موقعين",
                     vers, len(vers), fix="احذف النسخ القديمة بعد التأكد إن مفيش حد بيناديها"))
    return out, len(names)


# ------------------------------------------------------------------ 3) data (journals + documents + shadow accountant)
def check_data(db, log):
    out = []
    if not (db.has("JournalEntry") and db.has("JournalEntryDetail")):
        return out
    nd = "AND ISNULL(je.IsDeleted,0)=0" if db.has("JournalEntry", "IsDeleted") else ""
    ndd = "AND ISNULL(d.IsDeleted,0)=0" if db.has("JournalEntryDetail", "IsDeleted") else ""
    unb = db.rows(f"""SELECT TOP 200 je.Id, je.DocumentNumber, CONVERT(varchar(10), je.Date, 120) dt, je.SourcePageId sp, je.SourceId sid,
                             SUM(ISNULL(d.Debit,0)) deb, SUM(ISNULL(d.Credit,0)) cre FROM JournalEntry je JOIN JournalEntryDetail d ON d.JournalEntryId=je.Id {ndd}
                      WHERE 1=1 {nd} GROUP BY je.Id, je.DocumentNumber, je.Date, je.SourcePageId, je.SourceId
                      HAVING ABS(SUM(ISNULL(d.Debit,0)) - SUM(ISNULL(d.Credit,0))) > 0.005 ORDER BY ABS(SUM(ISNULL(d.Debit,0)) - SUM(ISNULL(d.Credit,0))) DESC""")
    pages = {r["Id"]: r for r in db.rows("SELECT Id, ArName, TableName, ControllerName FROM SystemPage")} if db.has("SystemPage") else {}
    pn = lambda i: (pages.get(i) or {}).get("ArName") or (f"صفحة {i}" if i else "قيد يدوي")
    if unb:
        out.append(F("الداتا", "عالية", f"{len(unb)} قيد مش متزن (المدين ≠ الدائن)", "ميزان المراجعة هيطلع مش متزن، والقوائم المالية غلط",
                     [{"القيد": r["Id"], "رقم المستند": r["DocumentNumber"], "التاريخ": r["dt"], "جاي من": pn(r["sp"]), "رقم المصدر": r["sid"], "مدين": float(r["deb"]),
                       "دائن": float(r["cre"]), "الفرق": round(float(r["deb"]) - float(r["cre"]), 2)} for r in unb], len(unb), fix="صلّح القيد وصلّح الكود اللي ولّده"))
    both = db.one(f"SELECT COUNT(*) FROM JournalEntryDetail d WHERE ISNULL(d.Debit,0)<>0 AND ISNULL(d.Credit,0)<>0 {ndd}")
    zero = db.one(f"SELECT COUNT(*) FROM JournalEntryDetail d WHERE ISNULL(d.Debit,0)=0 AND ISNULL(d.Credit,0)=0 {ndd}")
    neg = db.one(f"SELECT COUNT(*) FROM JournalEntryDetail d WHERE (d.Debit<0 OR d.Credit<0) {ndd}")
    if both or neg:
        out.append(F("الداتا", "متوسطة", f"سطور قيود غلط: {both} سطر فيه مدين ودائن مع بعض · {neg} سطر بالسالب", "السطر الواحد يا مدين يا دائن، وبقيمة موجبة", count=(both or 0) + (neg or 0)))
    if zero:
        out.append(F("الداتا", "منخفضة", f"{zero} سطر قيد بصفر في المدين والدائن", "سطور مالهاش لازمة بتطلع في كشوف الحساب", count=zero))
    empty = db.rows(f"""SELECT TOP 100 je.Id, je.DocumentNumber, je.SourcePageId sp, je.SourceId sid, CONVERT(varchar(10), je.Date, 120) dt FROM JournalEntry je
                        WHERE NOT EXISTS (SELECT 1 FROM JournalEntryDetail d WHERE d.JournalEntryId=je.Id {ndd}) {nd} ORDER BY je.Id DESC""")
    if empty:
        n = db.one(f"SELECT COUNT(*) FROM JournalEntry je WHERE NOT EXISTS (SELECT 1 FROM JournalEntryDetail d WHERE d.JournalEntryId=je.Id {ndd}) {nd}")
        out.append(F("الداتا", "متوسطة", f"{n} قيد من غير ولا سطر", "المستند اتعمله قيد فاضي — غالبًا الكود حفظ رأس القيد وفشل قبل السطور (من غير Transaction)",
                     [{"القيد": r["Id"], "رقم المستند": r["DocumentNumber"], "التاريخ": r["dt"], "جاي من": pn(r["sp"]), "رقم المصدر": r["sid"]} for r in empty], n,
                     fix="الحفظ لازم يبقى جوه Transaction واحدة"))
    if db.has("JournalEntry", "Date"):
        fut = db.one(f"SELECT COUNT(*) FROM JournalEntry je WHERE je.Date > DATEADD(day, 1, GETDATE()) {nd}")
        if fut:
            out.append(F("الداتا", "منخفضة", f"{fut} قيد بتاريخ في المستقبل", "بيطلع في التقارير لما الفترة توصل له — اتأكد إنه مقصود", count=fut))
    # accounts: trial balance, parent accounts, deleted / inactive accounts, mandatory cost centre, customer sub-ledger
    if db.has("ChartOfAccount") and db.has("JournalEntryDetail", "AccountId"):
        tb = db.rows(f"""SELECT SUM(ISNULL(d.Debit,0)) deb, SUM(ISNULL(d.Credit,0)) cre FROM JournalEntryDetail d JOIN JournalEntry je ON je.Id=d.JournalEntryId
                         WHERE 1=1 {ndd} {nd}""")[0]
        diff = float(tb["deb"] or 0) - float(tb["cre"] or 0)
        if abs(diff) > 0.01:
            out.append(F("الداتا", "عالية", f"ميزان المراجعة كله مش متزن: الفرق {diff:,.2f}", f"إجمالي المدين {float(tb['deb'] or 0):,.2f} · إجمالي الدائن {float(tb['cre'] or 0):,.2f}",
                         count=1, key="tb_total"))
        par = db.rows(f"""SELECT TOP 100 a.Code, a.ArName, COUNT(*) n, SUM(ISNULL(d.Debit,0)) deb, SUM(ISNULL(d.Credit,0)) cre FROM JournalEntryDetail d
                          JOIN JournalEntry je ON je.Id=d.JournalEntryId JOIN ChartOfAccount a ON a.Id=d.AccountId
                          WHERE EXISTS (SELECT 1 FROM ChartOfAccount c WHERE c.ParentId=a.Id AND ISNULL(c.IsDeleted,0)=0) {ndd} {nd}
                          GROUP BY a.Code, a.ArName ORDER BY COUNT(*) DESC""")
        if par:
            out.append(F("الداتا", "عالية", f"قيود متسجلة على {len(par)} حساب رئيسي (حساب ليه حسابات فرعية) — {sum(r['n'] for r in par):,} سطر",
                         "الحساب الرئيسي مجمّع لفروعه — لو اتسجل عليه مباشرة، رصيده في الميزان مش هيساوي مجموع فروعه",
                         [{"الكود": r["Code"], "الحساب": r["ArName"], "سطور": r["n"], "مدين": float(r["deb"] or 0), "دائن": float(r["cre"] or 0)} for r in par], len(par),
                         fix="امنع الترحيل على حساب ليه فروع، وانقل السطور لحساب فرعي"))
        dead = db.rows(f"""SELECT TOP 100 a.Code, a.ArName, CASE WHEN ISNULL(a.IsDeleted,0)=1 THEN N'ممسوح' ELSE N'موقوف' END st, COUNT(*) n FROM JournalEntryDetail d
                           JOIN JournalEntry je ON je.Id=d.JournalEntryId JOIN ChartOfAccount a ON a.Id=d.AccountId
                           WHERE (ISNULL(a.IsDeleted,0)=1 OR a.IsActive=0) {ndd} {nd} GROUP BY a.Code, a.ArName, a.IsDeleted ORDER BY COUNT(*) DESC""")
        if dead:
            out.append(F("الداتا", "متوسطة", f"قيود على {len(dead)} حساب ممسوح أو موقوف", "الحساب اتمسح / اتوقف وهو عليه حركة — رصيده هيختفي من شجرة الحسابات بس فاضل في الميزان",
                         [{"الكود": r["Code"], "الحساب": r["ArName"], "الحالة": r["st"], "سطور": r["n"]} for r in dead], len(dead)))
        if db.has("ChartOfAccount", "HasCostCenter") and db.has("JournalEntryDetail", "CostCenterId"):
            cc = db.rows(f"""SELECT TOP 100 a.Code, a.ArName, COUNT(*) n FROM JournalEntryDetail d JOIN JournalEntry je ON je.Id=d.JournalEntryId
                             JOIN ChartOfAccount a ON a.Id=d.AccountId WHERE a.HasCostCenter=1 AND ISNULL(d.CostCenterId,0)=0 {ndd} {nd}
                             GROUP BY a.Code, a.ArName ORDER BY COUNT(*) DESC""")
            if cc:
                out.append(F("الداتا", "متوسطة", f"{sum(r['n'] for r in cc):,} سطر على حسابات لازم لها مركز تكلفة ومن غير مركز تكلفة ({len(cc)} حساب)",
                             "تقارير مراكز التكلفة هتطلع ناقصة", [{"الكود": r["Code"], "الحساب": r["ArName"], "سطور من غير مركز": r["n"]} for r in cc], len(cc)))
        if db.has("ChartOfAccount", "IsCustomer") and db.has("JournalEntryDetail", "CustomerId"):
            cu = db.rows(f"""SELECT TOP 100 a.Code, a.ArName, COUNT(*) n FROM JournalEntryDetail d JOIN JournalEntry je ON je.Id=d.JournalEntryId
                             JOIN ChartOfAccount a ON a.Id=d.AccountId WHERE a.IsCustomer=1 AND ISNULL(d.CustomerId,0)=0 {ndd} {nd}
                             GROUP BY a.Code, a.ArName ORDER BY COUNT(*) DESC""")
            if cu:
                out.append(F("الداتا", "متوسطة", f"{sum(r['n'] for r in cu):,} سطر على حساب عملاء من غير ما يتحدد العميل ({len(cu)} حساب)",
                             "كشف حساب العميل وأعمار الديون مش هيطابقوا رصيد حساب العملاء في الميزان",
                             [{"الكود": r["Code"], "الحساب": r["ArName"], "سطور من غير عميل": r["n"]} for r in cu], len(cu)))

    # documents ↔ journals, per source page
    if pages and db.has("JournalEntry", "SourcePageId"):
        miss, orphan = [], []
        for r in db.rows(f"SELECT je.SourcePageId sp, COUNT(*) n FROM JournalEntry je WHERE je.SourcePageId IS NOT NULL {nd} GROUP BY je.SourcePageId"):
            p = pages.get(r["sp"])
            if not p or not p.get("TableName") or not db.has(p["TableName"], "Id"):
                continue
            t = _q(p["TableName"])
            dele = "AND ISNULL(x.IsDeleted,0)=0" if db.has(p["TableName"], "IsDeleted") else ""
            try:
                o = db.one(f"""SELECT COUNT(*) FROM JournalEntry je WHERE je.SourcePageId=%s {nd} AND je.SourceId IS NOT NULL
                               AND NOT EXISTS (SELECT 1 FROM {t} x WHERE x.Id=je.SourceId {dele})""", r["sp"])
                docs = db.one(f"SELECT COUNT(*) FROM {t} x WHERE 1=1 {dele}")
                m = db.one(f"""SELECT COUNT(*) FROM {t} x WHERE 1=1 {dele} AND NOT EXISTS (SELECT 1 FROM JournalEntry je WHERE je.SourcePageId=%s AND je.SourceId=x.Id {nd})""", r["sp"])
            except Exception:
                continue
            if o:
                orphan.append({"الشاشة": p["ArName"], "الجدول": p["TableName"], "قيود بتشاور على مستند ممسوح / مش موجود": o})
            if m:
                miss.append({"الشاشة": p["ArName"], "الجدول": p["TableName"], "مستندات": docs, "من غير قيد": m, "النسبة": f"{100 * m / max(1, docs):.0f}%"})
        if orphan:
            out.append(F("الداتا", "عالية", f"قيود باقية لمستندات اتمسحت أو مش موجودة في {len(orphan)} شاشة ({sum(x['قيود بتشاور على مستند ممسوح / مش موجود'] for x in orphan)} قيد)",
                         "المستند اتمسح والقيد بتاعه فضل في الحسابات — الأرصدة غلط", orphan, len(orphan), fix="الحذف لازم يمسح / يعكس القيد في نفس الـ Transaction"))
        if miss:
            out.append(F("الداتا", "متوسطة", f"مستندات من غير قيد محاسبي في {len(miss)} شاشة",
                         "مش كل مستند لازم يكون ليه قيد (مسودات، أنواع معينة) — بس النسب العالية محتاجة مراجعة", miss, len(miss)))
    # duplicate document numbers
    dups = []
    for p in pages.values():
        t = p.get("TableName")
        if not t or not db.has(t, "DocumentNumber"):
            continue
        dele = "AND ISNULL(IsDeleted,0)=0" if db.has(t, "IsDeleted") else ""
        br = ", BranchId" if db.has(t, "BranchId") else ""
        try:
            n = db.one(f"SELECT COUNT(*) FROM (SELECT DocumentNumber{br} FROM {_q(t)} WHERE DocumentNumber IS NOT NULL AND DocumentNumber NOT IN ('', '0') {dele} GROUP BY DocumentNumber{br} HAVING COUNT(*) > 1) z")
        except Exception:
            continue
        if n:
            dups.append({"الشاشة": p["ArName"], "الجدول": t, "أرقام متكررة": n})
    if dups:
        dups.sort(key=lambda x: -x["أرقام متكررة"])
        out.append(F("الداتا", "متوسطة", f"أرقام مستندات متكررة في {len(dups)} جدول", "رقم المستند المفروض يكون فريد (في نفس الفرع) — التكرار بيلخبط الترحيل والفاتورة الإلكترونية",
                     dups, len(dups), fix="Unique index على رقم المستند + الفرع"))
    out += shadow_accountant(db, log)
    return out


def _dominant(rows, formulas, tol=0.011):
    """formulas: {name: fn(row) -> (expected, actual)} → (best name, share, failures)"""
    best = None
    for name, fn in formulas.items():
        ok, bad = 0, []
        for r in rows:
            try:
                e, a = fn(r)
            except (TypeError, ValueError):
                continue
            if abs(float(e) - float(a)) <= tol:
                ok += 1
            else:
                bad.append((r, float(e), float(a)))
        if not best or ok > best[1]:
            best = (name, ok, bad)
    if not best or not rows:
        return None, 0, []
    return best[0], best[1] / len(rows), best[2]


def shadow_accountant(db, log):
    """every invoice recomputed from its lines and compared with what the ERP saved (the rule is learnt from the data)"""
    out = []
    for head, det, label in (("SalesInvoice", "SalesInvoiceDetails", "فواتير البيع"), ("PurchaseInvoice", "PurchaseInvoiceDetails", "فواتير الشراء"),
                             ("SalesReturns", "SalesReturnsDetails", "مرتجعات البيع"), ("PurchaseReturns", "PurchaseReturnsDetails", "مرتجعات الشراء")):
        if not (db.has(head) and db.has(det) and db.has(det, "MainDocId") and db.has(head, "Total") and db.has(det, "Qty") and db.has(det, "Price")):
            continue
        dele = "AND ISNULL(h.IsDeleted,0)=0" if db.has(head, "IsDeleted") else ""
        ddel = "AND ISNULL(d.IsDeleted,0)=0" if db.has(det, "IsDeleted") else ""
        dv = "ISNULL(d.DiscountValue,0)" if db.has(det, "DiscountValue") else "0"
        hc = [c for c in ("TotalItemsDiscount", "VoucherDiscountValue", "SalesTaxes", "PurchaseTaxes", "Taxes", "TotalAfterTaxes", "NetTotal") if db.has(head, c)]
        rows = db.rows(f"""SELECT h.Id, h.DocumentNumber, h.Total, {', '.join('h.' + c for c in hc) or '0 x'},
                             (SELECT SUM(ISNULL(d.Qty,0) * ISNULL(d.Price,0)) FROM {det} d WHERE d.MainDocId=h.Id {ddel}) lines,
                             (SELECT SUM({dv}) FROM {det} d WHERE d.MainDocId=h.Id {ddel}) ldisc,
                             (SELECT COUNT(*) FROM {det} d WHERE d.MainDocId=h.Id {ddel}) n
                           FROM {head} h WHERE 1=1 {dele}""")
        withl = [r for r in rows if r["n"]]
        nolines = [r for r in rows if not r["n"] and float(r["Total"] or 0)]
        if nolines:
            out.append(F("الداتا", "متوسطة", f"{label}: {len(nolines)} مستند ليه إجمالي ومن غير ولا سطر", "الإجمالي متخزن بس السطور اتمسحت أو ماتحفظتش",
                         [{"المستند": r["Id"], "الرقم": r["DocumentNumber"], "الإجمالي": float(r["Total"] or 0)} for r in nolines], len(nolines)))
        if len(withl) < 5:
            continue
        f = lambda v: float(v or 0)
        name, share, bad = _dominant(withl, {
            "الإجمالي = مجموع (الكمية × السعر)": lambda r: (f(r["lines"]), f(r["Total"])),
            "الإجمالي = مجموع (الكمية × السعر) − خصم السطور": lambda r: (f(r["lines"]) - f(r["ldisc"]), f(r["Total"])),
        })
        log(f"🧮 {label}: القاعدة «{name}» ماشية على {share:.0%}")
        if name and share >= 0.6 and bad:
            out.append(F("الداتا", "عالية", f"المحاسب الظل — {label}: {len(bad)} مستند إجماليه مش طالع من سطوره",
                         f"القاعدة اللي ماشية على {share:.0%} من المستندات: {name}. المستندات دي مخالفة لها",
                         [{"المستند": r["Id"], "الرقم": r["DocumentNumber"], "المحسوب من السطور": round(e, 2), "المتخزن": round(a, 2), "الفرق": round(a - e, 2)} for r, e, a in bad], len(bad),
                         fix="افتح المستند وشوف السطر اللي اتعدل من غير ما الإجمالي يتحدث"))
        tax = next((c for c in ("SalesTaxes", "PurchaseTaxes", "Taxes") if c in hc), None)
        if tax and "TotalAfterTaxes" in hc:
            disc = [c for c in ("TotalItemsDiscount", "VoucherDiscountValue") if c in hc]
            name2, share2, bad2 = _dominant(withl, {
                "الإجمالي بعد الضريبة = الإجمالي + الضريبة": lambda r: (f(r["Total"]) + f(r[tax]), f(r["TotalAfterTaxes"])),
                "الإجمالي بعد الضريبة = الإجمالي − الخصومات + الضريبة": lambda r: (f(r["Total"]) - sum(f(r[c]) for c in disc) + f(r[tax]), f(r["TotalAfterTaxes"])),
            })
            if name2 and share2 >= 0.6 and bad2:
                out.append(F("الداتا", "عالية", f"المحاسب الظل — {label}: {len(bad2)} مستند الإجمالي بعد الضريبة فيه غلط",
                             f"القاعدة اللي ماشية على {share2:.0%}: {name2}",
                             [{"المستند": r["Id"], "الرقم": r["DocumentNumber"], "المحسوب": round(e, 2), "المتخزن": round(a, 2), "الفرق": round(a - e, 2)} for r, e, a in bad2], len(bad2)))
            taxed = [r for r in withl if f(r[tax])]
            off = []
            for r in taxed:
                base_ = f(r["Total"]) - sum(f(r[c]) for c in disc)
                if base_ > 0:
                    rate = f(r[tax]) / base_
                    if abs(rate - 0.15) > 0.002 and abs(f(r[tax]) / max(0.01, f(r["Total"])) - 0.15) > 0.002:
                        off.append({"المستند": r["Id"], "الرقم": r["DocumentNumber"], "الأساس": round(base_, 2), "الضريبة": round(f(r[tax]), 2), "النسبة": f"{rate:.2%}"})
            if off and len(off) < len(taxed) * 0.5:
                out.append(F("الداتا", "متوسطة", f"المحاسب الظل — {label}: {len(off)} مستند ضريبته مش 15% من الأساس",
                             "ممكن يكون صنف معفي أو بنسبة مختلفة — بس لازم يتراجع قبل إقرار الضريبة", off, len(off)))
    return out


# ------------------------------------------------------------------ 3b) run the report / read procedures for real
SKIP_RUN = re.compile(r"(Delete|Insert|Update|Fix|Close|Open|Sync|Import|Upload|Send|Post|Generate|Recalc|Rebuild|Backup|Restore|Shrink|Job|Save|Add|Edit|Remove|Clear|Reset|Migrate|Transfer|Approve|Cancel|Move|Copy|Create|Set|Merge|Archive|Purge|Notify|Mail|Sms|Exec|Run)", re.I)
TYPE_VAL = {"date": "'{f}'", "datetime": "'{f}'", "datetime2": "'{f}'", "smalldatetime": "'{f}'", "bit": "0", "int": "NULL", "bigint": "NULL", "smallint": "NULL",
            "tinyint": "NULL", "decimal": "NULL", "numeric": "NULL", "money": "NULL", "float": "NULL", "nvarchar": "NULL", "varchar": "NULL", "nchar": "NULL",
            "char": "NULL", "uniqueidentifier": "NULL"}


def _classify(msg):
    m = msg.lower()
    for pat, kind, sev in ((r"invalid object name", "جدول / إجراء مش موجود", "عالية"), (r"invalid column name", "عمود مش موجود", "عالية"),
                           (r"could not find stored procedure", "بينادي إجراء مش موجود", "عالية"), (r"divide by zero", "قسمة على صفر", "عالية"),
                           (r"conversion failed|error converting|arithmetic overflow", "تحويل نوع / أرقام كبيرة", "متوسطة"),
                           (r"subquery returned more than 1 value", "استعلام فرعي رجّع أكتر من قيمة", "عالية"),
                           (r"ambiguous column", "اسم عمود مش واضح", "عالية"), (r"was specified multiple times", "عمود متكرر في نفس الاستعلام", "عالية"),
                           (r"timeout|timed out", "أبطأ من الحد", "متوسطة")):
        if re.search(pat, m):
            return kind, sev
    return None, None


def check_runtime(conn_factory, db, log, limit=3000, per=25, budget=900):
    """EXEC each report / read procedure with typical parameters (dates = this year, the rest NULL) inside a transaction that is
    always rolled back — on the COPY only. Finds procedures that crash at run time and the slow ones."""
    out = []
    procs = db.rows("""SELECT p.object_id i, SCHEMA_NAME(p.schema_id) s, p.name n FROM sys.procedures p WHERE p.is_ms_shipped=0
                       AND (p.name LIKE '%Report%' OR p.name LIKE '%Get%' OR p.name LIKE '%Select%' OR p.name LIKE '%List%' OR p.name LIKE '%Statement%' OR p.name LIKE '%Balance%')
                       ORDER BY p.name""")
    procs = [p for p in procs if not SKIP_RUN.search(re.sub(r"(Report|Get|Select|List|Statement|Balance)", "", p["n"], flags=re.I))][:limit]
    params = {}
    for r in db.rows("""SELECT p.object_id i, p.name pn, TYPE_NAME(p.user_type_id) t, p.is_output o, p.has_default_value hd FROM sys.parameters p
                        JOIN sys.procedures x ON x.object_id=p.object_id WHERE x.is_ms_shipped=0 ORDER BY p.object_id, p.parameter_id"""):
        params.setdefault(r["i"], []).append(r)
    y0 = f"{datetime.now().year}-01-01"
    today = datetime.now().strftime("%Y-%m-%d")
    log(f"⚙️ بشغّل {len(procs)} إجراء تقارير / قراءة على النسخة (كل واحد جوه Transaction بتترجع)")
    c2 = conn_factory(per)
    cur = c2.cursor()
    crashes, slow, other, ok, t0 = [], [], [], 0, time.time()
    for p in procs:
        if time.time() - t0 > budget:
            log("⚙️ وقفت بعد الوقت المحدد — الباقي المرة الجاية")
            break
        args, decl = [], []
        for a in params.get(p["i"], []):
            t = (a["t"] or "").lower()
            if a["o"]:
                v = f"@o{len(decl)}"
                decl.append(f"DECLARE {v} {t if t not in ('nvarchar', 'varchar', 'decimal', 'numeric') else ('nvarchar(4000)' if 'char' in t else 'decimal(18,4)')};")
                args.append(f"{a['pn']}={v} OUTPUT")
                continue
            val = TYPE_VAL.get(t, "NULL")
            nm = a["pn"].lstrip("@").lower().replace("_", "")
            if re.search(r"(pagesize|take|top|rows|length|limit|count|perpage|fetch)$", nm) and "int" in t:
                val = "50"
            elif re.search(r"(pagenumber|pageindex|pageno|page)$", nm) and "int" in t:
                val = "1"
            elif re.search(r"(start|skip|offset)$", nm) and "int" in t:
                val = "0"
            elif re.search(r"^(lang|language|culture)$", nm) and "char" in t:
                val = "'ar'"
            elif re.search(r"(search|filter|term|keyword|text|q|searchword)$", nm) and "char" in t:
                val = "''"
            if "{f}" in val:
                val = val.format(f=today if re.search(r"to|end|till|until", a["pn"], re.I) else y0)
            args.append(f"{a['pn']}={val}")
        sql = " ".join(decl) + f" EXEC [{p['s']}].[{p['n']}] " + ", ".join(args)
        t1 = time.time()
        try:
            cur.execute("SET XACT_ABORT OFF; BEGIN TRAN;")
            cur.execute(sql)
            while True:
                if cur.description:
                    cur.fetchmany(50)
                if not cur.nextset():
                    break
            ok += 1
            sec = time.time() - t1
            if sec > 8:
                slow.append({"الإجراء": p["n"], "الوقت (ث)": round(sec, 1)})
        except Exception as e:
            sec = time.time() - t1
            msg = re.sub(r"\s+", " ", str(e))
            kind, sev = _classify(msg)
            clean = re.sub(r"DB-Lib error message.*$", "", re.sub(r"^\(\d+, b?['\"]", "", msg)).strip()[:180]
            if kind:
                crashes.append({"الإجراء": p["n"], "المشكلة": kind, "sev": sev, "الرسالة": clean})
            elif not re.search(r"expects parameter|too many arguments|is not a parameter|must declare|DB-Lib error message 20018, severity 16:\\nGeneral SQL Server error: Check messages from the SQL Server\\n'\)$", msg, re.I):
                other.append({"الإجراء": p["n"], "الرسالة": clean})
            if "timeout" in msg.lower() or sec >= per - 1:
                c2 = conn_factory(per)
                cur = c2.cursor()
                continue
        finally:
            try:
                cur.execute("IF @@TRANCOUNT > 0 ROLLBACK;")
            except Exception:
                try:
                    c2 = conn_factory(per)
                    cur = c2.cursor()
                except Exception:
                    break
    log(f"⚙️ اشتغل {ok} إجراء سليم · {len(crashes)} وقع · {len(slow)} بطيء")
    hi = [x for x in crashes if x["sev"] == "عالية"]
    mid = [x for x in crashes if x["sev"] != "عالية"]
    for lst, sev, title in ((hi, "عالية", "إجراء تقارير / قراءة بيقع لما يشتغل فعلًا"), (mid, "متوسطة", "إجراء بيقع بخطأ تحويل أو بياخد أكتر من الحد")):
        if lst:
            out.append(F("التشغيل", sev, f"{len(lst)} {title}", "اتشغل على النسخة بقيم عادية (تواريخ السنة دي والباقي فاضي) — نفس اللي بيحصل لما مستخدم يفتح التقرير من غير فلاتر",
                         [{k: v for k, v in x.items() if k != "sev"} for x in lst], len(lst), fix="افتح الإجراء وصلّح السطر اللي في الرسالة", key=f"run_{sev}"))
    if slow:
        slow.sort(key=lambda x: -x["الوقت (ث)"])
        out.append(F("التشغيل", "متوسطة", f"{len(slow)} إجراء بياخد أكتر من 8 ثواني على داتا موقع الاختبار", "عند عميل داتاه أكبر هيبقى أبطأ بكتير", slow, len(slow),
                     fix="راجع خطة التنفيذ والفهارس", key="run_slow"))
    if other:
        out.append(F("التشغيل", "منخفضة", f"{len(other)} إجراء وقع بخطأ تاني (محتاج مراجعة يدوية)", "ممكن يكون محتاج قيم فلاتر معينة علشان يشتغل", other, len(other), key="run_other"))
    out.append(F("التشغيل", "للعلم", f"اتشغل {ok + len(crashes) + len(other)} إجراء من {len(procs)} — {ok} اشتغلوا من غير مشاكل", count=ok, key="run_total"))
    return out


# ------------------------------------------------------------------ 4) the map (seed of the digital twin)
def build_map(db, log):
    pages = db.rows("SELECT Id, ArName, EnName, TableName, ControllerName, IsReport, IsTransaction FROM SystemPage WHERE ISNULL(IsDeleted,0)=0") if db.has("SystemPage") else []
    deps = db.rows("""SELECT DISTINCT OBJECT_NAME(d.referencing_id) p, d.referenced_entity_name r FROM sys.sql_expression_dependencies d
                      JOIN sys.objects o ON o.object_id=d.referencing_id JOIN sys.tables tb ON tb.object_id=d.referenced_id WHERE o.type IN ('P','V','FN','IF','TF','TR')""")
    defs = {r["n"]: re.sub(r"--[^\n]*|/\*.*?\*/", " ", r["d"] or "", flags=re.S) for r in
            db.rows("SELECT o.name n, m.definition d FROM sys.sql_modules m JOIN sys.objects o ON o.object_id=m.object_id WHERE o.is_ms_shipped=0")}
    for r in deps:
        t = re.escape(r["r"])
        r["w"] = bool(re.search(rf"\b(INSERT\s+(INTO\s+)?|UPDATE\s+|DELETE\s+(FROM\s+)?|MERGE\s+(INTO\s+)?)(\[?dbo\]?\.)?\[?{t}\]?(\s|\(|$)", defs.get(r["p"], ""), re.I))
    by_table = {}
    for r in deps:
        e = by_table.setdefault(r["r"], {"read": [], "write": []})
        e["write" if r["w"] else "read"].append(r["p"])
    for e in by_table.values():
        e["read"] = sorted(set(e["read"]) - set(e["write"]))[:200]
        e["write"] = sorted(set(e["write"]))[:200]
    log(f"🗺️ الخريطة: {len(pages)} شاشة في SystemPage · {len(by_table)} جدول ليه إجراءات")
    return {"pages": [{"id": p["Id"], "ar": p["ArName"], "en": p["EnName"], "table": p["TableName"], "controller": p["ControllerName"],
                       "report": bool(p["IsReport"]), "doc": bool(p["IsTransaction"])} for p in pages], "tables": by_table}


# ------------------------------------------------------------------ the run
def run(conn=None, log=None, label="", conn_factory=None, run_procs=True, proc_limit=3000):
    log = log or (lambda m: logger.info(m))
    if conn is None:
        conn = connect()
        conn_factory = conn_factory or (lambda t: connect_timeout(t))
    db = DB(conn)
    t0 = time.time()
    info = db.rows("""SELECT DB_NAME() db, @@VERSION v, (SELECT COUNT(*) FROM sys.tables WHERE is_ms_shipped=0) tables,
                      (SELECT COUNT(*) FROM sys.procedures WHERE is_ms_shipped=0) procs, (SELECT COUNT(*) FROM sys.views WHERE is_ms_shipped=0) views,
                      (SELECT COUNT(*) FROM sys.objects WHERE type IN ('FN','IF','TF') AND is_ms_shipped=0) funcs,
                      (SELECT COUNT(*) FROM sys.triggers WHERE parent_class=1) triggers""")[0]
    log(f"🗄️ {info['db']}: {info['tables']} جدول · {info['procs']} إجراء · {info['views']} فيو · {info['funcs']} فانكشن")
    findings, sections = [], {}
    steps = [("الهيكل", check_structure), ("الكود", check_code), ("الداتا", check_data)]
    if conn_factory and run_procs:
        steps.append(("التشغيل", lambda d, l: check_runtime(conn_factory, d, l, limit=proc_limit)))
    for name, fn in steps:
        t1 = time.time()
        try:
            r = fn(db, log)
            got = r[0] if isinstance(r, tuple) else r
            findings += got
            sections[name] = {"secs": round(time.time() - t1), "n": len(got)}
        except Exception as e:
            sections[name] = {"secs": round(time.time() - t1), "error": str(e)[:300]}
            log(f"⚠️ {name}: {e}")
            try:
                conn.rollback()
            except Exception:
                pass
    try:
        mp = build_map(db, log)
    except Exception as e:
        mp = {"pages": [], "tables": {}, "error": str(e)[:200]}
    findings.sort(key=lambda f: (SEV.get(f["sev"], 9), f["area"]))
    prev = load() or {}
    old = {f["id"] for f in prev.get("findings") or []}
    for f in findings:
        f["new"] = bool(prev) and f["id"] not in old
    res = {"at": datetime.now().strftime("%Y-%m-%d %H:%M"), "secs": round(time.time() - t0), "label": label or info["db"],
           "info": {k: (v.split("\n")[0][:120] if isinstance(v, str) else v) for k, v in info.items()}, "sections": sections, "findings": findings, "map": mp,
           "fixed": [{"area": f["area"], "title": f["title"]} for f in prev.get("findings") or [] if f["id"] not in {x["id"] for x in findings}]}
    save_result(res)
    log(f"🗄️ خلص في {res['secs']} ث — " + " · ".join(f"{s}: {sum(1 for f in findings if f['sev'] == s)}" for s in SEV))
    return res


def run_check(driver, credentials, cfg, result=None):
    """queue entry point (no browser needed) — uses the saved connection"""
    result = result if result is not None else {}
    res = run(label=cfg.get("label") or "")
    result["detail"] = {"title": f"🗄️ فحص قاعدة البيانات — {res['label']}", "columns": ["النوع", "الخطورة", "الملاحظة", "العدد", "التصليح"],
                        "rows": [{"cells": [f["area"], f["sev"], f["title"], f.get("count") or "", f.get("fix", "")], "ok": False if f["sev"] in ("عالية", "متوسطة") else None}
                                 for f in res["findings"]], "note": f"{res['info']['tables']} جدول · {res['info']['procs']} إجراء — {len(res['findings'])} ملاحظة"}
    return result


def support_issues():
    d = load()
    if not d:
        return []
    out = []
    for f in d.get("findings") or []:
        if f["sev"] not in ("عالية", "متوسطة"):
            continue
        lines = "\n".join(" · ".join(f"{k}: {v}" for k, v in r.items()) for r in (f.get("sample") or [])[:15])
        out.append({"id": "dbaudit-" + f["id"][:120], "site": d.get("label") or "قاعدة البيانات", "url": "", "source": "فحص قاعدة البيانات", "screen": f["area"],
                    "severity": f["sev"], "title": f["title"][:200], "details": (f.get("detail") or "") + ("\n\n" + lines if lines else "") + ("\n\nالتصليح: " + f["fix"] if f.get("fix") else ""),
                    "evidence": f"فحص {d['at']} على {d['info'].get('db')}", "doc": "", "steps": "افتح «فحص قاعدة البيانات» في الأداة", "found": d["at"][:10]})
    return out
