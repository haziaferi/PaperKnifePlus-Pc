"""The Qt Rotate & Reorder page: a page organiser (group B)."""
import os

import pymupdf as fitz
import pytest

from qt_harness import make_pdf, pump, wait_job


def _page(window):
    assert window.open_tool("RotateTool")
    pump(0.05)
    return window.current_page()


def _open(window, tmp_path, pages=3, **kw):
    src = kw.pop("src", None) or make_pdf(tmp_path / "in.pdf", pages=pages)
    page = _page(window)
    page.file.set_path(src)
    pump(0.2)                               # thumbnails render a few per turn
    assert page._doc is not None and len(page._doc) == pages
    return page, src


def _texts(path):
    with fitz.open(path) as d:
        return [pg.get_text().strip() for pg in d]


def _rotations(path):
    with fitz.open(path) as d:
        return [pg.rotation for pg in d]


def _save(window, dialogs, page, out):
    """Save as *out* (the window's): the document as it is now."""
    dialogs.save(out)
    window.save_as()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()


def _doc_texts(page):
    return [pg.get_text().strip() for pg in page._doc]


def test_page_builds_with_its_actions_and_one_thumbnail_per_page(window, tmp_path):
    page, _ = _open(window, tmp_path, pages=4)
    assert page.title_label.text() == "Rotate & Reorder"
    assert [b.text() for b in page._actions] == [
        "↺ 90° CCW", "↻ 90° CW", "⤢ 180°", "← Move Left", "Move Right →",
        "Extract to a new PDF", "Undo", "Delete"]
    assert page.subtitle_label.text() == "Select pages · then rotate, move, delete or extract them"
    assert page.order() == [0, 1, 2, 3]
    assert [page.grid.item(i).text() for i in range(4)] == ["p.1", "p.2", "p.3", "p.4"]
    assert not page.rendering() and not page.grid.item(0).icon().isNull()
    assert not any(b.isEnabled() for b in page._actions)       # nothing selected, nothing to undo


def test_save_without_a_file_warns(window, dialogs):
    page = _page(window)
    page.save()
    assert dialogs.msgs[-1][:3] == ("warning", "Save", "Open a PDF first.")


def test_save_writes_over_the_file_without_asking(window, dialogs, tmp_path):
    page, src = _open(window, tmp_path)
    page.select(0)
    page.rotate(90)
    page.save()                             # the page's Save is the window's: over the file
    wait_job(window)
    assert _texts(src) == ["Page 1", "Page 2", "Page 3"]
    assert _rotations(src) == [90, 0, 0]
    assert window.status_text() == "✓  Saved → in.pdf"
    assert not dialogs.msgs                 # no dialog, no box


@pytest.mark.parametrize("deg,want", [(90, 90), (-90, 270), (180, 180)])
def test_each_rotation_turns_the_selected_pages(window, dialogs, tmp_path, deg, want):
    page, _ = _open(window, tmp_path)
    page.select(0)
    page.grid.item(2).setSelected(True)
    page.rotate(deg)
    out = tmp_path / "out.pdf"
    _save(window, dialogs, page, out)
    assert _rotations(out) == [want, 0, want]
    assert _texts(out) == ["Page 1", "Page 2", "Page 3"]


def test_rotations_add_up(window, dialogs, tmp_path):
    page, _ = _open(window, tmp_path)
    page.select(1)
    page.rotate(90)
    page.rotate(180)
    out = tmp_path / "out.pdf"
    _save(window, dialogs, page, out)
    assert _rotations(out) == [0, 270, 0]


def test_move_left_and_right_reorder_the_saved_pages(window, dialogs, tmp_path):
    page, _ = _open(window, tmp_path)
    page.select(0)
    page.move_pages(1)                      # 2 1 3
    assert _doc_texts(page) == ["Page 2", "Page 1", "Page 3"] and page.selected() == [1]
    page.select(2)
    page.move_pages(-1)                     # 2 3 1
    assert _doc_texts(page) == ["Page 2", "Page 3", "Page 1"]
    assert page.order() == [0, 1, 2]        # the grid is the document's pages in order
    assert [page.grid.item(i).text() for i in range(3)] == ["p.1", "p.2", "p.3"]
    page.select(0)
    page.move_pages(-1)                     # already first: nothing moves
    assert _doc_texts(page) == ["Page 2", "Page 3", "Page 1"]
    out = tmp_path / "out.pdf"
    _save(window, dialogs, page, out)
    assert _texts(out) == ["Page 2", "Page 3", "Page 1"]


