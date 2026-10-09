"""Redaction: cut line art under each box, remove what MuPDF leaves, scrub
the redacted phrases from metadata, bookmarks, attachments and fields."""
from __future__ import annotations
import io
import re
import zipfile

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


FILLS = {"Black": (0, 0, 0), "White": (1, 1, 1)}


def find_phrase(doc: fitz.Document, needle: str, stop=None, progress=None):
    """Every match of *needle* on every page, as (page number, rect, needle) boxes
    to redact; None when *stop* was set (a cancelled search marks nothing: half
    the matches would look like all of them).  progress(fraction) after each page."""
    found, total = [], len(doc)
    for pno in range(total):
        if stop is not None and stop.is_set():
            return None
        # search_for ignores case; for redaction over-marking is the safe side
        # (Find & Replace needs exact case and searches the characters itself).
        found += [(pno, rect, needle) for rect in doc[pno].search_for(needle)]
        if progress is not None:
            progress((pno + 1) / total)
    return found


def apply_boxes(doc: fitz.Document, pending, fill, stop=None, progress=None,
                modes: dict | None = None, secrets: dict | None = None):
    """Redact the pending boxes, (page number, rect in unrotated page space,
    search phrase or None), one page at a time through redact_page.

    *modes* (page number -> how its line art went) and *secrets* (phrase ->
    match whole words only, True for text taken from under a drawn box) are
    filled as each page is done, so a caller whose *stop* was set part-way knows
    which pages are redacted; the boxes of the pages not done stay to be applied.
    Returns (modes, secrets)."""
    modes = {} if modes is None else modes
    secrets = {} if secrets is None else secrets
    by_page: dict[int, list[fitz.Rect]] = {}
    for pno, r, _ in pending:
        by_page.setdefault(pno, []).append(r)
    pages = len(by_page)
    for i, (pno, rects) in enumerate(by_page.items()):
        if stop is not None and stop.is_set():
            break
        for pg, r, phrase in pending:
            if pg != pno:
                continue
            if phrase:
                secrets[phrase] = False
            else:
                # What a drawn box covered, so scrub_secrets can find it outside the page.
                for ln in doc[pno].get_textbox(r).splitlines():
                    if len(ln.strip()) >= _MIN_BOX_PHRASE:
                        secrets.setdefault(ln.strip(), True)
        modes[pno] = redact_page(doc, pno, rects, fill)
        if progress is not None:
            progress((i + 1) / pages)
    return modes, secrets


def merge_secrets(into: dict[str, bool], found: dict[str, bool]) -> None:
    """Add the phrases of one apply_boxes run to those kept for the save: a
    phrase searched for (match anywhere) wins over the same text under a box."""
    for phrase, whole_words in found.items():
        if not whole_words:
            into[phrase] = False
        else:
            into.setdefault(phrase, True)


# A PDF string token: a literal (one level of nested parentheses) or a hex string.
_PDF_STRING = rb"\((?:\\.|[^\\()]|\((?:\\.|[^\\()])*\))*\)|<[0-9A-Fa-f\s]*>"
# Marked-content properties that carry text a reader or a screen reader shows.
_MC_TEXT = re.compile(rb"(/(?:ActualText|Alt|E|T)\s*)(" + _PDF_STRING + rb")", re.S)
_ESCAPES = {b"n": 10, b"r": 13, b"t": 9, b"b": 8, b"f": 12}
_ATTACHMENT_TEXT_LIMIT = 64 * 1024 * 1024     # read at most this much of a zipped attachment


# What MuPDF raises for an object it cannot parse (FzErrorSyntax and kin).
_BROKEN = (fitz.mupdf.FzErrorBase, RuntimeError, ValueError)


def _keys(doc, x: int) -> list[str]:
    """The keys of object *x*; none for a free or broken object, which holds no
    text a reader can show either."""
    try:
        return doc.xref_get_keys(x)
    except _BROKEN:
        return []


def _is_form(doc, x: int) -> bool:
    try:
        return doc.xref_is_stream(x) and doc.xref_get_key(x, "Subtype") == ("name", "/Form")
    except _BROKEN:
        return False


