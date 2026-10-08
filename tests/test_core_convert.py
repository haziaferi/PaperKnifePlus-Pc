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


def test_doc_to_pdf_cancelled_returns_none_and_writes_nothing(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text("x " * 5000, encoding="utf-8")
    out = tmp_path / "out.pdf"
    stop = threading.Event()
    stop.set()
    assert core.doc_to_pdf(str(src), "TXT", str(out), stop) is None
    assert not Path(out).exists()
