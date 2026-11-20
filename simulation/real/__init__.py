"""
RealERP — the employees work on the real NQ ERP site, each in their own browser with their own user.

  • permissions = the screens in THAT user's menu on the system (read when they sign in)
  • every task opens the screen of NQ ERP that matches it (settings → «شاشات الشركة»), measures it, and reads what the
    system answered: opened · slow · server error · no permission · back to the login page
  • a picture of the employee's screen after every task → shown on their desk camera
  • on a TEST site the employees make real documents (simulation/real/writer.py, through the engine of the testing tool):
    add + verify · edit the same document + verify · print it · delete only what the company made · trial balance / journal review
  • site kind «نظام عميل» = read only: the company only opens screens.

Each employee has a worker thread: the engine hands it a task and gets a callback when the browser is done, so the
day keeps moving while the browsers work.
"""
import json
import queue
import time
import re
import threading

from simulation.real.browser import ErpSession
from simulation.real.writer import Writer, WRITES, REVIEWS

# our screen keys → words to find the matching screen in the NQ ERP menu
FIND = {
    "quotation": r"عروض? (?:ال)?أسعار|عرض (?:ال)?سعر",
    "sales_order": r"أوامر (?:ال)?بيع|أمر (?:ال)?بيع|اوامر (?:ال)?بيع",
    "stock_check": r"كارت (?:ال)?صنف|أرصدة (?:ال)?أصناف|ارصدة (?:ال)?اصناف|رصيد (?:ال)?صنف",
    "purchase_order": r"أوامر (?:ال)?شراء|أمر (?:ال)?شراء|اوامر (?:ال)?شراء",
    "stock_receipt": r"(?:سند|إذن|اذن) (?:استلام|إضافة|اضافة)",
    "purchase_invoice": r"فواتير (?:ال)?(?:شراء|مشتريات)|فاتور[ةه] (?:ال)?(?:شراء|مشتريات)",
    "stock_issue": r"(?:سند|إذن|اذن) صرف",
    "sales_invoice": r"فواتير (?:ال)?(?:بيع|مبيعات)|فاتور[ةه] (?:ال)?(?:بيع|مبيعات)",
    "journal_review": r"قيود? (?:ال)?(?:يومي[ةه]|يدوي[ةه]?)|القيود",
    "approval": r"اعتماد|موافقات",
    "receipt_voucher": r"سند(?:ات)? (?:ال)?قبض",
    "attendance": r"حضور|انصراف|بصم[ةه]",
    "cash_count": r"جرد (?:ال)?(?:خزين[ةه]|صندوق|نقدي[ةه])|حرك[ةه] (?:ال)?خزين[ةه]|الخزين[ةه]",
    "trial_balance": r"ميزان (?:ال)?مراجع[ةه]",
    "sales_report": r"تقرير (?:ال)?مبيعات|مبيعات (?:يومي[ةه]|فتر[ةه])|اجمالى المبيعات",
    "account_statement": r"كشف حساب مفصل|كشف حساب",
    "customer_statement": r"كشف حساب عميل",
    "sales_return": r"مرتجع (?:ال)?بيع|مرتجع (?:ال)?مبيعات", "purchase_request": r"طلب (?:ال)?شراء", "purchase_return": r"مرتجع (?:ال)?شراء|مرتجع (?:ال)?مشتريات",
    "payroll": r"مسير(?:ات)? (?:ال)?رواتب|كشف (?:ال)?رواتب الشهري",
    "payment_voucher": r"سند(?:ات)? (?:ال)?دفع|سند(?:ات)? (?:ال)?صرف نقدي", "stock_transfer": r"(?:سند|سندات) تحويل (?:ال)?مخاز", "journal_entry": r"قيود? (?:ال)?يومي[ةه]",
}
SKIP = re.compile(r"إعداد|اعداد|استيراد|طباع[ةه] متعدد", re.I)
# NQ ERP's own screens for each task (checked on the test site) — used first when the user's menu has them
PREFER = {"quotation": ["/SalesQuotation"], "sales_order": ["/SalesOrder"], "stock_check": ["/Report/ItemTransactionsReport", "/Report/DailyStockCard_Report"],
          "purchase_order": ["/PurchaseOrder"], "stock_receipt": ["/StockReceiptVoucher"], "purchase_invoice": ["/PurchaseInvoice"],
          "stock_issue": ["/StockIssueVoucher?type=1"], "sales_invoice": ["/SalesInvoice"], "journal_review": ["/JournalEntries?type=2", "/JournalEntriesReview"],
          "approval": ["/UnApprovedDocuments"], "receipt_voucher": ["/CashReceiptVoucher"], "attendance": ["/EmployeesAttendAndLeave"],
          "cash_count": ["/InventoryBoxes"], "trial_balance": ["/Report/TrialBalance", "/TrialBalanceWithLevelsTree"], "sales_report": ["/Report/SalesReportTotals"],
          "account_statement": ["/Report/StatementOfAccount"], "customer_statement": ["/Report/CustomerStatement"],
          "sales_return": ["/SalesReturn"], "purchase_request": ["/PurchaseRequest"], "purchase_return": ["/PurchaseReturn"],
          "payment_voucher": ["/CashIssueVoucher"], "stock_transfer": ["/StockTransferVoucher"], "journal_entry": ["/JournalEntries?type=1"]}


