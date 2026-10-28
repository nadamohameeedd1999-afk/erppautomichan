"""
Alerts (التنبيهات) after every run: email / Slack (their own Settings tabs) + WhatsApp, Telegram and a webhook
(Settings → 📱 واتساب وتليجرام), saved in data/settings/alerts.json:

  notify_on       "change" (recommended: a test turns from passing to failing or back) | "failure" | "always"
  dashboard_url   link put in the message (the report of the run)
  telegram_token  bot token from @BotFather · telegram_chats: chat ids (person / group), comma separated
  telegram_photo  send the failure screenshot with the message
  whatsapp_mode   "callmebot" (free, for one or a few phones) | "cloud" (WhatsApp Business Cloud API)
  callmebot       lines "phone|apikey"
  wa_token / wa_phone_id / wa_to   Cloud API
  webhook_url     any service that takes JSON {"text": "..."} (Teams, a WhatsApp gateway, n8n …)
"""
import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request

from config import paths
from config.storage import load_json, save_json

ALERTS_FILE = paths.settings_file("alerts.json")
SECRET_KEYS = ("telegram_token", "wa_token")


def load_config():
    c = load_json(ALERTS_FILE, {}) or {}
    c.setdefault("notify_on", "change")
    c.setdefault("dashboard_url", os.getenv("PUBLIC_URL") or (("https://" + os.getenv("RAILWAY_PUBLIC_DOMAIN")) if os.getenv("RAILWAY_PUBLIC_DOMAIN") else ""))
    return c


def save_config(new):
    cur = load_config()
    for k, v in new.items():
        if k in SECRET_KEYS and (not v or str(v).startswith("•")):
            continue                                   # «•••• متسجل» -> keep the saved secret
        cur[k] = v
    save_json(ALERTS_FILE, cur)
    return cur


def public_config():
    c = dict(load_config())
    for k in SECRET_KEYS:
        c[k] = "•••• متسجل" if c.get(k) else ""
    return c


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


def _text(summary, passed, changed, link=""):
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
    out = head + (f"\n{msg}" if msg and not passed else "") + hint + f"\n⏱️ {int(summary.get('duration_seconds', 0))} ثانية"
    if link:
        out += f"\n🔗 {link}"
    return out


