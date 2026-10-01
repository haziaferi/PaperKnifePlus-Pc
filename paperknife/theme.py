"""
paperknife.theme
All visual constants for the Minimalist Scholastic palette.

Every semantic constant is a (light_hex, dark_hex) tuple so that
customtkinter widgets switch automatically when the appearance mode
changes.  Native tkinter widgets (Canvas, Listbox) cannot consume
tuples — use the _tk_color() helper exported from this module.

Appearance mode is NOT set here; it is applied from PREFS at startup
in __main__.py so that the user's saved preference takes effect before
the first window is created.
"""
import customtkinter as ctk

__version__ = "3.0.0"

ctk.set_default_color_theme("blue")

# ── Warm Scholastic palette ───────────────────────────────────────────────────
# Each entry: (light, dark)
#
# Dark palette was derived via CHA optimisation:
#   • Hue family: 33 ° warm brown — same ancestry as the light parchment
#   • BG_D L ≈ 15 % → contrast with white document page ≈ 14.6 : 1
#     (intentionally mid-dark, not pitch-black, to reduce eye-strain at
#     the light/dark boundary of PDF pages)
#   • WCAG AA passes: TEXT/BG 10.9:1 · WHITE/ACCENT 5.6:1 · MUTED/SIDEBAR 5.4:1
#   • Non-text contrast (WCAG 1.4.11): ACCENT on SIDEBAR 3.05 : 1 ≥ 3 ✓

ACCENT   = ("#2B4C8C", "#4468A5")   # Oxford blue  /  lighter Oxford blue
ACCENT_H = ("#1E3566", "#35528A")   # deep navy hover  /  dark mode hover

BG      = ("#F5F1EB", "#2D2820")    # parchment  /  very dark warm brown
SIDEBAR = ("#EDE8DF", "#201C14")    # warm cream  /  deeper brown
CARD    = ("#E4DDD2", "#373027")    # aged paper  /  dark card
CARD2   = ("#EAE4D8", "#3D362C")    # light tan   /  slightly lighter dark card

TEXT    = ("#1C1A17", "#E8DEC8")    # ink  /  warm cream-white
MUTED   = ("#7A7268", "#9A8F82")    # faded ink  /  warm mid-grey

# Semantic / state colours — mode-invariant (work on both surfaces)
DANGER   = "#9B1B1B"
DANGER_H = "#7A1414"
SUCCESS  = "#2D6A4F"
WARN     = "#9A5A00"
GREEN    = "#2D6A4F"

# ── Native-tk widget colours (resolved strings, not tuples) ──────────────────
# These are used by tk.Canvas and tk.Listbox which cannot accept tuples.
# Always call through _tk_color() so they respond to mode changes.
CANVAS_BG = ("#F0EBE3", "#242019")
LB_BG     = ("#EAE4D8", "#373027")


def _tk_color(color) -> str:
    """Return the single hex string for the current appearance mode.

    Pass any theme constant (tuple or plain string); returns a string
    suitable for native tkinter widget `bg=` / `fg=` kwargs.
    """
    if isinstance(color, tuple):
        return color[0] if ctk.get_appearance_mode() == "Light" else color[1]
    return color
