"""
Safe file storage — use this for every JSON the program saves.

save_json(path, data)  : writes to a temp file then swaps it in (a crash never leaves half a file)
                         and keeps the previous version in data/history/ (last KEEP_VERSIONS)
load_json(path, default): reads with or without BOM; if the file is broken it falls back to the
                         newest good version from history
to_trash(path)         : "delete" = move to data/trash/<date>/... so nothing is ever lost by a click
"""
import json
import shutil
import threading
from datetime import datetime
from pathlib import Path

from config import paths

KEEP_VERSIONS = 10
_lock = threading.RLock()


def _rel(path: Path) -> Path:
    path = Path(path).resolve()
    for root in (paths.DATA_DIR, paths.DEFS_DIR, paths.BASE_DIR):
        try:
            return path.relative_to(root)
        except ValueError:
            continue
    return Path(path.name)


def _history_dir(path: Path) -> Path:
    return paths.HISTORY_DIR / _rel(path).parent / Path(path).stem


def load_json(path, default=None):
    path = Path(path)
    for enc in ("utf-8", "utf-8-sig"):
        try:
            with open(path, "r", encoding=enc) as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        except Exception:
            break
    # broken file -> newest good version from history
    for old in sorted(_history_dir(path).glob("*.json"), reverse=True):
        try:
            data = json.loads(old.read_text(encoding="utf-8-sig"))
            print(f"[storage] ⚠️ {path} كان بايظ — رجّعت آخر نسخة سليمة ({old.name})", flush=True)
            return data
        except Exception:
            continue
    return default


def save_json(path, data, keep=KEEP_VERSIONS):
    path = Path(path)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            try:
                if path.read_text(encoding="utf-8-sig") == text:
                    return path                      # nothing changed
                hd = _history_dir(path)
                hd.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, hd / f"{datetime.now():%Y%m%d_%H%M%S_%f}.json")
                olds = sorted(hd.glob("*.json"))
                for o in olds[:-keep]:
                    o.unlink(missing_ok=True)
            except Exception:
                pass
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    return path


def to_trash(path) -> bool:
    path = Path(path)
    if not path.exists():
        return False
    with _lock:
        dest = paths.TRASH_DIR / f"{datetime.now():%Y%m%d}" / _rel(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest = dest.with_name(f"{dest.stem}_{datetime.now():%H%M%S}{dest.suffix}")
        shutil.move(str(path), str(dest))
    return True


def history(path):
    """Saved older versions of a file, newest first."""
    hd = _history_dir(Path(path))
    return sorted(hd.glob("*.json"), reverse=True) if hd.exists() else []
