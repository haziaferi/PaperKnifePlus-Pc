"""
paperknife.prefs
Persistent user preferences stored alongside recent.json.
"""
from __future__ import annotations
import json
from pathlib import Path
from .recent import APPDIR

PREFS_PATH = APPDIR / "prefs.json"

_DEFAULTS: dict = {
    "output_dir":      "",        # default save-as directory (empty = last used)
    "default_dpi":     150,       # OCR / PDF→image default DPI
    "compress_level":  "medium",  # light / medium / aggressive
    "ocr_lang":        "eng",     # Tesseract language code
    "max_recent":      12,        # max recent-file cards on home screen
    "sidebar_open":    True,      # sidebar visible on launch
    "window_geometry": "",        # last window geometry string (WxH+X+Y)
    "appearance":      "light",   # light / dark / system
}


class Prefs:
    """Load/save/access user preferences as simple attributes."""

    def __init__(self):
        self._data: dict = dict(_DEFAULTS)
        self._load()

    # ── Internal ──────────────────────────────────────────────────────────────
    def _load(self):
        try:
            if PREFS_PATH.exists():
                stored = json.loads(PREFS_PATH.read_text())
                self._data.update(stored)
        except Exception:
            pass

    def save(self):
        try:
            APPDIR.mkdir(exist_ok=True)
            PREFS_PATH.write_text(json.dumps(self._data, indent=2))
        except Exception:
            pass

    # ── Attribute access ──────────────────────────────────────────────────────
    def __getattr__(self, key: str):
        if key.startswith("_"):
            raise AttributeError(key)
        if key in self._data:
            return self._data[key]
        raise AttributeError(f"Unknown pref: {key!r}")

    def __setattr__(self, key: str, value):
        if key.startswith("_"):
            super().__setattr__(key, value)
        else:
            self._data[key] = value

    def get(self, key: str, default=None):
        return self._data.get(key, default)


PREFS = Prefs()
