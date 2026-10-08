"""The Qt Merge page: a collection of PDFs, each with its own page range."""
import pymupdf as fitz

from qt_harness import make_pdf, pump, wait_job


def _page(window):
    assert window.open_tool("MergeTool")
    pump(0.05)
    return window.current_page()


def _texts(path):
    with fitz.open(path) as d:
        return [p.get_text().strip() for p in d]


def _spy_opens(window):
    opened = []
    real = window.open_pdf_safe

    def spy(path):
        doc = real(path)
        opened.append(doc)
        return doc
    window.open_pdf_safe = spy
    return opened


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


def test_merge_uses_each_files_range(window, dialogs, tmp_path):
    a = make_pdf(tmp_path / "a.pdf", pages=5, text="A{n}")
    b = make_pdf(tmp_path / "b.pdf", pages=2, text="B{n}")
    page = _page(window)
    page.add_paths([a, b])
    page.rows[0].extra.setText("4-end, 1")
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


def test_a_reversed_range_is_reported_instead_of_dropped(window, dialogs, tmp_path):
    a = make_pdf(tmp_path / "a.pdf", pages=5, text="A{n}")
    b = make_pdf(tmp_path / "b.pdf", pages=2, text="B{n}")
    page = _page(window)
    page.add_paths([a, b])
    page.rows[0].extra.setText("5-3")
    out = tmp_path / "merged.pdf"
    dialogs.save(out)
    opened = _spy_opens(window)
    page.run()
    wait_job(window)
    assert not out.exists(), f"merged without file a: {_texts(out)}"
    assert any(m[1] == "Merge" and "a.pdf" in m[2] for m in dialogs.errors()), dialogs.msgs
    assert opened and all(d.is_closed for d in opened)


def test_a_dropped_pdf_is_added_and_others_are_refused(window, tmp_path):
    page = _page(window)
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    assert page.paths() == []
    src = make_pdf(tmp_path / "in.pdf")
    assert page.accept_drop(src) is True
    assert page.paths() == [src]


def test_cancelling_the_save_dialog_closes_every_input(window, dialogs, tmp_path):
    page = _page(window)
    page.add_paths([make_pdf(tmp_path / "a.pdf"), make_pdf(tmp_path / "b.pdf")])
    opened = _spy_opens(window)
    page.run()                     # no save path queued: the dialog returns ""
    assert len(opened) == 2 and all(d.is_closed for d in opened)
    assert not dialogs.errors()


def test_leaving_the_tool_leaves_no_document_open(window, dialogs, tmp_path):
    page = _page(window)
    page.add_paths([make_pdf(tmp_path / "a.pdf")])
    opened = _spy_opens(window)
    out = tmp_path / "merged.pdf"
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert window.show_page("home")
    pump(0.02)
    assert opened and all(d.is_closed for d in opened)
    assert out.exists()
