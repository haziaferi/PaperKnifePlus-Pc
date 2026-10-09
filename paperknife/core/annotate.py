"""Add one annotation of a given kind to a page."""
from __future__ import annotations

import pymupdf as fitz

KINDS = ("highlight", "underline", "strikeout", "rect", "line", "note", "freetext")
# text markup kind -> the fitz.Page method that adds it
_MARKUP = {"highlight": "add_highlight_annot", "underline": "add_underline_annot",
           "strikeout": "add_strikeout_annot"}


def add(page, kind: str, p0, p1, color, opacity: float, text: str = ""):
    """Add a *kind* annotation to *page* from page point *p0* to *p1* (the rectangle
    they span; a line runs from one to the other; a note sits at *p0*).  *color* is
    RGB in 0-1; *opacity* 0-1 applies to all but notes and text boxes; *text* is a
    note's or text box's content.  Returns the annotation, or None for an unknown kind."""
    rect = fitz.Rect(p0[0], p0[1], p1[0], p1[1]).normalize()
    ann = None
    if kind in _MARKUP:
        ann = getattr(page, _MARKUP[kind])(rect)
        ann.set_colors(stroke=color)
        ann.set_opacity(opacity)
        ann.update()
    elif kind == "rect":
        ann = page.add_rect_annot(rect)
        # A 4-number colour is CMYK; transparency comes from set_opacity.
        ann.set_colors(stroke=color, fill=color)
        ann.set_opacity(opacity)
        ann.update()
    elif kind == "line":
        ann = page.add_line_annot(fitz.Point(p0), fitz.Point(p1))
        ann.set_colors(stroke=color)
        ann.set_opacity(opacity)
        ann.update()
    elif kind == "note":
        ann = page.add_text_annot(fitz.Point(p0), text or "Note")
        ann.set_colors(stroke=color)
        ann.update()
    elif kind == "freetext":
        ann = page.add_freetext_annot(rect, text or "Text", fontsize=11,
                                      fill_color=(1, 1, 1), text_color=color)
        ann.update()
    return ann


def by_xref(page, xref):
    return next((a for a in page.annots() if a.xref == xref), None)
