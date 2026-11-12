"""
Background ticker — runs inside the dashboard every ~20 s: the daily report e-mail, the monthly client reports and the
automatic backups. (It used to be part of the «الجدولة» schedules screen, which was removed from the project.)
Set BACKGROUND=0 to turn it off.
"""
import os
import threading
import time
from datetime import datetime

TZ_NAME = os.getenv("SCHEDULE_TZ", "Africa/Cairo")
_started = False


def now():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(TZ_NAME)).replace(tzinfo=None)
    except Exception:
        return datetime.now()


def _loop():
    while True:
        for name, mod in (("daily-report", "daily_report"), ("monthly-report", "monthly_report"), ("backup", "backup")):
            try:
                __import__(f"web.{mod}", fromlist=["auto_tick"]).auto_tick(now())
            except Exception as e:
                print(f"[{name}] tick error: {e}", flush=True)
        time.sleep(20)


def start():
    global _started
    if _started or os.getenv("BACKGROUND", os.getenv("SCHEDULER", "1")) in ("0", "false", "False"):
        return
    _started = True
    threading.Thread(target=_loop, name="background", daemon=True).start()
    print(f"[background] started ({TZ_NAME})", flush=True)
