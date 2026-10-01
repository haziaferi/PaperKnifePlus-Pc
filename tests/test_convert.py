"""Convert tools, OCR, metadata and the reader."""
import time

import pymupdf as fitz
import pytest

import fitz as legacy_fitz       # baseline-src still imports the old name

_FITZ_MODULES = (fitz, legacy_fitz)
from PIL import Image

from conftest import make_pdf, pump, tool, wait_job

_PAGE_CAP = 40


@pytest.fixture
def capped_writer(monkeypatch):
    """Doc→PDF Story loops that never end would fill the disk; stop them at a cap."""
    real = fitz.DocumentWriter
    stats = {"pages": 0}

    class Capped:
        def __init__(self, path, *a, **k):
            self._w = real(path, *a, **k)

        def begin_page(self, rect):
            stats["pages"] += 1
            if stats["pages"] > _PAGE_CAP:
                raise RuntimeError(f"runaway Story loop: more than {_PAGE_CAP} pages")
            return self._w.begin_page(rect)

        def end_page(self):
            self._w.end_page()

        def close(self):
            self._w.close()

    for mod in _FITZ_MODULES:
        monkeypatch.setattr(mod, "DocumentWriter", Capped)
    return stats


@pytest.fixture
def story_html(monkeypatch):
    real = fitz.Story
    seen = []

    def make(html="", *a, **k):
        seen.append(html)
        return real(html, *a, **k)

    for mod in _FITZ_MODULES:
        monkeypatch.setattr(mod, "Story", make)
    return seen


def _doc2pdf(app, dialogs, fmt, src, out):
    t = tool(app, "Doc2PdfTool")
    t._fmt.set(fmt)
    t._path.set(str(src))
    dialogs.save(out)
    t._run()
    wait_job(app, timeout=60)
    return t


def _pdf2doc(app, dialogs, fmt, src, out):
    t = tool(app, "Pdf2DocTool")
    t._fmt.set(fmt)
    t._fmt_changed(fmt)
    t._path.set(str(src))
    dialogs.save(out)
    t._run()
    wait_job(app, timeout=60)
    return t


# ── Doc → PDF ────────────────────────────────────────────────────────────────
def test_txt_to_pdf_short_text_finishes_on_one_page(app, dialogs, tmp_path, capped_writer):
    src = tmp_path / "short.txt"
    src.write_text("one\ntwo\nthree\n", encoding="utf-8")
    out = tmp_path / "short.pdf"
    _doc2pdf(app, dialogs, "TXT", src, out)
    assert capped_writer["pages"] <= _PAGE_CAP, "Story loop did not stop"
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        assert len(doc) == 1
        assert "three" in doc[0].get_text()


def test_txt_to_pdf_long_text_wraps_and_spans_pages(app, dialogs, tmp_path, capped_writer):
    long_line = " ".join(f"w{i:03d}" for i in range(80))
    body = "\n".join(f"line {i}" for i in range(150))
    src = tmp_path / "long.txt"
    src.write_text(long_line + "\n" + body, encoding="utf-8")
    out = tmp_path / "long.pdf"
    _doc2pdf(app, dialogs, "TXT", src, out)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        assert 1 < len(doc) < 10
        text = "".join(p.get_text() for p in doc)
        assert "w079" in text, "the end of a long line was cut off"
        assert "line 149" in text
        assert all(w[2] <= doc[0].rect.width - 20 for w in doc[0].get_text("words"))


def test_txt_to_pdf_cancel_stops_the_story_loop(app, dialogs, tmp_path, capped_writer):
    src = tmp_path / "huge.txt"
    src.write_text("\n".join(f"line {i}" for i in range(20_000)), encoding="utf-8")
    out = tmp_path / "huge.pdf"
    t = tool(app, "Doc2PdfTool")
    t._fmt.set("TXT")
    t._path.set(str(src))
    dialogs.save(out)
    t._run()
    assert app._current_job is not None and app._current_job.is_running
    app._cancel_job()          # before the first page: the loop must notice it
    wait_job(app, timeout=60)
    assert capped_writer["pages"] <= 2, capped_writer
    assert not dialogs.errors(), dialogs.errors()
    assert not out.exists(), "a cancelled conversion left a partial PDF"


