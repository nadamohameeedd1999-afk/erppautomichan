"""
Screen Builder command line.

  python -m engine.cli inspect  --list-url /CashReceiptVoucher [--add-url ...] [--out file.json]
  python -m engine.cli dry-run  cash_receipt            # fill only, NO save
  python -m engine.cli dry-run  --config-file my.json   # same, from an unsaved config
  python -m engine.cli run      cash_receipt            # full flow with save
  python -m engine.cli inspect-popup --config-file draft.json --open "ربط بمستند اخر" [--after CustomerId]
  python -m engine.cli sync                             # re-create missing tests/screens stubs

The dashboard calls the same commands in the background and reads --out.
"""
import argparse
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


_PROFILE_DIRS = []


def _driver():
    """Own temporary Chrome profile, so it never clashes with a test that is running from the queue."""
    import tempfile
    from tests.conftest import _build_options, _create_driver
    opts = _build_options()
    prof = tempfile.mkdtemp(prefix="screen_builder_chrome_")
    _PROFILE_DIRS.append(prof)
    opts.add_argument(f"--user-data-dir={prof}")
    d = _create_driver(opts)
    d.set_page_load_timeout(60)
    d.set_script_timeout(60)
    d.implicitly_wait(1)
    return d


def _credentials():
    from config.settings import USERNAME, PASSWORD
    return {"username": USERNAME, "password": PASSWORD}


def _write(out, data):
    text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8")
    print("@@RESULT@@")
    print(text)


def _browser_died(e):
    t = f"{type(e).__name__} {e}".lower()
    return any(w in t for w in ("invalidsessionid", "disconnected", "unable to receive message from renderer",
                                "chrome not reachable", "session deleted", "tab crashed"))


def _with_retry(fn):
    """Read-only commands (inspect / inspect-popup): if Chrome itself crashes, start a new one and try once more."""
    try:
        return fn()
    except Exception as e:
        if not _browser_died(e):
            raise
        from utils.logger import logger
        logger.warning("⚠️ المتصفح وقع (مش غلط في الشاشة) — بفتح متصفح جديد وبعيد مرة كمان")
        return fn()


def cmd_inspect(a):
    from engine.form_inspector import FormInspector
    from engine.screen_runner import login
    d = _driver()
    try:
        login(d, _credentials())
        data = FormInspector(d).inspect(a.list_url, a.add_url or "", a.add_button or "",
                                        find_dependencies=not a.no_deps)
        return {"success": True, **data}
    finally:
        try:
            d.quit()
        except Exception:
            pass


def cmd_record(a):
    from engine.form_inspector import FormInspector
    from engine.recorder import record, convert
    from engine.screen_runner import login
    cfg = _load_cfg(a)
    d = _driver()
    try:
        login(d, _credentials())
        FormInspector(d).open_add_page(cfg["list_url"], cfg.get("add_url", ""), cfg.get("add_button", ""))
        events = record(d, max_minutes=a.minutes)
        items = convert(events)
        return {"success": True, "items": items, "events": len(events)}
    finally:
        try:
            d.quit()
        except Exception:
            pass


def cmd_discover(a):
    from engine.discover import discover
    from engine.screen_runner import login
    from config.screens_catalog import all_pages, discovered, save_discovered
    d = _driver()
    try:
        login(d, _credentials())
        known = [p["url"] for p in all_pages().values() if p["module_key"] != "discovered"]
        res = discover(d, check=not a.no_check, limit=a.limit, known_urls=known)
        # keep earlier discoveries, add the new ones (never removes)
        cur = {x["key"]: x for x in discovered()}
        new = [x for x in res["screens"] if not x["known"] and x["key"] not in cur]
        for x in res["screens"]:
            if not x["known"]:
                cur[x["key"]] = {k: x[k] for k in ("key", "name", "group", "url")}
        save_discovered(list(cur.values()))
        return {"success": True, **res, "added": len(new)}
    finally:
        try:
            d.quit()
        except Exception:
            pass


