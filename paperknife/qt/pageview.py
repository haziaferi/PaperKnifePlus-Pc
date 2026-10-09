"""
paperknife.qt.pageview
One PDF page on a QGraphicsView: rendering, zoom, page <-> view mapping, mouse
events in page coordinates, and overlay shapes drawn over the page.

Page space is the unrotated page (PyMuPDF's coordinates); the view shows the
page rotated as it displays and scaled by the zoom, exactly as page_canvas.py
did for the CustomTkinter tools, so the same rectangles land in the same place.
"""
from __future__ import annotations

import pymupdf as fitz
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView

from ..pages import render

ZOOM_MIN, ZOOM_MAX = 0.5, 3.0


class PageView(QGraphicsView):
    """Emits pressed / dragged / released with the (x, y) scene position
    (scene_to_page turns it into page space), and zoomed(float) when
    Ctrl+wheel changes the zoom."""

    pressed = Signal(object)
    dragged = Signal(object)
    released = Signal(object)
    zoomed = Signal(float)

    def __init__(self, background: str = "#F0EBE3", parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QBrush(QColor(background)))
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.setDragMode(QGraphicsView.NoDrag)
        self._page: fitz.Page | None = None
        self._zoom = 1.5
        self._pix_item: QGraphicsPixmapItem | None = None
        self._overlays: list = []
        self._down = False

    # ── content ──────────────────────────────────────────────────────────────
    @property
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, z: float):
        z = max(ZOOM_MIN, min(ZOOM_MAX, float(z)))
        if z == self._zoom:             # at a limit: the same image, no render
            return
        self._zoom = z
        self.show_page(self._page)

    def show_page(self, page: fitz.Page | None):
        """Render *page* at the current zoom (None clears the view)."""
        self._page = page
        sc = self.scene()
        sc.clear()
        self._overlays = []
        self._pix_item = None
        if page is None:
            sc.setSceneRect(QRectF(0, 0, 1, 1))
            return
        pix = render(page, self._zoom, shrink=True)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        self._pix_item = sc.addPixmap(QPixmap.fromImage(img.copy()))
        self._scale = pix.width / max(1.0, (page.rect * page.rotation_matrix).width * self._zoom)
        sc.setSceneRect(QRectF(0, 0, pix.width, pix.height))

    # ── page <-> view ────────────────────────────────────────────────────────
    def screen_matrix(self) -> fitz.Matrix:
        """Page space -> scene: rotate as the page is shown, then zoom."""
        z = self._zoom * getattr(self, "_scale", 1.0)
        return self._page.rotation_matrix * fitz.Matrix(z, z)

    def page_to_scene(self, rect) -> QRectF:
        r = fitz.Rect(rect) * self.screen_matrix()
        return QRectF(r.x0, r.y0, r.width, r.height)

    def scene_to_page(self, x: float, y: float) -> fitz.Point:
        return fitz.Point(x, y) * ~self.screen_matrix()

    # ── overlays ─────────────────────────────────────────────────────────────
    def clear_overlays(self):
        for it in self._overlays:
            self.scene().removeItem(it)
        self._overlays = []

    def add_rect(self, rect, color: str, *, fill: str | None = None, dash: bool = False,
                 width: float = 2.0, pad: float = 0.0):
        """Outline (and optionally fill) a page-space rectangle."""
        r = self.page_to_scene(rect).adjusted(-pad, -pad, pad, pad)
        pen = QPen(QColor(color), width)
        if dash:
            pen.setStyle(Qt.DashLine)
        brush = QBrush(QColor(fill)) if fill else QBrush(Qt.NoBrush)
        it = self.scene().addRect(r, pen, brush)
        self._overlays.append(it)
        return it

    def add_scene_shape(self, kind: str, x0, y0, x1, y1, color: str):
        """A rubber-band rectangle or line in scene coordinates (while dragging)."""
        pen = QPen(QColor(color), 2)
        pen.setStyle(Qt.DashLine)
        if kind == "line":
            it = self.scene().addLine(x0, y0, x1, y1, pen)
        else:
            it = self.scene().addRect(QRectF(QPointF(x0, y0), QPointF(x1, y1)).normalized(),
                                      pen)
        self._overlays.append(it)
        return it

    def remove(self, item):
        if item in self._overlays:
            self._overlays.remove(item)
            self.scene().removeItem(item)

    # ── mouse ────────────────────────────────────────────────────────────────
    def _scene_xy(self, event):
        p = self.mapToScene(event.position().toPoint())
        return p.x(), p.y()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._page is not None:
            self._down = True
            self.pressed.emit(self._scene_xy(event))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._down:
            self.dragged.emit(self._scene_xy(event))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._down:
            self._down = False
            self.released.emit(self._scene_xy(event))
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier and self._page is not None:
            dy = event.angleDelta().y()
            if dy == 0:                 # sideways tilt / pan: scroll, never zoom
                super().wheelEvent(event)
                return
            old = self._zoom
            self.set_zoom(self._zoom * (1.1 if dy > 0 else 1 / 1.1))
            if self._zoom != old:
                self.zoomed.emit(self._zoom)
            event.accept()
            return
        super().wheelEvent(event)
