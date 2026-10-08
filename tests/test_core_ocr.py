"""paperknife.core.ocr without any user interface, Tesseract answered by stubs."""
import threading

import pymupdf as fitz
import pytest

from conftest import make_pdf
from paperknife.core import ocr as core

pytesseract = pytest.importorskip("pytesseract")

# (text, confidence, x, y, w, h) in points on a 595-pt-wide page
_WORDS = [("Hello", 95, 100, 200, 80, 20), ("World", 90, 200, 200, 80, 20),
          ("faint", 10, 100, 300, 60, 20)]


@pytest.fixture
def tess(monkeypatch):
    calls = {"pages": 0}

    def image_to_data(img, lang=None, output_type=None, **k):
        calls["lang"] = lang
        calls["pages"] += 1
        s = img.size[0] / 595.0
        d = {"text": [""], "conf": [-1], "left": [0], "top": [0], "width": [0], "height": [0]}
        for text, conf, x, y, w, h in _WORDS:
            d["text"].append(text)
            d["conf"].append(conf)
            d["left"].append(round(x * s))
            d["top"].append(round(y * s))
            d["width"].append(round(w * s))
            d["height"].append(round(h * s))
        return d

    monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "5.0")
    monkeypatch.setattr(pytesseract, "image_to_data", image_to_data)
    monkeypatch.setattr(pytesseract, "image_to_string",
                        lambda img, lang=None, **k: "Plain OCR text")
    return calls


def test_ocr_words_scales_to_page_space_and_drops_low_confidence(tess):
    from PIL import Image
    img = Image.new("RGB", (1190, 1684), "white")      # a 595-pt page at 2x
    words = core.ocr_words(img, "eng", 2.0)
    assert [t for _, t in words] == ["Hello", "World"]
    assert tuple(words[0][0]) == pytest.approx((100, 200, 180, 220), abs=0.6)


def test_add_text_layer_is_invisible_and_searchable(tmp_path):
    with fitz.open() as doc:
        page = doc.new_page()
        before = page.get_pixmap(alpha=False).samples
        core.add_text_layer(page, [(fitz.Rect(100, 200, 180, 220), "Hidden")])
        assert page.search_for("Hidden")
        assert page.get_pixmap(alpha=False).samples == before


def test_ocr_pdf_overlay_keeps_pages_and_reports_progress(tmp_path, tess):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    out = tmp_path / "out.pdf"
    seen, notes = [], []
    doc = fitz.open(src)
    n = core.ocr_pdf(doc, str(out), "ita", 72, False, threading.Event(), seen.append,
                     lambda i, t: notes.append((i, t)))
    assert n == 2 and doc.is_closed
    assert seen == pytest.approx([0.5, 1.0]) and notes == [(1, 2), (2, 2)]
    assert tess["lang"] == "ita" and tess["pages"] == 2
    with fitz.open(out) as d:
        text = d[0].get_text()
        assert "Page 1" in text and "Hello" in text and "faint" not in text


def test_ocr_pdf_text_only_makes_a4_text_pages(tmp_path, tess):
    src = make_pdf(tmp_path / "in.pdf", pages=2, width=300, height=300)
    out = tmp_path / "out.pdf"
    assert core.ocr_pdf(fitz.open(src), str(out), "eng", 72, True, threading.Event(),
                        lambda v: None) == 2
    with fitz.open(out) as d:
        assert len(d) == 2
        assert (round(d[0].rect.width), round(d[0].rect.height)) == (595, 842)
        assert "Plain OCR text" in d[1].get_text() and "Page 2" not in d[1].get_text()


def test_ocr_pdf_cancelled_writes_nothing_and_closes_the_document(tmp_path, tess):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    out = tmp_path / "out.pdf"
    stop = threading.Event()
    stop.set()
    doc = fitz.open(src)
    assert core.ocr_pdf(doc, str(out), "eng", 72, False, stop, lambda v: None) is None
    assert not out.exists() and doc.is_closed and tess["pages"] == 0


def test_ocr_pdf_without_tesseract_raises_and_closes_the_document(tmp_path, monkeypatch):
    def missing():
        raise pytesseract.TesseractNotFoundError()
    monkeypatch.setattr(pytesseract, "get_tesseract_version", missing)
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    doc = fitz.open(src)
    with pytest.raises(RuntimeError, match="Tesseract not found"):
        core.ocr_pdf(doc, str(tmp_path / "out.pdf"), "eng", 72, False, threading.Event(),
                     lambda v: None)
    assert doc.is_closed
    assert not (tmp_path / "out.pdf").exists()


def test_tesseract_is_found_in_its_install_folder_off_path(tmp_path, monkeypatch):
    exe = tmp_path / "pf" / "Tesseract-OCR" / "tesseract.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "pf"))
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(pytesseract.pytesseract, "tesseract_cmd", "tesseract")
    core.tesseract()
    assert pytesseract.pytesseract.tesseract_cmd == str(exe)
