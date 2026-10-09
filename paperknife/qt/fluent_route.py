"""
paperknife.qt.fluent_route
Routes every colour QFluentWidgets 1.11.3 draws by itself to a palette role
(palettes.ROLES), through the library's own mechanisms:

1. Style sheets.  Every library .qss file is read by
   style_sheet.getStyleSheetFromFile (FluentStyleSheet.content); a wrapper
   rewrites each colour literal by the role classify_qss() gives it.
2. The accent family.  ThemeColor.color() (behind --ThemeColor* in the qss,
   themeColor() and every accent fill painted in Python) is moved by the
   accent_fill / accent_hover / accent_pressed roles.
3. Paint code.  In the widget modules the app shows, the module-level names
   QColor and Qt are replaced: a QColor built from numbers (or Qt.white /
   Qt.black) is looked up in PAINT_ROUTES by the class whose code built it,
   the theme and its RGBA.  A colour no route covers is recorded in
   UNROUTED (the probe test fails on one it did not expect).
4. A few methods: Fluent's svg icons (FluentIcon / SpinIcon), the label
   default text colour, the focus line of inputs.

The rule is the same everywhere: a library colour C with role R becomes
C + (palette[R] - today[R]), per RGBA channel, clamped.  The role's
reference value (palettes.TODAY) is drawn exactly as the palette says; the
library's other shades of that role keep their distance from it.  Under the
"today" palette the move is zero and nothing is rewritten, so the app is
pixel-identical to the library's own look.

Not routed (reported, not hidden): drop shadows (QGraphicsDropShadowEffect
colours), Mica (Windows draws it; a palette that changes "window" turns
Mica off), the coloured InfoBar icons (two-colour svgs), and widgets the app
does not use (their qss is still rewritten; their paint code is not).
"""
from __future__ import annotations

import re
import sys
import weakref

from PySide6.QtCore import Qt as _RealQt
from PySide6.QtGui import QColor as _RealQColor

from . import palettes

TODAY = palettes.TODAY
# QFluentWidgets rounds its controls 5 px; Windows 11 (WinUI ControlCornerRadius) uses 4.
_RADIUS_5 = re.compile(r"(border-radius\s*:\s*)5px")
# Placeholder text in the secondary text colour (WinUI TextControlPlaceholderForeground).
# The library sets none, so Qt draws the field's text at half alpha: under 4.5:1.
PLACEHOLDER_QSS = {
    "line_edit": "\nLineEdit, TextEdit, PlainTextEdit {{ placeholder-text-color: {}; }}\n",
}

# ── palette arithmetic ────────────────────────────────────────────────────────
_active: dict = TODAY            # set by theme.set_active_palette()


def set_active(pal: dict) -> None:
    global _active
    _active = pal
    _delta_cache.clear()


def active() -> dict:
    return _active


def rgba_of(value) -> tuple[int, int, int, int]:
    c = _RealQColor(value)
    return c.red(), c.green(), c.blue(), c.alpha()


_delta_cache: dict = {}


def delta(role: str, dark: bool):
    """palette[role] - today[role] as an RGBA tuple, None when it is zero."""
    if _active is TODAY:
        return None
    key = (role, dark)
    if key not in _delta_cache:
        a = rgba_of(TODAY[role][dark])
        b = rgba_of(_active[role][dark])
        _delta_cache[key] = None if a == b else tuple(b[i] - a[i] for i in range(4))
    return _delta_cache[key]


_GROUND = {False: (255, 255, 255), True: (32, 32, 32)}   # light / dark window, roughly


def _over(rgba, dark):
    """*rgba* composited over the theme's ground: what it looks like, opaque."""
    a = rgba[3] / 255
    g = _GROUND[dark]
    return tuple(rgba[i] * a + g[i] * (1 - a) for i in range(3))


