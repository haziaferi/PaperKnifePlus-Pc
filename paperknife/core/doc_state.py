"""DocHolder: one open document, saved safely over itself, with whole-document undo.

The Qt document pages hold their file through it.
"""
from __future__ import annotations
import os
import shutil
import tempfile

import pymupdf as fitz

from ..job_queue import atomic_output
from .password import carry_open_password, open_password_of

UNDO_DEPTH = 10     # whole-document snapshots kept by the editing tools


def same_file(name: str, path: str) -> bool:
    """True when the document name *name* is the file at *path*.  A document
    opened from memory is named "pdf" (fitz.open("pdf", data)), which is no
    file, so it is never the same as anything."""
    return (bool(name) and os.path.isfile(name) and os.path.exists(path)
            and os.path.samefile(name, path))


def snapshot(doc) -> bytes:
    """*doc*'s content as bytes, for an undo step or an in-memory copy to go
    on with.  A file encrypted with an owner password only (none to open it)
    keeps its encryption: plain tobytes() writes it unencrypted and clears the
    document's own /Encrypt, so a later PDF_ENCRYPT_KEEP save had nothing to
    keep.  A file opened with a password is written plain: its password is
    put back on every file saved from it (core.password.protecting)."""
    if (doc.metadata or {}).get("encryption") and open_password_of(doc) is None:
        return doc.tobytes(encryption=fitz.PDF_ENCRYPT_KEEP)
    return doc.tobytes()


def can_append(doc) -> bool:
    """Whether *doc* can be saved by appending its edits to its own file: it
    was read from a file, is not encrypted (a kept or dropped password is
    written whole), and MuPDF can update it (not repaired on opening, and
    so on)."""
    # is_encrypted turns False once the password is given: the trailer says,
    # until tobytes() (an undo snapshot) clears its /Encrypt; the metadata
    # read at opening still names the encryption then.
    return (os.path.isfile(doc.name or "") and doc.xref_get_key(-1, "Encrypt")[0] == "null"
            and not (doc.metadata or {}).get("encryption")
            and doc.can_save_incrementally())


def append_edits(doc) -> None:
    """Append *doc*'s edits to the file it was read from (an incremental
    update: the file's bytes so far stay as they are, so a digital signature
    over them still holds, and a large file is not written again).

    MuPDF writes into the file itself, so a copy of it is kept beside it
    until the update is complete; if the update fails the copy is put back.
    Should the app die while appending, the copy (.<name>-*.pdf.bak) stays
    beside the file."""
    path = doc.name
    folder, name = os.path.split(path)
    stem, ext = os.path.splitext(name)
    fd, backup = tempfile.mkstemp(dir=folder or ".", prefix=f".{stem}-", suffix=ext + ".bak")
    os.close(fd)
    shutil.copy2(path, backup)
    try:
        doc.saveIncr()
    except Exception:
        try:
            # Copied back into the file, not moved over it: MuPDF holds it
            # open, and Windows refuses to replace an open file.
            with open(backup, "rb") as src, open(path, "r+b") as dst:
                shutil.copyfileobj(src, dst)
                dst.truncate()
        except OSError as err:
            raise OSError(f"The update failed and {name} could not be restored; "
                          f"its copy before the update is {backup}") from err
        os.remove(backup)
        raise
    os.remove(backup)


class DocHolder:
    """self._doc is the open document (or None); self._pg the current page."""
    _doc: fitz.Document | None = None
    _pg: int = 0

    def _close_doc(self) -> None:
        doc = self._doc
        if doc is not None:
            doc.close()
            self._doc = None

    def _holds(self, path: str) -> bool:
        """True when self._doc was read from the file at *path*."""
        doc = self._doc
        return doc is not None and same_file(doc.name, path)

    def _release(self, path: str) -> None:
        """Before *path* is replaced: if self._doc holds it, continue on an
        in-memory copy of the same content and close the file."""
        if self._holds(path):
            self._replace_doc(fitz.open("pdf", snapshot(self._doc)))

    def _save_doc(self, out: str, *, incremental: bool = False, **save_opts) -> str:
        """Save self._doc to *out*; "incremental" or "full", how it was written.

        incremental=True (the edits only add to the file: owner's choice
        2026-10-12) appends them to the file self._doc was read from, when
        *out* is that file and it can take an incremental update (append_edits).
        Otherwise the file is written whole, through atomic_output.

        Saving over the file self._doc was read from writes from the original
        (so save options such as encryption=PDF_ENCRYPT_KEEP still apply), then
        closes it before the replace and continues on an in-memory copy."""
        if incremental and self._holds(out) and can_append(self._doc):
            append_edits(self._doc)
            # MuPDF appends after the file as it was when opened: a second
            # update from the same document would overwrite the first.  Go
            # on from the file as it is now.
            self._replace_doc(fitz.open(out))
            return "incremental"
        self._write_whole(out, **save_opts)
        return "full"

    def _write_whole(self, out: str, **save_opts) -> None:
        doc = self._doc
        if not self._holds(out):
            with atomic_output(out) as tmp:
                doc.save(tmp, **save_opts)
            return
        with atomic_output(out) as tmp:
            doc.save(tmp, **save_opts)
            # Only after the save: a plain tobytes() writes unencrypted, and
            # an encryption=PDF_ENCRYPT_KEEP save after it would too.
            self._replace_doc(fitz.open("pdf", snapshot(doc)))

    # apply_redactions rewrites page resources as well as content, so undo
    # restores a serialised copy.  MuPDF's journal cannot be used: get_text on
    # a rotated page writes /Rotate outside an operation, which it refuses.
    def _push_undo(self) -> None:
        self._undo_stack = self._undo_stack[-(UNDO_DEPTH - 1):] + [
            (self._pg, snapshot(self._doc))]

    def _pop_undo(self) -> None:
        self._pg, data = self._undo_stack.pop()
        self._replace_doc(fitz.open("pdf", data))

    def _replace_doc(self, new) -> None:
        """Go on with *new* (a copy of self._doc's content) and close the old
        document; the password it was opened with goes with the content."""
        old = self._doc
        carry_open_password(old, new)
        self._doc = new
        old.close()
