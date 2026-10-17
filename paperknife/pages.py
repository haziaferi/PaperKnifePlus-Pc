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


def ranges_text(pages) -> str:
    """The page-range text for the 0-based *pages* ('1-3, 5'); '' for none.
    The inverse of selected_pages for the grid's selection (owner, 2026-10-17:
    the grid and the range field stay in step)."""
    out, run = [], None
    for p in sorted(set(pages)):
        if run is not None and p == run[1] + 1:
            run[1] = p
            continue
        if run is not None:
            out.append(run)
        run = [p, p]
    if run is not None:
        out.append(run)
    return ", ".join(f"{a + 1}" if a == b else f"{a + 1}-{b + 1}" for a, b in out)


# ── Split's parts (owner, 2026-10-17: cut marks on the grid, "Selected pages
# to one part", typed ranges and bookmarks all set the same parts) ──
def parse_parts(text: str, total: int) -> list[list[int]]:
    """Each comma-separated item of *text* is one part: a page, a range, or
    pages joined by '+' ('1-3, 2+5+7' is two parts).  Blank: one part per
    page.  Raises PageRangeError as parse_ranges."""
    if not text.strip():
        return [[i] for i in range(total)]
    parts = []
    for item in text.split(","):
        if not item.strip():
            continue
        pages: list[int] = []
        for piece in item.split("+"):
            for a, b in parse_ranges(piece, total):
                pages.extend(p for p in range(a, b + 1) if p not in pages)
        parts.append(pages)
    if not parts:
        raise PageRangeError("No pages given.")
    return parts


def parts_text(parts) -> str:
    """The text parse_parts reads back as *parts*: a part in a row is a range,
    one of scattered pages its pieces joined by '+'."""
    def one(pages):
        return ranges_text(pages).replace(", ", "+") if pages == sorted(pages) else \
            "+".join(str(p + 1) for p in pages)
    return ", ".join(one(list(p)) for p in parts)


def parts_from_cuts(total: int, cuts) -> list[list[int]]:
    """The parts a set of cut marks makes: a cut after page i (0-based) ends a
    part there; with no cut the whole document is one part."""
    parts, cur = [], []
    for i in range(total):
        cur.append(i)
        if i in cuts or i == total - 1:
            parts.append(cur)
            cur = []
    return parts


def cuts_of(parts, total: int) -> set[int] | None:
    """The cut marks that make *parts*, or None when they are not the whole
    document in order cut into runs (a scattered or missing page)."""
    flat = [p for part in parts for p in part]
    if flat != list(range(total)):
        return None
    return {part[-1] for part in parts[:-1]}


def take_part(parts, pages) -> list[list[int]]:
    """*parts* with *pages* made a part of their own (in page order), taken out
    of the parts they were in; a part left empty goes.  It goes where its
    first page's part was."""
    pages = sorted(set(pages))
    if not pages:
        return [list(p) for p in parts]
    taken = set(pages)
    out, placed = [], False
    for part in parts:
        if not placed and pages[0] in part:
            out.append(pages)
            placed = True
        rest = [p for p in part if p not in taken]
        if rest:
            out.append(rest)
    if not placed:
        out.append(pages)
    return out


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
