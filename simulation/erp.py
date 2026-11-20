"""
The ERP the employees work on. Today: SimERP — the behaviour of NQ ERP's screens from data/erp_sim.json (time per
screen, how fast the system answers, what can go wrong and how often, who has permission).

Next step: RealERP — the same `perform()` done on the real test site through the testing tool's engine
(it will return the real time, the real error message, the real number of steps), so the complaints become real
findings. Keep the same return shape: {kind: ok|slow|error|reject|wrong, ms, msg, steps}.
"""
import json
from pathlib import Path

DATA = Path(__file__).parent / "data"


class SimERP:
    mode = "محاكاة"

    def __init__(self, rng):
        self.rng = rng
        self.cfg = json.loads((DATA / "erp_sim.json").read_text(encoding="utf-8"))
        self.screens = self.cfg["screens"]
        self.slow_ms = int(self.cfg.get("slow_ms", 8000))
        self.stock_short_p = float(self.cfg.get("stock_short_p", 0.3))

    def screen(self, key):
        return self.screens[key]

    def action(self, name):
        return (self.cfg.get("actions") or {}).get(name)

    def perform(self, key, emp, task):
        s = self.screens[key]
        if task.get("_sticky"):                                        # a validation refusal comes back the same on a retry (same data)
            return dict(task["_sticky"])
        ms = int(s["ms"] * self.rng.uniform(0.6, 1.5))
        act = self.action(task.get("action") or "")
        issues = (act.get("issues") or []) + ([i for i in s.get("issues") or [] if i["type"] == "slow"] if task.get("action") != "review" else s.get("issues") or []) \
            if act else s.get("issues") or []
        for it in issues:
            p = it["p"] * (1.4 - emp.get("experience", 0.7) * 0.6 if it["type"] in ("reject", "wrong") else 1)
            if self.rng.random() < p:
                r = {"kind": it["type"], "ms": it.get("ms", ms), "msg": it.get("msg", ""), "steps": s["steps"]}
                if it["type"] == "reject":
                    task["_sticky"] = r
                return r
        if self.rng.random() > emp.get("accuracy", 0.95):            # the employee's own mistake: the system refuses it
            return {"kind": "mistake", "ms": ms, "msg": "نسي حقل إجباري", "steps": s["steps"]}
        return {"kind": "ok", "ms": ms, "msg": "", "steps": s["steps"]}
