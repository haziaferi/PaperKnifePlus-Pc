"""
paperknife.tool_base
ToolBase ABC and the global tool registry.

Each tool file defines a subclass and decorates it with @register:

    from paperknife.tool_base import ToolBase, register

    @register
    class MergeTool(ToolBase):
        section = "ORGANISE"
        label   = "📎  Merge"

        def show(self) -> None:
            body = self.app._card_layout("📎  Merge PDFs", "…")
            ...

The registry is populated by tools/__init__.py importing every tool
module.  app.py then reads TOOLS to build the sidebar navigation.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
import os
import typing

import pymupdf as fitz

from .job_queue import atomic_output

UNDO_DEPTH = 10     # whole-document snapshots kept by the editing tools

if typing.TYPE_CHECKING:
    from .app import App

# ── Registry ──────────────────────────────────────────────────────────────────
TOOLS: list["ToolBase"] = []

def register(cls: type["ToolBase"]) -> type["ToolBase"]:
    """Class decorator: instantiate the tool and add it to the registry."""
    TOOLS.append(cls())
    return cls


# ── Base class ─────────────────────────────────────────────────────────────────
class ToolBase(ABC):
    """
    Minimal contract every tool must fulfil.

    Attributes
    ----------
    section : str   Sidebar section heading (READ / ORGANISE / ENHANCE / CONVERT /
                    CONTENT / SETTINGS); first-seen order sets sidebar order
    label   : str   Sidebar button label, including emoji prefix
    """
    section: str = "MISC"
    label:   str = "(unnamed)"

    # Set by activate() before show() is called — tools use self.app freely.
    app: "App"

    def activate(self, app: "App") -> None:
        """Called by App._nav_click.  Binds app context then renders the view."""
        self.app = app
        self.show()

    def deactivate(self) -> None:
        """Called by App._nav_click when the user leaves this tool.

        A document kept in self._doc is closed, so the file is not left open
        (on Windows an open file cannot be replaced by another tool's save)."""
        self._close_doc()

    def _close_doc(self) -> None:
        doc = getattr(self, "_doc", None)
        if doc is not None:
            doc.close()
            self._doc = None

    @abstractmethod
    def show(self) -> None:
        """Build the tool UI into self.app.main.  Called on every navigation."""
        ...

    # ── Convenience shortcuts ─────────────────────────────────────────────────
    def _card(self, title: str, subtitle: str = ""):
        return self.app._card_layout(title, subtitle)

    def _file_row(self, parent, var, btn_text="Open PDF", exts=(".pdf",)):
        return self.app._file_row(parent, var, btn_text, exts)

    # ── Background work ───────────────────────────────────────────────────────
    # PyMuPDF holds the GIL for each call, so page-by-page work in a job keeps
    # the window responsive while one long call (a save) still pauses it
    # (docs/performance-2026-10-08.md).  Dialogs stay on the Tk thread: ask
    # first, run the work, then report in done().
    def _run_job(self, work, label: str, done=None, settle=None) -> bool:
        """Run work(stop) in the background on documents it opened itself;
        done(result) runs on the Tk thread if it succeeds, settle(kind) after
        any outcome ("done", "error", "cancel")."""
        return self.app.run_job(work, label, then=self._then(done, settle)) is not None

    def _run_on_doc(self, work, label: str, done=None, settle=None) -> bool:
        """As _run_job for work that uses self._doc: until it ends the window
        cannot reach the document (no edits, no Open, no leaving the tool)."""
        return self.app.run_job(work, label, lock=True,
                                then=self._then(done, settle)) is not None

    def _then(self, done, settle=None):
        def then(kind, value):
            if settle is not None:
                settle(kind)
            if kind == "done" and done is not None:
                done(value)
            self._after_job(kind)
        return then

    def _after_job(self, kind: str) -> None:  # noqa: B027  (an optional hook)
        """Called on the Tk thread after every job this tool started."""

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
