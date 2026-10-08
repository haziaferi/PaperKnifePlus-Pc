"""The Qt Normalise Pages page: a single-file transform."""
import pymupdf as fitz
import pytest

from qt_harness import make_pdf, pump, wait_job


def _page(window):
    assert window.open_tool("NormaliseTool")
    pump(0.05)
    return window.current_page()


def _spy_open(window):
    opened = []
    real = window.open_pdf_safe

    def spy(path):
        doc = real(path)
        opened.append(doc)
        return doc
    window.open_pdf_safe = spy
    return opened


def _src(path, sizes=((300, 400),), red=False):
    doc = fitz.open()
    for w, h in sizes:
        p = doc.new_page(width=w, height=h)
        if red:
            p.draw_rect(p.rect, color=(1, 0, 0), fill=(1, 0, 0))
    doc.save(path)
    doc.close()
    return str(path)


def _run(window, dialogs, page, src, out):
    page.file.set_path(src)
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()


def _sizes(path):
    with fitz.open(path) as d:
        return [(round(p.rect.width), round(p.rect.height)) for p in d]


def test_the_page_builds_with_the_ctk_defaults(window):
    page = _page(window)
    assert page.title_label.text() == "Normalise Pages"
    assert [page.size.itemText(i) for i in range(page.size.count())] == \
        ["A4", "A3", "A5", "Letter", "Legal", "Tabloid"]
    assert page.size.currentText() == "A4"
    assert page.orient == "Portrait" and page.stretch is False


def test_without_a_file_it_warns(window, dialogs):
    page = _page(window)
    page.run()
    assert dialogs.msgs[-1] == ("warning", "Normalise", "Select a PDF first.")
    assert not window._current_job


def test_normalise_end_to_end_resizes_every_page_and_reports(window, dialogs, tmp_path):
    page = _page(window)
    out = tmp_path / "out.pdf"
    _run(window, dialogs, page, make_pdf(tmp_path / "in.pdf", pages=2), out)
    assert _sizes(out) == [(595, 842), (595, 842)]
    with fitz.open(out) as d:
        assert "Page 1" in d[0].get_text() and "Page 2" in d[1].get_text()
    assert dialogs.msgs[-1] == ("info", "Done", f"Normalised PDF saved:\n{out}")
    assert window.status_text() == "✓  Normalised → out.pdf"


@pytest.mark.parametrize("size,expect", [("A4", (595, 842)), ("A3", (842, 1191)),
                                         ("A5", (420, 595)), ("Letter", (612, 792)),
                                         ("Legal", (612, 1008)), ("Tabloid", (792, 1224))])
def test_each_target_size(window, dialogs, tmp_path, size, expect):
    page = _page(window)
    page.size.setCurrentText(size)
    out = tmp_path / f"{size}.pdf"
    _run(window, dialogs, page, _src(tmp_path / "in.pdf"), out)
    assert _sizes(out) == [expect]


@pytest.mark.parametrize("orient,expect", [("Portrait", [(595, 842), (595, 842)]),
                                           ("Landscape", [(842, 595), (842, 595)]),
                                           ("Keep original", [(595, 842), (842, 595)])])
def test_each_orientation(window, dialogs, tmp_path, orient, expect):
    page = _page(window)
    page.orients[orient].setChecked(True)
    assert page.orient == orient
    out = tmp_path / "out.pdf"
    _run(window, dialogs, page, _src(tmp_path / "in.pdf", ((300, 400), (400, 300))), out)
    assert _sizes(out) == expect


def test_stretch_fills_the_page_and_fit_keeps_the_ratio(window, dialogs, tmp_path):
    src = _src(tmp_path / "in.pdf", ((200, 800),), red=True)
    page = _page(window)
    page.scales["stretch"].setChecked(True)
    assert page.stretch is True
    _run(window, dialogs, page, src, tmp_path / "stretch.pdf")
    page.scales["fit"].setChecked(True)
    _run(window, dialogs, page, src, tmp_path / "fit.pdf")
    with fitz.open(tmp_path / "stretch.pdf") as d:
        pix = d[0].get_pixmap(dpi=36)
    assert pix.pixel(2, pix.height // 2) == (255, 0, 0)
    with fitz.open(tmp_path / "fit.pdf") as d:
        pix = d[0].get_pixmap(dpi=36)
    assert pix.pixel(2, pix.height // 2) == (255, 255, 255)        # letterboxed
    assert pix.pixel(pix.width // 2, pix.height // 2) == (255, 0, 0)


def test_a_dropped_pdf_is_taken_and_others_are_refused(window, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf")
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False and page.file.path() == ""
    assert page.accept_drop(src) is True and page.file.path() == src


def test_cancelling_the_save_dialog_closes_the_document(window, dialogs, tmp_path):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    opened = _spy_open(window)
    page.run()
    assert opened and opened[0].is_closed
    assert not window._current_job


def test_leaving_the_tool_leaves_no_document_open(window, dialogs, tmp_path):
    page = _page(window)
    opened = _spy_open(window)
    _run(window, dialogs, page, make_pdf(tmp_path / "in.pdf"), tmp_path / "o.pdf")
    assert window.show_page("home")
    assert opened and all(d.is_closed for d in opened)
