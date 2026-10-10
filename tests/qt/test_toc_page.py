"""The Qt Bookmarks / TOC page: list, edit, reorder and save PDF bookmarks."""
import os

import pymupdf as fitz

from qt_harness import make_pdf, pump, spy_open, subtitle_with, wait_job


def _page(window):
    assert window.open_tool("TocTool")
    pump(0.05)
    return window.current_page()


def _with_toc(path, toc):
    with fitz.open(path) as doc:
        doc.set_toc(toc)
        doc.saveIncr()
    return str(path)


def _toc_of(path, pw=None):
    with fitz.open(path) as d:
        if pw:
            assert d.authenticate(pw)
        return d.get_toc()


def _texts(path):
    with fitz.open(path) as d:
        return [p.get_text().strip() for p in d]


def _save(window, dialogs, page, out):
    dialogs.save(out)
    page.save()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()


def test_the_page_builds_with_its_controls(window):
    page = _page(window)
    assert type(page).__name__ == "TocPage"
    assert page.title_label.text() == "Bookmarks / TOC"
    assert page.file.path() == "" and page.count() == 0
    assert page.level.currentText() == "1" and page.level.count() == 4
    assert page.title_edit.text() == "" and page.page_edit.text() == ""
    assert [b.text() for b in page._tools] == ["Add below", "Up", "Down", "Delete"]
    assert not page.update_btn.isEnabled()


def test_without_a_file_save_and_add_warn(window, dialogs):
    page = _page(window)
    page.save()
    assert dialogs.msgs[-1] == ("warning", "Save", "Open a PDF first.")
    page._add()
    assert dialogs.msgs[-1] == ("warning", "Add", "Open a PDF first.")


def test_opening_lists_the_bookmarks_as_the_ctk_list(window, tmp_path):
    page = _page(window)
    src = _with_toc(make_pdf(tmp_path / "in.pdf", pages=3),
                    [[1, "A", 1], [2, "A1", 2], [1, "B", 3]])
    page.file.set_path(src)
    assert page.count() == 3
    assert [page.list.item(i).text() for i in range(3)] == [
        "▸ A  (p.1)", "  ▸ A1  (p.2)", "▸ B  (p.3)"]
    assert page.subtitle_label.text() == subtitle_with(
        "View · add · edit · delete · reorder PDF bookmarks", "in.pdf")
    page.select(1)
    assert (page.level.currentText(), page.title_edit.text(), page.page_edit.text()) == (
        "2", "A1", "2")
    assert page.update_btn.isEnabled()


