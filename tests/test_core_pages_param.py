"""The page-range tools' core functions on chosen pages (owner, 2026-10-17:
the pages are picked on the grid).  Pages keep their original numbers."""
import threading
import zipfile

import pymupdf as fitz

from conftest import make_pdf
from paperknife.core import convert, enhance


def _stop():
    return threading.Event()


def test_pdf_to_doc_text_of_the_chosen_pages_only(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=4)
    out = tmp_path / "out.txt"
    assert convert.pdf_to_doc(fitz.open(src), "TXT", str(out), _stop(), lambda v: None,
                              pages=[2, 0])
    text = out.read_text(encoding="utf-8")
    assert "Page 3" in text and "Page 1" in text and "Page 2" not in text
    assert text.index("Page 3") < text.index("Page 1")          # in the order given


def test_page_images_keep_their_page_numbers(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=4)
    out = tmp_path / "out.zip"
    assert convert.pdf_to_doc(fitz.open(src), "PNG", str(out), _stop(), lambda v: None,
                              dpi=36, pages=[1, 3])
    with zipfile.ZipFile(out) as z:
        assert z.namelist() == ["page_0002.png", "page_0004.png"]


def test_spreadsheet_sheets_are_named_after_their_pages(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    out = tmp_path / "out.xlsx"
    convert.pdf_to_doc(fitz.open(src), "XLSX", str(out), _stop(), lambda v: None, pages=[2])
    import openpyxl
    assert openpyxl.load_workbook(out).sheetnames == ["Page 3"]


def test_watermark_stamps_only_the_chosen_pages(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    out = tmp_path / "out.pdf"
    enhance.watermark_pdf(fitz.open(src), str(out), "DRAFT", 40, 0.5, (0, 0, 0), _stop(),
                          pages=[1])
    with fitz.open(out) as d:
        assert len(d) == 3
        assert ["DRAFT" in p.get_text() for p in d] == [False, True, False]


def test_normalise_redraws_only_the_chosen_pages(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=3)               # Letter-ish default size
    out = tmp_path / "out.pdf"
    with fitz.open(src) as d:
        before = [(round(p.rect.width), round(p.rect.height)) for p in d]
    assert enhance.normalise_pdf(fitz.open(src), str(out), "A5", "Portrait", False, _stop(),
                                 lambda v: None, pages=[0])
    with fitz.open(out) as d:
        sizes = [(round(p.rect.width), round(p.rect.height)) for p in d]
        assert sizes[0] == (420, 595) and sizes[1:] == before[1:]
        assert [p.get_text().strip() for p in d] == ["Page 1", "Page 2", "Page 3"]


def test_extract_images_reads_only_the_chosen_pages(tmp_path):
    doc = fitz.open()
    for colour in (40, 200):
        p = doc.new_page()
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 80, 80), False)
        pix.clear_with(colour)
        p.insert_image(fitz.Rect(72, 72, 272, 272), pixmap=pix)
    src = tmp_path / "in.pdf"
    doc.save(src)
    doc.close()
    out = tmp_path / "imgs"
    out.mkdir()
    got = convert.extract_images(fitz.open(src), str(out), "PNG", 10, _stop(), lambda v: None,
                                 pages=[1])
    assert got.count == 1 and got.scanned == 1 and len(list(out.iterdir())) == 1
