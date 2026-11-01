"""The Qt OCR page: a single-file transform.  Tesseract is stubbed (as in
tests/test_convert.py) except for one test that needs the real binary and is
skipped when none is found."""
import html as _html

import pymupdf as fitz
import pytest

from qt_harness import make_pdf, pump, requires_tesseract, save_as, spy_open, wait_job

_WORDS = [  # (text, conf, left, top, width, height) in 72-dpi pixels
    ("Smith", 95, 100, 300, 50, 16),
    ("&", 90, 155, 300, 10, 16),
    ("don't", 92, 170, 300, 40, 16),
    ("Ελληνικά", 88, 220, 300, 70, 16),
    ("zzzq", 10, 300, 300, 40, 16),
]


@pytest.fixture
def tess(monkeypatch):
    import pytesseract
    calls = {"sizes": []}

    def scale_of(img):
        return img.size[0] / 595.0

    def image_to_data(img, lang=None, output_type=None, **k):
        calls["lang"] = lang
        calls["sizes"].append(img.size)
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

    def image_to_string(img, lang=None, **k):
        calls["lang"] = lang
        calls["sizes"].append(img.size)
        return "Plain OCR text"

    monkeypatch.setattr(pytesseract, "get_tesseract_version", lambda: "5.0")
    monkeypatch.setattr(pytesseract, "image_to_data", image_to_data)
    monkeypatch.setattr(pytesseract, "image_to_pdf_or_hocr", image_to_pdf_or_hocr)
    monkeypatch.setattr(pytesseract, "image_to_string", image_to_string)
    monkeypatch.setattr(pytesseract, "image_to_osd",
                        lambda img, **k: {"rotate": 0, "orientation_conf": 0.0})
    return calls


@pytest.fixture
def prefs(monkeypatch):
    from paperknife.prefs import PREFS
    monkeypatch.setitem(PREFS._data, "ocr_lang", "ita")
    monkeypatch.setitem(PREFS._data, "ocr_dpi", 250)
    return PREFS


def _page(window):
    assert window.open_tool("OCRTool")
    pump(0.05)
    return window.current_page()


def _source_pdf(path, rotation=0):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 120), "Original vector heading", fontsize=18, color=(0, 0, 1))
    page.draw_rect(fitz.Rect(72, 500, 300, 560), color=(1, 0, 0), width=2)
    page.set_rotation(rotation)
    doc.save(str(path))
    doc.close()
    return str(path)


def _run(window, dialogs, page, src, out):
    page.file.set_path(src)
    page.run()
    wait_job(window)
    save_as(window, dialogs, out)


def test_the_page_builds_with_the_ctk_defaults(window):
    page = _page(window)
    assert page.title_label.text() == "OCR"
    assert page.lang.text() == "eng"                # nothing chosen yet, no Windows language
    assert page.dpi.minimum() == 72 and page.dpi.maximum() == 400
    assert page.dpi.text() == f"{page.dpi.value()} DPI"
    page.dpi.setValue(123)
    assert page.dpi.text() == "123 DPI"
    assert page.text_only is False and page.run_button.isEnabled()


def test_without_a_file_it_warns(window, dialogs):
    page = _page(window)
    page.run()
    assert dialogs.msgs[-1] == ("warning", "OCR", "Select a PDF first.")
    assert not window._current_job


def test_ocr_overlay_keeps_original_page_and_adds_clean_text(window, dialogs, tmp_path, tess):
    page = _page(window)
    src = _source_pdf(tmp_path / "scan.pdf")
    out = tmp_path / "ocr.pdf"
    _run(window, dialogs, page, src, out)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(src) as a, fitz.open(out) as b:
        text = b[0].get_text()
        words = {w[4] for w in b[0].get_text("words")}
        assert {"Smith", "&", "don't", "Ελληνικά"} <= words, text
        # the invisible layer keeps every word (ScanKnife+, question 4, 2026-11-01)
        assert "zzzq" in words, text
        assert "Original vector heading" in text, "the original page content was replaced"
        assert not b[0].get_images(), "the page was rasterised"
        assert a[0].get_pixmap(alpha=False).samples == b[0].get_pixmap(alpha=False).samples
    assert not [m for m in dialogs.msgs if m[0] == "info"]
    assert window.applied_status == ("✓  OCR complete — 1 page(s) searchable · Save writes it "
                                     "to the file")
    assert page.log.text() == "✓  Done — 1 page(s) processed"


