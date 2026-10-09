"""The Qt Compress page: the single-file transform pilot."""
import pymupdf as fitz
import pytest

from qt_harness import image_pdf, make_pdf, pump, spy_open, wait_job


def _page(window):
    assert window.open_tool("CompressTool")
    pump(0.05)
    return window.current_page()


def test_without_a_file_it_asks_for_one(window, dialogs):
    page = _page(window)
    page.run()
    assert dialogs.msgs == [("warning", "Compress", "Select a PDF first.")]
    assert window._current_job is None


def test_a_dropped_pdf_fills_the_file_card_and_others_are_refused(window, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf")
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    assert page.accept_drop(src) is True and page.file.path() == src


# The image widths each level leaves (as in tests/test_core_enhance.py): the
# checked radio, not some fixed level, must reach the worker.
@pytest.mark.parametrize("level,width", [("light", 1500), ("medium", 625), ("aggressive", 400)])
def test_each_level_writes_a_smaller_file_and_reports_it(window, dialogs, tmp_path, level, width):
    page = _page(window)
    src = image_pdf(tmp_path / "big.pdf")
    page.file.set_path(src)
    page.radios[level].setChecked(True)
    assert page.level == level
    out = tmp_path / f"out-{level}.pdf"
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert out.exists()
    with fitz.open(out) as d:
        assert len(d) == 1
        assert [img[2] for img in d[0].get_images(full=True)] == [width]
        assert "Searchable text 1" in d[0].get_text()
    kind = dialogs.msgs[-1][0]
    if level == "light":
        assert kind in ("info", "warning")
    else:
        assert kind == "info" and out.stat().st_size < (tmp_path / "big.pdf").stat().st_size


def test_no_reduction_is_reported_as_a_warning(window, dialogs, tmp_path):
    from paperknife.qt.tools.compress import size_report
    role, status, title, _ = size_report(1000, 1200, str(tmp_path / "o.pdf"))
    assert role == "warning" and "No size reduction" in status and title == "Compress"
    role, status, *_ = size_report(10240, 5120, str(tmp_path / "o.pdf"))
    assert role == "success" and "(−50%)" in status


def test_cancelling_the_save_dialog_closes_the_document(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    opened = spy_open(window, monkeypatch)
    page.run()                     # no save path queued: the dialog returns ""
    assert opened and opened[0].is_closed
