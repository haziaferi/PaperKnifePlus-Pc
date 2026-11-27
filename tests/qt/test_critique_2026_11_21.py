"""Layout critique 2026-11-21 (critique-2026-11-21/critique.md beside the repo), E2 layout:
each fix with a test that fails on the commit before it (structures 1e81c24)."""
# ruff: noqa: F811  (e2win is a fixture imported from test_structure_e2)
import pytest
from PySide6.QtWidgets import QLabel, QWidget
from qt_harness import make_pdf, pump
from test_structure_e2 import E2_ENV, e2win, host_of, rail_of  # noqa: F401  (fixture)


def _y(w, win):
    return w.mapTo(win, w.rect().topLeft()).y()


# ── Fix first: Password ──────────────────────────────────────────────────────
def test_remove_password_sits_under_its_own_heading_not_beside_apply(e2win):
    host = host_of(e2win)
    host.pick("PasswordTool")
    pump(0.2)
    page = host.current_tool()
    assert [b.text() for b in page._buttons] == ["Apply"]        # one action on the card top
    btn = page.remove_btn
    assert btn.isVisibleTo(host.card)
    # Current password (read by both actions) first, Remove right under it, then Add / Change
    assert _y(page.cur_pw, e2win) < _y(btn, e2win) < _y(page.pw1, e2win)
    assert _y(btn, e2win) - _y(page.cur_pw, e2win) < 120            # was 486 px apart
    apply_btn = page._buttons[0]
    assert _y(btn, e2win) - (_y(apply_btn, e2win) + apply_btn.height()) > 60   # not beside Apply


# ── the card names its tool ──────────────────────────────────────────────────
@pytest.mark.parametrize("key, name", [("CompressTool", "Compress"), ("WatermarkTool", "Watermark"),
                                       ("RedactTool", "Redact")])
def test_card_names_the_tool_open_or_collapsed(e2win, key, name):
    host = host_of(e2win)
    host.pick(key)
    pump(0.2)
    assert host.card_name.text() == name and host.card_name.isVisibleTo(host.card)
    host.set_card_open(False)
    pump(0.1)
    assert host.card_name.isVisibleTo(host.card)
    assert host.card_name.geometry().bottom() < host.card.height()     # inside the edge card
    host.set_card_open(True)


def test_a_first_heading_that_repeats_the_name_goes(e2win):
    host = host_of(e2win)
    host.pick("WatermarkTool")
    pump(0.2)
    inner = host.options_stack.currentWidget()
    inner = inner.widget() if hasattr(inner, "widget") and inner.widget() else inner
    shown = [lb.text() for lb in inner.findChildren(QLabel) if lb.isVisibleTo(inner) and lb.text()]
    assert "Watermark" not in shown[:1]


# ── Find & Replace ───────────────────────────────────────────────────────────
def test_find_all_leads_and_replace_all_waits_for_hits(e2win):
    host = host_of(e2win)
    host.pick("FindReplaceTool")
    pump(0.2)
    page = host.current_tool()
    find, repl = page._buttons
    assert find.text() == "Find All" and repl.text() == "Replace All"
    assert _y(find, e2win) < _y(repl, e2win)
    assert not repl.isEnabled()
    page._hits = [(0, [])]
    assert repl.isEnabled()
    page.find_edit.textEdited.emit("other")
    assert not repl.isEnabled()


def test_hosted_editor_heading_has_no_stray_hide_button_and_is_not_cut(e2win):
    host = host_of(e2win)
    host.pick("FindReplaceTool")
    pump(0.2)
    page = host.current_tool()
    # the stray ">" took the end of the heading row ("Find & Replac"); text widths are
    # checked on the Windows-platform recapture (offscreen fonts measure wide)
    assert not page._panel_hide_btn.isVisibleTo(host.card)


def test_editor_headings_take_the_card_section_style(e2win):
    from paperknife.qt.pages import group_title
    host = host_of(e2win)
    host.pick("AnnotateTool")
    pump(0.2)
    head = host.current_tool()._panel_box.findChild(QLabel, "panelTitle")
    ref = group_title("x")
    assert head.font().pixelSize() == ref.font().pixelSize()
    assert head.font().weight() == ref.font().weight()


