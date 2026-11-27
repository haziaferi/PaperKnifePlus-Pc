"""The Qt Compress page: the single-file transform pilot."""
import pymupdf as fitz
import pytest

from qt_harness import image_pdf, make_pdf, pump, save_as, spy_open, wait_job


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
    page.run()
    wait_job(window)
    status = window.status_text()
    save_as(window, dialogs, out)
    # (a result no smaller leaves the document unchanged and nothing to save)
    d = fitz.open(out) if out.exists() else window.document.doc
    assert len(d) == 1
    assert [img[2] for img in d[0].get_images(full=True)] == [width]
    assert "Searchable text 1" in d[0].get_text()
    if level == "light":                # may be no smaller: then a warning, nothing changed
        assert window.document.dirty == status.startswith("✓")
    else:
        assert status.endswith("· Save writes it to the file") and window.document.path == str(out)
        assert out.stat().st_size < (tmp_path / "big.pdf").stat().st_size
        assert not [m for m in dialogs.msgs if m[0] == "info"]


def test_no_reduction_is_reported_as_a_warning(window, dialogs, tmp_path):
    from paperknife.qt.tools.compress import size_report
    role, status, box, take = size_report(1000, 1200)
    assert role == "warning" and "No size reduction" in status and box and not take
    role, status, box, take = size_report(10240, 5120)
    assert role == "success" and "(−50%)" in status and box is None and take


def test_compress_asks_no_file_name_and_closes_its_copy(window, dialogs, tmp_path,
                                                         monkeypatch):
    # Applied in place (owner's sort, 2026-10-23): no save dialog (the harness
    # would hand it nothing), and the job's own copy is closed when it ends.
    page = _page(window)
    page.file.set_path(image_pdf(tmp_path / "big.pdf"))
    opened = spy_open(window, monkeypatch)
    page.radios["aggressive"].setChecked(True)
    page.run()
    wait_job(window)
    assert window.document.dirty and window.document.undo_label() == "Compress"
    assert all(d.is_closed for d in opened)


def test_no_size_gain_is_reported_in_a_warning_box(window, dialogs, tmp_path, monkeypatch):
    # The result is no smaller: the box matches its ⚠ status line (owner's
    # choice, 2026-10-09), and the document is left as it was (2026-10-23).
    import shutil
    from paperknife.qt.tools import compress as page_mod
    monkeypatch.setattr(page_mod.core_enhance, "compress_pdf",
                        lambda doc, out, level: (doc.close(), shutil.copyfile(src, out)))
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf")
    assert page.accept_drop(src)
    page.run()
    wait_job(window)
    assert dialogs.msgs[-1][:2] == ("warning", "Compress")
    assert "it is left as it was" in dialogs.msgs[-1][2]
    assert "No size reduction" in window.status_text()
    assert not window.document.dirty and not window.document.can_undo()   # unchanged
