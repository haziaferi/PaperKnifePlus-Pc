"""The Qt PDF → Other page (PDF → Doc / Text, with PDF → Images folded in:
owner, 2026-10-18)."""
import io
import zipfile

import pymupdf as fitz
import pytest
from PIL import Image

from qt_harness import make_pdf, pump, spy_open, wait_job


def _page(window):
    assert window.open_tool("Pdf2DocTool")
    pump(0.05)
    return window.current_page()


def _convert(window, dialogs, page, fmt, src, out):
    page.fmt.setCurrentText(fmt)
    assert page.format == fmt
    page.file.set_path(str(src))
    dialogs.save(out)
    page.run()
    wait_job(window, timeout=60)
    assert not dialogs.errors(), dialogs.errors()


def _unicode_pdf(path, lines):
    doc = fitz.open()
    page = doc.new_page()
    tw = fitz.TextWriter(page.rect)
    for i, line in enumerate(lines):
        tw.append((72, 100 + 20 * i), line, font=fitz.Font("helv"), fontsize=12)
    tw.write_text(page)
    doc.save(str(path))
    doc.close()
    return path


def test_the_page_builds_and_each_format_shows_its_options(window):
    page = _page(window)
    assert type(page).__name__ == "Pdf2DocPage"
    assert page.format == "TXT"
    assert [page.fmt.itemText(i) for i in range(page.fmt.count())] == \
        ["TXT", "HTML", "XML", "RTF", "DOCX", "PPTX", "XLSX", "PNG", "JPEG"]
    from paperknife.qt.tools.pdf2doc import INFO
    for fmt in INFO:
        page.fmt.setCurrentText(fmt)
        assert page.fmt_info.info_text == INFO[fmt]
        assert page.image_card.isVisibleTo(page) == (fmt in ("PNG", "JPEG", "PPTX"))
        assert page.quality_row.isVisibleTo(page) == (fmt == "JPEG")
        assert not page.missing.isVisibleTo(page)        # every library is installed here
    assert page.dpi_box.text() == f"{page.dpi_box.value()} DPI"
    assert page.quality_box.value() == 92 and page.quality_box.text() == "92%"


def test_a_missing_library_is_named(window, monkeypatch):
    from paperknife.core import convert as core_convert
    monkeypatch.setitem(core_convert.NEEDS, "DOCX", ("python-docx", False))
    page = _page(window)
    page.fmt.setCurrentText("DOCX")
    assert page.missing.isVisibleTo(page)
    assert page.missing.text() == ("⚠  'python-docx' is not installed.\n"
                                   "Install it:  pip install python-docx")
    page.fmt.setCurrentText("TXT")
    assert not page.missing.isVisibleTo(page)


def test_without_a_file_it_asks_for_one(window, dialogs):
    page = _page(window)
    page.run()
    assert dialogs.msgs == [("warning", "Convert", "Select a PDF first.")]