def _post_json(url, data, headers=None, timeout=15):
    req = urllib.request.Request(url, data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _webhook(url, text):
    try:
        _post_json(url, {"text": text}, timeout=10)
        return True
    except Exception as e:
        print(f"[alerts] webhook error: {e}", flush=True)
        return False


def _ids(v):
    return [x.strip() for x in str(v or "").replace("،", ",").replace("\n", ",").split(",") if x.strip()]


# ---------------------------------------------------------------- channels (raise on error -> the test button shows it)
def send_telegram(cfg, text, photo=None):
    token, chats = (cfg.get("telegram_token") or "").strip(), _ids(cfg.get("telegram_chats"))
    if not token or not chats:
        raise RuntimeError("اكتبي توكن البوت ورقم الشات")
    base = f"https://api.telegram.org/bot{token}"
    for chat in chats:
        try:
            if photo and os.path.exists(photo) and cfg.get("telegram_photo", True):
                import requests
                with open(photo, "rb") as f:
                    r = requests.post(base + "/sendPhoto", data={"chat_id": chat, "caption": text[:1000]},
                                      files={"photo": f}, timeout=30)
                if not r.ok:
                    raise RuntimeError(r.json().get("description") or r.text[:200])
            else:
                _post_json(base + "/sendMessage", {"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True})
        except urllib.error.HTTPError as e:
            try:
                d = json.loads(e.read().decode()).get("description", "")
            except Exception:
                d = str(e)
            if e.code == 401:
                raise RuntimeError("توكن البوت غلط — خديه تاني من @BotFather") from None
            if "chat not found" in d.lower():
                raise RuntimeError(f"الشات {chat} مش لاقيه — ابعتي أي رسالة للبوت الأول (أو ضيفيه للجروب) وبعدين جربي") from None
            raise RuntimeError(f"تليجرام رفض: {d}") from None
    return len(chats)


def send_whatsapp(cfg, text):
    mode = cfg.get("whatsapp_mode") or "callmebot"
    if mode == "cloud":
        token, pid, to = (cfg.get("wa_token") or "").strip(), (cfg.get("wa_phone_id") or "").strip(), _ids(cfg.get("wa_to"))
        if not (token and pid and to):
            raise RuntimeError("اكتبي التوكن ورقم الـ Phone number ID والأرقام اللي هتستلم")
        for num in to:
            try:
                _post_json(f"https://graph.facebook.com/v19.0/{pid}/messages",
                           {"messaging_product": "whatsapp", "to": num.lstrip("+"), "type": "text", "text": {"body": text[:4000]}},
                           headers={"Authorization": f"Bearer {token}"})
            except urllib.error.HTTPError as e:
                try:
                    d = (json.loads(e.read().decode()).get("error") or {}).get("message", "")
                except Exception:
                    d = str(e)
                raise RuntimeError(f"واتساب (Cloud API) رفض: {d}") from None
        return len(to)
    lines = [l.strip() for l in str(cfg.get("callmebot") or "").splitlines() if "|" in l]
    if not lines:
        raise RuntimeError("اكتبي الرقم والـ apikey بالشكل ده: 201001234567|123456")
    for l in lines:
        phone, key = [x.strip() for x in l.split("|", 1)]
        url = "https://api.callmebot.com/whatsapp.php?" + urllib.parse.urlencode({"phone": phone, "text": text[:1500], "apikey": key})
        with urllib.request.urlopen(url, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
        if "error" in body.lower() or "apikey" in body.lower() and "invalid" in body.lower():
            raise RuntimeError(f"CallMeBot رفض ({phone}): {body[:160]}")
    return len(lines)


def _fail_shot(summary):
    try:
        from web import data_helper
        shots = data_helper.get_screenshots_for_run(summary.get("run_id", ""), summary)
        f = next((s for s in reversed(shots) if "FAILED" in s or "failed" in s), shots[-1] if shots else None)
        return str(paths.SCREENSHOTS_DIR / f) if f else None
    except Exception:
        return None


def _wanted(mode, passed, changed):
    return mode == "always" or (mode == "change" and changed) or (mode == "failure" and not passed)


def on_run_finished(summary):
    """Called by the queue after every run (in a thread)."""
    if summary.get("auto_retry"):            # wait for the automatic retry's result
        return
    from web import insights
    passed = insights.run_passed(summary)
    prev = _previous(summary)
    changed = prev is not None and prev != passed or (prev is None and not passed)
    cfg = load_config()
    link = (cfg.get("dashboard_url") or "").rstrip("/")
    link = f"{link}/reports/{summary.get('run_id')}" if link else ""
    text = _text(summary, passed, changed, link)
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
    if not _wanted(cfg.get("notify_on", "change"), passed, changed):
        return
    if cfg.get("telegram_on") and cfg.get("telegram_token"):
        try:
            send_telegram(cfg, text, None if passed else _fail_shot(summary))
        except Exception as e:
            print(f"[alerts] telegram: {e}", flush=True)
    if cfg.get("whatsapp_on"):
        try:
            send_whatsapp(cfg, text)
        except Exception as e:
            print(f"[alerts] whatsapp: {e}", flush=True)
    url = cfg.get("webhook_url") or os.getenv("ALERT_WEBHOOK", "")
    if url:
        _webhook(url, text)
    if changed:
        print(f"[alerts] {text.splitlines()[0]}", flush=True)


def send_test(channel, cfg=None):
    cfg = {**load_config(), **(cfg or {})}
    for k in SECRET_KEYS:                      # the form shows «•••• متسجل» for a saved secret
        if str(cfg.get(k) or "").startswith("•"):
            cfg[k] = load_config().get(k, "")
    text = "🧪 رسالة تجربة من أتمتة اختبارات ERP — لو وصلتك يبقى التنبيهات شغالة ✅"
    try:
        return _send_test(channel, cfg, text)
    except urllib.error.HTTPError:
        raise
    except (urllib.error.URLError, OSError) as e:
        why = getattr(e, "reason", e)
        raise RuntimeError(f"مقدرتش أوصل للخدمة من السيرفر (النت / البروكسي / الفايروول): {why}") from None


def _send_test(channel, cfg, text):
    if channel == "telegram":
        return send_telegram(cfg, text)
    if channel == "whatsapp":
        return send_whatsapp(cfg, text)
    if channel == "webhook":
        if not cfg.get("webhook_url"):
            raise RuntimeError("اكتبي رابط الـ webhook")
        _post_json(cfg["webhook_url"], {"text": text}, timeout=10)
        return 1
    raise RuntimeError("قناة مش معروفة")


def notify_async(summary):
    threading.Thread(target=on_run_finished, args=(summary,), daemon=True).start()
