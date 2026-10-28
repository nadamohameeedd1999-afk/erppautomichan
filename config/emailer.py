"""
Email notification service
"""
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
from config import paths
CONFIG_FILE = paths.settings_file("email_config.json")


def load_config():
    from config.storage import load_json
    return load_json(CONFIG_FILE, None)


def send_test_notification(summary, test_name="", changed=False):
    """
    Send email notification about a test run
    """
    config = load_config()
    if not config or not config.get("enabled"):
        return False

    # Check notify_on
    notify_on = config.get("notify_on", "failure")
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0) + summary.get("errors", 0)
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
        sender = config["sender_email"]
        password = config["sender_password"]
        recipients = config["recipients"]

        if not all([sender, password, recipients]):
            return False

        # Build email
        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)

        status_text = "✅ نجح" if is_success else "❌ فشل"
        status_color = "#10b981" if is_success else "#ef4444"
        msg["Subject"] = f"{status_text} - ERP Test: {test_name or 'اختبار'}"

        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #f8fafc; padding: 20px; border-radius: 10px;">
                <h2 style="color: {status_color}; margin: 0 0 20px 0;">
                    {status_text} — {test_name or 'اختبار'}
                </h2>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 8px; border-bottom: 1px solid #e2e8f0;"><strong>الاختبار:</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #e2e8f0;">{test_name}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #e2e8f0;"><strong>الإجمالي:</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #e2e8f0;">{summary.get('total', 0)}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #e2e8f0;"><strong>ناجح:</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; color: #10b981;">{passed}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #e2e8f0;"><strong>فاشل:</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #e2e8f0; color: #ef4444;">{failed}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #e2e8f0;"><strong>المدة:</strong></td>
                        <td style="padding: 8px; border-bottom: 1px solid #e2e8f0;">{int(summary.get('duration_seconds', 0))} ثانية</td></tr>
                    <tr><td style="padding: 8px;"><strong>التاريخ:</strong></td>
                        <td style="padding: 8px;">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
                </table>
            </div>
        </body>
        </html>
        """
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)

        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

def send_test_email(to_email):
    '''Send a simple test email to verify SMTP settings.'''
    config = load_config()
    if not config:
        return False, 'No email config found'

    sender = config.get('sender_email', '').strip()
    password = config.get('sender_password', '').strip()
    smtp_host = config.get('smtp_host', '').strip()
    smtp_port = int(config.get('smtp_port', 587))

    if not all([sender, password, smtp_host, to_email]):
        return False, 'Missing fields'

    try:
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = to_email
        msg['Subject'] = 'ERP Test - Email Test'

        body = '<h1>Email Test Success</h1><p>SMTP is working!</p><p>From: ' + sender + '</p>'
        msg.attach(MIMEText(body, 'html'))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)

        return True, 'Email sent to ' + to_email
    except smtplib.SMTPAuthenticationError:
        return False, 'Auth failed - check App Password'
    except Exception as e:
        return False, 'Error: ' + str(e)[:150]


def send_file(subject, text, file_path, to=None):
    """Email a file (the daily PDF report) to the recipients in Settings → Email (or to `to`)."""
    from email.mime.application import MIMEApplication
    from pathlib import Path
    config = load_config()
    if not config or not config.get("enabled"):
        return False
    try:
        sender, password, recipients = config["sender_email"], config["sender_password"], config["recipients"]
        if to:
            recipients = [x.strip() for x in (to if isinstance(to, list) else str(to).replace("،", ",").replace(";", ",").split(",")) if x.strip()]
        if not all([sender, password, recipients]):
            return False
        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        msg.attach(MIMEText(f'<div dir="rtl" style="font-family:Tahoma,Arial">{text}</div>', "html"))
        p = Path(file_path)
        part = MIMEApplication(p.read_bytes(), Name=p.name)
        part["Content-Disposition"] = f'attachment; filename="{p.name}"'
        msg.attach(part)
        with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as server:
            server.starttls()
            server.login(sender, password)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False
