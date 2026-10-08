"""OCR: find Tesseract, read the words of rendered pages, and add them to the
PDF as an invisible text layer (or typeset them as a text-only PDF)."""
from __future__ import annotations
import html
import importlib.util as _ilu
import os
import shutil

import pymupdf as fitz
from PIL import Image

from ..job_queue import atomic_output
from ..pages import render

HAS_OCR  = _ilu.find_spec("pytesseract") is not None
MIN_CONF = 30
# Where the UB-Mannheim installer puts Tesseract; it does not add itself to PATH.
TESS_DIRS = (("ProgramFiles", "Tesseract-OCR"), ("ProgramFiles(x86)", "Tesseract-OCR"),
             ("LOCALAPPDATA", r"Programs\Tesseract-OCR"))


def tesseract():
    """pytesseract, pointed at the Tesseract binary: PATH first, then its install folders."""
    import pytesseract
    pt = pytesseract.pytesseract
    if pt.tesseract_cmd == "tesseract" and not shutil.which("tesseract"):
        for var, sub in TESS_DIRS:
            base = os.environ.get(var)
            if base and os.path.isfile(exe := os.path.join(base, sub, "tesseract.exe")):
                pt.tesseract_cmd = exe
                break
    return pytesseract


def ocr_words(img, lang: str, scale: float) -> list[tuple[fitz.Rect, str]]:
    """Tesseract words in *img* (a page rendered at *scale*) as (rect, text) in page.rect space."""
    pytesseract = tesseract()
    data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
    to_page = fitz.Matrix(1 / scale, 1 / scale)
    words = []
    for text, conf, x, y, w, h in zip(data["text"], data["conf"], data["left"],
                                      data["top"], data["width"], data["height"],
                                      strict=True):
        text = text.strip()
        if text and float(conf) >= MIN_CONF:
            words.append((fitz.Rect(x, y, x + w, y + h) * to_page, text))
    return words


def add_text_layer(page: fitz.Page, words) -> None:
    """Add *words* ((rect, text) in page.rect space) to *page* as invisible, searchable text."""
    if not words:
        return
    if page.rotation:
        # Text placed on a rotated page lands in unrotated space, and
        # remove_rotation() shifts the content of a cropped page; derotating
        # the uncropped page and re-applying the crop keeps both right.
        crop = page.cropbox
        page.set_cropbox(page.mediabox)
        mat = page.rotation_matrix
        page.remove_rotation()
        page.set_cropbox((crop * mat) & page.mediabox)
    layer = fitz.open()
    lp = layer.new_page(width=page.rect.width, height=page.rect.height)
    tw = fitz.TextWriter(lp.rect)
    font = fitz.Font("helv")      # TextWriter falls back to MuPDF's Noto fonts for other scripts
    for rect, text in words:
        tw.append(fitz.Point(rect.x0, rect.y1), text, font=font,
                  fontsize=max(1, rect.height * 0.85))
    tw.write_text(lp, render_mode=3)
    layer.subset_fonts()
    # TextWriter ignores a cropbox offset on the target page; show_pdf_page honours it.
    page.show_pdf_page(page.rect, layer, 0)
    layer.close()


def ocr_pdf(doc, out: str, lang: str, dpi: int, text_only: bool, stop, progress,
            on_page=None) -> int | None:
    """OCR every page of *doc* (closed here) rendered at *dpi* and write *out*:
    the original pages with an invisible text layer, or with *text_only* one
    A4 page of plain text per page.  *on_page(n, total)* is called before page
    n (1-based) is read.  Returns the number of pages, or None if cancelled,
    writing nothing.  Raises RuntimeError when Tesseract cannot be found."""
    pytesseract = tesseract()

    try:
        pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        doc.close()
        raise RuntimeError(
            "Tesseract not found on PATH or in Program Files\\Tesseract-OCR.\n"
            "Install it from: https://github.com/UB-Mannheim/tesseract/wiki") from None

    total = len(doc)
    scale = dpi / 72.0
    # doc is closed before the replace, so the output may be the input file.
    with atomic_output(out) as tmp, doc, fitz.open() as nd:
        for pg_i, page in enumerate(doc):
            if stop.is_set():
                return None
            if on_page is not None:
                on_page(pg_i + 1, total)
            progress((pg_i + 1) / total)

            pix = render(page, scale)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            if text_only:
                text = pytesseract.image_to_string(img, lang=lang)
                A4   = fitz.paper_rect("A4")
                np   = nd.new_page(width=A4.width, height=A4.height)
                np.insert_htmlbox(A4,
                                  f"<pre>{html.escape(text)}</pre>",
                                  css="pre { font-size: 10pt; }")
            else:
                add_text_layer(page, ocr_words(img, lang, scale))

        if text_only:
            nd.save(tmp, deflate=True)
        else:
            # Merges the fonts each page's text layer brings, at a cost that
            # grows linearly (garbage=3 grows with the square of the pages).
            doc.save(tmp, garbage=4, deflate=True, clean=True)
    return total
