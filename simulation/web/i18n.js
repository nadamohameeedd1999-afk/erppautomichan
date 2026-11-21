// 🌐 NQ Simulation in English: when the language in the settings is English, every Arabic phrase the pages show
// (fixed text, buttons, tooltips, and what the pages draw later) is swapped for its English, and the page turns left-to-right.
// Phrases are matched as whole words only, longest first. Data from the system itself (customers, items, the system's own messages) stays as it is.
(function () {
  const D = {
    // header & controls
    'الشركة الافتراضية': 'Virtual Company', 'ابدأ يوم جديد': 'Start a new day', 'إيقاف مؤقت': 'Pause', 'كمّل': 'Resume', 'السرعة': 'Speed', 'بطيء': 'Slow', 'عادي': 'Normal',
    'سريع جدًا': 'Very fast', 'سريع': 'Fast', 'أقصى سرعة': 'Max speed', 'تقرير اليوم': "Today's report", 'تذاكر المطورين': 'Developer tickets', 'عرض للعميل': 'Client view',
    'مقارنة الأيام': 'Compare days', 'التنبيه': 'Alerts', 'الصوت': 'Voice', 'الإعدادات': 'Settings', 'وضع المحاكاة': 'Simulation mode', 'محاكاة': 'Simulation',
    'على الموقع الحقيقي': 'on the real site', 'الساعة مستنية': 'The clock is waiting for', 'مهمة في المتصفح)': 'tasks in the browser)',
    'مشاكل السيستم نفسه بصورها وأدلتها — تتبعت للمطورين': "The system's own problems with screenshots and evidence — for the developers",
    'شاشة نضيفة بالأرقام المهمة تعرضها قدام العميل': 'A clean screen with the key numbers to show a client',
    'اليوم ده قدام اللي قبله: اتصلح · جديد · لسه موجود': 'Today vs. the previous days: fixed · new · still there',
    'تنبيه فوري بصوت وإشعار أول ما شاشة تقف على السيستم': 'Instant sound + notification the moment a screen stops on the system',
    'الموظفين يتكلموا كلام الشات بصوت عربي سعودي (يحتاج إنترنت)': 'The employees speak the chat out loud (needs internet)',
    // health & timeline
    'صحة الشاشات النهارده': "Today's screens health", 'دوس تشوف الشاشات': 'click to see the screens', 'اقفل': 'close', 'شاشة تمام — اعرض الكل': 'screens OK — show all', 'اختصر': 'less',
    'لسه ما اتجربتش ولا شاشة — هتتلون أول ما الموظفين يشتغلوا': 'No screen tested yet — they light up once the employees start',
    'تمام': 'OK', 'بطيئة': 'slow', 'وقفت': 'stopped', 'صلاحيات': 'permissions', 'آخر مرة': 'last time', 'نجحت': 'passed', 'أبطأ مرة': 'slowest', 'آخر رد من السيستم': "The system's last answer",
    'افتح آخر شكوى على الشاشة دي': 'Open the last complaint on this screen', 'الخط الزمني لليوم': "The day's timeline", 'كل مربع مهمة': 'each block is a task',
    'دوس عليه للتفاصيل': 'click for details', 'هيتملى أول ما الموظفين يبدأوا شغل': 'Fills in once the employees start working', 'مستند رقم': 'document no.', 'الشكوى بالدليل': 'The complaint with its evidence',
    // legend & cards
    'فاضي': 'Free', 'شغال على السيستم': 'Working on the system', 'متعطل': 'Stuck', 'ماشي': 'Walking', 'دوس على أي موظف تشوف كاميرا مكتبه': "Click any employee to see his desk camera",
    'دوس على أي موظف تشوف يومه: عمل إيه، اتعطل فين، واشتكى من إيه': 'Click any employee to see his day: what he did, where he got stuck, what he complained about',
    'صفقة النهارده': 'deals today', 'اتقفلت': 'closed', 'متعطلة': 'stuck', 'شغالة': 'open', 'مشكلة سيستم': 'system problems', 'شغالين دلوقتي': 'working now', 'مهمة مستنية': 'tasks waiting',
    // tabs & panes
    'الشات': 'Chat', 'الصفقات': 'Deals', 'الشكاوى': 'Complaints', 'جديد/اتصلح': 'New/Fixed', 'اليوم': 'Today',
    'الشركة لسه ما فتحتش — دوس «ابدأ يوم جديد»': 'The company is not open yet — click «Start a new day»', 'مفيش صفقات لسه': 'No deals yet', 'مفيش شكاوى لحد دلوقتي': 'No complaints so far',
    'فتحت': 'opened', 'قفلت': 'closed', 'الدليل': 'Evidence', 'السيستم': 'System', 'بيانات / إعداد': 'Data / setup', 'النت': 'Internet', 'الأداة': 'Tool', 'ضغط شغل': 'Workload',
    'صفقات اتقفلت': 'deals closed', 'مبيعات': 'sales', 'متوسط الدورة (د)': 'avg. cycle (min)', 'شكوى': 'complaints', 'أكتر واحد اتعطل': 'got stuck most',
    'المشاكل حسب مصدرها': 'Problems by source', 'المشاكل': 'Problems', 'مرة': 'times', 'مفيش': 'none', 'أبطأ الشاشات': 'Slowest screens', 'متوسط': 'avg.', 'أقصى': 'max',
    'التقرير الكامل للطباعة / PDF': 'The full printable report / PDF', 'التقرير الكامل للطباعة': 'The full printable report', 'مقارنة بالأيام اللي فاتت': 'Compare with previous days',
    'التقرير بيطلع آخر اليوم (الساعة 4)': 'The report comes out at the end of the day (4 pm)',
    'جديد النهارده': 'New today', 'أول مرة تظهر النهارده': 'first seen today', 'مفيش مشاكل جديدة': 'No new problems', 'لسه موجودة': 'Still open', 'ظهرت': 'seen on', 'يوم': 'days',
    'اتصلحت': 'Fixed', 'كانت ظاهرة': 'was open for', 'لسه مفيش': 'none yet', 'المقارنة الكاملة': 'The full comparison', 'بحمّل': 'loading', 'مقدرتش أجيب المقارنة': "Couldn't load the comparison",
    // ticket
    'إضافة': 'Add', 'تعديل': 'Edit', 'حذف': 'Delete', 'طباعة': 'Print', 'فتح': 'Open', 'مراجعة': 'Review', 'ادخل بمستخدم': 'Log in as', 'افتح': 'Open', 'اعمل': 'Do',
    'بنفس البيانات اللي في الدليل': 'with the same data as in the evidence', 'المتوقع: الحفظ يتم أو رسالة واضحة — اللي حصل': 'Expected: it saves or shows a clear message — what happened',
    'حركات الشاشة النهارده (سجل السيستم)': "today's activity on the screen (system log)", 'آخر سجلات الجدول (اتأكد من اسمه)': "the table's latest rows (check its name)",
    'الوقت': 'Time', 'المشكلة': 'Problem', 'الصفحة': 'Page', 'خطوات التكرار': 'Steps to reproduce', 'صورة الصفحة وقت المشكلة': 'The page at the moment of the problem',
    'مفيش صورة للمشكلة دي (بتتصور في وضع الموقع الحقيقي بس)': 'No picture for this one (pictures are taken on the real site only)', 'SQL للتأكد': 'SQL to verify', 'للتأكد': 'to verify',
    'انسخ التذكرة': 'Copy the ticket', 'ابعتها واتساب': 'Send on WhatsApp', 'ابعتها إيميل': 'Send by email', 'اتنسخت': 'copied', 'انسخ يدوي من فوق': 'copy it by hand from above',
    'الصورة مش بتتبعت مع الواتساب/الإيميل تلقائي — اضغط عليها كليك يمين ← نسخ الصورة والصقها في الرسالة': "The picture isn't attached automatically — right-click it → Copy image and paste it into the message",
    'وقفت مع': 'stopped for', 'دوس للتذكرة': 'click for the ticket',
    // employee drawer
    'مش في المكتب': 'Not in the office', 'مباشر': 'LIVE', 'شغال على': 'Working on', 'شغال': 'Working', 'متعطل في': 'Stuck in', 'مش موجود': 'Away', 'مستني': 'waiting', 'مهمة': 'tasks',
    'مهام خلصت': 'tasks done', 'اتعطل': 'got stuck', 'شكاوى': 'complaints', 'شاشته الحقيقية على NQ ERP دلوقتي': 'His real NQ ERP screen right now', 'اسأل': 'Ask',
    'عملت إيه في فاتورة الجادة؟': 'What did you do with the Al-Jadda invoice?', 'وضع التدريب: شغل': 'Training mode: his work', 'خطوة بخطوة': 'step by step', 'الدقة': 'Accuracy',
    'الخبرة بالسيستم': 'System experience', 'الصبر': 'Patience', 'اشتكى من': 'Complained about', 'يومه': 'His day', 'لسه': 'not yet', 'ماشي ': 'Walking ', 'فاضي ': 'Free ',
    'الصوت شغال': 'Voice is on', 'مقدرتش أوصل للبرنامج': "Can't reach the program",
    // the office
    'مكتب المدير': "Manager's office", 'المبيعات': 'Sales', 'الحسابات': 'Accounts', 'الاجتماعات': 'Meetings', 'المخازن': 'Warehouse', 'المشتريات': 'Purchasing', 'الخزنة': 'Cashier',
    'الموارد البشرية': 'HR', 'البوفيه': 'Pantry', 'رايح لـ': 'Going to', 'بيعمل قهوة': 'Making coffee', 'جولة الشاشات': 'screens round',
    'على NQ ERP': 'on NQ ERP', 'على السيستم': 'on the system', 'نفس المستند': 'the same document',
    // client view
    'اختبار اليوم': "Today's test", 'اختبار مباشر على النظام بموظفين افتراضيين بيشتغلوا زي الموظف الحقيقي': 'Live testing of the system by virtual employees who work like real ones',
    'الشاشات اللي اتجربت النهارده': 'Screens tested today', 'مشاكل اتصلحت واتأكدنا منها': 'Problems fixed and verified',
    'كل رقم هنا من شغل فعلي على النظام: مستندات اتسجلت واتعدلت واتطبعت، ومراجعة إنها موجودة في شاشاتها': 'Every number here comes from real work on the system: documents saved, edited, printed, and checked in their screens',
    'مستند اتعمل على النظام': 'documents made on the system', 'شاشة اتجربت': 'screens tested', 'نسبة نجاح العمليات': 'operations success rate', 'متوسط سرعة الشاشة': 'average screen speed',
    'دورة بيع كاملة اتقفلت': 'full sales cycles closed', 'موظف شغال': 'employees working', 'اليوم لسه بادئ': 'The day has just started', 'ث': 's',
    // the office boy & the new colleague
    'عم صابر · أوفيس بوي': 'Saber · office boy', 'عم صابر — أوفيس بوي': 'Saber — office boy', 'شكرًا يا عم صابر': 'Thanks, Saber', 'موظف مبيعات جديد': 'New sales colleague',
    'مكتبه جاهز في المبيعات، بس لسه ما اتفعّلش على السيستم — لما تضيفه من الإعدادات هيبدأ يشتغل زي زمايله.': "His desk in Sales is ready, but he isn't active on the system yet — add him in the settings and he starts working like his colleagues.",
    'بيعمل الشاي والقهوة في البوفيه ويوديها للموظفين على مكاتبهم. مش بيشتغل على السيستم.': "Makes tea and coffee in the pantry and brings them to the employees' desks. He doesn't work on the system.",
    // settings page
    'كل حاجة هنا محفوظة على جهازك بس — وكلمات السر متشفرة': 'Everything here is saved on your computer only — passwords are encrypted', 'رجوع للشركة': 'Back to the company',
    'اسم الشركة': 'Company name', 'طلبات العملاء في اليوم': 'Customer orders per day', 'حد اعتماد المدير (فوقه الفاتورة تروح للمدير)': "Manager's approval limit (above it the invoice goes to the manager)",
    'الشركة بتشتغل على': 'The company works on', 'سلوك تقريبي للسيستم — للتجربة والعرض': 'An approximate system — for trying out and demos', 'الحقيقي': 'the real one',
    'الموظفين بيدخلوا الموقع المختار بمستخدميهم وصلاحياتهم، والشكاوى من السيستم فعلًا': 'The employees log in to the chosen site with their own users and permissions; complaints come from the real system',
    'لغة العرض والصوت': 'Display & voice language', 'العربية — صوت خليجي': 'Arabic — Gulf voices', 'بتتطبق من أول يوم جديد: الشاشات والشات وأصوات الموظفين بالإنجليزي': 'Applies from the next new day: screens, chat and voices in English',
    'نوع اليوم': 'Day type', 'يوم عادي': 'Normal day', 'آخر الشهر — إقفال (جرد صناديق · أرصدة · قيود · كشوف · ميزان · اعتمادات)': 'Month end — closing (cash counts · balances · entries · statements · trial balance · approvals)',
    'جولة الشاشات الرئيسية كل يوم: 14 شاشة × إضافة · تعديل · طباعة · حذف (على موقع الاختبار مستندات حقيقية — بتطوّل اليوم)': 'Daily round of the main screens: 14 screens × add · edit · print · delete (real documents on the test site — makes the day longer)',
    'أظهر متصفحات الموظفين وهما شغالين (أبطأ، بس تشوفهم بعينك)': "Show the employees' browsers while they work (slower, but you see them)",
    'مكان أداة الاختبار (erp-automation) — بيها الموظفين بيحفظوا ويعدّلوا ويطبعوا ويحذفوا مستندات حقيقية على مواقع الاختبار': 'Testing tool folder (erp-automation) — with it the employees save, edit, print and delete real documents on test sites',
    'مثلًا': 'e.g.', 'أدوّر عليها جنب البرنامج)': "I'll look for it next to the program)", 'مواقع': 'Sites', 'موقع': 'Site',
    'ضيف كل المواقع اللي عايز تختبرها، واختار الموقع اللي الشركة هتشتغل عليه دلوقتي. كل موقع ليه مستخدمينه': 'Add every site you want to test and choose the one the company works on now. Each site has its own users',
    'الموظفين ومستخدمينهم على': 'Employees and their users on', 'اختبر دخول الكل': 'Test everyone\'s login', 'موظف': 'employee', 'صلاحيات كل موظف': "Each employee's permissions",
    'الشاشات اللي في المنيو بتاعه على السيستم': 'the screens in his menu on the system', 'لو سبت مستخدم الموظف فاضي، بيشتغل بمستخدم المدير': "If you leave an employee's user empty, he works with the manager's user",
    'الاسم': 'Name', 'الوظيفة': 'Job', 'الدور': 'Role', 'مستخدم': 'User', 'كلمة السر': 'Password', 'الشكل': 'Look', 'اللبس': 'Clothes', 'الدخول والصلاحيات': 'Login & permissions',
    'شاشات الشركة': "The company's screens", 'شاشات': 'screens', 'اربط تلقائي من المنيو': 'Link automatically from the menu', 'المهمة في الشركة': 'Task in the company', 'الشاشة في': 'Screen in',
    'كل مهمة في الشركة بتفتح الشاشة دي في NQ ERP على الموقع المختار. القايمة جاية من منيو المستخدمين اللي اتختبر دخولهم': 'Each task opens this screen in NQ ERP on the chosen site. The list comes from the menus of the users whose login was tested',
    'احفظ الإعدادات': 'Save settings', 'رجالي': 'Man', 'حجاب': 'Hijab', 'شماغ': 'Shemagh', 'لقيتها': 'found it', 'موقع اختبار» الحفظ حقيقي': 'test site» saving is real',
    'مالقيتهاش — من غيرها الموظفين بيفتحوا الشاشات ويقروا بس (من غير حفظ)': "Not found — without it the employees only open and read the screens (no saving)", 'مش هيظهروا في الشركة': "won't appear in the company",
    'مفيش مكتب فاضي لـ': 'No free desk for', 'الموقع اللي الشركة هتشتغل عليه': 'The site the company works on', 'شيل الموقع': 'Remove the site', 'مثلًا: موقع الاختبار': 'e.g. the test site',
    'اللينك': 'Link', 'النوع': 'Type', 'موقع اختبار (مسموح مستندات تجريبية)': 'Test site (test documents allowed)', 'نظام عميل — قراءة بس': "A client's system — read only",
    'الموقع': 'Site', 'مستخدم المدير': "Manager's user", 'محفوظة': 'saved', 'لون اللبس': 'Clothes colour', 'اختبر': 'Test', 'شاشة مسموحة': 'allowed screens', 'بمستخدم المدير': "with the manager's user",
    'اكتب لينك الموقع': "Type the site's link", 'بيدخل': 'logging in', 'دخل': 'logged in', 'أخرى': 'other', 'اختار (أو سيبها للربط التلقائي)': 'choose (or leave it to auto-link)',
    'اختبر دخول موظف الأول — أو سيبها للربط التلقائي': 'Test an employee\'s login first — or leave it to auto-link', 'اتربط': 'linked', 'راجعهم واحفظ': 'review and save',
    'اتحفظ — ارجع للشركة وابدأ يوم جديد': 'Saved — go back to the company and start a new day', 'شغال': 'Active',
    // test catalog
    'كتالوج الاختبارات': 'Test catalog', 'كل أنواع الاختبارات: اللي البرنامج بيعمله كل يوم، واللي جزء منه، واللي مخطط — ونتيجة النهارده': 'Every kind of test: what runs every day, what partly runs, what is planned — and today\'s result',
    'كل أنواع اختبارات NQ ERP: اللي شغال كل يوم واللي مخطط، ونتيجة النهارده': 'Every kind of NQ ERP test: what runs every day, what is planned, and today\'s result',
    'الكل': 'All', 'شغال كل يوم': 'Runs every day', 'جزء منه': 'Partly', 'مخطط': 'Planned', 'سيناريو اختبار': 'test scenarios', 'التغطية': 'coverage', 'نوع اختبار': 'test types', 'سيناريو': 'scenarios',
    'السيناريو': 'Scenario', 'بيتعمل إزاي': 'How', 'المتوقع': 'Expected', 'الحالة': 'Status', 'نتيجة النهارده': "Today's result", 'لسه ما اتشغلش النهارده': 'not run yet today',
    'مرة — كلها نجحت': 'times — all passed', 'من': 'of', 'ملاحظة النهارده': 'notes today', 'مفيش ملاحظات': 'no notes', 'شاشة بطيئة من': 'slow screens of', 'شاشة في الوقت': 'screens on time',
    'رفض صلاحيات': 'permission refusals', 'مفيش رفض': 'no refusals', 'موظف اشتغلوا': 'employees worked', 'اتعمل النهارده': 'done today', 'بيتعمل خلال اليوم': 'runs during the day',
    'فهد · موظف مبيعات جديد': 'Fahd · new sales colleague', 'فهد — موظف مبيعات جديد': 'Fahd — new sales colleague',
    'مكتبه جاهز في المبيعات، بس لسه ما اتفعّلش على السيستم — فعّله من الإعدادات (علامة «شغال» واديله مستخدم) وهيبدأ يشتغل زي زمايله.': "His desk in Sales is ready but he isn't active yet — switch him on in the settings (tick «Active» and give him a user) and he starts working like his colleagues.",
    'فهد': 'Fahd', 'مندوب مبيعات (جديد)': 'Sales Rep (new)',
    'يدوي / محتاج إعداد': 'Manual / needs setup', 'مخطط / يدوي': 'planned / manual', 'التغطية الآلية': 'automatic coverage', 'يدوي': 'Manual',
    'مقدرش يتحقق — شوف التفاصيل في الشكاوى/الشات': "couldn't verify — see the complaints/chat", 'محتاج مراجعة': 'need review', 'اختبار': 'Test', 'مراجعة تصميم': 'Design review',
    'اختبار: حقل إجباري فاضي': 'Test: required field empty', 'اختبار: كمية بالسالب': 'Test: negative quantity', 'اختبار: خصم 150%': 'Test: 150% discount',
    'اختبار: نص طويل وحروف خاصة': 'Test: long text & special characters', 'اختبار: رقم فاتورة مورد متكرر': 'Test: duplicate supplier invoice no.', 'اختبار: عرض سعر بـ 30 سطر': 'Test: quotation with 30 lines',
    'اختبار: رابط من غير تسجيل دخول': 'Test: link without login', 'اختبار: أسرار مكتوبة في الصفحات': 'Test: secrets in the pages', 'اختبار: الشاشات على الموبايل': 'Test: screens on mobile',
    'اختبار: الواجهة الإنجليزي': 'Test: English interface', 'اختبار: قيد الفاتورة متزن': "Test: invoice's entry balances", 'اختبار: أرقام ميزان المراجعة': 'Test: trial balance figures',
    'اختبار: اعتماد مستند': 'Test: approving a document', 'مسير الرواتب': 'Payroll', 'اختبار: الضريبة 15%': 'Test: VAT 15%',
    'الدعم الفني (IT)': 'IT Support', 'الدعم الفني': 'IT Support', 'فحص كل شاشات السيستم (IT)': 'Full system screens check (IT)', 'فحص سرعة الشاشات (IT)': 'Screens speed check (IT)', 'مراجعة شكل الشاشات (IT)': 'Screens look review (IT)', 'مراجعة قيود اليوم': 'Today\'s books review',
    'فهد (IT) يفتح كل شاشات السيستم من المنيو': 'Fahd (IT) opens every screen in the menu',
    // jobs
    'المدير العام': 'General Manager', 'المدير': 'Manager', 'مندوبة مبيعات': 'Sales Rep', 'مندوب مبيعات': 'Sales Rep', 'محاسب': 'Accountant', 'محاسبة': 'Accountant',
    'أمين مخزن': 'Storekeeper', 'مسؤول مشتريات': 'Purchasing Officer', 'أمينة صندوق': 'Cashier', 'أمين صندوق': 'Cashier', 'موارد بشرية': 'HR Officer', '(جديد)': '(new)'
  };
  // screens and people (the same lists the program uses)
  Object.assign(D, {'عروض الأسعار': 'Quotations', 'أوامر البيع': 'Sales Orders', 'كارت الصنف': 'Item Card', 'أوامر الشراء': 'Purchase Orders', 'سند استلام مخزني': 'Stock Receipt',
    'فواتير الشراء': 'Purchase Invoices', 'سند صرف مخزني': 'Stock Issue', 'فواتير البيع': 'Sales Invoices', 'القيود اليومية': 'Journal Entries', 'اعتماد المستندات': 'Document Approval',
    'سند القبض': 'Receipt Voucher', 'الحضور والانصراف': 'Attendance', 'جرد الخزينة': 'Cash Count', 'ميزان المراجعة': 'Trial Balance', 'تقرير المبيعات اليومي': 'Daily Sales Report',
    'كشف حساب مفصل': 'Detailed Account Statement', 'كشف حساب عميل': 'Customer Statement', 'مرتجع البيع': 'Sales Return', 'طلب الشراء': 'Purchase Request', 'مرتجع الشراء': 'Purchase Return',
    'سند الدفع': 'Payment Voucher', 'سند تحويل مخزني': 'Stock Transfer', 'قيد يومية': 'Journal Entry', 'فحص جاهزية الموقع': 'Site Readiness Check', 'مراجعة مستندات اليوم': "Today's Documents Audit",
    'أ. خالد': 'Mr. Khaled', 'أ. أحمد': 'Mr. Ahmed', 'أ. احمد': 'Mr. Ahmed', 'خالد': 'Khaled', 'سارة': 'Sarah', 'يوسف': 'Youssef', 'أحمد': 'Ahmed', 'نورا': 'Noura', 'محمود': 'Mahmoud',
    'عمر': 'Omar', 'منى': 'Mona', 'هبة': 'Hiba'});
  const AR = '؀-ۿ';
  const keys = Object.keys(D).sort((a, b) => b.length - a.length);
  const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const RX = new RegExp(`(?<![${AR}])(${keys.map(esc).join('|')})(?![${AR}])`, 'g');
  const tr = s => (s && /[؀-ۿ]/.test(s)) ? s.replace(RX, m => D[m] || m) : s;
  window.NQ_T = tr;
  function walk(root) {
    if (root.nodeType === 3) { const pn = root.parentNode; if (pn && /^(SCRIPT|STYLE|TEXTAREA)$/.test(pn.nodeName)) return; const t = tr(root.nodeValue); if (t !== root.nodeValue) root.nodeValue = t; return; }
    if (root.nodeType !== 1 || /^(SCRIPT|STYLE|TEXTAREA|INPUT)$/.test(root.tagName)) return;
    for (const a of ['title', 'placeholder', 'aria-label']) { const v = root.getAttribute && root.getAttribute(a); if (v) { const t = tr(v); if (t !== v) root.setAttribute(a, t); } }
    for (const c of root.childNodes) walk(c);
  }
  function go() {
    document.documentElement.lang = 'en'; document.documentElement.dir = 'ltr'; document.title = tr(document.title);
    walk(document.body);
    new MutationObserver(ms => { for (const m of ms) { if (m.type === 'characterData') walk(m.target); else m.addedNodes.forEach(walk); } })
      .observe(document.body, {childList: true, subtree: true, characterData: true});
  }
  let lang = 'ar';
  try { const x = new XMLHttpRequest(); x.open('GET', '/api/lang', false); x.send(); lang = (JSON.parse(x.responseText) || {}).lang || 'ar'; } catch (_) {}
  window.NQ_LANG = lang;
  if (lang === 'en') { if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go); else go(); }
})();
