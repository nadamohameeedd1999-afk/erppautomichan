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
    from utils.secret_box import decrypt
    c = load_json(CONFIG_FILE, None)
    if c and c.get("sender_password"):
        c["sender_password"] = decrypt(c["sender_password"])
    if c and c.get("api_key"):
        c["api_key"] = decrypt(c["api_key"])
    return c


# 📮 Railway (Free / Hobby) blocks outbound SMTP (Errno 101 «Network is unreachable»). An email service over HTTPS
# works everywhere: Brevo (key «xkeysib-…», sends from your own Gmail after one confirm click — 300 a day free)
# or Resend (key «re_…», needs your own domain to send to anyone).
def _api_key(config):
    import os
    return (config.get("api_key") or os.getenv("BREVO_API_KEY") or os.getenv("RESEND_API_KEY") or "").strip()


def _deliver(config, recipients, subject, html, files=()):
    """send through the HTTPS API when a key is set, otherwise SMTP -> raises on failure"""
    import base64
    key = _api_key(config)
    sender = (config.get("sender_email") or "").strip()
    files = [Path(f) for f in files if f]
    if key:
        import requests
        att = [(f.name, base64.b64encode(f.read_bytes()).decode()) for f in files]
        if key.startswith("re_"):
            body = {"from": config.get("api_from") or f"ERP Tests <onboarding@resend.dev>", "to": recipients, "subject": subject,
                    "html": html, "reply_to": sender or None, "attachments": [{"filename": n, "content": c} for n, c in att]}
            r = requests.post("https://api.resend.com/emails", json=body, headers={"Authorization": f"Bearer {key}"}, timeout=30)
        else:
            body = {"sender": {"email": sender, "name": config.get("sender_name") or "ERP Tests"},
                    "to": [{"email": x} for x in recipients], "subject": subject, "htmlContent": html}
            if att:
                body["attachment"] = [{"name": n, "content": c} for n, c in att]
            r = requests.post("https://api.brevo.com/v3/smtp/email", json=body, headers={"api-key": key, "accept": "application/json"}, timeout=30)
        if r.status_code >= 300:
            raise RuntimeError(f"خدمة الإيميل ردت {r.status_code}: {r.text[:200]}")
        return
    from email.mime.application import MIMEApplication
    msg = MIMEMultipart()
    msg["From"], msg["To"], msg["Subject"] = sender, ", ".join(recipients), subject
    msg.attach(MIMEText(html, "html"))
    for f in files:
        part = MIMEApplication(f.read_bytes(), Name=f.name)
        part["Content-Disposition"] = f'attachment; filename="{f.name}"'
        msg.attach(part)
    try:
        with smtplib.SMTP(config["smtp_host"], int(config.get("smtp_port") or 587), timeout=20) as server:
            server.starttls()
            server.login(sender, config.get("sender_password", ""))
            server.send_message(msg)
    except OSError as e:
        if getattr(e, "errno", None) in (101, 110, 111, 113) or "unreachable" in str(e).lower() or "timed out" in str(e).lower():
            raise RuntimeError("السيرفر مش قادر يوصل لـ SMTP (Railway بيقفل SMTP في الخطة المجانية والـ Hobby) — "
                               "حطي مفتاح Brevo في «مفتاح خدمة الإيميل» وهيبعت من غير SMTP") from e
        raise


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

        if not (sender and recipients and (password or _api_key(config))):
            return False

        status_text = "✅ نجح" if is_success else "❌ فشل"
        status_color = "#10b981" if is_success else "#ef4444"
        subject = f"{status_text} - ERP Test: {test_name or 'اختبار'}"

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
        _deliver(config, recipients, subject, body)
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

    if not (sender and to_email and (_api_key(config) or (password and smtp_host))):
        return False, 'ناقص: إيميل المرسل + (مفتاح خدمة الإيميل أو SMTP وكلمة مرور التطبيق)'
    try:
        _deliver(config, [to_email], 'ERP Test - Email Test',
                 '<div dir="rtl" style="font-family:Tahoma,Arial"><h2>✅ الإيميل شغال</h2><p>من: ' + sender + '</p><p>'
                 + ('عن طريق خدمة الإيميل (HTTPS)' if _api_key(config) else 'عن طريق SMTP') + '</p></div>')
        return True, 'اتبعت لـ ' + to_email
    except smtplib.SMTPAuthenticationError:
        return False, 'جيميل رفض الدخول — حطي «كلمة مرور التطبيق» (16 حرف) مش الباسورد العادي'
    except Exception as e:
        return False, str(e)[:250]


def send_file(subject, text, file_path, to=None):
    """Email a file (the daily PDF report) to the recipients in Settings → Email (or to `to`)."""
    from email.mime.application import MIMEApplication
    from pathlib import Path
    config = load_config()
    if not config or not config.get("enabled"):
        return False
    try:
        sender, password, recipients = config["sender_email"], config.get("sender_password"), config["recipients"]
        if to:
            recipients = [x.strip() for x in (to if isinstance(to, list) else str(to).replace("،", ",").replace(";", ",").split(",")) if x.strip()]
        if not (sender and recipients and (password or _api_key(config))):
            return False
        _deliver(config, recipients, subject, f'<div dir="rtl" style="font-family:Tahoma,Arial">{text}</div>', [file_path])
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False
