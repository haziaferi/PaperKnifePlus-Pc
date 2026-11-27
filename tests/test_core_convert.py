"""paperknife.core.convert without any user interface: every format both ways,
progress, and Cancel leaving no file behind."""
import html
import io
import re
import threading
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pymupdf as fitz
import pytest

from conftest import make_pdf
from paperknife.core import convert as core

FORMATS = ["TXT", "HTML", "XML", "RTF", "DOCX", "PPTX", "XLSX", "PNG", "JPEG"]
EXT = {"TXT": ".txt", "HTML": ".html", "XML": ".xml", "RTF": ".rtf", "DOCX": ".docx",
       "PPTX": ".pptx", "XLSX": ".xlsx", "PNG": ".zip", "JPEG": ".zip"}


def _installed(fmt):
    return fmt not in core.NEEDS or core.NEEDS[fmt][1]


def _texts_in(out, fmt):
    """The text strings a reader of *fmt* finds in the file *out*."""
    if fmt == "TXT":
        return [out.read_text(encoding="utf-8")]
    if fmt == "HTML":
        raw = out.read_text(encoding="utf-8")
        assert raw.lstrip().lower().startswith("<!doctype html")
        return [html.unescape(t) for t in re.split(r"<[^>]*>", raw)]
    if fmt == "XML":
        # The file this test just wrote from its own PDF, not untrusted input.
        root = ET.parse(out).getroot()  # nosemgrep: python.lang.security.use-defused-xml-parse.use-defused-xml-parse
        return [ln.get("text", "") for ln in root.iter("line")]
    if fmt == "RTF":
        raw = out.read_text(encoding="utf-8")
        assert raw.startswith("{\\rtf1")
        return [re.sub(r"\\[a-z]+-?\d* ?|[{}]", "", raw)]
    if fmt == "DOCX":
        import docx
        return [p.text for p in docx.Document(str(out)).paragraphs]
    if fmt == "XLSX":
        import openpyxl
        wb = openpyxl.load_workbook(out)
        return [str(c) for ws in wb for row in ws.iter_rows(values_only=True)
                for c in row if c is not None]
    raise AssertionError(fmt)


@pytest.mark.parametrize("fmt", FORMATS)
def test_pdf_to_doc_writes_every_format_and_reports_progress(tmp_path, fmt):
    if not _installed(fmt):
        pytest.skip(f"{core.NEEDS[fmt][0]} not installed")
    src = make_pdf(tmp_path / "in.pdf", pages=3, text="Hello page {n}")
    out = tmp_path / f"out{EXT[fmt]}"
    seen = []
    ok = core.pdf_to_doc(fitz.open(src), fmt, str(out), threading.Event(), seen.append,
                         dpi=72)
    assert ok and out.exists() and out.stat().st_size > 0
    assert seen and seen[-1] == pytest.approx(1.0)
    # Each format re-opened with its own reader: every page is in it (any bytes
    # would pass a size check alone).
    if fmt in ("PNG", "JPEG"):
        from PIL import Image
        with zipfile.ZipFile(out) as z:
            names = sorted(z.namelist())
            assert len(names) == 3
            for name in names:
                with Image.open(z.open(name)) as im:
                    assert im.format == fmt and im.convert("L").getextrema()[0] < 128
    elif fmt == "PPTX":
        from PIL import Image
        from pptx import Presentation
        slides = list(Presentation(str(out)).slides)
        assert len(slides) == 3                     # a picture of each page, one per slide
        for slide in slides:
            pics = [sh for sh in slide.shapes if sh.shape_type == 13]     # PICTURE
            assert len(pics) == 1
            with Image.open(io.BytesIO(pics[0].image.blob)) as im:
                assert im.convert("L").getextrema()[0] < 128              # text drawn
    else:
        found = _texts_in(out, fmt)
        for want in ("Hello page 1", "Hello page 2", "Hello page 3"):
            assert any(want in t for t in found), (fmt, want, found[:20])


def test_pdf_to_doc_cancelled_writes_nothing_and_closes_the_document(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=5)
    out = tmp_path / "out.txt"
    stop = threading.Event()
    stop.set()
    doc = fitz.open(src)
    assert core.pdf_to_doc(doc, "TXT", str(out), stop, lambda v: None) is False
    assert not out.exists()
    assert doc.is_closed