def test_txt_end_to_end_writes_the_text_and_reports_it(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    opened = spy_open(window, monkeypatch)
    out = tmp_path / "out.txt"
    _convert(window, dialogs, page, "TXT", make_pdf(tmp_path / "in.pdf", pages=2), out)
    text = out.read_text(encoding="utf-8")
    assert "Page 1" in text and "Page 2" in text and "── Page Break ──" in text
    assert opened and opened[-1].is_closed  # the job's copy (the page holds its own)
    assert window.status_text() == "✓  PDF → TXT: out.txt"
    assert window.status_role == "success"
    assert dialogs.msgs[-1] == ("info", "Done", f"Saved:\n{out}")


def test_the_save_dialog_offers_the_format_default(window, dialogs, tmp_path, monkeypatch):
    from paperknife.qt import dialogs as dmod
    seen = []
    monkeypatch.setattr(dmod, "ask_save", lambda *a, **k: seen.append(a) or "")
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf", pages=1))
    for fmt in ("DOCX", "JPEG"):
        page.fmt.setCurrentText(fmt)
        page.run()
    assert seen == [("output.docx", ".docx", [("Word Document", "*.docx"), ("All", "*.*")]),
                    ("pages_jpeg.zip", ".zip", [("ZIP of JPEGs", "*.zip"), ("All", "*.*")])]


def test_html_holds_each_page(window, dialogs, tmp_path):
    page = _page(window)
    out = tmp_path / "o.html"
    _convert(window, dialogs, page, "HTML", make_pdf(tmp_path / "in.pdf", pages=2), out)
    html = out.read_text(encoding="utf-8")
    assert 'id="page-1"' in html and 'id="page-2"' in html and "Page 2" in html


def test_pdf_to_rtf_keeps_non_latin1_characters(window, dialogs, tmp_path):
    page = _page(window)
    src = _unicode_pdf(tmp_path / "u.pdf", ["cost €5 café", "Ελληνικά"])
    out = tmp_path / "u.rtf"
    _convert(window, dialogs, page, "RTF", src, out)
    data = out.read_bytes()
    assert all(b < 128 for b in data), "RTF must be 7-bit with \\uN escapes"
    assert b"\\u8364?" in data          # €
    assert b"\\u233?" in data           # é
    assert b"\\u917?" in data           # Ε


def test_pdf_to_xlsx_does_not_create_formulas(window, dialogs, tmp_path):
    import openpyxl
    page = _page(window)
    out = tmp_path / "f.xlsx"
    _convert(window, dialogs, page, "XLSX", make_pdf(tmp_path / "f.pdf", pages=1, text="=1+1"),
             out)
    cell = openpyxl.load_workbook(out)["Page 1"]["A1"]
    assert cell.value == "=1+1"
    assert cell.data_type == "s"


def test_pdf_to_docx_survives_control_characters(window, dialogs, tmp_path, monkeypatch):
    import docx
    real = fitz.Page.get_text

    def get_text(self, opt="text", *a, **k):
        res = real(self, opt, *a, **k)
        if opt == "dict":
            for b in res["blocks"]:
                for line in b.get("lines", []):
                    for span in line["spans"]:
                        span["text"] = span["text"].replace("P", "\x0bP")
        return res

    monkeypatch.setattr(fitz.Page, "get_text", get_text)
    page = _page(window)
    out = tmp_path / "c.docx"
    _convert(window, dialogs, page, "DOCX", make_pdf(tmp_path / "c.pdf", pages=1), out)
    assert any("Page 1" in p.text for p in docx.Document(str(out)).paragraphs)


def test_pdf_to_xml_is_well_formed_without_nested_pages(window, dialogs, tmp_path):
    import xml.etree.ElementTree as ET
    page = _page(window)
    out = tmp_path / "x.xml"
    _convert(window, dialogs, page, "XML", make_pdf(tmp_path / "x.pdf", pages=2), out)
    root = ET.parse(out).getroot()
    assert [p.tag for p in root] == ["page", "page"]
    assert all(p.find("page") is None for p in root)


def test_pdf_to_pptx_keeps_page_aspect(window, dialogs, tmp_path):
    from pptx import Presentation
    src = tmp_path / "mixed.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.new_page(width=842, height=595)
    doc.save(str(src))
    doc.close()
    page = _page(window)
    out = tmp_path / "mixed.pptx"
    _convert(window, dialogs, page, "PPTX", src, out)
    pic = Presentation(str(out)).slides[1].shapes[0]
    assert abs(pic.width / pic.height - 842 / 595) < 0.01


@pytest.mark.parametrize("fmt,ext,pil", [("PNG", "png", "PNG"), ("JPEG", "jpg", "JPEG")])
def test_image_formats_follow_the_resolution(window, dialogs, tmp_path, fmt, ext, pil):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    widths = {}
    for dpi in (72, 144):
        page.dpi_box.setValue(dpi)
        out = tmp_path / f"{dpi}.zip"
        _convert(window, dialogs, page, fmt, src, out)
        with zipfile.ZipFile(out) as zf:
            assert zf.namelist() == [f"page_0001.{ext}", f"page_0002.{ext}"]
            img = Image.open(io.BytesIO(zf.read(f"page_0001.{ext}")))
            assert img.format == pil
            widths[dpi] = img.size[0]
    assert abs(widths[72] - 595) <= 1 and abs(widths[144] - 2 * widths[72]) <= 2


def test_jpeg_quality_changes_the_output(window, dialogs, tmp_path):
    page = _page(window)
    src = tmp_path / "noise.pdf"
    d = fitz.open()
    buf = io.BytesIO()
    Image.effect_noise((400, 400), 60).convert("RGB").save(buf, "PNG")
    d.new_page().insert_image(fitz.Rect(0, 0, 400, 400), stream=buf.getvalue())
    d.save(str(src))
    d.close()
    page.dpi_box.setValue(72)
    sizes = {}
    for q in (50, 100):
        page.fmt.setCurrentText("JPEG")
        page.quality_box.setValue(q)
        assert page.options() == (72, q)
        out = tmp_path / f"q{q}.zip"
        _convert(window, dialogs, page, "JPEG", src, out)
        with zipfile.ZipFile(out) as zf:
            sizes[q] = len(zf.read("page_0001.jpg"))
    assert sizes[50] < sizes[100]


def test_options_fall_back_when_the_format_has_none(window):
    page = _page(window)
    page.dpi_box.setValue(200)
    page.quality_box.setValue(60)
    page.fmt.setCurrentText("TXT")
    assert page.options() == (200, 92)
    page.fmt.setCurrentText("PPTX")
    assert page.options() == (200, 92)


def test_a_protected_input_is_unlocked(window, dialogs, tmp_path):
    path = tmp_path / "enc.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "Locked text", fontsize=14)
    doc.save(str(path), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    doc.close()
    page = _page(window)
    dialogs.passwords.append("u")
    out = tmp_path / "out.txt"
    _convert(window, dialogs, page, "TXT", path, out)
    assert "Locked text" in out.read_text(encoding="utf-8")


def test_a_dropped_pdf_is_taken_and_others_are_refused(window, dialogs, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf")
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    assert page.accept_drop(src) is True and page.file.path() == src
    dialogs.open(src)
    assert window.page_hook("open") and page.file.path() == src


def test_cancelling_the_save_dialog_closes_the_document(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    opened = spy_open(window, monkeypatch)
    page.run()                     # no save path queued: the dialog returns ""
    assert opened and opened[0].is_closed
    assert window._current_job is None


def test_cancelling_the_job_leaves_no_file(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    page.fmt.setCurrentText("PNG")
    page.dpi_box.setValue(300)
    page.file.set_path(make_pdf(tmp_path / "in.pdf", pages=40))
    out = tmp_path / "pages.zip"
    dialogs.save(out)
    opened = spy_open(window, monkeypatch)
    page.run()
    window._cancel_job()
    wait_job(window)
    assert not out.exists() and not list(tmp_path.glob("*.part"))
    assert opened[0].is_closed
    assert window.status_text() == "⚠  Cancelled"


def test_leaving_the_tool_holds_no_document(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    opened = spy_open(window, monkeypatch)
    _convert(window, dialogs, page, "TXT", make_pdf(tmp_path / "in.pdf"), tmp_path / "o.txt")
    assert window.show_page("home")
    # the jobs' copies are closed; the window keeps the one document (2026-10-23)
    shared = window.document.doc
    assert opened and all(d.is_closed for d in opened if d is not shared)
    assert shared is not None and not shared.is_closed


def test_named_pdf_to_other_and_the_dpi_defaults_from_preferences(window, monkeypatch):
    # PDF → Images's own checks, folded in with its screen (owner, 2026-10-18).
    from paperknife.prefs import PREFS
    monkeypatch.setitem(PREFS._data, "export_dpi", 250)
    assert window.open_tool("Pdf2DocTool")
    page = window.current_page()
    assert page.title_label.text() == "PDF → Other"
    assert window._labels["Pdf2DocTool"] == "PDF → Other"
    assert int(page.dpi_box.value()) == 250
