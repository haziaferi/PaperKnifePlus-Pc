"""The Qt Merge page: PDFs in order, each with its own page range, and every
input's pages in one strip in merged order (owner, 2026-10-17)."""
import pymupdf as fitz

from qt_harness import make_pdf, pump, spy_open, wait_job


def _page(window):
    assert window.open_tool("MergeTool")
    pump(0.05)
    return window.current_page()


def _texts(path):
    with fitz.open(path) as d:
        return [p.get_text().strip() for p in d]


def test_the_page_builds_with_one_range_field_per_file(window, tmp_path):
    from qfluentwidgets import LineEdit
    page = _page(window)
    assert type(page).__name__ == "MergePage"
    assert page.settings is None
    page.add_paths([make_pdf(tmp_path / "a.pdf")])
    ed = page.rows[0].extra
    assert isinstance(ed, LineEdit)
    assert ed.placeholderText() == "all  or  1-3, 5, 8-end"


def test_merge_without_files_warns(window, dialogs):
    page = _page(window)
    page.run()
    assert dialogs.msgs[-1][:2] == ("warning", "Merge")
    assert "Add at least one PDF file." in dialogs.msgs[-1][2]


def test_blank_ranges_merge_every_page_in_list_order(window, dialogs, tmp_path):
    a = make_pdf(tmp_path / "a.pdf", pages=2, text="A{n}")
    b = make_pdf(tmp_path / "b.pdf", pages=3, text="B{n}")
    page = _page(window)
    page.add_paths([a, b])
    out = tmp_path / "merged.pdf"
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    assert _texts(out) == ["A1", "A2", "B1", "B2", "B3"]
    assert dialogs.msgs[-1][:2] == ("info", "Merge Complete")
    assert str(out) in dialogs.msgs[-1][2]
    assert window.status_text() == "✓  Merged 2 file(s) · 5 pages → merged.pdf"
    assert window.status_role == "success"


def test_merge_can_overwrite_one_of_its_inputs(window, dialogs, tmp_path):
    a = make_pdf(tmp_path / "a.pdf", pages=2, text="A{n}")
    b = make_pdf(tmp_path / "b.pdf", pages=3, text="B{n}")
    page = _page(window)
    page.add_paths([a, b])
    dialogs.save(a)                    # save the result over the first input
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    assert _texts(a) == ["A1", "A2", "B1", "B2", "B3"]
    assert _texts(b) == ["B1", "B2", "B3"]
    assert not list(tmp_path.glob("*.part"))
    assert dialogs.msgs[-1][:2] == ("info", "Merge Complete")


def test_merge_uses_each_files_range(window, dialogs, tmp_path):
    a = make_pdf(tmp_path / "a.pdf", pages=5, text="A{n}")
    b = make_pdf(tmp_path / "b.pdf", pages=2, text="B{n}")
    page = _page(window)
    page.add_paths([a, b])
    page.rows[0].extra.setText("4-end, 1")
    # Typing reorders too (owner, 2026-10-17): the strip follows the field.
    assert page.left_out() == [(0, 1), (0, 2)]
    assert page.strip.keys()[:5] == [(0, 3), (0, 1), (0, 2), (0, 4), (0, 0)]
    out = tmp_path / "merged.pdf"
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    assert _texts(out) == ["A4", "A5", "A1", "B1", "B2"]


def test_reordering_changes_the_output_order(window, dialogs, tmp_path):
    a = make_pdf(tmp_path / "a.pdf", pages=1, text="A{n}")
    b = make_pdf(tmp_path / "b.pdf", pages=1, text="B{n}")
    page = _page(window)
    page.add_paths([a, b])
    page.select(1)
    page.move(-1)
    out = tmp_path / "merged.pdf"
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert _texts(out) == ["B1", "A1"]


def test_a_reversed_range_is_reported_instead_of_dropped(window, dialogs, tmp_path, monkeypatch):
    a = make_pdf(tmp_path / "a.pdf", pages=5, text="A{n}")
    b = make_pdf(tmp_path / "b.pdf", pages=2, text="B{n}")
    page = _page(window)
    page.add_paths([a, b])
    page.rows[0].extra.setText("5-3")
    out = tmp_path / "merged.pdf"
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert not out.exists(), f"merged without file a: {_texts(out)}"
    assert any(m[1] == "Merge" and "a.pdf" in m[2] for m in dialogs.errors()), dialogs.msgs
    assert dialogs.saves == [str(out)]             # refused before the save dialog


