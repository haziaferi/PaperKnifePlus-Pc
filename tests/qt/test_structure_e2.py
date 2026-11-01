"""E2 layout prototype (PK_LEFT=grouprail, PK_DETAILS=float; owner, 2026-10-21): the tool
groups on a rail, a group's tools in a column that closes once a tool is chosen or in a
right-click pop-up, the tool's options floating over the page's right edge with the main
action fixed at the card's top, the card collapsing to an edge card that keeps the action at
the same spot, page grids clear of the card with a toolbar on the selected page, and the
zoom as  -  100 %  +  in the centre."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from conftest import close_test_window
from qt_harness import make_pdf, pump

E2_ENV = {"PK_STRUCT": "workspace", "PK_PICKER": "pane", "PK_FILES": "window",
          "PK_DETAILS": "float", "PK_LEFT": "grouprail"}


@pytest.fixture
def e2win(qapp, dialogs, monkeypatch, tmp_path):
    for k, v in E2_ENV.items():
        monkeypatch.setenv(k, v)
    from PySide6.QtCore import QPoint
    from paperknife.qt.shell import MainWindow
    w = MainWindow()
    w.resize(1280, 820)
    w.move(0, 0)
    w.pointer_at = QPoint(w.width() // 2, w.height() // 2)
    w._pointer = lambda: w.mapToGlobal(w.pointer_at)
    w.show()
    pump(0.05)
    w.open_document(make_pdf(tmp_path / "doc.pdf", pages=12))
    w.show_page("DocWorkspace")
    pump(0.3)
    yield w
    close_test_window(w)


def rail_of(w):
    return w._left["rail"]


def host_of(w):
    return w.current_page()


def test_rail_shows_the_groups_with_their_own_icons(e2win):
    rail = rail_of(e2win)
    assert list(rail.buttons) == ["Pages", "Content", "Protect & optimise", "Convert"]
    from paperknife.qt import structure
    glyphs = {structure.GROUP_GLYPH[g] for g in rail.buttons}
    assert len(glyphs) == 4                                  # four different icons
    assert not e2win.navigationInterface.isVisible()        # no navigation column
    host = host_of(e2win)
    assert host.pane.isHidden() and not host.pane.isVisibleTo(host)


def test_left_click_column_closes_once_a_tool_is_chosen(e2win):
    rail, host = rail_of(e2win), host_of(e2win)
    rail.toggle_column(rail.buttons["Protect & optimise"])
    pump(0.05)
    assert rail.column_shown()
    lst = rail.column_slot.currentWidget()
    keys = [lst.item(i).data(0x0100) for i in range(lst.count())]
    assert "CompressTool" in keys and "RotateTool" not in keys
    rail._choose("CompressTool")
    pump(0.1)
    assert not rail.column_shown()
    assert host._current == "CompressTool"
    assert rail.buttons["Protect & optimise"].isChecked()
    assert not rail.buttons["Pages"].isChecked()


def test_the_column_floats_over_the_page_without_resizing_it(e2win):
    rail, host = rail_of(e2win), host_of(e2win)
    before = host.centre.geometry()
    rail.toggle_column(rail.buttons["Pages"])
    pump(0.05)
    assert host.centre.geometry() == before
    rail.toggle_column(rail.buttons["Pages"])               # the same icon again closes it
    assert not rail.column_shown()


def test_right_click_popup_lists_the_groups_tools(e2win, monkeypatch):
    rail = rail_of(e2win)
    from qfluentwidgets import RoundMenu
    shown = []
    monkeypatch.setattr(RoundMenu, "exec", lambda self, *a, **k: shown.append(self))
    rail.popup(rail.buttons["Pages"])
    assert shown, "no pop-up"
    texts = [a.text().replace("&&", "&") for a in shown[0].actions()]
    assert texts[:2] == ["Rotate & Reorder", "Split"]
    shown[0].actions()[1].trigger()                          # choosing closes it and picks
    pump(0.1)
    assert host_of(e2win)._current == "SplitTool"
    assert not rail.column_shown()


def test_action_fixed_at_the_card_top_for_every_tool(e2win):
    host = host_of(e2win)
    tops = set()
    for tool in ("CompressTool", "WatermarkTool", "RotateTool", "PasswordTool"):
        host.pick(tool)
        pump(0.1)
        assert host.card.isVisible()
        a = host.action_slot.currentWidget()
        tops.add(a.mapTo(e2win, a.rect().topLeft()).y())
        assert host.action_slot.parentWidget() is host.card
    assert len(tops) == 1, tops                              # same height whatever the options


def test_collapsed_card_keeps_the_action_at_the_same_spot(e2win):
    host = host_of(e2win)
    host.pick("CompressTool")
    pump(0.1)
    a = host.action_slot.currentWidget()
    open_at = a.mapTo(e2win, a.rect().topRight())
    open_w = host.card.width()
    host.set_card_open(False)
    pump(0.1)
    assert not host.options_stack.isVisible()
    assert host.card.width() < open_w
    assert a.mapTo(e2win, a.rect().topRight()) == open_at
    assert a.isVisible()
    host.set_card_open(True)
    assert host.options_stack.isVisible()


def test_page_grid_keeps_clear_of_the_card(e2win):
    host = host_of(e2win)
    host.pick("RotateTool")
    pump(0.4)
    grid = host.current_tool().grid
    card_left = host.card.mapTo(e2win, host.card.rect().topLeft()).x()
    vp = grid.viewport()
    vp_right = vp.mapTo(e2win, vp.rect().topRight()).x()
    assert vp_right < card_left
    page = host.current_tool()                 # the row above it too (its hint was cut)
    for wdg in (page.context_bar_widget, page.hint_label):
        assert wdg.mapTo(e2win, wdg.rect().topRight()).x() < card_left, wdg.objectName()


def test_page_toolbar_on_the_selected_page_acts_on_it(e2win):
    host = host_of(e2win)
    host.pick("RotateTool")
    pump(0.4)
    page = host.current_tool()
    bar = page.page_toolbar
    assert bar.isHidden()
    page.grid.item(5).setSelected(True)
    pump(0.1)
    assert bar.isVisible()
    r = page.grid.visualItemRect(page.grid.item(5))
    assert bar.y() >= r.bottom() or bar.y() + bar.height() <= r.top()   # beside the page, not over it
    names = [b.text() for b, _src in bar.buttons]
    assert [n.endswith(k) for n, k in zip(names, ("90° CCW", "90° CW", "Delete"), strict=True)] \
        == [True, True, True]
    assert names == [src.text() for _b, src in bar.buttons]      # the page's own commands
    before = page.rotations() if hasattr(page, "rotations") else None
    bar.buttons[1][0].click()                                # 90 CW on page 6
    pump(0.2)
    assert page.is_dirty()
    if before is not None:
        assert page.rotations() != before


def test_zoom_is_a_percentage_in_the_centre(e2win):
    host = host_of(e2win)
    viewer = host.viewer
    minus, pct, plus = viewer.zoom_box
    assert not viewer.zoom_slider.isVisible()
    assert pct.text().endswith(" %")
    v0 = viewer.zoom_slider.value()
    plus.click()
    pump(0.1)
    assert viewer.zoom_slider.value() > v0
    assert pct.text() == f"{viewer.zoom_slider.value()} %"
    minus.click()
    minus.click()
    pump(0.1)
    assert viewer.zoom_slider.value() < v0
    box = pct.parentWidget()
    mid = box.mapTo(viewer, box.rect().center()).x()
    assert abs(mid - viewer.width() / 2) < viewer.width() * 0.1  # near the centre


def test_two_actions_stack_at_the_card_top_unsqueezed(e2win):
    host = host_of(e2win)
    host.pick("PasswordTool")
    pump(0.1)
    buttons = host.current_tool()._buttons
    assert len(buttons) == 2
    ys = sorted(b.mapTo(e2win, b.rect().topLeft()).y() for b in buttons)
    assert ys[1] > ys[0]                                     # one over the other
    for b in buttons:
        assert b.width() >= b.sizeHint().width()             # text not clipped


def test_files_list_starts_under_the_card(e2win):
    assert e2win.open_tool("MergeTool")
    pump(0.3)
    host = e2win.current_page()
    assert host.card is not None and host.card.isVisible()
    page = host.current_tool()
    card_bottom = host.card.mapTo(e2win, host.card.rect().bottomLeft()).y()
    add = page.add_btn
    assert add.isVisible()
    assert add.mapTo(e2win, add.rect().topLeft()).y() > card_bottom   # Add PDFs not covered


def test_card_fits_its_options_when_there_is_room(e2win):
    e2win.resize(1280, 1000)
    pump(0.2)
    host = host_of(e2win)
    host.pick("SplitTool")                                   # its parts list fills late
    pump(0.4)
    room = host.height() - host.centre.y() - 40
    assert host.card.height() < room
    sb = host.options_stack.currentWidget().verticalScrollBar()
    assert sb.maximum() == 0                                 # nothing hidden below


def test_title_bar_waits_over_an_empty_strip(e2win):
    """Revealed at the top edge, the bar stays while the pointer crosses an empty stretch
    of it towards its buttons (the walk, 2026-10-21: it vanished before they were reached);
    over a control under it, it still makes way at once."""
    from paperknife.qt import shell
    w = e2win

    def at(x, y):
        w.pointer_at = shell.QPoint(x, y)
        w._poll_edges()

    rail = rail_of(w)
    gap = rail.mapTo(w, rail.rect().topRight()).x() + 4  # just right of the rail, top row
    tabs_x = [x for x in range(gap, w.width() // 2, 6) if not w._control_under(shell.QPoint(x, 16))]
    assert tabs_x, "no empty stretch on the top row"
    at(w.width() // 2, 2)
    pump(shell.TOP_SLIDE_MS / 1000 + 0.1)
    assert w.title_bar_shown()
    at(tabs_x[0], 16)
    assert w.title_bar_shown()                               # waits (the hide timer runs)
    btn = next(x for x in range(gap, w.width(), 4) if w._control_under(shell.QPoint(x, 16))
               and not w._over_title_buttons(x, 16))
    at(btn, 16)
    assert w.title_bar_shown()                               # still on its way: it stays
    at(btn, w.titleBar.height() + 40)                        # back to the page...
    at(btn, 16)                                              # ...then onto a control under it
    assert not w.title_bar_shown()


def test_home_quick_actions_open_their_tools_in_a_structure(e2win):
    """Home listed no quick actions in a structure (it looked for tools among the places
    the navigation lists, 2026-10-21 walk)."""
    from paperknife.qt import home
    assert e2win.show_page("home")
    pump(0.1)
    page = e2win.current_page()
    assert list(page.quick_buttons) == list(home.QUICK_ACTIONS)
    page.quick_buttons["CompressTool"].click()
    pump(0.2)
    assert e2win.current_page()._current == "CompressTool"
    assert e2win.show_page("home")
    page.quick_buttons["MergeTool"].click()
    pump(0.2)
    assert e2win.current_page().current_tool() is not None
    assert type(e2win.current_page().current_tool()).__name__ == "MergePage"


def test_the_way_along_the_bar_to_its_buttons_stays_clear(e2win):
    """Crossing the revealed bar towards its buttons passes over the search field, and
    the bar made way there (the live check, 2026-10-22): brought by the top edge and
    never left, it stays all the way."""
    from paperknife.qt import shell
    w = e2win
    tb = w.titleBar
    buttons_left = tb.mapTo(w, tb.minBtn.pos()).x()
    s = w.search
    left, right = s.mapTo(w, s.rect().topLeft()).x(), s.mapTo(w, s.rect().topRight()).x()
    assert left < buttons_left and w.width() // 2 < right       # the field lies on the way

    def at(x, y):
        w.pointer_at = shell.QPoint(x, y)
        w._poll_edges()

    at(w.width() // 2, 2)
    pump(shell.TOP_SLIDE_MS / 1000 + 0.1)
    y = tb.height() // 2
    for x in range(w.width() // 2, buttons_left + 10, 6):
        at(x, y)
        assert w.title_bar_shown(), f"bar left at x={x}"


def test_the_first_action_sits_at_one_height_whatever_the_stack(e2win):
    """Find & Replace's three stacked actions put its Save 30 px above Edit Text's
    single Save (the live walk, 2026-10-22): the actions start at the card top, and the
    slot is only as tall as the current tool's actions."""
    host = host_of(e2win)
    tops = {}
    # Edit Text has no card action since 2026-10-23 (the bar's Save is the one place)
    for tool in ("WatermarkTool", "FindReplaceTool", "PasswordTool", "CompressTool"):
        host.pick(tool)
        pump(0.15)
        buttons = [b for b in host.current_tool()._buttons if b.isVisible()]
        tops[tool] = min(b.mapTo(e2win, b.rect().topLeft()).y() for b in buttons)
        slot = host.action_slot
        lowest = max(b.mapTo(e2win, b.rect().bottomLeft()).y() for b in buttons)
        assert slot.mapTo(e2win, slot.rect().bottomLeft()).y() - lowest < 8, tool
    assert len(set(tops.values())) == 1, tops