def test_ocr_overlay_places_words_on_rotated_page(window, dialogs, tmp_path, tess):
    page = _page(window)
    src = _source_pdf(tmp_path / "rot.pdf", rotation=90)
    out = tmp_path / "rot_ocr.pdf"
    _run(window, dialogs, page, src, out)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(src) as a, fitz.open(out) as b:
        pg = b[0]
        assert pg.rotation == 0
        smith = [w for w in pg.get_text("words") if w[4] == "Smith"]
        assert smith, pg.get_text()
        x0, y0, x1, y1 = smith[0][:4]
        sx = pg.rect.width / 595.0
        assert abs(x0 - 100 * sx) < 4 and abs(y1 - 316 * sx) < 6, smith
        assert a[0].get_pixmap(alpha=False).samples == pg.get_pixmap(alpha=False).samples


def test_ocr_uses_preferences_language_and_dpi(window, dialogs, tmp_path, tess, prefs):
    page = _page(window)
    assert page.lang.text() == "ita"
    assert page.dpi.value() == 250 and page.dpi.text() == "250 DPI"
    _run(window, dialogs, page, _source_pdf(tmp_path / "p.pdf"), tmp_path / "p_ocr.pdf")
    assert tess["lang"] == "ita"
    assert tess["sizes"] == [(round(595 * 250 / 72), round(842 * 250 / 72))]


def test_language_and_dpi_reach_tesseract(window, dialogs, tmp_path, tess):
    page = _page(window)
    page.lang.setText("deu+fra")
    page.dpi.setValue(144)
    _run(window, dialogs, page, _source_pdf(tmp_path / "p.pdf"), tmp_path / "o.pdf")
    assert tess["lang"] == "deu+fra" and tess["sizes"] == [(1190, 1684)]
    page.lang.setText("  ")                 # blank falls back to the last one used
    _run(window, dialogs, page, _source_pdf(tmp_path / "q.pdf"), tmp_path / "o2.pdf")
    assert tess["lang"] == "deu+fra"


def test_text_only_mode_writes_a4_text_pages(window, dialogs, tmp_path, tess):
    page = _page(window)
    page.modes["text"].setChecked(True)
    assert page.text_only is True
    out = tmp_path / "text.pdf"
    # a new file of plain text: the save dialog, and the document stays as it is
    page.file.set_path(make_pdf(tmp_path / "in.pdf", pages=2))
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    assert not window.document.dirty
    with fitz.open(out) as d:
        assert len(d) == 2
        # the words from 40 up (ScanKnife+, question 4), not Tesseract's own text
        assert all("Smith & don't" in p.get_text() and "zzzq" not in p.get_text() for p in d)
        assert "Page 2" not in d[1].get_text()
        assert (round(d[0].rect.width), round(d[0].rect.height)) == (595, 842)


def test_missing_tesseract_is_an_error_and_writes_nothing(window, dialogs, tmp_path,
                                                          monkeypatch):
    import pytesseract

    def missing():
        raise pytesseract.TesseractNotFoundError()
    monkeypatch.setattr(pytesseract, "get_tesseract_version", missing)
    page = _page(window)
    opened = spy_open(window, monkeypatch)
    out = tmp_path / "o.pdf"
    _run(window, dialogs, page, make_pdf(tmp_path / "in.pdf"), out)
    assert dialogs.errors() and "Tesseract not found" in dialogs.errors()[-1][2]
    assert opened and opened[-1].is_closed and not out.exists()  # the job's copy (the page holds its own)


def test_without_pytesseract_the_page_says_how_to_install_it(window, dialogs, monkeypatch,
                                                             tmp_path):
    from paperknife.core import ocr as core_ocr
    monkeypatch.setattr(core_ocr, "HAS_OCR", False)
    page = _page(window)
    assert page.missing is not None and not page.run_button.isEnabled()
    assert page.accept_drop(make_pdf(tmp_path / "in.pdf")) is False
    page.run()
    assert not dialogs.msgs and not window._current_job


