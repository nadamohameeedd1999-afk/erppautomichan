"""
Screen Builder command line.

  python -m engine.cli inspect  --list-url /CashReceiptVoucher [--add-url ...] [--out file.json]
  python -m engine.cli dry-run  cash_receipt            # fill only, NO save
  python -m engine.cli dry-run  --config-file my.json   # same, from an unsaved config
  python -m engine.cli run      cash_receipt            # full flow with save
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
        result = run_screen(d, _credentials(), cfg, save=save)
        return {"success": True, **result}
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
            data = cmd_inspect(a)
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