# ── one card place and size in both workspaces ───────────────────────────────
def test_files_card_matches_the_document_card(e2win):
    host = host_of(e2win)
    host.pick("CompressTool")
    pump(0.2)
    doc_geo = host.card.geometry()
    doc_action = host.action_slot.currentWidget().mapTo(e2win, host.action_slot.currentWidget().rect().topLeft())
    assert e2win.open_tool("MergeTool")
    pump(0.3)
    files = e2win.current_page()
    geo = files.card.geometry()
    act = files.action_slot.currentWidget().mapTo(e2win, files.action_slot.currentWidget().rect().topLeft())
    assert (geo.x(), geo.width()) == (doc_geo.x(), doc_geo.width())
    assert geo.y() == doc_geo.y()
    # the action's y is checked on the Windows-platform recapture: offscreen fonts draw
    # Merge's button 30 px tall against Compress's 32
    assert act.x() == doc_action.x()


# ── card rows and editor cards ───────────────────────────────────────────────
def test_a_radio_row_on_the_card_is_one_control_tall(e2win):
    host = host_of(e2win)
    host.pick("CompressTool")
    pump(0.2)
    rows = [r for r in host.card.findChildren(QWidget, "settingRow") if r.isVisibleTo(host.card)]
    from qfluentwidgets import RadioButton
    radio_rows = [r for r in rows if r.findChild(RadioButton) is not None]
    assert len(radio_rows) == 3
    assert all(r.height() <= 40 for r in radio_rows), [r.height() for r in radio_rows]


def test_undo_is_set_apart_from_the_modes(e2win):
    host = host_of(e2win)
    host.pick("RedactTool")
    pump(0.2)
    cmds = [b for b in host.card.findChildren(QWidget, "editorCommand") if b.isVisibleTo(host.card)]
    assert [b.text() for b in cmds] == ["Undo last (Ctrl+Z)"]
    modes = [b for b in host.card.findChildren(QWidget) if getattr(b, "isCheckable", None)
             and b.isCheckable() and b.text() in ("Draw box", "Find && redact text", "Pages")]
    assert modes and all(_y(m, e2win) < _y(cmds[0], e2win) for m in modes)


def test_the_mode_heading_sits_nearer_its_options_than_the_list_above(e2win):
    host = host_of(e2win)
    host.pick("RedactTool")
    pump(0.2)
    page = host.current_tool()
    from qfluentwidgets import SubtitleLabel
    head = (page._panel_box.findChild(QLabel, "panelTitle")
            or page._panel_box.findChildren(SubtitleLabel)[0])
    top, bottom = _y(head, e2win), _y(head, e2win) + head.height()
    shown = [w for w in host.card.findChildren(QWidget) if w.isVisibleTo(host.card)
             and w.height() > 4 and w is not head and not w.isAncestorOf(head)
             and not head.isAncestorOf(w)]
    rows_above = [w for w in shown if hasattr(w, "isCheckable") and _y(w, e2win) + w.height() <= top]
    above = top - max(_y(w, e2win) + w.height() for w in rows_above)
    below = min(_y(w, e2win) for w in shown if _y(w, e2win) >= bottom
                and page._panel_box.isAncestorOf(w) and w.parentWidget() is page._panel_box) - bottom
    assert above > below, (above, below)


def test_redact_action_names_the_new_copy(e2win):
    host = host_of(e2win)
    host.pick("RedactTool")
    pump(0.2)
    assert [b.text() for b in host.current_tool()._buttons] == ["Save redacted copy…"]


