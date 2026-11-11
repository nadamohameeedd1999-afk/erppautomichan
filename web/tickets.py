"""
🎫 Support tickets on the company's main ERP (nq-ts.premiumasp.net → /Tickets/Create) for the problems on «دعم المطورين».
Logs in the same way the ERP login page does (GetLoginData → activity + branch → POST /Login/Index), reads the
anti-forgery token from /Tickets/Create and posts the ticket form (multipart). The password is kept encrypted
(settings/tickets.json); it is entered by the user in the dashboard, never written in code or logs.
"""
import json
import re
from datetime import datetime

from config import paths

DEFAULT_URL = "https://nq-ts.premiumasp.net"
PRIORITY = {"عالية": "2", "متوسطة": "1", "منخفضة": "0"}          # 0 منخفض · 1 متوسط · 2 مرتفع · 3 حرج
DIFFICULTY = {"عالية": "6", "متوسطة": "4", "منخفضة": "2"}


def _file():
    return paths.SETTINGS_DIR / "tickets.json"


def load(with_password=False):
    try:
        c = json.loads(_file().read_text(encoding="utf-8"))
    except Exception:
        c = {}
    c.setdefault("base_url", DEFAULT_URL)
    if with_password and c.get("password"):
        from utils.secret_box import decrypt
        c["password"] = decrypt(c["password"])
    return c


def public():
    c = load()
    return {"base_url": c.get("base_url"), "username": c.get("username", ""), "has_password": bool(c.get("password")),
            "critical_high": bool(c.get("critical_high"))}


def save(d):
    from utils.secret_box import encrypt
    c = load()
    if d.get("base_url") is not None:
        c["base_url"] = (str(d["base_url"]).strip().rstrip("/") or DEFAULT_URL)
    if d.get("username") is not None:
        c["username"] = str(d["username"]).strip()
    pw = d.get("password")
    if pw == "-":
        c.pop("password", None)
    elif pw:
        c["password"] = encrypt(str(pw))
    if "critical_high" in d:
        c["critical_high"] = bool(d["critical_high"])
    _file().parent.mkdir(parents=True, exist_ok=True)
    _file().write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf-8")
    return public()


class TicketError(Exception):
    pass


def _session(c):
    import requests
    if not (c.get("username") and c.get("password")):
        raise TicketError("اكتب يوزر وباسورد موقع التيكتات في «إعدادات التيكتات» الأول")
    base = c["base_url"].rstrip("/")
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (ERP test automation)"})
    try:
        info = s.get(f"{base}/LogIn/GetLoginData", params={"userName": c["username"]}, timeout=30).json()
    except Exception as e:
        raise TicketError(f"موقع التيكتات مش بيرد ({base}): {str(e)[:150]}")
    if not info.get("success"):
        raise TicketError(f"اليوزر «{c['username']}» مش موجود على موقع التيكتات")
    act, brn = str(info.get("activityId") or "1"), str(info.get("deptId") or "")
    try:
        br = s.get(f"{base}/LogIn/GetBranches", params={"acode": act, "ucode": c["username"]}, timeout=30).json()
        codes = [str(b.get("code")) for b in (br.get("data") or [])]
        if codes and brn not in codes:
            brn = codes[0]
    except Exception:
        pass
    r = s.post(f"{base}/Login/Index", data={"lang": "ar", "userName": c["username"], "password": c["password"], "act": act, "brn": brn,
                                            "returnUrl": "/Tickets/Create"}, timeout=45, allow_redirects=True)
    if "/login" in r.url.lower() and 'name="password"' in r.text:
        raise TicketError("تسجيل الدخول على موقع التيكتات فشل — راجع اليوزر والباسورد في «إعدادات التيكتات»")
    return s, base


