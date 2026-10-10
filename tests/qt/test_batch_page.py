"""The Qt Batch page: one operation applied to every PDF in a folder (group D)."""
import re
from pathlib import Path

import pymupdf as fitz
import pytest

from qfluentwidgets import PushButton
from qt_harness import image_pdf, make_pdf, pump, requires_tesseract, wait_job


def _image_widths(path):
    with fitz.open(path) as doc:
        return [img[2] for img in doc[0].get_images(full=True)]


def _page(window):
    assert window.open_tool("BatchTool")
    pump(0.05)
    return window.current_page()


def _folders(tmp_path):
    in_dir, out_dir = tmp_path / "in", tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    return in_dir, out_dir


def _setup(page, in_dir, out_dir, op):
    """Set the folders and the operation (nothing runs yet)."""
    page._set_in_dir(str(in_dir))
    page._set_out_dir(str(out_dir))
    page.op.setCurrentText(op)
    pump(0.02)
    return page


def _watch_end(page):
    """The rows' notes as a finished batch left them, read just before the
    list and its input folder empty (owner's decision 2026-10-10: a finished
    job clears a collection); the list stays empty when nothing finished."""
    seen = []
    real = page.clear_document

    def spy():
        seen.append([r.note.text() for r in page.rows])
        real()
    page.clear_document = spy
    return seen


def _go(window, page):
    """Run; the per-file notes the batch posted (a finished batch then shows
    an empty list and no input folder)."""
    seen = _watch_end(page)
    page.run()
    wait_job(window)
    del page.clear_document
    if seen:
        assert page.rows == [] and page.in_dir == ""
        return seen[0]
    return [r.note.text() for r in page.rows]


# ── build and empty input ────────────────────────────────────────────────────

def test_the_page_builds_as_a_folder_collection(window):
    from paperknife.core.batch import OPS
    page = _page(window)
    assert type(page).__name__ == "BatchPage" and page.title_label.text() == "Batch"
    assert page.add_btn is None and page.remove_btn is None      # toolbar=False
    assert [page.op.itemText(i) for i in range(page.op.count())] == list(OPS)
    assert page.op.currentText() == "Compress" and set(page.controls) == {"level"}
    assert page.in_label.text() == "Not set…" and page.out_label.text() == "Not set…"


def test_without_folders_it_warns(window, dialogs):
    page = _page(window)
    page.run()
    assert dialogs.msgs[-1] == ("warning", "Batch", "Set input and output folders.")


def test_an_input_folder_without_pdfs_warns(window, dialogs, tmp_path):
    in_dir, out_dir = _folders(tmp_path)
    (in_dir / "notes.txt").write_text("x", encoding="utf-8")
    page = _setup(_page(window), in_dir, out_dir, "Compress")
    page.run()
    assert dialogs.msgs[-1] == ("warning", "Batch", "No PDF files found in input folder.")
    assert window._current_job is None


# ── folders and the list ─────────────────────────────────────────────────────

def test_browse_fills_the_list_with_the_folders_pdfs_and_cancel_keeps_it(window, dialogs,
                                                                         tmp_path):
    in_dir, out_dir = _folders(tmp_path)
    make_pdf(in_dir / "b.pdf", pages=1)
    make_pdf(in_dir / "a.pdf", pages=1)
    (in_dir / "c.txt").write_text("x", encoding="utf-8")
    page = _page(window)
    dialogs.dirs.append(str(in_dir))
    page.open()                                      # Ctrl+O chooses the input folder
    assert page.in_dir == str(in_dir) and page.in_label.text() == str(in_dir)
    assert [Path(p).name for p in page.paths()] == ["a.pdf", "b.pdf"]
    page._pick_dir("Choose input folder", page._set_in_dir)   # dialog cancelled
    assert page.in_dir == str(in_dir) and len(page.rows) == 2
    dialogs.dirs.append(str(out_dir))
    page._pick_dir("Choose output folder", page._set_out_dir)
    assert page.out_dir == str(out_dir) and page.out_label.text() == str(out_dir)


