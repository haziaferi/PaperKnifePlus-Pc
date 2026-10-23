"""SharedDocument: the one open document of a window (owner's decision 2026-10-23).

Every tool works on it; its edits pile up, unsaved, on one undo history until
Save writes them over its file or Save as to another.  Toolkit-free: the Qt
window owns one and listens to it.
"""
from __future__ import annotations

import os

import pymupdf as fitz

from .doc_state import UNDO_DEPTH, DocHolder, snapshot


class Step:
    """One edit on the undo history: the document before (or after, on the
    redo history) it, the page shown then, and *extra*: what the tool that
    made it keeps beside the document (its own state), handed back on undo."""
    __slots__ = ("label", "data", "pg", "extra", "seq")

    def __init__(self, label: str, data: bytes, pg: int, extra=None, seq: int = 0):
        self.label, self.data, self.pg, self.extra, self.seq = label, data, pg, extra, seq


class SharedDocument(DocHolder):
    """The open PDF (self.doc), the file it belongs to (self.path), whether
    it holds unsaved edits (self.dirty) and one undo / redo history.

    listen(fn): fn(event) after each change; event is "opened", "changed"
    (an edit, an undo, a redo), "saved" (dirty is now False, path may be
    new) or "closed"."""

    def __init__(self):
        self.path = ""
        self.dirty = False
        self.edits = 0                  # counts every change: crash recovery's cue
        self.adds_only = True           # every edit since the last save only added
        self._undo: list[Step] = []
        self._redo: list[Step] = []
        self._listeners = []
        self._seq = 0                   # one counter for steps and for tools' marks
        self._saved_at = 0              # the step the file holds (the save point)
        self._loose = False             # a change with no step since the save point
        self._begun = False             # begin() was called, changed() is to come

    def _at_save_point(self) -> None:
        self.dirty, self.adds_only = False, True
        self._saved_at, self._loose = self.last_step_seq(), False

    def tick(self) -> int:
        """The next number of the counter the history's steps take too: a
        tool numbers its own marks with it, so its undo can tell whether a
        mark or the document's last step came later."""
        self._seq += 1
        return self._seq

    def last_step_seq(self) -> int:
        """The number of the step undo would take back (0: none)."""
        return self._undo[-1].seq if self._undo else 0

    # ── listeners ──
    def listen(self, fn) -> None:
        self._listeners.append(fn)

    def _tell(self, event: str) -> None:
        for fn in list(self._listeners):
            fn(event)

    # ── the document ──
    @property
    def doc(self) -> fitz.Document | None:
        return self._doc

    @property
    def name(self) -> str:
        """The file's name ("" with none open)."""
        return os.path.basename(self.path) if self.path else ""

    def is_open(self) -> bool:
        return self._doc is not None

    def open(self, path: str, doc: fitz.Document) -> None:
        """Hold *doc*, read from *path*, in place of the document before: no
        unsaved edits and no history."""
        self._close_doc()
        self._doc, self.path, self._pg = doc, str(path), 0
        self._undo, self._redo = [], []
        self._at_save_point()
        self._tell("opened")

    def close(self) -> None:
        if self._doc is None and not self.path:
            return
        self._close_doc()
        self.path = ""
        self._undo, self._redo = [], []
        self._at_save_point()
        self._tell("closed")

    def forget_edits(self) -> None:
        """The unsaved edits are given up (the question's Discard): clean,
        no history; the content stays until the document is replaced."""
        self._undo, self._redo = [], []
        self._at_save_point()

    # ── edits ──
    def begin(self, label: str, extra=None, pg: int | None = None) -> None:
        """Before an edit made in place on self.doc: the document as it is
        goes on the undo history (finish with changed())."""
        page = self._pg if pg is None else pg
        self._undo = self._undo[-(UNDO_DEPTH - 1):] + [
            Step(label, snapshot(self._doc), page, extra, self.tick())]
        self._redo = []
        self._begun = True

    def changed(self, adds: bool = False) -> None:
        """After an edit (begun with begin(), or one that keeps no history,
        such as a mark a tool holds beside the document): it is unsaved.
        adds: the edit only added to the document (a note, a highlight), so
        a Save over its file may append it."""
        if not self._begun:
            self._loose = True          # no step to undo it by: unsaved until a save
        self._begun = False
        self.dirty = True
        self.adds_only = self.adds_only and adds
        self.edits += 1
        self._tell("changed")

    def abandon(self) -> None:
        """An edit begun with begin() failed half-way: the document as it was
        before it, and the step off the history; nothing is marked changed."""
        self._begun = False
        if self._undo:
            step = self._undo.pop()
            self._replace_doc(fitz.open("pdf", step.data))

    def drop_step(self) -> None:
        """An edit begun with begin() changed nothing after all (a drag over
        empty paper): its step goes, the document stays as it is."""
        self._begun = False
        if self._undo:
            self._undo.pop()

    def edit(self, label: str, fn, extra=None, adds: bool = False):
        """Run fn(doc) as one undoable edit; its result.  When fn raises, the
        document is put back as it was and the error goes on."""
        self.begin(label, extra)
        try:
            result = fn(self._doc)
        except BaseException:
            self.abandon()
            raise
        self.changed(adds)
        return result

    def replace(self, new: fitz.Document, label: str, extra=None) -> None:
        """*new* (a whole new content: a tool's output) takes the document's
        place as one undoable edit; the open password goes with it."""
        self.begin(label, extra)
        self._replace_doc(new)
        self.changed()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo_label(self) -> str:
        return self._undo[-1].label if self._undo else ""

    def undo(self) -> Step | None:
        """Go back one edit; the Step undone (its extra is the tool's state
        then), or None when there is none."""
        return self._swap(self._undo, self._redo)

    def redo(self) -> Step | None:
        return self._swap(self._redo, self._undo)

    def _swap(self, src: list, dst: list) -> Step | None:
        if not src or self._doc is None:
            return None
        step = src.pop()
        dst.append(Step(step.label, snapshot(self._doc), self._pg, step.extra, step.seq))
        self._pg = step.pg
        self._replace_doc(fitz.open("pdf", step.data))
        # Back at the save point: clean again (a change with no step keeps it unsaved).
        self.dirty = self._loose or self.last_step_seq() != self._saved_at
        self.adds_only = not self.dirty
        self.edits += 1
        self._tell("changed")
        return step

    # ── saving ──
    def save(self, **opts) -> str:
        """Write the document over its file: "incremental" (every edit since
        the last save only added: appended to the file, owner's choice
        2026-10-12) or "full"."""
        how = self._save_doc(self.path, incremental=self.adds_only, **opts)
        self._at_save_point()
        self._tell("saved")
        return how

    def save_as(self, out: str, **opts) -> None:
        """Write the document to *out*, which it belongs to from now on."""
        self._save_doc(out, **opts)
        self.path = str(out)
        self._at_save_point()
        self._tell("saved")