def _pdf_string_text(raw: bytes) -> str:
    """The text of one PDF string token as _PDF_STRING matched it."""
    if raw.startswith(b"<"):
        h = re.sub(rb"\s", b"", raw[1:-1])
        data = bytes.fromhex((h + b"0" * (len(h) % 2)).decode())
    else:
        body, out, i = raw[1:-1], bytearray(), 0
        while i < len(body):
            c = body[i:i + 1]
            if c != b"\\" or i + 1 >= len(body):
                out += c
                i += 1
                continue
            n = body[i + 1:i + 2]
            octal = re.match(rb"[0-7]{1,3}", body[i + 1:])
            if n in _ESCAPES:
                out.append(_ESCAPES[n])
                i += 2
            elif octal:
                out.append(int(octal.group(), 8) & 255)
                i += 1 + len(octal.group())
            elif n in b"\r\n":
                i += 2                          # a line continuation
            else:
                out += n
                i += 2
        data = bytes(out)
    if data[:2] == b"\xfe\xff":
        return data[2:].decode("utf-16-be", "ignore")
    return data.decode("latin-1")


def _attachment_texts(body: bytes) -> list[str]:
    """What an attachment says, as far as it can be read: its bytes as text, the
    members of a zip (.docx, .xlsx, .odt, .zip) and the text of a PDF."""
    texts = [body.decode("utf-8", "ignore")]
    # Any binary decodes to some UTF-16 text; only a marked UTF-16 file is text.
    if body[:2] in (b"\xff\xfe", b"\xfe\xff"):
        texts.append(body.decode("utf-16", "ignore"))
    if body[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                left = _ATTACHMENT_TEXT_LIMIT
                for m in z.infolist():
                    if left <= 0:
                        break
                    data = z.read(m)[:left]
                    left -= len(data)
                    texts.append(data.decode("utf-8", "ignore"))
        except (zipfile.BadZipFile, OSError, RuntimeError, ValueError):
            pass                                # not a readable zip: its bytes were checked
    if body[:5] == b"%PDF-":
        try:
            with fitz.open("pdf", body) as inner:
                texts += [p.get_text() for p in inner]
                texts += [v for v in (inner.metadata or {}).values() if v]
        except (RuntimeError, ValueError):
            pass                                # not a readable PDF: its bytes were checked
    return texts


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
        texts = [name, info.get("filename"), info.get("ufilename"), info.get("description"),
                 *_attachment_texts(doc.embfile_get(name))]
        if any(hit(t) for t in texts):
            doc.embfile_del(name)
            removed.append(f"attachment '{name}'")

    notes = fields = 0
    for page in doc:
        for annot in list(page.annots()):
            if annot.type[0] == fitz.PDF_ANNOT_FILE_ATTACHMENT:
                fi = annot.file_info
                texts = [fi.get("filename"), fi.get("description"), *_attachment_texts(annot.get_file())]
                if any(hit(t) for t in texts):
                    removed.append(f"attachment '{fi.get('filename')}'")
                    page.delete_annot(annot)
                    continue
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

    # Marked-content text (/ActualText, /Alt …) in page and form content streams:
    # apply_redactions removes the glyphs but keeps the BDC property strings.
    streams = {x for page in doc for x in page.get_contents()}
    streams |= {x for x in range(1, doc.xref_length()) if _is_form(doc, x)}
    marked = 0
    for x in sorted(streams):
        try:
            data = doc.xref_stream(x) or b""
        except _BROKEN:
            continue                            # an undecodable stream draws nothing either

        def blank(m):
            nonlocal marked
            if hit(_pdf_string_text(m.group(2))):
                marked += 1
                return m.group(1) + b"()"
            return m.group(0)
        new = _MC_TEXT.sub(blank, data)
        if new != data:
            doc.update_stream(x, new)
    if marked:
        removed.append(f"{marked} marked-content text(s)")

    # Every other string in the file: custom document-info keys, the structure
    # tree's /Alt and /ActualText, link and file names.
    info_xref = doc.xref_get_key(-1, "Info")
    info_xref = int(info_xref[1].split()[0]) if info_xref[0] == "xref" else 0
    info_hit = others = 0
    for x in range(1, doc.xref_length()):
        for key in _keys(doc, x):
            try:
                kind, value = doc.xref_get_key(x, key)
            except _BROKEN:
                continue
            if kind == "string" and hit(value):
                doc.xref_set_key(x, key, fitz.get_pdf_str(strip(value)))
                if x == info_xref:
                    info_hit += 1
                else:
                    others += 1
    if info_hit and "document properties" not in removed:
        removed.append("document properties")
    if others:
        removed.append(f"{others} other text string(s)")
    return removed
