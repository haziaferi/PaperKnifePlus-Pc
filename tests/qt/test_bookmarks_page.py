"""The Qt Split by Bookmarks page: an organiser whose centre is the outline (group B)."""
import os

import pymupdf as fitz

from qt_harness import make_pdf, pump, wait_job


def _page(window):
    assert window.open_tool("BookmarksTool")
    pump(0.05)
    return window.current_page()


def _book(tmp_path, toc, pages=4, name="book.pdf"):
    src = tmp_path / name
    make_pdf(src, pages=pages)
    with fitz.open(src) as doc:
        doc.set_toc(toc)
        doc.saveIncr()
    return str(src)


def _open(window, src):
    page = _page(window)
    page.file.set_path(src)
    assert page._doc is not None
    return page


def _texts(path):
    with fitz.open(path) as d:
        return [pg.get_text().strip() for pg in d]


def _split(window, dialogs, page, out):
    out.mkdir(exist_ok=True)
    dialogs.dirs.append(str(out))
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    return {p.name: _texts(p) for p in out.iterdir()}


def test_page_builds_with_the_outline_centre_and_split_at_options(window):
    page = _page(window)
    assert page.title_label.text() == "Split by Bookmarks"
    assert page.outline_lines() == ["Open a PDF to see its bookmarks"]
    assert not page.grid.isVisibleTo(page)
    assert page._actions == []                                  # no context-bar actions
    assert page.radios[False].isChecked() and not page.all_levels
    assert page.settings_area is not None


def test_split_without_a_file_warns(window, dialogs):
    page = _page(window)
    page.run()
    assert dialogs.msgs[-1] == ("warning", "Bookmarks", "Select a PDF first.")


def test_outline_lists_levels_with_indent_and_pages(window, tmp_path):
    src = _book(tmp_path, [[1, "Intro", 1], [2, "Part", 2], [1, "End", 4]])
    page = _open(window, src)
    assert page.outline_lines() == ["▸ Intro  (p.1)", "    Part  (p.2)", "▸ End  (p.4)"]
    assert page.subtitle_label.text() == "book.pdf"


def test_outline_caps_at_sixty_entries_with_a_more_line(window, tmp_path):
    src = _book(tmp_path, [[1, f"C{i}", 1] for i in range(65)], pages=1)
    page = _open(window, src)
    lines = page.outline_lines()
    assert len(lines) == 61 and lines[59] == "▸ C59  (p.1)"
    assert lines[-1] == "… and 5 more bookmarks"


def test_no_bookmarks_shows_the_warning_line_and_split_warns(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "plain.pdf", pages=2)
    page = _open(window, src)
    assert page.outline_lines() == ["⚠  This PDF has no bookmarks."]
    page.run()
    assert dialogs.msgs[-1] == ("warning", "Bookmarks", "PDF has no bookmarks.")


def test_split_skips_untargeted_entries(window, dialogs, tmp_path):
    # CTk test_bookmark_split_skips_untargeted_entries
    src = _book(tmp_path, [[1, "A", 1], [1, "Loose", -1], [1, "B", 3]])
    page = _open(window, src)
    files = _split(window, dialogs, page, tmp_path / "out")
    assert files == {"01_A.pdf": ["Page 1", "Page 2"],
                     "02_B.pdf": ["Page 3", "Page 4"]}, files
    out = tmp_path / "out"
    assert window.status_text() == f"✓  Split into 2 chapter(s) → {out}"
    assert dialogs.msgs[-1] == (
        "info", "Done",
        f"Split into 2 file(s):\n{out}\n\n1 bookmark(s) with no page target were skipped.")


def test_split_at_top_level_or_all_levels(window, dialogs, tmp_path):
    src = _book(tmp_path, [[1, "A", 1], [2, "A1", 2], [1, "B", 3]])
    page = _open(window, src)
    top = _split(window, dialogs, page, tmp_path / "top")
    assert top == {"01_A.pdf": ["Page 1", "Page 2"], "02_B.pdf": ["Page 3", "Page 4"]}, top
    page.radios[True].setChecked(True)
    assert page.all_levels
    every = _split(window, dialogs, page, tmp_path / "all")
    assert every == {"01_A.pdf": ["Page 1"], "02_A1.pdf": ["Page 2"],
                     "03_B.pdf": ["Page 3", "Page 4"]}, every


def test_split_cuts_in_page_order(window, dialogs, tmp_path):
    # CTk test_bookmark_split_cuts_in_page_order
    src = _book(tmp_path, [[1, "A", 1], [2, "A2", 3], [2, "A1", 2]], pages=3)
    page = _open(window, src)
    page.radios[True].setChecked(True)
    files = _split(window, dialogs, page, tmp_path / "out")
    pages = sorted(p for texts in files.values() for p in texts)
    assert pages == ["Page 1", "Page 2", "Page 3"], files


def test_no_bookmark_with_a_page_warns(window, dialogs, tmp_path):
    src = _book(tmp_path, [[1, "Loose", -1]], pages=2)
    page = _open(window, src)
    page.run()
    assert dialogs.msgs[-1] == ("warning", "Bookmarks",
                                "No matching bookmarks point to a page.")


def test_reopen_failure_keeps_the_open_document(window, dialogs, tmp_path):
    src = _book(tmp_path, [[1, "A", 1]], pages=2)
    page = _open(window, src)
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    page.file.set_path(str(bad))
    assert dialogs.errors()
    assert len(page._doc) == 2 and page.file.path() == src
    assert page.outline_lines() == ["▸ A  (p.1)"]


def test_drop_takes_pdfs_only(window, tmp_path):
    page = _page(window)
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    src = _book(tmp_path, [[1, "A", 1]], pages=2)
    assert page.accept_drop(src) is True
    assert page._doc is not None and page.file.path() == src


def test_cancelling_the_folder_dialog_writes_nothing_and_keeps_the_document(window, dialogs,
                                                                            tmp_path):
    src = _book(tmp_path, [[1, "A", 1], [1, "B", 3]])
    page = _open(window, src)
    held = page._doc
    page.run()                              # no folder queued: the dialog is cancelled
    pump(0.05)
    assert window._current_job is None
    assert list(tmp_path.iterdir()) == [tmp_path / "book.pdf"]
    assert page._doc is held and not held.is_closed     # nothing else was opened


def test_leaving_the_tool_closes_its_document_and_frees_the_file(window, tmp_path):
    # CTk test_navigating_away_closes_the_open_documents and
    # test_file_opened_in_another_tool_can_be_overwritten
    src = _book(tmp_path, [[1, "A", 1]], pages=2)
    page = _open(window, src)
    held = page._doc
    assert window.open_tool("CropTool")
    assert held.is_closed and page._doc is None and page.file.path() == ""
    assert page.outline_lines() == ["Open a PDF to see its bookmarks"]
    other = make_pdf(tmp_path / "other.pdf", pages=1)
    os.replace(other, src)                  # fails on Windows while a handle holds src
    assert _texts(src) == ["Page 1"]
