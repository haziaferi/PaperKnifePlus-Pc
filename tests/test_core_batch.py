"""paperknife.core.batch without any user interface: every operation, option
checks, password-protected inputs and Cancel."""
import threading

import pymupdf as fitz
import pytest

from conftest import make_pdf
from paperknife.core import batch as core
from paperknife.prefs import DPI_RANGE


def _locked(path):
    src = make_pdf(path.with_name("plain.pdf"), pages=1)
    with fitz.open(src) as d:
        d.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    return str(path)


def test_ops_are_the_four_batch_operations():
    assert list(core.OPS) == ["Compress", "Watermark", "OCR", "PDF → TXT"]


def test_validate_options_converts_numbers_in_place():
    opts = {"text": "X", "size": "48", "opacity": "0.5"}
    assert core.validate_options(opts) is opts
    assert opts == {"text": "X", "size": 48, "opacity": 0.5}
    lo, _ = DPI_RANGE
    assert core.validate_options({"lang": "eng", "dpi": str(lo)}) == {"lang": "eng", "dpi": lo}
    assert core.validate_options({"level": "light"}) == {"level": "light"}


@pytest.mark.parametrize("opts", [{"size": "big"}, {"size": "0"}, {"opacity": "0"},
                                  {"opacity": "1.5"}, {"dpi": "1"}, {"dpi": "150.5"}])
def test_validate_options_refuses_bad_values_with_the_message(opts):
    lo, hi = DPI_RANGE
    with pytest.raises(ValueError) as e:
        core.validate_options(opts)
    assert str(e.value) == (f"Size must be a positive whole number, DPI a whole number "
                            f"from {lo} to {hi}, opacity a number above 0 and up to 1.")



@pytest.mark.parametrize("text", ["", " " + chr(9) + " "])
def test_validate_options_refuses_an_empty_watermark_text(text):
    # R45-11: the Watermark page's own check, for the batch too.
    with pytest.raises(ValueError) as e:
        core.validate_options({"text": text, "size": "48", "opacity": "0.5"})
    assert str(e.value) == "Enter watermark text."


def test_open_input_refuses_a_password_protected_file(tmp_path):
    with pytest.raises(ValueError, match="password-protected"):
        core.open_input(_locked(tmp_path / "locked.pdf"))


@pytest.mark.parametrize("op,opts,name", [
    ("Compress", {"level": "light"}, "a_compressed.pdf"),
    ("Watermark", {"text": "BATCH MARK", "size": 40, "opacity": 0.3}, "a_watermarked.pdf"),
    ("PDF → TXT", {}, "a.txt"),
])
def test_each_operation_writes_its_output(tmp_path, op, opts, name):
    src = make_pdf(tmp_path / "a.pdf", pages=2)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    res = core.OPS[op](src, str(out_dir), opts, threading.Event())
    assert res == str(out_dir / name)
    if name.endswith(".txt"):
        text = (out_dir / name).read_text(encoding="utf-8")
        assert "Page 1" in text and "── Page Break ──" in text and "Page 2" in text
    else:
        with fitz.open(res) as d:
            assert d.page_count == 2
            if op == "Watermark":
                assert "BATCH MARK" in d[0].get_text()


def test_ocr_operation_adds_a_text_layer(tmp_path, monkeypatch):
    pytesseract = pytest.importorskip("pytesseract")
    monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "5.0")
    monkeypatch.setattr(pytesseract, "image_to_data", lambda img, lang=None, **k: {
        "text": ["", "HELLO"], "conf": [-1, 95], "left": [0, 100], "top": [0, 200],
        "width": [0, 150], "height": [0, 40]})
    src = make_pdf(tmp_path / "a.pdf", pages=1)
    res = core.OPS["OCR"](src, str(tmp_path), {"lang": "eng", "dpi": 72}, threading.Event())
    with fitz.open(res) as d:
        assert "HELLO" in d[0].get_text()


@pytest.mark.parametrize("op", ["Compress", "Watermark", "OCR", "PDF → TXT"])
def test_each_operation_cancelled_returns_none_and_writes_nothing(tmp_path, op):
    src = make_pdf(tmp_path / "a.pdf", pages=2)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    stop = threading.Event()
    stop.set()
    assert core.OPS[op](src, str(out_dir), {}, stop) is None
    assert list(out_dir.iterdir()) == []


# Where each operation does its per-page work, and the options it runs with.
_PER_PAGE_STEP = {
    "Compress": (fitz.Document, "rewrite_images", {"level": "medium"}),
    "Watermark": (fitz.Page, "insert_text", {}),
    "OCR": (core, "render", {"lang": "eng", "dpi": 72}),
    "PDF → TXT": (fitz.Page, "get_text", {}),
}


@pytest.mark.parametrize("op", [
    pytest.param("Compress", marks=pytest.mark.xfail(strict=True, reason=(
        "R6-37: _do_compress checks stop only on entry and compress_pdf takes no stop, "
        "so a Cancel that lands while a file is being compressed still writes its output"))),
    "Watermark", "OCR", "PDF → TXT"])
def test_each_operation_cancelled_mid_file_returns_none_and_writes_nothing(tmp_path, monkeypatch,
                                                                            op):
    # Cancel arrives while the file is being processed (after its first page
    # of three), the case that can leave a partial output behind.
    owner, name, opts = _PER_PAGE_STEP[op]
    real = getattr(owner, name)
    stop = threading.Event()
    calls = []

    def step_then_cancel(*a, **k):
        calls.append(1)
        try:
            return real(*a, **k)
        finally:
            stop.set()
    monkeypatch.setattr(owner, name, step_then_cancel)
    monkeypatch.setattr(core, "ocr_words", lambda img, lang, scale: [])
    src = make_pdf(tmp_path / "a.pdf", pages=3)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    assert core.OPS[op](src, str(out_dir), opts, stop) is None
    assert calls, "the per-page step never ran: the cancel did not land mid-file"
    assert list(out_dir.iterdir()) == []


@pytest.mark.parametrize("op", ["Compress", "Watermark", "OCR", "PDF → TXT"])
def test_each_operation_refuses_a_password_protected_input(tmp_path, op):
    with pytest.raises(ValueError, match="password-protected"):
        core.OPS[op](_locked(tmp_path / "locked.pdf"), str(tmp_path), {}, threading.Event())


def test_pdf_to_txt_operation_of_a_pdf_without_text_says_so(tmp_path):
    from paperknife.core.convert import NoText
    d = fitz.open()
    d.new_page()
    src = tmp_path / "scan.pdf"
    d.save(src)
    d.close()
    with pytest.raises(NoText):
        core.OPS["PDF → TXT"](str(src), str(tmp_path), {}, threading.Event())


def test_ocr_operation_without_tesseract_gives_the_install_hint(tmp_path, monkeypatch):
    pytesseract = pytest.importorskip("pytesseract")

    def missing(*a, **k):
        raise pytesseract.TesseractNotFoundError()
    monkeypatch.setattr(pytesseract, "get_tesseract_version", missing)
    monkeypatch.setattr(pytesseract, "image_to_data", missing)
    src = make_pdf(tmp_path / "a.pdf", pages=1)
    with pytest.raises(RuntimeError, match="Tesseract not found"):
        core.OPS["OCR"](src, str(tmp_path), {"lang": "eng", "dpi": 72}, threading.Event())
    assert not (tmp_path / "a_ocr.pdf").exists()
