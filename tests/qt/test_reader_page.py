"""The Qt Read / Preview page: a continuous reader on a render worker."""
import threading
import time

import pymupdf as fitz
import pytest

from qt_harness import make_pdf, pump, subtitle_with

from paperknife.core import reader as core_reader
from paperknife.pages import render


def _settle(page, timeout=10.0):
    """Pump until every page of the wanted window is drawn and nothing is in flight."""
    end = time.time() + timeout
    while time.time() < end:
        pump(0.05)
        lo, hi = page._window
        if (page._doc is not None and not page._inflight and hi >= lo
                and all(i in page._items for i in range(lo, hi + 1))):
            return
    raise TimeoutError(f"window {page._window}, drawn {sorted(page._items)}")


def _wait(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        pump(0.05)
    return cond()


def _open(window, tmp_path, pages=3, name="doc.pdf"):
    src = make_pdf(tmp_path / name, pages=pages)
    assert window.open_tool("ReaderTool", src)
    page = window.current_page()
    _settle(page)
    return page, src


def _dark_pixels(img, x0, y0, x1, y1):
    return sum(1 for x in range(x0, x1, 2) for y in range(y0, y1, 2)
               if img.pixelColor(x, y).lightness() < 100)


def test_page_builds_as_a_viewer_without_a_main_action(window):
    assert window.open_tool("ReaderTool")
    page = window.current_page()
    assert type(page).__name__ == "ReaderPage"
    assert page.title_label.text() == "Read / Preview"
    assert page.subtitle_label.text() == "Continuous smooth-scroll viewer — view-only"
    assert [b.text() for b in page._buttons] == ["Open PDF"]
    assert not any(b.pk_primary for b in page._buttons)
    assert page.page_label.text() == "—" and page.path_label.text() == "Open a PDF…"


def test_open_with_no_file_chosen_does_nothing(window, dialogs):
    window.open_tool("ReaderTool")
    page = window.current_page()
    page.open()                                  # the dialog returns "" (cancelled)
    pump(0.1)
    assert page._doc is None and page._items == {} and dialogs.msgs == []
    assert page.page_label.text() == "—"


def test_open_renders_the_visible_pages_with_their_content(window, dialogs, tmp_path):
    src = make_pdf(tmp_path / "doc.pdf", pages=3)
    window.open_tool("ReaderTool")
    page = window.current_page()
    dialogs.open(src)
    page.open()
    _settle(page)
    assert page.subtitle_label.text() == subtitle_with(
        "Continuous smooth-scroll viewer — view-only", "doc.pdf")
    assert page.path_label.text() == src
    assert 0 in page._items
    z = page._zoom
    with fitz.open(src) as d:
        want = render(d[0], z, shrink=True)
    img = page._items[0].pixmap().toImage()
    assert (img.width(), img.height()) == (want.width, want.height)
    assert img.width() == pytest.approx(page._page_rects[0].width * z, abs=1)
    # "Page 1" at (72, 100) pt: dark pixels there, none in the empty lower half.
    assert _dark_pixels(img, int(70 * z), int(85 * z), int(140 * z), int(105 * z)) > 0
    assert _dark_pixels(img, 0, img.height() // 2, img.width(), img.height()) == 0
    assert page.page_label.text().endswith(" / 3") and page.page_label.text().startswith("1–")


def _visible(page):
    """The 0-based first and last visible page, from the "a–b / n" label."""
    a, b = page.page_label.text().split(" / ")[0].split("–")
    return int(a) - 1, int(b) - 1


def test_pages_are_stacked_and_scrolling_renders_the_ones_that_come_into_view(window, tmp_path):
    page, _ = _open(window, tmp_path, pages=12)
    assert 11 not in page._items
    # Only the visible pages plus PRELOAD each side are rendered.
    first, last = _visible(page)
    assert last < 11 - core_reader.PRELOAD, "the window shows too much for this test to mean anything"
    assert set(page._items) == set(range(max(0, first - core_reader.PRELOAD),
                                         last + core_reader.PRELOAD + 1)), sorted(page._items)
    tops = page._tops
    assert all(b > a for a, b in zip(tops, tops[1:], strict=False))
    bar = page.view.verticalScrollBar()
    bar.setValue(bar.maximum())
    _settle(page)
    assert 11 in page._items and 0 not in page._items      # scrolled-away images are freed
    first, last = _visible(page)
    assert set(page._items) == set(range(first - core_reader.PRELOAD, 12)), sorted(page._items)
    assert page.page_label.text().endswith("–12 / 12")
    assert page._items[11].pos().y() == tops[11]


def test_page_strip_steps_page_by_page(window, tmp_path):
    page, _ = _open(window, tmp_path, pages=5)
    page.go(1)
    _settle(page)
    assert page._pg == 1 and page.page_label.text().startswith("2–")
    page.go(-1)
    assert page._pg == 0
    page.go(-1)
    assert page._pg == 0


def test_zoom_slider_shows_current_zoom(window):
    window.open_tool("ReaderTool")
    page = window.current_page()
    assert abs(page.zoom_slider.value() / 100 - page._zoom) < 0.06


def test_zoom_renders_the_pages_at_the_new_size(window, tmp_path):
    page, _ = _open(window, tmp_path)
    page.set_zoom(2.0)
    _settle(page)
    assert page.zoom_slider.value() == 200
    img = page._items[0].pixmap().toImage()
    r = page._page_rects[0]
    assert img.width() == pytest.approx(r.width * 2, abs=1)
    assert img.height() == pytest.approx(r.height * 2, abs=1)
    assert page._sizes[0] == (int(r.width * 2), int(r.height * 2))
    # The slider drives it too, once it rests.
    page.zoom_slider.setValue(80)
    assert _wait(lambda: page._zoom == 0.8)
    _settle(page)
    assert page._items[0].pixmap().width() == pytest.approx(page._page_rects[0].width * 0.8, abs=1)
    assert all(k[1] == 0.8 for k in page._cache)


def test_does_not_rerender_pages_already_requested(window, tmp_path, monkeypatch):
    src = make_pdf(tmp_path / "r.pdf", pages=12)
    real = fitz.Page.get_pixmap
    count = {"n": 0}

    def counting(self, *a, **k):
        count["n"] += 1
        return real(self, *a, **k)

    monkeypatch.setattr(fitz.Page, "get_pixmap", counting)
    window.open_tool("ReaderTool", src)
    page = window.current_page()
    for _ in range(10):
        page._update_viewport()
    _settle(page)
    visible = len(page._items)
    assert visible >= 1
    assert count["n"] <= visible, f"{count['n']} rasterisations for {visible} pages"


def test_drop_takes_pdfs_only(window, tmp_path):
    page, _ = _open(window, tmp_path)
    other = tmp_path / "x.txt"
    other.write_text("x", encoding="utf-8")
    assert page.accept_drop(str(other)) is False
    first = page._doc
    second = make_pdf(tmp_path / "second.pdf", pages=4)
    assert page.accept_drop(second) is True
    _settle(page)
    assert len(page._doc) == 4 and page.page_label.text().endswith(" / 4")
    assert _wait(lambda: first.is_closed)            # the old one is closed off the UI thread


def test_cancelled_open_keeps_the_document_open(window, tmp_path):
    page, src = _open(window, tmp_path)
    doc = page._doc
    page.open()                                  # cancelled
    assert page._doc is doc and not doc.is_closed and page._path == src


def test_leaving_closes_the_document_and_returning_reopens_it(window, tmp_path):
    page, src = _open(window, tmp_path, pages=12)
    bar = page.view.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    _settle(page)
    frac = page._scroll_frac
    held = page._doc
    window.open_tool("CropTool")
    assert _wait(lambda: held.is_closed)
    assert page._doc is None and page._items == {}
    window.open_tool("ReaderTool")
    assert _wait(lambda: page._doc is not None)
    _settle(page)
    assert page._doc is not held and page.path_label.text() == src
    assert page._scroll_frac == pytest.approx(frac, abs=0.02)


def _blocking_rasterise(monkeypatch):
    """Replace core.reader.rasterise with one that holds the document's lock
    until the returned gate is set."""
    started, gate = threading.Event(), threading.Event()

    def slow(doc, lock, idx, zoom):
        with lock:
            started.set()
            gate.wait(10)
            return render(doc[idx], zoom, shrink=True)

    monkeypatch.setattr(core_reader, "rasterise", slow)
    return started, gate


def test_a_render_that_finishes_after_a_zoom_change_is_dropped(window, tmp_path, monkeypatch):
    started, gate = _blocking_rasterise(monkeypatch)
    src = make_pdf(tmp_path / "doc.pdf", pages=3)
    window.open_tool("ReaderTool", src)
    page = window.current_page()
    assert started.wait(5)                       # a render at 1.25 is in flight
    page.set_zoom(2.0)
    gate.set()
    _settle(page)
    assert all(k[1] == 2.0 for k in page._cache)
    w = page._page_rects[0].width * 2
    assert page._items and all(abs(it.pixmap().width() - w) <= 1 for it in page._items.values())


def test_leaving_while_a_render_is_in_flight_closes_after_it(window, tmp_path, monkeypatch):
    started, gate = _blocking_rasterise(monkeypatch)
    src = make_pdf(tmp_path / "doc.pdf", pages=3)
    window.open_tool("ReaderTool", src)
    page = window.current_page()
    assert started.wait(5)
    held = page._doc
    window.show_page("home")
    assert page._doc is None
    pump(0.2)
    assert not held.is_closed                    # the render still holds it
    gate.set()
    assert _wait(lambda: held.is_closed)
    pump(0.2)
    assert page._items == {} and "could not be shown" not in window.status_text()


def test_a_page_that_fails_to_render_is_reported(window, tmp_path, monkeypatch):
    def broken(doc, lock, idx, zoom):
        raise RuntimeError("boom")

    monkeypatch.setattr(core_reader, "rasterise", broken)
    page, _ = _open_unsettled(window, tmp_path)
    assert _wait(lambda: "could not be shown" in window.status_text())
    assert window.status_text() == "⚠  Page 1 could not be shown: boom"
    assert _wait(lambda: not page._inflight)


def _open_unsettled(window, tmp_path):
    src = make_pdf(tmp_path / "doc.pdf", pages=1)
    assert window.open_tool("ReaderTool", src)
    return window.current_page(), src


def test_ctrl_sideways_wheel_does_not_zoom_the_reader(window):
    # R1-13: the Reader's view made the same zoom-out of a delta-0 wheel.
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    window.open_tool("ReaderTool")
    page = window.current_page()
    zooms = []
    page.view.zoomed.connect(zooms.append)
    ev = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(120, 0),
                     Qt.NoButton, Qt.ControlModifier, Qt.NoScrollPhase, False)
    page.view.wheelEvent(ev)
    assert zooms == []
