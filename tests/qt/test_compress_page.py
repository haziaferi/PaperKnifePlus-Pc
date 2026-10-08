"""The Qt Compress page: the single-file transform pilot."""
import io

import pymupdf as fitz
import pytest

from qt_harness import make_pdf, pump, wait_job


def _pdf_with_big_image(path):
    from PIL import Image
    d = fitz.open()
    pg = d.new_page()
    buf = io.BytesIO()
    Image.effect_noise((1600, 1600), 60).convert("RGB").save(buf, "PNG")
    pg.insert_image(pg.rect, stream=buf.getvalue())
    d.save(path)
    return str(path)


def _page(window):
    assert window.open_tool("CompressTool")
    pump(0.05)
    return window.current_page()


def test_without_a_file_it_asks_for_one(window, dialogs):
    page = _page(window)
    page.run()
    assert dialogs.msgs and dialogs.msgs[-1][0] == "warning"


def test_a_dropped_pdf_fills_the_file_card_and_others_are_refused(window, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf")
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    assert page.accept_drop(src) is True and page.file.path() == src


@pytest.mark.parametrize("level", ["light", "medium", "aggressive"])
def test_each_level_writes_a_smaller_file_and_reports_it(window, dialogs, tmp_path, level):
    page = _page(window)
    src = _pdf_with_big_image(tmp_path / "big.pdf")
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


def test_cancelling_the_save_dialog_closes_the_document(window, dialogs, tmp_path):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    opened = []
    real = window.open_pdf_safe

    def spy(path):
        doc = real(path)
        opened.append(doc)
        return doc
    window.open_pdf_safe = spy
    page.run()                     # no save path queued: the dialog returns ""
    assert opened and opened[0].is_closed
