"""
Self-tests of the engine against the fake ERP in selftest/mock_erp (not the real system).
  cd selftest/mock_erp && npm install          (once)
  python -m pytest selftest -q                 (starts the mock by itself)
Browser tests need Chrome (+ a display on Linux: xvfb-run).
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MOCK = Path(__file__).resolve().parent / "mock_erp" / "mock_erp.py"
PORT = 5055


def _up():
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


@pytest.fixture(scope="session")
def mock_erp(tmp_path_factory):
    proc = None
    if not _up():
        proc = subprocess.Popen([sys.executable, str(MOCK)], cwd=str(MOCK.parent),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(40):
            if _up():
                break
            time.sleep(0.25)
    data = tmp_path_factory.mktemp("data")
    env = {**os.environ, "BASE_URL": f"http://127.0.0.1:{PORT}", "LOGIN_USERNAME": "erpadmin", "LOGIN_PASSWORD": "pw",
           "DATA_DIR": str(data), "DEFS_DIR": str(data / "defs"), "SITE_PROFILE": "__none__",
           "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost", "PYTHONUTF8": "1"}
    yield env
    if proc:
        proc.terminate()


@pytest.fixture
def run_cli(mock_erp, tmp_path):
    """run `python -m engine.cli <cmd>` on a config dict; retries once if Chrome itself crashes"""
    import json

    def run(cmd, cfg=None, *args, defs=None):
        cfg_file = tmp_path / "cfg.json"
        out = tmp_path / "out.json"
        extra = []
        if cfg is not None:
            cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
            extra = ["--config-file", str(cfg_file)]
        if defs:                                   # configs the chain needs (saved definitions)
            d = Path(mock_erp["DEFS_DIR"]) / "screens"
            d.mkdir(parents=True, exist_ok=True)
            for c in defs:
                (d / f"{c['key']}.json").write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
        data = {}
        for _ in range(3):
            subprocess.run([sys.executable, "-m", "engine.cli", cmd, *extra, *args, "--out", str(out)],
                           cwd=str(ROOT), env=mock_erp, timeout=600, capture_output=True)
            data = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {"success": False, "error": "no output"}
            if not any(w in str(data.get("error", "")) for w in ("InvalidSessionId", "disconnected", "SessionNotCreated")):
                break
        return data
    return run
