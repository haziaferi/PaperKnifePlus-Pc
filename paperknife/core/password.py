"""Password: add, change or remove a PDF's encryption."""
from __future__ import annotations
import secrets
from dataclasses import dataclass, field

import pymupdf as fitz

from ..job_queue import atomic_output

ALL_PERMS = (fitz.PDF_PERM_PRINT | fitz.PDF_PERM_PRINT_HQ | fitz.PDF_PERM_COPY
             | fitz.PDF_PERM_MODIFY | fitz.PDF_PERM_ANNOTATE | fitz.PDF_PERM_FORM
             | fitz.PDF_PERM_ACCESSIBILITY | fitz.PDF_PERM_ASSEMBLE)


def owner_password(typed: str) -> str:
    """The owner password to use: *typed*, or a random one when it is blank.
    Anyone who knows the owner password gets every right, so an owner
    password equal to the open password would void the restrictions."""
    return typed or secrets.token_urlsafe(24)


def permissions(allow_print: bool, allow_copy: bool) -> int:
    """Every right, less printing and/or copying when they are not allowed."""
    perm = ALL_PERMS
    if not allow_print:
        perm &= ~(fitz.PDF_PERM_PRINT | fitz.PDF_PERM_PRINT_HQ)
    if not allow_copy:
        perm &= ~fitz.PDF_PERM_COPY
    return perm


def open_unlocked(src: str, password: str, any_encryption: bool = False):
    """The document at *src*, authenticated with *password* when it needs one
    to open (or, with *any_encryption*, whenever it is encrypted at all); None
    when the password is wrong.  An error opening the file propagates."""
    doc = fitz.open(src)
    locked = doc.is_encrypted if any_encryption else doc.needs_pass
    if locked and not doc.authenticate(password):
        doc.close()
        return None
    return doc


def protect_pdf(doc, out: str, user_pw: str, owner_pw: str, perm: int) -> None:
    """Save *doc* (closed here) to *out* with AES-256 encryption."""
    with atomic_output(out) as tmp, doc:
        doc.save(tmp, encryption=fitz.PDF_ENCRYPT_AES_256,
                 user_pw=user_pw, owner_pw=owner_pw, permissions=perm)


def unprotect_pdf(doc, out: str) -> None:
    """Save the authenticated *doc* (closed here) to *out* without encryption."""
    with atomic_output(out) as tmp, doc:
        doc.save(tmp, encryption=fitz.PDF_ENCRYPT_NONE)


# ── An input's open password, kept for the files written from it ─────────────
# The password typed to open a document lives on that document object only:
# never in prefs, logs or a module-level cache, and it is dropped when the
# document is closed.
@dataclass(frozen=True)
class OpenPassword:
    """What a new file needs to be protected like its input: the input's file
    name (for the question), the open password typed and the input's
    permissions.  Its repr never shows the password."""
    name: str
    user_pw: str = field(repr=False)
    perm: int = ALL_PERMS


class _KeptPasswordDocument(fitz.Document):
    """A document holding its OpenPassword; close() forgets it first."""
    __slots__ = ()

    def close(self):
        self.__dict__.pop("_pk_open_password", None)
        super().close()


def input_permissions(doc) -> int:
    """The permissions written in *doc*'s encryption dictionary (/P).  Not
    doc.permissions: that is the rights granted, every right when the owner
    password was the one typed."""
    kind, value = doc.xref_get_key(-1, "Encrypt/P")
    return int(value) if kind == "int" else doc.permissions


def keep_open_password(doc, name: str, user_pw: str) -> None:
    """Keep *user_pw* (the password *doc* was opened with) and its input's
    permissions on *doc* until it is closed."""
    _attach(doc, OpenPassword(name, user_pw, input_permissions(doc)))


def open_password_of(doc) -> OpenPassword | None:
    """The OpenPassword *doc* holds, or None (never protected, or closed)."""
    if doc is None or getattr(doc, "is_closed", True):
        return None
    return getattr(doc, "_pk_open_password", None)


def carry_open_password(old, new) -> None:
    """*new* replaces *old* (an in-memory copy of it): it holds *old*'s
    OpenPassword from now on.  Call before closing *old*."""
    kept = open_password_of(old)
    if kept is not None:
        _attach(new, kept)


def _attach(doc, kept: OpenPassword) -> None:
    if not isinstance(doc, _KeptPasswordDocument):
        doc.__class__ = _KeptPasswordDocument
    doc._pk_open_password = kept


def reprotect(path: str, user_pw: str, perm: int) -> None:
    """Re-save the unencrypted PDF at *path* over itself with AES-256: open
    password *user_pw*, permissions *perm*, and a random owner password (the
    Password tool's rule for a blank one)."""
    doc = fitz.open(path)
    try:
        with atomic_output(path) as tmp:
            doc.save(tmp, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=user_pw,
                     owner_pw=owner_password(""), permissions=perm)
            doc.close()             # the file is replaced next: let it go
    finally:
        if not doc.is_closed:
            doc.close()
