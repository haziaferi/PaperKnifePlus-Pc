"""paperknife.core.pdftools without any user interface."""
import pymupdf as fitz

from conftest import make_pdf
from paperknife.core import pdftools as core


def test_repair_recovers_a_truncated_file_and_says_so(tmp_path):
    good = make_pdf(tmp_path / "good.pdf", pages=2)
    data = open(good, "rb").read()
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(data[: data.rfind(b"xref")])
    out = tmp_path / "out.pdf"
    doc = fitz.open(bad)
    assert core.repair_pdf(doc, str(out)) is True
    assert doc.is_closed
    with fitz.open(out) as d:
        assert not d.is_repaired and d.page_count == 2


def test_repair_of_a_sound_file_reports_no_damage(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    out = tmp_path / "out.pdf"
    assert core.repair_pdf(fitz.open(src), str(out)) is False
    with fitz.open(out) as d:
        assert "Page 1" in d[0].get_text()


def test_repair_can_overwrite_its_input(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    core.repair_pdf(fitz.open(src), src)
    with fitz.open(src) as d:
        assert d.page_count == 2