@pytest.mark.parametrize("fmt,name,content", [
    ("TXT", "a.txt", "Plain text line\nsecond line"),
    ("HTML", "a.html", "<h1>Title here</h1><p>Body text</p>"),
    ("XML", "a.xml", "<root><item>Item text</item></root>"),
])
def test_doc_to_pdf_typesets_text_formats(tmp_path, fmt, name, content):
    src = tmp_path / name
    src.write_text(content, encoding="utf-8")
    out = tmp_path / "out.pdf"
    notes = core.doc_to_pdf(str(src), fmt, str(out), threading.Event())
    assert notes == []
    with fitz.open(out) as d:
        text = d[0].get_text()
    first_word = {"TXT": "Plain", "HTML": "Title", "XML": "Item"}[fmt]
    assert first_word in text


def test_doc_to_pdf_unparsable_xml_falls_back_with_a_note(tmp_path):
    src = tmp_path / "bad.xml"
    src.write_text("<root><open></root>", encoding="utf-8")
    notes = core.doc_to_pdf(str(src), "XML", str(tmp_path / "out.pdf"), threading.Event())
    assert notes and "could not be parsed" in notes[0]


def test_doc_to_pdf_image_page_matches_the_image(tmp_path):
    from PIL import Image
    src = tmp_path / "a.png"
    Image.new("RGB", (300, 200), "red").save(src)
    out = tmp_path / "out.pdf"
    assert core.doc_to_pdf(str(src), "PNG", str(out), threading.Event()) == []
    with fitz.open(out) as d:
        assert (round(d[0].rect.width), round(d[0].rect.height)) == (300, 200)


def _pdf_with_images(path, sizes):
    from PIL import Image
    import io
    d = fitz.open()
    pg = d.new_page()
    for i, (w, h) in enumerate(sizes):
        buf = io.BytesIO()
        Image.new("RGB", (w, h), (i * 40, 100, 200)).save(buf, "PNG")
        pg.insert_image(fitz.Rect(20, 20 + i * 120, 120, 120 + i * 120), stream=buf.getvalue())
    d.save(path)
    return str(path)


@pytest.mark.parametrize("fmt,ext", [("PNG", "png"), ("JPEG", "jpg")])
def test_extract_images_skips_small_ones_and_converts(tmp_path, fmt, ext):
    src = _pdf_with_images(tmp_path / "imgs.pdf", [(200, 150), (30, 30), (120, 90)])
    out = tmp_path / "out"
    out.mkdir()
    res = core.extract_images(fitz.open(src), str(out), fmt, 50, threading.Event(),
                              lambda v: None)
    assert (res.count, res.scanned, res.failed) == (2, 3, 0)
    assert sorted(p.suffix for p in out.iterdir()) == [f".{ext}", f".{ext}"]


def test_extract_images_cancelled_returns_none(tmp_path):
    src = _pdf_with_images(tmp_path / "imgs.pdf", [(200, 150)])
    stop = threading.Event()
    stop.set()
    doc = fitz.open(src)
    assert core.extract_images(doc, str(tmp_path), "PNG", 50, stop, lambda v: None) is None
    assert doc.is_closed