def shift(rgba, role: str, dark: bool):
    """The colour *rgba* moved with *role*; None when the role did not move.

    Channel by channel: rgba + (palette[role] - today[role]).  An opaque
    library colour whose role is translucent today (rgb(96, 96, 96) under
    rgba(0, 0, 0, 0.61)) moves by the change in what the role looks like
    over the ground, and stays opaque.  When the palette's value is opaque
    (every scorer candidate), every colour of the role moves that way: what
    it looks like over the ground, plus what the role's move looks like,
    opaque.  (Channel arithmetic between a black tint and a white-tint
    reference made a radio's rest fill a solid grey disc.)"""
    d = delta(role, dark)
    if d is None:
        return None
    new = rgba_of(_active[role][dark])
    if new[3] == 255 and rgba[3] < 255:
        ref = rgba_of(TODAY[role][dark])
        a, b, c = _over(ref, dark), _over(new, dark), _over(rgba, dark)
        return tuple(max(0, min(255, int(round(c[i] + b[i] - a[i])))) for i in range(3)) + (255,)
    if rgba[3] == 255:
        ref = rgba_of(TODAY[role][dark])
        if ref[3] < 255:
            a, b = _over(ref, dark), _over(rgba_of(_active[role][dark]), dark)
            return tuple(max(0, min(255, int(round(rgba[i] + b[i] - a[i]))))
                         for i in range(3)) + (255,)
    return tuple(max(0, min(255, int(round(rgba[i] + d[i])))) for i in range(4))


def routed(rgba, role: str, dark: bool) -> tuple[int, int, int, int]:
    """*rgba* under the active palette (itself when the role did not move)."""
    s = shift(rgba, role, dark)
    return tuple(rgba) if s is None else s


def _hexargb(rgba) -> str:
    r, g, b, a = rgba
    return f"#{a:02x}{r:02x}{g:02x}{b:02x}"


# ══════════════════════════════════════════════════════════════════════════════
# 1. STYLE SHEETS
# ══════════════════════════════════════════════════════════════════════════════
_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_COLOR = re.compile(r"rgba?\([^)]*\)|#[0-9a-fA-F]{3,8}\b|\b(?:white|black|transparent)\b"
                    r"|--ThemeColorPrimary\b")
_FLYOUT_FILES = {"menu", "tool_tip", "teaching_tip", "state_tool_tip", "dialog",
                 "message_dialog", "folder_list_dialog", "color_dialog"}
_INPUT_FILES = {"line_edit", "spin_box"}
_TRANSPARENT_SEL = ("Transparent", "Hyperlink", "::indicator", "TitleBar", "ListView",
                    "ListWidget", "TableView", "TreeView", "::item", "NavigationPanel",
                    "Pivot", "Segmented", "MenuActionListWidget", "CloseButton")
# InfoBar backgrounds (FluentSystemColor *_BACKGROUND, light and dark)
_INFO_TINTS = {(223, 246, 221): "success_tint", (57, 61, 27): "success_tint",
               (255, 244, 206): "warning_tint", (67, 53, 25): "warning_tint",
               (253, 231, 233): "danger_tint", (68, 39, 38): "danger_tint"}
_STATES = ("hover", "pressed", "disabled", "checked", "focus", "selected")


def parse_qss_color(lit: str):
    s = lit.strip().lower()
    if s == "white":
        return 255, 255, 255, 255
    if s == "black":
        return 0, 0, 0, 255
    if s == "transparent":
        return 0, 0, 0, 0
    if s.startswith("#"):
        return rgba_of(s)
    nums = [x.strip() for x in s[s.index("(") + 1:s.rindex(")")].split(",")]
    r, g, b = (int(float(x)) for x in nums[:3])
    a = 255
    if len(nums) > 3:
        av = nums[3]
        a = round(float(av) * 255) if "." in av else int(av)
    return r, g, b, a


def _kind(prop: str):
    if prop in ("color", "selection-color"):
        return "text"
    if prop.startswith("qproperty-") and prop.endswith("color"):
        return "fill" if "background" in prop else "text"
    if prop.startswith("background") or prop == "selection-background-color":
        return "fill"
    if prop.startswith("border") or prop.startswith("outline"):
        return "line"
    return None


def _state_of(sel: str) -> set:
    s = sel.lower()
    return {st for st in _STATES if f":{st}" in s or f"{st}=true" in s}


def _tint(states) -> str:
    if "pressed" in states:
        return "tint_pressed"
    if "hover" in states:
        return "tint_hover"
    if "selected" in states or "checked" in states:
        return "tint_selected"
    return "tint_hover"


def _control(states) -> str:
    if "disabled" in states:
        return "control_disabled"
    if "pressed" in states:
        return "control_pressed"
    if "hover" in states:
        return "control_hover"
    return "control"


