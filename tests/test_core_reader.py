"""paperknife.core.reader without any user interface."""
import threading
import time

import pymupdf as fitz
import pytest

from conftest import make_pdf
from paperknife.core import reader


def test_layout_stacks_pages_with_a_gap():
    rects = [fitz.Rect(0, 0, 100, 200), fitz.Rect(0, 0, 300, 50)]
    tops, sizes, total_h, max_w = reader.layout(rects, 2.0, gap=10)
    assert tops == [10, 420]
    assert sizes == [(200, 400), (600, 100)]
    assert total_h == 530 and max_w == 600


def test_visible_range_and_preload_window():
    tops, sizes, _, _ = reader.layout([fitz.Rect(0, 0, 100, 100)] * 10, 1.0, gap=10)
    assert reader.visible_range(tops, sizes, 0, 50) == (0, 0)
    assert reader.visible_range(tops, sizes, 115, 340) == (1, 3)
    assert reader.visible_range(tops, sizes, 5000, 6000) is None
    assert reader.preload_window(0, 0, 10) == (0, 2)
    assert reader.preload_window(4, 5, 10) == (2, 7)
    assert reader.preload_window(9, 9, 10) == (7, 9)


def test_rasterise_renders_the_page_at_the_zoom(tmp_path):
    src = make_pdf(tmp_path / "in.pdf", pages=2)
    with fitz.open(src) as doc:
        pix = reader.rasterise(doc, threading.Lock(), 1, 0.5)
        assert pix.width == pytest.approx(doc[1].rect.width * 0.5, abs=1)


def test_close_when_idle_waits_for_a_render_holding_the_lock(tmp_path):
    doc = fitz.open(make_pdf(tmp_path / "in.pdf", pages=1))
    lock = threading.Lock()
    lock.acquire()
    t = reader.close_when_idle(doc, lock)
    time.sleep(0.2)
    assert not doc.is_closed
    lock.release()
    t.join(5)
    assert doc.is_closed
