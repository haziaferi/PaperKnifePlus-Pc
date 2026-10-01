"""
paperknife.recent
Recent-file store, thumbnail cache, and time-ago formatter.
"""
from __future__ import annotations
import json, threading
from pathlib import Path
from datetime import datetime

import customtkinter as ctk
from PIL import Image
import fitz  # PyMuPDF

APPDIR      = Path.home() / ".paperknifepluspc"
RECENT_PATH = APPDIR / "recent.json"

def _max_recent() -> int:
    """Read max_recent from PREFS at call time to avoid circular import."""
    try:
        from .prefs import PREFS
        return int(PREFS.max_recent)
    except Exception:
        return 12

# ── Persistent recent-files store ─────────────────────────────────────────────
class RecentFiles:
    def __init__(self):
        APPDIR.mkdir(exist_ok=True)
        self._entries: list[dict] = []
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        try:
            if RECENT_PATH.exists():
                self._entries = json.loads(RECENT_PATH.read_text())
        except Exception:
            self._entries = []

    def _save(self):
        try:
            RECENT_PATH.write_text(json.dumps(self._entries, indent=2))
        except Exception:
            pass

    def push(self, path: str, pages: int = 0):
        path = str(Path(path).resolve())
        with self._lock:
            self._entries = [e for e in self._entries if e["path"] != path]
            size_kb = 0
            try:
                size_kb = Path(path).stat().st_size // 1024
            except Exception:
                pass
            self._entries.insert(0, {
                "path":     path,
                "name":     Path(path).name,
                "accessed": datetime.now().isoformat(timespec="seconds"),
                "pages":    pages,
                "size_kb":  size_kb,
            })
            self._entries = self._entries[:_max_recent()]
            self._save()

    def all(self) -> list[dict]:
        return [e for e in self._entries
                if isinstance(e, dict) and "path" in e and Path(e["path"]).exists()]

    def clear(self):
        with self._lock:
            self._entries = []
            self._save()


RECENT = RecentFiles()

# ── Thumbnail cache ────────────────────────────────────────────────────────────
_THUMB_CACHE: dict[str, ctk.CTkImage | None] = {}

def get_thumb(path: str, size=(100, 130)) -> ctk.CTkImage | None:
    key = f"{path}_{size}"
    if key not in _THUMB_CACHE:
        try:
            doc = fitz.open(path)
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(0.22, 0.22), alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            _THUMB_CACHE[key] = ctk.CTkImage(img, size=size)
            doc.close()
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
    except Exception:
        return ""
