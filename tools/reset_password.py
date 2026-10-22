"""
Reset a dashboard user's password (لوحة التحكم).

    python tools/reset_password.py            -> admin
    python tools/reset_password.py someuser
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from web import settings_helper as sh  # noqa: E402

user = sys.argv[1] if len(sys.argv) > 1 else "admin"
if not sh.get_user(user):
    print(f"مفيش مستخدم اسمه '{user}'. الموجودين: {', '.join(u['username'] for u in sh.load_users())}")
    sys.exit(1)
p1 = getpass.getpass(f"كلمة السر الجديدة لـ {user}: ")
p2 = getpass.getpass("اكتبيها تاني: ")
if not p1 or p1 != p2:
    print("مش متطابقين — محصلش تغيير")
    sys.exit(1)
sh.reset_password(user, p1)
print(f"✅ اتغيرت كلمة سر {user}. لو البرنامج شغال، اقفليه وشغليه تاني لو كان الدخول مقفول.")