def classify_qss(fname: str, sel: str, prop: str, rgba, dark: bool):
    """The role of one colour literal in a library .qss rule; None = not routed."""
    kind = _kind(prop)
    if kind is None:
        return None
    r, g, b, a = rgba
    states = _state_of(sel)
    ink = (255, 255, 255) if dark else (0, 0, 0)
    anti = (0, 0, 0) if dark else (255, 255, 255)
    rgb = (r, g, b)
    neutral = max(r, g, b) - min(r, g, b) <= 3     # rgb(225, 224, 223) is a grey too
    transparent_sel = any(t in sel for t in _TRANSPARENT_SEL)

    if a == 0:      # invisible: only the docked navigation pane is a real surface
        if fname == "navigation_interface" and "menu=false" in sel and kind == "fill":
            return "nav_pane"
        return None

    if not neutral:                             # chromatic
        if fname == "info_bar" and kind == "fill":
            return _INFO_TINTS.get(rgb)
        if fname == "fluent_window":            # the close button's red
            return "danger"
        return None

    if fname == "fluent_window":
        if "StackedWidget" in sel:
            return "layer" if kind == "fill" else "layer_border" if kind == "line" else None
        if kind == "text":
            if "CloseButton" in sel and ("hover" in prop or "pressed" in prop):
                return "on_danger"
            return "fluent_text"
        if kind == "fill":
            return "tint_pressed" if "pressed" in prop else "tint_hover"
        return None
    if fname == "navigation_interface" and "menu=true" in sel:
        return "flyout" if kind == "fill" else "flyout_border" if kind == "line" else None

    if kind == "text":
        if rgb == anti:
            return "on_accent"
        if "disabled" in states:
            return "fluent_text_disabled"
        if rgb == ink:
            return "fluent_text" if a >= 217 else "fluent_text_secondary"
        return "fluent_text_secondary"

    if kind == "fill":
        if rgb == anti and "checked" in states and fname not in _FLYOUT_FILES:
            return "on_accent"                  # the dot on a checked radio
        if fname in _FLYOUT_FILES:
            if "Button" in sel:
                return _control(states)
            if rgb == ink and a < 128:
                return _tint(states)
            return "flyout"
        if fname == "info_bar":
            return _tint(states) if rgb == ink else "flyout"
        if rgb == ink:
            if a >= 38:
                return "track"
            if dark and not transparent_sel:
                return _control(states)         # dark controls are white tints
            return _tint(states)
        return _control(states)

    # kind == "line"
    if fname in _INPUT_FILES and prop == "border-bottom" \
            and not states & {"disabled", "focus"}:
        return "input_underline"
    if rgb == ink and prop == ("border-top" if dark else "border-bottom"):
        return "control_border_strong"
    if fname in _FLYOUT_FILES or fname == "info_bar":
        return "flyout_border"
    return "control_border"


QSS_UNROUTED: set = set()       # (file, selector, property, literal) seen while translating


def _fname_dark(path: str):
    m = re.search(r"/qss/(light|dark)/(\w+)\.qss$", str(path))
    return (m.group(2), m.group(1) == "dark") if m else (None, False)


def translate_qss(qss: str, fname: str, dark: bool, record: bool = True) -> str:
    """Rewrite *qss* (one library file) for the active palette."""
    if _active is TODAY:
        return qss
    qss = _COMMENT.sub("", qss)
    focus_d = delta("focus_ring", dark)

    def rule(m):
        sel = " ".join(m.group(1).split())
        states = _state_of(sel)
        decls = m.group(2).split(";")
        out = []
        for d in decls:
            if ":" not in d:
                out.append(d)
                continue
            prop, val = d.split(":", 1)
            p = prop.strip().lower()

            def sub(cm, p=p):
                lit = cm.group(0)
                if lit.startswith("--"):
                    if "focus" in states and focus_d is not None:
                        return _hexargb(rgba_of(_active["focus_ring"][dark]))
                    return lit                  # ThemeColor.color() routes it
                rgba = parse_qss_color(lit)
                role = classify_qss(fname, sel, p, rgba, dark)
                if role is None:
                    if record and rgba[3]:
                        QSS_UNROUTED.add((fname, sel, p, lit))
                    return lit
                new = shift(rgba, role, dark)
                return lit if new is None else _hexargb(new)
            out.append(prop + ":" + _COLOR.sub(sub, val))
        return m.group(1) + "{" + ";".join(out) + "}"
    return _RULE.sub(rule, qss)


