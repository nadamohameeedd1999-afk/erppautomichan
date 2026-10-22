"""
Tests Registry — كل الاختبارات المتاحة
- نوع: full (اختبار كامل) / smoke (اختبار شاشة)
"""


class TestsRegistry:
    """سجل الاختبارات"""

    TESTS = [
        # ===== الحسابات العامة =====
        {
            "id": "journal_entries_smoke",
            "module_key": "general_accounting",
            "page_key": "journal_entries",
            "type": "smoke",
            "name_ar": "قيود التسوية اليدوية",
            "name_en": "Manual Journal Entries",
            "icon": "📝",
            "test_path": "tests/functional/test_09_general_accounting_smoke.py::test_individual_module_smoke[journal_entries]",
            "duration_estimate": 15,
            "tags": ["smoke", "accounting"],
            "available": True,
        },
        {
            "id": "expense_request_smoke",
            "module_key": "general_accounting",
            "page_key": "expense_request",
            "type": "smoke",
            "name_ar": "طلب صرف",
            "name_en": "Expense Request",
            "icon": "💸",
            "test_path": "tests/functional/test_09_general_accounting_smoke.py::test_individual_module_smoke[expense_request]",
            "duration_estimate": 15,
            "tags": ["smoke", "accounting"],
            "available": True,
        },
        {
            "id": "cash_issue_smoke",
            "module_key": "general_accounting",
            "page_key": "cash_issue",
            "type": "smoke",
            "name_ar": "سند الدفع",
            "name_en": "Cash Issue Voucher",
            "icon": "💰",
            "test_path": "tests/functional/test_09_general_accounting_smoke.py::test_individual_module_smoke[cash_issue]",
            "duration_estimate": 15,
            "tags": ["smoke", "accounting"],
            "available": True,
        },
        {
            "id": "cash_transfers_smoke",
            "module_key": "general_accounting",
            "page_key": "cash_transfers",
            "type": "smoke",
            "name_ar": "التحويلات المالية",
            "name_en": "Cash Transfers",
            "icon": "🔄",
            "test_path": "tests/functional/test_09_general_accounting_smoke.py::test_individual_module_smoke[cash_transfers]",
            "duration_estimate": 15,
            "tags": ["smoke", "accounting"],
            "available": True,
        },
        {
            "id": "inventory_boxes_smoke",
            "module_key": "general_accounting",
            "page_key": "inventory_boxes",
            "type": "smoke",
            "name_ar": "جرد الصناديق",
            "name_en": "Inventory Boxes",
            "icon": "📦",
            "test_path": "tests/functional/test_09_general_accounting_smoke.py::test_individual_module_smoke[inventory_boxes]",
            "duration_estimate": 15,
            "tags": ["smoke", "accounting"],
            "available": True,
        },
        {
            "id": "notifications_smoke",
            "module_key": "general_accounting",
            "page_key": "notifications",
            "type": "smoke",
            "name_ar": "الإشعارات",
            "name_en": "Notifications",
            "icon": "🔔",
            "test_path": "tests/functional/test_09_general_accounting_smoke.py::test_individual_module_smoke[notifications]",
            "duration_estimate": 15,
            "tags": ["smoke", "accounting"],
            "available": True,
        },
        {
            "id": "treasury_financing_smoke",
            "module_key": "general_accounting",
            "page_key": "treasury_financing",
            "type": "smoke",
            "name_ar": "تمويل الصناديق",
            "name_en": "Treasury Financing",
            "icon": "🏦",
            "test_path": "tests/functional/test_09_general_accounting_smoke.py::test_individual_module_smoke[treasury_financing]",
            "duration_estimate": 15,
            "tags": ["smoke", "accounting"],
            "available": True,
        },
        {
            "id": "utility_bill_smoke",
            "module_key": "general_accounting",
            "page_key": "utility_bill",
            "type": "smoke",
            "name_ar": "فاتورة خدمية",
            "name_en": "Utility Bill",
            "icon": "🧾",
            "test_path": "tests/functional/test_09_general_accounting_smoke.py::test_individual_module_smoke[utility_bill]",
            "duration_estimate": 15,
            "tags": ["smoke", "accounting"],
            "available": True,
        },
        {
            "id": "advance_payment_request_smoke",
            "module_key": "general_accounting",
            "page_key": "advance_payment_request",
            "type": "smoke",
            "name_ar": "طلب دفعة مقدمة",
            "name_en": "Advance Payment Request",
            "icon": "💳",
            "test_path": "tests/functional/test_09_general_accounting_smoke.py::test_individual_module_smoke[advance_payment_request]",
            "duration_estimate": 15,
            "tags": ["smoke", "accounting"],
            "available": True,
        },
        {
            "id": "advance_payment_invoice_smoke",
            "module_key": "general_accounting",
            "page_key": "advance_payment_invoice",
            "type": "smoke",
            "name_ar": "فاتورة دفعة مقدمة",
            "name_en": "Advance Payment Invoice",
            "icon": "📄",
            "test_path": "tests/functional/test_09_general_accounting_smoke.py::test_individual_module_smoke[advance_payment_invoice]",
            "duration_estimate": 15,
            "tags": ["smoke", "accounting"],
            "available": True,
        },
        {
            "id": "expenses_smoke",
            "module_key": "general_accounting",
            "page_key": "expenses",
            "type": "smoke",
            "name_ar": "تصفية العهد",
            "name_en": "Expenses Settlement",
            "icon": "💼",
            "test_path": "tests/functional/test_09_general_accounting_smoke.py::test_individual_module_smoke[expenses]",
            "duration_estimate": 15,
            "tags": ["smoke", "accounting"],
            "available": True,
        },

        # ===== حركات المبيعات =====
        {
            "id": "sales_invoice_full",
            "module_key": "sales",
            "page_key": "sales_invoice",
            "type": "full",
            "name_ar": "فاتورة البيع - كامل",
            "name_en": "Sales Invoice - Full",
            "icon": "🧾",
            "test_path": "tests/functional/test_03_sales_invoice.py::test_full_sales_invoice_flow",
            "duration_estimate": 151,
            "tags": ["full", "sales"],
            "available": True,
        },
        {
            "id": "sales_quotation_smoke",
            "module_key": "sales",
            "page_key": "sales_quotation",
            "type": "smoke",
            "name_ar": "عرض سعر بيع",
            "name_en": "Sales Quotation",
            "icon": "📋",
            "test_path": "tests/functional/test_09_general_accounting_smoke.py::test_individual_module_smoke[sales_quotation]",
            "duration_estimate": 15,
            "tags": ["smoke", "sales"],
            "available": True,
        },
        {
            "id": "sales_order_smoke",
            "module_key": "sales",
            "page_key": "sales_order",
            "type": "smoke",
            "name_ar": "أوامر البيع",
            "name_en": "Sales Orders",
            "icon": "📦",
            "test_path": "tests/functional/test_09_general_accounting_smoke.py::test_individual_module_smoke[sales_order]",
            "duration_estimate": 15,
            "tags": ["smoke", "sales"],
            "available": True,
        },
        {
            "id": "sales_return_smoke",
            "module_key": "sales",
            "page_key": "sales_return",
            "type": "smoke",
            "name_ar": "مرتجع البيع",
            "name_en": "Sales Return",
            "icon": "↩️",
            "test_path": "tests/functional/test_09_general_accounting_smoke.py::test_individual_module_smoke[sales_return]",
            "duration_estimate": 15,
            "tags": ["smoke", "sales"],
            "available": True,
        },
    ]

    @classmethod
    def get_all(cls):
        return [t for t in cls.TESTS if t.get("available", True)]

    @classmethod
    def get_by_id(cls, test_id):
        for t in cls.TESTS:
            if t["id"] == test_id:
                return t
        return None

    @classmethod
    def get_by_type(cls, test_type):
        return [t for t in cls.get_all() if t["type"] == test_type]

    @classmethod
    def get_by_module(cls, module_key):
        return [t for t in cls.get_all() if t["module_key"] == module_key]

    @classmethod
    def get_by_page(cls, page_key):
        return [t for t in cls.get_all() if t["page_key"] == page_key]

    @classmethod
    def get_stats(cls):
        tests = cls.get_all()
        return {
            "total": len(tests),
            "full": len([t for t in tests if t["type"] == "full"]),
            "smoke": len([t for t in tests if t["type"] == "smoke"]),
            "modules": len(set(t["module_key"] for t in tests)),
        }



    @classmethod
    def get_all_with_paths(cls, lang="ar"):
        """
        يرجّع كل الاختبارات مع مسارين:
        - full_path: مسار الاختبار الكامل
        - smoke_path: مسار الـ Smoke Test
        """
        result = []
        for t in cls.get_all():
            localized = cls.localize(t, lang)

            # full_path = test_path الحالي
            full_path = t["test_path"]

            # smoke_path = مسار Smoke
            page_key = t.get("page_key", "")
            smoke_path = f"tests/functional/test_09_general_accounting_smoke.py::test_individual_module_smoke[{page_key}]"

            result.append({
                **localized,
                "full_path": full_path,
                "smoke_path": smoke_path,
            })
        return result



    @classmethod
    def get_enriched(cls, lang="ar"):
        """
        يرجّع الاختبارات مع:
        - full_available: هل فيه اختبار كامل؟
        - smoke_available: هل فيه smoke؟
        - full_path / smoke_path
        - last_result: آخر نتيجة (من data/runs/results)
        """
        import json
        import re
        from pathlib import Path
        from datetime import datetime

        BASE_DIR = Path(__file__).resolve().parent.parent
        from config import paths
        RESULTS_DIR = paths.RESULTS_DIR

        # نبني خريطة: page_key → آخر نتيجة
        last_results = {}
        if RESULTS_DIR.exists():
            summaries = sorted(RESULTS_DIR.glob("summary_*.json"), reverse=True)
            for sf in summaries[:200]:
                try:
                    with open(sf, "r", encoding="utf-8") as f:
                        s = json.load(f)
                    tp = s.get("test_path", "")
                    # نستخرج page_key من مسار الاختبار
                    m = (re.search(r'\[([^\]]+)\]', tp) or re.search(r'test_screen_(\w+)\.py', tp)
                         or re.search(r'test_scn_(\w+)\.py', tp))
                    if m:
                        pk = m.group(1)
                        if pk not in last_results:
                            last_results[pk] = {
                                "outcome": ("passed" if s.get("exit_code") == 0 else "failed") if "exit_code" in s else ("passed" if s.get("failed", 0) == 0 and s.get("errors", 0) == 0 else "failed"),
                                "duration": s.get("duration_seconds", 0),
                                "timestamp": s.get("timestamp", ""),
                                "run_id": s.get("run_id", ""),
                            }
                except Exception:
                    continue

        result = []
        # كل الشاشات الممكنة (من المديولات)
        from config.modules_registry import ModulesRegistry
        all_modules = ModulesRegistry.MODULES

        # نبني set للاختبارات المعرّفة
        defined_tests = {t["page_key"]: t for t in cls.get_all()}

        # شاشات منشئ الشاشات (config/screens/*.json) — بتكسب على الاختبار القديم لنفس الشاشة
        try:
            from engine import screen_config
            screen_cfgs = {c["key"]: c for c in screen_config.list_all() if not c.get("error")}
        except Exception:
            screen_cfgs = {}
        used_screens = set()

        # نلف على كل الصفحات في كل المديولات
        for mod_key, mod_info in all_modules.items():
            for page_key, page_info in mod_info["pages"].items():
                # هل عندنا اختبار معرّف للصفحة دي؟
                defined = defined_tests.get(page_key)

                # نبني اسم مترجم
                if lang == "en":
                    name = page_info.get("name_en", page_info.get("name_ar", ""))
                else:
                    name = page_info.get("name_ar", "")

                # مسار الاختبار الكامل
                full_path = None
                smoke_path = None
                full_available = False
                smoke_available = False

                if page_key in screen_cfgs:
                    full_path = screen_config.test_path_for(page_key)
                    full_available = True
                    used_screens.add(page_key)
                    smoke_path = f"tests/functional/test_09_general_accounting_smoke.py::test_individual_module_smoke[{page_key}]"
                    smoke_available = True
                elif defined:
                    if defined["type"] == "full":
                        full_path = defined["test_path"]
                        full_available = True
                    # Smoke دايماً متاح (من test_09)
                    smoke_path = f"tests/functional/test_09_general_accounting_smoke.py::test_individual_module_smoke[{page_key}]"
                    smoke_available = True
                else:
                    # مفيش اختبار معرّف — نديله smoke فقط
                    smoke_path = f"tests/functional/test_09_general_accounting_smoke.py::test_individual_module_smoke[{page_key}]"
                    smoke_available = True

                # آخر نتيجة
                lr = last_results.get(page_key)

                result.append({
                    "id": f"{mod_key}::{page_key}",
                    "module_key": mod_key,
                    "module_name": mod_info.get(f"name_{lang}", mod_info["name_ar"]),
                    "module_icon": mod_info["icon"],
                    "page_key": page_key,
                    "name": name,
                    "icon": "🧾",
                    "url": page_info.get("url", ""),
                    "full_path": full_path,
                    "smoke_path": smoke_path,
                    "full_available": full_available,
                    "smoke_available": smoke_available,
                    "last_result": lr,
                    "duration_estimate": 150 if full_available else 15,
                    "builder": page_key in screen_cfgs,
                })

        # شاشات اتعملت في منشئ الشاشات ومش موجودة في المديولات
        for key, c in screen_cfgs.items():
            if key in used_screens:
                continue
            mod_key = c.get("module_key") or "custom"
            mod_info = all_modules.get(mod_key) or {
                "name_ar": "شاشات منشئ الشاشات", "name_en": "Screen Builder", "icon": "🧩"}
            if mod_key not in all_modules:
                mod_key = "custom"
            result.append({
                "id": f"{mod_key}::{key}",
                "module_key": mod_key,
                "module_name": mod_info.get(f"name_{lang}", mod_info["name_ar"]),
                "module_icon": mod_info["icon"],
                "page_key": key,
                "name": c["name_en"] if lang == "en" else c["name_ar"],
                "icon": c.get("icon") or "🧩",
                "url": c["list_url"],
                "full_path": screen_config.test_path_for(key),
                "smoke_path": None,
                "full_available": True,
                "smoke_available": False,
                "last_result": last_results.get(key),
                "duration_estimate": 120,
                "builder": True,
            })

        # السيناريوهات بتتعرض جوه صف الشاشة بتاعتها (قايمة "السيناريو" في صفحة الاختبارات)
        try:
            from engine import scenario_config
            scenarios = [c for c in scenario_config.list_all() if not c.get("error")]
        except Exception:
            scenarios = []
        by_screen = {}
        for c in scenarios:
            by_screen.setdefault(c["screen_key"], []).append({
                "key": c["scenario_key"],
                "name": c.get("scenario_name") or c["scenario_key"],
                "full_path": scenario_config.test_path_for(c["screen_key"], c["scenario_key"]),
                "last_result": last_results.get(c["key"]),
            })
        rows_by_page = {r["page_key"]: r for r in result}
        for sk, items in by_screen.items():
            row = rows_by_page.get(sk)
            if row is None:
                first = next(c for c in scenarios if c["screen_key"] == sk)
                row = {
                    "id": f"custom::{sk}", "module_key": "custom",
                    "module_name": "شاشات منشئ الشاشات" if lang != "en" else "Screen Builder",
                    "module_icon": "🧩", "page_key": sk,
                    "name": first.get("screen_name") or sk, "icon": "🧩", "url": first.get("list_url", ""),
                    "full_path": None, "smoke_path": None, "full_available": False, "smoke_available": False,
                    "last_result": None, "duration_estimate": 120, "builder": True,
                }
                result.append(row)
            row["scenarios"] = items
            row["full_available"] = True
            # آخر نتيجة للصف = الأحدث بين الأساسي وكل السيناريوهات
            cands = [x for x in [row.get("last_result")] + [i.get("last_result") for i in items] if x]
            if cands:
                row["last_result"] = max(cands, key=lambda x: str(x.get("timestamp") or x.get("run_id") or ""))
        for r in result:
            r.setdefault("scenarios", [])

        return result

    @classmethod
    def localize(cls, test, lang="ar"):
        if lang == "en":
            return {
                **test,
                "name": test.get("name_en", test.get("name_ar", "")),
            }
        return {
            **test,
            "name": test.get("name_ar", ""),
        }

    @classmethod
    def get_all_localized(cls, lang="ar"):
        return [cls.localize(t, lang) for t in cls.get_all()]