def test_a_dropped_folder_is_taken_and_files_are_refused(window, tmp_path):
    in_dir, _ = _folders(tmp_path)
    pdf = make_pdf(in_dir / "a.pdf", pages=1)
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    page = _page(window)
    assert page.accept_drop(str(other)) is False
    assert page.accept_drop(pdf) is False            # Batch works on a folder
    assert page.rows == [] and page.in_dir == ""
    assert window.forward_drop([str(in_dir)]) == 1
    assert page.in_dir == str(in_dir) and page.paths() == [pdf]


def test_changing_the_operation_rebuilds_its_options(window):
    page = _page(window)
    for op, keys in (("Watermark", {"text", "size", "opacity"}), ("OCR", {"lang", "dpi"}),
                     ("PDF → TXT", set()), ("Compress", {"level"})):
        page.op.setCurrentText(op)
        pump(0.02)
        assert set(page.controls) == keys, op
        assert set(page.options()) == keys, op


# ── Compress ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("level,width", [("light", 1500), ("medium", 625), ("aggressive", 400)])
def test_batch_compress_resamples_images_by_level_and_keeps_text(window, dialogs, tmp_path,
                                                                 level, width):
    in_dir, out_dir = _folders(tmp_path)
    image_pdf(in_dir / "a.pdf")
    page = _setup(_page(window), in_dir, out_dir, "Compress")
    page.radios[level].setChecked(True)
    assert page.options() == {"level": level}
    notes = _go(window, page)
    assert notes == ["✓  a.pdf"], notes
    assert not dialogs.errors(), dialogs.errors()
    out = out_dir / "a_compressed.pdf"
    with fitz.open(out) as doc:
        assert "Searchable text 1" in doc[0].get_text()
    assert _image_widths(out) == [width]
    assert window.status_text() == "✓  Batch done — 1 OK, 0 errors"
    assert window.status_role == "success"


# ── Watermark ────────────────────────────────────────────────────────────────

def test_batch_watermark_is_diagonal_and_honours_text_and_opacity(window, dialogs, tmp_path):
    in_dir, out_dir = _folders(tmp_path)
    make_pdf(in_dir / "a.pdf", pages=1)
    page = _setup(_page(window), in_dir, out_dir, "Watermark")
    page.controls["text"].setText("DRAFT COPY")
    page.controls["opacity"].setValue(40)
    notes = _go(window, page)
    assert notes == ["✓  a.pdf"], notes
    with fitz.open(out_dir / "a_watermarked.pdf") as doc:
        pg = doc[0]
        assert "DRAFT COPY" in pg.get_text()
        gs = doc.xref_get_key(pg.xref, "Resources/ExtGState")[1]
        assert [float(v) for v in re.findall(r"/ca\s*([\d.]+)", gs)] == [0.4]
        dirs = [ln["dir"] for b in pg.get_text("dict")["blocks"] for ln in b.get("lines", [])
                if any("DRAFT" in s["text"] for s in ln["spans"])]
        assert dirs and all(abs(abs(dx) - abs(dy)) < 0.01 and dx and dy for dx, dy in dirs)



@pytest.mark.parametrize("text", ["", "   "])
def test_batch_watermark_refuses_empty_text_up_front(window, dialogs, tmp_path, text):
    # R45-11: an empty text wrote unchanged copies reported ✓; the single-file
    # Watermark page refuses it with "Enter watermark text.".
    in_dir, out_dir = _folders(tmp_path)
    make_pdf(in_dir / "a.pdf", pages=1)
    page = _setup(_page(window), in_dir, out_dir, "Watermark")
    page.controls["text"].setText(text)
    page.run()
    wait_job(window)
    assert dialogs.warnings() == [("warning", "Batch", "Enter watermark text.")]
    assert list(out_dir.iterdir()) == []


