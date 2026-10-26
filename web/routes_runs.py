"""Running tests, status, logs, exports, Allure (التشغيل والتصدير).
Routes keep their names (url_for('export_pdf') still works): registered on the app by register(app)."""
from datetime import datetime
from pathlib import Path

from flask import (jsonify, render_template, request, Response)

from config import paths
from web import auth, data_helper, export_helper
from web.config import Config
from web.i18n_helper import get_current_lang
from web.queue_manager import get_manager as get_qm

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

@route("/export/json")
@auth.login_required
def export_json():
    summaries = data_helper.load_summaries()
    content = export_helper.export_to_json(summaries)
    filename = f"erp_reports_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return Response(content, mimetype="application/json",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@route("/export/csv")
@auth.login_required
def export_csv():
    summaries = data_helper.load_summaries()
    content = export_helper.export_to_csv(summaries)
    filename = f"erp_reports_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(content, mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@route("/export/excel")
@auth.login_required
def export_excel():
    summaries = data_helper.load_summaries()
    content = export_helper.export_to_excel(summaries)
    filename = f"erp_reports_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(content,
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@route("/export/pdf")
@auth.login_required
def export_pdf():
    summaries = data_helper.load_summaries()
    content = export_helper.export_to_pdf(summaries)
    filename = f"erp_reports_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(content, mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


MAX_REPEAT = 50


def _repeat_from_request(test_path):
    """عدد التكرار من الطلب (من 1 لـ MAX_REPEAT). اختبارات [param] بتتشغل مرة واحدة."""
    data = request.get_json(silent=True) or {}
    try:
        n = int(data.get("repeat", 1))
    except (TypeError, ValueError):
        n = 1
    n = max(1, min(MAX_REPEAT, n))
    if "[" in test_path:
        n = 1
    return n


@route("/api/run-test", methods=["POST"])
@auth.login_required
def run_test():
    data = request.get_json() or {}
    test_path = data.get("test_path", "").strip()
    test_name = data.get("test_name", "اختبار").strip()

    if not test_path:
        return jsonify({"success": False, "error": "test_path required"}), 400

    task_id = f"run_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    qm = get_qm()
    result = qm.add(task_id, test_path, test_name, repeat=_repeat_from_request(test_path))

    return jsonify({
        "success": True,
        "task_id": task_id,
        "queued": result["queued"],
        "repeat": _repeat_from_request(test_path),
        "position": result["position"],
    })


@route("/api/status/<task_id>")
@auth.login_required
def task_status(task_id):
    """حالة المهمة - يشتغل من QueueManager أو من ملفات الـ results"""
    qm = get_qm()
    task = qm.get_task(task_id)

    # لو المهمة موجودة في QueueManager
    if task:
        status = task.get("status", "unknown")

        # لو خلصت أو فشلت، نرجّع التقرير
        if status in ("completed", "failed", "stopped", "error"):
            return jsonify({
                "status": status,
                "running": False,
                "task": task,
                "duration_seconds": task.get("duration_seconds"),
                "exit_code": task.get("exit_code"),
                "summary": qm.read_summary(task_id),
            })

        # لو لسه شغالة
        if status == "running":
            return jsonify({
                "status": "running",
                "running": True,
                "task": task,
            })

        # queued
        if status == "queued":
            return jsonify({
                "status": "queued",
                "running": False,
                "task": task,
            })

    # لو مش موجودة في QueueManager، نشوف ملف الـ summary
    summary_file = Config.RESULTS_DIR / f"summary_{task_id}.json"
    if summary_file.exists():
        summary = qm.read_summary(task_id)
        return jsonify({
            "status": "completed",
            "running": False,
            "summary": summary,
            "source": "file",
        })

    # لو مفيش أي حاجة، نرجع unknown مع رسالة
    return jsonify({
        "status": "unknown",
        "running": False,
        "message": "Task not found in queue or files",
    })


@route("/api/queue")
@auth.login_required
def queue_status():
    qm = get_qm()
    return jsonify(qm.get_status())


@route("/api/stop", methods=["POST"])
@auth.login_required
def stop_test():
    qm = get_qm()
    if qm.stop_current():
        return jsonify({"success": True, "message": "Test stopping"})
    return jsonify({"success": False, "message": "No test running"})

