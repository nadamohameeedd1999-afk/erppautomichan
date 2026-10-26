"""
Live view (البث المباشر) through the dashboard itself.

- /novnc/<file>        the noVNC web client (files from NOVNC_DIR, default /usr/share/novnc)
- /novnc-ws            websocket -> raw TCP bridge to the VNC server (VNC_HOST:VNC_PORT, default localhost:5900)
- /api/live/status     is noVNC there? is the VNC server up? is a test running?

Everything goes through the dashboard's own port and login, so on Railway nothing
else has to be exposed. Needs `flask-sock` (in requirements.txt); without it the page
falls back to the external VNC URL from the tunnel settings.
"""
import os
import socket
import threading
from pathlib import Path

from flask import Blueprint, abort, jsonify, send_from_directory, session

from web import auth

bp = Blueprint("live", __name__)

NOVNC_DIRS = [os.getenv("NOVNC_DIR", ""), "/usr/share/novnc", "/usr/share/novnc/www",
              str(Path(__file__).resolve().parent / "static" / "novnc")]
VNC_HOST = os.getenv("VNC_HOST", "localhost")
VNC_PORT = int(os.getenv("VNC_PORT", "5900"))
VNC_PASSWORD = os.getenv("VNC_PASSWORD", "erp")

try:
    from flask_sock import Sock
    _sock = Sock()
    HAS_SOCK = True
except Exception:          # flask-sock not installed (e.g. local Windows before pip install)
    _sock = None
    HAS_SOCK = False


def novnc_dir():
    for d in NOVNC_DIRS:
        if d and (Path(d) / "vnc.html").exists():
            return Path(d)
    return None


def vnc_port_open(timeout=0.6):
    try:
        _vnc_connect(timeout).close()
        return True
    except OSError:
        return False