# 🧪 the test waves (simulation/real/probes.py): key -> (the screen it works on, the wrong field, its value)
PROBE_WRITE = {"neg_required": ("quotation", "required", None), "neg_negative": ("quotation", "negative", -5), "neg_discount": ("quotation", "discount", 150),
               "neg_text": ("quotation", "text", None), "neg_dupref": ("purchase_invoice", "dupref", "VC-DUP"), "perf_lines": ("quotation", "lines", 30)}
BUSY_LOCK = threading.Lock()
PROBE_READ = {"it_sweep", "it_speed", "sec_nologin", "sec_secrets", "ux_mobile", "ux_lang", "int_je", "tb_numbers", "approve_doc"}


def guess_map(menu):
    """{screen key: path} from the menu words"""
    out = {}
    paths = {x["path"].lower(): x["path"] for x in menu}
    for k, pref in PREFER.items():
        hit = next((paths[p.lower()] for p in pref if p.lower() in paths), None)
        if hit:
            out[k] = hit
    for k, rx in FIND.items():
        if k in out:
            continue
        r = re.compile(rx)
        m = next((x for x in menu if r.search(x["name"]) and not SKIP.search(x["name"]) and ("/Report/" in x["path"]) == (k in ("trial_balance", "sales_report", "stock_check"))), None) \
            or next((x for x in menu if r.search(x["name"]) and not SKIP.search(x["name"])), None)
        if m:
            out[k] = m["path"]
    return out


