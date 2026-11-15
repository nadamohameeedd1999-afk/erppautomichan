"""
🎯 أثر التغيير — what changed in the ERP code between two versions, and which screens / reports / procedures it touches,
so a release is tested where it changed instead of everywhere (the idea of Tricentis LiveCompare / Panaya).

Two ways to get «what changed»:
  • GitHub compare  — owner/repo + two branches / tags / commits (a read-only token kept encrypted in the settings)
  • two code ZIPs   — the old and the new copy; only code files are read (cs, cshtml, js, sql, config, resx)

Then every changed file is tied to the screens through the 🧬 digital twin's screen map (its last analysis):
  Controllers/XController*.cs, Views/X/…          → screen X
  Reporting/Reports/R*.cs, *.repx                   → report R (/Report/R)
  *.sql (CREATE / ALTER PROCEDURE p) and the procedure names in changed lines → every screen that calls p
  Models / Entities / X.cs                          → every screen that uses table X
  _Layout, BaseController, Global.asax, Web.config, shared scripts → «affects every screen»
Each screen gets a risk score (how many changes, how deep: a procedure > a controller > a view > a script) and the
tests to run: the automatic test of that screen, its reports, and the quick health check.
"""
import difflib
import hashlib
import io
import json
import re
import zipfile
from datetime import datetime

CODE_EXT = (".cs", ".cshtml", ".js", ".sql", ".config", ".resx", ".repx", ".vbhtml", ".aspx", ".ascx", ".json")
SKIP_DIR = re.compile(r"(^|/)(bin|obj|packages|node_modules|\.git|\.vs|Content/(?:fonts|images)|Scripts/(?:lib|vendor|kendo|devexpress|jquery[^/]*))(/|$)", re.I)
GLOBAL = re.compile(r"(^|/)(_Layout[^/]*\.cshtml|_ViewStart\.cshtml|BaseController\.cs|Global\.asax(\.cs)?|Web\.config|Startup\.cs|"
                    r"BundleConfig\.cs|RouteConfig\.cs|FilterConfig\.cs|site\.js|common\.js|main\.js|app\.js|_Menu[^/]*\.cshtml)$", re.I)
PROC_DEF = re.compile(r"(?:CREATE|ALTER)\s+(?:OR\s+ALTER\s+)?PROC(?:EDURE)?\s+(?:\[?dbo\]?\.)?\[?(\w+)\]?", re.I)
WEIGHT = {"proc": 5, "controller": 4, "report": 3, "model": 3, "view": 2, "script": 1, "global": 2}
KIND_AR = {"proc": "إجراء مخزن", "controller": "كنترولر", "report": "تقرير", "model": "جدول / موديل", "view": "شاشة (View)",
           "script": "جافاسكريبت", "global": "ملف عام", "other": "ملف"}


# ------------------------------------------------------------------ settings (GitHub)
def _cfg_file():
    from config import paths
    return paths.SETTINGS_DIR / "impact.json"


def load_cfg():
    try:
        d = json.loads(_cfg_file().read_text(encoding="utf-8"))
    except Exception:
        d = {}
    return d


def public_cfg():
    d = load_cfg()
    return {"repo": d.get("repo", ""), "base": d.get("base", ""), "head": d.get("head", ""), "has_token": bool(d.get("token"))}


def save_cfg(j):
    from utils.secret_box import encrypt
    d = load_cfg()
    for k in ("repo", "base", "head"):
        if k in j:
            d[k] = str(j[k] or "").strip()
    if j.get("token"):
        d["token"] = encrypt(str(j["token"]).strip())
    if j.get("clear_token"):
        d.pop("token", None)
    _cfg_file().parent.mkdir(parents=True, exist_ok=True)
    _cfg_file().write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return public_cfg()


def _state():
    from config import paths
    return paths.STATE_DIR / "impact.json"


def load():
    try:
        return json.loads(_state().read_text(encoding="utf-8"))
    except Exception:
        return None


def save(d):
    _state().parent.mkdir(parents=True, exist_ok=True)
    _state().write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------ getting the changed files