def cmd_inspect_popup(a):
    from engine.form_inspector import inspect_popup
    from engine.screen_runner import login
    cfg = _load_cfg(a)
    d = _driver()
    try:
        login(d, _credentials())
        choose = [c for c in (a.choose or "").split("|") if c.strip()]
        return {"success": True, **inspect_popup(d, cfg, a.open, a.after or "", choose)}
    finally:
        try:
            d.quit()
        except Exception:
            pass


def _load_cfg(a):
    from engine import screen_config
    if a.config_file:
        cfg = json.loads(Path(a.config_file).read_text(encoding="utf-8-sig"))
        return screen_config.normalize(cfg)
    return screen_config.load(a.key)


def cmd_fill(a, save):
    from engine.screen_runner import run_screen
    from engine.form_filler import FieldFillError
    cfg = _load_cfg(a)
    d = _driver()
    result = {"key": cfg["key"], "steps": []}
    try:
        if save and (cfg.get("run_before") or cfg.get("run_after") or cfg.get("data_file")):
            from engine.screen_runner import _run_with_extras, RUN_VARS
            _run_with_extras(d, _credentials(), cfg)
            return {"success": True, "key": cfg["key"], "steps": [], "vars": dict(RUN_VARS)}
        result = run_screen(d, _credentials(), cfg, save=save)
        from engine.screen_runner import RUN_VARS
        return {"success": True, **result, "vars": dict(RUN_VARS)}
    except (FieldFillError, AssertionError) as e:
        result = getattr(e, "partial_result", None) or result
        return {"success": False, **result, "error": str(e)}
    finally:
        try:
            d.quit()
        except Exception:
            pass


def main(argv=None):
    p = argparse.ArgumentParser(prog="engine.cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("inspect")
    i.add_argument("--list-url", required=True)
    i.add_argument("--add-url", default="")
    i.add_argument("--add-button", default="")
    i.add_argument("--no-deps", action="store_true", help="don't detect dependent dropdowns")
    i.add_argument("--out", default="")

    rc = sub.add_parser("record")
    rc.add_argument("--config-file", required=True)
    rc.add_argument("--minutes", type=int, default=20)
    rc.add_argument("--out", default="")
    rc.add_argument("key", nargs="?", default="")

    dc = sub.add_parser("discover")
    dc.add_argument("--no-check", action="store_true")
    dc.add_argument("--limit", type=int, default=200)
    dc.add_argument("--out", default="")

    ip = sub.add_parser("inspect-popup")
    ip.add_argument("--config-file", required=True)
    ip.add_argument("--open", required=True, help="text / css of the button that opens the pop-up")
    ip.add_argument("--after", default="")
    ip.add_argument("--choose", default="", help="values to pick in the pop-up first, separated by |")
    ip.add_argument("--out", default="")
    ip.add_argument("key", nargs="?", default="")

    for name in ("dry-run", "run"):
        r = sub.add_parser(name)
        r.add_argument("key", nargs="?", default="")
        r.add_argument("--config-file", default="")
        r.add_argument("--out", default="")

    s = sub.add_parser("sync")
    s.add_argument("--out", default="")

    a = p.parse_args(argv)
    try:
        if a.cmd == "inspect":
            data = _with_retry(lambda: cmd_inspect(a))
        elif a.cmd == "record":
            data = cmd_record(a)
        elif a.cmd == "discover":
            data = _with_retry(lambda: cmd_discover(a))
        elif a.cmd == "inspect-popup":
            data = _with_retry(lambda: cmd_inspect_popup(a))
        elif a.cmd in ("dry-run", "run"):
            if not a.key and not a.config_file:
                p.error("اكتب اسم الشاشة أو --config-file")
            data = cmd_fill(a, save=(a.cmd == "run"))
        else:
            from engine import screen_config
            data = {"success": True, "created": screen_config.sync_stubs()}
    except Exception as e:
        data = {"success": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-2000:]}
    _write(a.out, data)
    import shutil
    for prof in _PROFILE_DIRS:
        shutil.rmtree(prof, ignore_errors=True)
    return 0 if data.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