def test_a_card_without_actions_has_no_empty_action_band(e2win):
    """The instant editors lost their card Save (owner, 2026-10-23): no band is
    left where it was."""
    host = host_of(e2win)
    for tool in ("EditTextTool", "AnnotateTool", "RotateTool"):
        host.pick(tool)
        pump(0.15)
        assert not [b for b in host.current_tool()._buttons
                    if b.isVisible() and getattr(b, "pk_primary", False)], tool
        assert host.action_slot.height() <= 2, (tool, host.action_slot.height())


def test_redact_card_shows_its_warning_without_scrolling(e2win):
    """The empty pending-boxes list grew to fill the card and pushed the permanence
    warning below the fold at 1280 x 820 (owner, 2026-10-22): the list is as tall as
    its boxes, up to five rows, and gone while there are none."""
    import pymupdf as fitz
    from paperknife.qt.tools import redact
    host = host_of(e2win)
    host.pick("RedactTool")
    pump(0.4)
    page = host.current_tool()
    area = host.options_stack.currentWidget()
    assert area.vScrollBar.maximum() == 0                    # nothing hidden below
    assert not page.box_list.isVisible() and not page.remove_button.isEnabled()
    # "0 boxes pending" in the text colour (clearing its sheet left it near-invisible)
    assert page.pending_label._pk_role == "text"
    heights = []
    for n in (1, 2, 5, 30):
        page._pending = [(0, fitz.Rect(10, 10, 50, 30), "") for _ in range(n)]
        page._refresh_boxes()
        pump(0.2)
        assert page.box_list.isVisible() and page.remove_button.isEnabled()
        heights.append(page.box_list.height())
    assert heights[0] < heights[1] < heights[2] == heights[3]   # grows, capped at BOX_ROWS
    assert page.pending_label._pk_role == "danger"
    assert redact.BOX_ROWS == 5
    page._pending = []
    page._refresh_boxes()


