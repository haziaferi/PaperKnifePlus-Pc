"""The Batch prototypes (owner, 2026-10-18; env PK_BATCH): B gives Compress,
Watermark, OCR and PDF → Other a folder input and drops Batch; C gives Batch
each tool's full settings.  A (the default) is tests/qt/test_batch_page.py."""
import zipfile

import pymupdf as fitz
import pytest

from conftest import close_test_window
from qt_harness import make_pdf, pump, wait_job


@pytest.fixture
def proto(qapp, dialogs, monkeypatch):
    """make(mode): a MainWindow built with PK_BATCH=mode."""
    from PySide6.QtCore import QPoint
    made = []

    def make(mode):
        monkeypatch.setenv("PK_BATCH", mode)
        from paperknife.qt.shell import MainWindow
        w = MainWindow()
        w.move(0, 0)
        w.pointer_at = QPoint(w.width() // 2, w.height() // 2)
        w._pointer = lambda: w.mapToGlobal(w.pointer_at)
        w.show()
        pump(0.05)
        made.append(w)
        return w
    yield make
    for w in made:
        if w._current_job is not None and w._current_job.is_running:
            w._current_job.cancel()
            wait_job(w)
        close_test_window(w)


def _folders(tmp_path, n=2):
    inp, out = tmp_path / "in", tmp_path / "out"
    inp.mkdir()
    out.mkdir()
    for i in range(n):
        make_pdf(inp / f"f{i}.pdf", pages=2)
    return inp, out


# ── C ──
def test_c_batch_offers_the_four_tools_with_their_own_settings(proto):
    w = proto("C")
    assert w.open_tool("BatchTool")
    page = w.current_page()
    assert list(page.tool_radios) == ["compress", "watermark", "ocr", "other"]
    assert not hasattr(page, "op")
    shown = {k: p.box.isVisibleTo(page) for k, p in page.panels.items()}
    assert shown == {"compress": True, "watermark": False, "ocr": False, "other": False}
    page.tool_radios["watermark"].click()
    assert page.panels["watermark"].box.isVisibleTo(page)
    assert not page.panels["compress"].box.isVisibleTo(page)
    # The full settings: Watermark has its colour, OCR its text-only mode.
    assert hasattr(page.panels["watermark"], "pick_button")
    assert "text" in page.panels["ocr"].modes


def test_c_watermark_a_folder_in_the_chosen_colour(proto, dialogs, tmp_path):
    w = proto("C")
    w.open_tool("BatchTool")
    page = w.current_page()
    inp, out = _folders(tmp_path)
    page._set_in_dir(str(inp))
    page._set_out_dir(str(out))
    page.tool_radios["watermark"].click()
    wm = page.panels["watermark"]
    wm.text.setText("SECRET")
    wm.color = (255, 0, 0)
    page.run()
    wait_job(w)
    assert not dialogs.errors() and not dialogs.warnings(), dialogs.msgs
    made = sorted(p.name for p in out.iterdir())
    assert made == ["f0_watermarked.pdf", "f1_watermarked.pdf"]
    with fitz.open(out / "f0_watermarked.pdf") as d:
        spans = [s for b in d[0].get_text("dict")["blocks"] for ln in b.get("lines", [])
                 for s in ln["spans"] if "SECRET" in s["text"]]
        assert spans and spans[0]["color"] == 0xFF0000


def test_c_pdf_to_other_png_for_a_folder(proto, dialogs, tmp_path):
    w = proto("C")
    w.open_tool("BatchTool")
    page = w.current_page()
    inp, out = _folders(tmp_path, n=1)
    page._set_in_dir(str(inp))
    page._set_out_dir(str(out))
    page.tool_radios["other"].click()
    page.panels["other"].fmt.setCurrentText("PNG")
    page.run()
    wait_job(w)
    assert not dialogs.errors(), dialogs.errors()
    with zipfile.ZipFile(out / "f0_png.zip") as zf:
        assert zf.namelist() == ["page_0001.png", "page_0002.png"]


def test_c_an_empty_watermark_text_is_refused(proto, dialogs, tmp_path):
    w = proto("C")
    w.open_tool("BatchTool")
    page = w.current_page()
    inp, out = _folders(tmp_path, n=1)
    page._set_in_dir(str(inp))
    page._set_out_dir(str(out))
    page.tool_radios["watermark"].click()
    page.run()
    assert dialogs.msgs[-1] == ("warning", "Batch", "Enter watermark text.")
    assert list(out.iterdir()) == []


# ── B ──
def test_b_has_no_batch_screen(proto):
    w = proto("B")
    assert "BatchTool" not in w._labels


@pytest.mark.parametrize("tool", ["CompressTool", "WatermarkTool", "OCRTool", "Pdf2DocTool"])
def test_b_each_tool_switches_to_a_folder_and_back(proto, tmp_path, tool):
    w = proto("B")
    assert w.open_tool(tool, make_pdf(tmp_path / "in.pdf"))
    page = w.current_page()
    fm = page.__dict__.get("_folder_mode")
    if fm is None:
        pytest.skip("no OCR engine: the page only says how to get it")
    fm.set_folder(True)
    pump(0.05)
    assert fm.folder.isVisibleTo(page) and not fm.centre.isVisibleTo(page)
    assert not page.doc_bar.open_control.isVisibleTo(page)
    assert all(b.isEnabled() for b in page._buttons if b.pk_primary)
    fm.set_folder(False)
    pump(0.05)
    assert not fm.folder.isVisibleTo(page) and fm.centre.isVisibleTo(page) is (tool != "CompressTool")
    assert page.doc_bar.open_control.isVisibleTo(page)


def test_b_compress_a_folder_with_the_tools_own_level(proto, dialogs, tmp_path):
    w = proto("B")
    w.open_tool("CompressTool")
    page = w.current_page()
    inp, out = _folders(tmp_path)
    fm = page._folder_mode
    assert page.accept_drop(str(inp)) and fm.on and fm.folder.in_dir == str(inp)
    assert [r.path for r in fm.folder.rows] == [str(inp / "f0.pdf"), str(inp / "f1.pdf")]
    fm.folder.set_out_dir(str(out))
    page.radios["light"].click()
    page.run()
    wait_job(w)
    assert not dialogs.errors() and not dialogs.warnings(), dialogs.msgs
    assert sorted(p.name for p in out.iterdir()) == ["f0_compressed.pdf", "f1_compressed.pdf"]
    assert fm.folder.rows == []                     # a finished batch empties the list


def test_b_pdf_to_other_text_for_a_folder(proto, dialogs, tmp_path):
    w = proto("B")
    w.open_tool("Pdf2DocTool")
    page = w.current_page()
    inp, out = _folders(tmp_path, n=1)
    fm = page._folder_mode
    fm.set_folder(True)
    fm.folder.set_in_dir(str(inp))
    fm.folder.set_out_dir(str(out))
    page.run()
    wait_job(w)
    assert not dialogs.errors(), dialogs.errors()
    assert "Page 1" in (out / "f0.txt").read_text(encoding="utf-8")


def test_b_without_folders_it_asks_for_them(proto, dialogs):
    w = proto("B")
    w.open_tool("WatermarkTool")
    page = w.current_page()
    page._folder_mode.set_folder(True)
    page.run()
    assert dialogs.msgs[-1] == ("warning", "Watermark", "Set input and output folders.")


def test_a_is_today(proto):
    w = proto("A")
    assert "BatchTool" in w._labels
    w.open_tool("CompressTool")
    assert w.current_page().__dict__.get("_folder_mode") is None
    w.open_tool("BatchTool")
    assert hasattr(w.current_page(), "op")


@pytest.mark.parametrize("tool", ["CompressTool", "WatermarkTool", "OCRTool", "Pdf2DocTool"])
def test_b_a_folder_names_its_action_as_batch_does_and_hides_save(proto, tmp_path, tool):
    """A folder makes new files: its action is not Apply (step 5's rule), and the
    document bar's Save / Print go with the document."""
    w = proto("B")
    assert w.open_tool(tool, make_pdf(tmp_path / "in.pdf"))
    page = w.current_page()
    fm = page.__dict__.get("_folder_mode")
    if fm is None:
        pytest.skip("no OCR engine: the page only says how to get it")
    primary = next(b for b in page._buttons if b.pk_primary)
    before = primary.text()
    fm.set_folder(True)
    pump(0.05)
    assert primary.text() == "Run Batch"
    bar = page.doc_bar
    assert not bar.save_control.isVisibleTo(page) and not bar.print_button.isVisibleTo(page)
    if tool == "OCRTool":                           # its output mode does not rename it
        page.modes["text"].click()
        assert primary.text() == "Run Batch"
        page.modes["overlay"].click()
    fm.set_folder(False)
    pump(0.05)
    assert primary.text() == before
    assert bar.save_control.isVisibleTo(page) and bar.print_button.isVisibleTo(page)
