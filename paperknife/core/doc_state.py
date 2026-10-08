"""DocHolder: one open document, saved safely over itself, with whole-document undo.

Shared by the CustomTkinter tools (tool_base.ToolBase) and the Qt pages.
"""
from __future__ import annotations
import os

import pymupdf as fitz

from ..job_queue import atomic_output

UNDO_DEPTH = 10     # whole-document snapshots kept by the editing tools


class DocHolder:
    """self._doc is the open document (or None); self._pg the current page."""
    _doc: fitz.Document | None = None
    _pg: int = 0

    def _close_doc(self) -> None:
        doc = getattr(self, "_doc", None)
        if doc is not None:
            doc.close()
            self._doc = None

    # ── Saving the document held in self._doc ─────────────────────────────────
    def _holds(self, path: str) -> bool:
        """True when self._doc was read from the file at *path*."""
        doc = getattr(self, "_doc", None)
        return (doc is not None and bool(doc.name) and os.path.exists(path)
                and os.path.samefile(doc.name, path))

    def _release(self, path: str) -> None:
        """Before *path* is replaced: if self._doc holds it, continue on an
        in-memory copy of the same content and close the file."""
        if self._holds(path):
            doc = self._doc
            self._doc = fitz.open("pdf", doc.tobytes())
            doc.close()

    def _save_doc(self, out: str, **save_opts) -> None:
        """Save self._doc to *out* through atomic_output.

        Saving over the file self._doc was read from writes from the original
        (so save options such as encryption=PDF_ENCRYPT_KEEP still apply), then
        closes it before the replace and continues on an in-memory copy."""
        doc = self._doc
        if not self._holds(out):
            with atomic_output(out) as tmp:
                doc.save(tmp, **save_opts)
            return
        with atomic_output(out) as tmp:
            doc.save(tmp, **save_opts)
            # Only after the save: tobytes() writes unencrypted, and an
            # encryption=PDF_ENCRYPT_KEEP save after it would too.
            self._doc = fitz.open("pdf", doc.tobytes())
            doc.close()

    # ── Whole-document undo for the editing tools ─────────────────────────────
    # apply_redactions rewrites page resources as well as content, so undo
    # restores a serialised copy.  MuPDF's journal cannot be used: get_text on
    # a rotated page writes /Rotate outside an operation, which it refuses.
    def _push_undo(self) -> None:
        self._undo_stack = self._undo_stack[-(UNDO_DEPTH - 1):] + [
            (self._pg, self._doc.tobytes())]

    def _pop_undo(self) -> None:
        self._pg, data = self._undo_stack.pop()
        self._doc.close()
        self._doc = fitz.open("pdf", data)
