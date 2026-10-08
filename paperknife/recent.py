"""
paperknife.recent
Recent-file store, thumbnail cache, and time-ago formatter.
"""
from __future__ import annotations
import json, os, threading
from pathlib import Path
from datetime import datetime

from PIL import Image
import pymupdf as fitz

from .job_queue import atomic_output

APPDIR      = Path.home() / ".paperknifepluspc"
RECENT_PATH = APPDIR / "recent.json"

_THUMB_CACHE_MAX = 64
# Stored history is capped here, not at max_recent, so lowering max_recent
# only shortens the Home grid and raising it again brings entries back.
RECENT_STORE_MAX = 50


def _max_recent() -> int:
    """Read max_recent from PREFS at call time to avoid circular import."""
    try:
        from .prefs import PREFS
        return max(1, int(PREFS.max_recent))
    except (ImportError, AttributeError, TypeError, ValueError):
        return 12


def write_json_atomic(path: Path, data) -> None:
    """Write *data* as JSON so that *path* holds either the old or the new
    content, never a truncated file.  Raises OSError on failure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with atomic_output(path) as tmp, open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())


def _valid_entry(e) -> bool:
    return isinstance(e, dict) and isinstance(e.get("path"), str)


# ── Persistent recent-files store ─────────────────────────────────────────────
class RecentFiles:
    def __init__(self):
        self._entries: list[dict] = []
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        try:
            data = json.loads(RECENT_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(data, list):
            self._entries = [e for e in data if _valid_entry(e)]

    def _save(self):
        # Runs from worker threads during long jobs; a failed history write
        # must not fail the job itself.
        try:
            write_json_atomic(RECENT_PATH, self._entries)
        except OSError:
            pass

    def push(self, path: str, pages: int = 0):
        path = str(Path(path).resolve())
        with self._lock:
            self._entries = [e for e in self._entries if e["path"] != path]
            size_kb = 0
            try:
                size_kb = Path(path).stat().st_size // 1024
            except OSError:
                pass
            self._entries.insert(0, {
                "path":     path,
                "name":     Path(path).name,
                "accessed": datetime.now().isoformat(timespec="seconds"),
                "pages":    pages,
                "size_kb":  size_kb,
            })
            self._entries = self._entries[:RECENT_STORE_MAX]
            self._save()

    def all(self) -> list[dict]:
        out = []
        for e in self._entries:
            try:
                if Path(e["path"]).exists():
                    out.append(e)
            except OSError:
                continue
        return out[:_max_recent()]

    def clear(self):
        with self._lock:
            self._entries = []
            self._save()


RECENT = RecentFiles()

# ── Thumbnail cache ────────────────────────────────────────────────────────────
_THUMB_CACHE: dict[tuple, tuple[Image.Image, tuple[int, int]] | None] = {}

def thumb_image(path: str, size=(100, 130)) -> tuple[Image.Image, tuple[int, int]] | None:
    """The first page of *path* rendered at twice *size* (sharp at 200 % scaling),
    with the size to show it at; cached by path, size and modification time.
    Each user interface wraps the image in its own image type."""
    try:
        mtime = os.stat(path).st_mtime_ns
    except OSError:
        return None
    key = (path, size, mtime)
    if key not in _THUMB_CACHE:
        if len(_THUMB_CACHE) >= _THUMB_CACHE_MAX:
            _THUMB_CACHE.pop(next(iter(_THUMB_CACHE)))
        try:
            with fitz.open(path) as doc:
                page = doc[0]
                # Render at 2x the box so the image stays sharp at 200 % scaling.
                zoom = 2 * min(size[0] / page.rect.width,
                               size[1] / page.rect.height)
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            fit = (max(1, round(pix.width / 2)), max(1, round(pix.height / 2)))
            _THUMB_CACHE[key] = (img, fit)
        except Exception:
            _THUMB_CACHE[key] = None
    return _THUMB_CACHE[key]

def time_ago(iso: str) -> str:
    try:
        dt   = datetime.fromisoformat(iso)
        secs = (datetime.now() - dt).total_seconds()
        if secs < 60:    return "just now"
        if secs < 3600:  return f"{int(secs//60)}m ago"
        if secs < 86400: return f"{int(secs//3600)}h ago"
        return f"{int(secs//86400)}d ago"
    except (TypeError, ValueError):
        return ""
