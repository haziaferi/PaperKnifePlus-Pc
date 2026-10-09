"""The Qt PDF → Images page: every page as a PNG in a ZIP."""
import io
import zipfile

import pymupdf as fitz
from PIL import Image

from qt_harness import make_pdf, pump, spy_open, wait_job


def _page(window):
    assert window.open_tool("Pdf2ImgTool")
    pump(0.05)
    return window.current_page()


def _encrypted(path):
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "Locked text", fontsize=14)
    doc.save(str(path), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    doc.close()
    return str(path)


def test_the_page_builds_with_its_one_option(window):
    page = _page(window)
    assert type(page).__name__ == "Pdf2ImgPage"
    assert page.title_label.text() == "PDF → Images"
    assert 72 <= page.dpi <= 300 and page.dpi_label.text() == f"{page.dpi} DPI"
    page.dpi_slider.setValue(150)
    assert page.dpi_label.text() == "150 DPI"


def test_without_a_file_it_asks_for_one(window, dialogs):
    page = _page(window)
    page.run()
    assert dialogs.msgs == [("warning", "Export", "Select a PDF first.")]


def test_export_writes_every_page_as_a_png_and_reports_it(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf", pages=3))
    out = tmp_path / "pages.zip"
    dialogs.save(out)
    opened = spy_open(window, monkeypatch)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    with zipfile.ZipFile(out) as zf:
        assert zf.namelist() == ["page_0001.png", "page_0002.png", "page_0003.png"]
        img = Image.open(io.BytesIO(zf.read("page_0002.png")))
        assert img.format == "PNG"
    assert opened and opened[0].is_closed
    assert window.status_text() == "✓  Exported 3 pages → pages.zip"
    assert window.status_role == "success"
    assert dialogs.msgs[-1] == ("info", "Done", f"Exported 3 pages to:\n{out}")


def test_the_resolution_sets_the_image_size(window, dialogs, tmp_path):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf", pages=1))
    sizes = {}
    for dpi in (72, 144):
        page.dpi_slider.setValue(dpi)
        out = tmp_path / f"p{dpi}.zip"
        dialogs.save(out)
        page.run()
        wait_job(window)
        with zipfile.ZipFile(out) as zf:
            sizes[dpi] = Image.open(io.BytesIO(zf.read("page_0001.png"))).size
    assert abs(sizes[72][0] - 595) <= 1 and abs(sizes[72][1] - 842) <= 1   # A4, 1 px/pt
    assert abs(sizes[144][0] - 2 * sizes[72][0]) <= 2
    assert abs(sizes[144][1] - 2 * sizes[72][1]) <= 2


def test_dpi_defaults_from_preferences(window, monkeypatch):
    from paperknife.prefs import PREFS
    monkeypatch.setitem(PREFS._data, "default_dpi", 200)
    assert _page(window).dpi == 200


def test_a_protected_input_is_unlocked(window, dialogs, tmp_path):
    page = _page(window)
    page.file.set_path(_encrypted(tmp_path / "enc.pdf"))
    dialogs.passwords.append("u")
    out = tmp_path / "pages.zip"
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    with zipfile.ZipFile(out) as zf:
        assert zf.namelist() == ["page_0001.png"]


def test_a_dropped_pdf_is_taken_and_others_are_refused(window, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf")
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    assert page.accept_drop(src) is True and page.file.path() == src


def test_ctrl_o_chooses_a_file(window, dialogs, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf")
    dialogs.open(src)
    assert window.page_hook("open")
    assert page.file.path() == src


def test_cancelling_the_save_dialog_closes_the_document(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    opened = spy_open(window, monkeypatch)
    page.run()                     # no save path queued: the dialog returns ""
    assert opened and opened[0].is_closed
    assert window._current_job is None


def test_cancelling_the_job_leaves_no_zip(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf", pages=40))
    page.dpi_slider.setValue(300)
    out = tmp_path / "pages.zip"
    dialogs.save(out)
    opened = spy_open(window, monkeypatch)
    page.run()
    window._cancel_job()
    wait_job(window)
    assert not out.exists()
    assert not list(tmp_path.glob("*.part"))
    assert opened[0].is_closed
    assert window.status_text() == "⚠  Cancelled"


def test_leaving_the_tool_holds_no_document(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf", pages=1))
    out = tmp_path / "pages.zip"
    dialogs.save(out)
    opened = spy_open(window, monkeypatch)
    page.run()
    wait_job(window)
    assert window.show_page("home")
    assert opened and all(d.is_closed for d in opened)
