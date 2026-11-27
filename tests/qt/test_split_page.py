"""The Qt Split page: one PDF cut into files at page ranges, at bookmarks, or at
cut marks on its pages (owner, 2026-10-17: Split by Bookmarks is Split's
"Cut at" choice; the pages show as thumbnails with the parts on them)."""

import pymupdf as fitz
import pytest

from qt_harness import make_pdf, pump, wait_job


def _page(window):
    assert window.open_tool("SplitTool")
    pump(0.05)
    return window.current_page()


def _texts(path):
    with fitz.open(path) as d:
        return [p.get_text().strip() for p in d]


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


def _run(window, dialogs, page, out):
    out.mkdir(exist_ok=True)
    dialogs.dirs.append(str(out))
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    return {p.name: _texts(p) for p in out.iterdir()}


# ── the page ─────────────────────────────────────────────────────────────────
def test_the_page_builds_with_cut_at_and_the_grid(window):
    page = _page(window)
    assert type(page).__name__ == "SplitPage" and page.title_label.text() == "Split"
    assert page.radios["ranges"].isChecked() and page.mode == "ranges"
    assert not page.radios["top"].isEnabled() and not page.radios["all"].isEnabled()
    assert page.ranges.text() == "" and page.file.path() == ""
    assert not page.parts_card.isVisibleTo(page)            # no document, no parts
    assert page.settings_area is not None


def test_split_by_bookmarks_is_no_longer_a_tool(window):
    assert "BookmarksTool" not in window._hosts


def test_without_a_file_it_asks_for_one(window, dialogs):
    page = _page(window)
    page.run()
    assert dialogs.msgs[-1] == ("warning", "Split", "Select a PDF first.")


def test_opening_shows_every_page_and_one_part_per_page(window, tmp_path):
    page = _open(window, make_pdf(tmp_path / "in.pdf", pages=3))
    assert page.order() == [0, 1, 2]
    assert page.parts() == [[0], [1], [2]]
    assert page.part_lines() == ["Part 01 · page 1", "Part 02 · page 2", "Part 03 · page 3"]
    assert page.parts_title.text() == "Parts (3)"
    assert page.marks() == [(1, True), (2, True), (3, False)]


# ── page ranges ──────────────────────────────────────────────────────────────
def test_blank_ranges_write_every_page_to_its_own_file(window, dialogs, tmp_path):
    page = _open(window, make_pdf(tmp_path / "in.pdf", pages=3))
    out = tmp_path / "out"
    files = _run(window, dialogs, page, out)
    assert sorted(files) == ["in_part01_p1-1.pdf", "in_part02_p2-2.pdf", "in_part03_p3-3.pdf"]
    assert files["in_part02_p2-2.pdf"] == ["Page 2"]
    assert dialogs.msgs[-1] == ("info", "Done", f"Created 3 file(s) in:\n{out}")
    assert window.status_text() == f"✓  Split into 3 file(s) → {out}"


def test_typed_ranges_set_the_parts_and_the_grid(window, dialogs, tmp_path):
    page = _open(window, make_pdf(tmp_path / "in.pdf", pages=5))
    page.ranges.setText("2-3; end")
    assert page.parts() == [[1, 2], [4]]
    assert page.part_lines() == ["Part 01 · pages 2-3", "Part 02 · page 5"]
    # Page 1 and 4 are in no part: veiled; no cut between parts not in a row.
    assert page.marks() == [(0, False), (1, False), (1, False), (0, False), (2, False)]
    files = _run(window, dialogs, page, tmp_path / "out")
    assert files == {"in_part01_p2-3.pdf": ["Page 2", "Page 3"], "in_part02_p5-5.pdf": ["Page 5"]}


@pytest.mark.parametrize("ranges,bad", [("99, 7-9", "page 99 does not exist"),
                                        ("5, 7-9", "page 7 does not exist")])
