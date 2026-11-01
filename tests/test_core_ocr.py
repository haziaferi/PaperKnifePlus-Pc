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
    calls = {"pages": 0, "modes": set()}

    def image_to_data(img, lang=None, output_type=None, **k):
        calls["lang"] = lang
        calls["pages"] += 1
        calls["modes"].add(img.mode)
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

    def image_to_osd(img, **k):
        calls["osd"] = calls.get("osd", 0) + 1
        calls["modes"].add(img.mode)
        return {"rotate": 0, "orientation_conf": 0.0}

    monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "5.0")
    monkeypatch.setattr(pytesseract, "image_to_data", image_to_data)
    monkeypatch.setattr(pytesseract, "image_to_osd", image_to_osd)
    return calls


def test_tesseract_is_given_the_page_in_grey(tmp_path, tess):
    """Measured 2026-11-01 on simulated scans (clean, faded, cream paper, shaded, blue
    ink, receipts): the grey page reads as many words as the colour one, 0.7-1.1 s a
    page sooner.  It is not contrast-stretched (ScanKnife+, question 8): see
    test_ocr_with_real_tesseract_reads_a_page_of_one_line."""
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    assert core.ocr_pdf(fitz.open(src), str(tmp_path / "out.pdf"), "eng", 72, False,
                        threading.Event(), lambda v: None) == 2
    assert tess["osd"] == 2 and tess["pages"] == 2
    assert tess["modes"] == {"L"}


def test_ocr_words_scales_to_page_space_and_keeps_every_word(tess):
    """The text layer is invisible: a dropped word cannot be found (ScanKnife+,
    question 4: the layer keeps every word)."""
    from PIL import Image
    img = Image.new("RGB", (1190, 1684), "white")      # a 595-pt page at 2x
    words = core.ocr_words(img, "eng", 2.0)
    assert [w.text for w in words] == ["Hello", "World", "faint"]
    assert tuple(words[0].rect) == pytest.approx((100, 200, 180, 220), abs=0.6)
    assert words[2].conf == 10


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
        assert "Page 1" in text and "Hello" in text and "faint" in text
    assert tess["osd"] == 2                       # orientation asked once a page


def test_ocr_pdf_text_only_makes_a4_text_pages(tmp_path, tess):
    src = make_pdf(tmp_path / "in.pdf", pages=2, width=300, height=300)
    out = tmp_path / "out.pdf"
    assert core.ocr_pdf(fitz.open(src), str(out), "eng", 72, True, threading.Event(),
                        lambda v: None) == 2
    with fitz.open(out) as d:
        assert len(d) == 2
        assert (round(d[0].rect.width), round(d[0].rect.height)) == (595, 842)
        text = d[1].get_text()
        # the words from 40 up (ScanKnife+, question 4), not the page's own text
        assert "Hello World" in text and "faint" not in text and "Page 2" not in text


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


@pytest.mark.parametrize("text, rect", [("Hello", (100, 200, 180, 220)),
                                        ("a", (300, 200, 306, 212)),
                                        ("Wonderfully", (100, 400, 400, 430))])
def test_a_layer_word_fills_its_box(text, rect):
    """ScanKnife+'s fit (2026-11-01): the word's height from the font's ascent to
    its descent, its length stretched to the box's, so a selection covers the
    printed word (before: 0.85 of the height, the font's own length)."""
    with fitz.open() as doc:
        page = doc.new_page()
        core.add_text_layer(page, [(fitz.Rect(rect), text)])
        (x0, y0, x1, y1, word, *_), = page.get_text("words")
    assert word == text
    w, h = rect[2] - rect[0], rect[3] - rect[1]
    assert abs(x0 - rect[0]) < 0.02 * w and abs(x1 - rect[2]) < 0.02 * w, (x0, x1)
    assert abs(y0 - rect[1]) < 0.05 * h and abs(y1 - rect[3]) < 0.05 * h, (y0, y1)


def test_a_page_read_turned_gets_its_words_where_they_are_printed(monkeypatch):
    """Orientation detection (ScanKnife+, question 5): Tesseract reads the page
    turned upright; each word goes back where the page shows it, running as its
    printed text does."""
    from PIL import Image
    seen = {}

    def image_to_data(img, lang=None, output_type=None, **k):
        seen["size"] = img.size          # one word at (10, 20)-(110, 40) of the upright image
        return {"text": ["Upright"], "conf": [95], "left": [10], "top": [20],
                "width": [100], "height": [20]}
    monkeypatch.setattr(pytesseract, "image_to_data", image_to_data)
    monkeypatch.setattr(pytesseract, "image_to_osd",
                        lambda img, **k: {"rotate": 90, "orientation_conf": 10.0})
    img = Image.new("RGB", (300, 500), "white")          # a 300 x 500 pt page at 1x
    turn = core.upright_turn(img)
    words = core.ocr_words(img, "eng", 1.0, turn)
    assert turn == 90 and seen["size"] == (500, 300)
    # the upright image is the page turned clockwise: its (u, v) is the page's (v, 500 - u)
    assert tuple(words[0].rect) == pytest.approx((20, 390, 40, 490))
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=500)
        core.add_text_layer(page, words, turn)
        (x0, y0, x1, y1, word, *_), = page.get_text("words")
        line = page.get_text("dict")["blocks"][0]["lines"][0]
    assert word == "Upright"
    assert (x0, y0, x1, y1) == pytest.approx((20, 390, 40, 490), abs=1.5)
    assert line["dir"] == pytest.approx((0, -1))         # bottom to top, as printed


@pytest.mark.parametrize("osd", [{"rotate": 180, "orientation_conf": 1.2},
                                 {"rotate": 45, "orientation_conf": 20.0},
                                 pytesseract.TesseractError(1, "Too few characters")],
                         ids=["unsure", "not a quarter turn", "refused"])
def test_orientation_turns_nothing_when_unsure_or_unable(monkeypatch, osd):
    from PIL import Image

    def image_to_osd(img, **k):
        if isinstance(osd, Exception):
            raise osd
        return osd
    monkeypatch.setattr(pytesseract, "image_to_osd", image_to_osd)
    assert core.upright_turn(Image.new("RGB", (10, 10))) == 0


def test_text_only_text_breaks_lines_and_blocks_and_leaves_out_doubtful_words():
    """ScanKnife+'s text: words on a line by spaces, lines by a line break, blocks
    by an empty line; words below 40 left out."""
    W, r = core.OcrWord, fitz.Rect(0, 0, 1, 1)
    words = [W(r, "One", 90, (1, 1, 1)), W(r, "two", 90, (1, 1, 1)), W(r, "junk", 39, (1, 1, 1)),
             W(r, "three", 90, (1, 1, 2)), W(r, "four", 90, (1, 2, 1)), W(r, "five", 40, (2, 1, 1))]
    assert core.words_text(words) == "One two\nthree\nfour\n\nfive"
