"""
Slack notification service
"""
import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
from config import paths
CONFIG_FILE = paths.settings_file("slack_config.json")


def load_config():
    from config.storage import load_json
    return load_json(CONFIG_FILE, None)


def save_config(config):
    from config.storage import save_json
    save_json(CONFIG_FILE, config)


def send_test_notification(summary, test_name="", changed=False):
    config = load_config()
    if not config or not config.get("enabled"):
        return False

    webhook_url = config.get("webhook_url", "")
    if not webhook_url:
        return False

    notify_on = config.get("notify_on", "failure")
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0) + summary.get("errors", 0)
    total = summary.get("total", 0)
    duration = int(summary.get("duration_seconds", 0))
    is_success = failed == 0 and passed > 0

    should_send = (
        notify_on == "always" or
        (notify_on == "change" and changed) or
        (notify_on == "failure" and not is_success) or
        (notify_on == "success" and is_success)
    )
    if not should_send:
        return False

    try:
        from slack_sdk.webhook import WebhookClient

        color = "good" if is_success else "danger"
        emoji = "✅" if is_success else "❌"
        status = "نجح" if is_success else "فشل"

        client = WebhookClient(webhook_url)
        response = client.send(
            text=f"{emoji} ERP Test: {status}",
            attachments=[{
                "color": color,
                "title": f"{emoji} {test_name or 'اختبار'}",
                "fields": [
                    {"title": "الإجمالي", "value": str(total), "short": True},
                    {"title": "ناجح", "value": str(passed), "short": True},
                    {"title": "فاشل", "value": str(failed), "short": True},
                    {"title": "المدة", "value": f"{duration} ث", "short": True},
                ],
                "footer": "ERP Test Automation",
                "ts": int(datetime.now().timestamp()),
            }]
        )
        return response.status_code == 200
    except Exception as e:
        print(f"[Slack] Error: {e}")
        return False