def qss_routes(dark: bool, files=None):
    """Every colour literal of the library's .qss files with its role:
    [(file, selector, property, literal, role or None)] (for tests / reports)."""
    from PySide6.QtCore import QDir, QFile
    out = []
    folder = f":/qfluentwidgets/qss/{'dark' if dark else 'light'}"
    for name in QDir(folder).entryList(["*.qss"]):
        fname = name[:-4]
        if files is not None and fname not in files:
            continue
        f = QFile(f"{folder}/{name}")
        f.open(QFile.ReadOnly)
        text = _COMMENT.sub("", bytes(f.readAll()).decode("utf-8"))
        f.close()
        for m in _RULE.finditer(text):
            sel = " ".join(m.group(1).split())
            for d in m.group(2).split(";"):
                if ":" not in d:
                    continue
                prop, val = d.split(":", 1)
                p = prop.strip().lower()
                for cm in _COLOR.finditer(val):
                    lit = cm.group(0)
                    if lit.startswith("--"):
                        out.append((fname, sel, p, lit, "accent_fill"))
                        continue
                    rgba = parse_qss_color(lit)
                    out.append((fname, sel, p, lit, classify_qss(fname, sel, p, rgba, dark)))
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 3. PAINT CODE
# ══════════════════════════════════════════════════════════════════════════════
L, D = False, True


def _nav_tint(w, rgba):
    """NavigationPushButton.paintEvent: alpha 10 = selected at rest or
    hovered, 6 = selected and hovered or about to be selected (pressed)."""
    try:
        selected = bool(w._canDrawIndicator())
    except (AttributeError, RuntimeError):
        selected = bool(getattr(w, "isSelected", False))
    if rgba[3] == 10:
        return "tint_selected" if selected else "tint_hover"
    return "tint_hover" if selected else "tint_pressed"


def _radio_fill(w, _rgba):
    return "on_accent" if w.isChecked() else "control_pressed"


def _list_tint(_w, rgba):
    return {5: "tint_hover", 6: "tint_pressed", 9: "tint_pressed", 12: "tint_hover",
            15: "tint_pressed", 17: "tint_selected", 25: "tint_selected"}.get(rgba[3])


_W, _K = (255, 255, 255), (0, 0, 0)

