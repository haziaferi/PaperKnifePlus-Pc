"""PDF -> document and document -> PDF conversions, and the shared page helpers."""
from __future__ import annotations
import html
import importlib.util as _ilu
import io
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageOps

from ..job_queue import atomic_output
from ..pages import render


def _pkg(name): return _ilu.find_spec(name) is not None


_HAS_DOCX     = _pkg("docx")
_HAS_PPTX     = _pkg("pptx")
_HAS_OPENPYXL = _pkg("openpyxl")

FORMATS = ["TXT", "HTML", "XML", "RTF", "DOCX", "PPTX", "XLSX", "PNG", "JPEG"]
# format -> (pip package, installed)
NEEDS = {
    "DOCX": ("python-docx", _HAS_DOCX),
    "PPTX": ("python-pptx", _HAS_PPTX),
    "XLSX": ("openpyxl",    _HAS_OPENPYXL),
}

# Characters XML 1.0 forbids; python-docx and openpyxl refuse strings holding them.
_XML_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")
_STORY_CSS   = "pre { white-space: pre-wrap; font-size: 11pt; }"
_MARGIN      = (36, 36, -36, -36)


class Cancelled(Exception):
    """Raised inside atomic_output on Cancel so the partial file is discarded."""


class NoText(ValueError):
    """The PDF has no text layer to write as plain text."""

    def __init__(self):
        super().__init__("This PDF has no text to extract. A scanned page holds only an "
                         "image: run OCR on it first.")


def unused_path(path: str) -> str:
    """*path*, or *path* with -2, -3 … before its extension if a file is there."""
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(path):
        path = f"{stem}-{n}{ext}"
        n += 1
    return path


def require(fmt: str) -> None:
    lib, installed = NEEDS[fmt]
    if not installed:
        raise RuntimeError(f"{lib} not installed.\nRun: pip install {lib}")


def pages_to_zip(path, doc, dpi, fmt, quality, stop, progress) -> None:
    """Write every page of *doc* into a ZIP at *path* as PNG or JPEG images."""
    total = len(doc)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, page in enumerate(doc):
            if stop.is_set():
                raise Cancelled
            progress((i + 1) / total)
            pix = render(page, dpi / 72.0)
            if fmt == "JPEG":
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=quality)
                zf.writestr(f"page_{i + 1:04d}.jpg", buf.getvalue())
            else:
                zf.writestr(f"page_{i + 1:04d}.png", pix.tobytes("png"))


def image_page(doc, path) -> None:
    """Append a page sized to the image at *path*, upright, transparency flattened onto white."""
    with Image.open(path) as src:
        im = ImageOps.exif_transpose(src)
        if src.format == "JPEG" and src.getexif().get(0x0112, 1) == 1:
            data = Path(path).read_bytes()        # already upright: embed without recompressing
        else:
            if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
                im = im.convert("RGBA")
                flat = Image.new("RGB", im.size, "white")
                flat.paste(im, mask=im.getchannel("A"))
                im = flat
            elif im.mode not in ("1", "L", "RGB"):
                im = im.convert("RGB")
            buf = io.BytesIO()
            im.save(buf, "PNG")
            data = buf.getvalue()
        w, h = im.size
    page = doc.new_page(width=w, height=h)
    page.insert_image(page.rect, stream=data)


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp", ".gif")


def images_to_pdf(paths, out: str, stop, progress=None) -> bool:
    """Write one page per image in *paths*, in order, to a PDF at *out*.
    Returns False (and leaves *out* untouched) if *stop* was set."""
    n = len(paths)
    with atomic_output(out) as tmp, fitz.open() as doc:
        for i, p in enumerate(paths):
            if stop.is_set():
                return False
            image_page(doc, p)
            if progress:
                progress((i + 1) / n)
        doc.save(tmp, deflate=True)
    return True


def text_story(text: str):
    return fitz.Story(html=f"<pre>{html.escape(text)}</pre>", user_css=_STORY_CSS)


