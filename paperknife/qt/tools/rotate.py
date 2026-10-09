"""Rotate & Reorder — a page organiser (group B): turn and move pages, save in the new order."""
from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
from PySide6.QtGui import QImage

from ...core import organise
from ...core.doc_state import DocHolder
from .. import dialogs
from ..pages import OrganiserPage, register_page

SUBTITLE = "Click a thumbnail · then rotate or move it"
THUMB_ZOOM = 0.28           # as the CTk tool's thumbnails


@register_page("RotateTool")
class RotatePage(DocHolder, OrganiserPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Rotate & Reorder", SUBTITLE, tool=tool, window=window)
        self._extra: dict[int, int] = {}
        self._src = ""
        for text, deg in (("↺ 90° CCW", -90), ("↻ 90° CW", 90), ("⤢ 180°", 180)):
            self.add_action(text, None, lambda _=False, d=deg: self.rotate(d))
        self.add_action("← Move Left", None, lambda _=False: self.move_pages(-1))
        self.add_action("Move Right →", None, lambda _=False: self.move_pages(1))
        self.primary("Save PDF", self.save)

    # ── document ─────────────────────────────────────────────────────────────
    def open(self):
        self.file.choose()

    def open_path(self, path: str):
        self.file.set_path(path)

    def load(self, path: str):
        if not path:
            return
        doc = self.window_.open_pdf_safe(path) if self.window_ is not None else None
        if doc is None:
            # Keep the document already open (and show its name again).
            self.file.set_path(self._src, notify=False)
            return
        self._close_doc()
        self._doc, self._src = doc, path
        self._extra = {i: 0 for i in range(len(doc))}
        self.set_title("Rotate & Reorder", Path(path).name)
        self.set_pages(list(range(len(doc))), self.render, lambda k: f"p.{k + 1}")

    def deactivate(self):
        self._timer.stop()
        self.clear_pages()
        self._close_doc()
        self._src = ""
        self._extra = {}
        self.file.clear()
        self.set_title("Rotate & Reorder", SUBTITLE)

    def render(self, key: int) -> QImage:
        """Page *key* as a thumbnail, turned by its extra rotation."""
        mat = fitz.Matrix(THUMB_ZOOM, THUMB_ZOOM).prerotate(self._extra.get(key, 0))
        pix = self._doc[key].get_pixmap(matrix=mat, alpha=False)
        return QImage(pix.samples, pix.width, pix.height, pix.stride,
                      QImage.Format_RGB888).copy()

    # ── page actions ─────────────────────────────────────────────────────────
    def rotate(self, deg: int):
        order = self.order()
        for i in self.selected():
            k = order[i]
            self._extra[k] = (self._extra[k] + deg) % 360
            self.refresh(i)

    def move_pages(self, d: int):
        self.move(d)

    # ── save ─────────────────────────────────────────────────────────────────
    def save(self):
        if self._doc is None:
            return dialogs.warning("Save", "Open a PDF first.")
        out = dialogs.ask_save("reordered.pdf", ".pdf", [("PDF", "*.pdf")])
        if not out:
            return
        order, extra = self.order(), dict(self._extra)
        win = self.window_
        # The thumbnails read the document; none may render while the job uses it.
        self._timer.stop()

        def work(stop):
            self._release(out)
            organise.reorder(self._doc, order, extra, out)

        def then(kind, _value):
            if self._queue:
                self._timer.start()
            if kind == "done":
                win.set_status(f"✓  Saved → {Path(out).name}", "success")
                dialogs.info("Saved", f"PDF saved:\n{out}")

        if win.run_job(work, f"Saving {Path(out).name}…", lock=True, then=then, cancellable=False) is None \
                and self._queue:
            self._timer.start()
