"""
🏢 NQ Simulation inside the dashboard — the virtual company whose employees work on NQ ERP all day and report what broke.

  /simulation/…  the owner's company: behind the dashboard's login; NQ ERP sites + the manager's user come from the dashboard's
                 sites; real mode makes documents through this program's own engine
  /demo/…        the public page to show a client: the sample company in simulation only (never your sites, users or passwords),
                 its own history, no settings; DEMO_PASS = an optional access code the client types once

Both serve the same pages (simulation/web); the pages' paths are written for the root, so each response gets its prefix here.
"""
import base64
import hashlib
import json
import os
import random
import re
from datetime import datetime
from pathlib import Path

from flask import Blueprint, Response, jsonify, redirect, request, send_file, send_from_directory, session, url_for

from config import paths

WEB = Path(__file__).resolve().parent.parent / "simulation" / "web"
SIMDATA = WEB.parent / "data"
DEMO_BLOCKED = ("/settings", "/api/settings", "/shot/", "/evidence/", "/api/gate")
_PAGE_PATHS = re.compile(r"""(["'`(])/(api/|shot/|evidence/|training/|i18n\.js|report\b|tickets\b|tests\b|present\b|settings\b|compare\b)""")

VOICES = {"f": "ar-SA-ZariyahNeural", "m": "ar-SA-HamedNeural"}     # Saudi Arabic neural voices
# 🔊 every employee his own voice: a Gulf neural voice each + his own pitch and pace
VOICE_OF = {
    "manager": ("ar-SA-HamedNeural", "-8%", "-6Hz"), "sales2": ("ar-KW-FahedNeural", "+6%", "+2Hz"), "acc1": ("ar-AE-HamdanNeural", "-3%", "-2Hz"),
    "wh1": ("ar-BH-AliNeural", "+0%", "-10Hz"), "pur1": ("ar-QA-MoazNeural", "+4%", "+4Hz"),
    "sales1": ("ar-SA-ZariyahNeural", "+5%", "+4Hz"), "acc2": ("ar-KW-NouraNeural", "+0%", "+0Hz"), "cash1": ("ar-AE-FatimaNeural", "-2%", "-4Hz"),
    "hr1": ("ar-QA-AmalNeural", "+3%", "+6Hz"), "it1": ("ar-OM-AbdullahNeural", "+3%", "-2Hz"),
}
SPARE_M = ["ar-OM-AbdullahNeural", "ar-SA-HamedNeural", "ar-KW-FahedNeural", "ar-AE-HamdanNeural"]
SPARE_F = ["ar-OM-AyshaNeural", "ar-BH-LailaNeural", "ar-SA-ZariyahNeural", "ar-KW-NouraNeural"]


def voice_of(eid, female):
    if eid in VOICE_OF:
        return VOICE_OF[eid]
    h = sum(ord(c) * (i + 7) for i, c in enumerate(str(eid)))
    pool = SPARE_F if female else SPARE_M
    return pool[h % len(pool)], f"{(h % 11) - 5:+d}%", f"{(h % 13) - 6:+d}Hz"