# class (as named in the library's code) -> [(theme, (r, g, b, a), role or fn(self, rgba))]
PAINT_ROUTES: dict[str, list] = {
    "FluentWidget": [(L, (240, 244, 249, 255), "window"), (D, (32, 32, 32, 255), "window")],
    "NavigationWidget": [(L, _K + (255,), "fluent_text"), (D, _W + (255,), "fluent_text")],
    "NavigationPushButton": [(L, _K + (6,), _nav_tint), (L, _K + (10,), _nav_tint),
                             (D, _W + (6,), _nav_tint), (D, _W + (10,), _nav_tint)],
    "NavigationSeparator": [(L, _K + (15,), "fluent_divider"), (D, _W + (15,), "fluent_divider")],
    "NavigationItemHeader": [(L, (96, 96, 96, 255), "fluent_text_secondary"),
                             (D, (160, 160, 160, 255), "fluent_text_secondary")],
    "NavigationPanel": [(L, (255, 255, 255, 180), "flyout"), (D, (32, 32, 32, 200), "flyout")],
    "CardWidget": [(L, _W + (170,), "card"), (D, _W + (13,), "card"),
                   (L, _W + (64,), "card"), (D, _W + (21,), "card"), (D, _W + (8,), "card"),
                   (L, _K + (15,), "card_border"), (L, _K + (27,), "card_border"),
                   (D, _K + (20,), "card_border"), (D, _W + (18,), "card_border"),
                   (D, _W + (13,), "card_border")],
    "SimpleCardWidget": [(L, _W + (170,), "card"), (D, _W + (13,), "card"),
                         (L, _K + (12,), "card_border"), (D, _K + (48,), "card_border")],
    "RadioButton": [(L, _K + (255,), "fluent_text"), (D, _W + (255,), "fluent_text"),
                    (L, _K + (55,), "track"), (D, _W + (40,), "track"),
                    (L, _K + (153,), "track"), (D, _W + (153,), "track"),
                    (L, _K + (24,), "track"),
                    (L, _W + (255,), _radio_fill), (D, _K + (255,), _radio_fill),
                    (L, _K + (15,), "tint_hover"), (D, _W + (11,), "tint_hover"),
                    (L, _K + (6,), "control"), (D, _K + (26,), "control")],
    "Indicator": [(L, _K + (56,), "track"), (D, _W + (41,), "track"),
                  (L, _K + (23,), "tint_pressed"), (D, _W + (18,), "tint_pressed"),
                  (L, _K + (15,), "tint_hover"), (D, _W + (10,), "tint_hover"),
                  (L, _K + (133,), "track"), (D, _W + (153,), "track"),
                  (L, _W + (255,), "on_accent"), (D, _K + (255,), "on_accent"),
                  (D, _W + (77,), "on_accent"),
                  (L, _K + (156,), "track"), (D, _W + (201,), "track"),
                  (L, _K + (91,), "track"), (D, _W + (96,), "track")],
    "SwitchButton": [(L, _K + (255,), "fluent_text"), (D, _W + (255,), "fluent_text")],
    "SliderHandle": [(L, _K + (25,), "control_border"), (D, _K + (90,), "control_border"),
                     (L, _W + (255,), "control"), (D, (69, 69, 69, 255), "control")],
    "Slider": [(L, _K + (100,), "track"), (D, _W + (115,), "track")],
    "ProgressBar": [(L, _K + (155,), "track"), (D, _W + (155,), "track"),
                    (L, (157, 93, 0, 255), "warning"), (D, (252, 225, 0, 255), "warning"),
                    (L, (196, 43, 28, 255), "danger"), (D, (255, 153, 164, 255), "danger")],
    "ArrowButton": [(L, _K + (114,), "scrollbar"), (D, _W + (139,), "scrollbar")],
    "ScrollBarHandle": [(L, _K + (114,), "scrollbar"), (D, _W + (139,), "scrollbar")],
    "ScrollBarGroove": [(L, (252, 252, 252, 217), "flyout"), (D, (44, 44, 44, 245), "flyout")],
    "SpinFlyoutView": [(L, (249, 249, 249, 255), "flyout"), (D, (46, 46, 46, 255), "flyout"),
                       (L, _K + (15,), "flyout_border"), (D, _K + (51,), "flyout_border")],
    "MenuItemDelegate": [(L, _K + (25,), "fluent_divider"), (D, _W + (25,), "fluent_divider")],
    "ShortcutMenuItemDelegate": [(L, _K + (153,), "fluent_text_secondary"),
                                 (D, _W + (200,), "fluent_text_secondary")],
    "RadioIndicatorMenuItemDelegate": [(L, _K + (255,), "fluent_text"),
                                       (D, _W + (255,), "fluent_text")],
    "TableItemDelegate": [(L, _K + (255,), "fluent_text"), (D, _W + (255,), "fluent_text")]
    + [(t, (_W if t else _K) + (a,), _list_tint) for t in (L, D) for a in (5, 6, 9, 12, 15, 17, 25)]
    + [(L, _K + (6,), "control"), (D, _K + (26,), "control"),
       (L, _K + (122,), "track"), (D, _W + (142,), "track")],
    "HorizontalSeparator": [(L, _K + (22,), "fluent_divider"), (D, _W + (51,), "fluent_divider")],
    "VerticalSeparator": [(L, _K + (22,), "fluent_divider"), (D, _W + (51,), "fluent_divider")],
    "MessageBoxBase": [(L, _K + (76,), "overlay"), (D, _K + (76,), "overlay")],
    "Dialog": [(L, _K + (76,), "overlay"), (D, _K + (76,), "overlay")],
}
# Known and left alone: drop-shadow colours (not a palette colour in Fluent
# either: black at low alpha in both themes).
PAINT_IGNORED: dict[str, set] = {
    "MessageBoxBase": {_K + (50,)}, "Dialog": {_K + (50,)}, "ToolTip": {_K + (50,)},
}

_ROUTE_INDEX: dict = {}
for _cls, _entries in PAINT_ROUTES.items():
    for _theme, _rgba, _role in _entries:
        _ROUTE_INDEX.setdefault((_cls, _theme, _rgba), _role)

UNROUTED: set = set()      # (module, class, rgba) built by patched code with no route
_SEEN: set = set()          # (class, theme, rgba) routes actually used (tests)


