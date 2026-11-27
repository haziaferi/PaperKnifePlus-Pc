"""PDF Tools: repair a damaged file; sanitise, flatten, remove blank pages
(owner, 2026-10-18: Repair stays apart from Compress, and gains these three).

Every tool writes the file whole with garbage collection (garbage=4 with
clean and deflate: garbage=2/3 alone is quadratic, tests/test_save_settings.py),
so what it removed does not stay readable inside the file."""
from __future__ import annotations

import re

import pymupdf as fitz

from ..job_queue import atomic_output

_SAVE = dict(deflate=True, garbage=4, clean=True)
_JS = re.compile(r"/S\s*/JavaScript\b")
_LAUNCH = re.compile(r"/S\s*/Launch\b")


def repair_pdf(doc, out: str) -> bool:
    """Write a fresh, consistent copy of *doc* (closed here) to *out*.
    Returns True when MuPDF had to rebuild a broken xref to open it."""
    # MuPDF rebuilds a broken xref while opening; the garbage/clean save
    # then writes a fresh, consistent file from what it recovered.
    with atomic_output(out) as tmp, doc:
        repaired = doc.is_repaired
        doc.save(tmp, **_SAVE)
    return repaired


_REF = re.compile(r"^\s*(\d+)\s+0\s+R\s*$")
_ACTION_KEYS = ("A", "AA", "OpenAction")


def _holds(doc, kind: str, value: str, pattern) -> bool:
    """The key's value holds an action matching *pattern*, inline or in the
    object it points to."""
    if kind == "null" or not value:
        return False
    m = _REF.match(value) if kind == "xref" else None
    if m:
        try:
            value = doc.xref_object(int(m.group(1)), compressed=True)
        except Exception:
            return False
    return bool(pattern.search(value))


def _drop_actions(doc, pattern) -> int:
    """Set every A / AA / OpenAction key whose action matches *pattern* to
    null, in every object (catalog, pages, links, fields); the save's garbage
    collection then drops the actions themselves.  Returns how many went.
    (MuPDF's scrub(javascript=True) leaves a catalog's inline OpenAction
    script: measured 2026-10-18.)"""
    n = 0
    for x in range(1, doc.xref_length()):
        for key in _ACTION_KEYS:
            try:
                kind, value = doc.xref_get_key(x, key)
            except Exception:
                break               # a free or unreadable object holds nothing
            if _holds(doc, kind, value, pattern):
                doc.xref_set_key(x, key, "null")
                n += 1
    return n


def _attachment_annots(doc) -> int:
    return sum(1 for page in doc for a in page.annots()
               if a.type[0] == fitz.PDF_ANNOT_FILE_ATTACHMENT)


def sanitise_pdf(doc, out: str, *, javascript: bool = True, embedded: bool = True,
                 xmp: bool = True, actions: bool = True) -> dict[str, int]:
    """Write *doc* (closed here) to *out* without the parts chosen, keeping
    what the pages show: JavaScript (scripts of the document, its links and
    fields), embedded files (attachments and file-attachment comments), the
    XMP metadata, links that run actions (launch a program or a file).
    Returns how many of each were found: {"javascript", "embedded", "xmp",
    "actions"} (xmp 0 or 1)."""
    found = {"javascript": 0, "embedded": 0, "xmp": 0, "actions": 0}
    with atomic_output(out) as tmp, doc:
        if javascript:
            found["javascript"] = _drop_actions(doc, _JS)
            cat = doc.pdf_catalog()
            if doc.xref_get_key(cat, "Names/JavaScript")[0] != "null":
                doc.xref_set_key(cat, "Names/JavaScript", "null")     # the document's scripts
                found["javascript"] += 1
        if embedded:
            found["embedded"] = doc.embfile_count() + _attachment_annots(doc)
        if xmp:
            found["xmp"] = int(bool(doc.get_xml_metadata().strip()))
        if actions:
            for page in doc:
                for link in page.get_links():
                    # By its action, not get_links' kind: MuPDF 1.28 reports a
                    # launch of a file as LINK_GOTOR (measured 2026-10-18).
                    xref = link.get("xref") or 0
                    if xref and _LAUNCH.search(doc.xref_object(xref, compressed=True)):
                        page.delete_link(link)
                        found["actions"] += 1
            # A launch anywhere else: run when the file opens, by a field, ...
            found["actions"] += _drop_actions(doc, _LAUNCH)
        doc.scrub(attached_files=embedded, embedded_files=embedded, javascript=javascript,
                  xml_metadata=xmp, clean_pages=False, hidden_text=False, metadata=False,
                  redactions=False, remove_links=False, reset_fields=False,
                  reset_responses=False, thumbnails=False)
        doc.save(tmp, **_SAVE)
    return found


