"""
🌐 English for the whole dashboard (Arabic stays the source).

The pages are written in Arabic. When the viewer picks English, every response the dashboard sends — pages, the
JavaScript that builds parts of them, and JSON for the live parts — goes through one dictionary (web/i18n/ar_en.json:
every Arabic phrase of the pages → English), longest phrase first, whole words only. Names that come from the ERP
itself (screen names, customers…) stay as the client wrote them. To add or fix a translation: edit ar_en.json.
"""
import json
import re
from pathlib import Path

from flask import request

_FILE = Path(__file__).parent / "i18n" / "ar_en.json"
_DICT, _RX = {}, None
_PUNCT = str.maketrans({"«": "“", "»": "”", "،": ",", "؟": "?", "؛": ";", "٪": "%"})


def _load():
    global _DICT, _RX
    try:
        _DICT = json.loads(_FILE.read_text(encoding="utf-8"))
    except Exception:
        _DICT = {}
    keys = sorted(_DICT, key=len, reverse=True)
    _RX = re.compile(r"(?<![؀-ۿ])(?:" + "|".join(re.escape(k) for k in keys) + r")(?![؀-ۿ])") if keys else None


def translate(text):
    if not text or not re.search(r"[؀-ۿ«»]", text):
        return text
    if _RX is None:
        _load()
    if _RX is not None:
        text = _RX.sub(lambda m: _DICT[m.group(0)], text)
    return text.translate(_PUNCT)


def _walk(x):
    if isinstance(x, str):
        return translate(x)
    if isinstance(x, list):
        return [_walk(v) for v in x]
    if isinstance(x, dict):
        return {k: _walk(v) for k, v in x.items()}
    return x


def after_request(resp):
    try:
        from web.i18n_helper import get_current_lang
        if get_current_lang() != "en" or resp.status_code in (204, 304) or resp.status_code >= 300 and resp.status_code < 400:
            return resp
        if resp.headers.get("Content-Disposition", "").startswith("attachment"):
            return resp
        mt = (resp.mimetype or "").lower()
        if mt not in ("text/html", "application/javascript", "text/javascript", "application/json"):
            return resp
        if resp.is_streamed and not resp.direct_passthrough:
            return resp
        resp.direct_passthrough = False
        raw = resp.get_data(as_text=True)
        if mt == "application/json":
            try:
                body = json.dumps(_walk(json.loads(raw)), ensure_ascii=False)
            except Exception:
                return resp
        else:
            body = translate(raw)
        resp.set_data(body)
        if request.path.startswith("/static/"):
            resp.headers["Cache-Control"] = "no-cache"
            resp.headers["Vary"] = "Cookie"
    except Exception:
        pass
    return resp