def _route_from_frame(f, rgba):
    """(role, dark) for a colour built in frame *f*; None if unrouted."""
    from qfluentwidgets import isDarkTheme
    qual = f.f_code.co_qualname
    cls = qual.split(".")[0]
    dark = isDarkTheme()
    for th in (dark, not dark):
        role = _ROUTE_INDEX.get((cls, th, rgba))
        if role is not None:
            if callable(role):
                role = role(f.f_locals.get("self"), rgba)
                if role is None:
                    return None
            _SEEN.add((cls, th, rgba))
            return role, th
    if rgba[3] and rgba not in PAINT_IGNORED.get(cls, ()):
        UNROUTED.add((f.f_globals.get("__name__", "?"), qual, rgba))
    return None


class RoutedQColor(_RealQColor):
    """QColor as the patched library modules see it.  Calling it returns a
    plain QColor, never an instance of this class: a Python subclass reaches
    Qt as a QVariant holding a Python object, which QPropertyAnimation cannot
    interpolate (the window's background animated to black) and the QColor
    copy constructor refuses.  Built from numbers or Qt.white / Qt.black,
    the colour is moved with its role.  Class attributes (NameFormat,
    fromHsvF...) are QColor's."""

    def __new__(cls, *args):
        c = _RealQColor(*args)
        numbers = len(args) in (3, 4) and all(isinstance(x, int) for x in args)
        if numbers or (len(args) == 1 and isinstance(args[0], _RealQt.GlobalColor)):
            rgba = (c.red(), c.green(), c.blue(), c.alpha())
            hit = _route_from_frame(sys._getframe(1), rgba)
            if hit is not None:
                new = shift(rgba, hit[0], hit[1])
                if new is not None:
                    c.setRgb(*new)
        return c


class _GlobalColorProxy:
    def __getattr__(self, name):
        v = getattr(_RealQt.GlobalColor, name)
        if name in ("white", "black"):
            c = _RealQColor(v)
            rgba = (c.red(), c.green(), c.blue(), c.alpha())
            hit = _route_from_frame(sys._getframe(1), rgba)
            if hit is not None:
                new = shift(rgba, hit[0], hit[1])
                if new is not None:
                    return _RealQColor(*new)
        return v


class _QtProxy:
    """Qt as the patched modules see it: Qt.white / Qt.black are routed."""
    GlobalColor = _GlobalColorProxy()

    def __getattr__(self, name):
        v = getattr(_RealQt, name)
        if name in ("white", "black"):
            c = _RealQColor(v)
            rgba = (c.red(), c.green(), c.blue(), c.alpha())
            hit = _route_from_frame(sys._getframe(1), rgba)
            if hit is not None:
                new = shift(rgba, hit[0], hit[1])
                if new is not None:
                    return _RealQColor(*new)
        return v


_PAINT_MODULES = (
    "qfluentwidgets.window.fluent_window",
    "qfluentwidgets.components.navigation.navigation_widget",
    "qfluentwidgets.components.navigation.navigation_panel",
    "qfluentwidgets.components.widgets.card_widget",
    "qfluentwidgets.components.widgets.button",
    "qfluentwidgets.components.widgets.switch_button",
    "qfluentwidgets.components.widgets.slider",
    "qfluentwidgets.components.widgets.progress_bar",
    "qfluentwidgets.components.widgets.scroll_bar",
    "qfluentwidgets.components.widgets.spin_box",
    "qfluentwidgets.components.widgets.menu",
    "qfluentwidgets.components.widgets.table_view",
    "qfluentwidgets.components.widgets.separator",
    "qfluentwidgets.components.widgets.tool_tip",
    "qfluentwidgets.components.dialog_box.message_box_base",
    "qfluentwidgets.components.dialog_box.dialog",
)


# ══════════════════════════════════════════════════════════════════════════════
# 2 + 4. ACCENT FAMILY, ICONS, LABELS, FOCUS LINE
# ══════════════════════════════════════════════════════════════════════════════
_ACCENT_ROLE = {  # (ThemeColor member name, dark) -> role
    ("LIGHT_1", False): "accent_hover", ("LIGHT_3", False): "accent_pressed",
    ("DARK_1", True): "accent_hover", ("DARK_2", True): "accent_pressed",
}

_svg_fill_cache: dict = {}


def _svg_fill(path: str):
    if path not in _svg_fill_cache:
        from PySide6.QtCore import QFile
        f = QFile(path)
        fill = None
        if f.open(QFile.ReadOnly):
            m = re.search(rb'fill="(#[0-9A-Fa-f]{6})"', bytes(f.readAll()))
            f.close()
            fill = m.group(1).decode() if m else None
        _svg_fill_cache[path] = fill
    return _svg_fill_cache[path]


