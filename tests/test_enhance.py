"""Compress, batch, PDF tools, password, header/footer, crop and normalise."""
import io
import random
import re
import shutil
import tkinter as tk

import pymupdf as fitz
from PIL import Image

from conftest import make_pdf, tool, wait_job


def _image_pdf(path, pages=1):
    """Text plus a 1500 px noise image shown 300 pt wide (= 360 DPI)."""
    rnd = random.Random(1)
    im = Image.frombytes("RGB", (1500, 1500), rnd.randbytes(1500 * 1500 * 3))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    doc = fitz.open()
    for i in range(pages):
        p = doc.new_page()
        p.insert_image(fitz.Rect(72, 72, 372, 372), stream=buf.getvalue())
        p.insert_text((72, 500), f"Searchable text {i + 1}", fontsize=14)
    doc.save(str(path))
    doc.close()
    return str(path)


def _image_widths(path):
    with fitz.open(path) as doc:
        return [img[2] for img in doc[0].get_images(full=True)]


# ── Compress ────────────────────────────────────────────────────────────────

def _compress(app, dialogs, src, out, level):
    t = tool(app, "CompressTool")
    t._path.set(src)
    t._level.set(level)
    dialogs.save(out)
    t._run()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()


def test_compress_medium_resamples_images_and_keeps_text(app, dialogs, tmp_path):
    src = _image_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    _compress(app, dialogs, src, out, "medium")
    with fitz.open(out) as doc:
        assert "Searchable text 1" in doc[0].get_text()
    # 300 pt at 150 DPI = 625 px
    assert _image_widths(out) == [625]


def test_compress_aggressive_scales_images_to_96_dpi(app, dialogs, tmp_path):
    src = _image_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    _compress(app, dialogs, src, out, "aggressive")
    with fitz.open(out) as doc:
        assert "Searchable text 1" in doc[0].get_text()
    assert _image_widths(out) == [400]


def test_compress_never_reports_a_negative_saving(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=20)
    out = tmp_path / "out.pdf"
    _compress(app, dialogs, src, out, "medium")
    text = " ".join(m[2] for m in dialogs.msgs)
    assert not re.search(r"-\d+% smaller", text), text
    if out.stat().st_size >= (tmp_path / "in.pdf").stat().st_size:
        assert "smaller)" not in text, text


def test_compress_can_overwrite_its_input(app, dialogs, tmp_path):
    src = _image_pdf(tmp_path / "in.pdf")
    _compress(app, dialogs, src, src, "medium")
    assert _image_widths(src) == [625]


# ── Batch ───────────────────────────────────────────────────────────────────

def _batch(app, dialogs, tmp_path, op, **opts):
    in_dir, out_dir = tmp_path / "in", tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    _image_pdf(in_dir / "a.pdf")
    t = tool(app, "BatchTool")
    t._in_dir_var.set(str(in_dir))
    t._out_dir_var.set(str(out_dir))
    t._op.set(op)
    if op == "OCR":
        # The baseline's OCR options pane raised UnboundLocalError (PREFS);
        # set the option variables directly so this test isolates the worker.
        t._opt_widgets = {"lang": tk.StringVar(value="eng"),
                          "dpi": tk.StringVar(value="150")}
    else:
        t._op_changed(op)
    for k, v in opts.items():
        t._opt_widgets[k].set(v)
    t._run()
    wait_job(app)
    rows = list(t._lb.get(0, "end"))
    return out_dir, rows


def test_batch_watermark_is_diagonal_and_honours_opacity(app, dialogs, tmp_path):
    out_dir, rows = _batch(app, dialogs, tmp_path, "Watermark",
                           text="DRAFT COPY", opacity="0.4")
    assert rows and rows[0].startswith("✓"), rows
    with fitz.open(out_dir / "a_watermarked.pdf") as doc:
        page = doc[0]
        assert "DRAFT COPY" in page.get_text()
        gs = doc.xref_get_key(page.xref, "Resources/ExtGState")[1]
        assert [float(v) for v in re.findall(r"/ca\s*([\d.]+)", gs)] == [0.4]


def test_batch_compress_resamples_images_and_keeps_text(app, dialogs, tmp_path):
    out_dir, rows = _batch(app, dialogs, tmp_path, "Compress", level="medium")
    assert rows and rows[0].startswith("✓"), rows
    out = out_dir / "a_compressed.pdf"
    with fitz.open(out) as doc:
        assert "Searchable text 1" in doc[0].get_text()
    assert _image_widths(out) == [625]