def test_doc_to_pdf_cancelled_returns_none_and_writes_nothing(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x " * 5000, encoding="utf-8")
    out = tmp_path / "out.pdf"
    stop = threading.Event()
    stop.set()
    assert core.doc_to_pdf(str(src), "TXT", str(out), stop) is None
    assert not Path(out).exists()


def _blank_pdf(path):
    d = fitz.open()
    d.new_page()
    d.save(path)
    d.close()
    return str(path)


def test_pdf_to_txt_of_a_pdf_without_text_says_so(tmp_path):
    # The empty output used to be dropped by atomic_output while the tool
    # reported it saved (review R2a-5).
    src = _blank_pdf(tmp_path / "scan.pdf")
    out = tmp_path / "out.txt"
    with pytest.raises(core.NoText):
        core.pdf_to_doc(fitz.open(src), "TXT", str(out), threading.Event(), lambda v: None)
    assert not out.exists()


def test_extracting_a_second_pdf_into_the_same_folder_keeps_the_first(tmp_path):
    # Images were named by xref only; the same xref in another PDF overwrote
    # the first one's image without asking (review R2a-6).
    a = _pdf_with_images(tmp_path / "a.pdf", [(200, 150)])
    b = _pdf_with_images(tmp_path / "b.pdf", [(120, 90)])
    out = tmp_path / "out"
    out.mkdir()
    for src in (a, b):
        core.extract_images(fitz.open(src), str(out), "PNG", 10, threading.Event(), lambda v: None)
    from PIL import Image
    sizes = sorted(Image.open(p).size for p in out.iterdir())
    assert sizes == [(120, 90), (200, 150)]


@pytest.mark.parametrize("fmt", ["PNG", "TXT"])
def test_doc_to_pdf_cancel_after_the_file_is_in_place_still_reports_it(tmp_path, monkeypatch,
                                                                       fmt):
    # Cancel landing once the output has replaced *out*: the file is there, so
    # reporting "cancelled" would hide a written (or replaced) file.
    import contextlib
    from PIL import Image
    if fmt == "PNG":
        src = tmp_path / "a.png"
        Image.new("RGB", (50, 40), "red").save(src)
    else:
        src = tmp_path / "a.txt"
        src.write_text("hello", encoding="utf-8")
    out = tmp_path / "out.pdf"
    stop = threading.Event()
    real = core.atomic_output

    @contextlib.contextmanager
    def cancel_after_commit(path):
        with real(path) as tmp:
            yield tmp
        stop.set()
    monkeypatch.setattr(core, "atomic_output", cancel_after_commit)
    assert core.doc_to_pdf(str(src), fmt, str(out), stop) == []
    assert out.exists()


@pytest.fixture
def opened_docs(monkeypatch):
    """Every document fitz.open() returns while the test runs."""
    real, seen = fitz.open, []

    def recording(*a, **k):
        d = real(*a, **k)
        seen.append(d)
        return d
    monkeypatch.setattr(core.fitz, "open", recording)
    return seen


def test_doc_to_pdf_a_corrupt_image_leaves_no_document_open(tmp_path, opened_docs):
    src = tmp_path / "bad.png"
    src.write_bytes(b"\x89PNG\r\n\x1a\nnot really a png")
    with pytest.raises(OSError):           # PIL.UnidentifiedImageError
        core.doc_to_pdf(str(src), "PNG", str(tmp_path / "out.pdf"), threading.Event())
    assert opened_docs and all(d.is_closed for d in opened_docs)


def test_doc_to_pdf_a_failing_slide_leaves_no_document_open(tmp_path, opened_docs,
                                                            monkeypatch):
    if not _installed("PPTX"):
        pytest.skip("python-pptx not installed")
    from pptx import Presentation
    src = tmp_path / "a.pptx"
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[1]).shapes.title.text = "Slide"
    prs.save(src)

    def boom(*a, **k):
        raise RuntimeError("typesetting failed")
    monkeypatch.setattr(fitz.Page, "insert_htmlbox", boom)
    with pytest.raises(RuntimeError):
        core.doc_to_pdf(str(src), "PPTX", str(tmp_path / "out.pdf"), threading.Event())
    assert opened_docs and all(d.is_closed for d in opened_docs)


def test_extract_images_a_write_error_is_raised_not_counted_as_failed(tmp_path, monkeypatch):
    # Disk full, a locked file or a read-only folder is the job's error, not
    # "an image that could not be extracted".
    src = _pdf_with_images(tmp_path / "imgs.pdf", [(200, 150)])

    def disk_full(self, data):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(Path, "write_bytes", disk_full)
    doc = fitz.open(src)
    with pytest.raises(OSError, match="No space left"):
        core.extract_images(doc, str(tmp_path), "Original", 50, threading.Event(),
                            lambda v: None)
    assert doc.is_closed