def icon_fill(icon, theme_):
    """The fill a Fluent svg icon is drawn with under the active palette, or
    None when the icon role did not move (draw the library's file as it is)."""
    from qfluentwidgets import Theme, isDarkTheme
    dark = isDarkTheme() if theme_ == Theme.AUTO else theme_ == Theme.DARK
    if delta("fluent_icon", dark) is None:
        return None
    lit = _svg_fill(icon.path(theme_))
    if lit is None:
        return None
    r, g, b, _a = routed(rgba_of(lit), "fluent_icon", dark)
    return f"#{r:02x}{g:02x}{b:02x}"


_installed = False
_labels: "weakref.WeakSet" = weakref.WeakSet()


def install() -> None:
    """Patch QFluentWidgets once (before the first widget is built)."""
    global _installed
    if _installed:
        return
    _installed = True
    import importlib

    from qfluentwidgets import Theme
    from qfluentwidgets.common import style_sheet as ss

    # 1. style sheets
    real_read = ss.getStyleSheetFromFile

    def read(file):
        qss = _RADIUS_5.sub(r"\g<1>4px", real_read(file))
        fname, dark = _fname_dark(file if isinstance(file, str) else file.fileName())
        if not fname:
            return qss
        qss = translate_qss(qss, fname, dark)
        if fname in PLACEHOLDER_QSS:
            qss += PLACEHOLDER_QSS[fname].format(_active["fluent_text_secondary"][dark])
        return qss
    ss.getStyleSheetFromFile = read

    # 2. accent family
    real_color = ss.ThemeColor.color

    def accent_color(self):
        c = real_color(self)
        if _active is TODAY:
            return c
        from qfluentwidgets import isDarkTheme
        dark = isDarkTheme()
        role = _ACCENT_ROLE.get((self._name_, dark), "accent_fill")
        s = shift((c.red(), c.green(), c.blue(), c.alpha()), role, dark)
        return c if s is None else _RealQColor(*s)
    ss.ThemeColor.color = accent_color

    # 3. paint code
    proxy = _QtProxy()
    for modname in _PAINT_MODULES:
        mod = importlib.import_module(modname)
        if hasattr(mod, "QColor"):
            mod.QColor = RoutedQColor
        if hasattr(mod, "Qt"):
            mod.Qt = proxy

    # 4a. Fluent svg icons
    from qfluentwidgets.common.icon import FluentIcon
    from qfluentwidgets.components.widgets.spin_box import SpinIcon
    for cls in (FluentIcon, SpinIcon):
        _wrap_icon(cls, Theme)

    # 4b. label default colour -> fluent_text; app roles via theme.label_role
    from qfluentwidgets.components.widgets.label import FluentLabelBase
    real_set = FluentLabelBase.setTextColor

    def set_text_color(self, light=None, dark=None):
        if light is None and dark is None:
            light = _RealQColor(*routed((0, 0, 0, 255), "fluent_text", False))
            dark = _RealQColor(*routed((255, 255, 255, 255), "fluent_text", True))
            self._pk_role = "fluent_text"
        else:
            role = getattr(self, "_pk_role", None)
            if role and not _same_pair(light, dark, _role_pair(role)):
                self._pk_role = None
        _labels.add(self)
        return real_set(self, light, dark)
    FluentLabelBase.setTextColor = set_text_color

    # 4c. focus line of inputs
    from qfluentwidgets.components.widgets import line_edit, spin_box
    for cls in (line_edit.LineEdit, spin_box.SpinBoxBase):
        _wrap_focus(cls)
    real_theme_color = line_edit.themeColor

    def focus_theme_color():
        from qfluentwidgets import isDarkTheme
        dark = isDarkTheme()
        if delta("focus_ring", dark) is None:
            return real_theme_color()
        return _RealQColor(_active["focus_ring"][dark])
    line_edit.themeColor = focus_theme_color


def _role_pair(role):
    if role == "fluent_text":
        return (_RealQColor(*routed((0, 0, 0, 255), "fluent_text", False)),
                _RealQColor(*routed((255, 255, 255, 255), "fluent_text", True)))
    return _RealQColor(_active[role][0]), _RealQColor(_active[role][1])


def _same_pair(light, dark, pair) -> bool:
    try:
        return (_RealQColor(light).rgba() == pair[0].rgba()
                and _RealQColor(dark).rgba() == pair[1].rgba())
    except TypeError:
        return False


