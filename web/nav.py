"""
🗺️ One place for every page of the dashboard: its section, name (Arabic + English), icon and what it's for.
The side menu, the page titles, the search box (Ctrl K) and the «all pages» map are all built from this list,
so a page has ONE name everywhere and nothing is listed twice.
"""
from flask import Blueprint, render_template

from web import auth

# (key, [endpoints that light this item], url, icon, ar, en, what it's for — ar, en, admin_only)
SECTIONS = [
    ("overview", "نظرة عامة", "Overview", [
        ("home", ["index"], "/", "bi-grid-1x2", "الرئيسية", "Home",
         "ملخص اليوم: آخر التشغيلات، اللي فشل، اللي جاي في الجدولة", "Today at a glance: last runs, failures, what's scheduled"),
        ("map", ["nav.sitemap"], "/pages", "bi-signpost-split", "كل الصفحات", "All pages",
         "خريطة المشروع: كل صفحة وبتعمل إيه", "Every page of the project and what it does"),
    ]),
    ("build", "بناء الاختبارات", "Build tests", [
        ("auto", ["checks.auto_page"], "/auto-test", "bi-robot", "الاختبار الآلي", "Automatic test",
         "شاشة بكل الطرق: إضافة وتعديل وحذف وطباعة + المختبر العنيد + بيانات الاختبار + مكتبة الشاشات",
         "A screen every way: add / edit / delete / print + stubborn tester + test data + screen library"),
        ("bizsc", ["checks.biz_scenarios_page"], "/business-scenarios", "bi-clipboard-check", "سيناريوهات الأعمال", "Business scenarios",
         "سيناريو المطور كامل (زي فاتورة البيع الآجلة 19 بند) ونموذج الورد بالنتيجة", "The developer's full scenario (e.g. credit sales invoice, 19 steps) + the filled Word form"),
        ("checks", ["checks.checks_page"], "/checks", "bi-diagram-3", "الدورات والفحوصات", "Cycles & checks",
         "دورة كاملة (فاتورة ← قبض ← قيد)، فحص تقرير، سرعة، مطابقة الحسابات، تنظيف", "Full cycles, report checks, speed, account reconciliation, cleanup"),
    ]),
    ("run", "التشغيل", "Run", [
        ("queue", ["ops.run_center"], "/queue", "bi-list-task", "مركز التشغيل", "Run center",
         "الشغال دلوقتي والطابور، إيقاف وترتيب", "What's running and waiting; stop and reorder"),
    ]),
    ("health", "صحة الأنظمة", "System health", [
        ("health", ["checks.health_page"], "/health", "bi-heart-pulse", "صحة النظام", "System health",
         "كل الشاشات بتفتح؟ السرعة الحقيقية؟ الحسابات متزنة؟ + تقرير للعميل", "Do all screens open? Real speed? Balanced books? + client report"),
        ("readiness", ["checks.readiness_page"], "/readiness", "bi-traffic-light", "جاهزية الإصدار", "Release readiness",
         "درجة من 100 وقرار: ينفع ينزل / بحذر / متنشرش", "Score /100 and a go / care / no-go verdict"),
        ("xray", ["xray.page"], "/xray", "bi-radioactive", "أشعة النظام", "System X-ray",
         "قراءة الموقع من بره: روابط غلط، مكتبات فيها ثغرات، أمان، لغة، صور الشاشات، نت ضعيف + مقارنة موقعين", "Read the site from outside: wrong links, vulnerable libraries, security, language, screenshots, slow network + compare two sites"),
        ("twin", ["twin.page"], "/twin", "bi-diagram-3-fill", "التوأم الرقمي", "Digital twin",
         "بيقرا كود الـ ERP ويربطه بقاعدة البيانات: الشاشة ← الكنترولر ← الإجراءات ← الجداول، والأزرار والإجراءات والتقارير المكسورة", "Reads the ERP code and ties it to the database: screen → controller → procedures → tables, broken buttons, procedures and reports"),
        ("dbaudit", ["dbaudit.page"], "/db-audit", "bi-database-check", "فحص قاعدة البيانات", "Database audit",
         "نسخة من قاعدة موقع الاختبار: إجراءات مكسورة، داتا يتيمة، قيود مش متزنة، المحاسب الظل، وخريطة الشاشة ← الجدول ← الإجراء", "A copy of the test database: broken procedures, orphan data, unbalanced journals, shadow accountant, screen → table → procedure map"),
        ("repcmp", ["repcmp.page"], "/report-compare", "bi-layout-split", "مقارنة التقارير", "Compare reports",
         "نفس التقرير بنفس السيناريو على موقع الاختبار وموقع العميل: الشكل والحقول والتنسيق والقواعد", "Same report & scenario on the test site and a client: layout, fields, formats, rules"),
        ("envcmp", ["checks.env_compare_page"], "/env-compare", "bi-arrow-left-right", "مقارنة بيئتين", "Compare environments",
         "موقع الاختبار مقابل نظام العميل: الشاشات والحقول والسرعة", "Test site vs client system: screens, fields, speed"),
    ]),
    ("results", "النتائج والتقارير", "Results", [
        ("reports", ["reports", "report_detail", "ops.daily_report_page", "ops.discovery_report_page", "docs.test_summary"], "/reports", "bi-bar-chart-line",
         "التقارير", "Reports", "نتيجة كل تشغيلة + تقرير إثبات التنفيذ + اليومي", "Every run's result + evidence report + daily report"),
        ("compare", ["ops.compare_page"], "/compare", "bi-intersect", "مقارنة التشغيلات", "Compare runs",
         "تشغيلتين جنب بعض: إيه اللي اتغير", "Two runs side by side: what changed"),
        ("autohealth", ["autohealth.page"], "/automation-health", "bi-activity", "صحة الأتمتة", "Automation health",
         "الاختبارات اللي بتفشل أو متذبذبة أو بقت أبطأ", "Tests that fail, flip-flop or got slower"),
        ("devsup", ["support.dev_page"], "/dev-support", "bi-bug", "دعم المطورين", "Developer support",
         "كل مشاكل الـ ERP اللي الاختبارات لقتها بالتفاصيل — تتبعت للمطورين Word / Excel", "Every ERP problem the tests found, with details — send to developers as Word / Excel"),
        ("toolsup", ["support.tool_page"], "/tool-support", "bi-wrench-adjustable", "دعم الأداة", "Tool support",
         "مشاكل أداة الاختبار نفسها مع آخر اللوج — تتنسخ وتتبعت للإصلاح", "Problems of the test tool itself with the log tail — copy and send to be fixed"),
        ("diag", ["diag.page"], "/diagnostics", "bi-clipboard-pulse", "تقرير التشخيص", "Diagnostics",
         "كل اللوج في ملف واحد يتبعت للدعم", "All logs in one file to send to support"),
    ]),
    ("admin", "الإدارة", "Admin", [
        ("sites", ["sites.sites_page", "monthly.monthly_page"], "/sites", "bi-buildings", "العملاء والمواقع", "Clients & sites",
         "كل موقع ونتيجته + التقرير الشهري للعميل", "Every site and its results + monthly client report"),
        ("settings", ["settings"], "/settings", "bi-gear", "الإعدادات", "Settings",
         "المواقع وكلمات السر، التنبيهات، التخزين، المظهر، مفتاح Claude", "Sites & passwords, alerts, storage, look, Claude key"),
        ("users", ["users"], "/users", "bi-people", "المستخدمين", "Users", "حسابات اللوحة وصلاحياتها", "Dashboard accounts and roles"),
        ("backups", ["ops.backups_page"], "/backups", "bi-shield-check", "النسخ الاحتياطي والبداية الجديدة", "Backups & fresh start",
         "نسخة احتياطية، استرجاع، ومسح كل البيانات لتجربة من الأول", "Backup, restore, and wipe everything to start fresh"),
        ("audit", ["audit_page"], "/audit", "bi-journal-text", "سجل النشاط", "Activity log", "مين عمل إيه وإمتى", "Who did what and when", True),
    ]),
]


# reachable (search Ctrl K, «all pages», links inside other pages) but not in the side menu — each one belongs to a bigger page:
#   compare + automation health -> tabs on «Reports» · diagnostics + all pages -> «Settings» · environment compare -> «Release readiness»
HIDDEN = {"map", "compare", "autohealth", "diag", "envcmp"}


def menu_sections():
    """the side menu: SECTIONS without the HIDDEN pages (and without a section left empty)"""
    out = []
    for sk, sar, sen, its in SECTIONS:
        keep = [it for it in its if it[0] not in HIDDEN]
        if keep:
            out.append((sk, sar, sen, keep))
    return out


def items():
    for sk, sar, sen, its in SECTIONS:
        for it in its:
            yield sk, it


def page_meta(endpoint, lang):
    """-> (name, section name) for the current page, in the current language"""
    for sk, sar, sen, its in SECTIONS:
        for it in its:
            if endpoint in it[1]:
                return (it[4] if lang == "ar" else it[5]), (sar if lang == "ar" else sen)
    return None, None


bp = Blueprint("nav", __name__)


@bp.route("/pages")
@auth.login_required
def sitemap():
    return render_template("pages.html", sections=SECTIONS)