def test_a_dropped_pdf_is_taken_and_others_are_refused(window, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf")
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False and page.file.path() == ""
    assert page.accept_drop(src) is True and page.file.path() == src


def test_text_only_cancelled_at_the_save_dialog_closes_its_copy(window, dialogs, tmp_path,
                                                                monkeypatch):
    page = _page(window)
    page.modes["text"].setChecked(True)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    opened = spy_open(window, monkeypatch)
    page.run()                     # no save path queued: the dialog returns ""
    assert opened and opened[0].is_closed
    assert not window._current_job


def test_leaving_the_tool_leaves_no_document_open(window, dialogs, tmp_path, tess, monkeypatch):
    page = _page(window)
    opened = spy_open(window, monkeypatch)
    _run(window, dialogs, page, make_pdf(tmp_path / "in.pdf"), tmp_path / "o.pdf")
    assert window.show_page("home")
    # the jobs' copies are closed; the window keeps the one document (2026-10-23)
    shared = window.document.doc
    assert opened and all(d.is_closed for d in opened if d is not shared)
    assert shared is not None and not shared.is_closed


@requires_tesseract
def test_ocr_with_real_tesseract_makes_an_image_only_page_searchable(window, dialogs, tmp_path):
    with fitz.open() as text_doc, fitz.open() as img:
        p = text_doc.new_page()
        p.insert_text((72, 120), "Invoice quarterly statement", fontsize=22)
        img.new_page(width=p.rect.width, height=p.rect.height).insert_image(
            p.rect, pixmap=p.get_pixmap(dpi=200))
        img.save(tmp_path / "image_only.pdf")
    page = _page(window)
    out = tmp_path / "real_ocr.pdf"
    _run(window, dialogs, page, str(tmp_path / "image_only.pdf"), out)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        for word in ("Invoice", "quarterly", "statement"):
            assert doc[0].search_for(word), (word, doc[0].get_text())


@requires_tesseract
def test_ocr_with_real_tesseract_reads_a_page_scanned_upside_down(window, dialogs, tmp_path):
    """ScanKnife+'s orientation detection (2026-11-01): an upside-down scan is read
    upright and its words go where the page shows them (before: junk)."""
    import io

    from PIL import Image
    prose = "The quarterly statement lists every invoice paid this month. " * 14
    with fitz.open() as text_doc, fitz.open() as img:
        p = text_doc.new_page()
        assert p.insert_textbox(fitz.Rect(72, 72, 523, 770), prose, fontsize=13) >= 0
        w, h = p.rect.width, p.rect.height
        truth = [fitz.Rect(w - r.x1, h - r.y1, w - r.x0, h - r.y0)     # turned 180 degrees
                 for r in p.search_for("statement")]
        pix = p.get_pixmap(dpi=200)
        im = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        buf = io.BytesIO()
        im.transpose(Image.Transpose.ROTATE_180).save(buf, "PNG")
        img.new_page(width=w, height=h).insert_image(p.rect, stream=buf.getvalue())
        img.save(tmp_path / "upside_down.pdf")
    page = _page(window)
    out = tmp_path / "real_ocr.pdf"
    _run(window, dialogs, page, str(tmp_path / "upside_down.pdf"), out)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        hits = doc[0].search_for("statement")
    assert len(hits) >= len(truth) - 1, (len(hits), len(truth))
    for hit in hits:            # Tesseract's box is the ink's, inside the font's full box
        c = (hit.tl + hit.br) / 2
        assert any(c in t for t in truth), hit


def test_the_language_starts_from_windows_then_the_last_one_used(window, dialogs, tmp_path,
                                                                 tess, ocr_languages):
    """Owner, 2026-10-22: Windows' display language the first time (when installed),
    the last one used after that."""
    from paperknife.prefs import PREFS
    PREFS._data["ocr_lang"] = ""
    ocr_languages["windows"] = "ita"
    page = _page(window)
    assert page.lang.text() == "ita"
    assert page.lang.button.text() == "Italian"
    page.lang.setText("fra+eng")
    _run(window, dialogs, page, _source_pdf(tmp_path / "p.pdf"), tmp_path / "o.pdf")
    assert tess["lang"] == "fra+eng"
    assert PREFS.ocr_lang == "fra+eng"                       # remembered
    from paperknife.qt.pages import LanguagePicker
    assert LanguagePicker().text() == "fra+eng"              # the next picker starts there


def test_windows_language_not_installed_starts_in_english(window, ocr_languages):
    from paperknife.prefs import PREFS
    PREFS._data["ocr_lang"] = ""
    ocr_languages["windows"] = "jpn"
    assert _page(window).lang.text() == "eng"


def test_the_picker_ticks_in_order_and_keeps_one(window):
    from paperknife.qt.pages import LanguagePicker
    from qt_harness import pump
    p = LanguagePicker("ita")
    acts = p.actions_by_code
    assert set(acts) == {"deu", "eng", "fra", "ita"}         # the installed ones
    assert list(acts)[0] == "ita"                            # the chosen first
    acts["eng"].setChecked(True)
    pump(0.05)
    assert p.text() == "ita+eng" and p.button.toolTip() == "Italian + English"
    # shortened at the end when it does not fit (the offscreen font is wider)
    assert "Italian + English".startswith(p.button.text().rstrip("…"))
    assert p.chosen()
    p.actions_by_code["ita"].setChecked(False)
    pump(0.05)
    assert p.text() == "eng"
    p.actions_by_code["eng"].setChecked(False)                # the last one stays
    pump(0.05)
    assert p.text() == "eng" and p.actions_by_code["eng"].isChecked()


def test_a_saved_language_not_installed_stays_listed(window):
    from paperknife.qt.pages import LanguagePicker
    p = LanguagePicker("lat+eng")
    assert p.text() == "lat+eng" and "lat" in p.actions_by_code