def test_pdf_tools_card_fits_a_maximized_window(e2win):
    """Its four descriptions ran to 22 lines and hid 73 px below the fold in a maximized
    window (1920 x 1032 logical px on the owner's screen); two lines each (owner,
    2026-10-22) and nothing is hidden."""
    e2win.resize(1920, 1032)
    pump(0.3)
    host = host_of(e2win)
    host.pick("PdfToolsTool")
    pump(0.4)
    assert host.options_stack.currentWidget().vScrollBar.maximum() == 0


def test_language_picker_keeps_its_width_in_the_card(e2win):
    """The card's stacked rows size a control by its hint; the picker's button hinted
    at its text, shrank to "Italian" and showed "Italian + English" as "Italian ..."
    (the live check, 2026-10-23).  It keeps its full width there."""
    host = host_of(e2win)
    host.pick("OCRTool")
    pump(0.4)
    picker = host.current_tool().lang
    picker.setText("ita")                                    # a short name: a short hint
    pump(0.2)
    assert picker.button.width() == 160, picker.button.width()   # its own width, not the text's
    picker.setText("ita+eng")
    pump(0.2)
    assert picker.button.width() == 160
    assert picker.button.toolTip() == "Italian + English"


def test_ctrl_z_in_the_workspace_undoes_the_document_s_last_edit(e2win):
    # Live check 2026-10-23: Ctrl+Z reached the chosen tool (Watermark), which has
    # no undo of its own, and nothing happened.
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    host = host_of(e2win)
    host.pick("WatermarkTool")
    pump(0.2)
    sd = e2win.document
    sd.edit("Turn", lambda d: d[0].set_rotation(90))
    assert sd.dirty and sd.doc[0].rotation == 90
    e2win.activateWindow()
    e2win.setFocus()
    pump(0.05)
    QTest.keyClick(e2win, Qt.Key_Z, Qt.ControlModifier)
    pump(0.1)
    assert sd.doc[0].rotation == 0 and not sd.dirty


