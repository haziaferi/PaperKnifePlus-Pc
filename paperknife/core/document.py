"""SharedDocument: the one open document of a window (owner's decision 2026-10-23).

Every tool works on it; its edits pile up, unsaved, on one undo history until
Save writes them over its file or Save as to another.  Toolkit-free: the Qt
window owns one and listens to it.
"""
from __future__ import annotations

import os

import pymupdf as fitz

from .doc_state import UNDO_DEPTH, DocHolder


class Step:
    """One edit on the undo history: the document before (or after, on the
    redo history) it, the page shown then, and *extra*: what the tool that
    made it keeps beside the document (its own state), handed back on undo."""
    __slots__ = ("label", "data", "pg", "extra")

    def __init__(self, label: str, data: bytes, pg: int, extra=None):
        self.label, self.data, self.pg, self.extra = label, data, pg, extra


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
        self._undo: list[Step] = []
        self._redo: list[Step] = []
        self._listeners = []

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
        self.dirty = False
        self._undo, self._redo = [], []
        self._tell("opened")

    def close(self) -> None:
        if self._doc is None and not self.path:
            return
        self._close_doc()
        self.path, self.dirty = "", False
        self._undo, self._redo = [], []
        self._tell("closed")

    # ── edits ──
    def begin(self, label: str, extra=None, pg: int | None = None) -> None:
        """Before an edit made in place on self.doc: the document as it is
        goes on the undo history (finish with changed())."""
        page = self._pg if pg is None else pg
        self._undo = self._undo[-(UNDO_DEPTH - 1):] + [Step(label, self._doc.tobytes(), page, extra)]
        self._redo = []

    def changed(self) -> None:
        """After an edit (begun with begin(), or one that keeps no history,
        such as a mark a tool holds beside the document): it is unsaved."""
        self.dirty = True
        self.edits += 1
        self._tell("changed")

    def edit(self, label: str, fn, extra=None):
        """Run fn(doc) as one undoable edit; its result.  When fn raises, the
        document is put back as it was and the error goes on."""
        self.begin(label, extra)
        try:
            result = fn(self._doc)
        except BaseException:
            step = self._undo.pop()
            self._replace_doc(fitz.open("pdf", step.data))
            raise
        self.changed()
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
        dst.append(Step(step.label, self._doc.tobytes(), self._pg, step.extra))
        self._pg = step.pg
        self._replace_doc(fitz.open("pdf", step.data))
        self.changed()
        return step

    # ── saving ──
    def save(self, *, appends_only: bool = False, **opts) -> str:
        """Write the document over its file: "incremental" (the edits only
        add, appended to the file) or "full"."""
        how = self._save_doc(self.path, incremental=appends_only, **opts)
        self.dirty = False
        self._tell("saved")
        return how

    def save_as(self, out: str, **opts) -> None:
        """Write the document to *out*, which it belongs to from now on."""
        self._save_doc(out, **opts)
        self.path, self.dirty = str(out), False
        self._tell("saved")