def ensure_display():
    """On the server: if the display (Xvfb :99) or the VNC server isn't running — e.g. the app was started
    directly instead of through supervisord — start them, so Chrome has a screen and the live view works."""
    import shutil
    import subprocess
    import time
    on_server = os.path.exists("/.dockerenv") or os.getenv("RAILWAY_ENVIRONMENT")
    if not on_server or os.name == "nt" or vnc_port_open(0.3):
        return
    disp = os.getenv("DISPLAY", ":99")
    num = disp.split(":")[-1].split(".")[0] or "99"
    try:
        if not os.path.exists(f"/tmp/.X11-unix/X{num}") and shutil.which("Xvfb"):
            subprocess.Popen(["Xvfb", f":{num}", "-screen", "0", "1600x900x24", "-nolisten", "tcp"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            os.environ["DISPLAY"] = f":{num}"
            time.sleep(1.5)
            print(f"[live] 🖥️ شغّلت شاشة العرض Xvfb :{num}", flush=True)
        if shutil.which("x11vnc"):
            pw = "/root/.vnc/passwd"
            os.makedirs(os.path.dirname(pw), exist_ok=True)
            subprocess.run(["x11vnc", "-storepasswd", VNC_PASSWORD, pw], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.Popen(["x11vnc", "-display", f":{num}", "-forever", "-shared", "-localhost",
                              "-rfbauth", pw, "-rfbport", str(VNC_PORT)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            print("[live] 📺 شغّلت سيرفر البث (x11vnc)", flush=True)
    except Exception as e:
        print(f"[live] مقدرتش أشغّل شاشة العرض: {e}", flush=True)


def init_app(app):
    app.register_blueprint(bp)
    threading.Thread(target=ensure_display, daemon=True).start()
    if HAS_SOCK:
        _sock.init_app(app)
        _sock.route("/novnc-ws")(_ws_bridge)
        _sock.route("/novnc-ws-test")(_ws_echo)


def _vnc_connect(timeout=5):
    """x11vnc -localhost listens on IPv4 127.0.0.1; 'localhost' may resolve to ::1 first"""
    last = None
    for host in dict.fromkeys([VNC_HOST, "127.0.0.1"]):
        try:
            return socket.create_connection((host, VNC_PORT), timeout=timeout)
        except OSError as e:
            last = e
    raise last


def _ws_echo(ws):
    """the live page checks that websockets get through the server / Railway before opening noVNC"""
    try:
        msg = ws.receive(timeout=5)
        ws.send("pong" if msg == "ping" else "?")
    except Exception:
        pass


# ---------------- picture mode (no websocket needed): a JPEG of the test browser's screen ----------------
_frame = {"t": 0.0, "data": b"", "lock": threading.Lock()}


def grab_frame(max_w=1280, quality=62):
    import io
    import time
    with _frame["lock"]:
        if time.time() - _frame["t"] < 0.35 and _frame["data"]:      # several viewers share one grab
            return _frame["data"]
        from PIL import ImageGrab
        disp = os.getenv("DISPLAY", ":99")
        im = ImageGrab.grab(xdisplay=disp).convert("RGB")
        if im.width > max_w:
            im = im.resize((max_w, round(im.height * max_w / im.width)))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True)
        _frame.update(t=time.time(), data=buf.getvalue())
        return _frame["data"]


def frames_available():
    if os.name == "nt":
        return False
    try:
        from PIL import ImageGrab, features      # noqa: F401
        disp = os.getenv("DISPLAY", ":99").split(":")[-1].split(".")[0] or "99"
        return features.check("xcb") and os.path.exists(f"/tmp/.X11-unix/X{disp}")
    except Exception:
        return False


@bp.route("/api/live/frame.jpg")
@auth.login_required
def live_frame():
    from flask import Response
    try:
        data = grab_frame()
    except Exception as e:
        return jsonify({"success": False, "error": f"مقدرتش آخد صورة الشاشة: {e}"}), 503
    return Response(data, mimetype="image/jpeg", headers={"Cache-Control": "no-store"})


@bp.route("/novnc/<path:filename>")
@auth.login_required
def novnc_files(filename):
    d = novnc_dir()
    if not d:
        abort(404)
    return send_from_directory(str(d), filename)


@bp.route("/api/live/status")
@auth.login_required
def live_status():
    running, running_name = False, ""
    try:
        from web.queue_manager import get_manager
        cur = (get_manager().get_status() or {}).get("running")
        if cur and cur.get("status") in (None, "running", "queued"):
            running, running_name = True, cur.get("test_name", "")
    except Exception:
        pass
    return jsonify({
        "success": True,
        "proxy": HAS_SOCK and novnc_dir() is not None,
        "has_sock": HAS_SOCK,
        "novnc": novnc_dir() is not None,
        "vnc_up": vnc_port_open(),
        "frames": frames_available(),
        "test_running": running,
        "test_name": running_name,
    })


def _ws_bridge(ws):
    """Bridges the noVNC websocket to the VNC TCP port (what websockify does)."""
    if "user_id" not in session:
        ws.close()
        return
    try:
        tcp = _vnc_connect()
    except OSError as e:
        print(f"[live] websocket: مقدرتش أوصل لسيرفر العرض {VNC_HOST}:{VNC_PORT}: {e}", flush=True)
        ws.close()
        return
    tcp.settimeout(None)
    alive = {"on": True}

    def tcp_to_ws():
        try:
            while alive["on"]:
                data = tcp.recv(65536)
                if not data:
                    break
                ws.send(data)
        except Exception:
            pass
        finally:
            alive["on"] = False
            try:
                ws.close()
            except Exception:
                pass

    threading.Thread(target=tcp_to_ws, daemon=True).start()
    try:
        while alive["on"]:
            msg = ws.receive(timeout=30)
            if msg is None:
                continue
            if isinstance(msg, str):
                msg = msg.encode("latin-1")
            tcp.sendall(msg)
    except Exception:
        pass
    finally:
        alive["on"] = False
        try:
            tcp.close()
        except Exception:
            pass