def test_a_dropped_pdf_is_added_and_others_are_refused(window, tmp_path):
    page = _page(window)
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    assert page.paths() == []
    src = make_pdf(tmp_path / "in.pdf")
    assert page.accept_drop(src) is True
    assert page.paths() == [src]


def test_an_added_file_is_read_and_its_file_let_go(window, dialogs, tmp_path, monkeypatch):
    # Read once when added (thumbnails, password once); the file is not held.
    page = _page(window)
    opened = spy_open(window, monkeypatch)
    page.add_paths([make_pdf(tmp_path / "a.pdf"), make_pdf(tmp_path / "b.pdf")])
    assert len(opened) == 2 and all(d.is_closed for d in opened)
    page.run()                     # no save path queued: the dialog returns ""
    assert window._current_job is None and not dialogs.errors()


def test_leaving_the_tool_leaves_no_document_open(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    opened = spy_open(window, monkeypatch)
    page.add_paths([make_pdf(tmp_path / "a.pdf")])
    out = tmp_path / "merged.pdf"
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert window.show_page("home")
    pump(0.02)
    assert opened and all(d.is_closed for d in opened)
    assert out.exists()


# ── the strip ────────────────────────────────────────────────────────────────
def _two(window, tmp_path):
    a = make_pdf(tmp_path / "a.pdf", pages=3, text="A{n}")
    b = make_pdf(tmp_path / "b.pdf", pages=2, text="B{n}")
    page = _page(window)
    page.add_paths([a, b])
    return page


def test_the_strip_shows_every_page_under_its_file(window, tmp_path):
    page = _two(window, tmp_path)
    assert page.strip.keys() == [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1)]
    assert page.headings() == ["a.pdf · 3 pages", "b.pdf · 2 pages"]
    assert page.list_card.width() <= 360 and page.strip.isVisibleTo(page)
    while page.rendering():
        pump(0.02)
    assert all(page.strip.has_icon(k) for k in page.strip.keys())


def test_leave_out_and_put_back_keep_the_range_field_in_step(window, dialogs, tmp_path):
    page = _two(window, tmp_path)
    page.strip.select_keys([(0, 1), (1, 0)])
    page.leave_out()
    assert page.left_out() == [(0, 1), (1, 0)]
    assert page.ranges() == ["1, 3", "2"]
    assert page.strip.keys() == [(0, 0), (0, 1), (0, 2), (1, 0), (1, 1)]   # it stays in place
    page.strip.select_keys([(1, 0)])
    page.put_back()
    assert page.ranges() == ["1, 3", ""]
    out = tmp_path / "merged.pdf"
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert _texts(out) == ["A1", "A3", "B1", "B2"]


def test_dragging_pages_between_files_mixes_them_in_strip_order(window, dialogs, tmp_path):
    page = _two(window, tmp_path)
    page._moved([(1, 1)], (0, 0), True)         # B2 after A1
    assert page.strip.keys() == [(0, 0), (1, 1), (0, 1), (0, 2), (1, 0)]
    assert page.ranges() == ["", "2, 1"]          # the field follows the strip
    assert page.headings() == ["a.pdf · page 1", "b.pdf · page 2",
                               "a.pdf · pages 2-3", "b.pdf · page 1"]
    out = tmp_path / "merged.pdf"
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert _texts(out) == ["A1", "B2", "A2", "A3", "B1"]
    with fitz.open(out) as d:
        assert [e[1] for e in d.get_toc() if e[0] == 1] == ["a.pdf", "b.pdf", "a.pdf", "b.pdf"]


def test_up_and_down_gather_a_file_again(window, tmp_path):
    page = _two(window, tmp_path)
    page._moved([(1, 1)], (0, 0), True)
    page.select(1)
    page.move(-1)                                # b.pdf first: its pages together
    assert page.strip.keys() == [(1, 1), (1, 0), (0, 0), (0, 1), (0, 2)]


def test_removing_a_file_takes_its_pages_off_the_strip(window, tmp_path):
    page = _two(window, tmp_path)
    doc = page._docs[0]
    page.select(0)
    page.remove_selected()
    assert page.strip.keys() == [(1, 0), (1, 1)] and doc.is_closed


def test_every_page_left_out_is_refused(window, dialogs, tmp_path):
    page = _two(window, tmp_path)
    page.strip.select_keys(page.strip.keys())
    page.leave_out()
    page.run()
    assert dialogs.msgs[-1] == ("warning", "Merge", "Every page is left out: put back at least one.")
