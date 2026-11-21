"""Layout critique 2026-11-21 (critique-2026-11-21/critique.md beside the repo), E2 layout:
each fix with a test that fails on the commit before it (structures 1e81c24)."""
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
    # Current password (read by both actions) first, then Add / Change, then Remove
    assert _y(page.cur_pw, e2win) < _y(page.pw1, e2win) < _y(page.allow_copy, e2win) < _y(btn, e2win)


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
    page = host.current_tool()
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
