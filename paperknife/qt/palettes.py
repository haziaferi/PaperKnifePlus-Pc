"""
paperknife.qt.palettes
The colour palettes of the Qt interface: plain data, one dict per palette,
role name -> (light, dark).  A colour is "#RRGGBB" or "#AARRGGBB" (Qt's
HexArgb, alpha first).

theme.py reads the active palette (env PK_PALETTE, default
"windows-oxford-s1"; theme.apply_palette(name) at run time).  Two kinds of role:

- APP roles: read by paperknife's own code (theme.color / hex_color / pair,
  style sheets it writes, QPainter code) and used as they are.
- FLUENT roles: colours QFluentWidgets draws by itself (its .qss files and
  its paint code).  fluent_route.py gives every library colour a role and
  moves it by exactly as much as that role moved from "today" (the colours
  QFluentWidgets ships with, kept as the reference), so the library's own
  shading between states (rest / hover / pressed) is kept and the role's
  value is drawn exactly.  Under "today" nothing moves.

ROLES says where each role reaches the screen.

The default, "windows-oxford-s1", is the owner's pick from the phase 6 colour
scorer's shortlist (Windows 11 neutrals with Oxford blue, every text pair AA).
It is generated between the GENERATED markers from phase6/colour/candidates.json
by phase6/colour/to_app_palettes.py: the scorer's 24 roles directly, the rest
tone-on-tone from an anchor scorer role at today's OKLCH offset.
"""
from __future__ import annotations

DEFAULT = "windows-oxford-s1"

# role -> where it is applied
ROLES: dict[str, str] = {
    # ── app roles ──
    "accent": "app accents: splitter hover, thumbnail / row selection frame, find and "
              "edit-text highlights; also the base Fluent derives its accent family from "
              "(setThemeColor keeps today's base; the accent_* roles move the family)",
    "selection": "selected collection row; selected / hovered thumbnail (alpha 46 / 18 "
                 "kept per site, RGB from the role)",
    "text": "app ink: Segoe Fluent glyphs (navigation, rail, buttons), painted captions "
            "(thumbnail labels), the compact search glyph",
    "muted": "secondary captions (muted_caption, status bar at rest, notes), unselected "
             "thumbnail labels, the Home placeholder glyph",
    "success": "status text: success",
    "warning": "status text: warning; redact warning, missing-tool notes",
    "danger": "status text: error; danger buttons; redact boxes and pending count; "
              "the title bar's close button (hover / pressed, moved with this role)",
    "danger_hover": "danger button hover / pressed",
    "on_danger": "text on a danger button",
    "surface": "ground behind a revealed (auto-hiding) title bar",
    "divider": "the app's own 1 px dividers (setting rows, panels)",
    "overlay": "veil over a locked page",
    "drop_zone": "empty file card / missing thumbnail ground",
    "page_bg": "behind a rendered PDF page (page views)",
    "thumb_border": "thumbnail and Home recent-file frames",
    # ── Fluent roles ──
    "window": "window background (FluentWindow; shown when Mica is off - a palette "
              "that changes this role turns Mica off)",
    "nav_pane": "navigation pane background when docked (transparent today)",
    "layer": "the rounded layer the pages sit on (StackedWidget)",
    "layer_border": "that layer's top-left border",
    "card": "card surface (SimpleCardWidget / CardWidget, rest / hover / pressed)",
    "card_border": "card border",
    "control": "button / line edit / combo / spin box fill at rest",
    "control_hover": "control fill under the pointer",
    "control_pressed": "control fill pressed",
    "control_disabled": "control fill disabled",
    "control_border": "control border",
    "control_border_strong": "the darker bottom (light) / lighter top (dark) edge of buttons",
    "input_underline": "line edit / spin box bottom line at rest",
    "tint_hover": "hover tint of transparent things (navigation items, transparent "
                  "buttons, list rows, menu items, title bar buttons)",
    "tint_pressed": "pressed tint of the same",
    "tint_selected": "selected navigation item / list row / menu item tint",
    "fluent_text": "Fluent text: labels, buttons, inputs, navigation items, menus",
    "fluent_text_secondary": "Fluent secondary text: placeholders, item headers, "
                             "pressed button text",
    "fluent_text_disabled": "Fluent disabled text",
    "fluent_icon": "Fluent's own svg icons (combo arrow, search / clear, spin arrows, "
                   "page arrows, list buttons)",
    "fluent_divider": "Fluent separators (navigation, menus)",
    "flyout": "menus, tool tips, dialogs, the navigation pane when it floats",
    "flyout_border": "their border",
    "track": "slider groove, progress track, switch / radio rings, list check boxes",
    "scrollbar": "scroll bar handle and arrows",
    "accent_fill": "Fluent's accent fill: primary buttons, checked toggles, slider, "
                   "switch, progress bar, navigation selection mark",
    "accent_hover": "Fluent's accent fill under the pointer",
    "accent_pressed": "Fluent's accent fill pressed",
    "on_accent": "text / marks on an accent fill (primary button text, radio dot, "
                 "switch knob, selected-text colour)",
    "focus_ring": "focus line of line edits / spin boxes",
    "success_tint": "success info bar background",
    "warning_tint": "warning info bar background (OCR: Tesseract missing)",
    "danger_tint": "error info bar background",
}

