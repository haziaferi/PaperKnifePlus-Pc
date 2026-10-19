"""Documents into Other → PDF (owner, 2026-10-18: Doc / Text → PDF merged into
Image → PDF's list).  The conversions Doc / Text → PDF was tested for, now
through the list, plus documents and images together in list order."""
import threading

import pymupdf as fitz
import pytest
from PIL import Image

from qt_harness import make_pdf, pump, wait_job

_PAGE_CAP = 40


@pytest.fixture
def capped_writer(monkeypatch):
    """Story loops that never end would fill the disk; stop them at a cap.
    A test that sets stats["hold"] to an Event holds the worker inside its first
    begin_page (stats["first_page"] is set then) until the test sets it."""
    real = fitz.DocumentWriter
    stats = {"pages": 0, "hold": None, "first_page": threading.Event()}

    class Capped:
        def __init__(self, path, *a, **k):
            self._w = real(path, *a, **k)

        def begin_page(self, rect):
            stats["pages"] += 1
            if stats["pages"] == 1 and stats["hold"] is not None:
                stats["first_page"].set()
                assert stats["hold"].wait(30), "the test never released the worker"
            if stats["pages"] > _PAGE_CAP:
                raise RuntimeError(f"runaway Story loop: more than {_PAGE_CAP} pages")
            return self._w.begin_page(rect)

        def end_page(self):
            self._w.end_page()

        def close(self):
            self._w.close()

    monkeypatch.setattr(fitz, "DocumentWriter", Capped)
    return stats


def _page(window):
    assert window.open_tool("Img2PdfTool")
    pump(0.05)
    return window.current_page()


def _convert(window, dialogs, page, srcs, out, errors_ok=False):
    page.add_paths([str(s) for s in srcs])
    dialogs.save(out)
    page.run()
    wait_job(window, timeout=60)
    if not errors_ok:
        assert not dialogs.errors(), dialogs.errors()


def _parts(folder):
    return list(folder.glob("*.part"))


def test_the_merged_screen_is_named_to_match(window):
    page = _page(window)
    assert page.title_label.text() == "Other → PDF"
    assert window._labels["Img2PdfTool"] == "Other → PDF"
    assert "Doc2PdfTool" not in window._labels and "Pdf2ImgTool" not in window._labels


@pytest.mark.parametrize("name", ["a.txt", "a.HTML", "a.htm", "a.xml", "a.rtf", "a.docx",
                                  "a.pptx", "a.xlsx", "a.png", "a.jpg", "a.jpeg"])
def test_each_document_and_image_extension_is_taken(window, tmp_path, name):
    page = _page(window)
    f = tmp_path / name
    f.write_bytes(b"x")
    assert page.accept_drop(str(f)) is True and page.paths() == [str(f)]


def test_files_it_does_not_convert_are_refused(window, tmp_path):
    page = _page(window)
    for name in ("a.pdf", "a.doc", "noext"):
        f = tmp_path / name
        f.write_bytes(b"x")
        assert page.accept_drop(str(f)) is False
    assert page.paths() == []
    assert page.accept_drop(str(tmp_path / "missing.txt")) is False


def test_a_missing_library_is_named(window, dialogs, tmp_path, monkeypatch):
    from paperknife.core import convert as core_convert
    monkeypatch.setitem(core_convert.NEEDS, "XLSX", ("openpyxl", False))
    page = _page(window)
    src = tmp_path / "a.xlsx"
    src.write_bytes(b"x")
    out = tmp_path / "a.pdf"
    _convert(window, dialogs, page, [src], out, errors_ok=True)
    assert "openpyxl not installed" in dialogs.errors()[0][2]
    assert not out.exists()


def test_documents_and_images_go_in_list_order(window, dialogs, tmp_path):
    page = _page(window)
    txt = tmp_path / "a.txt"
    txt.write_text("text page", encoding="utf-8")
    img = tmp_path / "b.png"
    Image.new("RGB", (300, 200), (0, 128, 255)).save(img)
    out = tmp_path / "mix.pdf"
    _convert(window, dialogs, page, [img, txt], out)
    with fitz.open(out) as doc:
        assert len(doc) == 2
        assert (doc[0].rect.width, doc[0].rect.height) == (300, 200) and doc[0].get_images()
        assert "text page" in doc[1].get_text()
    assert window.status_text() == "✓  Converted 2 file(s) → mix.pdf"
    assert page.paths() == []                       # a finished job empties the list