# Greys the library passes as a fill string in its light branches (combo /
# drop-down arrow, line edit buttons, calendar / cycle list arrows).
LIBRARY_ICON_FILLS = {"#646464", "#656565", "#5e5e5e", "#9c9c9c"}


def _wrap_icon(cls, Theme):
    real_render, real_icon = cls.render, cls.icon

    def render(self, painter, rect, theme=Theme.AUTO, indexes=None, **attributes):
        if "fill" not in attributes:
            fill = icon_fill(self, theme)
            if fill is not None:
                attributes["fill"] = fill
        elif str(attributes["fill"]).lower() in LIBRARY_ICON_FILLS:
            from qfluentwidgets import isDarkTheme
            dark = isDarkTheme() if theme == Theme.AUTO else theme == Theme.DARK
            new = shift(rgba_of(attributes["fill"]), "fluent_icon", dark)
            if new is not None:
                attributes["fill"] = "#{:02x}{:02x}{:02x}".format(*new[:3])
        return real_render(self, painter, rect, theme, indexes, **attributes)

    def icon(self, theme=Theme.AUTO, color=None):
        if not color:
            color = icon_fill(self, theme)
        return real_icon(self, theme, color)
    cls.render, cls.icon = render, icon


def _wrap_focus(cls):
    real = cls.focusedBorderColor

    def focused(self):
        from qfluentwidgets import isDarkTheme
        dark = isDarkTheme()
        own = self.darkFocusedBorderColor if dark else self.lightFocusedBorderColor
        if (getattr(self, "isError", lambda: False)() or own.isValid()
                or delta("focus_ring", dark) is None):
            return real(self)
        return _RealQColor(_active["focus_ring"][dark])
    cls.focusedBorderColor = focused


# ── colours the library keeps on widgets (built once in __init__) ─────────────
# (class, light attribute, dark attribute, role, light literal, dark literal)
STORED = [
    ("FluentWidget", "_lightBackgroundColor", "_darkBackgroundColor", "window",
     (240, 244, 249, 255), (32, 32, 32, 255)),
    ("NavigationItemHeader", "lightTextColor", "darkTextColor", "fluent_text_secondary",
     (96, 96, 96, 255), (160, 160, 160, 255)),
    ("NavigationWidget", "lightTextColor", "darkTextColor", "fluent_text",
     _K + (255,), _W + (255,)),
    ("RadioButton", "_lightTextColor", "_darkTextColor", "fluent_text", _K + (255,), _W + (255,)),
    ("SwitchButton", "lightTextColor", "darkTextColor", "fluent_text", _K + (255,), _W + (255,)),
    ("ProgressBar", "lightBackgroundColor", "darkBackgroundColor", "track",
     _K + (155,), _W + (155,)),
    ("ArrowButton", "lightColor", "darkColor", "scrollbar", _K + (114,), _W + (139,)),
    ("ScrollBarHandle", "lightColor", "darkColor", "scrollbar", _K + (114,), _W + (139,)),
    ("ScrollBarGroove", "lightBackgroundColor", "darkBackgroundColor", "flyout",
     (252, 252, 252, 217), (44, 44, 44, 245)),
]


def retint(old: dict, new: dict) -> None:
    """After a palette switch: move the colours the library stored on live
    widgets, unless the app set its own (they do not match the old palette)."""
    from PySide6.QtWidgets import QApplication

    def under(pal, rgba, role, dark):
        saved = _active
        set_active(pal)
        try:
            return routed(rgba, role, dark)
        finally:
            set_active(saved)

    for w in QApplication.allWidgets():
        names = [c.__name__ for c in type(w).__mro__]
        for cls, la, da, role, lit_l, lit_d in STORED:
            if cls not in names:
                continue
            for attr, lit, dark in ((la, lit_l, False), (da, lit_d, True)):
                cur = getattr(w, attr, None)
                if cur is None:
                    continue
                if rgba_of(cur) == under(old, lit, role, dark):
                    setattr(w, attr, _RealQColor(*under(new, lit, role, dark)))
            break
        if hasattr(w, "_updateBackgroundColor"):
            try:
                w._updateBackgroundColor()
            except (RuntimeError, AttributeError):
                pass
    for lbl in list(_labels):
        role = getattr(lbl, "_pk_role", None)
        if role:
            try:
                lbl.setTextColor(*_role_pair(role)) if role != "fluent_text" else lbl.setTextColor()
            except RuntimeError:
                pass
