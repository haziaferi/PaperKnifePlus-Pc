from __future__ import annotations
import re

import pymupdf as fitz

_PART = re.compile(r"^(\d+|end)(?:\s*-\s*(\d+|end))?$")

# Page sizes come from the PDF and are not bounded; a 200-inch page at
# 300 DPI would ask for a ~10 GB pixmap.
MAX_PIXELS = 100_000_000


class PageRangeError(ValueError):
    pass


def parse_ranges(text: str, total: int) -> list[tuple[int, int]]:
    """Parse '1-3, 5, 8-end' or 'all' (1-based) into 0-based inclusive
    (first, last) pairs.

    Raises PageRangeError for anything that does not name pages that exist,
    so a typo never silently selects other pages or none at all."""
    groups: list[tuple[int, int]] = []
    for raw in text.split(","):
        part = raw.strip().lower()
        if not part:
            continue
        if part == "all":
            groups.append((0, total - 1))
            continue
        m = _PART.match(part)
        if not m:
            raise PageRangeError(f"'{raw.strip()}' is not a page or page range "
                                 "(use e.g. 1-3, 5, 8-end).")
        a, b = (total if g == "end" else int(g) for g in (m[1], m[2] or m[1]))
        for n in (a, b):
            if n < 1:
                raise PageRangeError(f"'{raw.strip()}': pages start at 1.")
            if n > total:
                raise PageRangeError(f"'{raw.strip()}': page {n} does not exist "
                                     f"(the document has {total} page(s)).")
        if a > b:
            raise PageRangeError(f"'{raw.strip()}': the range runs backwards; "
                                 f"write {b}-{a}.")
        groups.append((a - 1, b - 1))
    if not groups:
        raise PageRangeError("No pages given.")
    return groups


def selected_pages(range_str: str, total: int) -> list[int]:
    """Sorted unique 0-based pages for a page-range field; blank or 'all' is
    every page.  Raises PageRangeError for input naming no real pages."""
    if not range_str.strip():
        return list(range(total))
    return sorted({p for a, b in parse_ranges(range_str, total)
                   for p in range(a, b + 1)})


def textwriter_point(page: fitz.Page, point) -> fitz.Point:
    """*point* in page text coordinates, moved so TextWriter.write_text puts
    it there: write_text shifts by the crop box's top edge where the PDF
    needs its bottom edge, so text lands off its baseline on a cropped page."""
    cb, mb = page.cropbox, page.mediabox
    return fitz.Point(point) + (0, cb.y0 - (mb.height - cb.y1))


def render(page: fitz.Page, scale: float, shrink: bool = False) -> fitz.Pixmap:
    """page.get_pixmap at *scale*, kept under MAX_PIXELS.

    An export (shrink=False) refuses a page that would exceed it; a preview
    (shrink=True) is drawn at the largest scale that fits instead."""
    w, h = page.rect.width * scale, page.rect.height * scale
    if w * h > MAX_PIXELS:
        if not shrink:
            raise ValueError(
                f"Page {page.number + 1} is too large to render at this resolution "
                f"({w:,.0f} × {h:,.0f} px); choose a lower DPI.")
        scale *= (MAX_PIXELS / (w * h)) ** 0.5
    return page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