def test_a_bad_range_shows_in_the_list_and_is_refused(window, dialogs, tmp_path, ranges, bad):
    page = _open(window, make_pdf(tmp_path / "in.pdf", pages=5))
    out = tmp_path / "out"
    out.mkdir()
    dialogs.dirs.append(str(out))   # offered, so a split that ran anyway would land here
    page.ranges.setText(ranges)
    assert bad in page.part_lines()[0] and page.part_lines()[0].startswith("⚠")
    assert all(m[0] is None for m in page.marks())          # no parts on the grid
    page.run()
    assert window._current_job is None                      # refused before any job
    assert list(out.iterdir()) == [] and dialogs.dirs == [str(out)]
    assert dialogs.errors()[-1][1] == "Split" and bad in dialogs.errors()[-1][2]


# ── on the grid ──────────────────────────────────────────────────────────────
def test_clicking_a_gap_cuts_and_clicking_it_again_joins(window, tmp_path):
    page = _open(window, make_pdf(tmp_path / "in.pdf", pages=4))
    page.ranges.setText("1-4")
    assert page.parts() == [[0, 1, 2, 3]]
    page._toggle_cut(1)                                     # the gap after page 2
    assert page.parts() == [[0, 1], [2, 3]] and page.ranges.text() == "1-2; 3-4"
    assert page.marks()[1] == (1, True)
    page._toggle_cut(1)
    assert page.parts() == [[0, 1, 2, 3]] and page.ranges.text() == "1-4"


def test_a_click_in_the_gap_reaches_the_cut(window, tmp_path):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    page = _open(window, make_pdf(tmp_path / "in.pdf", pages=3))
    page.ranges.setText("1-3")
    pump(0.1)
    rect = page.grid.visualRect(page.grid.model().index(0, 0))
    QTest.mouseClick(page.grid.viewport(), Qt.LeftButton, Qt.NoModifier,
                     QPoint(rect.right() - 2, rect.center().y()))
    assert page.parts() == [[0], [1, 2]]
    assert page.grid.selectedItems() == []                  # a gap click does not select
    QTest.mouseClick(page.grid.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())
    assert len(page.grid.selectedItems()) == 1              # the thumbnail still selects


def test_selected_pages_become_one_part_and_the_field_says_so(window, dialogs, tmp_path):
    page = _open(window, make_pdf(tmp_path / "in.pdf", pages=6))
    page.ranges.setText("1-6")
    for row in (1, 4):
        page.grid.item(row).setSelected(True)
    page._selection_to_part()
    # The pages taken form a part; the rest of their part stays one part.
    assert page.parts() == [[1, 4], [0, 2, 3, 5]]
    assert page.ranges.text() == "2, 5; 1, 3-4, 6"
    files = _run(window, dialogs, page, tmp_path / "out")
    assert files == {"in_part01_p2+5.pdf": ["Page 2", "Page 5"],
                     "in_part02_p1+3-4+6.pdf": ["Page 1", "Page 3", "Page 4", "Page 6"]}


def test_cutting_on_the_grid_turns_bookmarks_into_ranges(window, tmp_path):
    page = _open(window, _book(tmp_path, [[1, "A", 1], [1, "B", 3]]))
    page.radios["top"].setChecked(True)
    assert page.parts() == [[0, 1], [2, 3]]
    page._toggle_cut(2)
    assert page.mode == "ranges" and page.parts() == [[0, 1], [2], [3]]


# ── bookmarks ────────────────────────────────────────────────────────────────
def test_bookmark_parts_are_listed_with_their_titles(window, tmp_path):
    page = _open(window, _book(tmp_path, [[1, "Intro", 1], [2, "Part", 2], [1, "End", 4]]))
    assert page.radios["top"].isEnabled()
    page.radios["top"].setChecked(True)
    assert page.part_lines() == ["01 Intro · pages 1-3", "02 End · page 4"]
    page.radios["all"].setChecked(True)
    assert page.part_lines() == ["01 Intro · page 1", "02 Part · pages 2-3", "03 End · page 4"]
    assert not page._range_row.parentWidget().isVisibleTo(page)     # the field is for ranges


def test_a_pdf_without_bookmarks_disables_them(window, tmp_path):
    page = _open(window, _book(tmp_path, [[1, "A", 1]], name="a.pdf"))
    page.radios["all"].setChecked(True)
    page.file.set_path(make_pdf(tmp_path / "plain.pdf", pages=2))
    assert not page.radios["top"].isEnabled() and page.mode == "ranges"