def test_docx_to_pdf_keeps_document_order(app, dialogs, tmp_path, capped_writer):
    import docx
    src = tmp_path / "d.docx"
    w = docx.Document()
    w.add_heading("Heading One", level=1)
    w.add_paragraph("before table")
    w.add_table(rows=1, cols=2).rows[0].cells[0].text = "cellA"
    w.add_paragraph("after table")
    w.save(src)
    out = tmp_path / "d.pdf"
    _doc2pdf(app, dialogs, "DOCX", src, out)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        text = doc[0].get_text()
    assert text.index("before table") < text.index("cellA") < text.index("after table"), text


def test_xlsx_to_pdf_keeps_zero_cells(app, dialogs, tmp_path, capped_writer, story_html):
    import openpyxl
    src = tmp_path / "zeros.xlsx"
    wb = openpyxl.Workbook()
    wb.active.append([0, 0.0, "x"])         # openpyxl reads 0.0 back as 0
    wb.save(src)
    out = tmp_path / "zeros.pdf"
    _doc2pdf(app, dialogs, "XLSX", src, out)
    assert story_html and "0\t0\tx" in story_html[0], story_html[:1]
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        assert len(doc) == 1


def test_html_to_pdf_resolves_relative_images(app, dialogs, tmp_path, capped_writer):
    Image.new("RGB", (40, 40), (255, 0, 0)).save(tmp_path / "red.png")
    src = tmp_path / "page.html"
    src.write_text('<p>hi</p><img src="red.png">', encoding="utf-8")
    out = tmp_path / "page.pdf"
    _doc2pdf(app, dialogs, "HTML", src, out)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        assert doc[0].get_images()


def _transparent_png(path):
    im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    for x in range(80, 120):
        for y in range(80, 120):
            im.putpixel((x, y), (255, 0, 0, 255))
    im.save(path)
    return path


def _corner_pixel(pdf):
    with fitz.open(pdf) as doc:
        pix = doc[0].get_pixmap(alpha=False)
        return pix.pixel(5, 5)


def test_img2pdf_transparent_png_gets_white_background(app, dialogs, tmp_path):
    src = _transparent_png(tmp_path / "t.png")
    out = tmp_path / "t.pdf"
    t = tool(app, "Img2PdfTool")
    t._lb.insert("end", str(src))
    dialogs.save(out)
    t._run()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    assert _corner_pixel(out) == (255, 255, 255)


def test_doc2pdf_transparent_png_gets_white_background(app, dialogs, tmp_path):
    src = _transparent_png(tmp_path / "t.png")
    out = tmp_path / "t.pdf"
    _doc2pdf(app, dialogs, "PNG", src, out)
    assert not dialogs.errors(), dialogs.errors()
    assert _corner_pixel(out) == (255, 255, 255)


# ── PDF → Doc ────────────────────────────────────────────────────────────────
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


def test_pdf_to_rtf_keeps_non_latin1_characters(app, dialogs, tmp_path):
    src = _unicode_pdf(tmp_path / "u.pdf", ["cost €5 café", "Ελληνικά"])
    out = tmp_path / "u.rtf"
    _pdf2doc(app, dialogs, "RTF", src, out)
    assert not dialogs.errors(), dialogs.errors()
    data = out.read_bytes()
    assert all(b < 128 for b in data), "RTF must be 7-bit with \\uN escapes"
    assert b"\\u8364?" in data          # €
    assert b"\\u233?" in data           # é
    assert b"\\u917?" in data           # Ε


def test_pdf_to_xlsx_does_not_create_formulas(app, dialogs, tmp_path):
    import openpyxl
    src = make_pdf(tmp_path / "f.pdf", pages=1, text="=1+1")
    out = tmp_path / "f.xlsx"
    _pdf2doc(app, dialogs, "XLSX", src, out)
    assert not dialogs.errors(), dialogs.errors()
    cell = openpyxl.load_workbook(out)["Page 1"]["A1"]
    assert cell.value == "=1+1"
    assert cell.data_type == "s"


def test_pdf_to_docx_survives_control_characters(app, dialogs, tmp_path, monkeypatch):
    # A broken ToUnicode map is hard to build, so inject what it extracts.
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
    src = make_pdf(tmp_path / "c.pdf", pages=1)
    out = tmp_path / "c.docx"
    _pdf2doc(app, dialogs, "DOCX", src, out)
    assert not dialogs.errors(), dialogs.errors()
    assert out.exists()


