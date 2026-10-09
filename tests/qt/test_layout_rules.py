"""Layout rules from the phase 6 measurement (owner's choices 2026-10-09):
every control at least Fluent's 32 px, a whole settings row selects its radio,
long paths shortened in the middle, page views without a dark scroll-bar corner,
placeholders and status symbols in the palette's text colours, 4 px corners."""
import re
from itertools import pairwise

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from qt_harness import pump

# The controls whose size the app sets.  The library's own (PushButton, ComboBox,
# LineEdit) are 32 px on Windows from their style sheet and font; offscreen fonts
# are smaller, so those are measured on the real platform (phase6/after/measure.py).
APP_SIZED = {"TransparentPushButton", "TransparentToolButton", "TransparentToggleToolButton",
             "PrimaryPushButton", "RadioButton", "TallSlider", "SwitchButton"}


def _click(w, pos=None):
    pos = QPointF(pos if pos is not None else w.rect().center())
    for kind in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease):
        QApplication.sendEvent(w, QMouseEvent(kind, pos, w.mapToGlobal(pos), Qt.LeftButton,
                                              Qt.LeftButton, Qt.NoModifier))


@pytest.mark.parametrize("dark", [False, True])
def test_no_app_sized_control_on_any_screen_is_under_32_px(window, dark):
    from paperknife.qt import theme
    from paperknife.qt.pages import QT_PAGES
    CONTROL_H = 32                            # Fluent's control height (owner's rule)
    theme.apply_appearance("dark" if dark else "light")
    try:
        small, seen = [], set()
        for name in QT_PAGES:
            assert window.open_tool(name), name
            pump(0.02)
            page = window.current_page()
            for w in page.findChildren(QWidget):
                kind = type(w).__name__
                if kind not in APP_SIZED or not w.isVisibleTo(page):
                    continue
                seen.add(kind)
                wide_enough = kind in ("TallSlider", "SwitchButton") or w.width() >= CONTROL_H
                if w.height() < CONTROL_H or not wide_enough:
                    small.append(f"{name}: {kind} {w.toolTip() or w.accessibleName()!r} "
                                 f"{w.width()}x{w.height()}")
        assert not small, "\n".join(small)
        assert seen == APP_SIZED                  # each kind was really checked somewhere
    finally:
        theme.apply_appearance("light")