def test_batch_ocr_writes_an_invisible_text_layer(app, dialogs, tmp_path, monkeypatch):
    import pytesseract
    # No Tesseract binary in the test environment: answer for it.
    monkeypatch.setattr(pytesseract, "image_to_string",
                        lambda img, lang=None, **k: "HELLO WORLD")
    monkeypatch.setattr(pytesseract, "image_to_data", lambda img, lang=None, **k: {
        "text": ["", "HELLO", "WORLD"], "conf": [-1, 95, 95], "left": [0, 100, 300],
        "top": [0, 200, 200], "width": [0, 150, 150], "height": [0, 40, 40]})
    out_dir, rows = _batch(app, dialogs, tmp_path, "OCR", dpi="150")
    assert rows and rows[0].startswith("✓"), rows
    with fitz.open(out_dir / "a_ocr.pdf") as doc:
        assert "HELLO" in doc[0].get_text()


def test_batch_ocr_options_pane_builds(app, dialogs):
    t = tool(app, "BatchTool")
    t._op_changed("OCR")
    assert set(t._opt_widgets) == {"lang", "dpi"}


def test_batch_rejects_bad_numeric_options_up_front(app, dialogs, tmp_path):
    out_dir, rows = _batch(app, dialogs, tmp_path, "Watermark", size="big")
    assert rows == [], rows
    assert any(m[0] == "showwarning" for m in dialogs.msgs), dialogs.msgs


# ── PDF Tools ───────────────────────────────────────────────────────────────

