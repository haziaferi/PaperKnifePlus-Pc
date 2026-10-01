"""
paperknife.prefs
Persistent user preferences stored alongside recent.json.
"""
from __future__ import annotations
import json
import os
from .recent import APPDIR, write_json_atomic

PREFS_PATH = APPDIR / "prefs.json"

_DEFAULTS: dict = {
    "output_dir":      "",        # default save-as directory (empty = last used)
    "default_dpi":     150,       # OCR / PDF→image default DPI
    "compress_level":  "medium",  # light / medium / aggressive
    "ocr_lang":        "eng",     # Tesseract language code
    "max_recent":      12,        # max recent-file cards on home screen
    "window_geometry": "",        # last window geometry string (WxH+X+Y)
    "appearance":      "light",   # light / dark / system
}

_CHOICES: dict = {
    "compress_level": ("light", "medium", "aggressive"),
    "appearance":     ("light", "dark", "system"),
}


def _valid(key: str, value) -> bool:
    default = _DEFAULTS[key]
    # bool is a subclass of int; a stored true must not pass as a DPI.
    if isinstance(value, bool) or type(value) is not type(default):
        return False
    return key not in _CHOICES or value in _CHOICES[key]


class Prefs:
    """Load/save/access user preferences as simple attributes."""

    def __init__(self):
        self._data: dict = dict(_DEFAULTS)
        self._load()

    # ── Internal ──────────────────────────────────────────────────────────────
    def _load(self):
        try:
            raw = PREFS_PATH.read_text(encoding="utf-8")
        except OSError:
            return
        try:
            stored = json.loads(raw)
            if not isinstance(stored, dict):
                raise ValueError("prefs.json is not an object")
        except ValueError:
            # Keep the unreadable file for the user instead of letting the
            # next save overwrite it with defaults.
            try:
                os.replace(PREFS_PATH, PREFS_PATH.with_name(PREFS_PATH.name + ".bad"))
            except OSError:
                pass
            return
        for key, value in stored.items():
            if key in _DEFAULTS and _valid(key, value):
                self._data[key] = value

    def save(self):
        """Persist atomically.  Raises OSError if the file cannot be written."""
        write_json_atomic(PREFS_PATH, self._data)

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
