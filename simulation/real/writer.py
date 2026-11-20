"""
✍️ Real documents on NQ ERP — through the engine of the testing tool (erp-automation), in the employee's own browser.

  • add    : reads the add form of THIS site (its required fields), fills it like a person, saves, then checks the save:
             the system's message, the new row on top of the list, and the document opened again with every value compared
  • edit   : opens the SAME document the employee made, changes it, saves, opens it again and compares
  • print  : prints that document and checks the print page opened, isn't empty and has no error
  • delete : deletes ONLY a document the company made itself (kept in runs/created.json), then checks it left the list
  • review : the trial balance (debit = credit, parents = sum of children) and today's journal entries (each one balanced),
             read from the site's own data

Test sites only: on a site marked «نظام عميل» nothing is written (and the engine's own guard refuses too).
"""
import json
import os
import re
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
from simulation.settings import RUNS  # noqa: E402
LEDGER = RUNS / "created.json"
# the company's screens that make documents (the others are opened / read)
WRITES = {"payroll", "quotation", "sales_order", "purchase_order", "stock_receipt", "purchase_invoice", "stock_issue", "sales_invoice", "receipt_voucher",
          "sales_return", "purchase_request", "purchase_return", "payment_voucher", "stock_transfer", "journal_entry"}
REVIEWS = {"trial_balance", "journal_review"}


def find_engine(hint=""):
    """the folder of the testing tool: the one in the settings, else next to this program"""
    cands = [str(ROOT), hint, os.getenv("NQ_ENGINE", "")]                # one program now: the engine sits beside simulation/
    for up in (ROOT.parent, ROOT.parent.parent):
        cands += [str(up / n) for n in ("erp-automation", "erppautomichan", "erp_automation")]
    for c in cands:
        if c and (Path(c) / "engine" / "auto_test.py").exists():
            return str(Path(c).resolve())
    return ""


# what a person in the company really picks on these screens (the tool's «first option» picked an export invoice and
# a split payment, which the system rightly refuses): option words, matched against the list's own options
PREFER = {
    "sales_invoice": {"InvoiceTypeId": "فاتورة ضريبيه - 1", "PaymentType": "آجل"},
    "purchase_invoice": {"PaymentType": "آجل"},
    "receipt_voucher": {"SourceTypeId": "عميل"},
    "payment_voucher": {"SourceTypeId": "مورد"},
    "sales_return": {"PaymentType": "آجل"},
    "purchase_return": {"PaymentType": "آجل"},
    "sales_order": {"OrderTypeId": "جديد"},
    "quotation": {"OrderTypeId": "جديد"},
}


def _prefer(key, fields):
    want = PREFER.get(key) or {}
    out = []
    for f in fields:
        w = want.get(f.get("id"))
        if w:
            opts = [o for o in (f.get("options") or []) if w in str(o.get("text", o) if isinstance(o, dict) else o)]
            val = (opts[0].get("text") if isinstance(opts[0], dict) else opts[0]) if opts else w
            f = {**f, "strategy": "fixed", "value": val, "soft": False}
        out.append(f)
    return out


ITEM_RE = re.compile(r"صنف «(?P<item>[^»]+)».*?الكمية (?P<qty>[\d.,]+).*?السعر (?P<price>[\d.,]+)")
PARTY = re.compile(r"^(العميل|المورد|العميل / المورد|المورد / العميل|من|الى|إلى)\s*:?$")
TOTAL_RE = re.compile(r"(?<![\d/])\d[\d,]*\.\d{2}(?![\d/])")


def _num(t):
    try:
        return float(str(t).replace(",", ""))
    except ValueError:
        return None


def facts(res, no=""):
    """what was REALLY entered and saved on the site — for the employees' chat and the deal (no invented names)"""
    out = {"no": str(no or "")}
    for st in (res or {}).get("steps") or []:
        lab, val = str(st.get("label") or "").strip(), str(st.get("result") or "").strip()
        m = ITEM_RE.search(lab) or ITEM_RE.search(val)
        if m and "item" not in out:
            out.update(item=m["item"], qty=_num(m["qty"]), price=_num(m["price"]))
        elif PARTY.match(lab) and val and "party" not in out and st.get("ok"):
            out["party"] = re.sub(r"^\s*[\w.-]*\d[\w.-]*\s*-\s*", "", val).strip()      # «14 - شركة …» → «شركة …»
    row = str((res or {}).get("first_row_after") or (res or {}).get("row") or "")
    tot = TOTAL_RE.findall(row)
    if tot:
        out["total"] = _num(tot[-1])
    return out