def test_a_page_grid_redraws_after_another_tool_s_edit_is_undone(e2win, tmp_path):
    # Live check 2026-10-23: a turn made in Rotate & Reorder, undone from Watermark,
    # left Watermark's thumbnail turned (its page had no document_replaced).
    import pymupdf as fitz
    src = tmp_path / "wide.pdf"
    d = fitz.open()
    d.new_page(width=842, height=595)
    d.new_page(width=842, height=595)
    d.save(str(src))
    d.close()
    assert e2win.open_document(str(src))
    host = host_of(e2win)
    host.pick("RotateTool")
    pump(0.3)
    rot = host.current_tool()
    rot.select(0)
    rot.rotate(90)
    host.pick("WatermarkTool")
    pump(0.3)
    wm = host.current_tool()

    def shape():
        while wm.rendering():
            pump(0.05)
        pm = wm.grid.item(0).icon().pixmap(200, 200)
        return "portrait" if pm.height() > pm.width() else "landscape"
    assert shape() == "portrait"
    assert e2win.undo()
    pump(0.2)
    assert shape() == "landscape"


@pytest.mark.parametrize("tool", ["PdfToolsTool", "MetadataTool", "PasswordTool", "CompressTool"])
def test_a_form_tool_s_target_never_opens_a_window_of_its_own(e2win, tool):
    """The live walk, 2026-10-31: the clear button on PDF Tools left the page empty,
    and its drop target - taken out of the page by the workspace - showed as a
    window of its own ("PaperKnife+ PC", "Drop a PDF here or click to choose one")."""
    from PySide6.QtWidgets import QApplication
    from paperknife.qt.docui import DropTarget
    host = host_of(e2win)
    host.pick(tool)
    pump(0.15)
    assert e2win.clear_current_document()
    pump(0.2)
    stray = [w for w in QApplication.topLevelWidgets()
             if isinstance(w, DropTarget) and w.isVisible()]
    assert not stray, tool