def flatten_pdf(doc, out: str, *, comments: bool = True, fields: bool = True) -> dict[str, int]:
    """Write *doc* (closed here) to *out* with its comments and / or form
    fields drawn into the pages, no longer editable.  Returns how many were
    flattened: {"comments", "fields"}."""
    found = {"comments": 0, "fields": 0}
    with atomic_output(out) as tmp, doc:
        for page in doc:
            if comments:
                found["comments"] += sum(1 for _a in page.annots())
            if fields:
                found["fields"] += sum(1 for _w in page.widgets())
        doc.bake(annots=comments, widgets=fields)
        doc.save(tmp, **_SAVE)
    return found


def _white(fill) -> bool:
    return fill is not None and all(c >= 0.99 for c in fill)


# A page that holds images (a scan) is blank when, rendered, nothing on it
# stands out from the paper.  Measured 2026-11-27 on simulated scans at 200 and
# 300 DPI, colour and grey (docs/blank-scans-2026-11-27.md): empty paper, cream
# or recycled paper, text showing through from the back and a 1 % edge shadow
# all count 0 pixels; the smallest content, a single 9 pt "x", counts 14.  A
# few specks of dust can count as many as that small mark, so a dusty page is
# kept: a blank page left in is harmless, a page with a mark removed is not.
_SCAN_DPI = 72          # render resolution of the look (13 ms a page)
_SCAN_CROP = 0.02       # each edge left out: a scanner's shadow along the sheet
_SCAN_DIFF = 40         # grey levels from the paper that make a pixel a mark
_SCAN_MARKS = 4         # more marked pixels than this: the page holds something
_SCAN_PAPER = 160       # a page darker than this overall is not empty paper


def _shows_only_paper(page) -> bool:
    """True when the rendered page is one even light tone (paper) with at most
    _SCAN_MARKS pixels standing out from it, darker or lighter."""
    from PIL import Image
    pix = page.get_pixmap(matrix=fitz.Matrix(_SCAN_DPI / 72, _SCAN_DPI / 72),
                          colorspace=fitz.csGRAY, alpha=False)
    im = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    cy, cx = int(pix.height * _SCAN_CROP), int(pix.width * _SCAN_CROP)
    hist = im.crop((cx, cy, pix.width - cx, pix.height - cy)).histogram()
    half, run, paper = sum(hist) / 2, 0, 255
    for value, n in enumerate(hist):
        run += n
        if run >= half:
            paper = value
            break
    if paper < _SCAN_PAPER:
        return False
    marks = sum(hist[:max(0, paper - _SCAN_DIFF)]) + sum(hist[paper + _SCAN_DIFF + 1:])
    return marks <= _SCAN_MARKS


def is_blank(page) -> bool:
    """No text, no drawing that shows (a white fill with no outline does
    not), no comment and no form field; and when it holds images, they show
    only empty paper (_shows_only_paper), as the back of a scanned sheet does."""
    if page.get_text("text").strip():
        return False
    if page.first_annot is not None or page.first_widget is not None:
        return False
    for d in page.get_drawings():
        if d.get("color") is not None or not _white(d.get("fill")):
            return False
    if page.get_images(full=False):
        return _shows_only_paper(page)
    return True


def is_scan(page) -> bool:
    """The page holds images (blank_pages' question names such pages apart)."""
    return bool(page.get_images(full=False))


def blank_pages(doc, stop=None) -> list[int]:
    """The 0-based numbers of *doc*'s blank pages (is_blank)."""
    out = []
    for i, page in enumerate(doc):
        if stop is not None and stop.is_set():
            break
        if is_blank(page):
            out.append(i)
    return out


def remove_pages(doc, out: str, pages) -> int:
    """Write *doc* (closed here) to *out* without *pages* (0-based), with
    what belongs to the document kept (organise.rearrange).  Returns the
    number of pages removed."""
    from .organise import rearrange
    gone = set(pages)
    keep = [i for i in range(len(doc)) if i not in gone]
    if not keep:
        raise ValueError("A PDF needs at least one page: keep one or more.")
    with atomic_output(out) as tmp, doc:
        rearrange(doc, keep)
        doc.save(tmp, **_SAVE)
    return len(gone)
