"""
Data helper - reads test results, screenshots, schedules
"""
import json
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = BASE_DIR / "reports" / "results"
SCREENSHOTS_DIR = BASE_DIR / "reports" / "screenshots"
SCHEDULES_FILE = BASE_DIR / "config" / "schedules" / "schedules.json"


def load_summaries(limit=None):
    """Load all summary JSON files"""
    summaries = []
    if not RESULTS_DIR.exists():
        return summaries

    for f in sorted(RESULTS_DIR.glob("summary_*.json"), reverse=True):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                data["_file"] = f.name
                summaries.append(data)
        except Exception:
            pass

    if limit:
        return summaries[:limit]
    return summaries


def load_recent_runs(limit=10):
    """Load recent runs"""
    return load_summaries(limit=limit)


def get_stats():
    """Calculate overall stats"""
    summaries = load_summaries()
    if not summaries:
        return {
            "total_runs": 0,
            "total_passed": 0,
            "total_failed": 0,
            "success_rate": 0,
        }

    total_passed = sum(s.get("passed", 0) for s in summaries)
    total_failed = sum(s.get("failed", 0) + s.get("errors", 0) for s in summaries)
    total = total_passed + total_failed

    return {
        "total_runs": len(summaries),
        "total_passed": total_passed,
        "total_failed": total_failed,
        "success_rate": round((total_passed / total * 100) if total > 0 else 0, 1),
    }


def get_screenshots_for_run(run_id, report=None):
    """Get screenshots for a specific run (taken between its start and end when known)"""
    screenshots = []
    if not SCREENSHOTS_DIR.exists():
        return screenshots
    if report and report.get("started_at") and report.get("finished_at"):
        try:
            start = datetime.fromisoformat(report["started_at"]).timestamp() - 2
            end = datetime.fromisoformat(report["finished_at"]).timestamp() + 5
            for f in sorted(SCREENSHOTS_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime):
                if start <= f.stat().st_mtime <= end:
                    screenshots.append(f.name)
            return screenshots
        except Exception:
            screenshots = []

    for f in sorted(SCREENSHOTS_DIR.glob("*.png"), reverse=True):
        if run_id[:8] in f.name:
            screenshots.append(f.name)
    return screenshots


def get_all_screenshots():
    """Get all screenshots"""
    screenshots = []
    if not SCREENSHOTS_DIR.exists():
        return screenshots
    for f in sorted(SCREENSHOTS_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True):
        screenshots.append(f.name)
    return screenshots


def load_schedules():
    """Load schedules"""
    if not SCHEDULES_FILE.exists():
        return []
    try:
        with open(SCHEDULES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_schedules(schedules):
    SCHEDULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SCHEDULES_FILE, "w", encoding="utf-8") as f:
        json.dump(schedules, f, ensure_ascii=False, indent=2)


def get_tests_registry(lang="ar"):
    """Load tests registry - localized"""
    import sys
    sys.path.insert(0, str(BASE_DIR))
    try:
        from config.test_registry import TestRegistry
        return TestRegistry.get_all_localized(lang)
    except Exception as e:
        print(f"[data_helper] Error: {e}")
        return []