def test_clearing_the_document_empties_the_viewer_under_a_form_tool(e2win):
    """The live walk, 2026-10-31: after the clear button, PDF Tools still showed
    the pages of the document just let go."""
    host = host_of(e2win)
    host.pick("PdfToolsTool")
    pump(0.15)
    assert host.viewer.document_path()
    assert e2win.clear_current_document()
    pump(0.2)
    assert host.viewer.document_path() == ""
    assert not host.viewer.view.isVisibleTo(host.viewer)


@pytest.mark.parametrize("tool", ["WatermarkTool", "OCRTool", "MetadataTool", "PasswordTool",
                                  "HeaderFooterTool"])
def test_a_card_s_input_fields_take_one_width(e2win, tool):
    """Owner, 2026-10-31: text 96, number 113 and language 120 px on one card;
    every input field takes FIELD_W."""
    from PySide6.QtWidgets import QAbstractSpinBox, QLineEdit
    from qfluentwidgets import ComboBox, EditableComboBox
    from paperknife.qt.pages import FIELD_W, LanguagePicker
    host = host_of(e2win)
    host.pick(tool)
    pump(0.2)
    kinds = (QLineEdit, QAbstractSpinBox, ComboBox, EditableComboBox, LanguagePicker)
    widths = {}
    for ctl in host.card.findChildren(QWidget, "settingControl"):
        for c in ctl.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
            if isinstance(c, kinds) and c.isVisibleTo(host.card):
                widths[f"{type(c).__name__}:{ctl.title_label.text()}"] = c.width()
    assert widths, tool
    assert set(widths.values()) == {FIELD_W}, widths


