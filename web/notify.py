"""
Alerts (التنبيهات) after every run.

Sent through email / Slack (Settings page) and an optional webhook (WhatsApp gateway, Teams, ...):
  - "change" mode (recommended): only when a test turns from passing to failing or back
  - failure / success / always: like before
The webhook URL is read from data/settings/alerts.json {"webhook_url": "...", "notify_on": "change"}
or the ALERT_WEBHOOK env var; it receives JSON {"text": "..."}.
"""
import json
import threading
import urllib.request

from config import paths
from config.storage import load_json

ALERTS_FILE = paths.settings_file("alerts.json")


def _previous(summary):
    """passed/failed of the previous run of the same test (and same site), or None"""
    from web import insights
    key = insights.test_key(summary.get("test_path", ""))
    site = summary.get("site") or ""
    for r in insights.all_runs():
        s = r["summary"]
        if r["run_id"] == summary.get("run_id") or s.get("retry_of") == summary.get("run_id"):
            continue
        if r["key"] == key and (s.get("site") or "") == site:
            return r["passed"]
    return None


def _text(summary, passed, changed):
    from web import insights
    name = summary.get("test_name") or summary.get("test_path", "")
    site = f" · {summary['site_name']}" if summary.get("site_name") else ""
    if changed and passed:
        head = f"✅ رجع يشتغل: {name}{site}"
    elif changed:
        head = f"🔴 بقى بيفشل: {name}{site}"
    else:
        head = f"{'✅ نجح' if passed else '❌ فشل'}: {name}{site}"
    msg = insights.first_failure_message(summary)
    hint = ""
    if not passed:
        try:
            from web import explain
            w = explain.explain(msg)
            if w:
                hint = f"\n{w['kind_label']}: {w['title']}\n💡 {w['fix']}"
        except Exception:
            pass
    return head + (f"\n{msg}" if msg and not passed else "") + hint + f"\n⏱️ {int(summary.get('duration_seconds', 0))} ثانية"


def _webhook(url, text):
    try:
        req = urllib.request.Request(url, data=json.dumps({"text": text}, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
        return True
    except Exception as e:
        print(f"[alerts] webhook error: {e}", flush=True)
        return False


def on_run_finished(summary):
    """Called by the queue after every run (in a thread)."""
    if summary.get("auto_retry"):            # wait for the automatic retry's result
        return
    from web import insights
    passed = insights.run_passed(summary)
    prev = _previous(summary)
    changed = prev is not None and prev != passed or (prev is None and not passed)
    text = _text(summary, passed, changed)
    name = summary.get("test_name") or ""
    try:
        from config import emailer
        emailer.send_test_notification(summary, name, changed=changed)
    except Exception as e:
        print(f"[alerts] email: {e}", flush=True)
    try:
        from config import slack_notifier
        slack_notifier.send_test_notification(summary, name, changed=changed)
    except Exception as e:
        print(f"[alerts] slack: {e}", flush=True)
    cfg = load_json(ALERTS_FILE, {}) or {}
    import os
    url = cfg.get("webhook_url") or os.getenv("ALERT_WEBHOOK", "")
    mode = cfg.get("notify_on", "change")
    if url and (mode == "always" or (mode == "change" and changed) or (mode == "failure" and not passed)):
        _webhook(url, text)
    if changed:
        print(f"[alerts] {text.splitlines()[0]}", flush=True)


def notify_async(summary):
    threading.Thread(target=on_run_finished, args=(summary,), daemon=True).start()
