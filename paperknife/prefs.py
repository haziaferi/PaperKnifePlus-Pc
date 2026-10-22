"""
paperknife.prefs
Persistent user preferences stored alongside recent.json.
"""
from __future__ import annotations
import json
import os
from .recent import APPDIR, write_json_atomic

PREFS_PATH = APPDIR / "prefs.json"

DPI_RANGE = (72, 600)     # what Settings accepts for ocr_dpi / export_dpi
OLD_DEFAULT_DPI = 150     # the one "default_dpi" before 2026-10-22, shared by OCR and export

_DEFAULTS: dict = {
    "output_dir":      "",        # default save-as directory (empty = last used)
    "ocr_dpi":         200,       # OCR and Batch → OCR (measured best, 2026-10-22)
    "export_dpi":      200,       # PDF → Other's images and slides (owner, 2026-10-22)
    "compress_level":  "medium",  # light / medium / aggressive
    "ocr_lang":        "",        # Tesseract code(s), "ita+eng"; "" = not chosen yet:
                                  # Windows' display language, else English
    "max_recent":      12,        # max recent-file cards on home screen
    "window_geometry": "",        # last window geometry string (WxH+X+Y)
    "qt_window_geometry": "",     # the Qt window's saveGeometry(), base64
    "qt_stale_parts":  [],        # .part files a job left when the Qt app quit
    "qt_nav_folded":   [],        # navigation groups folded under their title (section names)
    "qt_page_strip":   True,      # the editors' page strip is open (owner, 2026-10-18)
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
            raw = PREFS_PATH.read_bytes()
        except OSError:
            return
        try:
            stored = json.loads(raw.decode("utf-8"))
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
        # The shared "default_dpi" became two keys.  Saved at the old default it was
        # almost certainly never touched (every save writes every key): the new
        # defaults apply.  Any other value was chosen: both keys keep it.
        old = stored.get("default_dpi")
        if (isinstance(old, int) and not isinstance(old, bool) and old != OLD_DEFAULT_DPI
                and DPI_RANGE[0] <= old <= DPI_RANGE[1]):
            for key in ("ocr_dpi", "export_dpi"):
                if key not in stored:
                    self._data[key] = old

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


def pref_dpi(lo: int, hi: int, key: str) -> int:
    """The *key* DPI preference ("ocr_dpi" or "export_dpi") clamped to a tool's own
    slider range."""
    return min(hi, max(lo, PREFS.get(key, _DEFAULTS[key])))


PREFS = Prefs()
