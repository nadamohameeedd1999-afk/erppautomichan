"""
🗺️ One place for every page of the dashboard: its section, name (Arabic + English), icon and what it's for.
The side menu, the page titles, the search box (Ctrl K) and the «all pages» map are all built from this list,
so a page has ONE name everywhere and nothing is listed twice.
"""
from flask import Blueprint, render_template

from web import auth

# (key, [endpoints that light this item], url, icon, ar, en, what it's for — ar, en, admin_only)
# 8 groups (the review of 20-11): one question per group; «أدوات متقدمة» is folded in the side menu
SECTIONS = [
    ('overview', 'نظرة عامة', 'Overview', [
        ('home', ['index'], '/', 'bi-grid-1x2', 'الرئيسية', 'Home', 'ملخص اليوم: آخر التشغيلات، اللي فشل، اللي جاي في الجدولة', "Today at a glance: last runs, failures, what's scheduled"),
        ('map', ['nav.sitemap'], '/pages', 'bi-signpost-split', 'كل الصفحات', 'All pages', 'خريطة المشروع: كل صفحة وبتعمل إيه', 'Every page of the project and what it does'),
    ]),
    ('build', 'بناء الاختبارات', 'Build tests', [
        ('auto', ['checks.auto_page'], '/auto-test', 'bi-robot', 'الاختبار الآلي', 'Automatic test', 'شاشة بكل الطرق: إضافة وتعديل وحذف وطباعة + المختبر العنيد + بيانات الاختبار + مكتبة الشاشات', 'A screen every way: add / edit / delete / print + stubborn tester + test data + screen library'),
        ('bizsc', ['checks.biz_scenarios_page'], '/business-scenarios', 'bi-clipboard-check', 'سيناريوهات الأعمال', 'Business scenarios', 'سيناريو المطور كامل (زي فاتورة البيع الآجلة 19 بند) ونموذج الورد بالنتيجة', "The developer's full scenario (e.g. credit sales invoice, 19 steps) + the filled Word form"),
        ('checks', ['checks.checks_page'], '/checks', 'bi-diagram-3', 'الدورات والفحوصات', 'Cycles & checks', 'دورة كاملة (فاتورة ← قبض ← قيد)، فحص تقرير، سرعة، مطابقة الحسابات، تنظيف', 'Full cycles, report checks, speed, account reconciliation, cleanup'),
    ]),
    ('run', 'التشغيل', 'Run', [
        ('queue', ['ops.run_center'], '/queue', 'bi-list-task', 'مركز التشغيل', 'Run center', 'الشغال دلوقتي والطابور، إيقاف وترتيب', "What's running and waiting; stop and reorder"),
        ('simulation', ['simulation.index'], '/simulation/', 'bi-building', 'الشركة الافتراضية', 'Virtual company', 'NQ Simulation: موظفين افتراضيين بيشتغلوا على NQ ERP طول اليوم ويبلّغوا باللي وقع — وصفحة ديمو للعميل على /demo/', 'NQ Simulation: virtual staff working on NQ ERP all day, reporting what broke — and a client demo page at /demo/'),
    ]),
    ('health', 'فحص الموقع', 'Site checks', [
        ('health', ['checks.health_page'], '/health', 'bi-heart-pulse', 'صحة النظام', 'System health', 'كل الشاشات بتفتح؟ السرعة الحقيقية؟ الحسابات متزنة؟ + تقرير للعميل', 'Do all screens open? Real speed? Balanced books? + client report'),
        ('readiness', ['checks.readiness_page'], '/readiness', 'bi-stoplights', 'جاهزية الإصدار', 'Release readiness', 'درجة من 100 وقرار: ينفع ينزل / بحذر / متنشرش', 'Score /100 and a go / care / no-go verdict'),
        ('golive', ['golive.page'], '/go-live', 'bi-rocket-takeoff', 'اختبار الاستلام', 'Go-Live acceptance', 'زرار واحد قبل تسليم موقع العميل: الشاشات والأسماء واللينكات والتقارير والسرعة والحمل والحسابات والكود — حكم لكل جزء وتقرير للمطورين', 'One button before handing a client site over: screens, names, links, reports, speed, load, books, code — a verdict per area and a developer report'),
        ('xray', ['xray.page'], '/xray', 'bi-radioactive', 'أشعة النظام', 'System X-ray', 'قراءة الموقع من بره: روابط غلط، مكتبات فيها ثغرات، أمان، لغة، صور الشاشات، نت ضعيف + مقارنة موقعين', 'Read the site from outside: wrong links, vulnerable libraries, security, language, screenshots, slow network + compare two sites'),
    ]),
    ('compare', 'المقارنات', 'Compare', [
        ('repcmp', ['repcmp.page'], '/report-compare', 'bi-layout-split', 'مقارنة التقارير', 'Compare reports', 'نفس التقرير بنفس السيناريو على موقع الاختبار وموقع العميل: الشكل والحقول والتنسيق والقواعد', 'Same report & scenario on the test site and a client: layout, fields, formats, rules'),
        ('impact', ['impact.page'], '/impact', 'bi-bullseye', 'أثر التغيير', 'Change impact', 'إيه اللي اتغير في الكود بين نسختين (GitHub أو ZIP) وبيأثر على أنهي شاشات وتقارير وإجراءات — واختبر المتأثر بس', 'What changed between two code versions (GitHub or ZIP), which screens / reports / procedures it touches — test only those'),
        ('compare', ['ops.compare_page'], '/compare', 'bi-intersect', 'مقارنة التشغيلات', 'Compare runs', 'تشغيلتين جنب بعض: إيه اللي اتغير', 'Two runs side by side: what changed'),
        ('envcmp', ['checks.env_compare_page'], '/env-compare', 'bi-arrow-left-right', 'مقارنة بيئتين', 'Compare environments', 'موقع الاختبار مقابل نظام العميل: الشاشات والحقول والسرعة', 'Test site vs client system: screens, fields, speed'),
    ]),
    ('results', 'النتايج والتذاكر', 'Results & tickets', [
        ('reports', ['reports', 'report_detail', 'ops.daily_report_page', 'ops.discovery_report_page', 'docs.test_summary'], '/reports', 'bi-bar-chart-line', 'التقارير', 'Reports', 'نتيجة كل تشغيلة + تقرير إثبات التنفيذ + اليومي', "Every run's result + evidence report + daily report"),
        ('devsup', ['support.dev_page'], '/dev-support', 'bi-bug', 'دعم المطورين', 'Developer support', 'كل مشاكل الـ ERP اللي الاختبارات لقتها بالتفاصيل — تتبعت للمطورين Word / Excel', 'Every ERP problem the tests found, with details — send to developers as Word / Excel'),
        ('toolsup', ['support.tool_page'], '/tool-support', 'bi-wrench-adjustable', 'دعم الأداة', 'Tool support', 'مشاكل أداة الاختبار نفسها مع آخر اللوج — تتنسخ وتتبعت للإصلاح', 'Problems of the test tool itself with the log tail — copy and send to be fixed'),
        ('autohealth', ['autohealth.page'], '/automation-health', 'bi-activity', 'صحة الأتمتة', 'Automation health', 'الاختبارات اللي بتفشل أو متذبذبة أو بقت أبطأ', 'Tests that fail, flip-flop or got slower'),
        ('diag', ['diag.page'], '/diagnostics', 'bi-clipboard-pulse', 'تقرير التشخيص', 'Diagnostics', 'كل اللوج في ملف واحد يتبعت للدعم', 'All logs in one file to send to support'),
    ]),
    ('advanced', 'أدوات متقدمة', 'Advanced tools', [
        ('dbaudit', ['dbaudit.page'], '/db-audit', 'bi-database-check', 'فحص قاعدة البيانات', 'Database audit', 'نسخة من قاعدة موقع الاختبار: إجراءات مكسورة، داتا يتيمة، قيود مش متزنة، المحاسب الظل، وخريطة الشاشة ← الجدول ← الإجراء', 'A copy of the test database: broken procedures, orphan data, unbalanced journals, shadow accountant, screen → table → procedure map'),
        ('twin', ['twin.page'], '/twin', 'bi-diagram-3-fill', 'التوأم الرقمي', 'Digital twin', 'بيقرا كود الـ ERP ويربطه بقاعدة البيانات: الشاشة ← الكنترولر ← الإجراءات ← الجداول، والأزرار والإجراءات والتقارير المكسورة', 'Reads the ERP code and ties it to the database: screen → controller → procedures → tables, broken buttons, procedures and reports'),
        ('migration', ['migration.page'], '/migration', 'bi-box-arrow-in-down', 'نقل الأرصدة الافتتاحية', 'Opening-balance migration', 'Excel النظام القديم قدام Excel من NQ ERP سطر بسطر: المطابق والمختلف والناقص والزيادة والإجماليات', "The old system's Excel against NQ ERP's export, row by row: same, different, missing, extra, totals"),
        ('uat', ['uat.page'], '/uat', 'bi-pen', 'اختبار القبول مع العميل', 'Client acceptance (UAT)', 'موظفين العميل يختبروا بلينك: نجح / فشل وصورة لكل خطوة، وفي الآخر توقيع وشهادة استلام', 'Client staff test through a link: pass / fail and a screenshot per step, then a signature and a handover certificate'),
    ]),
    ('admin', 'الإدارة', 'Admin', [
        ('sites', ['sites.sites_page', 'monthly.monthly_page'], '/sites', 'bi-buildings', 'العملاء والمواقع', 'Clients & sites', 'كل موقع ونتيجته + التقرير الشهري للعميل', 'Every site and its results + monthly client report'),
        ('settings', ['settings'], '/settings', 'bi-gear', 'الإعدادات', 'Settings', 'المواقع وكلمات السر، التنبيهات، التخزين، المظهر، مفتاح Claude', 'Sites & passwords, alerts, storage, look, Claude key'),
        ('users', ['users'], '/users', 'bi-people', 'المستخدمين', 'Users', 'حسابات اللوحة وصلاحياتها', 'Dashboard accounts and roles'),
        ('backups', ['ops.backups_page'], '/backups', 'bi-shield-check', 'النسخ الاحتياطي والبداية الجديدة', 'Backups & fresh start', 'نسخة احتياطية، استرجاع، ومسح كل البيانات لتجربة من الأول', 'Backup, restore, and wipe everything to start fresh'),
        ('audit', ['audit_page'], '/audit', 'bi-journal-text', 'سجل النشاط', 'Activity log', 'مين عمل إيه وإمتى', 'Who did what and when', True),
    ]),
]


# reachable (search Ctrl K, «all pages», links inside other pages) but not in the side menu — each one belongs to a bigger page:
#   all pages = the Ctrl K search · run compare / environment compare -> «المقارنات» · automation health / diagnostics -> «النتايج»
HIDDEN = {"map", "autohealth", "diag"}


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