def test_pdf_to_xml_is_well_formed_without_nested_pages(app, dialogs, tmp_path):
    import xml.etree.ElementTree as ET
    src = make_pdf(tmp_path / "x.pdf", pages=2)
    out = tmp_path / "x.xml"
    _pdf2doc(app, dialogs, "XML", src, out)
    assert not dialogs.errors(), dialogs.errors()
    root = ET.parse(out).getroot()
    assert [p.tag for p in root] == ["page", "page"]
    assert all(p.find("page") is None for p in root)


def test_pdf_to_pptx_keeps_page_aspect(app, dialogs, tmp_path):
    from pptx import Presentation
    src = tmp_path / "mixed.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=842)
    doc.new_page(width=842, height=595)
    doc.save(str(src))
    doc.close()
    out = tmp_path / "mixed.pptx"
    _pdf2doc(app, dialogs, "PPTX", src, out)
    assert not dialogs.errors(), dialogs.errors()
    pic = Presentation(str(out)).slides[1].shapes[0]
    assert abs(pic.width / pic.height - 842 / 595) < 0.01


# ── Preferences ──────────────────────────────────────────────────────────────
@pytest.fixture
def prefs(monkeypatch):
    from paperknife.prefs import PREFS
    monkeypatch.setitem(PREFS._data, "ocr_lang", "ita")
    monkeypatch.setitem(PREFS._data, "default_dpi", 200)
    return PREFS


def test_pdf2img_dpi_defaults_from_preferences(app, prefs):
    t = tool(app, "Pdf2ImgTool")
    assert int(t._dpi.get()) == 200


# ── OCR (Tesseract is stubbed: the binary is not installed here) ─────────────
_WORDS = [  # (text, conf, left, top, width, height) in 72-dpi pixels
    ("Smith", 95, 100, 300, 50, 16),
    ("&", 90, 155, 300, 10, 16),
    ("don't", 92, 170, 300, 40, 16),
    ("Ελληνικά", 88, 220, 300, 70, 16),
    ("zzzq", 10, 300, 300, 40, 16),
]


@pytest.fixture
def tess(monkeypatch):
    import html as _html
    import pytesseract
    calls = {}

    def scale_of(img):
        return img.size[0] / 595.0

    def image_to_data(img, lang=None, output_type=None, **k):
        calls["lang"] = lang
        s = scale_of(img)
        d = {"text": [], "conf": [], "left": [], "top": [], "width": [], "height": []}
        for text, conf, x, y, w, h in _WORDS:
            for key, v in zip(("text", "conf", "left", "top", "width", "height"),
                              (text, conf, x * s, y * s, w * s, h * s), strict=True):
                d[key].append(round(v) if key not in ("text", "conf") else v)
        return d

    def image_to_pdf_or_hocr(img, lang=None, extension=None, **k):
        calls["lang"] = lang
        s = scale_of(img)
        spans = "".join(
            f"<span class='ocrx_word' title='bbox {round(x*s)} {round(y*s)} "
            f"{round((x+w)*s)} {round((y+h)*s)}; x_wconf {c}'>{_html.escape(t)}</span>"
            for t, c, x, y, w, h in _WORDS)
        return f"<html><body>{spans}</body></html>".encode()

    monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "5.0")
    monkeypatch.setattr(pytesseract, "image_to_data", image_to_data)
    monkeypatch.setattr(pytesseract, "image_to_pdf_or_hocr", image_to_pdf_or_hocr)
    monkeypatch.setattr(pytesseract, "image_to_string",
                        lambda img, lang=None, **k: calls.setdefault("lang", lang) and "text")
    return calls


def _source_pdf(path, rotation=0):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 120), "Original vector heading", fontsize=18, color=(0, 0, 1))
    page.draw_rect(fitz.Rect(72, 500, 300, 560), color=(1, 0, 0), width=2)
    page.set_rotation(rotation)
    doc.save(str(path))
    doc.close()
    return str(path)


def _run_ocr(app, dialogs, src, out):
    t = tool(app, "OCRTool")
    t._path.set(src)
    dialogs.save(out)
    t._run()
    wait_job(app)
    return t


def test_ocr_overlay_keeps_original_page_and_adds_clean_text(app, dialogs, tmp_path, tess):
    src = _source_pdf(tmp_path / "scan.pdf")
    out = tmp_path / "ocr.pdf"
    _run_ocr(app, dialogs, src, out)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(src) as a, fitz.open(out) as b:
        text = b[0].get_text()
        words = {w[4] for w in b[0].get_text("words")}
        assert {"Smith", "&", "don't", "Ελληνικά"} <= words, text
        assert "zzzq" not in text, "low-confidence words must be dropped"
        assert "Original vector heading" in text, "the original page content was replaced"
        assert not b[0].get_images(), "the page was rasterised"
        pa = a[0].get_pixmap(alpha=False)
        pb = b[0].get_pixmap(alpha=False)
        assert pa.samples == pb.samples, "the OCR layer changed how the page looks"


