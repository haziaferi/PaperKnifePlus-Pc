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
    dialogs.save(out)
    page.save()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()


def test_page_builds_with_its_actions_and_one_thumbnail_per_page(window, tmp_path):
    page, _ = _open(window, tmp_path, pages=4)
    assert page.title_label.text() == "Rotate & Reorder"
    assert [b.text() for b in page._actions] == [
        "↺ 90° CCW", "↻ 90° CW", "⤢ 180°", "← Move Left", "Move Right →"]
    assert page.order() == [0, 1, 2, 3]
    assert [page.grid.item(i).text() for i in range(4)] == ["p.1", "p.2", "p.3", "p.4"]
    assert not page.rendering() and not page.grid.item(0).icon().isNull()
    assert not any(b.isEnabled() for b in page._actions)       # nothing selected yet


def test_save_without_a_file_warns(window, dialogs):
    page = _page(window)
    page.save()
    assert dialogs.msgs[-1][:3] == ("warning", "Save", "Open a PDF first.")


def test_save_unchanged_writes_the_same_pages(window, dialogs, tmp_path):
    page, _ = _open(window, tmp_path)
    out = tmp_path / "out.pdf"
    _save(window, dialogs, page, out)
    assert _texts(out) == ["Page 1", "Page 2", "Page 3"]
    assert _rotations(out) == [0, 0, 0]
    assert window.status_text() == "✓  Saved → out.pdf"
    assert dialogs.msgs[-1] == ("info", "Saved", f"PDF saved:\n{out}")


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
    assert page.order() == [1, 0, 2] and page.selected() == [1]
    page.select(2)
    page.move_pages(-1)                     # 2 3 1
    assert page.order() == [1, 2, 0]
    page.select(0)
    page.move_pages(-1)                     # already first: nothing moves
    assert page.order() == [1, 2, 0]
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
    page, _ = _open(window, tmp_path)
    it = page.grid.takeItem(2)              # what an internal drag-move does
    page.grid.insertItem(0, it)
    assert page.order() == [2, 0, 1]
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
    page.save()                             # no answer queued: the dialog is cancelled
    pump(0.05)
    assert window._current_job is None
    assert list(tmp_path.iterdir()) == [tmp_path / "in.pdf"]
    assert page._doc is held and not held.is_closed     # nothing else was opened


def test_leaving_the_tool_closes_its_document_and_frees_the_file(window, dialogs, tmp_path):
    # CTk test_navigating_away_closes_the_open_documents and
    # test_file_opened_in_another_tool_can_be_overwritten
    page, src = _open(window, tmp_path)
    held = page._doc
    assert window.open_tool("CropTool")
    # Since 2026-10-10 (owner) leaving keeps the document: closed and its file
    # freed, the path kept; the page opens it again when shown.
    assert held.is_closed and page._doc is None and page.file.path() == src

    other = make_pdf(tmp_path / "other.pdf", pages=1)
    os.replace(other, src)                  # fails on Windows while a handle holds src
    assert _texts(src) == ["Page 1"]