def write_story(writer, story, page_rect, stop) -> bool:
    """Typeset *story* onto as many *page_rect* pages as it needs, inside the
    margins.  Returns False when the story cannot be laid out on pages."""
    where = page_rect + _MARGIN
    last = None
    while True:
        dev = writer.begin_page(page_rect)
        more, filled = story.place(where)
        story.draw(dev)
        writer.end_page()
        if not more or stop.is_set():
            return True
        # An element that cannot be split and is taller than the page (a long
        # table row) makes place() return more forever without consuming it;
        # it shows as the same overflowing area page after page.  A paragraph
        # margin overflows the area by a few points while the text still flows.
        filled = fitz.Rect(filled)
        if filled == last and filled.y1 - where.y1 > where.height * 0.05:
            return False
        last = filled


def rtf_escape(text: str) -> str:
    out = []
    for ch in text:
        if ch in "\\{}":
            out.append("\\" + ch)
        elif ord(ch) < 128:
            out.append(ch)
        else:
            b = ch.encode("utf-16-le")
            for i in range(0, len(b), 2):
                unit = int.from_bytes(b[i:i + 2], "little", signed=True)
                out.append(f"\\u{unit}?")
    return "".join(out)


def pdf_to_doc(doc, fmt: str, out: str, stop, progress, dpi: int = 150,
               quality: int = 92) -> bool:
    """Convert *doc* (closed here) to *fmt* at *out*.  Returns False if cancelled,
    in which case nothing is written."""
    try:
        with atomic_output(out) as tmp, doc:
            total = len(doc)

            def step(i):
                if stop.is_set():
                    raise Cancelled
                progress((i + 1) / total)

            if fmt == "TXT":
                parts = []
                for i, page in enumerate(doc):
                    step(i)
                    parts.append(page.get_text())
                    if i < total - 1:
                        parts.append("\n\n── Page Break ──\n\n")
                if not any(p.strip() for p in parts[::2]):
                    raise NoText
                Path(tmp).write_text("".join(parts), encoding="utf-8")

            elif fmt == "HTML":
                html_parts = ['<!DOCTYPE html>\n<html>\n<head>',
                              '<meta charset="utf-8">',
                              '<style>body{font-family:sans-serif;max-width:900px;margin:auto}',
                              '.page{border-bottom:1px solid #ccc;padding-bottom:2em;'
                              'margin-bottom:2em}</style>', '</head>\n<body>\n']
                for i, page in enumerate(doc):
                    step(i)
                    html_parts.append(f'<div class="page" id="page-{i+1}">\n')
                    html_parts.append(page.get_text("html"))
                    html_parts.append("</div>\n")
                html_parts.append("</body>\n</html>")
                Path(tmp).write_text("".join(html_parts), encoding="utf-8")

            elif fmt == "XML":
                parts = ['<?xml version="1.0" encoding="utf-8"?>\n<document>\n']
                for i, page in enumerate(doc):
                    step(i)
                    # get_text("xml") is already one <page id="pageN"> element, no prolog
                    parts.append(page.get_text("xml"))
                parts.append("</document>")
                Path(tmp).write_text("".join(parts), encoding="utf-8")

            elif fmt == "RTF":
                rtf = [r'{\rtf1\ansi\ansicpg1252\deff0',
                       r'{\fonttbl{\f0\froman\fcharset0 Times New Roman;}}',
                       r'\f0\fs22 ']
                for i, page in enumerate(doc):
                    step(i)
                    for line in page.get_text().splitlines():
                        rtf.append(rtf_escape(line) + r"\par" + "\n")
                    if i < total - 1:
                        rtf.append(r"\page" + "\n")
                rtf.append("}")
                Path(tmp).write_bytes("".join(rtf).encode("ascii"))

            elif fmt == "DOCX":
                require(fmt)
                from docx import Document as _DocxDoc
                wdoc = _DocxDoc()
                for i, page in enumerate(doc):
                    step(i)
                    for block in page.get_text("dict")["blocks"]:
                        if block.get("type") != 0:
                            continue
                        txt = " ".join(
                            "".join(s.get("text", "") for s in line.get("spans", []))
                            for line in block.get("lines", []))
                        txt = _XML_ILLEGAL.sub("", txt)
                        if txt.strip():
                            wdoc.add_paragraph(txt)
                    if i < total - 1:
                        wdoc.add_page_break()
                wdoc.save(tmp)

            elif fmt == "PPTX":
                require(fmt)
                from pptx import Presentation as _PptxPrs
                scale = dpi / 72.0
                prs   = _PptxPrs()
                p0    = doc[0]
                prs.slide_width  = int(p0.rect.width  * 12700)
                prs.slide_height = int(p0.rect.height * 12700)
                blank = prs.slide_layouts[6]
                sw, sh = prs.slide_width, prs.slide_height
                for i, page in enumerate(doc):
                    step(i)
                    pix  = render(page, scale)
                    buf  = io.BytesIO(pix.tobytes("png"))
                    slide = prs.slides.add_slide(blank)
                    # Pages of another size or orientation than page 1 are fitted, not stretched.
                    fit  = min(sw / page.rect.width, sh / page.rect.height)
                    w, h = int(page.rect.width * fit), int(page.rect.height * fit)
                    slide.shapes.add_picture(buf, (sw - w) // 2, (sh - h) // 2, w, h)
                prs.save(tmp)

            elif fmt == "XLSX":
                require(fmt)
                import openpyxl as _openpyxl
                wb = _openpyxl.Workbook()
                wb.remove(wb.active)
                for i, page in enumerate(doc):
                    step(i)
                    ws = wb.create_sheet(f"Page {i+1}")
                    for row_i, line in enumerate(page.get_text().splitlines(), 1):
                        cell = ws.cell(row=row_i, column=1, value=_XML_ILLEGAL.sub("", line))
                        cell.data_type = "s"      # text such as "=..." must not become a formula
                wb.save(tmp)

            elif fmt in ("PNG", "JPEG"):
                pages_to_zip(tmp, doc, dpi, fmt, quality, stop, progress)
    except Cancelled:
        return False
    return True


def doc_to_pdf(src: str, fmt: str, out: str, stop) -> list[str] | None:
    """Convert the *fmt* file *src* to a PDF at *out*.  Returns the notes on
    fallbacks that changed what was typeset, or None if cancelled."""
    A4 = fitz.paper_rect("A4")
    notes: list[str] = []

    if fmt == "PPTX":
        require(fmt)
        from pptx import Presentation as _PptxPrs
        prs = _PptxPrs(src)
        with fitz.open() as nd:
            for slide in prs.slides:
                if stop.is_set():
                    return None
                lines = []
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        for para in shape.text_frame.paragraphs:
                            lines.append(para.text)
                page = nd.new_page(width=A4.width, height=A4.height)
                page.insert_htmlbox(A4, "<br>".join(html.escape(ln) for ln in lines))
            if stop.is_set():
                return None
            with atomic_output(out) as tmp:
                nd.save(tmp, deflate=True)

    elif fmt in ("PNG", "JPEG"):
        with fitz.open() as nd:
            image_page(nd, src)
            with atomic_output(out) as tmp:
                nd.save(tmp, deflate=True)

    else:
        stories = []          # (Story, page rect)
        if fmt == "TXT":
            text = Path(src).read_text(encoding="utf-8", errors="replace")
            stories.append((text_story(text), A4))

        elif fmt == "HTML":
            html_src = Path(src).read_text(encoding="utf-8", errors="replace")
            # The archive lets relative <img>/<link> paths resolve next to the file.
            stories.append((fitz.Story(html=html_src,
                                       archive=fitz.Archive(str(Path(src).parent))), A4))

        elif fmt == "XML":
            import xml.etree.ElementTree as ET
            try:
                root = ET.parse(src).getroot()
                text = " ".join(root.itertext())
            except ET.ParseError as e:
                text = Path(src).read_text(encoding="utf-8", errors="replace")
                notes.append(f"The XML could not be parsed ({e}), "
                             "so the file was typeset as raw text, tags included.")
            stories.append((text_story(text), A4))

        elif fmt == "RTF":
            raw = Path(src).read_text(encoding="latin-1", errors="replace")
            try:
                from striprtf.striprtf import rtf_to_text
            except ImportError:
                text = raw
                notes.append("striprtf is not installed (pip install striprtf), "
                             "so the RTF markup was typeset as raw text.")
            else:
                text = rtf_to_text(raw)
            stories.append((text_story(text), A4))

        elif fmt == "DOCX":
            require(fmt)
            from docx import Document as _DocxDoc
            from docx.table import Table as _DocxTable
            from docx.text.paragraph import Paragraph as _DocxPara
            wdoc  = _DocxDoc(src)
            parts = []
            # Walk the body in document order so tables stay where they are.
            for el in wdoc.element.body.iterchildren():
                tag = el.tag.rsplit("}", 1)[-1]
                if tag == "p":
                    para  = _DocxPara(el, wdoc)
                    style = para.style.name if para.style is not None else ""
                    text  = html.escape(para.text) or "&#160;"
                    if style == "Title" or style == "Heading 1":
                        parts.append(f"<h1>{text}</h1>")
                    elif style == "Heading 2":
                        parts.append(f"<h2>{text}</h2>")
                    elif style.startswith("Heading"):
                        parts.append(f"<h3>{text}</h3>")
                    else:
                        parts.append(f"<p>{text}</p>")
                elif tag == "tbl":
                    rows = "".join(
                        "<tr>" + "".join(f"<td>{html.escape(c.text)}</td>"
                                         for c in row.cells) + "</tr>"
                        for row in _DocxTable(el, wdoc).rows)
                    parts.append(f"<table>{rows}</table>")
            stories.append((fitz.Story(
                html="".join(parts),
                user_css="table { border-collapse: collapse; } "
                         "td { border: 1px solid #888; padding: 2px 4px; }"), A4))

        elif fmt == "XLSX":
            require(fmt)
            import openpyxl as _openpyxl
            wb   = _openpyxl.load_workbook(src, data_only=True)
            LAND = fitz.paper_rect("A4-L")
            for ws in wb.worksheets:
                rows = ws.iter_rows(values_only=True)
                text = "\n".join("\t".join("" if c is None else str(c) for c in row)
                                 for row in rows)
                stories.append((text_story(text), LAND))

        try:
            with atomic_output(out) as tmp:
                writer = fitz.DocumentWriter(tmp)
                try:
                    for story, rect in stories:
                        # Raised here, not in write_story, so no traceback
                        # frame keeps the writer (and its open file) alive.
                        if not write_story(writer, story, rect, stop):
                            raise RuntimeError(
                                "The document contains an element, such as a table "
                                "row, that is taller than a page and cannot be split "
                                "across pages.")
                        if stop.is_set():
                            raise Cancelled
                finally:
                    writer.close()
                    # The file stays open until the writer object is freed,
                    # and os.replace in atomic_output fails while it is.
                    del writer
        except Cancelled:
            return None

    # Stop is checked only before the output is committed: once *out* has
    # been written or replaced, the conversion is reported, Cancel or not.
    return notes


@dataclass
class Extracted:
    count: int        # images written
    scanned: int      # unique image xrefs looked at
    failed: int       # images that could not be decoded


def extract_images(doc, out_dir: str, fmt: str, min_px: int, stop, progress) -> Extracted | None:
    """Write every embedded image of *doc* (closed here) at least *min_px* on both
    sides into *out_dir*, as "Original", "PNG" or "JPEG".  None if cancelled."""
    seen, count, failed = set(), 0, 0
    total = len(doc)
    with doc:
        for pg_i, page in enumerate(doc):
            if stop.is_set():
                return None
            progress((pg_i + 1) / total)
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                if xref in seen:
                    continue
                seen.add(xref)
                # Only decoding counts as a failed image; a write error (disk
                # full, a locked file) is the job's error.
                try:
                    base = doc.extract_image(xref)
                    w, h = base["width"], base["height"]
                    if w < min_px or h < min_px:
                        continue
                    data = base["image"]
                    ext  = base["ext"]
                    if fmt == "PNG":
                        img = Image.open(io.BytesIO(data))
                        if img.mode not in ("1", "L", "LA", "I", "P", "RGB", "RGBA"):
                            img = img.convert("RGB")      # PNG cannot store CMYK
                        buf = io.BytesIO()
                        img.save(buf, "PNG")
                        data = buf.getvalue()
                        ext  = "png"
                    elif fmt == "JPEG":
                        img = Image.open(io.BytesIO(data)).convert("RGB")
                        buf = io.BytesIO()
                        img.save(buf, "JPEG", quality=92)
                        data = buf.getvalue()
                        ext  = "jpg"
                except Exception:
                    failed += 1
                    continue
                # An image of another PDF extracted here may have the same xref.
                fname = unused_path(os.path.join(out_dir, f"img_{xref:05d}.{ext}"))
                with atomic_output(fname) as tmp:
                    Path(tmp).write_bytes(data)
                count += 1
    return Extracted(count, len(seen), failed)
