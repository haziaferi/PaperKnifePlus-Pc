"""The continuous reader's geometry, rendering and closing, without any user interface.

Shared by the CustomTkinter ReaderTool and the Qt reader page: both stack every
page vertically, render only the pages in (or near) the viewport on a worker
thread, and close a document off the UI thread once no render holds it.
"""
from __future__ import annotations
import threading

from ..pages import render

PRELOAD = 2      # extra pages rendered beyond the visible window, each side
CACHE_MAX = 16   # bounded render cache (pages currently displayed are exempt)
GAP = 10         # px between pages


def layout(rects, zoom: float, gap: int = GAP):
    """Stack pages of the given page rects at *zoom*: returns (tops, sizes,
    total_h, max_w) — each page's top y, its (w, h) in pixels, the height of
    the whole column and the widest page.  Geometry only: nothing is rendered."""
    tops, sizes = [], []
    y, max_w = gap, 0
    for rect in rects:
        w = int(rect.width * zoom)
        h = int(rect.height * zoom)
        tops.append(y)
        sizes.append((w, h))
        y += h + gap
        max_w = max(max_w, w)
    return tops, sizes, y, max_w


def visible_range(tops, sizes, top: float, bottom: float):
    """(first, last) index of the pages that overlap the band [top, bottom],
    or None when none does."""
    first = last = None
    for i, (y0, (_, h)) in enumerate(zip(tops, sizes, strict=True)):
        if y0 + h < top or y0 > bottom:
            continue
        first = i if first is None else first
        last = i
    return None if first is None else (first, last)


def preload_window(first: int, last: int, count: int, preload: int = PRELOAD):
    """The pages to have rendered: the visible ones plus *preload* each side."""
    return max(0, first - preload), min(count - 1, last + preload)


def rasterise(doc, lock, idx: int, zoom: float):
    """Render page *idx* of *doc* at *zoom* (shrunk to fit the pixel cap),
    holding *lock* so the document is never closed under the render."""
    with lock:
        return render(doc[idx], zoom, shrink=True)


def close_when_idle(doc, lock) -> threading.Thread:
    """Close *doc* on a thread of its own, once *lock* is free, so a render
    already in flight against it finishes before close() runs."""
    def _close():
        with lock:
            doc.close()
    t = threading.Thread(target=_close, daemon=True)
    t.start()
    return t
