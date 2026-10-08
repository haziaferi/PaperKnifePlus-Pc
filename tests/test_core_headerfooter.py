"""paperknife.core.headerfooter without any user interface."""
import threading

import pymupdf as fitz
import pytest

from conftest import make_pdf
from paperknife.core import headerfooter as core


def test_parse_style_defaults_blank_fields():
    assert core.parse_style("", "") == (10.0, 20.0)
    assert core.parse_style("12.5", "30") == (12.5, 30.0)


@pytest.mark.parametrize("size,margin", [("big", "20"), ("10", "wide")])
def test_parse_style_refuses_text(size, margin):
    with pytest.raises(ValueError, match="Enter numeric values for size and margin."):
        core.parse_style(size, margin)


def test_stamp_replaces_tokens_on_chosen_pages_only(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=3)
    out = tmp_path / "out.pdf"
    doc = fitz.open(src)
    assert core.stamp_pdf(doc, str(out), [0, 2], "P {page}/{total} {date}", "bottom-right",
                          "helv", 10, 20, "2026-10-08", threading.Event()) is True
    assert doc.is_closed
    with fitz.open(out) as d:
        assert "P 1/3 2026-10-08" in d[0].get_text()
        assert "P 2/3" not in d[1].get_text()
        assert "P 3/3 2026-10-08" in d[2].get_text()
        # bottom-right: the text ends at the right margin, near the bottom
        r = d[0].search_for("P 1/3")[0]
        assert r.y1 > d[0].rect.height - 40 and r.x0 > d[0].rect.width / 2


def test_stamp_top_left_sits_in_the_top_margin(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1)
    out = tmp_path / "out.pdf"
    core.stamp_pdf(fitz.open(src), str(out), [0], "HEADER", "top-left", "cour", 12, 20,
                   "", threading.Event())
    with fitz.open(out) as d:
        r = d[0].search_for("HEADER")[0]
        assert r.y0 < 40 and r.x0 == pytest.approx(20, abs=1)


def test_stamp_cancelled_writes_nothing_and_closes_the_document(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    out = tmp_path / "out.pdf"
    stop = threading.Event()
    stop.set()
    doc = fitz.open(src)
    assert core.stamp_pdf(doc, str(out), [0, 1], "x", "top-center", "helv", 10, 20, "",
                          stop) is False
    assert not out.exists()
    assert doc.is_closed
