"""Password: add, change or remove a PDF's encryption."""
from __future__ import annotations
import secrets

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