def test_pdftools_default_run_saves_without_errors(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    t = tool(app, "PdfToolsTool")
    t._path.set(src)
    dialogs.save(out)
    t._run()
    wait_job(app)
    assert [m for m in dialogs.msgs if m[0] != "showinfo"] == [], dialogs.msgs
    with fitz.open(out) as doc:
        assert doc.page_count == 3


def test_pdftools_offers_no_linearise_or_pdfa(app, dialogs, tmp_path):
    import customtkinter as ctk
    tool(app, "PdfToolsTool")
    radios, texts = [], []

    def walk(w):
        for c in w.winfo_children():
            if isinstance(c, ctk.CTkRadioButton):
                radios.append(c)
            if isinstance(c, ctk.CTkLabel):
                texts.append(c.cget("text"))
            walk(c)
    walk(app.main)
    assert radios == [], "a single operation needs no radio button"
    assert any(t.startswith("Repair") for t in texts), texts
    assert not any("Linear" in t or "PDF/A" in t for t in texts), texts


def test_pdftools_repair_recovers_a_truncated_file(app, dialogs, tmp_path):
    good = make_pdf(tmp_path / "good.pdf", pages=2)
    data = open(good, "rb").read()
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(data[: data.rfind(b"xref")])
    out = tmp_path / "out.pdf"
    t = tool(app, "PdfToolsTool")
    t._path.set(str(bad))
    dialogs.save(out)
    t._run()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    assert any("Repaired" in m[2] for m in dialogs.msgs), dialogs.msgs
    with fitz.open(out) as doc:
        assert not doc.is_repaired and doc.page_count == 2


# ── Password ────────────────────────────────────────────────────────────────

def _protect(app, dialogs, src, out, user="u", owner="", print_=True, copy=True):
    t = tool(app, "PasswordTool")
    t._path.set(src)
    t._pw1.insert(0, user)
    if owner:
        t._pw2.insert(0, owner)
    t._allow_print.select() if print_ else t._allow_print.deselect()
    t._allow_copy.select() if copy else t._allow_copy.deselect()
    dialogs.save(out)
    t._protect()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    return t


def test_password_allow_boxes_keep_unrelated_rights(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    _protect(app, dialogs, src, out, owner="o")
    with fitz.open(out) as doc:
        assert doc.authenticate("u")
        perm = doc.permissions
    for flag in ("PRINT", "PRINT_HQ", "COPY", "ACCESSIBILITY", "FORM", "ANNOTATE"):
        assert perm & getattr(fitz, "PDF_PERM_" + flag), flag


def test_password_unticked_print_removes_only_printing(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    _protect(app, dialogs, src, out, owner="o", print_=False)
    with fitz.open(out) as doc:
        doc.authenticate("u")
        perm = doc.permissions
    assert not perm & fitz.PDF_PERM_PRINT
    assert not perm & fitz.PDF_PERM_PRINT_HQ
    assert perm & fitz.PDF_PERM_COPY and perm & fitz.PDF_PERM_ACCESSIBILITY


def test_password_blank_owner_does_not_give_owner_rights(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    _protect(app, dialogs, src, out, copy=False)
    with fitz.open(out) as doc:
        # authenticate(): 2 = user rights, 4/6 = owner rights
        assert doc.authenticate("u") == 2


def test_password_change_on_an_encrypted_file(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf")
    first = tmp_path / "first.pdf"
    _protect(app, dialogs, src, first, user="old", owner="o")
    out = tmp_path / "second.pdf"
    t = tool(app, "PasswordTool")
    t._path.set(str(first))
    t._pw1.insert(0, "new")
    t._cur_pw.insert(0, "old")
    dialogs.save(out)
    t._protect()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        assert not doc.authenticate("old") and doc.authenticate("new")


# ── Header / Footer ─────────────────────────────────────────────────────────

def _stamp(app, dialogs, src, out, rng):
    t = tool(app, "HeaderFooterTool")
    t._path.set(src)
    t._page_range.insert(0, rng)
    dialogs.save(out)
    t._run()
    wait_job(app)
    return t


def test_headerfooter_accepts_capitalised_end(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=4)
    out = tmp_path / "out.pdf"
    _stamp(app, dialogs, src, out, "2-End")
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        stamped = ["of 4" in p.get_text() for p in doc]
    assert stamped == [False, True, True, True]


def test_headerfooter_overlapping_ranges_stamp_once(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=4)
    out = tmp_path / "out.pdf"
    _stamp(app, dialogs, src, out, "1-3, 2")
    with fitz.open(out) as doc:
        assert doc[1].get_text().count("Page 2 of 4") == 1


def test_headerfooter_bad_size_warns_instead_of_defaulting(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    t = tool(app, "HeaderFooterTool")
    t._path.set(src)
    t._size.delete(0, "end")
    t._size.insert(0, "abc")
    dialogs.save(out)
    t._run()
    wait_job(app)
    assert any(m[0] == "showwarning" for m in dialogs.msgs), dialogs.msgs
    assert not out.exists()


# ── Crop ────────────────────────────────────────────────────────────────────

def _crop(app, dialogs, src, out, rng="", **margins):
    t = tool(app, "CropTool")
    t._path.set(src)
    for k, v in margins.items():
        t._margins[k].set(str(v))
    if rng:
        t._page_range.insert(0, rng)
    dialogs.save(out)
    t._run()
    wait_job(app)
    return t


def test_crop_top_cuts_the_visible_top_of_a_rotated_page(app, dialogs, tmp_path):
    doc = fitz.open()
    doc.new_page().set_rotation(90)          # seen as 842 x 595
    doc.save(tmp_path / "in.pdf")
    doc.close()
    out = tmp_path / "out.pdf"
    _crop(app, dialogs, str(tmp_path / "in.pdf"), out, top=100)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        r = doc[0].rect
    assert (round(r.width), round(r.height)) == (842, 495)


def test_crop_overlapping_ranges_crop_once(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    out = tmp_path / "out.pdf"
    _crop(app, dialogs, src, out, rng="1-3, 2", top=50)
    with fitz.open(out) as doc:
        assert [round(p.rect.height) for p in doc] == [792, 792, 792]


def test_crop_negative_margin_is_refused_up_front(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"
    _crop(app, dialogs, src, out, top=-10)
    assert not dialogs.errors(), dialogs.errors()
    assert any(m[0] == "showwarning" for m in dialogs.msgs), dialogs.msgs


def test_crop_can_overwrite_its_input(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf")
    _crop(app, dialogs, src, src, top=50)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(src) as doc:
        assert round(doc[0].rect.height) == 792


# ── Normalise ───────────────────────────────────────────────────────────────

def test_normalise_stretch_fills_the_page(app, dialogs, tmp_path):
    doc = fitz.open()
    p = doc.new_page(width=200, height=800)
    p.draw_rect(p.rect, color=(1, 0, 0), fill=(1, 0, 0))
    doc.save(tmp_path / "in.pdf")
    doc.close()
    out = tmp_path / "out.pdf"
    t = tool(app, "NormaliseTool")
    t._path.set(str(tmp_path / "in.pdf"))
    t._scale.set("Stretch (fill page)")
    dialogs.save(out)
    t._run()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        pix = doc[0].get_pixmap(dpi=36)
    assert pix.pixel(2, pix.height // 2) == (255, 0, 0)


def test_watermark_can_overwrite_its_input(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf")
    copy = tmp_path / "copy.pdf"
    shutil.copy(src, copy)
    t = tool(app, "WatermarkTool")
    t._path.set(str(copy))
    t._text.insert(0, "OVER")
    dialogs.save(copy)
    t._run()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(copy) as doc:
        assert "OVER" in doc[0].get_text()