OFFLINE = re.compile(r"ERR_INTERNET_DISCONNECTED|ERR_NAME_NOT_RESOLVED|ERR_CONNECTION_|ERR_NETWORK_|ERR_TIMED_OUT|ERR_ADDRESS_UNREACHABLE|ERR_PROXY")
FLAG = re.compile(r"^(true|false|نعم|لا|0|)$", re.I)


def _first(text):
    for x in str(text or "").split("\n"):
        x = x.strip(" ❌")
        if x and "Session info" not in x:
            return x[:220]
    return ""


HERE = Path(__file__).resolve().parent
EVID = RUNS / "evidence"          # pictures of the refused pages (the developers' tickets)
# scripted steps before the save, per screen (the engine runs them after filling the form, before «حفظ»)
BEFORE_SAVE = {
    "journal_entry": lambda: [{"label": "سطرين القيد: مدين مصروف / دائن إيراد", "js": (HERE / "je_lines.js").read_text(encoding="utf-8"),
                               "args": [150], "timeout": 45}],
    "stock_receipt": lambda: [{"label": "صنف في السند: باركود + Enter", "js": (HERE / "receipt_lines.js").read_text(encoding="utf-8"),
                               "args": [2], "timeout": 30}],
}


class Ledger:
    """the documents the company made on each site — the only ones it may delete"""
    lock = threading.Lock()

    @classmethod
    def _all(cls):
        try:
            return json.loads(LEDGER.read_text(encoding="utf-8"))
        except Exception:
            return []

    @classmethod
    def add(cls, site, screen, no, by, deal):
        with cls.lock:
            a = cls._all()
            a.append({"site": site, "screen": screen, "no": str(no), "by": by, "deal": deal or "", "at": datetime.now().isoformat(timespec="seconds")})
            LEDGER.parent.mkdir(parents=True, exist_ok=True)
            LEDGER.write_text(json.dumps(a[-3000:], ensure_ascii=False, indent=0), encoding="utf-8")

    @classmethod
    def ours(cls, site, screen, no):
        return any(x["site"] == site and x["screen"] == screen and x["no"] == str(no) and not x.get("deleted") for x in cls._all())

    @classmethod
    def deleted(cls, site, screen, no):
        with cls.lock:
            a = cls._all()
            for x in a:
                if x["site"] == site and x["screen"] == screen and x["no"] == str(no):
                    x["deleted"] = datetime.now().isoformat(timespec="seconds")
            LEDGER.write_text(json.dumps(a, ensure_ascii=False, indent=0), encoding="utf-8")


