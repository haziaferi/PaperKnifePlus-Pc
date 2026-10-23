"""The Qt Watermark page: a single-file transform."""
import re
import shutil

import pymupdf as fitz

from qt_harness import make_pdf, pump, spy_open, wait_job


def _page(window):
    assert window.open_tool("WatermarkTool")
    pump(0.05)
    return window.current_page()


def _run(window, dialogs, page, src, out, text="CONFIDENTIAL"):
    page.file.set_path(src)
    page.text.setText(text)
    dialogs.save(out)
    page.run()
    wait_job(window)
    assert not dialogs.errors(), dialogs.errors()


def _spans(page):
    return [s for b in page.get_text("dict")["blocks"] for ln in b.get("lines", [])
            for s in ln["spans"]]


def test_the_page_builds_with_the_ctk_defaults(window):
    page = _page(window)
    assert page.title_label.text() == "Watermark"
    assert page.size.value() == 60 and page.size_label.text() == "60 pt"
    assert page.opacity.value() == 25 and page.opacity_label.text() == "25%"
    assert page.color == (128, 128, 128)
    page.size.setValue(90)
    page.opacity.setValue(40)
    assert page.size_label.text() == "90 pt" and page.opacity_label.text() == "40%"


def test_without_a_file_or_text_it_warns(window, dialogs, tmp_path):
    page = _page(window)
    page.run()
    assert dialogs.msgs[-1] == ("warning", "Watermark", "Select a PDF first.")
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    page.text.setText("   ")
    page.run()
    assert dialogs.msgs[-1] == ("warning", "Watermark", "Enter watermark text.")
    assert not window._current_job


def test_watermark_writes_text_on_every_page_and_reports(window, dialogs, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    out = tmp_path / "out.pdf"
    _run(window, dialogs, page, src, out)
    with fitz.open(out) as doc:
        assert len(doc) == 3
        assert all("CONFIDENTIAL" in p.get_text() for p in doc)
    assert dialogs.msgs[-1] == ("info", "Done", f"Watermarked PDF saved:\n{out}")
    assert window.status_text() == "✓  Watermarked → out.pdf"
    assert window.status_role == "success"


def test_watermark_honours_opacity_and_stays_on_the_page(window, dialogs, tmp_path):
    doc = fitz.open()
    doc.new_page()
    doc.new_page().set_rotation(90)
    doc.new_page(width=200, height=800)
    doc.save(tmp_path / "in.pdf")
    doc.close()
    out = tmp_path / "out.pdf"
    page = _page(window)
    page.size.setValue(120)
    page.opacity.setValue(40)
    _run(window, dialogs, page, str(tmp_path / "in.pdf"), out, "CONFIDENTIAL DOCUMENT")
    with fitz.open(out) as doc:
        for pg in doc:
            assert "CONFIDENTIAL DOCUMENT" in pg.get_text()
            gs = doc.xref_get_key(pg.xref, "Resources/ExtGState")[1]
            assert [float(v) for v in re.findall(r"/ca\s*([\d.]+)", gs)] == [0.4]
            block = pg.get_text("dict")["blocks"][0]
            assert abs(abs(block["lines"][0]["dir"][0]) - 0.7071) < 0.01
            assert fitz.Rect(block["bbox"]) in pg.cropbox


def test_font_size_sets_the_stamp_size(window, dialogs, tmp_path):
    sizes = {}
    for pt in (20, 50):
        page = _page(window)
        page.size.setValue(pt)
        out = tmp_path / f"out{pt}.pdf"
        _run(window, dialogs, page, make_pdf(tmp_path / f"in{pt}.pdf", pages=1), out, "MARK")
        with fitz.open(out) as doc:
            sizes[pt] = [round(s["size"]) for s in _spans(doc[0]) if s["text"] == "MARK"]
    assert sizes == {20: [20], 50: [50]}


def test_picked_colour_is_the_stamp_colour(window, dialogs, tmp_path):
    page = _page(window)
    dialogs.colors.append((255, 0, 0))
    page.pick_color()
    assert page.color == (255, 0, 0)
    assert "#ff0000" in page.swatch.styleSheet()
    out = tmp_path / "red.pdf"
    _run(window, dialogs, page, make_pdf(tmp_path / "in.pdf", pages=1), out, "RED")
    with fitz.open(out) as doc:
        assert [s["color"] for s in _spans(doc[0]) if s["text"] == "RED"] == [0xFF0000]
    # Cancel of the colour dialog keeps the colour
    page.pick_color()
    assert page.color == (255, 0, 0)


def test_default_colour_is_grey(window, dialogs, tmp_path):
    page = _page(window)
    out = tmp_path / "grey.pdf"
    _run(window, dialogs, page, make_pdf(tmp_path / "in.pdf", pages=1), out, "GREY")
    with fitz.open(out) as doc:
        assert [s["color"] for s in _spans(doc[0]) if s["text"] == "GREY"] == [0x808080]


def test_watermark_can_overwrite_its_input(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf")
    copy = tmp_path / "copy.pdf"
    shutil.copy(src, copy)
    page = _page(window)
    _run(window, dialogs, page, str(copy), copy, "OVER")
    with fitz.open(copy) as doc:
        assert "OVER" in doc[0].get_text()


def test_a_dropped_pdf_is_taken_and_others_are_refused(window, tmp_path):
    page = _page(window)
    src = make_pdf(tmp_path / "in.pdf")
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False and page.file.path() == ""
    assert page.accept_drop(src) is True and page.file.path() == src


def test_cancelling_the_save_dialog_closes_the_document(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    page.file.set_path(make_pdf(tmp_path / "in.pdf"))
    page.text.setText("X")
    opened = spy_open(window, monkeypatch)
    page.run()                     # no save path queued: the dialog returns ""
    assert opened and opened[0].is_closed
    assert not window._current_job


def test_leaving_the_tool_leaves_no_document_open(window, dialogs, tmp_path, monkeypatch):
    page = _page(window)
    opened = spy_open(window, monkeypatch)
    _run(window, dialogs, page, make_pdf(tmp_path / "in.pdf"), tmp_path / "o.pdf")
    assert window.show_page("home")
    # the jobs' copies are closed; the window keeps the one document (2026-10-23)
    shared = window.document.doc
    assert opened and all(d.is_closed for d in opened if d is not shared)
    assert shared is not None and not shared.is_closed