TODAY: dict[str, tuple[str, str]] = {
    # app (values as they were in theme.COLORS)
    "accent":       ("#2B4C8C", "#4468A5"),
    "selection":    ("#282B4C8C", "#284468A5"),
    "text":         ("#1C1A17", "#E8DEC8"),
    "muted":        ("#6B645B", "#A89D90"),
    "success":      ("#2D6A4F", "#6FBF97"),
    "warning":      ("#9A5A00", "#E0A84A"),
    "danger":       ("#9B1B1B", "#E57373"),
    "danger_hover": ("#7A1414", "#C85C5C"),
    "on_danger":    ("#FFFFFF", "#000000"),   # dark: the light red needs dark text (AA)
    "surface":      ("#F3F3F3", "#202020"),
    "divider":      ("#14000000", "#1FFFFFFF"),
    "overlay":      ("#33FFFFFF", "#33000000"),
    "drop_zone":    ("#0A000000", "#0FFFFFFF"),
    "page_bg":      ("#F0EBE3", "#242019"),
    "thumb_border": ("#1F000000", "#2EFFFFFF"),
    # Fluent (QFluentWidgets 1.11.3's own values; reference literal per role)
    "window":                ("#F0F4F9", "#202020"),
    "nav_pane":              ("#00000000", "#00000000"),
    "layer":                 ("#80FFFFFF", "#08FFFFFF"),
    "layer_border":          ("#11000000", "#2E000000"),
    "card":                  ("#AAFFFFFF", "#0DFFFFFF"),
    "card_border":           ("#0C000000", "#30000000"),
    "control":               ("#B3FFFFFF", "#0FFFFFFF"),
    "control_hover":         ("#80F9F9F9", "#15FFFFFF"),
    "control_pressed":       ("#4CF9F9F9", "#08FFFFFF"),
    "control_disabled":      ("#4CF9F9F9", "#0BFFFFFF"),
    "control_border":        ("#13000000", "#0EFFFFFF"),
    "control_border_strong": ("#2F000000", "#14FFFFFF"),
    "input_underline":       ("#64000000", "#8BFFFFFF"),
    # the tints' reference is the list row (TableItemDelegate), the site the
    # colour scorer models: hover c@12, pressed c@6 / c@9, selected c@17
    "tint_hover":            ("#0C000000", "#0CFFFFFF"),
    "tint_pressed":          ("#06000000", "#09FFFFFF"),
    "tint_selected":         ("#11000000", "#11FFFFFF"),
    "fluent_text":           ("#000000", "#FFFFFF"),
    "fluent_text_secondary": ("#9B000000", "#9BFFFFFF"),
    "fluent_text_disabled":  ("#5C000000", "#5CFFFFFF"),
    "fluent_icon":           ("#000000", "#FFFFFF"),
    "fluent_divider":        ("#0F000000", "#0FFFFFFF"),
    "flyout":                ("#F9F9F9", "#2B2B2B"),
    "flyout_border":         ("#1A000000", "#1AFFFFFF"),
    "track":                 ("#64000000", "#73FFFFFF"),
    "scrollbar":             ("#72000000", "#8BFFFFFF"),
    "accent_fill":           ("#2B4C8C", "#81B0FF"),   # Fluent's PRIMARY from today's accent
    "accent_hover":          ("#2D5093", "#749EE6"),   # LIGHT_1 / DARK_1
    "accent_pressed":        ("#516793", "#6C92D1"),   # LIGHT_3 / DARK_2
    "on_accent":             ("#FFFFFF", "#000000"),
    "focus_ring":            ("#2B4C8C", "#81B0FF"),
    "success_tint":          ("#DFF6DD", "#393D1B"),
    "warning_tint":          ("#FFF4CE", "#433519"),
    "danger_tint":           ("#FDE7E9", "#442726"),
}