# ── rail ─────────────────────────────────────────────────────────────────────
def test_the_selected_group_is_tinted_not_filled_with_the_action_colour(e2win):
    from paperknife.qt import theme
    host = host_of(e2win)
    host.pick("CompressTool")
    pump(0.2)
    btn = rail_of(e2win).buttons["Protect & optimise"]
    assert btn.isChecked()
    img = btn.grab().toImage()
    c = img.pixelColor(img.width() // 2, img.height() - 3)       # under the name
    accent = theme.color("accent")
    assert abs(c.red() - accent.red()) + abs(c.green() - accent.green()) \
        + abs(c.blue() - accent.blue()) > 120


def test_protect_and_optimise_is_named_whole_on_the_rail(e2win):
    label = rail_of(e2win).buttons["Protect & optimise"].label.text()
    assert "Protect" in label and "optimise" in label


# ── Home ─────────────────────────────────────────────────────────────────────
def test_home_offers_open_first_and_says_a_drop_works(qapp, dialogs, tmp_path):
    from paperknife.qt.shell import MainWindow
    from conftest import close_test_window
    w = MainWindow()
    w.show()
    w.show_page("home")
    pump(0.2)
    home = w.current_page()
    first = home.quick.itemAt(0).widget()
    assert first is home.open_button and "Open" in first.text()
    assert "drop" in home.empty_label.text().lower()
    pdf = make_pdf(tmp_path / "a.pdf")
    dialogs.open(pdf)
    home.open_button.click()
    pump(0.3)
    assert w.document.is_open()
    close_test_window(w)


# ── Files ────────────────────────────────────────────────────────────────────
def test_merge_with_no_files_shows_one_drop_target_and_the_hint_once(e2win):
    from paperknife.qt.tools import merge
    assert e2win.open_tool("MergeTool")
    pump(0.3)
    page = e2win.current_page().current_tool()
    page.clear_rows()
    pump(0.1)
    assert page.drop_target.isVisibleTo(page)
    shown = [lb.text() for lb in page.findChildren(QLabel) if lb.isVisibleTo(page)]
    assert shown.count(merge.HINT) == 1


# ── Rotate, Bookmarks / TOC ──────────────────────────────────────────────────
def test_rotate_hint_leads_the_grid_row_and_delete_is_set_apart(e2win):
    host = host_of(e2win)
    host.pick("RotateTool")
    pump(0.5)
    page = host.current_tool()
    assert page.context_bar.itemAt(0).widget() is page.hint_label
    from paperknife.qt.pages import Divider
    tb = page.page_toolbar
    assert tb.findChildren(Divider), "a line before Delete"


def test_the_bookmark_panel_keeps_clear_of_the_card(e2win):
    host = host_of(e2win)
    host.pick("TocTool")
    pump(0.3)
    page = host.current_tool()
    assert page.layout().contentsMargins().right() >= host.card.width()


# ── Preferences ──────────────────────────────────────────────────────────────
def test_preferences_marks_no_place_tab_and_keeps_a_reading_width(e2win):
    assert e2win.open_tool("MergeTool")
    pump(0.2)
    e2win.show_page("SettingsTool")
    pump(0.2)
    tabs = e2win._left["tabs"]
    assert tabs.currentItem() is None
    assert not any(it.isSelected for it in tabs.items.values())
    page = e2win.current_page()
    assert page.width() <= 800
    assert page.compress_level.currentText() == page.compress_level.currentText().capitalize()


# ── viewer footer, controls at CONTROL_H ─────────────────────────────────────
def test_footer_and_card_toggle_are_control_tall(e2win):
    from paperknife.qt.pages import CONTROL_H
    host = host_of(e2win)
    host.pick("CompressTool")
    pump(0.2)
    minus, pct, plus = host.viewer.zoom_box
    assert {minus.height(), pct.height(), plus.height(), host.card_toggle.height()} == {CONTROL_H}


def test_reader_counter_reads_one_page_as_the_editors_do(e2win):
    host = host_of(e2win)
    host.back()
    pump(0.4)
    shown = host.viewer.page_label.text().split(" / ")[0]
    first, _, last = shown.partition("–")
    assert not last or first != last              # never "1–1 / 12"


def test_no_page_footer_with_nothing_open(qapp, dialogs, monkeypatch):
    for k, v in E2_ENV.items():
        monkeypatch.setenv(k, v)
    from paperknife.qt.shell import MainWindow
    from conftest import close_test_window
    w = MainWindow()
    w.resize(1280, 820)
    w.show()
    w.show_page("DocWorkspace")
    pump(0.3)
    viewer = w.current_page().viewer
    assert not viewer.page_label.isVisibleTo(viewer)
    assert not viewer.zoom_box[1].isVisibleTo(viewer)
    close_test_window(w)


# ── notation shown by examples; units ────────────────────────────────────────
def test_split_examples_fill_the_range_field(e2win):
    host = host_of(e2win)
    host.pick("SplitTool")
    pump(0.4)
    page = host.current_tool()
    ex = page.range_examples
    assert ex.labels() == ["Every page", "Every 2 pages", "Page 1 apart"]
    assert [a.text() for a in ex.menu.actions()] == ex.labels()
    ex.menu.actions()[1].trigger()
    assert page.ranges.text() == "1-2; 3-4; 5-6; 7-8; 9-10; 11-12"
    ex.pick("Page 1 apart")
    assert page.ranges.text() == "1; 2-end"
    assert ex.height() <= 40                       # one row on the card


def test_header_footer_examples_fill_the_content(e2win):
    host = host_of(e2win)
    host.pick("HeaderFooterTool")
    pump(0.3)
    page = host.current_tool()
    page.content_examples.pick("Page n")
    assert page.content.text() == "{page}"


def test_crop_margins_default_to_millimetres_and_convert(e2win):
    host = host_of(e2win)
    host.pick("CropTool")
    pump(0.3)
    page = host.current_tool()
    assert page.unit.currentText() == "mm"
    page.margins["top"].setText("25.4")
    page.unit.setCurrentText("pt")
    assert page.margins["top"].text() == "72"


def test_one_label_for_the_colour_button(e2win):
    from qfluentwidgets import PushButton
    host = host_of(e2win)
    labels = set()
    for key in ("WatermarkTool", "AnnotateTool"):
        host.pick(key)
        pump(0.2)
        labels |= {b.text() for b in host.card.findChildren(PushButton)
                   if b.text() in ("Choose", "Pick…", "Choose…")}
    assert labels == {"Choose…"}


def test_page_thumbnails_grow_with_the_pane(e2win):
    host = host_of(e2win)
    host.pick("WatermarkTool")
    pump(0.5)
    page = host.current_tool()
    assert page.grid.iconSize().width() > 120


# ── owner, 2026-11-21, option B: the editors' page gets room beside the card ──
@pytest.mark.parametrize("key", ["RedactTool", "AnnotateTool", "FindReplaceTool", "EditTextTool"])
def test_an_editors_page_scrolls_clear_of_the_open_card(e2win, key):
    from PySide6.QtCore import QPoint
    host = host_of(e2win)
    host.pick(key)
    pump(0.6)
    view = host.current_tool().view
    card_x = host.card.mapTo(e2win, QPoint(0, 0)).x()
    vp = view.viewport()
    assert vp.mapTo(e2win, QPoint(vp.width(), 0)).x() <= card_x       # the view stops short of it
    zoom_before = view.zoom
    hbar = view.horizontalScrollBar()
    hbar.setValue(hbar.maximum())
    pump(0.2)
    page = view.scene().itemsBoundingRect()
    right = vp.mapTo(e2win, view.mapFromScene(page.bottomRight())).x()
    assert right <= card_x                                              # the line ends reachable
    assert view.zoom == zoom_before                                     # the page keeps its size
    host.set_card_open(False)
    pump(0.2)
    assert view.viewportMargins().right() == 0                         # collapsed: full width back
    host.set_card_open(True)


def test_leaving_the_editor_gives_its_view_the_full_width_back(e2win):
    host = host_of(e2win)
    host.pick("RedactTool")
    pump(0.4)
    view = host.current_tool().view
    assert view.viewportMargins().right() > 0
    host.pick("CompressTool")
    pump(0.3)
    assert view.viewportMargins().right() == 0
