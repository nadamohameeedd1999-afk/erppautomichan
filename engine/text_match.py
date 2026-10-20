"""
Text matching for option lists (Arabic aware).

"4 - هوليداى ان العليا" and "4 - هوليداي إن العليا" should be treated as the same text,
so comparisons go through normalize().
"""
import re

PLACEHOLDERS = {"", "اختر", "--اختر--", "-اختر-", "-- اختر --", "select", "-- select --", "choose"}

_AR_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ئ": "ي",
    "ة": "ه",
    "ؤ": "و",
    "ـ": "",  # tatweel
})
_DIACRITICS = re.compile(r"[ً-ْٰ]")
_SPACES = re.compile(r"\s+")


def normalize(text) -> str:
    if text is None:
        return ""
    t = str(text).strip().lower()
    t = _DIACRITICS.sub("", t)
    t = t.translate(_AR_MAP)
    t = _SPACES.sub(" ", t)
    return t


def is_placeholder(text) -> bool:
    n = normalize(text)
    stripped = n.replace("-", "").replace("_", "").replace(".", "").strip()
    return n in PLACEHOLDERS or stripped in PLACEHOLDERS


def real_options(texts):
    """Drop empty / placeholder entries."""
    return [t for t in (texts or []) if not is_placeholder(t)]


def find_exact(options, wanted):
    """Index of the option equal to wanted (normalized), else -1."""
    w = normalize(wanted)
    for i, o in enumerate(options):
        if not is_placeholder(o) and normalize(o) == w:
            return i
    return -1


def find_contains(options, wanted):
    """Index of the first option containing wanted (normalized), else -1.
    If several options contain it, an exact match wins."""
    exact = find_exact(options, wanted)
    if exact != -1:
        return exact
    w = normalize(wanted)
    if not w:
        return -1
    for i, o in enumerate(options):
        if not is_placeholder(o) and w in normalize(o):
            return i
    return -1


def preview(options, limit=15):
    """Short text listing of available options for error messages."""
    real = real_options(options)
    shown = real[:limit]
    more = f" ... (+{len(real) - limit})" if len(real) > limit else ""
    return (" | ".join(shown) + more) if shown else "(القايمة فاضية)"