# Test only: a loud, distinct colour per role (light and dark distinct too),
# so a pixel sample tells which role painted it.  Opaque on purpose.
PROBE: dict[str, tuple[str, str]] = {
    "accent":                ("#FF0000", "#00FFFF"),
    "selection":             ("#FF8000", "#0080FF"),
    "text":                  ("#C00040", "#40FFC0"),
    "muted":                 ("#808000", "#8080FF"),
    "success":               ("#00C000", "#FF40FF"),
    "warning":               ("#C08000", "#4080FF"),
    "danger":                ("#C000C0", "#40FF40"),
    "danger_hover":          ("#800080", "#80FF80"),
    "on_danger":             ("#FFFF00", "#0000FF"),
    "surface":               ("#00FF80", "#FF0080"),
    "divider":               ("#FF00FF", "#00FF00"),
    "overlay":               ("#4000FF", "#C0FF00"),
    "drop_zone":             ("#00C0C0", "#C04040"),
    "page_bg":               ("#80FF00", "#8000FF"),
    "thumb_border":          ("#FF0080", "#00FF80"),
    "window":                ("#FFC0C0", "#400000"),
    "nav_pane":              ("#C0FFC0", "#004000"),
    "layer":                 ("#C0C0FF", "#000040"),
    "layer_border":          ("#FF6000", "#00A0FF"),
    "card":                  ("#FFFFA0", "#404000"),
    "card_border":           ("#0060FF", "#FFA000"),
    "control":               ("#A0FFFF", "#004040"),
    "control_hover":         ("#FFA0FF", "#400040"),
    "control_pressed":       ("#A0A0FF", "#202060"),
    "control_disabled":      ("#D0D0A0", "#505020"),
    "control_border":        ("#00A060", "#FF60A0"),
    "control_border_strong": ("#6000A0", "#A0FF60"),
    "input_underline":       ("#A06000", "#60A0FF"),
    "tint_hover":            ("#FFD000", "#0030FF"),
    "tint_pressed":          ("#D0FF00", "#3000FF"),
    "tint_selected":         ("#00FFD0", "#FF0030"),
    "fluent_text":           ("#0000C0", "#FFFF40"),
    "fluent_text_secondary": ("#006000", "#FFA0FF"),
    "fluent_text_disabled":  ("#600000", "#A0FFFF"),
    "fluent_icon":           ("#C06000", "#40A0FF"),
    "fluent_divider":        ("#00C000", "#FF40C0"),
    "flyout":                ("#E0FFE0", "#200020"),
    "flyout_border":         ("#FF2000", "#00E0FF"),
    "track":                 ("#2000FF", "#E0FF00"),
    "scrollbar":             ("#00FF20", "#FF00E0"),
    "accent_fill":           ("#E00060", "#20FF90"),
    "accent_hover":          ("#A00040", "#10C060"),
    "accent_pressed":        ("#600020", "#008040"),
    "on_accent":             ("#FFFF80", "#000080"),
    "focus_ring":            ("#00E000", "#E000E0"),
    "success_tint":          ("#B0FFB0", "#105010"),
    "warning_tint":          ("#FFE0B0", "#503010"),
    "danger_tint":           ("#FFB0D0", "#501030"),
}