def make(name, prefix, demo):
    """one company + its pages under <prefix>"""
    from simulation.engine import Company
    from simulation.settings import RUNS as REAL_RUNS
    runs = paths.DATA_DIR / "simulation_demo" if demo else REAL_RUNS
    company = Company(use_settings=not demo, runs=runs)
    menus_file = paths.settings_file("simulation_menus.json")
    demo_pass = os.getenv("DEMO_PASS", "").strip()
    bp = Blueprint(name, __name__, url_prefix=prefix)
    art_cache = {}

    @bp.before_request
    def guard():
        sub = request.path[len(prefix):] or "/"
        if demo:
            if demo_pass:
                a = request.authorization
                if not a or a.password != demo_pass:
                    return Response("NQ Simulation — اكتب كود الدخول (أي اسم مستخدم)", 401, {"WWW-Authenticate": 'Basic realm="NQ Simulation"'})
            if sub.startswith(DEMO_BLOCKED):
                return Response("مش متاح في نسخة العرض", 403)
            return None
        if "user_id" not in session:                            # the owner's company: the dashboard's login
            if sub.startswith("/api/"):
                return jsonify({"ok": False, "error": "سجّل دخول اللوحة الأول"}), 401
            return redirect(url_for("login", next=request.path))
        return None

    @bp.after_request
    def with_prefix(resp):
        """the pages call /api/…, /report … — under this prefix they must call <prefix>/api/…"""
        if resp.mimetype in ("text/html", "application/javascript") and not resp.direct_passthrough:
            body = resp.get_data(as_text=True)
            body = _PAGE_PATHS.sub(lambda m: f"{m.group(1)}{prefix}/{m.group(2)}", body).replace('href="/"', f'href="{prefix}/"')
            resp.set_data(body)
        return resp

    def page(fname, extra=""):
        html = (WEB / fname).read_text(encoding="utf-8")
        if demo:                                                 # the client's copy: no settings button
            extra += "<style>a[href$='/settings']{display:none!important}</style>"
        back = ("" if demo else "<a href='/' class='co' aria-label='لوحة الاختبارات' style='color:#fff;text-decoration:none;border:1px solid rgba(255,255,255,.35);"
                                  "border-radius:8px;padding:2px 10px;font-size:13px'>🏠 لوحة الاختبارات</a>")   # in the header: never over the office
        html = html.replace("<header>", "<header>" + back, 1)
        return Response(html.replace("</body>", extra + "</body>", 1), mimetype="text/html")

    def days(real_only=False):
        """the saved days, oldest first (a broken file is skipped, never a 500)"""
        out = []
        for f in sorted(runs.glob("day_*.json")) if runs.exists() else []:
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not real_only or d.get("mode") != "محاكاة":
                out.append(d)
        return out

    def menus():
        try:
            return json.loads(menus_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    @bp.route("/")
    def index():
        return page("index.html")

    @bp.route("/api/art")
    def art():
        """the drawings, in the office's look (🕌 Saudi majlis)"""
        from simulation.art.themes import THEMES, themed
        if not art_cache:
            from simulation.art import build_art
            art_cache.update(build_art(company.cfg))
        th = "majlis"
        out = dict(art_cache, themes=THEMES, theme=th)
        key = "floor_" + th
        if key not in art_cache:
            art_cache[key] = themed(art_cache["floor"], th)
        out["floor"] = art_cache[key]
        return jsonify({k: v for k, v in out.items() if not k.startswith("floor_")})

    @bp.route("/i18n.js")
    def i18n_js():
        return Response((WEB / "i18n.js").read_text(encoding="utf-8"), mimetype="application/javascript")

    @bp.route("/api/lang")
    def api_lang():
        """🌐 the display language chosen in the settings (ar | en)"""
        from simulation import settings as S
        try:
            lang = os.getenv("DEMO_LANG") or request.args.get("lang") if demo else S.load().get("lang", "ar")
        except Exception:
            lang = "ar"
        return jsonify({"lang": lang if lang in ("ar", "en") else "ar"})

    @bp.route("/settings")
    def settings_page():
        return page("settings.html")

    @bp.route("/api/settings", methods=["GET", "POST"])
    def api_settings():
        from simulation import settings as S
        from simulation.art.floor import ROLE_SLOTS, ROLES_AR, assign_desks
        from simulation.erp import SimERP
        from simulation.real import FIND, guess_map
        if request.method == "POST":
            if company.running:
                return jsonify({"ok": False, "error": "وقّف اليوم الأول (الشركة شغالة دلوقتي)"}), 409
            try:
                out = S.save(request.get_json(silent=True) or {})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)[:300]}), 400
            art_cache.clear()
            company.cfg = company._load_cfg()
            company.reset()
        else:
            out = S.public()
        desks, left = assign_desks([e for e in out["employees"] if e.get("active", True)])
        m = menus()
        union = {}
        for k, v in m.items():
            if k.split(":")[0] == out.get("active_site"):
                for x in v.get("menu", []):
                    union.setdefault(x["path"], x)
        names = SimERP(random.Random(0)).screens
        return jsonify({"ok": True, "settings": out, "no_desk": [e["name"] for e in left], "roles": ROLES_AR, "slots": {k: len(v) for k, v in ROLE_SLOTS.items()},
                        "logins": {k: {kk: vv for kk, vv in v.items() if kk != "menu"} for k, v in m.items()}, "engine_found": True,
                        "menu": sorted(union.values(), key=lambda x: (x.get("module") or "", x["name"])), "guess": guess_map(list(union.values())),
                        "screens": {k: names[k]["name"] for k in FIND if k in names}})

    @bp.route("/api/settings/test", methods=["POST"])
    def api_settings_test():
        """sign in with one employee's NQ ERP user on one site and read their menu (= their permissions)"""
        from simulation import settings as S
        from simulation.real import test_login
        j = request.get_json(silent=True) or {}
        st = S.load()
        site = next((x for x in st["sites"] if x["id"] == j.get("site")), None)
        if not site:
            return jsonify({"ok": False, "error": "اختار موقع من مواقع اللوحة الأول"}), 400
        user, pw = S.site_credentials(site["id"], j.get("id") or "")
        user, pw = (j.get("user") or user), (j.get("pw") or pw)
        if not user or not pw:
            return jsonify({"ok": False, "error": "اكتب اسم المستخدم وكلمة السر (أو سيبه فاضي للمدير يشتغل بمستخدم الموقع)"}), 400
        try:
            menu = test_login(site["url"], user, pw, visible=bool(st.get("show_browsers")))
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)[:300]})
        m = menus()
        m[f"{site['id']}:{j.get('id') or user}"] = {"user": user, "at": datetime.now().strftime("%Y-%m-%d %H:%M"), "n": len(menu), "menu": menu}
        menus_file.parent.mkdir(parents=True, exist_ok=True)
        menus_file.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
        return jsonify({"ok": True, "n": len(menu)})

    @bp.route("/api/settings/permissions/<key>")
    def api_permissions(key):
        return jsonify({"ok": True, **menus().get(key, {"menu": []})})

    @bp.route("/shot/<eid>.png")
    def shot(eid):
        f = runs / "shots" / (re.sub(r"[^a-z0-9_]", "", eid) + ".png")
        return send_file(f, max_age=0) if f.exists() else ("", 404)

    @bp.route("/api/state")
    def state():
        return jsonify(company.snapshot())

    @bp.route("/api/stream")
    def stream():
        last = int(request.args.get("since") or 0)

        def gen():
            nonlocal last
            yield "retry: 2000\n\n"
            while True:
                evs = company.events_since(last, timeout=15)
                if not evs:
                    yield ": ping\n\n"
                    continue
                for ev in evs:
                    last = ev["id"]
                    yield f"id: {ev['id']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
        return Response(gen(), mimetype="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @bp.route("/api/poll")
    def poll():
        """the same events as /api/stream, as short requests (waits up to 8 s for news) — for links through a tunnel/proxy"""
        last = int(request.args.get("since") or 0)
        evs = company.events_since(last, timeout=8)
        return jsonify({"events": evs[-400:], "eid": company.eid})

    @bp.route("/api/control", methods=["POST"])
    def control():
        j = request.get_json(silent=True) or {}
        if not (demo and j.get("action") in ("reset", "speed")):    # demo viewers share one day: one of them can't reset / speed it for the others
            company.control(j.get("action"), j.get("value"))
        return jsonify({"ok": True, "running": company.running, "paused": company.paused, "speed": company.speed})

    @bp.route("/report")
    def report():
        from simulation.report import report_html
        r = company.report or (days() or [None])[-1]
        return report_html(r) if r else ("لسه مفيش يوم خلص — ابدأ اليوم الأول", 404)

    @bp.route("/tickets")
    def tickets():
        """the system's own problems as tickets for the developers, with the refused pages' pictures"""
        from simulation.report import tickets_html
        r = company.report or (days() or [None])[-1]
        if not r:
            return "لسه مفيش يوم خلص — ابدأ اليوم الأول", 404
        ev = runs / "evidence"

        def uri(fname):
            f = ev / Path(fname).name
            return "data:image/png;base64," + base64.b64encode(f.read_bytes()).decode() if f.exists() else None
        return tickets_html(r, uri)

    @bp.route("/api/tts")
    def api_tts():
        """🔊 an employee's line as speech (edge-tts neural voices, cached per text); no edge-tts / no internet → the page uses the browser's voice"""
        text = re.sub(r"[«»—•✅❌⚠️🕵️🧾⚡🆕📅🎓👍☀️]", " ", request.args.get("text", ""))[:400].strip()
        if not text:
            return "", 204
        e = company.emps.get(request.args.get("emp", ""), {})
        female = (e.get("look") or {}).get("kind") == "hijab"
        from simulation.i18n import ARABIC, voice_en
        eid = e.get("id", request.args.get("emp", ""))
        voice, rate, pitch = voice_of(eid, female) if ARABIC.search(text) else voice_en(eid, female)
        folder = runs / "tts"
        f = folder / (hashlib.sha1(f"{voice}|{rate}|{pitch}|{text}".encode("utf-8")).hexdigest()[:20] + ".mp3")
        if not f.exists():
            if demo and folder.exists() and sum(1 for _ in folder.glob("*.mp3")) >= 3000:
                return "", 204                                   # the public demo: a full voice cache → the browser's voice (nobody fills the disk)
            try:
                import asyncio
                import edge_tts
                folder.mkdir(parents=True, exist_ok=True)
                try:
                    asyncio.run(edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(f)))
                except Exception:                                # that dialect's voice isn't offered: the Saudi one with this person's pitch
                    asyncio.run(edge_tts.Communicate(text, VOICES["f" if female else "m"], rate=rate, pitch=pitch).save(str(f)))
            except Exception as ex:
                return jsonify({"error": str(ex)[:200]}), 503
        return send_file(f, mimetype="audio/mpeg")

    @bp.route("/api/ask")
    def api_ask():
        return jsonify({"answer": company.ask(request.args.get("emp", ""), request.args.get("q", ""))})

    @bp.route("/training/<eid>")
    def training(eid):
        """🎓 training mode: one employee's day step by step"""
        from simulation.report import training_html
        with company.lock:
            e = company.emps.get(eid)
            if not e:
                return "الموظف مش موجود", 404
            docs = [x for d in company.deals.values() for x in (d.get("real") or {}).get("docs", []) if d.get("sales") == eid]
            data = {"company": company.cfg["name"], "date": datetime.now().strftime("%Y-%m-%d"), "mode": company.erp.mode,
                    "eid": eid, "name": e["name"], "job": e.get("job", ""), "log": list(e["log"]), "docs": docs}
        return training_html(data, has_shot=(runs / "shots" / f"{eid}.png").exists())

    @bp.route("/api/gate")
    def gate():
        """🚦 release gate for a new NQ ERP build: no NEW problem of the system itself and no control leak = pass (JSON for a deploy script)"""
        from simulation.sources import problem_key
        ds = days(real_only=True)
        if not ds:
            return jsonify({"pass": False, "why": "مفيش يوم حقيقي خلص"}), 404
        key = lambda g: problem_key(g.get("screen"), g.get("sample"))  # noqa: E731
        cur, prev = ds[-1], (ds[-2] if len(ds) > 1 else {})
        old = {key(g) for g in prev.get("top") or [] if g.get("source") == "erp"}
        new = [g for g in cur.get("top") or [] if g.get("source") == "erp" and key(g) not in old]
        leaks = [g for g in cur.get("guards") or [] if g.get("kind") == "wrong"]
        return jsonify({"pass": not new and not leaks, "date": cur.get("date"), "new": [{"screen": g["screen"], "sample": g["sample"]} for g in new],
                        "control_leaks": leaks, "open_regressions": (cur.get("regressions") or {}).get("open")})

    @bp.route("/evidence/<path:f>")
    def evidence_file(f):
        return send_from_directory(runs / "evidence", f)

    @bp.route("/api/regressions")
    def api_regressions():
        """🧬 the system's problems across days: new today · still open (how many days) · fixed"""
        from simulation.sources import problem_key
        try:
            mem = json.loads((runs / "regressions.json").read_text(encoding="utf-8"))
        except Exception:
            mem = {}
        today = datetime.now().strftime("%Y-%m-%d")
        rows = list(mem.values())
        live = {problem_key(c["screen"], c["text"]): c for c in company.complaints if c.get("source") == "erp"}
        new_live = [{"screen": c["screen"], "text": c["text"][:200], "first": today, "days": [today], "status": "open"} for k, c in live.items() if k not in mem]
        return jsonify({"today": today,
                        "new": [m for m in rows if m.get("first") == today and m.get("status") == "open"] + new_live,
                        "open": sorted([m for m in rows if m.get("status") == "open" and m.get("first") != today], key=lambda m: -len(m.get("days", []))),
                        "fixed": sorted([m for m in rows if m.get("status") == "fixed"], key=lambda m: m.get("fixed", ""), reverse=True)[:30]})

    @bp.route("/api/tests")
    def api_tests():
        """🧪 the test catalog: every kind of test of NQ ERP, what runs today and what's planned"""
        return jsonify(json.loads((SIMDATA / "test_catalog.json").read_text(encoding="utf-8")))

    @bp.route("/tests")
    def tests_page():
        return page("tests.html")

    @bp.route("/present")
    def present():
        """🖥️ the clean screen to show a client: what was tested today, in big numbers"""
        return page("present.html")

    @bp.route("/compare")
    def compare():
        """the last real day against the real day before it"""
        from simulation.report import compare_html
        ds = days(real_only=True)
        if not ds:
            return "لسه مفيش يوم حقيقي خلص — شغّل يوم على الموقع الأول", 404
        return compare_html(ds[-1], ds[-2] if len(ds) > 1 else None)

    bp.company = company
    return bp
