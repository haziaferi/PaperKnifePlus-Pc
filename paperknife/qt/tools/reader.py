"""Read / Preview — the continuous reader (group A, document workspace).

Every page is stacked in one tall scene; only the pages in the viewport (plus
core.reader.PRELOAD each side) are rendered, on a worker thread, at the current
zoom.  A generation counter drops renders that finish after the document or
the zoom changed, and a document is closed off the UI thread once no render
holds it.  View-only: there is no main action and nothing mutates the PDF.
"""
from __future__ import annotations

import os
import queue
import threading
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView
from qfluentwidgets import BodyLabel

from ...core import reader as core_reader
from .. import bridge, dialogs, theme
from ..pages import WorkspacePage, register_page

TITLE = "Read / Preview"
SUBTITLE = "Continuous smooth-scroll viewer — view-only"
ZOOM_DEFAULT = 1.25
ZOOM_MIN, ZOOM_MAX = 0.5, 3.0
WORKER_IDLE_S = 2.0      # the render worker ends after this long with nothing to do


class ContinuousView(QGraphicsView):
    """The scrolling column of pages.  Emits moved when the visible band may
    have changed (scroll, resize) and zoomed(z) when Ctrl+wheel asks for zoom z."""

    moved = Signal()
    zoomed = Signal(float)

    def __init__(self, background: str, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QBrush(QColor(background)))
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        # Three lines a wheel notch: 60 px, as the CTk reader scrolled.
        self.verticalScrollBar().setSingleStep(20)
        self.verticalScrollBar().valueChanged.connect(lambda _v: self.moved.emit())
        self.zoom = ZOOM_DEFAULT

    def band(self) -> tuple[float, float]:
        """Top and bottom of the visible part of the column, in scene pixels."""
        r = self.mapToScene(self.viewport().rect()).boundingRect()
        return r.top(), r.bottom()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.moved.emit()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:
            if e.angleDelta().y() == 0:     # sideways tilt / pan: scroll, never zoom
                super().wheelEvent(e)
                return
            step = 1.1 if e.angleDelta().y() > 0 else 1 / 1.1
            self.zoomed.emit(max(ZOOM_MIN, min(ZOOM_MAX, self.zoom * step)))
            e.accept()
            return
        super().wheelEvent(e)


