"""
paperknife.qt.theme
Fluent theme setup, the colour palette and the Segoe Fluent Icons helpers.

EVERY colour the Qt interface shows comes from the active palette
(palettes.py: role -> (light, dark)); nothing else in paperknife.qt writes
a hex literal.  The app's own code reads roles through color() / hex_color()
/ pair() / label_role(); the colours QFluentWidgets draws itself are routed
to roles by fluent_route.py.  The palette is chosen by env PK_PALETTE
(default "today", today's look) and switched at run time by
apply_palette(name).  apply_appearance() reads PREFS["appearance"]
(light / dark / system) and applies it.
"""
from __future__ import annotations

import functools
import os
import sys
import weakref

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QGuiApplication, QIcon,
                           QIconEngine, QImage, QPainter, QPixmap)
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, isDarkTheme, setFontFamilies, setTheme, setThemeColor
from qfluentwidgets.common.icon import FluentIconBase

from . import fluent_route, palettes

# ── Palette ───────────────────────────────────────────────────────────────────
def _initial_palette() -> str:
    name = os.environ.get("PK_PALETTE", "").strip() or palettes.DEFAULT
    if name not in palettes.PALETTES:
        print(f"PK_PALETTE={name!r} is not a palette ({', '.join(palettes.PALETTES)}); "
              f"using {palettes.DEFAULT!r}", file=sys.stderr)
        name = palettes.DEFAULT
    return name


_palette_name = _initial_palette()
# The active palette, name -> (light, dark).  Rebound by apply_palette().
COLORS: dict[str, tuple[str, str]] = palettes.PALETTES[_palette_name]
fluent_route.set_active(COLORS)
fluent_route.install()

STATUS_ROLES = ("muted", "success", "warning", "danger")

FONT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei"]
_ICON_FONTS = ("Segoe Fluent Icons", "Segoe MDL2 Assets")


def palette_name() -> str:
    return _palette_name


def color(name: str, dark: bool | None = None) -> QColor:
    """The token *name* for the current theme (or the one given)."""
    light_hex, dark_hex = COLORS[name]
    if dark is None:
        dark = isDarkTheme()
    return QColor(dark_hex if dark else light_hex)


def hex_color(name: str, dark: bool | None = None) -> str:
    """As color(), as a #AARRGGBB / #RRGGBB string for style sheets."""
    c = color(name, dark)
    return c.name(QColor.HexArgb) if c.alpha() < 255 else c.name()


def pair(name: str) -> tuple[QColor, QColor]:
    light_hex, dark_hex = COLORS[name]
    return QColor(light_hex), QColor(dark_hex)


def label_role(label, role: str) -> None:
    """Colour a Fluent label with *role*; it follows apply_palette()."""
    label.setTextColor(*pair(role))
    label._pk_role = role


_styled: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def keep_styled(widget, fn) -> None:
    """Run fn(widget) now and again after every palette switch (for style
    sheets the app writes from roles).  fn None forgets the widget."""
    if fn is None:
        _styled.pop(widget, None)
        return
    _styled[widget] = fn
    fn(widget)


def apply_palette(name: str) -> None:
    """Switch the whole interface to palette *name* and repaint what is open
    (the library's style sheets, the colours it keeps on widgets, labels,
    the app's own style sheets and pages - their themeChangedFinished
    handlers run, as on a light / dark switch)."""
    global _palette_name, COLORS
    if name not in palettes.PALETTES:
        raise KeyError(f"no palette {name!r} (have {', '.join(palettes.PALETTES)})")
    old = COLORS
    _palette_name = name
    COLORS = palettes.PALETTES[name]
    fluent_route.set_active(COLORS)
    _icon_cache.clear()
    if QApplication.instance() is None:
        return
    from qfluentwidgets import qconfig
    from qfluentwidgets.common.style_sheet import updateStyleSheet
    updateStyleSheet(lazy=False)
    for w in QApplication.topLevelWidgets():      # before retint: its background
        window_follows_palette(w)                 # animation must aim at the Mica state
    fluent_route.retint(old, COLORS)
    for w, fn in list(_styled.items()):
        try:
            fn(w)
        except RuntimeError:
            pass
    qconfig.themeChangedFinished.emit()
    for w in QApplication.allWidgets():
        w.update()


def window_follows_palette(win) -> None:
    """A palette that moves the window role turns Mica off (Mica would cover
    the colour); a palette that keeps it gives Mica back if this turned it off."""
    if not hasattr(win, "setMicaEffectEnabled"):
        return
    moved = any(fluent_route.delta("window", d) is not None for d in (False, True))
    if moved and win.isMicaEffectEnabled():
        win.setMicaEffectEnabled(False)
        win._pk_mica_off = True
    elif not moved and getattr(win, "_pk_mica_off", False):
        win._pk_mica_off = False
        win.setMicaEffectEnabled(True)


# ── Appearance ────────────────────────────────────────────────────────────────
def system_is_dark() -> bool:
    hints = QGuiApplication.styleHints()
    try:
        return hints.colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:          # Qt < 6.5
        return False


