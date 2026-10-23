"""Rotate & Reorder — a page organiser (group B): turn, move and delete pages,
or extract the selected pages to a new PDF (owner, 2026-10-17: Delete asks
first and Undo brings the pages back, as in the editing tools' page strip).

Each turn, move or delete changes the window's document at once, as one
undoable edit (one document per window, owner 2026-10-23); Save writes it."""
from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

from ...core import organise
from .. import dialogs, theme
from ..pages import (KEEP_ONE, HeldDoc, OrganiserPage, _rearrange, ask_keep_password,
                     delete_question, register_page)

# Scored winners (phase10/rotate_score.py, owner 2026-10-17); KEEP_ONE and
# the delete question are shared with the editors' page strip.
SUBTITLE = "Select pages · then rotate, move, delete or extract them"
THUMB_ZOOM = 0.28           # thumbnail render scale


def _label(k: int) -> str:
    return f"p.{k + 1}"


@register_page("RotateTool")
class RotatePage(HeldDoc, OrganiserPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Rotate & Reorder", SUBTITLE, tool=tool, window=window)
        for text, deg in (("↺ 90° CCW", -90), ("↻ 90° CW", 90), ("⤢ 180°", 180)):
            self.add_action(text, None, lambda _=False, d=deg: self.rotate(d))
        self.add_action("← Move Left", None, lambda _=False: self.move_pages(-1))
        self.add_action("Move Right →", None, lambda _=False: self.move_pages(1))
        # Delete last, apart from the turn and move buttons (the scored order).
        self.add_action("Extract to a new PDF", None, lambda _=False: self.extract())
        self.undo_btn = self.add_action("Undo", None, lambda _=False: self.undo(),
                                        needs_selection=False)
        self.delete_btn = self.add_action("Delete", None, lambda _=False: self.delete_pages())
        self.grid.model().rowsMoved.connect(lambda *_: self._dragged())
        self.primary("Save PDF", self.save)
        self._show_undo()

    # ── document ─────────────────────────────────────────────────────────────
    def load(self, path: str):
        if not path:
            return
        doc = self.open_held(path, "Rotate & Reorder")
        if doc is None:
            return
        self.set_pages(list(range(len(doc))), self.render, _label)
        self._show_undo()

    def clear_document(self):
        self._timer.stop()
        self.clear_pages()
        self.release_held()
        self._show_undo()
        self.refresh_document()

    def document_replaced(self):
        """Another tool's edit or an undo: the pages as they are now."""
        keep = self.selected()
        self.set_pages(list(range(len(self._doc))), self.render, _label)
        self._reselect([r for r in keep if r < self.grid.count()])
        self._show_undo()

    def render(self, key: int) -> QImage:
        """Page *key* as a thumbnail, as turned."""
        pix = self._doc[key].get_pixmap(matrix=fitz.Matrix(THUMB_ZOOM, THUMB_ZOOM), alpha=False)
        return QImage(pix.samples, pix.width, pix.height, pix.stride,
                      QImage.Format_RGB888).copy()

    def _rekey(self):
        """The grid's rows are the document's pages in order again (after a
        move or a delete): each thumbnail keeps its picture."""
        for r in range(self.grid.count()):
            it = self.grid.item(r)
            it.setData(Qt.UserRole, r)
            it.setText(_label(r))

    def _reselect(self, rows):
        self.grid.clearSelection()
        for r in rows:
            self.grid.item(r).setSelected(True)

    # ── page actions: each one edit of the document ──────────────────────────
    def rotate(self, deg: int):
        rows = self.selected()
        if not rows or self._doc is None:
            return

        def turn(doc):
            for r in rows:
                p = doc[r]
                p.set_rotation((p.rotation + deg) % 360)
        self.edit_document("Rotate pages", turn, adds=True)   # removes nothing: appended
        for r in rows:
            self.refresh(r)
        self._edited()

    def move_pages(self, d: int):
        before = self.order()
        self.move(d)
        self._apply_order(before, "Move pages")

    def _dragged(self):
        if self._doc is not None:
            self._apply_order(list(range(len(self._doc))), "Move pages")

    def _apply_order(self, before, label: str):
        order = self.order()
        if self._doc is None or order == before:
            return
        sel = self.selected()
        try:
            self.edit_document(label, lambda doc: _rearrange(doc, order), adds=True)
        except Exception as e:      # the document is as it was (SharedDocument.edit)
            self.document_replaced()
            return dialogs.error("Rotate & Reorder", f"The pages could not be moved:\n{e}")
        self._rekey()
        self._reselect(sel)
        self._edited()

    def delete_pages(self):
        """Delete the selected pages, after asking; Undo brings them back."""
        rows = self.selected()
        if not rows or self._doc is None:
            return
        if len(rows) == self.grid.count():
            return                          # Delete is off then; the bar says why
        if not dialogs.ask_yes_no("Delete pages", delete_question(r + 1 for r in rows)):
            return
        gone = set(rows)
        keep = [i for i in range(len(self._doc)) if i not in gone]
        self.edit_document("Delete pages", lambda doc: _rearrange(doc, keep))
        for r in sorted(rows, reverse=True):
            self.grid.takeItem(r)
        self._rekey()
        self._show_grid_state()
        self._selection_changed()
        self._edited()

    # ── undo (Ctrl+Z and the bar's Undo: the document's last edit) ───────────
    def _edited(self):
        self._show_undo()

    def undo(self):
        if self.window_ is not None:
            self.window_.undo()
        self._show_undo()

    def _selection_changed(self):
        super()._selection_changed()
        # Every page selected: Delete is off and the bar says why (the scored
        # winner, as Merge does when every page is left out).
        if not hasattr(self, "delete_btn"):
            return
        n, total = len(self.grid.selectedItems()), self.grid.count()
        every = bool(total) and n == total
        self.delete_btn.setEnabled(bool(n) and not every)
        if every:
            self.hint_label.setText(KEEP_ONE)
        theme.label_role(self.hint_label, "warning" if every else "muted")

    def _show_undo(self):
        if hasattr(self, "undo_btn"):
            sd = self._shared()
            self.undo_btn.setEnabled(bool(sd is not None and self.shows_document()
                                          and sd.can_undo()))

    # ── extract ──────────────────────────────────────────────────────────────
    def extract(self):
        """The selected pages, in their order, to a new PDF; the document
        here is not changed."""
        rows = self.selected()
        if not rows or self._doc is None:
            return
        out = dialogs.ask_save("extracted.pdf", ".pdf", [("PDF", "*.pdf")])
        if not out:
            return
        if self._holds(out):
            return dialogs.warning("Extract", "Choose another file: this one is the PDF open here.")
        kept = ask_keep_password(self._doc)
        win = self.window_
        self._timer.stop()

        def work(stop):
            organise.reorder(self._doc, rows, dict.fromkeys(rows, 0), out)   # turns are in the pages

        def then(kind, _value):
            if self._queue:
                self._timer.start()
            if kind == "done":
                n = len(rows)
                win.set_status(f"✓  Extracted {n} page{'s' if n != 1 else ''} → {Path(out).name}",
                               "success")
                dialogs.info("Extracted", f"PDF saved:\n{out}")
                self.offer_output(out)

        if win.run_job(work, f"Extracting to {Path(out).name}…", lock=True, then=then,
                       cancellable=False, keep_password=(kept, [out])) is None and self._queue:
            self._timer.start()

    # ── save (the window's, over the file) ───────────────────────────────────
    def save(self, after=None):
        if self._doc is None:
            return dialogs.warning("Save", "Open a PDF first.")
        return self.window_.save(after)
