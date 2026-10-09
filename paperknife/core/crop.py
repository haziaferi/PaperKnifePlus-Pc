"""Crop / Trim: cut margins off the crop box of chosen pages."""
from __future__ import annotations

import pymupdf as fitz

from ..job_queue import atomic_output


def parse_margins(top: str, right: str, bottom: str, left: str
                  ) -> tuple[float, float, float, float]:
    """The four margins typed as text (blank = 0), as (top, right, bottom, left).
    Raises ValueError with the message to show when they cannot be used."""
    try:
        mt = float(top    or "0")
        mr = float(right  or "0")
        mb = float(bottom or "0")
        ml = float(left   or "0")
    except ValueError:
        raise ValueError("Enter numeric values for all margins.") from None
    if min(mt, mr, mb, ml) < 0:
        raise ValueError("Margins cannot be negative.")
    if mt == mr == mb == ml == 0:
        raise ValueError("All margins are 0 — nothing to crop.")
    return mt, mr, mb, ml


def croppable(doc, pages, margins, reset: bool) -> int:
    """How many of *pages* crop_pdf would crop (the others are smaller than
    their margins), without changing *doc*: a caller can refuse before it
    asks where to save a copy nothing was done to."""
    mt, mr, mb, ml = margins
    n = 0
    for pg_num in pages:
        page = doc[pg_num]
        seen = page.mediabox * page.rotation_matrix if reset else page.rect
        if not fitz.Rect(ml, mt, seen.width - mr, seen.height - mb).is_empty:
            n += 1
    return n


def crop_pdf(doc, out: str, pages, margins, reset: bool, stop) -> int | None:
    """Cut *margins* (top, right, bottom, left, in points as the page is seen)
    off each 0-based page number in *pages* of *doc* (closed here), first
    resetting the crop box to the media box when *reset*.  Returns how many
    pages were cropped (a page smaller than its margins is skipped), or None
    if cancelled, writing nothing."""
    mt, mr, mb, ml = margins
    with atomic_output(out) as tmp, doc:
        cropped = 0
        for pg_num in pages:
            if stop.is_set():
                return None     # nothing written: atomic_output drops the file
            page = doc[pg_num]
            if reset:
                page.set_cropbox(page.mediabox)
            # Margins are given as the page is seen (page.rect, rotation
            # applied); the crop box lives in unrotated space.
            seen = fitz.Rect(ml, mt, page.rect.width - mr, page.rect.height - mb)
            if seen.is_empty:
                continue
            cb  = page.cropbox
            new = (seen * page.derotation_matrix).normalize()
            page.set_cropbox(new + (cb.x0, cb.y0, cb.x0, cb.y0))
            cropped += 1
        doc.save(tmp, deflate=True)
    return cropped