def resolve_appearance(mode: str) -> Theme:
    if mode == "dark":
        return Theme.DARK
    if mode == "system":
        return Theme.DARK if system_is_dark() else Theme.LIGHT
    return Theme.LIGHT


_following_system = False


def apply_appearance(mode: str | None = None) -> Theme:
    """Apply light / dark / system (default: PREFS["appearance"]) and the
    accent.  "system" follows Windows while the app runs."""
    global _following_system
    if mode is None:
        from ..prefs import PREFS
        mode = PREFS.get("appearance", "light")
    theme = resolve_appearance(mode)
    setTheme(theme, lazy=True)
    # Fluent derives its accent family from today's accent; the accent_fill /
    # accent_hover / accent_pressed roles move that family (fluent_route).
    setThemeColor(QColor(palettes.TODAY["accent"][theme == Theme.DARK]), lazy=True)
    want_follow = mode == "system"
    hints = QGuiApplication.styleHints()
    if want_follow and not _following_system and hasattr(hints, "colorSchemeChanged"):
        hints.colorSchemeChanged.connect(_on_system_scheme)
        _following_system = True
    elif not want_follow and _following_system:
        try:
            hints.colorSchemeChanged.disconnect(_on_system_scheme)
        except (RuntimeError, TypeError):
            pass
        _following_system = False
    return theme


def _on_system_scheme(*_):
    apply_appearance("system")


def setup_fonts(app: QApplication) -> None:
    """Segoe UI Variable for the interface (Segoe UI where it is missing)."""
    setFontFamilies(FONT_FAMILIES)
    f = QFont()
    f.setFamilies(FONT_FAMILIES)
    f.setPointSize(10)
    app.setFont(f)


# ── Segoe Fluent Icons ────────────────────────────────────────────────────────
@functools.cache        # the font list costs ~7 ms; a paint must not pay it
def icon_font_family() -> str:
    families = set(QFontDatabase.families())
    for fam in _ICON_FONTS:
        if fam in families:
            return fam
    return _ICON_FONTS[0]


def _as_char(code) -> str:
    return chr(code) if isinstance(code, int) else str(code)


def _paint_glyph(painter: QPainter, rect, char: str, qcolor: QColor) -> None:
    f = QFont(icon_font_family())
    f.setPixelSize(max(1, round(QRectF(rect).height())))
    painter.save()
    painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
    painter.setFont(f)
    painter.setPen(qcolor)
    painter.drawText(QRectF(rect), Qt.AlignCenter, char)
    painter.restore()


_icon_cache: dict = {}


def glyph_icon(code, size: int = 16, color_=None) -> QIcon:
    """A Segoe Fluent Icons glyph (int code point or str) as a QIcon, drawn
    at 2x so it stays sharp at 200 % scaling.  color_: QColor / hex / a token
    name from COLORS; default the theme's text colour."""
    if color_ is None:
        qc = color("text")
    elif isinstance(color_, str) and color_ in COLORS:
        qc = color(color_)
    else:
        qc = QColor(color_)
    key = (_as_char(code), size, qc.rgba())
    if key in _icon_cache:
        return _icon_cache[key]
    img = QImage(size * 2, size * 2, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    _paint_glyph(p, QRect(0, 0, size * 2, size * 2), _as_char(code), qc)
    p.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(2.0)
    icon = QIcon(pm)
    _icon_cache[key] = icon
    return icon


class _GlyphEngine(QIconEngine):
    def __init__(self, char: str, qcolor: QColor):
        super().__init__()
        self.char, self.qcolor = char, qcolor

    def paint(self, painter, rect, mode, state):
        _paint_glyph(painter, rect, self.char, self.qcolor)

    def clone(self):
        return _GlyphEngine(self.char, self.qcolor)

    def pixmap(self, size, mode, state):
        img = QImage(size, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        self.paint(p, QRect(0, 0, size.width(), size.height()), mode, state)
        p.end()
        return QPixmap.fromImage(img)


class Glyph(FluentIconBase):
    """A Segoe Fluent Icons glyph usable wherever QFluentWidgets takes an
    icon (navigation items, buttons); it follows light / dark by itself."""

    def __init__(self, code, light: str | None = None, dark: str | None = None):
        self.char = _as_char(code)
        self.light = QColor(light) if light else None
        self.dark = QColor(dark) if dark else None

    def _color(self, theme=Theme.AUTO) -> QColor:
        dark = isDarkTheme() if theme == Theme.AUTO else theme == Theme.DARK
        own = self.dark if dark else self.light
        return own if own is not None else color("text", dark)

    def path(self, theme=Theme.AUTO) -> str:      # FluentIconBase contract
        return ""

    def icon(self, theme=Theme.AUTO, color: QColor = None) -> QIcon:  # noqa: A002
        return QIcon(_GlyphEngine(self.char, QColor(color) if color else self._color(theme)))

    def render(self, painter, rect, theme=Theme.AUTO, indexes=None, **attributes):
        qc = QColor(attributes["fill"]) if "fill" in attributes else self._color(theme)
        _paint_glyph(painter, rect, self.char, qc)