@route("/api/log/<task_id>")
@auth.login_required
def api_get_log(task_id):
    """يقرأ لوج اختبار"""
    qm = get_qm()
    max_lines = int(request.args.get("lines", 200))
    result = qm.read_log(task_id, max_lines=max_lines)
    return jsonify(result)


@route("/api/registry/tests")
@auth.login_required
def api_registry_tests():
    """يرجّع كل الاختبارات (enriched)"""
    from config.tests_registry_new import TestsRegistry
    lang = get_current_lang()
    try:
        tests = TestsRegistry.get_enriched(lang)
        return jsonify({
            "success": True,
            "tests": tests,
            "stats": TestsRegistry.get_stats(),
        })
    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e)[:500], "trace": traceback.format_exc()[:1000]}), 500


@route("/allure")
@auth.login_required
def allure_index():
    """صفحة Allure"""
    return render_template("allure.html")


def _find_allure_cli():
    """يدوّر على allure CLI في أماكن معروفة"""
    import shutil
    from pathlib import Path

    # 1) PATH
    found = shutil.which("allure")
    if found:
        return found

    # 2) C:\allure\bin\allure.bat
    candidates = [
        Path("C:/allure/bin/allure.bat"),
        Path("C:/allure/bin/allure"),
        Path("C:/Program Files/allure/bin/allure.bat"),
        Path.home() / "scoop" / "shims" / "allure.bat",
        Path("C:/ProgramData/chocolatey/bin/allure.bat"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    return None


@route("/api/allure/generate", methods=["POST"])
@auth.login_required
def api_allure_generate():
    """يولّد تقرير Allure"""
    import subprocess
    import shutil

    allure_results = paths.ALLURE_RESULTS_DIR
    allure_report = paths.ALLURE_REPORT_DIR

    if not allure_results.exists():
        return jsonify({"success": False, "error": "No allure-results folder"})

    # ندور على allure CLI
    allure_cli = _find_allure_cli()
    if not allure_cli:
        return jsonify({
            "success": False,
            "error": "Allure CLI not found. Install from: https://github.com/allure-framework/allure2/releases",
            "hint": "Then place it at C:\\allure and add to PATH"
        })

    # نشيل القديم
    if allure_report.exists():
        try:
            shutil.rmtree(allure_report, ignore_errors=True)
        except Exception:
            pass

    # نشغّل allure generate
    try:
        # على Windows، allure.bat محتاج shell=True
        if allure_cli.endswith(".bat"):
            cmd = f'"{allure_cli}" generate "{allure_results}" -o "{allure_report}" --clean'
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
        else:
            result = subprocess.run(
                [allure_cli, "generate", str(allure_results), "-o", str(allure_report), "--clean"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )

        if result.returncode == 0 and (allure_report / "index.html").exists():
            return jsonify({
                "success": True,
                "message": "Report generated successfully",
                "cli": allure_cli,
                "report_path": str(allure_report),
            })
        else:
            return jsonify({
                "success": False,
                "error": (result.stderr or result.stdout or "Unknown error")[:500],
                "cli": allure_cli,
                "returncode": result.returncode,
            })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)[:300], "cli": allure_cli})


@route("/allure-report/<path:filename>")
@auth.login_required
def serve_allure_report(filename):
    """يقدم ملفات تقرير Allure"""
    from flask import send_from_directory
    allure_report = paths.ALLURE_REPORT_DIR
    return send_from_directory(str(allure_report), filename)


@route("/api/allure/status")
@auth.login_required
def api_allure_status():
    """حالة Allure"""
    allure_results = paths.ALLURE_RESULTS_DIR
    allure_report = paths.ALLURE_REPORT_DIR

    allure_cli = _find_allure_cli()

    results_count = 0
    if allure_results.exists():
        results_count = len(list(allure_results.glob("*-result.json")))

    return jsonify({
        "success": True,
        "cli_installed": allure_cli is not None,
        "cli_path": allure_cli,
        "results_exist": allure_results.exists(),
        "results_count": results_count,
        "report_exists": allure_report.exists(),
        "report_index": (allure_report / "index.html").exists(),
    })
