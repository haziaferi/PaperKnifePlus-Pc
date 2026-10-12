"""Rotate & Reorder — a page organiser (group B): turn and move pages, save in the new order."""
from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
from PySide6.QtGui import QImage

from ...core import organise
from ...core.doc_state import can_append
from .. import dialogs
from ..pages import HeldDoc, OrganiserPage, ask_keep_password, register_page

SUBTITLE = "Click a thumbnail · then rotate or move it"
THUMB_ZOOM = 0.28           # thumbnail render scale


@register_page("RotateTool")
class RotatePage(HeldDoc, OrganiserPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Rotate & Reorder", SUBTITLE, tool=tool, window=window)
        self._extra: dict[int, int] = {}
        for text, deg in (("↺ 90° CCW", -90), ("↻ 90° CW", 90), ("⤢ 180°", 180)):
            self.add_action(text, None, lambda _=False, d=deg: self.rotate(d))
        self.add_action("← Move Left", None, lambda _=False: self.move_pages(-1))
        self.add_action("Move Right →", None, lambda _=False: self.move_pages(1))
        self.primary("Save PDF", self.save)

    # ── document ─────────────────────────────────────────────────────────────
    def load(self, path: str):
        if not path:
            return
        doc = self.open_held(path, "Rotate & Reorder")
        if doc is None:
            return
        self._extra = {i: 0 for i in range(len(doc))}
        self.set_pages(list(range(len(doc))), self.render, lambda k: f"p.{k + 1}")
        self._saved = self._state()

    def clear_document(self):
        self._timer.stop()
        self.clear_pages()
        self.release_held()
        self._extra = {}
        self._saved = None
        self.refresh_document()

    def park_document(self):
        if self._doc is not None and not self.is_dirty():
            self._timer.stop()              # no thumbnail may render from a closed file
            self._queue = []
        super().park_document()

    _saved = None

    def _state(self):
        return self.order(), dict(self._extra)

    def is_dirty(self) -> bool:
        """Pages turned or moved since the file was opened or saved."""
        return self._doc is not None and self._saved is not None and self._state() != self._saved

    def recovery_state(self) -> dict | None:
        order, extra = self._state()
        return {"order": order, "extra": {str(k): v for k, v in extra.items()}}

    def apply_recovery(self, state: dict) -> bool:
        n = len(self._doc)
        order = [int(k) for k in state["order"]]
        if sorted(order) != list(range(n)):
            return False
        self._extra = {i: int(state["extra"].get(str(i), 0)) % 360 for i in range(n)}
        self.set_pages(order, self.render, lambda k: f"p.{k + 1}")
        return True

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
    def save(self, after=None):
        if self._doc is None:
            return dialogs.warning("Save", "Open a PDF first.")
        out = dialogs.ask_save("reordered.pdf", ".pdf", [("PDF", "*.pdf")])
        if not out:
            return
        kept = ask_keep_password(self._doc)
        order, extra = self.order(), dict(self._extra)
        win = self.window_
        # Turning and moving pages removes nothing: over its own file the
        # edits are appended to it (owner's choice 2026-10-12), made on the
        # open document itself.
        appending = self._holds(out) and can_append(self._doc)
        # The thumbnails read the document; none may render while the job uses it.
        self._timer.stop()

        def work(stop):
            if appending:
                organise.turn_in_place(self._doc, order, extra)
                self._save_doc(out, incremental=True)
                return
            self._release(out)
            organise.reorder(self._doc, order, extra, out)

        def then(kind, _value):
            if appending and kind != "done":
                self.load(self._src)                # the open copy may be half turned
            elif appending:
                # The document is in the new order now: its pages from the top.
                self._extra = {i: 0 for i in range(len(self._doc))}
                self.set_pages(list(range(len(self._doc))), self.render, lambda k: f"p.{k + 1}")
            if self._queue:
                self._timer.start()
            if kind == "done":
                self._saved = self._state() if appending else (order, extra)   # the edits are saved
                win.set_status(f"✓  Saved → {Path(out).name}", "success")
                dialogs.info("Saved", f"PDF saved:\n{out}")
                if self.saved_elsewhere(out):
                    self.offer_output(out)
                if callable(after):
                    after()

        if win.run_job(work, f"Saving {Path(out).name}…", lock=True, then=then, cancellable=False,
                       keep_password=(kept, [out])) is None and self._queue:
            self._timer.start()
