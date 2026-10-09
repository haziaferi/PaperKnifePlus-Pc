"""The Qt Extract Images page: embedded images out to a folder."""
import io

import pymupdf as fitz
from PIL import Image

from qt_harness import make_pdf, pump, spy_open, wait_job


def _page(window):
    assert window.open_tool("ExtractTool")
    pump(0.05)
    return window.current_page()


def _img(fmt, size, color):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


def _pdf_with_images(path):
    """Page 1: a 200 px PNG and a 20 px PNG; page 2: the 200 px PNG again
    (same xref) and a 120 px JPEG."""
    d = fitz.open()
    p1 = d.new_page()
    big = _img("PNG", (200, 200), "red")
    xref = p1.insert_image(fitz.Rect(50, 50, 250, 250), stream=big)
    p1.insert_image(fitz.Rect(300, 50, 320, 70), stream=_img("PNG", (20, 20), "blue"))
    p2 = d.new_page()
    p2.insert_image(fitz.Rect(50, 50, 250, 250), xref=xref)
    p2.insert_image(fitz.Rect(300, 50, 420, 170), stream=_img("JPEG", (120, 120), "green"))
    d.save(path)
    d.close()
    return str(path)


def _extract(window, dialogs, page, src, out_dir):
    page.file.set_path(src)
    out_dir.mkdir(exist_ok=True)
    dialogs.dirs.append(str(out_dir))
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()
    return sorted(p.name for p in out_dir.iterdir())


def test_the_page_builds_with_its_options(window):
    page = _page(window)
    assert type(page).__name__ == "ExtractPage"
    assert page.min_px.value() == 50
    assert page.fmt.currentText() == "Keep original"
    assert [page.fmt.itemText(i) for i in range(page.fmt.count())] == \
        ["Keep original", "PNG", "JPEG"]


def test_without_a_file_it_asks_for_one(window, dialogs):
    page = _page(window)
    page.run()
    assert dialogs.msgs == [("warning", "Extract", "Select a PDF first.")]


def test_extract_writes_each_unique_image_once_and_reports_it(window, dialogs, tmp_path,
                                                              monkeypatch):
    page = _page(window)
    src = _pdf_with_images(tmp_path / "in.pdf")
    opened = spy_open(window, monkeypatch)
    out_dir = tmp_path / "imgs"
    names = _extract(window, dialogs, page, src, out_dir)
    # the 20 px image is under the 50 px minimum; the repeated one is written once
    assert len(names) == 2
    assert sorted(n.rsplit(".", 1)[1] for n in names) == ["jpeg", "png"]
    sizes = sorted(Image.open(out_dir / n).size for n in names)
    assert sizes == [(120, 120), (200, 200)]
    assert opened and opened[0].is_closed
    assert page.log.text() == "Found and extracted 2 image(s)  (3 unique xrefs scanned)"
    assert window.status_text() == f"✓  Extracted 2 image(s) → {out_dir}"
    assert window.status_role == "success"
    assert dialogs.msgs[-1] == ("info", "Done", f"Extracted 2 image(s) to:\n{out_dir}")


def test_the_minimum_dimension_filters_small_images(window, dialogs, tmp_path):
    page = _page(window)
    src = _pdf_with_images(tmp_path / "in.pdf")
    page.min_px.setValue(0)
    assert len(_extract(window, dialogs, page, src, tmp_path / "all")) == 3
    page.min_px.setValue(150)
    names = _extract(window, dialogs, page, src, tmp_path / "big")
    assert len(names) == 1
    assert Image.open(tmp_path / "big" / names[0]).size == (200, 200)


def test_the_output_format_converts_every_image(window, dialogs, tmp_path):
    page = _page(window)
    src = _pdf_with_images(tmp_path / "in.pdf")
    for fmt, ext, pil in (("PNG", "png", "PNG"), ("JPEG", "jpg", "JPEG")):
        page.fmt.setCurrentText(fmt)
        out_dir = tmp_path / fmt
        names = _extract(window, dialogs, page, src, out_dir)
        assert len(names) == 2 and all(n.endswith("." + ext) for n in names)
        assert all(Image.open(out_dir / n).format == pil for n in names)


def test_failed_images_are_reported_as_a_warning(window, dialogs, tmp_path, monkeypatch):
    from paperknife.core import convert as core_convert
    page = _page(window)
    monkeypatch.setattr(core_convert, "extract_images",
                        lambda doc, *a, **k: (doc.close(), core_convert.Extracted(1, 3, 2))[1])
    out_dir = tmp_path / "imgs"
    _extract(window, dialogs, page, make_pdf(tmp_path / "in.pdf"), out_dir)
    assert window.status_role == "warning"
    assert page.log.text() == ("Found and extracted 1 image(s)  (3 unique xrefs scanned)"
                               "  ·  2 image(s) could not be extracted.")
    assert dialogs.msgs[-1] == ("info", "Done", f"Extracted 1 image(s) to:\n{out_dir}"
                                                "\n2 image(s) could not be extracted.")


def test_a_protected_input_is_unlocked(window, dialogs, tmp_path):
    page = _page(window)
    path = tmp_path / "enc.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "Locked text", fontsize=14)
    doc.save(str(path), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    doc.close()
    dialogs.passwords.append("u")
    assert _extract(window, dialogs, page, str(path), tmp_path / "imgs") == []
    assert dialogs.msgs[-1][0] == "info"


def test_a_dropped_pdf_is_taken_and_others_are_refused(window, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf")
    other = tmp_path / "x.png"
    other.write_bytes(_img("PNG", (4, 4), "red"))
    assert page.accept_drop(str(other)) is False
    assert page.accept_drop(src) is True and page.file.path() == src


def test_ctrl_o_chooses_a_file(window, dialogs, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf")
    dialogs.open(src)
    assert window.page_hook("open")
    assert page.file.path() == src


def test_cancelling_the_folder_dialog_closes_the_document(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    opened = spy_open(window, monkeypatch)
    page.run()                     # no folder queued: the dialog returns ""
    assert opened and opened[0].is_closed
    assert window._current_job is None


def test_leaving_the_tool_holds_no_document(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    opened = spy_open(window, monkeypatch)
    _extract(window, dialogs, page, _pdf_with_images(tmp_path / "in.pdf"), tmp_path / "o")
    assert window.show_page("home")
    assert opened and all(d.is_closed for d in opened)