def test_rotation_follows_a_moved_page(window, dialogs, tmp_path):
    page, _ = _open(window, tmp_path)
    page.select(0)
    page.rotate(90)
    page.move_pages(1)
    out = tmp_path / "out.pdf"
    _save(window, dialogs, page, out)
    assert _texts(out) == ["Page 2", "Page 1", "Page 3"]
    assert _rotations(out) == [0, 90, 0]


def test_saved_order_includes_a_drag(window, dialogs, tmp_path):
    from PySide6.QtCore import QModelIndex
    page, _ = _open(window, tmp_path)
    # what an internal drag-move does: the model moves the row (rowsMoved)
    assert page.grid.model().moveRow(QModelIndex(), 2, QModelIndex(), 0)
    pump(0.05)
    assert _doc_texts(page) == ["Page 3", "Page 1", "Page 2"] and page.order() == [0, 1, 2]
    out = tmp_path / "out.pdf"
    _save(window, dialogs, page, out)
    assert _texts(out) == ["Page 3", "Page 1", "Page 2"]


def test_thumbnail_keeps_aspect_and_follows_rotation(window, tmp_path):
    # CTk test_rotate_thumbnail_keeps_aspect
    d = fitz.open()
    d.new_page(width=842, height=595)
    src = str(tmp_path / "wide.pdf")
    d.save(src)
    d.close()
    page, _ = _open(window, tmp_path, pages=1, src=src)
    img = page.render(0)
    assert img.width() > img.height()
    page.select(0)
    page.rotate(90)
    img = page.render(0)
    assert img.height() > img.width()
    icon = page.grid.item(0).icon().pixmap(200, 200)
    assert icon.height() > icon.width()     # refresh() re-rendered the thumbnail


def test_save_over_the_open_file(window, dialogs, tmp_path):
    page, src = _open(window, tmp_path)
    page.select(0)
    page.move_pages(1)
    _save(window, dialogs, page, src)
    assert _texts(src) == ["Page 2", "Page 1", "Page 3"]
    assert page._doc is not None and not page._doc.is_closed


def test_reopen_failure_keeps_the_open_document(window, dialogs, tmp_path):
    # CTk test_rotate_keeps_document_when_reopen_fails
    page, src = _open(window, tmp_path, pages=2)
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    page.file.set_path(str(bad))
    assert dialogs.errors()
    assert len(page._doc) == 2 and page.file.path() == src
    assert page.order() == [0, 1]


def test_drop_takes_pdfs_only(window, tmp_path):
    page, _ = _open(window, tmp_path)
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    second = make_pdf(tmp_path / "second.pdf", pages=5)
    assert page.accept_drop(second) is True
    assert len(page._doc) == 5 and page.order() == [0, 1, 2, 3, 4]


def test_cancelling_the_save_dialog_writes_nothing_and_keeps_the_document(window, dialogs,
                                                                          tmp_path):
    page, _ = _open(window, tmp_path)
    held = page._doc
    window.save_as()                        # no answer queued: the dialog is cancelled
    pump(0.05)
    assert window._current_job is None
    assert list(tmp_path.iterdir()) == [tmp_path / "in.pdf"]
    assert page._doc is held and not held.is_closed     # nothing else was opened


def test_leaving_the_tool_keeps_the_document_and_its_edits(window, dialogs, tmp_path):
    # One document per window (owner, 2026-10-23): the window holds it, the
    # page shows it again when it comes back, edits and all.
    page, src = _open(window, tmp_path)
    page.select(0)
    page.rotate(90)
    held = page._doc
    assert window.open_tool("MergeTool")
    assert not held.is_closed and window.document.doc is held and window.document.dirty
    assert window.open_tool("RotateTool")
    assert page._doc is held and page._doc[0].rotation == 90 and page.file.path() == src


def test_a_tool_may_write_its_output_over_the_open_file(window, dialogs, tmp_path):
    # CTk test_file_opened_in_another_tool_can_be_overwritten: the window lets
    # the file go (an in-memory copy) before a job replaces it.
    page, src = _open(window, tmp_path, pages=3)
    _select(page, 0)
    dialogs.save(src)
    page.extract()
    assert dialogs.msgs[-1][:2] == ("warning", "Extract")     # Extract itself refuses it
    window.run_job(lambda stop: os.replace(make_pdf(tmp_path / "o.pdf", pages=1), src),
                   keep_password=(None, [src]))
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    assert _texts(src) == ["Page 1"] and len(page._doc) == 3