# ── GENERATED by phase6/colour/to_app_palettes.py from candidates.json ──
# (do not edit by hand; the rule and the mapping are in that script)
CANDIDATE_WINDOWS_OXFORD_S1: dict[str, tuple[str, str]] = {   # windows-oxford/search-1
    "accent": ("#324D81", "#8AB1F0"),
    "selection": ("#62324D81", "#4F8AB1F0"),
    "text": ("#000000", "#FFFFFF"),
    "muted": ("#606060", "#CECECE"),
    "success": ("#1D7B5B", "#A1F9D3"),
    "warning": ("#8A681B", "#F4C181"),
    "danger": ("#742D33", "#D5857E"),
    "danger_hover": ("#793137", "#C2746D"),
    "on_danger": ("#FCFCFC", "#121212"),
    "surface": ("#F3F3F3", "#202020"),
    "divider": ("#F1F1F1", "#575757"),
    "overlay": ("#33FAFAFC", "#33101114"),
    "drop_zone": ("#EFEFEF", "#3B3B3B"),
    "page_bg": ("#F0EBE3", "#242019"),
    "thumb_border": ("#D9D9D9", "#595959"),
    "window": ("#F3F3F3", "#202020"),
    "nav_pane": ("#00000000", "#00000000"),
    "layer": ("#F9F9F9", "#272727"),
    "layer_border": ("#DEDEDE", "#1C1C1C"),
    "card": ("#FCFCFC", "#313131"),
    "card_border": ("#ECECEC", "#2B2B2B"),
    "control": ("#FDFDFD", "#3D3D3D"),
    "control_hover": ("#FAFAFA", "#424242"),
    "control_pressed": ("#FBFBFB", "#373737"),
    "control_disabled": ("#FBFBFB", "#3A3A3A"),
    "control_border": ("#E9E9E9", "#3C3C3C"),
    "control_border_strong": ("#CDCDCD", "#414141"),
    "input_underline": ("#8F8F8F", "#7D7D7D"),
    "tint_hover": ("#F1F1F1", "#3A3A3A"),
    "tint_pressed": ("#F7F7F7", "#373737"),
    "tint_selected": ("#B0BCD1", "#4E5A6D"),
    "fluent_text": ("#000000", "#FFFFFF"),
    "fluent_text_secondary": ("#606060", "#CECECE"),
    "fluent_text_disabled": ("#A2A2A2", "#7C7C7C"),
    "fluent_icon": ("#000000", "#FFFFFF"),
    "fluent_divider": ("#F6F6F6", "#4A4A4A"),
    "flyout": ("#F8F8F8", "#2A2A2A"),
    "flyout_border": ("#DBDBDB", "#434343"),
    "track": ("#8F8F8F", "#6A6A6A"),
    "scrollbar": ("#7F7F7F", "#787878"),
    "accent_fill": ("#324D81", "#8AB1F0"),
    "accent_hover": ("#365186", "#799FDD"),
    "accent_pressed": ("#55678B", "#7393C5"),
    "on_accent": ("#FFFFFF", "#000000"),
    "focus_ring": ("#324D81", "#8AB1F0"),
    "success_tint": ("#FAFFFA", "#666E4A"),
    "warning_tint": ("#F7FADA", "#564934"),
    "danger_tint": ("#E7DADD", "#422D2B"),
}
CANDIDATES = {
    "windows-oxford-s1": CANDIDATE_WINDOWS_OXFORD_S1,
}
# ── END GENERATED ──

PALETTES: dict[str, dict[str, tuple[str, str]]] = {
    "today": TODAY,
    "probe": PROBE,
    **CANDIDATES,
}