def _token(html):
    m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"', html) or re.search(r'value="([^"]+)"[^>]*name="__RequestVerificationToken"', html)
    return m.group(1) if m else ""


def describe(it, run_link=""):
    lines = [f"المشكلة: {it.get('title', '')}", f"الشاشة: {it.get('screen') or '—'}", f"الموقع اللي اتلاحظت عليه: {it.get('site') or '—'}",
             f"الخطورة: {it.get('severity') or '—'} · اتكررت {it.get('count', 1)} مرة · آخر ظهور {it.get('last') or '—'}", "",
             "التفاصيل:", it.get("details") or "—", "", "خطوات التكرار:", it.get("steps") or "—", "", "الدليل:", it.get("evidence") or "—"]
    if it.get("doc"):
        lines.append(f"رقم المستند: {it['doc']}")
    if run_link:
        lines += ["", f"تقرير التشغيلة: {run_link}"]
    lines += ["", f"— اتعملت من أداة أتمتة اختبارات ERP ({it.get('source') or 'دعم المطورين'}) · {datetime.now():%Y-%m-%d %H:%M}"]
    return "\n".join(lines)


def page_url(it):
    ev = str(it.get("evidence") or "") + " " + str(it.get("steps") or "")
    m = re.search(r"(https?://\S+|/[A-Z][A-Za-z]+/[A-Za-z]+(?:/\d+)?(?:\?\S+)?)", ev)
    if m:
        u = m.group(1).rstrip("،.")
        if u.startswith("/") and it.get("site"):
            u = "https://" + str(it["site"]).strip("/") + u
        return u
    return ("https://" + str(it["site"]).strip("/")) if it.get("site") and "." in str(it.get("site")) else ""


def _controller(it, url):
    m = re.search(r"/([A-Z][A-Za-z]+)/(?:AddEdit|Index|Create|Edit|Details)", url or "")
    if m:
        return m.group(1)
    try:
        from engine.biz_cases import NAMES, PROFILES
        for code, name in NAMES.items():
            if name and name in str(it.get("screen") or "") and code in PROFILES:
                return PROFILES[code]["ctrl"]
    except Exception:
        pass
    return ""


def _system_page(s, base, ctrl):
    """the ERP screen in the ticket's «اسم الشاشة» list — only an exact controller match, never a guess"""
    if not ctrl:
        return ""
    try:
        res = s.get(f"{base}/Tickets/SearchSystemPages", params={"q": ctrl}, timeout=30).json().get("results") or []
        hit = next((r for r in res if str(r.get("code") or "").lower() == ctrl.lower()), None)
        return str(hit["id"]) if hit else ""
    except Exception:
        return ""


def create(it, run_link=""):
    """→ {"ok": True, "url": …, "id": …} or raises TicketError"""
    c = load(with_password=True)
    s, base = _session(c)
    form = s.get(f"{base}/Tickets/Create", timeout=45)
    tok = _token(form.text)
    if not tok or "/login" in form.url.lower():
        raise TicketError("مقدرتش أفتح شاشة إضافة تذكرة بعد الدخول (صلاحية اليوزر؟)")
    sev = it.get("severity") or "متوسطة"
    prio = "3" if (sev == "عالية" and c.get("critical_high")) else PRIORITY.get(sev, "1")
    purl = page_url(it)
    spid = _system_page(s, base, _controller(it, purl))
    title = f"[اختبار آلي] {it.get('screen') or ''} — {it.get('title') or ''}".replace(" —  —", " —").strip()[:250]
    fields = [("__RequestVerificationToken", tok), ("id", "0"), ("DeletedAttachmentIds", ""), ("Title", title),
              ("Description", describe(it, run_link)), ("IsNewScreen", "false"), ("CustomerId", ""), ("PageUrl", purl[:500]),
              ("SystemPageId", spid), ("Difficulty", DIFFICULTY.get(sev, "4")), ("Priority", prio)]
    r = s.post(f"{base}/Tickets/Create", files=[(k, (None, v)) for k, v in fields], timeout=60, allow_redirects=False)
    loc = r.headers.get("Location", "")
    if r.status_code in (301, 302, 303) and "create" not in loc.lower() and "login" not in loc.lower():
        m = re.search(r"/(\d+)(?:$|\?)", loc)
        return {"ok": True, "url": (base + loc) if loc.startswith("/") else (loc or f"{base}/Tickets"), "id": m.group(1) if m else "",
                "at": datetime.now().strftime("%Y-%m-%d %H:%M"), "title": title}
    errs = re.findall(r'class="[^"]*(?:field-validation-error|text-danger|validation-summary-errors)[^"]*"[^>]*>\s*(?:<[^>]+>)*\s*([^<]{3,200})', r.text or "")
    if r.status_code == 200 and not errs and "create" not in (r.url or "").lower():
        return {"ok": True, "url": f"{base}/Tickets", "id": "", "at": datetime.now().strftime("%Y-%m-%d %H:%M"), "title": title}
    raise TicketError("موقع التيكتات ماقبلش التذكرة: " + (" · ".join(e.strip() for e in errs[:4]) or f"HTTP {r.status_code}"))
