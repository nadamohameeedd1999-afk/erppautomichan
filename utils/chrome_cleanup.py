"""
Chrome processes that outlive their test eat the server's memory (Railway) until every new tab crashes, and the
live view keeps showing a browser «with no test running». Linux only; never touches a Chrome whose test is alive.

kill_tree(pid)         a process and everything it started (a stopped test -> its chromedriver -> its Chrome)
kill_orphan_chrome()   Chrome / chromedriver whose parent is gone (adopted by PID 1)
"""
import os
import sys
import time

NAMES = ("chrome", "google-chrome", "chromedriver", "chrome_crashpad", "chrome_crashpad_handler", "chrome_crashpad_h")


def _procs():
    out = {}
    if not sys.platform.startswith("linux"):
        return out
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/stat") as fh:
                st = fh.read()
            out[int(d)] = (st[st.index("(") + 1:st.rindex(")")], int(st[st.rindex(")") + 2:].split()[1]))
        except Exception:
            continue
    return out


def kill_tree(pid):
    procs = _procs()
    kids = {}
    for p, (_, pp) in procs.items():
        kids.setdefault(pp, []).append(p)
    todo, all_ = [pid], []
    while todo:
        p = todo.pop()
        all_.append(p)
        todo += kids.get(p, [])
    for p in reversed(all_):
        try:
            os.kill(p, 9)
        except Exception:
            pass
    return len(all_)


def kill_orphan_chrome(passes=3):
    n = 0
    for _ in range(passes):
        k = 0
        for pid, (name, ppid) in _procs().items():
            if ppid == 1 and name.startswith(NAMES):
                try:
                    os.kill(pid, 9)
                    k += 1
                except Exception:
                    pass
        n += k
        if not k:
            break
        time.sleep(0.5)                      # their children become orphans now
    return n


def chrome_count():
    return sum(1 for name, _ in _procs().values() if name.startswith(("chrome", "chromedriver")))


def kill_all_chrome():
    """only when nothing is running (the live page's «اقفلي المتصفحات المعلقة»)"""
    n = 0
    for pid, (name, _) in _procs().items():
        if name.startswith(NAMES):
            try:
                os.kill(pid, 9)
                n += 1
            except Exception:
                pass
    return n
