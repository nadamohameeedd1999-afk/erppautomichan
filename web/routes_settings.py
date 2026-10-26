"""Settings, users, e-mail, test sites, tunnel (الإعدادات والمستخدمين).
Routes keep their names (url_for('settings') still works): registered on the app by register(app)."""
import json
from pathlib import Path

from flask import (flash, jsonify, redirect, render_template, request, url_for, session)

from web import auth, settings_helper
from web.i18n_helper import get_current_lang
from web.config import Config

BASE_DIR = Path(__file__).resolve().parent.parent
_ROUTES = []


def route(rule, **opts):
    def deco(fn):
        _ROUTES.append((rule, fn, opts))
        return fn
    return deco


def register(app):
    for rule, fn, opts in _ROUTES:
        app.add_url_rule(rule, endpoint=fn.__name__, view_func=fn, **opts)

@route("/settings")
@auth.login_required
def settings():
    site_config = settings_helper.load_site_config()
    slack_config = _load_json(Config.SLACK_CONFIG)
    email_config = _load_json(Config.EMAIL_CONFIG)
    users = settings_helper.load_users()

    from web import test_sites_helper as _tsh

    test_sites_data = _tsh.load_all()
    return render_template(
        "settings.html",
        site_config=site_config,
        slack_config=slack_config,
        email_config=email_config,
        users=users,
        test_sites_data=test_sites_data,
        tunnel_config=__import__("web.tunnel_helper", fromlist=["load_config"]).load_config(),
        login_styles_list=LOGIN_STYLE_NAMES[get_current_lang()],
        ui_themes_list=UI_THEME_NAMES[get_current_lang()],
        login_style_saved=site_config.get("login_style") or "terminal",
        ui_theme_saved=site_config.get("ui_theme") or "glass",
    )


LOGIN_STYLE_NAMES = {
    "ar": [("network", "شبكة متصلة + كارت مقسوم", "خلفية تيل غامق بنقط متوصلة بتتشد للماوس"),
           ("aurora", "شفق ملوّن + إطار متحرك", "بقع ألوان بتمشي ورا الماوس"),
           ("terminal", "تقني (Terminal)", "شبكة نقط خضرا بتنوّر حوالين الماوس"),
           ("tilt", "فاتح + كارت 3D", "الكارت بيميل مع الماوس وكروت طايرة"),
           ("teal", "ألوان الشركة (Teal)", "خطوط منسابة بتلف حوالين الماوس")],
    "en": [("network", "Network + split card", "Dark teal, connected dots follow the mouse"),
           ("aurora", "Aurora + animated border", "Color blobs follow the mouse"),
           ("terminal", "Terminal", "Green dot matrix glows around the mouse"),
           ("tilt", "Light + 3D card", "Card tilts with the mouse"),
           ("teal", "Company teal", "Flowing lines swirl around the mouse")],
}
UI_THEME_NAMES = {
    "ar": [("terminal", "تقني", "غامق بلون أخضر — زي شاشة الدخول التقنية"),
           ("teal", "ألوان الشركة Teal", "فاتح، قايمة تيل غامق، جداول زي التقارير المعتمدة"),
           ("glass", "زجاج وألوان", "غامق، قايمة زجاج عايمة وألوان متدرجة"),
           ("minimal", "بسيط + قايمة فوق", "فاتح وهادي، القايمة فوق والمساحة كلها للمحتوى"),
           ("rail", "أيقونات جانبية", "غامق، القايمة أيقونات بس والاسم بيظهر لما تقفي عليها")],
    "en": [("terminal", "Terminal", "Dark with green accents"),
           ("teal", "Company teal", "Light, dark-teal sidebar"),
           ("glass", "Glass & colors", "Dark, floating glass sidebar"),
           ("minimal", "Minimal + top menu", "Light and calm, menu on top"),
           ("rail", "Icon rail", "Dark, icons-only sidebar")],
}


@route("/settings/appearance", methods=["POST"])
@auth.login_required
def settings_appearance_save():
    config = settings_helper.load_site_config()
    ls, ui = request.form.get("login_style", ""), request.form.get("ui_theme", "")
    if ls in dict((k, 1) for k, _, _ in LOGIN_STYLE_NAMES["en"]):
        config["login_style"] = ls
    if ui in dict((k, 1) for k, _, _ in UI_THEME_NAMES["en"]):
        config["ui_theme"] = ui
    settings_helper.save_site_config(config)
    flash("✅ اتحفظ المظهر" if get_current_lang() == "ar" else "✅ Appearance saved", "success")
    return redirect(url_for("settings") + "#appearance")


