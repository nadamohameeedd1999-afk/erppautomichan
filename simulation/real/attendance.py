"""
Hiba's real morning job: the fingerprint machine's file for today -> «سجل الحضور والإنصراف» on NQ ERP.

  1. the branch's employees come from the site itself (/Helper/GetDepartmentEmployees -> «CODE - name»)
  2. a real Excel file in the site's standard layout (كود الموظف | اسم الموظف | التاريخ | الوردية | الحضور الفعلي | الانصراف الفعلي)
     with a realistic day: most on time, a few late / leaving early, one absent — saved in runs/attendance/
  3. the screen: branch + date, «Select File» = that file, «Upload File», the lines the system read, «Save»
  4. what the system made of it: lines read, matched to an employee, late / absent, and the saved document's number
"""
import random
import re
import time
from datetime import date, datetime

from selenium.webdriver.common.by import By

from simulation.settings import RUNS

OUT = RUNS / "attendance"

EMPS_JS = """
var done = arguments[arguments.length - 1], dep = arguments[0];
fetch('/Helper/GetDepartmentEmployees?DepartmentId=' + encodeURIComponent(dep), {credentials: 'same-origin'})
  .then(function (r) { return r.json(); }).then(function (j) { done({ok: true, list: j}); })
  .catch(function (e) { done({ok: false, error: String(e)}); });
"""

ROWS_JS = """
var rows = Array.prototype.slice.call(document.querySelectorAll('#EmployeesAttendLeaveDetails tr'));
var T = function (e) { return e ? e.innerText.replace(/\\s+/g, ' ').trim() : ''; };
return rows.map(function (tr) {
  var v = function (c) { var x = tr.querySelector('.' + c); return x ? (x.value !== undefined && x.tagName === 'INPUT' ? x.value : T(x)) : ''; };
  return {code: v('EmpCodeOnFingerPrint'), emp: v('EmployeeId'), name: v('EmployeeArName'),
          absent: !!tr.querySelector('img[src*="check-mark"]'), text: T(tr).slice(0, 160)};
});
"""


def _first(e):
    return f"{type(e).__name__}: {str(e).splitlines()[0][:160]}" if str(e) else type(e).__name__


def make_file(people, day=None, rng=None):
    """people = [(code, name)] -> path of a real .xlsx in the site's standard layout"""
    import openpyxl
    rng = rng or random.Random()
    day = day or date.today()
    OUT.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "تفاصيل الحضور والانصراف"
    ws.sheet_view.rightToLeft = True
    ws.append(["كود الموظف", "اسم الموظف", "التاريخ", "الوردية", "الحضور الفعلي", "الانصراف الفعلي"])
    plan = []
    absent = rng.randrange(len(people)) if len(people) > 3 else -1
    for i, (code, name) in enumerate(people):
        if i == absent:
            ws.append([code, name, day.isoformat(), "", "", ""])
            plan.append((code, "غياب"))
            continue
        r = rng.random()
        late = rng.randint(12, 45) if r < .2 else rng.randint(-8, 6)
        early = rng.randint(15, 50) if rng.random() < .1 else rng.randint(-5, 10)
        a = 8 * 60 + late
        lv = 17 * 60 - early
        ws.append([code, name, day.isoformat(), "", f"{a // 60:02d}:{a % 60:02d}", f"{lv // 60:02d}:{lv % 60:02d}"])
        plan.append((code, "تأخير" if late > 10 else "انصراف بدري" if early > 10 else "منتظم"))
    f = OUT / f"attendance_{day.isoformat()}_{datetime.now():%H%M%S}.xlsx"
    wb.save(f)
    return f, plan