def test_a_click_anywhere_on_a_settings_row_selects_its_radio(window):
    assert window.open_tool("CompressTool")
    pump(0.05)
    page = window.current_page()
    rb = next(b for b in page.level_group.buttons.values() if not b.isChecked())
    row = rb.parentWidget().parentWidget()
    assert row.objectName() == "settingRow"
    _click(row, QPoint(20, row.height() // 2))           # on the row's title, far from the circle
    pump(0.02)
    assert rb.isChecked()


def test_the_radio_circle_sits_in_the_middle_of_its_box():
    from paperknife.qt.pages import CONTROL_H, radio_button
    rb = radio_button()
    assert (rb.width(), rb.height()) == (CONTROL_H, CONTROL_H)
    assert (rb.indicatorPos.x(), rb.indicatorPos.y()) == (CONTROL_H // 2, CONTROL_H // 2)


def test_a_click_on_a_toggle_box_flips_it_and_says_so(qapp):
    from paperknife.qt.pages import CONTROL_H, toggle_switch
    s = toggle_switch(False)
    s.resize(120, CONTROL_H)
    seen = []
    s.checkedChanged.connect(seen.append)
    _click(s, QPoint(s.width() - 4, CONTROL_H // 2))     # beside the pill, not on it
    assert s.isChecked() and seen == [True]
    s.setEnabled(False)
    _click(s, QPoint(s.width() - 4, CONTROL_H // 2))
    assert s.isChecked() and seen == [True]


def test_header_footer_picks_its_position_on_a_page_diagram(window):
    assert window.open_tool("HeaderFooterTool")
    pump(0.05)
    page = window.current_page()
    btns = page.positions
    assert list(btns) == ["top-left", "top-center", "top-right",
                          "bottom-left", "bottom-center", "bottom-right"]
    outline = btns["top-left"].parentWidget()
    assert type(outline).__name__ == "PageOutline"
    assert all(b.parentWidget() is outline for b in btns.values())
    tops = {btns[k].geometry().top() for k in ("top-left", "top-center", "top-right")}
    bottoms = {btns[k].geometry().top() for k in ("bottom-left", "bottom-center", "bottom-right")}
    assert len(tops) == 1 and len(bottoms) == 1 and min(bottoms) > max(tops)
    xs = sorted(btns[k].geometry().left() for k in ("top-left", "top-center", "top-right"))
    assert all(b - a >= 32 + 4 for a, b in pairwise(xs))           # 4 px between targets
    assert {b.toolTip() for b in btns.values()} == {
        "Top left", "Top centre", "Top right", "Bottom left", "Bottom centre", "Bottom right"}
    _click(btns["top-right"])
    assert page.pos == "top-right"


def test_a_long_path_is_shortened_in_the_middle_with_the_whole_in_its_tooltip(qapp):
    from paperknife.qt.pages import ElidedLabel
    path = r"C:\Users\Someone\Documents\Projects\2026\Quarterly reports\final\report.pdf"
    lbl = ElidedLabel(path)
    lbl.resize(180, 20)
    lbl.show()                                            # a hidden label gets no resize event
    pump(0.02)
    shown = QLabel.text(lbl)                              # what is drawn
    assert "…" in shown and shown.startswith("C:") and shown.endswith(".pdf")
    assert lbl.text() == path and lbl.toolTip() == path
    lbl.resize(2000, 20)
    pump(0.02)
    assert QLabel.text(lbl) == path and lbl.toolTip() == ""   # it fits: nothing hidden
    lbl.close()


@pytest.mark.parametrize("dark", [False, True])
def test_a_page_view_s_scroll_bar_corner_is_the_page_ground(qapp, dark):
    from paperknife.qt import theme
    from paperknife.qt.pageview import PageView
    theme.apply_appearance("dark" if dark else "light")
    try:
        v = PageView(theme.hex_color("page_bg"))
        v.resize(300, 200)
        v.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        v.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        v.show()
        pump(0.02)
        c = v.cornerWidget()
        assert c.isVisible()
        img = v.grab().toImage()
        mid = c.geometry().center()
        assert img.pixelColor(mid).name() == theme.color("page_bg").name()
        v.close()
    finally:
        theme.apply_appearance("light")


@pytest.mark.parametrize("dark", [False, True])
def test_placeholders_use_the_secondary_text_colour(qapp, dark):
    from paperknife.qt import fluent_route, theme
    from qfluentwidgets.common.style_sheet import FluentStyleSheet, Theme
    want = theme.hex_color("fluent_text_secondary", dark).lower()
    qss = FluentStyleSheet.LINE_EDIT.content(Theme.DARK if dark else Theme.LIGHT)
    got = re.findall(r"placeholder-text-color:\s*([^;]+);", qss)
    assert got and {g.strip().lower() for g in got} == {want}
    assert "line_edit" in fluent_route.PLACEHOLDER_QSS


def test_library_controls_and_cards_are_rounded_4_px(qapp):
    from qfluentwidgets.common.style_sheet import FluentStyleSheet, Theme
    from paperknife.qt.pages import card
    for sheet in (FluentStyleSheet.BUTTON, FluentStyleSheet.LINE_EDIT, FluentStyleSheet.COMBO_BOX):
        qss = sheet.content(Theme.LIGHT)
        assert not re.search(r"border-radius\s*:\s*5px", qss), sheet
    assert card().getBorderRadius() == 4


def test_the_status_line_draws_symbols_from_segoe_ui_symbol(window):
    fams = window.status_label.font().families()
    assert fams.index("Segoe UI Symbol") < fams.index("Microsoft YaHei")   # before the fallbacks
