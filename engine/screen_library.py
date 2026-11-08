"""
📚 Screen library sync (idea: Tricentis Tosca «modules» — the screen is described once, a change is fixed in one place)

Every saved screen definition (Test Builder) is compared with the add form as the site has it NOW (read by the last
system-health check, read only). For each screen you get what changed and one click updates the definition — every
test that uses the screen (scenarios, cycles, the automatic test) gets the fix at once:
  ⚠️ a field became required          -> marked required
  ➕ a new required field              -> added (lists: first option / test-data store, text: smart value)
  🔀 a field's id changed (same label) -> the definition takes the new id
  ➖ a field is gone                   -> made optional (kept, so nothing breaks if it comes back)
"""
import json

from config import paths

from engine import screen_config
from engine.text_match import normalize as N


def _live_forms():
    """{add path (lower, no query) -> fields} from every system-health state (newest wins)"""
    out = {}
    files = sorted(paths.STATE_DIR.glob("health_*.json"), key=lambda f: f.stat().st_mtime)
    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for p, x in (d.get("forms") or {}).items():
            if x.get("f") and x.get("add"):
                out[x["add"].split("?")[0].lower().rstrip("/")] = {"fields": x["f"], "at": d.get("at"), "site": d.get("base_url")}
    return out


def diff(cfg, live):
    """-> list of changes {kind, id, label, new_id?, field?, text}"""
    lf = live["fields"]
    have = {f["id"]: f for f in cfg.get("fields") or [] if not str(f.get("id", "")).startswith("css:")}
    by_label = {}
    for k, v in lf.items():
        if v.get("l"):
            by_label.setdefault(N(v["l"]), k)
    out = []
    for fid, f in have.items():
        if fid in lf:
            if lf[fid].get("r") and not f.get("required"):
                out.append({"kind": "required", "id": fid, "label": f.get("label") or fid, "text": f"⚠️ «{f.get('label') or fid}» بقى إجباري"})
            continue
        nid = by_label.get(N(f.get("label") or ""))
        if nid and nid not in have:
            out.append({"kind": "renamed", "id": fid, "new_id": nid, "label": f.get("label") or fid,
                        "text": f"🔀 «{f.get('label') or fid}» الـ id اتغير من {fid} إلى {nid}"})
        elif not f.get("optional"):
            out.append({"kind": "gone", "id": fid, "label": f.get("label") or fid, "text": f"➖ «{f.get('label') or fid}» مش موجود في الفورم دلوقتي"})
    renamed_to = {c["new_id"] for c in out if c["kind"] == "renamed"}
    for k, v in lf.items():
        if v.get("r") and k not in have and k not in renamed_to:
            t = v.get("t") or "text"
            kind = {"select": "select2", "checkbox": "checkbox", "date": "date", "textarea": "textarea"}.get(t, "text")
            strategy = {"select2": "first", "checkbox": "check", "date": "today"}.get(kind, "smart")
            out.append({"kind": "new", "id": k, "label": v.get("l") or k,
                        "field": {"id": k, "label": v.get("l") or k, "kind": kind, "strategy": strategy, "value": "", "required": True},
                        "text": f"➕ حقل إجباري جديد «{v.get('l') or k}» ({'قايمة' if kind == 'select2' else 'خانة'})"})
    return out


def report():
    live = _live_forms()
    rows = []
    for cfg in screen_config.list_all():
        if cfg.get("error") or not cfg.get("add_url"):
            continue
        lv = live.get(cfg["add_url"].split("?")[0].lower().rstrip("/"))
        if not lv:
            rows.append({"key": cfg["key"], "name": cfg.get("name_ar"), "status": "unknown",
                         "note": "الفورم ده ما اتقراش في فحص صحة النظام لسه — شغّلي فحص على الموقع"})
            continue
        ch = diff(cfg, lv)
        rows.append({"key": cfg["key"], "name": cfg.get("name_ar"), "status": "changed" if ch else "ok", "changes": ch,
                     "at": lv.get("at"), "site": lv.get("site")})
    rows.sort(key=lambda r: {"changed": 0, "unknown": 2}.get(r["status"], 1))
    return rows


def apply(key):
    """apply every change of one screen to its definition (old version kept in history)"""
    cfg = screen_config.load(key)
    lv = _live_forms().get((cfg.get("add_url") or "").split("?")[0].lower().rstrip("/"))
    if not lv:
        raise ValueError("الفورم ده ما اتقراش لسه")
    ch = diff(cfg, lv)
    for c in ch:
        for f in cfg["fields"]:
            if f.get("id") != c["id"]:
                continue
            if c["kind"] == "required":
                f["required"] = True
                f.pop("soft", None)
            elif c["kind"] == "renamed":
                f["id"] = c["new_id"]
                for g in cfg["fields"]:
                    if g.get("depends_on") == c["id"]:
                        g["depends_on"] = c["new_id"]
            elif c["kind"] == "gone":
                f["optional"] = True
                f["soft"] = True
        if c["kind"] == "new":
            cfg["fields"].append(c["field"])
    screen_config.save(cfg)
    return ch