# ── Delete, Undo, Extract (owner, 2026-10-17) ────────────────────────────────
def _select(page, *rows):
    page.grid.clearSelection()
    for r in rows:
        page.grid.item(r).setSelected(True)


def test_delete_asks_first_and_undo_brings_the_pages_back(window, dialogs, tmp_path):
    page, _ = _open(window, tmp_path, pages=4)
    _select(page, 1, 2)
    dialogs.asks.append(False)                       # No: nothing goes
    page.delete_pages()
    assert page.order() == [0, 1, 2, 3] and not page.is_dirty()
    assert dialogs.msgs[-1] == ("ask_yes_no", "Delete pages",
                                "Delete pages 2 and 3? Undo brings them back until you save.")
    dialogs.asks.append(True)
    page.delete_pages()
    assert _doc_texts(page) == ["Page 1", "Page 4"] and page.order() == [0, 1]
    assert page.is_dirty() and page.undo_btn.isEnabled()
    page.undo()
    assert _doc_texts(page) == ["Page 1", "Page 2", "Page 3", "Page 4"]
    assert page.order() == [0, 1, 2, 3] and not page.is_dirty()    # back at the file
    assert not page.undo_btn.isEnabled()


def test_undo_steps_back_through_turns_moves_and_drags(window, dialogs, tmp_path):
    page, _ = _open(window, tmp_path, pages=3)
    _select(page, 0)
    page.rotate(90)
    page.move_pages(1)
    assert _doc_texts(page) == ["Page 2", "Page 1", "Page 3"] and page._doc[1].rotation == 90
    page.undo()
    assert _doc_texts(page) == ["Page 1", "Page 2", "Page 3"] and page._doc[0].rotation == 90
    page.undo()
    assert page._doc[0].rotation == 0 and not page.is_dirty()


def test_every_page_selected_turns_delete_off_and_says_why(window, dialogs, tmp_path):
    page, _ = _open(window, tmp_path, pages=5)
    _select(page, 0, 1, 2, 3, 4)
    assert not page.delete_btn.isEnabled()
    assert page.hint_label.text() == "A PDF needs at least one page: keep one or more."
    page.delete_pages()                              # Ctrl/keyboard: still nothing goes
    assert page.order() == [0, 1, 2, 3, 4] and not dialogs.msgs
    _select(page, 0, 2, 3, 4)
    assert page.delete_btn.isEnabled()
    dialogs.asks.append(False)
    page.delete_pages()
    assert dialogs.msgs[-1][2] == "Delete pages 1, 3-5? Undo brings them back until you save."


def test_save_after_delete_writes_the_pages_left_whole(window, dialogs, tmp_path):
    page, src = _open(window, tmp_path, pages=3)
    before = open(src, "rb").read()
    _select(page, 1)
    dialogs.asks.append(True)
    page.delete_pages()
    page.save()                                     # over the file: written whole
    wait_job(window)
    assert _texts(src) == ["Page 1", "Page 3"]
    assert not open(src, "rb").read().startswith(before)
    # Saved: clean, and the history stays (Undo goes back past the save, as in
    # desktop editors; the document is unsaved again then).
    assert not page.is_dirty() and page.undo_btn.isEnabled()


def test_extract_writes_the_selection_as_turned_and_keeps_the_document(window, dialogs, tmp_path):
    page, src = _open(window, tmp_path, pages=4)
    _select(page, 3)
    page.rotate(90)
    _select(page, 3, 1)
    out = tmp_path / "picked.pdf"
    dialogs.save(out)
    page.extract()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    assert _texts(out) == ["Page 2", "Page 4"] and _rotations(out) == [0, 90]
    assert _texts(src) == ["Page 1", "Page 2", "Page 3", "Page 4"]     # the file is untouched
    assert page.order() == [0, 1, 2, 3] and page.is_dirty()             # the turn is unsaved
    assert window.status_text() == "✓  Extracted 2 pages → picked.pdf"
    assert page.offered_output() is not None


def test_extract_over_the_open_file_is_refused(window, dialogs, tmp_path):
    page, src = _open(window, tmp_path, pages=2)
    _select(page, 0)
    dialogs.save(src)
    page.extract()
    assert dialogs.msgs[-1][:2] == ("warning", "Extract") and window._current_job is None
