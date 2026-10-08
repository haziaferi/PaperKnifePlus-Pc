"""Redaction: cut line art under each box, remove what MuPDF leaves, scrub
the redacted phrases from metadata, bookmarks, attachments and fields."""
from __future__ import annotations
import re

import pymupdf as fitz

from ..lineart import cut_line_art, residual

_INFO_KEYS = ("title", "author", "subject", "keywords", "creator", "producer")
# Annotation text a reader sees; the other info keys are dates, ids and icon names.
_ANNOT_TEXT_KEYS = ("content", "title", "subject")
# A line under a drawn box shorter than this (a page number, a year suffix)
# would match far too much elsewhere in the document.
_MIN_BOX_PHRASE = 4


def redact_page(doc: fitz.Document, pno: int, rects, fill) -> str:
    """Destroy everything under rects (unrotated page space) on page pno.

    fill is an RGB tuple, or None to leave the boxes unpainted.  Returns how line
    art was handled: "cut" at the box edge; "whole" (drawings a box touches removed
    entirely, when MuPDF still saw line art in a box after cutting); or "image"
    (the page replaced by a picture of itself, when neither could empty the boxes).
    """
    page = doc[pno]
    # apply_redactions removes only the redact annots themselves; a note or a
    # form field under a box would keep showing (and storing) the content.
    for annot in list(page.annots()):
        if any(annot.rect.intersects(r) for r in rects):
            page.delete_annot(annot)
    for widget in list(page.widgets()):
        if any(widget.rect.intersects(r) for r in rects):
            page.delete_widget(widget)
    # The page thumbnail is a picture of the unredacted page.
    doc.xref_set_key(page.xref, "Thumb", "null")
    # MuPDF keeps or drops whole paths; cut them at the box edge first, in place.
    # Should MuPDF still see line art in a box (a stream read differently),
    # go back to the original content and let MuPDF drop every path it touches.
    contents = doc.xref_get_key(page.xref, "Contents")
    mode, graphics, unsafe = "cut", fitz.PDF_REDACT_LINE_ART_NONE, []
    try:
        unsafe = cut_line_art(page, rects).unsafe
        left = residual(page, rects)
    except Exception:                   # a stream this module cannot read at all
        left = True
    if left:
        doc.xref_set_key(page.xref, "Contents", contents[1])
        mode, graphics = "whole", fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED
    for r in rects:
        page.add_redact_annot(r, fill=fill if fill is not None else False)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS, graphics=graphics)
    # MuPDF's own removal misses soft-mask groups, and nothing removes the data of
    # a mesh shading: last resort, the page becomes a picture of itself.
    if unsafe or (mode == "whole" and residual(doc[pno], rects)):
        _page_to_image(doc, pno)
        mode = "image"
    return mode


def _page_to_image(doc: fitz.Document, pno: int, dpi: int = 200) -> None:
    """Replace page pno by a picture of it.  Its old resources go too, so nothing
    the page drew survives in the file once it is saved with garbage collection."""
    page = doc[pno]
    rotation = page.rotation
    page.set_rotation(0)
    pix = page.get_pixmap(dpi=dpi, annots=False)
    xref = doc.get_new_xref()
    doc.update_object(xref, "<<>>")
    doc.update_stream(xref, b"")
    doc.xref_set_key(page.xref, "Contents", f"{xref} 0 R")
    doc.xref_set_key(page.xref, "Resources", "<<>>")
    page = doc[pno]
    page.insert_image(page.rect, pixmap=pix)
    page.set_rotation(rotation)


def scrub_secrets(doc, secrets: dict[str, bool]) -> list[str]:
    """Remove every redacted phrase from the places apply_redactions does not touch.

    Returns the names of the places that were changed.
    """
    if not secrets:
        return []
    # A phrase taken from under a drawn box must not cut a longer word apart.
    pats = [re.compile(rf"(?<!\w){re.escape(s)}(?!\w)" if whole else re.escape(s),
                       re.IGNORECASE)
            for s, whole in secrets.items()]

    def hit(text) -> bool:
        return bool(text) and any(p.search(text) for p in pats)

    def strip(text: str) -> str:
        for p in pats:
            text = p.sub("", text)
        return text

    removed = []
    meta = doc.metadata or {}
    if any(hit(meta.get(k)) for k in _INFO_KEYS):
        doc.set_metadata({k: strip(meta.get(k) or "") for k in _INFO_KEYS})
        removed.append("document properties")
    if hit(doc.get_xml_metadata()):
        doc.del_xml_metadata()
        removed.append("XMP metadata")

    toc = doc.get_toc(simple=False)
    if any(hit(item[1]) for item in toc):
        for item in toc:
            item[1] = strip(item[1])
        doc.set_toc(toc)
        removed.append("bookmarks")

    for name in doc.embfile_names():
        info = doc.embfile_info(name)
        body = doc.embfile_get(name)
        texts = [name, info.get("filename"), info.get("ufilename"), info.get("description"),
                 body.decode("utf-8", "ignore")]
        # Any binary decodes to some UTF-16 text; only a marked UTF-16 file is text.
        if body[:2] in (b"\xff\xfe", b"\xfe\xff"):
            texts.append(body.decode("utf-16", "ignore"))
        if any(hit(t) for t in texts):
            doc.embfile_del(name)
            removed.append(f"attachment '{name}'")

    notes = fields = 0
    for page in doc:
        for annot in list(page.annots()):
            if any(hit(annot.info.get(k)) for k in _ANNOT_TEXT_KEYS):
                page.delete_annot(annot)
                notes += 1
        for widget in list(page.widgets()):
            if widget.field_type == fitz.PDF_WIDGET_TYPE_TEXT and hit(widget.field_value):
                widget.field_value = strip(widget.field_value)
                widget.update()
                fields += 1
            elif hit(str(widget.field_value)) or hit(widget.field_label):
                page.delete_widget(widget)
                fields += 1
    if notes:
        removed.append(f"{notes} annotation(s)")
    if fields:
        removed.append(f"{fields} form field(s)")
    return removed
