"""
🔁 Compare two environments (idea: Opkey «environment drift detection» / selective config comparison)

Two system-health checks side by side — usually our test site vs a client's live system (read only on both) — to see
how the client differs before an update or when something works here and not there:
  screens only on one side · screens broken on one side only · add forms with different fields / required fields ·
  speed of the same screen on both
"""
import json

from config import paths


def _load(name):
    f = paths.STATE_DIR / name
    if not f.name.startswith("health_") or f.parent != paths.STATE_DIR or not f.exists():
        raise ValueError("ملف فحص مش موجود")
    return json.loads(f.read_text(encoding="utf-8"))


def states():
    out = []
    for f in sorted(paths.STATE_DIR.glob("health_*.json"), key=lambda f: -f.stat().st_mtime):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append({"file": f.name, "site": d.get("base_url"), "at": d.get("at"), "total": d.get("total"),
                        "activity": d.get("activity"), "branch": d.get("branch")})
        except Exception:
            pass
    return out


def compare(a_file, b_file):
    A, B = _load(a_file), _load(b_file)
    na, nb = A.get("names") or {}, B.get("names") or {}
    pa, pb = set(A.get("paths") or na), set(B.get("paths") or nb)
    ba, bb = set(A.get("broken") or {}), set(B.get("broken") or {})
    ta, tb = A.get("times") or {}, B.get("times") or {}
    name = lambda p: na.get(p) or nb.get(p) or p
    common = pa & pb
    speed = []
    for p in common:
        x, y = ta.get(p) or 0, tb.get(p) or 0
        if x and y and max(x, y) >= 1500 and max(x, y) >= 2 * min(x, y):
            speed.append({"path": p, "name": name(p), "a": round(x / 1000, 2), "b": round(y / 1000, 2)})
    speed.sort(key=lambda r: -abs(r["a"] - r["b"]))
    forms = []
    fa, fb = A.get("forms") or {}, B.get("forms") or {}
    for p in sorted(set(fa) & set(fb)):
        x, y = fa[p].get("f") or {}, fb[p].get("f") or {}
        if not x or not y:
            continue
        lab = lambda d, k: (d.get(k) or {}).get("l") or k
        only_a = [lab(x, k) for k in x if k not in y]
        only_b = [lab(y, k) for k in y if k not in x]
        req_a = [lab(x, k) for k in x if k in y and x[k].get("r") and not y[k].get("r")]
        req_b = [lab(y, k) for k in y if k in x and y[k].get("r") and not x[k].get("r")]
        if only_a or only_b or req_a or req_b:
            forms.append({"path": p, "name": name(p), "only_a": only_a, "only_b": only_b, "req_a": req_a, "req_b": req_b})
    return {
        "a": {"site": A.get("base_url"), "at": A.get("at"), "total": len(pa), "broken": len(ba)},
        "b": {"site": B.get("base_url"), "at": B.get("at"), "total": len(pb), "broken": len(bb)},
        "only_a": sorted(({"path": p, "name": name(p)} for p in pa - pb), key=lambda r: r["name"]),
        "only_b": sorted(({"path": p, "name": name(p)} for p in pb - pa), key=lambda r: r["name"]),
        "broken_a": sorted(({"path": p, "name": name(p), "why": (A["broken"][p] or {}).get("why", "")} for p in (ba - bb) & common), key=lambda r: r["name"]),
        "broken_b": sorted(({"path": p, "name": name(p), "why": (B["broken"][p] or {}).get("why", "")} for p in (bb - ba) & common), key=lambda r: r["name"]),
        "forms": forms, "speed": speed[:40], "common": len(common),
    }