class Writer:
    """one per run; the engine keeps its run variables in one place, so its jobs go one at a time"""
    _site_loaded = None

    def __init__(self, engine_path, base, user, pw, site_id, site_kind):
        self.ok, self.why = False, ""
        self.base, self.site = base.rstrip("/"), site_id
        self.cred = {"username": user, "password": pw}
        self.lock = threading.Lock()
        self.plans = {}
        if site_kind != "test":
            self.why = "الموقع متسجل «نظام عميل» — قراءة بس، مفيش حفظ ولا تعديل ولا حذف"
            return
        path = find_engine(engine_path)
        if not path:
            self.why = ("مالقيتش أداة الاختبار (erp-automation) — اكتب مكانها في الإعدادات ← «أداة الاختبار»"
                        " عشان الموظفين يحفظوا مستندات حقيقية")
            return
        if Writer._site_loaded and Writer._site_loaded != self.base:
            self.why = f"الأداة اتحملت على موقع تاني ({Writer._site_loaded}) — اقفل البرنامج وافتحه تاني عشان يشتغل على {self.base}"
            return
        # the engine reads its site from the environment when it is imported (our site, our user — not its own profiles)
        os.environ.update({"BASE_URL": self.base, "LOGIN_USERNAME": user, "LOGIN_PASSWORD": pw, "SITE_PROFILE": "__virtual_company__",
                           "SITE_KIND": "test", "LOGIN_ACTIVITY": os.environ.get("LOGIN_ACTIVITY", ""), "LOGIN_BRANCH": os.environ.get("LOGIN_BRANCH", "")})
        if path not in sys.path:
            sys.path.insert(0, path)
        try:
            from config import settings as cs
            from engine import auto_test, screen_runner          # noqa: F401
            if cs.BASE_URL.rstrip("/") != self.base:
                self.why = f"الأداة شايفة موقع تاني ({cs.BASE_URL}) — اقفل البرنامج وافتحه تاني"
                return
            if cs.READ_ONLY:
                self.why = "أداة الاختبار شايفة الموقع «نظام عميل» — مفيش كتابة"
                return
        except Exception as e:
            self.why = (f"أداة الاختبار ({path}) ما اشتغلتش: {type(e).__name__}: {str(e)[:160]} — "
                        "شغّل start.bat تاني (بيسطّب المكتبات بتاعتها)")
            return
        Writer._site_loaded = self.base
        self.path, self.ok = path, True

    # ------------------------------------------------------------------ the plan of a screen (read once per run)
    def _plan(self, driver, key, path, name):
        if key in self.plans:
            return self.plans[key]
        from engine import auto_test as A
        from engine.form_inspector import FormInspector
        from config.screens_catalog import all_pages
        u = A._u(path)
        cat = next((k for k, p in all_pages().items() if A._u(p.get("url")) == u), None)
        info = None
        if cat:
            try:
                info = A.screen_info(cat)          # the tool's own setup of this screen (items, buttons) when it has one
            except Exception:
                info = None
        if not info:
            info = {"key": "vc_" + key, "name": name, "list_url": path, "add_url": "", "add_button": "", "builder": None}
        insp = A._form_cache(info["key"], hours=24)
        if insp and not A._usable(insp.get("fields") or []):
            insp = None                                     # a bad read kept from last time: read the form again
        for attempt in (1, 2):
            if not insp:
                insp = FormInspector(driver).inspect(info["list_url"], info["add_url"], info["add_button"], find_dependencies=attempt == 1)
            if A._usable(insp.get("fields") or []):
                A._form_cache(info["key"], save=insp)
                break
            if attempt == 1:
                A._form_cache(info["key"], hours=-1)
                insp = None
                time.sleep(3)
        read = insp.get("fields") or []
        usable = A._usable(read)
        if not usable:
            kinds = {}
            for f in read:
                why = "مخفي" if not f.get("visible") else "مقفول" if f.get("disabled") else "في جدول الأصناف" if f.get("in_table") else f.get("kind")
                kinds[why] = kinds.get(why, 0) + 1
            raise AssertionError(f"قريت فورم الإضافة مرتين ({insp.get('add_url') or path}) ومالقيتش حقل أقدر أملاه — "
                                 f"لقيت {len(read)} حقل: " + "، ".join(f"{v} {k}" for k, v in kinds.items()))
        req = [f for f in usable if f.get("required")]
        mode = "required" if req else "all"
        base = A._base(info, insp)
        A.set_hint(info["name"])
        flds, _ = A.build_fields(read, mode, "first", info["builder"])
        flds = _prefer(key, flds)
        ed, _ = A.build_fields(read, mode, "random", None, editing=True)
        locked = re.compile(r"warehouse|store|branch|currency|doctype|مخزن|مستودع|فرع|عملة", re.I)   # a saved document's header: NQ ERP refuses changing these (by design)
        ed = [{**f, "optional": True, "soft": True} for f in ed if f["strategy"] != "keep" and not locked.search(str(f))] or flds[:1]
        p = {"info": info, "base": base, "read": read, "mode": mode, "fields": flds, "edit_fields": ed,
             "add": A._variant(base, "vc_add", fields=flds, auto_complete=True, verify={**base["verify"], "new_first_row": True, "open_saved": True})}
        self.plans[key] = p
        return p

    def _op(self, p, way, no):
        from engine import auto_test as A
        b = p["base"]
        if way == "edit":
            return A._variant(b, "vc_edit", operation="edit", target_row=str(no), fields=p["edit_fields"], flows=[], auto_complete=True,
                              verify={**b["verify"], "open_saved": True})
        return A._variant(b, "vc_" + way, operation=way, target_row=str(no), fields=[], flows=[])

    # ------------------------------------------------------------------ add / edit / print / delete
    def run(self, driver, key, path, name, act, no=None, emp="", deal="", cred=None, want=None, live=None):
        """one job + its evidence: a refused / wrong result keeps the page's picture and address for the developers' ticket"""
        self._prep = []
        r = self._run(driver, key, path, name, act, no, emp, deal, cred, want, live)
        if want and want.get("mutate"):                      # did the test's wrong field really go in? (no field = nothing proven)
            mp = [p for p in getattr(self, "_prep", []) if str(p.get("label", "")).startswith("🧪")]
            r["notarget"] = bool(mp and (mp[-1].get("notarget") or not mp[-1].get("ok")))
            r["probe_log"] = " · ".join(map(str, (mp[-1].get("log") if mp else []) or []))
            if mp and mp[-1].get("lines"):
                r["lines"] = mp[-1]["lines"]
        if r.get("kind") in ("reject", "wrong") or (r.get("kind") == "error" and not r.get("tool")):
            try:
                EVID.mkdir(parents=True, exist_ok=True)
                f = EVID / f"{datetime.now():%Y%m%d_%H%M%S}_{key}_{act}.png"
                driver.save_screenshot(str(f))
                r["shot"], r["url"] = f.name, driver.current_url
            except Exception:
                pass
        return r

    def _run(self, driver, key, path, name, act, no=None, emp="", deal="", cred=None, want=None, live=None):
        """-> {kind, ms, msg, note, evidence, doc_no}"""
        from engine import auto_test as A
        from engine.screen_runner import run_screen, RUN_VARS
        from engine.form_filler import FieldFillError
        from engine.guard import ReadOnlySite
        way = {"open": "add"}.get(act, act)
        t0 = time.time()
        if way in ("edit", "print", "delete") and not no:
            word = {"edit": "التعديل", "print": "الطباعة", "delete": "الحذف"}[way]
            return {"kind": "skip", "ms": 0, "msg": f"مفيش مستند عمله الموظف في «{name}» أعمل عليه {word} (الإضافة ما اتحفظتش قبلها)"}
        if way in ("edit", "delete") and not Ledger.ours(self.site, key, no):
            word = {"edit": "أعدّل", "delete": "أحذف"}[way]
            return {"kind": "skip", "ms": 0, "msg": f"🔒 مش هـ{word} المستند {no}: مش من المستندات اللي الشركة عملتها (أو رقمه مش مؤكد)"}
        with self.lock:
            if cred:
                self.cred = cred
            try:
                p = self._plan(driver, key, path, name)
            except Exception as e:
                return {"kind": "error", "tool": True, "ms": int((time.time() - t0) * 1000),
                        "msg": f"مقدرتش أقرا فورم «{name}»: {_first(e)}"}
            RUN_VARS.clear()
            res, err, tries = {}, "", []
            if want and want.get("party") and way == "add":         # the deal's real customer / supplier, picked like a person would
                p = {**p, "add": {**p["add"], "fields": [({**f, "strategy": "fixed", "value": want["party"], "soft": True}
                                                          if f.get("id") in ("VendorOrCustomerId", "VendorId", "CustomerId") else f)
                                                         for f in p["add"]["fields"]]}}
            if want and want.get("based") and way == "add":         # «بناءً على» = the source document the company itself just saved
                b = want["based"]
                p = {**p, "add": {**p["add"], "fields": [({**f, "strategy": "fixed", "value": b[f["id"]], "soft": True} if f.get("id") in b else f)
                                                         for f in p["add"]["fields"]]}}
            if want and want.get("date") and way == "add":          # 🕵️ a document dated years back: every date field of the form
                dates = [{k: f[k] for k in ("id", "kind", "label") if k in f} for f in (p.get("read") or [])
                         if f.get("kind") == "date" and not f.get("in_table") and not f.get("disabled") and f.get("visible") is not False]
                ids = {f["id"] for f in dates}
                p = {**p, "add": {**p["add"], "fields": [f for f in p["add"]["fields"] if f.get("id") not in ids] +
                                  [{**f, "strategy": "fixed", "value": want["date"], "soft": True} for f in dates]}}
            if want and want.get("note") and way in ("add", "edit"):  # the story's «البيان»: why this document exists today
                nf = self._note_field(p)
                if nf:
                    f2 = {**nf, "strategy": "fixed", "value": want["note"][:200], "soft": True, "optional": True}
                    if way == "add":
                        p = {**p, "add": {**p["add"], "fields": [f for f in p["add"]["fields"] if f.get("id") != nf["id"]] + [f2]}}
                    else:
                        p = {**p, "edit_fields": [f for f in p["edit_fields"] if f.get("id") != nf["id"]] + [f2]}
            if way == "add" and key in BEFORE_SAVE:             # lines a person types before saving (a journal entry's debit / credit)
                p = {**p, "add": {**p["add"], "before_save_js": list(BEFORE_SAVE[key]()) + (p["add"].get("before_save_js") or [])}}
            if way in ("add", "edit"):                          # 💱 local currency -> exchange rate 1 (before any test step)
                from simulation.real.probes import RATE_STEP
                if isinstance(p.get("add"), dict):
                    p = {**p, "add": {**p["add"], "before_save_js": (p["add"].get("before_save_js") or []) + [RATE_STEP]}}
            if way == "add" and want and want.get("mutate"):    # 🧪 a test wave: ONE field made wrong just before «حفظ»
                from simulation.real.probes import mutate_step
                p = {**p, "add": {**p["add"], "before_save_js": (p["add"].get("before_save_js") or []) + [mutate_step(want["mutate"], want.get("mutate_val"))]}}
            stop = threading.Event()
            if live:
                threading.Thread(target=self._mirror, args=(t0, live, stop), daemon=True).start()
            try:
                if way == "add":
                    from engine.stubborn import add_stubbornly
                    res, okk, err, tries = add_stubbornly(
                        driver, self.cred, p["info"], p["base"], p["add"], p["read"], p["mode"], p["info"]["builder"],
                        lambda c: A._variant(p["base"], "vc_add", **{k: v for k, v in c.items() if k not in ("key", "run_before", "run_after", "data_file")}),
                        A.build_fields)
                else:
                    res = run_screen(driver, self.cred, self._op(p, way, no), save=True, do_login=False)
                    okk = True
            except ReadOnlySite as e:
                return {"kind": "skip", "ms": 0, "msg": _first(e)}
            except (AssertionError, FieldFillError) as e:
                res, okk, err = getattr(e, "partial_result", None) or {}, False, str(e).split("\n  (Session info")[0]
            except Exception as e:
                res, okk, err = {}, False, f"{type(e).__name__}: {_first(e)}"
            stop.set()
            took = int((time.time() - t0) * 1000)              # the whole job: the tool's filling and retries too
            ms = self._erp_ms(driver) or took                  # «slow» is the system's own answer time, not the tool's work
            what = A.explain(way, res or {}, okk, err)
            self._prep = list((res or {}).get("prep") or [])
            for pr in (res or {}).get("prep") or []:             # the scripted lines before the save (journal entry…)
                what += f"\n🧾 {pr.get('label')}: " + " · ".join(map(str, pr.get("log") or [])) + (f" (مدين {pr['totals'][0]} / دائن {pr['totals'][1]})" if pr.get("totals") else "")
            if tries and (len(tries) > 1 or not okk):
                what += "\n🧠 المحاولات: " + " · ".join(tries)
            new_no, guessed = RUN_VARS.get("saved_no"), False
            if not re.search(r"\d", str(new_no or "")):          # the engine hands back «False» when it read no number → never a document number
                new_no = None
            srv = [] if okk else self._server_errors(driver)          # a 500 behind the page (an item price call…) = the system's own error
            # saved = the system took it: the engine says so, or it already read the new document's number in the list
            saved = bool((res or {}).get("saved")) or bool(re.search(r"\d", str(new_no or "")) and way == "add")
            if way == "add" and (okk or saved) and (FLAG.match(str(new_no or "").strip()) or not re.search(r"\d", str(new_no or ""))):
                new_no = self._doc_no(driver, path)              # the list's «رقم …» column, not a yes/no flag
                guessed = bool(new_no)                           # the list's top row may be a colleague's → never ours to edit / delete
        if way == "print" and not okk and re.search(r"ما فتحتش صفحة طباعة|PDF", err or ""):
            pr = self._print_probe(driver, path, no)              # the print link may hand back a PDF file (a download), not a page
            if pr and pr.get("pdf"):
                return {"kind": "ok", "ms": pr.get("ms") or ms, "note": f"🖨️ الطباعة نزلت ملف PDF ({pr['kb']} ك.ب) من «{pr['href']}»",
                        "evidence": f"🖨️ رابط الطباعة رجّع {pr['ct']} · {pr['kb']} ك.ب"}
            if pr and pr.get("status", 0) >= 500:
                return {"kind": "reject", "ms": ms, "msg": f"خطأ سيرفر في الطباعة: {pr['href']} → {pr['status']}", "evidence": what}
        if OFFLINE.search(err or "") and not saved:
            return {"kind": "offline", "ms": ms, "msg": "النت فصل عند الجهاز — ماوصلتش للموقع", "evidence": _first(OFFLINE.search(err).group(0))}
        if not okk and saved and way in ("add", "edit"):
            # the system SAVED it — only the check after the save disagreed: never redo it (that makes a second document)
            out = {"facts": facts(res, new_no or no), "kind": "wrong", "ms": ms, "msg": "اتحفظ، بس لما فتحته تاني: " + (_first(err.split("\n", 1)[-1]) or _first(err)), "evidence": what}
            if way == "add" and new_no:
                out["doc_no"] = str(new_no)
                self._own(key, new_no, emp, deal, guessed, out)
            elif way == "edit":
                out["doc_no"] = str(no)
            return out
        if okk:
            out = {"kind": "ok", "ms": ms, "note": what, "evidence": what, "facts": facts(res, new_no or no)}
            if way == "add":
                if not new_no:
                    return {"kind": "wrong", "ms": ms, "msg": "اتحفظ بس مالقيتش رقم المستند في أول القايمة", "evidence": what}
                out["doc_no"] = str(new_no)
                self._own(key, new_no, emp, deal, guessed, out)
            elif way == "edit":
                out["doc_no"] = str(new_no or no)
                chk = (res or {}).get("saved_check") or {}
                if chk.get("checked") and chk.get("warnings") and len(chk["warnings"]) >= len(chk.get("rows") or [1]):
                    return {"kind": "wrong", "ms": ms, "msg": "التعديل اتحفظ بس ولا قيمة اتغيرت لما فتحته تاني", "evidence": what}
            elif way == "delete":
                Ledger.deleted(self.site, key, no)
            return out
        # what the SYSTEM said while it refused (its own pop-ups), not the tool's summary «tried N ways»
        said = [a for a in ((res or {}).get("alerts") or []) if a and not re.search(r"هل تريد|انشاء سند|تم الحفظ بنجاح|سيقوم باعادة|^\s*موافقة\s*$", a)]   # «السداد الآلي سيقوم…» is a notice, not the refusal
        said += [m.strip() for m in re.findall(r"Alert Text:\s*([^\n]+?)(?:\s*🧠|\n|$)", err or "") if m.strip() not in said]   # a browser alert() = the system talking
        broke = next((pr["erp"] for pr in (res or {}).get("prep") or [] if pr.get("erp")), None)
        if broke:                                                 # the system's own page script broke on a person's step
            return {"kind": "reject", "ms": ms, "msg": "عطل في صفحة السيستم: " + broke[:200], "evidence": what}
        if srv:
            return {"kind": "reject", "ms": ms, "msg": f"خطأ سيرفر في السيستم: {srv[0]}" + (f" · ورسالته: «{said[-1][:120]}»" if said else ""),
                    "evidence": "طلبات رجعت بخطأ من السيرفر وقت الحفظ: " + " · ".join(srv[:5]) + "\n" + what}
        if said:                                                  # the system's own last word decides, not the tool's summary
            return {"kind": "reject", "ms": ms, "msg": f"السيستم رفض: «{said[-1][:160]}»", "evidence": "رسائل السيستم: " + " · ".join(dict.fromkeys(said)) + "\n" + what}
        md = A.missing_data(err)
        if md:
            return {"kind": "reject", "ms": ms, "msg": f"بيانات أساسية ناقصة في الموقع: «{md}» مفيهاش ولا اختيار", "evidence": what}
        tool = err.startswith(("WebDriverException", "NoSuchWindow", "InvalidSessionId", "TimeoutException"))
        return {"kind": "error" if tool else "reject", "tool": tool, "ms": ms, "msg": _first(err) or "فشل من غير رسالة", "evidence": what}

    PRINT_JS = r"""
var no = String(arguments[0] || '').trim(), done = arguments[arguments.length - 1];
var T = function (e) { return (e && e.innerText || '').replace(/\s+/g, ' ').trim(); };
var rows = Array.prototype.slice.call(document.querySelectorAll('table tbody tr'));
var row = rows.filter(function (tr) { return Array.prototype.some.call(tr.querySelectorAll('td'), function (td) { return T(td) === no; }); })[0];
if (!row) { done({ found: false }); return; }
var a = Array.prototype.filter.call(row.querySelectorAll('a[href]'), function (x) {
  var h = x.getAttribute('href') || ''; return /viewer|print|report|pdf/i.test(h) || (/طباعة/.test(x.title + T(x)) && !/^javascript/i.test(h)); })[0];
if (!a) { done({ found: true, link: false }); return; }
var t0 = Date.now(), href = a.getAttribute('href');
fetch(href, { credentials: 'same-origin' }).then(function (r) {
  return r.arrayBuffer().then(function (b) {
    var head = String.fromCharCode.apply(null, new Uint8Array(b.slice(0, 5)));
    done({ found: true, link: true, href: href, status: r.status, ct: r.headers.get('content-type') || '', kb: Math.round(b.byteLength / 1024),
           pdf: head === '%PDF-' && b.byteLength > 2000, ms: Date.now() - t0 });
  });
}).catch(function (e) { done({ found: true, link: true, href: href, error: String(e) }); });
"""

    def _print_probe(self, driver, path, no):
        """open the list, find the document's row and fetch its print link: a real PDF back = the print works"""
        if not no:
            return None
        try:
            driver.get(self.base.rstrip("/") + path)
            time.sleep(3)
            driver.set_script_timeout(60)
            return driver.execute_async_script(self.PRINT_JS, str(no))
        except Exception:
            return None

    NOTE_ID = re.compile(r"^(Notes?|Remarks?|Description|Explanation|Explaination|Details?|Statement|Comment|ArNotes|Note_?Ar|Bayan)$|notes?$|remark|explain|bayan", re.I)
    NOTE_LABEL = re.compile(r"البيان|ملاحظات|الشرح|الوصف|ملاحظة")

    def _note_field(self, p):
        """the form's free-text «البيان / ملاحظات» field (text or textarea, not in the item lines), from the form's own read"""
        for f in p.get("read") or []:
            if f.get("kind") not in ("text", "textarea") or f.get("in_table") or f.get("disabled") or f.get("visible") is False:
                continue
            if self.NOTE_ID.search(str(f.get("id") or "")) or self.NOTE_LABEL.search(str(f.get("label") or "")):
                return {k: f[k] for k in ("id", "kind", "label") if k in f}
        return None

    def readiness(self, driver, paths):
        """before the day: open each main add form like a person would and list the required lists that came with nothing
        to pick (a list that loads by search or after another choice is not empty) -> {key: [labels]}, the forms opened"""
        js = (HERE / "ready.js").read_text(encoding="utf-8")
        t0, empty, seen, bad = time.time(), {}, 0, {}
        for key, path in paths.items():
            p, _, q = path.partition("?")
            url = self.base + p.rstrip("/") + "/AddEdit" + (("?" + q) if q else "")
            try:
                driver.get(url)
                time.sleep(2.5)
                r = driver.execute_script(js) or {}
            except Exception as e:
                bad[key] = _first(e)
                continue
            if "/addedit" not in str(r.get("url", "")).lower():
                bad[key] = f"فتحت {url} ورجعني على {r.get('url')}"
                continue
            seen += 1
            if r.get("empty"):
                empty[key] = [x.get("label") or x.get("id") for x in r["empty"]]
        return {"empty": empty, "seen": seen, "bad": bad, "ms": int((time.time() - t0) * 1000)}

    def _erp_ms(self, driver):
        """the slowest single answer the system gave on the page the job ended on: the page itself or one of its requests
        (the time a person would sit waiting for NQ ERP) — the tool's typing, clicking and retries don't count"""
        try:
            v = driver.execute_script(
                "var n=performance.getEntriesByType('navigation')[0];"
                "var a=n?[n.responseEnd-n.requestStart]:[];"
                "performance.getEntriesByType('resource').forEach(function(e){"
                "if(e.initiatorType==='xmlhttprequest'||e.initiatorType==='fetch'){a.push(e.responseEnd-e.requestStart)}});"
                "return a.length?Math.max.apply(null,a):0")
            return int(v or 0)
        except Exception:
            return 0

    def _server_errors(self, driver):
        """requests of the open page that the server answered with 5xx (Chrome keeps each request's status)"""
        try:
            return driver.execute_script(
                "return performance.getEntriesByType('resource').filter(function(e){return e.responseStatus>=500})"
                ".map(function(e){return e.name.replace(location.origin,'').split('?')[0]+' → '+e.responseStatus})") or []
        except Exception:
            return []

    def _mirror(self, t0, live, stop):
        """while a save runs (a minute or two), the employee's desk camera shows the pictures the engine takes on the way"""
        try:
            from config.paths import SCREENSHOTS_DIR
        except Exception:
            return
        last = None
        while not stop.wait(2):
            try:
                pics = [f for f in SCREENSHOTS_DIR.glob("*.png") if f.stat().st_mtime >= t0 - 1]
                if pics:
                    f = max(pics, key=lambda x: x.stat().st_mtime)
                    if f != last:
                        last = f
                        live(f)
            except Exception:
                pass

    def _own(self, key, no, emp, deal, guessed, out):
        if guessed:
            out["evidence"] = (out.get("evidence") or "") + f"\n🔒 الرقم {no} من أول صف في القايمة مش من الحفظ نفسه — مش هيتعدل ولا يتمسح"
        else:
            Ledger.add(self.site, key, no, emp, deal)

    def _doc_no(self, driver, path):
        try:
            from engine.screen_runner import FIRST_CELL_JS, _abs
            driver.get(_abs(path))
            time.sleep(3)
            v = driver.execute_script(FIRST_CELL_JS)
            return "" if FLAG.match(str(v or "").strip()) or not re.search(r"\d", str(v or "")) else str(v)
        except Exception:
            return ""

    # ------------------------------------------------------------------ the accountant's review
    def review(self, driver, key):
        """trial balance: debit = credit (opening / movement / closing) and parents = children · journal: today's entries balanced"""
        t0 = time.time()
        driver.set_script_timeout(180)
        y = date.today().year
        try:
            if key == "trial_balance":
                from engine import books
                url = books.DEFAULT_URL.replace("{from}", f"{y - 10}-01-01").replace("{to}", f"{y}-12-31").replace("{dep}", "")
                r = driver.execute_async_script(books.FETCH_JS, url) or {}
                if not isinstance(r.get("data"), list):
                    return {"kind": "error", "ms": int((time.time() - t0) * 1000), "msg": f"الموقع ما رجّعش بيانات ميزان المراجعة ({r.get('s')}): {str(r.get('err', ''))[:160]}"}
                checks, _ = books.analyse(r["data"])
                txt = "\n".join(("✅ " if ok else "❌ ") + f"{rule}: {t}" for rule, ok, t in checks)
                bad = [f"{rule}: {t}" for rule, ok, t in checks if not ok]
                ms = int((time.time() - t0) * 1000)
                if bad:
                    return {"kind": "wrong", "ms": ms, "msg": "ميزان المراجعة مش متزن — " + bad[0][:180], "evidence": txt}
                return {"kind": "ok", "ms": ms, "note": f"⚖️ ميزان المراجعة ({len(r['data'])} حساب):\n" + txt, "evidence": txt}
            if key == "journal_review":
                from engine import journal_check
                today = date.today().isoformat()
                rows, fails = journal_check.run(driver, today, today)
                txt = "\n".join(" · ".join(str(c) for c in x["cells"][1:]) for x in rows[:12])
                ms = int((time.time() - t0) * 1000)
                if fails:
                    return {"kind": "wrong", "ms": ms, "msg": "قيود النهارده: " + fails[0][:180], "evidence": txt}
                return {"kind": "ok", "ms": ms, "note": "🧾 قيود النهارده: " + txt, "evidence": txt}
        except Exception as e:
            return {"kind": "error", "tool": True, "ms": int((time.time() - t0) * 1000), "msg": f"المراجعة: {_first(e)}"}
        return None
