"""
🛡️ الصلاحيات والفصل بين المهام (Segregation of Duties) — read only, no setup.
Reads from NQ ERP itself (GET only, the same data the privilege screens load):
  • the users          — «صلاحيات المستخدمين» (/UserPrivilege: the user list) + «المستخدمين» (/ERPUsers: each user's group)
  • each user's rights — /UserPrivilege/AllPages?id=<user>   [{Page, Action, Privileged}]
  • each group's rights— /RolePrivilege/AllPages?id=<group>
effective rights = the user's own ∪ his group's. Then checks the classic conflicts (one person can do both sides of a
money / stock cycle alone) + who can change permissions. Accepted exceptions: cfg["allow"] = ["<user>|<rule key>", …].
"""
import re

from utils.logger import logger

ADD, EDIT, DEL, ANY = {"اضافة", "إضافة", "حفظ"}, {"تعديل"}, {"حذف"}, None

# key, title, why, [(page regex, actions)] — every side must be allowed for the conflict to count
RULES = [
    ("vendor_pay", "إنشاء مورد + الدفع له", "يقدر يعمل مورد وهمي ويصرف له فلوس من غير ما حد تاني يشوف",
     [(r"^الموردين$", ADD | EDIT), (r"^سند الدفع$|سداد موردين", ADD)]),
    ("vendor_invoice", "إنشاء مورد + فاتورة شراء", "يقدر يسجل فاتورة لمورد هو اللي عمله",
     [(r"^الموردين$", ADD | EDIT), (r"^فواتير الشراء", ADD)]),
    ("purchase_cycle", "أمر شراء + استلام + فاتورة شراء", "دورة الشراء كلها في إيد شخص واحد (يطلب ويستلم ويفوتر)",
     [(r"^اوامر الشراء$|^أوامر الشراء$", ADD), (r"^سندات استلام المخازن$", ADD), (r"^فواتير الشراء", ADD)]),
    ("sales_receipt", "فاتورة بيع + سند قبض", "يقدر يبيع ويحصّل ويعدّل الفاتورة بعدها (lapping)",
     [(r"^فواتير البيع", ADD | EDIT | DEL), (r"^سند القبض$|^سند قبض متعدد العملاء$", ADD)]),
    ("price_sell", "تعديل أسعار الأصناف + البيع", "يقدر ينزّل السعر ويبيع بيه",
     [(r"^الأصناف$|مخطط تسعير الأصناف|رفع قوائم الاسعار", EDIT | ADD), (r"^فواتير البيع", ADD)]),
    ("stock_count", "الجرد + حركة المخزن", "يقدر يصرف بضاعة ويغطيها في الجرد",
     [(r"^سندات الجرد$|^بدء الجرد الفعلي$", ADD | EDIT), (r"^سندات صرف المخازن$|^سندات استلام المخازن$", ADD)]),
    ("cash_count", "جرد الصندوق + سندات الصندوق", "يقدر يصرف من الصندوق ويغطي العجز في الجرد",
     [(r"^جرد الصناديق$|^ضبط ارصدة الصناديق$", ADD | EDIT), (r"^سند الدفع$|^سند القبض$", ADD)]),
    ("je_bank", "قيود يدوية + التسويات البنكية", "يقدر يعمل قيد ويطابقه في تسوية البنك بنفسه",
     [(r"^قيود التسوية اليدوية$", ADD | EDIT), (r"^التسويات البنكية$|^مطابقات البنوك$", ADD | EDIT)]),
    ("payroll", "بيانات الموظفين + مسير البنك", "يقدر يضيف موظف أو يغير راتبه ويصرفه",
     [(r"^الموظفين$|^عقود الموظفين$", ADD | EDIT), (r"^مسير البنك$", ADD | EDIT)]),
    ("security", "تعديل الصلاحيات", "يقدر يدي نفسه أو غيره أي صلاحية",
     [(r"^صلاحية المستخدم$|^صلاحيات المجموعات$|^المستخدمين$|^مجموعات المستخدمين$", ADD | EDIT)]),
]

FIN_DOC = re.compile(r"^(فواتير|فاتورة|سند|قيود|سندات)")

READ_JS = r"""
const [maxUsers, done] = [arguments[0], arguments[arguments.length - 1]];
(async () => {
  const html = async u => { const r = await fetch(u, {credentials: 'include'}); return r.ok ? new DOMParser().parseFromString(await r.text(), 'text/html') : null; };
  const opts = (d, sel) => d ? [...d.querySelectorAll(sel + ' option')].filter(o => o.value).map(o => [o.value, o.textContent.trim()]) : [];
  const priv = async u => { try { const r = await fetch(u, {credentials: 'include'}); const a = await r.json(); const m = {};
      a.filter(x => +x.Privileged === 1).forEach(x => { const p = (x.Page || '').trim(); (m[p] = m[p] || []).push((x.Action || '').trim()); }); return m; }
    catch (e) { return null; } };
  const up = await html('/UserPrivilege'), rp = await html('/RolePrivilege'), ul = await html('/ERPUsers');
  if (!up) return done({err: 'مقدرتش أفتح «صلاحيات المستخدمين» (/UserPrivilege)'});
  const groupOf = {};
  if (ul) for (const t of ul.querySelectorAll('table')) {
    const h = [...t.querySelectorAll('thead th')].map(x => x.textContent.trim());
    const iu = h.indexOf('اسم المستخدم'), ig = h.indexOf('المجموعة');
    if (iu < 0 || ig < 0) continue;
    t.querySelectorAll('tbody tr').forEach(tr => { const c = tr.cells; if (c[iu]) groupOf[c[iu].textContent.trim()] = (c[ig] || {}).textContent.trim(); });
  }
  const roles = opts(rp, '#RoleId').map(([id, t]) => ({id, name: t.replace(/^-?\d+\s*-\s*/, '').trim()}));
  for (const r of roles) r.priv = await priv('/RolePrivilege/AllPages?id=' + r.id);
  const users = [];
  for (const [id, t] of opts(up, '#UserId').slice(0, maxUsers)) {
    const parts = t.split(' - ').map(x => x.trim());
    users.push({id, user: parts[0], name: parts[1] || '', employee: parts[2] || '', group: groupOf[parts[0]] || '',
                priv: await priv('/UserPrivilege/AllPages?id=' + id)});
  }
  done({users, roles: roles.map(r => ({id: r.id, name: r.name, priv: r.priv}))});
})().catch(e => done({err: String(e)}));
"""