# Image page size (2026-11-27): a scanner's resolution gives the sheet's size, up
# to A3; a phone photo or a screenshot (72, 96 or no resolution) fits A4, never enlarged.
@pytest.mark.parametrize("px, dpi, size", [
    ((4000, 3000), (72, 72), (793.7, 595.3)),        # phone photo, landscape: A4 on its side
    ((3000, 4000), None, (595.3, 793.7)),            # phone photo, portrait: A4's width
    ((2480, 3508), (300, 300), (595.2, 841.9)),      # A4 scanned at 300 DPI: A4
    ((1654, 2339), (200, 200), (595.4, 842.0)),      # A4 scanned at 200 DPI: its real size
    ((2550, 3300), (300, 300), (612.0, 792.0)),      # US Letter scanned: Letter, not A4
    ((2550, 4200), (300, 300), (612.0, 1008.0)),     # US Legal scanned: Legal
    ((3508, 4961), (300, 300), (841.9, 1190.6)),     # A3 scanned: A3
    ((6000, 4000), (300, 300), (841.9, 561.3)),      # a camera's 300 DPI, larger than A3: A4
    ((1728, 1145), (204, 98), (609.9, 841.2)),       # a fax at 204 x 98 DPI: portrait, its size
    ((500, 400), (72, 0), (500.0, 400.0)),           # a resolution of 0: none
    ((1920, 1080), (96, 96), (841.9, 473.6)),        # a screenshot: A4 across
    ((300, 200), None, (300.0, 200.0)),              # a small image: its own size
    ((600, 300), (150, 150), (288.0, 144.0)),        # a small scan: its real size
])
def test_an_image_page_is_sized_by_its_scan_resolution_and_fits_a4(px, dpi, size):
    assert core.image_page_size(*px, dpi) == pytest.approx(size, abs=0.1)


def test_a_phone_photo_becomes_an_a4_page_not_a_141_cm_one(tmp_path):
    from PIL import Image
    src = tmp_path / "photo.jpg"
    Image.new("RGB", (4000, 3000), "white").save(src, "JPEG", dpi=(72, 72))
    out = tmp_path / "out.pdf"
    core.files_to_pdf([str(src)], str(out), threading.Event())
    with fitz.open(out) as d:
        assert (round(d[0].rect.width), round(d[0].rect.height)) == (794, 595)
        assert d[0].get_images(full=True)[0][2:4] == (4000, 3000)    # every pixel kept


def test_a_photo_turned_by_its_exif_fits_a4_upright(tmp_path):
    from PIL import Image
    src = tmp_path / "turned.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6                                   # shown turned a quarter clockwise
    Image.new("RGB", (4000, 3000), "white").save(src, "JPEG", exif=exif, dpi=(72, 72))
    out = tmp_path / "out.pdf"
    core.files_to_pdf([str(src)], str(out), threading.Event())
    with fitz.open(out) as d:
        assert (round(d[0].rect.width), round(d[0].rect.height)) == (595, 794)


def test_a_square_photo_turned_by_its_exif_swaps_its_resolution(tmp_path):
    from PIL import Image
    src = tmp_path / "square.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6
    Image.new("RGB", (2000, 2000), "white").save(src, "JPEG", exif=exif, dpi=(200, 400))
    out = tmp_path / "out.pdf"
    core.files_to_pdf([str(src)], str(out), threading.Event())
    with fitz.open(out) as d:
        assert (round(d[0].rect.width), round(d[0].rect.height)) == (360, 720)


@pytest.mark.parametrize("fmt", ["PNG", "JPEG"])
def test_pages_exported_as_images_come_back_at_their_size(tmp_path, fmt):
    """PDF → Other's PNG / JPEG carry the export resolution, so Other → PDF
    gives each page its size again (A5 and Letter were fitted to A4)."""
    src = fitz.open()
    src.new_page(width=419.53, height=595.28)               # A5
    src.new_page(width=612, height=792)                     # US Letter
    zpath = tmp_path / "pages.zip"
    core.pages_to_zip(str(zpath), src, 150, fmt, 85, threading.Event(), lambda v: None)
    src.close()
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(tmp_path / "x")
    images = sorted(str(f) for f in (tmp_path / "x").iterdir())
    out = tmp_path / "back.pdf"
    core.files_to_pdf(images, str(out), threading.Event())
    with fitz.open(out) as d:
        sizes = [(p.rect.width, p.rect.height) for p in d]
    assert sizes[0] == pytest.approx((419.53, 595.28), abs=0.6)
    assert sizes[1] == pytest.approx((612, 792), abs=0.6)