def _stamp_size(path):
    with fitz.open(path) as doc:
        return max(s["size"] for b in doc[0].get_text("dict")["blocks"]
                   for ln in b.get("lines", []) for s in ln["spans"] if "DRAFT" in s["text"])


def test_batch_watermark_size_sets_the_font_size(window, dialogs, tmp_path):
    sizes = []
    for n, size in enumerate((20, 50)):
        in_dir, out_dir = tmp_path / f"in{n}", tmp_path / f"out{n}"
        in_dir.mkdir()
        out_dir.mkdir()
        make_pdf(in_dir / "a.pdf", pages=1)
        page = _setup(_page(window), in_dir, out_dir, "Watermark")
        page.controls["size"].setValue(size)
        assert _go(window, page) == ["✓  a.pdf"]
        sizes.append(_stamp_size(out_dir / "a_watermarked.pdf"))
    assert sizes[0] == pytest.approx(20, abs=0.5) and sizes[1] == pytest.approx(50, abs=0.5)


# ── options checked up front ─────────────────────────────────────────────────

def test_batch_rejects_bad_numeric_options_up_front(window, dialogs, tmp_path, monkeypatch):
    in_dir, out_dir = _folders(tmp_path)
    make_pdf(in_dir / "a.pdf", pages=1)
    page = _setup(_page(window), in_dir, out_dir, "Watermark")
    opts = page.options()
    monkeypatch.setattr(page, "options", lambda: dict(opts, size="big"))
    page.run()
    wait_job(window)
    assert [r.note.text() for r in page.rows] == [""]
    assert window._current_job is None and not list(out_dir.iterdir())
    assert dialogs.msgs[-1][0] == "warning" and "Size must be" in dialogs.msgs[-1][2]


def test_batch_dpi_is_kept_inside_the_settings_range(window, dialogs, tmp_path, monkeypatch):
    from paperknife.prefs import DPI_RANGE
    in_dir, out_dir = _folders(tmp_path)
    make_pdf(in_dir / "a.pdf", pages=1)
    page = _setup(_page(window), in_dir, out_dir, "OCR")
    page.controls["dpi"].setValue(5000)              # the control stops at the range
    assert page.options()["dpi"] == DPI_RANGE[1]
    opts = page.options()
    monkeypatch.setattr(page, "options", lambda: dict(opts, dpi=5000))
    page.run()
    wait_job(window)
    assert window._current_job is None
    assert dialogs.msgs[-1][0] == "warning" and "600" in dialogs.msgs[-1][2]


# ── OCR ──────────────────────────────────────────────────────────────────────

def test_batch_ocr_options_reach_the_worker(window, dialogs, tmp_path, monkeypatch):
    from paperknife.core import batch
    seen = []
    monkeypatch.setitem(batch.OPS, "OCR",
                        lambda src, out, opts, stop: seen.append(dict(opts)) or "x")
    in_dir, out_dir = _folders(tmp_path)
    make_pdf(in_dir / "a.pdf", pages=1)
    page = _setup(_page(window), in_dir, out_dir, "OCR")
    page.controls["lang"].setText("  ita ")
    page.controls["dpi"].setValue(200)
    assert _go(window, page) == ["✓  a.pdf"]
    assert seen == [{"lang": "ita", "dpi": 200}]