def effective(user, roles):
    """user's own rights ∪ his group's -> {page: set(actions)}"""
    out = {p: set(a) for p, a in (user.get("priv") or {}).items()}
    g = (user.get("group") or "").strip()
    for r in roles:
        if g and r.get("name") == g:
            for p, a in (r.get("priv") or {}).items():
                out.setdefault(p, set()).update(a)
    return out


def _side(rights, rx, acts):
    m = re.compile(rx)
    hits = []
    for p, a in rights.items():
        if m.search(p.strip()):
            got = a if acts is ANY else (a & acts)
            if got:
                hits.append(f"{p.strip()} ({'، '.join(sorted(got))})")
    return hits


def conflicts(rights, allow=(), who=""):
    out = []
    for key, title, why, sides in RULES:
        if f"{who}|{key}" in allow or f"*|{key}" in allow:
            continue
        ev = [_side(rights, rx, acts) for rx, acts in sides]
        if all(ev):
            out.append((key, title, why, " + ".join(e[0] + (f" و{len(e) - 1} غيرها" if len(e) > 1 else "") for e in ev)))
    return out


def analyse(data, cfg=None):
    """-> rows for the report, list of failures"""
    cfg = cfg or {}
    allow = set(cfg.get("allow") or [])
    rows, fails = [], []
    roles = data.get("roles") or []
    for u in data.get("users") or []:
        who = f"{u.get('user')} — {u.get('name') or u.get('employee')}" + (f" ({u['group']})" if u.get("group") else "")
        if u.get("priv") is None:
            rows.append({"cells": [who, "📥 قراءة الصلاحيات", "مقدرتش أقرا صلاحياته"], "ok": None})
            continue
        rights = effective(u, roles)
        n = sum(len(a) for a in rights.values())
        if not n:
            rows.append({"cells": [who, "الصلاحيات", "مفيش أي صلاحية متسجلة له (يا مشرف عام بيعدي الصلاحيات، يا مش شغال)"], "ok": None})
            continue
        found = conflicts(rights, allow, u.get("user"))
        for key, title, why, ev in found:
            rows.append({"cells": [who, f"⚠️ {title}", f"{why} — {ev}"], "ok": False, "rule": key})
            fails.append(f"{who}: {title}")
        dels = sorted(p.strip() for p, a in rights.items() if a & DEL and FIN_DOC.search(p.strip()))
        if dels:
            rows.append({"cells": [who, "🗑️ حذف مستندات مالية", f"{len(dels)} شاشة: " + "، ".join(dels[:8]) + (" …" if len(dels) > 8 else "")
                                   + " — الأفضل الإلغاء بدل الحذف عشان يفضل أثر"], "ok": None})
        if not found:
            rows.append({"cells": [who, "✅ الفصل بين المهام", f"{len(rights)} شاشة · {n} صلاحية — مفيش تعارض"], "ok": True})
    return rows, fails


def run_sod(driver, credentials, cfg, result=None):
    from engine.screen_runner import login
    from config.settings import BASE_URL
    result = result if result is not None else {}
    login(driver, credentials)
    driver.get(BASE_URL.rstrip("/") + "/Home")
    driver.set_script_timeout(900)
    data = driver.execute_async_script(READ_JS, int(cfg.get("max_users") or 200)) or {}
    if data.get("err"):
        raise AssertionError("🛡️ الصلاحيات: " + data["err"])
    rows, fails = analyse(data, cfg)
    result["detail"] = {"title": "🛡️ الصلاحيات والفصل بين المهام", "columns": ["المستخدم", "القاعدة", "النتيجة"], "rows": rows,
                        "note": f"{len(data.get('users') or [])} مستخدم · {len(RULES)} قاعدة تعارض · من شاشات الصلاحيات على الموقع نفسه (قراءة بس)"
                                " · استثناء مقبول: ضيفيه في الإعدادات «المستخدم|القاعدة»"}
    logger.info(f"🛡️ {len(data.get('users') or [])} مستخدم · {len(fails)} تعارض")
    if fails:
        e = AssertionError(f"الفصل بين المهام: {len(fails)} تعارض\n   " + "\n   ".join(fails[:15]))
        e.partial_result = result
        raise e
    logger.success("✅ مفيش تعارض في الصلاحيات")
    return result
