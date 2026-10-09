"""paperknife.core.convert without any user interface: every format both ways,
progress, and Cancel leaving no file behind."""
import threading
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
    if fmt == "TXT":
        text = out.read_text(encoding="utf-8")
        assert "Hello page 1" in text and "Hello page 3" in text
    if fmt in ("PNG", "JPEG"):
        assert len(zipfile.ZipFile(out).namelist()) == 3


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