def test_txt_to_pdf_short_text_finishes_on_one_page(window, dialogs, tmp_path, capped_writer):
    page = _page(window)
    src = tmp_path / "short.txt"
    src.write_text("one\ntwo\nthree\n", encoding="utf-8")
    out = tmp_path / "short.pdf"
    _convert(window, dialogs, page, [src], out)
    assert capped_writer["pages"] <= _PAGE_CAP, "Story loop did not stop"
    with fitz.open(out) as doc:
        assert len(doc) == 1
        assert "three" in doc[0].get_text()
    assert window.status_text() == "✓  Converted 1 file(s) → short.pdf"
    assert window.status_role == "success"
    assert dialogs.msgs[-1] == ("info", "Done", f"PDF saved:\n{out}")


def test_txt_to_pdf_long_text_wraps_and_spans_pages(window, dialogs, tmp_path, capped_writer):
    page = _page(window)
    long_line = " ".join(f"w{i:03d}" for i in range(80))
    body = "\n".join(f"line {i}" for i in range(150))
    src = tmp_path / "long.txt"
    src.write_text(long_line + "\n" + body, encoding="utf-8")
    out = tmp_path / "long.pdf"
    _convert(window, dialogs, page, [src], out)
    with fitz.open(out) as doc:
        assert 1 < len(doc) < 10
        text = "".join(p.get_text() for p in doc)
        assert "w079" in text, "the end of a long line was cut off"
        assert "line 149" in text
        assert all(w[2] <= doc[0].rect.width - 20 for w in doc[0].get_text("words"))


def test_txt_to_pdf_cancel_stops_the_story_loop(window, dialogs, tmp_path, capped_writer):
    page = _page(window)
    src = tmp_path / "huge.txt"
    src.write_text("\n".join(f"line {i}" for i in range(20_000)), encoding="utf-8")
    out = tmp_path / "huge.pdf"
    page.add_paths([str(src)])
    dialogs.save(out)
    capped_writer["hold"] = threading.Event()
    page.run()
    assert window._current_job is not None and window._current_job.is_running
    # Deterministic: the worker waits inside its first page until Cancel is sent
    # (parsing the 20 000 lines comes first, so no fixed delay could be enough).
    assert capped_writer["first_page"].wait(30)
    window._cancel_job()
    capped_writer["hold"].set()
    wait_job(window, timeout=60)
    assert capped_writer["pages"] == 1, capped_writer   # the loop stopped after that page
    assert not dialogs.errors(), dialogs.errors()
    assert not out.exists(), "a cancelled conversion left a partial PDF"
    assert window.status_text() == "⚠  Cancelled"


def test_html_to_pdf_resolves_relative_images(window, dialogs, tmp_path, capped_writer):
    page = _page(window)
    Image.new("RGB", (40, 40), (255, 0, 0)).save(tmp_path / "red.png")
    src = tmp_path / "page.html"
    src.write_text('<p>hi</p><img src="red.png">', encoding="utf-8")
    out = tmp_path / "page.pdf"
    _convert(window, dialogs, page, [src], out)
    with fitz.open(out) as doc:
        assert "hi" in doc[0].get_text()
        assert doc[0].get_images()


def test_an_unsplittable_html_row_is_an_error_and_leaves_no_file(window, dialogs, tmp_path):
    page = _page(window)
    src = tmp_path / "row.html"
    src.write_text("<table><tr><td>" + "line<br>" * 400 + "</td></tr></table>",
                   encoding="utf-8")
    out = tmp_path / "row.pdf"
    _convert(window, dialogs, page, [src], out, errors_ok=True)
    errors = dialogs.errors()
    assert errors and "taller than a page" in errors[0][2], errors
    assert not out.exists() and _parts(tmp_path) == []


def test_docx_to_pdf_keeps_document_order(window, dialogs, tmp_path, capped_writer):
    import docx
    page = _page(window)
    src = tmp_path / "d.docx"
    w = docx.Document()
    w.add_heading("Heading One", level=1)
    w.add_paragraph("before table")
    w.add_table(rows=1, cols=2).rows[0].cells[0].text = "cellA"
    w.add_paragraph("after table")
    w.save(src)
    out = tmp_path / "d.pdf"
    _convert(window, dialogs, page, [src], out)
    with fitz.open(out) as doc:
        text = doc[0].get_text()
    assert text.index("before table") < text.index("cellA") < text.index("after table"), text


def test_xlsx_to_pdf_keeps_zero_cells(window, dialogs, tmp_path, capped_writer):
    import openpyxl
    page = _page(window)
    src = tmp_path / "zeros.xlsx"
    wb = openpyxl.Workbook()
    wb.active.append([0, 0.0, "x"])         # openpyxl reads 0.0 back as 0
    wb.save(src)
    out = tmp_path / "zeros.pdf"
    _convert(window, dialogs, page, [src], out)
    with fitz.open(out) as doc:
        assert len(doc) == 1
        assert doc[0].rect.width > doc[0].rect.height            # A4 landscape
        words = [w[4] for w in doc[0].get_text("words")]
    assert words[:3] == ["0", "0", "x"], words