def upload(driver, base, dep="", rng=None):
    """-> result dict for the engine (kind ok / reject / error, note, evidence, doc no)"""
    t0 = time.time()
    try:
        driver.get(base.rstrip("/") + "/EmployeesAttendAndLeave/AddEdit")
        time.sleep(3)
        if "/addedit" not in driver.current_url.lower():
            return {"kind": "reject", "ms": int((time.time() - t0) * 1000),
                    "msg": f"مقدرتش أفتح شاشة الحضور: رجعني على {driver.current_url}" + (" (صلاحيات)" if "unauthor" in driver.current_url.lower() else "")}
        dep = dep or driver.execute_script("var s=document.getElementById('DepartmentId'); if(!s) return '';"
                                           "if(!s.value){var o=[].filter.call(s.options,function(o){return o.value})[0]; if(o){s.value=o.value; window.jQuery&&jQuery(s).trigger('change');}}"
                                           "return s.value;")
        driver.set_script_timeout(30)
        got = driver.execute_async_script(EMPS_JS, dep) or {}
        people = []
        for x in got.get("list") or []:
            m = re.match(r"\s*(.+?)\s+-\s+(.+)$", str(x.get("ArName") or ""))
            if m and not re.search(r"default|افتراضي|تست|test", m.group(2), re.I):
                people.append((m.group(1).strip(), m.group(2).strip()))
        if not people:
            return {"kind": "reject", "ms": int((time.time() - t0) * 1000), "msg": "مفيش موظفين للفرع على السيستم — مقدرتش أعمل ملف البصمة",
                    "evidence": str(got)[:300]}
        f, plan = make_file(people[:25], rng=rng)
        driver.find_element(By.ID, "file").send_keys(str(f))
        driver.execute_script("window.confirm=function(){return true}; GetFileData();")
        rows = []
        for _ in range(30):
            time.sleep(1)
            rows = driver.execute_script(ROWS_JS) or []
            msg = driver.execute_script("var m=document.getElementById('Message'); return m? m.innerText.trim() : ''")
            if rows or msg:
                break
        if not rows:
            return {"kind": "reject", "ms": int((time.time() - t0) * 1000), "msg": f"السيستم ما قراش ملف البصمة: «{msg or 'مفيش ولا سطر'}»",
                    "evidence": f"📎 الملف: {f.name} ({len(people)} موظف)"}
        unmatched = [r["code"] for r in rows if not r.get("emp") or r["emp"] in ("0", "null", "")]
        absent = [r["code"] for r in rows if r.get("absent")]
        expected_absent = [c for c, w in plan if w == "غياب"]
        wrong_absent = [c for c in absent if c not in expected_absent]        # had times in the file, the system says absent
        before = driver.current_url
        driver.execute_script("window.confirm=function(){return true}; window.__al=[]; window.alert=function(m){window.__al.push(String(m))};"
                              "if(typeof addEdit==='function') addEdit();")
        for _ in range(20):
            time.sleep(1)
            if driver.current_url != before:
                break
        alerts = driver.execute_script("return (window.__al||[]).concat([].map.call(document.querySelectorAll('.swal2-popup'),function(p){return p.innerText}))") or []
        saved = driver.current_url != before or any(re.search(r"تم الحفظ|Saved", a) for a in alerts)
        ms = int((time.time() - t0) * 1000)
        ev = (f"📎 الملف: {f.name} — {len(people)} موظف من الفرع\n"
              f"📄 السيستم قرا {len(rows)} سطر · مش متطابق مع موظف: {len(unmatched)} · غياب: {len(absent)}"
              + (f"\n⚠️ اتسجلوا غياب وهما ليهم حضور في الملف: {', '.join(wrong_absent)}" if wrong_absent else ""))
        if not saved:
            said = "؛ ".join(a.strip()[:150] for a in alerts if a.strip()) or "مفيش رسالة"
            return {"kind": "reject", "ms": ms, "msg": f"السيستم رفض حفظ سجل الحضور: «{said}»", "evidence": ev}
        if wrong_absent:
            return {"kind": "wrong", "ms": ms, "msg": f"ملف البصمة اتحفظ بس السيستم سجل {len(wrong_absent)} غياب لناس ليهم حضور وانصراف في الملف ({', '.join(wrong_absent[:5])})",
                    "evidence": ev, "did": "write"}
        return {"kind": "ok", "ms": ms, "did": "write", "evidence": ev,
                "note": f"رفعت ملف البصمة بتاع النهارده ({len(rows)} موظف) واتحفظ — غياب {len(absent)}، مش متطابق {len(unmatched)}"}
    except Exception as e:
        return {"kind": "error", "ms": int((time.time() - t0) * 1000), "msg": "رفع ملف البصمة: " + _first(e), "tool": True}