class RealERP:
    mode = "حقيقي"
    is_async = True

    def __init__(self, settings, sim, on_event=None):
        """sim = the SimERP (for the minutes a person spends on each screen); settings = simulation.settings.load()"""
        from simulation import settings as S
        self.S, self.sim, self.on_event = S, sim, on_event or (lambda *a: None)
        self.cfg = settings
        self.base = settings["url"]
        self.read_only = settings.get("site_kind") != "test"
        self.screens = sim.screens
        self.slow_ms = sim.slow_ms
        self.stock_short_p = sim.stock_short_p
        self.map = {**guess_map([]), **(settings.get("screens") or {})}
        self.sessions, self.queues, self.menus = {}, {}, {}
        self.closing = False
        self.writer = None
        self.write_note = ""

    def _writer(self, emp):
        """made once, with the first employee's user (the engine needs a site and a user when it loads)"""
        if self.writer is None:
            user, pw, _ = self._user(emp)
            self.writer = Writer(self.cfg.get("engine_path", ""), self.base, user, pw, self.cfg.get("site_id", ""), self.cfg.get("site_kind"))
            self.write_note = "" if self.writer.ok else self.writer.why
            self.on_event("writer", emp, 0, self.write_note)
        return self.writer if self.writer.ok else None

    def pending(self):
        return sum(q.qsize() for q in self.queues.values()) + getattr(self, "_busy", 0)

    def screen(self, key):
        return self.screens[key]

    def allowed(self, emp, key):
        """None = we don't know yet (not signed in) · True / False from the user's menu"""
        menu = self.menus.get(emp["id"])
        path = self.map.get(key)
        if menu is None or not path:
            return None
        return any(m["path"].split("?")[0].lower() == path.split("?")[0].lower() for m in menu)

    def _worker(self, key):
        q = self.queues[key]
        while True:
            job = q.get()
            if job is None:
                break
            if self.closing:                                       # the day ended: what's left is dropped
                continue
            key, emp, task, cb = job
            with BUSY_LOCK:                                        # one worker thread per user: += isn't atomic
                self._busy = getattr(self, "_busy", 0) + 1
            try:
                r = self._perform(key, emp, task)
                r.setdefault("did", "open")                    # what REALLY happened: open (looked only) · write · review — the chat says no more than that
                cb(r)
            except Exception as ex:
                cb({"kind": "error", "ms": 0, "msg": f"الأداة: {clean_error(ex)}", "steps": 0, "tool": True})
            finally:
                with BUSY_LOCK:
                    self._busy -= 1

    def _user(self, emp):
        user, pw, via = self.S.credentials(emp["id"])
        if not user or not pw:
            raise RuntimeError(f"{emp['name']} مالوش مستخدم على الموقع ده، ولا المدير — ضيف مستخدم المدير في الإعدادات")
        return user, pw, via

    def _session(self, emp):
        user, pw, via = self._user(emp)
        s = self.sessions.get(user.lower())
        if s is None:
            s = ErpSession(self.base, user, pw, visible=bool(self.cfg.get("show_browsers")))
            info = s.login()
            self.sessions[user.lower()] = s
            self.menus["@" + user.lower()] = info["menu"]
            if not self.cfg.get("screens"):
                for k, v in guess_map(info["menu"]).items():
                    self.map.setdefault(k, v)
        if emp["id"] not in self.menus:
            self.menus[emp["id"]] = self.menus["@" + user.lower()]
            self.on_event("login", emp, len(self.menus[emp["id"]]), user if via else "")
            if emp.get("role") == "manager":
                new = self._new_screens(self.menus[emp["id"]])
                if new:
                    self.on_event("new_screens", emp, new)
        return s

    def _new_screens(self, menu):
        """the manager's menu against the last snapshot of this site: paths that appeared since (first run = snapshot only)"""
        from simulation.settings import RUNS
        f = RUNS / f"menu_{self.cfg.get('site_id', 'site')}.json"
        now = sorted({str(x.get("path") or "") for x in menu if x.get("path") and not str(x.get("path")).lower().startswith(("javascript", "#"))
                      and not re.search(r"/\d+(?:[/?#]|$)", str(x.get("path")))})        # …/details/326 = one record, not a screen
        try:
            old = set(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            old = None
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(now, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        return [] if old is None else [p for p in now if p not in old]

    def _perform(self, key, emp, task):
        scr = self.screens[key]
        act = task.get("action") or "open"
        s = self._session(emp)
        if key == "readiness":                                     # before the day: the main add forms' required lists
            w = None if self.read_only else self._writer(emp)
            paths = {k: self.map[k] for k in WRITES if self.map.get(k)}
            if not w or not paths:
                return {"kind": "skip", "ms": 0, "msg": "فحص الجاهزية محتاج أداة الكتابة وشاشات مربوطة", "steps": scr["steps"]}
            v = w.readiness(s.driver, paths)
            names = {k: self.screens[k]["name"] for k in paths if k in self.screens}
            v["names"] = names
            txt = (f"فتحت {v['seen']} شاشة إضافة" + (": كله جاهز" if not v["empty"] else
                   " — قوايم إجبارية فاضية: " + " · ".join(f"{names.get(k, k)} ← {'، '.join(x)}" for k, x in v["empty"].items())))
            return {"kind": "ok", "ms": v["ms"], "did": "review", "note": txt, "ready": v, "steps": scr["steps"]}
        if key == "smoke":                                        # 🆕 a screen new in the menu: it opens (read only)
            r = s.open(task.get("path") or "/", shot_name=emp["id"])
            if r.get("kind") == "ok":
                r["note"] = f"🆕 الشاشة الجديدة «{task.get('path')}» بتفتح ✅"
            return {**r, "steps": scr["steps"], "path": task.get("path"), "did": "open"}
        if key == "fraud_perm":                                   # 🕵️ open a screen outside this user's work
            from simulation.real import guards
            r = guards.forbidden_open(s, task.get("path") or "/PurchaseInvoice/AddEdit", emp.get("role", ""))
            s.shot(emp["id"])
            return {**r, "steps": scr["steps"], "path": task.get("path")}
        if key == "audit_docs":                                   # 🧾 every document saved today is still in its list
            from simulation.real import guards
            paths = {k: self.map[k] for k in WRITES if self.map.get(k)}
            names = {k: self.screens[k]["name"] for k in paths if k in self.screens}
            r = guards.audit_documents(s.driver, self.base, self.cfg.get("site_id", ""), paths, names)
            return {**r, "steps": scr["steps"], "path": ""}
        if key in PROBE_WRITE:                                    # 🧪 a test wave on a real document: one field made wrong before «حفظ»
            base, mode, val = PROBE_WRITE[key]
            if self.read_only:
                return {"kind": "skip", "ms": 0, "msg": "اختبارات الكتابة على موقع اختبار بس", "steps": scr["steps"]}
            bpath, w = self.map.get(base), self._writer(emp)
            if not bpath or not w:
                return {"kind": "skip", "ms": 0, "notarget": True, "msg": f"«{self.screens[base]['name']}» مش متربطة أو أداة الكتابة مش موجودة", "steps": scr["steps"]}
            if self.allowed(emp, base) is False:
                return {"kind": "denied", "ms": 0, "msg": f"«{self.screens[base]['name']}» مش في منيو المستخدم {s.user}", "steps": scr["steps"]}
            want = {**(task.get("want") or {}), "mutate": mode, "mutate_val": task.get("mutate_val", val)}
            return {**self._write(w, s, base, bpath, self.screens[base], emp, {**task, "want": want}, "open"), "base": base}
        if key in PROBE_READ:                                     # 🔐 👁️ 🧮 checks that read the site (and approve our own document)
            from simulation.real import probes
            paths = [self.map[k] for k in WRITES if self.map.get(k)]
            t = task.get("doc_no") or ""
            if key == "it_sweep":                                # 🖥️ IT: every screen in his menu opens and loads data
                r = probes.it_sweep(s, self.menus.get(emp["id"]) or [])
            elif key == "it_speed":                              # 🐢 IT: how long each list takes to show its data (after lunch: vs. this morning)
                r, times = probes.it_speed(s, self.menus.get(emp["id"]) or [], getattr(self, "_speed_am", None))
                self._speed_am = getattr(self, "_speed_am", None) or times or None
            elif key == "sec_nologin":
                r = probes.no_login(self.base, paths)
            elif key == "sec_secrets":
                r = probes.secrets(s.driver, list(dict.fromkeys(paths + [v for v in self.map.values() if v])))
            elif key == "ux_mobile":
                r = probes.mobile(s, paths)
            elif key == "ux_lang":
                r = probes.english(s, paths)
            elif key == "int_je":
                lp = self.map.get("journal_review") or self.map.get("journal_entry")
                r = probes.journal_of(s, lp, t) if (lp and t) else {"kind": "skip", "notarget": True, "ms": 0, "msg": "مفيش فاتورة النهارده أو شاشة القيود مش متربطة"}
            elif key == "tb_numbers":
                lp = self.map.get("trial_balance")
                r = probes.trial_balance(s, lp) if lp else {"kind": "skip", "notarget": True, "ms": 0, "msg": "ميزان المراجعة مش متربط"}
            elif key == "approve_doc":
                lp = self.map.get("approval")
                r = probes.approve(s, lp, t) if (lp and t and not self.read_only) else {"kind": "skip", "notarget": True, "ms": 0, "msg": "مفيش فاتورة لينا النهارده أو شاشة الاعتماد مش متربطة"}
            else:
                r = {"kind": "skip", "ms": 0, "msg": key}
            s.shot(emp["id"])
            return {**r, "steps": scr["steps"], "path": ""}
        path = self.map.get(key)
        if not path:
            return {"kind": "skip", "ms": 0, "msg": f"«{scr['name']}» مش متربطة بشاشة في NQ ERP (الإعدادات ← شاشات الشركة)", "steps": scr["steps"]}
        if self.allowed(emp, key) is False:
            return {"kind": "denied", "ms": 0, "msg": f"«{scr['name']}» مش في منيو المستخدم {s.user} على NQ ERP", "steps": scr["steps"]}
        if key == "attendance" and not self.read_only:            # Hiba: today's fingerprint file, really uploaded and saved
            from simulation.real import attendance
            r = attendance.upload(s.driver, self.base, rng=self.rng if hasattr(self, "rng") else None)
            s.shot(emp["id"])
            return {**r, "steps": scr["steps"], "path": path}
        w = None if self.read_only else (self._writer(emp) if (key in WRITES or key in REVIEWS) else None)
        if w and (key in WRITES and act in ("open", "edit", "print", "delete")):
            return self._write(w, s, key, path, scr, emp, task, act)
        r = s.open(path, shot_name=emp["id"])
        r.update({"steps": scr["steps"], "path": path})
        if r["kind"] != "ok":
            return self._slow(r)
        if w and key in REVIEWS and act == "review":
            v = w.review(s.driver, key)
            s.shot(emp["id"])
            if v:
                return {**r, **v, "ms": r["ms"] + v["ms"], "did": "review"}
        if "/report/" in path.lower():                          # a report: wait for its pages (or its error)
            v, ms = s.wait_report()
            s.shot(emp["id"])
            r["ms"] += ms
            if v.startswith("error:"):
                return {**r, "kind": "error", "msg": "التقرير: " + v[6:]}
            if v == "params":
                return {**r, "kind": "ok", "note": "التقرير محتاج يختار فلتر (حساب / عميل) قبل ما يطلع — فتحته بس"}
            if v == "timeout":
                return {**r, "kind": "slow", "ms": max(r["ms"], 60000), "msg": "التقرير ما خلصش في 60 ثانية بعد «Submit»"}
        if act in ("edit", "print", "delete"):
            row = s.first_row()
            if not row:
                return {**r, "kind": "skip", "msg": f"مفيش مستندات في «{scr['name']}» أجرب عليها"}
            doc = " · ".join(c for c in row.get("cells", []) if c)[:60]
            if act == "edit":
                if not row.get("edit"):
                    return {**r, "kind": "reject", "msg": f"مفيش زرار تعديل على المستند ({doc})"}
                rr = s.open(row["edit"], shot_name=emp["id"])
                rr.update({"steps": scr["steps"], "path": row["edit"]})
                if rr["kind"] == "ok":
                    rr["note"] = f"فتح المستند للتعديل ({doc}) — الحفظ الحقيقي في المرحلة الجاية"
                return self._slow(rr)
            if act == "print":
                if not row.get("print"):
                    return {**r, "kind": "reject", "msg": f"مفيش زرار طباعة على المستند ({doc})"}
                rr = s.open(row["print"], shot_name=emp["id"])
                rr.update({"steps": scr["steps"], "path": row["print"]})
                if rr["kind"] == "ok" and "/report/" in row["print"].lower():
                    v, ms = s.wait_report()
                    s.shot(emp["id"])
                    rr["ms"] += ms
                    if v.startswith("error:"):
                        return {**rr, "kind": "error", "msg": "الطباعة: " + v[6:]}
                    if v == "timeout":
                        return {**rr, "kind": "slow", "ms": max(rr["ms"], 60000), "msg": "الطباعة ما ظهرتش في 60 ثانية"}
                    rr["note"] = f"اتطبع المستند ({doc})"
                return self._slow(rr)
            if act == "delete":
                r["note"] = (f"زرار الحذف {'موجود' if row.get('del') else 'مش ظاهر'} على المستند ({doc}) — "
                             + ("النظام «قراءة بس» فمحذفتش" if self.read_only else "الحذف الحقيقي في المرحلة الجاية (هيحذف مستنداته هو بس)"))
                return r
        if self.read_only and act == "open":
            r["note"] = "قراءة بس — النظام متسجل «نظام عميل»"
        return self._slow(r)

    def _live(self, emp, picture):
        """a picture the engine just took → the employee's desk camera"""
        import shutil
        from simulation.real.browser import SHOTS
        try:
            SHOTS.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(picture, SHOTS / f"{emp['id']}.png")
            self.on_event("shot", emp, 0, "")
        except Exception:
            pass

    @property
    def real_writes(self):
        """documents are really saved here (a test site + the testing tool found)"""
        if self.read_only:
            return False
        from simulation.real.writer import find_engine
        return bool(find_engine(self.cfg.get("engine_path", "")))

    def _write(self, w, s, key, path, scr, emp, task, act):
        """a real document: add / edit / print / delete with its checks"""
        user, pw, _ = self._user(emp)
        r = w.run(s.driver, key, path, scr["name"], act, no=task.get("doc_no"), emp=emp["id"], deal=task.get("deal", ""),
                  cred={"username": user, "password": pw}, want=task.get("want"), live=lambda f: self._live(emp, f))
        s.shot(emp["id"])
        r.update({"steps": scr["steps"], "path": path, "did": "write"})
        if r["kind"] == "ok" and act == "open":
            r["note"] = f"💾 حفظ مستند حقيقي رقم {r.get('doc_no')}\n" + (r.get("note") or "")
        return self._slow(r) if r["kind"] == "ok" and act != "open" else r

    def _slow(self, r):
        if r["kind"] == "ok" and r.get("ms", 0) > self.slow_ms:
            r["kind"], r["msg"] = "slow", f"فتحت في {r['ms'] / 1000:.1f} ث"
        return r

    def perform_async(self, key, emp, task, cb):
        """one queue per NQ ERP user: employees sharing the manager's user wait for his browser"""
        try:
            qk = self._user(emp)[0].lower()
        except Exception as ex:
            cb({"kind": "skip", "ms": 0, "msg": str(ex), "steps": 0})
            return
        if qk not in self.queues:
            self.queues[qk] = queue.Queue()
            threading.Thread(target=self._worker, args=(qk,), daemon=True).start()
        self.queues[qk].put((key, emp, task, cb))

    def close(self, wait=0):
        """end of the day: what's queued is dropped; the job in the middle (a save) is left to finish, up to `wait` s"""
        self.closing = True
        for q in self.queues.values():
            q.put(None)
        end = time.time() + wait
        while getattr(self, "_busy", 0) and time.time() < end:
            time.sleep(0.5)
        for s in self.sessions.values():
            s.close()
        self.sessions.clear()


def clean_error(e):
    """a Selenium error without its stack trace, in words a person understands"""
    t = str(getattr(e, "msg", None) or e).split("\n")[0].replace("Message:", "").strip()
    t = re.sub(r"\(Session info:.*?\)", "", t).strip()
    known = {"element not interactable": "الصفحة ما سمحتش بالكتابة في الخانة (لسه بتحمّل أو متغطية)",
             "net::ERR_NAME_NOT_RESOLVED": "اللينك غلط أو الجهاز مش واصل للنت", "net::ERR_CONNECTION": "الموقع مش بيرد",
             "cannot find Chrome binary": "Google Chrome مش متسطب على الجهاز", "session not created": "نسخة Chrome / chromedriver مش متوافقة — حدّث Chrome"}
    for k, v in known.items():
        if k.lower() in t.lower():
            return f"{v} ({k})"
    return t[:200] or type(e).__name__


def test_login(base, user, pw, visible=False):
    """settings page: sign in once, return the menu (= permissions)"""
    s = ErpSession(base, user, pw, visible)
    try:
        info = s.login()
        s.shot("_login_test")
        return info["menu"]
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(clean_error(e)) from None
    finally:
        s.close()
