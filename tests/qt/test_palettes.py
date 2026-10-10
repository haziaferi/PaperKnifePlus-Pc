"""
One palette colours the whole Qt app (paperknife/qt/palettes.py, theme.py,
fluent_route.py).

The probe palette gives every role a loud colour of its own; the window is
built under it and real pixels are sampled where each role should show
(window, navigation, layer, cards, text, controls, accent, focus line,
status text, overlay, title bar, thumbnails...).  A colour the routing
missed keeps today's value and the sample fails; a library colour built by
code no route covers lands in fluent_route.UNROUTED and fails the test too.

Under "today" the plumbing changes nothing: the pixel control for that is
the screenshot comparison of all screens (see the branch's report); here a
page grabbed before a switch to probe and back, and under a value-for-value
copy of today (which takes the rewriting path, not the shortcut), is
identical.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from qt_harness import make_pdf, pump

ROOT = Path(__file__).resolve().parents[2]


# ── pixel helpers ─────────────────────────────────────────────────────────────
def _grab(win):
    from PySide6.QtGui import QImage
    return win.grab().toImage().convertToFormat(QImage.Format_RGB32)


def _rect(win, w, x0=0, y0=0, x1=None, y1=None):
    """w's rectangle in window coordinates, optionally a sub-rectangle
    (negative x1 / y1 count from the right / bottom)."""
    from PySide6.QtCore import QPoint, QRect
    tl = w.mapTo(win, QPoint(0, 0))
    W, H = w.width(), w.height()
    x0 = W + x0 if x0 < 0 else x0
    y0 = H + y0 if y0 < 0 else y0
    x1 = W if x1 is None else (W + x1 if x1 < 0 else x1)
    y1 = H if y1 is None else (H + y1 if y1 < 0 else y1)
    return QRect(tl.x() + x0, tl.y() + y0, max(1, x1 - x0), max(1, y1 - y0))


def _pixels(img, r):
    out = set()
    for y in range(max(0, r.top()), min(img.height(), r.bottom() + 1)):
        for x in range(max(0, r.left()), min(img.width(), r.right() + 1)):
            c = img.pixel(x, y)
            out.add(((c >> 16) & 255, (c >> 8) & 255, c & 255))
    return out


def _diff(a, b):
    """Where two grabs differ: (count, bbox) - for the assertion message."""
    pts = [(x, y) for y in range(a.height()) for x in range(a.width())
           if a.pixel(x, y) != b.pixel(x, y)]
    if not pts:
        return 0, None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return len(pts), (min(xs), min(ys), max(xs), max(ys))


def _near(a, b, tol):
    return all(abs(a[i] - b[i]) <= tol for i in range(3))


def _rgb(hexstr):
    from PySide6.QtGui import QColor
    c = QColor(hexstr)
    return c.red(), c.green(), c.blue()


class Probe:
    """Expected colours under the probe palette for one theme."""

    def __init__(self, dark):
        from paperknife.qt import palettes
        self.dark = dark
        self.pal = palettes.PROBE

    def role(self, name):
        return _rgb(self.pal[name][self.dark])

    def routed(self, rgba, name):
        from paperknife.qt import fluent_route
        return fluent_route.routed(rgba, name, self.dark)[:3]

    def blend(self, top_rgb, alpha, under_rgb):
        a = alpha / 255
        return tuple(round(top_rgb[i] * a + under_rgb[i] * (1 - a)) for i in range(3))


def _has(img, r, rgb, what, tol=2):
    px = _pixels(img, r)
    assert any(_near(p, rgb, tol) for p in px), (
        f"{what}: #{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x} not among the "
        f"{len(px)} colours in {r.x()},{r.y()} {r.width()}x{r.height()}: "
        + " ".join(f"#{p[0]:02x}{p[1]:02x}{p[2]:02x}" for p in sorted(px)[:8]))


def _tinted(img, r, rgb, others, what):
    """A thin antialiased line: some pixel is rgb blended (>= 40 %) with one
    of *others* (what lies beside it)."""
    px = _pixels(img, r)
    for p in px:
        for o in others:
            for t10 in range(4, 11):
                t = t10 / 10
                mix = tuple(rgb[i] * t + o[i] * (1 - t) for i in range(3))
                if _near(p, mix, 6):
                    return
    raise AssertionError(f"{what}: no pixel of #{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x} "
                         f"(blended) in {r.x()},{r.y()} {r.width()}x{r.height()}")


# ── fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def probe(qapp, request):
    """The probe palette (and the theme the test is parametrized with) set
    before the window is built; the default palette and light put back afterwards."""
    from paperknife.qt import fluent_route, palettes, theme
    dark = getattr(request, "param", False)
    theme.apply_appearance("dark" if dark else "light")
    theme.apply_palette("probe")
    fluent_route.UNROUTED.clear()
    yield Probe(dark)
    theme.apply_palette(palettes.DEFAULT)
    theme.apply_appearance("light")
    pump(0.05)


def _hover(w, bottom=False):
    """Move the offscreen platform's pointer onto *w* (its centre, or near
    its bottom-left: an empty part of the page layer)."""
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    QTest.mouseMove(w, QPoint(20, w.height() - 20) if bottom else w.rect().center())
    pump(0.2)


def _open(win, cls, path=None, wait=0.9):      # the selection mark slides for a while
    assert win.open_tool(cls, path)
    pump(wait)
    return win.current_page()


def _find(page, cls_name, pred=lambda w: True):
    from PySide6.QtWidgets import QWidget
    for w in page.findChildren(QWidget):
        if any(c.__name__ == cls_name for c in type(w).__mro__) and w.isVisible() and pred(w):
            return w
    raise AssertionError(f"no visible {cls_name} on {type(page).__name__}")


# ══════════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("probe", [False, True], ids=["light", "dark"], indirect=True)
def test_every_role_reaches_the_screen(probe, window, tmp_path):
    from PySide6.QtGui import QIcon
    from paperknife.qt import fluent_route, pages
    P, win, dark = probe, window, probe.dark
    win.resize(1280, 820)
    ink = (255, 255, 255) if dark else (0, 0, 0)     # the library's text / tint base

    # ── shell, on Compress (with a document: no drop target in the first card's place) ──
    page = _open(win, "CompressTool", make_pdf(tmp_path / "doc.pdf"))
    img = _grab(win)
    _has(img, _rect(win, win.status_bar, 0, 0, -1, None), P.role("window"), "window (status bar ground)")
    _has(img, _rect(win, win.status_label), P.role("muted"), "status text at rest")
    header = next(h for _s, h, _k in win._sections if h is not None)
    _has(img, _rect(win, header), P.role("nav_pane"), "navigation pane")
    _has(img, _rect(win, header), P.routed(((160, 160, 160) if dark else (96, 96, 96)) + (255,),
                                           "fluent_text_secondary"), "navigation section header")
    home_item = win._items["home"]
    _has(img, _rect(win, home_item), P.role("text"), "navigation glyph (app ink)")
    _has(img, _rect(win, home_item), P.role("fluent_text"), "navigation item text")
    cur = win._items["CompressTool"]
    _has(img, _rect(win, cur, 60, 0, -4, None), P.routed(ink + (10,), "tint_selected"),
         "selected navigation item", tol=3)
    _has(img, _rect(win, cur, 0, 0, 10, None), P.role("accent_fill"), "navigation selection mark")
    edit = win.search.edit
    _has(img, _rect(win, edit, 4, 4, 40, -4), P.role("control"), "search box fill")
    _has(img, _rect(win, edit, 6, -2, -6, None), P.role("input_underline"), "search box underline")
    # thin antialiased strokes: the icon colour shows blended with the field
    icon_ink = P.role("fluent_icon") if dark else P.routed((0x65, 0x65, 0x65, 255), "fluent_icon")
    _tinted(img, _rect(win, edit, -32, 0, None, None), icon_ink, [P.role("control")],
            "Fluent search icon")
    sw = win.stackedWidget
    _has(img, _rect(win, sw, 20, -30, -20, -10), P.role("layer"), "page layer")
    _has(img, _rect(win, sw, 0, 40, 2, 300), P.role("layer_border"), "page layer border")

    # ── a ToolPage: card, divider, primary, buttons, radios, labels ──
    card = _find(page, "SimpleCardWidget", lambda c: c.height() > 120)
    _has(img, _rect(win, card, 6, 6, 40, 20), P.role("card"), "card")
    _tinted(img, _rect(win, card, 30, 0, 200, 3), P.role("card_border"),
            [P.role("card"), P.role("layer")], "card border")
    div = _find(page, "Divider")
    _has(img, _rect(win, div), P.role("divider"), "app divider")
    title = _find(page, "BodyLabel", lambda w: w.text() == "Light")
    _has(img, _rect(win, title), P.role("fluent_text"), "label text")
    desc = _find(card, "CaptionLabel")
    _has(img, _rect(win, desc), P.role("muted"), "muted caption")
    prim = next(b for b in page.findChildren(pages.PrimaryPushButton) if getattr(b, "pk_primary", 0))
    _has(img, _rect(win, prim, 4, 4, -4, -4), P.role("accent_fill"), "primary button")
    _has(img, _rect(win, prim, 4, 4, -4, -4), P.role("on_accent"), "primary button text")
    # The page's own "Choose file" button went with the file card (2026-10-10):
    # the Open control's main part is the plain PushButton now.
    btn = (win.doc_slot or page.doc_bar).open_control.button
    assert btn.isVisible() and btn.text() == "Open"

    _has(img, _rect(win, btn, 3, 3, 12, -3), P.role("control"), "button fill")
    _has(img, _rect(win, btn, 8, 0, -8, 1), P.role("control_border_strong" if dark else "control_border"),
         "button top edge")
    _has(img, _rect(win, btn, 8, -1, -8, None), P.role("control_border" if dark else "control_border_strong"),
         "button bottom edge")
    _has(img, _rect(win, btn, 3, 3, -3, -3), P.role("fluent_text"), "button text")
    radio = _find(page, "RadioButton", lambda r: r.isChecked())
    _has(img, _rect(win, radio), P.role("accent_fill"), "checked radio ring")
    _has(img, _rect(win, radio), P.role("on_accent"), "checked radio dot")

    # states: hover through the offscreen platform's own pointer (QTest; the
    # real one is never touched), pressed through setDown
    _hover(btn)
    _has(_grab(win), _rect(win, btn, 3, 3, 12, -3), P.role("control_hover"), "button hover")
    _hover(prim)
    _has(_grab(win), _rect(win, prim, 4, 4, -4, -4), P.role("accent_hover"), "primary hover")
    _hover(win.stackedWidget, bottom=True)
    btn.setDown(True), prim.setDown(True)
    pump(0.05)
    img = _grab(win)
    _has(img, _rect(win, btn, 3, 3, 12, -3), P.role("control_pressed"), "button pressed")
    _has(img, _rect(win, prim, 4, 4, -4, -4), P.role("accent_pressed"), "primary pressed")
    btn.setDown(False), prim.setDown(False)
    btn.setEnabled(False)
    pump(0.05)
    img = _grab(win)
    _has(img, _rect(win, btn, 3, 3, 12, -3), P.role("control_disabled"), "button disabled")
    _has(img, _rect(win, btn, 3, 3, -3, -3), P.role("fluent_text_disabled"), "disabled text")
    btn.setEnabled(True)

    # ── status text roles, progress strip, overlay, title bar ──
    for role in ("success", "warning", "danger"):
        win.set_status("Probe", role)
        pump(0.02)
        _has(_grab(win), _rect(win, win.status_label), P.role(role), f"status text: {role}")
    win.progress_strip.show()
    win.progress.setValue(500)
    pump(0.05)
    img = _grab(win)
    _has(img, _rect(win, win.progress, 0, 0, 40, None), P.role("accent_fill"), "progress bar")
    _tinted(img, _rect(win, win.progress, -60, 0, None, None),   # a 1 px antialiased line
            P.routed(ink + (155,), "track"), [P.role("window")], "progress track")
    win.progress_strip.hide()
    win._lock_view()
    pump(0.05)
    _has(_grab(win), _rect(win, win.lock_overlay, 40, 40, 80, 80), P.role("overlay"), "lock veil")
    win._unlock_view()
    win._show_top()
    pump(0.5)
    img = _grab(win)
    _has(img, _rect(win, win.titleBar, 100, 2, 300, -2), P.role("surface"), "revealed title bar")
    _has(img, _rect(win, win.titleBar, -50, 0, None, None), P.role("fluent_text"), "title bar buttons")
    win._hide_top()
    pump(0.5)

    # ── Settings: combo, spin box, a flyout ──
    page = _open(win, "SettingsTool")
    img = _grab(win)
    combo = page.appearance
    _has(img, _rect(win, combo, 3, 3, 20, -3), P.role("control"), "combo fill")
    arrow = P.role("fluent_icon") if dark else P.routed((0x64, 0x64, 0x64, 255), "fluent_icon")
    _tinted(img, _rect(win, combo, -30, 0, None, None), arrow, [P.role("control")], "combo arrow")
    _has(img, _rect(win, combo, 3, 3, -30, -3), P.role("fluent_text"), "combo text")
    spin = page.max_recent
    _has(img, _rect(win, spin, 3, 3, 20, -3), P.role("control"), "spin box fill")
    from paperknife.qt import fluent_route as fr
    up = fr._svg_fill(f":/qfluentwidgets/images/spin_box/Up_{'white' if dark else 'black'}.svg")
    _tinted(img, _rect(win, spin, -60, 0, None, None), P.routed(fr.rgba_of(up), "fluent_icon"),
            [P.role("control"), P.role("control_hover"), P.role("tint_hover")], "spin box arrows")
    combo._showComboMenu()
    pump(0.4)
    menu = combo.dropMenu
    mimg = menu.view.grab().toImage()
    from PySide6.QtCore import QRect
    _has(mimg, QRect(4, 4, 30, 10), P.role("flyout"), "drop-down menu")
    _has(mimg, QRect(10, 4, menu.view.width() - 20, menu.view.height() - 8),
         P.role("fluent_text"), "menu item text")
    combo._closeComboMenu()
    pump(0.2)

    # ── Crop: a switch, off and on ──
    page = _open(win, "CropTool")
    sw_ = page.reset
    img = _grab(win)
    _has(img, _rect(win, sw_.indicator), P.routed(ink + (201 if dark else 156,), "track"),
         "switch knob off", tol=3)
    sw_.setChecked(True)
    pump(0.4)
    img = _grab(win)
    _has(img, _rect(win, sw_.indicator), P.role("accent_fill"), "switch on")
    _has(img, _rect(win, sw_.indicator), P.role("on_accent"), "switch knob on")
    sw_.setChecked(False)

    # ── Watermark: slider, line edit focus ──
    page = _open(win, "WatermarkTool")
    img = _grab(win)
    slider = _find(page, "Slider")
    _has(img, _rect(win, slider), P.role("accent_fill"), "slider fill")
    _has(img, _rect(win, slider), P.role("track"), "slider groove")
    _has(img, _rect(win, slider.handle), P.routed(((69, 69, 69) if dark else (255, 255, 255)) + (255,),
                                                  "control"), "slider handle ring")
    win.activateWindow()
    page.text.setFocus()
    pump(0.1)
    assert page.text.hasFocus()
    _has(_grab(win), _rect(win, page.text, 6, -2, -6, None), P.role("focus_ring"), "focus line")
    page.text.clearFocus()

    # ── Merge (collection): transparent tool buttons with Fluent icons ──
    page = _open(win, "MergeTool")
    img = _grab(win)
    tb = page.add_btn
    _tinted(img, _rect(win, tb), P.role("fluent_icon"), [P.role("card"), P.role("layer")],
            "toolbar icon")
    _has(img, _rect(win, tb), P.role("fluent_text"), "toolbar text")
    _hover(tb)
    _has(_grab(win), _rect(win, tb, 2, 2, 8, -2), P.routed(ink + (9,), "tint_hover"),
         "transparent button hover", tol=3)
    tb.setDown(True)
    pump(0.05)
    _has(_grab(win), _rect(win, tb, 2, 2, 8, -2), P.routed(ink + (6,), "tint_pressed"),
         "transparent button pressed", tol=3)
    tb.setDown(False)
    _hover(win.stackedWidget, bottom=True)

    # ── Reader (workspace): page ground, rail glyphs ──
    page = _open(win, "ReaderTool")
    img = _grab(win)
    # It shows the current document now (2026-10-10): the ground in the gap above page 1.
    _has(img, _rect(win, page.view, 10, 1, 60, 8), P.role("page_bg"), "page ground")

    page = _open(win, "AnnotateTool")
    img = _grab(win)
    rail_btn = next(w for w in (page.rail.itemAt(i).widget() for i in range(page.rail.count()))
                    if getattr(w, "pk_glyph", None) and not w.isChecked())
    _tinted(img, _rect(win, rail_btn), P.role("text"), [P.role("card"), P.role("layer")], "rail glyph")

    # ── Redact: the danger action ──
    page = _open(win, "RedactTool")
    img = _grab(win)
    danger = next(b for b in page.findChildren(pages.PrimaryPushButton) if getattr(b, "pk_primary", 0))
    _has(img, _rect(win, danger, 4, 4, -4, -4), P.role("danger"), "danger button")
    _has(img, _rect(win, danger, 4, 4, -4, -4), P.role("on_danger"), "danger button text")
    _hover(danger)
    _has(_grab(win), _rect(win, danger, 4, 4, -4, -4), P.role("danger_hover"), "danger hover")
    _hover(win.stackedWidget, bottom=True)

    # ── OCR: the warning info bar (only while Tesseract is missing) ──
    page = _open(win, "OCRTool")
    bar = getattr(page, "missing", None)
    if bar is not None and bar.isVisible():
        _has(_grab(win), _rect(win, bar, 6, 6, -6, -6), P.role("warning_tint"), "warning info bar")

    # ── Rotate (organiser, loaded): thumbnails, selection, missing thumb ──
    pdf = make_pdf(tmp_path / "p.pdf", pages=3)
    page = _open(win, "RotateTool", pdf, wait=1.5)
    grid = page.grid
    assert grid.count() == 3
    grid.item(2).setIcon(QIcon())                     # a thumbnail not rendered yet
    grid.item(0).setSelected(True)
    pump(0.1)
    img = _grab(win)
    r1 = grid.visualItemRect(grid.item(1))
    r1.translate(grid.viewport().mapTo(win, grid.viewport().rect().topLeft()))
    _has(img, r1, P.role("thumb_border"), "thumbnail frame")
    _has(img, r1, P.role("muted"), "thumbnail label")
    r0 = grid.visualItemRect(grid.item(0))
    r0.translate(grid.viewport().mapTo(win, grid.viewport().rect().topLeft()))
    _has(img, r0, P.blend(P.role("selection"), 46, P.role("card")), "selected thumbnail", tol=3)
    _has(img, r0, P.role("text"), "selected thumbnail label")
    r2 = grid.visualItemRect(grid.item(2))
    r2.translate(grid.viewport().mapTo(win, grid.viewport().rect().topLeft()))
    _has(img, r2, P.role("drop_zone"), "missing thumbnail ground")

    # Home
    page = _open(win, "home")
    img = _grab(win)
    hb = _find(page, "PushButton")
    _has(img, _rect(win, hb, 3, 3, 12, -3), P.role("control"), "Home tool button")

    # window role moved -> Mica off; nothing built from an unrouted colour
    assert not win.isMicaEffectEnabled()
    assert not fluent_route.UNROUTED, sorted(fluent_route.UNROUTED)


def test_roles_not_sampled_still_have_a_route(qapp):
    """Roles the probe test cannot show (no widget of the app draws them in
    a reachable state) still route a library colour: they are not dead."""
    from paperknife.qt import fluent_route, palettes
    qss = {r[4] for d in (False, True) for r in fluent_route.qss_routes(d)}
    paint = {role for entries in fluent_route.PAINT_ROUTES.values()
             for _t, _c, role in entries if isinstance(role, str)}
    paint |= {"tint_hover", "tint_pressed", "tint_selected"}       # the callables' results
    for role in ("fluent_divider", "scrollbar", "flyout_border", "success_tint",
                 "danger_tint", "tint_selected"):
        assert role in qss | paint, role
    # every role is a known role and every palette names every role
    for name, pal in palettes.PALETTES.items():
        assert set(pal) == set(palettes.ROLES), name


@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_library_style_sheets_have_no_unrouted_colour(qapp, dark):
    from paperknife.qt import fluent_route
    un = [r for r in fluent_route.qss_routes(dark)
          if r[4] is None and fluent_route.parse_qss_color(r[3])[3] > 0]
    assert not un, un


def test_switching_back_to_today_and_a_copy_of_today_change_no_pixel(qapp, window):
    """apply_palette repaints an open window: probe and back gives today's
    pixels; a value-for-value copy of today (rewritten, not short-cut) too."""
    from paperknife.qt import palettes, theme
    win = window
    win.resize(1280, 820)
    _open(win, "CompressTool")
    try:
        theme.apply_palette("today")
        pump(0.4)
        before = _grab(win)
        theme.apply_palette("probe")
        pump(0.4)
        assert _grab(win) != before
        theme.apply_palette("today")
        pump(0.4)
        after = _grab(win)
        assert after == before, _diff(before, after)
        palettes.PALETTES["_today_copy"] = dict(palettes.TODAY)
        theme.apply_palette("_today_copy")
        pump(0.4)
        after = _grab(win)
        assert after == before, _diff(before, after)
    finally:
        theme.apply_palette(palettes.DEFAULT)
        palettes.PALETTES.pop("_today_copy", None)
        pump(0.05)


def test_pk_palette_picks_the_palette_and_falls_back(qapp):
    code = ("from PySide6.QtWidgets import QApplication; app = QApplication([]); "
            "from paperknife.qt import theme; print(theme.palette_name(), theme.hex_color('window', False))")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONUTF8="1")
    for name, want in (("probe", "probe #ffc0c0"), ("nope", "windows-oxford-s1 #f3f3f3")):
        env["PK_PALETTE"] = name
        out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env,
                             capture_output=True, text=True, timeout=120)
        assert out.stdout.strip().splitlines()[-1] == want, out.stdout + out.stderr
        if name == "nope":
            assert "not a palette" in out.stderr


def test_existing_token_api(qapp):
    from paperknife.qt import theme
    assert theme.palette_name() == "windows-oxford-s1"
    assert theme.hex_color("accent", False) == "#324d81"
    assert theme.hex_color("divider", True) == "#575757"
    light, dark = theme.pair("page_bg")
    assert (light.name(), dark.name()) == ("#f0ebe3", "#242019")
    assert theme.color("text", True).name() == "#ffffff"
