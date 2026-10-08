"""paperknife.core.crop without any user interface."""
import threading

import pymupdf as fitz
import pytest

from conftest import make_pdf
from paperknife.core import crop as core


def test_parse_margins_reads_blank_as_zero():
    assert core.parse_margins("10", "", "5.5", "0") == (10.0, 0.0, 5.5, 0.0)


@pytest.mark.parametrize("vals,msg", [
    (("a", "0", "0", "0"), "Enter numeric values for all margins."),
    (("-1", "0", "0", "5"), "Margins cannot be negative."),
    (("0", "", "0", ""), "All margins are 0 — nothing to crop."),
])
def test_parse_margins_refuses_unusable_values(vals, msg):
    with pytest.raises(ValueError) as e:
        core.parse_margins(*vals)
    assert str(e.value) == msg


def test_crop_cuts_chosen_pages_and_counts_skips(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=3, width=200, height=300)
    out = tmp_path / "out.pdf"
    doc = fitz.open(src)
    assert core.crop_pdf(doc, str(out), [0, 1], (10, 20, 30, 40), False,
                         threading.Event()) == 2
    assert doc.is_closed
    with fitz.open(out) as d:
        assert (round(d[0].rect.width), round(d[0].rect.height)) == (140, 260)
        assert (round(d[2].rect.width), round(d[2].rect.height)) == (200, 300)


def test_crop_skips_a_page_smaller_than_its_margins(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1, width=100, height=100)
    out = tmp_path / "out.pdf"
    assert core.crop_pdf(fitz.open(src), str(out), [0], (60, 0, 60, 0), False,
                         threading.Event()) == 0


def test_crop_reset_undoes_an_earlier_crop(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=1, width=200, height=300)
    once = tmp_path / "once.pdf"
    core.crop_pdf(fitz.open(src), str(once), [0], (50, 50, 50, 50), False, threading.Event())
    twice = tmp_path / "twice.pdf"
    core.crop_pdf(fitz.open(once), str(twice), [0], (10, 10, 10, 10), True, threading.Event())
    with fitz.open(twice) as d:
        assert (round(d[0].rect.width), round(d[0].rect.height)) == (180, 280)


def test_crop_cancelled_writes_nothing_and_closes_the_document(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    out = tmp_path / "out.pdf"
    stop = threading.Event()
    stop.set()
    doc = fitz.open(src)
    assert core.crop_pdf(doc, str(out), [0, 1], (10, 10, 10, 10), False, stop) is None
    assert not out.exists()
    assert doc.is_closed
