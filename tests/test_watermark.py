"""Watermark tool end to end through the real view."""
import re

import pymupdf as fitz

from conftest import make_pdf, tool, wait_job


def test_watermark_writes_text_on_every_page(app, dialogs, tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    out = tmp_path / "out.pdf"
    t = tool(app, "WatermarkTool")
    t._path.set(src)
    t._text.insert(0, "CONFIDENTIAL")
    dialogs.save(out)
    t._run()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        assert all("CONFIDENTIAL" in p.get_text() for p in doc)


def test_watermark_honours_opacity_and_stays_on_the_page(app, dialogs, tmp_path):
    doc = fitz.open()
    doc.new_page()
    doc.new_page().set_rotation(90)
    doc.new_page(width=200, height=800)
    doc.save(tmp_path / "in.pdf")
    doc.close()
    out = tmp_path / "out.pdf"
    t = tool(app, "WatermarkTool")
    t._path.set(str(tmp_path / "in.pdf"))
    t._text.insert(0, "CONFIDENTIAL DOCUMENT")
    t._size.set(120)
    t._opacity.set(40)
    dialogs.save(out)
    t._run()
    wait_job(app)
    assert not dialogs.errors(), dialogs.errors()
    with fitz.open(out) as doc:
        for page in doc:
            assert "CONFIDENTIAL DOCUMENT" in page.get_text()
            gs = doc.xref_get_key(page.xref, "Resources/ExtGState")[1]
            assert [float(v) for v in re.findall(r"/ca\s*([\d.]+)", gs)] == [0.4]
            block = page.get_text("dict")["blocks"][0]
            assert abs(abs(block["lines"][0]["dir"][0]) - 0.7071) < 0.01
            # get_text reports unrotated coordinates, so compare with the crop box
            assert fitz.Rect(block["bbox"]) in page.cropbox