def test_batch_ocr_writes_an_invisible_text_layer(window, dialogs, tmp_path, monkeypatch):
    import pytesseract
    # Answer for Tesseract, as the CTk test does, so this checks the worker alone.
    monkeypatch.setattr(pytesseract, "image_to_data", lambda img, lang=None, **k: {
        "text": ["", "HELLO", "WORLD"], "conf": [-1, 95, 95], "left": [0, 100, 300],
        "top": [0, 200, 200], "width": [0, 150, 150], "height": [0, 40, 40]})
    in_dir, out_dir = _folders(tmp_path)
    image_pdf(in_dir / "a.pdf")
    page = _setup(_page(window), in_dir, out_dir, "OCR")
    page.controls["dpi"].setValue(150)
    assert _go(window, page) == ["✓  a.pdf"]
    with fitz.open(out_dir / "a_ocr.pdf") as doc:
        assert "HELLO" in doc[0].get_text()
        # Invisible: every OCR span is drawn in render mode 3 (no fill, no stroke).
        ocr = [t for t in doc[0].get_texttrace()
               if any(w in "".join(chr(c[0]) for c in t["chars"]) for w in ("HELLO", "WORLD"))]
        assert ocr and {t["type"] for t in ocr} == {3}, [t["type"] for t in ocr]


@requires_tesseract
def test_batch_ocr_end_to_end_makes_a_scan_searchable(window, dialogs, tmp_path):
    in_dir, out_dir = _folders(tmp_path)
    src = fitz.open()
    src.new_page().insert_text((72, 120), "INVOICE NUMBER", fontsize=28)
    pix = src[0].get_pixmap(dpi=150)
    src.close()
    scan = fitz.open()
    scan.new_page().insert_image(scan[0].rect, stream=pix.tobytes("png"))
    scan.save(str(in_dir / "scan.pdf"))
    scan.close()
    page = _setup(_page(window), in_dir, out_dir, "OCR")
    page.controls["lang"].setText("eng")
    page.controls["dpi"].setValue(150)
    assert _go(window, page) == ["✓  scan.pdf"]
    with fitz.open(out_dir / "scan_ocr.pdf") as doc:
        assert "INVOICE" in doc[0].get_text().upper()


# ── PDF → TXT ────────────────────────────────────────────────────────────────

def test_batch_pdf_to_txt_writes_each_files_text(window, dialogs, tmp_path):
    in_dir, out_dir = _folders(tmp_path)
    make_pdf(in_dir / "a.pdf", pages=2)
    make_pdf(in_dir / "b.pdf", pages=1, text="Bee {n}")
    page = _setup(_page(window), in_dir, out_dir, "PDF → TXT")
    assert page.controls == {}
    assert _go(window, page) == ["✓  a.pdf", "✓  b.pdf"]
    a = (out_dir / "a.txt").read_text(encoding="utf-8")
    assert "Page 1" in a and "Page 2" in a and "── Page Break ──" in a
    assert "Bee 1" in (out_dir / "b.txt").read_text(encoding="utf-8")
    assert window.status_text() == "✓  Batch done — 2 OK, 0 errors"


# ── results: errors and cancel ───────────────────────────────────────────────

def test_a_failing_file_is_reported_on_its_row_and_the_rest_run(window, dialogs, tmp_path):
    in_dir, out_dir = _folders(tmp_path)
    make_pdf(in_dir / "a.pdf", pages=1)
    make_pdf(in_dir / "b.pdf", pages=1, password="pw")
    page = _setup(_page(window), in_dir, out_dir, "PDF → TXT")
    notes = _go(window, page)
    assert notes[0] == "✓  a.pdf"
    assert notes[1].startswith("✗  b.pdf  — password-protected"), notes
    assert window.status_text() == "⚠  Batch done — 1 OK, 1 errors"
    assert window.status_role == "warning"


def test_cancelled_batch_does_not_report_success(window, dialogs, tmp_path, monkeypatch):
    from paperknife.core import batch       # the worker looks compress_pdf up here
    in_dir, out_dir = _folders(tmp_path)
    for n in "abc":
        make_pdf(in_dir / f"{n}.pdf", pages=1)

    def compress_then_cancel(doc, out, level, stop=None):
        # This file finished compressing just before Cancel was pressed.
        doc.close()
        Path(out).write_bytes(b"%PDF-1.7")
        window._cancel_job()
        return True
    monkeypatch.setattr(batch, "compress_pdf", compress_then_cancel)
    page = _setup(_page(window), in_dir, out_dir, "Compress")
    notes = _go(window, page)
    status = window.status_text()
    assert "cancel" in status.lower() and "✓" not in status, status
    assert status == "⚠  Batch cancelled after 1 of 3 file(s) — 1 OK, 0 errors"
    assert notes == ["✓  a.pdf", "", ""], notes