def test_pptx_to_pdf_puts_each_slide_on_a_page(window, dialogs, tmp_path):
    from pptx import Presentation
    from pptx.util import Inches
    page = _page(window)
    prs = Presentation()
    for title in ("First slide", "Second slide"):
        s = prs.slides.add_slide(prs.slide_layouts[5])
        s.shapes.title.text = title
        s.shapes.add_textbox(Inches(1), Inches(2), Inches(4), Inches(1)).text_frame.text = "body"
    src = tmp_path / "s.pptx"
    prs.save(src)
    out = tmp_path / "s.pdf"
    _convert(window, dialogs, page, [src], out)
    with fitz.open(out) as doc:
        assert len(doc) == 2
        assert "Second slide" in doc[1].get_text() and "body" in doc[1].get_text()


def test_rtf_to_pdf_typesets_the_text_not_the_markup(window, dialogs, tmp_path):
    page = _page(window)
    src = tmp_path / "a.rtf"
    src.write_text(r"{\rtf1\ansi{\fonttbl\f0\fswiss Helvetica;}\f0 Hello \b RTF\b0 world\par}",
                   encoding="latin-1")
    out = tmp_path / "a.pdf"
    _convert(window, dialogs, page, [src], out)
    with fitz.open(out) as doc:
        text = doc[0].get_text()
    assert "Hello" in text and "world" in text and "rtf1" not in text


def test_unparsable_xml_conversion_says_it_fell_back(window, dialogs, tmp_path):
    page = _page(window)
    src = tmp_path / "bad.xml"
    src.write_text("<a><b>unclosed</a>", encoding="utf-8")
    out = tmp_path / "bad.pdf"
    _convert(window, dialogs, page, [src], out)
    assert out.exists()
    assert window.status_role == "warning"
    kind, title, msg = dialogs.msgs[-1]
    assert (kind, title) == ("info", "Done") and "could not be parsed" in msg
    assert msg.startswith(f"PDF saved:\n{out}\n\nbad.xml: ")


def test_well_formed_xml_typesets_its_text(window, dialogs, tmp_path):
    page = _page(window)
    src = tmp_path / "ok.xml"
    src.write_text("<a><b>inner words</b></a>", encoding="utf-8")
    out = tmp_path / "ok.pdf"
    _convert(window, dialogs, page, [src], out)
    with fitz.open(out) as doc:
        text = doc[0].get_text()
    assert "inner words" in text and "<b>" not in text


def test_cancelling_the_save_dialog_writes_nothing(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    src = tmp_path / "a.txt"
    src.write_text("hello", encoding="utf-8")
    page.add_paths([str(src)])
    opened = []
    monkeypatch.setattr(window, "open_pdf_safe", lambda p: opened.append(p))
    page.run()                     # no save path queued: the dialog returns ""
    assert window._current_job is None and not opened
    assert list(tmp_path.iterdir()) == [src]


def test_leaving_the_tool_after_a_conversion(window, dialogs, tmp_path):
    page = _page(window)
    out = tmp_path / "o.pdf"
    src = tmp_path / "a.txt"
    src.write_text("hello", encoding="utf-8")
    _convert(window, dialogs, page, [src], out)
    assert window.show_page("home")
    out.unlink()                   # nothing still holds the output open


def test_a_pdf_is_not_its_input(window, tmp_path):
    page = _page(window)
    assert page.accept_drop(make_pdf(tmp_path / "in.pdf")) is False


def test_cancel_after_the_pdf_is_written_still_says_done(window, dialogs, tmp_path,
                                                         monkeypatch):
    # The output already replaced *out* when Cancel landed; "Cancelled" with no
    # Done message would hide that the file was written.
    import contextlib
    from paperknife.core import convert as core_convert
    page = _page(window)
    src = tmp_path / "a.png"
    Image.new("RGB", (60, 40), "red").save(src)
    out = tmp_path / "a.pdf"
    real = core_convert.atomic_output

    @contextlib.contextmanager
    def cancel_after_commit(path):
        with real(path) as tmp:
            yield tmp
        if str(path) == str(out):
            window._current_job.cancel()
    monkeypatch.setattr(core_convert, "atomic_output", cancel_after_commit)
    _convert(window, dialogs, page, [src], out)
    assert out.exists()
    assert dialogs.msgs[-1] == ("info", "Done", f"PDF saved:\n{out}")
    assert window.status_text() == "✓  Converted 1 file(s) → a.pdf"
