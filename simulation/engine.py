"""
🏢 الشركة الافتراضية — the engine. No AI tokens: every employee follows rules (their job, their personality),
talks from a bank of sentences (data/dialogues.json) and works on the ERP through an adapter (erp.py).

Time is virtual: a working day (08:00 → 16:00) runs in a few real minutes (speed = virtual minutes per real second).
Everything that happens is an event (move / say / status / deal / complaint / clock) streamed to the page.
"""
import heapq
import re
import json
import math
import random
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

from simulation.erp import SimERP

DATA = Path(__file__).parent / "data"
from simulation.settings import RUNS  # noqa: E402


ACT_AR = {"edit": "تعديل", "print": "طباعة", "delete": "حذف", "review": "مراجعة"}


def _hm(v):
    return f"{int(v // 60):02d}:{int(v % 60):02d}"


def _min(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


# the main screens of the round, and who does each (the scenarios document: add · edit · print · delete)
ROUND = [("quotation", "sales"), ("sales_order", "sales"), ("sales_invoice", "sales"), ("sales_return", "sales"), ("receipt_voucher", "cashier"),
         ("purchase_request", "purchasing"), ("purchase_order", "purchasing"), ("purchase_invoice", "accountant"), ("purchase_return", "purchasing"),
         ("payment_voucher", "cashier"), ("stock_receipt", "warehouse"), ("stock_issue", "warehouse"), ("stock_transfer", "warehouse"),
         ("journal_entry", "accountant")]


# a screen of the round that is made FROM another one's document
ROUND_NEEDS = {"sales_return": "sales_invoice", "purchase_return": "purchase_invoice", "purchase_order": "purchase_request"}
# the form field that names the source document — filled with the number the round itself saved (not an old one from the list)
ROUND_BASED = {"purchase_order": "FromPurchaseRequest"}


class Company:
    def __init__(self, seed=None, erp=None, use_settings=True, runs=None):
        self.use_settings = use_settings
        self.runs = Path(runs) if runs else RUNS             # the client demo keeps its own history, apart from the real days
        self.cfg = self._load_cfg()
        self._load_texts()
        self.rng = random.Random(seed)
        self.erp = erp or SimERP(rng=self.rng)
        self.lock = threading.RLock()
        self.cond = threading.Condition(self.lock)
        self.speed = 4.0                     # virtual minutes per real second
        self.thread = None
        self.reset()

    def _load_texts(self):
        """the chat's words and the day's story in the display language (English files fall back to Arabic)"""
        self.lang = self.cfg.get("lang", "ar") if self.cfg.get("lang") in ("ar", "en") else "ar"
        sfx = "_en" if self.lang == "en" else ""
        def rd(n):
            for f in (DATA / f"{n}{sfx}.json", DATA / f"{n}.json"):
                try:
                    return json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
            return {}
        self.lines = rd("dialogues")
        self.story = rd("story")                                   # the day's story: why each employee opens each screen

    def T(self, ar, en):
        return en if getattr(self, "lang", "ar") == "en" else ar

    def _load_cfg(self):
        if self.use_settings:
            from simulation import settings as S
            return S.company_cfg()
        c = json.loads((DATA / "company.json").read_text(encoding="utf-8"))
        c["employees"] = [e for e in c["employees"] if e.get("active", True)]     # a colleague not switched on yet stays out
        return c

    def make_erp(self):
        """the settings decide: simulation, or the real NQ ERP site"""
        sim = SimERP(rng=self.rng)
        if not self.use_settings:
            return sim
        from simulation import settings as S
        st = S.runtime()
        if st.get("mode") == "real" and st.get("url"):
            from simulation.real import RealERP
            return RealERP(st, sim, on_event=self._erp_event)
        return sim

    def _erp_event(self, kind, emp, n, via=""):
        with self.lock:
            e = self.emps.get(emp["id"])
            if kind == "shot":                                     # a new picture of the employee's real screen
                self._emit("shot", {"emp": emp["id"]})
                return
            if e and kind == "writer":
                self.log(e, ("✍️ الموظفين هيحفظوا ويعدّلوا ويطبعوا ويحذفوا مستندات حقيقية على الموقع (موقع اختبار)" if not via
                             else f"👁️ مفيش حفظ حقيقي: {via}"), None if via else True)
            if e and kind == "new_screens":                        # 🆕 screens that weren't in the menu last time: open each once
                paths = list(n or [])[:10]
                self.log(e, f"🆕 لقيت {len(n or [])} شاشة جديدة في المنيو من آخر مرة — هفتحهم أتأكد إنهم شغالين", True)
                self.new_screens = list(n or [])
                for i, p in enumerate(paths):
                    self.after(5 + i * 3, self.assign, e, {"screen": "smoke", "path": p, "label": f"🆕 شاشة جديدة: {p}", "then": "_said_guard"})
                return
            if e and kind == "login":
                self.log(e, (f"🔑 بيشتغل على NQ ERP بمستخدم المدير ({via}) — {n} شاشة" if via else f"🔑 دخل NQ ERP بمستخدمه — {n} شاشة في المنيو بتاعه"), True)

    # ------------------------------------------------------------------ state
    def reset(self):
        with self.lock:
            self.events, self.eid = deque(maxlen=3000), 0
            self.start, self.end = _min(self.cfg["day_start"]), _min(self.cfg["day_end"])
            self.now = self.start
            self.running = self.paused = False
            self.queue, self.seq = [], 0
            self.deals, self.complaints, self.chat = {}, [], deque(maxlen=400)
            self.report = None
            self.emps = {}
            from simulation.art.floor import assign_desks, seat
            desks, _ = assign_desks(self.cfg["employees"])
            for e in self.cfg["employees"]:
                if e["id"] not in desks:
                    continue                                   # no free desk for this job
                e = {**e, "desk": desks[e["id"]], "x": seat(desks[e["id"]])[0], "y": seat(desks[e["id"]])[1]}
                if getattr(self, "lang", "ar") == "en":
                    from simulation.i18n import name_en
                    e["name_ar"], e["name"] = e["name"], name_en(e["name"])
                self.emps[e["id"]] = {**e, "hx": e["x"], "hy": e["y"], "last_err": "", "status": "away", "screen": "", "task": "", "q": deque(), "log": [],
                                      "done": 0, "failed": 0, "busy_min": 0.0, "complaints": 0, "last_busy_note": -999, "walking": False}
            people = self._people()
            for eid, e in self.emps.items():                    # 🎓 what each employee learned on earlier real days
                m = people.get(eid)
                if m and self.erp.mode != "محاكاة":
                    e["experience"] = max(.1, min(1.0, float(m.get("experience", e["experience"]))))
                    e["days"] = m.get("days", 0)
            self.screen_ms = {}
            self.screen_fail = {}                # screen -> times it failed (the frustration index)
            self.burst = []                      # ⚡ the load test: (screen, ms, who)
            self.guards = []                     # 🕵️ / 🧾 the watchdogs' results
            self.health = {}                     # 🩺 screen -> its state today (ok / slow / fail counts, last result)
            self.timeline = []                   # 🕒 every task of the day: who, when, which screen, how it ended
            self._emit("reset", {})

    def snapshot(self):
        with self.lock:
            return {"company": self.cfg["name"], "rooms": self.cfg["rooms"], "clock": _hm(self.now), "now": self.now, "start": self.start, "end": self.end,
                    "running": self.running, "paused": self.paused, "speed": self.speed, "mode": self.erp.mode,
                    "employees": [self._pub(e) for e in self.emps.values()], "deals": list(self.deals.values())[-60:],
                    "complaints": self.complaints[-200:], "chat": list(self.chat)[-150:], "report": self.report, "eid": self.eid, "lang": getattr(self, "lang", "ar"),
                    "health": list(getattr(self, "health", {}).values()), "timeline": getattr(self, "timeline", [])[-400:]}

    def _pub(self, e):
        return {k: e[k] for k in ("id", "name", "job", "role", "room", "x", "y", "hx", "hy", "color", "status", "screen", "task", "done", "failed",
                                  "complaints", "speed", "accuracy", "experience", "patience")} | {"queue": len(e["q"]), "log": e["log"][-40:],
                                                                                                    "look": e.get("look") or {}, "desk": e.get("desk", "")}

    def _emit(self, typ, data):
        with self.cond:
            self.eid += 1
            self.events.append({"id": self.eid, "type": typ, "data": data, "clock": _hm(self.now)})
            self.cond.notify_all()

    def events_since(self, eid, timeout=15):
        with self.cond:
            if not any(ev["id"] > eid for ev in self.events):
                self.cond.wait(timeout)
            return [ev for ev in self.events if ev["id"] > eid]

    # ------------------------------------------------------------------ helpers
    def at(self, vtime, fn, *args):
        self.seq += 1
        heapq.heappush(self.queue, (vtime, self.seq, fn, args))

    def after(self, vmin, fn, *args):
        self.at(self.now + vmin, fn, *args)

    def line(self, key, **kw):
        opts = self.lines.get(key) or [key]
        txt = self.rng.choice(opts)
        if getattr(self, "lang", "ar") == "en":
            from simulation.i18n import en
            kw = {k: en(v) for k, v in kw.items()}
        for k, v in kw.items():
            txt = txt.replace("{" + k + "}", str(v))
        return txt

    def say(self, e, text, to=None):
        msg = {"clock": _hm(self.now), "from": e["id"], "name": e["name"], "to": to["id"] if to else "", "to_name": to["name"] if to else "", "text": text}
        self.chat.append(msg)
        self._emit("say", msg)

    def log(self, e, text, ok=None):
        e["log"].append({"clock": _hm(self.now), "text": text, "ok": ok})
        self._emit("log", {"emp": e["id"], "clock": _hm(self.now), "text": text, "ok": ok})

    def status(self, e, st, screen="", task=""):
        e["status"], e["screen"], e["task"] = st, screen, task
        self._emit("status", {"emp": e["id"], "status": st, "screen": screen, "task": task, "queue": len(e["q"]), "done": e["done"],
                              "failed": e["failed"], "complaints": e["complaints"], "err": e.get("last_err", "") if st == "blocked" else ""})

    def by_role(self, role, exclude=None):
        c = [e for e in self.emps.values() if e["role"] == role and e["id"] != exclude]
        return min(c, key=lambda e: (len(e["q"]) + (1 if e["status"] == "working" else 0), self.rng.random())) if c else None

    def _track(self, e, task, scr, r):
        """🩺 the screen's health today + 🕒 the day's timeline (one entry per task)"""
        k = r.get("kind") or "?"
        state = r.get("_state") or ("ok" if k in ("ok", "skip") else "slow" if k == "slow" else "denied" if k == "denied" else "fail")
        h = self.health.setdefault(scr["name"], {"screen": scr["name"], "key": task.get("screen", ""), "ok": 0, "slow": 0, "fail": 0, "ms": []})
        if state != "skip":
            h["fail" if state in ("fail", "denied") else state] += 1
        h["ms"] = (h["ms"] + [int(r.get("ms") or 0)])[-20:]
        h.update(last=state, clock=_hm(self.now), who=e["name"], msg=str(r.get("msg") or "")[:200], url=r.get("url", ""), shot=r.get("shot", ""))
        t = {"emp": e["id"], "name": e["name"], "clock": _hm(self.now), "screen": scr["name"], "key": task.get("screen", ""), "probe": task.get("probe", ""), "action": task.get("action", "add"),
             "label": task.get("label", ""), "state": state, "ms": int(r.get("ms") or 0), "deal": task.get("deal", ""), "no": r.get("doc_no") or r.get("no") or "",
             "msg": str(r.get("msg") or "")[:160]}
        self.timeline.append(t)
        self._emit("track", {"t": t, "h": h})

    def complain(self, e, typ, screen, text, evidence, deal=None, source=None, tool=False, r=None):
        """every problem with its evidence and its source (🏢 the system · 👤 data / setup · 🌐 the internet · 🛠️ the tool · 📋 workload)"""
        from simulation.sources import classify
        src = source or classify(typ, text, evidence, tool)
        if src in ("erp", "data", "work"):                       # the employee's complaints; the internet / the tool are not theirs
            e["complaints"] += 1
        c = {"id": len(self.complaints) + 1, "clock": _hm(self.now), "emp": e["id"], "name": e["name"], "job": e["job"], "type": typ,
             "screen": screen, "text": text, "evidence": evidence, "deal": deal["id"] if deal else "", "source": src,
             "shot": (r or {}).get("shot", ""), "url": (r or {}).get("url", ""), "action": (r or {}).get("action", "")}
        self.complaints.append(c)
        self._emit("complaint", c)

    def deal_step(self, d, text, st="done"):
        d["steps"].append({"clock": _hm(self.now), "text": text, "status": st})
        self._emit("deal", d)

    # ------------------------------------------------------------------ walking & handoffs
    # the corridor between the two rows of rooms: people walk through it, not through walls
    CORRIDOR_Y = 365

    # every room's door (x of its middle) on the corridor walls: the top row's wall at y=330, the bottom row's at y=400
    DOORS_TOP = [(20, 370, 155), (370, 760, 455), (760, 930, 825), (930, 1330, 1015), (1330, 1580, 1415)]
    DOORS_BOT = [(20, 470, 235), (470, 800, 575), (800, 1030, 885), (1030, 1260, 1115), (1260, 1580, 1340)]

    def _room(self, p):
        x, y = p
        if 330 <= y <= 400:
            return None, None                     # in the corridor already
        rows, wy = (self.DOORS_TOP, 330) if y < 330 else (self.DOORS_BOT, 400)
        for i, (x0, x1, dx) in enumerate(rows):
            if x0 <= x < x1:
                return (wy, i), (dx, wy)
        return None, None

    def route(self, a, b):
        """out of the room through its door, along the corridor, in through the other room's door — never through a wall"""
        ra, da = self._room(a)
        rb, db = self._room(b)
        if ra is not None and ra == rb:
            return [a, b]                          # same room
        pts = [a]
        if da:
            inside = da[1] - 30 if da[1] == 330 else da[1] + 30
            pts += [(da[0], inside), (da[0], self.CORRIDOR_Y)]
        else:
            pts.append((a[0], self.CORRIDOR_Y))
        if db:
            inside = db[1] - 30 if db[1] == 330 else db[1] + 30
            pts += [(db[0], self.CORRIDOR_Y), (db[0], inside), b]
        else:
            pts += [(b[0], self.CORRIDOR_Y), b]
        out = [pts[0]]
        for q in pts[1:]:
            if q != out[-1]:
                out.append(q)
        return out

    def go(self, e, point, face, then, stay=1.5, label=""):
        """walk e to `point` (through the corridor), stand facing `face`, run then(), wait `stay` minutes, walk back to the desk"""
        start = (e["hx"], e["hy"])
        path = self.route(start, point)
        dist = sum(math.hypot(path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1]) for i in range(len(path) - 1))
        vmin = max(1.0, dist / 180)
        e["walking"] = True
        prev = e["status"]
        self.status(e, "walking", task=label)
        self._emit("path", {"emp": e["id"], "points": path, "ms": int(vmin / self.speed * 1000), "face": face})

        def arrive():
            if then:
                then()
            self.after(stay, back)

        def back():
            self.status(e, "walking", task="راجع مكتبه")
            self._emit("path", {"emp": e["id"], "points": list(reversed(path)), "ms": int(vmin / self.speed * 1000), "face": 0, "home": True})
            self.after(vmin, home)

        def home():
            e["walking"] = False
            self.status(e, "idle" if prev in ("idle", "walking", "away") else prev)
            self._next(e)
        self.after(vmin, arrive)

    def walk(self, e, to, then, *args):
        """e walks to `to`'s desk, talks, walks back"""
        side = 44 if to["hx"] < 1500 else -44
        point = (to["hx"] + side, to["hy"] - 6)
        face = -90 if side > 0 else 90                       # facing the colleague
        self.go(e, point, face, lambda: then(*args), 1.5, f"رايح لـ {to['name']}")

    def coffee(self, eid):
        e = self.emps[eid]
        if e["status"] != "idle" or e["walking"] or e["q"]:
            return
        from simulation.art.floor import SPOTS
        kx, ky = SPOTS["kitchen"]
        point = (kx + self.rng.uniform(-90, 60), ky + self.rng.uniform(10, 50))

        def at_kitchen():
            if self.rng.random() < .5:
                self.say(e, self.line("coffee"))
        self.go(e, point, 0, at_kitchen, self.rng.uniform(5, 10), "بيعمل قهوة ☕")

    def handoff(self, frm, to, key, task, **kw):
        if frm is to or to is None:
            if to is not None:
                self.assign(to, task)
            return
        text = self.line(key, to=to["name"], **kw)

        def deliver():
            self.say(frm, text, to)
            self.assign(to, task)
        if frm["walking"] or frm["status"] == "working":
            self.say(frm, text, to)                 # busy: a message instead of walking
            self.assign(to, task)
        else:
            self.walk(frm, to, deliver)

    # ------------------------------------------------------------------ doing a task on the ERP
    def assign(self, e, task):
        if e is None:                                       # that role is switched off in Settings
            return
        e["q"].append(task)
        if len(e["q"]) >= 5 and self.now - e["last_busy_note"] > 120:
            e["last_busy_note"] = self.now
            self.say(e, self.line("busy", n=len(e["q"])))
            self.complain(e, "ضغط شغل", "", f"عندي {len(e['q'])} مهام متكومة", f"طابور المهام: {len(e['q'])}")
        self._emit("status", {"emp": e["id"], "status": e["status"], "screen": e["screen"], "task": e["task"], "queue": len(e["q"])})
        if e["status"] in ("idle",) and not e["walking"]:
            self._next(e)

    def _next(self, e):
        if e["status"] != "idle" or e["walking"] or not e["q"]:
            return
        task = e["q"].popleft()
        self._do(e, task)

    def _deny(self, e, task, scr, evidence):
        self.say(e, self.line("no_permission", screen=scr["name"]))
        self.complain(e, "صلاحيات", scr["name"], f"مالوش صلاحية على {scr['name']}", evidence, self.deals.get(task.get("deal")))
        other = next((x for x in self.emps.values() if x is not e and x["role"] in scr["roles"]), None)
        if other and not task.get("_moved"):
            task["_moved"] = True
            self.assign(other, task)

    def scr_of(self, task):
        """the screen of a task, named with its action («تعديل فواتير البيع»)"""
        scr = dict(self.erp.screen(task["screen"]))
        act = task.get("action")
        if act in ACT_AR:
            a = self.erp.action(act) if hasattr(self.erp, "action") else None
            scr["name"] = f"{ACT_AR[act]} {scr['name']}"
            if a:
                scr["minutes"] = a.get("minutes", scr["minutes"])
        return scr

    def _do(self, e, task, attempt=1):
        scr = self.scr_of(task)
        if getattr(self.erp, "is_async", False):                 # the real NQ ERP: permissions come from the user's own menu
            if self.erp.allowed(e, task["screen"]) is False:
                self._deny(e, task, scr, "الشاشة مش في منيو المستخدم بتاعه على NQ ERP")
                self._next(e)
                return
            d = self.deals.get(task.get("deal"))
            if d and task.get("action") in ("edit", "print", "delete"):     # the document THIS deal made on the site
                task["doc_no"] = (d.get("docs") or {}).get(task.get("doc_key") or task["screen"])
            if d and (d.get("real") or {}).get("party") and task["screen"] in ("quotation", "sales_order", "sales_invoice"):
                task["want"] = {"party": d["real"]["party"]}             # the same real customer on every document of the deal
            if d and d.get("note") and task.get("action", "add") in ("add", "edit"):
                task["want"] = {**(task.get("want") or {}), "note": d["note"] + (" — معدّل" if task.get("action") == "edit" else "")}
            if d and d.get("based") and task.get("action", "add") == "add":
                task["want"] = {**(task.get("want") or {}), "based": d["based"]}   # made FROM the round's own source document
            t0 = self.now
            vmin = scr["minutes"] / max(0.3, e["speed"]) * (1.3 - 0.3 * e["experience"])
            self.status(e, "working", scr["name"], task["label"])
            self.log(e, f"فتح «{scr['name']}» على NQ ERP: {task['label']}")

            def done(r):
                with self.lock:
                    if not self.running:
                        return
                    self.screen_ms.setdefault(scr["name"], []).append(r.get("ms") or 0)
                    e["busy_min"] += max(vmin, self.now - t0)
                    self.after(max(0.3, vmin - (self.now - t0)), self._finish, e, task, r, attempt)
            self.erp.perform_async(task["screen"], e, task, done)
            return
        if e["role"] not in scr["roles"]:
            self._deny(e, task, scr, f"دوره «{e['job']}» مش من المسموح لهم")
            self._next(e)
            return
        r = self.erp.perform(task["screen"], e, task)
        self.screen_ms.setdefault(scr["name"], []).append(r["ms"])
        if r.get("kind") not in ("ok", "slow", "skip"):
            self.screen_fail[scr["name"]] = self.screen_fail.get(scr["name"], 0) + 1
        vmin = scr["minutes"] / max(0.3, e["speed"]) * (1.3 - 0.3 * e["experience"]) + r["ms"] / 60000 * 8
        e["busy_min"] += vmin
        self.status(e, "working", scr["name"], task["label"])
        self.log(e, f"فتح «{scr['name']}»: {task['label']}")
        self.after(vmin, self._finish, e, task, r, attempt)

    def _finish(self, e, task, r, attempt):
        scr = self.scr_of(task)
        if task.get("probe"):                                    # 🧪 a test wave: judged by what a correct system must do
            self._probe_done(e, task, scr, r)
            return
        self._track(e, task, scr, r)
        d = self.deals.get(task.get("deal"))
        if r["kind"] == "denied":
            self._deny(e, task, scr, r["msg"])
            if d:
                self.deal_step(d, f"🔒 {e['name']} مالوش صلاحية على «{scr['name']}»", "fail")
            self.status(e, "idle")
            self._next(e)
            return
        if d and d.get("round"):
            mark = {"skip": "⏭️ ", "wrong": "⚠️ ", "slow": "🐢 "}.get(r["kind"], "❌ " if r["kind"] in ("error", "reject") and attempt > 1 else "")
            if mark or r["kind"] == "ok":
                d.setdefault("res", {})[task.get("action") or "add"] = (mark or "✅ ") + (r.get("msg") or (f"رقم {r['doc_no']}" if r.get("doc_no") else "تم"))[:140]
            if r.get("tool"):
                d.setdefault("res", {})[task.get("action") or "add"] = "🛠️ " + (r.get("msg") or "")[:140]
        if r["kind"] == "skip" or r.get("tool"):                 # not linked to a screen / the tool itself failed: not the system's fault
            self.log(e, f"ℹ️ {r['msg']}", None)
            if r.get("tool"):
                self.complain(e, "مشكلة في الأداة", scr["name"], r["msg"], r.get("evidence") or r["msg"], d, tool=True)
            r = {**r, "kind": "ok"}
        if r["kind"] == "offline":                              # the internet of THIS computer dropped: not the system's fault
            n = task.get("_offline", 0) + 1
            self.log(e, f"📡 {r['msg']} — هستنى وأجرب تاني ({n}/3)", None)
            if n == 1:
                self.complain(e, "النت فصل", scr["name"], r["msg"], r.get("evidence") or "", d, source="net")
            if n <= 3:
                task["_offline"] = n
                self.status(e, "blocked", scr["name"], "مستني النت")
                self.after(10, self._retry, e, {**task}, 0)
                return
            if d:
                d["state"] = "متعطلة"
                self.deal_step(d, f"📡 وقفت عند {e['name']}: النت فصل 3 مرات (مش عيب في السيستم)", "fail")
            self.status(e, "idle")
            self._next(e)
            return
        if r["kind"] == "login":
            r = {**r, "kind": "error"}
        if r.get("note"):
            self.log(e, f"👁️ {r['note']}", None)
        if r.get("facts") and r["kind"] in ("ok", "wrong") and not task.get("action"):
            self._real_facts(e, d, task, scr, r["facts"])
        if r["kind"] == "ok" and r.get("doc_no") and d is not None and task.get("action") in (None, "open", "edit"):
            d.setdefault("docs", {})[task.get("doc_key") or task["screen"]] = r["doc_no"]
            if not task.get("action"):
                self.deal_step(d, f"💾 «{scr['name']}» اتحفظ على NQ ERP برقم {r['doc_no']} واتراجع بعد الحفظ", "info")
        if r["kind"] == "slow" and r["ms"] > self.erp.slow_ms:
            secs = round(r["ms"] / 1000)
            if self.rng.random() < 1.2 - e["patience"]:
                self.say(e, self.line("slow", screen=scr["name"], secs=secs))
                self.complain(e, "بطء", scr["name"], r["msg"] or f"{scr['name']} بطيئة", f"رد السيستم {secs} ث (الحد {self.erp.slow_ms // 1000} ث)", d)
        if r["kind"] == "wrong":
            self.say(e, self.line("wrong_data", screen=scr["name"], msg=r["msg"]))
            self.complain(e, "بيانات غلط", scr["name"], r["msg"], r.get("evidence") or "اتلاحظ أثناء المراجعة", d, r={**r, "action": task.get("action") or "add"})
        if r["kind"] == "mistake":                              # the employee's own slip: fixed and saved again — not the system's fault
            self.log(e, f"✏️ {scr['name']}: {r['msg']} — صلّحه", None)
            self.status(e, "blocked", scr["name"], "بيصلّح غلطة")
            self.after(2, self._redo, e, task, attempt)
            return
        if r["kind"] in ("error", "reject"):
            self.log(e, f"❌ {scr['name']}: {r['msg']}", False)
            e["last_err"] = r["msg"]
            if attempt == 1:
                self.status(e, "blocked", scr["name"], "بيحاول تاني")
                self.after(4, self._retry, e, task, 1)
                return
            e["failed"] += 1
            helper = self.by_role("manager") if e["role"] != "manager" else self.by_role("accountant")
            self.say(e, self.line("fail_ask", to=helper["name"] if helper else "", screen=scr["name"], msg=r["msg"]), helper)
            if helper:
                self.say(helper, self.line("fail_reply"), e)
            self.complain(e, "خطأ سيستم" if r["kind"] == "error" else "رفض", scr["name"], r["msg"],
                          f"فشل مرتين ورا بعض · {'رسالة السيرفر' if r['kind'] == 'error' else 'رسالة النظام'}: {r['msg']}"
                          + (f"\n{r['evidence']}" if r.get("evidence") else ""), d, r={**r, "action": task.get("action") or "add"})
            if d:
                d["state"] = "متعطلة"
                self.deal_step(d, f"❌ اتعطلت عند {e['name']} في «{scr['name']}»: {r['msg']}", "fail")
            self.status(e, "idle")
            self._next(e)
            return
        task["_did"], task["_r"] = r.get("did", "sim"), r                   # what really happened, for what the employee says next
        e["done"] += 1
        self.log(e, f"✅ {scr['name']}: {task['label']}" if task["_did"] != "open" else f"👁️ {scr['name']}: فتح الشاشة بس ({task['label']})", True)
        self.status(e, "idle")
        if d:
            self.deal_step(d, f"{e['name']}: {task['label']}")
        cb = task.get("then")
        if cb:
            getattr(self, cb)(e, d, task)
        self._next(e)

    # ------------------------------------------------------------------ the screen round (the scenarios document)
    MONTH_END = [("manager", None, "النهارده آخر الشهر — إقفال: كل واحد يراجع اللي عنده قبل ما نقفل الفترة"),
                 ("cashier", "cash_count", "هجرد الصناديق وأطابقها مع السيستم"),
                 ("warehouse", "stock_check", "هراجع حركة الأصناف والأرصدة قبل الجرد"),
                 ("accountant", "journal_review", "همر على قيود الشهر كلها"),
                 ("accountant", "customer_statement", "هطابق كشوف حساب العملاء"),
                 ("accountant", "account_statement", "هطلع كشف حساب الحسابات الرئيسية"),
                 ("accountant", "trial_balance", "ميزان المراجعة آخر الشهر — لازم مدين = دائن"),
                 ("manager", "approval", "هعتمد المستندات المعلقة قبل الإقفال")]

    def _month_end(self):
        """📅 the closing day of a month: cash count, stock review, the month's entries, statements, the trial balance, approvals"""
        for i, (role, key, line) in enumerate(self.MONTH_END):
            e = self.by_role(role)
            if not e:
                continue
            if key is None:
                self.at(self.start + 20, self._story_say, role, line)
                continue
            if key not in self.erp.screens:
                continue
            act = "review" if key in ("trial_balance", "journal_review") else None
            self.at(self.start + 60 + i * 25, self._story_say, role, line)
            task = {"screen": key, "label": f"📅 إقفال الشهر — {self.erp.screen(key)['name']}"}
            if act:
                task["action"] = act
            self.at(self.start + 61 + i * 25, self.assign, e, task)

    def _said_guard(self, e, d, t):
        r = (t or {}).get("_r") or {}
        self.guards.append({"who": e["name"], "what": t.get("label", ""), "kind": r.get("kind", ""), "note": r.get("note") or r.get("msg") or ""})
        if r.get("note"):
            self.say(e, r["note"])

    def _said_backdate(self, e, d, t):
        """🕵️ a sales order dated 2020: an open old period = anyone can rewrite last years' books"""
        r = (t or {}).get("_r") or {}
        no = r.get("doc_no")
        if r.get("kind") == "ok" and no:
            self.complain(e, "رقابة ناقصة", self.erp.screen("sales_order")["name"],
                          f"السيستم قبل أمر بيع بتاريخ 01-01-2020 (رقم {no}) — الفترات القديمة مفتوحة للتسجيل",
                          "🕵️ اختبار المختلس: مستند بتاريخ قديم المفروض يترفض لو الفترة مقفولة — هيتمسح حالًا", source="erp", r=r)
            self.guards.append({"who": e["name"], "what": "أمر بيع بتاريخ 2020", "kind": "wrong", "note": f"اتقبل (رقم {no}) واتمسح"})
            self.say(e, self.T(f"🕵️ سجلت أمر بيع بتاريخ 2020 والسيستم قبله (رقم {no}) — كتبتها شكوى وهمسحه دلوقتي",
                              f"🕵️ I saved a sales order dated 2020 and the system accepted it (no. {no}) — logged a complaint, deleting it now"))
            self.assign(e, {"screen": "sales_order", "action": "delete", "doc_no": no, "label": f"حذف أمر البيع التجريبي {no}"})
        else:
            self.guards.append({"who": e["name"], "what": "أمر بيع بتاريخ 2020", "kind": "ok", "note": r.get("msg") or "اترفض"})
            self.say(e, self.T("🕵️ حاولت أسجل أمر بيع بتاريخ 2020 والسيستم ما قبلهوش ✅", "🕵️ I tried to save a sales order dated 2020 and the system refused it ✅"))

    def _burst(self):
        """⚡ everyone opens his main screen at the same moment: how the site answers under load"""
        first = {}
        for k, role in ROUND:
            first.setdefault(role, k)
        for e in self.emps.values():
            k = first.get(e["role"])
            if k and k in self.erp.screens and e.get("status") != "away":
                self.assign(e, {"screen": k, "label": f"⚡ اختبار ضغط — {self.erp.screen(k)['name']}", "then": "_said_burst"})

    def _said_burst(self, e, d, t):
        r = (t or {}).get("_r") or {}
        self.burst.append({"screen": self.erp.screen(t["screen"])["name"], "ms": r.get("ms") or 0, "who": e["name"], "kind": r.get("kind", "")})

    def _said_ready(self, e, d, t):
        """the readiness check's findings: each empty required list is a setup problem known before anyone tries the screen"""
        v = (t.get("_r") or {}).get("ready") or {}
        self.ready = v
        names = v.get("names") or {}
        for k, labels in (v.get("empty") or {}).items():
            self.complain(e, "إعداد ناقص", names.get(k, k), f"«{'، '.join(labels)}» إجباري ومفيهوش ولا اختيار",
                          f"فحص الجاهزية فتح فورم الإضافة قبل الشغل: القايمة فاضية — تتملى من شاشة الإعداد بتاعها", source="data")
        n = len(v.get("empty") or {})
        self.say(e, self.T(f"فحصت الموقع قبل ما نبدأ: {v.get('seen', 0)} شاشة" + (" — كله جاهز 👍" if not n else f" — في {n} شاشة ناقصها إعداد، كتبتها في الشكاوى"),
                          f"I checked the site before we start: {v.get('seen', 0)} screens" + (" — all ready 👍" if not n else f" — {n} screens are missing setup, logged in complaints")))

    def _round_start(self, key, role, waited=0):
        """one main screen, four scenarios, one employee: add → edit the same document → print it → delete it"""
        e = self.by_role(role) or self.by_role("accountant")
        if not e or key not in self.erp.screens:
            return
        src = ROUND_NEEDS.get(key)
        if src:                                                    # a return is made FROM an invoice: wait for the round's invoice
            sd = next((x for x in self.deals.values() if x.get("round") == src), None)
            got = sd and (sd.get("docs") or {}).get(src)
            if not got and sd and sd["state"] == "شغالة" and waited < 6:
                self.after(30, self._round_start, key, role, waited + 1)
                return
            if not got:
                name, sname = self.erp.screen(key)["name"], self.erp.screen(src)["name"]
                rid = f"R-{len([x for x in self.deals.values() if x.get('round')]) + 1:02d}"
                self.deals[rid] = {"id": rid, "round": key, "customer": "—", "item": name, "qty": 0, "amount": 0, "sales": e["id"], "state": "اتقفلت",
                                   "start": self.now, "steps": [], "opened": _hm(self.now),
                                   "res": {"add": f"⏭️ محتاج «{sname}» متحفظة الأول — {sname} ما اتحفظتش في الجولة", "edit": "—", "print": "—", "delete": "—"}}
                self.deal_step(self.deals[rid], f"⏭️ «{name}» اتأجل: بيتعمل من «{sname}»، و{sname} ما اتحفظتش النهارده", "info")
                return
        name = self.erp.screen(key)["name"]
        rid = f"R-{len([x for x in self.deals.values() if x.get('round')]) + 1:02d}"
        based = {ROUND_BASED[key]: str(got)} if src and key in ROUND_BASED else None
        d = {"id": rid, "round": key, "based": based, "customer": "—", "item": name, "qty": 0, "amount": 0, "sales": e["id"], "state": "شغالة", "start": self.now,
             "steps": [], "opened": _hm(self.now)}
        self.deals[rid] = d
        ch = (self.story.get("chapters") or {}).get(key) or {}
        d["note"] = ch.get("note")
        self.deal_step(d, f"🧪 جولة «{name}»: إضافة ← تعديل ← طباعة ← حذف — مع {e['name']}", "info")
        if ch.get("start"):
            self.say(e, ch["start"])
        self.assign(e, {"screen": key, "label": f"إضافة {name} (جولة الشاشات)", "deal": rid, "then": "_round_edit"})

    def _story_say(self, role, text):
        e = self.by_role(role) if role else None
        if e and text:
            self.say(e, text)

    def _chapter(self, d, part):
        """the story's line for this step of a round deal (start / edit / print / delete), and the colleague's reply after the add"""
        ch = (self.story.get("chapters") or {}).get(d.get("round")) or {}
        return ch.get(part), ch.get("react")

    def _round_edit(self, e, d, t):
        line, react = self._chapter(d, "edit")
        if (d.get("res") or {}).get("add", "").startswith("✅") and react:
            self.after(1, self._story_say, react.get("role"), react.get("text"))
        if line and (d.get("res") or {}).get("add", "").startswith("✅"):
            self.say(e, line)
        self.assign(e, {"screen": d["round"], "action": "edit", "label": f"تعديل نفس المستند — {self.erp.screen(d['round'])['name']}", "deal": d["id"],
                        "then": "_round_print"})

    def _round_print(self, e, d, t):
        line, _ = self._chapter(d, "print")
        if line and (d.get("res") or {}).get("add", "").startswith("✅"):
            self.say(e, line)
        self.assign(e, {"screen": d["round"], "action": "print", "label": f"طباعة نفس المستند — {self.erp.screen(d['round'])['name']}", "deal": d["id"],
                        "then": "_round_delete"})

    def _round_delete(self, e, d, t, waited=0):
        # a source document (the invoice a return is made from…) stays until the round that needs it has used it
        dep = next((x for x in self.deals.values() if x.get("round") and ROUND_NEEDS.get(x["round"]) == d["round"] and x["state"] == "شغالة"
                    and not (x.get("res") or {}).get("add")), None)
        waiting = any(k for k, v in ROUND_NEEDS.items() if v == d["round"] and not any(x.get("round") == k for x in self.deals.values()))
        if (dep or waiting) and waited < 12:
            self.after(30, self._round_delete, e, d, t, waited + 1)
            return
        line, _ = self._chapter(d, "delete")
        if line and (d.get("res") or {}).get("add", "").startswith("✅"):
            self.say(e, line)
        self.assign(e, {"screen": d["round"], "action": "delete", "label": f"حذف نفس المستند — {self.erp.screen(d['round'])['name']}", "deal": d["id"],
                        "then": "_round_done"})

    def _round_done(self, e, d, t):
        d["state"] = "اتقفلت"
        d["closed"] = _hm(self.now)
        d["cycle_min"] = round(self.now - d["start"])
        self.deal_step(d, "✅ الأربع سيناريوهات خلصت", "done")

    def _real_facts(self, e, d, task, scr, f):
        """what the employee REALLY entered on NQ ERP: the deal takes the real customer, item, quantity and total,
        and the employee tells the others the real document — from here on the chat speaks the system's data"""
        if d is not None and d.get("round"):
            d.setdefault("real", {}).setdefault("docs", []).append({"screen": scr["name"], **f})
        elif d is not None:
            real = d.setdefault("real", {})
            if f.get("party") and not real.get("party"):
                real["party"] = f["party"]
                d["customer"] = f["party"]
            if f.get("item") and not real.get("item"):
                real["item"] = f["item"]
                d["item"] = f["item"]
                if f.get("qty"):
                    d["qty"] = f["qty"] if f["qty"] % 1 else int(f["qty"])
            if f.get("party") and task["screen"] in ("purchase_order", "stock_receipt", "purchase_invoice"):
                d["supplier"] = f["party"]
            if f.get("total") and task["screen"] in ("quotation", "sales_order", "sales_invoice"):
                d["amount"] = f["total"]
            real.setdefault("docs", []).append({"screen": scr["name"], **f})
        bits = [f"{scr['name']} رقم {f['no']}" if f.get("no") else scr["name"]]
        if f.get("party"):
            bits.append(f"لـ {f['party']}")
        if f.get("item"):
            q = f.get("qty")
            bits.append(f"{f['item']}" + (f" × {q:g}" if q else "") + (f" بسعر {f['price']:,.2f}" if f.get("price") else ""))
        if f.get("total"):
            bits.append(f"الإجمالي {f['total']:,.2f}")
        if getattr(self, "lang", "ar") == "en":
            from simulation.i18n import screen_en
            eb = [f"{screen_en(scr['name'])} no. {f['no']}" if f.get("no") else screen_en(scr["name"])]
            if f.get("party"):
                eb.append(f"for {f['party']}")
            if f.get("item"):
                q = f.get("qty")
                eb.append(f"{f['item']}" + (f" × {q:g}" if q else "") + (f" at {f['price']:,.2f}" if f.get("price") else ""))
            if f.get("total"):
                eb.append(f"total {f['total']:,.2f}")
            self.say(e, "Saved on the system: " + " · ".join(eb))
            return
        self.say(e, "سجلت على السيستم: " + " · ".join(bits))

    def _redo(self, e, task, attempt):
        e["status"] = "idle"
        self._do(e, task, attempt=attempt)

    def _retry(self, e, task, attempt=1):
        e["status"] = "idle"
        self._do(e, task, attempt=1 if attempt == 0 else (attempt + 1 if attempt == 1 else attempt))

    # ------------------------------------------------------------------ the sales cycle
    def new_order(self):
        sales = self.by_role("sales")
        if not sales:                                       # no sales person today → no deals
            return
        n = len(self.deals) + 1
        qty = self.rng.choice([5, 10, 20, 30, 50, 80])
        price = self.rng.choice([180, 250, 320, 450, 900, 1300])
        d = {"id": f"D-{n:03d}", "customer": self.rng.choice(self.cfg["customers"]), "item": self.rng.choice(self.cfg["items"]), "qty": qty,
             "amount": qty * price, "sales": sales["id"], "state": "شغالة", "start": self.now, "steps": [], "opened": _hm(self.now)}
        self.deals[d["id"]] = d
        if getattr(self.erp, "real_writes", False):             # real NQ ERP: the customer and item come from what gets saved
            d["customer"], d["item"] = "—", "—"
            self.say(sales, self.line("order_in_real"))
        else:
            self.say(sales, self.line("order_in", customer=d["customer"], qty=qty, item=d["item"]))
        self.deal_step(d, f"طلب من {d['customer']}: {qty} {d['item']} ({d['amount']:,})", "info")
        self.assign(sales, {"screen": "quotation", "label": f"عرض سعر {d['id']} — {d['customer']}", "deal": d["id"], "then": "_after_quote"})

    def _customer_change(self, did):
        d = self.deals[did]
        sales = self.emps[d["sales"]]
        self.say(sales, self.line("customer_change", **self._kw(d)))
        self.assign(sales, {"screen": "sales_invoice", "action": "edit", "label": f"تعديل فاتورة {d['id']} — طلب العميل", "deal": did, "then": "_after_edit"})

    def _after_edit(self, e, d, t):
        acc = self.by_role("accountant")
        self.handoff(e, acc, "to_review_edit", {"screen": "journal_review", "action": "review", "label": f"مراجعة قيد {d['id']} بعد التعديل", "deal": d["id"]},
                     **self._kw(d))

    def _kw(self, d):
        return {"customer": d["customer"], "item": d["item"], "qty": d["qty"], "amount": f"{d['amount']:,}", "deal": d["id"]}

    def _after_quote(self, e, d, t):
        if self.rng.random() < .15:                                  # a duplicate quotation by mistake → made, then deleted
            self.assign(e, {"screen": "quotation", "label": f"عرض سعر {d['id']} تاني (بالغلط)", "deal": d["id"], "doc_key": "quotation_dup",
                            "then": "_after_dup"})
        self.assign(e, {"screen": "sales_order", "label": f"أمر بيع {d['id']}", "deal": d["id"], "then": "_after_so"})

    def _after_dup(self, e, d, t):
        self.say(e, self.line("dup_delete", **self._kw(d)))
        self.assign(e, {"screen": "quotation", "action": "delete", "label": f"حذف عرض السعر المكرر لـ {d['customer']}", "deal": d["id"], "doc_key": "quotation_dup"})

    def _after_so(self, e, d, t):
        wh = self.by_role("warehouse")
        self.handoff(e, wh, "to_warehouse", {"screen": "stock_check", "label": f"رصيد {d['item']} لأمر {d['id']}", "deal": d["id"], "then": "_after_stock"}, **self._kw(d))

    def _opened(self, t):
        """the real system was only opened — no upload, no save, no approval happened (so nobody may say it did)"""
        return (t or {}).get("_did") == "open"

    def _real(self, t):
        return (t or {}).get("_did") in ("open", "write", "review")

    def _after_stock(self, e, d, t):
        sales = self.emps[d["sales"]]
        if self._real(t):                                             # the real balance is the system's to say: the issue voucher will tell
            self.say(e, self.T(f"فتحت «{self.erp.screen('stock_check')['name']}» على السيستم — داخل أعمل سند الصرف، ولو الرصيد مش كفاية السيستم هيرفض",
                              "I opened the Item Card on the system — making the stock issue now; if the balance is short the system will refuse it"), sales)
            self.assign(e, {"screen": "stock_issue", "label": f"صرف {d['item']} لأمر {d['id']}", "deal": d["id"], "then": "_after_issue"})
            return
        if self.rng.random() < self.erp.stock_short_p and not d.get("bought"):
            self.say(e, self.line("stock_short", to=sales["name"], **self._kw(d)), sales)
            pur = self.by_role("purchasing")
            d["supplier"] = self.rng.choice(self.cfg["suppliers"])
            self.handoff(e, pur, "to_purchasing", {"screen": "purchase_order", "label": f"أمر شراء {d['item']} لأمر {d['id']}", "deal": d["id"],
                                                   "then": "_after_po"}, **self._kw(d))
        else:
            self.say(e, self.line("stock_ok", to=sales["name"], **self._kw(d)), sales)
            self.assign(e, {"screen": "stock_issue", "label": f"صرف {d['qty']} {d['item']} لأمر {d['id']}", "deal": d["id"], "then": "_after_issue"})

    def _after_po(self, e, d, t):
        if self.rng.random() < .2:                                   # the supplier changes the price → the order is edited
            self.assign(e, {"screen": "purchase_order", "action": "edit", "label": f"تعديل أمر شراء {d['item']} — المورد غيّر السعر", "deal": d["id"]})
        if not self._real(t):                                         # on the real system the saved order was already announced with its data
            self.say(e, self.line("po_done", to=self.emps[d["sales"]]["name"], supplier=d["supplier"], **self._kw(d)))
        self.after(self.rng.uniform(30, 90), self._goods_arrive, d["id"])

    def _goods_arrive(self, did):
        d = self.deals[did]
        wh = self.by_role("warehouse")
        d["bought"] = True
        self.assign(wh, {"screen": "stock_receipt", "label": f"استلام {d['item']} من {d['supplier']}", "deal": did, "then": "_after_receipt"})

    def _after_receipt(self, e, d, t):
        if not self._real(t):
            self.say(e, self.line("goods_in", supplier=d["supplier"], **self._kw(d)))
        acc = self.by_role("accountant")
        self.handoff(e, acc, "to_accountant_pi", {"screen": "purchase_invoice", "label": f"فاتورة شراء {d['supplier']}", "deal": d["id"]}, supplier=d["supplier"], **self._kw(d))
        self.assign(e, {"screen": "stock_issue", "label": f"صرف {d['qty']} {d['item']} لأمر {d['id']}", "deal": d["id"], "then": "_after_issue"})

    def _after_issue(self, e, d, t):
        sales = self.emps[d["sales"]]
        self.handoff(e, sales, "to_sales_invoice", {"screen": "sales_invoice", "label": f"فاتورة بيع {d['id']} — {d['customer']}", "deal": d["id"],
                                                    "then": "_after_invoice"}, to_name=sales["name"], **self._kw(d))

    def _after_invoice(self, e, d, t):
        d["invoiced"] = True
        self.assign(e, {"screen": "sales_invoice", "action": "print", "label": f"طباعة فاتورة {d['id']} للعميل", "deal": d["id"]})
        acc = self.by_role("accountant")
        self.handoff(e, acc, "to_accountant", {"screen": "journal_review", "label": f"مراجعة قيد {d['id']}", "deal": d["id"], "then": "_after_journal"}, **self._kw(d))

    def _after_journal(self, e, d, t):
        if d["amount"] >= self.cfg["approval_limit"]:
            m = self.by_role("manager")
            self.handoff(e, m, "to_manager", {"screen": "approval", "label": f"اعتماد {d['id']} ({d['amount']:,})", "deal": d["id"], "then": "_after_approval"},
                         **self._kw(d))
        else:
            self._to_cashier(e, d)

    def _after_approval(self, e, d, t):
        acc = self.by_role("accountant")
        if self._opened(t):
            self.say(e, self.T(f"فتحت «{self.erp.screen('approval')['name']}» على السيستم — الاعتماد نفسه البرنامج لسه مش بيعمله، كمّل يا {acc['name']}",
                              f"I opened Document Approval on the system — the approval itself isn't automated yet, go ahead {acc['name']}"), acc)
        else:
            self.say(e, self.line("approved", to=acc["name"]), acc)
        self._to_cashier(e, d)

    def _to_cashier(self, e, d):
        c = self.by_role("cashier")
        self.handoff(e, c, "to_cashier", {"screen": "receipt_voucher", "label": f"سند قبض {d['customer']} — {d['amount']:,}", "deal": d["id"],
                                          "then": "_after_receipt_voucher"}, **self._kw(d))

    def _after_receipt_voucher(self, e, d, t):
        self.assign(e, {"screen": "receipt_voucher", "action": "print", "label": f"طباعة سند قبض {d['customer']}", "deal": d["id"]})
        if self.rng.random() < .25:                                  # the customer asks for a change after the fact
            self.after(self.rng.uniform(20, 60), self._customer_change, d["id"])
        d["state"] = "اتقفلت"
        d["closed"] = _hm(self.now)
        d["cycle_min"] = round(self.now - d["start"])
        self.say(self.emps[d["sales"]], self.line("done_deal", **self._kw(d)))
        self.deal_step(d, f"✅ الصفقة قفلت في {d['cycle_min']} دقيقة", "done")

    # ------------------------------------------------------------------ the daily routine
    def plan_day(self):
        for e in self.emps.values():
            arrive = self.start + self.rng.uniform(0, 20) + (15 if self.rng.random() < 0.1 else 0)
            self.at(arrive, self._arrive, e["id"])
        for e in self.emps.values():
            if self.rng.random() < .75:
                self.at(self.rng.uniform(self.start + 60, self.end - 90), self.coffee, e["id"])
        hr = self.by_role("hr")
        self.at(self.start + 30, self.assign, hr, {"screen": "attendance", "label": "رفع ملف البصمة", "then": "_said_attendance"})
        for _ in range(self.cfg["orders_per_day"]):
            self.at(self.rng.uniform(self.start + 25, self.end - 150), self.new_order)
        c = self.by_role("cashier")
        self.at(self.end - 60, self.assign, c, {"screen": "cash_count", "label": "جرد الخزينة آخر اليوم"})
        a = self.by_role("accountant")
        a2 = self.by_role("accountant", exclude=a["id"]) if a else None
        self.at(self.end - 75, self.assign, a, {"screen": "journal_review", "action": "review", "label": "مراجعة قيود النهارده"})
        self.at(self.end - 45, self.assign, a, {"screen": "trial_balance", "action": "review", "label": "ميزان المراجعة اليومي", "then": "_said_closing"})
        self.at(self.end - 40, self.assign, a2 or a, {"screen": "customer_statement", "action": "review", "label": "مراجعة كشوف حسابات العملاء"})
        self.at(self.end - 35, self.assign, a, {"screen": "account_statement", "action": "review", "label": "كشف حساب الصندوق والبنك"})
        m = self.by_role("manager")
        if getattr(self.erp, "real_writes", False) and "readiness" in self.erp.screens:   # before the work: is the site ready?
            self.at(self.start + 5, self.assign, m, {"screen": "readiness", "action": "review", "label": "فحص جاهزية الموقع قبل الشغل",
                                                     "then": "_said_ready"})
        self.at(self.end - 25, self.assign, m, {"screen": "sales_report", "label": "تقرير المبيعات اليومي", "then": "_said_report"})
        if self.cfg.get("day_type") == "month_end":             # 📅 آلة الزمن: a month-end closing day
            self._month_end()
        if getattr(self.erp, "real_writes", False):              # the watchdogs and the load test (real site only)
            for role, path, at in (("sales", "/PurchaseInvoice/AddEdit", 120), ("warehouse", "/CashIssueVoucher/AddEdit", 125),
                                   ("hr", "/SalesInvoice/AddEdit", 130)):
                e = self.by_role(role)
                if e and "fraud_perm" in self.erp.screens:
                    self.at(self.start + at, self.assign, e, {"screen": "fraud_perm", "path": path, "label": f"🕵️ اختبار الصلاحيات: {path}",
                                                              "then": "_said_guard"})
            s2 = [x for x in self.emps.values() if x["role"] == "sales"]
            if s2 and "sales_order" in self.erp.screens:
                self.at(self.start + 150, self.assign, s2[-1], {"screen": "sales_order", "label": "🕵️ أمر بيع بتاريخ 2020 (اختبار الفترات المقفولة)",
                                                                 "want": {"date": "2020-01-01"}, "then": "_said_backdate"})
            acc = self.by_role("accountant")
            if acc and "audit_docs" in self.erp.screens:
                self.at(self.end - 45, self.assign, acc, {"screen": "audit_docs", "action": "review", "label": "🧾 مراجعة مستندات اليوم",
                                                          "then": "_said_guard"})
            self.at(self.start + 200, self._burst)
        if self.cfg.get("test_waves", True):
            self._test_plan()
        if self.cfg.get("screen_round", True):                   # the round over the main screens: add · edit · print · delete
            for j, x in enumerate(self.story.get("intro") or []):    # the story's morning: what today is about
                self.at(self.start + 22 + j * 2, self._story_say, x.get("role"), x.get("text"))
            for i, (key, role) in enumerate(ROUND):
                self.at(self.start + 35 + i * 6, self._round_start, key, role)
        self.at(self.end, self._end_day)

    def _arrive(self, eid):
        e = self.emps[eid]
        self.status(e, "idle")
        if self.now - self.start > 15:
            self.log(e, f"وصل متأخر {int(self.now - self.start)} دقيقة")
        if self.rng.random() < 0.5:
            self.say(e, self.line("morning"))
        self._next(e)

    def _said_attendance(self, e, d, t):
        r = (t or {}).get("_r") or {}
        if r.get("did") == "write" and r.get("note"):            # the real upload: what the system made of the file
            self.say(e, r["note"])
            return
        if self._real(t) and r.get("kind") in ("reject", "wrong", "error"):
            self.say(e, self.T("حاولت أرفع ملف البصمة على السيستم ومنفعش — كتبت التفاصيل في الشكاوى", "I tried to upload the fingerprint file and it failed — details are in the complaints"))
            return
        if self._opened(t):
            self.say(e, self.T(f"فتحت «{self.erp.screen('attendance')['name']}» على السيستم واتأكدت إنها شغالة — رفع ملف البصمة نفسه البرنامج لسه مش بيعمله",
                          "I opened Attendance on the system and it works — uploading the fingerprint file isn't automated here yet"))
        else:
            self.say(e, self.line("attendance"))

    def _said_closing(self, e, d, t):
        r = (t or {}).get("_r") or {}
        if (t or {}).get("_did") == "review":                         # the real numbers the accountant read
            first = str(r.get("note") or r.get("msg") or "").split("\n")
            self.say(e, self.T("راجعت ميزان المراجعة على السيستم: ", "I reviewed the Trial Balance on the system: ") + " · ".join(x.strip("⚖️ ") for x in first[:3] if x.strip()))
        elif self._opened(t):
            self.say(e, self.T(f"فتحت «{self.erp.screen('trial_balance')['name']}» على السيستم — المراجعة بالأرقام محتاجة أداة الاختبار",
                          "I opened the Trial Balance — checking the figures needs the testing tool"))
        else:
            self.say(e, self.line("closing"))

    def _said_report(self, e, d, t):
        if self._real(t):                                             # only invoices really saved on the system today
            inv = [x for x in self.deals.values() if not x.get("round") and (x.get("docs") or {}).get("sales_invoice")]
            self.say(e, self.T(f"فتحت «{self.erp.screen('sales_report')['name']}» على السيستم · اللي اتسجل فعلًا النهارده من الشركة: "
                               f"{len(inv)} فاتورة بيع بـ {sum(x['amount'] or 0 for x in inv):,.2f}",
                               f"I opened the Daily Sales Report · what the company really saved today: {len(inv)} sales invoices worth {sum(x['amount'] or 0 for x in inv):,.2f}"))
            return
        inv = [x for x in self.deals.values() if x.get("invoiced")]
        self.say(e, self.line("manager_report", n=len(inv), amount=f"{sum(x['amount'] for x in inv):,}"))

    def _end_day(self):
        for e in self.emps.values():
            if self.rng.random() < 0.4:
                self.say(e, self.line("evening"))
            self.status(e, "away")
        self.running = False
        if hasattr(self.erp, "close"):
            threading.Thread(target=lambda: self.erp.close(120) if getattr(self.erp, "is_async", False) else self.erp.close(), daemon=True).start()
        self.report = self.make_report()
        if self.report.get("mode") != "محاكاة":
            self.report["regressions"] = self._regressions(self.report)
            self.report["learning"] = self._learn()
        self.runs.mkdir(parents=True, exist_ok=True)
        (self.runs / f"day_{datetime.now():%Y%m%d_%H%M%S}.json").write_text(json.dumps(self.report, ensure_ascii=False, indent=1), encoding="utf-8")
        self._manager_summary()
        self._emit("day_end", self.report)

    def _frustration(self):
        """😣 how hard each screen was on the employees today: failures weigh most, then waiting — a usability signal for the developers"""
        out = []
        for name, v in self.screen_ms.items():
            fails = self.screen_fail.get(name, 0)
            avg = sum(v) / len(v) if v else 0
            comp = sum(1 for c in self.complaints if c["screen"] == name)
            score = min(100, round(fails / max(1, len(v)) * 60 + min(avg / 1000, 60) / 60 * 25 + min(comp, 5) * 3))
            out.append({"screen": name, "n": len(v), "fails": fails, "avg": round(avg), "complaints": comp, "score": score})
        return sorted(out, key=lambda x: -x["score"])[:15]

    def _burst_summary(self):
        if not self.burst:
            return None
        normal = {k: sum(v) / len(v) for k, v in self.screen_ms.items() if v}
        rows = [{**b, "normal": round(normal.get(b["screen"], 0))} for b in self.burst]
        return {"n": len(rows), "avg": round(sum(b["ms"] for b in rows) / len(rows)), "max": max(b["ms"] for b in rows), "rows": rows}

    def ask(self, eid, q):
        """💬 an employee answers from his own day: the documents he made (number, customer, total), what failed and why,
        and his last steps — matched on the question's words (a screen, a customer, a number), no AI"""
        import re as _re
        with self.lock:
            e = self.emps.get(eid)
            if not e:
                return "مين ده؟ الموظف مش في الشركة النهارده"
            q = str(q or "").strip()
            words = [w for w in _re.split(r"[\s،,؟?.]+", q) if len(w) > 1 and w not in ("عملت", "ايه", "إيه", "في", "على", "من", "انت", "إنت", "النهارده")]
            mine = [d for d in self.deals.values() if d.get("sales") == eid or any(s.get("who") == e["name"] for s in d.get("steps", []))]
            docs = [x for d in self.deals.values() for x in (d.get("real") or {}).get("docs", []) if d.get("sales") == eid]
            comp = [c for c in self.complaints if c.get("emp") == eid]
            hit = lambda t: not words or any(w in str(t) for w in words)
            lines = []
            for x in docs:
                if hit(x):
                    lines.append(f"• {x.get('screen')} رقم {x.get('no')}" + (f" لـ {x['party']}" if x.get("party") else "") + (f" · الإجمالي {x['total']}" if x.get("total") else ""))
            for c in comp:
                if hit(c["screen"] + c["text"]):
                    lines.append(f"• {c['clock']} {c['screen']}: {c['text'][:140]}")
            if not lines:
                for l in e["log"][-60:]:
                    if hit(l["text"]):
                        lines.append(f"• {l['clock']} {l['text'][:140]}")
            if not lines:
                last = e["log"][-3:]
                return (f"مش فاكر حاجة عن «{q}» النهارده. آخر حاجات عملتها:\n" + "\n".join(f"• {l['clock']} {l['text'][:120]}" for l in last)) if last else "لسه ما بدأتش شغل النهارده"
            head = f"أنا {e['name']} — " + (f"عن «{q}»:" if q else "اللي عملته النهارده:")
            return head + "\n" + "\n".join(lines[-8:])

    def _people(self):
        try:
            return json.loads((self.runs / "people.json").read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _learn(self):
        """🎓 after a real day: every job done well adds a little experience (faster, fewer slips), every failure costs a little —
        the team on day 10 is not the team on day 1, like a real company"""
        people = self._people()
        out = []
        for eid, e in self.emps.items():
            m = people.setdefault(eid, {"name": e["name"], "days": 0, "experience": e["experience"], "history": []})
            before = float(m.get("experience", e["experience"]))
            after = max(.1, min(1.0, before + 0.01 * e["done"] - 0.005 * e["failed"]))
            m.update({"name": e["name"], "days": m.get("days", 0) + 1, "experience": round(after, 3)})
            m["history"] = (m.get("history") or [])[-29:] + [{"date": datetime.now().strftime("%Y-%m-%d"), "done": e["done"], "failed": e["failed"],
                                                               "experience": round(after, 3)}]
            out.append({"name": e["name"], "days": m["days"], "before": round(before, 2), "after": round(after, 2), "done": e["done"], "failed": e["failed"]})
        try:
            self.runs.mkdir(parents=True, exist_ok=True)
            (self.runs / "people.json").write_text(json.dumps(people, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass
        return out

    def _regressions(self, report):
        """🧬 the system's problems remembered across days: first / last seen, how many days, and «fixed» once a day that worked
        the same screen didn't meet it again — every bug becomes a check that runs every day"""
        from simulation.sources import problem_key
        f = self.runs / "regressions.json"
        try:
            mem = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            mem = {}
        today = datetime.now().strftime("%Y-%m-%d")
        worked = {x["screen"] for x in report.get("round") or []} | set(self.screen_ms)
        seen = set()
        for c in self.complaints:
            if c.get("source") != "erp":
                continue
            k = problem_key(c["screen"], c["text"])
            seen.add(k)
            m = mem.setdefault(k, {"screen": c["screen"], "text": c["text"][:200], "first": today, "days": []})
            m["last"], m["status"] = today, "open"
            if today not in m["days"]:
                m["days"].append(today)
        for k, m in mem.items():
            if k not in seen and m.get("status") == "open" and m["screen"] in worked and m.get("last") != today:
                m["status"], m["fixed"] = "fixed", today
        try:
            self.runs.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(mem, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass
        items = sorted(mem.values(), key=lambda m: (m.get("status") != "open", -len(m.get("days", []))))
        return {"open": sum(1 for m in items if m.get("status") == "open"), "fixed": sum(1 for m in items if m.get("status") == "fixed"),
                "items": items[:40]}

    # ------------------------------------------------------------------ the end-of-day report
    # ------------------------------------------------------------------ 🧪 the test waves
    TECH = re.compile(r"Exception|String or binary|Object reference|خطأ سيرفر|Server Error|500|stack|SqlException", re.I)

    def _test_plan(self):
        """every kind of test that isn't the daily round, spread over the day (simulation/data/test_catalog.json lists them)"""
        S = self.erp.screens
        sales = [x for x in self.emps.values() if x["role"] == "sales"]
        m, acc = self.by_role("manager"), self.by_role("accountant")
        pur = self.by_role("purchasing") or acc or m
        hr = self.by_role("hr")
        s1, s2 = (sales[0], sales[1]) if len(sales) > 1 else (sales[0], sales[0]) if sales else (m, m)
        T = self.T
        it = self.by_role("it")
        if it and "it_sweep" in S:                               # 🖥️ IT: first thing in the morning, and again after lunch
            for at in (12, 300):
                self.at(self.start + at, self.assign, it, {"screen": "it_sweep", "probe": "it_sweep",
                                                           "label": T("🖥️ فحص الصبح: بفتح كل شاشات السيستم وبتأكد إنها بتحمّل من غير Error أو 404", "🖥️ Morning check: opening every screen of the system — loads, no error, no 404")
                                                           if at < 100 else T("🖥️ فحص بعد الضهر: كل شاشات السيستم تاني", "🖥️ Afternoon check: every screen again")})
        if it and "it_speed" in S:                               # 🐢 IT's second round: the screens' speed, morning and again after lunch
            for at in (40, 330):
                self.at(self.start + at, self.assign, it, {"screen": "it_speed", "probe": "it_speed",
                                                           "label": T("🐢 فحص السرعة: بقيس كل شاشة قوايم بتاخد قد إيه لحد ما بياناتها تظهر", "🐢 Speed check: timing every list screen until its data shows")
                                                           if at < 100 else T("🐢 فحص السرعة تاني: مين بقى أبطأ من الصبح؟", "🐢 Speed check again: which screens got slower than this morning?")})
        plan = [(70, s1, "neg_required", "required", T("🧪 اختبار: حفظ بحقل إجباري فاضي", "🧪 Test: save with a required field empty")),
                (95, s2, "neg_negative", "negative", T("🧪 اختبار: كمية بالسالب", "🧪 Test: a negative quantity")),
                (120, s1, "neg_discount", "discount", T("🧪 اختبار: خصم 150%", "🧪 Test: a 150% discount")),
                (145, s2, "neg_text", "text", T("🧪 اختبار: بيان طويل بحروف خاصة", "🧪 Test: long text with special characters")),
                (170, pur, "neg_dupref", "dup1", T("🧪 اختبار: رقم فاتورة مورد متكرر (الأولى)", "🧪 Test: duplicate supplier invoice no. (first)")),
                (300, s2, "perf_lines", "perf_lines", T("⚡ اختبار: عرض سعر بـ 30 سطر", "⚡ Test: a quotation with 30 lines")),
                (85, m, "sec_nologin", "sec_nologin", T("🔐 اختبار: روابط الشاشات من غير تسجيل دخول", "🔐 Test: screen links without logging in")),
                (110, m, "sec_secrets", "sec_secrets", T("🔐 اختبار: أسرار مكتوبة في كود الصفحات", "🔐 Test: secrets written in the pages")),
                (330, m, "ux_mobile", "ux_mobile", T("📱 اختبار: الشاشات على مقاس الموبايل", "📱 Test: screens at phone size")),
                (350, m, "ux_lang", "ux_lang", T("🌐 اختبار: واجهة السيستم بالإنجليزي", "🌐 Test: the system in English")),
                (self.end - self.start - 70, acc or m, "tb_numbers", "tb_numbers", T("⚖️ اختبار: أرقام ميزان المراجعة", "⚖️ Test: trial balance figures")),
                (self.end - self.start - 55, acc or m, "acc_books", "acc_books", T("📒 مراجعة قيود اليوم: كل قيد متزن وكل مستند ليه قيد", "📒 Today's books: every entry balanced, every document has its entry"))]
        if hr and "payroll" in S:
            plan.append((200, hr, "payroll", "payroll", T("💰 مسير رواتب الشهر (إضافة ← حذف)", "💰 This month's payroll (add → delete)")))
        for at, who, key, probe, label in plan:
            if who and key in S:
                t = {"screen": key, "probe": probe, "label": label}
                if key == "neg_dupref":                          # a number used once today, then again
                    t["mutate_val"] = f"VC-{datetime.now():%m%d}-{self.rng.randrange(1000, 9999)}"
                self.at(self.start + at, self.assign, who, t)
        if "quotation" in S and sales:
            g = f"num{self.rng.randrange(10**6)}"                # two saves in the same second: numbers must differ
            for who in {s1["id"]: s1, s2["id"]: s2}.values() if s1 is not s2 else [s1, s1]:
                self.at(self.start + 220, self._urgent, who, {"screen": "quotation", "probe": "conc_num", "group": g, "label": T("👥 اختبار: حفظ في نفس الثانية", "👥 Test: saving in the same second")})
            self.at(self.start + 245, self.assign, s1, {"screen": "quotation", "probe": "conc_make", "label": T("👥 اختبار التزامن: مستند للتعديل المزدوج", "👥 Concurrency: a document for the double edit")})
            self.at(self.start + 270, self.assign, s1, {"screen": "quotation", "probe": "del_make", "label": T("🔐 اختبار: مستند يحذفه زميل", "🔐 Test: a document a colleague deletes")})
        self.at(self.end - 95, self._probe_late)
        if "int_vat" in S:
            self.at(self.end - 60, self._vat_check)

    def _vat_check(self):
        """🧮 VAT 15%: every saved invoice / quotation whose quantity, price and total the system showed: total = qty × price (+15%)"""
        scr = self.erp.screen("int_vat")
        acc = self.by_role("accountant") or self.by_role("manager")
        if not acc:
            return
        docs = [x for d in self.deals.values() for x in ((d.get("real") or {}).get("docs") or [])
                if x.get("qty") and x.get("price") and x.get("total")]
        bad, n = [], 0
        if self.erp.mode == "محاكاة":                              # the simulation: a handful of invoices, now and then one off
            for i in range(4):
                n += 1
                if self.rng.random() < 0.08:
                    bad.append(f"فاتورة D-0{20 + i}: الإجمالي 11,600.00 والمتوقع 11,500.00")
        for x in docs:
            base = float(x["qty"]) * float(x["price"])
            tot = float(x["total"])
            n += 1
            if not (abs(tot - base * 1.15) <= max(0.05, base * 0.005) or abs(tot - base) <= max(0.05, base * 0.005)):
                bad.append(f"{x.get('screen', '')} رقم {x.get('no', '')}: {x['qty']:g} × {x['price']:,.2f} = {base:,.2f} · بالضريبة {base * 1.15:,.2f} · الإجمالي في السيستم {tot:,.2f}")
        task = {"screen": "int_vat", "probe": "int_vat", "label": self.T("🧮 اختبار: ضريبة القيمة المضافة 15%", "🧮 Test: VAT 15%")}
        if not n:
            r = {"kind": "skip", "notarget": True, "ms": 0, "msg": self.T("مفيش فواتير النهارده ظاهر فيها الكمية والسعر والإجمالي", "no invoice today showed quantity, price and total")}
        elif bad:
            r = {"kind": "wrong", "ms": 0, "msg": self.T(f"{len(bad)} مستند إجماليه مش = الكمية × السعر + 15%", f"{len(bad)} documents whose total isn't qty × price + 15%"), "evidence": "\n".join(bad[:8])}
        else:
            r = {"kind": "ok", "ms": 0, "note": self.T(f"راجعت {n} مستند: الإجمالي = الكمية × السعر + 15% ✅", f"Checked {n} documents: total = qty × price + 15% ✅")}
        self._probe_done(acc, task, scr, r)

    def _probe_late(self):
        """late in the day: today's invoice -> its journal entry is balanced, and approving our own document"""
        inv = next((x for x in reversed(self.timeline) if x.get("key") == "sales_invoice" and x.get("no") and x["state"] in ("ok", "slow")), None)
        acc, m = self.by_role("accountant"), self.by_role("manager")
        T = self.T
        if acc and "int_je" in self.erp.screens:
            self.assign(acc, {"screen": "int_je", "probe": "int_je", "doc_no": (inv or {}).get("no", ""), "label": T("🧾 اختبار: قيد الفاتورة متزن", "🧾 Test: the invoice's entry balances")})
        if m and "approve_doc" in self.erp.screens:
            self.assign(m, {"screen": "approve_doc", "probe": "approve_doc", "doc_no": (inv or {}).get("no", ""), "label": T("✅ اختبار: اعتماد مستند", "✅ Test: approving a document")})
        self._next(acc) if acc else None
        self._next(m) if m else None

    def _urgent(self, e, task):
        """a task that must start NOW (two colleagues at the same second): first in his queue, started as soon as he's free"""
        if e:
            e["q"].appendleft(task)
            self._next(e)

    def _cleanup(self, who, base, no, label=""):
        """the test's own document goes (only ours: the writer checks the company's ledger)"""
        if no and who:
            self.assign(who, {"screen": base, "action": "delete", "doc_no": str(no), "label": self.T("🧹 حذف مستند الاختبار ", "🧹 Deleting the test document ") + str(no)})

    def _probe_done(self, e, task, scr, r):
        p, k, no = task.get("probe"), r.get("kind"), r.get("doc_no")
        base = r.get("base") or {"neg_dupref": "purchase_invoice"}.get(task["screen"], "quotation")
        msg, T = str(r.get("msg") or ""), self.T
        sim = self.erp.mode == "محاكاة"
        verdict, text = "pass", ""
        if r.get("notarget") or k in ("skip", "offline") or (k == "error" and r.get("tool")):
            verdict, text = "unverified", msg or r.get("probe_log") or T("مقدرتش أتحقق", "couldn't verify")
        elif p in ("required", "negative", "discount"):
            if k in ("reject", "mistake", "denied"):
                verdict, text = ("fail", T(f"اترفض بس برسالة تقنية مش مفهومة: «{msg[:120]}»", f"Refused, but with a technical message: «{msg[:120]}»")) if self.TECH.search(msg)                     else ("pass", T(f"السيستم رفض ✅ «{msg[:120]}»", f"The system refused ✅ «{msg[:120]}»"))
            else:
                verdict, text = "fail", T(f"السيستم قبل الحفظ بـ{ {'required': 'حقل إجباري فاضي', 'negative': 'كمية بالسالب', 'discount': 'خصم 150%'}[p] }"
                                          + (f" (رقم {no})" if no else ""), f"The system accepted a {p} value" + (f" (no. {no})" if no else ""))
                self._cleanup(e, base, no)
        elif p == "text":
            if k in ("ok", "slow", "wrong"):
                text = T("اتحفظ بالنص الطويل والحروف الخاصة ✅", "Saved with the long text and special characters ✅")
                self._cleanup(e, base, no)
            elif self.TECH.search(msg):
                verdict, text = "fail", T(f"النص الطويل وقّع السيستم: «{msg[:120]}»", f"The long text broke the system: «{msg[:120]}»")
            else:
                text = T(f"رفض النص برسالة واضحة ✅ «{msg[:100]}»", f"Refused with a clear message ✅ «{msg[:100]}»")
        elif p == "dup1":
            if k in ("ok", "slow", "wrong") and (no or sim):
                verdict, text = "info", T("اتحفظت فاتورة المورد الأولى — دلوقتي هسجلها تاني بنفس الرقم", "First supplier invoice saved — now the same number again")
                self.assign(e, {"screen": "neg_dupref", "probe": "dup2", "first_no": no, "mutate_val": task.get("mutate_val"), "label": T("🧪 اختبار: نفس رقم فاتورة المورد تاني", "🧪 Test: the same supplier invoice no. again")})
            else:
                verdict, text = "unverified", T(f"الفاتورة الأولى ما اتحفظتش: «{msg[:100]}»", f"The first invoice wasn't saved: «{msg[:100]}»")
        elif p == "dup2":
            if k in ("reject", "mistake"):
                text = T(f"السيستم منع الرقم المتكرر ✅ «{msg[:100]}»", f"The system blocked the duplicate ✅ «{msg[:100]}»")
            else:
                verdict, text = "fail", T("السيستم قبل نفس رقم فاتورة المورد مرتين", "The system accepted the same supplier invoice number twice")
                self._cleanup(e, base, no)
            self._cleanup(e, base, task.get("first_no"))
        elif p == "perf_lines":
            secs = round((r.get("ms") or 0) / 1000, 1)
            if k == "ok":
                text = T(f"اتحفظ بـ {r.get('lines', 30)} سطر في {secs} ث ✅", f"Saved with {r.get('lines', 30)} lines in {secs}s ✅")
            elif k == "slow":
                verdict, text = "fail", T(f"الحفظ بالسطور الكتير أخد {secs} ث", f"Saving many lines took {secs}s")
            else:
                verdict, text = "fail", T(f"مقدرش يحفظ السطور الكتير: «{msg[:100]}»", f"Couldn't save many lines: «{msg[:100]}»")
            self._cleanup(e, base, no)
        elif p in ("conc_num", "conc_edit"):
            box = self.__dict__.setdefault("_conc", {})
            g = task.get("group") or task.get("doc_no") or p
            box.setdefault(g, []).append((e, r))
            if len(box[g]) < 2:
                verdict, text = "info", T("مستني زميله يخلص في نفس اللحظة", "waiting for the colleague's save in the same moment")
            else:
                (e1, r1), (e2, r2) = box.pop(g)
                if p == "conc_num":
                    n1, n2 = r1.get("doc_no"), r2.get("doc_no")
                    if n1 and n2 and n1 == n2:
                        verdict, text = "fail", T(f"مستندين اتحفظوا في نفس الثانية بنفس الرقم {n1}", f"Two documents saved in the same second got the same number {n1}")
                    elif n1 and n2 or sim:
                        text = T(f"حفظ في نفس الثانية: رقمين مختلفين ✅ ({n1 or '—'} / {n2 or '—'})", f"Same-second saves: different numbers ✅ ({n1 or '—'} / {n2 or '—'})")
                    else:
                        verdict, text = "unverified", T("واحد من الحفظين ما تمش", "one of the two saves didn't go through")
                    self._cleanup(e1, "quotation", n1)
                    self._cleanup(e2, "quotation", n2)
                else:
                    oks = [x for x in (r1, r2) if x.get("kind") in ("ok", "slow", "wrong")]
                    if len(oks) == 2:
                        verdict, text = "warn", T("الاتنين عدّلوا نفس المستند في نفس اللحظة والسيستم قبل الاتنين من غير تحذير — آخر حفظ كسب",
                                                  "Both edited the same document at once and the system took both without a warning — the last save won")
                    else:
                        text = T("واحد اتحفظ والتاني اتمنع/اتنبه ✅", "One saved, the other was blocked/warned ✅")
                    self._cleanup(self.emps.get(task.get("maker")) or e, "quotation", task.get("doc_no"))
        elif p == "conc_make":
            if no or (sim and k in ("ok", "slow")):
                verdict, text = "info", T("المستند جاهز — سارة ويوسف هيعدلوه في نفس اللحظة", "Ready — two colleagues edit it at the same moment")
                sales = [x for x in self.emps.values() if x["role"] == "sales"] or [e]
                g = f"ce{no or self.rng.randrange(10**6)}"
                for who in (sales[:2] if len(sales) > 1 else [e, e]):
                    self._urgent(who, {"screen": "quotation", "action": "edit", "doc_no": no, "probe": "conc_edit", "group": g, "maker": e["id"],
                                      "label": T("👥 تعديل نفس المستند مع زميلي في نفس اللحظة", "👥 Editing the same document as my colleague, at the same moment")})
            else:
                verdict, text = "unverified", T("مستند الاختبار ما اتحفظش", "the test document wasn't saved")
        elif p == "del_make":
            if no or (sim and k in ("ok", "slow")):
                verdict, text = "info", T("المستند جاهز — زميلي هيحاول يحذفه", "Ready — a colleague will try to delete it")
                other = next((x for x in self.emps.values() if x["role"] == "sales" and x["id"] != e["id"]), None) or self.by_role("manager")
                self.assign(other, {"screen": "quotation", "action": "delete", "doc_no": no, "probe": "del_other", "maker": e["id"],
                                    "label": T("🔐 اختبار: أحذف مستند عمله زميلي", "🔐 Test: deleting a colleague's document")})
            else:
                verdict, text = "unverified", T("مستند الاختبار ما اتحفظش", "the test document wasn't saved")
        elif p == "del_other":
            if k in ("ok", "slow"):
                verdict, text = "warn", T("مسموح لموظف يحذف مستند عمله زميله — راجع لو ده مقصود", "An employee may delete a colleague's document — check it's intended")
            else:
                text = T(f"السيستم منع حذف مستند الزميل ✅ «{msg[:100]}»", f"The system blocked deleting a colleague's document ✅ «{msg[:100]}»")
                self._cleanup(self.emps.get(task.get("maker")) or e, "quotation", task.get("doc_no"))
        elif p == "payroll":
            if k in ("ok", "slow", "wrong"):
                text = T("مسير الرواتب اتحفظ ✅", "The payroll was saved ✅")
                self._cleanup(e, "payroll", no)
            else:
                verdict, text = "fail", T(f"مسير الرواتب اترفض: «{msg[:120]}»", f"The payroll was refused: «{msg[:120]}»")
        else:                                                      # read checks: 🔐 👁️ 🧮 ⚖️ ✅
            if k in ("ok", "slow"):
                text = r.get("note") or ({"it_sweep": T("فتحت كل الـ 118 شاشة في المنيو — كلها شغالة وبتحمّل بياناتها ✅", "Opened all 118 menu screens — all working and loading their data ✅"),
                                          "acc_books": T("📒 42 قيد النهارده كلهم متزنين، وكل مستند ليه قيده ✅", "📒 42 entries today, all balanced, every document has its entry ✅"),
                                          "it_speed": T("كل شاشات القوايم بتظهر بياناتها في أقل من 8 ث — المتوسط 2.4 ث ✅", "Every list screen shows its data in under 8 s — 2.4 s on average ✅")}.get(p)
                                         if sim else None) or T("تمام ✅", "OK ✅")
            else:
                verdict, text = "fail", msg or T("الاختبار لقى مشكلة", "the test found a problem")
        state = {"pass": "ok", "info": "ok", "warn": "slow", "fail": "fail", "unverified": "skip"}[verdict]
        self._track(e, task, scr, {**r, "_state": state, "msg": text})
        if verdict != "info":
            self.guards.append({"who": e["name"], "what": task.get("label", ""), "kind": {"pass": "ok", "warn": "warn", "fail": "wrong", "unverified": "skip"}[verdict],
                                "note": text, "probe": p})
        if verdict == "fail":
            self.complain(e, T("اختبار", "Test"), scr["name"], text, r.get("evidence") or r.get("probe_log") or msg or text, source="erp", r=r)
        elif verdict == "warn":
            self.complain(e, T("مراجعة تصميم", "Design review"), scr["name"], text, r.get("evidence") or msg or text, source="data", r=r)
        icon = {"pass": "✅", "info": "🧪", "warn": "🟡", "fail": "⛔", "unverified": "❔"}[verdict]
        self.say(e, f"{icon} {task.get('label', '')}: {text}")
        e["done" if verdict in ("pass", "info", "warn") else "failed"] += 1
        self.status(e, "idle")
        self._next(e)

    def _manager_summary(self):
        """🎙️ the manager closes the day in one minute, out loud: deals, the system's problems, the slowest screen, the screens that stopped"""
        m = next((x for x in self.emps.values() if x["role"] == "manager"), None)
        r = self.report or {}
        if not m:
            return
        h = list(getattr(self, "health", {}).values())
        stopped = [x["screen"] for x in h if x.get("last") in ("fail", "denied")]
        slow = (r.get("speed") or [{}])[0]
        if getattr(self, "lang", "ar") == "en":
            from simulation.i18n import screen_en
            p = [f"Team, that's the day: {r.get('closed', 0)} of {r.get('deals', 0)} deals closed",
                 f"we tested {len(h)} screens" + (f", and {len(stopped)} stopped on us: {', '.join(screen_en(x) for x in stopped[:3])}" if stopped else " and all of them worked")]
            if r.get("erp_problems"):
                p.append(f"We logged {r['erp_problems']} problems in the system itself; tickets went to the developers")
            if slow.get("screen"):
                p.append(f"The slowest screen was {screen_en(slow['screen'])} at {round(slow.get('avg', 0) / 1000, 1)} seconds on average")
            if r.get("most_blocked"):
                p.append(f"and the one who got stuck most today was {r['most_blocked']}")
            p.append("Thank you all, see you tomorrow")
            self.say(m, ", ".join(p[:2]) + ". " + ". ".join(p[2:]))
            return
        parts = [f"يا جماعة، خلصنا اليوم: {r.get('closed', 0)} صفقة اتقفلت من {r.get('deals', 0)}"]
        parts.append(f"جربنا {len(h)} شاشة على السيستم" + (f"، ووقف معانا {len(stopped)}: {'، '.join(stopped[:3])}" if stopped else " وكلها مشيت"))
        if r.get("erp_problems"):
            parts.append(f"وسجلنا {r['erp_problems']} مشكلة على السيستم نفسه، اتبعتت تذاكر للمطورين")
        if slow.get("screen"):
            parts.append(f"أبطأ شاشة كانت {slow['screen']} بمتوسط {round(slow.get('avg', 0) / 1000, 1)} ثانية")
        if r.get("most_blocked"):
            parts.append(f"وأكتر واحد اتعطل النهارده {r['most_blocked']}")
        parts.append("شكرًا للجميع، نكمل بكرة")
        self.say(m, "، ".join(parts[:2]) + ". " + ". ".join(parts[2:]))

    def make_report(self):
        rounds = [d for d in self.deals.values() if d.get("round")]
        deals = [d for d in self.deals.values() if not d.get("round")]
        closed = [d for d in deals if d["state"] == "اتقفلت"]
        from simulation.sources import ORDER, SOURCES
        groups = {}
        for c in self.complaints:
            src = c.get("source", "erp")
            k = (src, c["type"], c["screen"])
            g = groups.setdefault(k, {"source": src, "type": c["type"], "screen": c["screen"] or "—", "n": 0, "who": set(), "sample": c["text"],
                                      "evidence": c["evidence"]})
            g["n"] += 1
            g["who"].add(c["name"])
        top = sorted(groups.values(), key=lambda g: (ORDER.index(g["source"]) if g["source"] in ORDER else 9, -g["n"]))
        by_source = [{"source": k, **SOURCES[k], "n": sum(1 for c in self.complaints if c.get("source", "erp") == k)} for k in ORDER]
        for g in top:
            g["who"] = sorted(g["who"])
        speed = sorted(({"screen": s, "avg": round(sum(v) / len(v)), "max": max(v), "n": len(v)} for s, v in self.screen_ms.items()), key=lambda x: -x["avg"])
        day = self.end - self.start
        emps = [{"name": e["name"], "job": e["job"], "done": e["done"], "failed": e["failed"], "complaints": e["complaints"],
                 "load": round(100 * e["busy_min"] / day), "queue": len(e["q"])} for e in self.emps.values()]
        return {"company": self.cfg["name"], "date": datetime.now().strftime("%Y-%m-%d"), "mode": self.erp.mode,
                "deals": len(deals), "closed": len(closed), "stuck": sum(1 for d in deals if d["state"] == "متعطلة"),
                "open": sum(1 for d in deals if d["state"] == "شغالة"), "sales": sum(d["amount"] for d in deals if d.get("invoiced")),
                "avg_cycle": round(sum(d["cycle_min"] for d in closed) / len(closed)) if closed else None,
                "complaints": len(self.complaints), "top": top[:40], "by_source": by_source,
                "round": [{"screen": d["item"], "who": self.emps[d["sales"]]["name"] if d["sales"] in self.emps else "", **{a: (d.get("res") or {}).get(a, "—")
                           for a in ("add", "edit", "print", "delete")}} for d in rounds],
                "erp_problems": by_source[0]["n"], "speed": speed[:10], "employees": emps, "ready": getattr(self, "ready", None), "new_screens": getattr(self, "new_screens", []),
                "day_type": self.cfg.get("day_type", "normal"),
                "tickets": [c for c in self.complaints if c["source"] == "erp"],
                "frustration": self._frustration(), "burst": self._burst_summary(), "guards": list(self.guards),
                "most_blocked": max(emps, key=lambda x: (x["failed"], x["complaints"]))["name"] if emps else "",
                "stuck_deals": [{"id": d["id"], "customer": d["customer"], "where": (d["steps"][-1]["text"] if d["steps"] else "")} for d in deals if d["state"] == "متعطلة"]}

    # ------------------------------------------------------------------ the clock
    def control(self, action, value=None):
        with self.lock:
            if action == "start":
                if self.running:
                    return
                self.cfg = self._load_cfg()
                self._load_texts()
                try:
                    if hasattr(self.erp, "close"):
                        self.erp.close()
                    self.erp = self.make_erp()
                except Exception as ex:
                    self.erp = SimERP(rng=self.rng)
                    self._emit("log", {"emp": "", "clock": _hm(self.now), "text": f"⚠️ مقدرتش أوصل لـ NQ ERP — كملت محاكاة: {ex}", "ok": False})
                self.reset()
                self.running = True
                self.plan_day()
                self._emit("started", {})
                if not self.thread or not self.thread.is_alive():
                    self.thread = threading.Thread(target=self._loop, daemon=True)
                    self.thread.start()
            elif action == "pause":
                self.paused = True
            elif action == "resume":
                self.paused = False
            elif action == "speed" and value:
                self.speed = max(0.5, min(30.0, float(value)))
            elif action == "reset":
                self.reset()
            self._emit("control", {"running": self.running, "paused": self.paused, "speed": self.speed})

    def _loop(self):
        last = time.time()
        while True:
            time.sleep(0.05)
            t = time.time()
            dt, last = t - last, t
            with self.lock:
                if not self.running or self.paused:
                    continue
                prev = self.now
                wait = self.erp.pending() if hasattr(self.erp, "pending") else 0
                # real NQ ERP: a save takes the browser a minute or two, so the clock waits for it (≈ 15 virtual minutes per real
                # minute while a document is being made, almost stopped when work piles up) — the day lasts as long as the work
                sp = self.speed if not wait else min(self.speed, 0.25 if wait <= 2 else 0.05)
                self.now += dt * sp
                while self.queue and self.queue[0][0] <= self.now:
                    _, _, fn, args = heapq.heappop(self.queue)
                    try:
                        fn(*args)
                    except Exception as ex:                       # a bug in one rule must not stop the company
                        self._emit("log", {"emp": "", "clock": _hm(self.now), "text": f"⚠️ {type(ex).__name__}: {ex}", "ok": False})
                    if not self.running:
                        break
                if int(prev) != int(self.now):
                    self._emit("clock", {"clock": _hm(self.now), "now": self.now, "wait": wait})
                elif wait != getattr(self, "_last_wait", 0):
                    self._emit("clock", {"clock": _hm(self.now), "now": self.now, "wait": wait})
                self._last_wait = wait

    def run_fast(self):
        """the whole day with no waiting (tests / a quick report)"""
        with self.lock:
            self.reset()
            self.running = True
            self.plan_day()
            while self.queue and self.running:
                vt, _, fn, args = heapq.heappop(self.queue)
                self.now = max(self.now, vt)
                fn(*args)
            return self.report
