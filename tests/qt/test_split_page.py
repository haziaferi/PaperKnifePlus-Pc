"""The Qt Split page: page ranges into separate files."""
import pymupdf as fitz
import pytest

from qt_harness import make_pdf, pump, spy_open, wait_job


def _page(window):
    assert window.open_tool("SplitTool")
    pump(0.05)
    return window.current_page()


def _texts(path):
    with fitz.open(path) as d:
        return [p.get_text().strip() for p in d]


def _split(window, dialogs, page, src, ranges, out_dir):
    page.file.set_path(src)
    page.ranges.setText(ranges)
    dialogs.dirs.append(str(out_dir))
    page.run()
    wait_job(window)


def test_the_page_builds_with_its_controls(window):
    page = _page(window)
    assert type(page).__name__ == "SplitPage"
    assert page.title_label.text() == "Split"
    assert page.ranges.text() == "" and page.file.path() == ""


def test_without_a_file_it_asks_for_one(window, dialogs):
    page = _page(window)
    page.run()
    assert dialogs.msgs[-1] == ("warning", "Split", "Select a PDF first.")


def test_blank_ranges_write_every_page_to_its_own_file(window, dialogs, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    out = tmp_path / "out"
    out.mkdir()
    _split(window, dialogs, page, src, "", out)
    assert sorted(p.name for p in out.iterdir()) == [
        "in_part01_p1-1.pdf", "in_part02_p2-2.pdf", "in_part03_p3-3.pdf"]
    assert _texts(out / "in_part02_p2-2.pdf") == ["Page 2"]
    assert dialogs.msgs[-1] == ("info", "Done", f"Created 3 file(s) in:\n{out}")
    assert window.status_text() == f"✓  Split into 3 file(s) → {out}"


def test_split_writes_the_pages_it_names(window, dialogs, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf", pages=5)
    out = tmp_path / "out"
    out.mkdir()
    _split(window, dialogs, page, src, "2-3, end", out)
    assert not dialogs.errors(), dialogs.errors()
    assert _texts(out / "in_part01_p2-3.pdf") == ["Page 2", "Page 3"]
    assert _texts(out / "in_part02_p5-5.pdf") == ["Page 5"]
    assert len(list(out.iterdir())) == 2


@pytest.mark.parametrize("ranges,bad", [("99, 7-9", "page 99 does not exist"),
                                        ("5, 7-9", "page 7 does not exist")])
def test_split_rejects_pages_past_the_end(window, dialogs, tmp_path, monkeypatch, ranges, bad):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf", pages=5)
    out = tmp_path / "out"
    out.mkdir()
    dialogs.dirs.append(str(out))   # offered, so a split that ran anyway would land here
    opened = spy_open(window, monkeypatch)
    page.file.set_path(src)
    page.ranges.setText(ranges)
    page.run()
    assert window._current_job is None             # refused before any job started
    wait_job(window)
    assert list(out.iterdir()) == []
    assert dialogs.dirs == [str(out)]              # refused before the folder dialog
    assert dialogs.errors() and dialogs.errors()[-1][1] == "Split"
    assert bad in dialogs.errors()[-1][2]
    assert opened and opened[0].is_closed


def test_a_dropped_pdf_fills_the_file_card_and_others_are_refused(window, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf")
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    assert page.accept_drop(src) is True and page.file.path() == src


def test_cancelling_the_folder_dialog_closes_the_document(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    opened = spy_open(window, monkeypatch)
    page.run()                     # no folder queued: the dialog returns ""
    assert opened and opened[0].is_closed
    assert window._current_job is None


def test_leaving_the_tool_leaves_no_document_open(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    out = tmp_path / "out"
    out.mkdir()
    opened = spy_open(window, monkeypatch)
    page.file.set_path(make_pdf(tmp_path / "in.pdf", pages=4))
    dialogs.dirs.append(str(out))
    page.run()
    window.show_page("CompressTool")      # leave while the job may still run
    wait_job(window)
    assert opened and opened[0].is_closed
    assert len(list(out.iterdir())) == 4