def test_add_and_save_writes_the_bookmark_and_keeps_the_pages(window, dialogs, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    out = tmp_path / "out.pdf"
    page.file.set_path(src)
    page.title_edit.setText("Chapter")
    page.page_edit.setText("2")
    page._add()
    _save(window, dialogs, page, out)
    assert _toc_of(out) == [[1, "Chapter", 2]]
    assert _texts(out) == ["Page 1", "Page 2", "Page 3"]
    assert dialogs.msgs[-1] == ("info", "Saved", f"PDF with updated bookmarks:\n{out}")
    assert window.status_text() == "✓  Saved 1 bookmark(s) → out.pdf"


def test_add_without_a_title_uses_new_bookmark_and_goes_below_the_selection(
        window, dialogs, tmp_path):
    page = _page(window)
    src = _with_toc(make_pdf(tmp_path / "in.pdf", pages=3), [[1, "A", 1], [1, "B", 3]])
    page.file.set_path(src)
    page.select(0)
    page.title_edit.setText("")
    page.level.setCurrentText("2")
    page.page_edit.setText("2")
    page._add()
    assert page.current() == 1
    _save(window, dialogs, page, tmp_path / "out.pdf")
    assert _toc_of(tmp_path / "out.pdf") == [[1, "A", 1], [2, "New bookmark", 2], [1, "B", 3]]


def test_update_selected_changes_level_title_and_page(window, dialogs, tmp_path):
    page = _page(window)
    src = _with_toc(make_pdf(tmp_path / "in.pdf", pages=3), [[1, "A", 1], [1, "B", 3]])
    page.file.set_path(src)
    page.select(1)
    page.level.setCurrentText("2")
    page.title_edit.setText("  B2  ")
    page.page_edit.setText("2")
    page.update_btn.click()
    assert page.list.item(1).text() == "  ▸ B2  (p.2)" and page.current() == 1
    _save(window, dialogs, page, tmp_path / "out.pdf")
    assert _toc_of(tmp_path / "out.pdf") == [[1, "A", 1], [2, "B2", 2]]


def test_up_and_down_reorder(window, dialogs, tmp_path):
    page = _page(window)
    src = _with_toc(make_pdf(tmp_path / "in.pdf", pages=3),
                    [[1, "A", 1], [1, "B", 2], [1, "C", 3]])
    page.file.set_path(src)
    page.select(2)
    page._tools[1].click()                  # Up
    assert page.current() == 1
    page.select(0)
    page._tools[2].click()                  # Down
    assert page.current() == 1
    _save(window, dialogs, page, tmp_path / "out.pdf")
    assert _toc_of(tmp_path / "out.pdf") == [[1, "C", 3], [1, "A", 1], [1, "B", 2]]


def test_delete_parent_promotes_children(window, dialogs, tmp_path):
    page = _page(window)
    src = _with_toc(make_pdf(tmp_path / "in.pdf", pages=3),
                    [[1, "A", 1], [2, "A1", 2], [3, "A1a", 2], [1, "B", 3]])
    page.file.set_path(src)
    page.select(0)
    page._tools[3].click()                  # Delete
    _save(window, dialogs, page, tmp_path / "out.pdf")
    assert _toc_of(tmp_path / "out.pdf") == [[1, "A1", 2], [2, "A1a", 2], [1, "B", 3]]


def test_rejects_page_past_the_end_and_bad_numbers(window, dialogs, tmp_path):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf", pages=3))
    page.page_edit.setText("99")
    page._add()
    assert page._toc == []
    assert dialogs.msgs[-1] == ("warning", "Add", "Page must be between 1 and 3.")
    page.page_edit.setText("two")
    page._add()
    assert page._toc == []
    assert dialogs.msgs[-1] == ("warning", "Add", "Enter valid level and page number.")


def test_save_refuses_a_level_jump(window, dialogs, tmp_path):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf", pages=3))
    page.level.setCurrentText("3")
    page.title_edit.setText("Deep")
    page.page_edit.setText("1")
    page._add()
    out = tmp_path / "out.pdf"
    dialogs.save(out)
    page.save()
    assert dialogs.msgs[-1][:2] == ("warning", "Save")
    assert "is level 3 but follows level 0" in dialogs.msgs[-1][2]
    assert not out.exists()


def test_saves_over_the_open_input(window, dialogs, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    page.file.set_path(src)
    page.title_edit.setText("Chapter")
    page.page_edit.setText("2")
    page._add()
    _save(window, dialogs, page, src)
    window.show_page("CompressTool")
    assert _toc_of(src) == [[1, "Chapter", 2]]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["in.pdf"]


def test_saving_over_an_encrypted_input_keeps_its_password(window, dialogs, tmp_path):
    src = tmp_path / "in.pdf"
    doc = fitz.open()
    for _ in range(3):
        doc.new_page()
    doc.save(str(src), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    doc.close()
    page = _page(window)
    dialogs.passwords.append("u")
    page.file.set_path(str(src))
    page.title_edit.setText("Chapter")
    page.page_edit.setText("2")
    page._add()
    dialogs.asks.append(True)               # "Keep the password on the new file?"
    _save(window, dialogs, page, str(src))
    window.show_page("CompressTool")
    with fitz.open(str(src)) as d:
        assert d.needs_pass
        assert d.authenticate("u")
        assert d.get_toc() == [[1, "Chapter", 2]]


def test_a_dropped_pdf_is_opened_and_others_are_refused(window, tmp_path):
    page = _page(window)
    src = _with_toc(make_pdf(tmp_path / "in.pdf"), [[1, "A", 1]])
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False and page._doc is None
    assert page.accept_drop(src) is True and page.file.path() == src
    assert page._doc is not None and page.count() == 1


def test_a_file_that_cannot_be_opened_keeps_the_open_one(window, dialogs, tmp_path):
    page = _page(window)
    src = _with_toc(make_pdf(tmp_path / "in.pdf"), [[1, "A", 1]])
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    page.file.set_path(src)
    held = page._doc
    page.file.set_path(str(bad))
    assert dialogs.errors()
    assert page._doc is held and not held.is_closed
    assert page.file.path() == src and page.count() == 1


def test_cancelling_the_save_dialog_writes_nothing_and_opens_nothing(window, dialogs, tmp_path,
                                                                     monkeypatch):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf", pages=2))
    opened = spy_open(window, monkeypatch)
    page.title_edit.setText("X")
    page.page_edit.setText("1")
    page._add()
    page.save()                         # no path queued: the dialog returns ""
    assert opened == [] and window._current_job is None
    assert sorted(p.name for p in tmp_path.iterdir()) == ["in.pdf"]
    assert page._doc is not None and page._toc == [[1, "X", 1]]


def test_leaving_the_tool_closes_its_document(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    opened = spy_open(window, monkeypatch)
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    page.file.set_path(src)
    held = page._doc
    window.show_page("CompressTool")
    assert held.is_closed and opened == [held]
    # Since 2026-10-10 (owner) leaving keeps the document: closed and its file
    # freed, the path (and the list) kept; shown again, the page reopens it.
    assert page._doc is None and page.file.path() == src
    assert _page(window) is page and page._doc is not None and len(opened) == 2



def test_a_file_opened_here_can_be_overwritten_after_leaving(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    page = _page(window)
    page.file.set_path(src)
    held = page._doc
    window.show_page("CompressTool")
    assert held.is_closed
    other = make_pdf(tmp_path / "other.pdf", pages=1)
    os.replace(other, src)              # Windows refuses this while a handle is held
    assert _texts(src) == ["Page 1"]