def test_pdf_tools_descriptions_open_from_an_info_button(e2win):
    """Owner, 2026-10-31: no description lines under the names; a circled "i"
    beside each name shows it in a small card over the page."""
    from qfluentwidgets import Flyout
    from paperknife.qt.tools.pdftools import TOOLS
    host = host_of(e2win)
    host.pick("PdfToolsTool")
    pump(0.2)
    page = host.current_tool()
    rows = {c.title_label.text(): c for c in host.card.findChildren(QWidget, "settingControl")
            if getattr(c, "info_button", None) is not None}
    assert set(rows) == {title for _k, title, _d in TOOLS}
    for _k, title, desc in TOOLS:
        c = rows[title]
        assert c.desc_label is None and c.info_button.info_text == desc
    btn = rows["Sanitise"].info_button
    btn.click()
    pump(0.3)
    shown = [f for f in e2win.findChildren(Flyout) if f.isVisible()]
    assert shown and "hidden metadata" in shown[-1].view.contentLabel.text()
    fl = shown[-1]
    assert fl.view.contentLabel.wordWrap() and not fl.view.iconWidget.isVisible()
    # just under the "i", within the tool card's width (it covered the row above and
    # ran past the window, the live look 2026-10-31)
    from PySide6.QtCore import QPoint
    view_tl = fl.view.mapToGlobal(QPoint(0, 0))
    card_tl = host.card.mapToGlobal(QPoint(0, 0))
    assert view_tl.y() >= btn.mapToGlobal(QPoint(0, btn.height())).y()
    assert card_tl.x() <= view_tl.x() and view_tl.x() + fl.view.width() <= card_tl.x() + host.card.width()
    assert page.tool_choice == "repair"           # the "i" does not choose the row


def test_every_description_opens_from_an_info_button(e2win):
    """Owner, 2026-11-01: descriptions work the same way everywhere, by the "i".
    No named row of any tool keeps a description line (a path is the row's
    content, not a description), and a panel heading's description is an "i"."""
    from paperknife.qt.pages import ElidedCaption, WorkspacePage
    host = host_of(e2win)
    lines, infos = [], 0
    for _g, tools in host.groups:
        for key in tools:
            host.pick(key)
            pump(0.05)
            for c in host.findChildren(QWidget, "settingControl"):
                if not c.isVisibleTo(host) or not c.title_label.text():
                    continue
                if c.desc_label is not None and not isinstance(c.desc_label, ElidedCaption):
                    lines.append(f"{key}: {c.title_label.text()}")
                infos += c.info_button is not None
            page = host.current_tool()
            if key in ("AnnotateTool", "RedactTool"):      # their panels have a description
                assert isinstance(page, WorkspacePage)
                assert page.panel_info is not None and page.panel_info.info_text, key
    assert not lines, lines
    assert infos > 20


def test_a_description_that_follows_a_choice_follows_it_in_its_card(e2win):
    """Convert's format description changes with the format: the "i" shows the new one."""
    from paperknife.qt.tool_options import OTHER_INFO
    host = host_of(e2win)
    host.pick("Pdf2DocTool")
    pump(0.2)
    page = host.current_tool()
    for fmt in ("TXT", "HTML"):
        page.fmt.setCurrentText(fmt)
        assert page.fmt_info.info_text == OTHER_INFO[fmt]


def test_redact_s_remove_stays_put_as_the_list_grows(e2win):
    """Owner, 2026-10-31: Remove moved up as the pending list shrank."""
    host = host_of(e2win)
    host.pick("RedactTool")
    pump(0.3)
    page = host.current_tool()
    rm = page.remove_button
    ys = []
    for n in (0, 1, 3, 1):
        page._pending, page._marked_at = [], []
        page._add_marks([(0, (10, 10, 50, 30), "") for _ in range(n)])
        page._refresh_boxes()
        pump(0.1)
        ys.append(rm.mapTo(e2win, rm.rect().topLeft()).y())
    assert len(set(ys)) == 1, ys


def test_a_renamed_action_is_never_clipped(e2win):
    """2026-10-31: OCR's Text-only PDF renames its action "Text-only PDF from OCR";
    the card kept the width it had for "Apply" and the name read "ext-only PDF from OC"."""
    host = host_of(e2win)
    host.pick("OCRTool")
    pump(0.2)
    page = host.current_tool()
    if not getattr(page, "available", True):
        pytest.skip("no OCR engine")
    b = page.run_button
    page.modes["text"].click()
    pump(0.3)
    assert b.text() == "Text-only PDF from OCR"
    assert b.width() >= b.sizeHint().width(), (b.width(), b.sizeHint().width())
    assert host.card.geometry().right() <= host.width()      # the card still fits
    page.modes["overlay"].click()
    pump(0.3)
    assert b.text() == "Apply" and b.width() >= b.sizeHint().width()
