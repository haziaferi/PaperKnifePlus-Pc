"""Preferences: check and apply the values the Preferences tool edits."""
from __future__ import annotations

from ..prefs import _DEFAULTS, DPI_RANGE
from ..recent import RECENT_STORE_MAX

# (label, min, max) for the integer settings.
INT_RANGES = {
    "max_recent":  ("Max recent files shown", 1, RECENT_STORE_MAX),
    "ocr_dpi":     ("OCR DPI", *DPI_RANGE),
    "export_dpi":  ("Export DPI", *DPI_RANGE),
}
# What "Restore defaults" leaves alone.
KEEP_ON_RESTORE = ("window_geometry", "qt_window_geometry")


def check_values(values: dict) -> str | None:
    """Turn the integer settings of *values* into ints in place.  Returns the
    warning to show for the first one that is not a whole number in its range,
    else None."""
    for key, (name, lo, hi) in INT_RANGES.items():
        if key not in values:
            continue
        val = values[key]
        try:
            val = None if isinstance(val, bool) else int(val)
        except (TypeError, ValueError):
            val = None
        if val is None or not lo <= val <= hi:
            return f"{name} must be a whole number from {lo} to {hi}."
        values[key] = val
    return None


def apply_values(prefs, values: dict) -> None:
    """Set every key of *values* on *prefs* (a paperknife.prefs.Prefs)."""
    for key, val in values.items():
        setattr(prefs, key, val)


def restore_defaults(prefs) -> None:
    """Set every preference on *prefs* back to its default, except the ones in
    KEEP_ON_RESTORE."""
    for key, val in _DEFAULTS.items():
        if key not in KEEP_ON_RESTORE:
            setattr(prefs, key, val)