def from_github(repo, base, head, token=""):
    """[{path, status, add, del, lines: [changed lines]}] from the GitHub compare API"""
    import requests
    from utils.secret_box import decrypt
    tok = decrypt(token) if token else ""
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    out, page = [], 1
    while page <= 10:
        r = requests.get(f"https://api.github.com/repos/{repo}/compare/{base}...{head}", headers=h, params={"per_page": 300, "page": page}, timeout=60)
        if r.status_code == 404:
            raise RuntimeError("الريبو أو الفرع مش موجود — أو الريبو خاص ومحتاج توكن")
        if r.status_code in (401, 403):
            raise RuntimeError(f"GitHub رفض ({r.status_code}) — التوكن مش صح أو مالوش صلاحية قراءة على الريبو")
        r.raise_for_status()
        j = r.json()
        files = j.get("files") or []
        for f in files:
            patch = f.get("patch") or ""
            lines = [l[1:] for l in patch.splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---"))]
            out.append({"path": f["filename"], "status": {"added": "جديد", "removed": "اتشال", "renamed": "اتغير اسمه"}.get(f.get("status"), "اتعدل"),
                        "add": f.get("additions", 0), "del": f.get("deletions", 0), "lines": lines[:400]})
        if len(files) < 300:
            break
        page += 1
    return out, {"commits": len(j.get("commits") or []), "ahead": j.get("ahead_by"), "behind": j.get("behind_by")}


def _code_files(zf):
    out = {}
    names = zf.namelist()
    # the common top folder (MyERP-main/…) is dropped so both copies line up
    tops = {n.split("/")[0] for n in names if "/" in n}
    strip = (tops.pop() + "/") if len(tops) == 1 else ""
    for n in names:
        if n.endswith("/") or not n.lower().endswith(CODE_EXT):
            continue
        p = n[len(strip):] if strip and n.startswith(strip) else n
        if SKIP_DIR.search(p) or re.search(r"\.min\.js$", p, re.I):
            continue
        try:
            out[p] = zf.read(n)
        except Exception:
            pass
    return out


def from_zips(old_bytes, new_bytes):
    A = _code_files(zipfile.ZipFile(io.BytesIO(old_bytes)))
    B = _code_files(zipfile.ZipFile(io.BytesIO(new_bytes)))
    out = []
    la = {p.lower(): p for p in A}
    for p, data in B.items():
        q = la.get(p.lower())
        if q is None:
            txt = data.decode("utf-8", "ignore").splitlines()
            out.append({"path": p, "status": "جديد", "add": len(txt), "del": 0, "lines": txt[:400]})
        elif hashlib.md5(A[q]).digest() != hashlib.md5(data).digest():
            a, b = A[q].decode("utf-8", "ignore").splitlines(), data.decode("utf-8", "ignore").splitlines()
            ch = [l for l in difflib.unified_diff(a, b, lineterm="", n=0) if l[:1] in "+-" and not l.startswith(("+++", "---"))]
            if not ch:
                continue
            out.append({"path": p, "status": "اتعدل", "add": sum(1 for l in ch if l[0] == "+"), "del": sum(1 for l in ch if l[0] == "-"),
                        "lines": [l[1:] for l in ch][:400]})
    lb = {p.lower() for p in B}
    for p, data in A.items():
        if p.lower() not in lb:
            out.append({"path": p, "status": "اتشال", "add": 0, "del": len(data.splitlines()), "lines": []})
    return out, {"files_old": len(A), "files_new": len(B)}


# ------------------------------------------------------------------ tying files to screens
def classify(path):
    """(kind, name) of a changed file"""
    p = path.replace("\\", "/")
    base = p.rsplit("/", 1)[-1]
    if GLOBAL.search(p):
        return "global", base
    m = re.search(r"(?:^|/)Controllers/(?:[^/]+/)*(\w+?)Controller(?:\.\w+)?\.cs$", p, re.I)
    if m:
        return "controller", m.group(1).lower()
    m = re.search(r"(?:^|/)Views/(\w+)/", p, re.I)
    if m and m.group(1).lower() != "shared":
        return "view", m.group(1).lower()
    m = re.search(r"(?:^|/)Report(?:ing|s)?/(?:[^/]+/)*(\w+?)(?:\.Designer)?\.(?:cs|repx)$", p, re.I)
    if m:
        return "report", m.group(1)
    if p.lower().endswith(".sql"):
        return "proc", base
    m = re.search(r"(?:^|/)(?:Models|Entities|Domain|DAL|Data)/(?:[^/]+/)*(\w+)\.cs$", p, re.I)
    if m:
        return "model", m.group(1)
    if p.lower().endswith(".js"):
        return "script", re.sub(r"\.js$", "", base, flags=re.I).lower()
    return "other", base


def analyse(files, twin, label="", meta=None):
    screens_map = (twin or {}).get("screens") or {}
    by_proc, by_table = {}, {}
    for k, s in screens_map.items():
        for pr in s.get("procs") or []:
            by_proc.setdefault(pr.lower(), set()).add(k)
        for t in s.get("tables") or []:
            by_table.setdefault(t.lower(), set()).add(k)
    known_procs = set(by_proc)
    hit, reports, procs_changed, glob, other = {}, {}, {}, [], []

    def touch(screen, kind, path, why):
        if screen not in screens_map:
            return False
        e = hit.setdefault(screen, {"key": screen, "name": screens_map[screen].get("name") or screen, "ar": screens_map[screen].get("ar") or "",
                                    "module": screens_map[screen].get("module") or "", "score": 0, "why": [], "files": set()})
        e["score"] += WEIGHT.get(kind, 1)
        if len(e["why"]) < 12:
            e["why"].append(f"{KIND_AR.get(kind, kind)}: {why}")
        e["files"].add(path)
        return True

    for f in files:
        kind, name = classify(f["path"])
        f["kind"], f["kind_ar"], f["screens"] = kind, KIND_AR.get(kind, kind), []
        body = "\n".join(f.get("lines") or [])
        if kind == "global":
            glob.append(f["path"])
            continue
        if kind in ("controller", "view"):
            if touch(name, kind, f["path"], f["path"].rsplit("/", 1)[-1]):
                f["screens"].append(name)
        elif kind == "report":
            reports.setdefault(name, {"name": name, "path": f"/Report/{name}", "files": []})["files"].append(f["path"])
        elif kind == "model":
            for s in by_table.get(name.lower(), ()):
                if touch(s, kind, f["path"], f"الجدول {name}"):
                    f["screens"].append(s)
        elif kind == "script":
            if name in screens_map and touch(name, kind, f["path"], f["path"].rsplit("/", 1)[-1]):
                f["screens"].append(name)
        # procedures: defined in a changed .sql, or named in any changed line
        names = {m.group(1).lower() for m in PROC_DEF.finditer(body)}
        if known_procs and body:
            for tok in set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", body)):
                if tok.lower() in known_procs:
                    names.add(tok.lower())
        for pr in names:
            procs_changed.setdefault(pr, set()).add(f["path"])
            for s in by_proc.get(pr, ()):
                if touch(s, "proc", f["path"], pr):
                    f["screens"].append(s)
        if not f["screens"] and kind not in ("report",):
            other.append(f["path"])
        f["screens"] = sorted(set(f["screens"]))[:30]
        f.pop("lines", None)
    rows = sorted(hit.values(), key=lambda e: -e["score"])
    for e in rows:
        e["files"] = sorted(e["files"])[:20]
        e["level"] = "عالي" if e["score"] >= 8 else ("متوسط" if e["score"] >= 4 else "منخفض")
    return {"at": datetime.now().strftime("%Y-%m-%d %H:%M"), "label": label, "meta": meta or {}, "files": files,
            "screens": rows, "reports": sorted(reports.values(), key=lambda r: r["name"]),
            "procs": [{"name": p, "files": sorted(v)[:5], "screens": sorted(by_proc.get(p, ()))[:30]} for p, v in sorted(procs_changed.items())],
            "global": glob, "unmapped": other[:300], "twin_at": (twin or {}).get("at"),
            "counts": {"files": len(files), "screens": len(rows), "reports": len(reports), "procs": len(procs_changed), "global": len(glob),
                       "high": sum(1 for e in rows if e["level"] == "عالي")}}


# ------------------------------------------------------------------ what to run
def tests_for(result):
    """the automatic tests (catalog screens) of the affected controllers"""
    try:
        from engine.auto_test import all_screens
        scr = all_screens()
    except Exception:
        scr = []

    def ctrl(u):
        seg = [x for x in re.sub(r"^https?://[^/]+", "", str(u or "")).split("?")[0].strip("/").split("/") if x]
        return seg[0].lower() if seg else ""
    by_ctrl = {}
    for s in scr:
        by_ctrl.setdefault(ctrl(s["url"]), []).append(s)
    out = []
    for e in result.get("screens") or []:
        for s in by_ctrl.get(e["key"], [])[:2]:
            out.append({"screen": s["key"], "name": s["name"], "controller": e["key"], "level": e["level"], "score": e["score"]})
    return out


def check_key(screen):
    k = re.sub(r"[^a-z0-9_]", "_", str(screen).lower()).strip("_")[:50] or "s"
    return f"impact_{k}_{hashlib.sha1(str(screen).encode()).hexdigest()[:4]}"
