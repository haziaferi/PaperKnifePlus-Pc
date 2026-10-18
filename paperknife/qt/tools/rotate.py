"""Rotate & Reorder — a page organiser (group B): turn, move and delete pages,
save in the new order, or extract the selected pages to a new PDF (owner,
2026-10-17: Delete asks first and Undo brings the pages back, as in the
editing tools' page strip)."""
from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
from PySide6.QtGui import QImage

from ...core import organise
from ...core.doc_state import can_append
from ...pages import ranges_text
from .. import dialogs, theme
from ..pages import HeldDoc, OrganiserPage, ask_keep_password, register_page

# Scored winners (phase10/rotate_score.py, owner 2026-10-17).
SUBTITLE = "Select pages · then rotate, move, delete or extract them"
KEEP_ONE = "A PDF needs at least one page: keep one or more."
THUMB_ZOOM = 0.28           # thumbnail render scale


@register_page("RotateTool")
class RotatePage(HeldDoc, OrganiserPage):
    def __init__(self, tool=None, window=None):
        super().__init__("Rotate & Reorder", SUBTITLE, tool=tool, window=window)
        self._extra: dict[int, int] = {}
        self._undo: list = []
        self._shown = None
        for text, deg in (("↺ 90° CCW", -90), ("↻ 90° CW", 90), ("⤢ 180°", 180)):
            self.add_action(text, None, lambda _=False, d=deg: self.rotate(d))
        self.add_action("← Move Left", None, lambda _=False: self.move_pages(-1))
        self.add_action("Move Right →", None, lambda _=False: self.move_pages(1))
        # Delete last, apart from the turn and move buttons (the scored order).
        self.add_action("Extract to a new PDF", None, lambda _=False: self.extract())
        self.undo_btn = self.add_action("Undo", None, lambda _=False: self.undo(),
                                        needs_selection=False)
        self.delete_btn = self.add_action("Delete", None, lambda _=False: self.delete_pages())
        self.grid.model().rowsMoved.connect(lambda *_: self._edited())     # a drag
        self.primary("Save PDF", self.save)
        self._show_undo()

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
        self._undo, self._shown = [], self._state()
        self._show_undo()

    def clear_document(self):
        self._timer.stop()
        self.clear_pages()
        self.release_held()
        self._extra = {}
        self._saved = None
        self._undo, self._shown = [], None
        self._show_undo()
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
        """Pages turned, moved or deleted since the file was opened or saved."""
        return self._doc is not None and self._saved is not None and self._state() != self._saved

    def recovery_state(self) -> dict | None:
        order, extra = self._state()
        return {"order": order, "extra": {str(k): v for k, v in extra.items()}}

    def apply_recovery(self, state: dict) -> bool:
        n = len(self._doc)
        order = [int(k) for k in state["order"]]
        if not order or len(set(order)) != len(order) or not set(order) <= set(range(n)):
            return False
        self._extra = {i: int(state["extra"].get(str(i), 0)) % 360 for i in range(n)}
        self.set_pages(order, self.render, lambda k: f"p.{k + 1}")
        self._shown = self._state()
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
        self._edited()

    def move_pages(self, d: int):
        self.move(d)
        self._edited()

    def delete_pages(self):
        """Delete the selected pages, after asking; Undo brings them back."""
        rows = self.selected()
        if not rows or self._doc is None:
            return
        if len(rows) == self.grid.count():
            return                          # Delete is off then; the bar says why
        order = self.order()
        nums = sorted(order[r] + 1 for r in rows)
        what = (f"page {nums[0]}" if len(nums) == 1 else
                f"pages {nums[0]} and {nums[1]}" if len(nums) == 2 else
                "pages " + ranges_text([n - 1 for n in nums]))
        if not dialogs.ask_yes_no("Delete pages",
                                  f"Delete {what}? Undo brings them back until you save."):
            return
        for r in sorted(rows, reverse=True):
            self.grid.takeItem(r)
        self._show_grid_state()
        self._selection_changed()
        self._edited()

    # ── undo (Ctrl+Z and the bar's Undo) ─────────────────────────────────────
    def _edited(self):
        """After an edit: the state before it goes on the undo list."""
        if self._shown is not None and self._shown != self._state():
            self._undo.append(self._shown)
        self._shown = self._state()
        self._show_undo()

    def undo(self):
        if not self._undo or self._doc is None:
            return
        order, extra = self._undo.pop()
        self._extra = dict(extra)
        self.set_pages(order, self.render, lambda k: f"p.{k + 1}")
        self._shown = self._state()
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
            self.undo_btn.setEnabled(bool(self._undo))

    # ── extract ──────────────────────────────────────────────────────────────
    def extract(self):
        """The selected pages, in their order on the grid and as turned, to a
        new PDF; the document here is not changed."""
        rows = self.selected()
        if not rows or self._doc is None:
            return
        order = self.order()
        pages, extra = [order[r] for r in rows], dict(self._extra)
        out = dialogs.ask_save("extracted.pdf", ".pdf", [("PDF", "*.pdf")])
        if not out:
            return
        if self._holds(out):
            return dialogs.warning("Extract", "Choose another file: this one is the PDF open here.")
        kept = ask_keep_password(self._doc)
        win = self.window_
        self._timer.stop()

        def work(stop):
            organise.reorder(self._doc, pages, extra, out)

        def then(kind, _value):
            if self._queue:
                self._timer.start()
            if kind == "done":
                n = len(pages)
                win.set_status(f"✓  Extracted {n} page{'s' if n != 1 else ''} → {Path(out).name}",
                               "success")
                dialogs.info("Extracted", f"PDF saved:\n{out}")
                self.offer_output(out)

        if win.run_job(work, f"Extracting to {Path(out).name}…", lock=True, then=then,
                       cancellable=False, keep_password=(kept, [out])) is None and self._queue:
            self._timer.start()

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
        # open document itself.  Deleted pages would stay inside an appended
        # file: then it is written whole.
        appending = (self._holds(out) and can_append(self._doc)
                     and len(order) == len(self._doc))
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
                self._undo, self._shown = [], self._state()                  # undo ends at a save
                self._show_undo()
                win.set_status(f"✓  Saved → {Path(out).name}", "success")
                dialogs.info("Saved", f"PDF saved:\n{out}")
                if self.saved_elsewhere(out):
                    self.offer_output(out)
                if callable(after):
                    after()

        if win.run_job(work, f"Saving {Path(out).name}…", lock=True, then=then, cancellable=False,
                       keep_password=(kept, [out])) is None and self._queue:
            self._timer.start()
