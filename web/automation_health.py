"""
📈 Automation health (idea: Worksoft «Automation Insights» dashboards)

From the history of every run: which tests fail the most, which are flaky (pass / fail / pass…), which got slower,
which haven't run for a while — so you know where the test suite itself needs attention.
"""
from collections import defaultdict
from datetime import datetime

from flask import Blueprint, render_template

from web import auth, data_helper, insights

bp = Blueprint("autohealth", __name__)


def compute(days=30):
    now = datetime.now()
    by = defaultdict(list)
    for s in data_helper.load_summaries():
        t = insights.run_time(s)
        if not t or (now - t).days > days:
            continue
        name = s.get("test_name") or s.get("test_path") or "—"
        by[(name, s.get("site_name") or "")].append((t, insights.run_passed(s), float(s.get("duration_seconds") or 0), s))
    tests = []
    for (name, site), runs in by.items():
        runs.sort(key=lambda r: r[0])
        oks = [r[1] for r in runs]
        last10 = oks[-10:]
        flips = sum(1 for a, b in zip(last10, last10[1:]) if a != b)
        durs = [r[2] for r in runs if r[2]]
        half = len(durs) // 2
        slower = (round(100 * (sum(durs[half:]) / max(1, len(durs[half:])) / max(0.1, sum(durs[:half]) / max(1, half)) - 100))
                  if half >= 2 else None)
        fails = len(oks) - sum(oks)
        last = runs[-1]
        tests.append({"name": name, "site": site, "runs": len(runs), "pass_pct": round(100 * sum(oks) / len(oks)),
                      "fails": fails, "flips": flips, "flaky": flips >= 3, "avg": round(sum(durs) / len(durs), 1) if durs else None,
                      "slower_pct": slower, "last_at": last[0].strftime("%Y-%m-%d %H:%M"), "last_ok": last[1],
                      "last_run": last[3].get("run_id"), "idle_days": (now - last[0]).days,
                      "streak": next((i for i, o in enumerate(reversed(oks)) if o), len(oks)),
                      "dots": last10})
    total_runs = sum(t["runs"] for t in tests)
    ok_runs = sum(round(t["runs"] * t["pass_pct"] / 100) for t in tests)
    return {
        "days": days, "tests": len(tests), "runs": total_runs,
        "pass_pct": round(100 * ok_runs / total_runs) if total_runs else None,
        "failing": sorted([t for t in tests if t["fails"]], key=lambda t: (-t["streak"], -t["fails"]))[:15],
        "flaky": sorted([t for t in tests if t["flaky"]], key=lambda t: -t["flips"])[:15],
        "slower": sorted([t for t in tests if (t["slower_pct"] or 0) >= 25], key=lambda t: -t["slower_pct"])[:15],
        "idle": sorted([t for t in tests if t["idle_days"] >= 7], key=lambda t: -t["idle_days"])[:15],
        "all": sorted(tests, key=lambda t: (t["pass_pct"], -t["runs"])),
    }


@bp.route("/automation-health")
@auth.login_required
def page():
    return render_template("automation_health.html", h=compute())