@route("/settings/site", methods=["POST"])
@auth.login_required
def settings_site_save():
    config = settings_helper.load_site_config()
    config["site_name_ar"] = request.form.get("site_name_ar", "").strip()
    config["site_name_en"] = request.form.get("site_name_en", "").strip()
    config["company_name_ar"] = request.form.get("company_name_ar", "").strip()
    config["company_name_en"] = request.form.get("company_name_en", "").strip()
    config["company_address"] = request.form.get("company_address", "").strip()
    config["company_phone"] = request.form.get("company_phone", "").strip()
    config["company_email"] = request.form.get("company_email", "").strip()
    config["company_cr"] = request.form.get("company_cr", "").strip()
    config["company_vat"] = request.form.get("company_vat", "").strip()
    config["daily_report_hour"] = request.form.get("daily_report_hour", "").strip()
    key = request.form.get("anthropic_api_key", "").strip()
    if key == "__clear__":
        config["anthropic_api_key"] = ""
    elif key and not key.startswith("•"):           # the masked value means «unchanged»
        config["anthropic_api_key"] = key
    settings_helper.save_site_config(config)
    flash("✅ تم حفظ إعدادات الموقع", "success")
    return redirect(url_for("settings"))


@route("/settings/upload-logo", methods=["POST"])
@auth.login_required
def settings_upload_logo():
    file = request.files.get("logo")
    if not file or not file.filename:
        flash("❌ لم يتم اختيار ملف", "danger")
        return redirect(url_for("settings"))
    uploads_dir = settings_helper.get_uploads_dir()
    ext = Path(file.filename).suffix.lower()
    filename = f"logo{ext}"
    file.save(str(uploads_dir / filename))
    config = settings_helper.load_site_config()
    config["logo_filename"] = filename
    settings_helper.save_site_config(config)
    flash("✅ تم رفع الشعار", "success")
    return redirect(url_for("settings"))


@route("/settings/upload-favicon", methods=["POST"])
@auth.login_required
def settings_upload_favicon():
    file = request.files.get("favicon")
    if not file or not file.filename:
        flash("❌ لم يتم اختيار ملف", "danger")
        return redirect(url_for("settings"))
    uploads_dir = settings_helper.get_uploads_dir()
    ext = Path(file.filename).suffix.lower()
    filename = f"favicon{ext}"
    file.save(str(uploads_dir / filename))
    config = settings_helper.load_site_config()
    config["favicon_filename"] = filename
    settings_helper.save_site_config(config)
    flash("✅ تم رفع الأيقونة", "success")
    return redirect(url_for("settings"))


@route("/settings/slack", methods=["POST"])
@auth.login_required
def settings_slack_save():
    from config import slack_notifier
    config = slack_notifier.load_config() or {}
    config["enabled"] = "slack_enabled" in request.form
    config["webhook_url"] = request.form.get("slack_webhook", "").strip()
    config["notify_on"] = request.form.get("slack_notify_on", "failure")
    slack_notifier.save_config(config)
    flash("✅ تم حفظ إعدادات Slack", "success")
    return redirect(url_for("settings"))


@route("/users")
@auth.login_required
def users():
    if not auth.is_admin():
        flash("❌ غير مصرح لك بالوصول", "danger")
        return redirect(url_for("index"))
    all_users = settings_helper.load_users()
    return render_template("users.html", users=all_users)


@route("/users/add", methods=["POST"])
@auth.login_required
def users_add():
    if not auth.is_admin():
        return redirect(url_for("index"))
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    full_name = request.form.get("full_name", "").strip()
    role = request.form.get("role", "user")
    if not username or not password:
        flash("❌ اسم المستخدم وكلمة المرور مطلوبان", "danger")
        return redirect(url_for("users"))
    success, result = settings_helper.add_user(username, password, full_name, role)
    if success:
        flash(f"✅ تم إضافة المستخدم: {username}", "success")
    else:
        flash(f"❌ {result}", "danger")
    return redirect(url_for("users"))


