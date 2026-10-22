# ERP Test Automation — NQ ERP

برنامج اختبار آلي لنظام NQ ERP: لوحة تحكم (Flask) بتبني الشاشات والسيناريوهات من غير كود، وتشغّلها بـ Selenium، وتجدولها، وتطلع تقارير ومقارنات وبث مباشر.

## التشغيل على الجهاز

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # واكتبي فيه كلمة السر
python web/app.py           # http://localhost:5000
```

أو `start_all.ps1` (بيشغّل اللوحة + Cloudflare tunnel).

### نسيتي كلمة سر لوحة التحكم؟
- اكتبي `ADMIN_PASSWORD=...` في `.env` وشغّلي البرنامج تاني، أو
- `python tools\reset_password.py`

## Docker

```bash
docker compose up -d --build
```

كل البيانات في الـ volume `./data:/app/data`. على Railway اعملي Volume على `/app/data`.

## هيكل المشروع

| الفولدر | فيه إيه |
|---|---|
| `engine/` | منشئ الشاشات: فحص الفورم، التعبئة، التشغيل، السيناريوهات، الجلسة |
| `web/` | لوحة التحكم (Flask) + الصفحات + الطابور + الجدولة + النسخ الاحتياطي |
| `pages/` | Page Objects (تسجيل الدخول + الاختبارات القديمة) |
| `tests/` | الاختبارات (`screens/` و `scenarios/` بيتولّدوا أوتوماتيك) |
| `config/` | الإعدادات العامة + `paths.py` + `storage.py` + تعريفات `screens/` و `scenarios/` |
| `utils/` | أدوات مساعدة (logger…) |
| `data/` | **كل حاجة البرنامج بيحفظها** (مش على GitHub) |

## فولدر data/

```
data/
  settings/      المستخدمين، المواقع، الإيميل، Slack، المفتاح السري
  schedules.json الجدولة
  runs/          results / logs / screenshots / allure
  state/         الجلسة المحفوظة + مهام الفحص
  backups/       نسخ احتياطي يومي (zip)
  history/       آخر 10 نسخ من كل ملف إعداد اتعدّل
  trash/         أي شاشة أو سيناريو اتمسح
```

- الحفظ ذرّي (ملف مؤقت ثم استبدال)، فمفيش ملف بيبوظ لو البرنامج وقف فجأة.
- لو ملف باظ بيرجع لآخر نسخة سليمة من `history/`.
- صفحة **النسخ الاحتياطي** (من قائمة المستخدم) فيها: نسخة يدوية، تحميل، استرجاع، وسلة المحذوفات.

## متغيرات البيئة

| المتغير | الافتراضي | |
|---|---|---|
| `BASE_URL` / `LOGIN_USERNAME` / `LOGIN_PASSWORD` | — | موقع الـ ERP |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / — | دخول لوحة التحكم — كل ما البرنامج يشتغل بيتظبط عليها |
| `SECRET_KEY` | بيتولّد محليًا | **لازم** في السيرفر |
| `DATA_DIR` | `./data` | مكان البيانات |
| `DEFS_DIR` | `./config` | مكان تعريفات الشاشات والسيناريوهات |
| `SCHEDULE_TZ` | `Africa/Cairo` | توقيت الجدولة |
| `SESSION_REUSE` / `SESSION_REUSE_MINUTES` | `1` / `25` | إعادة استخدام تسجيل الدخول |
| `AUTO_RETRY` | `1` | إعادة الاختبار لو فشل بسبب المتصفح/الشبكة |
| `BACKUP_KEEP` / `BACKUP_HOUR` | `14` / `3` | النسخ الأوتوماتيك |
| `VNC_PASSWORD` | `erp` | البث المباشر |