def test_split_at_top_level_or_all_levels(window, dialogs, tmp_path):
    page = _open(window, _book(tmp_path, [[1, "A", 1], [2, "A1", 2], [1, "B", 3]]))
    page.radios["top"].setChecked(True)
    top = _run(window, dialogs, page, tmp_path / "top")
    assert top == {"01_A.pdf": ["Page 1", "Page 2"], "02_B.pdf": ["Page 3", "Page 4"]}, top
    page.radios["all"].setChecked(True)
    every = _run(window, dialogs, page, tmp_path / "all")
    assert every == {"01_A.pdf": ["Page 1"], "02_A1.pdf": ["Page 2"],
                     "03_B.pdf": ["Page 3", "Page 4"]}, every


def test_untargeted_bookmarks_are_skipped_and_said(window, dialogs, tmp_path):
    page = _open(window, _book(tmp_path, [[1, "A", 1], [1, "Loose", -1], [1, "B", 3]]))
    page.radios["top"].setChecked(True)
    assert page.part_lines()[-1] == "1 bookmark(s) with no page target will be skipped."
    out = tmp_path / "out"
    files = _run(window, dialogs, page, out)
    assert files == {"01_A.pdf": ["Page 1", "Page 2"], "02_B.pdf": ["Page 3", "Page 4"]}
    assert window.status_text() == f"✓  Split into 2 chapter(s) → {out}"
    assert dialogs.msgs[-1] == (
        "info", "Done",
        f"Split into 2 file(s):\n{out}\n\n1 bookmark(s) with no page target were skipped.")


def test_bookmarks_cut_in_page_order(window, dialogs, tmp_path):
    page = _open(window, _book(tmp_path, [[1, "A", 1], [2, "A2", 3], [2, "A1", 2]], pages=3))
    page.radios["all"].setChecked(True)
    files = _run(window, dialogs, page, tmp_path / "out")
    assert files == {"01_A.pdf": ["Page 1"], "02_A1.pdf": ["Page 2"], "03_A2.pdf": ["Page 3"]}


def test_no_bookmark_with_a_page_is_refused(window, dialogs, tmp_path):
    page = _open(window, _book(tmp_path, [[1, "Loose", -1]], pages=2))
    page.radios["top"].setChecked(True)
    assert page.part_lines() == ["⚠  No matching bookmarks point to a page."]
    page.run()
    assert dialogs.msgs[-1] == ("warning", "Split", "No matching bookmarks point to a page.")


# ── the document ─────────────────────────────────────────────────────────────
def test_a_dropped_pdf_opens_and_others_are_refused(window, tmp_path):
    page = _page(window)
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    src = make_pdf(tmp_path / "in.pdf")
    assert page.accept_drop(src) is True and page._doc is not None


def test_cancelling_the_folder_dialog_writes_nothing_and_keeps_the_document(window, dialogs,
                                                                            tmp_path):
    page = _open(window, make_pdf(tmp_path / "in.pdf"))
    held = page._doc
    page.run()                              # no folder queued: the dialog is cancelled
    pump(0.05)
    assert window._current_job is None and page._doc is held and not held.is_closed
    assert list(tmp_path.iterdir()) == [tmp_path / "in.pdf"]


def test_a_part_over_the_source_name_goes_on_from_its_copy(window, dialogs, tmp_path):
    # The source is named like its first chapter's output, in the output folder.
    src = _book(tmp_path, [[1, "Intro", 1], [1, "Body", 3]], name="01_Intro.pdf")
    page = _open(window, src)
    page.radios["top"].setChecked(True)
    dialogs.dirs.append(str(tmp_path))
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    assert _texts(tmp_path / "01_Intro.pdf") == ["Page 1", "Page 2"]
    assert _texts(tmp_path / "02_Body.pdf") == ["Page 3", "Page 4"]


def test_leaving_the_tool_keeps_the_document_for_the_next_tool(window, tmp_path):
    # One document per window (owner, 2026-10-23): the window holds it.
    from paperknife.qt.pages import same_path
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    page = _open(window, src)
    held = page._doc
    assert window.open_tool("MergeTool")
    assert not held.is_closed and window.document.doc is held
    assert _page(window) is page and page._doc is held and same_path(page.file.path(), src)
    assert page.order() == [0, 1]