@register_page("ReaderTool")
class ReaderPage(WorkspacePage):
    def __init__(self, tool=None, window=None):
        super().__init__(TITLE, SUBTITLE, tool=tool, window=window)
        self._doc = None
        self._doc_lock = None
        self._path = ""
        self._zoom = ZOOM_DEFAULT
        self._pg = 0
        self._page_rects: list = []
        self._tops: list[int] = []
        self._sizes: list[tuple[int, int]] = []
        self._total_h = 0
        self._max_w = 0
        self._scroll_frac = 0.0
        self._gen = 0
        self._cache: OrderedDict = OrderedDict()   # (page_idx, zoom) -> QPixmap
        self._items: dict = {}                      # page_idx -> pixmap item on the scene
        self._inflight: set = set()                 # (gen, page_idx, zoom) queued, not drawn
        self._window = (0, -1)                      # pages wanted now; the worker skips the rest
        self._req_q: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._worker_lock = threading.Lock()
        self._zoom_wait = None

        # The centre is a continuous column, not the one-page view.
        old = self.view
        self.view = ContinuousView(theme.hex_color("page_bg"))
        old.parentWidget().layout().replaceWidget(old, self.view)
        old.hide()
        old.setParent(None)
        old.deleteLater()
        self.view.moved.connect(self._update_viewport)
        self.view.zoomed.connect(lambda z: self.zoom_slider.setValue(int(round(z * 100))))

        # A viewer has no tools: no rail.
        rail = self.rail.parentWidget()
        frame = rail.parentWidget().layout()
        rail.hide()
        frame.itemAt(frame.indexOf(rail) + 1).widget().hide()     # the rail's divider

        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(int(round(self._zoom * 100)))
        self.zoom_slider.blockSignals(False)
        self.page_label.setText("—")

        self.secondary("Open PDF", self.open)
        self._fill_panel()

    # ── panel ────────────────────────────────────────────────────────────────
    def _fill_panel(self):
        self.panel_begin("Document")
        row = self.panel_field("File")
        self.path_label = BodyLabel(self._path or "Open a PDF…")
        self.path_label.setWordWrap(True)
        row.addWidget(self.path_label, 1)

    # ── file ─────────────────────────────────────────────────────────────────
    def open(self):
        path = dialogs.ask_open("Open PDF", [("PDF", "*.pdf")])
        if path:
            self.open_path(path)

    def open_path(self, path: str):
        """Other parts of the app can open a file straight into the reader."""
        self._load(path)

    def accept_drop(self, path: str) -> bool:
        if not str(path).lower().endswith(".pdf"):
            return False
        self.open_path(path)
        return True

    def _load(self, path: str) -> bool:
        win = self.window_
        doc = win.open_pdf_safe(path) if win is not None else None
        if doc is None:
            return False
        old_doc, old_lock = self._doc, self._doc_lock
        # Sizes are read once here, before the worker can see this document, so
        # layout never walks the Document while a render holds it.
        self._page_rects = [page.rect for page in doc]
        self._gen += 1
        self._doc, self._doc_lock, self._path = doc, threading.Lock(), path
        self._pg = 0
        self.set_title(TITLE, Path(path).name)
        self.path_label.setText(path)
        self._relayout()
        self.view.verticalScrollBar().setValue(0)
        self._update_viewport()
        if old_doc is not None:
            core_reader.close_when_idle(old_doc, old_lock)
        return True

    def activate(self):
        # Re-entering the tool: reopen the document closed on leaving it, once
        # the shell has finished switching (open_tool may hand a new file).
        if self._doc is None and self._path:
            QTimer.singleShot(0, self._reopen)

    def _reopen(self):
        win = self.window_
        if (self._doc is not None or not self._path or not os.path.exists(self._path)
                or (win is not None and win.current_page() is not self)):
            return
        frac = self._scroll_frac
        if self._load(self._path):
            self.view.verticalScrollBar().setValue(int(frac * self._total_h))
            QTimer.singleShot(30, self._update_viewport)

    def deactivate(self):
        # Keep the path and scroll position for re-entry, but not the file open.
        if self._doc is not None:
            self._gen += 1
            core_reader.close_when_idle(self._doc, self._doc_lock)
            self._doc = None
            self._cache.clear()
            self._items.clear()
            self.view.scene().clear()
            self.page_label.setText("—")

    # ── layout: page geometry only, no rendering ─────────────────────────────
    def _relayout(self):
        self._gen += 1                     # renders in flight are for the old layout
        self._cache.clear()
        self._items.clear()
        sc = self.view.scene()
        sc.clear()
        gap = core_reader.GAP
        self._tops, self._sizes, self._total_h, self._max_w = core_reader.layout(
            self._page_rects, self._zoom, gap)
        sc.setSceneRect(QRectF(0, 0, self._max_w + 2 * gap, self._total_h))
        blank = QBrush(QColor("#FFFFFF"))
        for y, (w, h) in zip(self._tops, self._sizes, strict=True):
            sc.addRect(QRectF(self._page_x(w), y, w, h), QPen(Qt.NoPen), blank)
        self.view.zoom = self._zoom

    def _page_x(self, w: int) -> float:
        return core_reader.GAP + (self._max_w - w) / 2

    # ── zoom ─────────────────────────────────────────────────────────────────
    def _zoom_changed(self, v: int):
        # Re-render once the slider rests.
        if self._zoom_wait is None:
            self._zoom_wait = QTimer(self, singleShot=True, interval=120)
            self._zoom_wait.timeout.connect(
                lambda: self.set_zoom(self.zoom_slider.value() / 100))
        self._zoom_wait.start()

    def set_zoom(self, z: float):
        z = max(ZOOM_MIN, min(ZOOM_MAX, float(z)))
        if int(round(z * 100)) != self.zoom_slider.value():
            self.zoom_slider.blockSignals(True)
            self.zoom_slider.setValue(int(round(z * 100)))
            self.zoom_slider.blockSignals(False)
        if z == self._zoom:
            return
        self._zoom = z
        self.view.zoom = z
        if self._doc is None:
            return
        frac = self._scroll_frac
        self._relayout()
        self.view.verticalScrollBar().setValue(int(frac * self._total_h))
        self._update_viewport()

    # ── navigation (the strip under the column) ──────────────────────────────
    def go(self, d: int):
        n = len(self._tops) if self._doc is not None else 0
        if n and 0 <= self._pg + d < n:
            # Half a gap above the page: the previous page has just left the view.
            self.view.verticalScrollBar().setValue(self._tops[self._pg + d] - core_reader.GAP // 2)
            self._update_viewport()

    def show_current(self):
        self._update_viewport()

    # ── viewport -> request the visible (+ preload) pages ────────────────────
    def _update_viewport(self):
        if self._doc is None or not self._tops:
            return
        top, bottom = self.view.band()
        seen = core_reader.visible_range(self._tops, self._sizes, top, bottom)
        if seen is None:
            return
        first, last = seen
        lo, hi = core_reader.preload_window(first, last, len(self._tops))
        self._window = (lo, hi)
        for i in range(lo, hi + 1):
            self._request_page(i)
        # Free scene images that scrolled well outside the window; the pixmap
        # stays in the cache so scrolling back redraws at once.
        sc = self.view.scene()
        for idx in list(self._items):
            if idx < lo or idx > hi:
                sc.removeItem(self._items.pop(idx))
        self._scroll_frac = max(0.0, top) / self._total_h if self._total_h else 0.0
        self._pg = first
        self.page_label.setText(f"{first + 1}–{last + 1} / {len(self._tops)}")

    def _request_page(self, idx: int):
        key = (idx, self._zoom)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            if idx not in self._items:
                self._draw_page(idx, cached)
            return
        # The cache only fills when a render reaches the UI thread, so without
        # this every scroll event would queue the same pages again.
        flight = (self._gen, idx, self._zoom)
        if flight in self._inflight:
            return
        self._inflight.add(flight)
        with self._worker_lock:
            self._req_q.put((self._gen, self._doc, self._doc_lock, idx, self._zoom))
            if self._worker is None:
                self._worker = threading.Thread(target=self._render_loop, daemon=True)
                self._worker.start()

    def _draw_page(self, idx: int, pixmap: QPixmap):
        sc = self.view.scene()
        if idx in self._items:
            sc.removeItem(self._items.pop(idx))
        item = sc.addPixmap(pixmap)
        item.setPos(self._page_x(self._sizes[idx][0]), self._tops[idx])
        item.setZValue(1)
        self._items[idx] = item

    # ── worker: rasterise off the UI thread ──────────────────────────────────
    def _render_loop(self):
        idle = 0.0
        while True:
            try:
                gen, doc, lock, idx, zoom = self._req_q.get(timeout=0.25)
            except queue.Empty:
                idle += 0.25
                if idle >= WORKER_IDLE_S:
                    with self._worker_lock:
                        if self._req_q.empty():
                            self._worker = None
                            return
                continue
            idle = 0.0
            flight = (gen, idx, zoom)
            lo, hi = self._window
            if gen != self._gen or doc is None or not lo <= idx <= hi:
                # stale (document or zoom changed) or scrolled out of view since queued
                bridge.post(self._inflight.discard, flight)
                continue
            try:
                pix = core_reader.rasterise(doc, lock, idx, zoom)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                             QImage.Format_RGB888).copy()
            except Exception as e:
                bridge.post(self._on_failed, flight, idx, e)
                continue
            bridge.post(self._on_rendered, gen, idx, zoom, img)

    def _on_failed(self, flight, idx, exc):
        self._inflight.discard(flight)
        if flight[0] == self._gen and self.window_ is not None:
            self.window_.set_status(f"Page {idx + 1} could not be shown: {exc}", "warning")

    def _on_rendered(self, gen, idx, zoom, img: QImage):
        self._inflight.discard((gen, idx, zoom))
        if gen != self._gen:
            return                  # stale: the document or zoom changed while it rendered
        pixmap = QPixmap.fromImage(img)
        key = (idx, zoom)
        self._cache[key] = pixmap
        self._cache.move_to_end(key)
        while len(self._cache) > core_reader.CACHE_MAX:
            for k in list(self._cache):
                if k[0] not in self._items:          # never evict a page on screen now
                    del self._cache[k]
                    break
            else:
                break
        self._draw_page(idx, pixmap)