def test_ocr_overlay_places_words_on_rotated_page(app, dialogs, tmp_path, tess):
    src = _source_pdf(tmp_path / "rot.pdf", rotation=90)
    out = tmp_path / "rot_ocr.pdf"
    _run_ocr(app, dialogs, src, out)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(src) as a, fitz.open(out) as b:
        page = b[0]
        assert page.rotation == 0
        smith = [w for w in page.get_text("words") if w[4] == "Smith"]
        assert smith, page.get_text()
        x0, y0, x1, y1 = smith[0][:4]
        sx = page.rect.width / 595.0
        assert abs(x0 - 100 * sx) < 4 and abs(y1 - 316 * sx) < 6, smith
        assert a[0].get_pixmap(alpha=False).samples == page.get_pixmap(alpha=False).samples


def test_ocr_uses_preferences_language_and_dpi(app, dialogs, tmp_path, tess, prefs):
    src = _source_pdf(tmp_path / "p.pdf")
    t = _run_ocr(app, dialogs, src, tmp_path / "p_ocr.pdf")
    assert t._lang.get() == "ita"
    assert int(t._dpi.get()) == 200
    assert tess["lang"] == "ita"


# ── Metadata ─────────────────────────────────────────────────────────────────
def test_metadata_clear_all_also_removes_xmp(app, dialogs, tmp_path):
    src = tmp_path / "m.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.set_metadata({"author": "Jane PRIVATE Doe", "title": "T"})
    doc.set_xml_metadata(
        '<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
        'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:creator><rdf:Seq><rdf:li>Jane PRIVATE Doe</rdf:li></rdf:Seq></dc:creator>'
        '</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>')
    doc.save(str(src))
    doc.close()
    out = tmp_path / "m_clean.pdf"
    t = tool(app, "MetadataTool")
    dialogs.open(str(src))
    t._open()
    t._clear()
    dialogs.save(out)
    t._save()
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as d:
        assert "PRIVATE" not in (d.get_xml_metadata() or "")
        for xref in range(1, d.xref_length()):
            body = d.xref_object(xref) + (
                (d.xref_stream(xref) or b"").decode("latin-1") if d.xref_is_stream(xref) else "")
            assert "PRIVATE" not in body, f"xref {xref} still holds the author"
    t._doc.close()
    t._doc = None


def test_metadata_date_field_converted_to_pdf_date(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "d.pdf", pages=1)
    out = tmp_path / "d_out.pdf"
    t = tool(app, "MetadataTool")
    dialogs.open(src)
    t._open()
    t._vars["creationDate"].set("2024-01-31")
    dialogs.save(out)
    t._save()
    with fitz.open(out) as d:
        assert d.metadata["creationDate"].startswith("D:20240131")
    t._doc.close()
    t._doc = None


# ── Reader ───────────────────────────────────────────────────────────────────
def test_reader_does_not_rerender_pages_already_requested(app, tmp_path, monkeypatch):
    src = make_pdf(tmp_path / "r.pdf", pages=12)
    real = fitz.Page.get_pixmap
    count = {"n": 0}

    def counting(self, *a, **k):
        count["n"] += 1
        return real(self, *a, **k)

    t = tool(app, "ReaderTool")
    monkeypatch.setattr(t._canvas, "winfo_height", lambda: 900)   # hidden window: 1 px tall
    monkeypatch.setattr(fitz.Page, "get_pixmap", counting)
    t.open_path(src)
    for _ in range(10):
        t._update_viewport()
    end = time.time() + 5
    while time.time() < end and not t._req_q.empty():
        time.sleep(0.05)
    time.sleep(0.3)
    pump(app, 0.3)
    visible = len(t._items)
    assert visible >= 1
    assert count["n"] <= visible, f"{count['n']} rasterisations for {visible} pages"


def test_reader_zoom_slider_shows_current_zoom(app):
    t = tool(app, "ReaderTool")
    assert abs(t._zoom_slider.get() - t._zoom) < 0.06


@pytest.mark.parametrize("name", ["ExtractTool", "Doc2PdfTool"])
def test_ctrl_o_opens_a_file_in_converter(app, name):
    tool(app, name)
    assert app._cur_open_fn is not None
