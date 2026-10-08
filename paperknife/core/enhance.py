"""Compress, watermark and normalise: the PDF work of the Enhance tools."""
from __future__ import annotations
import math

import pymupdf as fitz

from ..job_queue import atomic_output

_COMPRESS_DPI = {"medium": 150, "aggressive": 96}

PAGE_SIZES = {
    "A4": (595, 842), "A3": (842, 1191), "A5": (420, 595),
    "Letter": (612, 792), "Legal": (612, 1008), "Tabloid": (792, 1224),
}


def _image_rewrite_options(dpi: int):
    # rewrite_images() hard-codes FZ_SUBSAMPLE_AVERAGE, which only divides by
    # whole factors (a 360-DPI image lands at 180, not 150); bicubic hits the
    # target exactly.  Bitonal images are left alone.
    opts = fitz.mupdf.PdfImageRewriterOptions()
    opts.recompress_when = fitz.mupdf.FZ_RECOMPRESS_WHEN_SMALLER
    for kind in ("color_lossless", "color_lossy", "gray_lossless", "gray_lossy"):
        setattr(opts, f"{kind}_image_recompress_method", fitz.mupdf.FZ_RECOMPRESS_JPEG)
        setattr(opts, f"{kind}_image_recompress_quality", "80")
        setattr(opts, f"{kind}_image_subsample_method", fitz.mupdf.FZ_SUBSAMPLE_BICUBIC)
        setattr(opts, f"{kind}_image_subsample_threshold", dpi + 1)
        setattr(opts, f"{kind}_image_subsample_to", dpi)
    return opts


# Every function here takes an open document and closes it before the output
# is moved into place, so *out* may be the input file itself.

def compress_pdf(doc, out: str, level: str) -> None:
    """Light: clean + deflate.  Medium/aggressive: also resample embedded
    images above 150/96 DPI down to that DPI; page content is kept."""
    with atomic_output(out) as tmp, doc:
        dpi = _COMPRESS_DPI.get(level)
        if dpi:
            doc.rewrite_images(options=_image_rewrite_options(dpi))
        doc.save(tmp, deflate=True, garbage=4, clean=True)


def watermark_pdf(doc, out, text, size, opacity, color, stop, progress=None):
    """Stamp *text* at 45° through the centre of every page.  Returns *out*,
    or None when *stop* was set."""
    with atomic_output(out) as tmp, doc:
        total = len(doc)
        for i, page in enumerate(doc):
            if stop.is_set():
                return None
            r = page.rect
            # A 45° line of length L and height fs spans (L + fs) / sqrt(2) on
            # both axes; shrink the font until that fits inside the page.
            per_pt = fitz.get_text_length(text, fontname="helv", fontsize=1)
            fit = min(r.width, r.height) * 0.9 * math.sqrt(2) / (per_pt + 1)
            fs = min(size, fit)
            length = per_pt * fs
            # insert_text works in unrotated page space, so place the centre
            # there and add the page's /Rotate to keep the stamp at 45° on screen.
            centre = fitz.Point(r.width / 2, r.height / 2) * page.derotation_matrix
            page.insert_text(
                fitz.Point(centre.x - length / 2, centre.y + fs * 0.35),
                text, fontname="helv", fontsize=fs, color=color,
                fill_opacity=opacity, stroke_opacity=opacity,
                morph=(centre, fitz.Matrix(45 + page.rotation)),
            )
            if progress:
                progress((i + 1) / total)
        doc.save(tmp, deflate=True)
    return out


def normalise_pdf(doc, out: str, size: str, orient: str, stretch: bool, stop,
                  progress) -> bool:
    """Redraw every page of *doc* onto a *size* page (a PAGE_SIZES key) in
    *orient* ("Portrait", "Landscape" or "Keep original"), fitted or, with
    *stretch*, filling it.  Returns False if cancelled, writing nothing."""
    tw, th = PAGE_SIZES[size]
    if orient == "Landscape":
        tw, th = th, tw
    pages = len(doc)
    with atomic_output(out) as tmp, doc, fitz.open() as nd:
        for page in doc:
            if stop.is_set():
                return False    # nothing written: atomic_output drops the file
            progress((page.number + 1) / pages)
            pw, ph = page.rect.width, page.rect.height
            if orient == "Keep original":
                ftw, fth = (tw, th) if pw <= ph else (th, tw)
            else:
                ftw, fth = tw, th
            np = nd.new_page(width=ftw, height=fth)
            if stretch:
                clip = fitz.Rect(0, 0, ftw, fth)
            else:
                sx = ftw / pw
                sy = fth / ph
                sc = min(sx, sy)
                ox = (ftw - pw * sc) / 2
                oy = (fth - ph * sc) / 2
                clip = fitz.Rect(ox, oy, ox + pw * sc, oy + ph * sc)
            np.show_pdf_page(clip, doc, page.number, keep_proportion=not stretch)
        nd.save(tmp, deflate=True)
    return True