def test_leaving_the_tool_mid_way_keeps_the_page_usable(window, dialogs, tmp_path, monkeypatch):
    # Batch opens no document of its own (each worker opens and closes its
    # file): leaving while a batch runs and coming back keeps the folders, the
    # list and every result the batch posts meanwhile, and nothing fails.
    import threading
    from paperknife.core import batch as core
    in_dir, out_dir = _folders(tmp_path)
    for n in "ab":
        make_pdf(in_dir / f"{n}.pdf", pages=1)
    real = core.OPS["PDF → TXT"]
    started, release = threading.Event(), threading.Event()

    def held(src, out, opts, stop):
        started.set()
        assert release.wait(10)
        return real(src, out, opts, stop)
    monkeypatch.setitem(core.OPS, "PDF → TXT", held)
    page = _setup(_page(window), in_dir, out_dir, "PDF → TXT")
    seen = _watch_end(page)
    page.run()
    assert started.wait(5) and window.job_running()
    assert window.open_tool("CompressTool")
    pump(0.05)
    assert window.job_running(), "leaving the page stopped the batch"
    assert window.open_tool("BatchTool")
    pump(0.05)
    assert window.current_page() is page and page.in_dir == str(in_dir)
    release.set()
    wait_job(window)
    del page.clear_document
    assert seen == [["✓  a.pdf", "✓  b.pdf"]]
    assert page.rows == [] and page.in_dir == ""            # finished: the list empties
    assert (out_dir / "a.txt").exists() and (out_dir / "b.txt").exists()
    assert window.status_text() == "✓  Batch done — 2 OK, 0 errors"
    assert not dialogs.errors(), dialogs.errors()
    page._set_in_dir(str(in_dir))
    assert _go(window, page) == ["✓  a.pdf", "✓  b.pdf"]      # and it still runs


def test_run_or_a_new_folder_during_a_batch_keeps_its_results(window, dialogs, tmp_path,
                                                              monkeypatch):
    # R45-10: Run Batch (or Ctrl+O / a dropped folder) during a batch wiped
    # the rows with their notes, then said Busy; later notes were dropped.
    import threading
    from paperknife.core import batch as core
    in_dir, out_dir = _folders(tmp_path)
    for n in "abc":
        make_pdf(in_dir / f"{n}.pdf", pages=1)
    other = tmp_path / "other"
    other.mkdir()
    make_pdf(other / "z.pdf", pages=1)
    release, first = threading.Event(), threading.Event()

    def slow(src, out_dir, opts, stop):
        first.set()
        if src.endswith("b.pdf"):
            release.wait(10)
        return True
    monkeypatch.setitem(core.OPS, "PDF → TXT", slow)
    page = _setup(_page(window), in_dir, out_dir, "PDF → TXT")
    seen = _watch_end(page)
    page.run()
    assert first.wait(5)
    for _ in range(50):
        pump(0.02)
        if page.rows[0].note.text() == "✓  a.pdf":
            break
    rows = list(page.rows)
    page.run()
    dialogs.dirs.append(str(other))
    page.open()
    assert page.accept_drop(str(other)) is True
    dialogs.dirs.append(str(other))
    browse = [b for b in page.findChildren(PushButton) if b.text() == "Browse…"][0]
    browse.click()                       # the input folder's Browse
    assert page.rows == rows and page.in_dir == str(in_dir)
    assert [m[1] for m in dialogs.warnings()] == ["Busy"] * 4
    release.set()
    wait_job(window)
    del page.clear_document
    assert seen == [["✓  a.pdf", "✓  b.pdf", "✓  c.pdf"]]
