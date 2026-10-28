"""
Screen Builder command line.

  python -m engine.cli inspect  --list-url /CashReceiptVoucher [--add-url ...] [--out file.json]
  python -m engine.cli dry-run  cash_receipt            # fill only, NO save
  python -m engine.cli dry-run  --config-file my.json   # same, from an unsaved config
  python -m engine.cli run      cash_receipt            # full flow with save
  python -m engine.cli inspect-popup --config-file draft.json --open "ربط بمستند اخر" [--after CustomerId]
  python -m engine.cli check    --config-file chk.json  # an advanced test (cycle / report / permission / perf)
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
    import time
    for attempt in range(3):                   # Chrome sometimes fails to start on a busy server — try again
        opts = _build_options()
        prof = tempfile.mkdtemp(prefix="screen_builder_chrome_")
        _PROFILE_DIRS.append(prof)
        opts.add_argument(f"--user-data-dir={prof}")
        try:
            d = _create_driver(opts)
            break
        except Exception as e:
            if attempt == 2 or "session not created" not in str(e).lower():
                raise
            print(f"Chrome ما فتحش ({str(e).splitlines()[0][:80]}) — بجرب تاني", flush=True)
            time.sleep(2)
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


def _raise_crash(data):
    """cmd_fill returns errors as data; turn a Chrome crash into an exception so _with_retry can retry"""
    if not data.get("success") and _browser_died(Exception(str(data.get("error", "")))):
        raise RuntimeError(data.get("error"))
    return data


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

    def opened():                       # Chrome crashing while opening is retried (nothing was recorded yet)
        d = _driver()
        try:
            login(d, _credentials())
            FormInspector(d).open_add_page(cfg["list_url"], cfg.get("add_url", ""), cfg.get("add_button", ""))
            return d
        except Exception:
            try:
                d.quit()
            except Exception:
                pass
            raise
    d = _with_retry(opened)
    try:
        events = record(d, max_minutes=a.minutes, stop_file=a.stop_file or None)
        items = convert(events)
        return {"success": True, "items": items, "events": len(events)}
    finally:
        try:
            d.quit()
        except Exception:
            pass


def cmd_discover(a):
    from engine.discover import discover, Progress
    from engine.screen_runner import login
    from config.screens_catalog import all_pages, discovered, save_discovered
    prog = Progress(a.progress or None)
    d = _driver()
    try:
        login(d, _credentials())
        known = [p["url"] for p in all_pages().values() if p["module_key"] != "discovered"]
        skip = None if a.skip is None else [s.strip() for s in a.skip.replace("،", ",").split(",") if s.strip()]
        res = discover(d, check=not a.no_check, limit=a.limit, known_urls=known, progress=prog, skip=skip, deep=a.deep)
        added = 0
        if not a.no_save:                          # command line: add every new screen
            cur = {x["key"]: x for x in discovered()}
            for x in res["screens"]:
                if not x["known"] and x["key"] not in cur:
                    cur[x["key"]] = {k: x[k] for k in ("key", "name", "name_en", "group", "url")}
                    added += 1
            save_discovered(list(cur.values()))
        return {"success": True, **res, "added": added}
    except Exception as e:
        prog.step(f"❌ {str(e).splitlines()[0][:150]}", phase="error")
        raise
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


def cmd_check(a):
    from engine import checks
    from engine.check_runner import run_check
    if a.config_file:
        cfg = checks.normalize(json.loads(Path(a.config_file).read_text(encoding="utf-8-sig")))
    else:
        cfg = checks.load(a.key)
    d = _driver()
    result = {"key": cfg["key"]}
    try:
        result = run_check(d, _credentials(), cfg)
        return {"success": True, **result}
    except AssertionError as e:
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
    rc.add_argument("--stop-file", default="", help="recording ends when this file appears (the dashboard's «⏹ خلصت»)")
    rc.add_argument("--out", default="")
    rc.add_argument("key", nargs="?", default="")

    dc = sub.add_parser("discover")
    dc.add_argument("--no-check", action="store_true")
    dc.add_argument("--limit", type=int, default=200)
    dc.add_argument("--no-save", action="store_true", help="only report; the dashboard adds the screens the user picks")
    dc.add_argument("--progress", default="")
    dc.add_argument("--skip", default=None, help="skip links containing these words, comma separated (default: login,logout,tickets…)")
    dc.add_argument("--deep", action="store_true", help="also follow the links found inside each opened page")
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

    ck = sub.add_parser("check")
    ck.add_argument("key", nargs="?", default="")
    ck.add_argument("--config-file", default="")
    ck.add_argument("--out", default="")

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
            if a.cmd == "dry-run":                      # fills only -> safe to retry if Chrome crashes
                data = _with_retry(lambda: _raise_crash(cmd_fill(a, save=False)))
            else:
                data = cmd_fill(a, save=True)
        elif a.cmd == "check":
            if not a.key and not a.config_file:
                p.error("اكتب اسم الاختبار أو --config-file")
            data = cmd_check(a)
        else:
            from engine import screen_config, checks
            data = {"success": True, "created": screen_config.sync_stubs() + checks.sync_stubs()}
    except Exception as e:
        data = {"success": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-2000:]}
    _write(a.out, data)
    import shutil
    for prof in _PROFILE_DIRS:
        shutil.rmtree(prof, ignore_errors=True)
    return 0 if data.get("success") else 1


if __name__ == "__main__":
    sys.exit(main())
