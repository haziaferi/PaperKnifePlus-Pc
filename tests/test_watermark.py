"""Watermark tool end to end through the real view (FE register: L2-01, L2-03)."""
import fitz

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