@route("/users/delete/<user_id>", methods=["POST"])
@auth.login_required
def users_delete(user_id):
    if not auth.is_admin():
        return redirect(url_for("index"))
    if user_id == session.get("user_id"):
        flash("❌ لا يمكنك حذف حسابك الحالي", "danger")
        return redirect(url_for("users"))
    if settings_helper.delete_user(user_id):
        flash("✅ تم حذف المستخدم", "success")
    else:
        flash("❌ فشل الحذف", "danger")
    return redirect(url_for("users"))


def _load_json(path):
    p = Path(path)
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (UnicodeDecodeError, json.JSONDecodeError):
        try:
            with open(p, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception:
            return {}
    except Exception:
        return {}

@route("/settings/email", methods=["POST"])
@auth.login_required
def settings_email_save():
    recipients_raw = request.form.get("recipients", "").strip()
    recipients = [r.strip() for r in recipients_raw.replace("\n", ",").split(",") if r.strip()]

    config = {
        "enabled": "email_enabled" in request.form,
        "smtp_host": request.form.get("smtp_host", "").strip(),
        "smtp_port": int(request.form.get("smtp_port", 587) or 587),
        "sender_email": request.form.get("sender_email", "").strip(),
        "sender_password": request.form.get("sender_password", "").strip(),
        "recipients": recipients,
        "notify_on": request.form.get("notify_on", "failure"),
    }

    settings_helper.save_email_config(config)
    flash("Email settings saved", "success")
    return redirect(url_for("settings"))


@route("/settings/email/test", methods=["POST"])
@auth.login_required
def settings_email_test():
    from config import emailer as email_module
    to_email = request.form.get("test_email", "").strip()
    if not to_email:
        return jsonify({"success": False, "message": "Enter target email"})
    success, message = email_module.send_test_email(to_email)
    return jsonify({"success": success, "message": message})



@route("/settings/test-sites", methods=["POST"])
@auth.login_required
def settings_test_sites_save():
    from web import test_sites_helper as tsh
    profile_id = request.form.get("profile_id", "").strip()
    name = request.form.get("name", "").strip()
    base_url = request.form.get("base_url", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    notes = request.form.get("notes", "").strip()

    if not name or not base_url or not username:
        flash("الاسم والرابط واسم المستخدم مطلوبين", "danger")
        return redirect(url_for("settings") + "#test-sites")

    if profile_id:
        success, result = tsh.update_profile(
            profile_id,
            name=name, base_url=base_url,
            username=username, password=password, notes=notes
        )
        flash("تم تحديث الموقع" if success else "فشل التحديث",
              "success" if success else "danger")
    else:
        success, result = tsh.add_profile(
            name=name, base_url=base_url,
            username=username, password=password, notes=notes
        )
        flash("تم إضافة الموقع: " + name if success else "فشل الإضافة",
              "success" if success else "danger")

    return redirect(url_for("settings") + "#test-sites")


@route("/settings/test-sites/delete/<profile_id>", methods=["POST"])
@auth.login_required
def settings_test_sites_delete(profile_id):
    from web import test_sites_helper as tsh
    success, message = tsh.delete_profile(profile_id)
    flash("تم حذف الموقع" if success else message,
          "success" if success else "danger")
    return redirect(url_for("settings") + "#test-sites")


@route("/settings/test-sites/activate/<profile_id>", methods=["POST"])
@auth.login_required
def settings_test_sites_activate(profile_id):
    from web import test_sites_helper as tsh
    success = tsh.set_active_profile(profile_id)
    flash("تم تفعيل الموقع" if success else "فشل التفعيل",
          "success" if success else "danger")
    return redirect(url_for("settings") + "#test-sites")


@route("/settings/tunnel", methods=["POST"])
@auth.login_required
def tunnel_settings_save():
    from web import tunnel_helper
    flask_url = request.form.get("flask_url", "").strip()
    vnc_url = request.form.get("vnc_url", "").strip()
    provider = request.form.get("provider", "cloudflare").strip()

    tunnel_helper.save_config(flask_url, vnc_url, provider)
    flash("✅ تم حفظ إعدادات Tunnel", "success")
    return redirect(url_for("settings") + "#tunnel")


@route("/settings/tunnel/reload", methods=["POST"])
@auth.login_required
def tunnel_settings_reload():
    """يعيد قراءة الروابط من data/settings/tunnel_config.json"""
    flash("✅ تم إعادة تحميل الإعدادات", "success")
    return redirect(url_for("settings") + "#tunnel")
